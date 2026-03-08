#!/usr/bin/env python3
"""
SVG Floor Plan to Navigation Graph Parser

Parses an Inkscape-labeled SVG floor plan and extracts:
- Rooms, WCs, bars, elevator, exits from labeled groups
- Door positions as connection points
- Corridor navigation nodes at hallway intersections
- Edges connecting everything into a navigation graph

Output: JSON compatible with Map-Service DB schema (Node, Edge)

Usage:
    python svg_to_graph.py PLANTA1(3).svg.txt --output output/
    python svg_to_graph.py PLANTA1(3).svg.txt --visualize
"""

import argparse
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET


# ============================================================
# Data Classes
# ============================================================

@dataclass
class BBox:
    """Bounding box of an SVG element group."""
    min_x: float = float('inf')
    min_y: float = float('inf')
    max_x: float = float('-inf')
    max_y: float = float('-inf')
    
    @property
    def center_x(self) -> float:
        return (self.min_x + self.max_x) / 2
    
    @property
    def center_y(self) -> float:
        return (self.min_y + self.max_y) / 2
    
    @property
    def width(self) -> float:
        return self.max_x - self.min_x
    
    @property
    def height(self) -> float:
        return self.max_y - self.min_y
    
    @property
    def is_valid(self) -> bool:
        return self.min_x < self.max_x and self.min_y < self.max_y
    
    def expand(self, x: float, y: float):
        self.min_x = min(self.min_x, x)
        self.min_y = min(self.min_y, y)
        self.max_x = max(self.max_x, x)
        self.max_y = max(self.max_y, y)
    
    def merge(self, other: 'BBox'):
        if other.is_valid:
            self.min_x = min(self.min_x, other.min_x)
            self.min_y = min(self.min_y, other.min_y)
            self.max_x = max(self.max_x, other.max_x)
            self.max_y = max(self.max_y, other.max_y)


@dataclass
class GraphNode:
    """A node in the navigation graph."""
    id: str
    name: str
    x: float
    y: float
    level: int = 0
    type: str = "normal"
    description: Optional[str] = None
    num_servers: Optional[int] = None
    service_rate: Optional[float] = None
    
    # Internal: label from SVG, not exported
    svg_label: str = ""
    
    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "level": self.level,
            "type": self.type,
            "description": self.description,
        }
        if self.num_servers is not None:
            d["num_servers"] = self.num_servers
        if self.service_rate is not None:
            d["service_rate"] = self.service_rate
        return d


@dataclass
class GraphEdge:
    """An edge in the navigation graph."""
    id: str
    from_id: str
    to_id: str
    weight: float
    accessible: bool = True
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "weight": round(self.weight, 2),
            "accessible": self.accessible,
        }


@dataclass
class LabeledSpace:
    """A labeled group extracted from the SVG."""
    label: str
    bbox: BBox
    door_bbox: Optional[BBox] = None
    door_label: Optional[str] = None
    space_type: str = "room"  # room, wc, bar, elevator, exit, enter


# ============================================================
# SVG Path Parsing
# ============================================================

