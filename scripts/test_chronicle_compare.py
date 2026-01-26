#!/usr/bin/env python3
"""
Compare chronicle output WITH and WITHOUT Stellaris Invicta reference.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

MODEL = "gemini-3-flash-preview"

# Style guide WITH explicit Stellaris Invicta reference
STYLE_WITH_REFERENCE = """=== STYLE GUIDE ===
- Write like the Templin Institute's "Stellaris Invicta" series: epic, dramatic, cinematic
- Each chapter should read like the opening crawl of a space opera
- Use vivid language: "The stars themselves trembled" not "There was a big war"
- Name specific dates when dramatic (e.g., "On the first day of 2350, the sky burned")
- When leader names are missing or show as placeholders, use titles instead ("The Grand Admiral", "A brilliant scientist")
- DO NOT fabricate events - only reference what appears in the event log
- DO NOT give advice or recommendations - you are a chronicler, not an advisor"""

# Style guide WITHOUT the reference - describe the style instead
STYLE_WITHOUT_REFERENCE = """=== STYLE GUIDE ===
- Write as an epic galactic chronicle: dramatic, cinematic, larger-than-life
- Each chapter should read like the opening crawl of a space opera
- Use vivid, evocative language: "The stars themselves trembled" not "There was a big war"
- Employ narrative techniques: foreshadowing, dramatic irony, rising tension
- Name specific dates when dramatic (e.g., "On the first day of 2350, the sky burned")
- When leader names are missing or show as placeholders, use titles instead ("The Grand Admiral", "A brilliant scientist")
- DO NOT fabricate events - only reference what appears in the event log
- DO NOT give advice or recommendations - you are a chronicler, not an advisor"""


def get_db_connection():
    db_path = Path(__file__).parent.parent / "stellaris_history.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_session_data(conn, session_id: str) -> dict:
    session = dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone())

    events = [
        dict(row)
        for row in conn.execute(
            """SELECT event_type, game_date, summary
           FROM events WHERE session_id = ? ORDER BY game_date""",
            (session_id,),
        ).fetchall()
    ]

    briefing_json = session.get("latest_briefing_json")
    briefing = json.loads(briefing_json) if briefing_json else {}

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


def dedupe_events(events):
    seen = set()
    deduped = []
    for e in events:
        key = (e["game_date"], e["event_type"], e["summary"])
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    return deduped


def format_events_for_llm(events):
    events = dedupe_events(events)
    by_year = {}
    for e in events:
        year = e["game_date"][:4] if e["game_date"] else "Unknown"
        if year not in by_year:
            by_year[year] = []
        by_year[year].append(e)

    lines = []
    for year in sorted(by_year.keys()):
        year_events = by_year[year]
        if len(year_events) > 10:
            notable = [
                e
                for e in year_events
                if e["event_type"]
                in (
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
                )
            ]
            lines.append(f"\n=== {year} ===")
            for e in notable:
                lines.append(f"  * {e['summary']}")
        else:
            lines.append(f"\n=== {year} ===")
            for e in year_events:
                lines.append(f"  * {e['summary']}")
    return "\n".join(lines)


def summarize_state(briefing):
    identity = briefing.get("identity", {})
    situation = briefing.get("situation", {})
    military = briefing.get("military", {})
    territory = briefing.get("territory", {})
    endgame = briefing.get("endgame", {})

    lines = [
        "=== CURRENT STATE ===",
        f"Empire: {identity.get('empire_name', 'Unknown')}",
        f"Year: {situation.get('year', '?')}",
        f"Military Power: {military.get('military_power', 0):,.0f}",
        f"Colonies: {territory.get('colonies', {}).get('total_count', 0)}",
    ]

    crisis = endgame.get("crisis", {})
    if crisis.get("crisis_active"):
        lines.append(
            f"CRISIS: {crisis.get('crisis_type', 'Unknown').title()} ({crisis.get('crisis_systems_count', 0)} systems)"
        )

    fe = situation.get("fallen_empires", {})
    if fe.get("awakened_count", 0) > 0:
        lines.append(f"Awakened Empires: {fe.get('awakened_count', 0)}")

    return "\n".join(lines)


def build_prompt(data: dict, style_guide: str) -> str:
    briefing = data["briefing"]
    identity = briefing.get("identity", {})

    empire_name = identity.get("empire_name", "Unknown Empire")
    ethics = ", ".join(identity.get("ethics", []))
    authority = identity.get("authority", "unknown")
    civics = ", ".join(identity.get("civics", []))

    if "egalitarian" in ethics or "fanatic_egalitarian" in ethics:
        voice_note = "Write celebrating the triumph of the people. Emphasize collective achievement and democratic ideals."
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

You are NOT an advisor. You do NOT give recommendations or strategic advice. You are a HISTORIAN writing for future generations.

{style_guide}

{state_text}

=== COMPLETE EVENT HISTORY ===
(From {data["first_date"]} to {data["last_date"]})
{events_text}

=== YOUR TASK ===

Write a chronicle divided into 4-6 chapters. For each chapter:
1. **Chapter Title**: A dramatic, thematic name
2. **Date Range**: The years this chapter covers
3. **Narrative**: 2-4 paragraphs of dramatic prose

End with "The Story Continues..." about the current situation.

Begin the chronicle now.
"""
    return prompt


def call_gemini(prompt: str) -> str:
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
        raise ValueError("GOOGLE_API_KEY not found")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL, contents=prompt, config={"temperature": 1.0, "max_output_tokens": 4096}
    )
    return response.text


def main():
    print("=" * 70)
    print("COMPARING: With vs Without 'Stellaris Invicta' Reference")
    print("=" * 70)

    conn = get_db_connection()

    # Use session 2 (War in Heaven)
    sessions = conn.execute(
        """SELECT id, empire_name FROM sessions ORDER BY started_at DESC"""
    ).fetchall()
    session_id = sessions[1]["id"]  # Session 2

    data = get_session_data(conn, session_id)
    print(f"\nUsing: {data['briefing']['identity']['empire_name']}")
    print(f"Events: {len(data['events'])}")

    # Test 1: WITH reference
    print("\n" + "=" * 70)
    print("TEST 1: WITH 'Stellaris Invicta' Reference")
    print("=" * 70)

    prompt_with = build_prompt(data, STYLE_WITH_REFERENCE)
    output_with = call_gemini(prompt_with)

    Path(__file__).parent.joinpath("compare_WITH_reference.txt").write_text(output_with)
    print("\nFirst 1500 chars:")
    print("-" * 40)
    print(output_with[:1500])
    print("...")

    # Test 2: WITHOUT reference
    print("\n" + "=" * 70)
    print("TEST 2: WITHOUT 'Stellaris Invicta' Reference")
    print("=" * 70)

    prompt_without = build_prompt(data, STYLE_WITHOUT_REFERENCE)
    output_without = call_gemini(prompt_without)

    Path(__file__).parent.joinpath("compare_WITHOUT_reference.txt").write_text(output_without)
    print("\nFirst 1500 chars:")
    print("-" * 40)
    print(output_without[:1500])
    print("...")

    # Summary
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    print(f"\nWITH reference: {len(output_with)} chars")
    print(f"WITHOUT reference: {len(output_without)} chars")
    print("\nFull outputs saved to:")
    print("  - scripts/compare_WITH_reference.txt")
    print("  - scripts/compare_WITHOUT_reference.txt")


if __name__ == "__main__":
    main()
