from sqlalchemy.orm import Session
from database import SessionLocal, init_db
from models import Node, Edge, Closure, Tile, POI, Seat, Gate


def load_sample_data():
    """Load sample stadium data with FULL BIDIRECTIONAL connectivity."""
    
    # Initialize database
    init_db()
    db: Session = SessionLocal()
    
    try:
        # ==================== NODES ====================
        nodes_data = [
            # Entrance/Gate area nodes
            {"id": "N1", "x": 10.0, "y": 10.0, "level": 0, "type": "normal"},
            {"id": "N2", "x": 20.0, "y": 10.0, "level": 0, "type": "normal"},
            {"id": "N3", "x": 30.0, "y": 10.0, "level": 0, "type": "normal"},
            {"id": "N4", "x": 40.0, "y": 10.0, "level": 0, "type": "normal"},
            
            # Corridor nodes (level 0)
            {"id": "N5", "x": 50.0, "y": 10.0, "level": 0, "type": "normal"},
            {"id": "N6", "x": 60.0, "y": 10.0, "level": 0, "type": "normal"},
            {"id": "N7", "x": 70.0, "y": 10.0, "level": 0, "type": "normal"},
            {"id": "N8", "x": 80.0, "y": 10.0, "level": 0, "type": "normal"},
            
            # Vertical corridor nodes
            {"id": "N9", "x": 50.0, "y": 20.0, "level": 0, "type": "normal"},
            {"id": "N10", "x": 50.0, "y": 30.0, "level": 0, "type": "normal"},
            {"id": "N11", "x": 50.0, "y": 40.0, "level": 0, "type": "normal"},
            
            # Seating area access nodes
            {"id": "N12", "x": 60.0, "y": 20.0, "level": 0, "type": "normal"},
            {"id": "N13", "x": 70.0, "y": 20.0, "level": 0, "type": "normal"},
            {"id": "N14", "x": 80.0, "y": 20.0, "level": 0, "type": "normal"},
            
            # Stairs access nodes
            {"id": "N15", "x": 40.0, "y": 20.0, "level": 0, "type": "stairs"},
            {"id": "N16", "x": 40.0, "y": 20.0, "level": 1, "type": "stairs"},
            
            # Level 1 nodes
            {"id": "N17", "x": 50.0, "y": 20.0, "level": 1, "type": "normal"},
            {"id": "N18", "x": 60.0, "y": 20.0, "level": 1, "type": "normal"},
            {"id": "N19", "x": 70.0, "y": 20.0, "level": 1, "type": "normal"},
            
            # Exit nodes
            {"id": "N20", "x": 90.0, "y": 10.0, "level": 0, "type": "normal"},
            {"id": "N21", "x": 100.0, "y": 10.0, "level": 0, "type": "normal"},
        ]
        
        for node_data in nodes_data:
            node = Node(**node_data)
            db.add(node)
        
        print(f"✓ Loaded {len(nodes_data)} nodes")
        
        # ==================== EDGES (FULLY BIDIRECTIONAL) ====================
        edges_data = [
            # Main corridor (level 0) - BIDIRECTIONAL
            {"id": "E1", "from_id": "N1", "to_id": "N2", "weight": 10.0},
            {"id": "E2", "from_id": "N2", "to_id": "N1", "weight": 10.0},
            {"id": "E3", "from_id": "N2", "to_id": "N3", "weight": 10.0},
            {"id": "E4", "from_id": "N3", "to_id": "N2", "weight": 10.0},
            {"id": "E5", "from_id": "N3", "to_id": "N4", "weight": 10.0},
            {"id": "E6", "from_id": "N4", "to_id": "N3", "weight": 10.0},
            {"id": "E7", "from_id": "N4", "to_id": "N5", "weight": 10.0},
            {"id": "E8", "from_id": "N5", "to_id": "N4", "weight": 10.0},
            {"id": "E9", "from_id": "N5", "to_id": "N6", "weight": 10.0},
            {"id": "E10", "from_id": "N6", "to_id": "N5", "weight": 10.0},
            {"id": "E11", "from_id": "N6", "to_id": "N7", "weight": 10.0},
            {"id": "E12", "from_id": "N7", "to_id": "N6", "weight": 10.0},
            {"id": "E13", "from_id": "N7", "to_id": "N8", "weight": 10.0},
            {"id": "E14", "from_id": "N8", "to_id": "N7", "weight": 10.0},
            {"id": "E15", "from_id": "N8", "to_id": "N20", "weight": 10.0},
            {"id": "E16", "from_id": "N20", "to_id": "N8", "weight": 10.0},
            {"id": "E17", "from_id": "N20", "to_id": "N21", "weight": 10.0},
            {"id": "E18", "from_id": "N21", "to_id": "N20", "weight": 10.0},
            
            # Vertical connections - BIDIRECTIONAL
            {"id": "E19", "from_id": "N5", "to_id": "N9", "weight": 10.0},
            {"id": "E20", "from_id": "N9", "to_id": "N5", "weight": 10.0},
            {"id": "E21", "from_id": "N9", "to_id": "N10", "weight": 10.0},
            {"id": "E22", "from_id": "N10", "to_id": "N9", "weight": 10.0},
            {"id": "E23", "from_id": "N10", "to_id": "N11", "weight": 10.0},
            {"id": "E24", "from_id": "N11", "to_id": "N10", "weight": 10.0},
            
            # Horizontal branches - BIDIRECTIONAL
            {"id": "E25", "from_id": "N6", "to_id": "N12", "weight": 10.0},
            {"id": "E26", "from_id": "N12", "to_id": "N6", "weight": 10.0},
            {"id": "E27", "from_id": "N12", "to_id": "N13", "weight": 10.0},
            {"id": "E28", "from_id": "N13", "to_id": "N12", "weight": 10.0},
            {"id": "E29", "from_id": "N7", "to_id": "N13", "weight": 10.0},
            {"id": "E30", "from_id": "N13", "to_id": "N7", "weight": 10.0},
            {"id": "E31", "from_id": "N13", "to_id": "N14", "weight": 10.0},
            {"id": "E32", "from_id": "N14", "to_id": "N13", "weight": 10.0},
            
            # Stairs connection (between levels) - BIDIRECTIONAL
            {"id": "E33", "from_id": "N4", "to_id": "N15", "weight": 10.0},
            {"id": "E34", "from_id": "N15", "to_id": "N4", "weight": 10.0},
            {"id": "E35", "from_id": "N15", "to_id": "N16", "weight": 5.0},
            {"id": "E36", "from_id": "N16", "to_id": "N15", "weight": 5.0},
            
            # Level 1 corridor - BIDIRECTIONAL
            {"id": "E37", "from_id": "N16", "to_id": "N17", "weight": 10.0},
            {"id": "E38", "from_id": "N17", "to_id": "N16", "weight": 10.0},
            {"id": "E39", "from_id": "N17", "to_id": "N18", "weight": 10.0},
            {"id": "E40", "from_id": "N18", "to_id": "N17", "weight": 10.0},
            {"id": "E41", "from_id": "N18", "to_id": "N19", "weight": 10.0},
            {"id": "E42", "from_id": "N19", "to_id": "N18", "weight": 10.0},
        ]
        
        for edge_data in edges_data:
            edge = Edge(**edge_data)
            db.add(edge)
        
        print(f"✓ Loaded {len(edges_data)} edges (FULLY BIDIRECTIONAL)")
        
        # ==================== GATES ====================
        gates_data = [
            {"id": "Gate-1", "gate_number": "1", "x": 5.0, "y": 10.0, "level": 0},
            {"id": "Gate-2", "gate_number": "2", "x": 15.0, "y": 5.0, "level": 0},
            {"id": "Gate-3", "gate_number": "3", "x": 100.0, "y": 15.0, "level": 0},
            {"id": "Gate-14", "gate_number": "14", "x": 90.0, "y": 5.0, "level": 0},
        ]
        
        for gate_data in gates_data:
            gate = Gate(**gate_data)
            db.add(gate)
        
        print(f"✓ Loaded {len(gates_data)} gates")
        
        # ==================== POIs ====================
        pois_data = [
            # Restrooms
            {"id": "Restroom-A3", "name": "Restroom A3", "category": "restroom", 
             "x": 45.0, "y": 15.0, "level": 0},
            {"id": "Restroom-B1", "name": "Restroom B1", "category": "restroom", 
             "x": 75.0, "y": 15.0, "level": 0},
            {"id": "Restroom-C2", "name": "Restroom C2", "category": "restroom", 
             "x": 55.0, "y": 25.0, "level": 1},
            
            # Food & Beverage
            {"id": "Store-1", "name": "Concession Stand 1", "category": "food", 
             "x": 35.0, "y": 12.0, "level": 0},
            {"id": "Store-2", "name": "Concession Stand 2", "category": "food", 
             "x": 65.0, "y": 12.0, "level": 0},
            {"id": "Bar-1", "name": "Stadium Bar 1", "category": "bar", 
             "x": 85.0, "y": 15.0, "level": 0},
            
            # Emergency
            {"id": "Exit-A", "name": "Emergency Exit A", "category": "emergency_exit", 
             "x": 25.0, "y": 5.0, "level": 0},
            {"id": "Exit-B", "name": "Emergency Exit B", "category": "emergency_exit", 
             "x": 95.0, "y": 5.0, "level": 0},
            {"id": "FirstAid-1", "name": "First Aid Station", "category": "first_aid", 
             "x": 55.0, "y": 35.0, "level": 0},
            
            # Services
            {"id": "Info-Desk", "name": "Information Desk", "category": "information", 
             "x": 30.0, "y": 8.0, "level": 0},
            {"id": "Merchandise-1", "name": "Team Store", "category": "merchandise", 
             "x": 70.0, "y": 8.0, "level": 0},
        ]
        
        for poi_data in pois_data:
            poi = POI(**poi_data)
            db.add(poi)
        
        print(f"✓ Loaded {len(pois_data)} POIs")
        
        # ==================== SEATS ====================
        seats_data = []
        
        # Block A - Level 0
        for row in range(1, 11):
            for num in range(1, 21):
                seat_id = f"Seat-A{row}-{num}"
                seats_data.append({
                    "id": seat_id,
                    "block": "A",
                    "row": row,
                    "number": num,
                    "x": 60.0 + (num * 0.5),
                    "y": 25.0 + (row * 1.0),
                    "level": 0
                })
        
        # Block B - Level 0
        for row in range(1, 11):
            for num in range(1, 21):
                seat_id = f"Seat-B{row}-{num}"
                seats_data.append({
                    "id": seat_id,
                    "block": "B",
                    "row": row,
                    "number": num,
                    "x": 75.0 + (num * 0.5),
                    "y": 25.0 + (row * 1.0),
                    "level": 0
                })
        
        # Block C - Level 1
        for row in range(1, 8):
            for num in range(1, 16):
                seat_id = f"Seat-C{row}-{num}"
                seats_data.append({
                    "id": seat_id,
                    "block": "C",
                    "row": row,
                    "number": num,
                    "x": 60.0 + (num * 0.5),
                    "y": 25.0 + (row * 1.0),
                    "level": 1
                })
        
        for seat_data in seats_data:
            seat = Seat(**seat_data)
            db.add(seat)
        
        print(f"✓ Loaded {len(seats_data)} seats")
        
        # ==================== TILES ====================
        tiles_data = []
        
        for grid_x in range(0, 12):
            for grid_y in range(0, 12):
                tile_id = f"C-{grid_x}-{grid_y}"
                walkable = not ((grid_x == 5 and grid_y == 5) or 
                               (grid_x == 8 and grid_y == 8))
                tiles_data.append({
                    "id": tile_id,
                    "grid_x": grid_x,
                    "grid_y": grid_y,
                    "walkable": walkable
                })
        
        for tile_data in tiles_data:
            tile = Tile(**tile_data)
            db.add(tile)
        
        print(f"✓ Loaded {len(tiles_data)} tiles")
        
        # ==================== CLOSURES ====================
        # REMOVIDO closures iniciais para testes
        closures_data = []
        
        for closure_data in closures_data:
            closure = Closure(**closure_data)
            db.add(closure)
        
        print(f"✓ Loaded {len(closures_data)} closures")
        
        # ==================== COMMIT ====================
        db.commit()
        print("\n✅ All stadium data loaded successfully!")
        
        # Print summary
        print("\n📊 Summary:")
        print(f"   Nodes: {len(nodes_data)}")
        print(f"   Edges: {len(edges_data)} (fully bidirectional)")
        print(f"   Gates: {len(gates_data)}")
        print(f"   POIs: {len(pois_data)}")
        print(f"   Seats: {len(seats_data)}")
        print(f"   Tiles: {len(tiles_data)}")
        print(f"   Closures: {len(closures_data)}")
        print("\n✨ Graph is now FULLY CONNECTED!")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error loading data: {str(e)}")
        raise
    finally:
        db.close()


def clear_all_data():
    """Clear all data from the database."""
    db: Session = SessionLocal()
    try:
        db.query(Closure).delete()
        db.query(Edge).delete()
        db.query(Tile).delete()
        db.query(POI).delete()
        db.query(Seat).delete()
        db.query(Gate).delete()
        db.query(Node).delete()
        db.commit()
        print("✓ All data cleared from database")
    except Exception as e:
        db.rollback()
        print(f"❌ Error clearing data: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--clear":
        print("🗑️  Clearing all data...")
        clear_all_data()
        print()
    
    print("📥 Loading stadium data...")
    load_sample_data()
    print("\n✨ Done! You can now start the FastAPI server.")