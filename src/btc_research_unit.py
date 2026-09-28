"""Outcome-blind BTC structure inventory and settlement-cluster construction.

The inventory intentionally studies market structure before outcomes, quote data,
features, or models. Raw source responses may contain settlement outcomes, but
this module never reads or materializes those fields.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import re
from typing import Any, Mapping, Protocol, Sequence

from .btc_research_unit_schema import (
    CLUSTER_FIELDS,
    CLUSTER_SCHEMA_VERSION,
    EVENT_FIELDS,
    EVENT_SCHEMA_VERSION,
    FORBIDDEN_DERIVED_FIELDS,
    MARKET_FIELDS,
    MARKET_SCHEMA_VERSION,
    OVERLAP_FIELDS,
    OVERLAP_SCHEMA_VERSION,
    SERIES_SUMMARY_FIELDS,
    SERIES_SUMMARY_SCHEMA_VERSION,
)


class BtcResearchUnitError(RuntimeError):
    """Raised when the outcome-blind BTC inventory is structurally unsafe."""


class _RawReference(Protocol):
    source: str
    session_id: str
    request_id: str


class RawFirstJsonResponse(Protocol):
    payload: dict[str, Any]
    raw_record: _RawReference


class RawFirstJsonClient(Protocol):
    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> RawFirstJsonResponse: ...


@dataclass(frozen=True)
class HistoricalCutoff:
    market_settled_ts: datetime


@dataclass(frozen=True)
class MarketSource:
    market: Mapping[str, Any]
    series_ticker: str
    route_tier: str
    response: RawFirstJsonResponse


@dataclass(frozen=True)
class BtcResearchUnitRows:
    events: tuple[dict[str, str], ...]
    markets: tuple[dict[str, str], ...]
    clusters: tuple[dict[str, str], ...]
    overlaps: tuple[dict[str, str], ...]
    series_summary: tuple[dict[str, str], ...]
    cutoff: HistoricalCutoff
    cutoff_raw_source: str
    cutoff_raw_session_id: str
    cutoff_raw_request_id: str
    event_pages_scanned: int
    discovered_settled_event_count: int
    sampled_event_count: int
    events_per_series: int
    historical_market_pages_scanned: int
    live_market_pages_scanned: int
    bitcoin_series_count: int
    event_scope_fallback_count: int
    event_category_mismatch_count: int
    cross_tier_duplicate_market_count: int


@dataclass(frozen=True)
class CsvPaths:
    events: Path
    markets: Path
    clusters: Path
    overlaps: Path
    series_summary: Path

    def all(self) -> tuple[Path, ...]:
        return (
            self.events,
            self.markets,
            self.clusters,
            self.overlaps,
            self.series_summary,
        )


_BTC_WORD = re.compile(r"(?<![A-Z0-9])BTC(?![A-Z0-9])", re.IGNORECASE)
_BITCOIN_WORD = re.compile(r"\bBITCOIN\b", re.IGNORECASE)
_OTHER_ASSET_WORDS = (
    re.compile(r"\bETH(?:EREUM)?\b", re.IGNORECASE),
    re.compile(r"\bBNB\b", re.IGNORECASE),
    re.compile(r"\bZEC\b", re.IGNORECASE),
    re.compile(r"\bSOL(?:ANA)?\b", re.IGNORECASE),
    re.compile(r"\bXRP\b", re.IGNORECASE),
    re.compile(r"\bDOGE(?:COIN)?\b", re.IGNORECASE),
)


def classify_bitcoin_series(series: Mapping[str, Any]) -> dict[str, str]:
    """Classify whether a Crypto series is BTC-related from series metadata only."""

    category = _optional_text(series.get("category"))
    ticker = _optional_text(series.get("ticker")).upper()
    title = _optional_text(series.get("title"))
    tags_value = series.get("tags", [])
    tags = [str(item) for item in tags_value] if isinstance(tags_value, list) else []

    if category != "Crypto":
        return {
            "bitcoin_scope": "not_bitcoin",
            "scope_confidence": "high",
            "scope_reason": "series_category_not_crypto",
        }

    descriptive_text = " ".join(part for part in (title, *tags) if part)
    ticker_btc = ticker.startswith("KXBTC") or "BTC" in ticker
    text_btc = bool(
        _BTC_WORD.search(descriptive_text) or _BITCOIN_WORD.search(descriptive_text)
    )
    if not ticker_btc and not text_btc:
        return {
            "bitcoin_scope": "not_bitcoin",
            "scope_confidence": "high",
            "scope_reason": "no_bitcoin_identifier_in_series_metadata",
        }

    combined = f"{ticker} {descriptive_text}"
    cross_asset = any(pattern.search(combined) for pattern in _OTHER_ASSET_WORDS)
    if cross_asset:
        return {
            "bitcoin_scope": "bitcoin_cross_asset",
            "scope_confidence": "high" if ticker_btc else "medium",
            "scope_reason": "bitcoin_and_other_asset_identifiers_in_series_metadata",
        }

    return {
        "bitcoin_scope": "bitcoin_only",
        "scope_confidence": "high" if ticker_btc else "medium",
        "scope_reason": (
            "bitcoin_identifier_in_series_ticker"
            if ticker_btc
            else "bitcoin_identifier_in_series_title_or_tags"
        ),
    }


def classify_bitcoin_event(
    event: Mapping[str, Any],
    *,
    series_scope: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Classify BTC event scope, allowing a validated series-level fallback."""

    category = _optional_text(event.get("category"))
    series_ticker = _optional_text(event.get("series_ticker")).upper()
    title = _optional_text(event.get("title"))
    sub_title = _optional_text(event.get("sub_title"))

    # EventData.category is a deprecated compatibility field and is not a
    # safe membership gate. When the caller has already established exact
    # membership in a selected Crypto series, that series identity is the
    # classification authority for BTC scope. We still preserve the event's
    # source-reported category in the derived event row for audit.
    if category != "Crypto" and not (
        series_scope and series_scope.get("bitcoin_scope") in {
            "bitcoin_only",
            "bitcoin_cross_asset",
        }
    ):
        return {
            "bitcoin_scope": "not_bitcoin",
            "scope_confidence": "high",
            "scope_reason": "category_not_crypto_without_selected_series_scope",
        }

    descriptive_text = " ".join(part for part in (title, sub_title) if part)
    ticker_btc = series_ticker.startswith("KXBTC") or "BTC" in series_ticker
    text_btc = bool(
        _BTC_WORD.search(descriptive_text) or _BITCOIN_WORD.search(descriptive_text)
    )
    if ticker_btc or text_btc:
        combined = f"{series_ticker} {descriptive_text}"
        cross_asset = any(pattern.search(combined) for pattern in _OTHER_ASSET_WORDS)
        if cross_asset:
            return {
                "bitcoin_scope": "bitcoin_cross_asset",
                "scope_confidence": "high" if ticker_btc else "medium",
                "scope_reason": "bitcoin_and_other_asset_identifiers_present",
            }
        return {
            "bitcoin_scope": "bitcoin_only",
            "scope_confidence": "high" if ticker_btc else "medium",
            "scope_reason": (
                "bitcoin_identifier_in_series_ticker"
                if ticker_btc
                else "bitcoin_identifier_in_event_text"
            ),
        }

    if series_scope and series_scope.get("bitcoin_scope") in {
        "bitcoin_only",
        "bitcoin_cross_asset",
    }:
        return {
            "bitcoin_scope": str(series_scope["bitcoin_scope"]),
            "scope_confidence": str(series_scope.get("scope_confidence", "medium")),
            "scope_reason": "bitcoin_identity_inherited_from_selected_series_metadata",
        }

    return {
        "bitcoin_scope": "not_bitcoin",
        "scope_confidence": "high",
        "scope_reason": "no_bitcoin_identifier_in_series_or_event_text",
    }


