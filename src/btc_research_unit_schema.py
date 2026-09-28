"""Versioned outcome-blind schema for Checkpoint-10 BTC research-unit inventory."""

from __future__ import annotations

DATASET_SCHEMA_VERSION = "btc_research_unit_inventory.v1"
EVENT_SCHEMA_VERSION = "btc_research_event.v1"
MARKET_SCHEMA_VERSION = "btc_research_market.v1"
SERIES_SUMMARY_SCHEMA_VERSION = "btc_research_series_summary.v1"
CLUSTER_SCHEMA_VERSION = "btc_settlement_cluster.v1"
OVERLAP_SCHEMA_VERSION = "btc_primitive_overlap.v1"

LINEAGE_FIELDS = (
    "run_id",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "route_tier",
)

EVENT_FIELDS = (
    "schema_version",
    *LINEAGE_FIELDS,
    "event_ticker",
    "series_ticker",
    "category",
    "title",
    "sub_title",
    "strike_date",
    "strike_period",
    "mutually_exclusive",
    "bitcoin_scope",
    "scope_confidence",
    "scope_reason",
)

MARKET_FIELDS = (
    "schema_version",
    *LINEAGE_FIELDS,
    "ticker",
    "event_ticker",
    "series_ticker",
    "market_type",
    "title",
    "subtitle",
    "yes_sub_title",
    "no_sub_title",
    "open_time",
    "close_time",
    "expected_expiration_time",
    "expiration_time",
    "settlement_ts",
    "occurrence_datetime",
    "strike_type",
    "floor_strike",
    "cap_strike",
    "functional_strike",
    "custom_strike_json",
    "rules_primary_sha256",
    "rules_secondary_sha256",
    "settlement_family",
    "cluster_status",
    "settlement_cluster_id",
    "candidate_group_key",
    "primitive_ids_json",
    "cluster_reason",
)

CLUSTER_FIELDS = (
    "schema_version",
    "run_id",
    "settlement_cluster_id",
    "cluster_status",
    "series_ticker",
    "settlement_family",
    "event_tickers_json",
    "market_tickers_json",
    "market_count",
    "event_count",
    "earliest_open_time",
    "latest_close_time",
    "primitive_ids_json",
    "source_lineage_json",
    "cluster_reason",
)

OVERLAP_FIELDS = (
    "schema_version",
    "run_id",
    "primitive_id",
    "cluster_id_a",
    "cluster_id_b",
    "relation",
    "split_policy",
    "source_lineage_json",
)

SERIES_SUMMARY_FIELDS = (
    "schema_version",
    "run_id",
    "series_ticker",
    "bitcoin_scope",
    "discovered_settled_event_count",
    "sampled_event_count",
    "event_sample_cap",
    "event_sampling_rule",
    "event_count",
    "market_count",
    "settlement_cluster_count",
    "resolved_cluster_count",
    "candidate_cluster_count",
    "unresolved_cluster_count",
    "market_type_set_json",
    "strike_type_set_json",
    "earliest_close_time",
    "latest_close_time",
    "source_lineage_json",
)

# Outcome and market-state fields are intentionally absent from every derived
# schema. Raw API payloads may contain them; the inventory transformation must
# never materialize or use them.
FORBIDDEN_DERIVED_FIELDS = frozenset(
    {
        "result",
        "settlement_value",
        "settlement_value_dollars",
        "expiration_value",
        "yes_bid",
        "yes_ask",
        "no_bid",
        "no_ask",
        "yes_price",
        "no_price",
        "price",
        "volume",
        "volume_fp",
        "open_interest",
        "open_interest_fp",
        "liquidity",
        "liquidity_dollars",
    }
)


def validate_schema_contract() -> None:
    schemas = {
        "event": EVENT_FIELDS,
        "market": MARKET_FIELDS,
        "cluster": CLUSTER_FIELDS,
        "overlap": OVERLAP_FIELDS,
        "series_summary": SERIES_SUMMARY_FIELDS,
    }
    for name, fields in schemas.items():
        if len(fields) != len(set(fields)):
            raise ValueError(f"{name} schema contains duplicate fields")
        forbidden = FORBIDDEN_DERIVED_FIELDS.intersection(fields)
        if forbidden:
            raise ValueError(
                f"{name} schema contains forbidden outcome/market-state fields: "
                f"{sorted(forbidden)}"
            )

    required_market = {
        "event_ticker",
        "series_ticker",
        "open_time",
        "close_time",
        "settlement_cluster_id",
        "cluster_status",
        "primitive_ids_json",
    }
    missing = required_market - set(MARKET_FIELDS)
    if missing:
        raise ValueError(f"market schema missing required fields: {sorted(missing)}")


validate_schema_contract()
