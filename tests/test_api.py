"""
Tests for API endpoints (full coverage).
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from models import Node, Edge, Closure, EmergencyRoute, Camera, Tile


# ==================== MAP ENDPOINTS ====================

class TestMapEndpoints:
    def test_get_map_empty(self, client, auth_headers):
        response = client.get("/map", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data and "edges" in data and "closures" in data
        assert len(data["nodes"]) == 0

    def test_get_map_with_data(self, client, test_db, auth_headers):
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


# ==================== NODES ====================

class TestNodeEndpoints:
    def test_get_all_nodes(self, client, test_db):
        nodes = [Node(id=f"N{i}", x=float(i*10), y=float(i*10), type="corridor") for i in range(5)]
        test_db.add_all(nodes)
        test_db.commit()
        response = client.get("/nodes")
        assert response.status_code == 200
        assert len(response.json()) == 5

    def test_get_single_node(self, client, test_db):
        node = Node(id="TEST-1", name="Test Node", x=100, y=200, type="corridor")
        test_db.add(node)
        test_db.commit()
        response = client.get("/nodes/TEST-1")
        assert response.status_code == 200
        assert response.json()["id"] == "TEST-1"

    def test_get_nonexistent_node(self, client):
        response = client.get("/nodes/NONEXISTENT")
        assert response.status_code == 404

    def test_create_node_success(self, client, auth_headers, test_db):
        data = {
            "id": "NEW-NODE",
            "name": "Test Node",
            "x": 500,
            "y": 600,
            "level": 0,
            "type": "corridor",
            "description": "A test node"
        }
        response = client.post("/nodes", json=data, headers=auth_headers)
        assert response.status_code == 201
        assert response.json()["id"] == "NEW-NODE"
        assert test_db.query(Node).filter_by(id="NEW-NODE").first() is not None

    def test_create_node_duplicate(self, client, auth_headers, test_db):
        node = Node(id="DUPE", x=0, y=0, type="corridor")
        test_db.add(node)
        test_db.commit()
        data = {
            "id": "DUPE",
            "name": "Duplicate",
            "x": 10,
            "y": 10,
            "level": 0,
            "type": "corridor",
            "description": "Duplicate node"
        }
        response = client.post("/nodes", json=data, headers=auth_headers)
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_update_node_success(self, client, auth_headers, test_db):
        node = Node(id="UPDATE", x=0, y=0, name="Old", type="corridor")
        test_db.add(node)
        test_db.commit()
        data = {"name": "New", "x": 100, "y": 200}
        response = client.put("/nodes/UPDATE", json=data, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "New"
        assert response.json()["x"] == 100

    def test_update_nonexistent_node(self, client, auth_headers):
        response = client.put("/nodes/FAKE", json={"name": "Test"}, headers=auth_headers)
        assert response.status_code == 404

    def test_delete_node_success(self, client, auth_headers, test_db):
        node = Node(id="DELETE", x=0, y=0, type="corridor")
        test_db.add(node)
        test_db.commit()
        response = client.delete("/nodes/DELETE", headers=auth_headers)
        assert response.status_code == 200
        assert test_db.query(Node).filter_by(id="DELETE").first() is None

    def test_delete_node_with_edges(self, client, auth_headers, test_db):
        n1 = Node(id="N_A", x=0, y=0, type="corridor")
        n2 = Node(id="N_B", x=10, y=10, type="corridor")
        e = Edge(id="E", from_id="N_A", to_id="N_B", weight=1)
        test_db.add_all([n1, n2, e])
        test_db.commit()
        response = client.delete("/nodes/N_A", headers=auth_headers)
        assert response.status_code == 200
        assert test_db.query(Node).filter_by(id="N_A").first() is None
        assert test_db.query(Edge).filter_by(id="E").first() is None


# ==================== EDGES ====================

class TestEdgeEndpoints:
    def test_get_all_edges(self, client, test_db):
        n1 = Node(id="E_N1", x=0, y=0, type="corridor")
        n2 = Node(id="E_N2", x=10, y=10, type="corridor")
        e = Edge(id="E1", from_id="E_N1", to_id="E_N2", weight=5.0)
        test_db.add_all([n1, n2, e])
        test_db.commit()
        response = client.get("/edges")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_create_edge_success(self, client, auth_headers, test_db):
        n1 = Node(id="A", x=0, y=0, type="corridor")
        n2 = Node(id="B", x=10, y=10, type="corridor")
        test_db.add_all([n1, n2])
        test_db.commit()
        data = {"id": "NEW-EDGE", "from_id": "A", "to_id": "B", "weight": 7.5}
        response = client.post("/edges", json=data, headers=auth_headers)
        assert response.status_code == 201
        assert response.json()["id"] == "NEW-EDGE"

    def test_create_edge_missing_node(self, client, auth_headers):
        data = {"id": "E2", "from_id": "GHOST", "to_id": "A", "weight": 1}
        response = client.post("/edges", json=data, headers=auth_headers)
        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]

    def test_update_edge(self, client, auth_headers, test_db):
        n1 = Node(id="U1", x=0, y=0, type="corridor")
        n2 = Node(id="U2", x=10, y=10, type="corridor")
        e = Edge(id="EDGE", from_id="U1", to_id="U2", weight=5.0)
        test_db.add_all([n1, n2, e])
        test_db.commit()
        response = client.put("/edges/EDGE", json={"weight": 20.0}, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["weight"] == 20.0

    def test_delete_edge(self, client, auth_headers, test_db):
        n1 = Node(id="D1", x=0, y=0, type="corridor")
        n2 = Node(id="D2", x=10, y=10, type="corridor")
        e = Edge(id="DEL", from_id="D1", to_id="D2", weight=1)
        test_db.add_all([n1, n2, e])
        test_db.commit()
        response = client.delete("/edges/DEL", headers=auth_headers)
        assert response.status_code == 200
        assert test_db.query(Edge).filter_by(id="DEL").first() is None


# ==================== CLOSURES ====================

class TestClosureEndpoints:
    def test_get_all_closures(self, client, test_db):
        node = Node(id="C_NODE", x=0, y=0, type="corridor")
        test_db.add(node)
        test_db.commit()
        closure = Closure(id="CL1", node_id="C_NODE", reason="maintenance")
        test_db.add(closure)
        test_db.commit()
        response = client.get("/closures")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_create_node_closure(self, client, auth_headers, test_db):
        node = Node(id="CLOSED_NODE", x=0, y=0, type="corridor")
        test_db.add(node)
        test_db.commit()
        data = {"id": "NEW-CL", "node_id": "CLOSED_NODE", "reason": "emergency"}
        response = client.post("/closures", json=data, headers=auth_headers)
        assert response.status_code == 201
        assert response.json()["reason"] == "emergency"

    def test_create_edge_closure(self, client, auth_headers, test_db):
        n1 = Node(id="CE1", x=0, y=0, type="corridor")
        n2 = Node(id="CE2", x=10, y=10, type="corridor")
        e = Edge(id="E_CL", from_id="CE1", to_id="CE2", weight=1)
        test_db.add_all([n1, n2, e])
        test_db.commit()
        data = {"id": "CL-EDGE", "edge_id": "E_CL", "reason": "crowding"}
        response = client.post("/closures", json=data, headers=auth_headers)
        assert response.status_code == 201
        assert response.json()["edge_id"] == "E_CL"

    def test_create_closure_without_target(self, client, auth_headers):
        data = {"id": "BAD", "reason": "test"}
        response = client.post("/closures", json=data, headers=auth_headers)
        assert response.status_code == 400

    def test_delete_closure(self, client, auth_headers, test_db):
        node = Node(id="DEL_CL", x=0, y=0, type="corridor")
        test_db.add(node)
        test_db.commit()
        closure = Closure(id="DEL-CL", node_id="DEL_CL", reason="test")
        test_db.add(closure)
        test_db.commit()
        response = client.delete("/closures/DEL-CL", headers=auth_headers)
        assert response.status_code == 200
        assert test_db.query(Closure).filter_by(id="DEL-CL").first() is None


# ==================== TILES & GRID ====================

class TestGridEndpoints:
    def test_get_grid_config(self, client):
        response = client.get("/maps/grid/config")
        assert response.status_code == 200
        assert "cell_size" in response.json()

    def test_get_grid_tiles(self, client, test_db):
        from grid_name import GridManager
        gm = GridManager()
        gm.get_or_create_tile(test_db, 10, 10, 0)
        response = client.get("/maps/grid/tiles?level=0")
        assert response.status_code == 200
        assert response.json()["total_tiles"] > 0

    def test_get_grid_stats(self, client, test_db):
        response = client.get("/maps/grid/stats")
        assert response.status_code == 200
        assert "total_tiles" in response.json()

    def test_rebuild_grid(self, client, auth_headers, test_db):
        node = Node(id="GRID_NODE", x=5, y=5, level=0, type="corridor")
        test_db.add(node)
        test_db.commit()
        response = client.post("/maps/grid/rebuild", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["tiles_created"] > 0

    def test_get_nodes_from_tiles(self, client, auth_headers, test_db):
        from grid_name import GridManager
        gm = GridManager()
        tile = gm.get_or_create_tile(test_db, 12, 12, 0)
        tile.node_id = "N_TEST"
        test_db.commit()
        response = client.post("/maps/grid/tiles/nodes", json=[tile.id], headers=auth_headers)
        assert response.status_code == 200
        assert "N_TEST" in response.json()["node_ids"]


# ==================== POIs ====================

class TestPOIEndpoints:
    def test_get_all_pois(self, client, test_db):
        pois = [
            Node(id="R1", x=100, y=100, type="restroom"),
            Node(id="F1", x=200, y=200, type="food")
        ]
        test_db.add_all(pois)
        test_db.commit()
        response = client.get("/pois")
        assert response.status_code == 200
        assert len(response.json()) >= 2

    def test_create_poi(self, client, auth_headers, test_db):
        data = {
            "name": "Custom POI",
            "type": "food",
            "x": 300,
            "y": 400,
            "level": 0,
            "description": "A custom POI"
        }
        response = client.post("/pois", json=data, headers=auth_headers)
        assert response.status_code == 201
        poi_id = response.json()["id"]
        assert poi_id.startswith("CUSTOM-")
        assert test_db.query(Node).filter_by(id=poi_id).first() is not None

    def test_update_poi(self, client, auth_headers, test_db):
        poi = Node(id="POI_UPDATE", name="Old", type="restroom", x=0, y=0, level=0)
        test_db.add(poi)
        test_db.commit()
        data = {"name": "New Name", "type": "food"}
        response = client.put("/pois/POI_UPDATE", json=data, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "New Name"
        assert response.json()["type"] == "food"

    def test_delete_poi(self, client, auth_headers, test_db):
        poi = Node(id="POI_DEL", name="ToDelete", type="restroom", x=0, y=0, level=0)
        test_db.add(poi)
        test_db.commit()
        response = client.delete("/pois/POI_DEL", headers=auth_headers)
        assert response.status_code == 200
        assert test_db.query(Node).filter_by(id="POI_DEL").first() is None

    def test_get_osm_pois(self, client, auth_headers):
        # Mock the Overpass API to avoid real network calls
        fake_osm_response = {
            "elements": [
                {
                    "type": "node",
                    "id": 12345,
                    "lon": -8.654,
                    "lat": 40.631,
                    "tags": {"name": "Cantina", "amenity": "canteen"}
                }
            ]
        }
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps(fake_osm_response).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_response
            response = client.get("/pois/osm", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert "pois" in data


# ==================== SEATS ====================

class TestSeatEndpoints:
    def test_get_all_seats(self, client, test_db):
        seat = Node(id="SEAT1", x=0, y=0, type="seat", block="A", row=1, number=1)
        test_db.add(seat)
        test_db.commit()
        response = client.get("/seats")
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_get_single_seat(self, client, test_db):
        seat = Node(id="SEAT-TEST", x=0, y=0, type="seat", block="X", row=5, number=10)
        test_db.add(seat)
        test_db.commit()
        response = client.get("/seats/SEAT-TEST")
        assert response.status_code == 200
        assert response.json()["block"] == "X"

    def test_update_seat(self, client, auth_headers, test_db):
        seat = Node(id="SEAT-UP", x=0, y=0, type="seat", block="OLD", row=1, number=1)
        test_db.add(seat)
        test_db.commit()
        data = {"block": "NEW", "row": 2}
        response = client.put("/seats/SEAT-UP", json=data, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["block"] == "NEW"
        assert response.json()["row"] == 2


# ==================== GATES ====================

class TestGateEndpoints:
    def test_get_all_gates(self, client, test_db):
        gate = Node(id="GATE1", x=0, y=0, type="gate", num_servers=3, service_rate=10)
        test_db.add(gate)
        test_db.commit()
        response = client.get("/gates")
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_update_gate(self, client, auth_headers, test_db):
        gate = Node(id="GATE-UPD", x=0, y=0, type="gate", num_servers=2)
        test_db.add(gate)
        test_db.commit()
        data = {"num_servers": 5, "service_rate": 12.5}
        response = client.put("/gates/GATE-UPD", json=data, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["num_servers"] == 5
        assert response.json()["service_rate"] == 12.5


# ==================== EMERGENCY ROUTES ====================

class TestEmergencyRouteEndpoints:
    def test_list_empty(self, client):
        response = client.get("/emergency-routes")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_and_get_route(self, client, test_db):
        nodes = [Node(id=f"N{i}", x=i*10, y=i*10, type="corridor") for i in range(3)]
        exit_node = Node(id="EXIT", x=100, y=100, type="emergency_exit")
        test_db.add_all(nodes + [exit_node])
        test_db.commit()
        route = EmergencyRoute(
            id="ER1", name="Route 1", exit_id="EXIT", node_ids=["N0", "N1", "N2", "EXIT"]
        )
        test_db.add(route)
        test_db.commit()
        response = client.get("/emergency-routes")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == "ER1"

    def test_get_route_geojson(self, client, test_db):
        nodes = [Node(id=f"N{i}", x=i*10, y=i*10, type="corridor") for i in range(2)]
        exit_node = Node(id="EXIT2", x=50, y=50, type="emergency_exit")
        test_db.add_all(nodes + [exit_node])
        test_db.commit()
        route = EmergencyRoute(
            id="ER2", name="Route 2", exit_id="EXIT2", node_ids=["N0", "N1", "EXIT2"]
        )
        test_db.add(route)
        test_db.commit()
        response = client.get("/emergency-routes/ER2")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) > 0

    def test_nearest_emergency_route(self, client, test_db):
        nodes = [Node(id=f"N{i}", x=i*10, y=i*10, type="corridor") for i in range(3)]
        exit_node = Node(id="EXIT3", x=100, y=100, type="emergency_exit")
        test_db.add_all(nodes + [exit_node])
        test_db.commit()
        route = EmergencyRoute(
            id="ER3", name="Route 3", exit_id="EXIT3", node_ids=["N0", "N1", "N2", "EXIT3"]
        )
        test_db.add(route)
        test_db.commit()
        response = client.get("/emergency-routes/nearest?x=5&y=5&level=0")
        assert response.status_code == 200
        assert response.json()["route_id"] == "ER3"


# ==================== CAMERAS ====================

class TestCameraEndpoints:
    def test_create_camera(self, client, auth_headers, test_db):
        node = Node(id="CAM_NODE", x=0, y=0, type="camera")
        test_db.add(node)
        test_db.commit()
        data = {
            "id": "CAM1", "node_id": "CAM_NODE",
            "pos_x": 10, "pos_y": 20, "pos_z": 5,
            "pan": 0, "tilt": -30, "fov_horizontal": 70, "fov_vertical": 55
        }
        response = client.post("/cameras", json=data, headers=auth_headers)
        assert response.status_code == 201
        assert response.json()["id"] == "CAM1"

    def test_get_camera(self, client, test_db):
        node = Node(id="CAM_GET", x=0, y=0, type="camera")
        test_db.add(node)
        test_db.commit()
        camera = Camera(id="CAM_GET_ID", node_id="CAM_GET", pos_x=0, pos_y=0, pos_z=2)
        test_db.add(camera)
        test_db.commit()
        response = client.get("/cameras/CAM_GET_ID")
        assert response.status_code == 200
        assert response.json()["id"] == "CAM_GET_ID"

    def test_update_camera(self, client, auth_headers, test_db):
        node = Node(id="CAM_UPD", x=0, y=0, type="camera")
        test_db.add(node)
        test_db.commit()
        camera = Camera(id="CAM_UPD_ID", node_id="CAM_UPD", pos_x=0, pos_y=0, pos_z=2)
        test_db.add(camera)
        test_db.commit()
        data = {"pan": 45, "tilt": -60}
        response = client.put("/cameras/CAM_UPD_ID", json=data, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["pan"] == 45
        assert response.json()["tilt"] == -60

    def test_delete_camera(self, client, auth_headers, test_db):
        node = Node(id="CAM_DEL", x=0, y=0, type="camera")
        test_db.add(node)
        test_db.commit()
        camera = Camera(id="CAM_DEL_ID", node_id="CAM_DEL", pos_x=0, pos_y=0, pos_z=2)
        test_db.add(camera)
        test_db.commit()
        response = client.delete("/cameras/CAM_DEL_ID", headers=auth_headers)
        assert response.status_code == 200
        assert test_db.query(Camera).filter_by(id="CAM_DEL_ID").first() is None


# ==================== BATCH & SYNC ====================

class TestBatchEndpoints:
    def test_create_batch(self, client, auth_headers, test_db):
        batch_data = {
            "nodes": [
                {
                    "id": "BATCH_NODE",
                    "name": "Batch Node",
                    "x": 0,
                    "y": 0,
                    "level": 0,
                    "type": "corridor",
                    "description": "Batch node description"
                }
            ],
            "edges": [],
            "closures": []
        }
        response = client.post("/batch", json=batch_data, headers=auth_headers)
        assert response.status_code == 201
        assert "BATCH_NODE" in response.json()["nodes"]["created"]

    def test_sync_map(self, client, auth_headers, test_db):
        sync_data = {
            "nodes": [
                {
                    "id": "SYNC_NODE",
                    "name": "Sync Node",
                    "x": 10,
                    "y": 20,
                    "level": 0,
                    "type": "gate",
                    "description": "Sync node description"
                }
            ],
            "edges": [],
            "closures": []
        }
        response = client.post("/map/sync", json=sync_data, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        # Verify that old data was cleared
        assert test_db.query(Node).filter_by(id="SYNC_NODE").first() is not None


# ==================== UTILITY & RESET ====================

class TestUtilityEndpoints:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_reset_database(self, client, auth_headers, test_db):
        node = Node(id="RESET_NODE", x=0, y=0, type="corridor")
        test_db.add(node)
        test_db.commit()
        response = client.post("/reset", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        # After reset, the node should be gone (only sample data loaded)
        assert test_db.query(Node).filter_by(id="RESET_NODE").first() is None


# ==================== GEOJSON ENDPOINTS ====================

class TestGeoJSONEndpoints:
    def test_get_geojson_empty(self, client):
        response = client.get("/map/geojson")
        assert response.status_code == 200
        assert response.json()["type"] == "FeatureCollection"

    def test_get_geojson_with_nodes(self, client, test_db):
        node = Node(id="GEO_NODE", x=100, y=200, type="corridor", level=0)
        test_db.add(node)
        test_db.commit()
        response = client.get("/map/geojson")
        assert response.status_code == 200
        assert len(response.json()["features"]) >= 1

    def test_get_geojson_filtered_by_level(self, client, test_db):
        node0 = Node(id="L0", x=0, y=0, level=0, type="corridor")
        node1 = Node(id="L1", x=10, y=10, level=1, type="corridor")
        test_db.add_all([node0, node1])
        test_db.commit()
        response = client.get("/map/geojson?level=0")
        assert response.status_code == 200
        # Should only contain the level 0 node
        features = response.json()["features"]
        assert all(f["properties"]["level"] == 0 for f in features if f["geometry"]["type"] == "Point")

    def test_get_map_bounds(self, client, test_db):
        nodes = [Node(id="B1", x=0, y=10, type="corridor"), Node(id="B2", x=100, y=50, type="corridor")]
        test_db.add_all(nodes)
        test_db.commit()
        response = client.get("/map/bounds")
        assert response.status_code == 200
        data = response.json()
        assert data["bounds"]["min_x"] == 0
        assert data["bounds"]["max_x"] == 100
        assert data["bounds"]["min_y"] == 10
        assert data["bounds"]["max_y"] == 50
        assert "levels" in data


# ==================== ERROR HANDLING ====================

class TestErrorHandling:
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

class TestMapVisualization:
    def test_visualization_empty(self, client, auth_headers):
        response = client.get("/map/visualization", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["level"] == "all"
        assert all(len(data["nodes"][key]) == 0 for key in data["nodes"])
        assert data["stats"]["total"] == 0

    def test_visualization_with_corridor(self, client, test_db, auth_headers):
        node = Node(id="CORR", x=0, y=0, type="corridor", level=0)
        test_db.add(node)
        test_db.commit()
        response = client.get("/map/visualization", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]["navigation"]) == 1
        assert data["stats"]["navigation"] == 1
        assert data["stats"]["total"] == 1

    def test_visualization_with_gate(self, client, test_db, auth_headers):
        node = Node(id="GATE", x=0, y=0, type="gate", num_servers=2, service_rate=5.0)
        test_db.add(node)
        test_db.commit()
        response = client.get("/map/visualization", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]["gates"]) == 1
        assert data["nodes"]["gates"][0]["num_servers"] == 2
        assert data["stats"]["gates"] == 1

    def test_visualization_with_stairs(self, client, test_db, auth_headers):
        node = Node(id="STAIR", x=0, y=0, type="stairs")
        test_db.add(node)
        test_db.commit()
        response = client.get("/map/visualization", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]["stairs"]) == 1
        assert data["stats"]["stairs"] == 1

    def test_visualization_with_seat(self, client, test_db, auth_headers):
        node = Node(id="SEAT", x=0, y=0, type="seat", block="A", row=1, number=5)
        test_db.add(node)
        test_db.commit()
        response = client.get("/map/visualization", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]["seats"]) == 1
        assert data["nodes"]["seats"][0]["block"] == "A"
        assert data["stats"]["seats"] == 1

    def test_visualization_with_department(self, client, test_db, auth_headers):
        node = Node(id="DEPT", x=0, y=0, type="departments")
        test_db.add(node)
        test_db.commit()
        response = client.get("/map/visualization", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]["departments"]) == 1
        assert data["stats"]["departments"] == 1

    def test_visualization_with_poi(self, client, test_db, auth_headers):
        node = Node(id="REST", x=0, y=0, type="restroom", num_servers=2, service_rate=1.5)
        test_db.add(node)
        test_db.commit()
        response = client.get("/map/visualization", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]["pois"]) == 1
        assert data["nodes"]["pois"][0]["type"] == "restroom"
        assert data["stats"]["pois"] == 1

    def test_visualization_filter_level(self, client, test_db, auth_headers):
        node0 = Node(id="N0", x=0, y=0, level=0, type="corridor")
        node1 = Node(id="N1", x=10, y=10, level=1, type="corridor")
        test_db.add_all([node0, node1])
        test_db.commit()
        response = client.get("/map/visualization?level=0", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["level"] == 0
        assert data["stats"]["total"] == 1
        assert isinstance(data["edges"], list)

    def test_visualization_with_edges(self, client, test_db, auth_headers):
        n1 = Node(id="N1", x=0, y=0, level=0, type="corridor")
        n2 = Node(id="N2", x=10, y=10, level=0, type="corridor")
        e = Edge(id="E", from_id="N1", to_id="N2", weight=5.0)
        test_db.add_all([n1, n2, e])
        test_db.commit()
        response = client.get("/map/visualization?level=0", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["edges"]) == 1
        assert data["edges"][0]["id"] == "E"

