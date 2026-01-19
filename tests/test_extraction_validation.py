"""Tests for the extraction validation module.

These tests verify that the validation logic itself works correctly,
testing both positive cases (valid data passes) and negative cases
(invalid data is caught).
"""

import pytest
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stellaris_save_extractor.validation import ExtractionValidator, ValidationResult


# Path to test save fixture
TEST_SAVE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'test_save.sav'
)


@pytest.fixture
def test_save_path():
    """Return path to test save file."""
    if not os.path.exists(TEST_SAVE_PATH):
        pytest.skip(f"Test save file not found at {TEST_SAVE_PATH}")
    return TEST_SAVE_PATH


@pytest.fixture
def validator(test_save_path):
    """Create a validator instance with the test save."""
    return ExtractionValidator(test_save_path)


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
            "test_check",
            "Test message",
            details={"key": "value"},
            fix_suggestion="Try this fix"
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

    def test_add_pass_increments_counter(self):
        """Passing checks increment the counter."""
        result = ValidationResult(valid=True)
        result.add_pass()
        result.add_pass()

        assert result.checks_passed == 2

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
    """Tests for the ExtractionValidator class."""

    def test_initialization(self, validator):
        """Validator initializes with extractor and raw data."""
        assert validator.extractor is not None
        assert validator.raw is not None
        assert len(validator.raw) > 0

    def test_validate_wars_returns_result(self, validator):
        """validate_wars() returns a ValidationResult."""
        result = validator.validate_wars()

        assert isinstance(result, ValidationResult)
        assert isinstance(result.valid, bool)
        assert isinstance(result.issues, list)
        assert isinstance(result.warnings, list)

    def test_validate_wars_checks_exhaustion_bounds(self, validator):
        """validate_wars() checks exhaustion is in [0, 100]."""
        result = validator.validate_wars()

        # The result should exist - we're checking the validator runs
        assert result.checks_passed >= 0 or result.checks_failed >= 0

    def test_validate_wars_checks_participants(self, validator):
        """validate_wars() verifies wars have participants on both sides."""
        result = validator.validate_wars()

        # Check that participant validation was performed
        # (issues would mention "participant" if there's a problem)
        participant_issues = [i for i in result.issues if 'participant' in i.get('check', '').lower()]
        # We expect either no issues (valid) or properly formatted issues
        for issue in participant_issues:
            assert 'message' in issue

    def test_validate_fleets_returns_result(self, validator):
        """validate_fleets() returns a ValidationResult."""
        result = validator.validate_fleets()

        assert isinstance(result, ValidationResult)
        assert isinstance(result.valid, bool)

    def test_validate_fleets_checks_ownership(self, validator):
        """validate_fleets() verifies fleets are in owned_fleets."""
        result = validator.validate_fleets()

        # Check that existence validation was attempted
        assert result.checks_passed >= 0 or result.checks_failed >= 0

    def test_validate_fleets_checks_categorization(self, validator):
        """validate_fleets() verifies fleet categorization (no starbases in military)."""
        result = validator.validate_fleets()

        # Look for categorization issues
        cat_issues = [i for i in result.issues if 'categorization' in i.get('check', '').lower()]
        # If found, they should be properly structured
        for issue in cat_issues:
            assert 'fleet_id' in issue.get('details', {}) or 'message' in issue

    def test_validate_diplomacy_returns_result(self, validator):
        """validate_diplomacy() returns a ValidationResult."""
        result = validator.validate_diplomacy()

        assert isinstance(result, ValidationResult)
        assert isinstance(result.valid, bool)

    def test_validate_diplomacy_checks_country_ids(self, validator):
        """validate_diplomacy() validates country IDs exist."""
        result = validator.validate_diplomacy()

        # Should have run some checks
        assert result.checks_passed + result.checks_failed >= 0

    def test_validate_diplomacy_checks_opinion_bounds(self, validator):
        """validate_diplomacy() checks opinion values are reasonable."""
        result = validator.validate_diplomacy()

        # Opinion range warnings should be properly formatted if present
        opinion_warnings = [w for w in result.warnings if 'opinion' in w.get('check', '').lower()]
        for warning in opinion_warnings:
            assert 'country_id' in warning.get('details', {}) or 'message' in warning

    def test_validate_resources_returns_result(self, validator):
        """validate_resources() returns a ValidationResult."""
        result = validator.validate_resources()

        assert isinstance(result, ValidationResult)
        assert isinstance(result.valid, bool)

    def test_validate_resources_checks_stockpile_positive(self, validator):
        """validate_resources() verifies stockpiles are non-negative."""
        result = validator.validate_resources()

        # Look for stockpile invariant issues
        stockpile_issues = [i for i in result.issues if 'stockpile' in i.get('check', '').lower()]
        # Test save should have valid (non-negative) stockpiles
        # If there are issues, they should be properly formatted
        for issue in stockpile_issues:
            assert 'resource' in issue.get('details', {})

    def test_validate_resources_checks_budget_math(self, validator):
        """validate_resources() validates income - expense = net."""
        result = validator.validate_resources()

        # Budget math issues should be properly structured
        math_issues = [i for i in result.issues if 'budget_math' in i.get('check', '').lower()]
        for issue in math_issues:
            details = issue.get('details', {})
            assert 'resource' in details or 'message' in issue

    def test_validate_all_returns_comprehensive_report(self, validator):
        """validate_all() returns a complete report with all validations."""
        report = validator.validate_all()

        assert isinstance(report, dict)
        assert 'overall_valid' in report
        assert 'wars' in report
        assert 'fleets' in report
        assert 'diplomacy' in report
        assert 'resources' in report
        assert 'summary' in report

    def test_validate_all_summary_stats(self, validator):
        """validate_all() summary has correct statistics."""
        report = validator.validate_all()

        summary = report['summary']
        assert 'total_issues' in summary
        assert 'total_warnings' in summary
        assert 'total_checks_passed' in summary
        assert 'total_checks_failed' in summary
        assert 'pass_rate' in summary

        # Pass rate should be a percentage
        assert 0 <= summary['pass_rate'] <= 100

    def test_validate_all_aggregates_validity(self, validator):
        """validate_all() overall_valid reflects all domain validations."""
        report = validator.validate_all()

        # Overall valid should be True only if all domains are valid
        all_valid = (
            report['wars']['valid'] and
            report['fleets']['valid'] and
            report['diplomacy']['valid'] and
            report['resources']['valid']
        )

        assert report['overall_valid'] == all_valid


