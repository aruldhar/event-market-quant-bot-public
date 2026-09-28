from __future__ import annotations

import unittest

from src.crypto_subgroup_eligibility import (
    CryptoSubgroupEligibilityError,
    build_subgroup_eligibility,
)


def _summary(label, n, *, asset=None, template=None, early="1.000000", middle="1.000000", late="1.000000", all_three="1.000000", quote="1.000000"):
    row = {
        "group_type": "test",
        "group_label": label,
        "event_count": str(n),
        "unique_series_count": str(n),
        "market_count": str(n),
        "valid_quote_event_count": str(n if quote == "1.000000" else 0),
        "event_quote_coverage": quote,
        "valid_quote_observation_count": str(n * 10),
        "median_valid_observations_per_event": "10.000000",
        "early_event_coverage": early,
        "middle_event_coverage": middle,
        "late_event_coverage": late,
        "all_three_band_event_coverage": all_three,
        "max_event_observation_share": "0.100000",
        "top_decile_event_observation_share": "0.200000",
        "interpretation_scope": "descriptive_pre_outcome",
    }
    if asset is not None:
        row["asset_group"] = asset
    if template is not None:
        row["template_family"] = template
    return row


def profile(events):
    asset_groups = sorted({e["asset_group"] for e in events})
    templates = sorted({e["template_family"] for e in events})
    assets = [_summary(a, sum(e["asset_group"] == a for e in events)) for a in asset_groups]
    trows = [_summary(t, sum(e["template_family"] == t for e in events)) for t in templates]
    cross = []
    for a in asset_groups:
        for t in templates:
            n = sum(e["asset_group"] == a and e["template_family"] == t for e in events)
            if n:
                cross.append(_summary(f"{a} | {t}", n, asset=a, template=t))
    return {
        "event_count": len(events),
        "event_map": events,
        "asset_group_summary": assets,
        "template_family_summary": trows,
        "asset_template_summary": cross,
        "outcomes_materialized": False,
        "calibration_analysis_run": False,
        "strategy_model_analysis_run": False,
    }


