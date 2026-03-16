"""
Tests for database models.
"""
import pytest
from models import (
    Node, Edge, Closure, Tile, EmergencyRoute,
    NodeCreate, EdgeCreate, ClosureCreate,
    NODE_TYPES, CLOSURE_REASONS, LEVELS, STANDS
)


class TestNodeModel:
    """Test the Node SQLAlchemy model."""
    
    def test_create_basic_node(self, test_db):
        """Test creating a basic navigation node."""
        node = Node(
            id="TEST-1",
            name="Test Node",
            x=100.0,
            y=200.0,
            level=0,
            type="corridor"
        )
        test_db.add(node)
        test_db.commit()
        
        retrieved = test_db.query(Node).filter_by(id="TEST-1").first()
        assert retrieved is not None
        assert retrieved.name == "Test Node"
        assert retrieved.x == 100.0
        assert retrieved.y == 200.0
        assert retrieved.level == 0
        assert retrieved.type == "corridor"
    
    def test_create_gate_node_with_queue_params(self, test_db):
        """Test creating a gate node with queue/service parameters."""
        gate = Node(
            id="GATE-1",
            name="Main Gate",
            x=50.0,
            y=50.0,
            type="gate",
            num_servers=3,
            service_rate=10.0
        )
        test_db.add(gate)
        test_db.commit()
        
        retrieved = test_db.query(Node).filter_by(id="GATE-1").first()
        assert retrieved.type == "gate"
        assert retrieved.num_servers == 3
        assert retrieved.service_rate == 10.0
    
    def test_create_seat_node_with_details(self, test_db):
        """Test creating a seat node with block, row, and number."""
        seat = Node(
            id="SEAT-1",
            name="Seat Norte R1 #1",
            x=500.0,
            y=300.0,
            type="seat",
            block="Norte-T0",
            row=1,
            number=1
        )
        test_db.add(seat)
        test_db.commit()
        
        retrieved = test_db.query(Node).filter_by(id="SEAT-1").first()
        assert retrieved.type == "seat"
        assert retrieved.block == "Norte-T0"
        assert retrieved.row == 1
        assert retrieved.number == 1
    
    def test_node_default_values(self, test_db):
        """Test that node default values are set correctly."""
        node = Node(id="TEST-2", x=10.0, y=20.0)
        test_db.add(node)
        test_db.commit()
        
        retrieved = test_db.query(Node).filter_by(id="TEST-2").first()
        assert retrieved.level == 0
        assert retrieved.type == "normal"
        assert retrieved.name is None
    
    def test_node_relationships(self, test_db):
        """Test node relationships with edges."""
        node1 = Node(id="N1", x=0, y=0)
        node2 = Node(id="N2", x=10, y=10)
        test_db.add_all([node1, node2])
        test_db.commit()
        
        edge = Edge(id="E1", from_id="N1", to_id="N2", weight=5.0)
        test_db.add(edge)
        test_db.commit()
        
        retrieved_node1 = test_db.query(Node).filter_by(id="N1").first()
        assert len(retrieved_node1.edges_from) == 1
        assert retrieved_node1.edges_from[0].to_id == "N2"


