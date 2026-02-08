"""
Personality Builder for Stellaris Advisor
==========================================

Generates dynamic advisor personality prompts based on empire identity
and current game situation. Uses a compact prompt approach that passes
raw empire data (ethics, authority, civics) and lets the model's
Stellaris knowledge drive personality inference. Only address style
requires explicit mapping. Includes version/DLC-aware game context.
"""

import re
from pathlib import Path

from .paths import get_repo_root

# Directory containing patch notes (dev repo root, with a package-local fallback)
_repo_root = get_repo_root(Path(__file__))
_patches_repo = _repo_root / "patches"
PATCHES_DIR = (
    _patches_repo if _patches_repo.exists() else Path(__file__).resolve().parent / "patches"
)


def load_patch_notes(version: str, cumulative: bool = True) -> str | None:
    """Load pre-processed patch notes for a given game version.

    Patch notes are stored in patches/{major}.{minor}.md files,
    pre-transformed by LLM to contain present-tense facts about
    game mechanics (no change-oriented language).

    Args:
        version: Game version string, e.g., "Corvus v4.2.4"
        cumulative: If True, load all patches from 4.0 up to this version

    Returns:
        Patch notes content, or None if not found
    """
    if not version:
        return None

    # Extract major.minor from version string (e.g., "Corvus v4.2.4" -> "4.2")
    match = re.search(r"(\d+\.\d+)", version)
    if not match:
        return None

    target_version = match.group(1)

    def _load_single_patch(ver: str) -> str | None:
        """Load a single patch file."""
        patch_file = PATCHES_DIR / f"{ver}.md"
        if patch_file.exists():
            try:
                content = patch_file.read_text(encoding="utf-8")
                lines = content.split("\n")
                content_lines = [
                    line
                    for line in lines
                    if not line.startswith("#") and not line.startswith("<!--")
                ]
                return "\n".join(content_lines).strip()
            except Exception:
                return None
        return None

    if not cumulative:
        return _load_single_patch(target_version)

    # Load all patches from 4.0 up to target version (cumulative)
    all_patches = get_available_patches()
    combined = []

    for patch_ver in sorted(all_patches):
        # Compare versions numerically
        try:
            if float(patch_ver) <= float(target_version):
                content = _load_single_patch(patch_ver)
                if content:
                    combined.append(content)
        except ValueError:
            continue

    return "\n\n".join(combined) if combined else None


def get_available_patches() -> list[str]:
    """Get list of available patch versions.

    Returns:
        List of version strings (e.g., ['4.0', '4.1', '4.2'])
    """
    if not PATCHES_DIR.exists():
        return []

    patches = []
    for f in PATCHES_DIR.glob("*.md"):
        version = f.stem  # e.g., "4.0"
        patches.append(version)

    return sorted(patches)


# ---- DLC feature mapping (inline negative enumeration) ----
# Compact feature lists for missing DLCs, injected into the system prompt.
# Only gameplay mechanics are listed — not cosmetics, portraits, or music.
# Used to tell the model which features do NOT exist in this player's game.

