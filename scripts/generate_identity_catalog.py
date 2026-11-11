#!/usr/bin/env python3
"""Generate the identity and technology name catalogs from an installed Stellaris.

Reads the IDs that the game defines in ``common/governments/authorities``,
``common/governments/civics`` (civics and origins), ``common/ethics`` and
``common/technology``, then looks up each ID's English display name in
``localisation/english``. The outputs keep only ID -> name strings plus the
source game version, so no other localisation text is redistributed.

Usage:
    python3 scripts/generate_identity_catalog.py \\
        --game-dir "~/Library/Application Support/Steam/steamapps/common/Stellaris"

Both catalogs are written from the same install so their versions stay in step:
``stellaris_companion/identity_catalog.json`` and
``stellaris_companion/technology_catalog.json``.

Every defined entry is included, playable or not (fallen empire, enclave,
nomadic and pre-FTL civics/origins appear in saves too). ``swap_type`` display
variants (e.g. the lithoid Devouring Swarm "Terravore") are added under their
own name keys. IDs whose name cannot be resolved are reported and omitted.

Technologies keep their full save ID (``tech_cryostasis_1``) as the key because
that is what a save's research lists contain. Some empires see a technology
under a ``technology_swap`` name instead (Wilderness, Nomads, ...). Which one the
UI shows depends on game script, so the catalog does not decide: ``variants``
lists the swap IDs whose name differs from the technology's own, and each swap ID
is named under its own key.
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
                elif token in ("swap_type", "technology_swap") and after == "{":
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


def _load_english(game_dir: Path) -> tuple[dict[str, str], set[str]]:
    localisation, conflicts = load_localisation(game_dir / "localisation" / "english")
    if not localisation:
        raise SystemExit(f"No English localisation found under {game_dir / 'localisation'}")
    return localisation, conflicts


def collect_technology_ids(game_dir: Path) -> list[str]:
    paths = sorted((game_dir / "common" / "technology").glob("*.txt"))
    if not paths:
        raise SystemExit(f"No technology definition files found under {game_dir / 'common'}")
    ids: list[str] = []
    seen: set[str] = set()
    for path in paths:
        for entry in parse_definitions(read_text(path)):
            if entry["id"] not in seen:
                seen.add(entry["id"])
                ids.append(entry["id"])
    return ids


def _resolved(identifier: str, localisation: dict[str, str], conflicts: set[str]) -> str:
    """Return the display name, or raise ``LookupError`` with the reason it is unusable."""
    if identifier in conflicts:
        raise LookupError("conflicting English names")
    try:
        name = resolve_name(identifier, localisation)
    except KeyError:
        raise LookupError("no English name") from None
    if not name or "[" in name:
        raise LookupError(f"dynamic or empty name {name!r}")
    return name


def collect_technologies(game_dir: Path) -> dict[str, list[str]]:
    """Return ``{technology ID: [technology_swap IDs]}`` in definition order."""
    paths = sorted((game_dir / "common" / "technology").glob("*.txt"))
    if not paths:
        raise SystemExit(f"No technology definition files found under {game_dir / 'common'}")
    technologies: dict[str, list[str]] = {}
    for path in paths:
        for entry in parse_definitions(read_text(path)):
            swaps = technologies.setdefault(entry["id"], [])
            swaps.extend(name for name in entry["swap_names"] if name not in swaps)
    return technologies


def build_technology_catalog(
    game_dir: Path, english: tuple[dict[str, str], set[str]] | None = None
) -> tuple[dict, list[str]]:
    """Return technology names, their differently named swap IDs, and the IDs left out."""
    localisation, conflicts = english or _load_english(game_dir)
    names: dict[str, str] = {}
    variants: dict[str, list[str]] = {}
    unresolved: list[str] = []
    for identifier, swaps in collect_technologies(game_dir).items():
        try:
            names[identifier] = _resolved(identifier, localisation, conflicts)
        except LookupError as reason:
            unresolved.append(f"technology:{identifier} ({reason})")
            continue
        for swap in swaps:
            try:
                swap_name = _resolved(swap, localisation, conflicts)
            except LookupError:
                continue  # A swap without its own text shows the base name.
            names.setdefault(swap, swap_name)
            if swap_name != names[identifier] and swap not in variants.get(identifier, []):
                variants.setdefault(identifier, []).append(swap)
    catalog = {
        "game_version": read_game_version(game_dir),
        "source": "Stellaris common/technology definitions with localisation/english display names",
        "technology": dict(sorted(names.items())),
        "variants": dict(sorted(variants.items())),
    }
    return catalog, unresolved


def build_catalog(
    game_dir: Path, english: tuple[dict[str, str], set[str]] | None = None
) -> tuple[dict, list[str]]:
    localisation, conflicts = english or _load_english(game_dir)
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


def _write_catalog(path: Path, catalog: dict) -> None:
    path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--game-dir", required=True, type=Path, help="Stellaris install directory")
    package = Path(__file__).resolve().parents[1] / "stellaris_companion"
    parser.add_argument("--output", type=Path, default=package / "identity_catalog.json")
    parser.add_argument(
        "--technology-output", type=Path, default=package / "technology_catalog.json"
    )
    args = parser.parse_args(argv)
    game_dir = args.game_dir.expanduser()
    english = _load_english(game_dir)
    catalog, unresolved = build_catalog(game_dir, english)
    technology, technology_unresolved = build_technology_catalog(game_dir, english)
    _write_catalog(args.output, catalog)
    _write_catalog(args.technology_output, technology)
    counts = ", ".join(f"{kind}={len(catalog[kind])}" for kind in KINDS)
    print(f"Wrote {args.output} from {catalog['game_version']}: {counts}")
    print(
        f"Wrote {args.technology_output} from {technology['game_version']}: "
        f"technology={len(technology['technology'])}, "
        f"with variants={len(technology['variants'])}"
    )
    for item in (*unresolved, *technology_unresolved):
        print(f"  skipped {item}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