def collect_btc_research_unit_rows(
    client: RawFirstJsonClient,
    *,
    run_id: str,
    max_event_pages_per_series: int = 500,
    events_per_series: int = 25,
    max_market_pages_per_event_per_tier: int = 5,
) -> BtcResearchUnitRows:
    """Collect BTC structural metadata without reading outcomes or market prices.

    Discovery is series-first rather than a global settled-event scan:

    1. Fetch the Crypto series list.
    2. Select BTC-identifiable series using ticker/title/tags only.
    3. Fetch the complete settled-event list separately for each selected series.
    4. Deterministically select up to ``events_per_series`` events per series by
       SHA-256(event_ticker), without using outcomes, prices, volume, or quotes.
    5. Fetch historical/live settled markets by exact event_ticker for only the
       sampled events.

    Event discovery remains complete and fail-closed. Contract-level collection is
    intentionally bounded because this checkpoint is defining market structure, not
    estimating strategy performance over the full historical universe.
    """

    _required_text(run_id, "run_id")
    if max_event_pages_per_series <= 0:
        raise ValueError("max_event_pages_per_series must be positive")
    if events_per_series <= 0:
        raise ValueError("events_per_series must be positive")
    if max_market_pages_per_event_per_tier <= 0:
        raise ValueError("max_market_pages_per_event_per_tier must be positive")

    cutoff_response = client.get_json("/historical/cutoff")
    cutoff = HistoricalCutoff(
        market_settled_ts=_parse_utc(
            cutoff_response.payload.get("market_settled_ts"),
            "historical.cutoff.market_settled_ts",
        )
    )

    # The Series list is the cheap, bounded discovery layer. Kalshi documents
    # category filtering here and series_ticker filtering on GET /events.
    series_response = client.get_json(
        "/series",
        params={
            "category": "Crypto",
            "include_product_metadata": "false",
            "include_volume": "false",
        },
    )
    series_items = series_response.payload.get("series")
    if not isinstance(series_items, list):
        raise BtcResearchUnitError("response field 'series' is not a list")

    selected_series_scope: dict[str, dict[str, str]] = {}
    for index, item in enumerate(series_items):
        if not isinstance(item, Mapping):
            raise BtcResearchUnitError(f"series[{index}] is not an object")
        scope = classify_bitcoin_series(item)
        if scope["bitcoin_scope"] == "not_bitcoin":
            continue
        ticker = _required_text(item.get("ticker"), "series.ticker")
        if ticker in selected_series_scope:
            raise BtcResearchUnitError(f"duplicate series ticker discovered: {ticker}")
        selected_series_scope[ticker] = scope

    if not selected_series_scope:
        raise BtcResearchUnitError(
            "Crypto series discovery returned no BTC-identifiable series; "
            "inventory scope cannot be established"
        )

    event_rows: list[dict[str, str]] = []
    selected_event_tickers: set[str] = set()
    discovered_event_counts: dict[str, int] = {}
    event_scope_fallback_count = 0
    event_category_mismatch_count = 0
    event_pages_scanned = 0

    # Discover the complete settled-event population first. Sampling happens only
    # after a series cursor is exhausted, so the hash sample is deterministic over
    # the complete source-returned series population rather than over an arbitrary
    # early page prefix.
    for series_ticker in sorted(selected_series_scope):
        discovered: list[tuple[Mapping[str, Any], RawFirstJsonResponse, dict[str, str]]] = []
        discovered_tickers: set[str] = set()
        event_cursor = ""
        for _ in range(max_event_pages_per_series):
            params: dict[str, Any] = {
                "status": "settled",
                "series_ticker": series_ticker,
                "limit": 200,
                "with_nested_markets": "false",
            }
            if event_cursor:
                params["cursor"] = event_cursor
            response = client.get_json("/events", params=params)
            event_pages_scanned += 1
            events, event_cursor = _validate_list_response(response.payload, "events")
            for event in events:
                observed_series = _required_text(
                    event.get("series_ticker"), "event.series_ticker"
                )
                if observed_series != series_ticker:
                    raise BtcResearchUnitError(
                        f"series-filtered event query for {series_ticker} returned "
                        f"event from {observed_series}"
                    )
                event_ticker = _required_text(event.get("event_ticker"), "event.event_ticker")
                if event_ticker in discovered_tickers:
                    raise BtcResearchUnitError(
                        f"duplicate event ticker discovered within {series_ticker}: {event_ticker}"
                    )
                discovered_tickers.add(event_ticker)
                if _optional_text(event.get("category")) != "Crypto":
                    event_category_mismatch_count += 1
                direct_scope = classify_bitcoin_event(event)
                scope = classify_bitcoin_event(
                    event, series_scope=selected_series_scope[series_ticker]
                )
                if direct_scope["bitcoin_scope"] == "not_bitcoin":
                    event_scope_fallback_count += 1
                discovered.append((event, response, scope))
            if not event_cursor:
                break
        else:
            if event_cursor:
                raise BtcResearchUnitError(
                    f"settled event discovery for BTC series {series_ticker} "
                    "remained paginated after "
                    f"max_event_pages_per_series={max_event_pages_per_series}; "
                    "partial BTC structure inventory is not accepted"
                )

        discovered_event_counts[series_ticker] = len(discovered)
        sampled = _sample_discovered_events(discovered, limit=events_per_series)
        for event, response, scope in sampled:
            row = build_event_row(
                run_id=run_id,
                event=event,
                response=response,
                scope=scope,
            )
            ticker = row["event_ticker"]
            if ticker in selected_event_tickers:
                raise BtcResearchUnitError(f"duplicate sampled event ticker: {ticker}")
            selected_event_tickers.add(ticker)
            event_rows.append(row)

    market_sources: list[MarketSource] = []
    historical_pages = 0
    live_pages = 0
    duplicate_tickers: set[str] = set()

    # Market collection is event-scoped. KXBTC can contain more than 100,000
    # historical contracts, so a full series-level contract crawl is neither
    # necessary nor appropriate for this structure-design checkpoint. The exact
    # event filter is documented on both live and historical market endpoints.
    for event_row in sorted(event_rows, key=lambda row: (row["series_ticker"], row["event_ticker"])):
        series_ticker = event_row["series_ticker"]
        event_ticker = event_row["event_ticker"]
        historical, pages = _fetch_market_pages(
            client,
            path="/historical/markets",
            route_tier="historical",
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            max_pages=max_market_pages_per_event_per_tier,
            status=None,
        )
        historical_pages += pages
        live, pages = _fetch_market_pages(
            client,
            path="/markets",
            route_tier="live",
            series_ticker=series_ticker,
            event_ticker=event_ticker,
            max_pages=max_market_pages_per_event_per_tier,
            status="settled",
        )
        live_pages += pages
        if not historical and not live:
            raise BtcResearchUnitError(
                f"sampled settled event {event_ticker} returned no markets from either tier"
            )
        reconciled, duplicates = _reconcile_market_sources(
            historical + live,
            cutoff=cutoff,
            selected_event_tickers={event_ticker},
        )
        market_sources.extend(reconciled)
        duplicate_tickers.update(duplicates)

    market_sources.sort(
        key=lambda item: (
            item.series_ticker,
            _optional_text(item.market.get("event_ticker")),
            _optional_text(item.market.get("close_time")),
            _optional_text(item.market.get("ticker")),
        )
    )

    event_scope_by_ticker = {row["event_ticker"]: row for row in event_rows}
    assignments = _build_cluster_assignments(market_sources)
    market_rows = [
        build_market_row(
            run_id=run_id,
            source=source,
            assignment=assignments[
                _required_text(source.market.get("ticker"), "market.ticker")
            ],
        )
        for source in market_sources
    ]
    cluster_rows = build_cluster_rows(run_id=run_id, market_rows=market_rows)
    overlap_rows = build_overlap_rows(run_id=run_id, cluster_rows=cluster_rows)
    series_rows = build_series_summary_rows(
        run_id=run_id,
        event_rows=event_rows,
        market_rows=market_rows,
        cluster_rows=cluster_rows,
        event_scope_by_ticker=event_scope_by_ticker,
        discovered_event_counts=discovered_event_counts,
        event_sample_cap=events_per_series,
    )

    rows = BtcResearchUnitRows(
        events=tuple(event_rows),
        markets=tuple(market_rows),
        clusters=tuple(cluster_rows),
        overlaps=tuple(overlap_rows),
        series_summary=tuple(series_rows),
        cutoff=cutoff,
        cutoff_raw_source=cutoff_response.raw_record.source,
        cutoff_raw_session_id=cutoff_response.raw_record.session_id,
        cutoff_raw_request_id=cutoff_response.raw_record.request_id,
        event_pages_scanned=event_pages_scanned,
        discovered_settled_event_count=sum(discovered_event_counts.values()),
        sampled_event_count=len(event_rows),
        events_per_series=events_per_series,
        historical_market_pages_scanned=historical_pages,
        live_market_pages_scanned=live_pages,
        bitcoin_series_count=len(selected_series_scope),
        event_scope_fallback_count=event_scope_fallback_count,
        event_category_mismatch_count=event_category_mismatch_count,
        cross_tier_duplicate_market_count=len(duplicate_tickers),
    )
    validate_collected_rows(rows, run_id=run_id)
    return rows

