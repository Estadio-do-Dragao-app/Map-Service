"""
Tests for generate_ua.py – pure functions that don't require network access.
"""
import math
import pytest
from generate_ua import haversine, _poi_type, process_ways, process_pois


class TestHaversine:
    """Tests for the haversine distance function."""

    def test_same_point_returns_zero(self):
        dist = haversine(0.0, 0.0, 0.0, 0.0)
        assert dist == pytest.approx(0.0, abs=1e-6)

    def test_known_distance_equator(self):
        # 1 degree of longitude along the equator ≈ 111,320 m
        dist = haversine(0.0, 0.0, 1.0, 0.0)
        assert dist == pytest.approx(111320, rel=0.01)

    def test_known_distance_meridian(self):
        # 1 degree of latitude ≈ 111,111 m
        dist = haversine(0.0, 0.0, 0.0, 1.0)
        assert dist == pytest.approx(111111, rel=0.01)

    def test_short_distance(self):
        # Two points roughly 100 m apart at UA campus
        lon1, lat1 = -8.660, 40.630
        lon2, lat2 = -8.659, 40.630  # ~90 m east
        dist = haversine(lon1, lat1, lon2, lat2)
        assert 50 < dist < 150

    def test_symmetry(self):
        """haversine(A→B) == haversine(B→A)."""
        d1 = haversine(-8.660, 40.630, -8.655, 40.633)
        d2 = haversine(-8.655, 40.633, -8.660, 40.630)
        assert d1 == pytest.approx(d2, rel=1e-9)

    def test_returns_metres(self):
        """Result should be in metres (Earth radius ~6,371 km)."""
        dist = haversine(0.0, 0.0, 1.0, 0.0)
        assert dist > 100_000  # more than 100 km


class TestPoiType:
    """Tests for the _poi_type tag-mapping function."""

    # ── Skip clutter ──
    def test_skip_waste_basket(self):
        assert _poi_type({"amenity": "waste_basket"}) is None

    def test_skip_bench(self):
        assert _poi_type({"amenity": "bench"}) is None

    def test_skip_recycling(self):
        assert _poi_type({"amenity": "recycling"}) is None

    def test_skip_vending_machine(self):
        assert _poi_type({"amenity": "vending_machine"}) is None

    def test_skip_telephone(self):
        assert _poi_type({"amenity": "telephone"}) is None

    def test_skip_waiting_room(self):
        assert _poi_type({"amenity": "waiting_room"}) is None

    def test_skip_fountain(self):
        assert _poi_type({"amenity": "fountain"}) is None

    def test_skip_drinking_water(self):
        assert _poi_type({"amenity": "drinking_water"}) is None

    def test_skip_dormitory(self):
        assert _poi_type({"building": "dormitory"}) is None

    # ── ATM ──
    def test_atm(self):
        assert _poi_type({"amenity": "atm"}) == "atm"

    # ── Parking ──
    def test_parking(self):
        assert _poi_type({"amenity": "parking"}) == "parking"

    def test_bicycle_parking(self):
        assert _poi_type({"amenity": "bicycle_parking"}) == "parking"

    def test_motorcycle_parking(self):
        assert _poi_type({"amenity": "motorcycle_parking"}) == "parking"

    def test_parking_entrance(self):
        assert _poi_type({"amenity": "parking_entrance"}) == "parking"

    # ── Information ──
    def test_reception_desk(self):
        assert _poi_type({"amenity": "reception_desk"}) == "information"

    # ── Food & drink ──
    def test_restaurant(self):
        assert _poi_type({"amenity": "restaurant"}) == "food"

    def test_fast_food(self):
        assert _poi_type({"amenity": "fast_food"}) == "food"

    def test_food_court(self):
        assert _poi_type({"amenity": "food_court"}) == "food"

    def test_canteen(self):
        assert _poi_type({"amenity": "canteen"}) == "food"

    def test_cafe(self):
        assert _poi_type({"amenity": "cafe"}) == "cafe"

    def test_bar(self):
        assert _poi_type({"amenity": "bar"}) == "bar"

    def test_pub(self):
        assert _poi_type({"amenity": "pub"}) == "bar"

    # ── Services ──
    def test_toilets(self):
        assert _poi_type({"amenity": "toilets"}) == "wc"

    def test_library(self):
        assert _poi_type({"amenity": "library"}) == "library"

    def test_pharmacy(self):
        assert _poi_type({"amenity": "pharmacy"}) == "first_aid"

    def test_hospital(self):
        assert _poi_type({"amenity": "hospital"}) == "first_aid"

    def test_clinic(self):
        assert _poi_type({"amenity": "clinic"}) == "first_aid"

    # ── Departments ──
    def test_university_building(self):
        assert _poi_type({"building": "university"}) == "departments"

    def test_college_building(self):
        assert _poi_type({"building": "college"}) == "departments"

    def test_school_building(self):
        assert _poi_type({"building": "school"}) == "departments"

    def test_sports_centre_building(self):
        assert _poi_type({"building": "sports_centre"}) == "departments"

    def test_college_amenity(self):
        assert _poi_type({"amenity": "college"}) == "departments"

    def test_school_amenity(self):
        assert _poi_type({"amenity": "school"}) == "departments"

    # ── Shopping ──
    def test_shop(self):
        assert _poi_type({"shop": "convenience"}) == "shop"

    def test_shop_empty_other_tags(self):
        assert _poi_type({"shop": "bakery"}) == "shop"

    # ── Tourism ──
    def test_tourism(self):
        assert _poi_type({"tourism": "artwork"}) == "poi"

    # ── University amenity ──
    def test_university_amenity(self):
        assert _poi_type({"amenity": "university"}) == "poi"

    # ── Default ──
    def test_empty_tags_returns_poi(self):
        assert _poi_type({}) == "poi"

    def test_unknown_amenity_returns_poi(self):
        assert _poi_type({"amenity": "something_unknown"}) == "poi"

    def test_name_param_accepted(self):
        # name param doesn't affect logic currently, but should not raise
        assert _poi_type({"amenity": "cafe"}, name="Coffee Place") == "cafe"


