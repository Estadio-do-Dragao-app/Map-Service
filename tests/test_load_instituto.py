"""
Tests for load_instituto.py – graph loading functions.
Uses the same in-memory SQLite setup as conftest.py.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base, Node, Edge, Tile
from load_instituto import clear_database, load_graph, generate_tiles


@pytest.fixture(scope="function")
def db_session():
    """Provide an in-memory SQLite session for load_instituto tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def sample_graph_data():
    return {
        "metadata": {
            "name": "Test Graph",
            "source": "test",
            "svg_width": 100,
            "svg_height": 100,
        },
        "nodes": [
            {"id": "N1", "name": "Node 1", "x": 10.0, "y": 20.0, "level": 0, "type": "corridor"},
            {"id": "N2", "name": "Node 2", "x": 50.0, "y": 50.0, "level": 0, "type": "normal"},
            {"id": "POI-1", "name": "WC", "x": 30.0, "y": 30.0, "level": 0, "type": "restroom"},
        ],
        "edges": [
            {"id": "E1", "from_id": "N1", "to_id": "N2", "weight": 10.0, "accessible": True},
            {"id": "E2", "from_id": "N2", "to_id": "N1", "weight": 10.0},
        ],
    }


class TestClearDatabase:
    def test_clear_empty_database(self, db_session):
        """Clearing an already empty database should not raise."""
        clear_database(db_session)
        assert db_session.query(Node).count() == 0
        assert db_session.query(Edge).count() == 0
        assert db_session.query(Tile).count() == 0

    def test_clear_removes_all_data(self, db_session):
        node = Node(id="N1", x=0.0, y=0.0, level=0, type="corridor")
        edge = Edge(id="E1", from_id="N1", to_id="N1", weight=1.0, accessible=True)
        db_session.add(node)
        db_session.flush()
        db_session.add(edge)
        db_session.commit()

        assert db_session.query(Node).count() == 1
        clear_database(db_session)
        assert db_session.query(Node).count() == 0
        assert db_session.query(Edge).count() == 0


class TestGenerateTiles:
    def test_generates_correct_tile_count(self, db_session):
        nodes_data = [{"id": "N1", "x": 50.0, "y": 50.0, "type": "corridor"}]
        generate_tiles(db_session, nodes_data, svg_width=100, svg_height=100, grid_size=5)
        count = db_session.query(Tile).count()
        assert count == 25  # 5×5 grid

    def test_default_grid_size_10(self, db_session):
        generate_tiles(db_session, [], svg_width=460, svg_height=465)
        count = db_session.query(Tile).count()
        assert count == 100  # 10×10 grid

    def test_tile_ids_are_unique(self, db_session):
        generate_tiles(db_session, [], svg_width=100, svg_height=100, grid_size=3)
        tiles = db_session.query(Tile).all()
        ids = [t.id for t in tiles]
        assert len(ids) == len(set(ids))

    def test_tile_bounds_are_correct(self, db_session):
        generate_tiles(db_session, [], svg_width=100, svg_height=100, grid_size=10)
        tiles = db_session.query(Tile).all()
        for tile in tiles:
            assert tile.min_x < tile.max_x
            assert tile.min_y < tile.max_y
            assert tile.walkable is True

    def test_normal_node_assigned_to_tile(self, db_session):
        nodes_data = [{"id": "N1", "x": 5.0, "y": 5.0, "type": "corridor"}]
        generate_tiles(db_session, nodes_data, svg_width=100, svg_height=100, grid_size=10)
        tile = db_session.query(Tile).filter_by(id="tile_0_0_L0").first()
        assert tile is not None
        assert tile.node_id == "N1"

    def test_poi_node_assigned_as_poi_id(self, db_session):
        nodes_data = [{"id": "POI-42", "x": 5.0, "y": 5.0, "type": "restroom"}]
        generate_tiles(db_session, nodes_data, svg_width=100, svg_height=100, grid_size=10)
        tile = db_session.query(Tile).filter_by(id="tile_0_0_L0").first()
        assert tile is not None
        assert tile.poi_id == "POI-42"
        assert tile.node_id is None

    def test_empty_nodes_all_tiles_without_node(self, db_session):
        generate_tiles(db_session, [], svg_width=100, svg_height=100, grid_size=5)
        tiles = db_session.query(Tile).all()
        for tile in tiles:
            assert tile.node_id is None
            assert tile.poi_id is None


class TestLoadGraph:
    def test_loads_nodes_and_edges(self, db_session, sample_graph_data):
        load_graph(db_session, sample_graph_data)
        assert db_session.query(Node).count() == 3
        assert db_session.query(Edge).count() == 2

    def test_node_attributes(self, db_session, sample_graph_data):
        load_graph(db_session, sample_graph_data)
        n1 = db_session.query(Node).filter_by(id="N1").first()
        assert n1 is not None
        assert n1.x == 10.0
        assert n1.y == 20.0
        assert n1.level == 0
        assert n1.type == "corridor"

    def test_edge_attributes(self, db_session, sample_graph_data):
        load_graph(db_session, sample_graph_data)
        e1 = db_session.query(Edge).filter_by(id="E1").first()
        assert e1 is not None
        assert e1.from_id == "N1"
        assert e1.to_id == "N2"
        assert e1.weight == 10.0
        assert e1.accessible is True

    def test_edge_accessible_defaults_to_true(self, db_session, sample_graph_data):
        load_graph(db_session, sample_graph_data)
        e2 = db_session.query(Edge).filter_by(id="E2").first()
        assert e2.accessible is True

    def test_tiles_generated(self, db_session, sample_graph_data):
        load_graph(db_session, sample_graph_data)
        count = db_session.query(Tile).count()
        assert count == 100  # default 10×10 grid

    def test_empty_graph(self, db_session):
        graph_data = {
            "metadata": {"name": "Empty", "source": "test"},
            "nodes": [],
            "edges": [],
        }
        load_graph(db_session, graph_data)
        assert db_session.query(Node).count() == 0
        assert db_session.query(Edge).count() == 0

    def test_missing_optional_node_fields(self, db_session):
        graph_data = {
            "metadata": {},
            "nodes": [{"id": "N1", "x": 0.0, "y": 0.0}],
            "edges": [],
        }
        load_graph(db_session, graph_data)
        n1 = db_session.query(Node).filter_by(id="N1").first()
        assert n1 is not None
        assert n1.level == 0
        assert n1.type == "normal"
