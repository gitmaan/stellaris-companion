import sys
import unittest
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from save_extractor import SaveExtractor


class TestGalacticCommunityExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.extractor = SaveExtractor("test_save.sav")

    def test_get_galactic_community_schema_and_invariants(self) -> None:
        data = self.extractor.get_galactic_community()

        self.assertIsInstance(data, dict)
        for key in [
            "members",
            "members_count",
            "player_is_member",
            "council_members",
            "council_positions",
            "council_veto",
            "emissaries_count",
            "voting_resolution_id",
            "last_resolution_id",
            "days_until_election",
            "community_formed",
            "council_established",
            "proposed_count",
            "passed_count",
            "failed_count",
            "resolutions",
        ]:
            self.assertIn(key, data)

        self.assertIsInstance(data["members"], list)
        self.assertIsInstance(data["members_count"], int)
        self.assertIsInstance(data["player_is_member"], bool)
        self.assertIsInstance(data["council_members"], list)
        self.assertIsInstance(data["emissaries_count"], int)

        self.assertGreaterEqual(data["members_count"], len(data["members"]))
        self.assertGreaterEqual(data["members_count"], 0)
        self.assertGreaterEqual(data["emissaries_count"], 0)

        for cid in data["members"]:
            self.assertIsInstance(cid, int)
            self.assertNotEqual(cid, 4294967295)

        for cid in data["council_members"]:
            self.assertIsInstance(cid, int)
            self.assertNotEqual(cid, 4294967295)
            self.assertIn(cid, data["members"])

        if data["council_positions"] is not None:
            self.assertIsInstance(data["council_positions"], int)
            self.assertGreaterEqual(data["council_positions"], len(data["council_members"]))

        if data["council_veto"] is not None:
            self.assertIsInstance(data["council_veto"], bool)

        if data["voting_resolution_id"] is not None:
            self.assertIsInstance(data["voting_resolution_id"], int)
            self.assertGreaterEqual(data["voting_resolution_id"], 0)

        if data["last_resolution_id"] is not None:
            self.assertIsInstance(data["last_resolution_id"], int)
            self.assertGreaterEqual(data["last_resolution_id"], 0)

        if data["days_until_election"] is not None:
            self.assertIsInstance(data["days_until_election"], int)
            self.assertGreaterEqual(data["days_until_election"], 0)

        if data["community_formed"] is not None:
            self.assertIsInstance(data["community_formed"], str)
            self.assertTrue(data["community_formed"])

        if data["council_established"] is not None:
            self.assertIsInstance(data["council_established"], str)
            self.assertTrue(data["council_established"])

        self.assertIsInstance(data["proposed_count"], int)
        self.assertIsInstance(data["passed_count"], int)
        self.assertIsInstance(data["failed_count"], int)
        self.assertGreaterEqual(data["proposed_count"], 0)
        self.assertGreaterEqual(data["passed_count"], 0)
        self.assertGreaterEqual(data["failed_count"], 0)

        self.assertIsInstance(data["resolutions"], dict)
        for rkey in ["proposed", "passed", "failed"]:
            self.assertIn(rkey, data["resolutions"])
            self.assertIsInstance(data["resolutions"][rkey], list)
            for rid in data["resolutions"][rkey]:
                self.assertIsInstance(rid, int)
                self.assertGreaterEqual(rid, 0)

        self.assertGreaterEqual(data["proposed_count"], len(data["resolutions"]["proposed"]))
        self.assertGreaterEqual(data["passed_count"], len(data["resolutions"]["passed"]))
        self.assertGreaterEqual(data["failed_count"], len(data["resolutions"]["failed"]))


if __name__ == "__main__":
    unittest.main()
