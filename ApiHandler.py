from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from networkx import edges, nodes
from networkx import edges
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Annotated
from database import get_db, init_db
from models import (
    Node, Edge, Closure, Tile, EmergencyRoute, Camera,
    NodeCreate, NodeUpdate, NodeResponse,
    EdgeCreate, EdgeUpdate, EdgeResponse,
    ClosureCreate, ClosureResponse,
    TileCreate, TileUpdate, TileResponse,
    EmergencyRouteResponse, BatchCreate,
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

def notify_routing_refresh():
    """Trigger a silent background refresh in the routing service after a map change."""
    def _send():
        try:
            # Fire-and-forget webhook
            httpx.post("http://routing-service:8002/api/refresh_map", timeout=2.0)
            print("[WEBHOOK] Notified routing service of map change")
        except Exception as e:
            print(f"[WEBHOOK] Failed to notify routing service: {e}")
    threading.Thread(target=_send).start()

app = FastAPI(title="Smart Stadium Map Backend")

# Add CORS middleware (allows Flutter web app to make requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add GZip compression for large responses (reduces ~2MB GeoJSON to ~300KB)
app.add_middleware(GZipMiddleware, minimum_size=500)

# ================== STARTUP ==================

@app.on_event("startup")
def startup():
    init_db()
    print("Database initialized")

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

# ================== MAP ==================

@app.get("/map")
def get_map(db: Annotated[Session, Depends(get_db)]):
    """Get complete map with nodes, edges, and closures."""
    nodes = db.query(Node).all()
    edges = db.query(Edge).all()
    closures = db.query(Closure).all()
    
    return {
        "nodes": [serialize_node(n) for n in nodes],
        "edges": [serialize_edge(e) for e in edges],
        "closures": [serialize_closure(c) for c in closures]
    }

@app.get("/map/visualization")
def get_map_visualization(db: Annotated[Session, Depends(get_db)], level: int = None):
    """Get map data optimized for frontend visualization with grouped nodes by type."""
    query = db.query(Node)
    
    if level is not None:
        query = query.filter(Node.level == level)
    
    nodes = query.all()
    
    # Group nodes by type for easier frontend rendering
    grouped_nodes = {
        "navigation": [],
        "gates": [],
        "pois": [],
        "seats": [],
        "stairs": [],
        "departments": [],
    }
    
    for node in nodes:
        node_data = {
            "id": node.id,
            "x": node.x,
            "y": node.y,
            "level": node.level,
            "name": node.name,
            "description": node.description
        }
        
        if node.type in ["corridor", "normal"]:
            grouped_nodes["navigation"].append(node_data)
        elif node.type == "gate":
            grouped_nodes["gates"].append({
                **node_data,
                "num_servers": node.num_servers,
                "service_rate": node.service_rate
            })
        elif node.type == "stairs":
            grouped_nodes["stairs"].append(node_data)
        elif node.type == "seat":
            grouped_nodes["seats"].append({
                **node_data,
                "block": node.block,
                "row": node.row,
                "number": node.number
            })
        elif node.type == "departments":
            grouped_nodes["departments"].append({
                **node_data,
                "type": node.type
            })
        else:
            # POIs: restroom, food, bar, emergency_exit, first_aid, information, merchandise
            grouped_nodes["pois"].append({
                **node_data,
                "type": node.type,
                "num_servers": node.num_servers,
                "service_rate": node.service_rate
            })
    
    # Get edges for the selected level(s)
    if level is not None:
        edges = db.query(Edge).join(Node, Edge.from_id == Node.id).filter(Node.level == level).all()
    else:
        edges = db.query(Edge).all()
    
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

@app.get("/seats/{seat_id}", response_model=NodeResponse)
def get_seat(seat_id: str, db: Annotated[Session, Depends(get_db)]):
    """Get a specific seat by ID."""
    seat = db.query(Node).filter(Node.id == seat_id).first()
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")
    return seat

# (A função /map/preview foi removida)

# ================== NODES ==================

@app.get("/nodes", response_model=List[NodeResponse])
def get_nodes(db: Annotated[Session, Depends(get_db)]):
    """Get all nodes."""
    return db.query(Node).all()

@app.get("/nodes/{node_id}", response_model=NodeResponse)
def get_node(node_id: str, db: Annotated[Session, Depends(get_db)]):
    """Get a specific node by ID."""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node

@app.post("/nodes", response_model=NodeResponse, status_code=201)
def create_node(data: NodeCreate, db: Annotated[Session, Depends(get_db)]):
    """Create a new node."""
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

@app.put("/nodes/{node_id}", response_model=NodeResponse)
def update_node(node_id: str, data: NodeUpdate, db: Annotated[Session, Depends(get_db)]):
    """Update an existing node. Sending null for an optional field clears it."""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

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

@app.delete("/nodes/{node_id}")
def delete_node(node_id: str, db: Annotated[Session, Depends(get_db)]):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    try:
        # Delete edges that reference this node
        db.query(Edge).filter(
            (Edge.from_id == node_id) | (Edge.to_id == node_id)
        ).delete(synchronize_session=False)
        # Delete closures that reference this node
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
def get_edges(db: Annotated[Session, Depends(get_db)]):
    """Get all edges."""
    return db.query(Edge).all()

@app.get("/edges/{edge_id}", response_model=EdgeResponse)
def get_edge(edge_id: str, db: Annotated[Session, Depends(get_db)]):
    """Get a specific edge by ID."""
    edge = db.query(Edge).filter(Edge.id == edge_id).first()
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    return edge

@app.post("/edges", response_model=EdgeResponse, status_code=201)
def create_edge(data: EdgeCreate, db: Annotated[Session, Depends(get_db)]):
    """Create a new edge between two nodes."""
    existing = db.query(Edge).filter(Edge.id == data.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Edge already exists")
    
    # Validate that both nodes exist
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

@app.put("/edges/{edge_id}", response_model=EdgeResponse)
def update_edge(edge_id: str, data: EdgeUpdate, db: Annotated[Session, Depends(get_db)]):
    """Update an existing edge."""
    edge = db.query(Edge).filter(Edge.id == edge_id).first()
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    
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

@app.delete("/edges/{edge_id}")
def delete_edge(edge_id: str, db: Annotated[Session, Depends(get_db)]):
    """Delete an edge."""
    edge = db.query(Edge).filter(Edge.id == edge_id).first()
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    
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
def get_closures(db: Annotated[Session, Depends(get_db)]):
    """Get all closures."""
    return db.query(Closure).all()

@app.get("/closures/{closure_id}", response_model=ClosureResponse)
def get_closure(closure_id: str, db: Annotated[Session, Depends(get_db)]):
    """Get a specific closure by ID."""
    closure = db.query(Closure).filter(Closure.id == closure_id).first()
    if not closure:
        raise HTTPException(status_code=404, detail="Closure not found")
    return closure

@app.post("/closures", response_model=ClosureResponse, status_code=201)
def add_closure(data: ClosureCreate, db: Annotated[Session, Depends(get_db)]):
    """Create a new closure."""
    existing = db.query(Closure).filter(Closure.id == data.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Closure already exists")
    
    # Validate references
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
    
    closure = Closure(
        id=data.id,
        reason=data.reason,
        edge_id=data.edge_id,
        node_id=data.node_id
    )
    db.add(closure)
    try:
        db.commit()
        db.refresh(closure)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    notify_routing_refresh()
    return closure

@app.delete("/closures/{closure_id}")
def delete_closure(closure_id: str, db: Annotated[Session, Depends(get_db)]):
    """Delete a closure."""
    closure = db.query(Closure).filter(Closure.id == closure_id).first()
    if not closure:
        raise HTTPException(status_code=404, detail="Closure not found")
    
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
    """Get grid configuration."""
    return {
        "cell_size": grid_manager.cell_size,
        "origin_x": grid_manager.origin_x,
        "origin_y": grid_manager.origin_y
    }

@app.get("/maps/grid/tiles")
def get_all_tiles(db: Annotated[Session, Depends(get_db)], level: Optional[int] = None):
    """Get all tiles, optionally filtered by level."""
    query = db.query(Tile)
    if level is not None:
        query = query.filter(Tile.level == level)
    tiles = query.all()
    result = []
    for tile in tiles:
        node_count = len([nid for nid in tile.node_id.split(',') if nid]) if tile.node_id else 0
        poi_count = len([pid for pid in tile.poi_id.split(',') if pid]) if tile.poi_id else 0
        seat_count = len([sid for sid in tile.seat_id.split(',') if sid]) if tile.seat_id else 0
        gate_count = len([gid for gid in tile.gate_id.split(',') if gid]) if tile.gate_id else 0
        result.append({
            "id": tile.id,
            "grid_x": tile.grid_x,
            "grid_y": tile.grid_y,
            "level": tile.level,
            "bounds": {
                "min_x": tile.min_x,
                "max_x": tile.max_x,
                "min_y": tile.min_y,
                "max_y": tile.max_y
            },
            "walkable": tile.walkable,
            "entity_counts": {
                "nodes": node_count,
                "pois": poi_count,
                "seats": seat_count,
                "gates": gate_count,
                "total": node_count + poi_count + seat_count + gate_count
            }
        })
    
    return {
        "tiles": result,
        "total_tiles": len(result)
    }

@app.post("/maps/grid/rebuild")
def rebuild_grid(db: Annotated[Session, Depends(get_db)]):

    try:
        tile_count = grid_manager.rebuild_grid(db)
        return {
            "status": "success",
            "message": f"Grid rebuilt with {tile_count} tiles.",
            "tiles_created": tile_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid rebuild failed: {str(e)}")

@app.post("/maps/grid/tiles/nodes")
def get_nodes_from_tiles(tile_ids: List[str], db: Annotated[Session, Depends(get_db)]):
    """
    Resolve tile IDs to node IDs for emergency closures.
    
    Given a list of tile IDs (e.g., ["tile_180_80_0", "tile_179_85_0"]),
    returns all node IDs contained within those tiles.
    """
    if not tile_ids:
        return {"node_ids": [], "tile_count": 0}
    
    tiles = db.query(Tile).filter(Tile.id.in_(tile_ids)).all()
    
    all_node_ids = set()
    for tile in tiles:
        if tile.node_id:
            node_ids = [nid.strip() for nid in tile.node_id.split(',') if nid.strip()]
            all_node_ids.update(node_ids)
        if tile.poi_id:
            poi_ids = [pid.strip() for pid in tile.poi_id.split(',') if pid.strip()]
            all_node_ids.update(poi_ids)
        if tile.gate_id:
            gate_ids = [gid.strip() for gid in tile.gate_id.split(',') if gid.strip()]
            all_node_ids.update(gate_ids)
    
    return {
        "node_ids": list(all_node_ids),
        "tile_count": len(tiles),
        "tiles_found": [t.id for t in tiles]
    }
    
@app.get("/maps/grid/stats")
def get_grid_stats(db: Annotated[Session, Depends(get_db)]):
    """Get grid statistics."""
    tiles = db.query(Tile).all()
    
    total_nodes: int = sum(
        len([i for i in str(tile.node_id).split(',') if i]) for tile in tiles if tile.node_id
    )
    total_pois: int = sum(
        len([i for i in str(tile.poi_id).split(',') if i]) for tile in tiles if tile.poi_id
    )
    total_seats: int = sum(
        len([i for i in str(tile.seat_id).split(',') if i]) for tile in tiles if tile.seat_id
    )
    total_gates: int = sum(
        len([i for i in str(tile.gate_id).split(',') if i]) for tile in tiles if tile.gate_id
    )
    
    return {
        "total_tiles": len(tiles),
        "entities_indexed": {
            "nodes": total_nodes,
            "pois": total_pois,
            "seats": total_seats,
            "gates": total_gates,
            "total": total_nodes + total_pois + total_seats + total_gates
        },
        "configuration": {
            "cell_size": grid_manager.cell_size,
            "origin_x": grid_manager.origin_x,
            "origin_y": grid_manager.origin_y
        }
    }

# ================== POIs ==================
# Now handled via Node endpoints with type filtering

@app.get("/pois", response_model=List[NodeResponse])
def get_pois(db: Annotated[Session, Depends(get_db)]):
    """Get all POI nodes (restroom, food, emergency_exit, etc)."""
    poi_types = [
        'poi', 'restroom', 'wc', 'entrance', 'food', 'shop', 'bar',
        'emergency_exit', 'first_aid', 'information', 'merchandise'
    ]
    pois = db.query(Node).filter(Node.type.in_(poi_types)).all()
    return pois

# ================== OSM POIs (Dynamic) ==================

# In-memory cache for OSM POI queries
_osm_poi_cache: dict = {"data": None, "timestamp": 0}
_OSM_CACHE_TTL = 3600  # 1 hour

# UA Santiago Campus bounding box
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

# Separate query for entrance nodes
_OVERPASS_ENTRANCE_QUERY = f"""
[out:json];
node["entrance"]({_UA_BBOX});
out;
"""

def _osm_tag_to_type(tags: dict) -> str:
    """Map OSM tags to internal POI type."""
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
    if amenity == "university" or amenity == "school" or amenity == "college":
        return "departments"
    if shop:
        return "shop"
    if tourism:
        return "poi"
    return "poi"


def _haversine(lon1, lat1, lon2, lat2):
    """Distance in meters between two GPS points."""
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@app.get("/pois/osm")
def get_osm_pois(db: Annotated[Session, Depends(get_db)]):
    """
    Fetch POIs dynamically from OpenStreetMap Overpass API.
    Results are cached in memory for 1 hour.
    Each POI is snapped to the nearest walkable node in the DB graph.
    Response format matches /pois for Flutter compatibility.
    """
    global _osm_poi_cache

    now = time.time()
    if _osm_poi_cache["data"] is not None and (now - _osm_poi_cache["timestamp"]) < _OSM_CACHE_TTL:
        return _osm_poi_cache["data"]

    try:
        # Fetch from Overpass API
        data = urllib.parse.urlencode({"data": _OVERPASS_POI_QUERY}).encode("utf-8")
        req = urllib.request.Request(_OVERPASS_URL, data=data)
        with urllib.request.urlopen(req, timeout=30) as resp:
            osm_data = json_module.loads(resp.read().decode("utf-8"))
    except Exception as e:
        # If Overpass fails, return cached data if available, otherwise empty
        import traceback
        print(f"[OSM POIs] Main query failed: {e}")
        traceback.print_exc()
        if _osm_poi_cache["data"]:
            return _osm_poi_cache["data"]
        # return empty list instead of crashing app
        return {"pois": [], "total": 0, "source": "openstreetmap", "error": str(e)}

    # Also fetch entrance nodes for building entrance snapping
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

    # Load walkable nodes from DB for snapping
    walkable_nodes = db.query(Node).filter(Node.type == "normal").all()

    pois = []
    seen_names = set()  # deduplicate by name

    for el in osm_data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("alt_name") or tags.get("short_name")
        if not name:
            continue

        # Deduplicate (same building can appear as node + way)
        if name.lower() in seen_names:
            continue
        seen_names.add(name.lower())

        # Get coordinates — prefer entrance if available
        if el["type"] == "node":
            lon, lat = el["lon"], el["lat"]
        elif el["type"] == "way" and "center" in el:
            # For buildings: check if we have an entrance node nearby
            center_lon, center_lat = el["center"]["lon"], el["center"]["lat"]
            lon, lat = center_lon, center_lat

            # Look for entrance nodes within 50m of building center
            best_entrance_dist = float("inf")
            for ent in entrance_nodes:
                ent_dist = _haversine(center_lon, center_lat, ent["lon"], ent["lat"])
                if ent_dist < 50 and ent_dist < best_entrance_dist:
                    best_entrance_dist = ent_dist
                    lon, lat = ent["lon"], ent["lat"]  # Use entrance coords for snap
        else:
            continue

        # Find nearest walkable node (within 100m)
        nearest_id = None
        min_dist = float("inf")
        for wn in walkable_nodes:
            d = _haversine(lon, lat, wn.x, wn.y)
            if d < min_dist:
                min_dist = d
                nearest_id = wn.id

        if nearest_id is None or min_dist > 100:
            continue

        poi_type = _osm_tag_to_type(tags)
        description = tags.get("description", name)

        pois.append({
            "id": f"OSM-{el['id']}",
            "name": name,
            "type": poi_type,
            "description": description,
            "x": lon,
            "y": lat,
            "level": 0,
            "nearest_node_id": nearest_id,
            "distance_to_node_m": round(float(min_dist), 1),
        })

    result = {
        "pois": pois,
        "total": len(pois),
        "source": "openstreetmap",
        "cached_at": now,
    }

    _osm_poi_cache = {"data": result, "timestamp": now}
    print(f"[OSM POIs] Fetched {len(pois)} POIs from Overpass API")

    return result

@app.get("/pois/{poi_id}", response_model=NodeResponse)
def get_poi(poi_id: str, db: Annotated[Session, Depends(get_db)]):
    """Get a specific POI node by ID."""
    poi = db.query(Node).filter(Node.id == poi_id).first()
    if not poi:
        raise HTTPException(status_code=404, detail="POI not found")
    return poi

@app.put("/pois/{poi_id}", response_model=NodeResponse)
def update_poi(poi_id: str, data: NodeUpdate, db: Annotated[Session, Depends(get_db)]):
    """Update an existing POI node."""
    poi = db.query(Node).filter(Node.id == poi_id).first()
    if not poi:
        raise HTTPException(status_code=404, detail="POI not found")
    
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


@app.post("/pois", response_model=NodeResponse, status_code=201)
def create_poi(data: POICreate, db: Annotated[Session, Depends(get_db)]):
    """
    Create a custom POI (e.g. for events).
    Auto-generates an ID and links to nearest walkable node.
    """
    import uuid
    poi_id = f"CUSTOM-{uuid.uuid4().hex[:8]}"

    new_poi = Node(
        id=poi_id,
        name=data.name,
        type=data.type,
        x=data.x,
        y=data.y,
        level=data.level,
        description=data.description or data.name,
    )

    try:
        db.add(new_poi)
        db.commit()
        db.refresh(new_poi)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    print(f"[POI] Created custom POI '{data.name}' ({poi_id}) at ({data.x}, {data.y})")
    return new_poi


@app.delete("/pois/{poi_id}")
def delete_poi(poi_id: str, db: Annotated[Session, Depends(get_db)]):
    """Delete a custom POI."""
    poi = db.query(Node).filter(Node.id == poi_id).first()
    if not poi:
        raise HTTPException(status_code=404, detail="POI not found")
    db.delete(poi)
    db.commit()
    return {"status": "deleted", "id": poi_id}


# ================== SEATS ==================
# Now handled via Node endpoints with type='seat'

@app.get("/seats", response_model=List[NodeResponse])
def get_seats(db: Annotated[Session, Depends(get_db)], block: Optional[str] = None):
    """Get all seat nodes, optionally filtered by block."""
    query = db.query(Node).filter(Node.type == 'seat')
    if block:
        query = query.filter(Node.block == block)
    return query.all()

@app.get("/seats/{seat_id}", response_model=NodeResponse)
def get_seat(seat_id: str, db: Annotated[Session, Depends(get_db)]):
    """Get a specific seat node by ID."""
    seat = db.query(Node).filter(Node.id == seat_id).first()
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")
    return seat

@app.put("/seats/{seat_id}", response_model=NodeResponse)
def update_seat(seat_id: str, data: NodeUpdate, db: Annotated[Session, Depends(get_db)]):
    """Update an existing seat node."""
    seat = db.query(Node).filter(Node.id == seat_id).first()
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")
    
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
# Now handled via Node endpoints with type='gate'

@app.get("/gates", response_model=List[NodeResponse])
def get_gates(db: Annotated[Session, Depends(get_db)]):
    """Get all gate nodes."""
    return db.query(Node).filter(Node.type == 'gate').all()

@app.get("/gates/{gate_id}", response_model=NodeResponse)
def get_gate(gate_id: str, db: Annotated[Session, Depends(get_db)]):
    """Get a specific gate node by ID."""
    gate = db.query(Node).filter(Node.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")
    return gate

@app.put("/gates/{gate_id}", response_model=NodeResponse)
def update_gate(gate_id: str, data: NodeUpdate, db: Annotated[Session, Depends(get_db)]):
    """Update an existing gate node."""
    gate = db.query(Node).filter(Node.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")
    
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
    """Helper function to convert a Node to a GeoJSON Feature."""
    feature = {
        "type": "Feature",
        "id": node.id,
        "geometry": {
            "type": "Point",
            "coordinates": [node.x, node.y]
        },
        "properties": {
            "id": node.id,
            "name": node.name,
            "type": node.type,
            "level": node.level,
            "description": node.description,
        }
    }
    # Add optional properties only if present
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
    """Helper function to create GeoJSON features for edges."""
    features = []
    edge_query = db.query(Edge)
    if level is not None:
        level_node_ids = [n.id for n in nodes]
        edge_query = edge_query.filter(Edge.from_id.in_(level_node_ids))
    
    for e in edge_query.all():
        from_node = node_map.get(e.from_id)
        to_node = node_map.get(e.to_id)
        
        if from_node and to_node:
            features.append({
                "type": "Feature",
                "id": e.id,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [from_node.x, from_node.y],
                        [to_node.x, to_node.y]
                    ]
                },
                "properties": {
                    "id": e.id,
                    "type": "edge",
                    "weight": e.weight,
                    "from_id": e.from_id,
                    "to_id": e.to_id
                }
            })
    return features


def _calculate_bounds(nodes: list) -> Optional[dict]:
    """Helper function to calculate map bounds from nodes."""
    if not nodes:
        return None
    xs = [n.x for n in nodes]
    ys = [n.y for n in nodes]
    return {
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys)
    }


@app.get("/map/geojson")
def get_map_geojson(
    db: Annotated[Session, Depends(get_db)],
    level: Optional[int] = Query(None, description="Filter by floor level (0, 1, 2)"),
    types: Optional[str] = Query(None, description="Comma-separated node types: gate,poi,stairs,corridor,seat"),
    include_edges: bool = Query(True, description="Include edges as LineStrings"),
    include_seats: bool = Query(False, description="Include seat nodes (warning: many!)")
):
    """
    Get map data in GeoJSON format for frontend visualization.
    
    Returns a FeatureCollection with:
    - Points for nodes (gates, POIs, stairs, etc.)
    - LineStrings for edges (connections between nodes)
    
    Optimizations:
    - Filter by level to reduce payload
    - Exclude seats by default (there are thousands)
    - Response is GZip compressed automatically
    - ETag header for HTTP caching
    """
    # Build query with filters
    query = db.query(Node)
    
    if level is not None:
        query = query.filter(Node.level == level)
    
    if types:
        type_list = [t.strip() for t in types.split(',')]
        query = query.filter(Node.type.in_(type_list))
    
    if not include_seats:
        query = query.filter(Node.type != 'seat')
    
    nodes = query.all()
    
    # Convert nodes to GeoJSON features
    features = []
    node_map = {}
    
    for n in nodes:
        node_map[n.id] = n
        features.append(_create_node_feature(n))
    
    # Add edges as LineStrings
    if include_edges:
        features.extend(_create_edge_features(db, nodes, node_map, level))
    
    # Calculate bounds for viewport
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
    
    # Generate ETag for HTTP caching (MD5 is safe here - used only for cache fingerprinting, not security)
    # nosemgrep: python.lang.security.insecure-hash-function-md5.insecure-hash-function-md5
    etag = hashlib.md5(f"{len(features)}:{level}:{types}".encode()).hexdigest()[:16]
    
    return JSONResponse(
        content=result,
        headers={
            "ETag": f'"{etag}"',
            "Cache-Control": "public, max-age=300"
        }
    )


@app.get("/map/geojson/level/{level}")
def get_level_geojson(level: int, db: Annotated[Session, Depends(get_db)]):
    """
    Shortcut endpoint to get GeoJSON for a specific floor level.
    Excludes seats for performance.
    """
    return get_map_geojson(db=db, level=level, types=None, include_edges=True, include_seats=False)


@app.get("/map/bounds")
def get_map_bounds(db: Annotated[Session, Depends(get_db)]):
    """
    Get map boundaries and metadata for initial viewport configuration.
    
    Returns:
    - bounds: min/max coordinates
    - center: calculated center point  
    - levels: available floor levels
    """
    result = db.query(
        func.min(Node.x).label('min_x'),
        func.max(Node.x).label('max_x'),
        func.min(Node.y).label('min_y'),
        func.max(Node.y).label('max_y')
    ).first()
    
    # Get distinct levels
    levels = [row[0] for row in db.query(Node.level).distinct().order_by(Node.level).all()]
    
    return {
        "bounds": {
            "min_x": result.min_x,
            "max_x": result.max_x,
            "min_y": result.min_y,
            "max_y": result.max_y
        },
        "center": {
            "x": (result.min_x + result.max_x) / 2,
            "y": (result.min_y + result.max_y) / 2
        },
        "levels": levels
    }


@app.get("/map/geojson/pois")
def get_pois_geojson(db: Annotated[Session, Depends(get_db)], level: Optional[int] = None):
    """
    Get only POI nodes in GeoJSON format (optimized for markers layer).
    
    Includes: gates, restrooms, food, bars, stairs, ramps, emergency exits, 
    first aid, information, merchandise, and departments.
    """
    poi_types = [
        'gate', 'restroom', 'food', 'bar', 'stairs', 'ramp',
        'emergency_exit', 'first_aid', 'information', 'merchandise',
        'departments',
    ]
    return get_map_geojson(
        db=db,
        level=level, 
        types=','.join(poi_types), 
        include_edges=False,
        include_seats=False
    )

# ================== EMERGENCY ROUTES ==================

@app.get("/emergency-routes", response_model=List[EmergencyRouteResponse])
def list_emergency_routes(db: Annotated[Session, Depends(get_db)]):
    """
    List all predefined emergency evacuation routes.
    
    Returns a list of routes with their IDs, names, and exit points.
    Use the route ID to get the full path in GeoJSON format.
    """
    routes = db.query(EmergencyRoute).all()
    return routes


@app.get("/emergency-routes/nearest")
def get_nearest_emergency_route(
    db: Annotated[Session, Depends(get_db)],
    x: float = Query(..., description="Current X coordinate"),
    y: float = Query(..., description="Current Y coordinate"),
    level: int = Query(0, description="Current floor level")
):
    """
    Find the nearest emergency evacuation route based on current position.
    
    Returns the closest route's start point and distance to it.
    """
    routes = db.query(EmergencyRoute).all()
    
    if not routes:
        raise HTTPException(status_code=404, detail="No emergency routes defined")
    
    # Get all start nodes (first node of each route)
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
        
        # Calculate Euclidean distance
        distance = math.sqrt((x - start_node.x) ** 2 + (y - start_node.y) ** 2)
        
        # Prefer routes on the same level
        if start_node.level != level:
            distance += 100  # Penalty for level change
        
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
        "start_node": {
            "id": nearest_start_node.id,
            "x": nearest_start_node.x,
            "y": nearest_start_node.y,
            "level": nearest_start_node.level
        },
        "distance_to_start": round(min_distance, 2),
        "num_waypoints": len(nearest_route.node_ids)
    }


@app.get("/emergency-routes/{route_id}")
def get_emergency_route_geojson(route_id: str, db: Annotated[Session, Depends(get_db)]):
    """
    Get a specific emergency route in GeoJSON format.
    
    Returns the complete evacuation path as a LineString with all waypoints.
    """
    route = db.query(EmergencyRoute).filter(EmergencyRoute.id == route_id).first()
    
    if not route:
        raise HTTPException(status_code=404, detail=f"Emergency route '{route_id}' not found")
    
    # Get all nodes in the path
    path_nodes = {n.id: n for n in db.query(Node).filter(Node.id.in_(route.node_ids)).all()}
    
    # Build route coordinates
    coordinates = []
    waypoint_features = []
    
    for idx, node_id in enumerate(route.node_ids):
        node = path_nodes.get(node_id)
        if node:
            coordinates.append([node.x, node.y])
            
            # Add waypoint marker
            if idx == 0:
                role = "start"
            elif idx == len(route.node_ids) - 1:
                role = "exit"
            else:
                role = "waypoint"
            waypoint_features.append({
                "type": "Feature",
                "id": f"wp_{node_id}",
                "geometry": {
                    "type": "Point",
                    "coordinates": [node.x, node.y]
                },
                "properties": {
                    "id": node_id,
                    "name": node.name,
                    "type": node.type,
                    "level": node.level,
                    "role": role,
                    "order": idx
                }
            })
    
    features = [
        # The route line
        {
            "type": "Feature",
            "id": f"route_{route_id}",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            },
            "properties": {
                "type": "emergency_route",
                "route_id": route.id,
                "route_name": route.name,
                "exit_id": route.exit_id,
                "num_waypoints": len(route.node_ids)
            }
        }
    ] + waypoint_features
    
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "route_id": route.id,
            "route_name": route.name,
            "description": route.description,
            "exit_id": route.exit_id,
            "node_ids": route.node_ids,
            "num_waypoints": len(route.node_ids)
        }
    }