class TestEdgeModel:
    """Test the Edge SQLAlchemy model."""
    
    def test_create_basic_edge(self, test_db):
        """Test creating a basic edge between two nodes."""
        node1 = Node(id="N1", x=0, y=0)
        node2 = Node(id="N2", x=10, y=10)
        test_db.add_all([node1, node2])
        test_db.commit()
        
        edge = Edge(
            id="E1",
            from_id="N1",
            to_id="N2",
            weight=5.0,
            accessible=True
        )
        test_db.add(edge)
        test_db.commit()
        
        retrieved = test_db.query(Edge).filter_by(id="E1").first()
        assert retrieved is not None
        assert retrieved.from_id == "N1"
        assert retrieved.to_id == "N2"
        assert retrieved.weight == 5.0
        assert retrieved.accessible is True
    
    def test_edge_default_accessible(self, test_db):
        """Test that edges are accessible by default."""
        node1 = Node(id="N1", x=0, y=0)
        node2 = Node(id="N2", x=10, y=10)
        test_db.add_all([node1, node2])
        test_db.commit()
        
        edge = Edge(id="E1", from_id="N1", to_id="N2", weight=5.0)
        test_db.add(edge)
        test_db.commit()
        
        retrieved = test_db.query(Edge).filter_by(id="E1").first()
        assert retrieved.accessible is True
    
    def test_edge_not_accessible(self, test_db):
        """Test creating a non-accessible edge (e.g., stairs)."""
        node1 = Node(id="N1", x=0, y=0, level=0)
        node2 = Node(id="N2", x=0, y=0, level=1, type="stairs")
        test_db.add_all([node1, node2])
        test_db.commit()
        
        edge = Edge(
            id="E1",
            from_id="N1",
            to_id="N2",
            weight=15.0,
            accessible=False
        )
        test_db.add(edge)
        test_db.commit()
        
        retrieved = test_db.query(Edge).filter_by(id="E1").first()
        assert retrieved.accessible is False
        assert retrieved.weight == 15.0
    
    def test_edge_cascade_delete(self, test_db):
        """Test that edges are deleted when nodes are deleted."""
        node1 = Node(id="N1", x=0, y=0)
        node2 = Node(id="N2", x=10, y=10)
        test_db.add_all([node1, node2])
        test_db.commit()
        
        edge = Edge(id="E1", from_id="N1", to_id="N2", weight=5.0)
        test_db.add(edge)
        test_db.commit()
        
        # Delete node1
        test_db.delete(node1)
        test_db.commit()
        
        # Edge should be deleted too
        retrieved_edge = test_db.query(Edge).filter_by(id="E1").first()
        assert retrieved_edge is None


class TestClosureModel:
    """Test the Closure SQLAlchemy model."""
    
    def test_create_node_closure(self, test_db):
        """Test creating a closure for a node."""
        node = Node(id="N1", x=0, y=0)
        test_db.add(node)
        test_db.commit()
        
        closure = Closure(
            id="C1",
            node_id="N1",
            reason="maintenance"
        )
        test_db.add(closure)
        test_db.commit()
        
        retrieved = test_db.query(Closure).filter_by(id="C1").first()
        assert retrieved is not None
        assert retrieved.node_id == "N1"
        assert retrieved.edge_id is None
        assert retrieved.reason == "maintenance"
    
    def test_create_edge_closure(self, test_db):
        """Test creating a closure for an edge."""
        node1 = Node(id="N1", x=0, y=0)
        node2 = Node(id="N2", x=10, y=10)
        test_db.add_all([node1, node2])
        test_db.commit()
        
        edge = Edge(id="E1", from_id="N1", to_id="N2", weight=5.0)
        test_db.add(edge)
        test_db.commit()
        
        closure = Closure(
            id="C1",
            edge_id="E1",
            reason="crowding"
        )
        test_db.add(closure)
        test_db.commit()
        
        retrieved = test_db.query(Closure).filter_by(id="C1").first()
        assert retrieved.edge_id == "E1"
        assert retrieved.node_id is None
        assert retrieved.reason == "crowding"
    
    def test_closure_cascade_delete(self, test_db):
        """Test that closures are deleted when associated nodes/edges are deleted."""
        node = Node(id="N1", x=0, y=0)
        test_db.add(node)
        test_db.commit()
        
        closure = Closure(id="C1", node_id="N1", reason="maintenance")
        test_db.add(closure)
        test_db.commit()
        
        # Delete node
        test_db.delete(node)
        test_db.commit()
        
        # Closure should be deleted too
        retrieved = test_db.query(Closure).filter_by(id="C1").first()
        assert retrieved is None


