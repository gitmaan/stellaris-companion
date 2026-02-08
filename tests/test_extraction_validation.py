"""Tests for the extraction validation module.

Tests the ValidationResult dataclass and validate_all() integration.
"""

import os
import sys

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stellaris_save_extractor.validation import ExtractionValidator, ValidationResult

# Path to test save fixture
TEST_SAVE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_save.sav"
)


@pytest.fixture
def test_save_path():
    """Return path to test save file."""
    if not os.path.exists(TEST_SAVE_PATH):
        pytest.skip(f"Test save file not found at {TEST_SAVE_PATH}")
    return TEST_SAVE_PATH


@pytest.fixture
def validator(test_save_path):
    """Create a validator instance with Rust session."""
    try:
        from stellaris_companion.rust_bridge import session as rust_session
    except ImportError:
        pytest.skip("Rust bridge not available")
        return

    with rust_session(test_save_path):
        validator = ExtractionValidator(test_save_path)
        yield validator


class TestValidationResult:
    """Tests for the ValidationResult dataclass."""

    def test_initial_state(self):
        """ValidationResult starts as valid with empty collections."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.issues == []
        assert result.warnings == []
        assert result.checks_passed == 0
        assert result.checks_failed == 0

    def test_add_issue_sets_invalid(self):
        """Adding an issue marks the result as invalid."""
        result = ValidationResult(valid=True)
        result.add_issue("test_check", "Test message")

        assert result.valid is False
        assert len(result.issues) == 1
        assert result.checks_failed == 1

    def test_add_issue_with_details(self):
        """Issues can include details and fix suggestions."""
        result = ValidationResult(valid=True)
        result.add_issue(
            "test_check", "Test message", details={"key": "value"}, fix_suggestion="Try this fix"
        )

        issue = result.issues[0]
        assert issue["check"] == "test_check"
        assert issue["message"] == "Test message"
        assert issue["details"] == {"key": "value"}
        assert issue["fix_suggestion"] == "Try this fix"

    def test_add_warning_keeps_valid(self):
        """Warnings don't mark the result as invalid."""
        result = ValidationResult(valid=True)
        result.add_warning("test_warning", "Warning message")

        assert result.valid is True
        assert len(result.warnings) == 1
        assert result.checks_warned == 1

    def test_merge_combines_results(self):
        """Merging combines issues, warnings, and counters."""
        result1 = ValidationResult(valid=True)
        result1.add_pass()
        result1.add_pass()
        result1.add_warning("warn1", "Warning 1")

        result2 = ValidationResult(valid=True)
        result2.add_issue("issue1", "Issue 1")
        result2.add_pass()

        result1.merge(result2)

        assert result1.valid is False  # Became invalid due to merge
        assert result1.checks_passed == 3
        assert result1.checks_failed == 1
        assert result1.checks_warned == 1
        assert len(result1.issues) == 1
        assert len(result1.warnings) == 1

    def test_to_dict_serialization(self):
        """to_dict() returns proper dictionary structure."""
        result = ValidationResult(valid=True)
        result.add_pass()
        result.add_issue("test", "Test issue")
        result.add_warning("warn", "Test warning")

        d = result.to_dict()

        assert isinstance(d, dict)
        assert d["valid"] is False
        assert isinstance(d["issues"], list)
        assert isinstance(d["warnings"], list)
        assert "summary" in d
        assert d["summary"]["checks_passed"] == 1
        assert d["summary"]["checks_failed"] == 1
        assert d["summary"]["checks_warned"] == 1


class TestExtractionValidator:
    """Integration tests for validate_all()."""

    def test_validate_all_returns_comprehensive_report(self, validator):
        """validate_all() returns a complete report with all validations."""
        report = validator.validate_all()

        assert isinstance(report, dict)
        assert "overall_valid" in report
        assert "wars" in report
        assert "fleets" in report
        assert "diplomacy" in report
        assert "resources" in report
        assert "summary" in report

    def test_validate_all_aggregates_validity(self, validator):
        """validate_all() overall_valid reflects all domain validations."""
        report = validator.validate_all()

        # Overall valid should be True only if all domains are valid
        all_valid = (
            report["wars"]["valid"]
            and report["fleets"]["valid"]
            and report["diplomacy"]["valid"]
            and report["resources"]["valid"]
        )

        assert report["overall_valid"] == all_valid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