def build_event_row(
    *,
    run_id: str,
    event: Mapping[str, Any],
    response: RawFirstJsonResponse,
    scope: Mapping[str, str] | None = None,
) -> dict[str, str]:
    scope = dict(scope or classify_bitcoin_event(event))
    if scope["bitcoin_scope"] == "not_bitcoin":
        raise BtcResearchUnitError("non-Bitcoin event cannot be emitted")
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        **_lineage(run_id, response, "events"),
        "event_ticker": _required_text(event.get("event_ticker"), "event.event_ticker"),
        "series_ticker": _required_text(event.get("series_ticker"), "event.series_ticker"),
        "category": _optional_text(event.get("category")),
        "title": _optional_text(event.get("title")),
        "sub_title": _optional_text(event.get("sub_title")),
        "strike_date": _optional_text(event.get("strike_date")),
        "strike_period": _optional_text(event.get("strike_period")),
        "mutually_exclusive": _format_bool(event.get("mutually_exclusive")),
        "bitcoin_scope": scope["bitcoin_scope"],
        "scope_confidence": scope["scope_confidence"],
        "scope_reason": scope["scope_reason"],
    }


def build_market_row(
    *,
    run_id: str,
    source: MarketSource,
    assignment: Mapping[str, Any],
) -> dict[str, str]:
    market = source.market
    rules_primary = _optional_text(market.get("rules_primary"))
    rules_secondary = _optional_text(market.get("rules_secondary"))
    return {
        "schema_version": MARKET_SCHEMA_VERSION,
        **_lineage(run_id, source.response, source.route_tier),
        "ticker": _required_text(market.get("ticker"), "market.ticker"),
        "event_ticker": _required_text(market.get("event_ticker"), "market.event_ticker"),
        "series_ticker": source.series_ticker,
        "market_type": _optional_text(market.get("market_type")),
        "title": _optional_text(market.get("title")),
        "subtitle": _optional_text(market.get("subtitle")),
        "yes_sub_title": _optional_text(market.get("yes_sub_title")),
        "no_sub_title": _optional_text(market.get("no_sub_title")),
        "open_time": _optional_text(market.get("open_time")),
        "close_time": _optional_text(market.get("close_time")),
        "expected_expiration_time": _optional_text(market.get("expected_expiration_time")),
        "expiration_time": _optional_text(market.get("expiration_time")),
        "settlement_ts": _optional_text(market.get("settlement_ts")),
        "occurrence_datetime": _optional_text(market.get("occurrence_datetime")),
        "strike_type": _optional_text(market.get("strike_type")),
        "floor_strike": _format_scalar(market.get("floor_strike")),
        "cap_strike": _format_scalar(market.get("cap_strike")),
        "functional_strike": _optional_text(market.get("functional_strike")),
        "custom_strike_json": _stable_json(market.get("custom_strike", {})),
        "rules_primary_sha256": _sha256_text(rules_primary),
        "rules_secondary_sha256": _sha256_text(rules_secondary),
        "settlement_family": str(assignment["settlement_family"]),
        "cluster_status": str(assignment["cluster_status"]),
        "settlement_cluster_id": str(assignment["settlement_cluster_id"]),
        "candidate_group_key": str(assignment["candidate_group_key"]),
        "primitive_ids_json": _stable_json(assignment["primitive_ids"]),
        "cluster_reason": str(assignment["cluster_reason"]),
    }


