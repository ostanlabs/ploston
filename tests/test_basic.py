"""Basic test to verify test infrastructure works."""


def test_basic() -> None:
    """Test that basic assertions work."""
    assert True


def test_import_ploston() -> None:
    """Test that we can import the ploston package."""
    import ploston

    assert ploston.__version__ == "1.0.0"
