import unittest
from datetime import datetime, timedelta, timezone

from analyze_kxbtc15m_market_dynamics import (
    Market,
    Quote,
    elapsed_minute,
    evaluate_anchor,
    lower_side,
    price_band,
    time_phase,
)


UTC = timezone.utc


def quote(second: int, yes_bid: float, yes_ask: float) -> Quote:
    return Quote(
        time=datetime(2026, 8, 11, 12, 0, tzinfo=UTC) + timedelta(seconds=second),
        ticker="TEST",
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=1 - yes_ask,
        no_ask=1 - yes_bid,
    )


class MarketDynamicsTests(unittest.TestCase):
    def test_price_bands_cover_full_lower_side_range(self) -> None:
        self.assertEqual(price_band(0.09), "00_10c")
        self.assertEqual(price_band(0.10), "10_20c")
        self.assertEqual(price_band(0.29), "20_30c")
        self.assertEqual(price_band(0.49), "40_50c")
        self.assertEqual(price_band(0.50), "50c_plus")

    def test_all_fifteen_elapsed_minutes_are_preserved(self) -> None:
        self.assertEqual(elapsed_minute(0), 1)
        self.assertEqual(elapsed_minute(299.9), 5)
        self.assertEqual(elapsed_minute(300), 6)
        self.assertEqual(elapsed_minute(899), 15)
        self.assertEqual(time_phase(299.9), "01_first_0_5m")
        self.assertEqual(time_phase(300), "02_middle_5_10m")
        self.assertEqual(time_phase(779.9), "03_late_10_13m")
        self.assertEqual(time_phase(780), "04_terminal_13_15m")

    def test_lower_side_uses_executable_ask_and_skips_ties(self) -> None:
        self.assertEqual(lower_side(quote(0, 0.30, 0.32)), "YES")
        tied = Quote(quote(0, 0.49, 0.50).time, "TEST", 0.49, 0.50, 0.49, 0.50)
        self.assertIsNone(lower_side(tied))

    def test_anchor_single_and_two_tranche_recovery(self) -> None:
        quotes = (
            quote(0, 0.38, 0.40),
            quote(5, 0.34, 0.35),
            quote(10, 0.38, 0.39),
            quote(15, 0.40, 0.41),
        )
        market = Market(
            index=1,
            ticker="TEST",
            close=quotes[0].time + timedelta(minutes=15),
            quotes=quotes,
            eligible=True,
            exclusion_reasons=(),
        )
        row = evaluate_anchor(market, 0)
        assert row is not None
        self.assertFalse(row["single_recovery_30s"])
        self.assertTrue(row["drop_05c_triggered"])
        self.assertAlmostEqual(row["two_tranche_avg_05c"], 0.375)
        self.assertTrue(row["two_tranche_recovery_05c"])

    def test_three_tranche_recovery_requires_second_decline(self) -> None:
        quotes = (
            quote(0, 0.38, 0.40),
            quote(5, 0.33, 0.35),
            quote(10, 0.28, 0.30),
            quote(15, 0.34, 0.36),
        )
        market = Market(1, "TEST", quotes[0].time + timedelta(minutes=15), quotes, True, ())
        row = evaluate_anchor(market, 0)
        assert row is not None
        self.assertTrue(row["second_drop_05c_triggered"])
        self.assertAlmostEqual(row["three_tranche_avg_05c"], 0.35)
        self.assertFalse(row["three_tranche_recovery_05c"])


if __name__ == "__main__":
    unittest.main()
