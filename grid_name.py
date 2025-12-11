from sqlalchemy.orm import Session
from models import Tile, Node, POI, Seat, Gate
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
            node_id="",
            poi_id="",
            seat_id="",
            gate_id="",
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
        tile_id = f"tile_{grid_x}_{grid_y}_{level}"
        tile = db.query(Tile).filter(Tile.id == tile_id).first()
        if not tile:
            return {"nodes": [], "pois": [], "seats": [], "gates": [], "tile": None}

        def fetch(model, ids_str):
            ids = [i for i in (ids_str or "").split(",") if i]
            return db.query(model).filter(model.id.in_(ids)).all() if ids else []

        return {
            "nodes": fetch(Node, tile.node_id),
            "pois": fetch(POI, tile.poi_id),
            "seats": fetch(Seat, tile.seat_id),
            "gates": fetch(Gate, tile.gate_id),
            "tile": tile,
        }

    def rebuild_grid(self, db: Session):
        db.query(Tile).delete()
        db.commit()

        for node in db.query(Node).all():
            self.assign_entity_to_cell(db, node.x, node.y, node.level, "node", node)
        for poi in db.query(POI).all():
            self.assign_entity_to_cell(db, poi.x, poi.y, poi.level, "poi", poi)
        for seat in db.query(Seat).all():
            self.assign_entity_to_cell(db, seat.x, seat.y, seat.level, "seat", seat)
        for gate in db.query(Gate).all():
            self.assign_entity_to_cell(db, gate.x, gate.y, gate.level, "gate", gate)

        return db.query(Tile).count()