def _build_cluster_assignments(
    market_sources: Sequence[MarketSource],
) -> dict[str, dict[str, Any]]:
    assignments: dict[str, dict[str, Any]] = {}
    for source in market_sources:
        market = source.market
        ticker = _required_text(market.get("ticker"), "market.ticker")
        series = source.series_ticker
        event = _required_text(market.get("event_ticker"), "market.event_ticker")
        open_time = _optional_text(market.get("open_time"))
        close_time = _optional_text(market.get("close_time"))

        if series.upper() == "KXBTC15M" and open_time and close_time:
            open_boundary = _canonical_utc_text(open_time, "market.open_time")
            close_boundary = _canonical_utc_text(close_time, "market.close_time")
            primitive_ids = [
                _brti_boundary_primitive_id(open_boundary),
                _brti_boundary_primitive_id(close_boundary),
            ]
            cluster_id = _stable_id("btcsc", primitive_ids)
            assignments[ticker] = {
                "settlement_family": "kxbtc15m_two_boundary_brti_average_direction",
                "cluster_status": "resolved",
                "settlement_cluster_id": cluster_id,
                "candidate_group_key": f"{series}|{event}|{close_boundary}",
                "primitive_ids": primitive_ids,
                "cluster_reason": (
                    "KXBTC15M uses the already-validated pre-open and pre-close "
                    "60-second BRTI comparison boundaries"
                ),
            }
            continue

        if close_time:
            close_boundary = _canonical_utc_text(close_time, "market.close_time")
            candidate_key = f"{series}|{event}|{close_boundary}"
            assignments[ticker] = {
                # Candidate clustering is deliberately broader than source strike
                # metadata.  Markets in the same event and close boundary remain
                # one dependence candidate even when Kalshi populates strike fields
                # inconsistently across contracts.  Strike metadata is preserved on
                # each market row and can be used later only after rule validation.
                "settlement_family": "same_event_close_candidate",
                "cluster_status": "candidate_requires_rule_validation",
                "settlement_cluster_id": _stable_id("btccand", [candidate_key]),
                "candidate_group_key": candidate_key,
                "primitive_ids": [],
                "cluster_reason": (
                    "Grouped conservatively by series, source event, and close boundary; "
                    "market-level strike metadata is preserved separately and the underlying "
                    "settlement primitive has not yet been validated"
                ),
            }
        else:
            candidate_key = f"{series}|{event}|missing_close_time|{ticker}"
            assignments[ticker] = {
                "settlement_family": "unresolved_missing_close_time",
                "cluster_status": "unresolved",
                "settlement_cluster_id": _stable_id("btcunres", [candidate_key]),
                "candidate_group_key": candidate_key,
                "primitive_ids": [],
                "cluster_reason": "Market lacks a usable close_time; no settlement-period grouping is accepted",
            }
    return assignments