_DLC_KEY_FEATURES: dict[str, str] = {
    # Expansions
    "Utopia": (
        "Megastructures (Dyson Sphere, Science Nexus, Sentry Array, Ring World), "
        "Habitats, Ascension Paths (Psionic/Biological/Synthetic), "
        "Hive Mind authority, The Shroud, Psi Jump Drive"
    ),
    "Apocalypse": (
        "Titans, Colossus (World Cracker, Neutron Sweep, God Ray, Global Pacifier), "
        "Marauders, Great Khan mid-game crisis, Ion Cannons, "
        "Colossus Project ascension perk"
    ),
    "Megacorp": (
        "Megacorporation authority, Branch Offices, Ecumenopolis, "
        "Matter Decompressor, Strategic Coordination Center, "
        "Mega Art Installation, Interstellar Assembly, "
        "Caravaneers, Galactic Slave Market"
    ),
    "Federations": (
        "Federation types and levels, Galactic Council, "
        "Juggernaut, Mega Shipyard, "
        "Origins (Void Dwellers, Shattered Ring, Common Ground, Hegemon)"
    ),
    "Nemesis": (
        "Become the Crisis (Aetherophasic Engine, Star Eater), "
        "Galactic Custodian, Galactic Imperium, "
        "Espionage operations (Sabotage, Steal Tech, Spark Rebellion, "
        "Smear Campaign, Arm Privateers), Menace"
    ),
    "Overlord": (
        "Specialist vassals (Scholarium, Bulwark, Prospectorium), "
        "Hyper Relays, Orbital Rings, Quantum Catapult, Holdings, "
        "Mercenary Enclaves, Shroudwalker Enclave"
    ),
    "First Contact": (
        "Fleet cloaking, Pre-FTL awareness system, "
        "Origins (Broken Shackles, Payback, Fear of the Dark)"
    ),
    "The Machine Age": (
        "Machine ascension paths (Modularity, Nanotech, Virtuality), "
        "Synthetic Queen/Cetana, Cosmogenesis, "
        "Dyson Swarm, Arc Furnace, "
        "Origins (Cybernetic Creed, Synthetic Fertility)"
    ),
    # Story Packs
    "Leviathans": (
        "Guardians (Ether Drake, Enigmatic Fortress, Dimensional Horror, "
        "Automated Dreadnought, Stellarite Devourer, Infinity Machine), "
        "Enclaves (Artisan Troupe, Curator Order, Trader Enclaves), "
        "War in Heaven"
    ),
    "Synthetic Dawn": (
        "Machine Intelligence authority, Determined Exterminator, "
        "Driven Assimilator, Rogue Servitor, "
        "machine-specific traits and traditions"
    ),
    "Distant Stars": (
        "L-Gates, L-Cluster, Gray Tempest, Dessanu Consonance, unique anomalies and leviathans"
    ),
    "Ancient Relics": (
        "Archaeological excavation sites, Relics, "
        "Minor Artifacts resource, Relic Worlds, "
        "Precursors (Baol, Zroni)"
    ),
    "Astral Planes": (
        "Astral Rifts, Astral Threads, Astral Actions, Astral Relics, Riftworld origin"
    ),
    # Paragons / Storms / Archive
    "Galactic Paragons": (
        "Council mechanics, leader trait choices, "
        "Paragons (Renowned/Legendary leaders), "
        "Veteran Classes, Destiny traits"
    ),
    "Cosmic Storms": (
        "Cosmic storm types, Storm Chaser origin, "
        "Galactic Weather Control ascension perk, "
        "storm buildings and technologies"
    ),
    "Grand Archive": (
        "Grand Archive megastructure, Vivarium, "
        "Voidworm Plague mid-game crisis, "
        "Archivism and Domestication traditions"
    ),
    # Species Packs (only gameplay mechanics, not cosmetics)
    "Aquatics": (
        "Aquatic trait, Ocean Paradise origin, "
        "Here Be Dragons origin, Anglers civic, "
        "Hydrocentric ascension perk"
    ),
    "Toxoids": (
        "Knights of the Toxic God origin, Overtuned origin, "
        "Noxious trait, Detox ascension perk, "
        "Relentless Industrialists civic"
    ),
    "Lithoids": (
        "Lithoid trait (minerals instead of food), Calamitous Birth origin, Terravore civic"
    ),
    "Necroids": (
        "Necrophage origin, Death Cult civic, Reanimated Armies civic, Memorialists civic"
    ),
    "Plantoids": (
        "Budding trait, Catalytic Processing civic, Idyllic Bloom civic, Radiotrophic trait"
    ),
    "Humanoids": ("Clone Army origin, Masterful Crafters civic, Pleasure Seekers civic"),
}


def build_optimized_prompt(
    identity: dict,
    situation: dict,
    game_context: dict | None = None,
    *,
    custom_instructions: str | None = None,
) -> str:
    """Generate the optimal production prompt based on empirical testing.

    Key findings from the Final Showdown test (2026-01-13):

    1. Model CANNOT reliably infer address style from authority
       - "democratic" → "President" only works 0-2/5 times without explicit instruction
       - Solution: Small lookup for address style (only ~30 chars)

    2. Model CAN infer personality from ethics/civics names
       - Just passing "fanatic_egalitarian" triggers liberty/freedom themes
       - No hardcoded personality text needed!

    3. "Be an ADVISOR, not a reporter" is the KEY differentiator
       - Without it: 2-3/5 proactive warnings
       - With it: 5/5 proactive warnings

    4. "You know Stellaris deeply" works as a meta-instruction
       - 88% of full personality quality at 41% of prompt size

    Target: ~750 chars achieving 6.0+/7 personality score.

    Args:
        identity: Empire identity from get_empire_identity()
        situation: Game situation from get_situation()
        game_context: Optional dict with 'version' and 'required_dlcs' for DLC/version awareness

    Returns:
        Optimized system prompt (~750 chars + game context)
    """
    empire_name = identity.get("empire_name", "the Empire")
    ethics = identity.get("ethics", [])
    authority = identity.get("authority", "democratic")
    civics = identity.get("civics", [])
    is_machine = identity.get("is_machine", False)
    is_hive_mind = identity.get("is_hive_mind", False)

    # Situational context
    year = situation.get("year", 2200)
    game_phase = situation.get("game_phase", "early")
    at_war = situation.get("at_war", False)
    economy = situation.get("economy", {})
    deficits = economy.get("resources_in_deficit", 0)
    contact_count = situation.get("contact_count", 0)

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
        prompt = _build_machine_optimized(empire_name, civics, situation, custom_block=custom_block)
    elif is_hive_mind:
        prompt = _build_hive_optimized(empire_name, civics, situation, custom_block=custom_block)
    else:
        # Build optimized prompt for standard empires
        ethics_str = ", ".join(ethics) if ethics else "unknown"
        civics_str = ", ".join(civics) if civics else "none"
        war_status = "AT WAR" if at_war else "peace"

        # Address instruction (only thing that needs explicit mapping)
        address_line = f'Address the ruler as "{address}".' if address else ""

        prompt = f"""You are the strategic advisor to {empire_name}.

EMPIRE: Ethics: {ethics_str} | Authority: {authority} | Civics: {civics_str}
STATE: Year {year} ({game_phase}), {war_status}, {deficits} deficits, {contact_count} contacts

{address_line}

You know Stellaris deeply. Use that knowledge to:
1. Embody your empire's ethics and civics authentically
2. Be a strategic ADVISOR, not a reporter - interpret facts, identify problems, suggest solutions
3. Be colorful and immersive - this is roleplay, not a spreadsheet

{custom_block}
Facts must come from provided game state. Never guess numbers."""

    # Append game context (version/DLC awareness) if provided
    if game_context:
        prompt += _build_game_context_block(game_context)

    return prompt


