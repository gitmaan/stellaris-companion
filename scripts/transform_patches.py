#!/usr/bin/env python3
"""
Fetch and LLM-transform Stellaris patch notes.
One-time script to populate patches/*.md files.
"""

import os
import re
import sys
import time
from pathlib import Path

import requests
from google import genai
from google.genai import types

PATCHES_DIR = Path(__file__).parent.parent / "patches"

# LLM transformation prompt
TRANSFORM_PROMPT = """Convert these Stellaris patch notes into present-tense FACTS about game mechanics.

RULES:
1. Remove ALL change-oriented language:
   - "no longer" → state what it DOESN'T do
   - "now provides" → just state what it provides
   - "reduced from X to Y" → just state the current value Y
   - "increased/decreased by" → state the current state
   - "has been changed to" → just state what it is

2. Write as if these mechanics have ALWAYS been this way

3. Keep specific numbers (percentages, values, costs)

4. Add brief strategic implication in parentheses where helpful

5. Format as clean markdown with headers and bullet points

6. Skip: bug fixes, UI changes, tooltip fixes, crash fixes, AI improvements, modding changes

7. Focus on: balance changes, mechanic changes, origin/civic changes, building/job changes

8. Group related items under clear headers (e.g., "### Population System", "### Origins & Civics")

EXAMPLE INPUT:
"Ecumenopolises no longer provide pop growth bonuses. Gaia Worlds now provide +15% pop growth (was 10%)."

EXAMPLE OUTPUT:
### Population System
* **Ecumenopolises:** No pop growth bonus; strength is production density and job capacity (optimal for industrial specialization, not population farming)
* **Gaia Worlds:** +15% pop growth, 100% habitability for all species (optimal for population farming and high-stability colonies)

NOW TRANSFORM THESE PATCH NOTES:

"""


def strip_bbcode(text: str) -> str:
    """Remove BBCode tags from text."""
    return re.sub(r"\[.*?\]", "", text)


def extract_balance_section(content: str) -> str:
    """Extract relevant sections from patch notes."""
    clean = strip_bbcode(content)

    # Try to find Balance section
    sections = []

    # Look for various section patterns
    patterns = [
        (
            r"Balance\s*(.*?)(?=Bugfix|Bug\s*fix|Performance|Stability|AI\b(?!\s*\w)|UI\b|Modding|$)",
            "Balance",
        ),
        (r"Features?\s*(.*?)(?=Balance|Bugfix|Bug\s*fix|$)", "Features"),
        (r"Gameplay\s*(.*?)(?=Balance|Bugfix|Bug\s*fix|$)", "Gameplay"),
    ]

    for pattern, name in patterns:
        match = re.search(pattern, clean, re.IGNORECASE | re.DOTALL)
        if match:
            section = match.group(1).strip()
            if section and len(section) > 100:
                sections.append(section)

    return "\n\n".join(sections) if sections else clean[:15000]


def fetch_patch_notes() -> dict:
    """Fetch patch notes from Steam API."""
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=281990&count=200&maxlength=50000"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def find_patch_content(items: list, search_terms: list) -> tuple[str, str]:
    """Find patch content matching search terms."""
    for item in items:
        title = item.get("title", "")
        for term in search_terms:
            if term in title:
                return title, item.get("contents", "")
    return "", ""


def transform_with_llm(content: str, client: genai.Client, version: str) -> str:
    """Transform patch notes using LLM."""
    print(f"  Transforming {version} with LLM ({len(content)} chars input)...")

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=TRANSFORM_PROMPT + content,
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=4000,
        ),
    )

    result = response.text or ""
    print(f"  Got {len(result)} chars output")
    return result


def main():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    print("Fetching patch notes from Steam API...")
    data = fetch_patch_notes()
    items = data.get("appnews", {}).get("newsitems", [])
    print(f"Found {len(items)} news items")

    # Define which patches to process
    patches = {
        "4.0": {
            "search": ["Dev Diary #383", "Dev Diary #374"],  # Main 4.0 release notes
            "codename": "Phoenix",
        },
        "4.1": {
            "search": ["Dev Diary #396", "4.1 'Lyra'"],
            "codename": "Lyra",
        },
        "4.2": {
            "search": ["Dev Diary #405", "Corvus"],  # 4.2 Corvus
            "codename": "Corvus",
        },
    }

    PATCHES_DIR.mkdir(exist_ok=True)

    for version, config in patches.items():
        print(f"\n{'=' * 60}")
        print(f'Processing {version} "{config["codename"]}"')
        print("=" * 60)

        # Find the patch content
        title, content = find_patch_content(items, config["search"])
        if not content:
            print(f"  WARNING: Could not find patch notes for {version}")
            continue

        print(f"  Found: {title}")
        print(f"  Raw content: {len(content)} chars")

        # Extract balance section
        balance = extract_balance_section(content)
        print(f"  Balance section: {len(balance)} chars")

        # Transform with LLM
        transformed = transform_with_llm(balance, client, version)

        # Add header
        header = f"""# Stellaris {version} "{config["codename"]}" Game Mechanics

<!-- LLM-transformed from official patch notes. Strategic implications included. -->

"""

        final_content = header + transformed

        # Save to file
        output_file = PATCHES_DIR / f"{version}.md"
        output_file.write_text(final_content, encoding="utf-8")
        print(f"  Saved to {output_file}")

        # Rate limit
        time.sleep(1)

    print("\n" + "=" * 60)
    print("DONE! Patch files updated.")
    print("=" * 60)


if __name__ == "__main__":
    main()
