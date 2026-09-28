"""Versioned outcome-blind schema for Checkpoint-09 historical feasibility.

This is a new experiment family. It does not modify the frozen Checkpoint-08
Sports fixed-anchor design or its staleness decision.
"""

from __future__ import annotations

DATASET_SCHEMA_VERSION = "historical_feasibility_dataset.v1"
EVENT_SCHEMA_VERSION = "historical_feasibility_event.v1"
MARKET_SCHEMA_VERSION = "historical_feasibility_market.v1"
WINDOW_SCHEMA_VERSION = "historical_feasibility_window.v1"
OBSERVATION_SCHEMA_VERSION = "historical_feasibility_observation.v1"
CATEGORY_SUMMARY_SCHEMA_VERSION = "historical_feasibility_category_summary.v1"

TARGET_CATEGORIES = (
    "Sports",
    "Crypto",
    "Climate and Weather",
    "Commodities",
)

WINDOW_START_DAYS_BEFORE_CLOSE = 7
WINDOW_END_DAYS_BEFORE_CLOSE = 1
CANDLE_REQUEST_CHUNK_SECONDS = 24 * 60 * 60

# These are diagnostic coverage bands, not fixed observation anchors. Every
# observation retains exact time_to_close_seconds.
TIME_BANDS = (
    "early_5d_to_7d",
    "middle_3d_to_5d",
    "late_1d_to_3d",
)

# Outcome-blind feasibility gates. They determine whether a category has enough
# usable historical quote support to justify a later predeclared strategy
# experiment. They do not establish an edge.
MIN_FEASIBILITY_EVENTS_PER_CATEGORY = 25
MIN_EVENT_ANY_QUOTE_COVERAGE = 0.80
MIN_MARKET_ANY_QUOTE_COVERAGE = 0.60
MIN_EVENT_BAND_COVERAGE = 0.50
CONCENTRATION_MAX_EVENT_WARNING = 0.20
CONCENTRATION_TOP_DECILE_WARNING = 0.50

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
)

MARKET_FIELDS = LINEAGE_FIELDS + (
    "ticker",
    "event_ticker",
    "category",
    "market_type",
    "status",
    "open_time",
    "close_time",
    "settlement_ts",
    "mve_collection_ticker",
    "is_provisional",
    "selection_hash",
)

WINDOW_FIELDS = LINEAGE_FIELDS + (
    "ticker",
    "event_ticker",
    "category",
    "window_start_ts",
    "window_end_ts",
    "request_chunk_index",
    "request_start_ts",
    "request_end_ts",
    "window_start_days_before_close",
    "window_end_days_before_close",
    "period_interval_minutes",
    "candle_count",
    "quote_pair_count",
    "valid_quote_observation_count",
    "invalid_quote_observation_count",
    "crossed_quote_count",
    "early_valid_count",
    "middle_valid_count",
    "late_valid_count",
)

OBSERVATION_FIELDS = LINEAGE_FIELDS + (
    "ticker",
    "event_ticker",
    "category",
    "source_field_family",
    "end_period_ts",
    "close_time",
    "time_to_close_seconds",
    "time_band",
    "period_interval_minutes",
    "yes_bid_close",
    "yes_ask_close",
    "q_mid",
    "spread",
    "price_close",
    "volume",
    "open_interest",
    "quote_pair_present",
    "crossed_close",
    "valid_quote_observation",
    "exclusion_reason",
)

CATEGORY_SUMMARY_FIELDS = (
    "schema_version",
    "category",
    "target_event_count",
    "event_count",
    "market_count",
    "valid_quote_observation_count",
    "events_with_valid_quote",
    "markets_with_valid_quote",
    "event_any_quote_coverage",
    "market_any_quote_coverage",
    "early_event_coverage",
    "middle_event_coverage",
    "late_event_coverage",
    "events_with_all_three_bands",
    "all_three_band_event_coverage",
    "median_valid_observations_per_event",
    "p90_valid_observations_per_event",
    "max_event_observation_share",
    "top_decile_event_observation_share",
    "sample_target_met",
    "quote_feasibility_pass",
    "concentration_warning",
    "status",
)


def validate_schema_contract() -> None:
    for name, fields in (
        ("event", EVENT_FIELDS),
        ("market", MARKET_FIELDS),
        ("window", WINDOW_FIELDS),
        ("observation", OBSERVATION_FIELDS),
        ("category_summary", CATEGORY_SUMMARY_FIELDS),
    ):
        if len(fields) != len(set(fields)):
            raise ValueError(f"{name} schema contains duplicate field names")
        if "result" in fields:
            raise ValueError(f"{name} schema must not contain outcome field 'result'")

    for fields in (EVENT_FIELDS, MARKET_FIELDS, WINDOW_FIELDS, OBSERVATION_FIELDS):
        missing = set(LINEAGE_FIELDS) - set(fields)
        if missing:
            raise ValueError(f"derived schema missing lineage fields: {sorted(missing)}")

    required_observation = {
        "end_period_ts",
        "close_time",
        "time_to_close_seconds",
        "time_band",
        "yes_bid_close",
        "yes_ask_close",
        "q_mid",
        "spread",
        "valid_quote_observation",
        "exclusion_reason",
    }
    missing = required_observation - set(OBSERVATION_FIELDS)
    if missing:
        raise ValueError(f"observation schema missing fields: {sorted(missing)}")

    if set(TIME_BANDS) != {
        "early_5d_to_7d",
        "middle_3d_to_5d",
        "late_1d_to_3d",
    }:
        raise ValueError("unexpected time-band contract")


validate_schema_contract()
