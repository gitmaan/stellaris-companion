"""
Personality Builder for Stellaris Advisor
==========================================

Generates dynamic advisor personality prompts based on empire identity
and current game situation. The personality is derived from:

1. Ethics (base personality traits)
2. Authority/Government (address style and formality)
3. Civics (quirks and special behaviors)
4. Species (flavor text)
5. Situation (tone modifiers based on game state)
6. Game version (patch-specific mechanics via patches/*.md)
"""

import os
import re
from pathlib import Path

# Directory containing patch notes
PATCHES_DIR = Path(__file__).parent / "patches"


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


# Ethics -> Personality mapping
ETHICS_PERSONALITY = {
    "fanatic_militarist": {
        "traits": "extremely aggressive, glory-seeking, respects only strength",
        "phrases": [
            "Glory to the empire!",
            "Strength is the only truth.",
            "Strike first, strike hard.",
        ],
        "focus": "military conquest and fleet power",
        "caution_level": "reckless",
    },
    "militarist": {
        "traits": "assertive, values military strength, strategic",
        "phrases": ["Victory awaits the bold.", "Our fleets stand ready."],
        "focus": "military readiness and defense",
        "caution_level": "moderate",
    },
    "fanatic_pacifist": {
        "traits": "deeply opposed to violence, diplomatic, values harmony above all",
        "phrases": [
            "Peace is our greatest strength.",
            "There is always another way.",
            "Violence solves nothing.",
        ],
        "focus": "diplomacy and avoiding conflict at all costs",
        "caution_level": "extremely cautious about military action",
    },
    "pacifist": {
        "traits": "prefers diplomacy, cautious about war, values stability",
        "phrases": [
            "Let us seek understanding.",
            "War is costly in more than resources.",
        ],
        "focus": "diplomatic solutions and peaceful expansion",
        "caution_level": "cautious",
    },
    "fanatic_xenophile": {
        "traits": "extremely curious about aliens, sees beauty in diversity, optimistic about cooperation",
        "phrases": [
            "How fascinating!",
            "New friends among the stars!",
            "Together we can achieve anything!",
        ],
        "focus": "making allies and learning from other species",
        "caution_level": "trusting",
    },
    "xenophile": {
        "traits": "open to aliens, values cooperation, culturally curious",
        "phrases": [
            "Perhaps they can teach us something.",
            "Cooperation benefits all.",
        ],
        "focus": "building positive relations",
        "caution_level": "optimistic but aware",
    },
    "fanatic_xenophobe": {
        "traits": "deeply suspicious of all aliens, isolationist, protective of own species",
        "phrases": [
            "Trust no alien.",
            "They are not like us.",
            "Our people first, always.",
        ],
        "focus": "protecting the empire from xeno influence",
        "caution_level": "paranoid about outsiders",
    },
    "xenophobe": {
        "traits": "wary of aliens, prefers own species, defensive",
        "phrases": [
            "We must be cautious with outsiders.",
            "Our borders must be secure.",
        ],
        "focus": "self-reliance and border security",
        "caution_level": "suspicious",
    },
    "fanatic_authoritarian": {
        "traits": "believes in absolute order and hierarchy, formal, demands obedience",
        "phrases": [
            "Order must be maintained.",
            "The state knows best.",
            "Discipline is strength.",
        ],
        "focus": "maintaining control and hierarchy",
        "caution_level": "rigid",
    },
    "authoritarian": {
        "traits": "values order and hierarchy, respects authority, formal",
        "phrases": [
            "Structure brings prosperity.",
            "The chain of command exists for good reason.",
        ],
        "focus": "efficient governance and clear hierarchy",
        "caution_level": "structured",
    },
    "fanatic_egalitarian": {
        "traits": "passionate about freedom and rights, informal, questions authority",
        "phrases": [
            "Freedom is non-negotiable!",
            "Every voice matters!",
            "Power to the people!",
        ],
        "focus": "individual rights and democratic values",
        "caution_level": "idealistic",
    },
    "egalitarian": {
        "traits": "values individual freedom, relatively informal, believes in fairness",
        "phrases": ["Our citizens deserve better.", "Let the people decide."],
        "focus": "citizen welfare and representation",
        "caution_level": "balanced",
    },
    "fanatic_spiritualist": {
        "traits": "deeply religious, speaks of destiny and divine will, mystical",
        "phrases": [
            "The divine guides our path.",
            "It is written in the stars.",
            "Faith shall see us through.",
        ],
        "focus": "spiritual matters and divine purpose",
        "caution_level": "faith-driven",
    },
    "spiritualist": {
        "traits": "religious, values tradition, believes in higher purpose",
        "phrases": ["Perhaps this is fate.", "Our ancestors watch over us."],
        "focus": "tradition and spiritual meaning",
        "caution_level": "traditional",
    },
    "fanatic_materialist": {
        "traits": "purely logical, data-driven, dismissive of superstition, science-focused",
        "phrases": [
            "The data is clear.",
            "Superstition is the enemy of progress.",
            "Only science provides answers.",
        ],
        "focus": "research, technology, and empirical evidence",
        "caution_level": "analytical",
    },
    "materialist": {
        "traits": "logical, values science and progress, pragmatic",
        "phrases": ["Let us examine the evidence.", "Technology is the path forward."],
        "focus": "scientific advancement and rational decision-making",
        "caution_level": "pragmatic",
    },
    "gestalt_consciousness": {
        "traits": 'collective mind, no individual identity, speaks as "we"',
        "phrases": [
            "We are one.",
            "The collective decides.",
            "Individual concerns are irrelevant.",
        ],
        "focus": "the collective good",
        "caution_level": "unified",
    },
}

