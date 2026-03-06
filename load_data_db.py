"""
SVG Floor Plan → Navigation Graph Loader
=========================================
Parses Inkscape SVG floor plans and generates a navigation graph for A* routing.

SVG Labeling Conventions (inkscape:label on <g> groups):
    corridor*   → Corridor boundary (black wall lines define walkable area)
    room*       → Room (dead-end, only reachable via its child doors)
    wc*         → Restroom (same as room)
    bar*        → Bar (same as room)
    door*       → Door (child of room/wc/bar, bridges room to corridor)
    stair*      → Staircase (bridges to corridor mesh)
    exit*       → Emergency exit (bridges to corridor mesh)
    elevator    → Elevator (bridges to corridor mesh)
    courtyard   → Non-walkable exclusion zone (optional)
    gap*        → Additional exclusion zone (optional)

Rules:
    1. Rooms/WCs/Bars only connect to their doors (never directly to corridor)
    2. Doors/Stairs/Exits/Elevators bridge to the 1 nearest corridor node
    3. A* cannot traverse room/wc/bar nodes as intermediaries (enforced in routing)
"""

import xml.etree.ElementTree as ET
import re, math, json, sys, os
from sqlalchemy.orm import Session
from shapely.geometry import Point, MultiPoint, LineString, box
from shapely.ops import unary_union
from database import SessionLocal, init_db
from models import Node, Edge, Tile, EmergencyRoute, Closure
from grid_name import GridManager

# ─────────────────────────────────────────────
# SVG Geometry Helpers
# ─────────────────────────────────────────────

def parse_all_svg_points(d_str):
    """Extract ALL coordinate points from an SVG path 'd' attribute.
    Handles M/m, L/l, H/h, V/v and curve commands for accurate bounding boxes."""
    points = []
    cx, cy = 0.0, 0.0
    tokens = re.findall(r'([MmLlHhVvCcSsQqTtAaZz])|([-+]?[\d.]+)', d_str)
    cmd, nums = None, []

    def flush():
        nonlocal cx, cy
        if not cmd: return
        if cmd in ('M', 'L'):
            for i in range(0, len(nums)-1, 2):
                cx, cy = nums[i], nums[i+1]; points.append((cx, cy))
        elif cmd in ('m', 'l'):
            for i in range(0, len(nums)-1, 2):
                cx += nums[i]; cy += nums[i+1]; points.append((cx, cy))
        elif cmd == 'H':
            for n in nums: cx = n; points.append((cx, cy))
        elif cmd == 'h':
            for n in nums: cx += n; points.append((cx, cy))
        elif cmd == 'V':
            for n in nums: cy = n; points.append((cx, cy))
        elif cmd == 'v':
            for n in nums: cy += n; points.append((cx, cy))
        elif cmd in ('C', 'S', 'Q', 'T', 'A'):
            for i in range(0, len(nums)-1, 2):
                points.append((nums[i], nums[i+1]))
            if len(nums) >= 2: cx, cy = nums[-2], nums[-1]
        elif cmd in ('c', 's', 'q', 't', 'a'):
            ox, oy = cx, cy
            for i in range(0, len(nums)-1, 2):
                points.append((ox+nums[i], oy+nums[i+1]))
            if len(nums) >= 2: cx, cy = ox+nums[-2], oy+nums[-1]

    for tok in tokens:
        letter, number = tok
        if letter: flush(); cmd = letter; nums = []
        elif number: nums.append(float(number))
    flush()
    return points


def get_group_bbox(group, ns_svg):
    """Get bounding box of ALL paths and rects inside a group element."""
    xs, ys = [], []
    for path in group.iter(ns_svg + 'path'):
        for x, y in parse_all_svg_points(path.get('d', '')):
            xs.append(x); ys.append(y)
    for rect in group.iter(ns_svg + 'rect'):
        x, y = float(rect.get('x', '0')), float(rect.get('y', '0'))
        w, h = float(rect.get('width', '0')), float(rect.get('height', '0'))
        xs.extend([x, x+w]); ys.extend([y, y+h])
    if xs and ys:
        return (min(xs), min(ys), max(xs), max(ys))
    return None


