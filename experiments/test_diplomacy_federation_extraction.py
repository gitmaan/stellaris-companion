import sys
import unittest
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from save_extractor import SaveExtractor


class TestDiplomacyFederationExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.extractor = SaveExtractor("test_save.sav")

    def test_get_federation_details_schema_and_invariants(self) -> None:
        data = self.extractor.get_federation_details()

        self.assertIsInstance(data, dict)
        for key in [
            "federation_id",
            "type",
            "level",
            "cohesion",
            "experience",
            "laws",
            "members",
            "president",
        ]:
            self.assertIn(key, data)

        self.assertIsInstance(data["laws"], dict)
        self.assertIsInstance(data["members"], list)

        self.assertIsInstance(data["federation_id"], int)
        self.assertGreaterEqual(data["federation_id"], 0)

        self.assertIsInstance(data["type"], str)
        self.assertGreater(len(data["type"]), 0)

        self.assertIsInstance(data["level"], int)
        self.assertGreaterEqual(data["level"], 1)

        self.assertIsInstance(data["cohesion"], (int, float))
        self.assertGreaterEqual(float(data["cohesion"]), 0.0)

        self.assertIsInstance(data["experience"], (int, float))
        self.assertGreaterEqual(float(data["experience"]), 0.0)

        self.assertIsInstance(data["president"], int)
        self.assertGreaterEqual(data["president"], 0)

        self.assertGreaterEqual(len(data["members"]), 1)
        self.assertIn(0, data["members"])  # player is a member in test_save.sav
        for cid in data["members"]:
            self.assertIsInstance(cid, int)
            self.assertGreaterEqual(cid, 0)

        for k, v in data["laws"].items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, str)

    def test_get_diplomacy_includes_treaty_types(self) -> None:
        data = self.extractor.get_diplomacy()

        self.assertIsInstance(data, dict)
        for key in [
            "relations",
            "treaties",
            "allies",
            "rivals",
            "federation",
            "defensive_pacts",
            "non_aggression_pacts",
            "closed_borders",
            "migration_treaties",
            "commercial_pacts",
            "sensor_links",
            "relation_count",
            "summary",
        ]:
            self.assertIn(key, data)

        self.assertIsInstance(data["relations"], list)
        self.assertIsInstance(data["treaties"], list)
        self.assertIsInstance(data["allies"], list)
        self.assertIsInstance(data["rivals"], list)

        self.assertIsInstance(data["defensive_pacts"], list)
        self.assertIsInstance(data["non_aggression_pacts"], list)
        self.assertIsInstance(data["closed_borders"], list)
        self.assertIsInstance(data["migration_treaties"], list)
        self.assertIsInstance(data["commercial_pacts"], list)
        self.assertIsInstance(data["sensor_links"], list)

        self.assertIsInstance(data["relation_count"], int)
        self.assertGreaterEqual(data["relation_count"], 0)

        self.assertIsInstance(data["summary"], dict)

        self.assertIsInstance(data["federation"], int)
        self.assertGreaterEqual(data["federation"], 0)

        # In test_save.sav, there is at least one defensive pact/alliance.
        self.assertGreaterEqual(len(data["defensive_pacts"]), 1)
        self.assertIn(1, data["defensive_pacts"])


if __name__ == "__main__":
    unittest.main()

