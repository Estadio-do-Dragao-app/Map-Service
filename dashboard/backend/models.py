from pydantic import BaseModel
from typing import Optional, List

NODE_TYPES = [
    "corridor", "row_aisle", "seat", "gate", "stairs", "ramp",
    "restroom", "food", "bar", "merchandise", "first_aid",
    "emergency_exit", "information", "vip_box", "camera", "normal",
    "departments", "queue",
]

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


# ================== BATCH SCHEMAS ==================

class BatchCreate(BaseModel):
    nodes: List[NodeCreate] = []
    edges: List[EdgeCreate] = []
    closures: List[ClosureCreate] = []


class BatchDelete(BaseModel):
    node_ids: List[str] = []
    edge_ids: List[str] = []


# ================== CAMERA SCHEMAS ==================

class CameraCreate(BaseModel):
    id: str
    node_id: str
    pos_x: float
    pos_y: float
    pos_z: float
    pan: float = 0.0
    tilt: float = -30.0
    fov_horizontal: float = 70.0
    fov_vertical: float = 55.0
    # Legacy bounding box (kept for backwards compatibility)
    coverage_x_min: Optional[float] = None
    coverage_x_max: Optional[float] = None
    coverage_y_min: Optional[float] = None
    coverage_y_max: Optional[float] = None
    # Free-form polygon: list of {x, y} map-coordinate dicts (>=3 points)
    coverage_polygon: Optional[list] = None


class CameraUpdate(BaseModel):
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    pos_z: Optional[float] = None
    pan: Optional[float] = None
    tilt: Optional[float] = None
    fov_horizontal: Optional[float] = None
    fov_vertical: Optional[float] = None
    coverage_x_min: Optional[float] = None
    coverage_x_max: Optional[float] = None
    coverage_y_min: Optional[float] = None
    coverage_y_max: Optional[float] = None
    coverage_polygon: Optional[list] = None


class CameraResponse(BaseModel):
    id: str
    node_id: str
    pos_x: float
    pos_y: float
    pos_z: float
    pan: float
    tilt: float
    fov_horizontal: float
    fov_vertical: float
    coverage_x_min: Optional[float]
    coverage_x_max: Optional[float]
    coverage_y_min: Optional[float]
    coverage_y_max: Optional[float]
    coverage_polygon: Optional[list] = None