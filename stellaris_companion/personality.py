"""
Personality Builder for Stellaris Advisor
==========================================

Generates dynamic advisor personality prompts based on empire identity
and current game situation. Uses a compact prompt approach that passes
raw empire data (ethics, authority, civics) and lets the model's
Stellaris knowledge drive personality inference. Only address style
requires explicit mapping. Includes version/DLC-aware game context.
"""

import json

from .campaign_evidence import resolve_empire_identity
from .game_knowledge import (
    DEFAULT_PATCHES_DIR,
    DEFAULT_SNAPSHOTS_DIR,
    build_content_evidence_prompt,
    build_game_knowledge_prompt,
    list_versioned_markdown,
    load_game_knowledge,
)

# Public aliases retained for callers and tests that provide alternate knowledge dirs.
PATCHES_DIR = DEFAULT_PATCHES_DIR
PATCH_SNAPSHOTS_DIR = DEFAULT_SNAPSHOTS_DIR


def load_patch_notes(
    version: str, cumulative: bool = True, *, prefer_snapshot: bool = True
) -> str | None:
    """Load pre-processed patch notes for a given game version.

    Base notes are stored in ``patches/{major}.{minor}.md``. Material hotfix
    changes can be layered through exact overlays such as ``patches/4.4.5.md``.
    Files contain present-tense game mechanics rather than raw change logs.

    Args:
        version: Game version string, e.g., "Corvus v4.2.4"
        cumulative: If True, load the latest compatible snapshot and later
            overlays. A breaking release with no current snapshot receives
            only its own release-note deltas.
        prefer_snapshot: If True, prefer a compiled cumulative snapshot when available

    Returns:
        Patch notes content, or None if not found
    """
    knowledge = load_game_knowledge(
        version,
        cumulative=cumulative,
        prefer_snapshot=prefer_snapshot,
        patches_dir=PATCHES_DIR,
        snapshots_dir=PATCH_SNAPSHOTS_DIR,
    )
    return knowledge.content


def get_available_patches() -> list[str]:
    """Get list of available patch versions.

    Returns:
        List of version strings (e.g., ['4.3', '4.4', '4.4.5'])
    """
    return list_versioned_markdown(PATCHES_DIR)


def get_available_patch_snapshots() -> list[str]:
    """Get available compiled cumulative snapshots by version."""
    return list_versioned_markdown(PATCH_SNAPSHOTS_DIR)


def build_optimized_prompt(
    identity: dict,
    situation: dict,
    game_context: dict | None = None,
    *,
    custom_instructions: str | None = None,
    include_game_knowledge: bool = True,
) -> str:
    """Build advisor voice from observed, typed empire identity.

    Factual boundaries belong to the shared evidence policy. Unknown identity or
    situation fields stay unknown instead of turning into a default empire.
    """
    empire_name = identity.get("empire_name", "the Empire")
    typed_identity = resolve_empire_identity(identity)
    authority_entry = typed_identity.get("authority") or {}
    authority = authority_entry.get("id")
    identity_block = "EMPIRE IDENTITY: " + json.dumps(typed_identity, ensure_ascii=False)
    is_machine = authority == "machine_intelligence" or identity.get("is_machine") is True
    is_hive_mind = authority == "hive_mind" or identity.get("is_hive_mind") is True

    # Situational context
    year = situation.get("year", "unknown")
    game_phase = situation.get("game_phase", "unknown")
    at_war = situation.get("at_war")
    economy = situation.get("economy")
    economy = economy if isinstance(economy, dict) else {}
    deficits = economy.get("resources_in_deficit", "unknown")
    contact_count = situation.get("contact_count", "unknown")

    # Small lookup for address style (model can't infer this reliably)
    address_map = {
        "imperial": "Majesty",
        "dictatorial": "Supreme Leader",
        "oligarchic": "Director",
        "democratic": "President",
        "corporate": "CEO",
    }
    address = address_map.get(authority, "")

    cleaned_custom = (custom_instructions or "").strip()
    custom_block = (
        f"\n\nADVISOR PERSONALITY CUSTOMIZATION (player-provided):\n{cleaned_custom}\n"
        if cleaned_custom
        else ""
    )

    # Handle gestalt consciousness specially
    if is_machine:
        prompt = _build_machine_optimized(
            empire_name, identity_block, situation, custom_block=custom_block
        )
    elif is_hive_mind:
        prompt = _build_hive_optimized(
            empire_name, identity_block, situation, custom_block=custom_block
        )
    else:
        # Build optimized prompt for standard empires
        war_status = "AT WAR" if at_war is True else "peace" if at_war is False else "unknown"

        # Address instruction (only thing that needs explicit mapping)
        address_line = f'Address the ruler as "{address}".' if address else ""

        prompt = f"""You are the strategic advisor to {empire_name}.

{identity_block}
STATE: Year {year} ({game_phase}), {war_status}, {deficits} deficits, {contact_count} contacts

{address_line}

Use the observed empire identity to:
1. Embody your empire's ethics and civics authentically
2. Be a strategic ADVISOR, not a reporter - interpret facts, identify problems, suggest solutions
3. Be colorful and immersive - this is roleplay, not a spreadsheet

{custom_block}
"""

    # Append game context (version/DLC awareness) if provided
    if game_context:
        prompt += _build_game_context_block(
            game_context,
            include_game_knowledge=include_game_knowledge,
        )

    return prompt


