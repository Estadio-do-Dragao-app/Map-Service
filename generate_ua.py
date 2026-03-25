import json
import math
import os
import urllib.request
import urllib.parse

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# FIX 1: Split into two separate queries:
#   - One for walkable ways (paths/footways)
#   - One for POIs (amenity, building named nodes/ways)
# The original single query only fetched highway ways, completely missing POI nodes.

WAYS_QUERY = """
[out:json];
(
  way["highway"~"footway|pedestrian|path|steps"](40.628, -8.662, 40.635, -8.654);
);
out body;
>;
out skel qt;
"""

# FIX 2: Fetch POIs from OSM directly instead of hardcoding coordinates.
# Targets named amenities and buildings within the campus bounding box.
POIS_QUERY = """
[out:json];
(
  node["amenity"](40.628, -8.662, 40.635, -8.654);
  node["building"](40.628, -8.662, 40.635, -8.654);
  node["name"](40.628, -8.662, 40.635, -8.654);
  node["shop"](40.628, -8.662, 40.635, -8.654);
  node["tourism"](40.628, -8.662, 40.635, -8.654);
  way["amenity"](40.628, -8.662, 40.635, -8.654);
  way["building"]["name"](40.628, -8.662, 40.635, -8.654);
  way["shop"]["name"](40.628, -8.662, 40.635, -8.654);
);
out center;
"""


def haversine(lon1, lat1, lon2, lat2):
    """Returns distance in metres between two (lon, lat) points."""
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def overpass_fetch(query: str) -> dict:
    """POST a query to the Overpass API and return parsed JSON."""
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def process_ways(osm_data: dict) -> tuple[dict, list]:
    """Build nodes_map and edges list from OSM way data."""
    nodes_map: dict[str, dict] = {}
    edges: list[dict] = []

    for el in osm_data["elements"]:
        if el["type"] == "node":
            nodes_map[str(el["id"])] = {
                "id": str(el["id"]),
                "x": el["lon"],
                "y": el["lat"],
                "level": 0,
                "type": "normal",
                "name": f"Node_{el['id']}",
            }

    edge_counter = 1
    for el in osm_data["elements"]:
        if el["type"] == "way":
            way_nodes = el["nodes"]
            for i in range(len(way_nodes) - 1):
                u_id = str(way_nodes[i])
                v_id = str(way_nodes[i + 1])
                if u_id not in nodes_map or v_id not in nodes_map:
                    continue
                n1, n2 = nodes_map[u_id], nodes_map[v_id]
                dist = haversine(n1["x"], n1["y"], n2["x"], n2["y"])
                for src, dst in [(u_id, v_id), (v_id, u_id)]:
                    edges.append({
                        "id": f"EDGE-OSM-{edge_counter}",
                        "from_id": src,
                        "to_id": dst,
                        "weight": round(max(0.1, dist), 2),
                        "accessible": True,
                    })
                    edge_counter += 1

    return nodes_map, edges


def _poi_type(tags: dict, name: str = "") -> str:
    """Map OSM tags to a simple internal POI type.
    Returns None for POIs that should be skipped (irrelevant clutter)."""
    amenity = tags.get("amenity", "")
    building = tags.get("building", "")
    shop = tags.get("shop", "")
    tourism = tags.get("tourism", "")

    # ── Skip irrelevant amenities (map clutter) ──
    if amenity in (
        "waste_basket", "waste_disposal", "recycling",
        "vending_machine", "bench", "telephone",
        "waiting_room", "fountain", "drinking_water",
    ):
        return None  # Will be skipped in process_pois

    # ── ATMs ──
    if amenity == "atm":
        return "atm"

    # ── Parking (all types) ──
    if amenity in ("parking", "bicycle_parking", "motorcycle_parking", "parking_entrance"):
        return "parking"

    # ── Reception desks → information ──
    if amenity == "reception_desk":
        return "information"

    # ── Food & drink (BEFORE building check — e.g. Cantina has both fast_food + building=university) ──
    if amenity in ("restaurant", "fast_food", "food_court", "canteen"):
        return "food"
    if amenity == "cafe":
        return "cafe"
    if amenity in ("bar", "pub"):
        return "bar"

    # ── Services ──
    if amenity in ("toilets",):
        return "wc"
    if amenity in ("library",):
        return "library"
    if amenity in ("pharmacy", "hospital", "clinic"):
        return "first_aid"

    # ── Departamentos & campus buildings ──
    if building in ("university", "college", "school", "sports_centre"):
        return "departments"
    if amenity in ("college", "school"):
        return "departments"

    # ── Dormitories → skip (not navigable POIs) ──
    if building == "dormitory":
        return None

    # ── Shopping ──
    if shop:
        return "shop"

    # ── Tourism ──
    if tourism:
        return "poi"

    # ── University campus as generic POI ──
    if amenity in ("university",):
        return "poi"

    # ── Default: keep as generic poi ──
    return "poi"


