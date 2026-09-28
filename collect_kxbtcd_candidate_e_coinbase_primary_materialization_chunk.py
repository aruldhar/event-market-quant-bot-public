"""Collect one Coinbase-primary, outcome-blind Candidate-E historical chunk.

Checkpoint 19H-B supersedes only the mandatory Kraken verification/veto used by the
19G historical materializer. Candidate-E formulas, TTC anchors, structural KXBTCD
roles, partition sizes, untouched queue, and outcome firewall remain unchanged.

This collector uses Kalshi + Coinbase only. Kraken is not queried and cannot block a
row or event. No outcomes are read and no Candidate-E model is fit.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from collect_kxbtcd_candidate_e_historical_materialization_chunk import (
    COINBASE_RAW_ROOT,
    MAX_CHUNK_COUNT,
    _all_raw_paths,
    _fetch_coinbase_event_window,
    _fetch_historical_ladder,
    _parse_utc,
    _write_csv,
)
from src.config import (
    DEFAULT_MANIFEST_ROOT,
    DEFAULT_RAW_LOG_ROOT,
    DEFAULT_RUNTIME_EVENT_ROOT,
    KALSHI_PUBLIC_BASE_URL,
)
from src.kxbtcd_candidate_e_coinbase_primary_materialization import (
    ANCHOR_SCHEMA_VERSION,
    EVENT_SCHEMA_VERSION,
    FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
    FROZEN_CONTRACT_FINGERPRINT,
    PREOUTCOME_ROW_FIELDS,
    RAW_QUEUE_CONSUMPTION_LIMIT,
    TTC_TARGET_MINUTES,
    CandidateEHistoricalMaterializationError,
    build_coinbase_primary_candidate_row,
    evaluate_historical_coinbase_state,
    event_is_eligible,
    load_frozen_untouched_queue,
    validate_coinbase_primary_amendment,
)
from src.kxbtcd_independent_btc_historical_materialization import (
    COINBASE_BASE_URL,
    completed_minute_bounds,
    lookback_minute_bounds,
)
from src.kxbtcd_preoutcome_collector import (
    KxbtcdPreoutcomeCollectorError,
    fetch_anchor_window,
    normalize_quote_rows,
)
from src.kxbtcd_preoutcome_materialization import (
    KxbtcdPreoutcomeMaterializationError,
    select_anchor_observation,
)
from src.public_census_http import PublicCensusHttpClient, PublicCensusHttpError
from src.raw_json_log import RawLogWriteError
from src.run_manifest import CollectionRunManifest, RunManifestError
from src.runtime_events import RuntimeEventLogger, RuntimeEventWriteError

CANONICAL_ROOT = Path("data/derived/kxbtcd_candidate_e_coinbase_primary_materialization/chunks")
SMOKE_ROOT = Path("data/analysis/kxbtcd_candidate_e_coinbase_primary_materialization_smoke")
COLLECTOR_NAME = "collect_kxbtcd_candidate_e_coinbase_primary_materialization_chunk"

EVENT_FIELDS = (
    "schema_version",
    "contract_fingerprint",
    "source_amendment_fingerprint",
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
    "source_amendment_fingerprint",
    "event_ticker",
    "event_close_time_utc",
    "queue_index_zero_based",
    "ttc_target_minutes",
    "decision_target_utc",
    "anchor_eligible",
    "valid_kalshi_role_count",
    "valid_kalshi_roles_json",
    "coinbase_state_eligible",
    "coinbase_exclusion_reasons_json",
    "source_chunk_run_id",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-index", type=int, required=True)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--smoke", action="store_true")
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


def _output_paths(*, smoke: bool, run_id: str) -> tuple[Path, Path, Path]:
    root = SMOKE_ROOT if smoke else CANONICAL_ROOT
    return (
        root / f"{run_id}_events.csv",
        root / f"{run_id}_anchors.csv",
        root / f"{run_id}_rows.csv",
    )


def _materialize_event(
    *,
    event: Mapping[str, Any],
    run_id: str,
    cutoff_utc: datetime,
    kalshi: PublicCensusHttpClient,
    coinbase: PublicCensusHttpClient,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    ticker = str(event["event_ticker"])
    close_text = str(event["strike_date_utc"])
    queue_index = int(event["queue_index_zero_based"])
    if _parse_utc(close_text) >= cutoff_utc:
        raise CandidateEHistoricalMaterializationError(
            f"event {ticker} is not older than current historical market cutoff"
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
            "source_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
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
                "source_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
                "event_ticker": ticker,
                "event_close_time_utc": close_text,
                "queue_index_zero_based": queue_index,
                "ttc_target_minutes": minute,
                "decision_target_utc": str(_parse_utc(close_text).replace()).replace("+00:00", "Z"),
                "anchor_eligible": False,
                "valid_kalshi_role_count": 0,
                "valid_kalshi_roles_json": [],
                "coinbase_state_eligible": False,
                "coinbase_exclusion_reasons_json": [structural_exclusion],
                "source_chunk_run_id": run_id,
            }
            for minute in TTC_TARGET_MINUTES
        ]
        # Replace decision times with the frozen helper after constructing fixed schema.
        from src.kxbtcd_candidate_e_historical_materialization import decision_target_utc
        for anchor, minute in zip(anchors, TTC_TARGET_MINUTES):
            anchor["decision_target_utc"] = decision_target_utc(close_text, minute)
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

    from src.kxbtcd_candidate_e_historical_materialization import decision_target_utc

    target_bounds: dict[int, tuple[str, str, str]] = {}
    required_minutes: set[str] = set()
    for minute in TTC_TARGET_MINUTES:
        target = decision_target_utc(close_text, minute)
        current_start, _current_end = completed_minute_bounds(target)
        lookback_start, _lookback_end = lookback_minute_bounds(target)
        target_bounds[minute] = (target, current_start, lookback_start)
        required_minutes.add(current_start)
        required_minutes.add(lookback_start)

    coinbase_minutes = _fetch_coinbase_event_window(coinbase, sorted(required_minutes))
    structural_by_role = {row["structural_role"]: row for row in structural}

    anchor_rows: list[dict[str, Any]] = []
    common_rows: list[dict[str, Any]] = []
    anchor_flags: list[bool] = []
    event_reasons: list[str] = []

    for minute in TTC_TARGET_MINUTES:
        target, current_start, lookback_start = target_bounds[minute]
        cb_current = coinbase_minutes.get(current_start)
        cb_lookback = coinbase_minutes.get(lookback_start)
        state = evaluate_historical_coinbase_state(
            coinbase_current_price=cb_current.close_price if cb_current else None,
            coinbase_lookback_price=cb_lookback.close_price if cb_lookback else None,
        )
        valid_roles = [role for role in structural_by_role if quote_by_role[role][minute] is not None]
        anchor_eligible = bool(state.eligible and valid_roles)
        anchor_flags.append(anchor_eligible)

        reasons = list(state.exclusion_reasons)
        if not valid_roles:
            reasons.append("missing_valid_kalshi_quote_at_anchor")
        if not anchor_eligible:
            event_reasons.extend(reasons)

        anchor_rows.append(
            {
                "schema_version": ANCHOR_SCHEMA_VERSION,
                "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
                "source_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
                "event_ticker": ticker,
                "event_close_time_utc": close_text,
                "queue_index_zero_based": queue_index,
                "ttc_target_minutes": minute,
                "decision_target_utc": target,
                "anchor_eligible": anchor_eligible,
                "valid_kalshi_role_count": len(valid_roles),
                "valid_kalshi_roles_json": valid_roles,
                "coinbase_state_eligible": state.eligible,
                "coinbase_exclusion_reasons_json": list(state.exclusion_reasons),
                "source_chunk_run_id": run_id,
            }
        )

        if not state.eligible:
            continue
        assert cb_current is not None and cb_lookback is not None
        for role in valid_roles:
            selected_market = structural_by_role[role]
            quote = quote_by_role[role][minute]
            assert quote is not None
            refs = [
                *selected_market["source_lineage_refs"],
                quote["raw_observation_id"],
                *cb_current.raw_observation_refs,
                *cb_lookback.raw_observation_refs,
            ]
            common_rows.append(
                build_coinbase_primary_candidate_row(
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
                    coinbase_lookback_minute_start_utc=lookback_start,
                    coinbase_lookback_price=cb_lookback.close_price,
                    raw_observation_refs=refs,
                )
            )

    eligible_event, eligible_anchor_count = event_is_eligible(anchor_flags)
    if not eligible_event:
        event_reasons.append("fewer_than_four_eligible_anchors")
    event_row = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "source_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
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
    validate_coinbase_primary_amendment()
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

    manifest = CollectionRunManifest(
        collector_name=COLLECTOR_NAME,
        arguments={
            "checkpoint_id": "19H-B",
            "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
            "source_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
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
        ],
        runtime_observability=True,
    )
    runtime = RuntimeEventLogger(
        DEFAULT_RUNTIME_EVENT_ROOT,
        run_id=manifest.run_id,
        collector_name=COLLECTOR_NAME,
        started_at_utc=manifest.started_at_utc,
    )
    for client in (kalshi, coinbase):
        client.attach_runtime_event_logger(runtime)

    event_path, anchor_path, row_path = _output_paths(smoke=args.smoke, run_id=manifest.run_id)
    derived: list[Path] = []
    event_rows: list[dict[str, Any]] = []
    anchor_rows: list[dict[str, Any]] = []
    common_rows: list[dict[str, Any]] = []

    try:
        runtime.emit(
            "collector.started",
            severity="info",
            message="Checkpoint-19H-B Coinbase-primary Candidate-E materialization started",
            context={
                "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
                "source_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
                "start_index": args.start_index,
                "count": args.count,
                "smoke": args.smoke,
                "kraken_required": False,
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
            )
            event_rows.append(event_row)
            anchor_rows.extend(event_anchors)
            common_rows.extend(event_common)
            runtime.emit(
                "materialization.event.completed",
                severity="info",
                message="Coinbase-primary Candidate-E event materialization completed",
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
            message="Checkpoint-19H-B Coinbase-primary Candidate-E materialization completed",
            context={
                "processed_events": len(event_rows),
                "eligible_events": sum(bool(row["eligible_event"]) for row in event_rows),
                "common_rows": len(common_rows),
                "kraken_required": False,
                "outcomes_accessed": False,
                "orders_placed": 0,
            },
        )
        manifest.complete(
            raw_files=_all_raw_paths(kalshi, coinbase),
            derived_csv_files=derived,
            runtime_event_files=runtime.written_paths,
            result={
                "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
                "source_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
                "start_index": args.start_index,
                "count": args.count,
                "smoke": args.smoke,
                "processed_events": len(event_rows),
                "eligible_events": sum(bool(row["eligible_event"]) for row in event_rows),
                "ineligible_events": sum(not bool(row["eligible_event"]) for row in event_rows),
                "common_rows": len(common_rows),
                "kraken_requests": 0,
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
                message="Checkpoint-19H-B Coinbase-primary Candidate-E materialization failed",
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
                raw_files=_all_raw_paths(kalshi, coinbase),
                derived_csv_files=[path for path in derived if path.exists()],
                runtime_event_files=runtime.written_paths,
                result={
                    "source_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
                    "kraken_requests": 0,
                    "outcomes_accessed": False,
                    "candidate_e_fit_performed": False,
                    "orders_placed": 0,
                },
            )
        except RunManifestError:
            pass
        raise

    print("Checkpoint 19H-B Coinbase-primary historical materialization chunk: PASS")
    print(f"Parent contract fingerprint: {FROZEN_CONTRACT_FINGERPRINT}")
    print(f"Source amendment fingerprint: {FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT}")
    print(f"Queue range: [{args.start_index}, {end_index})")
    print(f"Events processed: {len(event_rows)}")
    print(f"Eligible events: {sum(bool(row['eligible_event']) for row in event_rows)}")
    print(f"Ineligible events: {sum(not bool(row['eligible_event']) for row in event_rows)}")
    print(f"Common Candidate-E rows: {len(common_rows)}")
    print(f"Smoke: {args.smoke}")
    print("Kraken requests: 0")
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
        raise SystemExit(f"Coinbase-primary Candidate-E materialization error: {exc}") from exc
