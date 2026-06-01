from fastapi import FastAPI, HTTPException, Depends, Query, Path, Security, Response
from fastapi.security import APIKeyHeader
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, event
from typing import List, Optional, Annotated
from database import get_db, init_db
from models import (
    Node, Edge, Closure, Tile, EmergencyRoute, Camera,
    NodeCreate, NodeUpdate, NodeResponse,
    EdgeCreate, EdgeUpdate, EdgeResponse,
    ClosureCreate, ClosureResponse,
    TileCreate, TileUpdate, TileResponse,
    EmergencyRouteResponse, BatchCreate, BatchDelete,
    CameraCreate, CameraUpdate, CameraResponse,
)
from grid_name import GridManager
import hashlib
import math
import time
import json as json_module
import urllib.request
import urllib.parse
import httpx
import threading
import os
import secrets

API_KEY = os.getenv("API_KEY", "dragao_secret_key_2026")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_api_key(api_key: Optional[str] = Security(_api_key_header)):
    if api_key and secrets.compare_digest(api_key, API_KEY):
        return api_key
    raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing API key")


def notify_routing_refresh():
    """Trigger a silent background refresh in the routing service after a map change."""
    def _send():
        try:
            httpx.post(
                "http://routing-service:8002/api/refresh_map", # NOSONAR
                headers={"X-API-Key": API_KEY},
                timeout=2.0,
            )
            print("[WEBHOOK] Notified routing service of map change")
        except Exception as e:
            print(f"[WEBHOOK] Failed to notify routing service: {e}")
    threading.Thread(target=_send).start()

app = FastAPI(title="Campus Map Backend")

from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)

app.add_middleware(GZipMiddleware, minimum_size=500)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_MAP_CACHE: dict[str, dict] = {}
_MAP_CACHE_TTL_SECONDS = 10
_MAP_CACHE_LOCK = threading.Lock()


def _cache_key(name: str, **params) -> str:
    return f"{name}:{json_module.dumps(params, sort_keys=True, default=str)}"


def invalidate_map_cache() -> None:
    with _MAP_CACHE_LOCK:
        _MAP_CACHE.clear()


@event.listens_for(Session, "after_commit")
def _invalidate_map_cache_after_commit(_session):
    invalidate_map_cache()


def _cache_get(key: str):
    now = time.time()
    with _MAP_CACHE_LOCK:
        entry = _MAP_CACHE.get(key)
        if not entry:
            return None
        if now - entry["timestamp"] > _MAP_CACHE_TTL_SECONDS:
            _MAP_CACHE.pop(key, None)
            return None
        return entry["value"]


def _cache_set(key: str, value):
    with _MAP_CACHE_LOCK:
        _MAP_CACHE[key] = {"timestamp": time.time(), "value": value}


def _cached_read(key: str, builder):
    cached = _cache_get(key)
    if cached is not None:
        return cached
    value = builder()
    _cache_set(key, value)
    return value


def _set_pagination_headers(response: Response, total: int, limit: int, offset: int) -> None:
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    response.headers["X-Has-More"] = "true" if offset + limit < total else "false"

@app.on_event("startup")
def startup():
    init_db()
    print("Database initialized")


ERR_NODE_NOT_FOUND = "Node not found"
ERR_EDGE_NOT_FOUND = "Edge not found"
ERR_POI_NOT_FOUND = "POI not found"
ERR_SEAT_NOT_FOUND = "Seat not found"
ERR_CAMERA_NOT_FOUND = "Camera not found"
ERR_GATE_NOT_FOUND = "Gate not found"
ERR_CLOSURE_NOT_FOUND = "Closure not found"

# ================== HELPERS ==================


def serialize_node(n: Node) -> dict:
    return {
        "id": n.id,
        "name": n.name,
        "type": n.type,
        "description": n.description,
        "x": n.x,
        "y": n.y,
        "level": n.level,
        "num_servers": n.num_servers,
        "service_rate": n.service_rate,
        "block": n.block,
        "row": n.row,
        "number": n.number,
        "door_id": n.door_id,
    }

def serialize_edge(e: Edge) -> dict:
    return {
        "id": e.id,
        "from_id": e.from_id,
        "to_id": e.to_id,
        "weight": e.weight,
        "accessible": e.accessible,
    }

def serialize_closure(c: Closure) -> dict:
    return {
        "id": c.id,
        "node_id": c.node_id,
        "edge_id": c.edge_id,
        "reason": c.reason
    }

def serialize_camera(c: Camera) -> dict:
    return {
        "id": c.id,
        "node_id": c.node_id,
        "pos_x": c.pos_x,
        "pos_y": c.pos_y,
        "pos_z": c.pos_z,
        "pan": c.pan,
        "tilt": c.tilt,
        "fov_horizontal": c.fov_horizontal,
        "fov_vertical": c.fov_vertical,
        "coverage_x_min": c.coverage_x_min,
        "coverage_x_max": c.coverage_x_max,
        "coverage_y_min": c.coverage_y_min,
        "coverage_y_max": c.coverage_y_max,
    }

def serialize_emergency_route(route: EmergencyRoute) -> dict:
    return {
        "id": route.id,
        "name": route.name,
        "description": route.description,
        "exit_id": route.exit_id,
        "node_ids": route.node_ids,
    }

# ================== MAP ENDPOINTS ==================

@app.get("/map")
def get_map(db: Annotated[Session, Depends(get_db)]):
    cache_key = _cache_key("map")

    def _build():
        nodes = db.query(Node).order_by(Node.id).all()
        edges = db.query(Edge).order_by(Edge.id).all()
        closures = db.query(Closure).order_by(Closure.id).all()
        return {
            "nodes": [serialize_node(n) for n in nodes],
            "edges": [serialize_edge(e) for e in edges],
            "closures": [serialize_closure(c) for c in closures]
        }

    return _cached_read(cache_key, _build)

def _get_node_group_and_data(node: Node) -> tuple[str, dict]:
    """
    Retorna (grupo, dados_do_nó) para um nó, usando um mapa de tipos.
    """
    base = {
        "id": node.id,
        "x": node.x,
        "y": node.y,
        "level": node.level,
        "name": node.name,
        "description": node.description,
    }
    # Mapeamento: tipo -> (grupo, transformador)
    type_mapping = {
        "corridor": ("navigation", lambda: base),
        "normal": ("navigation", lambda: base),
        "gate": ("gates", lambda: {**base, "num_servers": node.num_servers, "service_rate": node.service_rate}),
        "stairs": ("stairs", lambda: base),
        "seat": ("seats", lambda: {**base, "block": node.block, "row": node.row, "number": node.number}),
        "departments": ("departments", lambda: {**base, "type": node.type}),
    }
    if node.type in type_mapping:
        group, transformer = type_mapping[node.type]
        return group, transformer()
    # POI por defeito
    return "pois", {**base, "type": node.type, "num_servers": node.num_servers, "service_rate": node.service_rate}


