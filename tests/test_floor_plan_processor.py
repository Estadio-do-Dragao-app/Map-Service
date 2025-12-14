"""
Tests for floor_plan_to_graph.py module.
"""
import pytest
import numpy as np
import cv2
import json
import os
import tempfile
from floor_plan_to_graph import FloorPlanProcessor


@pytest.fixture
def sample_floor_plan_image():
    """Create a simple synthetic floor plan image for testing."""
    # Create a 200x200 white image (background)
    img = np.ones((200, 200, 3), dtype=np.uint8) * 255
    
    # Draw a simple corridor (black lines represent walkable areas)
    # Horizontal corridor
    cv2.rectangle(img, (20, 90), (180, 110), (0, 0, 0), -1)
    # Vertical corridor
    cv2.rectangle(img, (90, 20), (110, 180), (0, 0, 0), -1)
    
    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    cv2.imwrite(temp_file.name, img)
    temp_file.close()
    
    yield temp_file.name
    
    # Cleanup
    if os.path.exists(temp_file.name):
        os.unlink(temp_file.name)


@pytest.fixture
def temp_output_dir():
    """Create temporary output directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    
    # Cleanup
    import shutil
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)


class TestFloorPlanProcessor:
    """Test FloorPlanProcessor class."""
    
    def test_init_with_valid_image(self, sample_floor_plan_image):
        """Test initialization with valid image."""
        processor = FloorPlanProcessor(sample_floor_plan_image)
        assert processor.original is not None
        assert processor.height == 200
        assert processor.width == 200
        assert processor.nodes == []
        assert processor.edges == []
    
    def test_init_with_invalid_image(self):
        """Test initialization with invalid image path."""
        with pytest.raises(ValueError, match="Could not load image"):
            FloorPlanProcessor("nonexistent_image.png")
    
    def test_preprocess(self, sample_floor_plan_image):
        """Test image preprocessing."""
        processor = FloorPlanProcessor(sample_floor_plan_image)
        processor.preprocess()
        
        assert hasattr(processor, 'walkable')
        assert processor.walkable is not None
        assert processor.walkable.shape == (200, 200)
        assert processor.walkable.dtype == np.uint8
    
    def test_find_corridors(self, sample_floor_plan_image):
        """Test corridor detection."""
        processor = FloorPlanProcessor(sample_floor_plan_image)
        processor.preprocess()
        corridor_mask = processor.find_corridors()
        
        assert corridor_mask is not None
        assert hasattr(processor, 'corridor_mask')
        assert processor.corridor_mask.shape == (200, 200)
        # Should have some corridor pixels detected
        assert np.any(processor.corridor_mask > 0)
    
    def test_skeletonize_corridors(self, sample_floor_plan_image):
        """Test corridor skeletonization."""
        processor = FloorPlanProcessor(sample_floor_plan_image)
        processor.preprocess()
        processor.find_corridors()
        skeleton = processor.skeletonize_corridors()
        
        assert skeleton is not None
        assert hasattr(processor, 'skeleton')
        assert processor.skeleton.shape == (200, 200)
        assert processor.skeleton.dtype == np.uint8
    
    def test_extract_nodes(self, sample_floor_plan_image):
        """Test node extraction from skeleton."""
        processor = FloorPlanProcessor(sample_floor_plan_image)
        processor.preprocess()
        processor.find_corridors()
        processor.skeletonize_corridors()
        nodes = processor.extract_nodes(min_distance=20)
        
        assert nodes is not None
        assert isinstance(nodes, list)
        assert len(processor.nodes) >= 0
        
        # Check node structure if any nodes were extracted
        if len(nodes) > 0:
            node = nodes[0]
            assert 'id' in node
            assert 'x' in node
            assert 'y' in node
            assert 'type' in node
            assert 'neighbors' in node
            assert node['type'] in ['corridor', 'endpoint', 'intersection']
    
    def test_create_edges(self, sample_floor_plan_image):
        """Test edge creation between nodes."""
        processor = FloorPlanProcessor(sample_floor_plan_image)
        processor.preprocess()
        processor.find_corridors()
        processor.skeletonize_corridors()
        processor.extract_nodes()
        edges = processor.create_edges(max_distance=100)
        
        assert edges is not None
        assert isinstance(edges, list)
        assert len(processor.edges) >= 0
        
        # Check edge structure if any edges were created
        if len(edges) > 0:
            edge = edges[0]
            assert 'id' in edge
            assert 'from_id' in edge
            assert 'to_id' in edge
            assert 'weight' in edge
            assert 'accessible' in edge
            assert isinstance(edge['weight'], float)
    
    def test_visualize(self, sample_floor_plan_image, temp_output_dir):
        """Test visualization generation."""
        processor = FloorPlanProcessor(sample_floor_plan_image)
        processor.preprocess()
        processor.find_corridors()
        processor.skeletonize_corridors()
        processor.extract_nodes()
        processor.create_edges()
        
        output_path = os.path.join(temp_output_dir, "test_vis.png")
        vis = processor.visualize(output_path)
        
        assert vis is not None
        assert vis.shape == (200, 200, 3)
        assert os.path.exists(output_path)
    
    def test_export_json(self, sample_floor_plan_image, temp_output_dir):
        """Test JSON export."""
        processor = FloorPlanProcessor(sample_floor_plan_image)
        processor.preprocess()
        processor.find_corridors()
        processor.skeletonize_corridors()
        processor.extract_nodes()
        processor.create_edges()
        
        output_path = os.path.join(temp_output_dir, "test_graph.json")
        data = processor.export_json(output_path)
        
        assert data is not None
        assert os.path.exists(output_path)
        
        # Verify JSON structure
        assert "source_image" in data
        assert "image_dimensions" in data
        assert "nodes" in data
        assert "edges" in data
        assert "stats" in data
        
        assert data["image_dimensions"]["width"] == 200
        assert data["image_dimensions"]["height"] == 200
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
        
        # Verify stats
        stats = data["stats"]
        assert "total_nodes" in stats
        assert "total_edges" in stats
        assert "intersections" in stats
        assert "endpoints" in stats
        
        # Verify JSON is valid by reading it back
        with open(output_path, 'r') as f:
            loaded_data = json.load(f)
        assert loaded_data == data
    
    def test_full_process_pipeline(self, sample_floor_plan_image, temp_output_dir):
        """Test full processing pipeline."""
        processor = FloorPlanProcessor(sample_floor_plan_image)
        nodes, edges = processor.process(temp_output_dir)
        
        assert isinstance(nodes, list)
        assert isinstance(edges, list)
        
        # Check that intermediate files were created
        base_name = os.path.splitext(os.path.basename(sample_floor_plan_image))[0]
        assert os.path.exists(os.path.join(temp_output_dir, f"{base_name}_walkable.png"))
        assert os.path.exists(os.path.join(temp_output_dir, f"{base_name}_corridors.png"))
        assert os.path.exists(os.path.join(temp_output_dir, f"{base_name}_skeleton.png"))
        assert os.path.exists(os.path.join(temp_output_dir, f"{base_name}_graph.png"))
        assert os.path.exists(os.path.join(temp_output_dir, f"{base_name}_graph.json"))
    
    def test_process_without_output_dir(self, sample_floor_plan_image):
        """Test process without output directory."""
        processor = FloorPlanProcessor(sample_floor_plan_image)
        nodes, edges = processor.process(output_dir=None)
        
        assert isinstance(nodes, list)
        assert isinstance(edges, list)
        # Should not create any files when output_dir is None
    
    def test_node_deduplication(self, sample_floor_plan_image):
        """Test that duplicate nodes are filtered out."""
        processor = FloorPlanProcessor(sample_floor_plan_image)
        processor.preprocess()
        processor.find_corridors()
        processor.skeletonize_corridors()
        processor.extract_nodes(min_distance=30)
        
        # Check that no two nodes are too close together
        for i, n1 in enumerate(processor.nodes):
            for j, n2 in enumerate(processor.nodes):
                if i >= j:
                    continue
                dist = np.sqrt((n1['x'] - n2['x'])**2 + (n1['y'] - n2['y'])**2)
                assert dist >= 15  # Half of min_distance
    
    def test_edge_weight_calculation(self, sample_floor_plan_image):
        """Test that edge weights are calculated correctly."""
        processor = FloorPlanProcessor(sample_floor_plan_image)
        processor.preprocess()
        processor.find_corridors()
        processor.skeletonize_corridors()
        processor.extract_nodes()
        processor.create_edges()
        
        for edge in processor.edges:
            # Find the nodes
            n1 = next(n for n in processor.nodes if n['id'] == edge['from_id'])
            n2 = next(n for n in processor.nodes if n['id'] == edge['to_id'])
            
            # Calculate expected distance
            expected_dist = np.sqrt((n1['x'] - n2['x'])**2 + (n1['y'] - n2['y'])**2)
            expected_weight = expected_dist / 10
            
            # Check weight is approximately correct
            assert abs(edge['weight'] - expected_weight) < 0.01


class TestFloorPlanProcessorEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_image(self):
        """Test with completely white image (no corridors)."""
        # Create empty white image
        img = np.ones((100, 100, 3), dtype=np.uint8) * 255
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        cv2.imwrite(temp_file.name, img)
        temp_file.close()
        
        try:
            processor = FloorPlanProcessor(temp_file.name)
            processor.preprocess()
            processor.find_corridors()
            processor.skeletonize_corridors()
            nodes = processor.extract_nodes()
            
            # Should handle empty case gracefully
            assert isinstance(nodes, list)
        finally:
            os.unlink(temp_file.name)
    
    def test_small_image(self):
        """Test with very small image."""
        # Create small 50x50 image
        img = np.ones((50, 50, 3), dtype=np.uint8) * 255
        cv2.rectangle(img, (10, 20), (40, 30), (0, 0, 0), -1)
        
        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        cv2.imwrite(temp_file.name, img)
        temp_file.close()
        
        try:
            processor = FloorPlanProcessor(temp_file.name)
            assert processor.width == 50
            assert processor.height == 50
            nodes, edges = processor.process()
            assert isinstance(nodes, list)
            assert isinstance(edges, list)
        finally:
            os.unlink(temp_file.name)
