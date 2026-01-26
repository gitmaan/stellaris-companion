#!/usr/bin/env python3
"""
Quick test script to validate LLM-based chronicle generation.
Uses existing database data to generate a sample chronicle.

Run: python scripts/test_chronicle.py
"""

import json
import os
import sqlite3

# Add project root to path
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Model to use - must match production
MODEL = "gemini-3-flash-preview"


def get_db_connection():
    db_path = Path(__file__).parent.parent / "stellaris_history.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_session_data(conn, session_id: str) -> dict:
    """Fetch session, events, and briefing."""

    # Session info
    session = dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone())

    # All events
    events = [
        dict(row)
        for row in conn.execute(
            """SELECT event_type, game_date, summary
           FROM events
           WHERE session_id = ?
           ORDER BY game_date""",
            (session_id,),
        ).fetchall()
    ]

    # Latest briefing
    briefing_json = session.get("latest_briefing_json")
    briefing = json.loads(briefing_json) if briefing_json else {}

    # First/last snapshot dates
    dates = conn.execute(
        """SELECT MIN(game_date) as first_date, MAX(game_date) as last_date
           FROM snapshots WHERE session_id = ?""",
        (session_id,),
    ).fetchone()

    return {
        "session": session,
        "events": events,
        "briefing": briefing,
        "first_date": dates["first_date"],
        "last_date": dates["last_date"],
    }


def dedupe_events(events: list[dict]) -> list[dict]:
    """Remove duplicate events (same date + type + summary)."""
    seen = set()
    deduped = []
    for e in events:
        key = (e["game_date"], e["event_type"], e["summary"])
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    return deduped


def format_events_for_llm(events: list[dict]) -> str:
    """Format events as a readable list for the LLM."""
    events = dedupe_events(events)

    # Group by year
    by_year = {}
    for e in events:
        year = e["game_date"][:4] if e["game_date"] else "Unknown"
        if year not in by_year:
            by_year[year] = []
        by_year[year].append(e)

    lines = []
    for year in sorted(by_year.keys()):
        year_events = by_year[year]
        # Summarize if too many events in one year
        if len(year_events) > 10:
            type_counts = {}
            notable = []
            for e in year_events:
                t = e["event_type"]
                type_counts[t] = type_counts.get(t, 0) + 1
                if t in (
                    "war_started",
                    "war_ended",
                    "crisis_started",
                    "fallen_empire_awakened",
                    "war_in_heaven_started",
                    "federation_joined",
                    "alliance_formed",
                    "alliance_ended",
                    "colony_count_change",
                    "military_power_change",
                ):
                    notable.append(e)

            lines.append(f"\n=== {year} ===")
            for e in notable:
                lines.append(f"  * {e['summary']}")
            routine = [(t, c) for t, c in type_counts.items() if c > 2]
            if routine:
                lines.append(f"  (Also: {', '.join(f'{c}x {t}' for t, c in routine)})")
        else:
            lines.append(f"\n=== {year} ===")
            for e in year_events:
                lines.append(f"  * {e['summary']}")

    return "\n".join(lines)


def summarize_state(briefing: dict, label: str = "CURRENT") -> str:
    """Create a concise state summary."""
    identity = briefing.get("identity", {})
    situation = briefing.get("situation", {})
    military = briefing.get("military", {})
    territory = briefing.get("territory", {})
    endgame = briefing.get("endgame", {})

    lines = [
        f"=== {label} STATE ===",
        f"Empire: {identity.get('empire_name', 'Unknown')}",
        f"Year: {situation.get('year', '?')}",
        f"Military Power: {military.get('military_power', 0):,.0f}",
        f"Colonies: {territory.get('colonies', {}).get('total_count', 0)}",
    ]

    # Crisis info
    crisis = endgame.get("crisis", {})
    if crisis.get("crisis_active"):
        lines.append(
            f"CRISIS: {crisis.get('crisis_type', 'Unknown').title()} ({crisis.get('crisis_systems_count', 0)} systems)"
        )

    # Fallen empires
    fe = situation.get("fallen_empires", {})
    if fe.get("awakened_count", 0) > 0:
        lines.append(f"Awakened Empires: {fe.get('awakened_count', 0)}")

    if fe.get("war_in_heaven"):
        lines.append("WAR IN HEAVEN: Active")

    return "\n".join(lines)


