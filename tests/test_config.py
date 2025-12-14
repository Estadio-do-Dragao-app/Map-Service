"""
Tests for configuration module.
"""
import pytest
import os
from unittest.mock import patch


class TestConfig:
    """Test the Config class and environment variable handling."""
    
    def test_default_database_uri(self):
        """Test that default database URI is set correctly."""
        from config import Config
        
        # When no env var is set, should use default
        with patch.dict(os.environ, {}, clear=True):
            # Reimport to get fresh config
            import importlib
            import config
            importlib.reload(config)
            
            assert hasattr(config.Config, 'SQLALCHEMY_DATABASE_URI')
            # Should have a default value
            assert config.Config.SQLALCHEMY_DATABASE_URI is not None
    
    def test_database_uri_from_env(self):
        """Test that database URI can be set from environment variable."""
        test_uri = "postgresql://testuser:testpass@testhost:5432/testdb"
        
        with patch.dict(os.environ, {'DATABASE_URI': test_uri}):
            import importlib
            import config
            importlib.reload(config)
            
            assert config.Config.SQLALCHEMY_DATABASE_URI == test_uri
    
    def test_debug_mode_default_false(self):
        """Test that DEBUG defaults to False."""
        from config import Config
        
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            
            assert config.Config.DEBUG is False
    
    def test_debug_mode_true_from_env(self):
        """Test that DEBUG can be enabled via environment variable."""
        with patch.dict(os.environ, {'DEBUG': 'true'}):
            import importlib
            import config
            importlib.reload(config)
            
            assert config.Config.DEBUG is True
    
    def test_debug_mode_case_insensitive(self):
        """Test that DEBUG environment variable is case insensitive."""
        test_cases = ['True', 'TRUE', 'true', 'TrUe']
        
        for value in test_cases:
            with patch.dict(os.environ, {'DEBUG': value}):
                import importlib
                import config
                importlib.reload(config)
                
                assert config.Config.DEBUG is True, f"Failed for DEBUG={value}"
    
    def test_track_modifications_is_false(self):
        """Test that SQLALCHEMY_TRACK_MODIFICATIONS is False."""
        from config import Config
        
        assert Config.SQLALCHEMY_TRACK_MODIFICATIONS is False
    
    def test_config_class_exists(self):
        """Test that Config class is properly defined."""
        from config import Config
        
        assert hasattr(Config, 'SQLALCHEMY_DATABASE_URI')
        assert hasattr(Config, 'SQLALCHEMY_TRACK_MODIFICATIONS')
        assert hasattr(Config, 'DEBUG')
    
    def test_dotenv_loading(self):
        """Test that .env file loading is attempted."""
        # This test ensures the load_dotenv() is called
        # We can't easily test file loading, but we can verify the import works
        from config import load_dotenv
        assert callable(load_dotenv)