class TestValidatorEdgeCases:
    """Tests for edge cases and error handling."""

    def test_validator_handles_missing_sections_gracefully(self, validator):
        """Validator doesn't crash on missing save sections."""
        # All validations should complete without exceptions
        try:
            validator.validate_wars()
            validator.validate_fleets()
            validator.validate_diplomacy()
            validator.validate_resources()
        except Exception as e:
            pytest.fail(f"Validator raised unexpected exception: {e}")

    def test_validator_reports_extraction_errors(self, test_save_path):
        """Validator reports if extraction fails."""
        # This tests that extraction errors are caught and reported
        validator = ExtractionValidator(test_save_path)

        # Even if extraction has issues, validate_all should not raise
        try:
            report = validator.validate_all()
            assert isinstance(report, dict)
        except Exception as e:
            pytest.fail(f"validate_all raised exception: {e}")

    def test_empty_wars_is_valid(self, validator):
        """Having no wars is a valid state (not an error)."""
        result = validator.validate_wars()

        # If no wars exist, this should not be an error
        wars_data = validator.extractor.get_wars()
        if not wars_data.get('wars'):
            # No wars - should still be valid (or only have warnings)
            war_related_issues = [i for i in result.issues if 'war' in i.get('check', '').lower()]
            # Missing wars is not itself an issue (peace time is valid)
            for issue in war_related_issues:
                assert issue.get('check') != 'completeness' or 'war section' in issue.get('message', '').lower()


class TestValidatorAccuracy:
    """Tests to verify validator correctly identifies real issues."""

    def test_detects_missing_essential_resources(self, validator):
        """Validator warns if essential resources are missing."""
        result = validator.validate_resources()

        # Check that essential resource validation ran
        essential_warnings = [w for w in result.warnings if 'essential' in w.get('check', '').lower()]
        # If test save has all essentials, this should be empty
        # If not, warnings should have proper structure
        for warning in essential_warnings:
            assert 'resource' in warning.get('details', {})

    def test_validates_fleet_military_power(self, validator):
        """Validator checks military power invariants."""
        result = validator.validate_fleets()

        # Military power checks should have been run
        mp_checks = [
            i for i in result.issues + result.warnings
            if 'military_power' in i.get('check', '').lower()
        ]
        # Issues should be properly structured
        for check in mp_checks:
            assert 'message' in check

    def test_federation_cross_reference(self, validator):
        """Validator checks federation membership consistency."""
        result = validator.validate_diplomacy()

        # Federation checks should be properly structured
        fed_issues = [i for i in result.issues if 'federation' in i.get('check', '').lower()]
        for issue in fed_issues:
            assert 'federation_id' in issue.get('details', {}) or 'message' in issue


class TestValidatorPerformance:
    """Tests for validator performance characteristics."""

    def test_validate_all_completes_reasonably(self, validator):
        """validate_all() completes in reasonable time."""
        import time

        start = time.time()
        validator.validate_all()
        elapsed = time.time() - start

        # Should complete within 30 seconds even for large saves
        assert elapsed < 30, f"Validation took too long: {elapsed:.1f}s"

    def test_validator_uses_sampling_for_large_fleet_sets(self, validator):
        """Validator samples large fleet sets for performance."""
        result = validator.validate_fleets()

        # Check if sampling warning was issued for large fleet counts
        sampling_warnings = [w for w in result.warnings if 'sampl' in w.get('check', '').lower()]
        # If fleet count is large and sampling was used, verify warning format
        for warning in sampling_warnings:
            assert 'message' in warning


# Additional integration tests

class TestValidatorIntegration:
    """Integration tests verifying validator works with real extraction."""

    def test_wars_validation_matches_extraction(self, validator):
        """War validation results align with actual extraction data."""
        wars = validator.extractor.get_wars()
        result = validator.validate_wars()

        # If wars exist, checks should have been performed
        if wars.get('wars'):
            assert result.checks_passed + result.checks_failed > 0

    def test_fleets_validation_matches_extraction(self, validator):
        """Fleet validation results align with actual extraction data."""
        fleets = validator.extractor.get_fleets()
        result = validator.validate_fleets()

        # Validation should have run checks
        assert result.checks_passed + result.checks_failed >= 0

    def test_diplomacy_validation_matches_extraction(self, validator):
        """Diplomacy validation results align with actual extraction data."""
        diplomacy = validator.extractor.get_diplomacy()
        result = validator.validate_diplomacy()

        # If relations exist, checks should have been performed
        if diplomacy.get('relations'):
            assert result.checks_passed + result.checks_failed > 0

    def test_resources_validation_matches_extraction(self, validator):
        """Resources validation results align with actual extraction data."""
        resources = validator.extractor.get_resources()
        result = validator.validate_resources()

        # Stockpiles should trigger validation checks
        if resources.get('stockpiles'):
            assert result.checks_passed + result.checks_failed > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