def build_cluster_rows(
    *, run_id: str, market_rows: Sequence[Mapping[str, str]]
) -> list[dict[str, str]]:
    grouped: dict[str, list[Mapping[str, str]]] = {}
    for row in market_rows:
        grouped.setdefault(row["settlement_cluster_id"], []).append(row)

    out: list[dict[str, str]] = []
    for cluster_id in sorted(grouped):
        rows = grouped[cluster_id]
        statuses = {row["cluster_status"] for row in rows}
        families = {row["settlement_family"] for row in rows}
        series = {row["series_ticker"] for row in rows}
        primitive_sets = {row["primitive_ids_json"] for row in rows}
        if len(statuses) != 1 or len(families) != 1 or len(series) != 1 or len(primitive_sets) != 1:
            raise BtcResearchUnitError(f"cluster {cluster_id} contains inconsistent assignments")
        lineages = _lineage_set(rows)
        out.append(
            {
                "schema_version": CLUSTER_SCHEMA_VERSION,
                "run_id": run_id,
                "settlement_cluster_id": cluster_id,
                "cluster_status": next(iter(statuses)),
                "series_ticker": next(iter(series)),
                "settlement_family": next(iter(families)),
                "event_tickers_json": _stable_json(sorted({row["event_ticker"] for row in rows})),
                "market_tickers_json": _stable_json(sorted(row["ticker"] for row in rows)),
                "market_count": str(len(rows)),
                "event_count": str(len({row["event_ticker"] for row in rows})),
                "earliest_open_time": _min_nonempty(row["open_time"] for row in rows),
                "latest_close_time": _max_nonempty(row["close_time"] for row in rows),
                "primitive_ids_json": next(iter(primitive_sets)),
                "source_lineage_json": _stable_json(lineages),
                "cluster_reason": rows[0]["cluster_reason"],
            }
        )
    return out


