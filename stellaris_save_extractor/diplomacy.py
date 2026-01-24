from __future__ import annotations

import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path

# Rust bridge for fast Clausewitz parsing
try:
    from rust_bridge import extract_sections, iter_section_entries, ParserError, _get_active_session
    RUST_BRIDGE_AVAILABLE = True
except ImportError:
    RUST_BRIDGE_AVAILABLE = False
    ParserError = Exception  # Fallback type
    _get_active_session = lambda: None

logger = logging.getLogger(__name__)


class DiplomacyMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def _extract_braced_block(self, content: str, key: str) -> str | None:
        """Extract the full `key={...}` block from a larger text chunk."""
        match = re.search(rf'\b{re.escape(key)}\s*=\s*\{{', content)
        if not match:
            return None

        start = match.start()
        brace_count = 0
        started = False

        for i, char in enumerate(content[start:], start):
            if char == '{':
                brace_count += 1
                started = True
            elif char == '}':
                brace_count -= 1
                if started and brace_count == 0:
                    return content[start : i + 1]

        return None

    def _extract_entry_block(self, content: str, entry_id: int) -> str | None:
        """Extract a `\\t<id>={...}` entry block from a top-level section."""
        patterns = [
            rf'\n\t{entry_id}=\n\t\{{',
            rf'\n\t{entry_id}\s*=\s*\{{',
        ]
        start_match = None
        for pattern in patterns:
            start_match = re.search(pattern, content)
            if start_match:
                break
        if not start_match:
            return None

        start = start_match.start()
        brace_count = 0
        started = False

        for i, char in enumerate(content[start:], start):
            if char == '{':
                brace_count += 1
                started = True
            elif char == '}':
                brace_count -= 1
                if started and brace_count == 0:
                    return content[start : i + 1]

        return None

    def get_diplomacy(self) -> dict:
        """Get the player's diplomatic relations.

        Returns:
            Dict with relations, treaties, and diplomatic status with other empires
        """
        # Try Rust parser first
        if RUST_BRIDGE_AVAILABLE:
            try:
                return self._get_diplomacy_rust()
            except ParserError as e:
                logger.warning(f"Rust parser failed for diplomacy: {e}, falling back to regex")
            except Exception as e:
                logger.warning(f"Unexpected error from Rust parser: {e}, falling back to regex")

        # Fallback to regex
        return self._get_diplomacy_regex()

    def _get_diplomacy_rust(self) -> dict:
        """Get diplomatic relations using Rust parser with regex for relation entries.

        The Rust parser is used to:
        - Get federation ID from player country efficiently
        - Extract player country data

        Regex is used for parsing the relations_manager.relation entries because
        the Rust parser collapses duplicate 'relation' keys into a single dict,
        but Stellaris saves have multiple relation={} entries.
        """
        result = {
            'relations': [],
            'treaties': [],
            'allies': [],
            'rivals': [],
            'federation': None,
            'defensive_pacts': [],
            'non_aggression_pacts': [],
            'closed_borders': [],
            'migration_treaties': [],
            'commercial_pacts': [],
            'sensor_links': [],
        }

        player_id = self.get_player_empire_id()

        # Get country name mappings for resolving IDs to empire names
        country_names = self._get_country_names_map()

        # Use cached player country entry for federation ID lookup
        federation_id = None
        player_country = self._get_player_country_entry(player_id)
        if player_country and isinstance(player_country, dict):
            fed_val = player_country.get("federation")
            if fed_val and fed_val != "4294967295" and fed_val != 4294967295:
                try:
                    federation_id = int(fed_val)
                except (ValueError, TypeError):
                    pass

        # For relations, use regex since Rust parser collapses duplicate 'relation' keys
        player_chunk = self._find_player_country_content(player_id)
        if not player_chunk:
            result['error'] = "Could not find player country"
            return result

        # Find relations_manager section
        rel_match = re.search(r'relations_manager=\s*\{', player_chunk)
        if not rel_match:
            result['error'] = "Could not find relations_manager section"
            return result

        rel_block = self._extract_braced_block(player_chunk[rel_match.start():], "relations_manager")
        if not rel_block:
            result['error'] = "Could not parse relations_manager block"
            return result

        relations_found: list[dict] = []
        allies: list[dict] = []
        rivals: list[dict] = []
        defensive_pacts: list[dict] = []
        non_aggression_pacts: list[dict] = []
        closed_borders: list[dict] = []
        migration_treaties: list[dict] = []
        commercial_pacts: list[dict] = []
        sensor_links: list[dict] = []
        treaties: list[dict] = []

        for match in re.finditer(r'\brelation\s*=\s*\{', rel_block):
            rel_start = match.start()
            brace_count = 0
            rel_end = None
            for i, char in enumerate(rel_block[rel_start:], rel_start):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        rel_end = i + 1
                        break
            if rel_end is None:
                continue

            rel_text = rel_block[rel_start:rel_end]

            # Only process relations where owner=player_id
            if not re.search(rf'\bowner={player_id}\b', rel_text):
                continue

            relation_info = {}

            # Extract country ID and resolve to name
            country_match = re.search(r'\bcountry=(\d+)', rel_text)
            if country_match:
                relation_info['country_id'] = int(country_match.group(1))
            target_country_id = relation_info.get('country_id')
            if target_country_id is None:
                continue

            # Resolve empire name
            relation_info['empire_name'] = country_names.get(target_country_id, f"Empire {target_country_id}")

            # Extract trust
            trust_match = re.search(r'\btrust=(\d+)', rel_text)
            if trust_match:
                relation_info['trust'] = int(trust_match.group(1))

            # Extract relation score
            rel_current = re.search(r'\brelation_current=([-\d]+)', rel_text)
            if rel_current:
                relation_info['opinion'] = int(rel_current.group(1))

            empire_name = relation_info['empire_name']

            # Check for treaties/agreements
            if 'alliance=yes' in rel_text or 'defensive_pact=yes' in rel_text:
                relation_info['defensive_pact'] = True
                defensive_pacts.append({'id': target_country_id, 'name': empire_name})
                allies.append({'id': target_country_id, 'name': empire_name})
                treaties.append({'country_id': target_country_id, 'empire_name': empire_name, 'type': 'defensive_pact'})

            if 'non_aggression_pact=yes' in rel_text:
                relation_info['non_aggression_pact'] = True
                non_aggression_pacts.append({'id': target_country_id, 'name': empire_name})
                treaties.append({'country_id': target_country_id, 'empire_name': empire_name, 'type': 'non_aggression_pact'})

            if 'commercial_pact=yes' in rel_text:
                relation_info['commercial_pact'] = True
                commercial_pacts.append({'id': target_country_id, 'name': empire_name})
                treaties.append({'country_id': target_country_id, 'empire_name': empire_name, 'type': 'commercial_pact'})

            if 'migration_treaty=yes' in rel_text or 'migration_pact=yes' in rel_text:
                relation_info['migration_treaty'] = True
                migration_treaties.append({'id': target_country_id, 'name': empire_name})
                treaties.append({'country_id': target_country_id, 'empire_name': empire_name, 'type': 'migration_treaty'})

            if 'sensor_link=yes' in rel_text:
                relation_info['sensor_link'] = True
                sensor_links.append({'id': target_country_id, 'name': empire_name})
                treaties.append({'country_id': target_country_id, 'empire_name': empire_name, 'type': 'sensor_link'})

            if 'closed_borders=yes' in rel_text:
                relation_info['closed_borders'] = True
                closed_borders.append({'id': target_country_id, 'name': empire_name})
                treaties.append({'country_id': target_country_id, 'empire_name': empire_name, 'type': 'closed_borders'})

            if 'rival=yes' in rel_text or 'rivalry=yes' in rel_text:
                relation_info['rival'] = True
                rivals.append({'id': target_country_id, 'name': empire_name})
                treaties.append({'country_id': target_country_id, 'empire_name': empire_name, 'type': 'rival'})

            if 'research_agreement=yes' in rel_text:
                relation_info['research_agreement'] = True
                treaties.append({'country_id': target_country_id, 'empire_name': empire_name, 'type': 'research_agreement'})

            if 'embassy=yes' in rel_text:
                relation_info['embassy'] = True

            if 'truce=' in rel_text and 'truce' not in rel_text.split('=')[0]:
                relation_info['has_truce'] = True

            if 'communications=yes' in rel_text:
                relation_info['has_contact'] = True

            relations_found.append(relation_info)

        # Build result
        result['relations'] = relations_found
        result['allies'] = allies
        result['rivals'] = rivals
        result['defensive_pacts'] = defensive_pacts
        result['non_aggression_pacts'] = non_aggression_pacts
        result['closed_borders'] = closed_borders
        result['migration_treaties'] = migration_treaties
        result['commercial_pacts'] = commercial_pacts
        result['sensor_links'] = sensor_links
        result['treaties'] = treaties
        result['relation_count'] = len(relations_found)
        result['federation'] = federation_id

        # Summarize by opinion
        positive_relations = len([r for r in relations_found if r.get('opinion', 0) > 0])
        negative_relations = len([r for r in relations_found if r.get('opinion', 0) < 0])
        neutral_relations = len([r for r in relations_found if r.get('opinion', 0) == 0])

        result['summary'] = {
            'positive': positive_relations,
            'negative': negative_relations,
            'neutral': neutral_relations,
            'total_contacts': len(relations_found)
        }

        return result

    def _get_diplomacy_regex(self) -> dict:
        """Get diplomatic relations using regex (fallback method)."""
        result = {
            'relations': [],
            'treaties': [],
            'allies': [],
            'rivals': [],
            'federation': None,
            'defensive_pacts': [],
            'non_aggression_pacts': [],
            'closed_borders': [],
            'migration_treaties': [],
            'commercial_pacts': [],
            'sensor_links': [],
        }

        player_id = self.get_player_empire_id()
        player_chunk = self._find_player_country_content(player_id)
        if not player_chunk:
            result['error'] = "Could not find player country"
            return result

        # Get country name mappings for resolving IDs to empire names
        country_names = self._get_country_names_map()

        # Find relations_manager section
        rel_match = re.search(r'relations_manager=\s*\{', player_chunk)
        if not rel_match:
            result['error'] = "Could not find relations_manager section"
            return result

        rel_block = self._extract_braced_block(player_chunk[rel_match.start():], "relations_manager")
        if not rel_block:
            result['error'] = "Could not parse relations_manager block"
            return result

        relations_found: list[dict] = []
        allies: list[dict] = []  # List of {id, name}
        rivals: list[dict] = []
        defensive_pacts: list[dict] = []
        non_aggression_pacts: list[dict] = []
        closed_borders: list[dict] = []
        migration_treaties: list[dict] = []
        commercial_pacts: list[dict] = []
        sensor_links: list[dict] = []
        treaties: list[dict] = []  # List of {country_id, empire_name, type}

        for match in re.finditer(r'\brelation\s*=\s*\{', rel_block):
            rel_start = match.start()
            brace_count = 0
            rel_end = None
            for i, char in enumerate(rel_block[rel_start:], rel_start):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        rel_end = i + 1
                        break
            if rel_end is None:
                continue

            rel_text = rel_block[rel_start:rel_end]

            # Only process relations where owner=player_id (not hardcoded 0)
            if not re.search(rf'\bowner={player_id}\b', rel_text):
                continue

            relation_info = {}

            # Extract country ID and resolve to name
            country_match = re.search(r'\bcountry=(\d+)', rel_text)
            if country_match:
                relation_info['country_id'] = int(country_match.group(1))
            country_id = relation_info.get('country_id')
            if country_id is None:
                continue

            # Resolve empire name
            relation_info['empire_name'] = country_names.get(country_id, f"Empire {country_id}")

            # Extract trust
            trust_match = re.search(r'\btrust=(\d+)', rel_text)
            if trust_match:
                relation_info['trust'] = int(trust_match.group(1))

            # Extract relation score
            rel_current = re.search(r'\brelation_current=([-\d]+)', rel_text)
            if rel_current:
                relation_info['opinion'] = int(rel_current.group(1))

            # Get the resolved empire name for this country
            empire_name = relation_info['empire_name']

            # Check for treaties/agreements (some vary by game version)
            if 'alliance=yes' in rel_text or 'defensive_pact=yes' in rel_text:
                relation_info['defensive_pact'] = True
                defensive_pacts.append({'id': country_id, 'name': empire_name})
                allies.append({'id': country_id, 'name': empire_name})
                treaties.append({'country_id': country_id, 'empire_name': empire_name, 'type': 'defensive_pact'})
            if 'non_aggression_pact=yes' in rel_text:
                relation_info['non_aggression_pact'] = True
                non_aggression_pacts.append({'id': country_id, 'name': empire_name})
                treaties.append({'country_id': country_id, 'empire_name': empire_name, 'type': 'non_aggression_pact'})
            if 'commercial_pact=yes' in rel_text:
                relation_info['commercial_pact'] = True
                commercial_pacts.append({'id': country_id, 'name': empire_name})
                treaties.append({'country_id': country_id, 'empire_name': empire_name, 'type': 'commercial_pact'})
            if 'migration_treaty=yes' in rel_text or 'migration_pact=yes' in rel_text:
                relation_info['migration_treaty'] = True
                migration_treaties.append({'id': country_id, 'name': empire_name})
                treaties.append({'country_id': country_id, 'empire_name': empire_name, 'type': 'migration_treaty'})
            if 'sensor_link=yes' in rel_text:
                relation_info['sensor_link'] = True
                sensor_links.append({'id': country_id, 'name': empire_name})
                treaties.append({'country_id': country_id, 'empire_name': empire_name, 'type': 'sensor_link'})
            if 'closed_borders=yes' in rel_text:
                relation_info['closed_borders'] = True
                closed_borders.append({'id': country_id, 'name': empire_name})
                treaties.append({'country_id': country_id, 'empire_name': empire_name, 'type': 'closed_borders'})
            if 'rival=yes' in rel_text or 'rivalry=yes' in rel_text:
                relation_info['rival'] = True
                rivals.append({'id': country_id, 'name': empire_name})
                treaties.append({'country_id': country_id, 'empire_name': empire_name, 'type': 'rival'})

            if 'research_agreement=yes' in rel_text:
                relation_info['research_agreement'] = True
                treaties.append({'country_id': country_id, 'empire_name': empire_name, 'type': 'research_agreement'})
            if 'embassy=yes' in rel_text:
                relation_info['embassy'] = True
            if 'truce=' in rel_text and 'truce' not in rel_text.split('=')[0]:
                relation_info['has_truce'] = True

            # Check for communications
            if 'communications=yes' in rel_text:
                relation_info['has_contact'] = True

            relations_found.append(relation_info)

        # Full lists (no truncation); callers that need caps should slice.
        result['relations'] = relations_found
        result['allies'] = allies
        result['rivals'] = rivals
        result['defensive_pacts'] = defensive_pacts
        result['non_aggression_pacts'] = non_aggression_pacts
        result['closed_borders'] = closed_borders
        result['migration_treaties'] = migration_treaties
        result['commercial_pacts'] = commercial_pacts
        result['sensor_links'] = sensor_links
        result['treaties'] = treaties
        result['relation_count'] = len(relations_found)

        # Check for federation membership
        fed_match = re.search(r'\bfederation=(\d+)', player_chunk)
        if fed_match and fed_match.group(1) != '4294967295':  # Not null
            result['federation'] = int(fed_match.group(1))

        # Summarize by opinion
        positive_relations = len([r for r in relations_found if r.get('opinion', 0) > 0])
        negative_relations = len([r for r in relations_found if r.get('opinion', 0) < 0])
        neutral_relations = len([r for r in relations_found if r.get('opinion', 0) == 0])

        result['summary'] = {
            'positive': positive_relations,
            'negative': negative_relations,
            'neutral': neutral_relations,
            'total_contacts': len(relations_found)
        }

        return result

    def get_federation_details(self) -> dict:
        """Get details for the player's federation (if any)."""
        # Dispatch to Rust version when session is active
        session = _get_active_session()
        if session:
            return self._get_federation_details_rust()
        return self._get_federation_details_regex()

    def _get_federation_details_rust(self) -> dict:
        """Rust-optimized version using get_entry.

        Uses direct parsed JSON access instead of regex on raw gamestate.
        Benefits:
        - No regex parsing on raw text
        - No truncation limits
        - Handles nested structures correctly
        """
        session = _get_active_session()
        if not session:
            return self._get_federation_details_regex()

        result = {
            "federation_id": None,
            "type": None,
            "level": None,
            "cohesion": None,
            "experience": None,
            "laws": {},
            "members": [],
            "president": None,
        }

        # Get player's country entry via Rust session
        player_id = self.get_player_empire_id()
        player_country = self._get_player_country_entry(player_id)
        if not player_country or not isinstance(player_country, dict):
            return result

        # Get federation ID from player's country data
        fed_id = player_country.get('federation')
        if fed_id is None:
            return result

        try:
            fed_id = int(fed_id)
        except (ValueError, TypeError):
            return result

        # 4294967295 represents "none" in Stellaris
        if fed_id == 4294967295:
            return result

        result["federation_id"] = fed_id

        # Get federation entry directly by ID
        fed_entry = session.get_entry('federation', str(fed_id))
        if not fed_entry or not isinstance(fed_entry, dict):
            return result

        # Extract president (try 'leader' first, then 'president')
        leader = fed_entry.get('leader')
        if leader is not None:
            try:
                result["president"] = int(leader)
            except (ValueError, TypeError):
                pass
        president = fed_entry.get('president')
        if president is not None:
            try:
                result["president"] = int(president)
            except (ValueError, TypeError):
                pass

        # Extract members
        members = fed_entry.get('members')
        if members and isinstance(members, list):
            member_ids = []
            for m in members:
                try:
                    member_ids.append(int(m))
                except (ValueError, TypeError):
                    continue
            result["members"] = member_ids

        # Extract federation_progression data
        progression = fed_entry.get('federation_progression')
        if progression and isinstance(progression, dict):
            # Federation type
            fed_type = progression.get('federation_type')
            if not fed_type:
                fed_type = progression.get('type')
            if fed_type and isinstance(fed_type, str):
                result["type"] = fed_type

            # Experience (can be string or number)
            exp = progression.get('experience')
            if exp is not None:
                try:
                    exp_str = str(exp)
                    result["experience"] = float(exp_str) if '.' in exp_str else int(exp_str)
                except (ValueError, TypeError):
                    pass

            # Cohesion (can be string or number)
            cohesion = progression.get('cohesion')
            if cohesion is not None:
                try:
                    coh_str = str(cohesion)
                    result["cohesion"] = float(coh_str) if '.' in coh_str else int(coh_str)
                except (ValueError, TypeError):
                    pass

            # Level (try 'levels' first, then 'level')
            level = progression.get('levels')
            if level is None:
                level = progression.get('level')
            if level is not None:
                try:
                    result["level"] = int(level)
                except (ValueError, TypeError):
                    pass

            # Laws
            laws = progression.get('laws')
            if laws and isinstance(laws, dict):
                for key, value in laws.items():
                    if isinstance(value, str):
                        result["laws"][key] = value
                    else:
                        result["laws"][key] = str(value)

        return result

    def _get_federation_details_regex(self) -> dict:
        """Original regex implementation - fallback for non-session use."""
        result = {
            "federation_id": None,
            "type": None,
            "level": None,
            "cohesion": None,
            "experience": None,
            "laws": {},
            "members": [],
            "president": None,
        }

        player_id = self.get_player_empire_id()
        player_chunk = self._find_player_country_content(player_id)
        if not player_chunk:
            return result

        fed_match = re.search(r'\bfederation=(\d+)', player_chunk)
        if not fed_match:
            return result

        fed_id = int(fed_match.group(1))
        if fed_id == 4294967295:
            return result

        result["federation_id"] = fed_id

        federation_section = self._extract_section("federation")
        if not federation_section:
            return result

        federation_block = self._extract_entry_block(federation_section, fed_id)
        if not federation_block:
            return result

        leader_match = re.search(r'\bleader=(\d+)', federation_block)
        if leader_match:
            result["president"] = int(leader_match.group(1))
        president_match = re.search(r'\bpresident=(\d+)', federation_block)
        if president_match:
            result["president"] = int(president_match.group(1))

        members_match = re.search(r'\bmembers\s*=\s*\{([^}]*)\}', federation_block, re.DOTALL)
        if members_match:
            member_ids = [int(x) for x in re.findall(r'\d+', members_match.group(1))]
            result["members"] = member_ids

        progression_block = self._extract_braced_block(federation_block, "federation_progression")
        if progression_block:
            type_match = re.search(r'\bfederation_type="([^"]+)"', progression_block)
            if not type_match:
                type_match = re.search(r'\btype="([^"]+)"', progression_block)
            if type_match:
                result["type"] = type_match.group(1)

            exp_match = re.search(r'\bexperience=([\d.]+)', progression_block)
            if exp_match:
                value = exp_match.group(1)
                result["experience"] = float(value) if "." in value else int(value)

            cohesion_match = re.search(r'\bcohesion=([\d.]+)', progression_block)
            if cohesion_match:
                value = cohesion_match.group(1)
                result["cohesion"] = float(value) if "." in value else int(value)

            level_match = re.search(r'\blevels=(\d+)', progression_block)
            if not level_match:
                level_match = re.search(r'\blevel=(\d+)', progression_block)
            if level_match:
                result["level"] = int(level_match.group(1))

            laws_block = self._extract_braced_block(progression_block, "laws")
            if laws_block:
                open_brace = laws_block.find('{')
                close_brace = laws_block.rfind('}')
                if open_brace != -1 and close_brace != -1 and close_brace > open_brace:
                    inner = laws_block[open_brace + 1 : close_brace]
                    for key, value in re.findall(r'\b([A-Za-z0-9_]+)=([A-Za-z0-9_]+)\b', inner):
                        result["laws"][key] = value

        return result

    def get_galactic_community(
        self,
        limit_members: int = 50,
        limit_resolutions: int = 25,
        limit_council: int = 10,
    ) -> dict:
        """Get a compact summary of the Galactic Community and Council."""
        # Dispatch to Rust version when session is active
        session = _get_active_session()
        if session:
            return self._get_galactic_community_rust(limit_members, limit_resolutions, limit_council)
        return self._get_galactic_community_regex(limit_members, limit_resolutions, limit_council)

    def _get_galactic_community_rust(
        self,
        limit_members: int = 50,
        limit_resolutions: int = 25,
        limit_council: int = 10,
    ) -> dict:
        """Rust-optimized version using extract_sections.

        Uses direct parsed JSON access instead of regex on raw gamestate.
        Benefits:
        - No regex parsing on raw text
        - No truncation limits
        - Handles nested structures correctly
        """
        session = _get_active_session()
        if not session:
            return self._get_galactic_community_regex(limit_members, limit_resolutions, limit_council)

        result = {
            "members": [],
            "members_count": 0,
            "player_is_member": False,
            "council_members": [],
            "council_positions": None,
            "council_veto": None,
            "emissaries_count": 0,
            "voting_resolution_id": None,
            "last_resolution_id": None,
            "days_until_election": None,
            "community_formed": None,
            "council_established": None,
            "proposed_count": 0,
            "passed_count": 0,
            "failed_count": 0,
            "resolutions": {
                "proposed": [],
                "passed": [],
                "failed": [],
            },
        }

        # Use extract_sections for this small top-level section
        data = session.extract_sections(['galactic_community'])
        gc = data.get('galactic_community')

        # Section might not exist if no galactic community formed
        if not gc or not isinstance(gc, dict):
            return result

        def parse_int_list(value) -> list[int]:
            """Convert parsed list of string IDs to integers, filtering invalid values."""
            if not value:
                return []
            if isinstance(value, list):
                result_list = []
                for v in value:
                    try:
                        int_val = int(v)
                        # Filter out 4294967295 (represents "none" in Stellaris)
                        if int_val != 4294967295:
                            result_list.append(int_val)
                    except (ValueError, TypeError):
                        continue
                return result_list
            return []

        # Extract member lists
        members = parse_int_list(gc.get('members'))
        council = parse_int_list(gc.get('council'))
        proposed = parse_int_list(gc.get('proposed'))
        passed = parse_int_list(gc.get('passed'))
        failed = parse_int_list(gc.get('failed'))
        emissaries = parse_int_list(gc.get('emissaries'))

        result["members_count"] = len(members)
        result["members"] = members[: max(0, int(limit_members))]
        result["council_members"] = council[: max(0, int(limit_council))]

        player_id = self.get_player_empire_id()
        result["player_is_member"] = player_id in members

        result["proposed_count"] = len(proposed)
        result["passed_count"] = len(passed)
        result["failed_count"] = len(failed)
        result["resolutions"]["proposed"] = proposed[: max(0, int(limit_resolutions))]
        result["resolutions"]["passed"] = passed[: max(0, int(limit_resolutions))]
        result["resolutions"]["failed"] = failed[: max(0, int(limit_resolutions))]

        # Extract scalar values from parsed dict
        voting = gc.get('voting')
        if voting is not None:
            try:
                result["voting_resolution_id"] = int(voting)
            except (ValueError, TypeError):
                pass

        last = gc.get('last')
        if last is not None:
            try:
                result["last_resolution_id"] = int(last)
            except (ValueError, TypeError):
                pass

        days = gc.get('days')
        if days is not None:
            try:
                result["days_until_election"] = int(days)
            except (ValueError, TypeError):
                pass

        # String values
        community_formed = gc.get('community_formed')
        if community_formed and isinstance(community_formed, str):
            result["community_formed"] = community_formed

        council_established = gc.get('council_established')
        if council_established and isinstance(council_established, str):
            result["council_established"] = council_established

        # Integer values
        council_positions = gc.get('council_positions')
        if council_positions is not None:
            try:
                result["council_positions"] = int(council_positions)
            except (ValueError, TypeError):
                pass

        # Boolean value (stored as "yes"/"no" string)
        council_veto = gc.get('council_veto')
        if council_veto is not None:
            result["council_veto"] = council_veto == 'yes'

        result["emissaries_count"] = len(emissaries)

        return result

    def _get_galactic_community_regex(
        self,
        limit_members: int = 50,
        limit_resolutions: int = 25,
        limit_council: int = 10,
    ) -> dict:
        """Original regex implementation - fallback for non-session use."""
        result = {
            "members": [],
            "members_count": 0,
            "player_is_member": False,
            "council_members": [],
            "council_positions": None,
            "council_veto": None,
            "emissaries_count": 0,
            "voting_resolution_id": None,
            "last_resolution_id": None,
            "days_until_election": None,
            "community_formed": None,
            "council_established": None,
            "proposed_count": 0,
            "passed_count": 0,
            "failed_count": 0,
            "resolutions": {
                "proposed": [],
                "passed": [],
                "failed": [],
            },
        }

        section = self._extract_section("galactic_community")
        if not section:
            return result

        def parse_int_list(block_key: str) -> list[int]:
            block = self._extract_braced_block(section, block_key)
            if not block:
                return []
            open_brace = block.find("{")
            close_brace = block.rfind("}")
            if open_brace == -1 or close_brace == -1 or close_brace <= open_brace:
                return []
            values = [int(x) for x in re.findall(r"\d+", block[open_brace + 1 : close_brace])]
            return [v for v in values if v != 4294967295]

        members = parse_int_list("members")
        council = parse_int_list("council")
        proposed = parse_int_list("proposed")
        passed = parse_int_list("passed")
        failed = parse_int_list("failed")

        result["members_count"] = len(members)
        result["members"] = members[: max(0, int(limit_members))]
        result["council_members"] = council[: max(0, int(limit_council))]

        player_id = self.get_player_empire_id()
        result["player_is_member"] = player_id in members

        result["proposed_count"] = len(proposed)
        result["passed_count"] = len(passed)
        result["failed_count"] = len(failed)
        result["resolutions"]["proposed"] = proposed[: max(0, int(limit_resolutions))]
        result["resolutions"]["passed"] = passed[: max(0, int(limit_resolutions))]
        result["resolutions"]["failed"] = failed[: max(0, int(limit_resolutions))]

        voting_match = re.search(r"\bvoting=(\d+)", section)
        if voting_match:
            result["voting_resolution_id"] = int(voting_match.group(1))

        last_match = re.search(r"\blast=(\d+)", section)
        if last_match:
            result["last_resolution_id"] = int(last_match.group(1))

        days_match = re.search(r"\bdays=(\d+)", section)
        if days_match:
            result["days_until_election"] = int(days_match.group(1))

        formed_match = re.search(r'\bcommunity_formed\s*=\s*"([^"]+)"', section)
        if formed_match:
            result["community_formed"] = formed_match.group(1)

        established_match = re.search(r'\bcouncil_established\s*=\s*"([^"]+)"', section)
        if established_match:
            result["council_established"] = established_match.group(1)

        positions_match = re.search(r"\bcouncil_positions=(\d+)", section)
        if positions_match:
            result["council_positions"] = int(positions_match.group(1))

        veto_match = re.search(r"\bcouncil_veto=(yes|no)\b", section)
        if veto_match:
            result["council_veto"] = veto_match.group(1) == "yes"

        emissaries = parse_int_list("emissaries")
        result["emissaries_count"] = len(emissaries)

        return result

    def get_subjects(self, limit: int = 25) -> dict:
        """Get subject/overlord agreements involving the player.

        Parses the top-level `agreements` section (Overlord DLC style).
        Returns compact summaries only (no huge discrete term payloads).
        """
        # Dispatch to Rust version when session is active
        session = _get_active_session()
        if session:
            return self._get_subjects_rust(limit)
        return self._get_subjects_regex(limit)

    def _get_subjects_rust(self, limit: int = 25) -> dict:
        """Rust-optimized version using extract_sections.

        Uses direct parsed JSON access instead of regex on raw gamestate.
        Benefits:
        - No regex parsing on raw text
        - No truncation limits
        - Handles nested structures correctly
        """
        session = _get_active_session()
        if not session:
            return self._get_subjects_regex(limit)

        result = {
            "player_id": self.get_player_empire_id(),
            "as_overlord": {"subjects": [], "count": 0},
            "as_subject": {"overlords": [], "count": 0},
            "count": 0,
        }

        # Use extract_sections for this section
        data = session.extract_sections(['agreements'])
        agreements_section = data.get('agreements')

        # Section might not exist if no agreements
        if not agreements_section or not isinstance(agreements_section, dict):
            return result

        # The inner 'agreements' dict contains the actual entries
        inner_agreements = agreements_section.get('agreements')
        if not inner_agreements or not isinstance(inner_agreements, dict):
            return result

        player_id = result["player_id"]
        overlord_entries: list[dict] = []
        subject_entries: list[dict] = []

        def parse_terms_rust(term_data: dict) -> dict:
            """Parse term_data from parsed dict structure."""
            if not isinstance(term_data, dict):
                return {}

            terms: dict = {}

            # Boolean fields (convert "yes"/"no" to bool)
            for bool_key in [
                "can_subject_be_integrated",
                "can_subject_do_diplomacy",
                "can_subject_vote",
                "has_access",
                "has_sensors",
                "has_cooldown_on_first_renegotiation",
            ]:
                val = term_data.get(bool_key)
                if val is not None:
                    terms[bool_key] = (val == "yes") if isinstance(val, str) else bool(val)

            # String fields
            for str_key in [
                "joins_overlord_wars",
                "calls_overlord_to_war",
                "subject_expansion_type",
            ]:
                val = term_data.get(str_key)
                if val and isinstance(val, str):
                    terms[str_key] = val

            # Agreement preset
            preset = term_data.get("agreement_preset")
            if preset and isinstance(preset, str):
                terms["agreement_preset"] = preset

            # Forced initial loyalty
            fil = term_data.get("forced_initial_loyalty")
            if fil is not None:
                try:
                    terms["forced_initial_loyalty"] = int(fil)
                except (ValueError, TypeError):
                    pass

            # Discrete terms (list of {key, value} dicts)
            discrete_terms = term_data.get("discrete_terms")
            if discrete_terms and isinstance(discrete_terms, list):
                parsed_discrete = {}
                for item in discrete_terms:
                    if isinstance(item, dict):
                        k = item.get("key")
                        v = item.get("value")
                        if k and v:
                            parsed_discrete[str(k)] = str(v)
                if parsed_discrete:
                    terms["discrete_terms"] = parsed_discrete

            # Resource terms (list of {key, value} dicts)
            resource_terms = term_data.get("resource_terms")
            if resource_terms and isinstance(resource_terms, list):
                parsed_resource = {}
                for item in resource_terms:
                    if isinstance(item, dict):
                        k = item.get("key")
                        v = item.get("value")
                        if k and v is not None:
                            try:
                                parsed_resource[str(k)] = float(v)
                            except (ValueError, TypeError):
                                continue
                if parsed_resource:
                    terms["resource_terms"] = parsed_resource

            return terms

        # Iterate through all agreements
        for agreement_id, adata in inner_agreements.items():
            if not isinstance(adata, dict):
                continue

            # Get owner and target IDs
            owner = adata.get("owner")
            target = adata.get("target")
            if owner is None or target is None:
                continue

            try:
                owner_id = int(owner)
                target_id = int(target)
            except (ValueError, TypeError):
                continue

            # 4294967295 represents "none" in Stellaris
            if owner_id == 4294967295 or target_id == 4294967295:
                continue

            # Extract basic fields
            active_status = adata.get("active_status")
            date_added = adata.get("date_added")
            date_changed = adata.get("date_changed")

            # Parse term_data
            term_data_dict = adata.get("term_data", {})
            term_data = parse_terms_rust(term_data_dict) if isinstance(term_data_dict, dict) else {}

            # Parse subject_specialization
            specialization = None
            spec_level = None
            spec_data = adata.get("subject_specialization")
            if spec_data and isinstance(spec_data, dict):
                spec_type = spec_data.get("specialist_type")
                if spec_type and isinstance(spec_type, str):
                    specialization = spec_type
                level = spec_data.get("level")
                if level is not None:
                    try:
                        spec_level = int(level)
                    except (ValueError, TypeError):
                        spec_level = 0

            entry = {
                "agreement_id": str(agreement_id),
                "owner_id": owner_id,
                "target_id": target_id,
                "active_status": active_status if isinstance(active_status, str) else None,
                "date_added": date_added if isinstance(date_added, str) else None,
                "date_changed": date_changed if isinstance(date_changed, str) else None,
                "preset": term_data.get("agreement_preset"),
                "specialization": specialization,
                "specialization_level": spec_level,
                "terms": term_data,
            }

            if owner_id == player_id:
                overlord_entries.append(entry)
            if target_id == player_id:
                subject_entries.append(entry)

        # Sort as in regex version
        overlord_entries.sort(key=lambda e: (e.get("preset") or "", e.get("target_id", 0)))
        subject_entries.sort(key=lambda e: (e.get("preset") or "", e.get("owner_id", 0)))

        result["as_overlord"]["count"] = len(overlord_entries)
        result["as_overlord"]["subjects"] = overlord_entries[: max(0, min(int(limit), 50))]
        result["as_subject"]["count"] = len(subject_entries)
        result["as_subject"]["overlords"] = subject_entries[: max(0, min(int(limit), 50))]
        result["count"] = result["as_overlord"]["count"] + result["as_subject"]["count"]

        return result

    def _get_subjects_regex(self, limit: int = 25) -> dict:
        """Original regex implementation - fallback for non-session use."""
        result = {
            "player_id": self.get_player_empire_id(),
            "as_overlord": {"subjects": [], "count": 0},
            "as_subject": {"overlords": [], "count": 0},
            "count": 0,
        }

        agreements_section = self._extract_section("agreements")
        if not agreements_section:
            return result

        inner_match = re.search(r"\n\tagreements\s*=\s*\{", agreements_section)
        if not inner_match:
            inner_match = re.search(r"\bagreements\s*=\s*\{", agreements_section)
        if not inner_match:
            return result

        start = inner_match.start() + (1 if agreements_section[inner_match.start()] == "\n" else 0)
        brace_count = 0
        end = None
        for i, char in enumerate(agreements_section[start:], start):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break

        if end is None:
            return result

        agreements_block = agreements_section[start:end]
        player_id = result["player_id"]

        overlord_entries: list[dict] = []
        subject_entries: list[dict] = []

        def parse_terms(term_data_block: str) -> dict:
            terms: dict = {}

            def parse_yes_no(key: str) -> None:
                m = re.search(rf"\b{re.escape(key)}=(yes|no)\b", term_data_block)
                if m:
                    terms[key] = m.group(1) == "yes"

            for bool_key in [
                "can_subject_be_integrated",
                "can_subject_do_diplomacy",
                "can_subject_vote",
                "has_access",
                "has_sensors",
                "has_cooldown_on_first_renegotiation",
            ]:
                parse_yes_no(bool_key)

            for str_key in [
                "joins_overlord_wars",
                "calls_overlord_to_war",
                "subject_expansion_type",
            ]:
                m = re.search(rf"\b{re.escape(str_key)}=([A-Za-z0-9_]+)\b", term_data_block)
                if m:
                    terms[str_key] = m.group(1)

            preset_match = re.search(r'\bagreement_preset="([^"]+)"', term_data_block)
            if preset_match:
                terms["agreement_preset"] = preset_match.group(1)

            fil_match = re.search(r"\bforced_initial_loyalty=([-\d]+)", term_data_block)
            if fil_match:
                terms["forced_initial_loyalty"] = int(fil_match.group(1))

            discrete_terms_block = self._extract_braced_block(term_data_block, "discrete_terms")
            if discrete_terms_block:
                pairs = re.findall(r"\bkey=([A-Za-z0-9_]+)\s*value=([A-Za-z0-9_]+)", discrete_terms_block)
                if pairs:
                    terms["discrete_terms"] = {k: v for k, v in pairs}

            resource_terms_block = self._extract_braced_block(term_data_block, "resource_terms")
            if resource_terms_block:
                pairs = re.findall(r"\bkey=([A-Za-z0-9_]+)\s*value=([-\d.]+)", resource_terms_block)
                if pairs:
                    parsed: dict[str, float] = {}
                    for k, v in pairs:
                        try:
                            parsed[k] = float(v)
                        except ValueError:
                            continue
                    if parsed:
                        terms["resource_terms"] = parsed

            return terms

        for match in re.finditer(r"\n\t\t(\d+)\s*=\s*\{", agreements_block):
            agreement_id = match.group(1)
            entry_start = match.start()

            brace_count = 0
            entry_end = None
            for i, char in enumerate(agreements_block[entry_start:], entry_start):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        entry_end = i + 1
                        break
            if entry_end is None:
                continue

            block = agreements_block[entry_start:entry_end]

            owner_match = re.search(r"\bowner=(\d+)", block)
            target_match = re.search(r"\btarget=(\d+)", block)
            if not owner_match or not target_match:
                continue

            owner_id = int(owner_match.group(1))
            target_id = int(target_match.group(1))

            if owner_id == 4294967295 or target_id == 4294967295:
                continue

            status_match = re.search(r"\bactive_status=([A-Za-z0-9_]+)", block)
            date_added_match = re.search(r'\bdate_added=\s*"([^"]+)"', block)
            date_changed_match = re.search(r'\bdate_changed=\s*"([^"]+)"', block)

            term_data = {}
            term_block = self._extract_braced_block(block, "term_data")
            if term_block:
                term_data = parse_terms(term_block)

            specialization = None
            spec_level = None
            spec_block = self._extract_braced_block(block, "subject_specialization")
            if spec_block:
                stype_match = re.search(r'\bspecialist_type="([^"]+)"', spec_block)
                if stype_match:
                    specialization = stype_match.group(1)
                slevel_match = re.search(r"\blevel=(\d+)", spec_block)
                if slevel_match:
                    spec_level = int(slevel_match.group(1))

            entry = {
                "agreement_id": str(agreement_id),
                "owner_id": owner_id,
                "target_id": target_id,
                "active_status": status_match.group(1) if status_match else None,
                "date_added": date_added_match.group(1) if date_added_match else None,
                "date_changed": date_changed_match.group(1) if date_changed_match else None,
                "preset": term_data.get("agreement_preset"),
                "specialization": specialization,
                "specialization_level": spec_level,
                "terms": term_data,
            }

            if owner_id == player_id:
                overlord_entries.append(entry)
            if target_id == player_id:
                subject_entries.append(entry)

        overlord_entries.sort(key=lambda e: (e.get("preset") or "", e.get("target_id", 0)))
        subject_entries.sort(key=lambda e: (e.get("preset") or "", e.get("owner_id", 0)))

        result["as_overlord"]["count"] = len(overlord_entries)
        result["as_overlord"]["subjects"] = overlord_entries[: max(0, min(int(limit), 50))]
        result["as_subject"]["count"] = len(subject_entries)
        result["as_subject"]["overlords"] = subject_entries[: max(0, min(int(limit), 50))]
        result["count"] = result["as_overlord"]["count"] + result["as_subject"]["count"]

        return result

    def get_fallen_empires(self) -> dict:
        """Get information about all Fallen Empires in the galaxy (both dormant and awakened).

        Fallen Empires are ancient, powerful civilizations. They start dormant but can
        awaken in the late game, becoming major threats or allies.

        Returns:
            Dict with:
                - fallen_empires: List of all FEs with status
                - dormant_count: Number still dormant
                - awakened_count: Number that have awakened
                - war_in_heaven: Whether War in Heaven is active
        """
        # Use Rust-optimized version when session is active
        session = _get_active_session()
        if session:
            return self._get_fallen_empires_rust()
        return self._get_fallen_empires_regex()

    def _get_fallen_empires_rust(self) -> dict:
        """Optimized Rust-based implementation of get_fallen_empires.

        Uses iter_section to iterate countries once instead of regex scanning
        the 84MB gamestate multiple times.
        """
        session = _get_active_session()
        if not session:
            return self._get_fallen_empires_regex()

        result = {
            'fallen_empires': [],
            'dormant_count': 0,
            'awakened_count': 0,
            'total_count': 0,
            'war_in_heaven': False,
        }

        # Get player military power for comparison
        player_status = self.get_player_status()
        player_military = player_status.get('military_power', 0)

        # Check for War in Heaven using contains_tokens
        try:
            wih_result = session.contains_tokens(['war_in_heaven=yes'])
            if wih_result.get('matches', {}).get('war_in_heaven=yes'):
                result['war_in_heaven'] = True
        except Exception:
            pass

        # FE archetype mapping
        FE_ARCHETYPES = {
            'xenophile': ('Benevolent Interventionists', 'May awaken to "guide" younger races'),
            'xenophobe': ('Militant Isolationists', 'Hostile if you colonize near them'),
            'materialist': ('Ancient Caretakers', 'Protect galaxy from synthetic threats'),
            'spiritualist': ('Holy Guardians', 'Protect holy worlds, hate tomb worlds'),
        }

        # Iterate countries once and filter for fallen empires
        for cid, country in session.iter_section('country'):
            if not isinstance(country, dict):
                continue

            ctype = country.get('type')
            if ctype not in ('fallen_empire', 'awakened_fallen_empire'):
                continue

            status = 'awakened' if ctype == 'awakened_fallen_empire' else 'dormant'

            empire_info = {
                'country_id': int(cid),
                'name': 'Unknown Fallen Empire',
                'status': status,
                'archetype': 'Unknown',
                'archetype_behavior': '',
                'military_power': 0,
                'power_ratio': 0.0,
                'ethics': None,
            }

            # Extract name from nested structure
            name_data = country.get('name')
            if isinstance(name_data, dict):
                variables = name_data.get('variables', [])
                for var in variables:
                    if isinstance(var, dict) and var.get('key') == 'adjective':
                        value = var.get('value', {})
                        if isinstance(value, dict):
                            raw_name = value.get('key', '')
                            empire_info['name'] = raw_name.replace('SPEC_', '').replace('_', ' ').title()
                            break

            # Extract ethics
            ethos_data = country.get('ethos')
            if isinstance(ethos_data, dict):
                ethic = ethos_data.get('ethic')
                if isinstance(ethic, list):
                    # Multiple ethics - prefer fanatic
                    for e in ethic:
                        if 'fanatic' in str(e):
                            empire_info['ethics'] = e
                            break
                    if not empire_info['ethics'] and ethic:
                        empire_info['ethics'] = ethic[0]
                elif ethic:
                    empire_info['ethics'] = ethic

                # Map to FE archetype
                if empire_info['ethics']:
                    for key, (archetype, behavior) in FE_ARCHETYPES.items():
                        if key in empire_info['ethics']:
                            empire_info['archetype'] = archetype
                            empire_info['archetype_behavior'] = behavior
                            break

            # Extract military power
            mil_power = country.get('military_power')
            if mil_power is not None:
                empire_info['military_power'] = float(mil_power)
                if player_military > 0:
                    empire_info['power_ratio'] = round(empire_info['military_power'] / player_military, 1)

            # Extract opinion of player from relations_manager
            rm = country.get('relations_manager')
            if isinstance(rm, dict):
                relations = rm.get('relation', [])
                if isinstance(relations, list):
                    for rel in relations:
                        if isinstance(rel, dict) and rel.get('country') == 0:
                            opinion = rel.get('opinion')
                            if opinion is not None:
                                empire_info['opinion_of_player'] = int(opinion)
                            break

            result['fallen_empires'].append(empire_info)

        # Count by status
        result['dormant_count'] = sum(1 for fe in result['fallen_empires'] if fe['status'] == 'dormant')
        result['awakened_count'] = sum(1 for fe in result['fallen_empires'] if fe['status'] == 'awakened')
        result['total_count'] = len(result['fallen_empires'])

        return result

    def _get_fallen_empires_regex(self) -> dict:
        """Original regex-based implementation - used as fallback."""
        # This is the original implementation, kept for fallback
        result = {
            'fallen_empires': [],
            'dormant_count': 0,
            'awakened_count': 0,
            'total_count': 0,
            'war_in_heaven': False,
        }

        # Get player military power for comparison
        player_status = self.get_player_status()
        player_military = player_status.get('military_power', 0)

        # Find country section and build country position index
        country_start = self._find_country_section_start()
        if country_start == -1:
            return result

        country_chunk = self.gamestate[country_start:]
        country_entries = [(int(m.group(1)), country_start + m.start())
                          for m in re.finditer(r'\n\t(\d+)=\n\t\{', country_chunk)]

        # Find all fallen empire types (both dormant and awakened)
        fe_positions = [(m.start(), 'dormant') for m in re.finditer(r'type="fallen_empire"', self.gamestate)]
        fe_positions += [(m.start(), 'awakened') for m in re.finditer(r'type="awakened_fallen_empire"', self.gamestate)]

        if not fe_positions:
            return result

        # Check for War in Heaven
        if 'war_in_heaven' in self.gamestate.lower():
            if re.search(r'(?<!no_)war_in_heaven\s*=\s*yes', self.gamestate):
                result['war_in_heaven'] = True

        # FE archetype mapping
        FE_ARCHETYPES = {
            'xenophile': ('Benevolent Interventionists', 'May awaken to "guide" younger races'),
            'xenophobe': ('Militant Isolationists', 'Hostile if you colonize near them'),
            'materialist': ('Ancient Caretakers', 'Protect galaxy from synthetic threats'),
            'spiritualist': ('Holy Guardians', 'Protect holy worlds, hate tomb worlds'),
        }

        # Process each fallen empire
        for fe_pos, status in fe_positions:
            # Find which country this belongs to
            country_id = None
            country_pos = None
            for cid, cpos in country_entries:
                if cpos < fe_pos:
                    country_id = cid
                    country_pos = cpos
                else:
                    break

            if country_id is None:
                continue

            # Get next country position for boundary
            next_pos = None
            for cid, cpos in country_entries:
                if cpos > country_pos:
                    next_pos = cpos
                    break

            block = self.gamestate[country_pos:next_pos] if next_pos else self.gamestate[country_pos:country_pos + 200000]

            # Extract empire details
            empire_info = {
                'country_id': country_id,
                'name': 'Unknown Fallen Empire',
                'status': status,
                'archetype': 'Unknown',
                'archetype_behavior': '',
                'military_power': 0,
                'power_ratio': 0.0,
                'ethics': None,
            }

            # Get name
            name_m = re.search(r'name=\n\t*\{[^}]*key="([^"]+)"', block)
            if name_m:
                raw_name = name_m.group(1)
                empire_info['name'] = raw_name.replace('SPEC_', '').replace('_', ' ').title()

            # Get ethics (determines FE archetype)
            ethos_m = re.search(r'ethos=\s*\{([^}]+)\}', block[:200000])
            if ethos_m:
                ethos_block = ethos_m.group(1)
                ethics_list = re.findall(r'ethic="(ethic_[^"]+)"', ethos_block)
                if ethics_list:
                    # Use the fanatic ethic if present
                    ethic = None
                    for e in ethics_list:
                        if 'fanatic' in e:
                            ethic = e
                            break
                    if not ethic:
                        ethic = ethics_list[0]

                    empire_info['ethics'] = ethic

                    # Map to FE archetype
                    for key, (archetype, behavior) in FE_ARCHETYPES.items():
                        if key in ethic:
                            empire_info['archetype'] = archetype
                            empire_info['archetype_behavior'] = behavior
                            break

            # Get military power
            mil_m = re.search(r'military_power=([\d.]+)', block)
            if mil_m:
                empire_info['military_power'] = float(mil_m.group(1))
                if player_military > 0:
                    empire_info['power_ratio'] = round(empire_info['military_power'] / player_military, 1)

            # Get their opinion of player
            opinion_m = re.search(r'relations_manager=.*?country=0[^}]*opinion=([-\d]+)', block[:80000], re.DOTALL)
            if opinion_m:
                empire_info['opinion_of_player'] = int(opinion_m.group(1))

            result['fallen_empires'].append(empire_info)

        # Count by status
        result['dormant_count'] = sum(1 for fe in result['fallen_empires'] if fe['status'] == 'dormant')
        result['awakened_count'] = sum(1 for fe in result['fallen_empires'] if fe['status'] == 'awakened')
        result['total_count'] = len(result['fallen_empires'])

        return result

    def get_espionage(self, limit: int = 20) -> dict:
        """Get active espionage operations (summary-first, capped)."""
        # Dispatch to Rust version when session is active
        session = _get_active_session()
        if session:
            return self._get_espionage_rust(limit)
        return self._get_espionage_regex(limit)

    def _get_espionage_rust(self, limit: int = 20) -> dict:
        """Rust-optimized version using extract_sections.

        Uses direct parsed JSON access instead of regex on raw gamestate.
        Benefits:
        - No regex parsing on raw text
        - No truncation limits
        - Handles nested structures correctly
        """
        session = _get_active_session()
        if not session:
            return self._get_espionage_regex(limit)

        limit = max(1, min(int(limit or 20), 50))

        result = {
            'player_id': self.get_player_empire_id(),
            'operations': [],
            'count': 0,
        }

        # Use extract_sections to get the espionage_operations section
        data = session.extract_sections(['espionage_operations'])
        espionage_section = data.get('espionage_operations')

        # Section might not exist if no espionage operations
        if not espionage_section or not isinstance(espionage_section, dict):
            return result

        # The inner 'operations' dict contains the actual entries
        operations_dict = espionage_section.get('operations')
        if not operations_dict or not isinstance(operations_dict, dict):
            return result

        operations_found: list[dict] = []

        for op_id, op_data in operations_dict.items():
            # P010: Entry might be string "none" (deleted)
            if not isinstance(op_data, dict):
                continue

            entry = {
                'operation_id': op_id,
                'target_country_id': None,
                'spy_network_id': None,
                'type': None,
                'difficulty': None,
                'days_left': None,
                'info': None,
                'log_entries': 0,
                'last_log': None,
            }

            # Extract target country ID
            target_data = op_data.get('target')
            if isinstance(target_data, dict):
                target_id = target_data.get('id')
                if target_id is not None:
                    try:
                        entry['target_country_id'] = int(target_id)
                    except (ValueError, TypeError):
                        pass

            # Extract spy_network ID
            spy_network = op_data.get('spy_network')
            if spy_network is not None:
                try:
                    entry['spy_network_id'] = int(spy_network)
                except (ValueError, TypeError):
                    pass

            # Extract type
            op_type = op_data.get('type')
            if op_type and isinstance(op_type, str):
                entry['type'] = op_type

            # Extract numeric fields
            for key in ['difficulty', 'days_left', 'info']:
                val = op_data.get(key)
                if val is not None:
                    try:
                        entry[key] = int(val)
                    except (ValueError, TypeError):
                        pass

            # Extract log entries
            log_data = op_data.get('log')
            if log_data and isinstance(log_data, list) and len(log_data) > 0:
                entry['log_entries'] = len(log_data)
                # Get last log entry
                last_entry = log_data[-1]
                if isinstance(last_entry, dict):
                    entry['last_log'] = {
                        'date': last_entry.get('date'),
                        'roll': None,
                        'skill': None,
                        'info': None,
                        'difficulty': None,
                    }
                    for log_key in ['roll', 'skill', 'info', 'difficulty']:
                        val = last_entry.get(log_key)
                        if val is not None:
                            try:
                                entry['last_log'][log_key] = int(val)
                            except (ValueError, TypeError):
                                pass

            operations_found.append(entry)
            if len(operations_found) >= limit:
                break

        result['operations'] = operations_found
        result['count'] = len(operations_found)
        return result

    def _get_espionage_regex(self, limit: int = 20) -> dict:
        """Original regex implementation - fallback for non-session mode."""
        limit = max(1, min(int(limit or 20), 50))

        result = {
            'player_id': self.get_player_empire_id(),
            'operations': [],
            'count': 0,
        }

        section = self._extract_section('espionage_operations')
        if not section:
            result['error'] = 'Could not find espionage_operations section'
            return result

        operations_block = self._extract_braced_block(section, 'operations') or ''
        if not operations_block:
            return result

        op_pattern = r'\n\t\t(\d+)=\n\t\t\{'
        operations_found: list[dict] = []

        for match in re.finditer(op_pattern, operations_block):
            op_id = match.group(1)
            block_start = match.start() + 1

            brace_count = 0
            block_end = None
            started = False
            for i, ch in enumerate(operations_block[block_start:], block_start):
                if ch == '{':
                    brace_count += 1
                    started = True
                elif ch == '}':
                    brace_count -= 1
                    if started and brace_count == 0:
                        block_end = i + 1
                        break
            if block_end is None:
                continue

            op_block = operations_block[block_start:block_end]

            entry = {
                'operation_id': op_id,
                'target_country_id': None,
                'spy_network_id': None,
                'type': None,
                'difficulty': None,
                'days_left': None,
                'info': None,
                'log_entries': 0,
                'last_log': None,
            }

            target_block = self._extract_braced_block(op_block, 'target') or ''
            if target_block:
                target_id = re.search(r'\bid=(\d+)', target_block)
                if target_id:
                    entry['target_country_id'] = int(target_id.group(1))

            spy_network = re.search(r'\bspy_network=(\d+)', op_block)
            if spy_network:
                entry['spy_network_id'] = int(spy_network.group(1))

            type_match = re.search(r'\btype="([^"]+)"', op_block)
            if type_match:
                entry['type'] = type_match.group(1)

            for key in ['difficulty', 'days_left', 'info']:
                m = re.search(rf'\b{key}=([-\d]+)', op_block)
                if m:
                    entry[key] = int(m.group(1))

            log_block = self._extract_braced_block(op_block, 'log') or ''
            if log_block:
                dates = re.findall(r'\bdate=\s*"(\d+\.\d+\.\d+)"', log_block)
                rolls = re.findall(r'\broll=([-\d]+)', log_block)
                skills = re.findall(r'\bskill=([-\d]+)', log_block)
                infos = re.findall(r'\binfo=([-\d]+)', log_block)
                diffs = re.findall(r'\bdifficulty=([-\d]+)', log_block)

                entry['log_entries'] = len(rolls) if rolls else max(len(dates), 0)
                if dates or rolls:
                    entry['last_log'] = {
                        'date': dates[-1] if dates else None,
                        'roll': int(rolls[-1]) if rolls else None,
                        'skill': int(skills[-1]) if skills else None,
                        'info': int(infos[-1]) if infos else None,
                        'difficulty': int(diffs[-1]) if diffs else None,
                    }

            operations_found.append(entry)
            if len(operations_found) >= limit:
                break

        result['operations'] = operations_found
        result['count'] = len(operations_found)
        return result

    def get_claims(self) -> dict:
        """Get territorial claims for the player empire.

        Returns:
            Dict with:
              - player_claims: List of systems the player has claimed
              - claims_against_player: List of claims other empires have on player systems
              - player_claims_count: Number of systems player has claimed
              - claims_against_count: Number of claims against player
        """
        result = {
            'player_claims': [],
            'claims_against_player': [],
            'player_claims_count': 0,
            'claims_against_count': 0,
        }

        player_id = self.get_player_empire_id()

        # Find galactic_object section
        go_start = self.gamestate.find('\ngalactic_object=')
        if go_start == -1:
            go_start = self.gamestate.find('galactic_object=')
        if go_start == -1:
            return result

        # Get a large chunk of the galactic_object section
        go_section = self.gamestate[go_start:go_start + 10000000]  # 10MB should cover most saves

        # Find all systems with claims
        # Each galactic object can have a claims={ } block with multiple claim entries
        # Format: claims={ { owner=X date="Y" claims=N } { owner=Z ... } }

        # First, find systems owned by player (to detect claims against us)
        player_systems = set()
        # Pattern: id=X ... owner=player_id (within same galactic_object block)
        system_pattern = r'\n\t(\d+)=\s*\{'

        player_claims = []
        claims_against = []

        for match in re.finditer(system_pattern, go_section):
            system_id = match.group(1)
            start_pos = match.end()

            # Find end of this galactic_object block
            brace_count = 1
            pos = start_pos
            max_pos = min(start_pos + 10000, len(go_section))
            while brace_count > 0 and pos < max_pos:
                if go_section[pos] == '{':
                    brace_count += 1
                elif go_section[pos] == '}':
                    brace_count -= 1
                pos += 1

            block = go_section[start_pos:pos]

            # Check if this system has claims
            claims_start = block.find('claims=')
            if claims_start == -1:
                continue

            # Extract claims block
            claims_section = block[claims_start:claims_start + 2000]
            brace_pos = claims_section.find('{')
            if brace_pos == -1:
                continue

            # Find end of claims block
            brace_count = 1
            cpos = brace_pos + 1
            while brace_count > 0 and cpos < len(claims_section):
                if claims_section[cpos] == '{':
                    brace_count += 1
                elif claims_section[cpos] == '}':
                    brace_count -= 1
                cpos += 1

            claims_block = claims_section[brace_pos:cpos]

            # Get system owner
            owner_match = re.search(r'\bstarbase_owner=(\d+)', block)
            system_owner = int(owner_match.group(1)) if owner_match else None

            # Get system name
            name_match = re.search(r'name=\s*\{[^}]*key="([^"]+)"', block)
            if not name_match:
                name_match = re.search(r'name="([^"]+)"', block)
            system_name = name_match.group(1) if name_match else f"System {system_id}"

            # Parse individual claims within this block
            # Each claim is: { owner=X date="Y" claims=N }
            claim_entries = re.findall(
                r'\{\s*owner=(\d+)\s*(?:date="([^"]+)")?\s*(?:claims=(\d+))?\s*\}',
                claims_block
            )

            for claim_owner, claim_date, claim_strength in claim_entries:
                claim_owner_id = int(claim_owner)
                strength = int(claim_strength) if claim_strength else 1

                claim_info = {
                    'system_id': system_id,
                    'system_name': system_name,
                    'claimant_id': claim_owner_id,
                    'date': claim_date if claim_date else None,
                    'strength': strength,
                }

                # Is this player claiming someone else's system?
                if claim_owner_id == player_id:
                    claim_info['current_owner'] = system_owner
                    player_claims.append(claim_info)
                # Is this someone claiming a player-owned system?
                elif system_owner == player_id:
                    claims_against.append(claim_info)

        # Sort by system name for readability
        player_claims.sort(key=lambda x: x.get('system_name', ''))
        claims_against.sort(key=lambda x: x.get('system_name', ''))

        # Return all claims - large empires in late-game can have 200+ claims
        result['player_claims'] = player_claims
        result['claims_against_player'] = claims_against
        result['player_claims_count'] = len(player_claims)
        result['claims_against_count'] = len(claims_against)

        return result
