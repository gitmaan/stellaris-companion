"""Pytest configuration and shared fixtures for Stellaris save extractor tests."""

import os
import sys

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")


@pytest.fixture(scope="session")
def project_root():
    """Return the project root directory."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def test_save_path(project_root):
    """Return path to test save file, skip if not found."""
    path = os.path.join(project_root, "test_save.sav")
    if not os.path.exists(path):
        pytest.skip(f"Test save file not found at {path}")
    return path


@pytest.fixture(scope="session")
def extractor(test_save_path):
    """Create a SaveExtractor with Rust session (session-scoped for performance).

    Most extractors require an active Rust session for fast data access.
    """
    from stellaris_save_extractor.extractor import SaveExtractor

    try:
        from stellaris_companion.rust_bridge import session as rust_session
    except ImportError:
        pytest.skip("Rust bridge not available")
        return

    with rust_session(test_save_path):
        extractor = SaveExtractor(test_save_path)
        yield extractor


@pytest.fixture(scope="session")
def validator(test_save_path):
    """Create an ExtractionValidator with Rust session (session-scoped).

    The validator's extractor requires an active Rust session.
    """
    from stellaris_save_extractor.validation import ExtractionValidator

    try:
        from stellaris_companion.rust_bridge import session as rust_session
    except ImportError:
        pytest.skip("Rust bridge not available")
        return

    with rust_session(test_save_path):
        validator = ExtractionValidator(test_save_path)
        yield validator


@pytest.fixture(scope="module")
def rust_session_extractor(test_save_path):
    """Create a SaveExtractor with active Rust session (module-scoped).

    This fixture starts a Rust session and yields an extractor that can use
    session-based methods like get_species_full(), get_leaders(), etc.

    The session is automatically closed when the test module completes.
    """
    from stellaris_save_extractor.extractor import SaveExtractor

    try:
        from stellaris_companion.rust_bridge import session as rust_session
    except ImportError:
        pytest.skip("Rust bridge not available")
        return

    with rust_session(test_save_path):
        extractor = SaveExtractor(test_save_path)
        yield extractor
