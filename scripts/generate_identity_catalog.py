#!/usr/bin/env python3
"""Generate the empire identity name catalog from an installed Stellaris.

Reads the IDs that the game defines in ``common/governments/authorities``,
``common/governments/civics`` (civics and origins) and ``common/ethics``, then
looks up each ID's English display name in ``localisation/english``. The output
keeps only ID -> name strings plus the source game version, so no other
localisation text is redistributed.

Usage:
    python3 scripts/generate_identity_catalog.py \\
        --game-dir "~/Library/Application Support/Steam/steamapps/common/Stellaris" \\
        --output stellaris_companion/identity_catalog.json

Every defined entry is included, playable or not (fallen empire, enclave,
nomadic and pre-FTL civics/origins appear in saves too). ``swap_type`` display
variants (e.g. the lithoid Devouring Swarm "Terravore") are added under their
own name keys. IDs whose name cannot be resolved are reported and omitted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path

KINDS = ("authority", "civic", "ethic", "origin")
PREFIXES = {"authority": "auth_", "civic": "civic_", "ethic": "ethic_", "origin": "origin_"}

_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|[{}]|[<>!]?=|[<>]|[^\s{}=<>!"#]+')
_LOC_LINE = re.compile(r'^\s*([A-Za-z0-9_.\-]+):\d*\s*"(.*)"\s*(?:#.*)?$')
_REFERENCE = re.compile(r"\$([A-Za-z0-9_.\-]+)(?:\|[^$]*)?\$")
_COLOR_START = re.compile(r"§.")
_ICON = re.compile(r"£[^£\s]+£")


def _tokens(text: str) -> Iterator[str]:
    for line in text.splitlines():
        code = _strip_comment(line)
        yield from _TOKEN.findall(code)


def _strip_comment(line: str) -> str:
    in_string = False
    for index, char in enumerate(line):
        if char == '"':
            in_string = not in_string
        elif char == "#" and not in_string:
            return line[:index]
    return line


def _unquote(token: str) -> str:
    return token[1:-1] if len(token) >= 2 and token[0] == token[-1] == '"' else token


def parse_definitions(text: str) -> list[dict]:
    """Return top-level ``key = { ... }`` entries with origin and swap-name facts."""
    tokens = list(_tokens(text))
    entries: list[dict] = []
    depth = 0
    current: dict | None = None
    in_swap_depth: int | None = None
    i = 0
    while i < len(tokens):
        token = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        after = tokens[i + 2] if i + 2 < len(tokens) else None
        if token == "{":
            depth += 1
        elif token == "}":
            if in_swap_depth is not None and depth == in_swap_depth:
                in_swap_depth = None
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced braces")
            if depth == 0:
                current = None
        elif nxt == "=":
            if depth == 0 and after == "{" and not token.startswith("@"):
                current = {"id": token, "is_origin": False, "swap_names": []}
                entries.append(current)
            elif depth == 1 and current is not None:
                if token == "is_origin" and after == "yes":
                    current["is_origin"] = True
                elif token == "swap_type" and after == "{":
                    in_swap_depth = 2
            elif (
                depth == 2
                and current is not None
                and in_swap_depth == 2
                and token == "name"
                and after not in (None, "{")
            ):
                current["swap_names"].append(_unquote(after))
        i += 1
    if depth != 0:
        raise ValueError("unbalanced braces")
    return entries


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def load_localisation(english_dir: Path) -> tuple[dict[str, str], set[str]]:
    """Load ``key:N "value"`` lines from every English .yml.

    Returns the values and the keys defined more than once with different text;
    callers skip those rather than guess which definition the game displays.
    """
    values: dict[str, str] = {}
    conflicts: set[str] = set()
    for path in sorted(english_dir.rglob("*.yml")):
        for line in read_text(path).splitlines():
            match = _LOC_LINE.match(line)
            if not match:
                continue
            key, value = match.groups()
            if values.setdefault(key, value) != value:
                conflicts.add(key)
    return values, conflicts


def resolve_name(key: str, localisation: dict[str, str], _seen: frozenset = frozenset()) -> str:
    """Resolve ``$key$`` references and strip colour/icon codes from a display name."""
    if key in _seen:
        raise ValueError(f"localisation reference cycle at {key}")
    if key not in localisation:
        raise KeyError(key)
    seen = _seen | {key}

    def substitute(match: re.Match[str]) -> str:
        return resolve_name(match.group(1), localisation, seen)

    value = _REFERENCE.sub(substitute, localisation[key])
    value = _ICON.sub("", value)
    value = value.replace("§!", "")
    value = _COLOR_START.sub("", value)
    value = value.replace('\\"', '"')
    return " ".join(value.split())


def read_game_version(game_dir: Path) -> str:
    settings = game_dir / "launcher-settings.json"
    try:
        version = json.loads(read_text(settings)).get("version")
    except (OSError, ValueError):
        version = None
    if not isinstance(version, str) or not version.strip():
        raise SystemExit(f"Could not read game version from {settings}")
    return version.strip()


def collect_ids(game_dir: Path) -> dict[str, list[str]]:
    common = game_dir / "common"
    sources = {
        "authority": sorted((common / "governments" / "authorities").glob("*.txt")),
        "civic": sorted((common / "governments" / "civics").glob("*.txt")),
        "ethic": sorted((common / "ethics").glob("*.txt")),
    }
    ids: dict[str, list[str]] = {kind: [] for kind in KINDS}
    for kind, paths in sources.items():
        if not paths:
            raise SystemExit(f"No definition files found for {kind} under {common}")
        for path in paths:
            for entry in parse_definitions(read_text(path)):
                target = kind
                if kind == "civic" and entry["is_origin"]:
                    target = "origin"
                for identifier in (entry["id"], *entry["swap_names"]):
                    if identifier not in ids[target]:
                        ids[target].append(identifier)
    return ids


def build_catalog(game_dir: Path) -> tuple[dict, list[str]]:
    localisation, conflicts = load_localisation(game_dir / "localisation" / "english")
    if not localisation:
        raise SystemExit(f"No English localisation found under {game_dir / 'localisation'}")
    ids = collect_ids(game_dir)
    catalog: dict = {
        "game_version": read_game_version(game_dir),
        "source": "Stellaris common/ definitions with localisation/english display names",
    }
    unresolved: list[str] = []
    for kind in KINDS:
        names: dict[str, str] = {}
        for identifier in ids[kind]:
            if not identifier.startswith(PREFIXES[kind]):
                unresolved.append(f"{kind}:{identifier} (unexpected prefix)")
                continue
            if identifier in conflicts:
                unresolved.append(f"{kind}:{identifier} (conflicting English names)")
                continue
            try:
                name = resolve_name(identifier, localisation)
            except KeyError:
                unresolved.append(f"{kind}:{identifier} (no English name)")
                continue
            if not name or "[" in name:
                unresolved.append(f"{kind}:{identifier} (dynamic or empty name {name!r})")
                continue
            names[identifier.removeprefix(PREFIXES[kind])] = name
        catalog[kind] = dict(sorted(names.items()))
    return catalog, unresolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--game-dir", required=True, type=Path, help="Stellaris install directory")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "stellaris_companion"
        / "identity_catalog.json",
    )
    args = parser.parse_args(argv)
    game_dir = args.game_dir.expanduser()
    catalog, unresolved = build_catalog(game_dir)
    args.output.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    counts = ", ".join(f"{kind}={len(catalog[kind])}" for kind in KINDS)
    print(f"Wrote {args.output} from {catalog['game_version']}: {counts}")
    for item in unresolved:
        print(f"  skipped {item}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
