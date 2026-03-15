from pydantic import BaseModel
from typing import Optional, List

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
    door_id: Optional[str] = None


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
    door_id: Optional[str]


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
    door_id: Optional[str] = None


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


# ================== BATCH SCHEMA ==================

class BatchCreate(BaseModel):
    nodes: List[NodeCreate] = []
    edges: List[EdgeCreate] = []
    closures: List[ClosureCreate] = []