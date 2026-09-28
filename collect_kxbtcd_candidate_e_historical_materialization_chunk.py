"""Collect one raw-first, outcome-blind Checkpoint-19G historical materialization chunk.

The command processes an explicit contiguous slice of the frozen 19F untouched queue.
It never reads Candidate-E labels, fits a model, or performs execution. Canonical
chunks are later combined only by the offline freezer after their manifests complete.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.config import DEFAULT_MANIFEST_ROOT, DEFAULT_RAW_LOG_ROOT, DEFAULT_RUNTIME_EVENT_ROOT, KALSHI_PUBLIC_BASE_URL
from src.kxbtcd_candidate_e_historical_materialization import (
    ANCHOR_SCHEMA_VERSION,
    EVENT_SCHEMA_VERSION,
    FROZEN_CONTRACT_FINGERPRINT,
    MINIMUM_ELIGIBLE_ANCHORS,
    PREOUTCOME_ROW_FIELDS,
    RAW_QUEUE_CONSUMPTION_LIMIT,
    TTC_TARGET_MINUTES,
    CandidateEHistoricalMaterializationError,
    anchor_is_eligible,
    build_common_candidate_row,
    decision_target_utc,
    evaluate_historical_btc_pair,
    event_is_eligible,
    load_frozen_untouched_queue,
    project_historical_market_metadata,
    validate_contract,
)
from src.kxbtcd_chronological_split_contract import TARGET_REGIME_ID
from src.kxbtcd_independent_btc_historical_materialization import (
    COINBASE_BASE_URL,
    COINBASE_CANDLES_PATH,
    COINBASE_GRANULARITY_SECONDS,
    KRAKEN_BASE_URL,
    KRAKEN_MAX_PAGES_PER_MINUTE,
    KRAKEN_PAGE_COUNT,
    KRAKEN_POSTTRADE_PATH,
    KRAKEN_SYMBOL,
    completed_minute_bounds,
    lookback_minute_bounds,
    parse_coinbase_candles_payload,
    parse_kraken_posttrade_payload,
    select_kraken_minute,
)
from src.kxbtcd_preoutcome_collector import (
    KxbtcdPreoutcomeCollectorError,
    _strike_dollars,
    _validate_market_semantics,
    fetch_anchor_window,
    normalize_quote_rows,
    provisional_modern_primitive_id,
)
from src.kxbtcd_preoutcome_materialization import (
    KxbtcdPreoutcomeMaterializationError,
    select_anchor_observation,
    select_structural_markets,
)
from src.public_census_http import PublicCensusHttpClient, PublicCensusHttpError, PublicJsonResponse
from src.raw_json_log import RawLogWriteError
from src.run_manifest import CollectionRunManifest, RunManifestError
from src.runtime_events import RuntimeEventLogger, RuntimeEventWriteError

CANONICAL_ROOT = Path("data/derived/kxbtcd_candidate_e_historical_materialization/chunks")
SMOKE_ROOT = Path("data/analysis/kxbtcd_candidate_e_historical_materialization_smoke")
COINBASE_RAW_ROOT = Path("data/raw/coinbase_exchange_rest")
KRAKEN_RAW_ROOT = Path("data/raw/kraken_spot_rest")
MARKET_LIMIT = 1000
MAX_CHUNK_COUNT = 100

EVENT_FIELDS = (
    "schema_version",
    "contract_fingerprint",
    "event_ticker",
    "event_close_time_utc",
    "queue_index_zero_based",
    "eligible_event",
    "eligible_anchor_count",
    "common_row_count",
    "exclusion_reasons_json",
    "selected_market_roles_json",
    "source_chunk_run_id",
)
ANCHOR_FIELDS = (
    "schema_version",
    "contract_fingerprint",
    "event_ticker",
    "event_close_time_utc",
    "queue_index_zero_based",
    "ttc_target_minutes",
    "decision_target_utc",
    "anchor_eligible",
    "valid_kalshi_role_count",
    "valid_kalshi_roles_json",
    "btc_pair_eligible",
    "btc_exclusion_reasons_json",
    "current_disagreement_bps",
    "lookback_disagreement_bps",
    "source_chunk_run_id",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-index", type=int, required=True, help="Zero-based untouched-queue start index")
    parser.add_argument("--count", type=int, default=50, help="Number of contiguous queue events (default 50, max 100)")
    parser.add_argument("--smoke", action="store_true", help="Write to noncanonical smoke root; never used by final freezer")
    args = parser.parse_args()
    if args.start_index < 0:
        parser.error("--start-index must be nonnegative")
    if args.count <= 0 or args.count > MAX_CHUNK_COUNT:
        parser.error(f"--count must be in [1,{MAX_CHUNK_COUNT}]")
    if not args.smoke and args.start_index + args.count > RAW_QUEUE_CONSUMPTION_LIMIT:
        parser.error(
            f"canonical chunk would cross protected queue-consumption limit {RAW_QUEUE_CONSUMPTION_LIMIT}"
        )
    return args


def _raw_ref(response: PublicJsonResponse) -> str:
    ref = response.raw_record
    return f"raw:{ref.source}:{ref.session_id}:{ref.request_id}"


def _format_request_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _json_cell(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for original in rows:
            row = dict(original)
            if set(row) != set(fields):
                raise CandidateEHistoricalMaterializationError(
                    f"CSV schema mismatch for {path.name}: missing={sorted(set(fields)-set(row))}, extra={sorted(set(row)-set(fields))}"
                )
            writer.writerow({key: _json_cell(value) if isinstance(value, (list, dict, tuple)) else value for key, value in row.items()})


def _all_raw_paths(*clients: PublicCensusHttpClient) -> list[Path]:
    paths: list[Path] = []
    for client in clients:
        paths.extend(client.raw_recorder.written_paths)
    return paths


def _chunk_output_paths(*, smoke: bool, run_id: str) -> tuple[Path, Path, Path]:
    """Return bounded derived paths without repeating run_id in a smoke subdirectory.

    The filename already contains the globally unique run_id. Repeating that same
    long identifier as a directory component can exceed the traditional Windows
    MAX_PATH limit in repositories located under OneDrive.
    """
    root = SMOKE_ROOT if smoke else CANONICAL_ROOT
    return (
        root / f"{run_id}_events.csv",
        root / f"{run_id}_anchors.csv",
        root / f"{run_id}_rows.csv",
    )


def _fetch_historical_ladder(
    client: PublicCensusHttpClient,
    *,
    event_ticker: str,
    event_close_time_utc: str,
) -> tuple[tuple[dict[str, Any], ...], str] | tuple[None, str]:
    response = client.get_json(
        "/historical/markets",
        params={"event_ticker": event_ticker, "limit": MARKET_LIMIT},
    )
    payload = response.payload
    markets = payload.get("markets")
    if not isinstance(markets, list):
        raise CandidateEHistoricalMaterializationError("historical market response 'markets' must be list")
    cursor = payload.get("cursor", "")
    if not isinstance(cursor, str):
        raise CandidateEHistoricalMaterializationError("historical market cursor must be string")
    if cursor:
        raise CandidateEHistoricalMaterializationError(
            f"event {event_ticker} exceeded {MARKET_LIMIT} historical markets"
        )
    if not markets:
        raise CandidateEHistoricalMaterializationError(f"event {event_ticker} historical ladder is empty")

    raw_ref = _raw_ref(response)
    normalized: list[dict[str, Any]] = []
    primitive: str | None = None
    seen_tickers: set[str] = set()
    for source_market in markets:
        projected = project_historical_market_metadata(source_market)
        regime, observed_close, observed_primitive = _validate_market_semantics(
            projected,
            expected_event_ticker=event_ticker,
        )
        if regime != TARGET_REGIME_ID:
            raise CandidateEHistoricalMaterializationError(
                f"event {event_ticker} contains non-target settlement regime {regime}"
            )
        if observed_close != event_close_time_utc:
            raise CandidateEHistoricalMaterializationError(
                f"event {event_ticker} market close disagrees with frozen census close"
            )
        if primitive is None:
            primitive = observed_primitive
        elif primitive != observed_primitive:
            raise CandidateEHistoricalMaterializationError(
                f"event {event_ticker} ladder has multiple settlement primitives"
            )
        ticker = str(projected["ticker"]).strip()
        if ticker in seen_tickers:
            raise CandidateEHistoricalMaterializationError(f"duplicate market ticker in event {event_ticker}: {ticker}")
        seen_tickers.add(ticker)
        normalized.append(
            {
                "event_ticker": event_ticker,
                "market_ticker": ticker,
                "strike_type": projected["strike_type"],
                "strike_dollars": _strike_dollars(projected),
                "source_lineage_refs": [raw_ref],
            }
        )

    if primitive != provisional_modern_primitive_id(event_close_time_utc):
        raise CandidateEHistoricalMaterializationError(
            f"event {event_ticker} settlement primitive disagrees with frozen modern signature"
        )
    if len(normalized) < 5:
        return None, "fewer_than_five_distinct_structural_markets"
    try:
        structural = select_structural_markets(normalized, event_ticker=event_ticker)
    except KxbtcdPreoutcomeMaterializationError as exc:
        if "needs at least" in str(exc) or "collapsed" in str(exc):
            return None, "fewer_than_five_distinct_structural_markets"
        raise
    return tuple(dict(row) for row in structural), ""


def _fetch_coinbase_event_window(
    client: PublicCensusHttpClient,
    required_minute_starts: Sequence[str],
) -> dict[str, Any]:
    starts = sorted(_parse_utc(value) for value in set(required_minute_starts))
    if not starts:
        raise CandidateEHistoricalMaterializationError("Coinbase required-minute set is empty")
    request_start = starts[0]
    request_end = starts[-1] + timedelta(minutes=1)
    if (request_end - request_start) > timedelta(minutes=60):
        raise CandidateEHistoricalMaterializationError("event Coinbase request window unexpectedly exceeds 60 minutes")
    response = client.get_json(
        COINBASE_CANDLES_PATH,
        params={
            "granularity": COINBASE_GRANULARITY_SECONDS,
            "start": _format_request_time(request_start),
            "end": _format_request_time(request_end),
        },
        top_level_container="array",
    )
    return parse_coinbase_candles_payload(response.payload, raw_observation_ref=_raw_ref(response))


def _fetch_kraken_minute(
    client: PublicCensusHttpClient,
    minute_start_utc: str,
) -> tuple[tuple[Any, ...], tuple[str, ...]]:
    minute_start = _parse_utc(minute_start_utc)
    minute_end = minute_start + timedelta(minutes=1)
    cursor = minute_start - timedelta(microseconds=1)
    to_ts = minute_end - timedelta(microseconds=1)
    all_trades: list[Any] = []
    refs: list[str] = []
    seen_cursors: set[str] = set()
    for _ in range(KRAKEN_MAX_PAGES_PER_MINUTE):
        response = client.get_json(
            KRAKEN_POSTTRADE_PATH,
            params={
                "symbol": KRAKEN_SYMBOL,
                "from_ts": _format_request_time(cursor),
                "to_ts": _format_request_time(to_ts),
                "count": KRAKEN_PAGE_COUNT,
            },
        )
        refs.append(_raw_ref(response))
        trades, last_ts, count = parse_kraken_posttrade_payload(response.payload)
        all_trades.extend(trades)
        if count < KRAKEN_PAGE_COUNT:
            return tuple(all_trades), tuple(refs)
        if last_ts is None:
            raise CandidateEHistoricalMaterializationError(
                "full Kraken minute page omitted pagination cursor"
            )
        if last_ts in seen_cursors:
            raise CandidateEHistoricalMaterializationError("Kraken pagination cursor repeated")
        seen_cursors.add(last_ts)
        next_cursor = _parse_utc(last_ts)
        if next_cursor <= cursor:
            raise CandidateEHistoricalMaterializationError("Kraken pagination cursor did not advance")
        cursor = next_cursor
    raise CandidateEHistoricalMaterializationError(
        f"Kraken minute exceeded frozen {KRAKEN_MAX_PAGES_PER_MINUTE}-page guard"
    )


def _materialize_event(
    *,
    event: Mapping[str, Any],
    run_id: str,
    cutoff_utc: datetime,
    kalshi: PublicCensusHttpClient,
    coinbase: PublicCensusHttpClient,
    kraken: PublicCensusHttpClient,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    ticker = str(event["event_ticker"])
    close_text = str(event["strike_date_utc"])
    queue_index = int(event["queue_index_zero_based"])
    close_dt = _parse_utc(close_text)
    if close_dt >= cutoff_utc:
        raise CandidateEHistoricalMaterializationError(
            f"event {ticker} is not older than current historical market cutoff; canonical 19G chunks require historical route"
        )

    structural, structural_exclusion = _fetch_historical_ladder(
        kalshi,
        event_ticker=ticker,
        event_close_time_utc=close_text,
    )
    if structural is None:
        event_row = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
            "event_ticker": ticker,
            "event_close_time_utc": close_text,
            "queue_index_zero_based": queue_index,
            "eligible_event": False,
            "eligible_anchor_count": 0,
            "common_row_count": 0,
            "exclusion_reasons_json": [structural_exclusion],
            "selected_market_roles_json": [],
            "source_chunk_run_id": run_id,
        }
        anchors = [
            {
                "schema_version": ANCHOR_SCHEMA_VERSION,
                "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
                "event_ticker": ticker,
                "event_close_time_utc": close_text,
                "queue_index_zero_based": queue_index,
                "ttc_target_minutes": minute,
                "decision_target_utc": decision_target_utc(close_text, minute),
                "anchor_eligible": False,
                "valid_kalshi_role_count": 0,
                "valid_kalshi_roles_json": [],
                "btc_pair_eligible": False,
                "btc_exclusion_reasons_json": [structural_exclusion],
                "current_disagreement_bps": "",
                "lookback_disagreement_bps": "",
                "source_chunk_run_id": run_id,
            }
            for minute in TTC_TARGET_MINUTES
        ]
        return event_row, anchors, []

    quote_by_role: dict[str, dict[int, Mapping[str, Any] | None]] = {}
    for selected_market in structural:
        role = selected_market["structural_role"]
        response = fetch_anchor_window(
            kalshi,
            market_ticker=selected_market["market_ticker"],
            close_time_utc=close_text,
            route_tier="historical",
        )
        quotes = normalize_quote_rows(
            response,
            market_ticker=selected_market["market_ticker"],
            route_tier="historical",
        )
        quote_by_role[role] = {
            minute: select_anchor_observation(
                quotes,
                close_time_utc=close_text,
                anchor_seconds=minute * 60,
            )
            for minute in TTC_TARGET_MINUTES
        }

    target_bounds: dict[int, tuple[str, str, str, str, str]] = {}
    required_minutes: set[str] = set()
    for minute in TTC_TARGET_MINUTES:
        target = decision_target_utc(close_text, minute)
        current_start, current_end = completed_minute_bounds(target)
        lookback_start, lookback_end = lookback_minute_bounds(target)
        target_bounds[minute] = (target, current_start, current_end, lookback_start, lookback_end)
        required_minutes.add(current_start)
        required_minutes.add(lookback_start)

    coinbase_minutes = _fetch_coinbase_event_window(coinbase, sorted(required_minutes))
    kraken_minutes = {
        minute_start: _fetch_kraken_minute(kraken, minute_start)
        for minute_start in sorted(required_minutes)
    }

    anchor_rows: list[dict[str, Any]] = []
    common_rows: list[dict[str, Any]] = []
    anchor_flags: list[bool] = []
    event_reasons: list[str] = []

    structural_by_role = {row["structural_role"]: row for row in structural}
    for minute in TTC_TARGET_MINUTES:
        target, current_start, current_end, lookback_start, lookback_end = target_bounds[minute]
        cb_current = coinbase_minutes.get(current_start)
        cb_lookback = coinbase_minutes.get(lookback_start)
        current_trades, current_refs = kraken_minutes[current_start]
        lookback_trades, lookback_refs = kraken_minutes[lookback_start]
        kr_current = select_kraken_minute(
            current_trades,
            minute_start_utc=current_start,
            minute_end_utc=current_end,
            as_of_utc=target,
            raw_observation_refs=current_refs,
        )
        kr_lookback = select_kraken_minute(
            lookback_trades,
            minute_start_utc=lookback_start,
            minute_end_utc=lookback_end,
            as_of_utc=target,
            raw_observation_refs=lookback_refs,
        )
        pair = evaluate_historical_btc_pair(
            coinbase_current_price=cb_current.close_price if cb_current else None,
            kraken_current_price=kr_current.selected_price,
            coinbase_lookback_price=cb_lookback.close_price if cb_lookback else None,
            kraken_lookback_price=kr_lookback.selected_price,
        )
        valid_roles = [role for role in structural_by_role if quote_by_role[role][minute] is not None]
        anchor_eligible = anchor_is_eligible(
            btc_pair_eligible=pair.eligible,
            valid_common_row_count=len(valid_roles),
        )
        anchor_flags.append(anchor_eligible)
        reasons = list(pair.exclusion_reasons)
        if not valid_roles:
            reasons.append("missing_valid_kalshi_quote_at_anchor")
        if not anchor_eligible:
            event_reasons.extend(reasons)

        anchor_rows.append(
            {
                "schema_version": ANCHOR_SCHEMA_VERSION,
                "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
                "event_ticker": ticker,
                "event_close_time_utc": close_text,
                "queue_index_zero_based": queue_index,
                "ttc_target_minutes": minute,
                "decision_target_utc": target,
                "anchor_eligible": anchor_eligible,
                "valid_kalshi_role_count": len(valid_roles),
                "valid_kalshi_roles_json": valid_roles,
                "btc_pair_eligible": pair.eligible,
                "btc_exclusion_reasons_json": list(pair.exclusion_reasons),
                "current_disagreement_bps": "" if pair.current_disagreement_bps is None else repr(pair.current_disagreement_bps),
                "lookback_disagreement_bps": "" if pair.lookback_disagreement_bps is None else repr(pair.lookback_disagreement_bps),
                "source_chunk_run_id": run_id,
            }
        )

        if not pair.eligible:
            continue
        assert cb_current is not None and cb_lookback is not None
        assert kr_current.selected_price is not None and kr_lookback.selected_price is not None
        assert pair.current_disagreement_bps is not None and pair.lookback_disagreement_bps is not None
        for role in valid_roles:
            selected_market = structural_by_role[role]
            quote = quote_by_role[role][minute]
            assert quote is not None
            refs = [
                *selected_market["source_lineage_refs"],
                quote["raw_observation_id"],
                *cb_current.raw_observation_refs,
                *kr_current.raw_observation_refs,
                *cb_lookback.raw_observation_refs,
                *kr_lookback.raw_observation_refs,
            ]
            common_rows.append(
                build_common_candidate_row(
                    event_ticker=ticker,
                    event_close_time_utc=close_text,
                    queue_index_zero_based=queue_index,
                    structural_role=role,
                    market_ticker=selected_market["market_ticker"],
                    strike_dollars=selected_market["strike_dollars"],
                    ttc_target_minutes=minute,
                    decision_target=target,
                    kalshi_anchor=quote,
                    coinbase_current_minute_start_utc=current_start,
                    coinbase_current_price=cb_current.close_price,
                    kraken_current_price=kr_current.selected_price,
                    current_disagreement_bps=pair.current_disagreement_bps,
                    coinbase_lookback_minute_start_utc=lookback_start,
                    coinbase_lookback_price=cb_lookback.close_price,
                    kraken_lookback_price=kr_lookback.selected_price,
                    lookback_disagreement_bps=pair.lookback_disagreement_bps,
                    raw_observation_refs=refs,
                )
            )

    eligible_event, eligible_anchor_count = event_is_eligible(anchor_flags)
    if not eligible_event:
        event_reasons.append("fewer_than_four_eligible_anchors")
    event_row = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "event_ticker": ticker,
        "event_close_time_utc": close_text,
        "queue_index_zero_based": queue_index,
        "eligible_event": eligible_event,
        "eligible_anchor_count": eligible_anchor_count,
        "common_row_count": len(common_rows) if eligible_event else 0,
        "exclusion_reasons_json": [] if eligible_event else sorted(set(event_reasons)),
        "selected_market_roles_json": [row["structural_role"] for row in structural],
        "source_chunk_run_id": run_id,
    }
    if not eligible_event:
        common_rows = []
    return event_row, anchor_rows, common_rows


def main() -> None:
    args = parse_args()
    validate_contract()
    queue = load_frozen_untouched_queue()
    end_index = args.start_index + args.count
    if end_index > len(queue):
        raise CandidateEHistoricalMaterializationError("requested chunk exceeds frozen untouched queue")
    selected = queue[args.start_index:end_index]

    kalshi = PublicCensusHttpClient(
        base_url=KALSHI_PUBLIC_BASE_URL,
        source_name="kalshi_rest_candidate_e_historical",
        raw_root=DEFAULT_RAW_LOG_ROOT,
        timeout_seconds=15.0,
        max_rate_limit_retries=4,
    )
    coinbase = PublicCensusHttpClient(
        base_url=COINBASE_BASE_URL,
        source_name="coinbase_exchange_rest_candidate_e_historical",
        raw_root=COINBASE_RAW_ROOT,
        timeout_seconds=15.0,
        max_rate_limit_retries=4,
    )
    kraken = PublicCensusHttpClient(
        base_url=KRAKEN_BASE_URL,
        source_name="kraken_spot_rest_candidate_e_historical",
        raw_root=KRAKEN_RAW_ROOT,
        timeout_seconds=15.0,
        max_rate_limit_retries=4,
    )

    manifest = CollectionRunManifest(
        collector_name="collect_kxbtcd_candidate_e_historical_materialization_chunk",
        arguments={
            "checkpoint_id": "19G",
            "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
            "start_index": args.start_index,
            "count": args.count,
            "smoke": args.smoke,
            "outcomes_accessed": False,
            "candidate_e_fit_performed": False,
            "execution_enabled": False,
            "orders_placed": 0,
        },
        manifest_root=DEFAULT_MANIFEST_ROOT,
        source_sessions=[
            {"source": kalshi.raw_recorder.source_name, "session_id": kalshi.raw_recorder.session_id},
            {"source": coinbase.raw_recorder.source_name, "session_id": coinbase.raw_recorder.session_id},
            {"source": kraken.raw_recorder.source_name, "session_id": kraken.raw_recorder.session_id},
        ],
        runtime_observability=True,
    )
    runtime = RuntimeEventLogger(
        DEFAULT_RUNTIME_EVENT_ROOT,
        run_id=manifest.run_id,
        collector_name="collect_kxbtcd_candidate_e_historical_materialization_chunk",
        started_at_utc=manifest.started_at_utc,
    )
    for client in (kalshi, coinbase, kraken):
        client.attach_runtime_event_logger(runtime)

    event_path, anchor_path, row_path = _chunk_output_paths(
        smoke=args.smoke,
        run_id=manifest.run_id,
    )
    derived: list[Path] = []

    event_rows: list[dict[str, Any]] = []
    anchor_rows: list[dict[str, Any]] = []
    common_rows: list[dict[str, Any]] = []
    try:
        runtime.emit(
            "collector.started",
            severity="info",
            message="Checkpoint-19G Candidate-E historical materialization chunk started",
            context={
                "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
                "start_index": args.start_index,
                "count": args.count,
                "smoke": args.smoke,
                "outcomes_accessed": False,
                "orders_placed": 0,
            },
        )
        cutoff_response = kalshi.get_json("/historical/cutoff")
        cutoff_text = cutoff_response.payload.get("market_settled_ts")
        if not isinstance(cutoff_text, str):
            raise CandidateEHistoricalMaterializationError("historical cutoff missing market_settled_ts")
        cutoff_utc = _parse_utc(cutoff_text)

        for event in selected:
            event_row, event_anchors, event_common = _materialize_event(
                event=event,
                run_id=manifest.run_id,
                cutoff_utc=cutoff_utc,
                kalshi=kalshi,
                coinbase=coinbase,
                kraken=kraken,
            )
            event_rows.append(event_row)
            anchor_rows.extend(event_anchors)
            common_rows.extend(event_common)
            runtime.emit(
                "materialization.event.completed",
                severity="info",
                message="Historical Candidate-E event materialization completed",
                context={
                    "event_ticker": event_row["event_ticker"],
                    "queue_index_zero_based": event_row["queue_index_zero_based"],
                    "eligible_event": event_row["eligible_event"],
                    "eligible_anchor_count": event_row["eligible_anchor_count"],
                    "common_row_count": event_row["common_row_count"],
                },
            )

        _write_csv(event_path, EVENT_FIELDS, event_rows)
        _write_csv(anchor_path, ANCHOR_FIELDS, anchor_rows)
        _write_csv(row_path, PREOUTCOME_ROW_FIELDS, common_rows)
        derived = [event_path, anchor_path, row_path]
        runtime.emit(
            "collector.completed",
            severity="info",
            message="Checkpoint-19G Candidate-E historical materialization chunk completed",
            context={
                "processed_events": len(event_rows),
                "eligible_events": sum(bool(row["eligible_event"]) for row in event_rows),
                "common_rows": len(common_rows),
                "outcomes_accessed": False,
                "orders_placed": 0,
            },
        )
        manifest.complete(
            raw_files=_all_raw_paths(kalshi, coinbase, kraken),
            derived_csv_files=derived,
            runtime_event_files=runtime.written_paths,
            result={
                "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
                "start_index": args.start_index,
                "count": args.count,
                "smoke": args.smoke,
                "processed_events": len(event_rows),
                "eligible_events": sum(bool(row["eligible_event"]) for row in event_rows),
                "ineligible_events": sum(not bool(row["eligible_event"]) for row in event_rows),
                "common_rows": len(common_rows),
                "outcomes_accessed": False,
                "candidate_e_fit_performed": False,
                "orders_placed": 0,
            },
        )
    except BaseException as exc:
        try:
            runtime.emit(
                "collector.failed",
                severity="critical",
                message="Checkpoint-19G Candidate-E historical materialization chunk failed",
                context={
                    "start_index": args.start_index,
                    "processed_events_before_failure": len(event_rows),
                    "outcomes_accessed": False,
                    "orders_placed": 0,
                },
                error={"type": type(exc).__name__, "message": str(exc)},
            )
        except RuntimeEventWriteError:
            pass
        try:
            manifest.fail(
                exc,
                raw_files=_all_raw_paths(kalshi, coinbase, kraken),
                derived_csv_files=[path for path in derived if path.exists()],
                runtime_event_files=runtime.written_paths,
                result={
                    "outcomes_accessed": False,
                    "candidate_e_fit_performed": False,
                    "orders_placed": 0,
                },
            )
        except RunManifestError:
            pass
        raise

    print("Checkpoint 19G historical materialization chunk: PASS")
    print(f"Contract fingerprint: {FROZEN_CONTRACT_FINGERPRINT}")
    print(f"Queue range: [{args.start_index}, {end_index})")
    print(f"Events processed: {len(event_rows)}")
    print(f"Eligible events: {sum(bool(row['eligible_event']) for row in event_rows)}")
    print(f"Ineligible events: {sum(not bool(row['eligible_event']) for row in event_rows)}")
    print(f"Common Candidate-E rows: {len(common_rows)}")
    print(f"Smoke: {args.smoke}")
    print("New Candidate-E outcomes accessed: 0")
    print("Candidate-E fits performed: 0")
    print("Orders placed: 0")
    print(f"Manifest: {manifest.manifest_path}")
    print(f"Events CSV: {event_path}")
    print(f"Anchors CSV: {anchor_path}")
    print(f"Rows CSV: {row_path}")


if __name__ == "__main__":
    try:
        main()
    except (
        CandidateEHistoricalMaterializationError,
        KxbtcdPreoutcomeCollectorError,
        KxbtcdPreoutcomeMaterializationError,
        PublicCensusHttpError,
        RawLogWriteError,
        RunManifestError,
        RuntimeEventWriteError,
    ) as exc:
        raise SystemExit(f"Candidate-E historical materialization error: {exc}") from exc
