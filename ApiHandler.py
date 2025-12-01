from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from database import get_db, init_db
from models import (
    Node, Edge, Closure, Tile, POI, Seat, Gate,
    NodeCreate, NodeUpdate, NodeResponse,
    EdgeCreate, EdgeUpdate, EdgeResponse,
    ClosureCreate, ClosureResponse,
    TileCreate, TileUpdate, TileResponse,
    POICreate, POIUpdate, POIResponse,
    SeatCreate, SeatUpdate, SeatResponse,
    GateCreate, GateUpdate, GateResponse
)

app = FastAPI(title="Smart Stadium Map Backend")

# ================== STARTUP ==================

@app.on_event("startup")
def startup():
    init_db()
    print("Database initialized")

# ================== HELPERS ==================

def serialize_node(n: Node) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "x": n.x,
        "y": n.y,
        "level": n.level,
    }

def serialize_edge(e: Edge) -> dict:
    return {
        "id": e.id,
        "from": e.from_id,
        "to": e.to_id,
        "w": e.weight
    }

def serialize_closure(c: Closure) -> dict:
    return {
        "id": c.id,
        "node_id": c.node_id,
        "edge_id": c.edge_id,
        "reason": c.reason
    }

# ================== MAP ==================

@app.get("/api/map")
def get_map(db: Session = Depends(get_db)):
    """Get complete map with nodes, edges, and closures."""
    nodes = db.query(Node).all()
    edges = db.query(Edge).all()
    closures = db.query(Closure).all()
    
    return {
        "nodes": [serialize_node(n) for n in nodes],
        "edges": [serialize_edge(e) for e in edges],
        "closures": [serialize_closure(c) for c in closures]
    }

# ================== NODES ==================

@app.get("/api/nodes", response_model=List[NodeResponse])
def get_nodes(db: Session = Depends(get_db)):
    """Get all nodes."""
    return db.query(Node).all()

@app.get("/api/nodes/{node_id}", response_model=NodeResponse)
def get_node(node_id: str, db: Session = Depends(get_db)):
    """Get a specific node by ID."""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node

# @app.post("/api/nodes", response_model=NodeResponse, status_code=201)
# def add_node(data: NodeCreate, db: Session = Depends(get_db)):
#     """Create a new node."""
#     existing = db.query(Node).filter(Node.id == data.id).first()
#     if existing:
#         raise HTTPException(status_code=400, detail="Node already exists")
    
#     node = Node(
#         id=data.id,
#         x=data.x,
#         y=data.y,
#         level=data.level,
#         type=data.type
#     )
#     db.add(node)
#     try:
#         db.commit()
#         db.refresh(node)
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
#     return node

@app.put("/api/nodes/{node_id}", response_model=NodeResponse)
def update_node(node_id: str, data: NodeUpdate, db: Session = Depends(get_db)):
    """Update an existing node."""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    if data.x is not None:
        node.x = data.x
    if data.y is not None:
        node.y = data.y
    if data.level is not None:
        node.level = data.level
    if data.type is not None:
        node.type = data.type
    
    try:
        db.commit()
        db.refresh(node)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    return node

# @app.delete("/api/nodes/{node_id}")
# def delete_node(node_id: str, db: Session = Depends(get_db)):
#     """Delete a node. Will also delete related edges and closures due to CASCADE."""
#     node = db.query(Node).filter(Node.id == node_id).first()
#     if not node:
#         raise HTTPException(status_code=404, detail="Node not found")
    
#     try:
#         db.delete(node)
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
#     return {"deleted": node_id}

# ================== EDGES ==================

@app.get("/api/edges", response_model=List[EdgeResponse])
def get_edges(db: Session = Depends(get_db)):
    """Get all edges."""
    return db.query(Edge).all()

@app.get("/api/edges/{edge_id}", response_model=EdgeResponse)
def get_edge(edge_id: str, db: Session = Depends(get_db)):
    """Get a specific edge by ID."""
    edge = db.query(Edge).filter(Edge.id == edge_id).first()
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    return edge

# @app.post("/api/edges", response_model=EdgeResponse, status_code=201)
# def add_edge(data: EdgeCreate, db: Session = Depends(get_db)):
#     """Create a new edge."""
#     existing = db.query(Edge).filter(Edge.id == data.id).first()
#     if existing:
#         raise HTTPException(status_code=400, detail="Edge already exists")
    
#     # Validate that both nodes exist
#     from_node = db.query(Node).filter(Node.id == data.from_id).first()
#     to_node = db.query(Node).filter(Node.id == data.to_id).first()
    
#     if not from_node:
#         raise HTTPException(status_code=400, detail=f"from_id node '{data.from_id}' does not exist")
#     if not to_node:
#         raise HTTPException(status_code=400, detail=f"to_id node '{data.to_id}' does not exist")
    
#     edge = Edge(
#         id=data.id,
#         from_id=data.from_id,
#         to_id=data.to_id,
#         weight=data.weight
#     )
#     db.add(edge)
#     try:
#         db.commit()
#         db.refresh(edge)
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
#     return edge

