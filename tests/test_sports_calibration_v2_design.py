from __future__ import annotations

from decimal import Decimal
import unittest

from src.sports_calibration_v2_design import (
    SportsCalibrationV2DesignError,
    event_weight_totals,
    hierarchical_observation_weights,
)


def obs(event: str, market: str, end: int, *, band: str = "early_5d_to_7d", result=None):
    row = {
        "category": "Sports",
        "event_ticker": event,
        "ticker": market,
        "end_period_ts": str(end),
        "time_to_close_seconds": "500000",
        "time_band": band,
        "q_mid": "0.50",
        "valid_quote_observation": "true",
    }
    if result is not None:
        row["result"] = result
    return row


class SportsCalibrationV2DesignTests(unittest.TestCase):
    def test_dense_event_cannot_dominate_equal_event_weights(self) -> None:
        rows = []
        rows.extend(obs("E1", "M1", i) for i in range(1000))
        rows.extend(obs("E2", "M2", 2000 + i) for i in range(2))
        weighted = hierarchical_observation_weights(rows)
        totals = event_weight_totals(weighted)
        self.assertEqual(set(totals), {"E1", "E2"})
        self.assertAlmostEqual(float(totals["E1"]), 0.5, places=12)
        self.assertAlmostEqual(float(totals["E2"]), 0.5, places=12)

    def test_markets_share_event_weight_equally_before_observation_density(self) -> None:
        rows = [obs("E1", "M1", i) for i in range(100)]
        rows.extend(obs("E1", "M2", 1000 + i) for i in range(2))
        rows.append(obs("E2", "M3", 3000))
        weighted = hierarchical_observation_weights(rows)
        by_market = {}
        for row in weighted:
            by_market.setdefault(row["ticker"], Decimal(0))
            by_market[row["ticker"]] += Decimal(row["analysis_weight"])
        self.assertAlmostEqual(float(by_market["M1"]), 0.25, places=12)
        self.assertAlmostEqual(float(by_market["M2"]), 0.25, places=12)
        self.assertAlmostEqual(float(by_market["M3"]), 0.50, places=12)

    def test_band_weights_are_recomputed_from_band_contributors(self) -> None:
        rows = [
            obs("E1", "M1", 1, band="early_5d_to_7d"),
            obs("E1", "M1", 2, band="late_1d_to_3d"),
            obs("E2", "M2", 3, band="late_1d_to_3d"),
        ]
        early = hierarchical_observation_weights(rows, time_band="early_5d_to_7d")
        late = hierarchical_observation_weights(rows, time_band="late_1d_to_3d")
        self.assertEqual(event_weight_totals(early), {"E1": Decimal("1.000000000000000000")})
        late_totals = event_weight_totals(late)
        self.assertAlmostEqual(float(late_totals["E1"]), 0.5, places=12)
        self.assertAlmostEqual(float(late_totals["E2"]), 0.5, places=12)

    def test_outcome_field_is_rejected_even_if_not_used(self) -> None:
        with self.assertRaisesRegex(SportsCalibrationV2DesignError, "forbidden outcome"):
            hierarchical_observation_weights([obs("E1", "M1", 1, result="yes")])

    def test_non_sports_and_invalid_quote_rows_are_not_weighted(self) -> None:
        good = obs("E1", "M1", 1)
        crypto = dict(obs("C1", "CM1", 2), category="Crypto")
        invalid = dict(obs("E1", "M1", 3), valid_quote_observation="false")
        weighted = hierarchical_observation_weights([good, crypto, invalid])
        self.assertEqual(len(weighted), 1)
        self.assertEqual(weighted[0]["event_ticker"], "E1")
        self.assertEqual(weighted[0]["analysis_weight"], "1.000000000000000000")


if __name__ == "__main__":
    unittest.main()
