"""Versioned outcome-blind schema for Checkpoint-10 BTC-family quote feasibility."""

from __future__ import annotations

DATASET_SCHEMA_VERSION = "btc_family_quote_feasibility.v1"
CLUSTER_SCHEMA_VERSION = "btc_family_quote_cluster.v1"
PROBE_SCHEMA_VERSION = "btc_family_quote_probe_market.v1"
WINDOW_SCHEMA_VERSION = "btc_family_quote_window.v1"
OBSERVATION_SCHEMA_VERSION = "btc_family_quote_observation.v1"
SUMMARY_SCHEMA_VERSION = "btc_family_quote_summary.v1"

TARGET_FAMILIES = ("KXBTC15M", "KXBTC", "KXBTCD")
TARGET_CLUSTERS_PER_FAMILY = 20
LADDER_PROBES_PER_CLUSTER = 3
MODERN_LADDER_REGIME_ID = "brti_60s_simple_mean_untrimmed"

MIN_CLUSTER_ANY_QUOTE_COVERAGE = 0.80
MIN_PROBE_MARKET_ANY_QUOTE_COVERAGE = 0.60
MIN_CLUSTER_BAND_COVERAGE = 0.50
MIN_LADDER_ALL_PROBE_ALL_BANDS_COVERAGE = 0.50

TIME_BANDS = ("early", "middle", "late")

CLUSTER_FIELDS = (
    "schema_version",
    "run_id",
    "inventory_run_id",
    "family",
    "series_ticker",
    "event_ticker",
    "source_cluster_id",
    "regime_id",
    "primitive_ids_json",
    "open_time",
    "close_time",
    "duration_seconds",
    "selection_hash",
    "probe_market_count",
    "cluster_selection_rule",
)

PROBE_FIELDS = (
    "schema_version",
    "run_id",
    "inventory_run_id",
    "family",
    "event_ticker",
    "source_cluster_id",
    "ticker",
    "probe_role",
    "strike_type",
    "floor_strike",
    "cap_strike",
    "functional_strike",
    "open_time",
    "close_time",
    "settlement_ts",
    "inventory_raw_source",
    "inventory_raw_session_id",
    "inventory_raw_request_id",
)

NEW_LINEAGE_FIELDS = (
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "route_tier",
)

WINDOW_FIELDS = (
    "schema_version",
    "run_id",
    "inventory_run_id",
    *NEW_LINEAGE_FIELDS,
    "family",
    "event_ticker",
    "source_cluster_id",
    "ticker",
    "probe_role",
    "open_time",
    "close_time",
    "duration_seconds",
    "period_interval_minutes",
    "candle_count",
    "valid_quote_observation_count",
    "invalid_quote_observation_count",
    "crossed_quote_count",
    "early_valid_count",
    "middle_valid_count",
    "late_valid_count",
)

OBSERVATION_FIELDS = (
    "schema_version",
    "run_id",
    "inventory_run_id",
    *NEW_LINEAGE_FIELDS,
    "family",
    "event_ticker",
    "source_cluster_id",
    "ticker",
    "probe_role",
    "source_field_family",
    "end_period_ts",
    "open_time",
    "close_time",
    "duration_seconds",
    "time_to_close_seconds",
    "normalized_time_remaining",
    "time_band",
    "period_interval_minutes",
    "yes_bid_close",
    "yes_ask_close",
    "q_mid",
    "spread",
    "quote_pair_present",
    "crossed_close",
    "valid_quote_observation",
    "exclusion_reason",
)

SUMMARY_FIELDS = (
    "schema_version",
    "family",
    "target_cluster_count",
    "cluster_count",
    "probe_market_count",
    "valid_quote_observation_count",
    "clusters_with_valid_quote",
    "probe_markets_with_valid_quote",
    "cluster_any_quote_coverage",
    "probe_market_any_quote_coverage",
    "early_cluster_coverage",
    "middle_cluster_coverage",
    "late_cluster_coverage",
    "all_three_band_cluster_coverage",
    "all_probe_early_cluster_coverage",
    "all_probe_middle_cluster_coverage",
    "all_probe_late_cluster_coverage",
    "all_probe_all_three_band_cluster_coverage",
    "median_duration_seconds",
    "min_duration_seconds",
    "max_duration_seconds",
    "sample_target_met",
    "base_quote_feasibility_pass",
    "ladder_breadth_gate_applicable",
    "ladder_breadth_pass",
    "status",
)

FORBIDDEN_FIELDS = frozenset({"result", "settlement_value", "expiration_value"})


def validate_schema_contract() -> None:
    for label, fields in (
        ("cluster", CLUSTER_FIELDS),
        ("probe", PROBE_FIELDS),
        ("window", WINDOW_FIELDS),
        ("observation", OBSERVATION_FIELDS),
        ("summary", SUMMARY_FIELDS),
    ):
        if len(fields) != len(set(fields)):
            raise ValueError(f"{label} schema contains duplicate fields")
        bad = FORBIDDEN_FIELDS.intersection(fields)
        if bad:
            raise ValueError(f"{label} schema contains forbidden outcome fields: {sorted(bad)}")

    if set(TIME_BANDS) != {"early", "middle", "late"}:
        raise ValueError("unexpected normalized time-band contract")


validate_schema_contract()
