import sys
import unittest
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from save_extractor import SaveExtractor


class TestFleetCompositionExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.extractor = SaveExtractor("test_save.sav")

    def test_get_fleet_composition_schema_and_invariants(self) -> None:
        data = self.extractor.get_fleet_composition(limit=9999)

        self.assertIsInstance(data, dict)
        self.assertIn("fleets", data)
        self.assertIn("by_class_total", data)
        self.assertIn("fleet_count", data)

        self.assertIsInstance(data["fleets"], list)
        self.assertIsInstance(data["by_class_total"], dict)
        self.assertIsInstance(data["fleet_count"], int)

        self.assertGreaterEqual(data["fleet_count"], 0)
        self.assertEqual(data["fleet_count"], len(data["fleets"]))

        if data["fleet_count"] == 0:
            self.assertEqual(data["by_class_total"], {})
            return

        self.assertGreater(len(data["by_class_total"]), 0)
        total_from_classes = 0
        for ship_class, count in data["by_class_total"].items():
            self.assertIsInstance(ship_class, str)
            self.assertTrue(ship_class)
            self.assertIsInstance(count, int)
            self.assertGreaterEqual(count, 0)
            total_from_classes += count

        total_from_fleets = 0
        for fleet in data["fleets"]:
            self.assertIsInstance(fleet, dict)
            for key in ["fleet_id", "name", "ship_classes", "total_ships"]:
                self.assertIn(key, fleet)

            self.assertIsInstance(fleet["fleet_id"], str)
            self.assertIsInstance(fleet["ship_classes"], dict)
            self.assertIsInstance(fleet["total_ships"], int)
            self.assertGreaterEqual(fleet["total_ships"], 0)

            if fleet["name"] is not None:
                self.assertIsInstance(fleet["name"], str)

            class_sum = 0
            for ship_class, count in fleet["ship_classes"].items():
                self.assertIsInstance(ship_class, str)
                self.assertTrue(ship_class)
                self.assertIsInstance(count, int)
                self.assertGreaterEqual(count, 0)
                class_sum += count

            self.assertEqual(class_sum, fleet["total_ships"])
            total_from_fleets += fleet["total_ships"]

        self.assertEqual(total_from_classes, total_from_fleets)


if __name__ == "__main__":
    unittest.main()