def build_overlap_rows(
    *, run_id: str, cluster_rows: Sequence[Mapping[str, str]]
) -> list[dict[str, str]]:
    by_primitive: dict[str, list[Mapping[str, str]]] = {}
    for cluster in cluster_rows:
        if cluster["cluster_status"] != "resolved":
            continue
        primitive_ids = json.loads(cluster["primitive_ids_json"])
        for primitive_id in primitive_ids:
            by_primitive.setdefault(str(primitive_id), []).append(cluster)

    out: list[dict[str, str]] = []
    for primitive_id in sorted(by_primitive):
        clusters = sorted(
            by_primitive[primitive_id], key=lambda row: row["settlement_cluster_id"]
        )
        if len(clusters) < 2:
            continue
        for left, right in itertools.combinations(clusters, 2):
            lineages = sorted(
                {
                    tuple(item)
                    for item in (
                        json.loads(left["source_lineage_json"])
                        + json.loads(right["source_lineage_json"])
                    )
                }
            )
            out.append(
                {
                    "schema_version": OVERLAP_SCHEMA_VERSION,
                    "run_id": run_id,
                    "primitive_id": primitive_id,
                    "cluster_id_a": left["settlement_cluster_id"],
                    "cluster_id_b": right["settlement_cluster_id"],
                    "relation": "shared_settlement_primitive",
                    "split_policy": "same_partition_or_boundary_embargo",
                    "source_lineage_json": _stable_json([list(item) for item in lineages]),
                }
            )
    return out


def build_series_summary_rows(
    *,
    run_id: str,
    event_rows: Sequence[Mapping[str, str]],
    market_rows: Sequence[Mapping[str, str]],
    cluster_rows: Sequence[Mapping[str, str]],
    event_scope_by_ticker: Mapping[str, Mapping[str, str]],
    discovered_event_counts: Mapping[str, int],
    event_sample_cap: int,
) -> list[dict[str, str]]:
    series_tickers = sorted({row["series_ticker"] for row in event_rows})
    out: list[dict[str, str]] = []
    for series in series_tickers:
        events = [row for row in event_rows if row["series_ticker"] == series]
        markets = [row for row in market_rows if row["series_ticker"] == series]
        clusters = [row for row in cluster_rows if row["series_ticker"] == series]
        scopes = {event_scope_by_ticker[row["event_ticker"]]["bitcoin_scope"] for row in events}
        scope = next(iter(scopes)) if len(scopes) == 1 else "mixed_bitcoin_scope"
        out.append(
            {
                "schema_version": SERIES_SUMMARY_SCHEMA_VERSION,
                "run_id": run_id,
                "series_ticker": series,
                "bitcoin_scope": scope,
                "discovered_settled_event_count": str(discovered_event_counts.get(series, 0)),
                "sampled_event_count": str(len(events)),
                "event_sample_cap": str(event_sample_cap),
                "event_sampling_rule": "sha256_event_ticker_ascending",
                "event_count": str(len(events)),
                "market_count": str(len(markets)),
                "settlement_cluster_count": str(len(clusters)),
                "resolved_cluster_count": str(sum(row["cluster_status"] == "resolved" for row in clusters)),
                "candidate_cluster_count": str(sum(row["cluster_status"] == "candidate_requires_rule_validation" for row in clusters)),
                "unresolved_cluster_count": str(sum(row["cluster_status"] == "unresolved" for row in clusters)),
                "market_type_set_json": _stable_json(sorted({row["market_type"] for row in markets if row["market_type"]})),
                "strike_type_set_json": _stable_json(sorted({row["strike_type"] for row in markets if row["strike_type"]})),
                "earliest_close_time": _min_nonempty(row["close_time"] for row in markets),
                "latest_close_time": _max_nonempty(row["close_time"] for row in markets),
                "source_lineage_json": _stable_json(_lineage_set([*events, *markets])),
            }
        )
    return out