class TestProcessWays:
    """Tests for process_ways with mock OSM data."""

    def _make_osm_data(self, nodes, ways):
        elements = []
        for node_id, lon, lat in nodes:
            elements.append({"type": "node", "id": node_id, "lon": lon, "lat": lat})
        for way_id, way_nodes in ways:
            elements.append({"type": "way", "id": way_id, "nodes": way_nodes})
        return {"elements": elements}

    def test_empty_data_returns_empty(self):
        nodes_map, edges = process_ways({"elements": []})
        assert nodes_map == {}
        assert edges == []

    def test_nodes_only_no_edges(self):
        data = self._make_osm_data([(1, -8.66, 40.63), (2, -8.659, 40.63)], [])
        nodes_map, edges = process_ways(data)
        assert len(nodes_map) == 2
        assert edges == []

    def test_way_creates_bidirectional_edges(self):
        data = self._make_osm_data(
            [(1, -8.660, 40.630), (2, -8.659, 40.630)],
            [(100, [1, 2])]
        )
        nodes_map, edges = process_ways(data)
        # One segment → 2 directed edges (forward + reverse)
        assert len(edges) == 2
        from_ids = {e["from_id"] for e in edges}
        assert "1" in from_ids
        assert "2" in from_ids

    def test_node_attributes(self):
        data = self._make_osm_data([(42, -8.660, 40.630)], [])
        nodes_map, _ = process_ways(data)
        node = nodes_map["42"]
        assert node["id"] == "42"
        assert node["x"] == -8.660
        assert node["y"] == 40.630
        assert node["level"] == 0
        assert node["type"] == "normal"

    def test_edge_weight_is_positive(self):
        data = self._make_osm_data(
            [(1, -8.660, 40.630), (2, -8.659, 40.630)],
            [(100, [1, 2])]
        )
        _, edges = process_ways(data)
        for edge in edges:
            assert edge["weight"] > 0

    def test_way_with_unknown_node_skipped(self):
        # Way references node 999 which doesn't exist
        data = self._make_osm_data(
            [(1, -8.660, 40.630)],
            [(100, [1, 999])]
        )
        _, edges = process_ways(data)
        assert edges == []

    def test_multi_segment_way(self):
        data = self._make_osm_data(
            [(1, -8.660, 40.630), (2, -8.659, 40.630), (3, -8.658, 40.630)],
            [(100, [1, 2, 3])]
        )
        _, edges = process_ways(data)
        # 2 segments × 2 directions = 4 edges
        assert len(edges) == 4

    def test_edge_ids_are_unique(self):
        data = self._make_osm_data(
            [(1, -8.660, 40.630), (2, -8.659, 40.630), (3, -8.658, 40.630)],
            [(100, [1, 2, 3])]
        )
        _, edges = process_ways(data)
        ids = [e["id"] for e in edges]
        assert len(ids) == len(set(ids))