@app.put("/api/edges/{edge_id}", response_model=EdgeResponse)
def update_edge(edge_id: str, data: EdgeUpdate, db: Session = Depends(get_db)):
    """Update an existing edge."""
    edge = db.query(Edge).filter(Edge.id == edge_id).first()
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    
    if data.weight is not None:
        edge.weight = data.weight
    
    try:
        db.commit()
        db.refresh(edge)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    return edge

# @app.delete("/api/edges/{edge_id}")
# def delete_edge(edge_id: str, db: Session = Depends(get_db)):
#     """Delete an edge."""
#     edge = db.query(Edge).filter(Edge.id == edge_id).first()
#     if not edge:
#         raise HTTPException(status_code=404, detail="Edge not found")
    
#     try:
#         db.delete(edge)
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
#     return {"deleted": edge_id}

# ================== CLOSURES ==================

@app.get("/api/closures", response_model=List[ClosureResponse])
def get_closures(db: Session = Depends(get_db)):
    """Get all closures."""
    return db.query(Closure).all()

@app.get("/api/closures/{closure_id}", response_model=ClosureResponse)
def get_closure(closure_id: str, db: Session = Depends(get_db)):
    """Get a specific closure by ID."""
    closure = db.query(Closure).filter(Closure.id == closure_id).first()
    if not closure:
        raise HTTPException(status_code=404, detail="Closure not found")
    return closure

@app.post("/api/closures", response_model=ClosureResponse, status_code=201)
def add_closure(data: ClosureCreate, db: Session = Depends(get_db)):
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
    
    return closure

@app.delete("/api/closures/{closure_id}")
def delete_closure(closure_id: str, db: Session = Depends(get_db)):
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

@app.get("/api/tiles", response_model=List[TileResponse])
def get_tiles(db: Session = Depends(get_db)):
    """Get all tiles."""
    return db.query(Tile).all()

@app.get("/api/tiles/{tile_id}", response_model=TileResponse)
def get_tile(tile_id: str, db: Session = Depends(get_db)):
    """Get a specific tile by ID."""
    tile = db.query(Tile).filter(Tile.id == tile_id).first()
    if not tile:
        raise HTTPException(status_code=404, detail="Tile not found")
    return tile

# @app.post("/api/tiles", response_model=TileResponse, status_code=201)
# def add_tile(data: TileCreate, db: Session = Depends(get_db)):
#     """Create a new tile."""
#     existing = db.query(Tile).filter(Tile.id == data.id).first()
#     if existing:
#         raise HTTPException(status_code=400, detail="Tile already exists")
    
#     tile = Tile(
#         id=data.id,
#         grid_x=data.grid_x,
#         grid_y=data.grid_y,
#         walkable=data.walkable
#     )
#     db.add(tile)
#     try:
#         db.commit()
#         db.refresh(tile)
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
#     return tile

@app.put("/api/tiles/{tile_id}", response_model=TileResponse)
def update_tile(tile_id: str, data: TileUpdate, db: Session = Depends(get_db)):
    """Update an existing tile."""
    tile = db.query(Tile).filter(Tile.id == tile_id).first()
    if not tile:
        raise HTTPException(status_code=404, detail="Tile not found")
    
    if data.walkable is not None:
        tile.walkable = data.walkable
    
    try:
        db.commit()
        db.refresh(tile)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    return tile

# @app.delete("/api/tiles/{tile_id}")
# def delete_tile(tile_id: str, db: Session = Depends(get_db)):
#     """Delete a tile."""
#     tile = db.query(Tile).filter(Tile.id == tile_id).first()
#     if not tile:
#         raise HTTPException(status_code=404, detail="Tile not found")
    
#     try:
#         db.delete(tile)
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
#     return {"deleted": tile_id}

# ================== POIs ==================

@app.get("/api/pois", response_model=List[POIResponse])
def get_pois(db: Session = Depends(get_db)):
    """Get all POIs."""
    return db.query(POI).all()

@app.get("/api/pois/{poi_id}", response_model=POIResponse)
def get_poi(poi_id: str, db: Session = Depends(get_db)):
    """Get a specific POI by ID."""
    poi = db.query(POI).filter(POI.id == poi_id).first()
    if not poi:
        raise HTTPException(status_code=404, detail="POI not found")
    return poi

# @app.post("/api/pois", response_model=POIResponse, status_code=201)
# def add_poi(data: POICreate, db: Session = Depends(get_db)):
#     """Create a new POI."""
#     existing = db.query(POI).filter(POI.id == data.id).first()
#     if existing:
#         raise HTTPException(status_code=400, detail="POI already exists")
    
#     poi = POI(
#         id=data.id,
#         name=data.name,
#         category=data.category,
#         x=data.x,
#         y=data.y,
#         level=data.level
#     )
#     db.add(poi)
#     try:
#         db.commit()
#         db.refresh(poi)
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
#     return poi

