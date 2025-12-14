from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from database import get_db, init_db
from models import (
    Node, Edge, Closure, Tile, EmergencyRoute,
    NodeCreate, NodeUpdate, NodeResponse,
    EdgeCreate, EdgeUpdate, EdgeResponse,
    ClosureCreate, ClosureResponse,
    TileCreate, TileUpdate, TileResponse,
    EmergencyRouteResponse
)
from grid_name import GridManager
import hashlib
import math

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

@app.get("/map")
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

@app.get("/map/visualization")
def get_map_visualization(level: int = None, db: Session = Depends(get_db)):
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
        "stairs": []
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
            "total": len(nodes)
        }
    }

@app.get("/map/preview", response_class=HTMLResponse)
def preview_map(level: int = 0, db: Session = Depends(get_db)):
    """Visual preview of nodes on a 2D canvas with improved UI."""
    nodes = db.query(Node).filter(Node.level == level).all()
    edges = db.query(Edge).join(Node, Edge.from_id == Node.id).filter(Node.level == level).all()
    
    # Count by type
    counts = {
        'corridor': sum(1 for n in nodes if n.type == 'corridor'),
        'row_aisle': sum(1 for n in nodes if n.type == 'row_aisle'),
        'gate': sum(1 for n in nodes if n.type == 'gate'),
        'stairs': sum(1 for n in nodes if n.type in ['stairs', 'ramp']),
        'poi': sum(1 for n in nodes if n.type in ['restroom', 'food', 'bar', 'emergency_exit', 'first_aid', 'information', 'merchandise']),
        'seat': sum(1 for n in nodes if n.type == 'seat'),
    }
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Estádio do Dragão - Nível {level}</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
                min-height: 100vh;
            }}
            h1 {{
                margin: 0 0 15px 0;
                background: linear-gradient(90deg, #00d4ff, #5c7cfa);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-size: 1.8em;
            }}
            .container {{
                max-width: 1500px;
                margin: 0 auto;
            }}
            .controls {{
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                align-items: center;
                padding: 15px;
                background: rgba(255,255,255,0.05);
                border-radius: 12px;
                margin-bottom: 20px;
                backdrop-filter: blur(10px);
            }}
            .btn-group {{
                display: flex;
                gap: 5px;
            }}
            .btn {{
                padding: 10px 20px;
                background: linear-gradient(180deg, #3d5af1 0%, #2541b2 100%);
                color: white;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-weight: 500;
                transition: all 0.2s;
            }}
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(61, 90, 241, 0.4);
            }}
            .btn.active {{
                background: linear-gradient(180deg, #00d4ff 0%, #0099cc 100%);
            }}
            .checkbox-group {{
                display: flex;
                flex-wrap: wrap;
                gap: 15px;
                margin-left: 20px;
            }}
            .checkbox-label {{
                display: flex;
                align-items: center;
                gap: 6px;
                cursor: pointer;
            }}
            .checkbox-label input {{
                width: 18px;
                height: 18px;
                accent-color: #00d4ff;
            }}
            .canvas-container {{
                position: relative;
                background: rgba(0,0,0,0.3);
                border-radius: 12px;
                padding: 10px;
                overflow: hidden;
            }}
            canvas {{
                background: radial-gradient(circle at center, #1e2a3a 0%, #0d1117 100%);
                border-radius: 8px;
                display: block;
            }}
            .zoom-controls {{
                position: absolute;
                top: 20px;
                right: 20px;
                display: flex;
                flex-direction: column;
                gap: 5px;
            }}
            .zoom-btn {{
                width: 36px;
                height: 36px;
                background: rgba(0,0,0,0.7);
                border: 1px solid #444;
                border-radius: 8px;
                color: white;
                font-size: 18px;
                cursor: pointer;
            }}
            .zoom-btn:hover {{ background: rgba(61, 90, 241, 0.5); }}
            .info-panel {{
                margin-top: 15px;
                padding: 15px;
                background: rgba(255,255,255,0.05);
                border-radius: 12px;
                backdrop-filter: blur(10px);
            }}
            .legend {{
                display: flex;
                flex-wrap: wrap;
                gap: 20px;
                margin-top: 10px;
            }}
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            .legend-color {{
                width: 16px;
                height: 16px;
                border-radius: 50%;
                border: 2px solid rgba(255,255,255,0.2);
            }}
            #nodeInfo {{
                font-size: 14px;
                color: #888;
            }}
            #nodeInfo strong {{
                color: #00d4ff;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Estadio do Dragao - Nivel {level}</h1>
            
            <div class="controls">
                <div class="btn-group">
                    <button class="btn {'active' if level == 0 else ''}" onclick="window.location.href='/map/preview?level=0'">Piso 0</button>
                    <button class="btn {'active' if level == 1 else ''}" onclick="window.location.href='/map/preview?level=1'">Piso 1</button>
                </div>
                
                <div class="checkbox-group">
                    <label class="checkbox-label">
                        <input type="checkbox" id="showEdges" checked onchange="draw()">
                        <span>Edges</span>
                    </label>
                    <label class="checkbox-label">
                        <input type="checkbox" id="showCorridors" checked onchange="draw()">
                        <span>Corredores</span>
                    </label>
                    <label class="checkbox-label">
                        <input type="checkbox" id="showAisles" checked onchange="draw()">
                        <span>Aisles</span>
                    </label>
                    <label class="checkbox-label">
                        <input type="checkbox" id="showPOIs" checked onchange="draw()">
                        <span>POIs</span>
                    </label>
                    <label class="checkbox-label">
                        <input type="checkbox" id="showSeats" onchange="draw()">
                        <span>Seats</span>
                    </label>
                    <label class="checkbox-label">
                        <input type="checkbox" id="showLabels" onchange="draw()">
                        <span>Labels</span>
                    </label>
                </div>
            </div>
            
            <div class="canvas-container">
                <canvas id="canvas" width="1400" height="900"></canvas>
                <div class="zoom-controls">
                    <button class="zoom-btn" onclick="zoomIn()">+</button>
                    <button class="zoom-btn" onclick="zoomOut()">−</button>
                    <button class="zoom-btn" onclick="resetZoom()">⟲</button>
                </div>
            </div>
            
            <div class="info-panel">
                <div id="nodeInfo">Passa o rato sobre os nodes para ver detalhes</div>
                <div class="legend">
                    <div class="legend-item">
                        <div class="legend-color" style="background: #4ade80;"></div>
                        <span>Corredores ({counts['corridor']})</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #fbbf24;"></div>
                        <span>Row Aisles ({counts['row_aisle']})</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #60a5fa;"></div>
                        <span>Portões ({counts['gate']})</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #f97316;"></div>
                        <span>Escadas/Rampas ({counts['stairs']})</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #ec4899;"></div>
                        <span>POIs ({counts['poi']})</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #a855f7;"></div>
                        <span>Seats ({counts['seat']})</span>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            const canvas = document.getElementById('canvas');
            const ctx = canvas.getContext('2d');
            
            const nodes = {str([{
                "id": n.id,
                "x": n.x,
                "y": n.y,
                "level": n.level,
                "type": n.type,
                "name": n.name,
                "num_servers": n.num_servers,
                "block": n.block,
                "row": n.row,
                "number": n.number
            } for n in nodes]).replace("'", '"').replace("None", "null")};
            const edges = {str([{"from": e.from_id, "to": e.to_id} for e in edges]).replace("'", '"')};
            
            let scale = 1.3;
            let offsetX = 50;
            let offsetY = 30;
            
            function getNodeColor(type) {{
                const colors = {{
                    'corridor': '#4ade80',
                    'row_aisle': '#fbbf24',
                    'gate': '#60a5fa',
                    'stairs': '#f97316',
                    'ramp': '#f97316',
                    'seat': '#a855f7',
                    'emergency_exit': '#ef4444',
                    'restroom': '#06b6d4',
                    'food': '#f97316',
                    'bar': '#8b5cf6',
                    'first_aid': '#22c55e',
                    'information': '#3b82f6',
                    'merchandise': '#ec4899'
                }};
                return colors[type] || '#ec4899';
            }}
            
            function screenX(x) {{ return x * scale + offsetX; }}
            function screenY(y) {{ return y * scale + offsetY; }}
            
            function zoomIn() {{ scale *= 1.2; draw(); }}
            function zoomOut() {{ scale /= 1.2; draw(); }}
            function resetZoom() {{ scale = 1.3; offsetX = 50; offsetY = 30; draw(); }}
            
            function draw() {{
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                
                const showEdges = document.getElementById('showEdges').checked;
                const showCorridors = document.getElementById('showCorridors').checked;
                const showAisles = document.getElementById('showAisles').checked;
                const showPOIs = document.getElementById('showPOIs').checked;
                const showSeats = document.getElementById('showSeats').checked;
                const showLabels = document.getElementById('showLabels').checked;
                
                // Draw edges
                if (showEdges) {{
                    ctx.strokeStyle = 'rgba(100, 100, 100, 0.3)';
                    ctx.lineWidth = 0.5;
                    edges.forEach(edge => {{
                        const fromNode = nodes.find(n => n.id === edge.from);
                        const toNode = nodes.find(n => n.id === edge.to);
                        if (fromNode && toNode) {{
                            ctx.beginPath();
                            ctx.moveTo(screenX(fromNode.x), screenY(fromNode.y));
                            ctx.lineTo(screenX(toNode.x), screenY(toNode.y));
                            ctx.stroke();
                        }}
                    }});
                }}
                
                // Draw nodes
                nodes.forEach(node => {{
                    if (node.type === 'seat' && !showSeats) return;
                    if (node.type === 'corridor' && !showCorridors) return;
                    if (node.type === 'row_aisle' && !showAisles) return;
                    if (['restroom', 'food', 'bar', 'emergency_exit', 'first_aid', 'information', 'merchandise', 'gate', 'stairs', 'ramp'].includes(node.type) && !showPOIs) return;
                    
                    const x = screenX(node.x);
                    const y = screenY(node.y);
                    
                    let radius = 4;
                    if (node.type === 'seat') radius = 2;
                    else if (node.type === 'gate') radius = 10;
                    else if (node.type === 'row_aisle') radius = 3;
                    else if (['stairs', 'ramp', 'emergency_exit'].includes(node.type)) radius = 8;
                    
                    ctx.fillStyle = getNodeColor(node.type);
                    ctx.beginPath();
                    ctx.arc(x, y, radius, 0, Math.PI * 2);
                    ctx.fill();
                    
                    // Draw labels for POIs
                    if (showLabels && ['gate', 'stairs', 'ramp', 'emergency_exit', 'first_aid', 'restroom', 'food', 'bar'].includes(node.type)) {{
                        ctx.fillStyle = '#fff';
                        ctx.font = '10px Arial';
                        ctx.fillText(node.name || node.id, x + 12, y + 3);
                    }}
                }});
            }}
            
            canvas.addEventListener('mousemove', (e) => {{
                const rect = canvas.getBoundingClientRect();
                const mouseX = e.clientX - rect.left;
                const mouseY = e.clientY - rect.top;
                
                let hoveredNode = null;
                for (let node of nodes) {{
                    const x = screenX(node.x);
                    const y = screenY(node.y);
                    const radius = node.type === 'seat' ? 4 : 10;
                    
                    if (Math.sqrt((mouseX - x)**2 + (mouseY - y)**2) < radius) {{
                        hoveredNode = node;
                        break;
                    }}
                }}
                
                const infoDiv = document.getElementById('nodeInfo');
                if (hoveredNode) {{
                    let info = `<strong>${{hoveredNode.id}}</strong> - ${{hoveredNode.type}}`;
                    if (hoveredNode.name) info += ` | ${{hoveredNode.name}}`;
                    info += ` | (${{hoveredNode.x.toFixed(0)}}, ${{hoveredNode.y.toFixed(0)}})`;
                    if (hoveredNode.block) info += ` | ${{hoveredNode.block}} R${{hoveredNode.row}} S${{hoveredNode.number}}`;
                    infoDiv.innerHTML = info;
                }} else {{
                    infoDiv.innerHTML = 'Passa o rato sobre os nodes para ver detalhes';
                }}
            }});
            
            // Pan with mouse drag
            let isDragging = false;
            let lastX, lastY;
            canvas.addEventListener('mousedown', (e) => {{ isDragging = true; lastX = e.clientX; lastY = e.clientY; }});
            canvas.addEventListener('mouseup', () => {{ isDragging = false; }});
            canvas.addEventListener('mouseleave', () => {{ isDragging = false; }});
            canvas.addEventListener('mousemove', (e) => {{
                if (isDragging) {{
                    offsetX += e.clientX - lastX;
                    offsetY += e.clientY - lastY;
                    lastX = e.clientX;
                    lastY = e.clientY;
                    draw();
                }}
            }});
            
            draw();
        </script>
    </body>
    </html>
    """
    
    return html_content

# ================== NODES ==================

@app.get("/nodes", response_model=List[NodeResponse])
def get_nodes(db: Session = Depends(get_db)):
    """Get all nodes."""
    return db.query(Node).all()

@app.get("/nodes/{node_id}", response_model=NodeResponse)
def get_node(node_id: str, db: Session = Depends(get_db)):
    """Get a specific node by ID."""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node

# @app.post("/nodes", response_model=NodeResponse, status_code=201)
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

@app.put("/nodes/{node_id}", response_model=NodeResponse)
def update_node(node_id: str, data: NodeUpdate, db: Session = Depends(get_db)):
    """Update an existing node."""
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    if data.name is not None:
        node.name = data.name
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

# @app.delete("/nodes/{node_id}")
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

@app.get("/edges", response_model=List[EdgeResponse])
def get_edges(db: Session = Depends(get_db)):
    """Get all edges."""
    return db.query(Edge).all()

@app.get("/edges/{edge_id}", response_model=EdgeResponse)
def get_edge(edge_id: str, db: Session = Depends(get_db)):
    """Get a specific edge by ID."""
    edge = db.query(Edge).filter(Edge.id == edge_id).first()
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    return edge

# @app.post("/edges", response_model=EdgeResponse, status_code=201)
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

@app.put("/edges/{edge_id}", response_model=EdgeResponse)
def update_edge(edge_id: str, data: EdgeUpdate, db: Session = Depends(get_db)):
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
    
    return edge

# @app.delete("/edges/{edge_id}")
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

@app.get("/closures", response_model=List[ClosureResponse])
def get_closures(db: Session = Depends(get_db)):
    """Get all closures."""
    return db.query(Closure).all()

@app.get("/closures/{closure_id}", response_model=ClosureResponse)
def get_closure(closure_id: str, db: Session = Depends(get_db)):
    """Get a specific closure by ID."""
    closure = db.query(Closure).filter(Closure.id == closure_id).first()
    if not closure:
        raise HTTPException(status_code=404, detail="Closure not found")
    return closure

@app.post("/closures", response_model=ClosureResponse, status_code=201)
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

@app.delete("/closures/{closure_id}")
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
def get_all_tiles(level: Optional[int] = None, db: Session = Depends(get_db)):
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
def rebuild_grid(db: Session = Depends(get_db)):

    try:
        tile_count = grid_manager.rebuild_grid(db)
        return {
            "status": "success",
            "message": f"Grid rebuilt with {tile_count} tiles.",
            "tiles_created": tile_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grid rebuild failed: {str(e)}")
    
@app.get("/maps/grid/stats")
def get_grid_stats(db: Session = Depends(get_db)):
    """Get grid statistics."""
    tiles = db.query(Tile).all()
    
    total_nodes = 0
    total_pois = 0
    total_seats = 0
    total_gates = 0
    
    for tile in tiles:
        if tile.node_id:
            total_nodes += len([i for i in tile.node_id.split(',') if i])
        if tile.poi_id:
            total_pois += len([i for i in tile.poi_id.split(',') if i])
        if tile.seat_id:
            total_seats += len([i for i in tile.seat_id.split(',') if i])
        if tile.gate_id:
            total_gates += len([i for i in tile.gate_id.split(',') if i])
    
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
def get_pois(db: Session = Depends(get_db)):
    """Get all POI nodes (restroom, entrance, food, etc)."""
    pois = db.query(Node).filter(Node.type.in_(['poi', 'restroom', 'entrance', 'food', 'shop'])).all()
    return pois

@app.get("/pois/{poi_id}", response_model=NodeResponse)
def get_poi(poi_id: str, db: Session = Depends(get_db)):
    """Get a specific POI node by ID."""
    poi = db.query(Node).filter(Node.id == poi_id).first()
    if not poi:
        raise HTTPException(status_code=404, detail="POI not found")
    return poi

@app.put("/pois/{poi_id}", response_model=NodeResponse)
def update_poi(poi_id: str, data: NodeUpdate, db: Session = Depends(get_db)):
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

# ================== SEATS ==================
# Now handled via Node endpoints with type='seat'

@app.get("/seats", response_model=List[NodeResponse])
def get_seats(block: Optional[str] = None, db: Session = Depends(get_db)):
    """Get all seat nodes, optionally filtered by block."""
    query = db.query(Node).filter(Node.type == 'seat')
    if block:
        query = query.filter(Node.block == block)
    return query.all()

@app.get("/seats/{seat_id}", response_model=NodeResponse)
def get_seat(seat_id: str, db: Session = Depends(get_db)):
    """Get a specific seat node by ID."""
    seat = db.query(Node).filter(Node.id == seat_id).first()
    if not seat:
        raise HTTPException(status_code=404, detail="Seat not found")
    return seat

@app.put("/seats/{seat_id}", response_model=NodeResponse)
def update_seat(seat_id: str, data: NodeUpdate, db: Session = Depends(get_db)):
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
def get_gates(db: Session = Depends(get_db)):
    """Get all gate nodes."""
    return db.query(Node).filter(Node.type == 'gate').all()

@app.get("/gates/{gate_id}", response_model=NodeResponse)
def get_gate(gate_id: str, db: Session = Depends(get_db)):
    """Get a specific gate node by ID."""
    gate = db.query(Node).filter(Node.id == gate_id).first()
    if not gate:
        raise HTTPException(status_code=404, detail="Gate not found")
    return gate

@app.put("/gates/{gate_id}", response_model=NodeResponse)
def update_gate(gate_id: str, data: NodeUpdate, db: Session = Depends(get_db)):
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

@app.get("/map/geojson")
def get_map_geojson(
    level: Optional[int] = Query(None, description="Filter by floor level (0, 1, 2)"),
    types: Optional[str] = Query(None, description="Comma-separated node types: gate,poi,stairs,corridor,seat"),
    include_edges: bool = Query(True, description="Include edges as LineStrings"),
    include_seats: bool = Query(False, description="Include seat nodes (warning: many!)"),
    db: Session = Depends(get_db)
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
        feature = {
            "type": "Feature",
            "id": n.id,
            "geometry": {
                "type": "Point",
                "coordinates": [n.x, n.y]
            },
            "properties": {
                "id": n.id,
                "name": n.name,
                "type": n.type,
                "level": n.level,
                "description": n.description,
            }
        }
        # Add optional properties only if present
        if n.num_servers is not None:
            feature["properties"]["num_servers"] = n.num_servers
        if n.service_rate is not None:
            feature["properties"]["service_rate"] = n.service_rate
        if n.block is not None:
            feature["properties"]["block"] = n.block
        if n.row is not None:
            feature["properties"]["row"] = n.row
        if n.number is not None:
            feature["properties"]["number"] = n.number
        
        features.append(feature)
    
    # Add edges as LineStrings
    if include_edges:
        edge_query = db.query(Edge)
        if level is not None:
            # Get edges where from_node is in this level
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
    
    # Calculate bounds for viewport
    bounds = None
    if nodes:
        xs = [n.x for n in nodes]
        ys = [n.y for n in nodes]
        bounds = {
            "min_x": min(xs),
            "max_x": max(xs),
            "min_y": min(ys),
            "max_y": max(ys)
        }
    
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
    
    # Generate ETag for HTTP caching
    etag = hashlib.md5(f"{len(features)}:{level}:{types}".encode()).hexdigest()[:16]
    
    return JSONResponse(
        content=result,
        headers={
            "ETag": f'"{etag}"',
            "Cache-Control": "public, max-age=300"
        }
    )


@app.get("/map/geojson/level/{level}")
def get_level_geojson(level: int, db: Session = Depends(get_db)):
    """
    Shortcut endpoint to get GeoJSON for a specific floor level.
    Excludes seats for performance.
    """
    return get_map_geojson(level=level, include_seats=False, db=db)


@app.get("/map/bounds")
def get_map_bounds(db: Session = Depends(get_db)):
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
def get_pois_geojson(level: Optional[int] = None, db: Session = Depends(get_db)):
    """
    Get only POI nodes in GeoJSON format (optimized for markers layer).
    
    Includes: gates, restrooms, food, bars, stairs, ramps, emergency exits, 
    first aid, information, and merchandise.
    """
    poi_types = [
        'gate', 'restroom', 'food', 'bar', 'stairs', 'ramp',
        'emergency_exit', 'first_aid', 'information', 'merchandise'
    ]
    return get_map_geojson(
        level=level, 
        types=','.join(poi_types), 
        include_edges=False, 
        db=db
    )

# ================== EMERGENCY ROUTES ==================

@app.get("/emergency-routes", response_model=List[EmergencyRouteResponse])
def list_emergency_routes(db: Session = Depends(get_db)):
    """
    List all predefined emergency evacuation routes.
    
    Returns a list of routes with their IDs, names, and exit points.
    Use the route ID to get the full path in GeoJSON format.
    """
    routes = db.query(EmergencyRoute).all()
    return routes


@app.get("/emergency-routes/nearest")
def get_nearest_emergency_route(
    x: float = Query(..., description="Current X coordinate"),
    y: float = Query(..., description="Current Y coordinate"),
    level: int = Query(0, description="Current floor level"),
    db: Session = Depends(get_db)
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
def get_emergency_route_geojson(route_id: str, db: Session = Depends(get_db)):
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
            role = "start" if idx == 0 else ("exit" if idx == len(route.node_ids) - 1 else "waypoint")
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

# ================== RESET ==================

# ================== HEALTH CHECK ==================

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# ================== DATA MANAGEMENT ==================

@app.post("/reset")
def reset_data(db: Session = Depends(get_db)):
    """Reset database to initial state with sample data."""
    from load_data_db import clear_all_data, load_sample_data
    
    try:
        print("Resetting database...")
        clear_all_data()
        load_sample_data()
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