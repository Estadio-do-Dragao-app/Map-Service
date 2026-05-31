import json
import math
import os
import urllib.request
import urllib.parse

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

WAYS_QUERY = """
[out:json];
(
  way["highway"~"footway|pedestrian|path|steps"](40.628, -8.662, 40.635, -8.654);
);
out body;
>;
out skel qt;
"""

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


def _extract_nodes(elements: list) -> dict:
    nodes_map = {}
    for el in elements:
        if el.get("type") == "node":
            nodes_map[str(el["id"])] = {
                "id": str(el["id"]),
                "x": el["lon"],
                "y": el["lat"],
                "level": 0,
                "type": "normal",
                "name": f"Node_{el['id']}",
            }
    return nodes_map


def _add_edge_pair(edges: list, u_id: str, v_id: str, dist: float, edge_counter: int) -> int:
    weight = round(max(0.1, dist), 2)
    for src, dst in [(u_id, v_id), (v_id, u_id)]:
        edges.append({
            "id": f"EDGE-OSM-{edge_counter}",
            "from_id": src,
            "to_id": dst,
            "weight": weight,
            "accessible": True,
        })
        edge_counter += 1
    return edge_counter


def _extract_edges(elements: list, nodes_map: dict) -> list:
    edges = []
    edge_counter = 1
    for el in elements:
        if el.get("type") == "way":
            way_nodes = el.get("nodes", [])
            for i in range(len(way_nodes) - 1):
                u_id = str(way_nodes[i])
                v_id = str(way_nodes[i + 1])
                if u_id not in nodes_map or v_id not in nodes_map:
                    continue
                n1, n2 = nodes_map[u_id], nodes_map[v_id]
                dist = haversine(n1["x"], n1["y"], n2["x"], n2["y"])
                edge_counter = _add_edge_pair(edges, u_id, v_id, dist, edge_counter)
    return edges


def process_ways(osm_data: dict) -> tuple[dict, list]:
    """Build nodes_map and edges list from OSM way data."""
    nodes_map = _extract_nodes(osm_data.get("elements", []))
    edges = _extract_edges(osm_data.get("elements", []), nodes_map)
    return nodes_map, edges


def _is_ignored_amenity(amenity: str) -> bool:
    return amenity in (
        "waste_basket", "waste_disposal", "recycling",
        "vending_machine", "bench", "telephone",
        "waiting_room", "fountain", "drinking_water",
    )


def _check_direct_mappings(amenity: str, building: str, shop: str, tourism: str) -> str | None:
    if amenity == "atm":
        return "atm"
    if amenity in ("parking", "bicycle_parking", "motorcycle_parking", "parking_entrance"):
        return "parking"
    if amenity == "reception_desk":
        return "information"
    if amenity in ("restaurant", "fast_food", "food_court", "canteen"):
        return "food"
    if amenity == "cafe":
        return "cafe"
    if amenity in ("bar", "pub"):
        return "bar"
    if amenity == "toilets":
        return "wc"
    if amenity == "library":
        return "library"
    if amenity in ("pharmacy", "hospital", "clinic"):
        return "first_aid"
    if building in ("university", "college", "school", "sports_centre") or amenity in ("college", "school"):
        return "departments"
    if shop:
        return "shop"
    if tourism:
        return "poi"
    if amenity == "university":
        return "poi"
    return None


def _poi_type(tags: dict) -> str | None:
    """Map OSM tags to a simple internal POI type.
    Returns None for POIs that should be skipped."""
    amenity = tags.get("amenity", "")
    if _is_ignored_amenity(amenity):
        return None

    building = tags.get("building", "")
    if building == "dormitory":
        return None

    direct_type = _check_direct_mappings(amenity, building, tags.get("shop", ""), tags.get("tourism", ""))
    if direct_type is not None:
        return direct_type

    return "poi"


def _add_poi_to_graph(poi_id: str, name: str, lon: float, lat: float, tags: dict, nodes_map: dict, edges: list, connect_radius_m: float) -> tuple[bool, bool]:
    nearest_id = None
    min_dist = float("inf")
    for nid, node in nodes_map.items():
        if node.get("type") != "normal":
            continue
        d = haversine(lon, lat, node["x"], node["y"])
        if d < min_dist:
            min_dist = d
            nearest_id = nid

    if nearest_id is None or min_dist > connect_radius_m:
        print(f"  [SKIP] '{name}' — nearest node {min_dist:.0f}m away (limit {connect_radius_m}m)")
        return False, True

    poi_type = _poi_type(tags)
    if poi_type is None:
        return False, False

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

    print(f"  [POI] '{name}' ({poi_type}) connected at {min_dist:.1f}m")
    return True, False


def _extract_poi_name(tags: dict) -> str | None:
    name = (
        tags.get("name")
        or tags.get("alt_name")
        or tags.get("short_name")
        or tags.get("operator")
        or tags.get("brand")
    )
    if not name:
        amenity = tags.get("amenity", "")
        if amenity:
            name = amenity.replace("_", " ").title()
    return name


def _extract_poi_coordinates(element: dict) -> tuple[float, float] | None:
    if element.get("type") == "node":
        return element.get("lon"), element.get("lat")
    if element.get("type") == "way" and "center" in element:
        return element["center"].get("lon"), element["center"].get("lat")
    return None


def process_pois(poi_data: dict, nodes_map: dict, edges: list, connect_radius_m: float = 100.0):
    """
    Extract POIs from OSM response (both node and way center),
    add them to nodes_map, and connect each to its nearest walkable node.
    """
    added = 0
    skipped_no_name = 0
    skipped_too_far = 0

    for el in poi_data.get("elements", []):
        tags = el.get("tags", {})
        name = _extract_poi_name(tags)
        if not name:
            skipped_no_name += 1
            continue

        coords = _extract_poi_coordinates(el)
        if not coords:
            continue

        lon, lat = coords
        poi_id = f"POI-{el['id']}"

        if poi_id in nodes_map:
            continue

        added_poi, too_far = _add_poi_to_graph(poi_id, name, lon, lat, tags, nodes_map, edges, connect_radius_m)
        if added_poi:
            added += 1
        elif too_far:
            skipped_too_far += 1

    print(f"\nPOI summary: {added} added, {skipped_no_name} unnamed skipped, {skipped_too_far} too far skipped.")


def main():
    print("=== UA Campus Graph Generator ===\n")

    try:
        print("1/3  Fetching walkable ways from OSM...")
        ways_data = overpass_fetch(WAYS_QUERY)
        print(f"     Got {len(ways_data.get('elements', []))} elements.")

        print("2/3  Fetching POIs from OSM...")
        poi_data = overpass_fetch(POIS_QUERY)
        print(f"     Got {len(poi_data.get('elements', []))} POI elements.")

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