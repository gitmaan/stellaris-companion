"""The player's resources are read as the save lists them, whatever they are.

Stockpiles and monthly income were kept only for eighteen named resources. The
game defines more (Trade, Nanites, Biomass, ...) and a mod can add its own, and
all of those were left out before the Advisor saw them.
"""

from __future__ import annotations

import zipfile

import pytest

GAMESTATE = """version="Cygnus v4.5.3"
date="2300.01.01"
player=
{
	{
		name="tester"
		country=0
	}
}
country=
{
	0=
	{
		type="default"
		budget=
		{
			current_month=
			{
				income=
				{
					country_base=
					{
						energy=20
						minerals=20
					}
					planet_jobs=
					{
						energy=30.5
						trade=12
						nanites=1
						giga_sr_negative_mass=0.25
					}
				}
				expenses=
				{
					ships=
					{
						energy=10
						trade=4
					}
				}
			}
		}
		modules=
		{
			standard_economy_module=
			{
				resources=
				{
					energy=1000
					trade=8717.42046
					nanites=3
					giga_sr_negative_mass=5.5
				}
			}
		}
	}
}
"""


@pytest.fixture(scope="module")
def resources(tmp_path_factory):
    rust_bridge = pytest.importorskip("stellaris_companion.rust_bridge")
    from stellaris_save_extractor import SaveExtractor

    path = tmp_path_factory.mktemp("save") / "resources.sav"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("gamestate", GAMESTATE.encode("utf-8"))
        archive.writestr("meta", b'version="Cygnus v4.5.3"\nname="tester"\n')
    with rust_bridge.session(path):
        yield SaveExtractor(str(path)).get_resources()


def test_every_stockpile_the_save_lists_is_kept(resources):
    assert resources["stockpiles"] == {
        "energy": 1000.0,
        "trade": 8717.42046,
        "nanites": 3.0,
        "giga_sr_negative_mass": 5.5,
    }


def test_income_and_expenses_cover_every_resource_in_the_budget(resources):
    assert resources["monthly_income"] == {
        "energy": 50.5,
        "minerals": 20.0,
        "trade": 12.0,
        "nanites": 1.0,
        "giga_sr_negative_mass": 0.25,
    }
    assert resources["monthly_expenses"] == {"energy": 10.0, "trade": 4.0}
    assert resources["net_monthly"] == {
        "energy": 40.5,
        "minerals": 20.0,
        "trade": 8.0,
        "nanites": 1.0,
        "giga_sr_negative_mass": 0.25,
    }


def test_the_named_summary_is_unchanged(resources):
    assert resources["summary"]["energy_net"] == 40.5
    assert resources["summary"]["minerals_net"] == 20.0
