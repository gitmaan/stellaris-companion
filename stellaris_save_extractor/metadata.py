from __future__ import annotations

import re
from datetime import datetime

from stellaris_companion.campaign_evidence import resolve_content_availability

# All known major Stellaris DLCs (for detecting what's missing)
# Updated for Stellaris 4.x - add new DLCs as they release
KNOWN_MAJOR_DLCS = {
    # Expansions
    "Utopia",
    "Apocalypse",
    "Megacorp",
    "Federations",
    "Nemesis",
    "Overlord",
    "First Contact",
    "The Machine Age",
    "Nomads",
    # Story Packs
    "Leviathans",
    "Synthetic Dawn",
    "Distant Stars",
    "Ancient Relics",
    "Aquatics",
    "Toxoids",
    "Astral Planes",
    # Species Packs (less critical for mechanics)
    "Plantoids",
    "Humanoids",
    "Lithoids",
    "Necroids",
    # Free DLCs / Events
    "Horizon Signal",
    "Anniversary Portraits",
    # Paragons
    "Galactic Paragons",
    # Cosmic Storms
    "Cosmic Storms",
    # Grand Archive
    "Grand Archive",
}


class MetadataMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def get_metadata(self) -> dict:
        """Get basic save metadata.

        Returns:
            Dict with empire name, date, version, required_dlcs, etc.
        """
        result = {
            "file_path": str(self.save_path),
            "file_size_mb": self.save_path.stat().st_size / (1024 * 1024),
            "modified": datetime.fromtimestamp(self.save_path.stat().st_mtime).isoformat(),
            "gamestate_loaded": getattr(self, "_gamestate", None) is not None,
        }
        if getattr(self, "_gamestate", None) is not None:
            result["gamestate_chars"] = len(self.gamestate)

        # Parse meta file for simple key=value pairs
        for line in self.meta.split("\n"):
            if "=" in line and "flag" not in line.lower():
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"')
                if key in ["version", "name", "date"]:
                    result[key] = value

        # Parse required_dlcs block
        result["required_dlcs"], result["required_dlcs_status"] = (
            self._parse_required_dlcs_evidence()
        )

        return result

    def _parse_required_dlcs(self) -> list[str]:
        """Extract required_dlcs list from meta file.

        Parses blocks like:
            required_dlcs={
                "Federations"
                "Utopia"
            }

        Returns:
            List of DLC names (strings)
        """
        return self._parse_required_dlcs_evidence()[0]

    def _parse_required_dlcs_evidence(self) -> tuple[list[str], str]:
        """Distinguish a reported empty list from missing or malformed metadata."""
        meta = getattr(self, "_meta", None) or ""
        # Ignore comments without stripping a # inside a quoted name.
        meta = re.sub(r'("(?:\\.|[^"\\])*")|#[^\n]*', lambda m: m.group(1) or "", meta)
        if not re.search(r"\brequired_dlcs\s*=", meta):
            return [], "not_recorded"

        match = re.search(r"\brequired_dlcs\s*=\s*\{([^{}]*)\}", meta, re.DOTALL)
        if not match:
            return [], "invalid"
        block = match.group(1)
        dlcs = re.findall(r'"([^"\n]+)"', block)
        residue = re.sub(r'"([^"\n]+)"', "", block)
        if residue.strip() or any(not name.strip() for name in dlcs):
            return [], "invalid"
        return dlcs, "reported"

    def get_missing_dlcs(self) -> list[str]:
        """Return known standalone packs not reported by this save (legacy API).

        Absence from the save's requirement list is not proof that a feature is
        unavailable. Unknown/malformed evidence yields no negative inference.
        """
        content = resolve_content_availability(self.get_metadata())
        if content["dlc_evidence_status"] != "reported":
            return []
        indicated = set(content["reported_dlcs"]) | set(content["base_game_dlcs"])
        return sorted(KNOWN_MAJOR_DLCS - indicated)
