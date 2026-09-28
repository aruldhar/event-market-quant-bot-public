"""Checkpoint-08 source-registry additions for Kalshi Sports history.

This module is data-only and deterministic. It does not make network requests.
The companion CLI applies these additions to configs/source_registry.json only
after the existing registry has passed the normal project validator.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

REVIEWED_AT_UTC = "2026-08-09T05:18:48Z"
QUALITY_POLICY_ID = "read_only_source_quality.v1"
RAW_SOURCE_NAME = "kalshi_public_rest"
BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

CHECKPOINT08_SOURCE_IDS = (
    "kalshi.public_rest.historical_cutoff.v1",
    "kalshi.public_rest.historical_markets.v1",
    "kalshi.public_rest.historical_market.v1",
    "kalshi.public_rest.event.v1",
    "kalshi.public_rest.historical_market_candlesticks.v1",
    "kalshi.public_rest.historical_trades.v1",
    "kalshi.public_rest.market_candlesticks.v1",
)


def _timestamp(path: str, meaning: str, *, required: bool = False) -> dict[str, Any]:
    return {
        "json_path": path,
        "meaning": meaning,
        "required": required,
        "validation_state": "validated",
    }


def _source(
    *,
    source_id: str,
    name: str,
    roles: list[str],
    path_template: str,
    official_urls: list[str],
    timestamps: list[dict[str, Any]],
    notes: str,
    auth_notes: str,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "name": name,
        "owner": "Kalshi",
        "roles": roles,
        "market_scope": ["all_public_sports_markets"],
        "transport": "https_rest",
        "endpoint_identity": {
            "method": "GET",
            "base_url": BASE_URL,
            "path_template": path_template,
        },
        "official_urls": official_urls,
        "authentication": {
            "mode": "none",
            "validation_state": "validated",
            "conflict_status": "no_current_conflict",
            "notes": auth_notes,
        },
        "expected_timestamp_fields": timestamps,
        "settlement_role": "none",
        "settlement_validation_state": "validated",
        "collection_state": "active",
        "validation_state": "validated",
        "quality_policy_id": QUALITY_POLICY_ID,
        "raw_source_name": RAW_SOURCE_NAME,
        "evidence": [
            {
                "url": url,
                "claim": (
                    "Official endpoint documentation reviewed for Checkpoint 08; "
                    "the project's raw-first public validation run on "
                    "2026-08-09 UTC observed the endpoint without authentication."
                ),
                "reviewed_at_utc": REVIEWED_AT_UTC,
            }
            for url in official_urls
        ],
        "notes": notes,
    }


def checkpoint08_sources() -> list[dict[str, Any]]:
    """Return canonical source records added after the successful live probe."""

    return [
        _source(
            source_id="kalshi.public_rest.historical_cutoff.v1",
            name="Kalshi public historical cutoff REST endpoint",
            roles=["historical_routing_control", "sports_historical_validation"],
            path_template="/historical/cutoff",
            official_urls=[
                "https://docs.kalshi.com/api-reference/historical/get-historical-cutoff-timestamps",
                "https://docs.kalshi.com/getting_started/historical_data",
            ],
            timestamps=[
                _timestamp(
                    "$.market_settled_ts",
                    "Routing cutoff for markets and their candlesticks.",
                    required=True,
                ),
                _timestamp(
                    "$.trades_created_ts",
                    "Routing cutoff for public trade history.",
                    required=True,
                ),
                _timestamp(
                    "$.orders_updated_ts",
                    "Routing cutoff for historical orders; recorded but unused by the Sports collector.",
                    required=True,
                ),
                _timestamp(
                    "$.market_positions_last_updated_ts",
                    "Optional historical market-position cutoff observed in the current response shape; unused by this checkpoint.",
                ),
            ],
            auth_notes=(
                "Checkpoint-08 raw-first validation successfully called the public cutoff "
                "endpoint without credentials."
            ),
            notes=(
                "The 2026-08-09 validation captured market_settled_ts="
                "2026-06-09T00:00:00Z. Cutoffs are routing controls, not fixed constants; "
                "collectors must fetch the current cutoff at run time."
            ),
        ),
        _source(
            source_id="kalshi.public_rest.historical_markets.v1",
            name="Kalshi public historical market-list REST endpoint",
            roles=["historical_market_metadata", "sports_historical_discovery"],
            path_template="/historical/markets",
            official_urls=[
                "https://docs.kalshi.com/api-reference/historical/get-historical-markets",
                "https://docs.kalshi.com/getting_started/historical_data",
            ],
            timestamps=[
                _timestamp("$.markets[*].open_time", "Market open time.", required=True),
                _timestamp("$.markets[*].close_time", "Market close time.", required=True),
                _timestamp(
                    "$.markets[*].settlement_ts",
                    "Market settlement timestamp used to verify historical-tier routing.",
                    required=True,
                ),
                _timestamp("$.markets[*].created_time", "Market creation time."),
                _timestamp("$.markets[*].updated_time", "Market metadata update time."),
            ],
            auth_notes=(
                "Checkpoint-08 raw-first validation discovered archived Sports markets "
                "through this endpoint without credentials."
            ),
            notes=(
                "Validated for archived market discovery only. Sports classification is "
                "confirmed through event metadata rather than inferred from ticker text."
            ),
        ),
        _source(
            source_id="kalshi.public_rest.historical_market.v1",
            name="Kalshi public historical single-market REST endpoint",
            roles=["historical_market_metadata", "sports_historical_collection"],
            path_template="/historical/markets/{ticker}",
            official_urls=[
                "https://docs.kalshi.com/api-reference/historical/get-historical-market",
                "https://docs.kalshi.com/getting_started/historical_data",
            ],
            timestamps=[
                _timestamp("$.market.open_time", "Market open time.", required=True),
                _timestamp("$.market.close_time", "Market close time.", required=True),
                _timestamp(
                    "$.market.settlement_ts",
                    "Market settlement timestamp used to verify historical-tier routing.",
                    required=True,
                ),
                _timestamp("$.market.created_time", "Market creation time."),
                _timestamp("$.market.updated_time", "Market metadata update time."),
            ],
            auth_notes=(
                "Checkpoint-08 raw-first validation fetched KXITFMATCH-26JUN08LEGBRA-LEG "
                "from this endpoint without credentials."
            ),
            notes=(
                "The raw market object may contain final result fields. Checkpoint-08 "
                "staleness logic must not inspect those fields; derived outcomes are kept "
                "in a separate outcome table."
            ),
        ),
        _source(
            source_id="kalshi.public_rest.event.v1",
            name="Kalshi public single-event REST endpoint",
            roles=["execution_event_metadata", "historical_event_identity", "sports_historical_collection"],
            path_template="/events/{event_ticker}",
            official_urls=[
                "https://docs.kalshi.com/api-reference/events/get-event",
            ],
            timestamps=[
                _timestamp("$.event.strike_date", "Event strike or occurrence date when present."),
                _timestamp("$.event.last_updated_ts", "Event metadata update timestamp when present."),
            ],
            auth_notes=(
                "Checkpoint-08 raw-first validation used the single-event endpoint without "
                "credentials to verify category=Sports and series identity for an archived market."
            ),
            notes=(
                "Events remain on the normal event surface even when associated markets have "
                "moved behind the historical market cutoff."
            ),
        ),
        _source(
            source_id="kalshi.public_rest.historical_market_candlesticks.v1",
            name="Kalshi public historical market-candlesticks REST endpoint",
            roles=["historical_quote_candlesticks", "sports_historical_collection"],
            path_template="/historical/markets/{ticker}/candlesticks",
            official_urls=[
                "https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks",
                "https://docs.kalshi.com/getting_started/historical_data",
            ],
            timestamps=[
                _timestamp(
                    "$.candlesticks[*].end_period_ts",
                    "Unix timestamp marking the candlestick period end.",
                    required=True,
                ),
            ],
            auth_notes=(
                "Checkpoint-08 raw-first validation retrieved non-empty one-minute historical "
                "candles without credentials."
            ),
            notes=(
                "The observed historical field family uses yes_bid/yes_ask/price close fields "
                "named 'close', not the live endpoint's 'close_dollars'. The collector must "
                "normalize explicitly while preserving exact raw lineage."
            ),
        ),
        _source(
            source_id="kalshi.public_rest.historical_trades.v1",
            name="Kalshi public historical trades REST endpoint",
            roles=["historical_trade_prints", "sports_historical_collection"],
            path_template="/historical/trades",
            official_urls=[
                "https://docs.kalshi.com/api-reference/historical/get-historical-trades",
                "https://docs.kalshi.com/getting_started/historical_data",
            ],
            timestamps=[
                _timestamp(
                    "$.trades[*].created_time",
                    "Trade creation/fill timestamp reported by Kalshi.",
                    required=True,
                ),
            ],
            auth_notes=(
                "Checkpoint-08 raw-first validation retrieved historical public trades without credentials."
            ),
            notes=(
                "The official historical-trades endpoint and Historical Data guide support this "
                "route. The cutoff reference currently contains inconsistent prose referring to "
                "historical fills; the project preserves that documentation inconsistency rather "
                "than silently treating it as resolved."
            ),
        ),
        _source(
            source_id="kalshi.public_rest.market_candlesticks.v1",
            name="Kalshi public live single-market candlesticks REST endpoint",
            roles=["live_quote_candlesticks", "sports_historical_collection"],
            path_template="/series/{series_ticker}/markets/{ticker}/candlesticks",
            official_urls=[
                "https://docs.kalshi.com/api-reference/market/get-market-candlesticks",
                "https://docs.kalshi.com/getting_started/historical_data",
            ],
            timestamps=[
                _timestamp(
                    "$.candlesticks[*].end_period_ts",
                    "Unix timestamp marking the candlestick period end.",
                    required=True,
                ),
            ],
            auth_notes=(
                "Checkpoint-08 raw-first validation retrieved non-empty live one-minute Sports "
                "candles without credentials."
            ),
            notes=(
                "The live field family uses close_dollars. For Checkpoint 08, "
                "include_latest_before_start must remain false so synthetic continuity candles "
                "cannot satisfy a real-candle anchor."
            ),
        ),
    ]


def apply_checkpoint08_registry_updates(registry: Mapping[str, Any]) -> dict[str, Any]:
    """Return an updated registry without mutating the input mapping."""

    updated = deepcopy(dict(registry))
    if updated.get("schema") != "source_registry.v1":
        raise ValueError("Checkpoint-08 migration requires source_registry.v1")

    sources = updated.get("sources")
    policies = updated.get("quality_policies")
    if not isinstance(sources, list) or not isinstance(policies, list):
        raise ValueError("registry must contain list-valued sources and quality_policies")

    ids = [source.get("source_id") for source in sources if isinstance(source, dict)]
    if len(ids) != len(set(ids)):
        raise ValueError("registry contains duplicate source IDs before Checkpoint-08 migration")

    event_source = next(
        (
            source
            for source in sources
            if isinstance(source, dict)
            and source.get("source_id") == "kalshi.public_rest.events.v1"
        ),
        None,
    )
    if event_source is None:
        raise ValueError("required existing source kalshi.public_rest.events.v1 is missing")

    event_source.setdefault("roles", [])
    if "sports_historical_validation" not in event_source["roles"]:
        event_source["roles"].append("sports_historical_validation")
    event_source["collection_state"] = "active"
    event_source["validation_state"] = "validated"
    auth = event_source.get("authentication")
    if not isinstance(auth, dict):
        raise ValueError("existing Kalshi events source has malformed authentication metadata")
    auth["validation_state"] = "validated"
    auth["notes"] = (
        "Kalshi documents GET /events as public event discovery. Checkpoint-08 raw-first "
        "validation also used it without credentials to select a currently active Sports "
        "market with positive 24-hour volume."
    )
    event_source["notes"] = (
        "Active read-only event discovery for the opportunity census and Checkpoint-08 Sports "
        "historical routing validation. It remains metadata only and does not authorize trading."
    )

    by_id = {
        source.get("source_id"): source
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("source_id"), str)
    }
    canonical = checkpoint08_sources()
    existing_new = set(CHECKPOINT08_SOURCE_IDS).intersection(by_id)
    if existing_new and existing_new != set(CHECKPOINT08_SOURCE_IDS):
        raise ValueError(
            "partial Checkpoint-08 source migration detected; refusing to guess how to merge"
        )

    if not existing_new:
        sources.extend(canonical)
    else:
        canonical_by_id = {source["source_id"]: source for source in canonical}
        for index, source in enumerate(sources):
            source_id = source.get("source_id") if isinstance(source, dict) else None
            if source_id in canonical_by_id:
                sources[index] = deepcopy(canonical_by_id[source_id])

    policy = next(
        (
            policy
            for policy in policies
            if isinstance(policy, dict) and policy.get("policy_id") == QUALITY_POLICY_ID
        ),
        None,
    )
    if policy is None:
        raise ValueError(f"required quality policy {QUALITY_POLICY_ID!r} is missing")
    scope = policy.get("scope_source_ids")
    if not isinstance(scope, list):
        raise ValueError("quality policy scope_source_ids must be a list")
    for source_id in CHECKPOINT08_SOURCE_IDS:
        if source_id not in scope:
            scope.append(source_id)

    updated["reviewed_at_utc"] = REVIEWED_AT_UTC
    return updated
