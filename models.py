from sqlalchemy import Column, String, Float, Integer, Boolean, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel
from typing import Optional

Base = declarative_base()

# ================== Constants for Valid Values ==================

# SQLAlchemy cascade option for relationships
CASCADE_ALL_DELETE_ORPHAN = "all, delete-orphan"

# Foreign key reference to nodes table
NODES_ID_FK = "nodes.id"
NODES_TABLE_ID = "nodes.id"  # Constant for ForeignKey references

# Valid node types used in the stadium map
NODE_TYPES = [
    "corridor",       # Navigation node in corridors/concourses
    "row_aisle",      # Aisle between seat rows (for accessing seats)
    "seat",           # Individual seat in the stands (endpoint only)
    "gate",           # Stadium entrance/exit gate
    "stairs",         # Stairs connecting levels
    "ramp",           # Accessible ramp connecting levels
    "restroom",       # WC/Bathroom facilities
    "food",           # Food court/restaurant
    "bar",            # Bar/drinks area
    "merchandise",    # FC Porto store/merchandise shop
    "first_aid",      # Medical/first aid station
    "emergency_exit", # Emergency exit point
    "information",    # Information desk
    "vip_box",        # VIP box/corporate area
    "normal",         # Generic navigation node
]

# Valid closure reasons
CLOSURE_REASONS = [
    "maintenance",    # Under maintenance/repair
    "crowding",       # Temporarily closed due to crowding
    "emergency",      # Emergency closure
    "event",          # Closed for special event
    "security",       # Security-related closure
    "weather",        # Weather-related closure
]

# Stadium levels (0 = ground/lower, 1 = upper for Este/Oeste)
LEVELS = [0, 1]

# Stadium stands/sections
STANDS = [
    "Norte",   # North stand (Coca-Cola) - Single tier, Ultras Colectivo 95
    "Sul",     # South stand (Super Bock) - Single tier, Super Dragões
    "Este",    # East stand (tmn) - Double tier, Away fans upper
    "Oeste",   # West stand (meo) - Double tier, VIP boxes, players tunnel
]

# ================== SQLAlchemy Models ==================

class Node(Base):
    """
    Represents a point in the stadium navigation graph.
    
    Nodes can be:
    - Navigation points (corridors, stairs, ramps)
    - Points of Interest (gates, restrooms, bars, etc.)
    - Seats (individual stadium seats)
    """
    __tablename__ = "nodes"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=True)  # Human-readable name for display
    x = Column(Float, nullable=False)     # X coordinate (pixels, center ~500)
    y = Column(Float, nullable=False)     # Y coordinate (pixels, center ~400)
    
    # Level: 0 = ground floor/lower tier, 1 = upper tier
    level = Column(Integer, default=0)
    
    # Node type - see NODE_TYPES constant for valid values
    # Options: "corridor", "seat", "gate", "stairs", "ramp", "restroom", 
    #          "food", "bar", "merchandise", "first_aid", "emergency_exit",
    #          "information", "vip_box", "normal"
    type = Column(String, default="normal")
    
    description = Column(String, nullable=True)  # Additional info (e.g., sponsor name)

    # Waiting/queue service fields (for POIs with queues like gates, WCs)
    num_servers = Column(Integer, nullable=True)   # Number of service points
    service_rate = Column(Float, nullable=True)    # Average service rate (people/min)
    
    # Seat-specific fields (only for type="seat")
    # Block format: "{Stand}-T{Tier}" e.g., "Norte-T0", "Este-T1"
    block = Column(String, nullable=True)
    row = Column(Integer, nullable=True)     # Row number (1 = closest to corridor)
    number = Column(Integer, nullable=True)  # Seat number within row
    
    # Relationships
    edges_from = relationship("Edge", foreign_keys="Edge.from_id", back_populates="from_node", cascade=CASCADE_ALL_DELETE_ORPHAN)
    edges_to = relationship("Edge", foreign_keys="Edge.to_id", back_populates="to_node", cascade=CASCADE_ALL_DELETE_ORPHAN)
    closures = relationship("Closure", back_populates="node", cascade=CASCADE_ALL_DELETE_ORPHAN)


class Edge(Base):
    """
    Represents a connection between two nodes in the navigation graph.
    
    Edges are directional - if you need bidirectional movement,
    create two edges (A→B and B→A).
    
    Weight represents the "cost" of traversing this edge:
    - Lower weight = faster/easier path
    - Typical weights: corridor=5, stairs_up=15, seat_to_seat=0.5
    """
    __tablename__ = "edges"
    
    id = Column(String, primary_key=True)
    from_id = Column(String, ForeignKey(NODES_ID_FK, ondelete="CASCADE"), nullable=False)
    to_id = Column(String, ForeignKey(NODES_ID_FK, ondelete="CASCADE"), nullable=False)
    
    # Weight/cost of traversing this edge (used in pathfinding)
    # Suggested weights:
    #   - Corridor walking: 5.0
    #   - Radial corridor connection: 8.0
    #   - Stairs going up: 15.0
    #   - Stairs going down: 10.0
    #   - Seat to seat (same row): 0.5
    #   - Row to row (aisle): 1.5 (involves steps)
    #   - Gate to corridor: 3.0
    #   - POI to corridor: 2.0
    weight = Column(Float, nullable=False)
    
    # Accessibility flag for wheelchair routing
    # False = has stairs/steps (not wheelchair accessible)
    # True = flat surface or ramp (wheelchair accessible)
    # Examples:
    #   - Corridor edges: True
    #   - Row-to-row aisles: False (have steps between rows)
    #   - Stairs between levels: False
    #   - Ramps between levels: True
    #   - Seat access from aisle: True
    accessible = Column(Boolean, default=True)
    
    # Relationships
    from_node = relationship("Node", foreign_keys=[from_id], back_populates="edges_from")
    to_node = relationship("Node", foreign_keys=[to_id], back_populates="edges_to")
    closures = relationship("Closure", back_populates="edge", cascade="all, delete-orphan")


