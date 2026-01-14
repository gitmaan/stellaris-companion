from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

class DiplomacyMixin:
    """Domain methods extracted from the original SaveExtractor."""

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
            'federation': None
        }

        player_id = self.get_player_empire_id()

        # Find the country section and player's relations_manager
        country_match = re.search(r'^country=\s*\{', self.gamestate, re.MULTILINE)
        if not country_match:
            result['error'] = "Could not find country section"
            return result

        start = country_match.start()
        player_match = re.search(r'\n\t0=\s*\{', self.gamestate[start:start + 1000000])
        if not player_match:
            result['error'] = "Could not find player country"
            return result

        player_start = start + player_match.start()
        player_chunk = self.gamestate[player_start:player_start + 500000]

        # Find relations_manager section
        rel_match = re.search(r'relations_manager=\s*\{', player_chunk)
        if not rel_match:
            result['error'] = "Could not find relations_manager section"
            return result

        rel_start = rel_match.start()
        # Extract relations_manager block
        brace_count = 0
        rel_end = rel_start
        for i, char in enumerate(player_chunk[rel_start:rel_start + 100000], rel_start):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    rel_end = i + 1
                    break

        rel_block = player_chunk[rel_start:rel_end]

        # Parse individual relations
        # Pattern: relation={owner=<player_id> country=X ...}
        relation_pattern = r'relation=\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}'

        relations_found = []
        allies = []
        rivals = []

        for match in re.finditer(relation_pattern, rel_block):
            rel_content = match.group(1)

            # Only process relations where owner=player_id (not hardcoded 0)
            if not re.search(rf'owner={player_id}\b', rel_content):
                continue

            relation_info = {}

            # Extract country ID
            country_match = re.search(r'country=(\d+)', rel_content)
            if country_match:
                relation_info['country_id'] = int(country_match.group(1))

            # Extract trust
            trust_match = re.search(r'trust=(\d+)', rel_content)
            if trust_match:
                relation_info['trust'] = int(trust_match.group(1))

            # Extract relation score
            rel_current = re.search(r'relation_current=([-\d]+)', rel_content)
            if rel_current:
                relation_info['opinion'] = int(rel_current.group(1))

            # Check for treaties/agreements
            if 'alliance=yes' in rel_content:
                relation_info['alliance'] = True
                allies.append(relation_info.get('country_id'))
            if 'research_agreement=yes' in rel_content:
                relation_info['research_agreement'] = True
            if 'embassy=yes' in rel_content:
                relation_info['embassy'] = True
            if 'truce=' in rel_content and 'truce' not in rel_content.split('=')[0]:
                relation_info['has_truce'] = True

            # Check for communications
            if 'communications=yes' in rel_content:
                relation_info['has_contact'] = True

            relations_found.append(relation_info)

        result['relations'] = relations_found[:30]  # Limit to 30
        result['allies'] = allies
        result['relation_count'] = len(relations_found)

        # Check for federation membership
        fed_match = re.search(r'federation=(\d+)', player_chunk[:5000])
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

