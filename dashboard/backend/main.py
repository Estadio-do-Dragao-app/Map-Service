from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import re
import httpx

from models import (
    EdgeUpdate, NodeCreate, NodeResponse,
    EdgeCreate, EdgeResponse,
    ClosureCreate, ClosureResponse, BatchCreate, BatchDelete, NodeUpdate,
    CameraCreate, CameraUpdate, CameraResponse,
    NODE_TYPES
)
from database import call_map_service, check_map_service_health

ERR_MAP_UNREACHABLE = "Map-Service não está acessível"
SAFE_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def build_item_path(resource: str, resource_id: str, field_name: str) -> str:
    """Build a proxy path after validating the dynamic identifier."""
    if not isinstance(resource_id, str) or not SAFE_PATH_SEGMENT_RE.fullmatch(resource_id):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")
    return f"/{resource}/{resource_id}"

app = FastAPI(
    title="Dashboard Backend — Map-Service",
    description="Backend do dashboard para gerir o mapa do campus. Comunica com o Map-Service em modo proxy.",
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

@app.get("/health", tags=["health"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def health():
    """Estado do dashboard backend e conectividade com o Map-Service."""
    map_status = await check_map_service_health()
    return {
        "dashboard_backend": "ok",
        "map_service": map_status,
    }


# ================== MAP ==================

@app.get("/map", tags=["map"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def get_map():
    """Mapa completo com nodes, edges e closures."""
    try:
        return await call_map_service("GET", "/map")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.get("/export", tags=["map"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def export_map():
    """Exporta o estado atual do mapa num ficheiro JSON (incluindo nodes, edges e closures)."""
    try:
        # Reutilizamos o endpoint do map para simplificar
        data = await call_map_service("GET", "/map")
        return data
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

# ================== NODES ==================

@app.get("/nodes", response_model=List[NodeResponse], tags=["nodes"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def get_nodes(limit: Optional[int] = None, offset: Optional[int] = None):
    """Lista todos os nodes do mapa. Encaminha `limit` e `offset` para o Map-Service quando presentes."""
    try:
        params = {}
        if limit is not None:
            params['limit'] = limit
        if offset is not None:
            params['offset'] = offset
        return await call_map_service("GET", "/nodes", params=params if params else None)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.get("/nodes/{node_id}", response_model=NodeResponse, tags=["nodes"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def get_node(node_id: str):
    """Obtém um node pelo ID."""
    try:
        return await call_map_service("GET", build_item_path("nodes", node_id, "node_id"))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.post("/nodes", response_model=NodeResponse, status_code=201, tags=["nodes"], responses={503: {"description": ERR_MAP_UNREACHABLE}, 400: {"description": "Tipo de node inválido"}})
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
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.delete("/nodes/{node_id}", tags=["nodes"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def delete_node(node_id: str):
    """Apaga um node e todas as suas edges associadas."""
    try:
        return await call_map_service("DELETE", build_item_path("nodes", node_id, "node_id"))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    
@app.put("/nodes/{node_id}", response_model=NodeResponse, tags=["nodes"], responses={503: {"description": ERR_MAP_UNREACHABLE}, 400: {"description": "Tipo de node inválido"}})
async def update_node(node_id: str, data: NodeUpdate):
    """
    Atualiza um node existente.
    """
    if data.type is not None and data.type not in NODE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid node type: {data.type}")
    try:
        return await call_map_service("PUT", build_item_path("nodes", node_id, "node_id"), json=data.model_dump(exclude_none=True))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

# ================== EDGES ==================

@app.get("/edges", response_model=List[EdgeResponse], tags=["edges"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def get_edges(limit: Optional[int] = None, offset: Optional[int] = None):
    """Lista todas as edges do mapa. Encaminha `limit` e `offset` para o Map-Service quando presentes."""
    try:
        params = {}
        if limit is not None:
            params['limit'] = limit
        if offset is not None:
            params['offset'] = offset
        return await call_map_service("GET", "/edges", params=params if params else None)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.get("/edges/{edge_id}", response_model=EdgeResponse, tags=["edges"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def get_edge(edge_id: str):
    """Obtém uma edge pelo ID."""
    try:
        return await call_map_service("GET", build_item_path("edges", edge_id, "edge_id"))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.post("/edges", response_model=EdgeResponse, status_code=201, tags=["edges"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def create_edge(data: EdgeCreate):
    """
    Cria uma nova edge (ligação entre dois nodes).

    O `from_id` e `to_id` devem ser IDs de nodes existentes.
    Para ligações bidirecionais, cria duas edges (A→B e B→A).
    """
    try:
        return await call_map_service("POST", "/edges", json=data.model_dump())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.delete("/edges/{edge_id}", tags=["edges"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def delete_edge(edge_id: str):
    """Apaga uma edge pelo ID."""
    try:
        return await call_map_service("DELETE", build_item_path("edges", edge_id, "edge_id"))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

@app.put("/edges/{edge_id}", response_model=EdgeResponse, tags=["edges"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def update_edge(edge_id: str, data: EdgeUpdate):
    """
    Atualiza uma edge existente.
    """
    try:
        return await call_map_service("PUT", build_item_path("edges", edge_id, "edge_id"), json=data.model_dump())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

# ================== CLOSURES ==================

@app.get("/closures", response_model=List[ClosureResponse], tags=["closures"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def get_closures():
    """Lista todas as closures (encerramentos temporários de nodes/edges)."""
    try:
        return await call_map_service("GET", "/closures")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.post("/closures", response_model=ClosureResponse, status_code=201, tags=["closures"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def create_closure(data: ClosureCreate):
    """
    Cria um encerramento temporário de um node ou edge.

    Razões válidas: maintenance, crowding, emergency, event, security, weather
    """
    try:
        return await call_map_service("POST", "/closures", json=data.model_dump())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.delete("/closures/{closure_id}", tags=["closures"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def delete_closure(closure_id: str):
    """Remove um encerramento temporário."""
    try:
        return await call_map_service("DELETE", build_item_path("closures", closure_id, "closure_id"))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

@app.post("/batch", status_code=201, tags=["batch"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def create_batch(data: BatchCreate):
    """
    Cria múltiplos nodes, edges e closures num único pedido.
    Delegates to Map-Service native /batch endpoint for efficiency.
    """
    try:
        return await call_map_service("POST", "/batch", json=data.model_dump(exclude_none=True))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# ================== MAP SYNC ==================

@app.post("/map/sync", status_code=200, tags=["map"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
@app.post("/api/map/sync", status_code=200, tags=["map"])
async def sync_map(data: BatchCreate):
    """
    Sincroniza o mapa completo. Lê o estado atual do dashboard e sobrescreve o mapa no backend principal.
    """
    try:
        return await call_map_service("POST", "/map/sync", json=data.model_dump())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# ================== BATCH DELETE ==================

@app.post("/batch/delete", status_code=200, tags=["batch"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def delete_batch(data: BatchDelete):
    """Apaga múltiplos nodes e/ou edges num único pedido.

    Delegates to Map-Service native /batch/delete endpoint, which deletes
    edges first then nodes (with dependent edges/closures) in a single
    transaction, instead of issuing one DELETE per item.
    """
    try:
        return await call_map_service("POST", "/batch/delete", json=data.model_dump())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# ================== CAMERAS ==================

@app.get("/cameras", response_model=List[CameraResponse], tags=["cameras"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def get_cameras():
    """Lista todas as câmaras."""
    try:
        return await call_map_service("GET", "/cameras")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.get("/cameras/{camera_id}", response_model=CameraResponse, tags=["cameras"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def get_camera(camera_id: str):
    """Obtém uma câmara pelo ID."""
    try:
        return await call_map_service("GET", build_item_path("cameras", camera_id, "camera_id"))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.post("/cameras", response_model=CameraResponse, status_code=201, tags=["cameras"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def create_camera(data: CameraCreate):
    """Cria uma nova câmara com dados de calibração."""
    try:
        return await call_map_service("POST", "/cameras", json=data.model_dump())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.put("/cameras/{camera_id}", response_model=CameraResponse, tags=["cameras"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def update_camera(camera_id: str, data: CameraUpdate):
    """Atualiza os dados de calibração de uma câmara."""
    try:
        return await call_map_service("PUT", build_item_path("cameras", camera_id, "camera_id"), json=data.model_dump(exclude_none=True))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@app.delete("/cameras/{camera_id}", tags=["cameras"], responses={503: {"description": ERR_MAP_UNREACHABLE}})
async def delete_camera(camera_id: str):
    """Apaga uma câmara pelo ID."""
    try:
        return await call_map_service("DELETE", build_item_path("cameras", camera_id, "camera_id"))
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=ERR_MAP_UNREACHABLE)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# ================== GRID TILES ==================

@app.get("/maps/grid/tiles", tags=["grid"])
async def get_grid_tiles(level: Optional[int] = None):
    """Lista todos os tiles do grid, opcionalmente filtrados por nível."""
    try:
        params = {}
        if level is not None:
            params["level"] = level
        return await call_map_service("GET", "/maps/grid/tiles", params=params if params else None)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Map-Service não está acessível")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