def process_pois(poi_data: dict, nodes_map: dict, edges: list, connect_radius_m: float = 100.0):
    """
    FIX 3: Extract POIs from OSM response (both node and way center),
    add them to nodes_map, and connect each to its nearest walkable node.
    The connect_radius_m is raised to 100 m (was 50 m) to avoid silent drops
    for POIs that are slightly off the pedestrian network.
    """
    added = 0
    skipped_no_name = 0
    skipped_too_far = 0

    for el in poi_data["elements"]:
        tags = el.get("tags", {})
        # FIX: Fallback to short_name, operator, brand, or amenity tag for unnamed POIs (e.g. ATMs)
        name = (
            tags.get("name")
            or tags.get("alt_name")
            or tags.get("short_name")
            or tags.get("operator")
            or tags.get("brand")
        )
        if not name:
            # Last resort: use amenity/shop tag as name (e.g. "atm" → "ATM")
            amenity = tags.get("amenity", "")
            if amenity:
                name = amenity.replace("_", " ").title()

        if not name:
            skipped_no_name += 1
            continue

        # FIX 4: For ways, OSM returns a "center" lat/lon when using "out center;"
        if el["type"] == "node":
            lon, lat = el["lon"], el["lat"]
        elif el["type"] == "way" and "center" in el:
            lon, lat = el["center"]["lon"], el["center"]["lat"]
        else:
            continue

        poi_id = f"POI-{el['id']}"

        # Skip if already added (duplicate OSM id)
        if poi_id in nodes_map:
            continue

        # Find nearest walkable node
        nearest_id = None
        min_dist = float("inf")
        for nid, node in nodes_map.items():
            if node["type"] != "normal":
                continue  # skip other POIs during search
            d = haversine(lon, lat, node["x"], node["y"])
            if d < min_dist:
                min_dist = d
                nearest_id = nid

        if nearest_id is None or min_dist > connect_radius_m:
            skipped_too_far += 1
            print(f"  [SKIP] '{name}' — nearest node {min_dist:.0f}m away (limit {connect_radius_m}m)")
            continue

        poi_type = _poi_type(tags, name=name)
        if poi_type is None:
            # Irrelevant POI (waste baskets, benches, etc.) — skip
            continue
        nodes_map[poi_id] = {
            "id": poi_id,
            "x": lon,
            "y": lat,
            "level": 0,
            "type": poi_type,
            "name": name,
            "description": tags.get("description", name),
            "osm_tags": {k: v for k, v in tags.items() if k in ("amenity", "building", "shop")},
        }

        for src, dst in [(poi_id, nearest_id), (nearest_id, poi_id)]:
            edges.append({
                "id": f"EDGE-{poi_id}-{'TO' if src == poi_id else 'FROM'}",
                "from_id": src,
                "to_id": dst,
                "weight": round(max(0.1, min_dist), 2),
                "accessible": True,
            })

        added += 1
        print(f"  [POI] '{name}' ({poi_type}) connected at {min_dist:.1f}m")

    print(f"\nPOI summary: {added} added, {skipped_no_name} unnamed skipped, {skipped_too_far} too far skipped.")


def main():
    print("=== UA Campus Graph Generator ===\n")

    try:
        print("1/3  Fetching walkable ways from OSM...")
        ways_data = overpass_fetch(WAYS_QUERY)
        print(f"     Got {len(ways_data['elements'])} elements.")

        print("2/3  Fetching POIs from OSM...")
        poi_data = overpass_fetch(POIS_QUERY)
        print(f"     Got {len(poi_data['elements'])} POI elements.")

        print("3/3  Building graph...")
        nodes_map, edges = process_ways(ways_data)
        print(f"     Walkable network: {len(nodes_map)} nodes, {len(edges)} edges.")

        process_pois(poi_data, nodes_map, edges)

        nodes = list(nodes_map.values())
        graph = {
            "metadata": {
                "name": "Universidade de Aveiro — Santiago Campus (OSM)",
                "source": "openstreetmap",
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "levels": [0],
            },
            "nodes": nodes,
            "edges": edges,
        }

        os.makedirs("output", exist_ok=True)
        out_path = "output/ua_graph.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(graph, f, indent=2, ensure_ascii=False)

        print(f"\nSaved {out_path}  ({len(nodes)} nodes, {len(edges)} edges)")

    except Exception as e:
        print(f"\nFatal error: {e}")
        raise


if __name__ == "__main__":
    main()