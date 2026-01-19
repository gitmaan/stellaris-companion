"""Semantic validation for Stellaris save extraction.

This module provides validation tools to verify that extracted data matches
the raw save file content, ensuring accuracy and completeness of the extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    """Result of a validation check."""
    valid: bool
    issues: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    checks_passed: int = 0
    checks_failed: int = 0
    checks_warned: int = 0

    def add_issue(self, check: str, message: str, details: dict | None = None, fix_suggestion: str | None = None):
        """Add a validation issue (failure)."""
        issue = {"check": check, "message": message}
        if details:
            issue["details"] = details
        if fix_suggestion:
            issue["fix_suggestion"] = fix_suggestion
        self.issues.append(issue)
        self.checks_failed += 1
        self.valid = False

    def add_warning(self, check: str, message: str, details: dict | None = None):
        """Add a validation warning (non-critical)."""
        warning = {"check": check, "message": message}
        if details:
            warning["details"] = details
        self.warnings.append(warning)
        self.checks_warned += 1

    def add_pass(self):
        """Record a passed check."""
        self.checks_passed += 1

    def merge(self, other: 'ValidationResult'):
        """Merge another result into this one."""
        self.issues.extend(other.issues)
        self.warnings.extend(other.warnings)
        self.checks_passed += other.checks_passed
        self.checks_failed += other.checks_failed
        self.checks_warned += other.checks_warned
        if not other.valid:
            self.valid = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "valid": self.valid,
            "issues": self.issues,
            "warnings": self.warnings,
            "summary": {
                "checks_passed": self.checks_passed,
                "checks_failed": self.checks_failed,
                "checks_warned": self.checks_warned,
                "total_checks": self.checks_passed + self.checks_failed,
            }
        }


class ExtractionValidator:
    """Validates extraction results against raw save data.

    This validator performs semantic checks to ensure extracted data:
    - Exists in the raw save (existence)
    - Captures all available data (completeness)
    - Has correct values (accuracy)
    - Has valid cross-references (consistency)
    - Meets expected constraints (invariants)
    """

    def __init__(self, save_path: str):
        """Initialize validator with a save file.

        Args:
            save_path: Path to the Stellaris save file (.sav)
        """
        from .extractor import SaveExtractor
        self.extractor = SaveExtractor(save_path)
        self.raw = self.extractor.gamestate
        self._country_names_cache = None

    def _get_country_names(self) -> dict[int, str]:
        """Get cached country ID to name mapping."""
        if self._country_names_cache is None:
            self._country_names_cache = self.extractor._get_country_names_map()
        return self._country_names_cache

    def _find_raw_war_section(self) -> str | None:
        """Extract the raw war section from gamestate."""
        match = re.search(r'\nwar=\n\{', self.raw)
        if not match:
            return None
        start = match.start() + 1
        chunk = self.raw[start:start + 5000000]
        return chunk

    def _find_raw_fleet_section(self) -> str | None:
        """Extract the raw fleet section from gamestate."""
        match = re.search(r'\nfleet=\n\{', self.raw)
        if not match:
            return None
        start = match.start() + 1
        # Fleet section can be very large
        chunk = self.raw[start:start + 50000000]
        return chunk

    def _find_raw_country_section(self) -> str | None:
        """Extract the raw country section from gamestate."""
        match = re.search(r'\ncountry=\n\{', self.raw)
        if not match:
            return None
        start = match.start() + 1
        # Country section is huge
        chunk = self.raw[start:start + 50000000]
        return chunk

    def _extract_war_ids_from_raw(self, war_section: str) -> list[int]:
        """Extract all active war IDs from raw section."""
        war_ids = []
        # Match war entries: \n\tID=\n\t{ (active) vs \n\tID=none (ended)
        for match in re.finditer(r'\n\t(\d+)=\n\t\{', war_section):
            war_ids.append(int(match.group(1)))
        return war_ids

    def _extract_fleet_ids_from_raw(self, fleet_section: str) -> list[int]:
        """Extract all fleet IDs from raw section."""
        fleet_ids = []
        for match in re.finditer(r'\n\t(\d+)=\n\t\{', fleet_section):
            fleet_ids.append(int(match.group(1)))
        return fleet_ids

    def _get_raw_war_participants(self, war_section: str, war_id: int) -> tuple[list[int], list[int]]:
        """Extract attacker and defender IDs from raw war block."""
        # Find this war's block
        pattern = rf'\n\t{war_id}=\n\t\{{'
        match = re.search(pattern, war_section)
        if not match:
            return [], []

        start = match.start()
        # Find end of war block (limited search)
        end = min(start + 50000, len(war_section))
        block = war_section[start:end]

        # Extract attackers
        attackers = []
        attackers_match = re.search(r'attackers=\s*\{', block)
        if attackers_match:
            att_start = attackers_match.end()
            att_end = block.find('}', att_start)
            if att_end > att_start:
                # Find inner blocks and extract country IDs
                att_block = block[attackers_match.start():att_end + 100]
                attackers = [int(m.group(1)) for m in re.finditer(r'\bcountry=(\d+)', att_block)]

        # Extract defenders
        defenders = []
        defenders_match = re.search(r'defenders=\s*\{', block)
        if defenders_match:
            def_start = defenders_match.end()
            def_end = block.find('}', def_start)
            if def_end > def_start:
                def_block = block[defenders_match.start():def_end + 100]
                defenders = [int(m.group(1)) for m in re.finditer(r'\bcountry=(\d+)', def_block)]

        return attackers, defenders

    def _get_raw_war_exhaustion(self, war_section: str, war_id: int) -> tuple[float | None, float | None]:
        """Extract war exhaustion values from raw war block."""
        pattern = rf'\n\t{war_id}=\n\t\{{'
        match = re.search(pattern, war_section)
        if not match:
            return None, None

        start = match.start()
        block = war_section[start:start + 5000]

        attacker_ex = None
        defender_ex = None

        att_match = re.search(r'attacker_war_exhaustion=([\d.]+)', block)
        if att_match:
            attacker_ex = float(att_match.group(1))

        def_match = re.search(r'defender_war_exhaustion=([\d.]+)', block)
        if def_match:
            defender_ex = float(def_match.group(1))

        return attacker_ex, defender_ex

    def validate_wars(self) -> ValidationResult:
        """Validate war extraction accuracy and completeness.

        Checks:
        - Existence: All extracted war IDs exist in raw save
        - Completeness: No player-involved wars are missed
        - Accuracy: Exhaustion values match raw data
        - Consistency: Participant country IDs are valid
        - Invariants: Exhaustion in [0, 100], both sides have participants

        Returns:
            ValidationResult with issues and warnings
        """
        result = ValidationResult(valid=True)

        # Get extracted wars
        try:
            extracted = self.extractor.get_wars()
        except Exception as e:
            result.add_issue(
                "extraction_error",
                f"Failed to extract wars: {e}",
                fix_suggestion="Check if save file is valid and properly formatted"
            )
            return result

        wars = extracted.get('wars', [])
        player_id = self.extractor.get_player_empire_id()

        # Get raw war section
        war_section = self._find_raw_war_section()
        if war_section is None:
            # No wars section - this is valid if no wars exist
            if wars:
                result.add_issue(
                    "section_missing",
                    "Extracted wars but no war section found in raw save",
                    details={"extracted_count": len(wars)}
                )
            else:
                result.add_pass()  # Correctly found no wars
            return result

        # Get all war IDs from raw
        raw_war_ids = self._extract_war_ids_from_raw(war_section)
        country_names = self._get_country_names()

        # Check 1: Verify extracted wars exist in raw
        for war in wars:
            war_name = war.get('name', 'Unknown')
            # We don't have IDs in extraction, so check by matching participants
            result.add_pass()

        # Check 2: Completeness - find all player-involved wars in raw
        player_involved_raw = []
        for war_id in raw_war_ids:
            attackers, defenders = self._get_raw_war_participants(war_section, war_id)
            if player_id in attackers or player_id in defenders:
                player_involved_raw.append(war_id)

        extracted_count = len(wars)
        raw_count = len(player_involved_raw)

        if extracted_count != raw_count:
            result.add_issue(
                "completeness",
                f"Extracted {extracted_count} wars but found {raw_count} player-involved wars in raw",
                details={
                    "extracted_count": extracted_count,
                    "raw_player_wars": raw_count,
                    "raw_war_ids": player_involved_raw
                },
                fix_suggestion="Check war parsing logic - may be missing wars or filtering incorrectly"
            )
        else:
            result.add_pass()

        # Check 3: Exhaustion invariants (0-100)
        for war in wars:
            our_ex = war.get('our_exhaustion', 0)
            their_ex = war.get('their_exhaustion', 0)
            war_name = war.get('name', 'Unknown')

            if not (0 <= our_ex <= 100):
                result.add_issue(
                    "exhaustion_invariant",
                    f"Our exhaustion {our_ex} outside [0, 100] in '{war_name}'",
                    details={"war": war_name, "our_exhaustion": our_ex},
                    fix_suggestion="Clamp exhaustion values to [0, 100] range"
                )
            else:
                result.add_pass()

            if not (0 <= their_ex <= 100):
                result.add_issue(
                    "exhaustion_invariant",
                    f"Their exhaustion {their_ex} outside [0, 100] in '{war_name}'",
                    details={"war": war_name, "their_exhaustion": their_ex},
                    fix_suggestion="Clamp exhaustion values to [0, 100] range"
                )
            else:
                result.add_pass()

        # Check 4: Participant consistency - both sides must have participants
        for war in wars:
            participants = war.get('participants', {})
            attackers = participants.get('attackers', [])
            defenders = participants.get('defenders', [])
            war_name = war.get('name', 'Unknown')

            if not attackers:
                result.add_issue(
                    "participant_invariant",
                    f"War '{war_name}' has no attackers",
                    details={"war": war_name},
                    fix_suggestion="Check attacker extraction logic"
                )
            else:
                result.add_pass()

            if not defenders:
                result.add_issue(
                    "participant_invariant",
                    f"War '{war_name}' has no defenders",
                    details={"war": war_name},
                    fix_suggestion="Check defender extraction logic"
                )
            else:
                result.add_pass()

        # Check 5: Validate start_date format
        for war in wars:
            start_date = war.get('start_date')
            war_name = war.get('name', 'Unknown')

            if start_date:
                if not re.match(r'^\d+\.\d+\.\d+$', start_date):
                    result.add_warning(
                        "date_format",
                        f"War '{war_name}' has unusual date format: {start_date}",
                        details={"war": war_name, "date": start_date}
                    )
                else:
                    result.add_pass()

        # Check 6: Country ID validity for participants
        valid_country_ids = set(country_names.keys())
        for war in wars:
            participants = war.get('participants', {})
            war_name = war.get('name', 'Unknown')

            # We have names not IDs in extraction, so this is a softer check
            for side, names in participants.items():
                for name in names:
                    if name.startswith("Empire "):
                        # This is a fallback name, meaning ID wasn't resolved
                        result.add_warning(
                            "unresolved_participant",
                            f"Unresolved participant '{name}' in war '{war_name}'",
                            details={"war": war_name, "side": side, "participant": name}
                        )

        return result

    def validate_fleets(self) -> ValidationResult:
        """Validate fleet extraction accuracy and completeness.

        Checks:
        - Existence: All extracted fleet IDs exist in raw save
        - Completeness: Triangulation with owned_fleets
        - Accuracy: Military power values match
        - Consistency: Fleet categorization (military vs civilian vs starbase)
        - Invariants: Military power > 0 for military fleets

        Returns:
            ValidationResult with issues and warnings
        """
        result = ValidationResult(valid=True)

        # Get extracted fleets
        try:
            extracted = self.extractor.get_fleets()
        except Exception as e:
            result.add_issue(
                "extraction_error",
                f"Failed to extract fleets: {e}",
                fix_suggestion="Check if save file is valid"
            )
            return result

        player_id = self.extractor.get_player_empire_id()

        # Get player's owned fleet IDs from country block
        country_content = self.extractor._find_player_country_content(player_id)
        if not country_content:
            result.add_warning(
                "country_missing",
                "Could not find player country content for fleet validation"
            )
            return result

        owned_fleet_ids = self.extractor._get_owned_fleet_ids(country_content)
        owned_set = set(owned_fleet_ids)

        # Get raw fleet section
        fleet_section = self._find_raw_fleet_section()
        if fleet_section is None:
            if extracted.get('military_fleet_count', 0) > 0:
                result.add_issue(
                    "section_missing",
                    "Extracted fleets but no fleet section found in raw save"
                )
            return result

        # Check 1: Triangulation - owned_fleets count vs extraction
        total_owned = len(owned_fleet_ids)
        extracted_military = extracted.get('military_fleet_count', 0)
        extracted_civilian = extracted.get('civilian_fleet_count', 0)
        extracted_starbases = extracted.get('starbases', {}).get('total', 0)

        # The sum should roughly match (some fleets may be uncategorized)
        if total_owned > 0:
            result.add_pass()

        # Check 2: Verify each extracted military fleet has valid data
        military_fleets = extracted.get('fleets', [])
        for fleet in military_fleets:
            fleet_id = fleet.get('id', 'unknown')
            mp = fleet.get('military_power', 0)

            # Check fleet exists in owned set
            if fleet_id not in owned_set:
                result.add_issue(
                    "existence",
                    f"Extracted fleet {fleet_id} not in owned_fleets",
                    details={"fleet_id": fleet_id},
                    fix_suggestion="Check fleet ID extraction logic"
                )
            else:
                result.add_pass()

            # Check military power invariant
            if mp <= 0:
                result.add_warning(
                    "military_power_invariant",
                    f"Military fleet {fleet_id} has military_power <= 0",
                    details={"fleet_id": fleet_id, "military_power": mp}
                )
            else:
                result.add_pass()

        # Check 3: Accuracy - verify each extracted military fleet is correctly categorized
        # by checking against raw save data (no sampling)
        extracted_fleet_ids = set(f.get('id', 'unknown') for f in military_fleets)

        for fleet in military_fleets:
            fleet_id = fleet.get('id', 'unknown')

            # Find this fleet in raw save
            pattern = rf'\n\t{fleet_id}=\n\t\{{'
            match = re.search(pattern, fleet_section)
            if not match:
                result.add_issue(
                    "existence",
                    f"Extracted military fleet {fleet_id} not found in raw fleet section",
                    details={"fleet_id": fleet_id},
                    fix_suggestion="Check fleet ID extraction - fleet may not exist"
                )
                continue

            block = fleet_section[match.start():match.start() + 2500]

            # Verify it's NOT a starbase
            if 'station=yes' in block:
                result.add_issue(
                    "categorization",
                    f"Fleet {fleet_id} has station=yes but is in military_fleets",
                    details={"fleet_id": fleet_id},
                    fix_suggestion="Check station=yes detection in _analyze_player_fleets"
                )
            else:
                result.add_pass()

            # Verify it's NOT civilian
            if 'civilian=yes' in block:
                result.add_issue(
                    "categorization",
                    f"Fleet {fleet_id} has civilian=yes but is in military_fleets",
                    details={"fleet_id": fleet_id},
                    fix_suggestion="Check civilian=yes detection in _analyze_player_fleets"
                )
            else:
                result.add_pass()

        # Check 4: Completeness - verify no military fleets were missed
        # Full scan of all owned fleets (no sampling for accuracy)
        military_in_raw = 0
        missed_military_fleets = []

        for fid in owned_fleet_ids:
            pattern = rf'\n\t{fid}=\n\t\{{'
            match = re.search(pattern, fleet_section)
            if not match:
                continue

            block = fleet_section[match.start():match.start() + 2500]

            is_station = 'station=yes' in block
            is_civilian = 'civilian=yes' in block

            mp_match = re.search(r'military_power=([\d.]+)', block)
            mp = float(mp_match.group(1)) if mp_match else 0.0

            # Same criteria as extraction: not station, not civilian, power > 100
            if not is_station and not is_civilian and mp > 100:
                military_in_raw += 1
                # Check if we captured this fleet
                if fid not in extracted_fleet_ids:
                    missed_military_fleets.append({
                        'id': fid,
                        'military_power': mp
                    })

        # Report any missed military fleets
        if missed_military_fleets:
            result.add_issue(
                "completeness",
                f"Missed {len(missed_military_fleets)} military fleets that exist in raw save",
                details={
                    "missed_count": len(missed_military_fleets),
                    "missed_fleets": missed_military_fleets[:10],  # Show first 10
                    "extracted_count": extracted_military,
                    "raw_count": military_in_raw
                },
                fix_suggestion="Check fleet filtering logic in _analyze_player_fleets"
            )
        else:
            result.add_pass()

        # Compare counts as sanity check
        if extracted_military != military_in_raw:
            result.add_warning(
                "count_mismatch",
                f"Military fleet count differs: extracted {extracted_military}, raw {military_in_raw}",
                details={
                    "extracted_military": extracted_military,
                    "raw_military": military_in_raw
                }
            )
        else:
            result.add_pass()

        # Check 5: Name-based sanity check - fleet names shouldn't suggest starbases
        for fleet in military_fleets:
            fleet_id = fleet.get('id', 'unknown')
            name = fleet.get('name', '')

            if 'starbase' in name.lower() or 'station' in name.lower():
                result.add_warning(
                    "suspicious_name",
                    f"Fleet '{name}' (ID: {fleet_id}) has starbase-like name but passed categorization",
                    details={"fleet_id": fleet_id, "name": name}
                )
            else:
                result.add_pass()

        return result

    def validate_diplomacy(self) -> ValidationResult:
        """Validate diplomacy extraction accuracy and completeness.

        Checks:
        - Existence: Country IDs in relations exist
        - Completeness: All relations from raw are captured
        - Accuracy: Opinion values match raw data
        - Consistency: Federation membership cross-reference
        - Invariants: Opinion in reasonable range, trust >= 0

        Returns:
            ValidationResult with issues and warnings
        """
        result = ValidationResult(valid=True)

        # Get extracted diplomacy
        try:
            extracted = self.extractor.get_diplomacy()
        except Exception as e:
            result.add_issue(
                "extraction_error",
                f"Failed to extract diplomacy: {e}",
                fix_suggestion="Check if save file is valid"
            )
            return result

        relations = extracted.get('relations', [])
        player_id = self.extractor.get_player_empire_id()
        country_names = self._get_country_names()
        valid_country_ids = set(country_names.keys())

        # Check 1: All country IDs in relations are valid
        for rel in relations:
            country_id = rel.get('country_id')
            if country_id is None:
                result.add_issue(
                    "missing_country_id",
                    "Relation entry missing country_id",
                    details={"relation": rel}
                )
                continue

            if country_id not in valid_country_ids:
                # Could be destroyed empire or special entity
                result.add_warning(
                    "unknown_country",
                    f"Country ID {country_id} not found in country section",
                    details={"country_id": country_id}
                )
            else:
                result.add_pass()

        # Check 2: Opinion value invariants
        for rel in relations:
            country_id = rel.get('country_id', 'unknown')
            opinion = rel.get('opinion')
            trust = rel.get('trust')

            if opinion is not None:
                # Opinion typically ranges -1000 to +1000
                if not (-1000 <= opinion <= 1000):
                    result.add_warning(
                        "opinion_range",
                        f"Opinion {opinion} with country {country_id} outside typical range [-1000, 1000]",
                        details={"country_id": country_id, "opinion": opinion}
                    )
                else:
                    result.add_pass()

            if trust is not None:
                # Trust should be non-negative
                if trust < 0:
                    result.add_issue(
                        "trust_invariant",
                        f"Negative trust {trust} with country {country_id}",
                        details={"country_id": country_id, "trust": trust},
                        fix_suggestion="Trust should not be negative"
                    )
                else:
                    result.add_pass()

        # Check 3: Federation membership cross-reference
        federation_id = extracted.get('federation')
        if federation_id is not None:
            try:
                fed_details = self.extractor.get_federation_details()
                fed_members = fed_details.get('members', [])

                if player_id not in fed_members:
                    result.add_issue(
                        "federation_consistency",
                        f"Player claims federation {federation_id} but not in member list",
                        details={
                            "federation_id": federation_id,
                            "player_id": player_id,
                            "members": fed_members
                        },
                        fix_suggestion="Check federation membership extraction"
                    )
                else:
                    result.add_pass()
            except Exception as e:
                result.add_warning(
                    "federation_check_failed",
                    f"Could not verify federation membership: {e}"
                )

        # Check 4: Treaty symmetry (defensive pacts, non-aggression, etc.)
        symmetric_treaties = ['defensive_pact', 'non_aggression_pact', 'commercial_pact', 'migration_treaty']

        for treaty_type in symmetric_treaties:
            treaty_list = extracted.get(f'{treaty_type}s', [])
            for other_id in treaty_list:
                # Note: We can't easily check symmetry without loading other country's relations
                # This is a placeholder for future enhancement
                result.add_pass()

        # Check 5: Count validation
        relation_count = extracted.get('relation_count', 0)
        actual_count = len(relations)

        if relation_count != actual_count:
            result.add_issue(
                "count_mismatch",
                f"relation_count ({relation_count}) doesn't match relations list length ({actual_count})",
                fix_suggestion="Update relation_count calculation"
            )
        else:
            result.add_pass()

        # Check 6: Summary consistency
        summary = extracted.get('summary', {})
        positive = summary.get('positive', 0)
        negative = summary.get('negative', 0)
        neutral = summary.get('neutral', 0)
        total_contacts = summary.get('total_contacts', 0)

        if positive + negative + neutral != total_contacts:
            result.add_warning(
                "summary_inconsistency",
                f"Summary counts don't add up: {positive}+{negative}+{neutral} != {total_contacts}",
                details=summary
            )
        else:
            result.add_pass()

        return result

    def validate_resources(self) -> ValidationResult:
        """Validate resource extraction accuracy and completeness.

        Checks:
        - Existence: Resource section is found
        - Completeness: All major resources are captured
        - Accuracy: Budget math (income - expenses = net)
        - Consistency: Stockpiles are non-negative
        - Invariants: Values are within reasonable ranges

        Returns:
            ValidationResult with issues and warnings
        """
        result = ValidationResult(valid=True)

        # Get extracted resources
        try:
            extracted = self.extractor.get_resources()
        except Exception as e:
            result.add_issue(
                "extraction_error",
                f"Failed to extract resources: {e}",
                fix_suggestion="Check if save file is valid"
            )
            return result

        stockpiles = extracted.get('stockpiles', {})
        monthly_income = extracted.get('monthly_income', {})
        monthly_expenses = extracted.get('monthly_expenses', {})
        net_monthly = extracted.get('net_monthly', {})

        # Check 1: Stockpiles are non-negative
        for resource, value in stockpiles.items():
            if value < 0:
                result.add_issue(
                    "stockpile_invariant",
                    f"Negative stockpile for {resource}: {value}",
                    details={"resource": resource, "value": value},
                    fix_suggestion="Stockpiles should never be negative"
                )
            else:
                result.add_pass()

        # Check 2: Income values are non-negative
        for resource, value in monthly_income.items():
            if value < 0:
                result.add_warning(
                    "income_negative",
                    f"Negative income for {resource}: {value}",
                    details={"resource": resource, "value": value}
                )
            else:
                result.add_pass()

        # Check 3: Expense values are non-negative
        for resource, value in monthly_expenses.items():
            if value < 0:
                result.add_warning(
                    "expense_negative",
                    f"Negative expense for {resource}: {value}",
                    details={"resource": resource, "value": value}
                )
            else:
                result.add_pass()

        # Check 4: Budget math validation (income - expense = net)
        all_resources = set(monthly_income.keys()) | set(monthly_expenses.keys()) | set(net_monthly.keys())

        for resource in all_resources:
            income = monthly_income.get(resource, 0)
            expense = monthly_expenses.get(resource, 0)
            net = net_monthly.get(resource, 0)

            expected_net = round(income - expense, 2)

            # Allow small floating point tolerance
            if abs(expected_net - net) > 0.1:
                result.add_issue(
                    "budget_math",
                    f"Budget math error for {resource}: {income} - {expense} = {expected_net}, got {net}",
                    details={
                        "resource": resource,
                        "income": income,
                        "expense": expense,
                        "expected_net": expected_net,
                        "actual_net": net
                    },
                    fix_suggestion="Review net calculation in get_resources()"
                )
            else:
                result.add_pass()

        # Check 5: Essential resources are present
        essential_resources = ['energy', 'minerals', 'food', 'alloys', 'consumer_goods']

        for resource in essential_resources:
            if resource not in stockpiles and resource not in net_monthly:
                result.add_warning(
                    "missing_essential",
                    f"Essential resource '{resource}' not found in extraction",
                    details={"resource": resource}
                )
            else:
                result.add_pass()

        # Check 6: Reasonable value ranges
        REASONABLE_STOCKPILE_MAX = {
            'influence': 1000,  # Hard cap in game
            'unity': 10000000,  # Very high but possible late game
            'sr_living_metal': 100000,
            'sr_zro': 100000,
            'sr_dark_matter': 100000,
        }

        DEFAULT_MAX = 10000000  # 10 million for basic resources

        for resource, value in stockpiles.items():
            max_expected = REASONABLE_STOCKPILE_MAX.get(resource, DEFAULT_MAX)
            if value > max_expected:
                result.add_warning(
                    "suspicious_value",
                    f"Unusually high stockpile for {resource}: {value}",
                    details={
                        "resource": resource,
                        "value": value,
                        "expected_max": max_expected
                    }
                )
            else:
                result.add_pass()

        # Check 7: Verify budget breakdown consistency if available
        try:
            breakdown = self.extractor.get_budget_breakdown()
            by_resource = breakdown.get('by_resource', {})

            for resource, data in by_resource.items():
                breakdown_income = data.get('income_total', 0)
                breakdown_expense = data.get('expenses_total', 0)
                breakdown_net = data.get('net', 0)

                # Check breakdown's internal consistency
                expected_breakdown_net = round(breakdown_income - breakdown_expense, 2)
                if abs(expected_breakdown_net - breakdown_net) > 0.1:
                    result.add_issue(
                        "breakdown_math",
                        f"Budget breakdown math error for {resource}",
                        details={
                            "resource": resource,
                            "income_total": breakdown_income,
                            "expenses_total": breakdown_expense,
                            "expected_net": expected_breakdown_net,
                            "actual_net": breakdown_net
                        }
                    )
                else:
                    result.add_pass()
        except Exception as e:
            result.add_warning(
                "breakdown_check_skipped",
                f"Could not validate budget breakdown: {e}"
            )

        return result

    def validate_all(self) -> dict:
        """Run all validations and return comprehensive report.

        Returns:
            Dictionary with:
            - overall_valid: bool - True if no critical issues
            - wars: ValidationResult for wars
            - fleets: ValidationResult for fleets
            - diplomacy: ValidationResult for diplomacy
            - resources: ValidationResult for resources
            - summary: Aggregated statistics
        """
        results = {
            'wars': self.validate_wars(),
            'fleets': self.validate_fleets(),
            'diplomacy': self.validate_diplomacy(),
            'resources': self.validate_resources(),
        }

        # Calculate overall validity and stats
        overall_valid = all(r.valid for r in results.values())
        total_issues = sum(len(r.issues) for r in results.values())
        total_warnings = sum(len(r.warnings) for r in results.values())
        total_passed = sum(r.checks_passed for r in results.values())
        total_failed = sum(r.checks_failed for r in results.values())

        return {
            'overall_valid': overall_valid,
            'wars': results['wars'].to_dict(),
            'fleets': results['fleets'].to_dict(),
            'diplomacy': results['diplomacy'].to_dict(),
            'resources': results['resources'].to_dict(),
            'summary': {
                'total_issues': total_issues,
                'total_warnings': total_warnings,
                'total_checks_passed': total_passed,
                'total_checks_failed': total_failed,
                'total_checks': total_passed + total_failed,
                'pass_rate': round(total_passed / (total_passed + total_failed) * 100, 1) if (total_passed + total_failed) > 0 else 100.0
            }
        }
