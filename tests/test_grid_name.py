"""
Tests for GridManager and tile operations.
"""
import pytest
from grid_name import GridManager
from models import Tile, Node


class TestGridManager:
    """Test the GridManager class."""
    
    def test_grid_manager_initialization(self):
        """Test GridManager initialization with default parameters."""
        gm = GridManager()
        assert gm.cell_size == 5.0
        assert gm.origin_x == 0.0
        assert gm.origin_y == 0.0
    
    def test_grid_manager_custom_params(self):
        """Test GridManager with custom parameters."""
        gm = GridManager(cell_size=10.0, origin_x=100.0, origin_y=200.0)
        assert gm.cell_size == 10.0
        assert gm.origin_x == 100.0
        assert gm.origin_y == 200.0
    
    def test_get_cell_coords_origin(self):
        """Test getting cell coordinates at origin."""
        gm = GridManager(cell_size=5.0, origin_x=0.0, origin_y=0.0)
        gx, gy = gm.get_cell_coords(0.0, 0.0)
        assert gx == 0
        assert gy == 0
    
    def test_get_cell_coords_positive(self):
        """Test getting cell coordinates for positive values."""
        gm = GridManager(cell_size=5.0, origin_x=0.0, origin_y=0.0)
        
        # Point at (12, 7) should be in cell (2, 1)
        gx, gy = gm.get_cell_coords(12.0, 7.0)
        assert gx == 2
        assert gy == 1
    
    def test_get_cell_coords_negative(self):
        """Test getting cell coordinates for negative values."""
        gm = GridManager(cell_size=5.0, origin_x=0.0, origin_y=0.0)
        
        # Point at (-3, -8) should be in cell (-1, -2)
        gx, gy = gm.get_cell_coords(-3.0, -8.0)
        assert gx == -1
        assert gy == -2
    
    def test_get_cell_coords_with_offset_origin(self):
        """Test cell coordinates with non-zero origin."""
        gm = GridManager(cell_size=10.0, origin_x=50.0, origin_y=100.0)
        
        # Point at (55, 110) should be in cell (0, 1)
        gx, gy = gm.get_cell_coords(55.0, 110.0)
        assert gx == 0
        assert gy == 1
    
    def test_get_cell_bounds(self):
        """Test getting cell boundary coordinates."""
        gm = GridManager(cell_size=5.0, origin_x=0.0, origin_y=0.0)
        
        min_x, max_x, min_y, max_y = gm.get_cell_bounds(0, 0)
        assert min_x == 0.0
        assert max_x == 5.0
        assert min_y == 0.0
        assert max_y == 5.0
    
    def test_get_cell_bounds_non_origin(self):
        """Test getting cell bounds for non-origin cell."""
        gm = GridManager(cell_size=5.0, origin_x=0.0, origin_y=0.0)
        
        min_x, max_x, min_y, max_y = gm.get_cell_bounds(2, 3)
        assert min_x == 10.0
        assert max_x == 15.0
        assert min_y == 15.0
        assert max_y == 20.0
    
    def test_get_cell_bounds_with_custom_origin(self):
        """Test cell bounds with custom origin and cell size."""
        gm = GridManager(cell_size=10.0, origin_x=100.0, origin_y=200.0)
        
        min_x, max_x, min_y, max_y = gm.get_cell_bounds(1, 1)
        assert min_x == 110.0
        assert max_x == 120.0
        assert min_y == 210.0
        assert max_y == 220.0


