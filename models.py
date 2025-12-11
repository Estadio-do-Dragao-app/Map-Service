from sqlalchemy import Column, String, Float, Integer, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel
from typing import Optional

Base = declarative_base()

# ================== SQLAlchemy Models ==================

class Node(Base):
    __tablename__ = "nodes"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=True)  # Name for POIs/Gates
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    level = Column(Integer, default=0)
    type = Column(String, default="normal")  # "normal", "gate", "poi", "restroom", "entrance", etc.
    
    # Waiting service fields (for POIs and Gates)
    num_servers = Column(Integer, nullable=True)
    service_rate = Column(Float, nullable=True)
    
    # Legacy fields for seats
    block = Column(String, nullable=True)
    row = Column(Integer, nullable=True)
    number = Column(Integer, nullable=True)
    
    # Relationships
    edges_from = relationship("Edge", foreign_keys="Edge.from_id", back_populates="from_node", cascade="all, delete-orphan")
    edges_to = relationship("Edge", foreign_keys="Edge.to_id", back_populates="to_node", cascade="all, delete-orphan")
    closures = relationship("Closure", back_populates="node", cascade="all, delete-orphan")


class Edge(Base):
    __tablename__ = "edges"
    
    id = Column(String, primary_key=True)
    from_id = Column(String, ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    to_id = Column(String, ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    weight = Column(Float, nullable=False)
    
    # Relationships
    from_node = relationship("Node", foreign_keys=[from_id], back_populates="edges_from")
    to_node = relationship("Node", foreign_keys=[to_id], back_populates="edges_to")
    closures = relationship("Closure", back_populates="edge", cascade="all, delete-orphan")


class Closure(Base):
    __tablename__ = "closures"
    
    id = Column(String, primary_key=True)
    reason = Column(String, nullable=False)
    edge_id = Column(String, ForeignKey("edges.id", ondelete="CASCADE"), nullable=True)
    node_id = Column(String, ForeignKey("nodes.id", ondelete="CASCADE"), nullable=True)
    
    # Relationships
    edge = relationship("Edge", back_populates="closures")
    node = relationship("Node", back_populates="closures")


class Tile(Base):
    __tablename__ = "tiles"
    
    id = Column(String, primary_key=True)
    grid_x = Column(Integer, nullable=False)
    grid_y = Column(Integer, nullable=False)
    walkable = Column(Boolean, default=True)


# ================== Pydantic Schemas ==================

class NodeBase(BaseModel):
    id: str
    name: Optional[str] = None
    x: float
    y: float
    level: int = 0
    type: str = "normal"
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

class EdgeCreate(BaseModel):
    id: str
    from_id: str
    to_id: str
    weight: float

class EdgeUpdate(BaseModel):
    weight: Optional[float] = None

class EdgeResponse(BaseModel):
    id: str
    from_id: str
    to_id: str
    weight: float
    
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
    grid_x: int
    grid_y: int
    walkable: bool = True

class TileUpdate(BaseModel):
    walkable: Optional[bool] = None

class TileResponse(BaseModel):
    id: str
    grid_x: int
    grid_y: int
    walkable: bool
    class Config:  
        from_attributes = True  
    