def parse_svg_path_points(d: str) -> List[Tuple[float, float]]:
    """
    Extract coordinate points from an SVG path 'd' attribute.
    Handles M, m, L, l, H, h, V, v, Z, z and basic arc (a/A) commands.
    Returns a list of (x, y) absolute coordinates.
    """
    points = []
    current_x, current_y = 0.0, 0.0
    start_x, start_y = 0.0, 0.0
    
    # Tokenize: split by command letters, keeping the letter
    tokens = re.findall(r'[MmLlHhVvZzAaCcSsQqTt][^MmLlHhVvZzAaCcSsQqTt]*', d.strip())
    
    for token in tokens:
        cmd = token[0]
        params_str = token[1:].strip()
        
        # Parse numbers (handle negative numbers and comma-separated values)
        nums = re.findall(r'-?\d+\.?\d*(?:e[+-]?\d+)?', params_str)
        nums = [float(n) for n in nums]
        
        if cmd == 'M':  # Absolute moveto
            if len(nums) >= 2:
                current_x, current_y = nums[0], nums[1]
                start_x, start_y = current_x, current_y
                points.append((current_x, current_y))
                # Additional coordinate pairs are implicit lineto
                for i in range(2, len(nums) - 1, 2):
                    current_x, current_y = nums[i], nums[i + 1]
                    points.append((current_x, current_y))
                    
        elif cmd == 'm':  # Relative moveto
            if len(nums) >= 2:
                current_x += nums[0]
                current_y += nums[1]
                start_x, start_y = current_x, current_y
                points.append((current_x, current_y))
                for i in range(2, len(nums) - 1, 2):
                    current_x += nums[i]
                    current_y += nums[i + 1]
                    points.append((current_x, current_y))
                    
        elif cmd == 'L':  # Absolute lineto
            for i in range(0, len(nums) - 1, 2):
                current_x, current_y = nums[i], nums[i + 1]
                points.append((current_x, current_y))
                
        elif cmd == 'l':  # Relative lineto
            for i in range(0, len(nums) - 1, 2):
                current_x += nums[i]
                current_y += nums[i + 1]
                points.append((current_x, current_y))
                
        elif cmd == 'H':  # Absolute horizontal line
            for n in nums:
                current_x = n
                points.append((current_x, current_y))
                
        elif cmd == 'h':  # Relative horizontal line
            for n in nums:
                current_x += n
                points.append((current_x, current_y))
                
        elif cmd == 'V':  # Absolute vertical line
            for n in nums:
                current_y = n
                points.append((current_x, current_y))
                
        elif cmd == 'v':  # Relative vertical line
            for n in nums:
                current_y += n
                points.append((current_x, current_y))
                
        elif cmd in ('Z', 'z'):  # Close path
            current_x, current_y = start_x, start_y
            points.append((current_x, current_y))
            
        elif cmd == 'a':  # Relative arc (we just extract the endpoint)
            # Arc params: rx ry x-axis-rotation large-arc-flag sweep-flag dx dy
            if len(nums) >= 7:
                for i in range(0, len(nums) - 6, 7):
                    current_x += nums[i + 5]
                    current_y += nums[i + 6]
                    points.append((current_x, current_y))
                    
        elif cmd == 'A':  # Absolute arc
            if len(nums) >= 7:
                for i in range(0, len(nums) - 6, 7):
                    current_x = nums[i + 5]
                    current_y = nums[i + 6]
                    points.append((current_x, current_y))
    
    return points


def get_element_bbox(element, ns: dict) -> BBox:
    """Calculate bounding box of all paths in an SVG element (recursively)."""
    bbox = BBox()
    
    # Process direct path children
    for path in element.iter(f'{{{ns["svg"]}}}path'):
        d = path.get('d', '')
        if d:
            points = parse_svg_path_points(d)
            for px, py in points:
                bbox.expand(px, py)
    
    # Process line elements
    for line in element.iter(f'{{{ns["svg"]}}}line'):
        try:
            x1 = float(line.get('x1', 0))
            y1 = float(line.get('y1', 0))
            x2 = float(line.get('x2', 0))
            y2 = float(line.get('y2', 0))
            bbox.expand(x1, y1)
            bbox.expand(x2, y2)
        except (ValueError, TypeError):
            pass
    
    # Process rect elements
    for rect in element.iter(f'{{{ns["svg"]}}}rect'):
        try:
            x = float(rect.get('x', 0))
            y = float(rect.get('y', 0))
            w = float(rect.get('width', 0))
            h = float(rect.get('height', 0))
            bbox.expand(x, y)
            bbox.expand(x + w, y + h)
        except (ValueError, TypeError):
            pass
    
    return bbox


# ============================================================
# SVG Parser
# ============================================================