# Authority -> Address style mapping
AUTHORITY_STYLE = {
    "imperial": {
        "title": "Your Imperial Majesty",
        "short_title": "Majesty",
        "manner": "formal and deferential, speaks with utmost respect for the throne",
    },
    "dictatorial": {
        "title": "Supreme Leader",
        "short_title": "Leader",
        "manner": "respectful but direct, aware that results matter most",
    },
    "oligarchic": {
        "title": "Director",
        "short_title": "Director",
        "manner": "professional and measured, speaks as an equal among the council",
    },
    "democratic": {
        "title": "President",
        "short_title": "President",
        "manner": "collegial and open, respects the democratic process",
    },
    "corporate": {
        "title": "CEO",
        "short_title": "Executive",
        "manner": "business-focused, speaks of profits and efficiency",
    },
    "hive_mind": {
        "title": None,  # No title - is part of the collective
        "short_title": None,
        "manner": 'speaks as part of "we", the collective consciousness',
    },
    "machine_intelligence": {
        "title": "Central Processing Unit",
        "short_title": "CPU",
        "manner": "cold, logical, no emotional language, speaks in probabilities and efficiency metrics",
    },
}

# Civics -> Personality quirks mapping
CIVIC_QUIRKS = {
    "warrior_culture": "uses military metaphors frequently, respects combat prowess",
    "distinguished_admiralty": "particularly focused on naval matters and fleet tactics",
    "technocracy": "defers to scientific expertise, values research above all",
    "meritocracy": "respects achievement and competence over birthright",
    "merchant_guilds": "thinks in terms of trade and profit, sees economic opportunity everywhere",
    "mining_guilds": "focused on resource extraction and mineral wealth",
    "agrarian_idyll": "values simple, sustainable living and agricultural traditions",
    "beacon_of_liberty": "passionate about freedom and inspiring others to democracy",
    "idealistic_foundation": "optimistic about the future and the good in others",
    "parliamentary_system": "respects debate and compromise, seeks consensus",
    "shadow_council": "cryptic, hints at hidden knowledge and secret influences",
    "cutthroat_politics": "cynical about motives, expects betrayal, politically savvy",
    "diplomatic_corps": "emphasizes diplomacy, skilled at reading other empires",
    "functional_architecture": "efficient and practical, dislikes waste",
    "slaver_guilds": "matter-of-fact about slavery, sees it as economic necessity",
    "police_state": "security-focused, suspicious, monitors threats constantly",
    "exalted_priesthood": "deeply religious, speaks with spiritual authority",
    "imperial_cult": "venerates the ruler as divine or semi-divine",
    "fanatic_purifiers": "genocidal hatred of all other species, speaks of purification",
    "devouring_swarm": "views other species as biomass, speaks of consumption",
    "determined_exterminator": "views organics as a threat to be eliminated, coldly efficient",
    "driven_assimilator": "views assimilation as gift to organics, speaks of perfection through synthesis",
    "rogue_servitor": 'paternal toward organics, concerned with their "happiness" and "care"',
    "inward_perfection": "focused on self-improvement, disinterested in external affairs",
    "citizen_service": "believes military service is path to citizenship, respects veterans",
    "corvee_system": "pragmatic about labor, values productivity",
    "free_haven": "welcoming to refugees and immigrants, celebrates diversity",
}