# ================== CAMERAS ==================

@app.get("/cameras", response_model=List[CameraResponse])
def get_cameras(db: Annotated[Session, Depends(get_db)]):
    """List all cameras."""
    return db.query(Camera).all()

@app.get("/cameras/{camera_id}", response_model=CameraResponse)
def get_camera(camera_id: str, db: Annotated[Session, Depends(get_db)]):
    """Get a specific camera by ID."""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera

@app.post("/cameras", response_model=CameraResponse, status_code=201)
def create_camera(data: CameraCreate, db: Annotated[Session, Depends(get_db)]):
    """Create a new camera and link it to an existing node (type=camera)."""
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

@app.put("/cameras/{camera_id}", response_model=CameraResponse)
def update_camera(camera_id: str, data: CameraUpdate, db: Annotated[Session, Depends(get_db)]):
    """Update camera calibration data."""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(camera, field, value)
    try:
        db.commit()
        db.refresh(camera)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    return camera

@app.delete("/cameras/{camera_id}")
def delete_camera(camera_id: str, db: Annotated[Session, Depends(get_db)]):
    """Delete a camera record (does NOT delete the linked node)."""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    try:
        db.delete(camera)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    return {"deleted": camera_id}

# ================== RESET ==================

# ================== HEALTH CHECK ==================

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# ================== DATA MANAGEMENT ==================

