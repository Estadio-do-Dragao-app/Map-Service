from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import httpx
import asyncio

from models import (
    EdgeUpdate, NodeCreate, NodeResponse,
    EdgeCreate, EdgeResponse,
    ClosureCreate, ClosureResponse, BatchCreate, NodeUpdate
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
    try:
        return await call_map_service("PUT", f"/nodes/{node_id}", json=data.model_dump())
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
    A ordem de criação é: nodes → edges → closures.
    Retorna um resumo dos itens criados e eventuais erros.
    """
    results = {
        "nodes": {"created": [], "errors": []},
        "edges": {"created": [], "errors": []},
        "closures": {"created": [], "errors": []},
    }

    # Função auxiliar para criar um node
    async def create_node(node):
        try:
            resp = await call_map_service("POST", "/nodes", json=node.model_dump())
            results["nodes"]["created"].append(resp.get("id") or node.id)
        except Exception as e:
            results["nodes"]["errors"].append({"item": node.model_dump(), "error": str(e)})

    # Função auxiliar para criar uma edge
    async def create_edge(edge):
        try:
            resp = await call_map_service("POST", "/edges", json=edge.model_dump())
            results["edges"]["created"].append(resp.get("id") or edge.id)
        except Exception as e:
            results["edges"]["errors"].append({"item": edge.model_dump(), "error": str(e)})

    # Função auxiliar para criar uma closure
    async def create_closure(closure):
        try:
            resp = await call_map_service("POST", "/closures", json=closure.model_dump())
            results["closures"]["created"].append(resp.get("id") or closure.id)
        except Exception as e:
            results["closures"]["errors"].append({"item": closure.model_dump(), "error": str(e)})

    # Executar todas as tarefas de nodes em paralelo
    if data.nodes:
        await asyncio.gather(*[create_node(node) for node in data.nodes])

    # Depois as edges
    if data.edges:
        await asyncio.gather(*[create_edge(edge) for edge in data.edges])

    # Por fim as closures
    if data.closures:
        await asyncio.gather(*[create_closure(closure) for closure in data.closures])

    return results