"""
Authorization tests: verify all mutation endpoints return 401 without X-API-Key.

Uses the shared 'client' fixture from conftest.py — the same setup that
the 71 passing tests use. The conftest client correctly builds the middleware
stack and provides a warm TestClient.
"""
import pytest


# ── Payloads ────────────────────────────────────────────────────────────────

_NODE = {"id": "AUTH-N", "name": "n", "x": 0, "y": 0, "level": 0, "type": "corridor", "description": "x"}
_EDGE = {"id": "AUTH-E", "from_id": "X", "to_id": "Y", "weight": 1.0}
_CLOSURE = {"id": "AUTH-CL", "node_id": "X", "reason": "test"}
_POI = {"name": "Auth POI", "type": "food", "x": 0, "y": 0, "level": 0}
_CAMERA = {"id": "AUTH-CAM", "node_id": "X", "pos_x": 0, "pos_y": 0, "pos_z": 2}
_BATCH = {"nodes": [], "edges": [], "closures": []}


# ── Node mutations ────────────────────────────────────────────────────────────

def test_create_node_401(client):
    assert client.post("/nodes", json=_NODE).status_code == 401

def test_update_node_401(client):
    assert client.put("/nodes/X", json={"name": "X"}).status_code == 401

def test_delete_node_401(client):
    assert client.delete("/nodes/X").status_code == 401


# ── Edge mutations ────────────────────────────────────────────────────────────

def test_create_edge_401(client):
    assert client.post("/edges", json=_EDGE).status_code == 401

def test_update_edge_401(client):
    assert client.put("/edges/X", json={"weight": 1}).status_code == 401

def test_delete_edge_401(client):
    assert client.delete("/edges/X").status_code == 401


# ── Closure mutations ─────────────────────────────────────────────────────────

def test_create_closure_401(client):
    assert client.post("/closures", json=_CLOSURE).status_code == 401

def test_delete_closure_401(client):
    assert client.delete("/closures/X").status_code == 401


# ── Grid mutations ────────────────────────────────────────────────────────────

def test_rebuild_grid_401(client):
    assert client.post("/maps/grid/rebuild").status_code == 401

def test_get_nodes_from_tiles_401(client):
    assert client.post("/maps/grid/tiles/nodes", json=["tile1"]).status_code == 401


# ── POI mutations ─────────────────────────────────────────────────────────────

def test_create_poi_401(client):
    assert client.post("/pois", json=_POI).status_code == 401

def test_update_poi_401(client):
    assert client.put("/pois/X", json={"name": "X"}).status_code == 401

def test_delete_poi_401(client):
    assert client.delete("/pois/X").status_code == 401


# ── Seat / Gate mutations ─────────────────────────────────────────────────────

def test_update_seat_401(client):
    assert client.put("/seats/X", json={"block": "A"}).status_code == 401

def test_update_gate_401(client):
    assert client.put("/gates/X", json={"name": "G"}).status_code == 401


# ── Camera mutations ──────────────────────────────────────────────────────────

def test_create_camera_401(client):
    assert client.post("/cameras", json=_CAMERA).status_code == 401

def test_update_camera_401(client):
    assert client.put("/cameras/X", json={"pan": 0}).status_code == 401

def test_delete_camera_401(client):
    assert client.delete("/cameras/X").status_code == 401


# ── Data-management mutations ─────────────────────────────────────────────────

def test_reset_401(client):
    assert client.post("/reset").status_code == 401

def test_batch_401(client):
    assert client.post("/batch", json=_BATCH).status_code == 401

def test_sync_map_401(client):
    assert client.post("/map/sync", json=_BATCH).status_code == 401


# ── Health check is public ────────────────────────────────────────────────────

def test_health_is_public(client):
    assert client.get("/health").status_code == 200
