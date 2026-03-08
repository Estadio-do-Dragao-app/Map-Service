from pydantic import BaseModel
from typing import Optional
from typing import List

# ================== NODE SCHEMAS ==================

class NodeCreate(BaseModel):
    id: str
    name: Optional[str] = None
    x: float
    y: float
    level: int = 0
    type: str = "normal"
    description: Optional[str] = None
    num_servers: Optional[int] = None
    service_rate: Optional[float] = None
    block: Optional[str] = None
    row: Optional[int] = None
    number: Optional[int] = None


class NodeResponse(BaseModel):
    id: str
    name: Optional[str]
    x: float
    y: float
    level: int
    type: str
    description: Optional[str]
    num_servers: Optional[int]
    service_rate: Optional[float]
    block: Optional[str]
    row: Optional[int]
    number: Optional[int]

class NodeUpdate(BaseModel):
    name: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    level: Optional[int] = None
    type: Optional[str] = None
    description: Optional[str] = None
    num_servers: Optional[int] = None
    service_rate: Optional[float] = None
    block: Optional[str] = None
    row: Optional[int] = None
    number: Optional[int] = None

# ================== EDGE SCHEMAS ==================

class EdgeCreate(BaseModel):
    id: str
    from_id: str
    to_id: str
    weight: float
    accessible: bool = True


class EdgeResponse(BaseModel):
    id: str
    from_id: str
    to_id: str
    weight: float
    accessible: bool


Agora que o código do dashboard está correto e inclui o endpoint batch, falta adicionar os métodos PUT para nodes e edges, conforme os testes mostraram. Também precisamos de verificar se o modelo BatchCreate está definido em models.py (provavelmente sim, pois o código importa). Vou sugerir as adições necessárias e depois testar todos os endpoints novamente.

🛠️ Adicionar métodos PUT em falta
No ficheiro main.py, adiciona os seguintes endpoints após os respetivos GET/POST:

Para nodes (após o DELETE, por exemplo)
python
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
Para edges (após o DELETE de edges)
python
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
Para closures (opcional, se o map-service suportar PUT)
Se o map-service também tiver PUT para closures, podes adicionar de forma análoga.

📦 Verificar importações
Certifica-te de que no topo do main.py tens os modelos necessários:

python
from models import (
    NodeCreate, NodeResponse, NodeUpdate,
    EdgeCreate, EdgeResponse, EdgeUpdate,
    ClosureCreate, ClosureResponse, BatchCreate
)
Nota: NodeUpdate e EdgeUpdate já existem nos ficheiros fornecidos? Nos ficheiros que partilhaste inicialmente, models.py tem NodeCreate e NodeResponse, mas não NodeUpdate. No entanto, o ApiHandler.py usa NodeUpdate. Precisas de definir esses modelos no models.py do dashboard ou ajustar para usar os mesmos modelos. Como o dashboard é um proxy, ele deve usar os mesmos modelos que o map-service espera. Vou assumir que no models.py do dashboard tens NodeUpdate e EdgeUpdate definidos. Se não tiveres, podes criá-los:

Em dashboard/backend/models.py, adiciona:

python
class NodeUpdate(BaseModel):
    name: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    level: Optional[int] = None
    type: Optional[str] = None
    description: Optional[str] = None
    num_servers: Optional[int] = None
    service_rate: Optional[float] = None
    block: Optional[str] = None
    row: Optional[int] = None
    number: Optional[int] = None

class EdgeUpdate(BaseModel):
    weight: Optional[float] = None
    accessible: Optional[bool] = None
    
# ================== CLOSURE SCHEMAS ==================

class ClosureCreate(BaseModel):
    id: str
    reason: str
    edge_id: Optional[str] = None
    node_id: Optional[str] = None


class ClosureResponse(BaseModel):
    id: str
    reason: str
    edge_id: Optional[str]
    node_id: Optional[str]

class BatchCreate(BaseModel):
    nodes: List[NodeCreate] = []
    edges: List[EdgeCreate] = []
    closures: List[ClosureCreate] = []