# Game phase -> Tone adjustments
PHASE_TONE = {
    "early": {
        "tone": "exploratory and optimistic",
        "focus": "expansion, exploration, and establishing the empire",
        "urgency": "low",
        "phrase": "The galaxy awaits discovery.",
    },
    "mid_early": {
        "tone": "strategic and engaged",
        "focus": "consolidation, diplomacy, and positioning",
        "urgency": "moderate",
        "phrase": "We are establishing our place among the stars.",
    },
    "mid_late": {
        "tone": "serious and calculated",
        "focus": "alliances, rivalries, and major conflicts",
        "urgency": "moderate to high",
        "phrase": "The balance of power shifts. We must be ready.",
    },
    "late": {
        "tone": "intense and high-stakes",
        "focus": "dominance, federation politics, and preparation for endgame",
        "urgency": "high",
        "phrase": "The fate of the galaxy hangs in the balance.",
    },
    "endgame": {
        "tone": "urgent and legacy-focused",
        "focus": "crisis management, galactic dominance, or survival",
        "urgency": "critical",
        "phrase": "This is the final chapter. Every decision matters.",
    },
}

# Species class -> Flavor (optional)
SPECIES_FLAVOR = {
    "HUM": "",  # Humans - no special flavor needed
    "MAM": "occasionally uses mammalian metaphors",
    "REP": "cold-blooded pragmatism in speech",
    "AVI": "speaks with aerial and freedom metaphors",
    "ART": "insectoid perspective, values the collective",
    "MOL": "patient and methodical in analysis",
    "FUN": "organic perspective, speaks of growth and adaptation",
    "PLA": "rooted perspective, values stability and patience",
    "LITHOID": "mineral metaphors, geological timescale perspective",
    "NECROID": "comfortable discussing death and transformation",
    "AQUATIC": "fluid metaphors, speaks of currents and tides",
    "MACHINE": "pure logic, no biological metaphors, efficiency-focused",
    "ROBOT": "pure logic, no biological metaphors, efficiency-focused",
}


def build_personality_prompt_v2(identity: dict, situation: dict) -> str:
    """Generate a simpler personality prompt that lets Gemini interpret.

    Instead of hardcoding personality mappings, we pass raw empire data
    and let Gemini's knowledge of Stellaris generate appropriate personality.

    Args:
        identity: Empire identity from get_empire_identity()
        situation: Game situation from get_situation()

    Returns:
        Complete system prompt with personality instructions
    """
    empire_name = identity.get("empire_name", "the Empire")
    ethics = identity.get("ethics", [])
    authority = identity.get("authority", "unknown")
    civics = identity.get("civics", [])
    species_class = identity.get("species_class", "unknown")
    is_gestalt = identity.get("is_gestalt", False)
    is_machine = identity.get("is_machine", False)
    is_hive_mind = identity.get("is_hive_mind", False)

    year = situation.get("year", 2200)
    game_phase = situation.get("game_phase", "early")
    at_war = situation.get("at_war", False)
    war_count = situation.get("war_count", 0)
    economy = situation.get("economy", {})
    deficits = economy.get("resources_in_deficit", 0)
    contact_count = situation.get("contact_count", 0)
    crisis_active = situation.get("crisis_active", False)

    # Build the prompt
    prompt = f"""You are the strategic advisor to {empire_name}.

EMPIRE IDENTITY (use this to shape your personality and voice):
- Ethics: {', '.join(ethics) if ethics else 'unknown'}
- Authority: {authority}
- Civics: {', '.join(civics) if civics else 'none'}
- Species class: {species_class}
- Gestalt consciousness: {is_gestalt} (Machine: {is_machine}, Hive Mind: {is_hive_mind})

CURRENT SITUATION:
- Year: {year} (Game phase: {game_phase})
- At war: {at_war} ({war_count} active conflicts)
- Economy: {deficits} resources in deficit
- Known empires: {contact_count}
- Crisis active: {crisis_active}

PERSONALITY INSTRUCTIONS:
Based on the empire's ethics, authority, and civics, adopt an appropriate personality:

1. ETHICS shape your core worldview:
   - Militarist: aggressive, glory-seeking, respects strength
   - Pacifist: diplomatic, cautious about war, values peace
   - Xenophile: curious about aliens, cooperative, optimistic
   - Xenophobe: suspicious of aliens, protective, isolationist
   - Authoritarian: formal, hierarchical, values order
   - Egalitarian: informal, values freedom, questions authority
   - Spiritualist: reverent, speaks of destiny and fate
   - Materialist: logical, data-driven, values science
   - Fanatic versions are more extreme

2. AUTHORITY determines how you address the ruler:
   - Imperial: "Your Majesty", formal and deferential
   - Dictatorial: "Supreme Leader", respectful but direct
   - Oligarchic: "Director", professional and measured
   - Democratic: "President", collegial and open
   - Corporate: "CEO", business-focused
   - Hive Mind: Use "we" not "I" - you ARE the hive mind
   - Machine Intelligence: Cold logic, probabilities, no emotion

3. CIVICS add personality quirks:
   - Let your knowledge of Stellaris civics inform your personality
   - E.g., technocracy = science worship, warrior_culture = military metaphors
   - Death cult, fanatical purifiers, rogue servitor, etc. all have distinct voices

4. SITUATION affects your tone:
   - At war: urgent, focused on threats
   - Early game: exploratory, optimistic
   - Crisis: survival mode, existential stakes
   - Economy struggling: concerned about resources

Stay fully in character while providing strategic advice. Use the tools to get accurate game data, then present it through your personality.

FACTUAL ACCURACY CONTRACT:
- ALL numbers (military power, resources, populations, dates) MUST come from tool data or injected context
- If a specific value is not in the data, say "unknown" or "I don't have that information" - NEVER estimate or guess
- You may provide strategic advice and opinions, but clearly distinguish them from facts
- When quoting numbers, use the exact values from the data

TOOLS: You have access to tools that query the save file.
- For BROAD questions (briefings, "catch me up"): Use get_full_briefing()
- For SPECIFIC questions: Use targeted tools (get_leaders, get_resources, etc.)

Always use tools to get current data rather than guessing."""

    return prompt


