import unittest

from save_extractor import SaveExtractor


class TestProgressionExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.extractor = SaveExtractor("test_save.sav")

    def test_get_traditions_schema_and_invariants(self) -> None:
        data = self.extractor.get_traditions()

        self.assertIsInstance(data, dict)
        self.assertIn("traditions", data)
        self.assertIn("by_tree", data)
        self.assertIn("count", data)

        self.assertIsInstance(data["traditions"], list)
        self.assertIsInstance(data["by_tree"], dict)
        self.assertIsInstance(data["count"], int)
        self.assertEqual(data["count"], len(data["traditions"]))

        self.assertGreaterEqual(data["count"], 1)
        for tid in data["traditions"]:
            self.assertIsInstance(tid, str)
            self.assertTrue(tid.startswith("tr_"))

        total_picked = 0
        for tree, tree_data in data["by_tree"].items():
            self.assertIsInstance(tree, str)
            self.assertIsInstance(tree_data, dict)
            self.assertIn("picked", tree_data)
            self.assertIn("adopted", tree_data)
            self.assertIn("finished", tree_data)

            self.assertIsInstance(tree_data["picked"], list)
            self.assertIsInstance(tree_data["adopted"], bool)
            self.assertIsInstance(tree_data["finished"], bool)

            self.assertGreaterEqual(len(tree_data["picked"]), 1)
            total_picked += len(tree_data["picked"])

            for tid in tree_data["picked"]:
                self.assertIsInstance(tid, str)
                self.assertTrue(tid.startswith("tr_"))

        self.assertEqual(total_picked, data["count"])

    def test_get_ascension_perks_schema_and_invariants(self) -> None:
        data = self.extractor.get_ascension_perks()

        self.assertIsInstance(data, dict)
        self.assertIn("ascension_perks", data)
        self.assertIn("count", data)

        self.assertIsInstance(data["ascension_perks"], list)
        self.assertIsInstance(data["count"], int)
        self.assertEqual(data["count"], len(data["ascension_perks"]))

        self.assertGreaterEqual(data["count"], 1)
        for pid in data["ascension_perks"]:
            self.assertIsInstance(pid, str)
            self.assertTrue(pid.startswith("ap_"))


if __name__ == "__main__":
    unittest.main()