class TestTileCreation:
    """Test tile creation and management."""
    
    def test_get_or_create_tile_new(self, test_db):
        """Test creating a new tile."""
        gm = GridManager()
        tile = gm.get_or_create_tile(test_db, x=12.0, y=7.0, level=0)
        
        assert tile is not None
        assert tile.id == "tile_2_1_0"
        assert tile.grid_x == 2
        assert tile.grid_y == 1
        assert tile.level == 0
        assert tile.walkable is True
    
    def test_get_or_create_tile_existing(self, test_db):
        """Test retrieving an existing tile."""
        gm = GridManager()
        
        # Create tile
        tile1 = gm.get_or_create_tile(test_db, x=12.0, y=7.0, level=0)
        tile1_id = tile1.id
        
        # Get the same tile again
        tile2 = gm.get_or_create_tile(test_db, x=14.0, y=9.0, level=0)
        
        # Should be the same tile (both points in same cell)
        assert tile2.id == tile1_id
        
        # Verify only one tile exists in database
        count = test_db.query(Tile).count()
        assert count == 1
    
    def test_get_or_create_tile_different_levels(self, test_db):
        """Test creating tiles on different levels."""
        gm = GridManager()
        
        tile_level_0 = gm.get_or_create_tile(test_db, x=10.0, y=10.0, level=0)
        tile_level_1 = gm.get_or_create_tile(test_db, x=10.0, y=10.0, level=1)
        
        assert tile_level_0.id != tile_level_1.id
        assert tile_level_0.level == 0
        assert tile_level_1.level == 1
    
    def test_tile_bounds_correct(self, test_db):
        """Test that created tiles have correct bounds."""
        gm = GridManager(cell_size=5.0)
        tile = gm.get_or_create_tile(test_db, x=12.0, y=7.0, level=0)
        
        assert tile.min_x == 10.0
        assert tile.max_x == 15.0
        assert tile.min_y == 5.0
        assert tile.max_y == 10.0


class TestEntityAssignment:
    """Test assigning entities to tiles."""
    
    def test_assign_node_to_cell(self, test_db):
        """Test assigning a node to a cell."""
        gm = GridManager()
        
        node = Node(id="N1", x=12.0, y=7.0)
        test_db.add(node)
        test_db.commit()
        
        tile = gm.assign_entity_to_cell(test_db, 12.0, 7.0, 0, "node", node)
        
        assert tile is not None
        assert "N1" in tile.node_id
    
    def test_assign_poi_to_cell(self, test_db):
        """Test assigning a POI to a cell."""
        gm = GridManager()
        
        poi = Node(id="POI1", x=12.0, y=7.0, type="restroom")
        test_db.add(poi)
        test_db.commit()
        
        tile = gm.assign_entity_to_cell(test_db, 12.0, 7.0, 0, "poi", poi)
        
        assert "POI1" in tile.poi_id
    
    def test_assign_seat_to_cell(self, test_db):
        """Test assigning a seat to a cell."""
        gm = GridManager()
        
        seat = Node(id="SEAT1", x=12.0, y=7.0, type="seat")
        test_db.add(seat)
        test_db.commit()
        
        tile = gm.assign_entity_to_cell(test_db, 12.0, 7.0, 0, "seat", seat)
        
        assert "SEAT1" in tile.seat_id
    
    def test_assign_gate_to_cell(self, test_db):
        """Test assigning a gate to a cell."""
        gm = GridManager()
        
        gate = Node(id="GATE1", x=12.0, y=7.0, type="gate")
        test_db.add(gate)
        test_db.commit()
        
        tile = gm.assign_entity_to_cell(test_db, 12.0, 7.0, 0, "gate", gate)
        
        assert "GATE1" in tile.gate_id
    
    def test_assign_multiple_entities_to_same_cell(self, test_db):
        """Test assigning multiple entities to the same cell."""
        gm = GridManager()
        
        node1 = Node(id="N1", x=12.0, y=7.0)
        node2 = Node(id="N2", x=13.0, y=8.0)
        test_db.add_all([node1, node2])
        test_db.commit()
        
        gm.assign_entity_to_cell(test_db, 12.0, 7.0, 0, "node", node1)
        tile = gm.assign_entity_to_cell(test_db, 13.0, 8.0, 0, "node", node2)
        
        assert "N1" in tile.node_id
        assert "N2" in tile.node_id
    
    def test_append_id_helper(self):
        """Test the _append_id helper method."""
        gm = GridManager()
        
        # Append to empty string
        result = gm._append_id("", "ID1")
        assert result == "ID1"
        
        # Append to existing
        result = gm._append_id("ID1", "ID2")
        assert result == "ID1,ID2"
        
        # Don't duplicate
        result = gm._append_id("ID1,ID2", "ID1")
        assert result == "ID1,ID2"
        
        # Append to None
        result = gm._append_id(None, "ID1")
        assert result == "ID1"


