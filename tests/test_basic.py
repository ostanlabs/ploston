"""Basic test to verify test infrastructure works."""


def test_basic() -> None:
    """Test that basic assertions work."""
    assert True


def test_import_ael() -> None:
    """Test that we can import the ael package."""
    import ploston_core

    assert ael.__version__ == "0.1.0"