class TestProcessPois:
    """Tests for process_pois with mock data."""

    def _make_nodes_map(self):
        return {
            "1": {"id": "1", "x": -8.660, "y": 40.630, "type": "normal"},
            "2": {"id": "2", "x": -8.659, "y": 40.631, "type": "normal"},
        }

    def _make_poi_element(self, osm_id, lon, lat, tags):
        return {"type": "node", "id": osm_id, "lon": lon, "lat": lat, "tags": tags}

    def test_poi_with_no_name_skipped(self):
        nodes_map = self._make_nodes_map()
        edges = []
        poi_data = {"elements": [
            self._make_poi_element(100, -8.660, 40.630, {"amenity": "bench"})
        ]}
        process_pois(poi_data, nodes_map, edges)
        # bench has no name and is irrelevant anyway
        assert "POI-100" not in nodes_map

    def test_poi_added_when_close_enough(self):
        nodes_map = self._make_nodes_map()
        edges = []
        poi_data = {"elements": [
            self._make_poi_element(200, -8.660, 40.630, {"amenity": "cafe", "name": "Campus Café"})
        ]}
        process_pois(poi_data, nodes_map, edges)
        assert "POI-200" in nodes_map
        assert nodes_map["POI-200"]["type"] == "cafe"
        assert nodes_map["POI-200"]["name"] == "Campus Café"

    def test_poi_too_far_skipped(self):
        nodes_map = self._make_nodes_map()
        edges = []
        poi_data = {"elements": [
            # Very far away from nodes
            self._make_poi_element(300, 0.0, 0.0, {"amenity": "restaurant", "name": "Far Away"})
        ]}
        process_pois(poi_data, nodes_map, edges)
        assert "POI-300" not in nodes_map

    def test_poi_creates_bidirectional_edges(self):
        nodes_map = self._make_nodes_map()
        edges = []
        poi_data = {"elements": [
            self._make_poi_element(400, -8.660, 40.630, {"amenity": "toilets", "name": "WC"})
        ]}
        process_pois(poi_data, nodes_map, edges)
        assert len(edges) == 2  # TO and FROM edges

    def test_poi_duplicate_skipped(self):
        nodes_map = self._make_nodes_map()
        nodes_map["POI-500"] = {"id": "POI-500", "x": -8.660, "y": 40.630, "type": "cafe"}
        edges = []
        poi_data = {"elements": [
            self._make_poi_element(500, -8.660, 40.630, {"amenity": "cafe", "name": "Café"})
        ]}
        original_len = len(nodes_map)
        process_pois(poi_data, nodes_map, edges)
        assert len(nodes_map) == original_len  # no duplicate added

    def test_way_center_poi_processed(self):
        nodes_map = self._make_nodes_map()
        edges = []
        poi_data = {"elements": [
            {
                "type": "way",
                "id": 600,
                "tags": {"building": "university", "name": "Dep. Informatica"},
                "center": {"lon": -8.660, "lat": 40.630},
            }
        ]}
        process_pois(poi_data, nodes_map, edges)
        assert "POI-600" in nodes_map

    def test_way_without_center_skipped(self):
        nodes_map = self._make_nodes_map()
        edges = []
        poi_data = {"elements": [
            {
                "type": "way",
                "id": 700,
                "tags": {"building": "university", "name": "Some Building"},
                # No "center" key
            }
        ]}
        process_pois(poi_data, nodes_map, edges)
        assert "POI-700" not in nodes_map

    def test_irrelevant_poi_type_not_added(self):
        nodes_map = self._make_nodes_map()
        edges = []
        # waste_basket with name — _poi_type returns None so it's skipped
        poi_data = {"elements": [
            self._make_poi_element(800, -8.660, 40.630, {"amenity": "waste_basket", "name": "Bin"})
        ]}
        process_pois(poi_data, nodes_map, edges)
        assert "POI-800" not in nodes_map

    def test_amenity_used_as_fallback_name(self):
        nodes_map = self._make_nodes_map()
        edges = []
        # ATM with no name → amenity tag used as name
        poi_data = {"elements": [
            self._make_poi_element(900, -8.660, 40.630, {"amenity": "atm"})
        ]}
        process_pois(poi_data, nodes_map, edges)
        assert "POI-900" in nodes_map
        assert nodes_map["POI-900"]["name"] == "Atm"

    def test_custom_connect_radius(self):
        nodes_map = self._make_nodes_map()
        edges = []
        poi_data = {"elements": [
            # POI is ~200m from nearest node
            self._make_poi_element(1000, -8.658, 40.630, {"amenity": "library", "name": "Library"})
        ]}
        # With default 100m radius, might be skipped; with 1000m it should be added
        process_pois(poi_data, nodes_map, edges, connect_radius_m=1000.0)
        assert "POI-1000" in nodes_map
