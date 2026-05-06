import sys
from pathlib import Path
import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

def test_import_database():
    """Test that database module can be imported"""
    from modules import database
    assert database is not None

def test_import_code():
    """Test that code module can be imported"""
    from modules import code
    assert code is not None

@pytest.mark.skipif(sys.platform == "win32", reason="Rust modules may not be built")
def test_import_chainlog_with_rust():
    """Test chainlog with Rust bindings (skip if not available)"""
    try:
        from modules import chainlog
        assert chainlog is not None
    except ImportError:
        pytest.skip("Rust bindings not available")

@pytest.mark.skipif(sys.platform == "win32", reason="Rust modules may not be built")
def test_import_exif_checker_with_rust():
    """Test exif_checker with Rust bindings (skip if not available)"""
    try:
        from modules import exif_checker
        assert exif_checker is not None
    except ImportError:
        pytest.skip("Rust bindings not available")