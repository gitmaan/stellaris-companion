"""The technology name catalog is generated from game files and ships with the package."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.generate_identity_catalog import build_technology_catalog
from stellaris_companion.campaign_evidence import IDENTITY_CATALOG_GAME_VERSION
from stellaris_companion.technology_names import (
    TECHNOLOGY_CATALOG_GAME_VERSION,
    TECHNOLOGY_CATALOG_PATH,
    _load_technology_catalog,
    catalog_covers_game_version,
    technology_display_name,
    technology_label,
    technology_names_for,
    technology_variant_names,
)

ROOT = Path(__file__).resolve().parents[1]
GAME_DIR = Path(
    os.environ.get(
        "STELLARIS_GAME_DIR",
        Path.home() / "Library/Application Support/Steam/steamapps/common/Stellaris",
    )
)


@pytest.mark.parametrize(
    ("identifier", "name"),
    [
        # Issue #104: the ID says "cryostasis", the game says colony ships.
        ("tech_cryostasis_1", "Automated Colony Ships"),
        ("tech_cryostasis_2", "Self-Aware Colony Ships"),
        ("tech_colonization_1", "New Worlds Protocol"),
        ("tech_lasers_2", "Blue Lasers"),
    ],
)
def test_catalog_names_save_ids_as_the_game_shows_them(identifier, name) -> None:
    assert technology_display_name(identifier) == name
    assert technology_label(identifier) == name


def test_uncatalogued_ids_get_no_invented_name() -> None:
    # The ID guessed in issue #104 does not exist in the game.
    assert technology_display_name("tech_colonization_x") is None
    assert technology_display_name("tech_my_mod_reactor") is None
    assert technology_display_name(None) is None
    assert technology_label("tech_my_mod_reactor") == "My Mod Reactor"
    assert technology_names_for(
        ["tech_cryostasis_1", "tech_my_mod_reactor", None, "tech_cryostasis_1"]
    ) == {"tech_cryostasis_1": "Automated Colony Ships"}


def test_shipped_catalog_records_source_version_and_only_names() -> None:
    data = json.loads(TECHNOLOGY_CATALOG_PATH.read_text(encoding="utf-8"))
    assert set(data) == {"game_version", "source", "technology", "variants"}
    assert data["game_version"] == TECHNOLOGY_CATALOG_GAME_VERSION
    # Both catalogs come from one generator run.
    assert TECHNOLOGY_CATALOG_GAME_VERSION == IDENTITY_CATALOG_GAME_VERSION
    names = data["technology"]
    assert len(names) >= 600
    for identifier, name in names.items():
        assert isinstance(name, str) and name.strip() == name and name
        assert not any(code in name for code in ("$", "§", "£", "["))
    for identifier, variants in data["variants"].items():
        assert variants and names[identifier] not in variants
        assert all(isinstance(name, str) and name for name in variants)


def test_variants_list_the_other_names_an_empire_can_see() -> None:
    # Wilderness empires see Automated Colony Ships as Seedling Incubation.
    assert technology_variant_names("tech_cryostasis_1") == ("Seedling Incubation",)
    assert technology_display_name("tech_cryostasis_1_wilderness") == "Seedling Incubation"
    assert technology_variant_names("tech_my_mod_reactor") == ()
    assert technology_variant_names(None) == ()


@pytest.mark.parametrize(
    ("game", "catalog", "covered"),
    [
        ("Cygnus v4.5.3 (4e91)", "Cygnus v4.5.3 (4e91)", True),
        ("Pegasus v4.4.6", "Cygnus v4.5.3 (4e91)", True),
        ("Cygnus v4.5.4", "Cygnus v4.5.3 (4e91)", False),
        ("Next v5.0", "Cygnus v4.5.3 (4e91)", False),
        ("", "Cygnus v4.5.3 (4e91)", None),
        ("modded build", "Cygnus v4.5.3 (4e91)", None),
        ("Cygnus v4.5.3", None, None),
    ],
)
def test_catalog_coverage_compares_game_versions(game, catalog, covered) -> None:
    assert catalog_covers_game_version(game, catalog) is covered


def test_catalog_loads_without_game_install(tmp_path) -> None:
    script = (
        "from stellaris_companion.technology_names import technology_display_name as n;"
        "print(n('tech_cryostasis_1'))"
    )
    env = {**os.environ, "HOME": str(tmp_path), "STELLARIS_GAME_DIR": str(tmp_path / "none")}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "Automated Colony Ships"


def test_unreadable_catalog_degrades_to_no_names(tmp_path) -> None:
    assert _load_technology_catalog(tmp_path / "missing.json") == (None, {}, {})
    broken = tmp_path / "broken.json"
    broken.write_text('{"game_version": "x", "technology": []}', encoding="utf-8")
    assert _load_technology_catalog(broken) == (None, {}, {})
    # A catalog written before variants existed still loads.
    older = tmp_path / "older.json"
    older.write_text('{"game_version": "x", "technology": {"tech_a": "A"}}', encoding="utf-8")
    assert _load_technology_catalog(older) == ("x", {"tech_a": "A"}, {})


def test_package_data_ships_the_catalog() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"technology_catalog.json"' in pyproject
    assert TECHNOLOGY_CATALOG_PATH.parent == ROOT / "stellaris_companion"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig")


def test_generator_names_technologies_by_full_save_id(tmp_path) -> None:
    _write(tmp_path / "launcher-settings.json", json.dumps({"version": "Test v9.9.9"}))
    _write(
        tmp_path / "common/technology/00_phys_tech.txt",
        "@tier1cost1 = 100\n"
        "# tech_commented_out = { }\n"
        "tech_alpha = {\n"
        '\tprerequisites = { "tech_beta" }\n'
        "\ttechnology_swap = { name = tech_alpha_variant trigger = { is_x = yes } }\n"
        "}\n"
        "tech_ref = { }\n"
        "tech_unnamed = { }\n"
        "tech_dup = { }\n",
    )
    _write(tmp_path / "common/technology/00_soc_tech.txt", "tech_alpha = { }\ntech_beta = { }\n")
    _write(tmp_path / "common/technology/category/00_category.txt", "computing = { }\n")
    _write(
        tmp_path / "localisation/english/a_l_english.yml",
        "l_english:\n"
        ' tech_alpha:0 "§YAlpha§! Ships"\n'
        ' tech_alpha_variant:0 "Alpha Variant"\n'
        ' tech_alpha_desc:0 "Not a name."\n'
        ' tech_ref:0 "$tech_alpha$ II"\n'
        ' tech_beta:0 "Beta"\n'
        ' tech_dup:0 "First"\n'
        ' computing:0 "Computing"\n',
    )
    _write(
        tmp_path / "localisation/english/b_l_english.yml",
        'l_english:\n tech_dup:0 "Second"\n',
    )
    catalog, skipped = build_technology_catalog(tmp_path)
    assert catalog["game_version"] == "Test v9.9.9"
    assert catalog["technology"] == {
        "tech_alpha": "Alpha Ships",
        "tech_alpha_variant": "Alpha Variant",
        "tech_beta": "Beta",
        "tech_ref": "Alpha Ships II",
    }
    assert catalog["variants"] == {"tech_alpha": ["tech_alpha_variant"]}
    assert skipped == [
        "technology:tech_unnamed (no English name)",
        "technology:tech_dup (conflicting English names)",
    ]


@pytest.mark.skipif(not (GAME_DIR / "localisation").is_dir(), reason="Stellaris not installed")
def test_committed_catalog_matches_installed_game_when_same_version() -> None:
    catalog, _ = build_technology_catalog(GAME_DIR)
    if catalog["game_version"] != TECHNOLOGY_CATALOG_GAME_VERSION:
        pytest.skip(f"installed {catalog['game_version']} differs from committed catalog")
    committed = json.loads(TECHNOLOGY_CATALOG_PATH.read_text(encoding="utf-8"))
    assert catalog == committed