class TestGetEntitiesInCell:
    """Test retrieving entities from cells."""
    
    def test_get_entities_empty_cell(self, test_db):
        """Test getting entities from a non-existent cell."""
        gm = GridManager()
        
        result = gm.get_entities_in_cell(test_db, 0, 0, 0)
        
        assert result["nodes"] == []
        assert result["pois"] == []
        assert result["seats"] == []
        assert result["gates"] == []
        assert result["tile"] is None
    
    def test_get_entities_with_nodes(self, test_db):
        """Test getting entities from a cell with nodes."""
        gm = GridManager()
        
        # Create and assign nodes
        node1 = Node(id="N1", x=12.0, y=7.0, type="corridor")
        node2 = Node(id="N2", x=13.0, y=8.0, type="corridor")
        test_db.add_all([node1, node2])
        test_db.commit()
        
        gm.assign_entity_to_cell(test_db, 12.0, 7.0, 0, "node", node1)
        gm.assign_entity_to_cell(test_db, 13.0, 8.0, 0, "node", node2)
        
        # Get entities
        result = gm.get_entities_in_cell(test_db, 2, 1, 0)
        
        assert len(result["nodes"]) == 2
        node_ids = [n.id for n in result["nodes"]]
        assert "N1" in node_ids
        assert "N2" in node_ids
    
    def test_get_entities_mixed_types(self, test_db):
        """Test getting entities of different types from the same cell."""
        gm = GridManager()
        
        # Create different entity types
        node = Node(id="N1", x=12.0, y=7.0, type="corridor")
        poi = Node(id="POI1", x=12.5, y=7.5, type="restroom")
        seat = Node(id="SEAT1", x=13.0, y=8.0, type="seat")
        gate = Node(id="GATE1", x=13.5, y=8.5, type="gate")
        
        test_db.add_all([node, poi, seat, gate])
        test_db.commit()
        
        # Assign to cell
        gm.assign_entity_to_cell(test_db, 12.0, 7.0, 0, "node", node)
        gm.assign_entity_to_cell(test_db, 12.5, 7.5, 0, "poi", poi)
        gm.assign_entity_to_cell(test_db, 13.0, 8.0, 0, "seat", seat)
        gm.assign_entity_to_cell(test_db, 13.5, 8.5, 0, "gate", gate)
        
        # Get all entities
        result = gm.get_entities_in_cell(test_db, 2, 1, 0)
        
        assert len(result["nodes"]) == 1
        assert len(result["pois"]) == 1
        assert len(result["seats"]) == 1
        assert len(result["gates"]) == 1
        assert result["nodes"][0].id == "N1"
        assert result["pois"][0].id == "POI1"
        assert result["seats"][0].id == "SEAT1"
        assert result["gates"][0].id == "GATE1"
    
    def test_get_entities_returns_tile(self, test_db):
        """Test that get_entities_in_cell returns the tile object."""
        gm = GridManager()
        
        # Create a tile
        tile = gm.get_or_create_tile(test_db, 12.0, 7.0, 0)
        
        # Get entities (should return the tile even if empty)
        result = gm.get_entities_in_cell(test_db, 2, 1, 0)
        
        assert result["tile"] is not None
        assert result["tile"].id == tile.id


class TestGridManagerEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_cell_coords_boundary(self):
        """Test cell coordinates at exact cell boundaries."""
        gm = GridManager(cell_size=5.0, origin_x=0.0, origin_y=0.0)
        
        # Point exactly at cell boundary
        gx, gy = gm.get_cell_coords(5.0, 5.0)
        assert gx == 1
        assert gy == 1
        
        # Point just before boundary
        gx, gy = gm.get_cell_coords(4.999, 4.999)
        assert gx == 0
        assert gy == 0
    
    def test_large_coordinates(self):
        """Test with very large coordinate values."""
        gm = GridManager()
        
        gx, gy = gm.get_cell_coords(10000.0, 10000.0)
        assert gx == 2000
        assert gy == 2000
    
    def test_very_small_cell_size(self):
        """Test with very small cell size."""
        gm = GridManager(cell_size=0.1)
        
        gx, gy = gm.get_cell_coords(1.0, 1.0)
        assert gx == 10
        assert gy == 10
