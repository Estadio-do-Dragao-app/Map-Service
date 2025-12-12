"""
Stadium Data Loader from JSON Configuration

This module provides an alternative, more scalable approach to loading stadium data.
Instead of hardcoding values, it reads from a JSON configuration file.

Usage:
    python load_from_config.py stadiums/dragao_config.json
    
The original load_data_db.py remains unchanged for backwards compatibility.
"""

from sqlalchemy.orm import Session
from database import SessionLocal, init_db
from grid_name import GridManager
from models import Node, Edge, Closure, Tile, EmergencyRoute
import math
import json
import sys


class StadiumLoader:
    """Loads stadium navigation graph from JSON configuration."""
    
    def __init__(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.nodes_data = []
        self.edges_data = []
        self.grid_nodes = {}  # (level, corridor_type, position) -> node_id
        self.node_id_counter = 1
        
    def ellipse_pos(self, angle_deg: float, radius_x: float, radius_y: float) -> tuple:
        """Calculate position on ellipse at given angle."""
        dims = self.config['dimensions']
        angle = math.radians(angle_deg)
        return (
            dims['center_x'] + radius_x * math.cos(angle),
            dims['center_y'] + radius_y * math.sin(angle)
        )
    
    def add_edge(self, from_id: str, to_id: str, weight: float, accessible: bool = True):
        """Add an edge to the graph."""
        edge_id = f"E{len(self.edges_data)+1}"
        self.edges_data.append({
            "id": edge_id,
            "from_id": from_id,
            "to_id": to_id,
            "weight": weight,
            "accessible": accessible
        })
    
    def generate_corridors(self):
        """Generate corridor navigation nodes for both levels."""
        dims = self.config['dimensions']
        corridors = dims['corridors']
        num_points = self.config['navigation']['corridor_points']
        
        corridor_specs = [
            ('outer', corridors['outer_x'], corridors['outer_y']),
            ('mid', corridors['mid_x'], corridors['mid_y']),
            ('inner', corridors['inner_x'], corridors['inner_y'])
        ]
        
        for level in range(2):
            for corridor_type, radius_x, radius_y in corridor_specs:
                for i in range(num_points):
                    angle = i * 360 / num_points
                    x, y = self.ellipse_pos(angle, radius_x, radius_y)
                    node_id = f"N{self.node_id_counter}"
                    
                    self.nodes_data.append({
                        "id": node_id,
                        "x": x,
                        "y": y,
                        "level": level,
                        "type": "corridor",
                        "name": f"{corridor_type.capitalize()} L{level} P{i}"
                    })
                    self.grid_nodes[(level, corridor_type, i)] = node_id
                    self.node_id_counter += 1
        
        print(f"   Generated {len(self.nodes_data)} corridor nodes")
    
    def connect_corridors(self):
        """Connect corridor nodes with edges."""
        num_points = self.config['navigation']['corridor_points']
        weights = self.config['edge_weights']
        
        for level in range(2):
            # Connect along each corridor ring
            for corridor_type in ['outer', 'mid', 'inner']:
                for i in range(num_points):
                    next_i = (i + 1) % num_points
                    from_node = self.grid_nodes[(level, corridor_type, i)]
                    to_node = self.grid_nodes[(level, corridor_type, next_i)]
                    self.add_edge(from_node, to_node, weights['corridor_along'])
                    self.add_edge(to_node, from_node, weights['corridor_along'])
            
            # Radial connections
            for i in range(0, num_points, 2):
                outer = self.grid_nodes[(level, 'outer', i)]
                mid = self.grid_nodes[(level, 'mid', i)]
                inner = self.grid_nodes[(level, 'inner', i)]
                
                self.add_edge(outer, mid, weights['corridor_radial'])
                self.add_edge(mid, outer, weights['corridor_radial'])
                self.add_edge(mid, inner, weights['corridor_radial'])
                self.add_edge(inner, mid, weights['corridor_radial'])
            
            # Diagonal shortcuts
            for i in range(0, num_points, 6):
                next_i = (i + 1) % num_points
                outer = self.grid_nodes[(level, 'outer', i)]
                mid_next = self.grid_nodes[(level, 'mid', next_i)]
                
                self.add_edge(outer, mid_next, weights['corridor_diagonal'])
                self.add_edge(mid_next, outer, weights['corridor_diagonal'])
        
        print(f"   Generated corridor connections")
    
    def generate_stairs_and_ramps(self):
        """Generate stair and ramp nodes connecting levels."""
        dims = self.config['dimensions']
        corridors = dims['corridors']
        num_points = self.config['navigation']['corridor_points']
        connectors = self.config['level_connectors']
        
        # Stairs
        stairs_config = connectors['stairs']
        for idx, pos in enumerate(stairs_config['positions']):
            pos = pos % num_points
            angle = pos * 360 / num_points
            x, y = self.ellipse_pos(
                angle, 
                corridors['outer_x'] + stairs_config['offset_x'],
                corridors['outer_y'] + stairs_config['offset_y']
            )
            
            # Create two nodes per stair (one per level)
            stair_l0_id = f"Stairs-{idx+1}-L0"
            stair_l1_id = f"Stairs-{idx+1}-L1"
            
            self.nodes_data.append({
                "id": stair_l0_id,
                "name": f"Escadas {idx+1} (Piso 0)",
                "x": x, "y": y, "level": 0,
                "type": "stairs",
                "description": "Escadas - acesso ao Piso 1"
            })
            self.nodes_data.append({
                "id": stair_l1_id,
                "name": f"Escadas {idx+1} (Piso 1)",
                "x": x, "y": y, "level": 1,
                "type": "stairs",
                "description": "Escadas - acesso ao Piso 0"
            })
            
            # Connect to corridors and between levels
            l0_corridor = self.grid_nodes[(0, 'outer', pos)]
            l1_corridor = self.grid_nodes[(1, 'outer', pos)]
            accessible = stairs_config['accessible']
            
            self.add_edge(l0_corridor, stair_l0_id, 2.0, accessible)
            self.add_edge(stair_l0_id, l0_corridor, 2.0, accessible)
            self.add_edge(l1_corridor, stair_l1_id, 2.0, accessible)
            self.add_edge(stair_l1_id, l1_corridor, 2.0, accessible)
            self.add_edge(stair_l0_id, stair_l1_id, stairs_config['weight_up'], accessible)
            self.add_edge(stair_l1_id, stair_l0_id, stairs_config['weight_down'], accessible)
        
        # Ramps
        ramps_config = connectors['ramps']
        for idx, pos in enumerate(ramps_config['positions']):
            angle = pos * 360 / num_points
            x, y = self.ellipse_pos(
                angle,
                corridors['outer_x'] + ramps_config['offset_x'],
                corridors['outer_y'] + ramps_config['offset_y']
            )
            
            ramp_l0_id = f"Ramp-{idx+1}-L0"
            ramp_l1_id = f"Ramp-{idx+1}-L1"
            
            self.nodes_data.append({
                "id": ramp_l0_id,
                "name": f"Rampa {idx+1} (Piso 0)",
                "x": x, "y": y, "level": 0,
                "type": "ramp",
                "description": "Rampa acessível - acesso ao Piso 1"
            })
            self.nodes_data.append({
                "id": ramp_l1_id,
                "name": f"Rampa {idx+1} (Piso 1)",
                "x": x, "y": y, "level": 1,
                "type": "ramp",
                "description": "Rampa acessível - acesso ao Piso 0"
            })
            
            l0_corridor = self.grid_nodes[(0, 'outer', pos)]
            l1_corridor = self.grid_nodes[(1, 'outer', pos)]
            accessible = ramps_config['accessible']
            
            self.add_edge(l0_corridor, ramp_l0_id, 2.0, accessible)
            self.add_edge(ramp_l0_id, l0_corridor, 2.0, accessible)
            self.add_edge(l1_corridor, ramp_l1_id, 2.0, accessible)
            self.add_edge(ramp_l1_id, l1_corridor, 2.0, accessible)
            self.add_edge(ramp_l0_id, ramp_l1_id, ramps_config['weight_up'], accessible)
            self.add_edge(ramp_l1_id, ramp_l0_id, ramps_config['weight_down'], accessible)
        
        total_connectors = len(stairs_config['positions']) + len(ramps_config['positions'])
        print(f"   Generated {total_connectors * 2} stair/ramp nodes (dual-level)")
    
    def generate_gates(self):
        """Generate gate nodes."""
        dims = self.config['dimensions']
        num_points = self.config['navigation']['corridor_points']
        weights = self.config['edge_weights']
        gates_data = []
        
        for stand_name, stand in self.config['stands'].items():
            angle_range = stand['angle_end'] - stand['angle_start']
            gates = stand.get('gates', [])
            
            for i, gate_num in enumerate(gates):
                angle = stand['angle_start'] + (i + 0.5) * angle_range / len(gates)
                if angle >= 360:
                    angle -= 360
                
                x, y = self.ellipse_pos(angle, dims['outer_perimeter_x'], dims['outer_perimeter_y'])
                
                gate_id = f"Gate-{gate_num}"
                gates_data.append({
                    "id": gate_id,
                    "name": f"Porta {gate_num}",
                    "x": x, "y": y, "level": 0,
                    "type": "gate",
                    "description": f"Entrada {stand_name}",
                    "num_servers": 4,
                    "service_rate": 0.8
                })
                
                # Connect to corridor
                corridor_pos = round(angle * num_points / 360) % num_points
                corridor = self.grid_nodes[(0, 'outer', corridor_pos)]
                self.add_edge(gate_id, corridor, weights['gate_connection'])
                self.add_edge(corridor, gate_id, weights['gate_connection'])
        
        self.nodes_data.extend(gates_data)
        print(f"   Generated {len(gates_data)} gate nodes")
        return gates_data
    
    def generate_pois(self):
        """Generate POI nodes (restrooms, food, bars, etc.)."""
        dims = self.config['dimensions']
        corridors = dims['corridors']
        num_points = self.config['navigation']['corridor_points']
        pois_config = self.config['pois']
        weights = self.config['edge_weights']
        pois_data = []
        
        # Restrooms
        restrooms = pois_config['restrooms']
        for level in range(2) if restrooms.get('per_level', False) else [0]:
            for stand_name, stand in self.config['stands'].items():
                for wc_idx in range(restrooms['per_stand']):
                    angle = stand['angle_start'] + (wc_idx + 1) * (stand['angle_end'] - stand['angle_start']) / 3
                    if angle >= 360:
                        angle -= 360
                    x, y = self.ellipse_pos(angle, corridors['mid_x'], corridors['mid_y'])
                    
                    wc_id = f"WC-{stand_name}-L{level}-{wc_idx+1}"
                    pois_data.append({
                        "id": wc_id,
                        "name": f"WC {stand_name} {wc_idx+1}",
                        "type": "restroom",
                        "x": x, "y": y, "level": level,
                        "num_servers": restrooms['num_servers'],
                        "service_rate": restrooms['service_rate']
                    })
                    
                    corridor_pos = round(angle * num_points / 360) % num_points
                    corridor = self.grid_nodes[(level, 'mid', corridor_pos)]
                    self.add_edge(wc_id, corridor, weights['poi_connection'])
                    self.add_edge(corridor, wc_id, weights['poi_connection'])
        
        # Food/Bars
        food_bars = pois_config['food_bars']
        for stand_name, stand in self.config['stands'].items():
            for food_idx in range(food_bars['per_stand']):
                angle = stand['angle_start'] + (food_idx + 0.5) * (stand['angle_end'] - stand['angle_start']) / 3
                if angle >= 360:
                    angle -= 360
                x, y = self.ellipse_pos(angle, corridors['mid_x'] + 10, corridors['mid_y'] + 10)
                
                food_id = f"Food-{stand_name}-{food_idx+1}"
                pois_data.append({
                    "id": food_id,
                    "name": f"Bar/Restaurante {stand_name} {food_idx+1}",
                    "type": "food" if food_idx % 2 == 0 else "bar",
                    "x": x, "y": y, "level": food_bars['level'],
                    "num_servers": food_bars['num_servers'],
                    "service_rate": food_bars['service_rate']
                })
                
                corridor_pos = round(angle * num_points / 360) % num_points
                corridor = self.grid_nodes[(0, 'mid', corridor_pos)]
                self.add_edge(food_id, corridor, weights['poi_connection'])
                self.add_edge(corridor, food_id, weights['poi_connection'])
        
        # Emergency exits
        exits = pois_config['emergency_exits']
        for stand_name, stand in self.config['stands'].items():
            for exit_idx in range(exits['per_stand']):
                angle = stand['angle_start'] + (exit_idx + 0.5) * (stand['angle_end'] - stand['angle_start']) / 2
                if angle >= 360:
                    angle -= 360
                x, y = self.ellipse_pos(angle, dims['outer_perimeter_x'] - 10, dims['outer_perimeter_y'] - 10)
                
                exit_id = f"Exit-{stand_name}-{exit_idx+1}"
                pois_data.append({
                    "id": exit_id,
                    "name": f"Saída Emergência {stand_name} {exit_idx+1}",
                    "type": "emergency_exit",
                    "x": x, "y": y, "level": exits['level']
                })
                
                corridor_pos = round(angle * num_points / 360) % num_points
                corridor = self.grid_nodes[(0, 'outer', corridor_pos)]
                self.add_edge(exit_id, corridor, weights['poi_connection'])
                self.add_edge(corridor, exit_id, weights['poi_connection'])
        
        # First aid
        for first_aid in pois_config['first_aid']['positions']:
            angle = first_aid['angle']
            x, y = self.ellipse_pos(angle, corridors['mid_x'] - 15, corridors['mid_y'] - 15)
            
            aid_id = f"Medical-{first_aid['stand']}"
            pois_data.append({
                "id": aid_id,
                "name": f"Posto Médico {first_aid['stand']}",
                "type": "first_aid",
                "x": x, "y": y, "level": 0,
                "num_servers": pois_config['first_aid']['num_servers'],
                "service_rate": pois_config['first_aid']['service_rate']
            })
            
            corridor_pos = round(angle * num_points / 360) % num_points
            corridor = self.grid_nodes[(0, 'mid', corridor_pos)]
            self.add_edge(aid_id, corridor, weights['poi_connection'])
            self.add_edge(corridor, aid_id, weights['poi_connection'])
        
        # Stores
        stores = pois_config['stores']
        for idx, angle in enumerate(stores['positions']):
            x, y = self.ellipse_pos(angle, corridors['mid_x'], corridors['mid_y'])
            
            store_id = f"Store-{idx+1}"
            pois_data.append({
                "id": store_id,
                "name": f"Loja FC Porto {idx+1}",
                "type": "merchandise",
                "x": x, "y": y, "level": stores['level'],
                "num_servers": stores['num_servers'],
                "service_rate": stores['service_rate']
            })
            
            corridor_pos = round(angle * num_points / 360) % num_points
            corridor = self.grid_nodes[(0, 'mid', corridor_pos)]
            self.add_edge(store_id, corridor, weights['poi_connection'])
            self.add_edge(corridor, store_id, weights['poi_connection'])
        
        # Information
        info = pois_config['information']
        for idx, angle in enumerate(info['positions']):
            x, y = self.ellipse_pos(angle, corridors['outer_x'] - 20, corridors['outer_y'] - 20)
            
            info_id = f"Info-{idx+1}"
            pois_data.append({
                "id": info_id,
                "name": f"Informações {idx+1}",
                "type": "information",
                "x": x, "y": y, "level": info['level'],
                "num_servers": info['num_servers'],
                "service_rate": info['service_rate']
            })
            
            corridor_pos = round(angle * num_points / 360) % num_points
            corridor = self.grid_nodes[(0, 'outer', corridor_pos)]
            self.add_edge(info_id, corridor, weights['poi_connection'])
            self.add_edge(corridor, info_id, weights['poi_connection'])
        
        self.nodes_data.extend(pois_data)
        print(f"   Generated {len(pois_data)} POI nodes")
        return pois_data
    
    def generate_seats_and_aisles(self):
        """Generate seat and aisle nodes for all stands."""
        dims = self.config['dimensions']
        corridors = dims['corridors']
        nav = self.config['navigation']
        num_points = nav['corridor_points']
        seats_per_row = nav['seats_per_row']
        aisle_positions = nav['aisle_positions']
        weights = self.config['edge_weights']
        
        seats_data = []
        aisles_data = []
        aisle_nodes = {}
        
        for stand_name, stand in self.config['stands'].items():
            angle_start = stand['angle_start']
            angle_end = stand['angle_end']
            if angle_end > 360:
                angle_end -= 360
            
            for tier in range(stand['tiers']):
                rows = stand['rows_per_tier'][tier]
                level = tier
                
                base_radius_x = corridors['inner_x'] - 20 - (tier * 40)
                base_radius_y = corridors['inner_y'] - 20 - (tier * 40)
                
                for row in range(1, rows + 1):
                    row_progress = (row - 1) / max(rows - 1, 1)
                    row_radius_x = base_radius_x - row_progress * 100
                    row_radius_y = base_radius_y - row_progress * 80
                    
                    # Create aisles
                    for aisle_idx, aisle_pos in enumerate(aisle_positions):
                        seat_progress = (aisle_pos + 1) / (seats_per_row + 1)
                        if angle_end < angle_start:
                            angle = angle_start + seat_progress * (360 - angle_start + angle_end)
                            if angle >= 360:
                                angle -= 360
                        else:
                            angle = angle_start + seat_progress * (angle_end - angle_start)
                        
                        x, y = self.ellipse_pos(angle, row_radius_x, row_radius_y)
                        
                        aisle_id = f"Aisle-{stand_name}-T{tier}-R{row:02d}-{aisle_idx}"
                        aisles_data.append({
                            "id": aisle_id,
                            "type": "row_aisle",
                            "name": f"Corredor {stand_name} T{tier} Fila {row}",
                            "x": x, "y": y, "level": level
                        })
                        aisle_nodes[(stand_name, tier, row, aisle_idx)] = aisle_id
                    
                    # Connect aisles horizontally
                    for i in range(len(aisle_positions) - 1):
                        a1 = aisle_nodes[(stand_name, tier, row, i)]
                        a2 = aisle_nodes[(stand_name, tier, row, i + 1)]
                        self.add_edge(a1, a2, weights['aisle_horizontal'], True)
                        self.add_edge(a2, a1, weights['aisle_horizontal'], True)
                    
                    # Connect aisles vertically (NOT accessible - has stairs)
                    if row > 1:
                        for aisle_idx in range(len(aisle_positions)):
                            curr_aisle = aisle_nodes[(stand_name, tier, row, aisle_idx)]
                            prev_aisle = aisle_nodes[(stand_name, tier, row - 1, aisle_idx)]
                            self.add_edge(prev_aisle, curr_aisle, weights['aisle_vertical'], False)
                            self.add_edge(curr_aisle, prev_aisle, weights['aisle_vertical'], False)
                    
                    # Connect first row to inner corridor
                    if row == 1:
                        for aisle_idx, aisle_pos in enumerate(aisle_positions):
                            aisle_id = aisle_nodes[(stand_name, tier, 1, aisle_idx)]
                            seat_progress = (aisle_pos + 1) / (seats_per_row + 1)
                            if angle_end < angle_start:
                                aisle_angle = angle_start + seat_progress * (360 - angle_start + angle_end)
                                if aisle_angle >= 360:
                                    aisle_angle -= 360
                            else:
                                aisle_angle = angle_start + seat_progress * (angle_end - angle_start)
                            
                            corridor_pos = round(aisle_angle * num_points / 360) % num_points
                            corridor = self.grid_nodes[(level, 'inner', corridor_pos)]
                            self.add_edge(corridor, aisle_id, 2.0)
                            self.add_edge(aisle_id, corridor, 2.0)
                    
                    # Create seats
                    for num in range(1, seats_per_row + 1):
                        seat_progress = num / (seats_per_row + 1)
                        if angle_end < angle_start:
                            angle = angle_start + seat_progress * (360 - angle_start + angle_end)
                            if angle >= 360:
                                angle -= 360
                        else:
                            angle = angle_start + seat_progress * (angle_end - angle_start)
                        
                        x, y = self.ellipse_pos(angle, row_radius_x, row_radius_y)
                        
                        seat_id = f"Seat-{stand_name}-T{tier}-R{row:02d}-{num:02d}"
                        seats_data.append({
                            "id": seat_id,
                            "type": "seat",
                            "block": f"{stand_name}-T{tier}",
                            "row": row,
                            "number": num,
                            "x": x, "y": y, "level": level
                        })
                        
                        # Connect to nearest aisle
                        nearest_aisle_idx = min(range(len(aisle_positions)),
                                                key=lambda i: abs(aisle_positions[i] - (num - 1)))
                        nearest_aisle = aisle_nodes[(stand_name, tier, row, nearest_aisle_idx)]
                        distance = abs(aisle_positions[nearest_aisle_idx] - (num - 1)) * weights['seat_to_aisle_per_distance'] + weights['seat_to_aisle_base']
                        self.add_edge(nearest_aisle, seat_id, distance)
                        self.add_edge(seat_id, nearest_aisle, distance)
        
        self.nodes_data.extend(aisles_data)
        self.nodes_data.extend(seats_data)
        print(f"   Generated {len(aisles_data)} aisle nodes")
        print(f"   Generated {len(seats_data)} seat nodes")
        return aisles_data, seats_data
    
    def load_to_database(self):
        """Load all generated data to database."""
        init_db()
        db: Session = SessionLocal()
        
        try:
            # Clear existing data
            db.query(EmergencyRoute).delete()
            db.query(Closure).delete()
            db.query(Edge).delete()
            db.query(Tile).delete()
            db.query(Node).delete()
            db.commit()
            
            print(f"\n{'='*70}")
            print(f"Loading: {self.config['name']}")
            print(f"{'='*70}\n")
            
            # Generate all data
            self.generate_corridors()
            self.connect_corridors()
            self.generate_stairs_and_ramps()
            self.generate_gates()
            self.generate_pois()
            self.generate_seats_and_aisles()
            
            # Insert nodes
            for node_data in self.nodes_data:
                db.add(Node(**node_data))
            
            # Insert edges
            for edge_data in self.edges_data:
                db.add(Edge(**edge_data))
            
            db.commit()
            
            # Rebuild grid
            grid_manager = GridManager(cell_size=5.0, origin_x=0.0, origin_y=0.0)
            tile_count = grid_manager.rebuild_grid(db)
            
            print(f"\n{'='*70}")
            print("RESUMO:")
            print(f"   Total nodes: {len(self.nodes_data)}")
            print(f"   Total edges: {len(self.edges_data)}")
            print(f"   Total tiles: {tile_count}")
            print(f"{'='*70}\n")
            
        except Exception as e:
            db.rollback()
            print(f"Error: {e}")
            raise
        finally:
            db.close()


def main():
    if len(sys.argv) < 2:
        config_path = "stadiums/dragao_config.json"
        print(f"Using default config: {config_path}")
    else:
        config_path = sys.argv[1]
    
    loader = StadiumLoader(config_path)
    loader.load_to_database()
    print("Done!")


if __name__ == "__main__":
    main()
