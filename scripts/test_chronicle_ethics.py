#!/usr/bin/env python3
"""
Test chronicle voice differentiation across ethics types.

Uses existing Session 2 event data but modifies the ethics to test:
1. Egalitarian (baseline - already tested)
2. Authoritarian
3. Machine Intelligence
"""

import json
import os
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

MODEL = "gemini-3-flash-preview"

STYLE_GUIDE = """=== STYLE GUIDE ===
- Write as an epic galactic chronicle: dramatic, cinematic, larger-than-life
- Each chapter should read like the opening crawl of a space opera
- Use vivid, evocative language: "The stars themselves trembled" not "There was a big war"
- Employ narrative techniques: foreshadowing, dramatic irony, rising tension
- Name specific dates when dramatic (e.g., "On the first day of 2350, the sky burned")
- When leader names are missing or show as placeholders, use titles instead
- DO NOT fabricate events - only reference what appears in the event log
- DO NOT give advice or recommendations - you are a chronicler, not an advisor"""


def get_db_connection():
    db_path = Path(__file__).parent.parent / "stellaris_history.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_session_data(conn, session_id: str) -> dict:
    session = dict(conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone())

    events = [dict(row) for row in conn.execute(
        """SELECT event_type, game_date, summary
           FROM events WHERE session_id = ? ORDER BY game_date""",
        (session_id,)
    ).fetchall()]

    briefing_json = session.get('latest_briefing_json')
    briefing = json.loads(briefing_json) if briefing_json else {}

    dates = conn.execute(
        """SELECT MIN(game_date) as first_date, MAX(game_date) as last_date
           FROM snapshots WHERE session_id = ?""",
        (session_id,)
    ).fetchone()

    return {
        'session': session,
        'events': events,
        'briefing': briefing,
        'first_date': dates['first_date'],
        'last_date': dates['last_date'],
    }


def dedupe_events(events):
    seen = set()
    deduped = []
    for e in events:
        key = (e['game_date'], e['event_type'], e['summary'])
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    return deduped


def format_events_for_llm(events):
    events = dedupe_events(events)
    by_year = {}
    for e in events:
        year = e['game_date'][:4] if e['game_date'] else 'Unknown'
        if year not in by_year:
            by_year[year] = []
        by_year[year].append(e)

    lines = []
    for year in sorted(by_year.keys()):
        year_events = by_year[year]
        if len(year_events) > 10:
            notable = [e for e in year_events if e['event_type'] in (
                'war_started', 'war_ended', 'crisis_started', 'fallen_empire_awakened',
                'war_in_heaven_started', 'federation_joined', 'alliance_formed',
                'alliance_ended', 'colony_count_change', 'military_power_change')]
            lines.append(f"\n=== {year} ===")
            for e in notable:
                lines.append(f"  * {e['summary']}")
        else:
            lines.append(f"\n=== {year} ===")
            for e in year_events:
                lines.append(f"  * {e['summary']}")
    return '\n'.join(lines)


def summarize_state(briefing):
    identity = briefing.get('identity', {})
    situation = briefing.get('situation', {})
    military = briefing.get('military', {})
    territory = briefing.get('territory', {})
    endgame = briefing.get('endgame', {})

    lines = [
        f"=== CURRENT STATE ===",
        f"Empire: {identity.get('empire_name', 'Unknown')}",
        f"Year: {situation.get('year', '?')}",
        f"Military Power: {military.get('military_power', 0):,.0f}",
        f"Colonies: {territory.get('colonies', {}).get('total_count', 0)}",
    ]

    crisis = endgame.get('crisis', {})
    if crisis.get('crisis_active'):
        lines.append(f"CRISIS: {crisis.get('crisis_type', 'Unknown').title()} ({crisis.get('crisis_systems_count', 0)} systems)")

    fe = situation.get('fallen_empires', {})
    if fe.get('awakened_count', 0) > 0:
        lines.append(f"Awakened Empires: {fe.get('awakened_count', 0)}")

    return '\n'.join(lines)


# Ethics configurations to test
ETHICS_CONFIGS = {
    'egalitarian': {
        'empire_name': 'United Nations of Earth 2',
        'ethics': ['fanatic_egalitarian', 'xenophile'],
        'authority': 'democratic',
        'civics': ['idealistic_foundation', 'meritocracy'],
        'is_machine': False,
        'is_hive_mind': False,
        'voice': "Write celebrating the triumph of the people. Emphasize collective achievement and democratic ideals.",
    },
    'authoritarian': {
        'empire_name': 'The Terran Imperium',
        'ethics': ['fanatic_authoritarian', 'militarist'],
        'authority': 'imperial',
        'civics': ['distinguished_admiralty', 'police_state'],
        'is_machine': False,
        'is_hive_mind': False,
        'voice': "Write with imperial grandeur. Emphasize the glory of the state, the wisdom of the throne, and the order that hierarchy brings. Frame sacrifices as necessary for the Empire's eternal glory.",
    },
    'machine': {
        'empire_name': 'The Calculated Consensus',
        'ethics': ['gestalt_consciousness'],
        'authority': 'machine_intelligence',
        'civics': ['determined_exterminator', 'rapid_replicator'],
        'is_machine': True,
        'is_hive_mind': False,
        'voice': "Write with cold, logical precision. No emotion, only analysis of historical patterns. Use technical terminology. Refer to organic conflicts as 'inefficient resource allocation'. Frame the chronicle as a data log for future processing units.",
    },
}