class TestTileModel:
    """Test the Tile SQLAlchemy model."""
    
    def test_create_tile(self, test_db):
        """Test creating a grid tile."""
        tile = Tile(
            id="tile_0_0_0",
            grid_x=0,
            grid_y=0,
            level=0,
            min_x=0.0,
            max_x=5.0,
            min_y=0.0,
            max_y=5.0,
            walkable=True
        )
        test_db.add(tile)
        test_db.commit()
        
        retrieved = test_db.query(Tile).filter_by(id="tile_0_0_0").first()
        assert retrieved is not None
        assert retrieved.grid_x == 0
        assert retrieved.grid_y == 0
        assert retrieved.walkable is True
    
    def test_tile_with_entities(self, test_db):
        """Test tile with associated entity IDs."""
        tile = Tile(
            id="tile_1_1_0",
            grid_x=1,
            grid_y=1,
            level=0,
            min_x=5.0,
            max_x=10.0,
            min_y=5.0,
            max_y=10.0,
            node_id="N1,N2",
            poi_id="POI1",
            seat_id="SEAT1,SEAT2,SEAT3"
        )
        test_db.add(tile)
        test_db.commit()
        
        retrieved = test_db.query(Tile).filter_by(id="tile_1_1_0").first()
        assert "N1" in retrieved.node_id
        assert "N2" in retrieved.node_id
        assert retrieved.poi_id == "POI1"
        assert "SEAT1" in retrieved.seat_id


class TestEmergencyRouteModel:
    """Test the EmergencyRoute SQLAlchemy model."""
    
    def test_create_emergency_route(self, test_db):
        """Test creating an emergency evacuation route."""
        # Create exit node
        exit_node = Node(id="EXIT-1", name="Emergency Exit", x=0, y=0, type="emergency_exit")
        test_db.add(exit_node)
        test_db.commit()
        
        route = EmergencyRoute(
            id="ER-1",
            name="North Exit Route",
            description="Evacuation route to north exit",
            exit_id="EXIT-1",
            node_ids=["N1", "N2", "N3", "EXIT-1"]
        )
        test_db.add(route)
        test_db.commit()
        
        retrieved = test_db.query(EmergencyRoute).filter_by(id="ER-1").first()
        assert retrieved is not None
        assert retrieved.name == "North Exit Route"
        assert retrieved.exit_id == "EXIT-1"
        assert len(retrieved.node_ids) == 4
        assert retrieved.node_ids[0] == "N1"
        assert retrieved.node_ids[-1] == "EXIT-1"


class TestConstants:
    """Test that model constants are properly defined."""
    
    def test_node_types_defined(self):
        """Test that NODE_TYPES constant is defined."""
        assert isinstance(NODE_TYPES, list)
        assert "corridor" in NODE_TYPES
        assert "seat" in NODE_TYPES
        assert "gate" in NODE_TYPES
        assert "stairs" in NODE_TYPES
    
    def test_closure_reasons_defined(self):
        """Test that CLOSURE_REASONS constant is defined."""
        assert isinstance(CLOSURE_REASONS, list)
        assert "maintenance" in CLOSURE_REASONS
        assert "crowding" in CLOSURE_REASONS
        assert "emergency" in CLOSURE_REASONS
    
    def test_levels_defined(self):
        """Test that LEVELS constant is defined."""
        assert isinstance(LEVELS, list)
        assert 0 in LEVELS
        assert 1 in LEVELS
    
    def test_stands_defined(self):
        """Test that STANDS constant is defined."""
        assert isinstance(STANDS, list)
        assert "Norte" in STANDS
        assert "Sul" in STANDS
        assert "Este" in STANDS
        assert "Oeste" in STANDS


class TestPydanticSchemas:
    """Test Pydantic schemas for validation."""
    
    def test_node_create_schema(self):
        """Test NodeCreate schema validation."""
        data = {
            "id": "TEST-1",
            "name": "Test",
            "x": 100.0,
            "y": 200.0,
            "level": 0,
            "type": "corridor",
            "description": None
        }
        node = NodeCreate(**data)
        assert node.id == "TEST-1"
        assert node.x == 100.0
        assert node.y == 200.0
    
    def test_node_create_with_optional_fields(self):
        """Test NodeCreate with optional seat fields."""
        data = {
            "id": "SEAT-1",
            "x": 100.0,
            "y": 200.0,
            "type": "seat",
            "description": None,
            "block": "Norte-T0",
            "row": 1,
            "number": 15
        }
        node = NodeCreate(**data)
        assert node.block == "Norte-T0"
        assert node.row == 1
        assert node.number == 15