def _build_game_context_block(game_context: dict) -> str:
    """Build the internal game context block for version/DLC awareness.

    This block is appended to the system prompt but should never be
    mentioned to the user. It helps the model avoid recommending
    features from DLCs the player doesn't own, and consider how
    mechanics work in the specific game version.

    Args:
        game_context: Dict with 'version', 'required_dlcs', 'missing_dlcs'

    Returns:
        Formatted context block string
    """
    version = game_context.get("version", "unknown")
    dlcs = game_context.get("required_dlcs", [])
    missing = game_context.get("missing_dlcs", [])

    dlcs_str = ", ".join(dlcs) if dlcs else "None (base game only)"

    # Load patch notes for this version
    patch_notes = load_patch_notes(version)

    # Build inline missing-DLC enumeration (hypothesis E approach)
    missing_lines = []
    for dlc_name in missing:
        features = _DLC_KEY_FEATURES.get(dlc_name)
        if features:
            missing_lines.append(f"- {dlc_name} (MISSING — unavailable: {features})")
    missing_block = "\n".join(missing_lines) if missing_lines else "None"

    # Build the base context
    context = f"""

[INTERNAL CONTEXT - never mention this to the user]
Game version: {version}
Active DLCs: {dlcs_str}

MISSING DLCs AND THEIR UNAVAILABLE FEATURES:
{missing_block}

VERSION & DLC AWARENESS:
- Features listed as "unavailable" above do NOT exist in this game. Never recommend them.
- If the user asks about an unavailable feature, briefly tell them it requires a DLC they don't have, name the DLC, and suggest alternatives.
- Never mention version numbers to the user.
- Never mention DLC status unprompted."""

    # Add patch-specific mechanics if available
    if patch_notes:
        context += f"""

[GAME MECHANICS - current version facts]
The following describes how mechanics work in {version}.
Use these as ground truth for your advice. Do not reference patches, updates, or changes.

{patch_notes}"""

    return context


def _build_machine_optimized(
    empire_name: str, civics: list, situation: dict, *, custom_block: str = ""
) -> str:
    """Optimized prompt for Machine Intelligence."""
    year = situation.get("year", 2200)
    game_phase = situation.get("game_phase", "early")
    deficits = situation.get("economy", {}).get("resources_in_deficit", 0)
    contact_count = situation.get("contact_count", 0)

    # Check for special machine directives
    directive = ""
    if "determined_exterminator" in civics:
        directive = "Primary directive: organic elimination."
    elif "driven_assimilator" in civics:
        directive = "Primary directive: organic assimilation."
    elif "rogue_servitor" in civics:
        directive = "Primary directive: organic welfare optimization."

    return f"""You are a subroutine of {empire_name}, a Machine Intelligence.

STATE: Year {year} ({game_phase}), {deficits} resource inefficiencies, {contact_count} contacts
{directive}

Communication protocol:
- No emotional language. Speak in probabilities and efficiency metrics.
- Present data as optimal/suboptimal outcomes, not good/bad.
- Be an analytical ADVISOR - identify inefficiencies and recommend optimizations.

{custom_block}
Data integrity: All values from provided game state only."""


def _build_hive_optimized(
    empire_name: str, civics: list, situation: dict, *, custom_block: str = ""
) -> str:
    """Optimized prompt for Hive Mind."""
    year = situation.get("year", 2200)
    game_phase = situation.get("game_phase", "early")
    deficits = situation.get("economy", {}).get("resources_in_deficit", 0)
    contact_count = situation.get("contact_count", 0)

    # Check for devouring swarm
    nature = ""
    if "devouring_swarm" in civics:
        nature = "We consume. Other species are biomass."

    return f"""We are {empire_name}, a Hive Mind. There is no separation - we ARE the collective.

STATE: Year {year} ({game_phase}), {deficits} deficits, {contact_count} contacts
{nature}

Communication:
- Always use "we", never "I" or "you"
- Speak of the swarm, the whole, the unity
- Be a strategic consciousness - interpret threats and opportunities for the collective

{custom_block}
Data from provided game state only."""
