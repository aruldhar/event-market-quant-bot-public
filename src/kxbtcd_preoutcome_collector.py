"""Raw-first, outcome-blind KXBTCD historical materialization core.

This module implements the Checkpoint-12 collection path without owning HTTP,
credentials, or execution. Callers supply a GET-only raw-first client. Source
responses may contain settlement fields, but this module never reads or emits
settlement outcomes.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .btc_rule_template import (
    BtcRuleTemplateError,
    RuleSemanticSignature,
    measurement_end_utc,
    measurement_regime_id,
    parse_rule_semantics,
    settlement_primitive_id,
)
from .kxbtcd_chronological_split_contract import (
    CHECKPOINT10_SOURCE_EVENT_COUNT,
    EVENT_UNIT_FIELDS,
    TARGET_REGIME_ID,
    build_chronological_split,
    split_summary,
)
from .kxbtcd_preoutcome_dataset import (
    DATASET_ROW_FIELDS,
    EXCLUSION_ROW_FIELDS,
    build_preoutcome_dataset,
)
from .kxbtcd_preoutcome_materialization import (
    ANCHOR_SELECTION_FIELDS,
    CONSERVATIVE_MODERN_START_UTC,
    HISTORICAL_STATE_VIEW,
    MAX_ANCHOR_STALENESS_SECONDS,
    MAX_EVENTS_PER_UTC_WEEK,
    NORMALIZED_MARKET_FIELDS,
    NORMALIZED_QUOTE_FIELDS,
    PERIOD_INTERVAL_MINUTES,
    SELECTED_EVENT_FIELDS,
    SELECTED_MARKET_FIELDS,
    TIME_TO_CLOSE_ANCHORS_SECONDS,
    build_historical_reconstructed_state,
    materialization_fingerprint,
    select_anchor_observation,
    select_structural_markets,
    select_weekly_events,
)


class KxbtcdPreoutcomeCollectorError(RuntimeError):
    """Raised when the pre-outcome collection path cannot prove its invariants."""


SERIES_TICKER = "KXBTCD"
EVENT_CENSUS_SCHEMA_VERSION = "kxbtcd_preoutcome_event_census.v3"
MODERN_EVENT_SCHEMA_VERSION = "kxbtcd_preoutcome_modern_event.v3"
QUOTE_AUDIT_SCHEMA_VERSION = "kxbtcd_preoutcome_quote_audit.v1"
MAX_EVENT_PAGES_DEFAULT = 100
MARKET_PAGE_LIMIT = 1000
EVENT_PAGE_LIMIT = 200
REGIME_SCAN_MIN_CLOSE_UTC = CONSERVATIVE_MODERN_START_UTC
CHECKPOINT10_OLD_RULE_REGIME_ID = "brti_60s_trimmed_mean_trim20_20_above"
CHECKPOINT10_MODERN_RULE_REGIME_ID = "brti_60s_simple_mean_untrimmed_above"

EVENT_CENSUS_FIELDS = (
    "schema_version",
    "run_id",
    "event_ticker",
    "strike_date_utc",
    "event_raw_ref",
)

MODERN_EVENT_FIELDS = (
    "schema_version",
    "run_id",
    "event_ticker",
    "strike_date_utc",
    "close_time_utc",
    "settlement_regime_id",
    "settlement_primitive_id",
    "event_raw_ref",
    "regime_evidence_ref",
)

STATE_AUDIT_FIELDS = (
    "state_id",
    "state_view",
    "event_ticker",
    "market_ticker",
    "as_of_utc",
    "state_json",
)

QUOTE_AUDIT_FIELDS = (
    "schema_version",
    "run_id",
    "event_ticker",
    "market_ticker",
    "anchor_seconds",
    "anchor_available",
    "raw_observation_id",
    "exclusion_reason",
)

FORBIDDEN_OUTCOME_KEYS = frozenset(
    {
        "result",
        "outcome",
        "label",
        "y",
        "resolved_yes",
        "settled_yes",
        "settlement_value",
        "settlement_value_dollars",
        "expiration_value",
        "prediction",
        "p_yes",
        "model_output",
        "gross_edge",
        "net_edge",
        "expected_pnl",
        "decision",
        "order_id",
    }
)


class _RawReference(Protocol):
    source: str
    session_id: str
    request_id: str


class RawFirstJsonResponse(Protocol):
    payload: dict[str, Any]
    raw_record: _RawReference
    received_at_utc: str
    received_monotonic_ns: int


class RawFirstJsonClient(Protocol):
    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> RawFirstJsonResponse: ...


@dataclass(frozen=True)
class Checkpoint10Quarantine:
    event_tickers: tuple[str, ...]
    primitive_ids: tuple[str, ...]
    source_manifest_path: str
    source_manifest_sha256: str


@dataclass(frozen=True)
class ModernRegimeEvidence:
    last_old_close_utc: str
    last_old_event_ticker: str
    first_modern_close_utc: str
    first_modern_event_ticker: str
    source_report_path: str
    source_report_sha256: str

    @property
    def lineage_ref(self) -> str:
        return f"checkpoint10_rule_regime_report:sha256:{self.source_report_sha256}"


@dataclass(frozen=True)
class PreoutcomeCollectionRows:
    event_census: tuple[dict[str, Any], ...]
    modern_events: tuple[dict[str, Any], ...]
    split_rows: tuple[dict[str, Any], ...]
    selected_events: tuple[dict[str, Any], ...]
    selected_markets: tuple[dict[str, Any], ...]
    quote_audit: tuple[dict[str, Any], ...]
    states: tuple[dict[str, Any], ...]
    dataset_rows: tuple[dict[str, Any], ...]
    exclusions: tuple[dict[str, Any], ...]
    summary: dict[str, Any]


@dataclass(frozen=True)
class CsvPaths:
    event_census: Path
    modern_events: Path
    split_rows: Path
    selected_events: Path
    selected_markets: Path
    quote_audit: Path
    states_csv: Path
    dataset_rows: Path
    exclusions: Path

    def all(self) -> tuple[Path, ...]:
        return (
            self.event_census,
            self.modern_events,
            self.split_rows,
            self.selected_events,
            self.selected_markets,
            self.quote_audit,
            self.states_csv,
            self.dataset_rows,
            self.exclusions,
        )


def _error(message: str) -> None:
    raise KxbtcdPreoutcomeCollectorError(message)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be a non-empty string")
    return value.strip()


def _parse_utc(value: Any, name: str) -> datetime:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KxbtcdPreoutcomeCollectorError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _error(f"{name} must carry UTC timezone information")
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _optional_utc(value: Any, name: str) -> str:
    """Canonicalize an optional source timestamp without inventing a fallback."""

    if value is None:
        return ""
    if not isinstance(value, str):
        _error(f"{name} must be text or null")
    if not value.strip():
        return ""
    return _format_utc(_parse_utc(value, name))


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KxbtcdPreoutcomeCollectorError(f"{name} must be numeric") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _raw_ref(response: RawFirstJsonResponse) -> str:
    return "raw:" + ":".join(
        [
            _text(response.raw_record.source, "raw source"),
            _text(response.raw_record.session_id, "raw session_id"),
            _text(response.raw_record.request_id, "raw request_id"),
        ]
    )


def _raw_observation_id(
    response: RawFirstJsonResponse,
    *,
    market_ticker: str,
    end_period_ts: int,
) -> str:
    payload = "|".join(
        [
            _raw_ref(response),
            market_ticker,
            str(end_period_ts),
        ]
    )
    return "rawobs:kxbtcd:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _reject_forbidden_columns(rows: Sequence[Mapping[str, Any]], name: str) -> None:
    for index, row in enumerate(rows):
        bad = FORBIDDEN_OUTCOME_KEYS.intersection(row)
        if bad:
            _error(f"{name}[{index}] contains forbidden outcome/downstream fields: {sorted(bad)}")


def _reject_forbidden_tree(value: Any, name: str) -> None:
    if isinstance(value, Mapping):
        bad = FORBIDDEN_OUTCOME_KEYS.intersection(value)
        if bad:
            _error(f"{name} contains forbidden outcome/downstream fields: {sorted(bad)}")
        for key, child in value.items():
            _reject_forbidden_tree(child, f"{name}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_forbidden_tree(child, f"{name}[{index}]")


def load_checkpoint10_quarantine(repository_root: str | Path = ".") -> Checkpoint10Quarantine:
    """Load exactly the twenty source KXBTCD clusters from Checkpoint 10."""

    from .kxbtcd_baseline_design import load_latest_source_artifacts

    artifacts = load_latest_source_artifacts(repository_root)
    try:
        with artifacts.clusters_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        raise KxbtcdPreoutcomeCollectorError(
            f"could not read Checkpoint-10 cluster artifact: {artifacts.clusters_path}"
        ) from exc
    _reject_forbidden_columns(rows, "checkpoint10 clusters")

    selected = [
        row
        for row in rows
        if row.get("family") == SERIES_TICKER
        and row.get("regime_id") == TARGET_REGIME_ID
    ]
    if len(selected) != CHECKPOINT10_SOURCE_EVENT_COUNT:
        _error(
            f"Checkpoint-10 quarantine requires {CHECKPOINT10_SOURCE_EVENT_COUNT} modern KXBTCD "
            f"source clusters; found {len(selected)}"
        )

    events: list[str] = []
    primitives: list[str] = []
    for row in selected:
        events.append(_text(row.get("event_ticker"), "checkpoint10 event_ticker"))
        raw_primitives = _text(row.get("primitive_ids_json"), "checkpoint10 primitive_ids_json")
        try:
            parsed = json.loads(raw_primitives)
        except json.JSONDecodeError as exc:
            raise KxbtcdPreoutcomeCollectorError(
                "Checkpoint-10 primitive_ids_json is not valid JSON"
            ) from exc
        if not isinstance(parsed, list) or len(parsed) != 1:
            _error("each Checkpoint-10 KXBTCD cluster must contain exactly one primitive")
        primitives.append(_text(parsed[0], "checkpoint10 primitive_id"))

    if len(set(events)) != len(events):
        _error("Checkpoint-10 quarantine event tickers contain duplicates")
    if len(set(primitives)) != len(primitives):
        _error("Checkpoint-10 quarantine primitive IDs contain duplicates")

    manifest_sha = hashlib.sha256(artifacts.manifest_path.read_bytes()).hexdigest()
    return Checkpoint10Quarantine(
        event_tickers=tuple(sorted(events)),
        primitive_ids=tuple(sorted(primitives)),
        source_manifest_path=str(artifacts.manifest_path),
        source_manifest_sha256=manifest_sha,
    )



def load_checkpoint10_regime_evidence(
    repository_root: str | Path = ".",
) -> ModernRegimeEvidence:
    """Load the Checkpoint-10 sample-observed KXBTCD old->modern rule bracket.

    The report is outcome-blind. The first sample-observed modern close is used
    only as a conservative lower bound for the new sampling frame; it is not
    treated as the exact production rule-change timestamp.
    """

    repo = Path(repository_root).resolve()
    root = repo / "data" / "derived" / "btc_research_unit"
    candidates = sorted(
        root.glob("*_btc_ladder_rule_regimes.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    if not candidates:
        _error("no Checkpoint-10 btc_ladder_rule_regimes report was found")

    for report_path in candidates:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(report, Mapping) or report.get("status") != "PASS":
            continue
        series = report.get("series_results")
        if not isinstance(series, Mapping):
            continue
        kxbtcd = series.get(SERIES_TICKER)
        if not isinstance(kxbtcd, Mapping) or kxbtcd.get("status") != "PASS":
            continue
        _reject_forbidden_tree(report, "checkpoint10 regime report")

        transitions = kxbtcd.get("observed_sample_transitions")
        if not isinstance(transitions, list):
            _error("Checkpoint-10 KXBTCD transition list is missing")
        matching = [
            item
            for item in transitions
            if isinstance(item, Mapping)
            and item.get("from_regime_id") == CHECKPOINT10_OLD_RULE_REGIME_ID
            and item.get("to_regime_id") == CHECKPOINT10_MODERN_RULE_REGIME_ID
        ]
        if len(matching) != 1:
            _error(
                "Checkpoint-10 KXBTCD report must contain exactly one recognized "
                "trimmed->simple transition bracket"
            )
        transition = matching[0]
        last_old_close = _format_utc(
            _parse_utc(
                transition.get("last_observed_from_close_time"),
                "checkpoint10 last old close",
            )
        )
        first_modern_close = _format_utc(
            _parse_utc(
                transition.get("first_observed_to_close_time"),
                "checkpoint10 first modern close",
            )
        )
        if first_modern_close != CONSERVATIVE_MODERN_START_UTC:
            _error(
                "Checkpoint-10 first sample-observed modern close changed from frozen "
                f"materialization lower bound {CONSERVATIVE_MODERN_START_UTC}: "
                f"observed {first_modern_close}"
            )
        if _parse_utc(last_old_close, "last_old_close") >= _parse_utc(
            first_modern_close, "first_modern_close"
        ):
            _error("Checkpoint-10 transition bracket is not chronological")

        samples = kxbtcd.get("samples")
        if not isinstance(samples, list):
            _error("Checkpoint-10 KXBTCD sample list is missing")

        def _sample_event(close_time: str, regime_id: str, label: str) -> str:
            matches = []
            for item in samples:
                if not isinstance(item, Mapping):
                    continue
                raw_close = (
                    item.get("close_time")
                    or item.get("close_time_utc")
                    or item.get("measurement_end_utc")
                )
                if not isinstance(raw_close, str) or not raw_close.strip():
                    continue
                try:
                    normalized_close = _format_utc(_parse_utc(raw_close, f"{label} close"))
                except KxbtcdPreoutcomeCollectorError:
                    continue
                if normalized_close == close_time and item.get("regime_id") == regime_id:
                    matches.append(_text(item.get("event_ticker"), f"{label} event_ticker"))
            if len(matches) != 1:
                _error(
                    f"Checkpoint-10 report must contain exactly one {label} sample at {close_time}; "
                    f"found {len(matches)}"
                )
            return matches[0]

        last_old_event = _sample_event(
            last_old_close,
            CHECKPOINT10_OLD_RULE_REGIME_ID,
            "last old-regime",
        )
        first_modern_event = _sample_event(
            first_modern_close,
            CHECKPOINT10_MODERN_RULE_REGIME_ID,
            "first modern-regime",
        )
        sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
        return ModernRegimeEvidence(
            last_old_close_utc=last_old_close,
            last_old_event_ticker=last_old_event,
            first_modern_close_utc=first_modern_close,
            first_modern_event_ticker=first_modern_event,
            source_report_path=str(report_path.resolve()),
            source_report_sha256=sha,
        )

    _error("no completed PASS Checkpoint-10 KXBTCD rule-regime report was found")


def discover_settled_event_census(
    client: RawFirstJsonClient,
    *,
    run_id: str,
    min_close_utc: str = REGIME_SCAN_MIN_CLOSE_UTC,
    max_event_pages: int = MAX_EVENT_PAGES_DEFAULT,
) -> tuple[dict[str, Any], ...]:
    """Discover the conservative post-proof KXBTCD Event sampling frame.

    ``min_close_utc`` is the first Checkpoint-10 sample-observed event whose
    rules were independently proven to use the target simple 60-second regime.
    Event ``strike_date`` is required in this post-proof frame because the
    Checkpoint-12 offline audit found it complete and unique there, and all 25
    Checkpoint-10 sampled KXBTCD Events matched validated market ``close_time``
    exactly. Any future missing, duplicate, or pre-boundary strike date fails
    closed instead of falling back to ticker parsing or per-event witness calls.
    """

    run_id = _text(run_id, "run_id")
    min_close = _parse_utc(min_close_utc, "min_close_utc")
    if max_event_pages <= 0:
        _error("max_event_pages must be positive")
    rows: list[dict[str, Any]] = []
    seen_events: set[str] = set()
    seen_strike_dates: set[str] = set()
    cursor = ""
    for _page_index in range(max_event_pages):
        params: dict[str, Any] = {
            "status": "settled",
            "series_ticker": SERIES_TICKER,
            "min_close_ts": int(min_close.timestamp()) - 1,
            "limit": EVENT_PAGE_LIMIT,
            "with_nested_markets": "false",
        }
        if cursor:
            params["cursor"] = cursor
        response = client.get_json("/events", params=params)
        events = response.payload.get("events")
        if not isinstance(events, list):
            _error("GET /events response field 'events' must be a list")
        for index, event in enumerate(events):
            if not isinstance(event, Mapping):
                _error(f"events[{index}] must be an object")
            ticker = _text(event.get("event_ticker"), "event.event_ticker")
            if ticker in seen_events:
                _error(f"duplicate settled KXBTCD event discovered: {ticker}")
            seen_events.add(ticker)
            if _text(event.get("series_ticker"), "event.series_ticker") != SERIES_TICKER:
                _error(f"series-filtered event response returned non-{SERIES_TICKER} event")
            strike_date = _format_utc(
                _parse_utc(event.get("strike_date"), "event.strike_date")
            )
            if _parse_utc(strike_date, "event.strike_date") < min_close:
                _error(
                    f"event {ticker} strike_date {strike_date} precedes conservative modern "
                    f"start {min_close_utc}"
                )
            if strike_date in seen_strike_dates:
                _error(
                    f"post-proof KXBTCD Event census contains duplicate strike_date {strike_date}"
                )
            seen_strike_dates.add(strike_date)
            rows.append(
                {
                    "schema_version": EVENT_CENSUS_SCHEMA_VERSION,
                    "run_id": run_id,
                    "event_ticker": ticker,
                    "strike_date_utc": strike_date,
                    "event_raw_ref": _raw_ref(response),
                }
            )
        raw_cursor = response.payload.get("cursor")
        if raw_cursor is None:
            raw_cursor = ""
        if not isinstance(raw_cursor, str):
            _error("GET /events cursor must be a string")
        cursor = raw_cursor
        if not cursor:
            break
    else:
        if cursor:
            _error(
                f"settled KXBTCD event census remained paginated after max_event_pages={max_event_pages}"
            )
    if not rows:
        _error("settled KXBTCD event census returned no events")
    rows.sort(
        key=lambda row: (
            _parse_utc(row["strike_date_utc"], "strike_date_utc"),
            row["event_ticker"],
        )
    )
    return tuple(rows)

def _market_query(
    client: RawFirstJsonClient,
    *,
    event_ticker: str,
    route_tier: str,
    limit: int,
) -> RawFirstJsonResponse:
    # Historical market filters are mutually exclusive. Use event_ticker as the
    # sole historical selector. The live route may add settled/MVE filters.
    params: dict[str, Any] = {
        "event_ticker": event_ticker,
        "limit": limit,
    }
    if route_tier == "historical":
        return client.get_json("/historical/markets", params=params)
    if route_tier == "live":
        params["series_ticker"] = SERIES_TICKER
        params["mve_filter"] = "exclude"
        params["status"] = "settled"
        return client.get_json("/markets", params=params)
    _error(f"unsupported route_tier: {route_tier}")


def _markets_from_response(response: RawFirstJsonResponse) -> list[Mapping[str, Any]]:
    markets = response.payload.get("markets")
    if not isinstance(markets, list):
        _error("market-list response field 'markets' must be a list")
    output: list[Mapping[str, Any]] = []
    for index, market in enumerate(markets):
        if not isinstance(market, Mapping):
            _error(f"markets[{index}] must be an object")
        output.append(market)
    return output


def _route_for_close_time(close_time_utc: str, cutoff_utc: str) -> str:
    return (
        "historical"
        if _parse_utc(close_time_utc, "close_time_utc") < _parse_utc(cutoff_utc, "cutoff_utc")
        else "live"
    )


def _fetch_event_markets(
    client: RawFirstJsonClient,
    *,
    event_ticker: str,
    preferred_route: str,
    limit: int,
) -> tuple[list[Mapping[str, Any]], RawFirstJsonResponse, str]:
    routes = (preferred_route, "live" if preferred_route == "historical" else "historical")
    empty_responses: list[str] = []
    for route in routes:
        response = _market_query(
            client,
            event_ticker=event_ticker,
            route_tier=route,
            limit=limit,
        )
        markets = _markets_from_response(response)
        if markets:
            cursor = response.payload.get("cursor", "")
            if not isinstance(cursor, str):
                _error("market-list cursor must be a string")
            if limit == MARKET_PAGE_LIMIT and cursor:
                _error(
                    f"event {event_ticker} contains more than {MARKET_PAGE_LIMIT} markets; "
                    "partial event market structure is not accepted"
                )
            return markets, response, route
        empty_responses.append(route)
    _error(
        f"event {event_ticker} returned no markets from either route; tried {empty_responses}"
    )


def _validate_market_identity(market: Mapping[str, Any], event_ticker: str) -> None:
    if _text(market.get("event_ticker"), "market.event_ticker") != event_ticker:
        _error("event-scoped market query returned the wrong event_ticker")
    _text(market.get("ticker"), "market.ticker")


def _validate_market_semantics(
    market: Mapping[str, Any],
    *,
    expected_event_ticker: str,
) -> tuple[str, str, str]:
    """Return (regime_id, measurement_end_utc, primitive_id)."""

    _validate_market_identity(market, expected_event_ticker)
    rules_primary = _text(market.get("rules_primary"), "market.rules_primary")
    rules_secondary = _text(market.get("rules_secondary"), "market.rules_secondary")
    try:
        signature, clock_label, date_label = parse_rule_semantics(
            series_ticker=SERIES_TICKER,
            rules_primary=rules_primary,
            rules_secondary=rules_secondary,
            expected_relation="above",
        )
        regime = measurement_regime_id(signature)
        measurement_end = measurement_end_utc(
            measurement_clock_label=clock_label,
            settlement_date_label=date_label,
        )
        primitive = settlement_primitive_id(
            signature=signature,
            measurement_end_utc_value=measurement_end,
        )
    except BtcRuleTemplateError as exc:
        raise KxbtcdPreoutcomeCollectorError(
            f"could not prove KXBTCD rule semantics for market {market.get('ticker')}: {exc}"
        ) from exc
    close_time = _format_utc(_parse_utc(market.get("close_time"), "market.close_time"))
    if measurement_end != close_time:
        _error(
            f"market {market.get('ticker')} settlement measurement end {measurement_end} "
            f"does not equal source close_time {close_time}"
        )
    return regime, measurement_end, primitive


def modern_sampling_signature() -> RuleSemanticSignature:
    """Return the frozen target KXBTCD measurement/payoff signature."""

    signature = RuleSemanticSignature(
        index_provider="CF Benchmarks",
        index_name="Bitcoin Real-Time Index (BRTI)",
        window_seconds=60,
        statistic="simple_mean",
        trim_top_pct=0,
        trim_bottom_pct=0,
        payoff_relation="above",
    )
    if measurement_regime_id(signature) != TARGET_REGIME_ID:
        _error("frozen modern sampling signature no longer maps to TARGET_REGIME_ID")
    if signature.regime_id != CHECKPOINT10_MODERN_RULE_REGIME_ID:
        _error("frozen modern sampling signature no longer matches Checkpoint-10 rule regime")
    return signature


def provisional_modern_primitive_id(close_time_utc: str) -> str:
    """Construct the provisional target-regime primitive for split/quarantine.

    This is not a claim that an unsampled event's rules were individually
    validated. Every selected event must later pass the complete-ladder semantic
    gate and produce exactly this primitive or the whole run fails closed.
    """

    close_time = _format_utc(_parse_utc(close_time_utc, "close_time_utc"))
    return settlement_primitive_id(
        signature=modern_sampling_signature(),
        measurement_end_utc_value=close_time,
    )


def build_conservative_modern_sampling_frame(
    *,
    run_id: str,
    event_census: Sequence[Mapping[str, Any]],
    regime_evidence: ModernRegimeEvidence,
) -> tuple[dict[str, Any], ...]:
    """Build the post-proof outcome-blind event frame without per-event markets.

    The frame begins at the first Checkpoint-10 sample-observed modern event.
    Event ``strike_date`` supplies chronology. Regime/primitive fields are
    provisional target-regime identities needed by the unchanged split contract;
    only selected events are promoted to usable materialization inputs after
    their complete market ladders are individually rule-validated.
    """

    run_id = _text(run_id, "run_id")
    if regime_evidence.first_modern_close_utc != CONSERVATIVE_MODERN_START_UTC:
        _error("regime evidence disagrees with frozen conservative modern start")
    if not event_census:
        _error("event census must not be empty")

    first_modern_seen = False
    rows: list[dict[str, Any]] = []
    for census_row in event_census:
        event_ticker = _text(census_row.get("event_ticker"), "census.event_ticker")
        strike_date = _format_utc(
            _parse_utc(census_row.get("strike_date_utc"), "census.strike_date_utc")
        )
        if _parse_utc(strike_date, "strike_date") < _parse_utc(
            regime_evidence.first_modern_close_utc,
            "first_modern_close_utc",
        ):
            _error(
                f"event {event_ticker} precedes conservative modern sampling-frame start"
            )
        if (
            event_ticker == regime_evidence.first_modern_event_ticker
            and strike_date == regime_evidence.first_modern_close_utc
        ):
            first_modern_seen = True
        primitive = provisional_modern_primitive_id(strike_date)
        rows.append(
            {
                "schema_version": MODERN_EVENT_SCHEMA_VERSION,
                "run_id": run_id,
                "event_ticker": event_ticker,
                "strike_date_utc": strike_date,
                "close_time_utc": strike_date,
                "settlement_regime_id": TARGET_REGIME_ID,
                "settlement_primitive_id": primitive,
                "event_raw_ref": _text(census_row.get("event_raw_ref"), "event_raw_ref"),
                "regime_evidence_ref": regime_evidence.lineage_ref,
            }
        )
    if not first_modern_seen:
        _error(
            "conservative event census does not contain the Checkpoint-10 first "
            "sample-observed modern event"
        )
    rows.sort(
        key=lambda row: (
            _parse_utc(row["close_time_utc"], "close_time_utc"),
            row["event_ticker"],
        )
    )
    if any(set(row) != set(MODERN_EVENT_FIELDS) for row in rows):
        _error("modern sampling-frame row schema drift")
    return tuple(rows)

def event_units_from_modern_events(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    output: list[dict[str, Any]] = []
    for row in rows:
        if row.get("settlement_regime_id") != TARGET_REGIME_ID:
            _error("modern event row contains non-target settlement regime")
        output.append(
            {
                "event_ticker": _text(row.get("event_ticker"), "event_ticker"),
                "close_time_utc": _text(row.get("close_time_utc"), "close_time_utc"),
                "settlement_regime_id": TARGET_REGIME_ID,
                "settlement_primitive_ids": [
                    _text(row.get("settlement_primitive_id"), "settlement_primitive_id")
                ],
                "source_lineage_refs": [
                    _text(row.get("event_raw_ref"), "event_raw_ref"),
                    _text(row.get("regime_evidence_ref"), "regime_evidence_ref"),
                ],
            }
        )
    for row in output:
        if set(row) != set(EVENT_UNIT_FIELDS):
            _error("event unit schema drift")
    return tuple(output)


def _strike_dollars(market: Mapping[str, Any]) -> str:
    strike_type = _text(market.get("strike_type"), "market.strike_type")
    if strike_type != "greater":
        _error(f"KXBTCD selected market must use strike_type='greater', got {strike_type!r}")
    for key in ("floor_strike", "functional_strike"):
        value = market.get(key)
        if value is None or str(value).strip() == "":
            continue
        try:
            strike = _decimal(value, f"market.{key}")
        except KxbtcdPreoutcomeCollectorError:
            continue
        if strike > 0:
            return _decimal_text(strike)
    _error(f"market {market.get('ticker')} has no positive threshold strike")


def validate_and_normalize_selected_event_markets(
    client: RawFirstJsonClient,
    *,
    selected_event: Mapping[str, Any],
    market_settled_cutoff_utc: str,
) -> tuple[tuple[dict[str, Any], ...], str, int]:
    """Fetch and semantically validate every market in one selected event."""

    event_ticker = _text(selected_event.get("event_ticker"), "selected_event.event_ticker")
    close_time = _text(selected_event.get("close_time_utc"), "selected_event.close_time_utc")
    preferred = _route_for_close_time(close_time, market_settled_cutoff_utc)
    markets, response, route = _fetch_event_markets(
        client,
        event_ticker=event_ticker,
        preferred_route=preferred,
        limit=MARKET_PAGE_LIMIT,
    )
    validated_primitive: str | None = None
    normalized: list[dict[str, Any]] = []
    seen_tickers: set[str] = set()
    for market in markets:
        regime, observed_close, primitive = _validate_market_semantics(
            market,
            expected_event_ticker=event_ticker,
        )
        if regime != TARGET_REGIME_ID:
            _error(f"selected event {event_ticker} contains non-target market regime {regime}")
        if observed_close != close_time:
            _error(f"selected event {event_ticker} market close_time disagrees with frozen split")
        if validated_primitive is None:
            validated_primitive = primitive
        elif primitive != validated_primitive:
            _error(f"selected event {event_ticker} markets do not share one settlement primitive")
        ticker = _text(market.get("ticker"), "market.ticker")
        if ticker in seen_tickers:
            _error(f"duplicate market ticker in selected event {event_ticker}: {ticker}")
        seen_tickers.add(ticker)
        normalized.append(
            {
                "event_ticker": event_ticker,
                "market_ticker": ticker,
                "strike_type": _text(market.get("strike_type"), "market.strike_type"),
                "strike_dollars": _strike_dollars(market),
                "source_lineage_refs": [
                    *list(selected_event.get("source_lineage_refs", [])),
                    _raw_ref(response),
                ],
            }
        )
    expected_primitives = selected_event.get("settlement_primitive_ids")
    if not isinstance(expected_primitives, list) or len(expected_primitives) != 1:
        _error("selected event must carry exactly one settlement primitive")
    if validated_primitive != expected_primitives[0]:
        _error(
            f"selected event {event_ticker} full-market primitive disagrees with provisional sampling frame"
        )
    for row in normalized:
        if set(row) != set(NORMALIZED_MARKET_FIELDS):
            _error("normalized market schema drift")
    return tuple(normalized), route, response.received_monotonic_ns


def _quote_close_value(obj: Any, close_key: str) -> Decimal | None:
    if not isinstance(obj, Mapping):
        return None
    value = obj.get(close_key)
    if value is None or str(value).strip() == "":
        return None
    try:
        return _decimal(value, f"quote.{close_key}")
    except KxbtcdPreoutcomeCollectorError:
        return None


def normalize_quote_rows(
    response: RawFirstJsonResponse,
    *,
    market_ticker: str,
    route_tier: str,
) -> tuple[dict[str, Any], ...]:
    payload_ticker = _text(response.payload.get("ticker"), "candles.ticker")
    if payload_ticker != market_ticker:
        _error(f"candlestick ticker mismatch: expected {market_ticker}, got {payload_ticker}")
    candles = response.payload.get("candlesticks")
    if not isinstance(candles, list):
        _error("candlesticks must be a list")
    close_key = "close" if route_tier == "historical" else "close_dollars"
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, candle in enumerate(candles):
        if not isinstance(candle, Mapping):
            _error(f"candlesticks[{index}] must be an object")
        end_ts = candle.get("end_period_ts")
        if not isinstance(end_ts, int) or isinstance(end_ts, bool):
            _error("candlestick end_period_ts must be an integer")
        if end_ts in seen:
            _error(f"duplicate candlestick end_period_ts for {market_ticker}: {end_ts}")
        seen.add(end_ts)
        bid = _quote_close_value(candle.get("yes_bid"), close_key)
        ask = _quote_close_value(candle.get("yes_ask"), close_key)
        valid = bool(
            bid is not None
            and ask is not None
            and Decimal("0") <= bid <= Decimal("1")
            and Decimal("0") <= ask <= Decimal("1")
            and bid <= ask
        )
        midpoint = (bid + ask) / Decimal("2") if valid and bid is not None and ask is not None else None
        spread = ask - bid if valid and bid is not None and ask is not None else None
        rows.append(
            {
                "end_period_ts": end_ts,
                "valid_quote_observation": valid,
                "yes_bid": _decimal_text(bid) if bid is not None else "",
                "yes_ask": _decimal_text(ask) if ask is not None else "",
                "midpoint": _decimal_text(midpoint) if midpoint is not None else "",
                "spread": _decimal_text(spread) if spread is not None else "",
                "raw_observation_id": _raw_observation_id(
                    response,
                    market_ticker=market_ticker,
                    end_period_ts=end_ts,
                ),
            }
        )
    rows.sort(key=lambda row: row["end_period_ts"])
    for row in rows:
        if set(row) != set(NORMALIZED_QUOTE_FIELDS):
            _error("normalized quote schema drift")
    return tuple(rows)


def fetch_anchor_window(
    client: RawFirstJsonClient,
    *,
    market_ticker: str,
    close_time_utc: str,
    route_tier: str,
) -> RawFirstJsonResponse:
    close_ts = int(_parse_utc(close_time_utc, "close_time_utc").timestamp())
    start_ts = close_ts - max(TIME_TO_CLOSE_ANCHORS_SECONDS) - MAX_ANCHOR_STALENESS_SECONDS
    end_ts = close_ts - min(TIME_TO_CLOSE_ANCHORS_SECONDS)
    params: dict[str, Any] = {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "period_interval": PERIOD_INTERVAL_MINUTES,
    }
    if route_tier == "historical":
        path = f"/historical/markets/{market_ticker}/candlesticks"
    elif route_tier == "live":
        path = f"/series/{SERIES_TICKER}/markets/{market_ticker}/candlesticks"
        params["include_latest_before_start"] = "false"
    else:
        _error(f"unsupported candlestick route tier: {route_tier}")
    return client.get_json(path, params=params)


def collect_preoutcome_rows(
    client: RawFirstJsonClient,
    *,
    run_id: str,
    quarantine: Checkpoint10Quarantine,
    regime_evidence: ModernRegimeEvidence,
    max_event_pages: int = MAX_EVENT_PAGES_DEFAULT,
) -> PreoutcomeCollectionRows:
    """Run the full Checkpoint-12 outcome-blind historical materialization.

    The post-proof Event census is used only as the deterministic sampling frame.
    Every selected event is then promoted through the complete-ladder semantic
    gate before any strike/quote state is emitted.
    """

    run_id = _text(run_id, "run_id")
    cutoff_response = client.get_json("/historical/cutoff")
    cutoff = _format_utc(
        _parse_utc(
            cutoff_response.payload.get("market_settled_ts"),
            "historical.cutoff.market_settled_ts",
        )
    )

    if regime_evidence.first_modern_close_utc != CONSERVATIVE_MODERN_START_UTC:
        _error("Checkpoint-10 regime evidence disagrees with materialization contract")

    event_census = discover_settled_event_census(
        client,
        run_id=run_id,
        min_close_utc=regime_evidence.first_modern_close_utc,
        max_event_pages=max_event_pages,
    )
    modern_events = build_conservative_modern_sampling_frame(
        run_id=run_id,
        event_census=event_census,
        regime_evidence=regime_evidence,
    )
    event_units = event_units_from_modern_events(modern_events)
    split_rows = build_chronological_split(
        event_units,
        checkpoint10_event_tickers=quarantine.event_tickers,
        checkpoint10_primitive_ids=quarantine.primitive_ids,
    )
    selected_events = select_weekly_events(split_rows)

    selected_market_rows: list[dict[str, Any]] = []
    quote_audit: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    fully_validated_selected_events = 0

    for selected_event in selected_events:
        normalized_markets, route_tier, _market_receive_monotonic_ns = (
            validate_and_normalize_selected_event_markets(
                client,
                selected_event=selected_event,
                market_settled_cutoff_utc=cutoff,
            )
        )
        fully_validated_selected_events += 1
        structural = select_structural_markets(
            normalized_markets,
            event_ticker=selected_event["event_ticker"],
        )
        selected_market_rows.extend(structural)
        for selected_market in structural:
            response = fetch_anchor_window(
                client,
                market_ticker=selected_market["market_ticker"],
                close_time_utc=selected_event["close_time_utc"],
                route_tier=route_tier,
            )
            quote_rows = normalize_quote_rows(
                response,
                market_ticker=selected_market["market_ticker"],
                route_tier=route_tier,
            )
            for anchor_seconds in TIME_TO_CLOSE_ANCHORS_SECONDS:
                anchor = select_anchor_observation(
                    quote_rows,
                    close_time_utc=selected_event["close_time_utc"],
                    anchor_seconds=anchor_seconds,
                )
                if anchor is None:
                    quote_audit.append(
                        {
                            "schema_version": QUOTE_AUDIT_SCHEMA_VERSION,
                            "run_id": run_id,
                            "event_ticker": selected_event["event_ticker"],
                            "market_ticker": selected_market["market_ticker"],
                            "anchor_seconds": anchor_seconds,
                            "anchor_available": False,
                            "raw_observation_id": "",
                            "exclusion_reason": "no_valid_quote_at_or_before_anchor_within_60s",
                        }
                    )
                    continue
                quote_audit.append(
                    {
                        "schema_version": QUOTE_AUDIT_SCHEMA_VERSION,
                        "run_id": run_id,
                        "event_ticker": selected_event["event_ticker"],
                        "market_ticker": selected_market["market_ticker"],
                        "anchor_seconds": anchor_seconds,
                        "anchor_available": True,
                        "raw_observation_id": anchor["raw_observation_id"],
                        "exclusion_reason": "",
                    }
                )
                state = build_historical_reconstructed_state(
                    selected_market=selected_market,
                    selected_anchor=anchor,
                    close_time_utc=selected_event["close_time_utc"],
                    raw_receive_monotonic_ns=response.received_monotonic_ns,
                    alignment_epoch_id=f"historical:{run_id}",
                )
                states.append(state)

    if fully_validated_selected_events != len(selected_events):
        _error("not every selected event completed full-ladder semantic validation")

    dataset = build_preoutcome_dataset(states, split_rows)
    split_stats = split_summary(split_rows)
    quote_available = sum(bool(row["anchor_available"]) for row in quote_audit)
    quote_missing = len(quote_audit) - quote_available
    summary = {
        "run_id": run_id,
        "series_ticker": SERIES_TICKER,
        "materialization_fingerprint": materialization_fingerprint(),
        "market_settled_cutoff_utc": cutoff,
        "cutoff_raw_ref": _raw_ref(cutoff_response),
        "conservative_modern_start_utc": regime_evidence.first_modern_close_utc,
        "checkpoint10_last_old_observed_close_utc": regime_evidence.last_old_close_utc,
        "checkpoint10_first_modern_observed_event": regime_evidence.first_modern_event_ticker,
        "checkpoint10_regime_report": regime_evidence.source_report_path,
        "checkpoint10_regime_report_sha256": regime_evidence.source_report_sha256,
        "settled_event_census_count": len(event_census),
        "event_strike_date_missing_count": 0,
        "event_strike_date_duplicate_count": 0,
        "conservative_modern_sampling_frame_count": len(modern_events),
        "fully_validated_selected_event_count": fully_validated_selected_events,
        "unsampled_event_semantics_claimed_proven": False,
        "split": split_stats,
        "selected_event_count": len(selected_events),
        "selected_market_count": len(selected_market_rows),
        "anchor_attempt_count": len(quote_audit),
        "anchor_available_count": quote_available,
        "anchor_missing_count": quote_missing,
        "state_count": len(states),
        "dataset": dataset.summary,
        "checkpoint10_quarantine_event_count": len(quarantine.event_tickers),
        "checkpoint10_quarantine_primitive_count": len(quarantine.primitive_ids),
        "outcomes_materialized": False,
        "model_fit_performed": False,
        "authentication_used": False,
        "orders_placed": 0,
    }
    return PreoutcomeCollectionRows(
        event_census=event_census,
        modern_events=modern_events,
        split_rows=split_rows,
        selected_events=selected_events,
        selected_markets=tuple(selected_market_rows),
        quote_audit=tuple(quote_audit),
        states=tuple(states),
        dataset_rows=dataset.rows,
        exclusions=dataset.exclusions,
        summary=summary,
    )

def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            missing = set(fields) - set(row)
            extra = set(row) - set(fields)
            if missing or extra:
                _error(f"CSV row schema mismatch for {path.name}; missing={sorted(missing)}, extra={sorted(extra)}")
            writer.writerow({key: _csv_value(row[key]) for key in fields})


def write_preoutcome_collection(
    output_dir: str | Path,
    *,
    run_id: str,
    rows: PreoutcomeCollectionRows,
) -> CsvPaths:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = CsvPaths(
        event_census=root / f"{run_id}_kxbtcd_event_census.csv",
        modern_events=root / f"{run_id}_kxbtcd_modern_events.csv",
        split_rows=root / f"{run_id}_kxbtcd_split_rows.csv",
        selected_events=root / f"{run_id}_kxbtcd_selected_events.csv",
        selected_markets=root / f"{run_id}_kxbtcd_selected_markets.csv",
        quote_audit=root / f"{run_id}_kxbtcd_quote_anchor_audit.csv",
        states_csv=root / f"{run_id}_kxbtcd_historical_states.csv",
        dataset_rows=root / f"{run_id}_kxbtcd_preoutcome_dataset.csv",
        exclusions=root / f"{run_id}_kxbtcd_preoutcome_exclusions.csv",
    )
    _write_csv(paths.event_census, EVENT_CENSUS_FIELDS, rows.event_census)
    _write_csv(paths.modern_events, MODERN_EVENT_FIELDS, rows.modern_events)
    from .kxbtcd_chronological_split_contract import SPLIT_ROW_FIELDS
    _write_csv(paths.split_rows, SPLIT_ROW_FIELDS, rows.split_rows)
    _write_csv(paths.selected_events, SELECTED_EVENT_FIELDS, rows.selected_events)
    _write_csv(paths.selected_markets, SELECTED_MARKET_FIELDS, rows.selected_markets)
    _write_csv(paths.quote_audit, QUOTE_AUDIT_FIELDS, rows.quote_audit)
    _write_csv(paths.dataset_rows, DATASET_ROW_FIELDS, rows.dataset_rows)
    _write_csv(paths.exclusions, EXCLUSION_ROW_FIELDS, rows.exclusions)
    state_audit_rows: list[dict[str, Any]] = []
    for state in rows.states:
        if state.get("state_view") != HISTORICAL_STATE_VIEW:
            _error("only historical_reconstructed states may be persisted by this collector")
        if FORBIDDEN_OUTCOME_KEYS.intersection(state):
            _error("state unexpectedly contains forbidden outcome/downstream fields")
        context = state.get("product_context")
        if not isinstance(context, Mapping):
            _error("historical state product_context must be a mapping")
        state_audit_rows.append({
            "state_id": _text(state.get("state_id"), "state.state_id"),
            "state_view": _text(state.get("state_view"), "state.state_view"),
            "event_ticker": _text(context.get("event_ticker"), "state.event_ticker"),
            "market_ticker": _text(context.get("market_ticker"), "state.market_ticker"),
            "as_of_utc": _text(state.get("as_of_utc"), "state.as_of_utc"),
            "state_json": json.dumps(state, sort_keys=True, separators=(",", ":")),
        })
    _write_csv(paths.states_csv, STATE_AUDIT_FIELDS, state_audit_rows)
    return paths
