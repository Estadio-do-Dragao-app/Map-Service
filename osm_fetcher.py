import json
import math
import os
import urllib.request
import urllib.parse

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Bounding box for UA Santiago Campus
QUERY = """
[out:json];
(
  way["highway"~"footway|pedestrian|path|steps"](40.628, -8.662, 40.635, -8.654);
);
out body;
>;
out skel qt;
"""

def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    r = 6371000
    return c * r

def fetch_osm_data():
    data = urllib.parse.urlencode({"data": QUERY}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

def process_osm_to_graph(osm_data):
    nodes_map = {}
    edges = []
    
    # Extract nodes
    for element in osm_data['elements']:
        if element['type'] == 'node':
            nodes_map[str(element['id'])] = {
                "id": str(element['id']),
                "x": element['lon'],
                "y": element['lat'],
                "level": 0,
                "type": "normal",
                "name": f"Node_{element['id']}"
            }
            
    # Extract ways and create edges
    edge_id_counter = 1
    for element in osm_data['elements']:
        if element['type'] == 'way':
            nodes_in_way = element['nodes']
            for i in range(len(nodes_in_way) - 1):
                u_id = str(nodes_in_way[i])
                v_id = str(nodes_in_way[i+1])
                
                if u_id in nodes_map and v_id in nodes_map:
                    n1 = nodes_map[u_id]
                    n2 = nodes_map[v_id]
                    dist = haversine(n1['x'], n1['y'], n2['x'], n2['y'])
                    
                    # Add bi-directional edges
                    edges.append({
                        "id": f"EDGE-OSM-{edge_id_counter}",
                        "from_id": u_id,
                        "to_id": v_id,
                        "weight": round(max(0.1, dist), 2),
                        "accessible": True
                    })
                    edge_id_counter += 1
                    edges.append({
                        "id": f"EDGE-OSM-{edge_id_counter}",
                        "from_id": v_id,
                        "to_id": u_id,
                        "weight": round(max(0.1, dist), 2),
                        "accessible": True
                    })
                    edge_id_counter += 1

    # Add POIs (Manually snapped to nearest OSM node or just added)
    pois = [
        {"id": "POI-reitoria", "name": "Reitoria", "x": -8.65622, "y": 40.63032, "type": "poi"},
        {"id": "POI-biblioteca", "name": "Biblioteca Central", "x": -8.65789, "y": 40.63152, "type": "poi"},
        {"id": "POI-deti", "name": "DETI (Informática)", "x": -8.65934, "y": 40.63321, "type": "poi"},
        {"id": "POI-fisica", "name": "Física", "x": -8.65856, "y": 40.63278, "type": "poi"},
        {"id": "POI-cantina", "name": "Cantina Santiago", "x": -8.65825, "y": 40.62972, "type": "food"},
    ]
    
    # Connect POIs to nearest OSM node
    for poi in pois:
        nearest_node = None
        min_dist = float('inf')
        for node_id, node in nodes_map.items():
            d = haversine(poi['x'], poi['y'], node['x'], node['y'])
            if d < min_dist:
                min_dist = d
                nearest_node = node_id
        
        if nearest_node and min_dist < 50: # Only connect if within 50m
            poi_id = poi['id']
            nodes_map[poi_id] = {
                "id": poi_id,
                "x": poi['x'],
                "y": poi['y'],
                "level": 0,
                "type": poi['type'],
                "name": poi['name']
            }
            # Add edge to the nearest network node
            edges.append({
                "id": f"EDGE-POI-{poi_id}",
                "from_id": poi_id,
                "to_id": nearest_node,
                "weight": round(max(0.1, min_dist), 2),
                "accessible": True
            })
            edges.append({
                "id": f"EDGE-POI-{poi_id}-REV",
                "from_id": nearest_node,
                "to_id": poi_id,
                "weight": round(max(0.1, min_dist), 2),
                "accessible": True
            })

    return list(nodes_map.values()), edges

def main():
    try:
        print("Fetching OSM data...")
        osm_data = fetch_osm_data()
        print(f"Fetched {len(osm_data['elements'])} elements.")
        
        nodes, edges = process_osm_to_graph(osm_data)
        print(f"Processed into {len(nodes)} nodes and {len(edges)} edges.")
        
        graph = {
            "metadata": {
                "name": "Universidade de Aveiro (OSM Smooth)",
                "source": "openstreetmap",
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "levels": [0]
            },
            "nodes": nodes,
            "edges": edges
        }
        
        if not os.path.exists("output"):
            os.makedirs("output")
            
        with open("output/ua_graph.json", "w") as f:
            json.dump(graph, f, indent=2)
            
        print("Successfully saved to output/ua_graph.json")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
