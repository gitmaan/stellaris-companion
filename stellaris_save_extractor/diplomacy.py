from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

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
        allies: list[int] = []
        rivals: list[int] = []
        defensive_pacts: list[int] = []
        non_aggression_pacts: list[int] = []
        closed_borders: list[int] = []
        migration_treaties: list[int] = []
        commercial_pacts: list[int] = []
        sensor_links: list[int] = []
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

            # Only process relations where owner=player_id (not hardcoded 0)
            if not re.search(rf'\bowner={player_id}\b', rel_text):
                continue

            relation_info = {}

            # Extract country ID
            country_match = re.search(r'\bcountry=(\d+)', rel_text)
            if country_match:
                relation_info['country_id'] = int(country_match.group(1))
            country_id = relation_info.get('country_id')
            if country_id is None:
                continue

            # Extract trust
            trust_match = re.search(r'\btrust=(\d+)', rel_text)
            if trust_match:
                relation_info['trust'] = int(trust_match.group(1))

            # Extract relation score
            rel_current = re.search(r'\brelation_current=([-\d]+)', rel_text)
            if rel_current:
                relation_info['opinion'] = int(rel_current.group(1))

            # Check for treaties/agreements (some vary by game version)
            if 'alliance=yes' in rel_text or 'defensive_pact=yes' in rel_text:
                relation_info['defensive_pact'] = True
                defensive_pacts.append(country_id)
                allies.append(country_id)  # Backwards-compatible "allies"
                treaties.append({'country_id': country_id, 'type': 'defensive_pact'})
            if 'non_aggression_pact=yes' in rel_text:
                relation_info['non_aggression_pact'] = True
                non_aggression_pacts.append(country_id)
                treaties.append({'country_id': country_id, 'type': 'non_aggression_pact'})
            if 'commercial_pact=yes' in rel_text:
                relation_info['commercial_pact'] = True
                commercial_pacts.append(country_id)
                treaties.append({'country_id': country_id, 'type': 'commercial_pact'})
            if 'migration_treaty=yes' in rel_text or 'migration_pact=yes' in rel_text:
                relation_info['migration_treaty'] = True
                migration_treaties.append(country_id)
                treaties.append({'country_id': country_id, 'type': 'migration_treaty'})
            if 'sensor_link=yes' in rel_text:
                relation_info['sensor_link'] = True
                sensor_links.append(country_id)
                treaties.append({'country_id': country_id, 'type': 'sensor_link'})
            if 'closed_borders=yes' in rel_text:
                relation_info['closed_borders'] = True
                closed_borders.append(country_id)
                treaties.append({'country_id': country_id, 'type': 'closed_borders'})
            if 'rival=yes' in rel_text or 'rivalry=yes' in rel_text:
                relation_info['rival'] = True
                rivals.append(country_id)
                treaties.append({'country_id': country_id, 'type': 'rival'})

            if 'research_agreement=yes' in rel_text:
                relation_info['research_agreement'] = True
                treaties.append({'country_id': country_id, 'type': 'research_agreement'})
            if 'embassy=yes' in rel_text:
                relation_info['embassy'] = True
            if 'truce=' in rel_text and 'truce' not in rel_text.split('=')[0]:
                relation_info['has_truce'] = True

            # Check for communications
            if 'communications=yes' in rel_text:
                relation_info['has_contact'] = True

            relations_found.append(relation_info)

        result['relations'] = relations_found[:30]  # Limit to 30
        result['allies'] = allies[:50]
        result['rivals'] = rivals[:50]
        result['defensive_pacts'] = defensive_pacts[:50]
        result['non_aggression_pacts'] = non_aggression_pacts[:50]
        result['closed_borders'] = closed_borders[:50]
        result['migration_treaties'] = migration_treaties[:50]
        result['commercial_pacts'] = commercial_pacts[:50]
        result['sensor_links'] = sensor_links[:50]
        result['treaties'] = treaties[:100]
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
                'status': status,  # 'dormant' or 'awakened'
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
