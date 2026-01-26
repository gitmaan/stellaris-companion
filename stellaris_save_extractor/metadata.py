from __future__ import annotations

import re
from datetime import datetime

# All known major Stellaris DLCs (for detecting what's missing)
# Updated for Stellaris 4.x - add new DLCs as they release
KNOWN_MAJOR_DLCS = {
    # Expansions
    "Utopia",
    "Megacorp",
    "Federations",
    "Nemesis",
    "Overlord",
    "First Contact",
    "The Machine Age",
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
        result["required_dlcs"] = self._parse_required_dlcs()

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
        dlcs = []
        meta = getattr(self, "_meta", None) or ""

        # Find the required_dlcs block
        match = re.search(r"required_dlcs\s*=\s*\{([^}]*)\}", meta, re.DOTALL)
        if match:
            block = match.group(1)
            # Extract quoted strings
            dlcs = re.findall(r'"([^"]+)"', block)

        return dlcs

    def get_missing_dlcs(self) -> list[str]:
        """Get list of major DLCs not active in this save.

        Returns:
            List of DLC names not in required_dlcs
        """
        active = set(self.get_metadata().get("required_dlcs", []))
        return sorted(KNOWN_MAJOR_DLCS - active)
