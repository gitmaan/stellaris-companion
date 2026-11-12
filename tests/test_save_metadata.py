"""A save's name, date and version are its own top-level lines.

Every line holding the word "flag" was skipped, to pass over the empire's flag
block, so an empire with "flag" in its name had no name in the metadata.
"""

from __future__ import annotations

import zipfile

from stellaris_save_extractor import SaveExtractor

META = """version="Cygnus v4.5.3"
version_control_revision=10
name="Flagellant Concord"
date="2215.01.01"
required_dlcs=
{
	"Federations"
	"Utopia"
}
player_portrait="mol7"
flag=
{
	icon=
	{
		category="pointy"
		file="flag_pointy_6.dds"
		name="not the empire"
	}
	colors=
	{
		"turquoise"
		"null"
	}
}
meta_fleets=100
ironman=yes
"""


def _metadata(tmp_path, meta: str) -> dict:
    path = tmp_path / "save.sav"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("meta", meta.encode("utf-8"))
        archive.writestr("gamestate", b"")
    return SaveExtractor(str(path)).get_metadata()


def test_an_empire_with_flag_in_its_name_keeps_its_name(tmp_path):
    metadata = _metadata(tmp_path, META)

    assert metadata["name"] == "Flagellant Concord"
    assert metadata["date"] == "2215.01.01"
    assert metadata["version"] == "Cygnus v4.5.3"
    assert metadata["required_dlcs"] == ["Federations", "Utopia"]


def test_windows_line_endings_are_read_the_same(tmp_path):
    metadata = _metadata(tmp_path, META.replace("\n", "\r\n"))

    assert metadata["name"] == "Flagellant Concord"
    assert metadata["date"] == "2215.01.01"
