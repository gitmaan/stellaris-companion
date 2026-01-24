import sys
import unittest
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from save_extractor import SaveExtractor


class TestSpecialtySystemsExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.extractor = SaveExtractor("test_save.sav")

    def test_get_espionage_schema_and_invariants(self) -> None:
        data = self.extractor.get_espionage()

        self.assertIsInstance(data, dict)
        for key in ["player_id", "operations", "count"]:
            self.assertIn(key, data)

        self.assertIsInstance(data["player_id"], int)
        self.assertIsInstance(data["operations"], list)
        self.assertIsInstance(data["count"], int)
        self.assertGreaterEqual(data["count"], len(data["operations"]))

        # test_save.sav has at least one operation.
        self.assertGreaterEqual(data["count"], 1)

        for op in data["operations"]:
            self.assertIsInstance(op, dict)
            for required in [
                "operation_id",
                "target_country_id",
                "spy_network_id",
                "type",
                "difficulty",
                "days_left",
                "info",
                "log_entries",
                "last_log",
            ]:
                self.assertIn(required, op)

            self.assertIsInstance(op["operation_id"], str)
            self.assertIsInstance(op["log_entries"], int)
            self.assertGreaterEqual(op["log_entries"], 0)

            if op["target_country_id"] is not None:
                self.assertIsInstance(op["target_country_id"], int)
            if op["spy_network_id"] is not None:
                self.assertIsInstance(op["spy_network_id"], int)
            if op["type"] is not None:
                self.assertIsInstance(op["type"], str)
            if op["difficulty"] is not None:
                self.assertIsInstance(op["difficulty"], int)
            if op["days_left"] is not None:
                self.assertIsInstance(op["days_left"], int)
            if op["info"] is not None:
                self.assertIsInstance(op["info"], int)

            if op["last_log"] is not None:
                self.assertIsInstance(op["last_log"], dict)
                for k in ["date", "roll", "skill", "info", "difficulty"]:
                    self.assertIn(k, op["last_log"])

    def test_get_archaeology_schema_and_invariants(self) -> None:
        data = self.extractor.get_archaeology()

        self.assertIsInstance(data, dict)
        for key in ["sites", "count"]:
            self.assertIn(key, data)

        self.assertIsInstance(data["sites"], list)
        self.assertIsInstance(data["count"], int)
        self.assertGreaterEqual(data["count"], len(data["sites"]))

        # test_save.sav includes archaeological sites.
        self.assertGreaterEqual(data["count"], 1)

        for site in data["sites"]:
            self.assertIsInstance(site, dict)
            for required in [
                "site_id",
                "type",
                "location",
                "index",
                "clues",
                "difficulty",
                "days_left",
                "locked",
                "last_excavator_country",
                "excavator_fleet",
                "completed_count",
                "last_completed_date",
                "events_count",
                "active_events_count",
            ]:
                self.assertIn(required, site)

            self.assertIsInstance(site["site_id"], str)
            self.assertIsInstance(site["completed_count"], int)
            self.assertIsInstance(site["events_count"], int)
            self.assertIsInstance(site["active_events_count"], int)
            self.assertGreaterEqual(site["completed_count"], 0)
            self.assertGreaterEqual(site["events_count"], 0)
            self.assertGreaterEqual(site["active_events_count"], 0)

            if site["location"] is not None:
                self.assertIsInstance(site["location"], dict)
                self.assertIn("type", site["location"])
                self.assertIn("id", site["location"])
                self.assertIsInstance(site["location"]["type"], int)
                self.assertIsInstance(site["location"]["id"], int)

            for optional_int in ["index", "clues", "difficulty", "days_left", "last_excavator_country", "excavator_fleet"]:
                if site[optional_int] is not None:
                    self.assertIsInstance(site[optional_int], int)

            if site["locked"] is not None:
                self.assertIsInstance(site["locked"], bool)

            if site["type"] is not None:
                self.assertIsInstance(site["type"], str)

            if site["last_completed_date"] is not None:
                self.assertIsInstance(site["last_completed_date"], str)

    def test_get_relics_schema_and_invariants(self) -> None:
        data = self.extractor.get_relics()

        self.assertIsInstance(data, dict)
        for key in ["relics", "count", "last_activated_relic", "last_received_relic", "activation_cooldown_days"]:
            self.assertIn(key, data)

        self.assertIsInstance(data["relics"], list)
        self.assertIsInstance(data["count"], int)
        self.assertEqual(data["count"], len(data["relics"]))

        for relic in data["relics"]:
            self.assertIsInstance(relic, str)

        if data["last_activated_relic"] is not None:
            self.assertIsInstance(data["last_activated_relic"], str)
        if data["last_received_relic"] is not None:
            self.assertIsInstance(data["last_received_relic"], str)
        if data["activation_cooldown_days"] is not None:
            self.assertIsInstance(data["activation_cooldown_days"], int)


if __name__ == "__main__":
    unittest.main()