class Closure(Base):
    """
    Represents a temporary closure of a node or edge.
    
    Used for dynamic navigation - closed nodes/edges should be
    excluded from pathfinding.
    """
    __tablename__ = "closures"
    
    id = Column(String, primary_key=True)
    
    # Reason for closure - see CLOSURE_REASONS constant
    # Options: "maintenance", "crowding", "emergency", "event", "security", "weather"
    reason = Column(String, nullable=False)
    
    # Either edge_id OR node_id should be set, not both
    edge_id = Column(String, ForeignKey("edges.id", ondelete="CASCADE"), nullable=True)
    node_id = Column(String, ForeignKey("nodes.id", ondelete="CASCADE"), nullable=True)
    
    # Relationships
    edge = relationship("Edge", back_populates="closures")
    node = relationship("Node", back_populates="closures")


class EmergencyRoute(Base):
    """
    Predefined evacuation route for emergencies.
    
    Each route is a sequence of navigation nodes leading from
    various parts of the stadium to an emergency exit.
    
    Endpoints:
    - GET /emergency-routes: List all routes
    - GET /emergency-routes/{id}: Full route in GeoJSON
    - GET /emergency-routes/nearest: Find closest route start
    """
    __tablename__ = "emergency_routes"
    
    id = Column(String, primary_key=True)           # e.g., "ER-Norte-1"
    name = Column(String, nullable=False)           # e.g., "Saída Norte 1"
    description = Column(String, nullable=True)     # Additional info
    
    # The emergency exit node this route leads to
    exit_id = Column(String, ForeignKey("nodes.id"), nullable=False)
    
    # Ordered list of navigation node IDs forming the evacuation path
    # Format: ["N1", "N2", "N3", ..., "Exit-Norte-1"]
    # First node is the route's "entry point", last is the exit
    node_ids = Column(JSON, nullable=False)
    
    # Relationship to exit node
    exit_node = relationship("Node", foreign_keys=[exit_id])

class Tile(Base):
    __tablename__ = "tiles"

    id = Column(String, primary_key=True)
    grid_x = Column(Float, nullable=False)
    grid_y = Column(Float, nullable=False)
    level= Column(Integer, default=0)

    min_x = Column(Float, nullable=False)
    max_x = Column(Float, nullable=False)
    min_y = Column(Float, nullable=False)
    max_y = Column(Float, nullable=False)    
    walkable = Column(Boolean, default=True)

    node_id = Column(String, nullable=True)
    poi_id = Column(String, nullable=True)
    seat_id = Column(String, nullable=True)
    gate_id = Column(String, nullable=True)

# ================== Pydantic Schemas ==================

class NodeBase(BaseModel):
    id: str
    name: Optional[str] = None
    x: float
    y: float
    level: int = 0
    type: str = "normal"
    description: Optional[str]
    num_servers: Optional[int] = None
    service_rate: Optional[float] = None
    block: Optional[str] = None
    row: Optional[int] = None
    number: Optional[int] = None

class NodeCreate(BaseModel):
    id: str
    name: Optional[str] = None
    x: float
    y: float
    level: int = 0
    type: str = "normal"
    description: Optional[str]
    num_servers: Optional[int] = None
    service_rate: Optional[float] = None
    block: Optional[str] = None
    row: Optional[int] = None
    number: Optional[int] = None

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
    
    class Config:
        from_attributes = True


class EdgeBase(BaseModel):
    id: str
    from_id: str
    to_id: str
    weight: float
    accessible: bool = True

class EdgeCreate(BaseModel):
    id: str
    from_id: str
    to_id: str
    weight: float
    accessible: bool = True

class EdgeUpdate(BaseModel):
    weight: Optional[float] = None
    accessible: Optional[bool] = None

class EdgeResponse(BaseModel):
    id: str
    from_id: str
    to_id: str
    weight: float
    accessible: bool
    
    class Config:
        from_attributes = True


class ClosureBase(BaseModel):
    id: str
    reason: str
    edge_id: Optional[str] = None
    node_id: Optional[str] = None

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
    
    class Config:
        from_attributes = True


class TileCreate(BaseModel):
    id: str
    grid_x: float
    grid_y: float
    level: int = 0
    
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    walkable: bool = True

    node_id: Optional[str] = None
    poi_id: Optional[str] = None
    seat_id: Optional[str] = None
    gate_id: Optional[str] = None

class TileUpdate(BaseModel):
    walkable: Optional[bool] = None
    node_id: Optional[str] = None
    poi_id: Optional[str] = None
    seat_id: Optional[str] = None
    gate_id: Optional[str] = None

class TileResponse(BaseModel):
    id: str
    grid_x: float
    grid_y: float
    level: int
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    walkable: bool
    node_id: Optional[str] = None
    poi_id: Optional[str] = None
    seat_id: Optional[str] = None
    gate_id: Optional[str] = None
    class Config:
        from_attributes = True


class EmergencyRouteCreate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    exit_id: str
    node_ids: list[str]

class EmergencyRouteResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    exit_id: str
    node_ids: list[str]
    
    class Config:
        from_attributes = True
