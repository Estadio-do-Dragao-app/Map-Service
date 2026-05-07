"""
Tests for API endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from models import Node, Edge, Closure, EmergencyRoute


class TestMapEndpoints:
    """Test /map endpoints."""

    def test_get_map_empty(self, client, auth_headers):
        """Test getting an empty map."""
        response = client.get("/map", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert "closures" in data
        assert len(data["nodes"]) == 0
        assert len(data["edges"]) == 0

    def test_get_map_with_data(self, client, test_db, auth_headers):
        """Test getting map with nodes and edges."""
        node1 = Node(id="N1", x=100, y=200, type="corridor")
        node2 = Node(id="N2", x=150, y=250, type="gate")
        edge1 = Edge(id="E1", from_id="N1", to_id="N2", weight=5.0)

        test_db.add_all([node1, node2, edge1])
        test_db.commit()

        response = client.get("/map", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1

        node_ids = [n["id"] for n in data["nodes"]]
        assert "N1" in node_ids
        assert "N2" in node_ids


class TestNodeEndpoints:
    """Test /nodes endpoints."""

    def test_get_all_nodes(self, client, test_db):
        """Test getting all nodes."""
        nodes = [
            Node(id=f"N{i}", x=float(i * 10), y=float(i * 10))
            for i in range(5)
        ]
        test_db.add_all(nodes)
        test_db.commit()

        response = client.get("/nodes")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    def test_get_single_node(self, client, test_db):
        """Test getting a single node by ID."""
        node = Node(id="TEST-1", name="Test Node", x=100, y=200, type="corridor")
        test_db.add(node)
        test_db.commit()

        response = client.get("/nodes/TEST-1")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == "TEST-1"
        assert data["name"] == "Test Node"
        assert data["x"] == 100
        assert data["y"] == 200

    def test_get_nonexistent_node(self, client):
        """Test getting a node that doesn't exist."""
        response = client.get("/nodes/NONEXISTENT")
        assert response.status_code == 404

    def test_update_node(self, client, test_db):
        """Test updating a node."""
        node = Node(id="N1", x=100, y=200, name="Original")
        test_db.add(node)
        test_db.commit()

        update_data = {"name": "Updated", "x": 150, "y": 250}

        response = client.put("/nodes/N1", json=update_data)
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Updated"
        assert data["x"] == 150
        assert data["y"] == 250

        updated_node = test_db.query(Node).filter_by(id="N1").first()
        assert updated_node.name == "Updated"
        assert updated_node.x == 150

    def test_update_nonexistent_node(self, client):
        """Test updating a node that doesn't exist."""
        update_data = {"name": "Test"}
        response = client.put("/nodes/NONEXISTENT", json=update_data)
        assert response.status_code == 404


