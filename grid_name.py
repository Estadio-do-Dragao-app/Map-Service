from sqlalchemy.orm import Session
from models import Tile, Node
from typing import Tuple, Dict
import math

class GridManager:
    def __init__(self, cell_size: float = 5.0, origin_x: float = 0.0, origin_y: float = 0.0):
        self.cell_size = cell_size
        self.origin_x = origin_x
        self.origin_y = origin_y

    def get_cell_coords(self, x: float, y: float) -> Tuple[int, int]:
        gx = math.floor((x - self.origin_x) / self.cell_size)
        gy = math.floor((y - self.origin_y) / self.cell_size)
        return gx, gy
    
    def get_cell_bounds(self, grid_x: int, grid_y: int) -> Tuple[float, float, float, float]:
        min_x = self.origin_x + grid_x * self.cell_size
        max_x = min_x + self.cell_size
        min_y = self.origin_y + grid_y * self.cell_size
        max_y = min_y + self.cell_size
        return min_x, max_x, min_y, max_y
    
    def get_or_create_tile(self, db: Session, x: float, y: float, level: int = 0) -> Tile:
        grid_x, grid_y = self.get_cell_coords(x, y)
        tile_id = f"tile_{grid_x}_{grid_y}_{level}"
        tile = db.query(Tile).filter(Tile.id == tile_id).first()
        if tile:
            return tile

        min_x, max_x, min_y, max_y = self.get_cell_bounds(grid_x, grid_y)
        tile = Tile(
            id=tile_id,
            grid_x=grid_x,
            grid_y=grid_y,
            level=level,
            min_x=min_x,
            max_x=max_x,
            min_y=min_y,
            max_y=max_y,
            walkable=True,
            node_id=None,
            poi_id=None,
            seat_id=None,
            gate_id=None,
        )
        db.add(tile)
        db.commit()
        db.refresh(tile)
        return tile

    def _append_id(self, current: str, new_id: str) -> str:
        ids = [i for i in (current or "").split(",") if i]
        if new_id not in ids:
            ids.append(new_id)
        return ",".join(ids)

    def assign_entity_to_cell(self, db: Session, x: float, y: float, level: int, entity_type: str, entity_obj=None):
        tile = self.get_or_create_tile(db, x, y, level)
        if entity_type == "node" and entity_obj:
            tile.node_id = self._append_id(tile.node_id, entity_obj.id)
        elif entity_type == "poi" and entity_obj:
            tile.poi_id = self._append_id(tile.poi_id, entity_obj.id)
        elif entity_type == "seat" and entity_obj:
            tile.seat_id = self._append_id(tile.seat_id, entity_obj.id)
        elif entity_type == "gate" and entity_obj:
            tile.gate_id = self._append_id(tile.gate_id, entity_obj.id)
        db.commit()
        return tile

    def get_entities_in_cell(self, db: Session, grid_x: int, grid_y: int, level: int = 0) -> Dict:
        """Get all entities within a specific grid cell.
        
        In the new unified model, all entities are Nodes with different types.
        This method returns them categorized by type for backwards compatibility.
        """
        tile_id = f"tile_{grid_x}_{grid_y}_{level}"
        tile = db.query(Tile).filter(Tile.id == tile_id).first()
        if not tile:
            return {"nodes": [], "pois": [], "seats": [], "gates": [], "tile": None}

        def fetch_ids(ids_str):
            return [i for i in (ids_str or "").split(",") if i]

        # Fetch all referenced nodes
        node_ids = fetch_ids(tile.node_id)
        poi_ids = fetch_ids(tile.poi_id)
        seat_ids = fetch_ids(tile.seat_id)
        gate_ids = fetch_ids(tile.gate_id)
        
        all_ids = node_ids + poi_ids + seat_ids + gate_ids
        all_nodes = db.query(Node).filter(Node.id.in_(all_ids)).all() if all_ids else []
        
        # Categorize by ID list
        node_lookup = {n.id: n for n in all_nodes}
        
        return {
            "nodes": [node_lookup[nid] for nid in node_ids if nid in node_lookup],
            "pois": [node_lookup[nid] for nid in poi_ids if nid in node_lookup],
            "seats": [node_lookup[nid] for nid in seat_ids if nid in node_lookup],
            "gates": [node_lookup[nid] for nid in gate_ids if nid in node_lookup],
            "tile": tile,
        }

    def rebuild_grid(self, db: Session):
        """Rebuild the entire grid from all nodes in the database.
        
        ALL nodes are added to node_id (for complete reference).
        Additionally, nodes are categorized into specific fields by type:
        - gate: Also added to gate_id
        - seat: Also added to seat_id
        - POI types (restroom, food, bar, etc.): Also added to poi_id
        """
        db.query(Tile).delete()
        db.commit()

        # POI types that should also be stored in poi_id
        poi_types = {'restroom', 'food', 'bar', 'merchandise', 'first_aid', 
                     'emergency_exit', 'information', 'vip_box'}
        
        # Build tiles in memory first (MUCH faster than individual commits)
        tiles_cache = {}  # tile_id -> Tile object
        
        nodes = db.query(Node).all()
        total = len(nodes)
        
        for i, node in enumerate(nodes):
            grid_x, grid_y = self.get_cell_coords(node.x, node.y)
            tile_id = f"tile_{grid_x}_{grid_y}_{node.level}"
            
            # Get or create tile in cache
            if tile_id not in tiles_cache:
                min_x, max_x, min_y, max_y = self.get_cell_bounds(grid_x, grid_y)
                tiles_cache[tile_id] = Tile(
                    id=tile_id,
                    grid_x=grid_x,
                    grid_y=grid_y,
                    level=node.level,
                    min_x=min_x,
                    max_x=max_x,
                    min_y=min_y,
                    max_y=max_y,
                    walkable=True,
                    node_id="",
                    poi_id="",
                    seat_id="",
                    gate_id="",
                )
            
            tile = tiles_cache[tile_id]
            
            # ALL nodes go to node_id
            tile.node_id = self._append_id(tile.node_id, node.id)
            
            # Additionally categorize into specific fields based on type
            if node.type == "gate":
                tile.gate_id = self._append_id(tile.gate_id, node.id)
            elif node.type == "seat":
                tile.seat_id = self._append_id(tile.seat_id, node.id)
            elif node.type in poi_types:
                tile.poi_id = self._append_id(tile.poi_id, node.id)
            
            # Progress indicator every 1000 nodes
            if (i + 1) % 1000 == 0:
                print(f"   Processing nodes: {i+1}/{total}...")
        
        # Bulk insert all tiles at once
        for tile in tiles_cache.values():
            db.add(tile)
        
        db.commit()
        
        return len(tiles_cache)