@app.put("/api/pois/{poi_id}", response_model=POIResponse)
def update_poi(poi_id: str, data: POIUpdate, db: Session = Depends(get_db)):
    """Update an existing POI."""
    poi = db.query(POI).filter(POI.id == poi_id).first()
    if not poi:
        raise HTTPException(status_code=404, detail="POI not found")
    
    if data.name is not None:
        poi.name = data.name
    if data.category is not None:
        poi.category = data.category
    if data.x is not None:
        poi.x = data.x
    if data.y is not None:
        poi.y = data.y
    if data.level is not None:
        poi.level = data.level
    
    try:
        db.commit()
        db.refresh(poi)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    return poi

# @app.delete("/api/pois/{poi_id}")
# def delete_poi(poi_id: str, db: Session = Depends(get_db)):
#     """Delete a POI."""
#     poi = db.query(POI).filter(POI.id == poi_id).first()
#     if not poi:
#         raise HTTPException(status_code=404, detail="POI not found")
    
#     try:
#         db.delete(poi)
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
#     return {"deleted": poi_id}

# ================== SEATS ==================

@app.get("/api/seats", response_model=List[SeatResponse])
def get_seats(db: Session = Depends(get_db)):
    """Get all seats."""
    return db.query(Seat).all()

@app.get("/api/seats/{seat_id}", response_model=SeatResponse)
def get_seat(seat_id: str, db: Session = Depends(get_db)):
    """Get a specific seat by ID."""
    seat = db.query(Seat).filter(Seat.id == seat_id).first()
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")
    return seat

# @app.post("/api/seats", response_model=SeatResponse, status_code=201)
# def add_seat(data: SeatCreate, db: Session = Depends(get_db)):
#     """Create a new seat."""
#     existing = db.query(Seat).filter(Seat.id == data.id).first()
#     if existing:
#         raise HTTPException(status_code=400, detail="Seat already exists")
    
#     seat = Seat(
#         id=data.id,
#         block=data.block,
#         row=data.row,
#         number=data.number,
#         x=data.x,
#         y=data.y,
#         level=data.level
#     )
#     db.add(seat)
#     try:
#         db.commit()
#         db.refresh(seat)
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
#     return seat

@app.put("/api/seats/{seat_id}", response_model=SeatResponse)
def update_seat(seat_id: str, data: SeatUpdate, db: Session = Depends(get_db)):
    """Update an existing seat."""
    seat = db.query(Seat).filter(Seat.id == seat_id).first()
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

# @app.delete("/api/seats/{seat_id}")
# def delete_seat(seat_id: str, db: Session = Depends(get_db)):
#     """Delete a seat."""
#     seat = db.query(Seat).filter(Seat.id == seat_id).first()
#     if not seat:
#         raise HTTPException(status_code=404, detail="Seat not found")
    
#     try:
#         db.delete(seat)
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
#     return {"deleted": seat_id}

# ================== GATES ==================

@app.get("/api/gates", response_model=List[GateResponse])
def get_gates(db: Session = Depends(get_db)):
    """Get all gates."""
    return db.query(Gate).all()

@app.get("/api/gates/{gate_id}", response_model=GateResponse)
def get_gate(gate_id: str, db: Session = Depends(get_db)):
    """Get a specific gate by ID."""
    gate = db.query(Gate).filter(Gate.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")
    return gate

# @app.post("/api/gates", response_model=GateResponse, status_code=201)
# def add_gate(data: GateCreate, db: Session = Depends(get_db)):
#     """Create a new gate."""
#     existing = db.query(Gate).filter(Gate.id == data.id).first()
#     if existing:
#         raise HTTPException(status_code=400, detail="Gate already exists")
    
#     gate = Gate(
#         id=data.id,
#         gate_number=data.gate_number,
#         x=data.x,
#         y=data.y,
#         level=data.level
#     )
#     db.add(gate)
#     try:
#         db.commit()
#         db.refresh(gate)
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
#     return gate

@app.put("/api/gates/{gate_id}", response_model=GateResponse)
def update_gate(gate_id: str, data: GateUpdate, db: Session = Depends(get_db)):
    """Update an existing gate."""
    gate = db.query(Gate).filter(Gate.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")
    
    if data.gate_number is not None:
        gate.gate_number = data.gate_number
    if data.x is not None:
        gate.x = data.x
    if data.y is not None:
        gate.y = data.y
    if data.level is not None:
        gate.level = data.level
    
    try:
        db.commit()
        db.refresh(gate)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    return gate

# @app.delete("/api/gates/{gate_id}")
# def delete_gate(gate_id: str, db: Session = Depends(get_db)):
#     """Delete a gate."""
#     gate = db.query(Gate).filter(Gate.id == gate_id).first()
#     if not gate:
#         raise HTTPException(status_code=404, detail="Gate not found")
    
#     try:
#         db.delete(gate)
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
#     return {"deleted": gate_id}

# ================== HEALTH CHECK ==================

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# ================== DATA MANAGEMENT ==================

@app.post("/api/reset")
def reset_data(db: Session = Depends(get_db)):
    """Reset database to initial state with sample data."""
    from load_data_db import clear_all_data, load_sample_data
    
    try:
        print("Resetting database...")
        clear_all_data()
        load_sample_data()
        print("Database reset complete")
        
        return {
            "status": "success",
            "message": "Database reset to initial state with sample data"
        }
    except Exception as e:
        print(f"❌ Reset failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")