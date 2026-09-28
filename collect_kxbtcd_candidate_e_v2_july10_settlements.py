#!/usr/bin/env python3
"""Minimal raw-first outcome collector/scorer for frozen Candidate-E July-10 paths.

Default behavior is zero-network preflight. Real outcome access requires --collect
and is blocked until the implementation checkpoint has been safely closed/pushed.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

from src.public_census_http import PublicCensusHttpClient
from src import kxbtcd_candidate_e_v2_july10_settlement_evaluator as evaluator


def relative(path: Path, repo: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def preflight(repo: Path) -> dict:
    contract, paths = evaluator.load_frozen_inputs(repo)
    fallback = evaluator.fallback_tickers_by_class(contract, paths)
    print("CANDIDATE-E JULY10 SETTLEMENT PREFLIGHT: PASS")
    print("Scenario classes: 27 EXACT / 33 CENSORED")
    print("Exact fallback settlement tickers:", len(fallback["exact_required"]))
    for ticker in fallback["exact_required"]:
        print("  EXACT_REQUIRED:", ticker)
    print("Censored fallback tickers:", len(fallback["censored_fallback"]))
    for ticker in fallback["censored_fallback"]:
        print("  CENSORED_FALLBACK:", ticker)
    print("Exact/censored ticker overlap:", len(fallback["overlap"]))
    for ticker in fallback["overlap"]:
        print("  OVERLAP:", ticker)
    print("Planned network requests if later authorized:", len(fallback["exact_required"]))
    print("Settlement outcomes: NOT ACCESSED")
    print("Strategy P&L: NOT CALCULATED | Strategy: NOT RERUN | Orders: 0")
    return fallback


def collect_and_score(repo: Path) -> int:
    evaluator.require_collection_closeout_gate(repo)
    contract, paths = evaluator.load_frozen_inputs(repo)
    fallback = evaluator.fallback_tickers_by_class(contract, paths)
    required = fallback["exact_required"]

    cached = evaluator.load_cached_required_settlements(repo, required)
    missing = [ticker for ticker in required if ticker not in cached]

    raw_root = repo / "data/raw" / evaluator.SOURCE_NAME
    raw_files_before: set[Path] = set()

    client = None
    if missing:
        client = PublicCensusHttpClient(
            base_url=evaluator.KALSHI_BASE_URL,
            source_name=evaluator.SOURCE_NAME,
            raw_root=raw_root,
            timeout_seconds=15.0,
            max_rate_limit_retries=3,
            rate_limit_backoff_seconds=0.5,
        )
        raw_files_before = set(client.raw_recorder.written_paths)

    requests_made = 0
    source_tier_counts = {"live_recent": 0, "historical": 0}
    for ticker in missing:
        assert client is not None

        live_response = client.get_json(
            evaluator.LIVE_MARKETS_PATH,
            params=evaluator.market_filter_params(ticker),
            top_level_container="object",
        )
        requests_made += 1
        live_market = evaluator.exact_filtered_market(
            expected_ticker=ticker,
            payload=live_response.payload,
            allow_zero=True,
        )

        if live_market is not None:
            response = live_response
            source_tier = "live_recent"
            source_path = evaluator.LIVE_MARKETS_PATH
        else:
            historical_response = client.get_json(
                evaluator.HISTORICAL_MARKETS_PATH,
                params=evaluator.market_filter_params(ticker),
                top_level_container="object",
            )
            requests_made += 1
            evaluator.exact_filtered_market(
                expected_ticker=ticker,
                payload=historical_response.payload,
                allow_zero=False,
            )
            response = historical_response
            source_tier = "historical"
            source_path = evaluator.HISTORICAL_MARKETS_PATH

        raw_ref = {
            "source": response.raw_record.source,
            "session_id": response.raw_record.session_id,
            "request_id": response.raw_record.request_id,
        }
        record = evaluator.normalize_market_list_response(
            expected_ticker=ticker,
            payload=response.payload,
            source_tier=source_tier,
            source_path=source_path,
            raw_reference=raw_ref,
            request_started_at_utc=response.request_started_at_utc,
            received_at_utc=response.received_at_utc,
        )
        source_tier_counts[source_tier] += 1
        cache_path = evaluator.settlement_cache_path(repo, ticker)
        evaluator.atomic_write_json(cache_path, record)
        cached[ticker] = record

    evaluator.require(set(cached) == set(required), "required settlement cache incomplete")

    raw_files = []
    if client is not None:
        for path in sorted(set(client.raw_recorder.written_paths) - raw_files_before):
            raw_files.append(
                {
                    "relative_path": relative(path, repo),
                    "sha256": evaluator.sha256_file(path),
                }
            )

    manifest = evaluator.build_settlement_manifest(
        required_tickers=required,
        censored_fallback_tickers=fallback["censored_fallback"],
        cached_records=cached,
        raw_files=raw_files,
    )
    manifest_path = repo / evaluator.SETTLEMENT_MANIFEST_PATH
    manifest_sha = evaluator.atomic_write_json(manifest_path, manifest)

    report = evaluator.build_pnl_report(
        contract=contract,
        paths=paths,
        settlement_records=cached,
        settlement_manifest_sha256=manifest_sha,
    )
    report_path = repo / evaluator.PNL_REPORT_PATH
    report_sha = evaluator.atomic_write_json(report_path, report)

    print("CANDIDATE-E JULY10 OUTCOME EVALUATION: PASS")
    print("Settlement transport: live /markets exact filter, historical fallback if absent")
    print("Settlement source tiers:", source_tier_counts)
    print("Exact settlement tickers required:", len(required))
    print("Network requests this run:", requests_made)
    print("Exact scenarios scored:", report["exact_scenario_count"])
    print("Censored scenarios interval-valued:", report["censored_scenario_count"])
    print("Robustness classes:", report["robustness_classification_counts"])
    print("Settlement manifest:", evaluator.SETTLEMENT_MANIFEST_PATH)
    print("Settlement manifest SHA256:", manifest_sha)
    print("P&L report:", evaluator.PNL_REPORT_PATH)
    print("P&L report SHA256:", report_sha)
    print("Policy selection/ranking: NOT PERFORMED")
    print("Strategy: NOT RERUN | Orders: 0")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Open only exact-path fallback settlements and build the frozen P&L report.",
    )
    args = parser.parse_args()
    repo = Path.cwd().resolve()
    if not args.collect:
        preflight(repo)
        return 0
    return collect_and_score(repo)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("CANDIDATE-E JULY10 SETTLEMENT EVALUATION: FAIL CLOSED")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)