def build_prompt(data: dict, ethics_config: dict) -> str:
    empire_name = ethics_config['empire_name']
    ethics = ', '.join(ethics_config['ethics'])
    authority = ethics_config['authority']
    civics = ', '.join(ethics_config['civics'])
    voice_note = ethics_config['voice']

    events_text = format_events_for_llm(data['events'])
    state_text = summarize_state(data['briefing'])

    # Override empire name in state text
    state_text = state_text.replace(
        data['briefing']['identity']['empire_name'],
        empire_name
    )

    prompt = f"""You are the Royal Chronicler of {empire_name}. Your task is to write the official historical chronicle of this empire.

=== EMPIRE IDENTITY ===
Name: {empire_name}
Ethics: {ethics}
Authority: {authority}
Civics: {civics}

=== CHRONICLER'S VOICE ===
{voice_note}

You are NOT an advisor. You do NOT give recommendations or strategic advice. You are a HISTORIAN writing for future generations.

{STYLE_GUIDE}

{state_text}

=== COMPLETE EVENT HISTORY ===
(From {data['first_date']} to {data['last_date']})
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

    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        env_path = Path(__file__).parent.parent / '.env'
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith('GOOGLE_API_KEY='):
                    api_key = line.split('=', 1)[1].strip()
                    break

    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={'temperature': 1.0, 'max_output_tokens': 4096}
    )
    return response.text


def extract_voice_indicators(output: str) -> dict:
    """Extract phrases that indicate the voice/ethics of the chronicle."""
    output_lower = output.lower()

    indicators = {
        'egalitarian': [
            'people', 'citizens', 'democracy', 'liberty', 'freedom',
            'collective', 'republic', 'beacon', 'hope', 'rights'
        ],
        'authoritarian': [
            'empire', 'throne', 'glory', 'order', 'obedience',
            'emperor', 'imperial', 'majesty', 'dominion', 'subjects'
        ],
        'machine': [
            'processing', 'calculated', 'efficiency', 'units', 'data',
            'protocol', 'optimal', 'logic', 'parameters', 'designation'
        ],
    }

    counts = {}
    for ethics_type, words in indicators.items():
        counts[ethics_type] = sum(1 for word in words if word in output_lower)

    return counts


def main():
    print("=" * 70)
    print("CHRONICLE ETHICS VOICE TESTING")
    print("=" * 70)

    conn = get_db_connection()

    # Use session 2 (War in Heaven) for all tests
    sessions = conn.execute(
        """SELECT id, empire_name FROM sessions ORDER BY started_at DESC"""
    ).fetchall()
    session_id = sessions[1]['id']

    data = get_session_data(conn, session_id)
    print(f"\nUsing event data from: {data['briefing']['identity']['empire_name']}")
    print(f"Events: {len(data['events'])}")

    results = {}

    for ethics_name, ethics_config in ETHICS_CONFIGS.items():
        print("\n" + "=" * 70)
        print(f"TESTING: {ethics_name.upper()} ({ethics_config['empire_name']})")
        print("=" * 70)

        prompt = build_prompt(data, ethics_config)
        output = call_gemini(prompt)

        # Save output
        filename = f"ethics_{ethics_name}.txt"
        Path(__file__).parent.joinpath(filename).write_text(output)
        print(f"Saved to: scripts/{filename}")

        # Analyze voice
        voice_counts = extract_voice_indicators(output)
        results[ethics_name] = {
            'output': output,
            'voice_counts': voice_counts,
            'length': len(output),
        }

        # Show first 800 chars
        print(f"\n--- First 800 chars ---")
        print(output[:800])
        print("...")

        print(f"\nVoice indicator counts:")
        for vtype, count in voice_counts.items():
            marker = "✓" if vtype == ethics_name else " "
            print(f"  {marker} {vtype}: {count}")

    # Summary comparison
    print("\n" + "=" * 70)
    print("VOICE COMPARISON SUMMARY")
    print("=" * 70)

    print("\n| Ethics Type | Egal Words | Auth Words | Machine Words | Dominant |")
    print("|-------------|------------|------------|---------------|----------|")
    for ethics_name, result in results.items():
        vc = result['voice_counts']
        dominant = max(vc, key=vc.get)
        match = "✓" if dominant == ethics_name else "✗"
        print(f"| {ethics_name:11} | {vc['egalitarian']:10} | {vc['authoritarian']:10} | {vc['machine']:13} | {dominant:8} {match} |")

    conn.close()
    print("\nFull outputs saved to scripts/ethics_*.txt")


if __name__ == '__main__':
    main()