def validate_collected_rows(rows: BtcResearchUnitRows, *, run_id: str) -> dict[str, int]:
    for row_type, records, expected_fields in (
        ("event", rows.events, EVENT_FIELDS),
        ("market", rows.markets, MARKET_FIELDS),
        ("cluster", rows.clusters, CLUSTER_FIELDS),
        ("overlap", rows.overlaps, OVERLAP_FIELDS),
        ("series_summary", rows.series_summary, SERIES_SUMMARY_FIELDS),
    ):
        for record in records:
            if tuple(record.keys()) != tuple(expected_fields):
                raise BtcResearchUnitError(f"{row_type} row does not match frozen schema")
            if record.get("run_id") != run_id:
                raise BtcResearchUnitError(f"{row_type} row has wrong run_id")
            forbidden = FORBIDDEN_DERIVED_FIELDS.intersection(record.keys())
            if forbidden:
                raise BtcResearchUnitError(
                    f"{row_type} row materialized forbidden fields: {sorted(forbidden)}"
                )

    event_ids = [row["event_ticker"] for row in rows.events]
    market_ids = [row["ticker"] for row in rows.markets]
    cluster_ids = [row["settlement_cluster_id"] for row in rows.clusters]
    if len(event_ids) != len(set(event_ids)):
        raise BtcResearchUnitError("duplicate event rows")
    if len(market_ids) != len(set(market_ids)):
        raise BtcResearchUnitError("duplicate market rows")
    if len(cluster_ids) != len(set(cluster_ids)):
        raise BtcResearchUnitError("duplicate cluster rows")

    event_set = set(event_ids)
    cluster_set = set(cluster_ids)
    for market in rows.markets:
        if market["event_ticker"] not in event_set:
            raise BtcResearchUnitError("market references unknown event")
        if market["settlement_cluster_id"] not in cluster_set:
            raise BtcResearchUnitError("market references unknown settlement cluster")
        if market["series_ticker"].upper() == "KXBTC15M":
            if market["cluster_status"] != "resolved":
                raise BtcResearchUnitError("KXBTC15M market must use resolved cluster assignment")
            if len(json.loads(market["primitive_ids_json"])) != 2:
                raise BtcResearchUnitError("KXBTC15M market must carry two settlement primitives")


    for summary_row in rows.series_summary:
        discovered = int(summary_row["discovered_settled_event_count"])
        sampled = int(summary_row["sampled_event_count"])
        cap = int(summary_row["event_sample_cap"])
        if sampled != int(summary_row["event_count"]):
            raise BtcResearchUnitError("series summary sampled_event_count mismatch")
        if discovered < sampled:
            raise BtcResearchUnitError("series summary discovered count below sampled count")
        if sampled > cap:
            raise BtcResearchUnitError("series summary sample exceeds event cap")
        if summary_row["event_sampling_rule"] != "sha256_event_ticker_ascending":
            raise BtcResearchUnitError("unexpected event sampling rule")
    for overlap in rows.overlaps:
        if overlap["cluster_id_a"] not in cluster_set or overlap["cluster_id_b"] not in cluster_set:
            raise BtcResearchUnitError("overlap references unknown cluster")
        if overlap["cluster_id_a"] == overlap["cluster_id_b"]:
            raise BtcResearchUnitError("overlap cannot self-reference")

    return {
        "event_rows": len(rows.events),
        "discovered_settled_event_rows": rows.discovered_settled_event_count,
        "sampled_event_rows": rows.sampled_event_count,
        "market_rows": len(rows.markets),
        "settlement_cluster_rows": len(rows.clusters),
        "primitive_overlap_rows": len(rows.overlaps),
        "series_summary_rows": len(rows.series_summary),
        "resolved_cluster_rows": sum(row["cluster_status"] == "resolved" for row in rows.clusters),
        "candidate_cluster_rows": sum(row["cluster_status"] == "candidate_requires_rule_validation" for row in rows.clusters),
        "unresolved_cluster_rows": sum(row["cluster_status"] == "unresolved" for row in rows.clusters),
    }


def write_collected_csvs(
    root: str | Path, *, run_id: str, rows: BtcResearchUnitRows
) -> CsvPaths:
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    paths = CsvPaths(
        events=root_path / f"{run_id}_btc_events.csv",
        markets=root_path / f"{run_id}_btc_markets.csv",
        clusters=root_path / f"{run_id}_btc_settlement_clusters.csv",
        overlaps=root_path / f"{run_id}_btc_primitive_overlaps.csv",
        series_summary=root_path / f"{run_id}_btc_series_summary.csv",
    )
    _write_csv(paths.events, EVENT_FIELDS, rows.events)
    _write_csv(paths.markets, MARKET_FIELDS, rows.markets)
    _write_csv(paths.clusters, CLUSTER_FIELDS, rows.clusters)
    _write_csv(paths.overlaps, OVERLAP_FIELDS, rows.overlaps)
    _write_csv(paths.series_summary, SERIES_SUMMARY_FIELDS, rows.series_summary)
    return paths


def _sample_discovered_events(
    discovered: Sequence[tuple[Mapping[str, Any], RawFirstJsonResponse, dict[str, str]]],
    *,
    limit: int,
) -> list[tuple[Mapping[str, Any], RawFirstJsonResponse, dict[str, str]]]:
    """Select an outcome-blind deterministic structural sample by event ticker hash."""

    if limit <= 0:
        raise ValueError("event sample limit must be positive")
    return sorted(
        discovered,
        key=lambda item: (
            hashlib.sha256(
                _required_text(item[0].get("event_ticker"), "event.event_ticker").encode("utf-8")
            ).hexdigest(),
            _required_text(item[0].get("event_ticker"), "event.event_ticker"),
        ),
    )[:limit]


