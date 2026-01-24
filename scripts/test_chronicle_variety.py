#!/usr/bin/env python3
"""
Test chronicle variety - ensure we don't get cookie-cutter outputs.

Tests:
1. Run same prompt 3x on same session - compare chapter titles
2. Test on both sessions - different data should produce different styles
3. Analyze repeated phrases across outputs
"""

import json
import os
import re
import sqlite3
from collections import Counter
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


def build_prompt(data: dict) -> str:
    briefing = data['briefing']
    identity = briefing.get('identity', {})

    empire_name = identity.get('empire_name', 'Unknown Empire')
    ethics = ', '.join(identity.get('ethics', []))
    authority = identity.get('authority', 'unknown')
    civics = ', '.join(identity.get('civics', []))

    if 'egalitarian' in ethics or 'fanatic_egalitarian' in ethics:
        voice_note = "Write celebrating the triumph of the people. Emphasize collective achievement and democratic ideals."
    elif 'authoritarian' in ethics or 'fanatic_authoritarian' in ethics:
        voice_note = "Write with imperial grandeur. Emphasize the glory and order of the state."
    elif 'militarist' in ethics or 'fanatic_militarist' in ethics:
        voice_note = "Write with martial pride. Emphasize battles, conquests, and military honor."
    else:
        voice_note = "Write with epic gravitas befitting a galactic chronicle."

    events_text = format_events_for_llm(data['events'])
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


def extract_chapter_titles(output: str) -> list:
    """Extract chapter titles from output."""
    # Match patterns like "CHAPTER I:", "Chapter 1:", "### CHAPTER I", etc.
    patterns = [
        r'(?:###?\s*)?(?:CHAPTER|Chapter)\s+[IVX0-9]+[:\s]+([^\n*]+)',
        r'\*\*CHAPTER\s+[IVX0-9]+[:\s]+([^\n*]+)\*\*',
        r'####?\s*CHAPTER\s+[IVX0-9]+[:\s]+([^\n*]+)',
    ]

    titles = []
    for pattern in patterns:
        matches = re.findall(pattern, output, re.IGNORECASE)
        titles.extend([m.strip().strip('*').strip() for m in matches])

    return titles[:6]  # Max 6 chapters


def extract_key_phrases(output: str) -> list:
    """Extract dramatic phrases that might be repeated."""
    phrases = [
        "stars themselves",
        "beacon of",
        "void was shattered",
        "titans of",
        "celestial",
        "forged in",
        "annihilation",
        "trembled",
        "darkest hour",
        "never surrender",
        "ashes of",
        "dawn of",
        "precipice",
        "flames of",
        "shadow",
    ]

    found = []
    output_lower = output.lower()
    for phrase in phrases:
        if phrase in output_lower:
            found.append(phrase)
    return found


def analyze_variety(outputs: list) -> dict:
    """Analyze variety across multiple outputs."""
    all_titles = []
    all_phrases = []

    for output in outputs:
        titles = extract_chapter_titles(output)
        phrases = extract_key_phrases(output)
        all_titles.extend(titles)
        all_phrases.extend(phrases)

    title_counts = Counter(all_titles)
    phrase_counts = Counter(all_phrases)

    # Find repeated titles (same title appearing in multiple runs)
    repeated_titles = {t: c for t, c in title_counts.items() if c > 1}

    # Find overused phrases
    overused_phrases = {p: c for p, c in phrase_counts.items() if c >= len(outputs)}

    return {
        'unique_titles': len(set(all_titles)),
        'total_titles': len(all_titles),
        'repeated_titles': repeated_titles,
        'phrase_counts': dict(phrase_counts),
        'overused_phrases': overused_phrases,
    }


