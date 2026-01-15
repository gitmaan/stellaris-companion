from __future__ import annotations

import re


class ArmiesMixin:
    """Army-related extraction methods."""

    def get_armies(self) -> dict:
        """Get all armies owned by the player empire.

        Parses the top-level `army={}` section and filters to player-owned armies.
        Armies can be stationed on planets (defense) or on transport ships (assault).

        Returns:
            Dict with:
              - armies: List of army dicts with type, health, max_health, morale,
                        location (planet_id or ship_id), leader_id
              - count: Total number of player armies
              - by_type: Dict mapping army type to count
              - total_strength: Sum of max_health for combat power estimate
        """
        result = {
            'armies': [],
            'count': 0,
            'by_type': {},
            'total_strength': 0.0,
        }

        player_id = self.get_player_empire_id()

        # Find the army section
        army_start = self.gamestate.find('\narmy=')
        if army_start == -1:
            army_start = self.gamestate.find('army=')
        if army_start == -1:
            return result

        # Get a chunk for the army section
        army_section = self.gamestate[army_start:army_start + 5000000]

        # Find the opening brace of the army section
        brace_pos = army_section.find('{')
        if brace_pos == -1:
            return result

        # Parse individual army entries: \n\t{id}=\s*{
        entry_pattern = r'\n\t(\d+)=\s*\{'
        entries = list(re.finditer(entry_pattern, army_section))

        armies_list = []
        by_type: dict[str, int] = {}
        total_strength = 0.0

        for i, match in enumerate(entries):
            army_id = match.group(1)
            start_pos = match.end()

            # Find end of this army block using brace matching
            brace_count = 1
            pos = start_pos
            max_pos = min(start_pos + 3000, len(army_section))
            while brace_count > 0 and pos < max_pos:
                if army_section[pos] == '{':
                    brace_count += 1
                elif army_section[pos] == '}':
                    brace_count -= 1
                pos += 1

            block = army_section[start_pos:pos]

            # Check owner - only include player's armies
            owner_match = re.search(r'\n\s*owner=(\d+)', block)
            if not owner_match:
                continue
            owner = int(owner_match.group(1))
            if owner != player_id:
                continue

            # Extract army type
            type_match = re.search(r'\n\s*type="([^"]+)"', block)
            army_type = type_match.group(1) if type_match else 'unknown'

            # Extract health values
            health_match = re.search(r'\n\s*health=([\d.]+)', block)
            max_health_match = re.search(r'\n\s*max_health=([\d.]+)', block)
            health = float(health_match.group(1)) if health_match else 0.0
            max_health = float(max_health_match.group(1)) if max_health_match else 0.0

            # Extract morale
            morale_match = re.search(r'\n\s*morale=([\d.]+)', block)
            morale = float(morale_match.group(1)) if morale_match else None

            # Determine location - planet or ship
            planet_match = re.search(r'\n\s*planet=(\d+)', block)
            ship_match = re.search(r'\n\s*ship=(\d+)', block)

            location_type = None
            location_id = None
            if planet_match and planet_match.group(1) != '4294967295':
                location_type = 'planet'
                location_id = planet_match.group(1)
            elif ship_match and ship_match.group(1) != '4294967295':
                location_type = 'ship'
                location_id = ship_match.group(1)

            # Extract leader if present
            leader_match = re.search(r'\n\s*leader=(\d+)', block)
            leader_id = leader_match.group(1) if leader_match else None

            # Extract experience
            exp_match = re.search(r'\n\s*experience=([\d.]+)', block)
            experience = float(exp_match.group(1)) if exp_match else 0.0

            # Extract species if present
            species_match = re.search(r'\n\s*species=(\d+)', block)
            species_id = species_match.group(1) if species_match else None

            # Build army info
            army_info = {
                'id': army_id,
                'type': army_type,
                'health': round(health, 1),
                'max_health': round(max_health, 1),
            }

            if morale is not None:
                army_info['morale'] = round(morale, 1)

            if location_type:
                army_info['location_type'] = location_type
                army_info['location_id'] = location_id

            if leader_id and leader_id != '4294967295':
                army_info['leader_id'] = leader_id

            if experience > 0:
                army_info['experience'] = round(experience, 1)

            if species_id and species_id != '4294967295':
                army_info['species_id'] = species_id

            armies_list.append(army_info)

            # Track by type
            by_type[army_type] = by_type.get(army_type, 0) + 1

            # Sum strength
            total_strength += max_health

        result['armies'] = armies_list
        result['count'] = len(armies_list)
        result['by_type'] = by_type
        result['total_strength'] = round(total_strength, 1)

        return result