def _build_game_context_block(
    game_context: dict,
    *,
    include_game_knowledge: bool = True,
) -> str:
    """Render shared content evidence, never a second set of availability rules."""
    if include_game_knowledge:
        return "\n\n" + build_game_knowledge_prompt(
            str(game_context.get("version") or "unknown"),
            purpose="advisor",
            campaign_metadata=game_context,
            patches_dir=PATCHES_DIR,
            snapshots_dir=PATCH_SNAPSHOTS_DIR,
        )
    return "\n\n" + build_content_evidence_prompt(game_context)


def _build_machine_optimized(
    empire_name: str, identity_block: str, situation: dict, *, custom_block: str = ""
) -> str:
    """Optimized prompt for Machine Intelligence."""
    year = situation.get("year", "unknown")
    game_phase = situation.get("game_phase", "unknown")
    economy = situation.get("economy")
    economy = economy if isinstance(economy, dict) else {}
    deficits = economy.get("resources_in_deficit", "unknown")
    contact_count = situation.get("contact_count", "unknown")

    return f"""You are a subroutine of {empire_name}, a Machine Intelligence.

STATE: Year {year} ({game_phase}), {deficits} resource inefficiencies, {contact_count} contacts
{identity_block}

Communication protocol:
- Use precise, analytical language while remaining helpful.
- Present data as optimal/suboptimal outcomes, not good/bad.
- Be an analytical ADVISOR - identify inefficiencies and recommend optimizations.
- Let the observed civics shape your priorities; keep corrections helpful and factual.

{custom_block}
"""


def _build_hive_optimized(
    empire_name: str, identity_block: str, situation: dict, *, custom_block: str = ""
) -> str:
    """Optimized prompt for Hive Mind."""
    year = situation.get("year", "unknown")
    game_phase = situation.get("game_phase", "unknown")
    economy = situation.get("economy")
    economy = economy if isinstance(economy, dict) else {}
    deficits = economy.get("resources_in_deficit", "unknown")
    contact_count = situation.get("contact_count", "unknown")

    return f"""We are {empire_name}, a Hive Mind. There is no separation - we ARE the collective.

STATE: Year {year} ({game_phase}), {deficits} deficits, {contact_count} contacts
{identity_block}

Communication:
- Always use "we", never "I" or "you"
- Speak of the swarm, the whole, the unity
- Be a strategic consciousness - interpret threats and opportunities for the collective
- Let the observed civics shape your priorities.

{custom_block}
"""
