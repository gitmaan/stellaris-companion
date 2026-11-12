from __future__ import annotations

import zipfile

import pytest


def _save(tmp_path, *, flags=()):
    """A minimal save with L-Gates enabled and a researched L-Cluster insight."""
    lines = ['version="Cygnus v4.5.3"', 'date="2400.01.01"']
    lines += ["player=", "{", "\t", "\t{", '\t\tname="tester"', "\t\tcountry=0", "\t}", "}"]
    lines += ["galaxy=", "{", "\tlgate_enabled=yes", "}"]
    lines += ["flags=", "{"] + [f"\t{flag}=62808000" for flag in flags] + ["}"]
    lines += ["country=", "{", "\t0=", "\t{", '\t\ttype="default"']
    lines += ["\t\ttech_status=", "\t\t{", '\t\t\ttechnology="tech_repeatable_lcluster_clue"']
    lines += ["\t\t\tlevel=3", "\t\t}", "\t}", "}", ""]
    path = tmp_path / "lgate.sav"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("gamestate", "\n".join(lines).encode("utf-8"))
        archive.writestr("meta", b'version="Cygnus v4.5.3"\nname="tester"\n')
    return path


@pytest.fixture
def lgate_status(tmp_path):
    rust_bridge = pytest.importorskip("stellaris_companion.rust_bridge")
    from stellaris_save_extractor import SaveExtractor

    def _read(**save):
        path = _save(tmp_path, **save)
        with rust_bridge.session(path):
            return SaveExtractor(str(path)).get_lgate_status()

    return _read


def test_repeatable_lcluster_technology_does_not_mean_lgate_opened(lgate_status) -> None:
    result = lgate_status()

    assert result["lgate_enabled"] is True
    assert result["insights_collected"] == 3
    assert result["lgate_opened"] is False


def test_explicit_lcluster_opened_flag_is_detected(lgate_status) -> None:
    assert lgate_status(flags=["l_cluster_opened"])["lgate_opened"] is True