def _get_edges_for_level(db: Session, level: Optional[int]) -> list:
    if level is not None:
        ids = [r[0] for r in db.query(Node.id).filter(Node.level == level).all()]
        return db.query(Edge).filter((Edge.from_id.in_(ids)) | (Edge.to_id.in_(ids))).all()
    return db.query(Edge).all()


@app.get("/map/visualization")
def get_map_visualization(
    db: Annotated[Session, Depends(get_db)],
    level: Optional[int] = None
):
    cache_key = _cache_key("map_visualization", level=level)

    def _build():
        query = db.query(Node)
        if level is not None:
            query = query.filter(Node.level == level)
        nodes = query.order_by(Node.id).all()

        grouped_nodes = {
            "navigation": [], "gates": [], "pois": [], "seats": [], "stairs": [], "departments": [],
        }

        for node in nodes:
            group, data = _get_node_group_and_data(node)
            grouped_nodes[group].append(data)

        edges = _get_edges_for_level(db, level)

        return {
            "level": level if level is not None else "all",
            "nodes": grouped_nodes,
            "edges": [serialize_edge(e) for e in edges],
            "stats": {
                "navigation": len(grouped_nodes["navigation"]),
                "gates": len(grouped_nodes["gates"]),
                "pois": len(grouped_nodes["pois"]),
                "seats": len(grouped_nodes["seats"]),
                "stairs": len(grouped_nodes["stairs"]),
                "departments": len(grouped_nodes["departments"]),
                "total": len(nodes)
            }
        }

    return _cached_read(cache_key, _build)

@app.get("/seats/{seat_id}", response_model=NodeResponse, responses={404: {"description": ERR_SEAT_NOT_FOUND}})
def get_seat(
    seat_id: Annotated[str, Path(description="The ID of the seat")],
    db: Annotated[Session, Depends(get_db)]
):
    seat = db.query(Node).filter(Node.id == seat_id).first()
    if not seat:
        raise HTTPException(status_code=404, detail=ERR_SEAT_NOT_FOUND)
    return seat

# ================== NODES ==================

@app.get("/nodes", response_model=List[NodeResponse])
def get_nodes(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    cache_key = _cache_key("nodes", limit=limit, offset=offset)

    def _build():
        query = db.query(Node).order_by(Node.id)
        total = query.order_by(None).count()
        items = [serialize_node(node) for node in query.limit(limit).offset(offset).all()]
        return {"total": total, "items": items}

    payload = _cached_read(cache_key, _build)
    _set_pagination_headers(response, payload["total"], limit, offset)
    return payload["items"]

@app.get("/nodes/{node_id}", response_model=NodeResponse, responses={404: {"description": ERR_NODE_NOT_FOUND}})
def get_node(
    node_id: Annotated[str, Path(description="The ID of the node")],
    db: Annotated[Session, Depends(get_db)]
):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail=ERR_NODE_NOT_FOUND)
    return node

