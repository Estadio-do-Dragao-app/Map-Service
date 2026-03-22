from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import httpx
import asyncio

from models import (
    EdgeUpdate, NodeCreate, NodeResponse,
    EdgeCreate, EdgeResponse,
    ClosureCreate, ClosureResponse, BatchCreate, BatchDelete, NodeUpdate,
    CameraCreate, CameraUpdate, CameraResponse,
    NODE_TYPES
)
from database import call_map_service, check_map_service_health

app = FastAPI(
    title="Dashboard Backend — Map-Service",
    description="Backend do dashboard para gerir o mapa do estádio. Comunica com o Map-Service em modo proxy.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================== HEALTH ==================

@app.get("/health", tags=["health"])
async def health():
    """Estado do dashboard backend e conectividade com o Map-Service."""
    map_status = await check_map_service_health()
    return {
        "dashboard_backend": "ok",
        "map_service": map_status,
    }


# ================== MAP ==================

@app.get("/map", tags=["map"])
async def get_map():
    """Mapa completo com nodes, edges e closures."""
    try:
        return await call_map_service("GET", "/map")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.get("/export", tags=["map"])
async def export_map():
    """Exporta o estado atual do mapa num ficheiro JSON (incluindo nodes, edges e closures)."""
    try:
        # Reutilizamos o endpoint do map para simplificar
        data = await call_map_service("GET", "/map")
        return data
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

# ================== NODES ==================

@app.get("/nodes", response_model=List[NodeResponse], tags=["nodes"])
async def get_nodes():
    """Lista todos os nodes do mapa."""
    try:
        return await call_map_service("GET", "/nodes")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.get("/nodes/{node_id}", response_model=NodeResponse, tags=["nodes"])
async def get_node(node_id: str):
    """Obtém um node pelo ID."""
    try:
        return await call_map_service("GET", f"/nodes/{node_id}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.post("/nodes", response_model=NodeResponse, status_code=201, tags=["nodes"])
async def create_node(data: NodeCreate):
    """
    Cria um novo node no mapa.

    Tipos válidos: corridor, row_aisle, seat, gate, stairs, ramp, restroom,
    food, bar, merchandise, first_aid, emergency_exit, information, vip_box, normal
    """
    if data.type not in NODE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid node type: {data.type}")
    try:
        return await call_map_service("POST", "/nodes", json=data.model_dump())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.delete("/nodes/{node_id}", tags=["nodes"])
async def delete_node(node_id: str):
    """Apaga um node e todas as suas edges associadas."""
    try:
        return await call_map_service("DELETE", f"/nodes/{node_id}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    
@app.put("/nodes/{node_id}", response_model=NodeResponse, tags=["nodes"])
async def update_node(node_id: str, data: NodeUpdate):
    """
    Atualiza um node existente.
    """
    if data.type is not None and data.type not in NODE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid node type: {data.type}")
    try:
        return await call_map_service("PUT", f"/nodes/{node_id}", json=data.model_dump(exclude_none=True))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

# ================== EDGES ==================

@app.get("/edges", response_model=List[EdgeResponse], tags=["edges"])
async def get_edges():
    """Lista todas as edges do mapa."""
    try:
        return await call_map_service("GET", "/edges")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.get("/edges/{edge_id}", response_model=EdgeResponse, tags=["edges"])
async def get_edge(edge_id: str):
    """Obtém uma edge pelo ID."""
    try:
        return await call_map_service("GET", f"/edges/{edge_id}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.post("/edges", response_model=EdgeResponse, status_code=201, tags=["edges"])
async def create_edge(data: EdgeCreate):
    """
    Cria uma nova edge (ligação entre dois nodes).

    O `from_id` e `to_id` devem ser IDs de nodes existentes.
    Para ligações bidirecionais, cria duas edges (A→B e B→A).
    """
    try:
        return await call_map_service("POST", "/edges", json=data.model_dump())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.delete("/edges/{edge_id}", tags=["edges"])
async def delete_edge(edge_id: str):
    """Apaga uma edge pelo ID."""
    try:
        return await call_map_service("DELETE", f"/edges/{edge_id}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

@app.put("/edges/{edge_id}", response_model=EdgeResponse, tags=["edges"])
async def update_edge(edge_id: str, data: EdgeUpdate):
    """
    Atualiza uma edge existente.
    """
    try:
        return await call_map_service("PUT", f"/edges/{edge_id}", json=data.model_dump())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

# ================== CLOSURES ==================

@app.get("/closures", response_model=List[ClosureResponse], tags=["closures"])
async def get_closures():
    """Lista todas as closures (encerramentos temporários de nodes/edges)."""
    try:
        return await call_map_service("GET", "/closures")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.post("/closures", response_model=ClosureResponse, status_code=201, tags=["closures"])
async def create_closure(data: ClosureCreate):
    """
    Cria um encerramento temporário de um node ou edge.

    Razões válidas: maintenance, crowding, emergency, event, security, weather
    """
    try:
        return await call_map_service("POST", "/closures", json=data.model_dump())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.delete("/closures/{closure_id}", tags=["closures"])
async def delete_closure(closure_id: str):
    """Remove um encerramento temporário."""
    try:
        return await call_map_service("DELETE", f"/closures/{closure_id}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

@app.post("/batch", status_code=201, tags=["batch"])
async def create_batch(data: BatchCreate):
    """
    Cria múltiplos nodes, edges e closures num único pedido.
    Delegates to Map-Service native /batch endpoint for efficiency.
    """
    try:
        return await call_map_service("POST", "/batch", json=data.model_dump(exclude_none=True))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# ================== MAP SYNC ==================

@app.post("/map/sync", status_code=200, tags=["map"])
async def sync_map(data: BatchCreate):
    """
    Sincroniza o mapa completo. Lê o estado atual do dashboard e sobrescreve o mapa no backend principal.
    """
    try:
        return await call_map_service("POST", "/map/sync", json=data.model_dump(exclude_none=True))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# ================== BATCH DELETE ==================

@app.post("/batch/delete", status_code=200, tags=["batch"])
async def delete_batch(data: BatchDelete):
    """Apaga múltiplos nodes e/ou edges em paralelo. Edges primeiro, depois nodes."""
    results = {
        "edges": {"deleted": [], "errors": []},
        "nodes": {"deleted": [], "errors": []},
    }

    async def del_edge(edge_id: str):
        try:
            await call_map_service("DELETE", f"/edges/{edge_id}")
            results["edges"]["deleted"].append(edge_id)
        except Exception as e:
            results["edges"]["errors"].append({"id": edge_id, "error": str(e)})

    async def del_node(node_id: str):
        try:
            await call_map_service("DELETE", f"/nodes/{node_id}")
            results["nodes"]["deleted"].append(node_id)
        except Exception as e:
            results["nodes"]["errors"].append({"id": node_id, "error": str(e)})

    if data.edge_ids:
        await asyncio.gather(*[del_edge(eid) for eid in data.edge_ids])
    if data.node_ids:
        await asyncio.gather(*[del_node(nid) for nid in data.node_ids])

    return results


# ================== CAMERAS ==================

@app.get("/cameras", response_model=List[CameraResponse], tags=["cameras"])
async def get_cameras():
    """Lista todas as câmaras."""
    try:
        return await call_map_service("GET", "/cameras")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.get("/cameras/{camera_id}", response_model=CameraResponse, tags=["cameras"])
async def get_camera(camera_id: str):
    """Obtém uma câmara pelo ID."""
    try:
        return await call_map_service("GET", f"/cameras/{camera_id}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.post("/cameras", response_model=CameraResponse, status_code=201, tags=["cameras"])
async def create_camera(data: CameraCreate):
    """Cria uma nova câmara com dados de calibração."""
    try:
        return await call_map_service("POST", "/cameras", json=data.model_dump())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.put("/cameras/{camera_id}", response_model=CameraResponse, tags=["cameras"])
async def update_camera(camera_id: str, data: CameraUpdate):
    """Atualiza os dados de calibração de uma câmara."""
    try:
        return await call_map_service("PUT", f"/cameras/{camera_id}", json=data.model_dump(exclude_none=True))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.delete("/cameras/{camera_id}", tags=["cameras"])
async def delete_camera(camera_id: str):
    """Apaga uma câmara pelo ID."""
    try:
        return await call_map_service("DELETE", f"/cameras/{camera_id}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