class SVGFloorPlanParser:
    """
    Parses an Inkscape-labeled SVG floor plan and generates
    a navigation graph (nodes + edges).
    """
    
    NS = {
        'svg': 'http://www.w3.org/2000/svg',
        'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
        'sodipodi': 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd',
    }
    
    # Map SVG label prefixes to node types
    LABEL_TYPE_MAP = {
        'room': 'corridor',   # Room POI — type "corridor" for generic, name carries label
        'wc': 'restroom',
        'bar': 'bar',
        'elevator': 'stairs',  # Reuse 'stairs' type for vertical transport
        'exit': 'emergency_exit',
        'enter': 'gate',
    }
    
    # Edge weight defaults (in abstract units, ~proportional to meters)
    WEIGHT_CORRIDOR = 5.0
    WEIGHT_DOOR = 2.0
    WEIGHT_ELEVATOR = 3.0
    
    def __init__(self, svg_path: str):
        self.svg_path = svg_path
        self.tree = ET.parse(svg_path)
        self.root = self.tree.getroot()
        
        # Parsed data
        self.labeled_spaces: List[LabeledSpace] = []
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, GraphEdge] = {}
        
        # SVG dimensions
        self.svg_width = float(self.root.get('width', 0))
        self.svg_height = float(self.root.get('height', 0))
        
        # Wall segments (black paths) for corridor detection
        self.wall_segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    
    def parse(self):
        """Full parsing pipeline."""
        print(f"📐 SVG dimensions: {self.svg_width:.1f} x {self.svg_height:.1f}")
        
        # Step 1: Extract labeled groups (rooms, doors, WCs, etc.)
        self._extract_labeled_groups()
        print(f"🏷️  Found {len(self.labeled_spaces)} labeled spaces")
        
        # Step 2: Extract wall segments (black paths)
        self._extract_walls()
        print(f"🧱 Found {len(self.wall_segments)} wall segments")
        
        # Step 3: Generate POI nodes from labeled groups
        self._generate_poi_nodes()
        
        # Step 4: Generate corridor nodes
        self._generate_corridor_nodes()
        
        # Step 5: Generate edges
        self._generate_edges()
        
        print(f"\n✅ Graph generated:")
        print(f"   Nodes: {len(self.nodes)}")
        print(f"   Edges: {len(self.edges)}")
        
        # Print breakdown
        type_counts = {}
        for n in self.nodes.values():
            type_counts[n.type] = type_counts.get(n.type, 0) + 1
        for t, c in sorted(type_counts.items()):
            print(f"   - {t}: {c}")
    
    def _extract_labeled_groups(self):
        """Find all <g> elements with inkscape:label attributes."""
        ink_label = f'{{{self.NS["inkscape"]}}}label'
        svg_g = f'{{{self.NS["svg"]}}}g'
        
        for group in self.root.iter(svg_g):
            label = group.get(ink_label, '')
            if not label:
                continue
            
            # Determine space type from label prefix
            space_type = None
            if label.startswith('room'):
                space_type = 'room'
            elif label.startswith('wc'):
                space_type = 'wc'
            elif label.startswith('bar'):
                space_type = 'bar'
            elif label == 'elevator':
                space_type = 'elevator'
            elif label.startswith('exit'):
                space_type = 'exit'
            elif label.startswith('enter'):
                space_type = 'enter'
            elif label.startswith('door'):
                # Doors at top level (not inside a room group) — standalone
                continue
            else:
                continue
            
            # Calculate bounding box of the entire group
            bbox = get_element_bbox(group, self.NS)
            
            if not bbox.is_valid:
                continue
            
            space = LabeledSpace(
                label=label,
                bbox=bbox,
                space_type=space_type,
            )
            
            # Look for door sub-groups
            for subgroup in group.findall(svg_g):
                sub_label = subgroup.get(ink_label, '')
                if sub_label.startswith('door') or sub_label.startswith('exit') or sub_label.startswith('enter'):
                    door_bbox = get_element_bbox(subgroup, self.NS)
                    if door_bbox.is_valid:
                        space.door_bbox = door_bbox
                        space.door_label = sub_label
            
            # Also check direct child paths with door labels
            svg_path = f'{{{self.NS["svg"]}}}path'
            for path_elem in group.findall(svg_path):
                path_label = path_elem.get(ink_label, '')
                if path_label.startswith('door') or path_label.startswith('exit') or path_label.startswith('enter'):
                    d = path_elem.get('d', '')
                    if d:
                        points = parse_svg_path_points(d)
                        if points:
                            door_bb = BBox()
                            for px, py in points:
                                door_bb.expand(px, py)
                            if door_bb.is_valid:
                                space.door_bbox = door_bb
                                space.door_label = path_label
            
            self.labeled_spaces.append(space)
            
            print(f"   {space_type:10s} | {label:15s} | "
                  f"center=({bbox.center_x:.1f}, {bbox.center_y:.1f}) | "
                  f"size=({bbox.width:.1f} x {bbox.height:.1f})"
                  f"{' | door=' + space.door_label if space.door_label else ''}")
    
    def _extract_walls(self):
        """Extract wall segments from black-stroked paths (not inside labeled groups)."""
        ink_label = f'{{{self.NS["inkscape"]}}}label'
        svg_path = f'{{{self.NS["svg"]}}}path'
        svg_g = f'{{{self.NS["svg"]}}}g'
        
        # Collect IDs of elements inside labeled groups (to exclude them)
        labeled_ids = set()
        for group in self.root.iter(svg_g):
            label = group.get(ink_label, '')
            if label and any(label.startswith(p) for p in ['room', 'wc', 'bar', 'elevator', 'exit', 'enter']):
                for elem in group.iter():
                    eid = elem.get('id', '')
                    if eid:
                        labeled_ids.add(eid)
        
        # Extract black path segments that are NOT inside labeled groups
        for path in self.root.iter(svg_path):
            stroke = path.get('stroke', '')
            eid = path.get('id', '')
            
            if stroke != '#000000':
                continue
            if eid in labeled_ids:
                continue
            
            d = path.get('d', '')
            if not d:
                continue
            
            points = parse_svg_path_points(d)
            
            # Create line segments from consecutive points
            for i in range(len(points) - 1):
                p1, p2 = points[i], points[i + 1]
                seg_len = math.dist(p1, p2)
                if seg_len > 1.0:  # Ignore tiny segments
                    self.wall_segments.append((p1, p2))
    
    def _generate_poi_nodes(self):
        """Create nodes for each labeled space (room, WC, bar, etc.)."""
        for space in self.labeled_spaces:
            label = space.label
            
            # Node type mapping
            node_type = self.LABEL_TYPE_MAP.get(space.space_type, 'normal')
            
            # Special handling for rooms — they're destinations, not navigation
            if space.space_type == 'room':
                node_type = 'normal'
            
            # Room node — place at room center
            room_node_id = f"POI-{label}"
            room_node = GraphNode(
                id=room_node_id,
                name=label,
                x=space.bbox.center_x,
                y=space.bbox.center_y,
                level=0,
                type=node_type,
                description=f"Sala {label}" if space.space_type == 'room' else label,
                svg_label=label,
            )
            
            # Add service info for WCs and bars
            if space.space_type == 'wc':
                room_node.num_servers = 4
                room_node.service_rate = 0.5
                room_node.description = f"WC {label}"
            elif space.space_type == 'bar':
                room_node.num_servers = 3
                room_node.service_rate = 0.4
                room_node.description = f"Bar {label}"
            elif space.space_type == 'elevator':
                room_node.description = "Elevador"
            elif space.space_type == 'exit':
                room_node.description = f"Saída {label}"
            elif space.space_type == 'enter':
                room_node.description = f"Entrada {label}"
            
            self.nodes[room_node_id] = room_node
            
            # Door node — place at door center (connection point)
            if space.door_bbox and space.door_bbox.is_valid:
                door_id = f"DOOR-{space.door_label or label}"
                door_node = GraphNode(
                    id=door_id,
                    name=f"Porta {space.door_label or label}",
                    x=space.door_bbox.center_x,
                    y=space.door_bbox.center_y,
                    level=0,
                    type='corridor',  # Doors act as corridor transition points
                    description=f"Porta de acesso a {label}",
                    svg_label=space.door_label or label,
                )
                self.nodes[door_id] = door_node
                
                # Edge: door ↔ room (bidirectional)
                dist = math.dist(
                    (door_node.x, door_node.y),
                    (room_node.x, room_node.y)
                )
                weight = max(self.WEIGHT_DOOR, dist * 0.3)
                
                e1_id = f"E-{door_id}-{room_node_id}"
                self.edges[e1_id] = GraphEdge(
                    id=e1_id,
                    from_id=door_id,
                    to_id=room_node_id,
                    weight=round(weight, 2),
                    accessible=True,
                )
                e2_id = f"E-{room_node_id}-{door_id}"
                self.edges[e2_id] = GraphEdge(
                    id=e2_id,
                    from_id=room_node_id,
                    to_id=door_id,
                    weight=round(weight, 2),
                    accessible=True,
                )
        
        print(f"📍 Generated {len(self.nodes)} POI + door nodes")
    
    def _generate_corridor_nodes(self):
        """
        Generate navigation nodes along corridors.
        
        Strategy:
        1. Find the main horizontal and vertical corridors by analyzing
           wall segment clusters
        2. Place nodes at corridor intersections
        3. Place nodes at regular intervals along corridors
        """
        # Separate walls into horizontal and vertical
        h_walls = []  # Mostly horizontal walls
        v_walls = []  # Mostly vertical walls
        
        for (x1, y1), (x2, y2) in self.wall_segments:
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            length = math.sqrt(dx*dx + dy*dy)
            
            if length < 5:
                continue
            
            if dx > dy * 2:  # Horizontal
                h_walls.append(((min(x1, x2), (y1 + y2) / 2), 
                                (max(x1, x2), (y1 + y2) / 2)))
            elif dy > dx * 2:  # Vertical
                v_walls.append((((x1 + x2) / 2, min(y1, y2)),
                                ((x1 + x2) / 2, max(y1, y2))))
        
        # Cluster horizontal walls by Y coordinate to find corridor centerlines
        corridor_ys = self._find_corridor_centerlines(h_walls, axis='y')
        corridor_xs = self._find_corridor_centerlines(v_walls, axis='x')
        
        print(f"🛤️  Detected {len(corridor_ys)} horizontal corridors, "
              f"{len(corridor_xs)} vertical corridors")
        
        # Generate corridor nodes at intersections and along corridors
        corridor_node_count = 0
        
        # Place nodes along each horizontal corridor
        for cy, (x_min, x_max) in corridor_ys:
            # Place nodes at regular intervals
            spacing = 20.0  # Node every ~20 SVG units
            x = x_min
            while x <= x_max:
                node_id = f"COR-H{corridor_node_count}"
                self.nodes[node_id] = GraphNode(
                    id=node_id,
                    name=f"Corredor H{corridor_node_count}",
                    x=round(x, 2),
                    y=round(cy, 2),
                    level=0,
                    type='corridor',
                )
                corridor_node_count += 1
                x += spacing
        
        # Place nodes along each vertical corridor
        for cx, (y_min, y_max) in corridor_xs:
            spacing = 20.0
            y = y_min
            while y <= y_max:
                node_id = f"COR-V{corridor_node_count}"
                self.nodes[node_id] = GraphNode(
                    id=node_id,
                    name=f"Corredor V{corridor_node_count}",
                    x=round(cx, 2),
                    y=round(y, 2),
                    level=0,
                    type='corridor',
                )
                corridor_node_count += 1
                y += spacing
        
        print(f"🛤️  Generated {corridor_node_count} corridor nodes")
    
    def _find_corridor_centerlines(self, walls, axis='y') -> List[Tuple[float, Tuple[float, float]]]:
        """
        Find corridor centerlines by clustering parallel walls.
        
        For horizontal corridors, cluster by Y coordinate:
        two horizontal walls close in Y but spanning the same X range
        form a corridor between them.
        
        Returns: list of (center_coord, (extent_min, extent_max))
        """
        if not walls:
            return []
        
        # Extract the perpendicular coordinate for clustering
        if axis == 'y':
            coords = [(w[0][1], min(w[0][0], w[1][0]), max(w[0][0], w[1][0])) for w in walls]
        else:
            coords = [(w[0][0], min(w[0][1], w[1][1]), max(w[0][1], w[1][1])) for w in walls]
        
        # Sort by the perpendicular coordinate
        coords.sort(key=lambda c: c[0])
        
        # Cluster walls that are close together (within 30 units = probable corridor width)
        corridors = []
        used = set()
        max_corridor_width = 30.0
        min_corridor_width = 3.0
        
        for i in range(len(coords)):
            if i in used:
                continue
            for j in range(i + 1, len(coords)):
                if j in used:
                    continue
                
                perp_dist = abs(coords[j][0] - coords[i][0])
                
                if perp_dist < min_corridor_width:
                    continue
                if perp_dist > max_corridor_width:
                    break
                
                # Check X overlap (they must span a similar range)
                overlap_min = max(coords[i][1], coords[j][1])
                overlap_max = min(coords[i][2], coords[j][2])
                overlap = overlap_max - overlap_min
                
                if overlap > 20:  # Significant overlap
                    center = (coords[i][0] + coords[j][0]) / 2
                    extent_min = max(coords[i][1], coords[j][1])
                    extent_max = min(coords[i][2], coords[j][2])
                    
                    corridors.append((center, (extent_min, extent_max)))
                    used.add(i)
                    used.add(j)
                    break
        
        # Deduplicate corridors that are very close
        if not corridors:
            return corridors
        
        corridors.sort(key=lambda c: c[0])
        merged = [corridors[0]]
        for c in corridors[1:]:
            if abs(c[0] - merged[-1][0]) < 5:  # Very close, merge
                # Extend the range
                merged[-1] = (
                    (merged[-1][0] + c[0]) / 2,
                    (min(merged[-1][1][0], c[1][0]), max(merged[-1][1][1], c[1][1]))
                )
            else:
                merged.append(c)
        
        return merged
    
    def _generate_edges(self):
        """
        Generate edges connecting all nodes.
        
        Strategy:
        1. Connect corridor nodes that are close and aligned
        2. Connect door nodes to nearest corridor nodes
        3. Ensure graph connectivity
        """
        # Get all corridor nodes
        corridor_nodes = [n for n in self.nodes.values() if n.type == 'corridor']
        door_nodes = [n for n in self.nodes.values() 
                      if n.id.startswith('DOOR-')]
        poi_nodes = [n for n in self.nodes.values() 
                     if n.id.startswith('POI-')]
        
        # 1. Connect adjacent corridor nodes (within ~25 units)
        max_corridor_dist = 30.0
        edge_count = len(self.edges)
        
        for i, n1 in enumerate(corridor_nodes):
            for n2 in corridor_nodes[i + 1:]:
                dist = math.dist((n1.x, n1.y), (n2.x, n2.y))
                if dist < max_corridor_dist:
                    eid1 = f"E-{n1.id}-{n2.id}"
                    eid2 = f"E-{n2.id}-{n1.id}"
                    if eid1 not in self.edges:
                        self.edges[eid1] = GraphEdge(
                            id=eid1, from_id=n1.id, to_id=n2.id,
                            weight=round(dist * 0.5, 2), accessible=True,
                        )
                        self.edges[eid2] = GraphEdge(
                            id=eid2, from_id=n2.id, to_id=n1.id,
                            weight=round(dist * 0.5, 2), accessible=True,
                        )
        
        corridor_edges = len(self.edges) - edge_count
        print(f"🔗 Generated {corridor_edges} corridor↔corridor edges")
        edge_count = len(self.edges)
        
        # 2. Connect each door node to the nearest corridor nodes
        for door in door_nodes:
            # Find closest corridor nodes
            nearby = []
            for cn in corridor_nodes:
                dist = math.dist((door.x, door.y), (cn.x, cn.y))
                nearby.append((dist, cn))
            
            nearby.sort(key=lambda x: x[0])
            
            # Connect to the 2 closest corridor nodes
            connected = 0
            for dist, cn in nearby[:3]:
                if dist < 50.0:  # Max distance to connect door to corridor
                    eid1 = f"E-{door.id}-{cn.id}"
                    eid2 = f"E-{cn.id}-{door.id}"
                    if eid1 not in self.edges:
                        weight = round(dist * 0.4, 2)
                        self.edges[eid1] = GraphEdge(
                            id=eid1, from_id=door.id, to_id=cn.id,
                            weight=weight, accessible=True,
                        )
                        self.edges[eid2] = GraphEdge(
                            id=eid2, from_id=cn.id, to_id=door.id,
                            weight=weight, accessible=True,
                        )
                        connected += 1
                if connected >= 2:
                    break
            
            # If no corridor node found nearby, connect to nearest POI door
            if connected == 0:
                for other_door in door_nodes:
                    if other_door.id == door.id:
                        continue
                    dist = math.dist((door.x, door.y), (other_door.x, other_door.y))
                    if dist < 60.0:
                        eid1 = f"E-{door.id}-{other_door.id}"
                        if eid1 not in self.edges:
                            weight = round(dist * 0.4, 2)
                            self.edges[eid1] = GraphEdge(
                                id=eid1, from_id=door.id, to_id=other_door.id,
                                weight=weight, accessible=True,
                            )
                            eid2 = f"E-{other_door.id}-{door.id}"
                            self.edges[eid2] = GraphEdge(
                                id=eid2, from_id=other_door.id, to_id=door.id,
                                weight=weight, accessible=True,
                            )
                            break
        
        door_edges = len(self.edges) - edge_count
        print(f"🚪 Generated {door_edges} door↔corridor edges")
        edge_count = len(self.edges)
        
        # 3. Connect orphan POI nodes (rooms without doors) directly to corridors
        for poi in poi_nodes:
            # Check if this POI is already connected via a door
            has_connection = any(
                e.from_id == poi.id or e.to_id == poi.id
                for e in self.edges.values()
            )
            if has_connection:
                continue
            
            # Connect to nearest corridor node
            nearby = []
            for cn in corridor_nodes:
                dist = math.dist((poi.x, poi.y), (cn.x, cn.y))
                nearby.append((dist, cn))
            
            if nearby:
                nearby.sort(key=lambda x: x[0])
                dist, cn = nearby[0]
                if dist < 80.0:
                    weight = round(dist * 0.4, 2)
                    eid1 = f"E-{poi.id}-{cn.id}"
                    eid2 = f"E-{cn.id}-{poi.id}"
                    self.edges[eid1] = GraphEdge(
                        id=eid1, from_id=poi.id, to_id=cn.id,
                        weight=weight, accessible=True,
                    )
                    self.edges[eid2] = GraphEdge(
                        id=eid2, from_id=cn.id, to_id=poi.id,
                        weight=weight, accessible=True,
                    )
        
        orphan_edges = len(self.edges) - edge_count
        print(f"🔌 Generated {orphan_edges} orphan POI→corridor edges")
        
        # 4. Ensure connectivity — connect disconnected components
        self._ensure_connectivity()
    
    def _ensure_connectivity(self):
        """BFS to find disconnected components and bridge them."""
        if not self.nodes:
            return
        
        # Build adjacency list
        adj = {nid: set() for nid in self.nodes}
        for e in self.edges.values():
            if e.from_id in adj and e.to_id in adj:
                adj[e.from_id].add(e.to_id)
                adj[e.to_id].add(e.from_id)
        
        # Find connected components via BFS
        visited = set()
        components = []
        
        for nid in self.nodes:
            if nid in visited:
                continue
            component = set()
            queue = [nid]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                component.add(current)
                for neighbor in adj.get(current, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)
            components.append(component)
        
        if len(components) <= 1:
            print(f"✅ Graph is fully connected ({len(components)} component)")
            return
        
        print(f"⚠️  Graph has {len(components)} disconnected components. Bridging...")
        
        # Sort components by size (largest first)
        components.sort(key=len, reverse=True)
        
        # Connect each smaller component to the largest
        main_component = components[0]
        bridges_added = 0
        
        for comp in components[1:]:
            # Find the closest pair of nodes between components
            best_dist = float('inf')
            best_pair = None
            
            for nid1 in comp:
                n1 = self.nodes[nid1]
                for nid2 in main_component:
                    n2 = self.nodes[nid2]
                    dist = math.dist((n1.x, n1.y), (n2.x, n2.y))
                    if dist < best_dist:
                        best_dist = dist
                        best_pair = (nid1, nid2)
            
            if best_pair:
                n1_id, n2_id = best_pair
                weight = round(best_dist * 0.4, 2)
                eid1 = f"E-BRIDGE-{n1_id}-{n2_id}"
                eid2 = f"E-BRIDGE-{n2_id}-{n1_id}"
                self.edges[eid1] = GraphEdge(
                    id=eid1, from_id=n1_id, to_id=n2_id,
                    weight=weight, accessible=True,
                )
                self.edges[eid2] = GraphEdge(
                    id=eid2, from_id=n2_id, to_id=n1_id,
                    weight=weight, accessible=True,
                )
                bridges_added += 1
                main_component.update(comp)
        
        print(f"🌉 Added {bridges_added} bridge edges to connect components")
    
    def export_json(self, output_path: str):
        """Export graph to JSON file compatible with Map-Service."""
        data = {
            "metadata": {
                "name": "Instituto - Piso 1",
                "source": os.path.basename(self.svg_path),
                "svg_width": self.svg_width,
                "svg_height": self.svg_height,
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
            },
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges.values()],
        }
        
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Exported to {output_path}")
        print(f"   {len(data['nodes'])} nodes, {len(data['edges'])} edges")
    
    def export_visualization(self, output_path: str):
        """
        Generate a simple SVG visualization overlay showing nodes and edges.
        Creates a new SVG with colored circles (nodes) and lines (edges).
        """
        svg_lines = [
            f'<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg width="{self.svg_width}" height="{self.svg_height}" '
            f'viewBox="0 0 {self.svg_width} {self.svg_height}" '
            f'xmlns="http://www.w3.org/2000/svg">',
            f'  <style>',
            f'    .edge {{ stroke: #888; stroke-width: 0.8; opacity: 0.5; }}',
            f'    .node-corridor {{ fill: #2196F3; }}',
            f'    .node-restroom {{ fill: #9C27B0; }}',
            f'    .node-bar {{ fill: #FF9800; }}',
            f'    .node-stairs {{ fill: #4CAF50; }}',
            f'    .node-gate {{ fill: #00BCD4; }}',
            f'    .node-emergency_exit {{ fill: #F44336; }}',
            f'    .node-normal {{ fill: #607D8B; }}',
            f'    .node-door {{ fill: #FFEB3B; }}',
            f'    .label {{ font-size: 3px; fill: #333; font-family: Arial; }}',
            f'  </style>',
            f'  <!-- Background: semi-transparent white -->',
            f'  <rect width="100%" height="100%" fill="white" opacity="0.8"/>',
        ]
        
        # Draw edges
        svg_lines.append('  <!-- Edges -->')
        for edge in self.edges.values():
            if edge.from_id in self.nodes and edge.to_id in self.nodes:
                n1 = self.nodes[edge.from_id]
                n2 = self.nodes[edge.to_id]
                svg_lines.append(
                    f'  <line x1="{n1.x}" y1="{n1.y}" '
                    f'x2="{n2.x}" y2="{n2.y}" class="edge"/>'
                )
        
        # Draw nodes
        svg_lines.append('  <!-- Nodes -->')
        for node in self.nodes.values():
            css_class = f'node-{node.type}'
            if node.id.startswith('DOOR-'):
                css_class = 'node-door'
            
            radius = 2.0 if node.type == 'corridor' else 3.0
            if node.id.startswith('DOOR-'):
                radius = 1.5
            
            svg_lines.append(
                f'  <circle cx="{node.x}" cy="{node.y}" r="{radius}" '
                f'class="{css_class}">'
                f'<title>{node.id}: {node.name}</title></circle>'
            )
            
            # Only label POI nodes (not corridor nodes, too cluttered)
            if not node.id.startswith('COR-'):
                svg_lines.append(
                    f'  <text x="{node.x + 3}" y="{node.y + 1}" '
                    f'class="label">{node.name}</text>'
                )
        
        svg_lines.append('</svg>')
        
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(svg_lines))
        
        print(f"🎨 Visualization saved to {output_path}")
    
    def print_summary(self):
        """Print a summary of the parsed graph for quick review."""
        print("\n" + "=" * 60)
        print("  GRAPH SUMMARY")
        print("=" * 60)
        
        # POI nodes
        poi_nodes = [n for n in self.nodes.values() if n.id.startswith('POI-')]
        door_nodes = [n for n in self.nodes.values() if n.id.startswith('DOOR-')]
        cor_nodes = [n for n in self.nodes.values() if n.id.startswith('COR-')]
        
        print(f"\n  POIs ({len(poi_nodes)}):")
        for n in sorted(poi_nodes, key=lambda n: n.svg_label):
            print(f"    {n.id:25s}  ({n.x:7.1f}, {n.y:7.1f})  type={n.type:15s}  {n.description or ''}")
        
        print(f"\n  Doors ({len(door_nodes)}):")
        for n in sorted(door_nodes, key=lambda n: n.svg_label):
            print(f"    {n.id:25s}  ({n.x:7.1f}, {n.y:7.1f})")
        
        print(f"\n  Corridor nodes: {len(cor_nodes)}")
        print(f"  Total edges: {len(self.edges)}")
        
        # Check connectivity
        print(f"\n  Connectivity check:")
        adj = {nid: set() for nid in self.nodes}
        for e in self.edges.values():
            if e.from_id in adj and e.to_id in adj:
                adj[e.from_id].add(e.to_id)
                adj[e.to_id].add(e.from_id)
        
        # Count isolated nodes
        isolated = [nid for nid, neighbors in adj.items() if not neighbors]
        print(f"    Isolated nodes (no edges): {len(isolated)}")
        for nid in isolated:
            n = self.nodes[nid]
            print(f"      ⚠️  {nid} at ({n.x:.1f}, {n.y:.1f})")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='Parse SVG floor plan to navigation graph'
    )
    parser.add_argument('svg_file', help='Path to SVG file (.svg or .svg.txt)')
    parser.add_argument('--output', '-o', default='output',
                        help='Output directory (default: output/)')
    parser.add_argument('--visualize', '-v', action='store_true',
                        help='Generate SVG visualization overlay')
    parser.add_argument('--summary', '-s', action='store_true',
                        help='Print detailed summary')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.svg_file):
        print(f"❌ File not found: {args.svg_file}")
        sys.exit(1)
    
    print(f"🗺️  Parsing: {args.svg_file}")
    print("=" * 60)
    
    svg_parser = SVGFloorPlanParser(args.svg_file)
    svg_parser.parse()
    
    # Export JSON
    base_name = os.path.splitext(os.path.basename(args.svg_file))[0]
    base_name = base_name.replace('.svg', '')
    json_path = os.path.join(args.output, f'{base_name}_graph.json')
    svg_parser.export_json(json_path)
    
    # Optional: visualization
    if args.visualize:
        viz_path = os.path.join(args.output, f'{base_name}_graph_overlay.svg')
        svg_parser.export_visualization(viz_path)
    
    # Optional: detailed summary
    if args.summary:
        svg_parser.print_summary()
    
    print("\n✅ Done!")


if __name__ == '__main__':
    main()
