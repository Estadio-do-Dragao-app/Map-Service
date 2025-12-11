from sqlalchemy.orm import Session
from database import SessionLocal, init_db
from grid_name import GridManager
from models import Node, Edge, Closure, Tile, EmergencyRoute
import math


def load_sample_data():
    """
    Load Estádio do Dragão data with realistic structure.
    
    Based on real stadium data:
    - Capacity: 50,033 seats
    - 4 stands: Norte, Sul (single-tier), Este, Oeste (double-tier with VIP boxes)
    - 27 gates distributed around the stadium
    - Continuous bowl design (European style)
    """
    
    init_db()
    db: Session = SessionLocal()
    
    try:
        # ==================== STADIUM CONFIGURATION ====================
        # Real Estádio do Dragão structure
        
        # Stadium dimensions (pixels - for visualization)
        CENTER_X = 500
        CENTER_Y = 400
        
        # Elliptical shape
        OUTER_PERIMETER_X = 420
        OUTER_PERIMETER_Y = 340
        
        # Corridors
        CORRIDOR_OUTER_X = 400
        CORRIDOR_OUTER_Y = 320
        CORRIDOR_MID_X = 360
        CORRIDOR_MID_Y = 280
        CORRIDOR_INNER_X = 320
        CORRIDOR_INNER_Y = 240
        
        # Navigation grid density
        NUM_CORRIDOR_POINTS = 72  # Every 5 degrees
        
        # Real stand configuration
        # Norte/Sul: single tier (bancada simples)
        # Este/Oeste: double tier with VIP boxes (bancada + arquibancada)
        STANDS = {
            'Norte': {
                'angle_start': 45,    # degrees
                'angle_end': 135,
                'tiers': 1,           # Single tier
                'rows_per_tier': [35],
                'sponsor': 'Coca-Cola',
                'ultra_group': 'Colectivo Ultras 95'
            },
            'Sul': {
                'angle_start': 225,
                'angle_end': 315,
                'tiers': 1,
                'rows_per_tier': [35],
                'sponsor': 'Super Bock',
                'ultra_group': 'Super Dragões'
            },
            'Este': {
                'angle_start': 315,
                'angle_end': 405,  # 45 degrees (wraps around)
                'tiers': 2,        # Double tier
                'rows_per_tier': [20, 15],  # Lower + Upper
                'sponsor': 'tmn',
                'has_vip_boxes': True,
                'away_fans': True
            },
            'Oeste': {
                'angle_start': 135,
                'angle_end': 225,
                'tiers': 2,
                'rows_per_tier': [20, 15],
                'sponsor': 'meo',
                'has_vip_boxes': True,
                'has_tunnel': True  # Players tunnel
            }
        }
        
        # Real gates based on official FC Porto info
        GATES = {
            # Norte (Superior Norte)
            'Norte': [21, 22, 23],
            # Sul (similar distribution)
            'Sul': [7, 8, 9],
            # Este (Bancada + Arquibancada Nascente)
            'Este': [10, 11, 12, 13, 17, 18],
            # Oeste (Bancada + Arquibancada Poente)
            'Oeste': [3, 4, 5, 6, 24, 25, 26, 27]
        }
        
        SEATS_PER_ROW = 40  # ~50k / (4 stands * ~30 rows) ≈ 40 per row
        
        nodes_data = []
        edges_data = []
        node_id_counter = 1
        grid_nodes = {}  # (level, corridor_type, position) -> node_id
        
        # Helper function for elliptical position
        def ellipse_pos(angle_deg, radius_x, radius_y):
            angle = math.radians(angle_deg)
            return (
                CENTER_X + radius_x * math.cos(angle),
                CENTER_Y + radius_y * math.sin(angle)
            )
        
        # ==================== NAVIGATION CORRIDORS ====================
        # Level 0 = Ground floor, Level 1 = Upper tier (Este/Oeste only)
        
        for level in range(2):  # 0 = lower, 1 = upper
            # Outer corridor (main concourse)
            for i in range(NUM_CORRIDOR_POINTS):
                angle = i * 360 / NUM_CORRIDOR_POINTS
                x, y = ellipse_pos(angle, CORRIDOR_OUTER_X, CORRIDOR_OUTER_Y)
                node_id = f"N{node_id_counter}"
                nodes_data.append({
                    "id": node_id,
                    "x": x,
                    "y": y,
                    "level": level,
                    "type": "corridor",
                    "name": f"Concourse L{level} P{i}"
                })
                grid_nodes[(level, 'outer', i)] = node_id
                node_id_counter += 1
            
            # Middle corridor
            for i in range(NUM_CORRIDOR_POINTS):
                angle = i * 360 / NUM_CORRIDOR_POINTS
                x, y = ellipse_pos(angle, CORRIDOR_MID_X, CORRIDOR_MID_Y)
                node_id = f"N{node_id_counter}"
                nodes_data.append({
                    "id": node_id,
                    "x": x,
                    "y": y,
                    "level": level,
                    "type": "corridor",
                    "name": f"Mid L{level} P{i}"
                })
                grid_nodes[(level, 'mid', i)] = node_id
                node_id_counter += 1
            
            # Inner corridor (seating access)
            for i in range(NUM_CORRIDOR_POINTS):
                angle = i * 360 / NUM_CORRIDOR_POINTS
                x, y = ellipse_pos(angle, CORRIDOR_INNER_X, CORRIDOR_INNER_Y)
                node_id = f"N{node_id_counter}"
                nodes_data.append({
                    "id": node_id,
                    "x": x,
                    "y": y,
                    "level": level,
                    "type": "corridor",
                    "name": f"Inner L{level} P{i}"
                })
                grid_nodes[(level, 'inner', i)] = node_id
                node_id_counter += 1
        
        # ==================== CORRIDOR CONNECTIONS ====================
        
        for level in range(2):
            # Connect along each corridor ring (circular)
            for corridor_type in ['outer', 'mid', 'inner']:
                for i in range(NUM_CORRIDOR_POINTS):
                    next_i = (i + 1) % NUM_CORRIDOR_POINTS
                    from_node = grid_nodes[(level, corridor_type, i)]
                    to_node = grid_nodes[(level, corridor_type, next_i)]
                    edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": from_node, "to_id": to_node, "weight": 5.0})
                    edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": to_node, "to_id": from_node, "weight": 5.0})
            
            # Radial connections between corridors (every 2 points for denser network)
            for i in range(0, NUM_CORRIDOR_POINTS, 2):
                outer = grid_nodes[(level, 'outer', i)]
                mid = grid_nodes[(level, 'mid', i)]
                inner = grid_nodes[(level, 'inner', i)]
                
                # Outer <-> Mid
                edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": outer, "to_id": mid, "weight": 8.0})
                edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": mid, "to_id": outer, "weight": 8.0})
                # Mid <-> Inner
                edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": mid, "to_id": inner, "weight": 8.0})
                edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": inner, "to_id": mid, "weight": 8.0})
            
            # Diagonal shortcuts (every 6 points) - allows cutting corners
            for i in range(0, NUM_CORRIDOR_POINTS, 6):
                next_i = (i + 1) % NUM_CORRIDOR_POINTS
                outer = grid_nodes[(level, 'outer', i)]
                mid_next = grid_nodes[(level, 'mid', next_i)]
                
                edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": outer, "to_id": mid_next, "weight": 9.0})
                edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": mid_next, "to_id": outer, "weight": 9.0})
        
        # ==================== STAIRS & RAMPS (Level connections) ====================
        
        # 8 stair locations around the stadium
        stair_positions = [9, 18, 27, 36, 45, 54, 63, 72]
        for idx, pos in enumerate(stair_positions):
            pos = pos % NUM_CORRIDOR_POINTS
            angle = pos * 360 / NUM_CORRIDOR_POINTS
            x, y = ellipse_pos(angle, CORRIDOR_OUTER_X + 15, CORRIDOR_OUTER_Y + 15)
            
            stair_id = f"Stairs-{idx+1}"
            nodes_data.append({
                "id": stair_id,
                "name": f"Escadas {idx+1}",
                "x": x,
                "y": y,
                "level": 0,
                "type": "stairs",
                "description": f"Stairs connecting Level 0 to Level 1"
            })
            
            # Connect to both levels - STAIRS ARE NOT ACCESSIBLE
            l0_node = grid_nodes[(0, 'outer', pos)]
            l1_node = grid_nodes[(1, 'outer', pos)]
            
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": l0_node, "to_id": stair_id, "weight": 2.0, "accessible": False})
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": stair_id, "to_id": l0_node, "weight": 2.0, "accessible": False})
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": stair_id, "to_id": l1_node, "weight": 15.0, "accessible": False})  # Going up
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": l1_node, "to_id": stair_id, "weight": 10.0, "accessible": False})  # Going down
        
        # 4 ramps for accessibility
        ramp_positions = [12, 30, 48, 66]
        for idx, pos in enumerate(ramp_positions):
            angle = pos * 360 / NUM_CORRIDOR_POINTS
            x, y = ellipse_pos(angle, CORRIDOR_OUTER_X + 20, CORRIDOR_OUTER_Y + 20)
            
            ramp_id = f"Ramp-{idx+1}"
            nodes_data.append({
                "id": ramp_id,
                "name": f"Rampa {idx+1}",
                "x": x,
                "y": y,
                "level": 0,
                "type": "ramp",
                "description": f"Accessible ramp for wheelchair users"
            })
            
            # Connect to both levels - RAMPS ARE ACCESSIBLE
            l0_node = grid_nodes[(0, 'outer', pos)]
            l1_node = grid_nodes[(1, 'outer', pos)]
            
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": l0_node, "to_id": ramp_id, "weight": 2.0, "accessible": True})
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": ramp_id, "to_id": l0_node, "weight": 2.0, "accessible": True})
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": ramp_id, "to_id": l1_node, "weight": 20.0, "accessible": True})
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": l1_node, "to_id": ramp_id, "weight": 15.0, "accessible": True})
        
        # ==================== GATES ====================
        gates_data = []
        
        for stand_name, gate_numbers in GATES.items():
            stand = STANDS[stand_name]
            angle_range = stand['angle_end'] - stand['angle_start']
            
            for i, gate_num in enumerate(gate_numbers):
                # Distribute gates evenly across stand
                angle = stand['angle_start'] + (i + 0.5) * angle_range / len(gate_numbers)
                if angle >= 360:
                    angle -= 360
                
                x, y = ellipse_pos(angle, OUTER_PERIMETER_X, OUTER_PERIMETER_Y)
                
                gate_id = f"Gate-{gate_num}"
                gates_data.append({
                    "id": gate_id,
                    "name": f"Porta {gate_num}",
                    "x": x,
                    "y": y,
                    "level": 0,
                    "type": "gate",
                    "description": f"Entrada {stand_name}",
                    "num_servers": 4,
                    "service_rate": 0.8
                })
                
                # Connect to nearest corridor node
                corridor_pos = round(angle * NUM_CORRIDOR_POINTS / 360) % NUM_CORRIDOR_POINTS
                corridor = grid_nodes[(0, 'outer', corridor_pos)]
                edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": gate_id, "to_id": corridor, "weight": 3.0})
                edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": corridor, "to_id": gate_id, "weight": 3.0})
        
        # ==================== ROW AISLES & SEATS (New Navigation Structure) ====================
        # Seats are ENDPOINTS only - routes go through row_aisle nodes
        
        seats_data = []
        aisles_data = []
        aisle_nodes = {}  # Track aisle nodes: (stand, tier, row, position) -> node_id
        
        # Aisle positions: left, center-left, center-right, right
        AISLE_POSITIONS = [0, SEATS_PER_ROW // 3, 2 * SEATS_PER_ROW // 3, SEATS_PER_ROW - 1]
        
        for stand_name, stand in STANDS.items():
            angle_start = stand['angle_start']
            angle_end = stand['angle_end']
            if angle_end > 360:
                angle_end -= 360
            
            for tier in range(stand['tiers']):
                rows = stand['rows_per_tier'][tier]
                level = tier
                
                base_radius_x = CORRIDOR_INNER_X - 20 - (tier * 40)
                base_radius_y = CORRIDOR_INNER_Y - 20 - (tier * 40)
                
                for row in range(1, rows + 1):
                    row_progress = (row - 1) / max(rows - 1, 1)
                    row_radius_x = base_radius_x - row_progress * 100
                    row_radius_y = base_radius_y - row_progress * 80
                    
                    # Create aisle nodes for this row (positioned between seats)
                    for aisle_idx, aisle_pos in enumerate(AISLE_POSITIONS):
                        seat_progress = (aisle_pos + 1) / (SEATS_PER_ROW + 1)
                        if angle_end < angle_start:
                            angle = angle_start + seat_progress * (360 - angle_start + angle_end)
                            if angle >= 360:
                                angle -= 360
                        else:
                            angle = angle_start + seat_progress * (angle_end - angle_start)
                        
                        # Position aisle slightly outward from seats (clearer separation)
                        x, y = ellipse_pos(angle, row_radius_x, row_radius_y)
                        
                        aisle_id = f"Aisle-{stand_name}-T{tier}-R{row:02d}-{aisle_idx}"
                        aisles_data.append({
                            "id": aisle_id,
                            "type": "row_aisle",
                            "name": f"Corredor {stand_name} T{tier} Fila {row}",
                            "x": x,
                            "y": y,
                            "level": level
                        })
                        aisle_nodes[(stand_name, tier, row, aisle_idx)] = aisle_id
                    
                    # Connect aisles horizontally (along the row) - ACCESSIBLE (flat)
                    for i in range(len(AISLE_POSITIONS) - 1):
                        a1 = aisle_nodes[(stand_name, tier, row, i)]
                        a2 = aisle_nodes[(stand_name, tier, row, i + 1)]
                        edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": a1, "to_id": a2, "weight": 3.0, "accessible": True})
                        edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": a2, "to_id": a1, "weight": 3.0, "accessible": True})
                    
                    # Connect aisles vertically to previous row - NOT ACCESSIBLE (has stairs/steps)
                    if row > 1:
                        for aisle_idx in range(len(AISLE_POSITIONS)):
                            curr_aisle = aisle_nodes[(stand_name, tier, row, aisle_idx)]
                            prev_aisle = aisle_nodes[(stand_name, tier, row - 1, aisle_idx)]
                            # These edges have stairs between rows - NOT wheelchair accessible
                            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": prev_aisle, "to_id": curr_aisle, "weight": 1.5, "accessible": False})
                            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": curr_aisle, "to_id": prev_aisle, "weight": 1.5, "accessible": False})
                    
                    # Connect first row aisles to inner corridor
                    if row == 1:
                        for aisle_idx, aisle_pos in enumerate(AISLE_POSITIONS):
                            aisle_id = aisle_nodes[(stand_name, tier, 1, aisle_idx)]
                            seat_progress = (aisle_pos + 1) / (SEATS_PER_ROW + 1)
                            if angle_end < angle_start:
                                aisle_angle = angle_start + seat_progress * (360 - angle_start + angle_end)
                                if aisle_angle >= 360:
                                    aisle_angle -= 360
                            else:
                                aisle_angle = angle_start + seat_progress * (angle_end - angle_start)
                            
                            corridor_pos = round(aisle_angle * NUM_CORRIDOR_POINTS / 360) % NUM_CORRIDOR_POINTS
                            corridor = grid_nodes[(level, 'inner', corridor_pos)]
                            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": corridor, "to_id": aisle_id, "weight": 2.0})
                            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": aisle_id, "to_id": corridor, "weight": 2.0})
                    
                    # Create seats (endpoints only!)
                    for num in range(1, SEATS_PER_ROW + 1):
                        seat_progress = num / (SEATS_PER_ROW + 1)
                        if angle_end < angle_start:
                            angle = angle_start + seat_progress * (360 - angle_start + angle_end)
                            if angle >= 360:
                                angle -= 360
                        else:
                            angle = angle_start + seat_progress * (angle_end - angle_start)
                        
                        x, y = ellipse_pos(angle, row_radius_x, row_radius_y)
                        
                        seat_id = f"Seat-{stand_name}-T{tier}-R{row:02d}-{num:02d}"
                        seats_data.append({
                            "id": seat_id,
                            "type": "seat",
                            "block": f"{stand_name}-T{tier}",
                            "row": row,
                            "number": num,
                            "x": x,
                            "y": y,
                            "level": level
                        })
                        
                        # Connect seat to nearest aisle (seat is an ENDPOINT)
                        nearest_aisle_idx = min(range(len(AISLE_POSITIONS)), 
                                                key=lambda i: abs(AISLE_POSITIONS[i] - (num - 1)))
                        nearest_aisle = aisle_nodes[(stand_name, tier, row, nearest_aisle_idx)]
                        distance = abs(AISLE_POSITIONS[nearest_aisle_idx] - (num - 1)) * 0.5 + 0.5
                        edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": nearest_aisle, "to_id": seat_id, "weight": distance})
                        edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": seat_id, "to_id": nearest_aisle, "weight": distance})
        
        # ==================== POIs ====================
        pois_data = []
        
        # WCs - 2 per stand per level
        for level in range(2):
            for idx, stand_name in enumerate(['Norte', 'Sul', 'Este', 'Oeste']):
                stand = STANDS[stand_name]
                for wc_idx in range(2):
                    angle = stand['angle_start'] + (wc_idx + 1) * (stand['angle_end'] - stand['angle_start']) / 3
                    if angle >= 360:
                        angle -= 360
                    x, y = ellipse_pos(angle, CORRIDOR_MID_X, CORRIDOR_MID_Y)
                    
                    wc_id = f"WC-{stand_name}-L{level}-{wc_idx+1}"
                    pois_data.append({
                        "id": wc_id,
                        "name": f"WC {stand_name} {wc_idx+1}",
                        "type": "restroom",
                        "x": x,
                        "y": y,
                        "level": level,
                        "num_servers": 8,
                        "service_rate": 0.5
                    })
                    
                    corridor_pos = round(angle * NUM_CORRIDOR_POINTS / 360) % NUM_CORRIDOR_POINTS
                    corridor = grid_nodes[(level, 'mid', corridor_pos)]
                    edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": wc_id, "to_id": corridor, "weight": 2.0})
                    edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": corridor, "to_id": wc_id, "weight": 2.0})
        
        # Food/Bars - 3 per stand on level 0
        for idx, stand_name in enumerate(['Norte', 'Sul', 'Este', 'Oeste']):
            stand = STANDS[stand_name]
            for food_idx in range(3):
                angle = stand['angle_start'] + (food_idx + 0.5) * (stand['angle_end'] - stand['angle_start']) / 3
                if angle >= 360:
                    angle -= 360
                x, y = ellipse_pos(angle, CORRIDOR_MID_X + 10, CORRIDOR_MID_Y + 10)
                
                food_id = f"Food-{stand_name}-{food_idx+1}"
                pois_data.append({
                    "id": food_id,
                    "name": f"Bar/Restaurante {stand_name} {food_idx+1}",
                    "type": "food" if food_idx % 2 == 0 else "bar",
                    "x": x,
                    "y": y,
                    "level": 0,
                    "num_servers": 6,
                    "service_rate": 0.4
                })
                
                corridor_pos = round(angle * NUM_CORRIDOR_POINTS / 360) % NUM_CORRIDOR_POINTS
                corridor = grid_nodes[(0, 'mid', corridor_pos)]
                edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": food_id, "to_id": corridor, "weight": 2.0})
                edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": corridor, "to_id": food_id, "weight": 2.0})
        
        # Emergency exits - 2 per stand
        for idx, stand_name in enumerate(['Norte', 'Sul', 'Este', 'Oeste']):
            stand = STANDS[stand_name]
            for exit_idx in range(2):
                angle = stand['angle_start'] + (exit_idx + 0.5) * (stand['angle_end'] - stand['angle_start']) / 2
                if angle >= 360:
                    angle -= 360
                x, y = ellipse_pos(angle, OUTER_PERIMETER_X - 10, OUTER_PERIMETER_Y - 10)
                
                exit_id = f"Exit-{stand_name}-{exit_idx+1}"
                pois_data.append({
                    "id": exit_id,
                    "name": f"Saída Emergência {stand_name} {exit_idx+1}",
                    "type": "emergency_exit",
                    "x": x,
                    "y": y,
                    "level": 0
                })
                
                corridor_pos = round(angle * NUM_CORRIDOR_POINTS / 360) % NUM_CORRIDOR_POINTS
                corridor = grid_nodes[(0, 'outer', corridor_pos)]
                edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": exit_id, "to_id": corridor, "weight": 2.0})
                edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": corridor, "to_id": exit_id, "weight": 2.0})
        
        # First aid stations - 1 per side
        for idx, (stand_name, angle) in enumerate([('Norte', 90), ('Sul', 270), ('Este', 0), ('Oeste', 180)]):
            x, y = ellipse_pos(angle, CORRIDOR_MID_X - 15, CORRIDOR_MID_Y - 15)
            
            aid_id = f"Medical-{stand_name}"
            pois_data.append({
                "id": aid_id,
                "name": f"Posto Médico {stand_name}",
                "type": "first_aid",
                "x": x,
                "y": y,
                "level": 0,
                "num_servers": 3,
                "service_rate": 0.2
            })
            
            corridor_pos = round(angle * NUM_CORRIDOR_POINTS / 360) % NUM_CORRIDOR_POINTS
            corridor = grid_nodes[(0, 'mid', corridor_pos)]
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": aid_id, "to_id": corridor, "weight": 2.0})
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": corridor, "to_id": aid_id, "weight": 2.0})
        
        # FC Porto Store - 2 locations
        for idx, angle in enumerate([60, 240]):
            x, y = ellipse_pos(angle, CORRIDOR_MID_X, CORRIDOR_MID_Y)
            
            store_id = f"Store-{idx+1}"
            pois_data.append({
                "id": store_id,
                "name": f"Loja FC Porto {idx+1}",
                "type": "merchandise",
                "x": x,
                "y": y,
                "level": 0,
                "num_servers": 4,
                "service_rate": 0.5
            })
            
            corridor_pos = round(angle * NUM_CORRIDOR_POINTS / 360) % NUM_CORRIDOR_POINTS
            corridor = grid_nodes[(0, 'mid', corridor_pos)]
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": store_id, "to_id": corridor, "weight": 2.0})
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": corridor, "to_id": store_id, "weight": 2.0})
        
        # Information points - 3 locations
        for idx, angle in enumerate([90, 180, 270]):
            x, y = ellipse_pos(angle, CORRIDOR_OUTER_X - 20, CORRIDOR_OUTER_Y - 20)
            
            info_id = f"Info-{idx+1}"
            pois_data.append({
                "id": info_id,
                "name": f"Informações {idx+1}",
                "type": "information",
                "x": x,
                "y": y,
                "level": 0,
                "num_servers": 2,
                "service_rate": 0.6
            })
            
            corridor_pos = round(angle * NUM_CORRIDOR_POINTS / 360) % NUM_CORRIDOR_POINTS
            corridor = grid_nodes[(0, 'outer', corridor_pos)]
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": info_id, "to_id": corridor, "weight": 2.0})
            edges_data.append({"id": f"E{len(edges_data)+1}", "from_id": corridor, "to_id": info_id, "weight": 2.0})
        
        # ==================== INSERT DATA ====================
        
        for node_data in nodes_data:
            db.add(Node(**node_data))
        
        for gate_data in gates_data:
            db.add(Node(**gate_data))
        
        for poi_data in pois_data:
            db.add(Node(**poi_data))
        
        # Insert aisles (new navigation nodes)
        for aisle_data in aisles_data:
            db.add(Node(**aisle_data))
        
        for seat_data in seats_data:
            db.add(Node(**seat_data))
        
        for edge_data in edges_data:
            db.add(Edge(**edge_data))
        
        # ==================== EMERGENCY ROUTES ====================
        # Create evacuation routes from various parts of the stadium to emergency exits
        emergency_routes_data = []
        
        # Find all emergency exits
        exit_nodes = [poi for poi in pois_data if poi['type'] == 'emergency_exit']
        
        for exit_node in exit_nodes:
            exit_id = exit_node['id']
            stand_name = exit_id.split('-')[1]  # e.g., "Norte" from "Exit-Norte-1"
            
            # Get corridor nodes near this exit to form evacuation path
            exit_angle = STANDS[stand_name]['angle_start'] + (STANDS[stand_name]['angle_end'] - STANDS[stand_name]['angle_start']) / 2
            if exit_angle >= 360:
                exit_angle -= 360
            
            # Build a path from inner corridor to exit
            center_pos = round(exit_angle * NUM_CORRIDOR_POINTS / 360) % NUM_CORRIDOR_POINTS
            
            # Path: inner corridor -> mid corridor -> outer corridor -> exit
            path_nodes = []
            for level in [0]:  # Level 0 evacuation
                path_nodes.append(grid_nodes[(level, 'inner', center_pos)])
                path_nodes.append(grid_nodes[(level, 'mid', center_pos)])
                path_nodes.append(grid_nodes[(level, 'outer', center_pos)])
            path_nodes.append(exit_id)
            
            route_id = f"ER-{exit_id}"
            emergency_routes_data.append({
                "id": route_id,
                "name": f"Rota de Evacuação {exit_node['name']}",
                "description": f"Evacuação para {stand_name}",
                "exit_id": exit_id,
                "node_ids": path_nodes
            })
        
        # Insert emergency routes
        for route_data in emergency_routes_data:
            db.add(EmergencyRoute(**route_data))
        
        db.commit()
        
        # ==================== SUMMARY ====================
        print("=" * 70)
        print("ESTADIO DO DRAGAO - Dados Realistas Carregados!")
        print("=" * 70)
        print("\nESTATISTICAS:")
        print(f"   - Corredores:          {len(nodes_data):>7} nodes")
        print(f"   - Corredores filas:    {len(aisles_data):>7} (row_aisle)")
        print(f"   - Portoes:             {len(gates_data):>7}")
        print(f"   - POIs:                {len(pois_data):>7}")
        print(f"   - Lugares:             {len(seats_data):>7}")
        print(f"   - Rotas emergencia:    {len(emergency_routes_data):>7}")
        print(f"   - Conexoes:            {len(edges_data):>7}")
        total_nodes = len(nodes_data) + len(aisles_data) + len(gates_data) + len(pois_data) + len(seats_data)
        print(f"\n   TOTAL NODES:           {total_nodes:>7}")
        print("\nCARACTERISTICAS:")
        print("   [x] Estrutura real: Norte/Sul (1 tier), Este/Oeste (2 tiers)")
        print("   [x] Seats sao endpoints (rotas passam por row_aisle)")
        print("   [x] Rotas de emergencia predefinidas")
        print("   [x] 8 escadas + 4 rampas entre niveis")
        
        # ==================== REBUILD GRID ====================
        grid_manager = GridManager(cell_size=5.0, origin_x=0.0, origin_y=0.0)
        tile_count = grid_manager.rebuild_grid(db)
        print(f"\n   TILES:                 {tile_count:>7}")
        
        print("\nBase de dados pronta!")
        print("=" * 70)
        
    except Exception as e:
        db.rollback()
        print(f"\nError loading data: {str(e)}")
        raise
    finally:
        db.close()


def clear_all_data():
    """Clear all data from the database."""
    # Ensure tables exist before trying to delete
    init_db()
    
    db: Session = SessionLocal()
    try:
        db.query(EmergencyRoute).delete()
        db.query(Closure).delete()
        db.query(Edge).delete()
        db.query(Tile).delete()
        db.query(Node).delete()
        db.commit()
        print("All data cleared from database")
    except Exception as e:
        db.rollback()
        print(f"Error clearing data: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--clear":
        print("Clearing all data...")
        clear_all_data()
        print()
    
    print("Loading Estádio do Dragão data...")
    load_sample_data()
    print("\nDone! You can now start the FastAPI server.")