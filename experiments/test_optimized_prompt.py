#!/usr/bin/env python3
"""
Quick test of the optimized prompt for qualitative review.
Outputs full responses to an MD file for human evaluation.
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import sys
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from google import genai
from google.genai import types
from save_extractor import SaveExtractor
from personality import build_optimized_prompt

MODEL = "gemini-3-flash-preview"

# Empire name resolution
EMPIRE_LOC_KEYS = {
    'EMPIRE_DESIGN_orbis': 'United Nations of Earth',
    'EMPIRE_DESIGN_humans1': 'Commonwealth of Man',
    'PRESCRIPTED_empire_name_orbis': 'United Nations of Earth',
}


def find_save_file() -> Path:
    """Find the most recent Stellaris save file."""
    save_dirs = [
        Path.home() / "Library/Application Support/Steam/steamapps/compatdata/281990/pfx/drive_c/users/steamuser/Documents/Paradox Interactive/Stellaris/save games",
        Path.home() / "Documents/Paradox Interactive/Stellaris/save games",
        Path.home() / ".local/share/Paradox Interactive/Stellaris/save games",
    ]

    for save_dir in save_dirs:
        if save_dir.exists():
            sav_files = list(save_dir.rglob("*.sav"))
            if sav_files:
                return max(sav_files, key=lambda p: p.stat().st_mtime)

    raise FileNotFoundError("No Stellaris save files found")


def get_empire_name_by_id(extractor, empire_id: int) -> str:
    """Resolve empire ID to name."""
    gamestate = extractor.gamestate
    country_match = re.search(r'^country=\s*\{', gamestate, re.MULTILINE)
    if not country_match:
        return f"Empire {empire_id}"
    start = country_match.start()
    pattern = rf'\n\t{empire_id}=\s*\{{'
    id_match = re.search(pattern, gamestate[start:start + 10000000])
    if not id_match:
        return f"Empire {empire_id}"
    chunk_start = start + id_match.start()
    chunk = gamestate[chunk_start:chunk_start + 8000]
    name_match = re.search(r'name=\s*\{[^}]*key=\"([^\"]+)\"', chunk)
    if not name_match:
        return f"Empire {empire_id}"
    name_key = name_match.group(1)
    if name_key in EMPIRE_LOC_KEYS:
        return EMPIRE_LOC_KEYS[name_key]
    clean_name = name_key.replace('EMPIRE_DESIGN_', '').replace('PRESCRIPTED_', '').replace('_', ' ').title()
    return clean_name if clean_name else f"Empire {empire_id}"


def build_comprehensive_snapshot(extractor) -> dict:
    """Build comprehensive snapshot with resolved names."""
    snapshot = extractor.get_full_briefing()
    all_leaders = extractor.get_leaders()
    snapshot['leadership']['leaders'] = all_leaders.get('leaders', [])
    snapshot['leadership']['count'] = len(all_leaders.get('leaders', []))
    detailed_diplo = extractor.get_diplomacy()
    relations = []
    for r in detailed_diplo.get('relations', [])[:20]:
        cid = r.get('country_id')
        if cid is not None:
            r['empire_name'] = get_empire_name_by_id(extractor, cid)
        relations.append(r)
    snapshot['diplomacy']['relations'] = relations
    snapshot['diplomacy']['allies_named'] = [
        {'id': aid, 'name': get_empire_name_by_id(extractor, aid)}
        for aid in snapshot['diplomacy'].get('allies', [])
    ]
    tech = extractor.get_technology()
    snapshot['current_research'] = tech.get('current_research', {}) or "None - research slots are idle"
    return snapshot


def format_snapshot(snapshot: dict) -> str:
    """Format snapshot for injection."""
    return json.dumps(snapshot, indent=2, default=str)


def run_test():
    """Run the optimized prompt test."""

    # Find and parse save
    save_path = find_save_file()
    print(f"Using save: {save_path.name}")

    extractor = SaveExtractor(str(save_path))
    snapshot = build_comprehensive_snapshot(extractor)

    # Get identity and situation directly from extractor
    identity = extractor.get_empire_identity()
    situation = extractor.get_situation()

    print(f"Empire: {identity.get('empire_name')}")
    print(f"Ethics: {identity.get('ethics')}")
    print(f"Authority: {identity.get('authority')}")

    # Build the optimized prompt
    system_prompt = build_optimized_prompt(identity, situation)
    print(f"\nPrompt size: {len(system_prompt)} chars")
    print("\n--- SYSTEM PROMPT ---")
    print(system_prompt)
    print("--- END PROMPT ---\n")

    # Format snapshot for injection
    snapshot_text = format_snapshot(snapshot)

    # Initialize Gemini
    client = genai.Client()

    # Test questions - mix of specific and broad
    questions = [
        "What's the state of my empire?",  # Broad strategic
        "Who should I be worried about?",   # Diplomatic/threat assessment
        "What should I focus on next?",     # Strategic advice
    ]

    results = []

    for q in questions:
        print(f"Q: {q}")

        # Inject snapshot into user message
        user_message = f"""CURRENT GAME STATE:
{snapshot_text}

QUESTION: {q}"""

        start = time.time()
        response = client.models.generate_content(
            model=MODEL,
            contents=[user_message],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.8,
            )
        )
        elapsed = time.time() - start

        text = response.text if response.text else "[No response]"
        word_count = len(text.split())

        print(f"   {elapsed:.1f}s, {word_count} words")

        results.append({
            'question': q,
            'response': text,
            'time': elapsed,
            'words': word_count,
        })

    # Write results to MD file
    output = f"""# Optimized Prompt Test Results

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

**Empire:** {identity.get('empire_name')}

**Ethics:** {', '.join(identity.get('ethics', []))}

**Authority:** {identity.get('authority')}

**Civics:** {', '.join(identity.get('civics', []))}

---

## System Prompt ({len(system_prompt)} chars)

```
{system_prompt}
```

---

## Responses

"""

    for r in results:
        output += f"""### Q: {r['question']}

*{r['time']:.1f}s | {r['words']} words*

{r['response']}

---

"""

    output_path = Path("OPTIMIZED_PROMPT_TEST.md")
    output_path.write_text(output)
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    run_test()
