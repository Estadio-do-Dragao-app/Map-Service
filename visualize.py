import matplotlib.pyplot as plt
import matplotlib.patches as patches
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Node, Edge, Gate, POI, Seat, Closure
import numpy as np

def visualize_stadium_matplotlib():
    """Visualização com matplotlib"""
    db: Session = SessionLocal()
    
    try:
        # Buscar dados
        nodes = db.query(Node).all()
        edges = db.query(Edge).all()
        gates = db.query(Gate).all()
        pois = db.query(POI).all()
        closures = db.query(Closure).all()
        
        # Criar figura
        fig, axes = plt.subplots(1, 2, figsize=(16, 8))
        
        # ========== PLOT 1: Layout do Estádio ==========
        ax1 = axes[0]
        ax1.set_title('Stadium Layout - Navigation Graph', fontsize=14)
        ax1.set_xlabel('X Coordinate')
        ax1.set_ylabel('Y Coordinate')
        ax1.grid(True, alpha=0.3)
        
        # Plot nodes
        node_colors = {'normal': 'blue', 'stairs': 'red'}
        for node in nodes:
            color = node_colors.get(node.type, 'gray')
            ax1.scatter(node.x, node.y, color=color, s=50, alpha=0.7, 
                       label='Stairs' if node.type == 'stairs' and node.id == 'N15' else '')
            
            # Add node labels for important nodes
            if node.id in ['N1', 'N5', 'N10', 'N15', 'N20']:
                ax1.annotate(node.id, (node.x, node.y), 
                           xytext=(5, 5), textcoords='offset points', fontsize=8)
        
        # Plot edges
        for edge in edges:
            from_node = next((n for n in nodes if n.id == edge.from_id), None)
            to_node = next((n for n in nodes if n.id == edge.to_id), None)
            
            if from_node and to_node:
                ax1.plot([from_node.x, to_node.x], [from_node.y, to_node.y], 
                        'gray', alpha=0.5, linewidth=1)
        
        # Plot gates
        gate_x = [g.x for g in gates]
        gate_y = [g.y for g in gates]
        ax1.scatter(gate_x, gate_y, color='green', s=100, marker='s', 
                   label='Gates', edgecolors='black')
        
        for gate in gates:
            ax1.annotate(f'Gate {gate.gate_number}', (gate.x, gate.y),
                       xytext=(10, 0), textcoords='offset points',
                       fontsize=9, fontweight='bold')
        
        # Plot POIs
        poi_categories = set(p.category for p in pois)
        colors = plt.cm.tab10(np.linspace(0, 1, len(poi_categories)))
        color_map = {cat: colors[i] for i, cat in enumerate(poi_categories)}
        
        for poi in pois:
            ax1.scatter(poi.x, poi.y, color=color_map[poi.category], 
                       s=80, marker='^', edgecolors='black')
            ax1.annotate(poi.name.split()[0], (poi.x, poi.y),
                       xytext=(5, -15), textcoords='offset points',
                       fontsize=8, alpha=0.8)
        
        # Add legend
        ax1.legend(loc='upper right')
        
        # ========== PLOT 2: Seats Distribution ==========
        ax2 = axes[1]
        ax2.set_title('Seating Arrangement', fontsize=14)
        ax2.set_xlabel('X Coordinate')
        ax2.set_ylabel('Y Coordinate')
        
        # Get seats (limit for performance)
        seats = db.query(Seat).limit(200).all()
        
        # Group seats by block
        blocks = {}
        for seat in seats:
            if seat.block not in blocks:
                blocks[seat.block] = {'x': [], 'y': []}
            blocks[seat.block]['x'].append(seat.x)
            blocks[seat.block]['y'].append(seat.y)
        
        # Plot each block with different color
        block_colors = {'A': 'red', 'B': 'blue', 'C': 'green'}
        for block, data in blocks.items():
            color = block_colors.get(block, 'gray')
            ax2.scatter(data['x'], data['y'], color=color, s=10, 
                       alpha=0.5, label=f'Block {block}')
        
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Add closure information as text
        closure_text = "Closures:\n" + "\n".join([
            f"• {c.id}: {c.reason}" for c in closures
        ])
        
        plt.figtext(0.02, 0.02, closure_text, fontsize=9, 
                   bbox=dict(boxstyle="round,pad=0.5", facecolor="yellow", alpha=0.5))
        
        plt.tight_layout()
        plt.show()
        
    finally:
        db.close()

if __name__ == "__main__":
    visualize_stadium_matplotlib()