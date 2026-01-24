import sys
import unittest
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from save_extractor import SaveExtractor


class TestPhase4CompleteBriefingExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.extractor = SaveExtractor("test_save.sav")

    def test_complete_briefing_schema_and_no_truncation_invariants(self) -> None:
        briefing = self.extractor.get_complete_briefing()
        self.assertIsInstance(briefing, dict)

        for key in [
            "meta",
            "identity",
            "situation",
            "military",
            "economy",
            "territory",
            "diplomacy",
            "defense",
            "leadership",
            "technology",
            "fallen_empires",
        ]:
            self.assertIn(key, briefing)

        meta = briefing["meta"]
        self.assertIsInstance(meta, dict)
        self.assertIsInstance(meta.get("empire_name"), str)
        self.assertGreater(len(meta.get("empire_name", "")), 0)
        self.assertIsInstance(meta.get("date"), str)
        self.assertGreater(len(meta.get("date", "")), 0)

        leadership = briefing["leadership"]
        self.assertIsInstance(leadership, dict)
        self.assertIsInstance(leadership.get("leaders"), list)
        self.assertIsInstance(leadership.get("count"), int)
        self.assertEqual(leadership.get("count"), len(leadership.get("leaders", [])))

        planets = briefing["territory"].get("planets", {})
        self.assertIsInstance(planets, dict)
        self.assertIsInstance(planets.get("planets"), list)
        self.assertIsInstance(planets.get("count"), int)
        self.assertEqual(planets.get("count"), len(planets.get("planets", [])))

        diplomacy = briefing["diplomacy"]
        self.assertIsInstance(diplomacy, dict)
        self.assertIsInstance(diplomacy.get("relations"), list)
        self.assertIsInstance(diplomacy.get("relation_count"), int)
        self.assertEqual(diplomacy.get("relation_count"), len(diplomacy.get("relations", [])))

        defense = briefing["defense"]
        self.assertIsInstance(defense, dict)
        self.assertIsInstance(defense.get("starbases"), list)
        self.assertIsInstance(defense.get("count"), int)
        self.assertEqual(defense.get("count"), len(defense.get("starbases", [])))

        fleets = briefing["military"].get("fleets", {})
        self.assertIsInstance(fleets, dict)
        self.assertIsInstance(fleets.get("fleets"), list)
        self.assertIsInstance(fleets.get("military_fleet_count"), int)
        # Fleet list may exclude tiny/irrelevant fleets (e.g., power<=100), but should not be truncated.
        self.assertLessEqual(len(fleets.get("fleets", [])), fleets.get("military_fleet_count"))

        wars = briefing["military"].get("wars", {})
        self.assertIsInstance(wars, dict)
        self.assertIsInstance(wars.get("wars"), list)
        self.assertIsInstance(wars.get("active_war_count"), int)
        self.assertEqual(wars.get("active_war_count"), len(wars.get("wars", [])))

        fallen = briefing.get("fallen_empires", {})
        self.assertIsInstance(fallen, dict)
        self.assertIsInstance(fallen.get("fallen_empires"), list)
        self.assertIsInstance(fallen.get("total_count"), int)
        self.assertEqual(fallen.get("total_count"), len(fallen.get("fallen_empires", [])))


if __name__ == "__main__":
    unittest.main()
