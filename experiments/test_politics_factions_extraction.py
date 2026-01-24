import unittest

from save_extractor import SaveExtractor


class TestPoliticsFactionsExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.extractor = SaveExtractor("test_save.sav")

    def test_get_factions_schema_and_invariants(self) -> None:
        data = self.extractor.get_factions()

        self.assertIsInstance(data, dict)
        self.assertIn("is_gestalt", data)
        self.assertIn("factions", data)
        self.assertIn("count", data)

        self.assertIsInstance(data["is_gestalt"], bool)
        self.assertIsInstance(data["factions"], list)
        self.assertIsInstance(data["count"], int)
        self.assertGreaterEqual(data["count"], 0)

        if data["is_gestalt"]:
            self.assertEqual(data["count"], 0)
            self.assertEqual(data["factions"], [])
            return

        self.assertGreaterEqual(data["count"], 1)
        self.assertGreaterEqual(len(data["factions"]), 1)
        self.assertLessEqual(len(data["factions"]), 25)

        for faction in data["factions"]:
            self.assertIsInstance(faction, dict)
            for key in [
                "id",
                "country_id",
                "type",
                "name",
                "support_percent",
                "support_power",
                "approval",
                "members_count",
            ]:
                self.assertIn(key, faction)

            self.assertIsInstance(faction["id"], str)
            self.assertIsInstance(faction["country_id"], int)
            self.assertIsInstance(faction["type"], str)
            self.assertIsInstance(faction["name"], str)

            self.assertIsInstance(faction["support_percent"], float)
            self.assertIsInstance(faction["support_power"], float)
            self.assertIsInstance(faction["approval"], float)
            self.assertIsInstance(faction["members_count"], int)

            self.assertGreaterEqual(faction["support_percent"], 0.0)
            self.assertLessEqual(faction["support_percent"], 1.0)
            self.assertGreaterEqual(faction["approval"], 0.0)
            self.assertLessEqual(faction["approval"], 1.0)
            self.assertGreaterEqual(faction["members_count"], 0)


if __name__ == "__main__":
    unittest.main()

