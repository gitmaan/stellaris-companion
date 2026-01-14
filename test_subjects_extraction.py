import unittest

from save_extractor import SaveExtractor


class TestSubjectsExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.extractor = SaveExtractor("test_save.sav")

    def test_get_subjects_schema_and_invariants(self) -> None:
        data = self.extractor.get_subjects()

        self.assertIsInstance(data, dict)
        for key in ["player_id", "as_overlord", "as_subject", "count"]:
            self.assertIn(key, data)

        self.assertIsInstance(data["player_id"], int)
        self.assertIsInstance(data["as_overlord"], dict)
        self.assertIsInstance(data["as_subject"], dict)
        self.assertIsInstance(data["count"], int)

        for side_key, list_key in [("as_overlord", "subjects"), ("as_subject", "overlords")]:
            side = data[side_key]
            self.assertIn("count", side)
            self.assertIn(list_key, side)
            self.assertIsInstance(side["count"], int)
            self.assertIsInstance(side[list_key], list)
            self.assertGreaterEqual(side["count"], len(side[list_key]))

            for entry in side[list_key]:
                self.assertIsInstance(entry, dict)
                for required in [
                    "agreement_id",
                    "owner_id",
                    "target_id",
                    "active_status",
                    "date_added",
                    "date_changed",
                    "preset",
                    "specialization",
                    "specialization_level",
                    "terms",
                ]:
                    self.assertIn(required, entry)

                self.assertIsInstance(entry["agreement_id"], str)
                self.assertIsInstance(entry["owner_id"], int)
                self.assertIsInstance(entry["target_id"], int)
                self.assertIsInstance(entry["terms"], dict)

                if entry["preset"] is not None:
                    self.assertIsInstance(entry["preset"], str)

                if entry["specialization"] is not None:
                    self.assertIsInstance(entry["specialization"], str)

                if entry["specialization_level"] is not None:
                    self.assertIsInstance(entry["specialization_level"], int)
                    self.assertGreaterEqual(entry["specialization_level"], 0)

        self.assertEqual(data["count"], data["as_overlord"]["count"] + data["as_subject"]["count"])

        # Sanity check: test_save.sav includes at least one agreement involving the player (as subject).
        self.assertGreaterEqual(data["as_subject"]["count"], 1)


if __name__ == "__main__":
    unittest.main()

