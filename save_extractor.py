"""
Compatibility shim for Stellaris save extraction.

The implementation of `SaveExtractor` lives in `stellaris_save_extractor/`.
This module preserves the original import path:

    from save_extractor import SaveExtractor

SaveExtractor provides these attributes:
    - save_path: Path to the .sav file
    - gamestate_path: Alias for save_path (for Rust bridge integration)
    - gamestate: Raw gamestate text (loaded lazily)
    - meta: Raw meta text (loaded on init)
"""

from __future__ import annotations

from stellaris_save_extractor import SaveExtractor

# Re-export rust_bridge for direct access (used by extractors)
try:
    from rust_bridge import ParserError, extract_sections, iter_section_entries
except ImportError:
    # Rust bridge not available - extractors will use regex fallback
    ParserError = None
    extract_sections = None
    iter_section_entries = None

__all__ = [
    "SaveExtractor",
    "get_player_status",
    "get_empire",
    "get_wars",
    "get_fleets",
    "get_leaders",
    "get_technology",
    "get_resources",
    "get_diplomacy",
    "get_planets",
    "get_starbases",
    "get_pop_statistics",
]


def get_player_status(extractor: SaveExtractor) -> dict:
    """Get the player's current status (core metrics)."""
    return extractor.get_player_status()


def get_empire(extractor: SaveExtractor, name: str) -> dict:
    """Get detailed information about a specific empire by name."""
    return extractor.get_empire(name)


def get_wars(extractor: SaveExtractor) -> dict:
    """Get information about all active wars."""
    return extractor.get_wars()


def get_fleets(extractor: SaveExtractor) -> dict:
    """Get information about the player's fleets."""
    return extractor.get_fleets()


def get_leaders(extractor: SaveExtractor) -> dict:
    """Get information about the player's leaders."""
    return extractor.get_leaders()


def get_technology(extractor: SaveExtractor) -> dict:
    """Get technology and research information."""
    return extractor.get_technology()


def get_resources(extractor: SaveExtractor) -> dict:
    """Get resource stockpiles and monthly net values."""
    return extractor.get_resources()


def get_diplomacy(extractor: SaveExtractor) -> dict:
    """Get diplomacy/relations/treaties information."""
    return extractor.get_diplomacy()


def get_planets(extractor: SaveExtractor) -> dict:
    """Get the player's colonized planets."""
    return extractor.get_planets()


def get_starbases(extractor: SaveExtractor) -> dict:
    """Get the player's starbase information."""
    return extractor.get_starbases()


def get_pop_statistics(extractor: SaveExtractor) -> dict:
    """Get detailed population statistics for the player's empire."""
    return extractor.get_pop_statistics()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python save_extractor.py <save_file.sav>")
        sys.exit(1)

    extractor = SaveExtractor(sys.argv[1])

    print("=== Metadata ===")
    print(extractor.get_metadata())

    print("\n=== Player Status ===")
    print(extractor.get_player_status())

    print("\n=== Summary ===")
    print(extractor.get_summary())