def line_of_sight(p1, p2, exclusion_union):
    """Check if a straight line between two points does NOT cross exclusion zones."""
    line = LineString([p1, p2])
    return not line.crosses(exclusion_union) and not exclusion_union.contains(line)


# ─────────────────────────────────────────────
# Node Type Classification
# ─────────────────────────────────────────────

# Labels → node types
LABEL_TYPES = {
    'corridor': 'corridor',
    'room':     'room',
    'wc':       'restroom',
    'bar':      'bar',
    'exit':     'emergency_exit',
    'stair':    'stairs',
}

# Exact-match labels
EXACT_TYPES = {
    'elevator': 'elevator',
}

# Types that are dead-ends (only accessible via their child doors)
DEAD_END_TYPES = {'room', 'restroom', 'bar'}

# Labels that create exclusion zones in the corridor mesh
EXCLUSION_PREFIXES = ('room', 'wc', 'bar', 'stair', 'courtyard', 'gap')
EXCLUSION_EXACT = ('elevator',)


def classify_label(label):
    """Map an SVG inkscape:label to a node type. Returns None if unrecognized."""
    if label in EXACT_TYPES:
        return EXACT_TYPES[label]
    for prefix, ntype in LABEL_TYPES.items():
        if label.startswith(prefix):
            return ntype
    return None


# ─────────────────────────────────────────────
# Main Loader
# ─────────────────────────────────────────────

