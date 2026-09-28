from __future__ import annotations

import unittest

from src.sports_historical_schema import (
    ANCHOR_FIELDS,
    CANDLE_FIELDS,
    DATASET_SCHEMA_VERSION,
    EVENT_FIELDS,
    LINEAGE_FIELDS,
    PRE_STALENESS_COLLECTOR_TABLES,
    STALENESS_PILOT_ALLOWED_TABLES,
    TABLES,
    validate_schema_contract,
)


class SportsHistoricalSchemaTests(unittest.TestCase):
    def test_contract_is_valid(self) -> None:
        validate_schema_contract()
        self.assertEqual(DATASET_SCHEMA_VERSION, "sports_historical_dataset.v1")

    def test_every_table_carries_exact_raw_lineage_fields(self) -> None:
        for name, contract in TABLES.items():
            with self.subTest(table=name):
                self.assertTrue(set(LINEAGE_FIELDS).issubset(contract.fields))

    def test_staleness_pilot_tables_do_not_expose_result(self) -> None:
        self.assertNotIn("outcomes", STALENESS_PILOT_ALLOWED_TABLES)
        self.assertEqual(
            set(PRE_STALENESS_COLLECTOR_TABLES),
            set(STALENESS_PILOT_ALLOWED_TABLES),
        )
        for name in STALENESS_PILOT_ALLOWED_TABLES:
            with self.subTest(table=name):
                self.assertFalse(TABLES[name].outcome_sensitive)
                self.assertNotIn("result", TABLES[name].fields)

    def test_outcome_table_is_isolated_and_not_collected_before_freeze(self) -> None:
        self.assertTrue(TABLES["outcomes"].outcome_sensitive)
        self.assertFalse(TABLES["outcomes"].collected_before_staleness_freeze)
        self.assertIn("result", TABLES["outcomes"].fields)

    def test_baseline_trades_are_not_required_before_staleness_freeze(self) -> None:
        self.assertFalse(TABLES["trades"].collected_before_staleness_freeze)
        self.assertNotIn("trades", PRE_STALENESS_COLLECTOR_TABLES)

    def test_event_table_owns_source_native_category_and_series(self) -> None:
        self.assertIn("event_ticker", EVENT_FIELDS)
        self.assertIn("series_ticker", EVENT_FIELDS)
        self.assertIn("category", EVENT_FIELDS)
        self.assertNotIn("category", CANDLE_FIELDS)
        self.assertNotIn("series_ticker", CANDLE_FIELDS)

    def test_anchor_table_preserves_zero_candle_observation_state(self) -> None:
        for field in (
            "anchor_name",
            "anchor_ts",
            "window_start_ts",
            "window_end_ts",
            "candle_count",
            "quote_pair_count",
            "latest_real_candle_ts",
            "latest_quote_pair_ts",
            "latest_quote_age_seconds",
        ):
            self.assertIn(field, ANCHOR_FIELDS)

    def test_candle_schema_keeps_source_family_and_quality_flags(self) -> None:
        for field in (
            "anchor_name",
            "anchor_ts",
            "source_field_family",
            "end_period_ts",
            "yes_bid_close",
            "yes_ask_close",
            "quote_pair_present",
            "crossed_close",
        ):
            self.assertIn(field, CANDLE_FIELDS)


if __name__ == "__main__":
    unittest.main()
