from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import record_btc15m_continuous as continuous
from record_btc15m_continuous import (
    ContinuousCaptureError,
    OpenMarket,
    parse_args,
    parse_completed_manifest,
    parse_scan_output,
    recording_seconds,
    select_current_market,
    should_continue,
)


class ContinuousBtc15mParsingTests(unittest.TestCase):
    def test_parses_scan_output(self) -> None:
        output = """
Found 2 open Bitcoin-related markets:

[1] KXBTC15M-26AUG111245-45
    BTC price up in next 15 mins?
    closes: 2026-08-11T16:45:00Z

[2] KXBTC15M-26AUG111300-00
    BTC price up in next 15 mins?
    closes: 2026-08-11T17:00:00Z
"""
        markets = parse_scan_output(output)

        self.assertEqual(
            [market.ticker for market in markets],
            [
                "KXBTC15M-26AUG111245-45",
                "KXBTC15M-26AUG111300-00",
            ],
        )
        self.assertEqual(
            markets[0].close_time,
            datetime(2026, 8, 11, 16, 45, tzinfo=timezone.utc),
        )

    def test_selects_earliest_unseen_open_market(self) -> None:
        now = datetime(2026, 8, 11, 16, 40, tzinfo=timezone.utc)
        markets = [
            OpenMarket("OLD", now - timedelta(seconds=1)),
            OpenMarket("FIRST", now + timedelta(minutes=5)),
            OpenMarket("SECOND", now + timedelta(minutes=20)),
        ]

        selected = select_current_market(
            markets,
            now_utc=now,
            seen_tickers={"SECOND"},
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.ticker, "FIRST")

    def test_recording_duration_includes_grace_and_rounds_up(self) -> None:
        now = datetime(2026, 8, 11, 16, 40, 0, 250000, tzinfo=timezone.utc)
        close = datetime(2026, 8, 11, 16, 45, tzinfo=timezone.utc)

        seconds = recording_seconds(
            close_time=close,
            now_utc=now,
            post_close_grace_seconds=2.0,
        )

        self.assertEqual(seconds, 302)

    def test_completed_manifest_path_is_extracted(self) -> None:
        output = """
Finished. No orders were placed.
Completed manifest: data\\manifests\\2026\\08\\11\\record_orderbook_test.json
"""
        path = parse_completed_manifest(output)
        self.assertEqual(
            str(path),
            "data\\manifests\\2026\\08\\11\\record_orderbook_test.json",
        )

    def test_missing_manifest_is_failure(self) -> None:
        with self.assertRaises(ContinuousCaptureError):
            parse_completed_manifest("Finished without a manifest line")

    def test_continuous_mode_has_no_market_limit(self) -> None:
        self.assertTrue(
            should_continue(completed_markets=10_000, continuous=True, markets=None)
        )

    def test_bounded_mode_stops_at_target(self) -> None:
        self.assertTrue(
            should_continue(completed_markets=7, continuous=False, markets=8)
        )
        self.assertFalse(
            should_continue(completed_markets=8, continuous=False, markets=8)
        )

    def test_continuous_cli_mode(self) -> None:
        args = parse_args(["--continuous", "--interval", "0.5"])
        self.assertTrue(args.continuous)
        self.assertIsNone(args.markets)

    def test_default_remains_bounded_eight_markets(self) -> None:
        args = parse_args([])
        self.assertFalse(args.continuous)
        self.assertEqual(args.markets, 8)

    def test_windows_sleep_inhibitor_sets_and_restores_execution_state(self) -> None:
        calls: list[int] = []

        def fake_set(flags: int) -> bool:
            calls.append(flags)
            return True

        with mock.patch.object(continuous.sys, "platform", "win32"), mock.patch.object(
            continuous, "_set_windows_execution_state", side_effect=fake_set
        ):
            with continuous.keep_system_awake(enabled=True) as active:
                self.assertTrue(active)

        self.assertEqual(
            calls,
            [continuous._ES_CONTINUOUS | continuous._ES_SYSTEM_REQUIRED, continuous._ES_CONTINUOUS],
        )


if __name__ == "__main__":
    unittest.main()
