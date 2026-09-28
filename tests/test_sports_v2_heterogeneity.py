from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.sports_v2_heterogeneity import (
    SportsV2HeterogeneityError,
    _resolve_path,
    build_heterogeneity_profile,
    classify_series_ticker,
)


class SportsV2HeterogeneityTests(unittest.TestCase):
    def test_high_confidence_sport_and_product_classification(self):
        self.assertEqual(classify_series_ticker("KXMLBDEBUT")["sport_group"], "MLB")
        self.assertEqual(
            classify_series_ticker("KXMLBDEBUT")["product_family"],
            "debut_or_first_appearance",
        )
        self.assertEqual(classify_series_ticker("KXNEXTTEAMNFL")["sport_group"], "NFL")
        self.assertEqual(
            classify_series_ticker("KXNEXTTEAMNFL")["product_family"],
            "team_destination_or_roster",
        )
        self.assertEqual(classify_series_ticker("KXGOLFMAJOR")["sport_group"], "Golf")

    def test_unknown_series_stays_unclassified(self):
        row = classify_series_ticker("KXMCGREGORFIGHTNEXT")
        self.assertEqual(row["sport_group"], "Other/Unclassified")
        self.assertEqual(row["sport_classification_confidence"], "unclassified")
        self.assertEqual(row["product_family"], "appearance_or_scheduling")

    def test_profile_is_event_based_and_reports_band_coverage(self):
        events = [
            {"category": "Sports", "event_ticker": "E1", "series_ticker": "KXMLBDEBUT"},
            {"category": "Sports", "event_ticker": "E2", "series_ticker": "KXNEXTTEAMNFL"},
        ]
        markets = [
            {"category": "Sports", "ticker": "M1", "event_ticker": "E1"},
            {"category": "Sports", "ticker": "M2", "event_ticker": "E2"},
        ]
        observations = [
            {"category": "Sports", "ticker": "M1", "event_ticker": "E1", "valid_quote_observation": "true", "time_band": "early_5d_to_7d"},
            {"category": "Sports", "ticker": "M1", "event_ticker": "E1", "valid_quote_observation": "true", "time_band": "middle_3d_to_5d"},
            {"category": "Sports", "ticker": "M1", "event_ticker": "E1", "valid_quote_observation": "true", "time_band": "late_1d_to_3d"},
            {"category": "Sports", "ticker": "M2", "event_ticker": "E2", "valid_quote_observation": "true", "time_band": "late_1d_to_3d"},
        ]
        report = build_heterogeneity_profile(events, markets, observations)
        self.assertEqual(report["event_count"], 2)
        self.assertFalse(report["general_sports_conclusion_authorized"])
        mlb = next(row for row in report["sport_group_summary"] if row["group_label"] == "MLB")
        self.assertEqual(mlb["event_count"], "1")
        self.assertEqual(mlb["all_three_band_event_coverage"], "1.000000")
        nfl = next(row for row in report["sport_group_summary"] if row["group_label"] == "NFL")
        self.assertEqual(nfl["early_event_coverage"], "0.000000")
        self.assertEqual(nfl["late_event_coverage"], "1.000000")

    def test_dense_observations_do_not_change_event_count(self):
        events = [
            {"category": "Sports", "event_ticker": "E1", "series_ticker": "KXMLBDEBUT"},
            {"category": "Sports", "event_ticker": "E2", "series_ticker": "KXMLBDEBUT"},
        ]
        markets = [
            {"category": "Sports", "ticker": "M1", "event_ticker": "E1"},
            {"category": "Sports", "ticker": "M2", "event_ticker": "E2"},
        ]
        observations = []
        for _ in range(100):
            observations.append({"category": "Sports", "ticker": "M1", "event_ticker": "E1", "valid_quote_observation": "true", "time_band": "late_1d_to_3d"})
        observations.append({"category": "Sports", "ticker": "M2", "event_ticker": "E2", "valid_quote_observation": "true", "time_band": "late_1d_to_3d"})
        report = build_heterogeneity_profile(events, markets, observations)
        mlb = report["sport_group_summary"][0]
        self.assertEqual(mlb["event_count"], "2")
        self.assertEqual(mlb["valid_quote_observation_count"], "101")
        self.assertGreater(float(mlb["max_event_observation_share"]), 0.98)

    def test_result_field_is_rejected(self):
        with self.assertRaises(SportsV2HeterogeneityError):
            build_heterogeneity_profile(
                [{"category": "Sports", "event_ticker": "E", "series_ticker": "KXMLB", "result": "yes"}],
                [],
                [],
            )


    def test_manifest_path_descriptor_is_supported(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            resolved = _resolve_path(
                {"kind": "repository_relative", "value": "data/manifests/run.json"},
                root,
            )
            self.assertEqual(resolved, (root / "data/manifests/run.json").resolve())

    def test_repository_relative_path_escape_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            with self.assertRaises(SportsV2HeterogeneityError):
                _resolve_path(
                    {"kind": "repository_relative", "value": "../outside.json"},
                    root,
                )

    def test_non_sports_rows_are_rejected(self):
        with self.assertRaises(SportsV2HeterogeneityError):
            build_heterogeneity_profile(
                [{"category": "Crypto", "event_ticker": "E", "series_ticker": "KXBTC"}],
                [],
                [],
            )


if __name__ == "__main__":
    unittest.main()