def build_chronicler_prompt(data: dict) -> str:
    """Build a bespoke chronicler prompt - NOT advisor mode."""

    briefing = data["briefing"]
    identity = briefing.get("identity", {})
    situation = briefing.get("situation", {})

    empire_name = identity.get("empire_name", "Unknown Empire")
    ethics = ", ".join(identity.get("ethics", []))
    authority = identity.get("authority", "unknown")
    civics = ", ".join(identity.get("civics", []))

    # Determine voice based on ethics/authority
    if identity.get("is_machine"):
        voice_note = (
            "Write with cold, logical precision. No emotion, only analysis of historical patterns."
        )
    elif identity.get("is_hive_mind"):
        voice_note = "Write as the collective memory. Use 'we' and 'the swarm'. Individual names are meaningless - only the whole matters."
    elif "authoritarian" in ethics or "fanatic_authoritarian" in ethics:
        voice_note = "Write with imperial grandeur. Emphasize the glory of the state and the wisdom of leadership."
    elif "egalitarian" in ethics or "fanatic_egalitarian" in ethics:
        voice_note = "Write celebrating the triumph of the people. Emphasize collective achievement and democratic ideals."
    elif "militarist" in ethics or "fanatic_militarist" in ethics:
        voice_note = "Write with martial pride. Emphasize battles, conquests, and military glory."
    elif "pacifist" in ethics or "fanatic_pacifist" in ethics:
        voice_note = (
            "Write valuing peace and diplomacy. Frame conflicts as tragedies, peace as triumph."
        )
    elif "spiritualist" in ethics or "fanatic_spiritualist" in ethics:
        voice_note = (
            "Write with religious reverence. Frame history as divine providence and sacred destiny."
        )
    elif "materialist" in ethics or "fanatic_materialist" in ethics:
        voice_note = "Write celebrating scientific progress. Frame history as the march of knowledge and reason."
    else:
        voice_note = "Write with epic gravitas befitting a galactic chronicle."

    events_text = format_events_for_llm(data["events"])
    state_text = summarize_state(briefing)

    prompt = f"""You are the Royal Chronicler of {empire_name}. Your task is to write the official historical chronicle of this empire.

=== EMPIRE IDENTITY ===
Name: {empire_name}
Ethics: {ethics}
Authority: {authority}
Civics: {civics}

=== CHRONICLER'S VOICE ===
{voice_note}

You are NOT an advisor. You do NOT give recommendations or strategic advice. You are a HISTORIAN writing for future generations. Write in past tense for completed events, present tense only for the current crisis.

=== STYLE GUIDE ===
- Write like the Templin Institute's "Stellaris Invicta" series: epic, dramatic, cinematic
- Each chapter should read like the opening crawl of a space opera
- Use vivid language: "The stars themselves trembled" not "There was a big war"
- Name specific dates when dramatic (e.g., "On the first day of 2350, the sky burned")
- When leader names are missing or show as placeholders, use titles instead ("The Grand Admiral", "A brilliant scientist")
- DO NOT fabricate events - only reference what appears in the event log
- DO NOT give advice or recommendations - you are a chronicler, not an advisor

{state_text}

=== COMPLETE EVENT HISTORY ===
(From {data["first_date"]} to {data["last_date"]})
{events_text}

=== YOUR TASK ===

Write a chronicle divided into 4-6 chapters. For each chapter:

1. **Chapter Title**: A dramatic, thematic name (e.g., "The Long Night", "Fire and Stars", "The Reckoning")
2. **Date Range**: The years this chapter covers (use actual dates from events)
3. **Narrative**: 2-4 paragraphs of dramatic prose describing this era

End with a brief "The Story Continues..." section about the current situation.

Begin the chronicle now.
"""

    return prompt


def call_gemini(prompt: str) -> str:
    """Call Gemini API to generate the chronicle."""
    from google import genai

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("GOOGLE_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment or .env file")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "temperature": 1.0,
            "max_output_tokens": 4096,
        },
    )
    return response.text


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test chronicle generation")
    parser.add_argument(
        "--session",
        type=int,
        default=None,
        help="Session index (1-based) to use. Default: most events",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("CHRONICLE GENERATION TEST")
    print(f"Model: {MODEL}")
    print("=" * 60)

    conn = get_db_connection()

    # List available sessions
    sessions = conn.execute(
        """SELECT id, empire_name, last_game_date,
                  (SELECT MIN(game_date) FROM snapshots WHERE session_id = sessions.id) as first_date,
                  (SELECT COUNT(*) FROM events WHERE session_id = sessions.id) as event_count
           FROM sessions ORDER BY started_at DESC"""
    ).fetchall()

    print("\nAvailable sessions:")
    for i, s in enumerate(sessions):
        print(
            f"  {i + 1}. {s['empire_name']} ({s['first_date']} → {s['last_game_date']}) - {s['event_count']} events"
        )

    # Select session
    if args.session:
        session_id = sessions[args.session - 1]["id"]
    else:
        session_id = max(sessions, key=lambda s: s["event_count"])["id"]

    selected = next(s for s in sessions if s["id"] == session_id)
    print(f"\nUsing: {selected['empire_name']} ({selected['event_count']} events)")

    # Fetch data
    print("\nFetching data...")
    data = get_session_data(conn, session_id)
    print(f"  Events: {len(data['events'])}")
    print(f"  Date range: {data['first_date']} → {data['last_date']}")

    # Build prompt
    print("\nBuilding chronicler prompt...")
    prompt = build_chronicler_prompt(data)
    print(f"  Prompt length: {len(prompt):,} chars (~{len(prompt) // 4:,} tokens)")

    # Save prompt for inspection
    prompt_path = Path(__file__).parent / "test_chronicle_prompt.txt"
    prompt_path.write_text(prompt)
    print(f"  Saved to: {prompt_path}")

    # Call Gemini
    print("\nCalling Gemini...")
    try:
        chronicle = call_gemini(prompt)
        print("\n" + "=" * 60)
        print("GENERATED CHRONICLE")
        print("=" * 60 + "\n")
        print(chronicle)

        # Save output
        output_path = Path(__file__).parent / "test_chronicle_output.txt"
        output_path.write_text(chronicle)
        print(f"\n(Saved to: {output_path})")

    except Exception as e:
        print(f"\nError calling Gemini: {e}")
        print("\nYou can still inspect the prompt at:")
        print(f"  {prompt_path}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