class CryptoSubgroupEligibilityTests(unittest.TestCase):
    def test_asset_group_can_qualify_with_same_numeric_gates_as_sports(self):
        events = [{
            "event_ticker": f"E{i}", "series_ticker": f"KXFDV{i}",
            "asset_group": "ProjectOrTokenSpecific", "asset_classification_confidence": "high",
            "template_family": "fdv_family", "template_classification_confidence": "high",
        } for i in range(12)]
        result = build_subgroup_eligibility(profile(events))
        row = result["asset_group_eligibility"][0]
        self.assertEqual(row["eligibility_status"], "eligible_robustness_stratum")
        self.assertTrue(result["policy"]["sports_policy_numeric_parity"])

    def test_small_bitcoin_group_is_descriptive_only(self):
        events = [{
            "event_ticker": f"E{i}", "series_ticker": f"KXBTC{i}",
            "asset_group": "Bitcoin", "asset_classification_confidence": "high",
            "template_family": "min_or_max_family", "template_classification_confidence": "high",
        } for i in range(3)]
        result = build_subgroup_eligibility(profile(events))
        row = result["asset_group_eligibility"][0]
        self.assertEqual(row["eligibility_status"], "descriptive_only")
        self.assertIn("fewer_than_minimum_events", row["eligibility_reasons"])

    def test_unclassified_asset_never_qualifies(self):
        events = [{
            "event_ticker": f"E{i}", "series_ticker": f"KXUNKNOWN{i}",
            "asset_group": "Other/Unclassified", "asset_classification_confidence": "unclassified",
            "template_family": "launch_or_deployment_family", "template_classification_confidence": "high",
        } for i in range(12)]
        result = build_subgroup_eligibility(profile(events))
        row = result["asset_group_eligibility"][0]
        self.assertIn("asset_identity_not_high_confidence", row["eligibility_reasons"])

    def test_general_template_requires_cross_asset_diversity(self):
        events = [{
            "event_ticker": f"E{i}", "series_ticker": f"KXFDV{i}",
            "asset_group": "ProjectOrTokenSpecific", "asset_classification_confidence": "high",
            "template_family": "fdv_family", "template_classification_confidence": "high",
        } for i in range(12)]
        result = build_subgroup_eligibility(profile(events))
        row = result["template_family_eligibility"][0]
        self.assertEqual(row["eligibility_status"], "descriptive_only")
        self.assertIn("insufficient_cross_asset_diversity", row["eligibility_reasons"])

    def test_general_template_can_qualify_across_two_asset_groups(self):
        events = []
        for i in range(10):
            asset = "Bitcoin" if i < 5 else "Ethereum"
            events.append({
                "event_ticker": f"E{i}", "series_ticker": f"KX{asset}{i}",
                "asset_group": asset, "asset_classification_confidence": "high",
                "template_family": "min_or_max_family", "template_classification_confidence": "high",
            })
        result = build_subgroup_eligibility(profile(events))
        row = result["template_family_eligibility"][0]
        self.assertEqual(row["eligibility_status"], "eligible_robustness_stratum")

    def test_specific_cross_cell_can_qualify_even_if_template_is_not_general(self):
        events = [{
            "event_ticker": f"E{i}", "series_ticker": f"KXFDVPROJECT{i}",
            "asset_group": "ProjectOrTokenSpecific", "asset_classification_confidence": "high",
            "template_family": "fdv_family", "template_classification_confidence": "high",
        } for i in range(12)]
        result = build_subgroup_eligibility(profile(events))
        cross = result["asset_template_eligibility"][0]
        self.assertEqual(cross["eligibility_status"], "eligible_robustness_stratum")

    def test_dominant_series_blocks_cross_cell(self):
        events = [{
            "event_ticker": f"E{i}", "series_ticker": "KXBTCMINY" if i < 9 else "KXBTCMAXY",
            "asset_group": "Bitcoin", "asset_classification_confidence": "high",
            "template_family": "min_or_max_family", "template_classification_confidence": "high",
        } for i in range(10)]
        result = build_subgroup_eligibility(profile(events))
        cross = result["asset_template_eligibility"][0]
        self.assertIn("dominant_series_share_above_block_threshold", cross["eligibility_reasons"])

    def test_band_coverage_failure_blocks(self):
        events = [{
            "event_ticker": f"E{i}", "series_ticker": f"KXBTC{i}",
            "asset_group": "Bitcoin", "asset_classification_confidence": "high",
            "template_family": "min_or_max_family", "template_classification_confidence": "high",
        } for i in range(10)]
        p = profile(events)
        p["asset_group_summary"][0]["early_event_coverage"] = "0.400000"
        result = build_subgroup_eligibility(p)
        self.assertIn("early_event_coverage_below_threshold", result["asset_group_eligibility"][0]["eligibility_reasons"])

    def test_result_key_anywhere_is_rejected(self):
        p = profile([])
        p["nested"] = {"result": "yes"}
        with self.assertRaises(CryptoSubgroupEligibilityError):
            build_subgroup_eligibility(p)

    def test_matrix_preserves_zero_cells(self):
        events = [
            {"event_ticker": "E1", "series_ticker": "KXBTC1", "asset_group": "Bitcoin", "asset_classification_confidence": "high", "template_family": "min_or_max_family", "template_classification_confidence": "high"},
            {"event_ticker": "E2", "series_ticker": "KXFDV1", "asset_group": "ProjectOrTokenSpecific", "asset_classification_confidence": "high", "template_family": "fdv_family", "template_classification_confidence": "high"},
        ]
        result = build_subgroup_eligibility(profile(events))
        matrix = {row["asset_group"]: row for row in result["asset_template_event_count_matrix"]}
        self.assertEqual(matrix["Bitcoin"]["fdv_family"], 0)
        self.assertEqual(matrix["ProjectOrTokenSpecific"]["min_or_max_family"], 0)


if __name__ == "__main__":
    unittest.main()
