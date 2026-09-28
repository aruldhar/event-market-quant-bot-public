from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.crypto_heterogeneity import (
    CryptoHeterogeneityError,
    _resolve_path,
    build_crypto_heterogeneity_profile,
    classify_series_ticker,
)


class CryptoHeterogeneityTests(unittest.TestCase):
    def test_asset_classification_is_conservative(self):
        self.assertEqual(classify_series_ticker("KXBTCMINY")["asset_group"], "Bitcoin")
        self.assertEqual(classify_series_ticker("KXETHMINY")["asset_group"], "Ethereum")
        self.assertEqual(classify_series_ticker("KXBNBMAXY")["asset_group"], "BNB")
        self.assertEqual(classify_series_ticker("KXZECMINY")["asset_group"], "ZEC")
        self.assertEqual(classify_series_ticker("KXBTCETHATH")["asset_group"], "CrossAssetBTCETH")
        self.assertEqual(classify_series_ticker("KXFDVMONAD")["asset_group"], "ProjectOrTokenSpecific")
        self.assertEqual(classify_series_ticker("KXUNKNOWN")["asset_group"], "Other/Unclassified")

    def test_template_classification(self):
        self.assertEqual(classify_series_ticker("KXFDVMONAD")["template_family"], "fdv_family")
        self.assertEqual(classify_series_ticker("KXBTCMINY")["template_family"], "min_or_max_family")
        self.assertEqual(
            classify_series_ticker("KXGTEDEPLOYMEGAETHDAY1")["template_family"],
            "launch_or_deployment_family",
        )
        self.assertEqual(classify_series_ticker("KXBTC75VS100")["template_family"], "relative_or_ath_family")

    def test_profile_is_event_based(self):
        events = [
            {"category": "Crypto", "event_ticker": "E1", "series_ticker": "KXBTCMINY"},
            {"category": "Crypto", "event_ticker": "E2", "series_ticker": "KXFDVMONAD"},
        ]
        markets = [
            {"category": "Crypto", "ticker": "M1", "event_ticker": "E1"},
            {"category": "Crypto", "ticker": "M2", "event_ticker": "E2"},
        ]
        observations = [
            {"category": "Crypto", "ticker": "M1", "event_ticker": "E1", "valid_quote_observation": "true", "time_band": "early_5d_to_7d"},
            {"category": "Crypto", "ticker": "M1", "event_ticker": "E1", "valid_quote_observation": "true", "time_band": "middle_3d_to_5d"},
            {"category": "Crypto", "ticker": "M1", "event_ticker": "E1", "valid_quote_observation": "true", "time_band": "late_1d_to_3d"},
            {"category": "Crypto", "ticker": "M2", "event_ticker": "E2", "valid_quote_observation": "true", "time_band": "late_1d_to_3d"},
        ]
        report = build_crypto_heterogeneity_profile(events, markets, observations)
        self.assertEqual(report["event_count"], 2)
        self.assertFalse(report["general_crypto_conclusion_authorized"])
        btc = next(row for row in report["asset_group_summary"] if row["group_label"] == "Bitcoin")
        self.assertEqual(btc["all_three_band_event_coverage"], "1.000000")

    def test_dense_rows_do_not_change_event_count(self):
        events = [
            {"category": "Crypto", "event_ticker": "E1", "series_ticker": "KXBTCMINY"},
            {"category": "Crypto", "event_ticker": "E2", "series_ticker": "KXBTCMAXY"},
        ]
        markets = [
            {"category": "Crypto", "ticker": "M1", "event_ticker": "E1"},
            {"category": "Crypto", "ticker": "M2", "event_ticker": "E2"},
        ]
        observations = [
            {"category": "Crypto", "ticker": "M1", "event_ticker": "E1", "valid_quote_observation": "true", "time_band": "late_1d_to_3d"}
            for _ in range(100)
        ] + [
            {"category": "Crypto", "ticker": "M2", "event_ticker": "E2", "valid_quote_observation": "true", "time_band": "late_1d_to_3d"}
        ]
        report = build_crypto_heterogeneity_profile(events, markets, observations)
        btc = report["asset_group_summary"][0]
        self.assertEqual(btc["event_count"], "2")
        self.assertGreater(float(btc["max_event_observation_share"]), 0.98)

    def test_outcome_field_is_rejected(self):
        with self.assertRaises(CryptoHeterogeneityError):
            build_crypto_heterogeneity_profile(
                [{"category": "Crypto", "event_ticker": "E", "series_ticker": "KXBTCMINY", "result": "yes"}],
                [],
                [],
            )

    def test_non_crypto_rows_are_rejected(self):
        with self.assertRaises(CryptoHeterogeneityError):
            build_crypto_heterogeneity_profile(
                [{"category": "Sports", "event_ticker": "E", "series_ticker": "KXMLB"}],
                [],
                [],
            )

    def test_manifest_path_descriptor_is_supported(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            resolved = _resolve_path(
                {"kind": "repository_relative", "value": "data/manifests/run.json"}, root
            )
            self.assertEqual(resolved, (root / "data/manifests/run.json").resolve())

    def test_repository_relative_path_escape_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            with self.assertRaises(CryptoHeterogeneityError):
                _resolve_path(
                    {"kind": "repository_relative", "value": "../outside.json"}, root
                )


if __name__ == "__main__":
    unittest.main()
