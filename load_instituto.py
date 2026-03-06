#!/usr/bin/env python3
"""
Load Instituto navigation graph into Map-Service database.

Reads the JSON output from svg_to_graph.py and inserts nodes, edges,
and tiles into the database.

Usage:
    python load_instituto.py output/PLANTA1(3)_graph.json
    python load_instituto.py output/PLANTA1(3)_graph.json --clear  # Clear DB first
"""

import argparse
import json
import math
import os
import sys
import uuid

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import engine, SessionLocal, init_db
from models import Node, Edge, Tile, Base


def clear_database(session):
    """Clear all existing data from the database."""
    print("🗑️  Clearing existing data...")
    session.query(Tile).delete()
    session.query(Edge).delete()
    session.query(Node).delete()
    session.commit()
    print("   Done.")


def load_graph(session, graph_data: dict):
    """Load nodes and edges from parsed graph JSON into the database."""
    
    metadata = graph_data.get("metadata", {})
    nodes_data = graph_data.get("nodes", [])
    edges_data = graph_data.get("edges", [])
    
    print(f"\n📥 Loading graph: {metadata.get('name', 'Unknown')}")
    print(f"   Source: {metadata.get('source', 'Unknown')}")
    print(f"   Nodes: {len(nodes_data)}, Edges: {len(edges_data)}")
    
    # Load nodes
    print("\n📍 Loading nodes...")
    node_count = 0
    for nd in nodes_data:
        node = Node(
            id=nd["id"],
            name=nd.get("name"),
            x=nd["x"],
            y=nd["y"],
            level=nd.get("level", 0),
            type=nd.get("type", "normal"),
            description=nd.get("description"),
            num_servers=nd.get("num_servers"),
            service_rate=nd.get("service_rate"),
        )
        session.add(node)
        node_count += 1
    
    session.flush()  # Flush to ensure foreign keys work for edges
    print(f"   ✅ Loaded {node_count} nodes")
    
    # Load edges
    print("🔗 Loading edges...")
    edge_count = 0
    for ed in edges_data:
        edge = Edge(
            id=ed["id"],
            from_id=ed["from_id"],
            to_id=ed["to_id"],
            weight=ed["weight"],
            accessible=ed.get("accessible", True),
        )
        session.add(edge)
        edge_count += 1
    
    session.flush()
    print(f"   ✅ Loaded {edge_count} edges")
    
    # Generate tiles
    svg_width = metadata.get("svg_width", 460)
    svg_height = metadata.get("svg_height", 465)
    generate_tiles(session, nodes_data, svg_width, svg_height)
    
    session.commit()
    print("\n✅ Database loaded successfully!")


def generate_tiles(session, nodes_data: list, svg_width: float, svg_height: float,
                   grid_size: int = 10):
    """
    Generate grid tiles for the floor plan.
    
    Each tile is a rectangular area on the map. Tiles that contain
    nodes are marked with the node_id. POI tiles get the poi_id.
    """
    print(f"🗺️  Generating {grid_size}x{grid_size} tile grid...")
    
    tile_width = svg_width / grid_size
    tile_height = svg_height / grid_size
    
    # Build node lookup
    nodes_by_pos = []
    for nd in nodes_data:
        nodes_by_pos.append({
            "id": nd["id"],
            "x": nd["x"],
            "y": nd["y"],
            "type": nd.get("type", "normal"),
        })
    
    tile_count = 0
    for gx in range(grid_size):
        for gy in range(grid_size):
            min_x = gx * tile_width
            max_x = (gx + 1) * tile_width
            min_y = gy * tile_height
            max_y = (gy + 1) * tile_height
            
            tile_id = f"tile_{gx}_{gy}_L0"
            
            # Find nodes in this tile
            node_in_tile = None
            poi_in_tile = None
            for nd in nodes_by_pos:
                if min_x <= nd["x"] < max_x and min_y <= nd["y"] < max_y:
                    if nd["id"].startswith("POI-"):
                        poi_in_tile = nd["id"]
                    elif node_in_tile is None:
                        node_in_tile = nd["id"]
            
            tile = Tile(
                id=tile_id,
                grid_x=gx,
                grid_y=gy,
                level=0,
                min_x=round(min_x, 2),
                max_x=round(max_x, 2),
                min_y=round(min_y, 2),
                max_y=round(max_y, 2),
                walkable=True,
                node_id=node_in_tile,
                poi_id=poi_in_tile,
            )
            session.add(tile)
            tile_count += 1
    
    session.flush()
    print(f"   ✅ Generated {tile_count} tiles")


def main():
    parser = argparse.ArgumentParser(
        description='Load Instituto graph into Map-Service database'
    )
    parser.add_argument('graph_json', help='Path to graph JSON file')
    parser.add_argument('--clear', action='store_true',
                        help='Clear existing data before loading')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.graph_json):
        print(f"❌ File not found: {args.graph_json}")
        sys.exit(1)
    
    # Read graph data
    with open(args.graph_json, 'r', encoding='utf-8') as f:
        graph_data = json.load(f)
    
    # Initialize database
    print("🔧 Initializing database...")
    init_db()
    
    session = SessionLocal()
    try:
        if args.clear:
            clear_database(session)
        
        load_graph(session, graph_data)
        
    except Exception as e:
        session.rollback()
        print(f"\n❌ Error: {e}")
        raise
    finally:
        session.close()


if __name__ == '__main__':
    main()
