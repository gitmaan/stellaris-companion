"""The identity name catalog is generated from game files and ships with the package."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.generate_identity_catalog import build_catalog, parse_definitions, resolve_name
from stellaris_companion.campaign_evidence import (
    IDENTITY_CATALOG_GAME_VERSION,
    IDENTITY_CATALOG_PATH,
    _load_identity_catalog,
    resolve_empire_identity,
)
from stellaris_companion.game_install import find_game_install

ROOT = Path(__file__).resolve().parents[1]
INSTALL = find_game_install()
GAME_DIR = INSTALL.game_dir if INSTALL else Path("no Stellaris install")

# The hand-maintained catalog shipped by PR #84, verified against 4.4.6 localisation.
LEGACY_NAMES = {
    "authority": {
        "democratic": "Democratic",
        "oligarchic": "Oligarchic",
        "dictatorial": "Dictatorial",
        "imperial": "Imperial",
        "corporate": "Corporate",
        "hive_mind": "Hive Mind",
        "machine_intelligence": "Machine Intelligence",
    },
    "civics": {
        "machine_servitor": "Rogue Servitor",
        "machine_terminator": "Determined Exterminator",
        "machine_assimilator": "Driven Assimilator",
        "machine_replication": "Rapid Replicator",
        "machine_builder": "Constructobot",
        "machine_warbots": "Warbots",
        "machine_maintenance_protocols": "Maintenance Protocols",
        "hive_devouring_swarm": "Devouring Swarm",
        "hive_devouring_swarm_lithoid": "Terravore",
        "hive_ascetic": "Ascetic",
        "hive_one_mind": "One Mind",
        "hive_subspace_ephapse": "Subspace Ephapse",
        "meritocracy": "Meritocracy",
        "citizen_service": "Citizen Service",
        "technocracy": "Technocracy",
        "inwards_perfection": "Inward Perfection",
        "fanatic_purifiers": "Fanatic Purifiers",
    },
    "ethics": {
        "authoritarian": "Authoritarian",
        "fanatic_authoritarian": "Fanatic Authoritarian",
        "egalitarian": "Egalitarian",
        "fanatic_egalitarian": "Fanatic Egalitarian",
        "xenophobe": "Xenophobe",
        "fanatic_xenophobe": "Fanatic Xenophobe",
        "xenophile": "Xenophile",
        "fanatic_xenophile": "Fanatic Xenophile",
        "militarist": "Militarist",
        "fanatic_militarist": "Fanatic Militarist",
        "pacifist": "Pacifist",
        "fanatic_pacifist": "Fanatic Pacifist",
        "spiritualist": "Spiritualist",
        "fanatic_spiritualist": "Fanatic Spiritualist",
        "materialist": "Materialist",
        "fanatic_materialist": "Fanatic Materialist",
        "gestalt_consciousness": "Gestalt Consciousness",
    },
    "origin": {"default": "Prosperous Unification", "remnants": "Remnants"},
}
_SINGLE = {"authority", "origin"}


def _resolve_one(field: str, identifier: str) -> dict:
    value = identifier if field in _SINGLE else [identifier]
    result = resolve_empire_identity({field: value})[field]
    return result if field in _SINGLE else result[0]


@pytest.mark.parametrize(
    ("field", "identifier", "name"),
    [
        (field, identifier, name)
        for field, names in LEGACY_NAMES.items()
        for identifier, name in names.items()
    ],
)
def test_generated_catalog_keeps_every_legacy_name(field, identifier, name) -> None:
    resolved = _resolve_one(field, identifier)
    assert resolved["id"] == identifier
    assert resolved["name"] == name
    assert resolved["source"] == "verified_catalog"


@pytest.mark.parametrize(
    ("field", "identifier", "canonical", "name"),
    [
        ("civics", "machine_servitor", "machine_servitor", "Rogue Servitor"),
        ("civics", "civic_machine_servitor", "machine_servitor", "Rogue Servitor"),
        # Previously unmapped civics, including Nomad-pack and special entries.
        ("civics", "civic_caravan_masters", "caravan_masters", "Caravan Masters"),
        ("civics", "civic_void_reavers", "void_reavers", "Void Reavers"),
        ("civics", "machine_ota_updates", "machine_ota_updates", "OTA Updates"),
        ("civics", "civic_corporate_hedonism", "corporate_hedonism", "Corporate Hedonism"),
        ("civics", "civic_corvee_system", "corvee_system", "Corvée System"),
        # $civic_machine_warbots$ reference in localisation.
        ("civics", "civic_individual_machine_warbots", "individual_machine_warbots", "Warbots"),
        # Previously unmapped origins, playable and non-playable.
        ("origin", "origin_default_nomads", "default_nomads", "Voidfarers"),
        ("origin", "nomadic_purger", "nomadic_purger", "Planetary Purgers"),
        ("origin", "origin_shattered_ring", "shattered_ring", "Shattered Ring"),
        ("origin", "origin_fallen_empire", "fallen_empire", "Elder Race"),
        ("origin", "origin_mechanists", "mechanists", "Mechanist"),
        (
            "authority",
            "auth_ancient_machine_intelligence",
            "ancient_machine_intelligence",
            "Ancient Machine Intelligence",
        ),
    ],
)
def test_generated_catalog_names_previously_unmapped_ids(
    field, identifier, canonical, name
) -> None:
    resolved = _resolve_one(field, identifier)
    assert resolved == {
        "id": canonical,
        "name": name,
        "kind": "civic" if field == "civics" else "ethic" if field == "ethics" else field,
        "source": "verified_catalog",
    }


@pytest.mark.parametrize(
    ("field", "identifier", "canonical"),
    [
        ("civics", "civic_cygnus_future_civic", "cygnus_future_civic"),
        ("civics", "my_mod_civic", "my_mod_civic"),
        ("origin", "origin_modded_start", "modded_start"),
        # Defined in 4.4.6 but with an empty English name; must not render blank.
        ("civics", "civic_caravaneer_caravansary", "caravaneer_caravansary"),
        # An origin ID is not a civic, and vice versa.
        ("civics", "origin_default_nomads", "origin_default_nomads"),
        ("origin", "civic_caravan_masters", "civic_caravan_masters"),
    ],
)
def test_unknown_ids_pass_through_as_raw_identifiers(field, identifier, canonical) -> None:
    resolved = _resolve_one(field, identifier)
    assert resolved["id"] == canonical
    assert resolved["name"] == canonical
    assert resolved["source"] == "raw_identifier"


def test_shipped_catalog_records_source_version_and_only_names() -> None:
    data = json.loads(IDENTITY_CATALOG_PATH.read_text(encoding="utf-8"))
    assert set(data) == {"game_version", "source", "authority", "civic", "ethic", "origin"}
    assert data["game_version"] == IDENTITY_CATALOG_GAME_VERSION
    assert IDENTITY_CATALOG_GAME_VERSION.startswith("Cygnus v4.5.3")
    prefixes = ("auth_", "civic_", "ethic_", "origin_")
    for kind, minimum in {"authority": 8, "civic": 250, "ethic": 17, "origin": 60}.items():
        names = data[kind]
        assert len(names) >= minimum
        for identifier, name in names.items():
            assert not identifier.startswith(prefixes)
            assert isinstance(name, str) and name.strip() == name and name
            assert not any(code in name for code in ("$", "§", "£", "["))


def test_catalog_loads_without_game_install(tmp_path) -> None:
    script = (
        "from stellaris_companion.campaign_evidence import resolve_empire_identity as r;"
        "print(r({'civics': ['civic_machine_servitor']})['civics'][0]['name'])"
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
    assert result.stdout.strip() == "Rogue Servitor"


def test_unreadable_catalog_degrades_to_raw_identifiers(tmp_path) -> None:
    version, names = _load_identity_catalog(tmp_path / "missing.json")
    assert version is None
    assert names == {"authority": {}, "civic": {}, "ethic": {}, "origin": {}}
    broken = tmp_path / "broken.json"
    broken.write_text('{"game_version": "x", "civic": []}', encoding="utf-8")
    assert _load_identity_catalog(broken)[1]["civic"] == {}


def test_pyinstaller_spec_and_package_data_ship_the_catalog() -> None:
    spec = (ROOT / "stellaris-backend.spec").read_text(encoding="utf-8")
    assert "('stellaris_companion', 'stellaris_companion')" in spec
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"identity_catalog.json"' in pyproject
    assert IDENTITY_CATALOG_PATH.parent == ROOT / "stellaris_companion"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig")


def test_generator_reads_definitions_and_cleans_localisation(tmp_path) -> None:
    _write(tmp_path / "launcher-settings.json", json.dumps({"version": "Test v9.9.9"}))
    common = tmp_path / "common"
    _write(
        common / "governments/authorities/00_authorities.txt",
        "@cost = 2\nauth_test = { has_heir = no }\n",
    )
    _write(
        common / "governments/civics/00_civics.txt",
        "# civic_commented_out = { }\n"
        "civic_alpha = {\n"
        '\tdescription = "civic_tooltip_alpha" # name = civic_not_a_swap\n'
        "\tswap_type = { name = civic_alpha_variant trigger = { is_x = yes } }\n"
        "\tmodifier = { name = ignored_nested }\n"
        "}\n"
        "civic_ref = { }\n"
        "civic_unnamed = { }\n"
        "civic_dup = { }\n",
    )
    _write(
        common / "governments/civics/00_origins.txt",
        "origin_beta = {\n\tis_origin = yes\n}\n",
    )
    _write(common / "ethics/00_ethics.txt", 'ethic_gamma = { category = "col" }\n')
    _write(
        tmp_path / "localisation/english/a_l_english.yml",
        "l_english:\n"
        ' auth_test:0 "§YTest§! Authority"\n'
        ' civic_alpha:0 "£unity£ Alpha"  # comment\n'
        ' civic_alpha_variant: "Alpha Variant"\n'
        ' civic_ref:0 "$civic_alpha$ Prime"\n'
        ' origin_beta:0 "Beta"\n'
        ' ethic_gamma:0 "Gamma"\n',
    )
    _write(
        tmp_path / "localisation/english/b_l_english.yml",
        'l_english:\n civic_dup:0 "First"\n origin_beta:0 "Beta"\n',
    )
    _write(
        tmp_path / "localisation/english/c_l_english.yml",
        'l_english:\n civic_dup:0 "Second"\n',
    )
    catalog, skipped = build_catalog(tmp_path)
    assert catalog["game_version"] == "Test v9.9.9"
    assert catalog["authority"] == {"test": "Test Authority"}
    assert catalog["civic"] == {
        "alpha": "Alpha",
        "alpha_variant": "Alpha Variant",
        "ref": "Alpha Prime",
    }
    assert catalog["origin"] == {"beta": "Beta"}
    assert catalog["ethic"] == {"gamma": "Gamma"}
    assert skipped == [
        "civic:civic_unnamed (no English name)",
        "civic:civic_dup (conflicting English names)",
    ]


def test_generator_rejects_reference_cycles_and_unbalanced_files() -> None:
    with pytest.raises(ValueError):
        resolve_name("a", {"a": "$b$", "b": "$a$"})
    with pytest.raises(ValueError):
        parse_definitions("civic_x = { ")


@pytest.mark.skipif(not (GAME_DIR / "localisation").is_dir(), reason="Stellaris not installed")
def test_committed_catalog_matches_installed_game_when_same_version() -> None:
    catalog, _ = build_catalog(GAME_DIR)
    if catalog["game_version"] != IDENTITY_CATALOG_GAME_VERSION:
        pytest.skip(f"installed {catalog['game_version']} differs from committed catalog")
    committed = json.loads(IDENTITY_CATALOG_PATH.read_text(encoding="utf-8"))
    assert catalog == committed
