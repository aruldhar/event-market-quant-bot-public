#!/usr/bin/env python3
"""Raw-first collector/evaluator for the frozen E1 July-10 sensitivity universe.

Default mode is zero-network readiness inspection.
Real settlement access requires --collect and is blocked until the E2
implementation checkpoint is safely closed and pushed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from src.public_census_http import PublicCensusHttpClient
from src import kxbtcd_candidate_e_v2_july10_settlement_evaluator as base
from src import kxbtcd_candidate_e_v2_july10_settlement_sensitivity_evaluator as s


def relative(path: Path, repo: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def preflight(repo: Path) -> int:
    predecl, observed, _ = s.load_frozen_e1(repo)
    tickers = tuple(predecl["future_settlement_access"]["exact_ticker_universe"])
    cached, origins = s.load_cached_settlements(repo, tickers)
    print("CANDIDATE-E JULY10 SETTLEMENT SENSITIVITY READINESS: PASS")
    print("Role: POST-OUTCOME EXPLORATORY SENSITIVITY ONLY")
    print("Official frozen result: 27 EXACT / 33 CENSORED / 15 INCONCLUSIVE — UNCHANGED")
    print("Observed filled trades:", observed["observed_filled_trade_count"])
    print("Frozen settlement tickers:", len(tickers))
    print("Already cached/reusable settlement records:", len(cached))
    print("Missing settlement records:", len(tickers) - len(cached))
    print("Cached origins:", dict(sorted(__import__("collections").Counter(origins.values()).items())))
    for ticker in tickers:
        print(" ", ticker)
    print("Settlement transport: live /markets exact filter, historical fallback if absent")
    print("Real --collect: BLOCKED UNTIL E2 IS CLOSED/PUSHED")
    print("No additional settlement requested in preflight | Network: 0 | Orders: 0")
    return 0


def collect_and_score(repo: Path) -> int:
    s.require_collection_closeout_gate(repo)
    predecl, observed, contract = s.load_frozen_e1(repo)
    tickers = tuple(predecl["future_settlement_access"]["exact_ticker_universe"])

    cached, origins = s.load_cached_settlements(repo, tickers)
    missing = [ticker for ticker in tickers if ticker not in cached]

    raw_root = repo / "data/raw" / base.SOURCE_NAME
    client = None
    raw_files_before: set[Path] = set()
    if missing:
        client = PublicCensusHttpClient(
            base_url=base.KALSHI_BASE_URL,
            source_name=base.SOURCE_NAME,
            raw_root=raw_root,
            timeout_seconds=15.0,
            max_rate_limit_retries=3,
            rate_limit_backoff_seconds=0.5,
        )
        raw_files_before = set(client.raw_recorder.written_paths)

    requests_made = 0
    fetched_tiers = {"live_recent": 0, "historical": 0}

    for ticker in missing:
        assert client is not None
        live_response = client.get_json(
            base.LIVE_MARKETS_PATH,
            params=base.market_filter_params(ticker),
            top_level_container="object",
        )
        requests_made += 1
        live_market = base.exact_filtered_market(
            expected_ticker=ticker,
            payload=live_response.payload,
            allow_zero=True,
        )

        if live_market is not None:
            response = live_response
            source_tier = "live_recent"
            source_path = base.LIVE_MARKETS_PATH
        else:
            historical_response = client.get_json(
                base.HISTORICAL_MARKETS_PATH,
                params=base.market_filter_params(ticker),
                top_level_container="object",
            )
            requests_made += 1
            base.exact_filtered_market(
                expected_ticker=ticker,
                payload=historical_response.payload,
                allow_zero=False,
            )
            response = historical_response
            source_tier = "historical"
            source_path = base.HISTORICAL_MARKETS_PATH

        raw_ref = {
            "source": response.raw_record.source,
            "session_id": response.raw_record.session_id,
            "request_id": response.raw_record.request_id,
        }
        record = base.normalize_market_list_response(
            expected_ticker=ticker,
            payload=response.payload,
            source_tier=source_tier,
            source_path=source_path,
            raw_reference=raw_ref,
            request_started_at_utc=response.request_started_at_utc,
            received_at_utc=response.received_at_utc,
        )
        cache_path = s.sensitivity_cache_path(repo, ticker)
        base.atomic_write_json(cache_path, record)
        cached[ticker] = record
        origins[ticker] = "sensitivity_cache"
        fetched_tiers[source_tier] += 1

    s.require(set(cached) == set(tickers), "frozen sensitivity settlement universe incomplete")

    raw_files = []
    if client is not None:
        for path in sorted(set(client.raw_recorder.written_paths) - raw_files_before):
            raw_files.append(
                {
                    "relative_path": relative(path, repo),
                    "sha256": base.sha256_file(path),
                }
            )

    manifest = s.build_settlement_manifest(
        predecl=predecl,
        records=cached,
        origins=origins,
        raw_files_current_run=raw_files,
        network_requests_current_run=requests_made,
    )
    manifest_path = repo / s.SENSITIVITY_SETTLEMENT_MANIFEST_PATH
    manifest_sha = base.atomic_write_json(manifest_path, manifest)

    report = s.build_sensitivity_report(
        repo=repo,
        predecl=predecl,
        observed=observed,
        contract=contract,
        settlement_records=cached,
        settlement_manifest_sha256=manifest_sha,
    )
    report_path = repo / s.SENSITIVITY_REPORT_PATH
    report_sha = base.atomic_write_json(report_path, report)

    entry = report["independent_entry_diagnostic_summary"]
    trace = report["observed_trace_analysis"]
    hybrid = report["hybrid_analysis"]

    print("CANDIDATE-E JULY10 SETTLEMENT SENSITIVITY: PASS")
    print("Role: POST-OUTCOME EXPLORATORY SENSITIVITY ONLY")
    print("Official frozen result: 27 EXACT / 33 CENSORED / 15 INCONCLUSIVE — UNCHANGED")
    print("Frozen settlement tickers:", len(tickers))
    print("Network requests this run:", requests_made)
    print("Fetched source tiers:", fetched_tiers)
    print("All settlement source tiers:", manifest["source_tier_counts"])
    print("Cache origins:", manifest["cache_origin_counts"])
    print("Hybrid exact official P&Ls preserved:", hybrid["exact_official_pnl_preserved_count"])
    print("Hybrid liquidation-only settlement-terminalized:", hybrid["liquidation_only_terminalized_count"])
    print("Hybrid selection/rearm scenarios still incomplete:", hybrid["selection_or_rearm_incomplete_count"])
    print("Hybrid interval zero relations:", hybrid["policy_interval_zero_relation_counts"])
    print("Censored observed-trace signs:", trace["trace_value_sign_counts"])
    print(
        "Independent entry diagnostics:",
        {
            "entries": entry["entry_count"],
            "settled_in_the_money": entry["settled_in_the_money_count"],
            "settled_out_of_the_money": entry["settled_out_of_the_money_count"],
            "hold_pnl_signs": entry["hold_pnl_sign_counts"],
        },
    )
    print("Settlement manifest:", s.SENSITIVITY_SETTLEMENT_MANIFEST_PATH)
    print("Settlement manifest SHA256:", manifest_sha)
    print("Sensitivity report:", s.SENSITIVITY_REPORT_PATH)
    print("Sensitivity report SHA256:", report_sha)
    print("Policy selection/ranking: NOT PERFORMED")
    print("Strategy: NOT RERUN | Orders: 0")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Collect only the frozen E1 settlement ticker universe and run E1 sensitivity analyses.",
    )
    args = parser.parse_args()
    repo = Path.cwd().resolve()
    return collect_and_score(repo) if args.collect else preflight(repo)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("CANDIDATE-E JULY10 SETTLEMENT SENSITIVITY: FAIL CLOSED")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)
