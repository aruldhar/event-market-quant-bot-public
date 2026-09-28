"""Versioned derived-data contract for Checkpoint-08 Kalshi Sports history.

The raw HTTP archive remains the source of truth. This module defines the
normalized tables used by the historical collector and the later outcome-blind
staleness pilot.

Important blinding rule: final YES/NO results exist in raw historical market
responses, but the collector does not materialize the outcome table before the
staleness rule is frozen.
"""

from __future__ import annotations

from dataclasses import dataclass

DATASET_SCHEMA_VERSION = "sports_historical_dataset.v1"
EVENT_SCHEMA_VERSION = "sports_historical_event.v1"
MARKET_SCHEMA_VERSION = "sports_historical_market.v1"
ANCHOR_SCHEMA_VERSION = "sports_historical_anchor.v1"
CANDLE_SCHEMA_VERSION = "sports_historical_candle.v1"
TRADE_SCHEMA_VERSION = "sports_historical_trade.v1"
OUTCOME_SCHEMA_VERSION = "sports_historical_outcome.v1"

ANCHOR_DAYS = {"7d": 7, "3d": 3, "1d": 1}

LINEAGE_FIELDS = (
    "run_id",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "route_tier",
)

EVENT_FIELDS = LINEAGE_FIELDS + (
    "event_ticker",
    "series_ticker",
    "category",
    "mutually_exclusive",
    "strike_date",
)

MARKET_FIELDS = LINEAGE_FIELDS + (
    "ticker",
    "event_ticker",
    "market_type",
    "status",
    "open_time",
    "close_time",
    "settlement_ts",
    "mve_collection_ticker",
    "is_provisional",
)

ANCHOR_FIELDS = LINEAGE_FIELDS + (
    "ticker",
    "anchor_name",
    "anchor_ts",
    "window_start_ts",
    "window_end_ts",
    "candle_count",
    "quote_pair_count",
    "latest_real_candle_ts",
    "latest_quote_pair_ts",
    "latest_quote_age_seconds",
)

CANDLE_FIELDS = LINEAGE_FIELDS + (
    "ticker",
    "anchor_name",
    "anchor_ts",
    "source_field_family",
    "end_period_ts",
    "period_interval_minutes",
    "yes_bid_close",
    "yes_ask_close",
    "price_close",
    "volume",
    "open_interest",
    "quote_pair_present",
    "crossed_close",
)

TRADE_FIELDS = LINEAGE_FIELDS + (
    "ticker",
    "trade_id",
    "created_time",
    "count_fp",
    "yes_price_dollars",
    "no_price_dollars",
    "taker_side",
)

OUTCOME_FIELDS = LINEAGE_FIELDS + (
    "ticker",
    "event_ticker",
    "result",
)


@dataclass(frozen=True)
class TableContract:
    schema_version: str
    fields: tuple[str, ...]
    outcome_sensitive: bool
    collected_before_staleness_freeze: bool


TABLES = {
    "events": TableContract(EVENT_SCHEMA_VERSION, EVENT_FIELDS, False, True),
    "markets": TableContract(MARKET_SCHEMA_VERSION, MARKET_FIELDS, False, True),
    "anchors": TableContract(ANCHOR_SCHEMA_VERSION, ANCHOR_FIELDS, False, True),
    "candles": TableContract(CANDLE_SCHEMA_VERSION, CANDLE_FIELDS, False, True),
    "trades": TableContract(TRADE_SCHEMA_VERSION, TRADE_FIELDS, False, False),
    "outcomes": TableContract(OUTCOME_SCHEMA_VERSION, OUTCOME_FIELDS, True, False),
}

STALENESS_PILOT_ALLOWED_TABLES = frozenset(
    {"events", "markets", "anchors", "candles"}
)
PRE_STALENESS_COLLECTOR_TABLES = (
    "events",
    "markets",
    "anchors",
    "candles",
)


def validate_schema_contract() -> None:
    """Fail if the schema violates lineage, relationship, or blinding rules."""

    expected = {"events", "markets", "anchors", "candles", "trades", "outcomes"}
    if set(TABLES) != expected:
        raise ValueError("unexpected Sports historical table set")

    for name, contract in TABLES.items():
        if len(contract.fields) != len(set(contract.fields)):
            raise ValueError(f"{name} contains duplicate field names")
        missing_lineage = set(LINEAGE_FIELDS) - set(contract.fields)
        if missing_lineage:
            raise ValueError(f"{name} is missing lineage fields: {sorted(missing_lineage)}")

    for name in STALENESS_PILOT_ALLOWED_TABLES:
        contract = TABLES[name]
        if contract.outcome_sensitive:
            raise ValueError(f"staleness pilot table {name!r} is outcome-sensitive")
        if "result" in contract.fields:
            raise ValueError(f"staleness pilot table {name!r} leaks result")

    if set(PRE_STALENESS_COLLECTOR_TABLES) != set(STALENESS_PILOT_ALLOWED_TABLES):
        raise ValueError("pre-staleness collector table set must equal pilot-safe table set")

    outcomes = TABLES["outcomes"]
    if not outcomes.outcome_sensitive or "result" not in outcomes.fields:
        raise ValueError("outcome table must be explicitly outcome-sensitive and contain result")
    if outcomes.collected_before_staleness_freeze:
        raise ValueError("outcomes must not be materialized before staleness freeze")

    if TABLES["trades"].collected_before_staleness_freeze:
        raise ValueError("baseline collector should not add unnecessary trade collection")

    required_anchor_fields = {
        "anchor_name",
        "anchor_ts",
        "window_start_ts",
        "window_end_ts",
        "candle_count",
        "quote_pair_count",
        "latest_real_candle_ts",
        "latest_quote_pair_ts",
        "latest_quote_age_seconds",
    }
    missing_anchor = required_anchor_fields - set(ANCHOR_FIELDS)
    if missing_anchor:
        raise ValueError(f"anchor schema missing fields: {sorted(missing_anchor)}")

    required_candle_fields = {
        "anchor_name",
        "anchor_ts",
        "source_field_family",
        "end_period_ts",
        "yes_bid_close",
        "yes_ask_close",
        "quote_pair_present",
        "crossed_close",
    }
    missing_candle = required_candle_fields - set(CANDLE_FIELDS)
    if missing_candle:
        raise ValueError(f"candle schema missing fields: {sorted(missing_candle)}")


validate_schema_contract()
