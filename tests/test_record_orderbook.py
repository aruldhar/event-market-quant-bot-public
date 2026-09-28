from __future__ import annotations

import unittest

from record_orderbook import ORDERBOOK_CSV_FIELDS, build_orderbook_row
from src.kalshi_public import RawRecordReference, SourcedOrderbook


class BuildOrderbookRowTests(unittest.TestCase):
    def test_builds_row_with_exact_raw_lineage(self) -> None:
        sourced_orderbook = SourcedOrderbook(
            orderbook={
                "yes_dollars": [
                    ["0.4000", "5.00"],
                    ["0.4200", "3.00"],
                ],
                "no_dollars": [
                    ["0.5500", "8.00"],
                    ["0.5600", "2.00"],
                ],
            },
            raw_record=RawRecordReference(
                source="kalshi_public_rest",
                session_id="kalshi-session-1",
                request_id="request-123",
            ),
        )

        row = build_orderbook_row(
            run_id="record_orderbook_run-1",
            ticker="TEST",
            observed_at_utc="2026-08-03T10:00:00+00:00",
            sourced_orderbook=sourced_orderbook,
        )

        self.assertEqual(list(row), ORDERBOOK_CSV_FIELDS)
        self.assertEqual(row["run_id"], "record_orderbook_run-1")
        self.assertEqual(row["raw_source"], "kalshi_public_rest")
        self.assertEqual(row["raw_session_id"], "kalshi-session-1")
        self.assertEqual(row["raw_request_id"], "request-123")
        self.assertEqual(row["observed_at_utc"], "2026-08-03T10:00:00+00:00")
        self.assertEqual(row["ticker"], "TEST")
        self.assertEqual(row["yes_bid"], "0.4200")
        self.assertEqual(row["yes_ask"], "0.4400")
        self.assertEqual(row["yes_spread"], "0.0200")
        self.assertEqual(row["no_bid"], "0.5600")
        self.assertEqual(row["no_ask"], "0.5800")
        self.assertEqual(row["no_spread"], "0.0200")

    def test_empty_orderbook_preserves_lineage(self) -> None:
        sourced_orderbook = SourcedOrderbook(
            orderbook={
                "yes_dollars": [],
                "no_dollars": [],
            },
            raw_record=RawRecordReference(
                source="kalshi_public_rest",
                session_id="kalshi-session-empty",
                request_id="request-empty",
            ),
        )

        row = build_orderbook_row(
            run_id="record_orderbook_empty-run",
            ticker="EMPTY",
            observed_at_utc="2026-08-03T10:01:00+00:00",
            sourced_orderbook=sourced_orderbook,
        )

        self.assertEqual(row["raw_request_id"], "request-empty")
        self.assertEqual(row["yes_bid"], "")
        self.assertEqual(row["yes_ask"], "")
        self.assertEqual(row["no_bid"], "")
        self.assertEqual(row["no_ask"], "")


if __name__ == "__main__":
    unittest.main()
