"""
Floor Plan to Navigation Graph Converter using OpenCV

This script processes floor plan images and attempts to automatically extract
navigation nodes and edges using computer vision techniques.

Process:
1. Load and preprocess image (grayscale, threshold)
2. Detect walkable areas (corridors) using morphological operations
3. Skeletonize to get center lines of corridors
4. Extract nodes at intersections and endpoints
5. Create edges between nearby nodes
6. Export to JSON format

Usage:
    python floor_plan_to_graph.py deti_plans/teachers-1.png
"""

import cv2
import numpy as np
from scipy import ndimage
from skimage.morphology import skeletonize
from skimage import img_as_ubyte
import json
import sys
import os


class FloorPlanProcessor:
    """Processes floor plan images to extract navigation graphs."""
    
    def __init__(self, image_path: str):
        self.image_path = image_path
        self.original = cv2.imread(image_path)
        if self.original is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        self.height, self.width = self.original.shape[:2]
        self.nodes = []
        self.edges = []
        
    def preprocess(self):
        """Convert to grayscale and apply threshold to isolate corridors."""
        # Convert to grayscale
        gray = cv2.cvtColor(self.original, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # Use adaptive threshold - better for floor plans with text
        # This will detect dark lines (walls) on light background
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # Detect lines (walls) using Hough transform or morphology
        # Use morphological closing to connect nearby wall segments
        kernel_close = np.ones((5, 5), np.uint8)
        walls = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_close, iterations=3)
        
        # Dilate walls to make them thicker
        kernel_dilate = np.ones((3, 3), np.uint8)
        walls_thick = cv2.dilate(walls, kernel_dilate, iterations=2)
        
        # Invert to get walkable areas (white = walkable)
        walkable = cv2.bitwise_not(walls_thick)
        
        # Clean up small noise areas
        kernel_open = np.ones((5, 5), np.uint8)
        cleaned = cv2.morphologyEx(walkable, cv2.MORPH_OPEN, kernel_open, iterations=2)
        
        self.walkable = cleaned
        self.walls = walls_thick
        return cleaned
    
    def find_corridors(self):
        """Detect main corridor areas using connected components."""
        # Find connected components (potential corridor areas)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            self.walkable, connectivity=8
        )
        
        # Filter by area - corridors are typically medium-to-large regions
        min_area = 1000  # Minimum area in pixels
        max_area = self.width * self.height * 0.7  # Max 70% of image
        
        corridor_mask = np.zeros_like(self.walkable)
        
        # Keep the largest connected components (likely the main corridors)
        areas = []
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if min_area < area < max_area:
                areas.append((i, area))
        
        # Sort by area and keep top components
        areas.sort(key=lambda x: x[1], reverse=True)
        for label_id, area in areas[:10]:  # Keep top 10 largest
            corridor_mask[labels == label_id] = 255
        
        self.corridor_mask = corridor_mask
        return corridor_mask
    
    def skeletonize_corridors(self):
        """Create skeleton of corridor areas to get center lines."""
        # Convert to binary (0 or 1)
        binary = self.corridor_mask > 0
        
        # Skeletonize
        skeleton = skeletonize(binary)
        
        # Convert back to uint8
        self.skeleton = img_as_ubyte(skeleton)
        return self.skeleton
    
    def extract_nodes(self, min_distance: int = 30):
        """Extract nodes from skeleton - at intersections and endpoints."""
        skeleton = self.skeleton.copy()
        
        # Find all non-zero points in skeleton
        points = np.column_stack(np.nonzero(skeleton))
        
        if len(points) == 0:
            print("Warning: No skeleton points found!")
            return []
        
        # Define kernels for detecting special points
        # Endpoints have only 1 neighbor
        # Intersections have 3+ neighbors
        
        nodes = []
        node_id = 1
        
        # Sample points along skeleton at regular intervals
        # This is a simplified approach - we're sampling every N pixels
        step = min_distance
        
        for i in range(0, len(points), step):
            y, x = points[i]
            
            # Check 3x3 neighborhood to count neighbors
            neighborhood = skeleton[max(0,y-1):y+2, max(0,x-1):x+2]
            neighbors = np.sum(neighborhood > 0) - 1  # Subtract the point itself
            
            # Determine node type based on neighbor count
            if neighbors == 2:
                node_type = "corridor"
            elif neighbors == 1:
                node_type = "endpoint"
            else:
                node_type = "intersection"
            
            # Add as node if it's an endpoint or intersection, or just at intervals
            nodes.append({
                "id": f"N{node_id}",
                "x": float(x),
                "y": float(y),
                "type": node_type,
                "neighbors": int(neighbors)
            })
            node_id += 1
        
        # Also add endpoints explicitly
        for y, x in points:
            neighborhood = skeleton[max(0,y-1):y+2, max(0,x-1):x+2]
            neighbors = np.sum(neighborhood > 0) - 1
            
            if neighbors == 1:  # Endpoint
                # Check if we don't already have a node nearby
                is_duplicate = False
                for n in nodes:
                    dist = np.sqrt((n['x'] - x)**2 + (n['y'] - y)**2)
                    if dist < min_distance / 2:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    nodes.append({
                        "id": f"N{node_id}",
                        "x": float(x),
                        "y": float(y),
                        "type": "endpoint",
                        "neighbors": 1
                    })
                    node_id += 1
        
        # Find intersections (3+ neighbors)
        for y, x in points:
            neighborhood = skeleton[max(0,y-1):y+2, max(0,x-1):x+2]
            neighbors = np.sum(neighborhood > 0) - 1
            
            if neighbors >= 3:  # Intersection
                is_duplicate = False
                for n in nodes:
                    dist = np.sqrt((n['x'] - x)**2 + (n['y'] - y)**2)
                    if dist < min_distance / 2:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    nodes.append({
                        "id": f"N{node_id}",
                        "x": float(x),
                        "y": float(y),
                        "type": "intersection",
                        "neighbors": int(neighbors)
                    })
                    node_id += 1
        
        self.nodes = nodes
        print(f"   Extracted {len(nodes)} nodes")
        return nodes
    
    def create_edges(self, max_distance: int = 60):
        """Create edges between nearby nodes."""
        edges = []
        edge_id = 1
        
        for i, n1 in enumerate(self.nodes):
            for j, n2 in enumerate(self.nodes):
                if i >= j:  # Skip self and already processed pairs
                    continue
                
                # Calculate distance
                dist = np.sqrt((n1['x'] - n2['x'])**2 + (n1['y'] - n2['y'])**2)
                
                if dist < max_distance:
                    # Check if there's a corridor path between them
                    # (simplified: just check if distance is reasonable)
                    edges.append({
                        "id": f"E{edge_id}",
                        "from_id": n1['id'],
                        "to_id": n2['id'],
                        "weight": float(dist / 10),  # Convert to walking weight
                        "accessible": True
                    })
                    edge_id += 1
        
        self.edges = edges
        print(f"   Created {len(edges)} edges")
        return edges
    
    def visualize(self, output_path: str = None):
        """Create visualization of extracted graph overlaid on original."""
        vis = self.original.copy()
        
        # Draw edges
        for edge in self.edges:
            n1 = next(n for n in self.nodes if n['id'] == edge['from_id'])
            n2 = next(n for n in self.nodes if n['id'] == edge['to_id'])
            pt1 = (int(n1['x']), int(n1['y']))
            pt2 = (int(n2['x']), int(n2['y']))
            cv2.line(vis, pt1, pt2, (0, 255, 0), 2)
        
        # Draw nodes
        for node in self.nodes:
            pt = (int(node['x']), int(node['y']))
            color = (0, 0, 255) if node['type'] == 'intersection' else (255, 0, 0)
            radius = 8 if node['type'] == 'intersection' else 5
            cv2.circle(vis, pt, radius, color, -1)
        
        if output_path:
            cv2.imwrite(output_path, vis)
            print(f"   Saved visualization to {output_path}")
        
        return vis
    
    def export_json(self, output_path: str):
        """Export nodes and edges to JSON format."""
        data = {
            "source_image": os.path.basename(self.image_path),
            "image_dimensions": {"width": self.width, "height": self.height},
            "nodes": self.nodes,
            "edges": self.edges,
            "stats": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
                "intersections": len([n for n in self.nodes if n['type'] == 'intersection']),
                "endpoints": len([n for n in self.nodes if n['type'] == 'endpoint'])
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"   Exported graph to {output_path}")
        return data
    
    def process(self, output_dir: str = None):
        """Run full processing pipeline."""
        print(f"\n{'='*60}")
        print(f"Processing: {self.image_path}")
        print(f"Image size: {self.width}x{self.height}")
        print(f"{'='*60}\n")
        
        print("1. Preprocessing image...")
        self.preprocess()
        
        print("2. Finding corridor areas...")
        self.find_corridors()
        
        print("3. Skeletonizing corridors...")
        self.skeletonize_corridors()
        
        print("4. Extracting nodes...")
        self.extract_nodes()
        
        print("5. Creating edges...")
        self.create_edges()
        
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            base_name = os.path.splitext(os.path.basename(self.image_path))[0]
            
            # Save intermediate images for debugging
            cv2.imwrite(f"{output_dir}/{base_name}_walkable.png", self.walkable)
            cv2.imwrite(f"{output_dir}/{base_name}_corridors.png", self.corridor_mask)
            cv2.imwrite(f"{output_dir}/{base_name}_skeleton.png", self.skeleton)
            
            # Save visualization and JSON
            self.visualize(f"{output_dir}/{base_name}_graph.png")
            self.export_json(f"{output_dir}/{base_name}_graph.json")
        
        print(f"\n{'='*60}")
        print("SUMMARY:")
        print(f"   Nodes: {len(self.nodes)}")
        print(f"   Edges: {len(self.edges)}")
        print(f"   Intersections: {len([n for n in self.nodes if n['type'] == 'intersection'])}")
        print(f"{'='*60}\n")
        
        return self.nodes, self.edges


def main():
    if len(sys.argv) < 2:
        print("Usage: python floor_plan_to_graph.py <image_path> [output_dir]")
        print("Example: python floor_plan_to_graph.py deti_plans/teachers-1.png deti_plans/output")
        sys.exit(1)
    
    image_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "deti_plans/output"
    
    processor = FloorPlanProcessor(image_path)
    processor.process(output_dir)


if __name__ == "__main__":
    main()
