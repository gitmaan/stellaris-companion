from __future__ import annotations

import re


class PoliticsMixin:
    """Internal politics extractors (factions, elections, agendas, etc.)."""

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

    def get_factions(self, limit: int = 10) -> dict:
        """Get a compact summary of the player's political factions.

        Notes:
        - Returns an empty list for gestalt empires.
        - Does not return raw pop IDs (members are summarized as a count).
        """
        identity = self.get_empire_identity()
        is_gestalt = bool(identity.get("is_gestalt", False))

        result = {
            "is_gestalt": is_gestalt,
            "factions": [],
            "count": 0,
        }

        if is_gestalt:
            return result

        player_id = self.get_player_empire_id()
        factions_section = self._extract_section("pop_factions")
        if not factions_section:
            return result

        factions: list[dict] = []

        for match in re.finditer(r'\n\t(-?\d+)\s*=\s*\{', factions_section):
            faction_id = match.group(1)
            start = match.start()

            brace_count = 0
            end = None
            for i, char in enumerate(factions_section[start:], start):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break
            if end is None:
                continue

            block = factions_section[start:end]

            country_match = re.search(r'\bcountry=(\d+)', block)
            if not country_match or int(country_match.group(1)) != player_id:
                continue

            faction_type_match = re.search(r'\btype="([^"]+)"', block)
            support_percent_match = re.search(r'\bsupport_percent=([\d.]+)', block)
            support_power_match = re.search(r'\bsupport_power=([\d.]+)', block)
            approval_match = re.search(r'\bfaction_approval=([\d.]+)', block)

            name = "Unknown"
            name_block = self._extract_braced_block(block, "name")
            if name_block:
                name_key = re.search(r'\bkey="([^"]+)"', name_block)
                if name_key:
                    name = name_key.group(1)

            members_count = 0
            members_block = self._extract_braced_block(block, "members")
            if members_block:
                open_brace = members_block.find('{')
                close_brace = members_block.rfind('}')
                if open_brace != -1 and close_brace != -1 and close_brace > open_brace:
                    inner = members_block[open_brace + 1 : close_brace]
                    members_count = len(re.findall(r'\d+', inner))

            factions.append(
                {
                    "id": str(faction_id),
                    "country_id": player_id,
                    "type": faction_type_match.group(1) if faction_type_match else "unknown",
                    "name": name,
                    "support_percent": float(support_percent_match.group(1)) if support_percent_match else 0.0,
                    "support_power": float(support_power_match.group(1)) if support_power_match else 0.0,
                    "approval": float(approval_match.group(1)) if approval_match else 0.0,
                    "members_count": members_count,
                }
            )

        factions.sort(key=lambda f: f.get("support_percent", 0.0), reverse=True)

        result["count"] = len(factions)
        result["factions"] = factions[: max(0, min(int(limit), 25))]
        return result

