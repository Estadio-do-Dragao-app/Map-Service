"""
Pytest configuration and shared fixtures for Map-Service tests.
"""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from database import get_db
from models import Base
from ApiHandler import app


# ================== DATABASE FIXTURES ==================

@pytest.fixture(scope="function")
def test_engine():
    """Create a test database engine using in-memory SQLite."""
    # Use check_same_thread=False to allow usage across different threads (needed for FastAPI testing)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    
    # Enable foreign key constraints for SQLite
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db(test_engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def override_get_db(test_db):
    """Override the get_db dependency for API tests."""
    def _override_get_db():
        try:
            yield test_db
        finally:
            pass
    return _override_get_db


# ================== API FIXTURES ==================

@pytest.fixture(scope="function")
def client(override_get_db):
    """Create a test client with overridden database dependency."""
    from fastapi.testclient import TestClient
    
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ================== TEST DATA FIXTURES ==================

@pytest.fixture
def sample_node_data():
    """Sample node data for testing."""
    return {
        "id": "TEST-NODE-1",
        "name": "Test Node",
        "x": 100.0,
        "y": 200.0,
        "level": 0,
        "type": "corridor",
        "description": "Test corridor node"
    }


@pytest.fixture
def sample_gate_data():
    """Sample gate node data with queue parameters."""
    return {
        "id": "GATE-1",
        "name": "Gate 1",
        "x": 50.0,
        "y": 50.0,
        "level": 0,
        "type": "gate",
        "description": "Main entrance",
        "num_servers": 3,
        "service_rate": 10.0
    }


@pytest.fixture
def sample_seat_data():
    """Sample seat node data."""
    return {
        "id": "SEAT-Norte-T0-R1-S1",
        "name": "Seat Norte T0 R1 #1",
        "x": 150.0,
        "y": 250.0,
        "level": 0,
        "type": "seat",
        "block": "Norte-T0",
        "row": 1,
        "number": 1
    }


@pytest.fixture
def sample_edge_data():
    """Sample edge data for testing."""
    return {
        "id": "EDGE-1",
        "from_id": "NODE-A",
        "to_id": "NODE-B",
        "weight": 5.0,
        "accessible": True
    }


@pytest.fixture
def sample_closure_data():
    """Sample closure data for testing."""
    return {
        "id": "CLOSURE-1",
        "node_id": "NODE-A",
        "edge_id": None,
        "reason": "maintenance"
    }


@pytest.fixture
def sample_emergency_route_data():
    """Sample emergency route data."""
    return {
        "id": "ER-TEST-1",
        "name": "Test Emergency Route",
        "description": "Test evacuation route",
        "exit_id": "EXIT-1",
        "node_ids": ["NODE-1", "NODE-2", "NODE-3", "EXIT-1"]
    }


# ================== MODEL FIXTURES ==================

@pytest.fixture
def create_test_nodes(test_db):
    """Factory fixture to create test nodes in the database."""
    from models import Node
    
    def _create_nodes(num_nodes=5):
        nodes = []
        for i in range(num_nodes):
            node = Node(
                id=f"NODE-{i}",
                name=f"Test Node {i}",
                x=float(i * 10),
                y=float(i * 10),
                level=0,
                type="corridor"
            )
            test_db.add(node)
            nodes.append(node)
        test_db.commit()
        return nodes
    
    return _create_nodes


@pytest.fixture
def create_test_edges(test_db, create_test_nodes):
    """Factory fixture to create test edges connecting nodes."""
    from models import Edge
    
    def _create_edges(nodes=None):
        if nodes is None:
            nodes = create_test_nodes(5)
        
        edges = []
        for i in range(len(nodes) - 1):
            edge = Edge(
                id=f"EDGE-{i}",
                from_id=nodes[i].id,
                to_id=nodes[i + 1].id,
                weight=5.0,
                accessible=True
            )
            test_db.add(edge)
            edges.append(edge)
        test_db.commit()
        return edges
    
    return _create_edges


@pytest.fixture
def create_stadium_graph(test_db):
    """Create a small stadium-like graph structure for testing."""
    from models import Node, Edge
    
    # Create nodes in a simple stadium structure
    nodes = [
        # Gates
        Node(id="GATE-1", name="Gate 1", x=50, y=400, level=0, type="gate", 
             num_servers=3, service_rate=10.0),
        Node(id="GATE-2", name="Gate 2", x=950, y=400, level=0, type="gate",
             num_servers=2, service_rate=8.0),
        
        # Corridors
        Node(id="CORR-1", name="Corridor 1", x=150, y=400, level=0, type="corridor"),
        Node(id="CORR-2", name="Corridor 2", x=850, y=400, level=0, type="corridor"),
        Node(id="CORR-CENTER", name="Center Corridor", x=500, y=400, level=0, type="corridor"),
        
        # Stairs
        Node(id="STAIRS-1", name="Stairs 1", x=300, y=400, level=0, type="stairs"),
        Node(id="STAIRS-1-UP", name="Stairs 1 Upper", x=300, y=400, level=1, type="stairs"),
        
        # POIs
        Node(id="WC-1", name="Restroom 1", x=400, y=300, level=0, type="restroom",
             num_servers=5, service_rate=15.0),
        Node(id="FOOD-1", name="Food Court", x=600, y=300, level=0, type="food",
             num_servers=4, service_rate=5.0),
        
        # Seats
        Node(id="SEAT-1", name="Seat 1", x=500, y=200, level=0, type="seat",
             block="Norte-T0", row=1, number=1),
        Node(id="SEAT-2", name="Seat 2", x=510, y=200, level=0, type="seat",
             block="Norte-T0", row=1, number=2),
    ]
    
    for node in nodes:
        test_db.add(node)
    test_db.commit()
    
    # Create edges
    edges = [
        # Gate to corridor connections
        Edge(id="E1", from_id="GATE-1", to_id="CORR-1", weight=3.0, accessible=True),
        Edge(id="E2", from_id="GATE-2", to_id="CORR-2", weight=3.0, accessible=True),
        
        # Corridor connections
        Edge(id="E3", from_id="CORR-1", to_id="CORR-CENTER", weight=5.0, accessible=True),
        Edge(id="E4", from_id="CORR-2", to_id="CORR-CENTER", weight=5.0, accessible=True),
        
        # Stairs connections
        Edge(id="E5", from_id="CORR-CENTER", to_id="STAIRS-1", weight=5.0, accessible=True),
        Edge(id="E6", from_id="STAIRS-1", to_id="STAIRS-1-UP", weight=15.0, accessible=False),
        
        # POI connections
        Edge(id="E7", from_id="CORR-CENTER", to_id="WC-1", weight=2.0, accessible=True),
        Edge(id="E8", from_id="CORR-CENTER", to_id="FOOD-1", weight=2.0, accessible=True),
        
        # Seat connections
        Edge(id="E9", from_id="CORR-CENTER", to_id="SEAT-1", weight=1.5, accessible=True),
        Edge(id="E10", from_id="SEAT-1", to_id="SEAT-2", weight=0.5, accessible=True),
    ]
    
    for edge in edges:
        test_db.add(edge)
    test_db.commit()
    
    return {"nodes": nodes, "edges": edges}
