import sys
import unittest
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from save_extractor import SaveExtractor


class TestEconomyDeepDiveExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.extractor = SaveExtractor("test_save.sav")

    def test_get_market_schema_and_invariants(self) -> None:
        data = self.extractor.get_market()

        self.assertIsInstance(data, dict)
        for key in [
            "enabled",
            "galactic_market_host_country_id",
            "player_has_galactic_access",
            "resources",
            "top_overpriced",
            "top_underpriced",
            "internal_market_fluctuations",
        ]:
            self.assertIn(key, data)

        self.assertIsInstance(data["enabled"], bool)
        self.assertIsInstance(data["resources"], dict)
        self.assertIsInstance(data["top_overpriced"], list)
        self.assertIsInstance(data["top_underpriced"], list)
        self.assertIsInstance(data["internal_market_fluctuations"], dict)

        # test_save.sav includes the market section; ensure core resources exist.
        for res in ["energy", "minerals", "food", "alloys", "consumer_goods"]:
            self.assertIn(res, data["resources"])
            entry = data["resources"][res]
            self.assertIsInstance(entry, dict)
            for required in [
                "fluctuation",
                "is_galactic",
                "global_bought",
                "global_sold",
                "player_bought",
                "player_sold",
            ]:
                self.assertIn(required, entry)

            self.assertIsInstance(entry["global_bought"], int)
            self.assertIsInstance(entry["global_sold"], int)
            self.assertIsInstance(entry["player_bought"], int)
            self.assertIsInstance(entry["player_sold"], int)
            self.assertGreaterEqual(entry["global_bought"], 0)
            self.assertGreaterEqual(entry["global_sold"], 0)
            self.assertGreaterEqual(entry["player_bought"], 0)
            self.assertGreaterEqual(entry["player_sold"], 0)

            if entry["fluctuation"] is not None:
                self.assertIsInstance(entry["fluctuation"], (int, float))
            if entry["is_galactic"] is not None:
                self.assertIsInstance(entry["is_galactic"], bool)

        for ranked_key in ["top_overpriced", "top_underpriced"]:
            ranked = data[ranked_key]
            self.assertLessEqual(len(ranked), 10)
            for item in ranked:
                self.assertIsInstance(item, dict)
                self.assertIn("resource", item)
                self.assertIn("fluctuation", item)
                self.assertIsInstance(item["resource"], str)
                self.assertIsInstance(item["fluctuation"], (int, float))

    def test_get_trade_value_schema_and_invariants(self) -> None:
        data = self.extractor.get_trade_value()

        self.assertIsInstance(data, dict)
        for key in [
            "trade_policy",
            "trade_conversions",
            "trade_policy_income",
            "trade_value",
            "collection",
        ]:
            self.assertIn(key, data)

        # test_save.sav uses the trade league trade policy (observed in country policies).
        self.assertIsInstance(data["trade_policy"], str)
        self.assertIn("trade_policy_", data["trade_policy"])

        self.assertIsInstance(data["trade_conversions"], dict)
        self.assertIsInstance(data["trade_policy_income"], dict)
        self.assertIsInstance(data["collection"], dict)

        for k, v in data["trade_conversions"].items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, float)
            self.assertGreaterEqual(v, 0.0)

        # Conversions are fractions; allow a bit of slack for variants/mods.
        if data["trade_conversions"]:
            total = sum(data["trade_conversions"].values())
            self.assertGreater(total, 0.0)
            self.assertLess(total, 2.0)

        if data["trade_value"] is not None:
            self.assertIsInstance(data["trade_value"], (int, float))
            self.assertGreaterEqual(float(data["trade_value"]), 0.0)

        collection = data["collection"]
        for k in ["starbases_scanned", "trade_hub_modules", "offworld_trading_companies"]:
            self.assertIn(k, collection)
            self.assertIsInstance(collection[k], int)
            self.assertGreaterEqual(collection[k], 0)

    def test_get_budget_breakdown_schema_and_invariants(self) -> None:
        data = self.extractor.get_budget_breakdown()

        self.assertIsInstance(data, dict)
        for key in [
            "by_resource",
            "tracked_resources",
            "income_source_count",
            "expense_source_count",
        ]:
            self.assertIn(key, data)

        self.assertIsInstance(data["by_resource"], dict)
        self.assertIsInstance(data["tracked_resources"], list)
        self.assertIsInstance(data["income_source_count"], int)
        self.assertIsInstance(data["expense_source_count"], int)
        self.assertGreaterEqual(data["income_source_count"], 0)
        self.assertGreaterEqual(data["expense_source_count"], 0)

        for res in ["energy", "minerals", "food", "consumer_goods", "alloys", "unity"]:
            self.assertIn(res, data["by_resource"])
            entry = data["by_resource"][res]
            self.assertIsInstance(entry, dict)
            for required in [
                "income_total",
                "expenses_total",
                "net",
                "top_income_sources",
                "top_expense_sources",
            ]:
                self.assertIn(required, entry)

            self.assertIsInstance(entry["income_total"], (int, float))
            self.assertIsInstance(entry["expenses_total"], (int, float))
            self.assertIsInstance(entry["net"], (int, float))
            self.assertIsInstance(entry["top_income_sources"], list)
            self.assertIsInstance(entry["top_expense_sources"], list)

            expected_net = round(float(entry["income_total"]) - float(entry["expenses_total"]), 2)
            self.assertAlmostEqual(float(entry["net"]), expected_net, places=2)

            for top_list in [entry["top_income_sources"], entry["top_expense_sources"]]:
                self.assertLessEqual(len(top_list), 10)
                for item in top_list:
                    self.assertIsInstance(item, dict)
                    self.assertIn("source", item)
                    self.assertIn("amount", item)
                    self.assertIsInstance(item["source"], str)
                    self.assertIsInstance(item["amount"], (int, float))


if __name__ == "__main__":
    unittest.main()