def _fetch_market_pages(
    client: RawFirstJsonClient,
    *,
    path: str,
    route_tier: str,
    series_ticker: str,
    event_ticker: str,
    max_pages: int,
    status: str | None,
) -> tuple[list[MarketSource], int]:
    cursor = ""
    out: list[MarketSource] = []
    pages = 0
    for _ in range(max_pages):
        params: dict[str, Any] = {
            "limit": 1000,
            "event_ticker": event_ticker,
        }
        # Historical filters are mutually exclusive, so event_ticker is the
        # sole historical selection filter. The live route may additionally
        # use status and mve_filter.
        if path == "/markets":
            params["mve_filter"] = "exclude"
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        response = client.get_json(path, params=params)
        pages += 1
        markets, cursor = _validate_list_response(response.payload, "markets")
        for market in markets:
            observed_event = _required_text(market.get("event_ticker"), "market.event_ticker")
            if observed_event != event_ticker:
                raise BtcResearchUnitError(
                    f"{path} event-filtered request for {event_ticker} returned market from {observed_event}"
                )
            out.append(MarketSource(market=market, series_ticker=series_ticker, route_tier=route_tier, response=response))
        if not cursor:
            break
    else:
        if cursor:
            raise BtcResearchUnitError(
                f"{path} for event {event_ticker} remained paginated after max_pages={max_pages}"
            )
    return out, pages


def _reconcile_market_sources(
    candidates: Sequence[MarketSource],
    *,
    cutoff: HistoricalCutoff,
    selected_event_tickers: set[str],
) -> tuple[list[MarketSource], set[str]]:
    by_ticker: dict[str, list[MarketSource]] = {}
    for source in candidates:
        event_ticker = _optional_text(source.market.get("event_ticker"))
        if event_ticker not in selected_event_tickers:
            continue
        ticker = _required_text(source.market.get("ticker"), "market.ticker")
        by_ticker.setdefault(ticker, []).append(source)

    chosen: list[MarketSource] = []
    duplicates: set[str] = set()
    for ticker in sorted(by_ticker):
        sources = by_ticker[ticker]
        if len(sources) == 1:
            chosen.append(sources[0])
            continue
        duplicates.add(ticker)
        settlement_text = _optional_text(sources[0].market.get("settlement_ts"))
        expected = None
        if settlement_text:
            settlement = _parse_utc(settlement_text, "market.settlement_ts")
            expected = "historical" if settlement < cutoff.market_settled_ts else "live"
        matching = [source for source in sources if source.route_tier == expected]
        selected = matching[0] if matching else sorted(sources, key=lambda item: item.route_tier)[0]
        chosen.append(selected)
    return chosen, duplicates


def _validate_list_response(payload: Mapping[str, Any], field: str) -> tuple[list[Mapping[str, Any]], str]:
    items = payload.get(field)
    if not isinstance(items, list):
        raise BtcResearchUnitError(f"response field {field!r} is not a list")
    checked: list[Mapping[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise BtcResearchUnitError(f"{field}[{index}] is not an object")
        checked.append(item)
    cursor = payload.get("cursor", "")
    if cursor is None:
        cursor = ""
    if not isinstance(cursor, str):
        raise BtcResearchUnitError("response cursor is not text/null")
    return checked, cursor


def _lineage(run_id: str, response: RawFirstJsonResponse, route_tier: str) -> dict[str, str]:
    return {
        "run_id": run_id,
        "raw_source": response.raw_record.source,
        "raw_session_id": response.raw_record.session_id,
        "raw_request_id": response.raw_record.request_id,
        "route_tier": route_tier,
    }


def _lineage_set(rows: Sequence[Mapping[str, str]]) -> list[list[str]]:
    values = sorted(
        {
            (row["raw_source"], row["raw_session_id"], row["raw_request_id"], row["route_tier"])
            for row in rows
            if all(key in row for key in ("raw_source", "raw_session_id", "raw_request_id", "route_tier"))
        }
    )
    return [list(item) for item in values]


def _brti_boundary_primitive_id(boundary_utc: str) -> str:
    return f"cfbenchmarks_brti_60s_pre_boundary@{boundary_utc}"


def _stable_id(prefix: str, parts: Sequence[str]) -> str:
    material = "\n".join(sorted(parts)).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(material).hexdigest()[:20]}"


def _canonical_utc_text(value: str, field: str) -> str:
    return _parse_utc(value, field).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any, field: str) -> datetime:
    text = _required_text(value, field)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BtcResearchUnitError(f"{field} is not a valid ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise BtcResearchUnitError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BtcResearchUnitError(f"{field} must be non-empty text")
    return value.strip()


def _optional_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _format_bool(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return ""


def _format_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value)
    return _stable_json(value)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def _min_nonempty(values: Sequence[str] | Any) -> str:
    present = [value for value in values if value]
    return min(present) if present else ""


def _max_nonempty(values: Sequence[str] | Any) -> str:
    present = [value for value in values if value]
    return max(present) if present else ""


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
