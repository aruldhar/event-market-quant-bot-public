"""Collect Checkpoint-10 outcome-blind BTC market-structure and cluster inventory.

Public/read-only only. No quotes, outcomes, external predictive feeds, models, or
orders are collected or used by this command.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.btc_research_unit import (
    collect_btc_research_unit_rows,
    validate_collected_rows,
    write_collected_csvs,
)
from src.config import (
    DEFAULT_MANIFEST_ROOT,
    DEFAULT_RAW_LOG_ROOT,
    DEFAULT_RUNTIME_EVENT_ROOT,
    KALSHI_PUBLIC_BASE_URL,
)
from src.public_census_http import PublicCensusHttpClient
from src.run_manifest import CollectionRunManifest, RunManifestError
from src.runtime_events import RuntimeEventLogger, RuntimeEventWriteError

DERIVED_ROOT = Path("data/derived/btc_research_unit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-event-pages-per-series",
        type=int,
        default=500,
        help="Fail-closed settled-event pagination guard for each BTC series (default: 500)",
    )
    parser.add_argument(
        "--events-per-series",
        type=int,
        default=25,
        help=(
            "Deterministic SHA-256 event sample cap per BTC series for structural "
            "market collection (default: 25)"
        ),
    )
    parser.add_argument(
        "--max-market-pages-per-event-per-tier",
        type=int,
        default=5,
        help="Fail-closed market pagination guard per sampled event and tier (default: 5)",
    )
    args = parser.parse_args()
    if args.max_event_pages_per_series <= 0:
        parser.error("--max-event-pages-per-series must be positive")
    if args.events_per_series <= 0:
        parser.error("--events-per-series must be positive")
    if args.max_market_pages_per_event_per_tier <= 0:
        parser.error("--max-market-pages-per-event-per-tier must be positive")
    return args


def main() -> None:
    args = parse_args()
    client = PublicCensusHttpClient(
        base_url=KALSHI_PUBLIC_BASE_URL,
        source_name="kalshi_public_rest",
        raw_root=DEFAULT_RAW_LOG_ROOT,
        timeout_seconds=15.0,
    )
    manifest = CollectionRunManifest(
        collector_name="collect_btc_research_unit_inventory",
        arguments={
            "max_event_pages_per_series": args.max_event_pages_per_series,
            "discovery_rule": "Crypto series -> BTC-identifiable series -> series-filtered settled events",
            "events_per_series": args.events_per_series,
            "event_sampling_rule": "sha256_event_ticker_ascending",
            "max_market_pages_per_event_per_tier": args.max_market_pages_per_event_per_tier,
            "event_scope": "complete settled-event discovery within selected BTC series; deterministic structural sample",
            "market_scope": "all public non-MVE settled markets for sampled BTC events",
            "kxbtc15m_cluster_rule": "two validated BRTI boundary primitives",
            "other_btc_cluster_rule": "candidate series+event+close boundary only; requires rule validation",
            "outcomes_materialized": False,
            "quotes_collected": False,
            "external_predictive_feed_used": False,
            "strategy_analysis_run": False,
            "execution_enabled": False,
        },
        manifest_root=DEFAULT_MANIFEST_ROOT,
        source_sessions=[
            {
                "source": client.raw_recorder.source_name,
                "session_id": client.raw_recorder.session_id,
            }
        ],
        runtime_observability=True,
    )
    runtime = RuntimeEventLogger(
        DEFAULT_RUNTIME_EVENT_ROOT,
        run_id=manifest.run_id,
        collector_name="collect_btc_research_unit_inventory",
        started_at_utc=manifest.started_at_utc,
    )
    client.attach_runtime_event_logger(runtime)

    derived_dir = (
        DERIVED_ROOT
        / manifest.started_at_utc[0:4]
        / manifest.started_at_utc[5:7]
        / manifest.started_at_utc[8:10]
    )
    derived_paths: list[Path] = []
    rows = None
    summary: dict[str, int] = {}

    try:
        runtime.emit(
            "collector.started",
            severity="info",
            message="Checkpoint-10 outcome-blind BTC research-unit inventory started",
            context={
                "outcomes_materialized": False,
                "quotes_collected": False,
                "orders_placed": 0,
            },
        )
        rows = collect_btc_research_unit_rows(
            client,
            run_id=manifest.run_id,
            max_event_pages_per_series=args.max_event_pages_per_series,
            events_per_series=args.events_per_series,
            max_market_pages_per_event_per_tier=args.max_market_pages_per_event_per_tier,
        )
        summary = validate_collected_rows(rows, run_id=manifest.run_id)
        paths = write_collected_csvs(derived_dir, run_id=manifest.run_id, rows=rows)
        derived_paths = list(paths.all())

        runtime.emit(
            "collector.completed",
            severity="info",
            message="Checkpoint-10 outcome-blind BTC research-unit inventory completed",
            context={
                **summary,
                "bitcoin_series_count": rows.bitcoin_series_count,
                "primitive_overlap_rows": len(rows.overlaps),
                "outcomes_materialized": False,
                "quotes_collected": False,
                "orders_placed": 0,
            },
        )
        manifest.complete(
            raw_files=client.raw_recorder.written_paths,
            derived_csv_files=derived_paths,
            runtime_event_files=runtime.written_paths,
            result={
                **summary,
                "bitcoin_series_count": rows.bitcoin_series_count,
                "event_pages_scanned": rows.event_pages_scanned,
                "discovered_settled_event_count": rows.discovered_settled_event_count,
                "sampled_event_count": rows.sampled_event_count,
                "events_per_series": rows.events_per_series,
                "historical_market_pages_scanned": rows.historical_market_pages_scanned,
                "live_market_pages_scanned": rows.live_market_pages_scanned,
                "event_scope_fallback_count": rows.event_scope_fallback_count,
                "event_category_mismatch_count": rows.event_category_mismatch_count,
                "cross_tier_duplicate_market_count": rows.cross_tier_duplicate_market_count,
                "market_settled_cutoff": rows.cutoff.market_settled_ts.isoformat(),
                "cutoff_raw_source": rows.cutoff_raw_source,
                "cutoff_raw_session_id": rows.cutoff_raw_session_id,
                "cutoff_raw_request_id": rows.cutoff_raw_request_id,
                "outcomes_materialized": False,
                "quotes_collected": False,
                "external_predictive_feed_used": False,
                "strategy_analysis_run": False,
                "authentication_used": False,
                "orders_placed": 0,
            },
        )
    except BaseException as exc:
        event_failure: RuntimeEventWriteError | None = None
        if not isinstance(exc, RuntimeEventWriteError):
            try:
                runtime.emit(
                    "collector.failed",
                    severity="critical",
                    message="Checkpoint-10 BTC research-unit inventory failed",
                    context={
                        "derived_files_written": len(derived_paths),
                        "outcomes_materialized": False,
                        "quotes_collected": False,
                        "orders_placed": 0,
                    },
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            except RuntimeEventWriteError as log_exc:
                event_failure = log_exc
        failure = event_failure or exc
        try:
            manifest.fail(
                failure,
                raw_files=client.raw_recorder.written_paths,
                derived_csv_files=[path for path in derived_paths if path.exists()],
                runtime_event_files=runtime.written_paths,
                result={
                    "outcomes_materialized": False,
                    "quotes_collected": False,
                    "strategy_analysis_run": False,
                    "authentication_used": False,
                    "orders_placed": 0,
                    "original_failure_type": type(exc).__name__,
                },
            )
        except RunManifestError as manifest_exc:
            raise manifest_exc from failure
        if event_failure is not None:
            raise event_failure from exc
        raise

    assert rows is not None
    print("Checkpoint-10 BTC research-unit inventory: PASS")
    print(f"BTC series: {rows.bitcoin_series_count}")
    print(f"Settled BTC events discovered: {summary['discovered_settled_event_rows']}")
    print(f"BTC events sampled for structure: {summary['sampled_event_rows']}")
    print(f"BTC markets: {summary['market_rows']}")
    print(f"Settlement clusters: {summary['settlement_cluster_rows']}")
    print(f"  resolved: {summary['resolved_cluster_rows']}")
    print(f"  candidate: {summary['candidate_cluster_rows']}")
    print(f"  unresolved: {summary['unresolved_cluster_rows']}")
    print(f"Shared primitive overlap edges: {summary['primitive_overlap_rows']}")
    print("Outcomes materialized: no")
    print("Quotes collected: no")
    print("External predictive feed used: no")
    print("Orders placed: 0")
    print(f"Manifest: {manifest.manifest_path}")


if __name__ == "__main__":
    main()