def main():
    print("=" * 70)
    print("CHRONICLE VARIETY TESTING")
    print("=" * 70)

    conn = get_db_connection()

    # Get both sessions
    sessions = conn.execute(
        """SELECT id, empire_name FROM sessions ORDER BY started_at DESC"""
    ).fetchall()

    print(f"\nAvailable sessions:")
    for i, s in enumerate(sessions):
        print(f"  {i+1}. {s['empire_name']}")

    # Test 1: Run 3x on Session 2 (War in Heaven)
    print("\n" + "=" * 70)
    print("TEST 1: REPETITION CHECK - Same session, 3 runs")
    print("=" * 70)

    session_id = sessions[1]['id']  # Session 2
    data = get_session_data(conn, session_id)
    print(f"\nUsing: {data['briefing']['identity']['empire_name']}")

    outputs = []
    for i in range(3):
        print(f"\n--- Run {i+1}/3 ---")
        prompt = build_prompt(data)
        output = call_gemini(prompt)
        outputs.append(output)

        titles = extract_chapter_titles(output)
        print(f"Chapter titles:")
        for t in titles:
            print(f"  - {t}")

        # Save output
        Path(__file__).parent.joinpath(f"variety_session2_run{i+1}.txt").write_text(output)

    # Analyze variety
    print("\n" + "-" * 40)
    print("VARIETY ANALYSIS - Session 2")
    print("-" * 40)

    analysis = analyze_variety(outputs)
    print(f"Unique chapter titles: {analysis['unique_titles']} / {analysis['total_titles']}")

    if analysis['repeated_titles']:
        print(f"\n⚠️  REPEATED TITLES (appear in multiple runs):")
        for title, count in analysis['repeated_titles'].items():
            print(f"  - '{title}' ({count}x)")
    else:
        print("\n✅ No repeated chapter titles across runs")

    print(f"\nPhrase usage across all 3 outputs:")
    for phrase, count in sorted(analysis['phrase_counts'].items(), key=lambda x: -x[1]):
        indicator = "⚠️" if count >= 3 else "  "
        print(f"  {indicator} '{phrase}': {count}x")

    # Test 2: Compare Session 1 vs Session 2
    print("\n" + "=" * 70)
    print("TEST 2: CROSS-SESSION CHECK - Different data, different output?")
    print("=" * 70)

    session1_id = sessions[0]['id']  # Session 1
    data1 = get_session_data(conn, session1_id)
    print(f"\nSession 1: {data1['briefing']['identity']['empire_name']}")
    print(f"Events: {len(data1['events'])}, Range: {data1['first_date']} → {data1['last_date']}")

    prompt1 = build_prompt(data1)
    output1 = call_gemini(prompt1)

    titles1 = extract_chapter_titles(output1)
    print(f"\nSession 1 Chapter Titles:")
    for t in titles1:
        print(f"  - {t}")

    Path(__file__).parent.joinpath("variety_session1.txt").write_text(output1)

    # Compare titles
    print("\n" + "-" * 40)
    print("CROSS-SESSION COMPARISON")
    print("-" * 40)

    session2_titles = set()
    for output in outputs:
        session2_titles.update(extract_chapter_titles(output))

    session1_titles = set(titles1)

    overlap = session1_titles.intersection(session2_titles)
    if overlap:
        print(f"⚠️  OVERLAPPING TITLES between sessions:")
        for t in overlap:
            print(f"  - '{t}'")
    else:
        print("✅ No overlapping chapter titles between sessions")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"""
Files saved:
  - scripts/variety_session2_run1.txt
  - scripts/variety_session2_run2.txt
  - scripts/variety_session2_run3.txt
  - scripts/variety_session1.txt

Key Findings:
  - Unique titles in Session 2 (3 runs): {analysis['unique_titles']}/{analysis['total_titles']}
  - Repeated titles: {len(analysis['repeated_titles'])}
  - Cross-session title overlap: {len(overlap)}
  - Phrases used 3+ times: {len([p for p,c in analysis['phrase_counts'].items() if c >= 3])}
""")

    conn.close()


if __name__ == '__main__':
    main()