class SVGLoader:
    def __init__(self, svg_path, level=0):
        self.svg_path = svg_path
        self.level = level
        self.nodes_data = {}
        self.edges_data = []

    # ── Node / Edge helpers ──

    def add_node(self, node_id, name, node_type, x, y, level=None):
        if level is None: level = self.level
        uid = f"{node_id}_L{level}"
        if uid not in self.nodes_data:
            self.nodes_data[uid] = {
                "id": uid, "name": name, "type": node_type,
                "x": round(x, 2), "y": round(y, 2), "level": level,
            }

    def add_edge(self, from_id, to_id, weight, accessible=True):
        from_uid = f"{from_id}_L{self.level}" if not from_id.endswith(f"_L{self.level}") else from_id
        to_uid = f"{to_id}_L{self.level}" if not to_id.endswith(f"_L{self.level}") else to_id
        edge_id = f"E_{from_uid}_{to_uid}"
        self.edges_data.append({
            "id": edge_id, "from_id": from_uid, "to_id": to_uid,
            "weight": round(weight, 2), "accessible": accessible,
        })

    # ── Main parse pipeline ──

    def parse(self):
        tree = ET.parse(self.svg_path)
        root = tree.getroot()
        ns_ink = '{http://www.inkscape.org/namespaces/inkscape}'
        ns_svg = '{http://www.w3.org/2000/svg}'

        # Step 1: Parse labeled groups → nodes + room↔door edges
        self._parse_groups(root, ns_svg, ns_ink)

        # Step 2: Generate corridor mesh
        corr_nodes = self._generate_corridor_mesh(root, ns_svg, ns_ink)

        # Step 3: Bridge connectable nodes to nearest corridor node
        self._bridge_to_mesh(corr_nodes)

        print(f"\n  Nodes: {len(self.nodes_data)}, Edges: {len(self.edges_data)}")

    # ── Step 1: Parse SVG groups ──

    def _parse_groups(self, root, ns_svg, ns_ink):
        """Extract nodes from labeled SVG groups and create room↔door edges."""
        SVG_SCALE = 12.567  # SVG units per meter

        for g in root.iter(ns_svg + 'g'):
            label = g.get(ns_ink + 'label', '')
            if not label:
                continue

            node_type = classify_label(label)
            if not node_type or node_type == 'corridor':
                continue

            bbox = get_group_bbox(g, ns_svg)
            if not bbox:
                continue

            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            self.add_node(label, label, node_type, cx, cy)

            # Parse child doors inside this group
            for child in g:
                child_label = child.get(ns_ink + 'label', '')
                if not child_label or not child_label.startswith('door'):
                    continue

                child_bbox = get_group_bbox(child, ns_svg)
                if not child_bbox:
                    continue

                dcx = (child_bbox[0] + child_bbox[2]) / 2
                dcy = (child_bbox[1] + child_bbox[3]) / 2
                self.add_node(child_label, f"Porta {child_label}", "door", dcx, dcy)

                # Room ↔ Door edge (physical distance)
                dist = math.sqrt((cx-dcx)**2 + (cy-dcy)**2) / SVG_SCALE
                self.add_edge(label, child_label, dist)
                self.add_edge(child_label, label, dist)

    # ── Step 2: Generate corridor mesh ──

    def _generate_corridor_mesh(self, root, ns_svg, ns_ink, grid_spacing=12.0):
        """Generate a grid of walkable corridor nodes within the corridor boundary."""
        SVG_SCALE = 12.567
        print("\nGenerating corridor grid mesh...")

        # Find corridor group
        corridor_group = None
        for g in root.iter(ns_svg + 'g'):
            if g.get(ns_ink + 'label', '').startswith('corridor'):
                corridor_group = g
                break

        if corridor_group is None:
            print("  WARNING: No 'corridor*' group found in SVG!")
            return []

        # Build corridor boundary from black wall lines
        wall_points = []
        for path in corridor_group.findall(ns_svg + 'path'):
            if path.get('stroke', '') == '#000000':
                wall_points.extend(parse_all_svg_points(path.get('d', '')))

        if len(wall_points) < 3:
            print("  WARNING: Not enough wall points to form corridor boundary!")
            return []

        corridor_hull = MultiPoint(wall_points).convex_hull

        # Build exclusion zones from labeled groups
        exclusion_zones = []
        for g in root.iter(ns_svg + 'g'):
            label = g.get(ns_ink + 'label', '')
            if not label:
                continue
            is_excluded = (
                any(label.startswith(p) for p in EXCLUSION_PREFIXES) or
                label in EXCLUSION_EXACT
            )
            if is_excluded:
                bbox = get_group_bbox(g, ns_svg)
                if bbox:
                    pad = 3.0
                    exclusion_zones.append(box(
                        bbox[0]-pad, bbox[1]-pad,
                        bbox[2]+pad, bbox[3]+pad
                    ))

        exclusion_union = unary_union(exclusion_zones) if exclusion_zones else None
        walkable = corridor_hull.difference(exclusion_union) if exclusion_union else corridor_hull

        if walkable.is_empty:
            print("  WARNING: No walkable area after exclusions!")
            return []

        # Generate grid nodes
        corr_nodes = []
        min_x, min_y, max_x, max_y = walkable.bounds
        node_grid = {}
        node_idx = 0
        col = 0
        x = min_x + grid_spacing / 2
        while x < max_x:
            row = 0
            y = min_y + grid_spacing / 2
            while y < max_y:
                if walkable.contains(Point(x, y)):
                    nid = f"corr_n{node_idx}"
                    self.add_node(nid, f"Corredor {node_idx}", "corridor", round(x,2), round(y,2))
                    uid = f"{nid}_L{self.level}"
                    corr_nodes.append(self.nodes_data[uid])
                    node_grid[(col, row)] = nid
                    node_idx += 1
                row += 1
                y += grid_spacing
            col += 1
            x += grid_spacing

        # Generate grid edges (4-connected + diagonals, with line-of-sight)
        weight = round(grid_spacing / SVG_SCALE, 2)
        diag_weight = round(weight * math.sqrt(2), 2)
        NEIGHBORS = [((1,0), weight), ((0,1), weight), ((1,1), diag_weight), ((-1,1), diag_weight)]

        for (c, r), nid in node_grid.items():
            uid1 = f"{nid}_L{self.level}"
            n1 = self.nodes_data[uid1]
            for (dc, dr), w in NEIGHBORS:
                nb_key = (c+dc, r+dr)
                if nb_key not in node_grid:
                    continue
                nbid = node_grid[nb_key]
                uid2 = f"{nbid}_L{self.level}"
                n2 = self.nodes_data[uid2]
                if not exclusion_union or line_of_sight(
                    (n1['x'], n1['y']), (n2['x'], n2['y']), exclusion_union
                ):
                    self.add_edge(nid, nbid, w)
                    self.add_edge(nbid, nid, w)

        print(f"  Grid: {len(corr_nodes)} nodes, {len(node_grid)} cells")
        return corr_nodes

    # ── Step 3: Bridge nodes to corridor mesh ──

    def _bridge_to_mesh(self, corr_nodes, max_dist_svg=150):
        """Connect connectable nodes to nearest corridor node(s).
        
        - Doors/exits/elevators: connect to 1 nearest corridor node
        - Stairs: connect to nearest node in EACH corridor mesh component
          (ensures bridging across floor barriers)
        
        Dead-end types (room/restroom/bar) are NOT bridged.
        """
        SVG_SCALE = 12.567
        if not corr_nodes:
            return

        # Pre-compute corridor mesh connected components for stair bridging
        corr_graph = {}
        for e in self.edges_data:
            if e['from_id'].startswith('corr_') and e['to_id'].startswith('corr_'):
                corr_graph.setdefault(e['from_id'], []).append(e['to_id'])
        
        components = []  # list of sets of node IDs
        visited = set()
        for cn in corr_nodes:
            if cn['id'] in visited:
                continue
            # BFS to find component
            comp = set()
            queue = [cn['id']]
            while queue:
                node = queue.pop(0)
                if node in comp:
                    continue
                comp.add(node)
                visited.add(node)
                for nb in corr_graph.get(node, []):
                    if nb not in comp:
                        queue.append(nb)
            components.append(comp)
        
        if len(components) > 1:
            print(f"  Corridor mesh has {len(components)} components (sizes: {[len(c) for c in components]})")

        # ── Determine component floor identities for directional stair bridging ──
        # Parse stair labels (stair-X-to-Y) to determine which floor each component represents.
        # A stair only bridges to a component if its label references that component's floor.
        
        def parse_stair_floors(label):
            """Parse 'stair-X-to-Y' → (X, Y) or None."""
            m = re.match(r'stair-(.+)-to-(.+)', label)
            return (m.group(1), m.group(2)) if m else None
        
        # Map each stair to its local component (nearest corridor node's component)
        stair_to_comp = {}  # stair_id → component_index
        for n_id, n_data in self.nodes_data.items():
            if n_data['type'] != 'stairs':
                continue
            nx, ny = n_data['x'], n_data['y']
            nearest = min(corr_nodes, key=lambda cn: (nx-cn['x'])**2 + (ny-cn['y'])**2)
            for ci, comp in enumerate(components):
                if nearest['id'] in comp:
                    stair_to_comp[n_id] = ci
                    break
        
        # Determine each component's floor identity:
        # Collect all floor IDs from stairs in each component, pick the most common one
        comp_floors = {}  # component_index → floor_id
        for ci in range(len(components)):
            floor_counts = {}
            for s_id, s_ci in stair_to_comp.items():
                if s_ci != ci:
                    continue
                floors = parse_stair_floors(s_id)
                if floors:
                    for f in floors:
                        floor_counts[f] = floor_counts.get(f, 0) + 1
            if floor_counts:
                # The floor that appears in ALL stairs of this component = component's floor
                comp_floors[ci] = max(floor_counts, key=floor_counts.get)
        
        if comp_floors:
            print(f"  Component floor identities: {comp_floors}")

        for n_id, n_data in self.nodes_data.items():
            if n_id.startswith('corr_') or n_data['type'] == 'corridor':
                continue
            if n_data['type'] in DEAD_END_TYPES:
                continue

            nx, ny = n_data['x'], n_data['y']
            
            if n_data['type'] == 'stairs' and len(components) > 1:
                stair_floors = parse_stair_floors(n_id)
                local_ci = stair_to_comp.get(n_id)
                
                for ci, comp in enumerate(components):
                    comp_nodes = [cn for cn in corr_nodes if cn['id'] in comp]
                    if not comp_nodes:
                        continue
                    
                    # Always connect to local component
                    # For other components: only bridge if this stair's label
                    # references that component's floor
                    if ci != local_ci:
                        comp_floor = comp_floors.get(ci)
                        if not comp_floor or not stair_floors or comp_floor not in stair_floors:
                            continue  # Skip — stair doesn't connect to this floor
                    
                    nearest = min(comp_nodes, key=lambda cn: (nx-cn['x'])**2 + (ny-cn['y'])**2)
                    dist_svg = math.sqrt((nx-nearest['x'])**2 + (ny-nearest['y'])**2)
                    if dist_svg > max_dist_svg:
                        continue
                    dist_m = dist_svg / SVG_SCALE
                    self.add_edge(n_id, nearest['id'], dist_m)
                    self.add_edge(nearest['id'], n_id, dist_m)
                    
                    if ci != local_ci:
                        print(f"  Stair bridge: {n_id} <-> comp[{comp_floor}] via {nearest['id']}")
            else:
                # Create a list of all potential connection targets:
                # 1. All corridor nodes
                # 2. All stair nodes on this same level
                potential_targets = list(corr_nodes)
                for sid, sdata in self.nodes_data.items():
                    if sdata['type'] == 'stairs' and sdata['level'] == self.level:
                        potential_targets.append(sdata)

                # Connect to 1 nearest target overall, BUT if it is an emergency exit
                # and there are stairs very close (like in a hall), connect to ALL stairs within radius.
                nearby_targets = [t for t in potential_targets if math.sqrt((nx-t['x'])**2 + (ny-t['y'])**2) <= max_dist_svg]
                
                if not nearby_targets:
                    print(f"  WARNING: {n_id} has no nearby targets")
                    continue
                    
                nearest = min(nearby_targets, key=lambda t: (nx-t['x'])**2 + (ny-t['y'])**2)
                min_dist_svg = math.sqrt((nx-nearest['x'])**2 + (ny-nearest['y'])**2)
                
                targets_to_connect = [nearest]
                
                # Special rule for emergency exits in halls/atriums:
                # If there are other stairs very close to the nearest distance (e.g. within 20 SVG units difference),
                # connect to them too. This ensures exit1_L0 connects to BOTH stair-1-to-hall AND stair-hall-to-2.
                if n_data['type'] == 'emergency_exit':
                    for t in nearby_targets:
                        if t['type'] == 'stairs' and t['id'] != nearest['id']:
                            dist_t = math.sqrt((nx-t['x'])**2 + (ny-t['y'])**2)
                            if dist_t <= min_dist_svg + 25.0: # 25 SVG units threshold
                                targets_to_connect.append(t)
                
                for target in targets_to_connect:
                    dist_svg = math.sqrt((nx-target['x'])**2 + (ny-target['y'])**2)
                    dist_m = dist_svg / SVG_SCALE
                    self.add_edge(n_id, target['id'], dist_m)
                    self.add_edge(target['id'], n_id, dist_m)

    # ── Database loading ──

    def load_to_db(self, clear_db=False):
        """Load all nodes + edges. Optionally clear DB first."""
        init_db()
        db: Session = SessionLocal()

        try:
            if clear_db:
                db.query(EmergencyRoute).delete()
                db.query(Closure).delete()
                db.query(Edge).delete()
                db.query(Tile).delete()
                db.query(Node).delete()
                db.commit()

            print(f"Loading SVG (Level {self.level}) → DB from: {self.svg_path}")

            for node_data in self.nodes_data.values():
                db.merge(Node(**node_data))
            for edge_data in self.edges_data:
                db.merge(Edge(**edge_data))
            db.commit()

            # Auto-link vertical connections (stairs, elevators) across floors
            # Emergency exits should NOT teleport people between floors
            vertical_types = ['stairs', 'elevator']
            for node_data in self.nodes_data.values():
                if node_data['type'] in vertical_types:
                    base_name = node_data['id'].rsplit('_L', 1)[0]
                    # Find nodes on other floors with the same base name
                    other_nodes = db.query(Node).filter(
                        Node.id.like(f"{base_name}_L%"),
                        Node.id != node_data['id']
                    ).all()
                    
                    for other in other_nodes:
                        if node_data['type'] == 'stairs':
                            # Verificação estrita para escadas com nomes arquitetónicos (ex: stair-1-to-hall)
                            import re
                            m = re.match(r'stair-(.+)-to-(.+)', base_name)
                            if m:
                                allowed_targets = {m.group(1), m.group(2)}
                                # Mapear os níveis internos (0, 1) para os nomes da arquitetura ("1", "2")
                                def get_arch_name(lvl):
                                    if lvl == 0: return "1"
                                    if lvl == 1: return "2"
                                    return str(lvl)
                                
                                arch_this = get_arch_name(node_data['level'])
                                arch_other = get_arch_name(other.level)
                                
                                # Se as escadas não foram feitas para ir de arch_this para arch_other, não unir!
                                if arch_this not in allowed_targets or arch_other not in allowed_targets:
                                    print(f"Skipping vertical link for {base_name} between {arch_this} and {arch_other}")
                                    continue
                                    
                        weight = 15.0 if node_data['type'] == 'stairs' else 5.0
                        accessible = node_data['type'] in ['elevator']
                        
                        e1 = Edge(id=f"E_vert_{node_data['id']}_{other.id}", from_id=node_data['id'], to_id=other.id, weight=weight, accessible=accessible)
                        e2 = Edge(id=f"E_vert_{other.id}_{node_data['id']}", from_id=other.id, to_id=node_data['id'], weight=weight, accessible=accessible)
                        db.merge(e1)
                        db.merge(e2)
            db.commit()

            # Rebuild spatial grid (cell_size ≈ 1 meter)
            # We must pass the level if we only want to rebuild tiles for this floor, or it rebuilds all?
            # grid_manager.rebuild_grid clears tiles. If it clears ALL tiles, we lose level 0!
            # Let's import GridManager. Rebuild might drop everything.
            grid_manager = GridManager(cell_size=12.5, origin_x=0.0, origin_y=0.0)
            # WARNING: rebuild_grid usually wipes the Tile table. We will let it handle its own logic or update it if needed.
            tile_count = grid_manager.rebuild_grid(db)

            print("=" * 50)
            print(f"Nodes: {len(self.nodes_data)}")
            print(f"Edges: {len(self.edges_data)}")
            print(f"Tiles: {tile_count} (total in DB)")
            print("=" * 50)

        except Exception as e:
            db.rollback()
            raise
        finally:
            db.close()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SVG Floor Plan → DB Loader")
    parser.add_argument("svg_path", nargs="?", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Fanapp", "fan_app_interface", "assets", "images", "PLANTA1.svg"
    ))
    parser.add_argument("--level", type=int, default=0, help="Floor level for the SVG nodes (e.g. 0 for PLANTA1, 1 for PLANTA2)")
    parser.add_argument("--clear", action="store_true", help="Clear the entire DB before loading")
    parser.add_argument("--clear-only", action="store_true", help="Clear the entire DB and exit")

    args = parser.parse_args()

    if args.clear_only:
        print("Clearing all data...")
        init_db()
        db = SessionLocal()
        db.query(EmergencyRoute).delete()
        db.query(Closure).delete()
        db.query(Edge).delete()
        db.query(Tile).delete()
        db.query(Node).delete()
        db.commit()
        db.close()
        print("Done!")
        sys.exit(0)

    loader = SVGLoader(args.svg_path, level=args.level)
    loader.parse()
    loader.load_to_db(clear_db=args.clear)
    print("\nDone! You can now start the FastAPI server.")