@app.post("/nodes", response_model=NodeResponse, status_code=201, responses={
    400: {"description": "Node already exists"},
    500: {"description": "Database error while creating node"}
})
def create_node(
    data: NodeCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    existing = db.query(Node).filter(Node.id == data.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Node already exists")
    node = Node(**data.model_dump())
    db.add(node)
    try:
        db.commit()
        db.refresh(node)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    notify_routing_refresh()
    return node

@app.put("/nodes/{node_id}", response_model=NodeResponse, responses={
    404: {"description": ERR_NODE_NOT_FOUND},
    500: {"description": "Database error while updating node"}
})
def update_node(
    node_id: Annotated[str, Path(description="The ID of the node")],
    data: NodeUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail=ERR_NODE_NOT_FOUND)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(node, field, value)
    try:
        db.commit()
        db.refresh(node)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    notify_routing_refresh()
    return node

@app.delete("/nodes/{node_id}", responses={
    404: {"description": ERR_NODE_NOT_FOUND},
    500: {"description": "Database error while deleting node"}
})
def delete_node(
    node_id: Annotated[str, Path(description="The ID of the node")],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail=ERR_NODE_NOT_FOUND)
    try:
        db.query(Edge).filter((Edge.from_id == node_id) | (Edge.to_id == node_id)).delete(synchronize_session=False)
        db.query(Closure).filter(Closure.node_id == node_id).delete(synchronize_session=False)
        db.delete(node)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    notify_routing_refresh()
    return {"deleted": node_id}

# ================== EDGES ==================

@app.get("/edges", response_model=List[EdgeResponse])
def get_edges(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    cache_key = _cache_key("edges", limit=limit, offset=offset)

    def _build():
        query = db.query(Edge).order_by(Edge.id)
        total = query.order_by(None).count()
        items = [serialize_edge(edge) for edge in query.limit(limit).offset(offset).all()]
        return {"total": total, "items": items}

    payload = _cached_read(cache_key, _build)
    _set_pagination_headers(response, payload["total"], limit, offset)
    return payload["items"]

@app.get("/edges/{edge_id}", response_model=EdgeResponse, responses={404: {"description": ERR_EDGE_NOT_FOUND}})
def get_edge(
    edge_id: Annotated[str, Path(description="The ID of the edge")],
    db: Annotated[Session, Depends(get_db)]
):
    edge = db.query(Edge).filter(Edge.id == edge_id).first()
    if not edge:
        raise HTTPException(status_code=404, detail=ERR_EDGE_NOT_FOUND)
    return edge

@app.post("/edges", response_model=EdgeResponse, status_code=201, responses={
    400: {"description": "Edge already exists or nodes do not exist"},
    500: {"description": "Database error while creating edge"}
})
def create_edge(
    data: EdgeCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    existing = db.query(Edge).filter(Edge.id == data.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Edge already exists")
    from_node = db.query(Node).filter(Node.id == data.from_id).first()
    if not from_node:
        raise HTTPException(status_code=400, detail=f"from_id '{data.from_id}' does not exist")
    to_node = db.query(Node).filter(Node.id == data.to_id).first()
    if not to_node:
        raise HTTPException(status_code=400, detail=f"to_id '{data.to_id}' does not exist")
    edge = Edge(**data.model_dump())
    db.add(edge)
    try:
        db.commit()
        db.refresh(edge)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    notify_routing_refresh()
    return edge

@app.put("/edges/{edge_id}", response_model=EdgeResponse, responses={
    404: {"description": ERR_EDGE_NOT_FOUND},
    500: {"description": "Database error while updating edge"}
})
def update_edge(
    edge_id: Annotated[str, Path(description="The ID of the edge")],
    data: EdgeUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    edge = db.query(Edge).filter(Edge.id == edge_id).first()
    if not edge:
        raise HTTPException(status_code=404, detail=ERR_EDGE_NOT_FOUND)
    if data.weight is not None:
        edge.weight = data.weight
    if data.accessible is not None:
        edge.accessible = data.accessible
    try:
        db.commit()
        db.refresh(edge)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    notify_routing_refresh()
    return edge

@app.delete("/edges/{edge_id}", responses={
    404: {"description": ERR_EDGE_NOT_FOUND},
    500: {"description": "Database error while deleting edge"}
})
def delete_edge(
    edge_id: Annotated[str, Path(description="The ID of the edge")],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    edge = db.query(Edge).filter(Edge.id == edge_id).first()
    if not edge:
        raise HTTPException(status_code=404, detail=ERR_EDGE_NOT_FOUND)
    try:
        db.delete(edge)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    notify_routing_refresh()
    return {"deleted": edge_id}

# ================== CLOSURES ==================

@app.get("/closures", response_model=List[ClosureResponse])
def get_closures(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    cache_key = _cache_key("closures", limit=limit, offset=offset)

    def _build():
        query = db.query(Closure).order_by(Closure.id)
        total = query.order_by(None).count()
        items = [serialize_closure(closure) for closure in query.limit(limit).offset(offset).all()]
        return {"total": total, "items": items}

    payload = _cached_read(cache_key, _build)
    _set_pagination_headers(response, payload["total"], limit, offset)
    return payload["items"]

@app.get("/closures/{closure_id}", response_model=ClosureResponse, responses={404: {"description": ERR_CLOSURE_NOT_FOUND}})
def get_closure(
    closure_id: Annotated[str, Path(description="The ID of the closure")],
    db: Annotated[Session, Depends(get_db)]
):
    closure = db.query(Closure).filter(Closure.id == closure_id).first()
    if not closure:
        raise HTTPException(status_code=404, detail=ERR_CLOSURE_NOT_FOUND)
    return closure

@app.post("/closures", response_model=ClosureResponse, status_code=201, responses={
    400: {"description": "Closure already exists, or invalid references, or neither edge_id nor node_id"},
    500: {"description": "Database error while creating closure"}
})
def add_closure(
    data: ClosureCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    existing = db.query(Closure).filter(Closure.id == data.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Closure already exists")
    if data.edge_id:
        edge = db.query(Edge).filter(Edge.id == data.edge_id).first()
        if not edge:
            raise HTTPException(status_code=400, detail=f"edge_id '{data.edge_id}' does not exist")
    if data.node_id:
        node = db.query(Node).filter(Node.id == data.node_id).first()
        if not node:
            raise HTTPException(status_code=400, detail=f"node_id '{data.node_id}' does not exist")
    if not data.edge_id and not data.node_id:
        raise HTTPException(status_code=400, detail="Either edge_id or node_id must be provided")
    closure = Closure(id=data.id, reason=data.reason, edge_id=data.edge_id, node_id=data.node_id)
    db.add(closure)
    try:
        db.commit()
        db.refresh(closure)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    notify_routing_refresh()
    return closure

@app.delete("/closures/{closure_id}", responses={
    404: {"description": ERR_CLOSURE_NOT_FOUND},
    500: {"description": "Database error while deleting closure"}
})
def delete_closure(
    closure_id: Annotated[str, Path(description="The ID of the closure")],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    closure = db.query(Closure).filter(Closure.id == closure_id).first()
    if not closure:
        raise HTTPException(status_code=404, detail=ERR_CLOSURE_NOT_FOUND)
    try:
        db.delete(closure)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    return {"deleted": closure_id}

# ================== TILES ==================
grid_manager = GridManager(cell_size=5.0, origin_x=0.0, origin_y=0.0)

@app.get("/maps/grid/config")
def get_grid_config():
    return {
        "cell_size": grid_manager.cell_size,
        "origin_x": grid_manager.origin_x,
        "origin_y": grid_manager.origin_y
    }

@app.get("/maps/grid/tiles")
def get_all_tiles(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    level: Optional[int] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    cache_key = _cache_key("grid_tiles", level=level, limit=limit, offset=offset)

    def _build():
        query = db.query(Tile)
        if level is not None:
            query = query.filter(Tile.level == level)
        total = query.order_by(None).count()
        tiles = query.order_by(Tile.id).limit(limit).offset(offset).all()
        result = []
        for tile in tiles:
            node_count = len([nid for nid in tile.node_id.split(',') if nid]) if tile.node_id else 0
            poi_count = len([pid for pid in tile.poi_id.split(',') if pid]) if tile.poi_id else 0
            seat_count = len([sid for sid in tile.seat_id.split(',') if sid]) if tile.seat_id else 0
            gate_count = len([gid for gid in tile.gate_id.split(',') if gid]) if tile.gate_id else 0
            result.append({
                "id": tile.id, "grid_x": tile.grid_x, "grid_y": tile.grid_y, "level": tile.level,
                "bounds": {"min_x": tile.min_x, "max_x": tile.max_x, "min_y": tile.min_y, "max_y": tile.max_y},
                "walkable": tile.walkable,
                "entity_counts": {"nodes": node_count, "pois": poi_count, "seats": seat_count, "gates": gate_count, "total": node_count + poi_count + seat_count + gate_count}
            })
        return {"total": total, "tiles": result}

    payload = _cached_read(cache_key, _build)
    _set_pagination_headers(response, payload["total"], limit, offset)
    return {"tiles": payload["tiles"], "total_tiles": len(payload["tiles"])}

@app.post("/maps/grid/rebuild", responses={
    500: {"description": "Grid rebuild failed due to database error"}
})
def rebuild_grid(db: Annotated[Session, Depends(get_db)], _: Annotated[str, Depends(get_api_key)]):
    try:
        tile_count = grid_manager.rebuild_grid(db)
        return {"status": "success", "message": f"Grid rebuilt with {tile_count} tiles.", "tiles_created": tile_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid rebuild failed: {str(e)}")

@app.post("/maps/grid/tiles/nodes")
def get_nodes_from_tiles(
    tile_ids: List[str],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    if not tile_ids:
        return {"node_ids": [], "tile_count": 0}
    tiles = db.query(Tile).filter(Tile.id.in_(tile_ids)).all()
    all_node_ids = set()
    for tile in tiles:
        if tile.node_id:
            all_node_ids.update([nid.strip() for nid in tile.node_id.split(',') if nid.strip()])
        if tile.poi_id:
            all_node_ids.update([pid.strip() for pid in tile.poi_id.split(',') if pid.strip()])
        if tile.gate_id:
            all_node_ids.update([gid.strip() for gid in tile.gate_id.split(',') if gid.strip()])
    return {"node_ids": list(all_node_ids), "tile_count": len(tiles), "tiles_found": [t.id for t in tiles]}

@app.get("/maps/grid/stats")
def get_grid_stats(db: Annotated[Session, Depends(get_db)]):
    cache_key = _cache_key("grid_stats")

    def _build():
        tiles = db.query(Tile).all()
        total_nodes = sum(len([i for i in str(tile.node_id).split(',') if i]) for tile in tiles if tile.node_id)
        total_pois = sum(len([i for i in str(tile.poi_id).split(',') if i]) for tile in tiles if tile.poi_id)
        total_seats = sum(len([i for i in str(tile.seat_id).split(',') if i]) for tile in tiles if tile.seat_id)
        total_gates = sum(len([i for i in str(tile.gate_id).split(',') if i]) for tile in tiles if tile.gate_id)
        return {
            "total_tiles": len(tiles),
            "entities_indexed": {"nodes": total_nodes, "pois": total_pois, "seats": total_seats, "gates": total_gates, "total": total_nodes + total_pois + total_seats + total_gates},
            "configuration": {"cell_size": grid_manager.cell_size, "origin_x": grid_manager.origin_x, "origin_y": grid_manager.origin_y}
        }

    return _cached_read(cache_key, _build)

# ================== POIs ==================

@app.get("/pois", response_model=List[NodeResponse])
def get_pois(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    poi_types = ['poi', 'restroom', 'wc', 'entrance', 'food', 'shop', 'bar', 'emergency_exit', 'first_aid', 'information', 'merchandise', 'departments', 'department', 'departamento']
    cache_key = _cache_key("pois", limit=limit, offset=offset)

    def _build():
        query = db.query(Node).filter(Node.type.in_(poi_types)).order_by(Node.id)
        total = query.order_by(None).count()
        items = [serialize_node(poi) for poi in query.limit(limit).offset(offset).all()]
        return {"total": total, "items": items}

    payload = _cached_read(cache_key, _build)
    _set_pagination_headers(response, payload["total"], limit, offset)
    return payload["items"]

# ================== OSM POIs (Dynamic) ==================
_osm_poi_cache: dict = {"data": None, "timestamp": 0}
_OSM_CACHE_TTL = 3600
_UA_BBOX = "40.628,-8.662,40.635,-8.654"
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_OVERPASS_POI_QUERY = f"""
[out:json];
(
  node["amenity"]({_UA_BBOX});
  node["shop"]({_UA_BBOX});
  node["tourism"]({_UA_BBOX});
  way["amenity"]["name"]({_UA_BBOX});
  way["building"]["name"]({_UA_BBOX});
  way["shop"]["name"]({_UA_BBOX});
);
out center;
"""
_OVERPASS_ENTRANCE_QUERY = f"""
[out:json];
node["entrance"]({_UA_BBOX});
out;
"""

def _osm_tag_to_type(tags: dict) -> str:
    amenity = tags.get("amenity", "")
    building = tags.get("building", "")
    shop = tags.get("shop", "")
    tourism = tags.get("tourism", "")
    if amenity in ("restaurant", "cafe", "fast_food", "food_court", "canteen"):
        return "food"
    if amenity == "bar" or amenity == "pub":
        return "bar"
    if amenity == "toilets":
        return "wc"
    if amenity == "library":
        return "library"
    if amenity == "parking":
        return "parking"
    if amenity in ("pharmacy", "hospital", "clinic", "first_aid"):
        return "first_aid"
    if building in ("university", "college", "school", "sports_centre"):
        return "departments"
    if amenity in ("university", "school", "college"):
        return "departments"
    if shop:
        return "shop"
    if tourism:
        return "poi"
    return "poi"

def _haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def _fetch_osm_data():
    try:
        data = urllib.parse.urlencode({"data": _OVERPASS_POI_QUERY}).encode("utf-8")
        req = urllib.request.Request(_OVERPASS_URL, data=data)
        with urllib.request.urlopen(req, timeout=30) as resp:
            osm_data = json_module.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[OSM POIs] Main query failed: {e}")
        return {"elements": []}, []

    entrance_nodes = []
    try:
        ent_data = urllib.parse.urlencode({"data": _OVERPASS_ENTRANCE_QUERY}).encode("utf-8")
        ent_req = urllib.request.Request(_OVERPASS_URL, data=ent_data)
        with urllib.request.urlopen(ent_req, timeout=15) as ent_resp:
            ent_json = json_module.loads(ent_resp.read().decode("utf-8"))
            entrance_nodes = [e for e in ent_json.get("elements", []) if e["type"] == "node"]
            print(f"[OSM POIs] Fetched {len(entrance_nodes)} entrance nodes")
    except Exception as e:
        print(f"[OSM POIs] Could not fetch entrances: {e} (using building centers)")

    return osm_data, entrance_nodes

def _get_coordinates(el, entrance_nodes):
    if el["type"] == "node":
        return el["lon"], el["lat"]
    if el["type"] == "way" and "center" in el:
        center_lon, center_lat = el["center"]["lon"], el["center"]["lat"]
        lon, lat = center_lon, center_lat
        best_dist = float("inf")
        for ent in entrance_nodes:
            d = _haversine(center_lon, center_lat, ent["lon"], ent["lat"])
            if d < 50 and d < best_dist:
                best_dist = d
                lon, lat = ent["lon"], ent["lat"]
        return lon, lat
    return None, None

def _find_nearest_walkable(lon, lat, walkable_nodes):
    nearest_id = None
    min_dist = float("inf")
    for wn in walkable_nodes:
        d = _haversine(lon, lat, wn.x, wn.y)
        if d < min_dist:
            min_dist = d
            nearest_id = wn.id
    return nearest_id, min_dist

def _create_poi_from_element(el, entrance_nodes, walkable_nodes):
    """Process one OSM element, return POI dict or None."""
    tags = el.get("tags", {})
    name = tags.get("name") or tags.get("alt_name") or tags.get("short_name")
    if not name:
        return None

    lon, lat = _get_coordinates(el, entrance_nodes)
    if lon is None:
        return None

    nearest_id, min_dist = _find_nearest_walkable(lon, lat, walkable_nodes)
    if nearest_id is None or min_dist > 100:
        return None

    poi_type = _osm_tag_to_type(tags)
    description = tags.get("description", name)
    return {
        "id": f"OSM-{el['id']}",
        "name": name,
        "type": poi_type,
        "description": description,
        "x": lon,
        "y": lat,
        "level": 0,
        "nearest_node_id": nearest_id,
        "distance_to_node_m": round(float(min_dist), 1),
    }

@app.get("/pois/osm")
def get_osm_pois(db: Annotated[Session, Depends(get_db)]):
    global _osm_poi_cache
    now = time.time()
    if _osm_poi_cache["data"] is not None and (now - _osm_poi_cache["timestamp"]) < _OSM_CACHE_TTL:
        return _osm_poi_cache["data"]

    osm_data, entrance_nodes = _fetch_osm_data()
    if not osm_data.get("elements") and _osm_poi_cache["data"] is not None:
        print("[OSM POIs] Network query failed, falling back to expired cached data")
        return _osm_poi_cache["data"]
        
    walkable_nodes = db.query(Node).filter(Node.type == "normal").all()

    pois = []
    seen_names = set()
    for el in osm_data.get("elements", []):
        name = el.get("tags", {}).get("name") or el.get("tags", {}).get("alt_name") or el.get("tags", {}).get("short_name")
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        poi_dict = _create_poi_from_element(el, entrance_nodes, walkable_nodes)
        if poi_dict:
            pois.append(poi_dict)

    result = {"pois": pois, "total": len(pois), "source": "openstreetmap", "cached_at": now}
    _osm_poi_cache = {"data": result, "timestamp": now}
    print(f"[OSM POIs] Fetched {len(pois)} POIs from Overpass API")
    return result

@app.get("/pois/{poi_id}", response_model=NodeResponse, responses={404: {"description": ERR_POI_NOT_FOUND}})
def get_poi(
    poi_id: Annotated[str, Path(description="The ID of the POI")],
    db: Annotated[Session, Depends(get_db)]
):
    poi = db.query(Node).filter(Node.id == poi_id).first()
    if not poi:
        raise HTTPException(status_code=404, detail=ERR_POI_NOT_FOUND)
    return poi

@app.put("/pois/{poi_id}", response_model=NodeResponse, responses={
    404: {"description": ERR_POI_NOT_FOUND},
    500: {"description": "Database error while updating POI"}
})
def update_poi(
    poi_id: Annotated[str, Path(description="The ID of the POI")],
    data: NodeUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    poi = db.query(Node).filter(Node.id == poi_id).first()
    if not poi:
        raise HTTPException(status_code=404, detail=ERR_POI_NOT_FOUND)
    if data.name is not None:
        poi.name = data.name
    if data.type is not None:
        poi.type = data.type
    if data.x is not None:
        poi.x = data.x
    if data.y is not None:
        poi.y = data.y
    if data.level is not None:
        poi.level = data.level
    if data.num_servers is not None:
        poi.num_servers = data.num_servers
    if data.service_rate is not None:
        poi.service_rate = data.service_rate
    try:
        db.commit()
        db.refresh(poi)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    return poi

from pydantic import BaseModel as PydanticBaseModel

class POICreate(PydanticBaseModel):
    name: str
    type: str = "poi"
    x: float
    y: float
    level: int = 0
    description: Optional[str] = None

@app.post("/pois", response_model=NodeResponse, status_code=201, responses={
    500: {"description": "Database error while creating POI"}
})
def create_poi(
    data: POICreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    import uuid
    poi_id = f"CUSTOM-{uuid.uuid4().hex[:8]}"
    new_poi = Node(id=poi_id, name=data.name, type=data.type, x=data.x, y=data.y, level=data.level, description=data.description or data.name)
    try:
        db.add(new_poi)
        db.commit()
        db.refresh(new_poi)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    print(f"[POI] Created custom POI '{data.name}' ({poi_id}) at ({data.x}, {data.y})")
    return new_poi

@app.delete("/pois/{poi_id}", responses={
    404: {"description": ERR_POI_NOT_FOUND},
    500: {"description": "Database error while deleting POI"}
})
def delete_poi(
    poi_id: Annotated[str, Path(description="The ID of the POI")],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    poi = db.query(Node).filter(Node.id == poi_id).first()
    if not poi:
        raise HTTPException(status_code=404, detail=ERR_POI_NOT_FOUND)
    db.delete(poi)
    db.commit()
    return {"status": "deleted", "id": poi_id}

# ================== SEATS ==================
@app.get("/seats", response_model=List[NodeResponse])
def get_seats(
    db: Annotated[Session, Depends(get_db)],
    block: Optional[str] = None
):
    query = db.query(Node).filter(Node.type == 'seat')
    if block:
        query = query.filter(Node.block == block)
    return query.all()

@app.get("/seats/{seat_id}", response_model=NodeResponse, responses={404: {"description": ERR_SEAT_NOT_FOUND}})
def get_seat(
    seat_id: Annotated[str, Path(description="The ID of the seat")],
    db: Annotated[Session, Depends(get_db)]
):
    seat = db.query(Node).filter(Node.id == seat_id).first()
    if not seat:
        raise HTTPException(status_code=404, detail=ERR_SEAT_NOT_FOUND)
    return seat

@app.put("/seats/{seat_id}", response_model=NodeResponse, responses={
    404: {"description": ERR_SEAT_NOT_FOUND},
    500: {"description": "Database error while updating seat"}
})
def update_seat(
    seat_id: Annotated[str, Path(description="The ID of the seat")],
    data: NodeUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    seat = db.query(Node).filter(Node.id == seat_id).first()
    if not seat:
        raise HTTPException(status_code=404, detail=ERR_SEAT_NOT_FOUND)
    if data.block is not None:
        seat.block = data.block
    if data.row is not None:
        seat.row = data.row
    if data.number is not None:
        seat.number = data.number
    if data.x is not None:
        seat.x = data.x
    if data.y is not None:
        seat.y = data.y
    if data.level is not None:
        seat.level = data.level
    try:
        db.commit()
        db.refresh(seat)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    return seat

# ================== GATES ==================
@app.get("/gates", response_model=List[NodeResponse])
def get_gates(db: Annotated[Session, Depends(get_db)]):
    return db.query(Node).filter(Node.type == 'gate').all()

@app.get("/gates/{gate_id}", response_model=NodeResponse, responses={404: {"description": ERR_GATE_NOT_FOUND}})
def get_gate(
    gate_id: Annotated[str, Path(description="The ID of the gate")],
    db: Annotated[Session, Depends(get_db)]
):
    gate = db.query(Node).filter(Node.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail=ERR_GATE_NOT_FOUND)
    return gate

@app.put("/gates/{gate_id}", response_model=NodeResponse, responses={
    404: {"description": ERR_GATE_NOT_FOUND},
    500: {"description": "Database error while updating gate"}
})
def update_gate(
    gate_id: Annotated[str, Path(description="The ID of the gate")],
    data: NodeUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    gate = db.query(Node).filter(Node.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail=ERR_GATE_NOT_FOUND)
    if data.name is not None:
        gate.name = data.name
    if data.x is not None:
        gate.x = data.x
    if data.y is not None:
        gate.y = data.y
    if data.level is not None:
        gate.level = data.level
    if data.num_servers is not None:
        gate.num_servers = data.num_servers
    if data.service_rate is not None:
        gate.service_rate = data.service_rate
    try:
        db.commit()
        db.refresh(gate)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    return gate

# ================== GEOJSON ENDPOINTS ==================
def _create_node_feature(node: Node) -> dict:
    feature = {
        "type": "Feature",
        "id": node.id,
        "geometry": {"type": "Point", "coordinates": [node.x, node.y]},
        "properties": {"id": node.id, "name": node.name, "type": node.type, "level": node.level, "description": node.description}
    }
    if node.num_servers is not None:
        feature["properties"]["num_servers"] = node.num_servers
    if node.service_rate is not None:
        feature["properties"]["service_rate"] = node.service_rate
    if node.block is not None:
        feature["properties"]["block"] = node.block
    if node.row is not None:
        feature["properties"]["row"] = node.row
    if node.number is not None:
        feature["properties"]["number"] = node.number
    return feature

def _create_edge_features(db: Session, nodes: list, node_map: dict, level: Optional[int]) -> list:
    features = []
    edge_query = db.query(Edge)
    if level is not None:
        level_node_ids = [n.id for n in nodes]
        edge_query = edge_query.filter((Edge.from_id.in_(level_node_ids)) | (Edge.to_id.in_(level_node_ids)))
    for e in edge_query.all():
        from_node = node_map.get(e.from_id)
        to_node = node_map.get(e.to_id)
        if from_node and to_node:
            features.append({
                "type": "Feature",
                "id": e.id,
                "geometry": {"type": "LineString", "coordinates": [[from_node.x, from_node.y], [to_node.x, to_node.y]]},
                "properties": {"id": e.id, "type": "edge", "weight": e.weight, "from_id": e.from_id, "to_id": e.to_id}
            })
    return features

def _calculate_bounds(nodes: list) -> Optional[dict]:
    if not nodes:
        return None
    xs = [n.x for n in nodes]
    ys = [n.y for n in nodes]
    return {"min_x": min(xs), "max_x": max(xs), "min_y": min(ys), "max_y": max(ys)}

def _build_geojson_features(db: Session, nodes: list, include_edges: bool, level: Optional[int]) -> tuple[list, dict]:
    features = []
    node_map = {}
    for n in nodes:
        node_map[n.id] = n
        features.append(_create_node_feature(n))
    if include_edges:
        features.extend(_create_edge_features(db, nodes, node_map, level))
    return features, node_map

@app.get("/map/geojson")
def get_map_geojson(
    db: Annotated[Session, Depends(get_db)],
    level: Annotated[Optional[int], Query(description="Filter by floor level (0, 1, 2)")] = None,
    types: Annotated[Optional[str], Query(description="Comma-separated node types: gate,poi,stairs,corridor,seat")] = None,
    include_edges: Annotated[bool, Query(description="Include edges as LineStrings")] = True,
    include_seats: Annotated[bool, Query(description="Include seat nodes (warning: many!)")] = False
):
    cache_key = _cache_key(
        "map_geojson",
        level=level,
        types=types,
        include_edges=include_edges,
        include_seats=include_seats,
    )

    def _build():
        query = db.query(Node)
        if level is not None:
            query = query.filter(Node.level == level)
        if types:
            type_list = [t.strip() for t in types.split(',')]
            query = query.filter(Node.type.in_(type_list))
        if not include_seats:
            query = query.filter(Node.type != 'seat')
        nodes = query.all()

        features, _ = _build_geojson_features(db, nodes, include_edges, level)
        bounds = _calculate_bounds(nodes)

        result = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "level": level if level is not None else "all",
                "total_nodes": len([f for f in features if f["geometry"]["type"] == "Point"]),
                "total_edges": len([f for f in features if f["geometry"]["type"] == "LineString"]),
                "bounds": bounds
            }
        }
        etag = hashlib.md5(f"{len(features)}:{level}:{types}:{include_edges}:{include_seats}".encode()).hexdigest()[:16]
        return {"result": result, "etag": etag}

    payload = _cached_read(cache_key, _build)
    return JSONResponse(content=payload["result"], headers={"ETag": f'"{payload["etag"]}"', "Cache-Control": "public, max-age=300"})

@app.get("/map/geojson/level/{level}")
def get_level_geojson(
    level: int,
    db: Annotated[Session, Depends(get_db)]
):
    return get_map_geojson(db=db, level=level, types=None, include_edges=True, include_seats=False)

@app.get("/map/bounds")
def get_map_bounds(db: Annotated[Session, Depends(get_db)]):
    cache_key = _cache_key("map_bounds")

    def _build():
        result = db.query(func.min(Node.x).label('min_x'), func.max(Node.x).label('max_x'), func.min(Node.y).label('min_y'), func.max(Node.y).label('max_y')).first()
        levels = [row[0] for row in db.query(Node.level).distinct().order_by(Node.level).all()]
        return {
            "bounds": {"min_x": result.min_x, "max_x": result.max_x, "min_y": result.min_y, "max_y": result.max_y},
            "center": {"x": (result.min_x + result.max_x) / 2, "y": (result.min_y + result.max_y) / 2},
            "levels": levels
        }

    return _cached_read(cache_key, _build)

@app.get("/map/geojson/pois")
def get_pois_geojson(
    db: Annotated[Session, Depends(get_db)],
    level: Annotated[Optional[int], Query(description="Filter by floor level")] = None
):
    poi_types = ['gate', 'restroom', 'food', 'bar', 'stairs', 'ramp', 'emergency_exit', 'first_aid', 'information', 'departments']
    return get_map_geojson(db=db, level=level, types=','.join(poi_types), include_edges=False, include_seats=False)

# ================== EMERGENCY ROUTES ==================
@app.get("/emergency-routes", response_model=List[EmergencyRouteResponse])
def list_emergency_routes(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    cache_key = _cache_key("emergency_routes", limit=limit, offset=offset)

    def _build():
        query = db.query(EmergencyRoute).order_by(EmergencyRoute.id)
        total = query.order_by(None).count()
        items = [serialize_emergency_route(route) for route in query.limit(limit).offset(offset).all()]
        return {"total": total, "items": items}

    payload = _cached_read(cache_key, _build)
    _set_pagination_headers(response, payload["total"], limit, offset)
    return payload["items"]

@app.get("/emergency-routes/nearest")
def get_nearest_emergency_route(
    db: Annotated[Session, Depends(get_db)],
    x: Annotated[float, Query(description="Current X coordinate")],
    y: Annotated[float, Query(description="Current Y coordinate")],
    level: Annotated[int, Query(description="Current floor level")] = 0
):
    routes = db.query(EmergencyRoute).all()
    if not routes:
        raise HTTPException(status_code=404, detail="No emergency routes defined")
    nearest_route = None
    min_distance = float('inf')
    nearest_start_node = None
    for route in routes:
        if not route.node_ids or len(route.node_ids) == 0:
            continue
        start_node_id = route.node_ids[0]
        start_node = db.query(Node).filter(Node.id == start_node_id).first()
        if not start_node:
            continue
        distance = math.sqrt((x - start_node.x) ** 2 + (y - start_node.y) ** 2)
        if start_node.level != level:
            distance += 100
        if distance < min_distance:
            min_distance = distance
            nearest_route = route
            nearest_start_node = start_node
    if not nearest_route:
        raise HTTPException(status_code=404, detail="No valid emergency routes found")
    return {
        "route_id": nearest_route.id,
        "route_name": nearest_route.name,
        "exit_id": nearest_route.exit_id,
        "start_node": {"id": nearest_start_node.id, "x": nearest_start_node.x, "y": nearest_start_node.y, "level": nearest_start_node.level},
        "distance_to_start": round(min_distance, 2),
        "num_waypoints": len(nearest_route.node_ids)
    }

@app.get("/emergency-routes/{route_id}", responses={404: {"description": "Emergency route not found"}})
def get_emergency_route_geojson(
    route_id: Annotated[str, Path(description="The ID of the emergency route")],
    db: Annotated[Session, Depends(get_db)]
):
    route = db.query(EmergencyRoute).filter(EmergencyRoute.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail=f"Emergency route '{route_id}' not found")
    path_nodes = {n.id: n for n in db.query(Node).filter(Node.id.in_(route.node_ids)).all()}
    coordinates = []
    waypoint_features = []
    for idx, node_id in enumerate(route.node_ids):
        node = path_nodes.get(node_id)
        if node:
            coordinates.append([node.x, node.y])
            # Determine role
            if idx == 0:
                role = "start"
            elif idx == len(route.node_ids) - 1:
                role = "exit"
            else:
                role = "waypoint"
            waypoint_features.append({
                "type": "Feature",
                "id": f"wp_{node_id}",
                "geometry": {"type": "Point", "coordinates": [node.x, node.y]},
                "properties": {"id": node_id, "name": node.name, "type": node.type, "level": node.level, "role": role, "order": idx}
            })
    features = [{
        "type": "Feature",
        "id": f"route_{route_id}",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {"type": "emergency_route", "route_id": route.id, "route_name": route.name, "exit_id": route.exit_id, "num_waypoints": len(route.node_ids)}
    }] + waypoint_features
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {"route_id": route.id, "route_name": route.name, "description": route.description, "exit_id": route.exit_id, "node_ids": route.node_ids, "num_waypoints": len(route.node_ids)}
    }

# ================== CAMERAS ==================
@app.get("/cameras", response_model=List[CameraResponse])
def get_cameras(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    cache_key = _cache_key("cameras", limit=limit, offset=offset)

    def _build():
        query = db.query(Camera).order_by(Camera.id)
        total = query.order_by(None).count()
        items = [serialize_camera(camera) for camera in query.limit(limit).offset(offset).all()]
        return {"total": total, "items": items}

    payload = _cached_read(cache_key, _build)
    _set_pagination_headers(response, payload["total"], limit, offset)
    return payload["items"]

@app.get("/cameras/{camera_id}", response_model=CameraResponse, responses={404: {"description": ERR_CAMERA_NOT_FOUND}})
def get_camera(
    camera_id: Annotated[str, Path(description="The ID of the camera")],
    db: Annotated[Session, Depends(get_db)]
):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail=ERR_CAMERA_NOT_FOUND)
    return camera

@app.post("/cameras", response_model=CameraResponse, status_code=201, responses={
    400: {"description": "Camera already exists or node not found"},
    500: {"description": "Database error while creating camera"}
})
def create_camera(
    data: CameraCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    if db.query(Camera).filter(Camera.id == data.id).first():
        raise HTTPException(status_code=400, detail="Camera already exists")
    node = db.query(Node).filter(Node.id == data.node_id).first()
    if not node:
        raise HTTPException(status_code=400, detail=f"Node '{data.node_id}' not found")
    camera = Camera(**data.model_dump())
    db.add(camera)
    try:
        db.commit()
        db.refresh(camera)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    return camera

@app.put("/cameras/{camera_id}", response_model=CameraResponse, responses={
    404: {"description": ERR_CAMERA_NOT_FOUND},
    500: {"description": "Database error while updating camera"}
})
def update_camera(
    camera_id: Annotated[str, Path(description="The ID of the camera")],
    data: CameraUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail=ERR_CAMERA_NOT_FOUND)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(camera, field, value)
    try:
        db.commit()
        db.refresh(camera)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    return camera

@app.delete("/cameras/{camera_id}", responses={
    404: {"description": ERR_CAMERA_NOT_FOUND},
    500: {"description": "Database error while deleting camera"}
})
def delete_camera(
    camera_id: Annotated[str, Path(description="The ID of the camera")],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail=ERR_CAMERA_NOT_FOUND)
    try:
        db.delete(camera)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    return {"deleted": camera_id}

# ================== HEALTH CHECK ==================
@app.get("/health")
def health_check():
    return {"status": "ok"}

# ================== DATA MANAGEMENT ==================
@app.post("/reset", responses={
    500: {"description": "Reset failed due to database error"}
})
def reset_data(db: Annotated[Session, Depends(get_db)], _: Annotated[str, Depends(get_api_key)]):
    from load_data_db import clear_all_data, load_sample_data
    try:
        print("Resetting database...")
        clear_all_data(db)
        load_sample_data(db)
        print("Database reset complete")
        print("Rebuilding grid...")
        tile_count = grid_manager.rebuild_grid(db)
        print(f"Grid rebuilt with {tile_count} tiles.")
        return {"status": "success", "message": "Database reset to initial state with sample data", "tiles_created": tile_count}
    except Exception as e:
        print(f"Reset failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")

# ================== BATCH IMPORT ==================
def _insert_batch_nodes(db: Session, nodes_data: list, existing_nodes: set, results: dict):
    for node_data in nodes_data:
        try:
            if node_data.id in existing_nodes:
                results["nodes"]["errors"].append({"id": node_data.id, "error": "Node already exists"})
                continue
            node = Node(**node_data.model_dump())
            db.add(node)
            results["nodes"]["created"].append(node.id)
            existing_nodes.add(node.id)
        except Exception as e:
            results["nodes"]["errors"].append({"id": getattr(node_data, 'id', 'unknown'), "error": str(e)})

def _insert_batch_edges(db: Session, edges_data: list, existing_nodes: set, results: dict):
    existing_edges = {r[0] for r in db.query(Edge.id).all()}
    for edge_data in edges_data:
        try:
            if edge_data.id in existing_edges:
                results["edges"]["errors"].append({"id": edge_data.id, "error": "Edge already exists"})
                continue
            if edge_data.from_id not in existing_nodes or edge_data.to_id not in existing_nodes:
                results["edges"]["errors"].append({"id": edge_data.id, "error": f"One or both nodes do not exist ({edge_data.from_id}, {edge_data.to_id})"})
                continue
            edge = Edge(**edge_data.model_dump())
            db.add(edge)
            results["edges"]["created"].append(edge.id)
            existing_edges.add(edge.id)
        except Exception as e:
            results["edges"]["errors"].append({"id": getattr(edge_data, 'id', 'unknown'), "error": str(e)})

def _insert_batch_cameras(db: Session, cameras_data: list, existing_nodes: set, results: dict):
    existing_cameras = {r[0] for r in db.query(Camera.id).all()}
    for camera_data in cameras_data:
        try:
            if camera_data.id in existing_cameras:
                results["cameras"]["errors"].append({"id": camera_data.id, "error": "Camera already exists"})
                continue
            if camera_data.node_id not in existing_nodes:
                results["cameras"]["errors"].append({"id": camera_data.id, "error": f"node_id '{camera_data.node_id}' does not exist"})
                continue
            camera = Camera(**camera_data.model_dump())
            db.add(camera)
            results["cameras"]["created"].append(camera_data.id)
            existing_cameras.add(camera_data.id)
        except Exception as e:
            results["cameras"]["errors"].append({"id": getattr(camera_data, 'id', 'unknown'), "error": str(e)})


def _insert_batch_closures(db: Session, closures_data: list, results: dict):
    existing_closures = {r[0] for r in db.query(Closure.id).all()}
    for closure_data in closures_data:
        try:
            if closure_data.id in existing_closures:
                results["closures"]["errors"].append({"id": closure_data.id, "error": "Closure already exists"})
                continue
            closure = Closure(**closure_data.model_dump())
            db.add(closure)
            results["closures"]["created"].append(closure.id)
            existing_closures.add(closure.id)
        except Exception as e:
            results["closures"]["errors"].append({"id": getattr(closure_data, 'id', 'unknown'), "error": str(e)})

@app.post("/batch", status_code=201, responses={
    500: {"description": "Database error during batch operation"}
})
def create_batch(
    data: BatchCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    results = {
        "nodes": {"created": [], "errors": []},
        "edges": {"created": [], "errors": []},
        "closures": {"created": [], "errors": []},
        "cameras": {"created": [], "errors": []},
    }
    existing_nodes = {r[0] for r in db.query(Node.id).all()}

    _insert_batch_nodes(db, data.nodes, existing_nodes, results)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error committing nodes: {str(e)}")

    _insert_batch_edges(db, data.edges, existing_nodes, results)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error committing edges: {str(e)}")

    _insert_batch_closures(db, data.closures, results)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error committing closures: {str(e)}")

    _insert_batch_cameras(db, data.cameras, existing_nodes, results)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error committing cameras: {str(e)}")

    if results["nodes"]["created"] or results["edges"]["created"] or results["closures"]["created"] or results["cameras"]["created"]:
        notify_routing_refresh()
    return results

# ================== BATCH DELETE ==================
@app.post("/batch/delete", status_code=200, responses={
    500: {"description": "Database error during batch delete operation"}
})
def delete_batch(
    data: BatchDelete,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    """Apaga múltiplos edges e nodes numa única transação.

    Edges primeiro, depois nodes (incluindo edges e closures dependentes
    de cada node). Tudo num único commit para evitar N pedidos individuais.
    """
    results = {
        "edges": {"deleted": [], "errors": []},
        "nodes": {"deleted": [], "errors": []},
    }

    if data.edge_ids:
        existing_edges = {r[0] for r in db.query(Edge.id).filter(Edge.id.in_(data.edge_ids)).all()}
        for edge_id in data.edge_ids:
            if edge_id not in existing_edges:
                results["edges"]["errors"].append({"id": edge_id, "error": ERR_EDGE_NOT_FOUND})

    if data.node_ids:
        existing_nodes = {r[0] for r in db.query(Node.id).filter(Node.id.in_(data.node_ids)).all()}
        for node_id in data.node_ids:
            if node_id not in existing_nodes:
                results["nodes"]["errors"].append({"id": node_id, "error": ERR_NODE_NOT_FOUND})

    deletable_edges = [eid for eid in data.edge_ids if not any(e["id"] == eid for e in results["edges"]["errors"])]
    deletable_nodes = [nid for nid in data.node_ids if not any(n["id"] == nid for n in results["nodes"]["errors"])]

    try:
        if deletable_edges:
            db.query(Edge).filter(Edge.id.in_(deletable_edges)).delete(synchronize_session=False)
            results["edges"]["deleted"] = deletable_edges

        if deletable_nodes:
            # Remove edges and closures attached to the nodes being deleted
            db.query(Edge).filter(
                Edge.from_id.in_(deletable_nodes) | Edge.to_id.in_(deletable_nodes)
            ).delete(synchronize_session=False)
            db.query(Closure).filter(Closure.node_id.in_(deletable_nodes)).delete(synchronize_session=False)
            db.query(Node).filter(Node.id.in_(deletable_nodes)).delete(synchronize_session=False)
            results["nodes"]["deleted"] = deletable_nodes

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    if results["edges"]["deleted"] or results["nodes"]["deleted"]:
        notify_routing_refresh()
    return results

# ================== MAP SYNC ==================
@app.post("/map/sync", status_code=200, responses={
    500: {"description": "Database error during map synchronization"}
})
def sync_map(
    data: BatchCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_api_key)]
):
    try:
        # Preserve existing cameras before wiping the DB
        existing_cameras = db.query(Camera).all()
        camera_dumps = [
            {c.key: getattr(cam, c.key) for c in cam.__mapper__.columns}
            for cam in existing_cameras
        ]

        db.query(Camera).delete()
        db.query(Closure).delete()
        db.query(Edge).delete()
        db.query(Node).delete()
        db.query(Tile).delete()

        # Insert nodes without door_id first to avoid FK violations
        nodes_without_door = [n for n in data.nodes if not n.door_id]
        nodes_with_door = [n for n in data.nodes if n.door_id]
        for node_data in nodes_without_door:
            db.add(Node(**node_data.model_dump()))
        for node_data in nodes_with_door:
            db.add(Node(**node_data.model_dump()))

        for edge_data in data.edges:
            db.add(Edge(**edge_data.model_dump()))
        for closure_data in data.closures:
            db.add(Closure(**closure_data.model_dump()))
        for camera_data in data.cameras:
            db.add(Camera(**camera_data.model_dump()))
        db.commit()

        # Reinsert cameras whose linked node still exists after sync
        new_node_ids = {n.id for n in data.nodes}
        for cam_data in camera_dumps:
            if cam_data.get("node_id") in new_node_ids:
                db.add(Camera(**cam_data))
        db.commit()

        grid_manager = GridManager(cell_size=5.0, origin_x=0.0, origin_y=0.0)
        grid_manager.rebuild_grid(db)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error during sync: {str(e)}")
    notify_routing_refresh()
    return {"status": "success", "message": "Map synchronized successfully"}