class TestEdgeEndpoints:
    """Test /edges endpoints."""

    def test_get_all_edges(self, client, test_db):
        """Test getting all edges."""
        node1 = Node(id="N1", x=0, y=0)
        node2 = Node(id="N2", x=10, y=10)
        test_db.add_all([node1, node2])
        test_db.commit()

        edges = [Edge(id="E1", from_id="N1", to_id="N2", weight=5.0)]
        test_db.add_all(edges)
        test_db.commit()

        response = client.get("/edges")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_get_single_edge(self, client, test_db):
        """Test getting a single edge by ID."""
        node1 = Node(id="N1", x=0, y=0)
        node2 = Node(id="N2", x=10, y=10)
        test_db.add_all([node1, node2])
        test_db.commit()

        edge = Edge(id="E1", from_id="N1", to_id="N2", weight=5.0)
        test_db.add(edge)
        test_db.commit()

        response = client.get("/edges/E1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "E1"
        assert data["from_id"] == "N1"
        assert data["to_id"] == "N2"
        assert data["weight"] == 5.0

    def test_update_edge(self, client, test_db):
        """Test updating an edge."""
        node1 = Node(id="N1", x=0, y=0)
        node2 = Node(id="N2", x=10, y=10)
        test_db.add_all([node1, node2])
        test_db.commit()

        edge = Edge(id="E1", from_id="N1", to_id="N2", weight=5.0, accessible=True)
        test_db.add(edge)
        test_db.commit()

        update_data = {"weight": 10.0, "accessible": False}
        response = client.put("/edges/E1", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 10.0
        assert data["accessible"] is False


class TestClosureEndpoints:
    """Test /closures endpoints."""

    def test_create_node_closure(self, client, test_db):
        node = Node(id="N1", x=0, y=0)
        test_db.add(node)
        test_db.commit()

        closure_data = {"id": "C1", "node_id": "N1", "reason": "maintenance"}
        response = client.post("/closures", json=closure_data)
        assert response.status_code == 201
        data = response.json()
        assert data["node_id"] == "N1"
        assert data["reason"] == "maintenance"

    def test_create_edge_closure(self, client, test_db):
        node1 = Node(id="N1", x=0, y=0)
        node2 = Node(id="N2", x=10, y=10)
        test_db.add_all([node1, node2])
        test_db.commit()

        edge = Edge(id="E1", from_id="N1", to_id="N2", weight=5.0)
        test_db.add(edge)
        test_db.commit()

        closure_data = {"id": "C1", "edge_id": "E1", "reason": "crowding"}
        response = client.post("/closures", json=closure_data)
        assert response.status_code == 201
        data = response.json()
        assert data["edge_id"] == "E1"
        assert data["reason"] == "crowding"

    def test_create_closure_neither_node_nor_edge(self, client):
        closure_data = {"id": "C1", "reason": "maintenance"}
        response = client.post("/closures", json=closure_data)
        assert response.status_code == 400

    def test_delete_closure(self, client, test_db):
        node = Node(id="N1", x=0, y=0)
        test_db.add(node)
        test_db.commit()

        closure = Closure(id="C1", node_id="N1", reason="maintenance")
        test_db.add(closure)
        test_db.commit()

        response = client.delete("/closures/C1")
        assert response.status_code == 200
        deleted = test_db.query(Closure).filter_by(id="C1").first()
        assert deleted is None

    def test_delete_nonexistent_closure(self, client):
        response = client.delete("/closures/NONEXISTENT")
        assert response.status_code == 404


class TestPOIEndpoints:
    """Test POI endpoints."""

    def test_get_all_pois(self, client, test_db):
        pois = [
            Node(id="R1", x=100, y=100, type="restroom"),
            Node(id="F1", x=200, y=200, type="food"),
        ]
        test_db.add_all(pois)
        test_db.commit()

        response = client.get("/pois")
        assert response.status_code == 200
        assert len(response.json()) >= 2


class TestGeoJSONEndpoints:
    """Test GeoJSON endpoints."""

    def test_get_geojson_empty(self, client):
        response = client.get("/map/geojson")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 0

    def test_get_geojson_with_nodes(self, client, test_db):
        nodes = [
            Node(id="N1", x=100, y=200, type="corridor", level=0),
            Node(id="N2", x=150, y=250, type="gate", level=0),
        ]
        test_db.add_all(nodes)
        test_db.commit()

        response = client.get("/map/geojson")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 2

    def test_get_geojson_filtered_by_level(self, client, test_db):
        nodes = [
            Node(id="N1", x=100, y=200, level=0),
            Node(id="N2", x=150, y=250, level=1),
        ]
        test_db.add_all(nodes)
        test_db.commit()

        response = client.get("/map/geojson?level=0")
        assert response.status_code == 200

    def test_get_map_bounds(self, client, test_db):
        nodes = [
            Node(id="N1", x=0, y=10),
            Node(id="N2", x=100, y=50),
        ]
        test_db.add_all(nodes)
        test_db.commit()

        response = client.get("/map/bounds")
        assert response.status_code == 200
        data = response.json()
        assert "bounds" in data
        assert "center" in data
        assert "levels" in data


class TestGridEndpoints:
    """Test grid management endpoints."""

    def test_get_grid_config(self, client):
        response = client.get("/maps/grid/config")
        assert response.status_code == 200
        data = response.json()
        assert "cell_size" in data
        assert "origin_x" in data
        assert "origin_y" in data

    def test_get_grid_tiles(self, client, test_db):
        from grid_name import GridManager
        gm = GridManager()
        gm.get_or_create_tile(test_db, 10.0, 10.0, 0)
        response = client.get("/maps/grid/tiles?level=0")
        assert response.status_code == 200
        data = response.json()
        assert "tiles" in data
        assert len(data["tiles"]) > 0

    def test_get_grid_stats(self, client, test_db):
        response = client.get("/maps/grid/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_tiles" in data


class TestEmergencyRouteEndpoints:
    """Test emergency route endpoints."""

    def test_list_emergency_routes(self, client, test_db):
        response = client.get("/emergency-routes")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_nearest_emergency_route(self, client, test_db):
        nodes = [Node(id=f"N{i}", x=float(i * 10), y=float(i * 10)) for i in range(5)]
        test_db.add_all(nodes)
        test_db.commit()

        route = EmergencyRoute(
            id="ER1", name="Exit Route 1", exit_id="N4", node_ids=["N0", "N1", "N2", "N3", "N4"]
        )
        test_db.add(route)
        test_db.commit()

        response = client.get("/emergency-routes/nearest?x=5&y=5")
        assert response.status_code == 200

    def test_get_emergency_route_geojson(self, client, test_db):
        nodes = [Node(id=f"N{i}", x=float(i * 10), y=float(i * 10)) for i in range(5)]
        test_db.add_all(nodes)
        test_db.commit()

        route = EmergencyRoute(
            id="ER1", name="Exit Route 1", exit_id="N4", node_ids=["N0", "N1", "N2", "N3", "N4"]
        )
        test_db.add(route)
        test_db.commit()

        response = client.get("/emergency-routes/ER1")
        assert response.status_code == 200


class TestUtilityEndpoints:
    """Test utility endpoints."""

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_reset_database(self, client, auth_headers):
        response = client.post("/reset", headers=auth_headers)
        assert response.status_code == 200


class TestCORSAndMiddleware:
    """Test middleware and CORS configuration."""

    def test_gzip_compression(self, client, test_db, auth_headers):
        nodes = [Node(id=f"N{i}", x=float(i), y=float(i)) for i in range(100)]
        test_db.add_all(nodes)
        test_db.commit()

        response = client.get("/map", headers=auth_headers)
        assert response.status_code == 200


class TestErrorHandling:
    """Test error handling in API."""

    def test_invalid_endpoint(self, client):
        response = client.get("/invalid/endpoint")
        assert response.status_code == 404

    def test_malformed_json(self, client):
        response = client.post(
            "/closures",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422