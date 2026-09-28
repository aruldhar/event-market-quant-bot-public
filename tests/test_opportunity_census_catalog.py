import copy
import unittest

from src.opportunity_census_catalog import (
    OpportunityCensusCatalogError,
    load_opportunity_census_catalog,
    summarize_opportunity_census_catalog,
    validate_opportunity_census_catalog,
)


class OpportunityCensusCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_opportunity_census_catalog()

    def test_committed_catalog_is_neutral_and_execution_blocked(self):
        summary = summarize_opportunity_census_catalog(self.catalog)
        self.assertEqual(summary["preferred_candidate_id"], None)
        self.assertFalse(summary["ranking_score_enabled"])
        self.assertEqual(summary["execution_enabled_count"], 0)
        self.assertGreaterEqual(summary["event_venue_candidate_count"], 10)
        self.assertGreaterEqual(summary["comparison_class_count"], 9)

    def test_required_broad_market_classes_are_present(self):
        class_ids = {item["class_id"] for item in self.catalog["comparison_classes"]}
        self.assertTrue({
            "event_markets",
            "crypto_spot",
            "crypto_perpetuals",
            "crypto_options",
            "traditional_futures",
            "traditional_options",
            "sports_exchange_betting",
            "weather_event_contracts",
            "macro_event_contracts",
        }.issubset(class_ids))

    def test_preferred_candidate_is_rejected(self):
        changed = copy.deepcopy(self.catalog)
        changed["selection_policy"]["preferred_candidate_id"] = "kalshi"
        with self.assertRaises(OpportunityCensusCatalogError):
            validate_opportunity_census_catalog(changed)

    def test_ranking_score_is_rejected(self):
        changed = copy.deepcopy(self.catalog)
        changed["selection_policy"]["ranking_score_enabled"] = True
        with self.assertRaises(OpportunityCensusCatalogError):
            validate_opportunity_census_catalog(changed)

    def test_execution_enablement_is_rejected(self):
        changed = copy.deepcopy(self.catalog)
        changed["event_venue_candidates"][0]["execution_state"] = "enabled"
        with self.assertRaises(OpportunityCensusCatalogError):
            validate_opportunity_census_catalog(changed)

    def test_duplicate_candidate_is_rejected(self):
        changed = copy.deepcopy(self.catalog)
        changed["event_venue_candidates"].append(copy.deepcopy(changed["event_venue_candidates"][0]))
        with self.assertRaises(OpportunityCensusCatalogError):
            validate_opportunity_census_catalog(changed)


if __name__ == "__main__":
    unittest.main()
