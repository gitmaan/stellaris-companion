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
    """Create a SaveExtractor instance for the test save (session-scoped for performance)."""
    from stellaris_save_extractor.extractor import SaveExtractor

    return SaveExtractor(test_save_path)


@pytest.fixture(scope="session")
def validator(test_save_path):
    """Create an ExtractionValidator instance for the test save (session-scoped)."""
    from stellaris_save_extractor.validation import ExtractionValidator

    return ExtractionValidator(test_save_path)
