from __future__ import annotations

import unittest

from src.sports_v2_subgroup_eligibility import (
    SportsV2SubgroupEligibilityError,
    build_subgroup_eligibility,
)


def summary(group_type, label, events, *, sport=None, product=None, quote=1.0, early=1.0, middle=1.0, late=1.0, all_three=1.0):
    row = {
        "group_type": group_type,
        "group_label": label,
        "event_count": str(events),
        "unique_series_count": str(events),
        "market_count": str(events),
        "valid_quote_event_count": str(int(events * quote)),
        "event_quote_coverage": f"{quote:.6f}",
        "valid_quote_observation_count": str(events * 10),
        "median_valid_observations_per_event": "10.000000",
        "early_event_coverage": f"{early:.6f}",
        "middle_event_coverage": f"{middle:.6f}",
        "late_event_coverage": f"{late:.6f}",
        "all_three_band_event_coverage": f"{all_three:.6f}",
        "max_event_observation_share": "0.100000",
        "top_decile_event_observation_share": "0.200000",
        "interpretation_scope": "descriptive_pre_outcome",
    }
    if sport is not None:
        row["sport_group"] = sport
    if product is not None:
        row["product_family"] = product
    return row


def profile(events):
    sport_groups = {}
    products = {}
    crosses = {}
    for row in events:
        sport_groups.setdefault(row["sport_group"], []).append(row)
        products.setdefault(row["product_family"], []).append(row)
        crosses.setdefault((row["sport_group"], row["product_family"]), []).append(row)
    return {
        "event_count": len(events),
        "event_map": events,
        "sport_group_summary": [summary("sport_group", k, len(v)) for k, v in sport_groups.items()],
        "product_family_summary": [summary("product_family", k, len(v)) for k, v in products.items()],
        "sport_product_summary": [summary("sport_x_product", f"{s} | {p}", len(v), sport=s, product=p) for (s, p), v in crosses.items()],
        "outcomes_materialized": False,
        "calibration_analysis_run": False,
        "profitability_analysis_run": False,
    }


class SportsV2SubgroupEligibilityTests(unittest.TestCase):
    def test_eligible_sport_needs_events_coverage_and_series_diversity(self):
        events = []
        for i in range(10):
            events.append({
                "event_ticker": f"E{i}",
                "series_ticker": f"KXMLBTYPE{i % 2}",
                "sport_group": "MLB",
                "sport_classification_confidence": "high",
                "product_family": "coach_or_manager_status" if i < 5 else "team_destination_or_roster",
                "product_classification_confidence": "high",
            })
        result = build_subgroup_eligibility(profile(events))
        mlb = result["sport_group_eligibility"][0]
        self.assertEqual(mlb["eligibility_status"], "eligible_robustness_stratum")
        self.assertFalse(mlb["standalone_calibration_claim_authorized"])

    def test_nine_events_stays_descriptive(self):
        events = [{
            "event_ticker": f"E{i}", "series_ticker": f"KXNFL{i % 2}",
            "sport_group": "NFL", "sport_classification_confidence": "high",
            "product_family": "team_destination_or_roster", "product_classification_confidence": "high",
        } for i in range(9)]
        result = build_subgroup_eligibility(profile(events))
        nfl = result["sport_group_eligibility"][0]
        self.assertEqual(nfl["eligibility_status"], "descriptive_only")
        self.assertIn("fewer_than_minimum_events", nfl["eligibility_reasons"])

    def test_unclassified_sport_never_becomes_eligible(self):
        events = [{
            "event_ticker": f"E{i}", "series_ticker": f"KXOTHER{i % 3}",
            "sport_group": "Other/Unclassified", "sport_classification_confidence": "unclassified",
            "product_family": "coach_or_manager_status", "product_classification_confidence": "high",
        } for i in range(12)]
        result = build_subgroup_eligibility(profile(events))
        row = result["sport_group_eligibility"][0]
        self.assertEqual(row["eligibility_status"], "descriptive_only")
        self.assertIn("sport_identity_not_high_confidence", row["eligibility_reasons"])

    def test_product_family_requires_cross_sport_diversity(self):
        events = [{
            "event_ticker": f"E{i}", "series_ticker": f"KXMLB{i % 2}",
            "sport_group": "MLB", "sport_classification_confidence": "high",
            "product_family": "debut_or_first_appearance", "product_classification_confidence": "high",
        } for i in range(12)]
        result = build_subgroup_eligibility(profile(events))
        row = result["product_family_eligibility"][0]
        self.assertEqual(row["eligibility_status"], "descriptive_only")
        self.assertIn("insufficient_cross_sport_diversity", row["eligibility_reasons"])

    def test_product_family_can_be_eligible_across_two_sports(self):
        events = []
        for i in range(10):
            sport = "MLB" if i < 5 else "NFL"
            events.append({
                "event_ticker": f"E{i}", "series_ticker": f"KX{sport}COACH{i % 2}",
                "sport_group": sport, "sport_classification_confidence": "high",
                "product_family": "coach_or_manager_status", "product_classification_confidence": "high",
            })
        result = build_subgroup_eligibility(profile(events))
        row = result["product_family_eligibility"][0]
        self.assertEqual(row["eligibility_status"], "eligible_robustness_stratum")

    def test_cross_cell_requires_series_diversity(self):
        events = [{
            "event_ticker": f"E{i}", "series_ticker": "KXNEXTTEAMNFL",
            "sport_group": "NFL", "sport_classification_confidence": "high",
            "product_family": "team_destination_or_roster", "product_classification_confidence": "high",
        } for i in range(10)]
        result = build_subgroup_eligibility(profile(events))
        row = result["sport_product_eligibility"][0]
        self.assertEqual(row["eligibility_status"], "descriptive_only")
        self.assertIn("insufficient_series_diversity", row["eligibility_reasons"])
        self.assertIn("dominant_series_share_above_block_threshold", row["eligibility_reasons"])

    def test_band_coverage_failure_blocks_eligibility(self):
        events = [{
            "event_ticker": f"E{i}", "series_ticker": f"KXNBA{i % 2}",
            "sport_group": "NBA", "sport_classification_confidence": "high",
            "product_family": "coach_or_manager_status", "product_classification_confidence": "high",
        } for i in range(10)]
        p = profile(events)
        p["sport_group_summary"][0]["early_event_coverage"] = "0.400000"
        result = build_subgroup_eligibility(p)
        self.assertIn("early_event_coverage_below_threshold", result["sport_group_eligibility"][0]["eligibility_reasons"])

    def test_result_key_anywhere_is_rejected(self):
        p = profile([])
        p["result"] = "yes"
        with self.assertRaises(SportsV2SubgroupEligibilityError):
            build_subgroup_eligibility(p)

    def test_cross_matrix_preserves_zero_cells(self):
        events = [
            {"event_ticker": "E1", "series_ticker": "KXMLB1", "sport_group": "MLB", "sport_classification_confidence": "high", "product_family": "coach_or_manager_status", "product_classification_confidence": "high"},
            {"event_ticker": "E2", "series_ticker": "KXNFL1", "sport_group": "NFL", "sport_classification_confidence": "high", "product_family": "team_destination_or_roster", "product_classification_confidence": "high"},
        ]
        result = build_subgroup_eligibility(profile(events))
        matrix = {row["sport_group"]: row for row in result["sport_product_event_count_matrix"]}
        self.assertEqual(matrix["MLB"]["team_destination_or_roster"], 0)
        self.assertEqual(matrix["NFL"]["coach_or_manager_status"], 0)


if __name__ == "__main__":
    unittest.main()