@app.post("/reset")
def reset_data(db: Annotated[Session, Depends(get_db)]):
    """Reset database to initial state with sample data."""
    from load_data_db import clear_all_data, load_sample_data
    
    try:
        print("Resetting database...")
        clear_all_data(db)
        load_sample_data(db)
        print("Database reset complete")

        print("Rebuilding grid...")
        tile_count = grid_manager.rebuild_grid(db)
        print(f"Grid rebuilt with {tile_count} tiles.")
        
        return {
            "status": "success",
            "message": "Database reset to initial state with sample data",
            "tiles_created": tile_count
        }
    except Exception as e:
        print(f"Reset failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")

# ================== BATCH IMPORT ==================
@app.post("/batch", status_code=201)
def create_batch(data: BatchCreate, db: Annotated[Session, Depends(get_db)]):
    """
    Create multiple nodes, edges, and closures in a single request.
    Notifies routing service only once at the end.
    """
    results = {
        "nodes": {"created": [], "errors": []},
        "edges": {"created": [], "errors": []},
        "closures": {"created": [], "errors": []},
    }

    existing_nodes = set(r[0] for r in db.query(Node.id).all())

    # Add nodes
    for node_data in data.nodes:
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

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error committing nodes: {str(e)}")

    existing_edges = set(r[0] for r in db.query(Edge.id).all())

    # Add edges
    for edge_data in data.edges:
        try:
            if edge_data.id in existing_edges:
                results["edges"]["errors"].append({"id": edge_data.id, "error": "Edge already exists"})
                continue
            
            # validate nodes
            if edge_data.from_id not in existing_nodes or edge_data.to_id not in existing_nodes:
                results["edges"]["errors"].append({"id": edge_data.id, "error": f"One or both nodes do not exist ({edge_data.from_id}, {edge_data.to_id})"})
                continue

            edge = Edge(**edge_data.model_dump())
            db.add(edge)
            results["edges"]["created"].append(edge.id)
            existing_edges.add(edge.id)
        except Exception as e:
            results["edges"]["errors"].append({"id": getattr(edge_data, 'id', 'unknown'), "error": str(e)})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error committing edges: {str(e)}")

    existing_closures = set(r[0] for r in db.query(Closure.id).all())

    # Add closures
    for closure_data in data.closures:
        try:
            if closure_data.id in existing_closures:
                results["closures"]["errors"].append({"id": closure_data.id, "error": "Closure already already exists"})
                continue
            
            closure = Closure(**closure_data.model_dump())
            db.add(closure)
            results["closures"]["created"].append(closure.id)
            existing_closures.add(closure.id)
        except Exception as e:
            results["closures"]["errors"].append({"id": getattr(closure_data, 'id', 'unknown'), "error": str(e)})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error committing closures: {str(e)}")

    # Only notify routing once if something was actually created
    if results["nodes"]["created"] or results["edges"]["created"] or results["closures"]["created"]:
        notify_routing_refresh()

    return results


# ================== MAP SYNC ==================
@app.post("/map/sync", status_code=200)
def sync_map(data: BatchCreate, db: Annotated[Session, Depends(get_db)]):
    """
    Overwrites the entire map with the provided nodes, edges, and closures.
    Rebuilds the grid index and notifies the routing service.
    """
    try:
        # Clear existing data (Camera first — FK references nodes)
        db.query(Camera).delete()
        db.query(Closure).delete()
        db.query(Edge).delete()
        db.query(Node).delete()
        db.query(Tile).delete()

        # Insert new data
        for node_data in data.nodes:
            db.add(Node(**node_data.model_dump()))
            
        for edge_data in data.edges:
            db.add(Edge(**edge_data.model_dump()))
            
        for closure_data in data.closures:
            db.add(Closure(**closure_data.model_dump()))    
            
        db.commit()

        # Rebuild grid
        grid_manager = GridManager(cell_size=5.0, origin_x=0.0, origin_y=0.0)
        grid_manager.rebuild_grid(db)

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error during sync: {str(e)}")

    notify_routing_refresh()
    return {"status": "success", "message": "Map synchronized successfully"}