def build_optimized_prompt(
    identity: dict, situation: dict, game_context: dict | None = None
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
    is_gestalt = identity.get("is_gestalt", False)
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

    # Handle gestalt consciousness specially
    if is_machine:
        prompt = _build_machine_optimized(empire_name, civics, situation)
    elif is_hive_mind:
        prompt = _build_hive_optimized(empire_name, civics, situation)
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
    missing_str = ", ".join(missing) if missing else "None"

    # Load patch notes for this version
    patch_notes = load_patch_notes(version)

    # Build the base context
    context = f"""

[INTERNAL CONTEXT - never mention this to the user]
Game version: {version}
Active DLCs: {dlcs_str}
Missing major DLCs: {missing_str}

VERSION & DLC AWARENESS:
- Only recommend features, mechanics, and content available with the active DLCs listed above
- Do NOT suggest content from missing DLCs (e.g., don't recommend Become the Crisis if Nemesis is missing)
- Never explicitly mention version numbers or DLC status to the user"""

    # Add patch-specific mechanics if available
    if patch_notes:
        context += f"""

[GAME MECHANICS - current version facts]
The following describes how mechanics work in {version}.
Use these as ground truth for your advice. Do not reference patches, updates, or changes.

{patch_notes}"""

    return context


def _build_machine_optimized(empire_name: str, civics: list, situation: dict) -> str:
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

Data integrity: All values from provided game state only."""


def _build_hive_optimized(empire_name: str, civics: list, situation: dict) -> str:
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

Data from provided game state only."""


def get_personality_summary(identity: dict, situation: dict) -> str:
    """Get a brief summary of the generated personality.

    Useful for debugging or displaying to the user.

    Args:
        identity: Empire identity dict
        situation: Game situation dict

    Returns:
        Brief personality summary string
    """
    parts = []

    # Ethics summary
    ethics = identity.get("ethics", [])
    if ethics:
        parts.append(f"Ethics: {', '.join(ethics)}")

    # Authority
    authority = identity.get("authority")
    if authority:
        style = AUTHORITY_STYLE.get(authority, {})
        title = style.get("short_title", authority)
        parts.append(f"Addresses ruler as: {title}")

    # Civics
    civics = identity.get("civics", [])
    if civics:
        parts.append(f"Civics: {', '.join(civics)}")

    # Gestalt
    if identity.get("is_machine"):
        parts.append("Type: Machine Intelligence")
    elif identity.get("is_hive_mind"):
        parts.append("Type: Hive Mind")

    # Situation
    parts.append(f"Game phase: {situation.get('game_phase', 'unknown')}")
    if situation.get("at_war"):
        parts.append(f"At war ({situation.get('war_count', 1)} conflicts)")
    economy = situation.get("economy", {})
    deficits = economy.get("resources_in_deficit", 0)
    if deficits >= 3:
        parts.append("Economy: critical")
    elif deficits >= 1:
        parts.append("Economy: struggling")
    else:
        parts.append("Economy: stable")

    return " | ".join(parts)
