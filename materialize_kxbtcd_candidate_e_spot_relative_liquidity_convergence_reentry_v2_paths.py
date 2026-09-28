"""21N-Y-B outcome-blind July 10 V2 path runner.

This file is included in the 21N-Y-A implementation freeze but MUST NOT be run
until that freeze is committed and closed.  It scores Candidate E on the newly
predeclared nonstructural ATM±5 domain, but it never opens settlement outcomes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from src.kxbtcd_candidate_e_continuous_btc_materialization import (
    load_materialization,
)
from src.kxbtcd_candidate_e_continuous_july10_source_binding import (
    EXPECTED_BINDING_FINGERPRINT,
    validate_binding,
)
from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    LATENCY_MS,
    THRESHOLDS,
    VerifiedTickerTimeline,
    build_verified_ticker_timeline,
)
from src.kxbtcd_candidate_e_july10_outcome_blind_binding import (
    BACKFILL_ROOT_RELATIVE_PATH,
    EXPECTED_PAID_TICKS_SHA256,
    EXPECTED_REPLAY_SUMMARY_SHA256,
    PAID_COLUMNS,
    PAID_TICKS_RELATIVE_PATH,
    REPLAY_TICKER_ROOT_RELATIVE_PATH,
    _validate_replay_ticker_artifact,
    collect_paid_tickers,
    derive_structural_universe,
    sha256_file,
    validate_file_set_alignment,
)
from src.predexon_full_ladder_replay import load_backfill_snapshots
from src.kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import (
    STRATEGY_ID,
    assert_outcome_blind_payload,
    build_event_ladders,
    jsonable,
    required_dynamic_tickers,
    simulate_policy,
    validate_parents,
)
from src.kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator_freeze import (
    validate_freeze,
)

DEFAULT_OUTPUT_RELATIVE_PATH = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_spot_relative_liquidity_convergence_reentry_v2_"
    "outcome_blind_paths.json"
)


class V2PathMaterializationError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise V2PathMaterializationError(message)


def load_paid_rows_for_tickers(
    parquet_path: Path,
    selected_tickers: Sequence[str],
) -> dict[str, list[Mapping[str, Any]]]:
    selected = tuple(sorted(set(str(x) for x in selected_tickers)))
    if not selected:
        _fail("dynamic ticker subset is empty")

    output: dict[str, list[Mapping[str, Any]]] = {
        ticker: [] for ticker in selected
    }
    values = pa.array(selected, type=pa.string())
    parquet = pq.ParquetFile(parquet_path)

    for batch in parquet.iter_batches(
        batch_size=131072,
        columns=list(PAID_COLUMNS),
    ):
        ticker_column = batch.column(batch.schema.get_field_index("ticker"))
        mask = pc.is_in(ticker_column, value_set=values)
        if not pc.any(mask).as_py():
            continue
        filtered = batch.filter(mask)
        for row in filtered.to_pylist():
            ticker = str(row["ticker"])
            if ticker in output:
                output[ticker].append(row)

    for ticker, rows in output.items():
        if not rows:
            _fail(f"zero paid deltas for dynamic ticker {ticker}")
        rows.sort(
            key=lambda row: (
                int(row["timestamp"]),
                int(row["sequence"]),
            )
        )

    return output


def build_dynamic_timelines(
    *,
    repo_root: str | Path,
    selected_tickers: Sequence[str],
    paid_rows_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, VerifiedTickerTimeline]:
    repo = Path(repo_root)
    output: dict[str, VerifiedTickerTimeline] = {}

    for ticker in sorted(set(str(x) for x in selected_tickers)):
        backfill_path = (
            repo
            / BACKFILL_ROOT_RELATIVE_PATH
            / f"{ticker}_raw_pages.jsonl"
        )
        snapshots = load_backfill_snapshots(
            backfill_path,
            ticker=ticker,
        )
        timeline = build_verified_ticker_timeline(
            ticker=ticker,
            snapshots=snapshots,
            paid_rows=paid_rows_by_ticker[ticker],
        )

        replay_path = (
            repo
            / REPLAY_TICKER_ROOT_RELATIVE_PATH
            / f"{ticker}.json"
        )
        _validate_replay_ticker_artifact(
            path=replay_path,
            ticker=ticker,
            timeline=timeline,
        )
        output[ticker] = timeline

    if set(output) != set(selected_tickers):
        _fail("dynamic timeline set mismatch")
    return output


def materialize(repo_root: str | Path = "."):
    repo = Path(repo_root)

    parents = validate_parents(repo)
    freeze = validate_freeze(repo)

    binding = validate_binding(repo)
    if binding.get("source_binding_fingerprint") != EXPECTED_BINDING_FINGERPRINT:
        _fail("21N-U-B source binding fingerprint mismatch")

    btc_block = binding["continuous_btc_materialization"]
    btc_path = repo / btc_block["relative_path"]
    if sha256_file(btc_path) != btc_block["sha256"]:
        _fail("bound continuous Coinbase artifact changed")
    btc_rows = load_materialization(btc_path)

    paid_path = repo / PAID_TICKS_RELATIVE_PATH
    if sha256_file(paid_path) != EXPECTED_PAID_TICKS_SHA256:
        _fail("paid Predexon shard hash mismatch")
    if (
        binding.get("full_ladder_replay_summary_sha256")
        != EXPECTED_REPLAY_SUMMARY_SHA256
    ):
        _fail("full-ladder replay binding mismatch")

    paid_tickers = collect_paid_tickers(paid_path)
    validate_file_set_alignment(
        repo_root=repo,
        paid_tickers=paid_tickers,
    )
    structural = derive_structural_universe(paid_tickers)
    ladders = build_event_ladders(paid_tickers, structural)

    dynamic_tickers = required_dynamic_tickers(
        event_ladders=ladders,
        btc_rows=btc_rows,
    )
    paid_rows = load_paid_rows_for_tickers(
        paid_path,
        dynamic_tickers,
    )
    timelines = build_dynamic_timelines(
        repo_root=repo,
        selected_tickers=dynamic_tickers,
        paid_rows_by_ticker=paid_rows,
    )

    results = []
    for event in sorted(ladders):
        for threshold in THRESHOLDS:
            for latency_ms in LATENCY_MS:
                results.append(
                    {
                        "event_ticker": event,
                        "threshold_dollars": threshold,
                        "latency_ms": latency_ms,
                        "policy_result": simulate_policy(
                            event_ticker=event,
                            event_ladder=ladders[event],
                            timelines=timelines,
                            btc_rows=btc_rows,
                            threshold=threshold,
                            latency_ms=latency_ms,
                        ),
                    }
                )

    payload = {
        "schema_version": (
            "kxbtcd_candidate_e_spot_relative_liquidity_"
            "convergence_reentry_v2_outcome_blind_paths.v1"
        ),
        "checkpoint_id": "21N-Y-B",
        "strategy_id": STRATEGY_ID,
        "evidence_role": "four_event_july10_development_and_mechanics_only",
        "advancement_gate": "NONE_N_EQ_4",
        "frozen_parents": parents,
        "implementation_fingerprint": freeze["implementation_fingerprint"],
        "source_binding_fingerprint": binding["source_binding_fingerprint"],
        "dynamic_ticker_union_count": len(dynamic_tickers),
        "dynamic_ticker_union": list(dynamic_tickers),
        "policy_results": jsonable(results),
        "safety": {
            "candidate_e_refit": False,
            "candidate_e_nonstructural_scoring_performed": True,
            "outcomes_accessed": False,
            "strategy_pnl_calculated": False,
            "network_requests": 0,
            "predexon_paid_purchases": 0,
            "orders_placed": 0,
            "paper_broker": False,
            "demo_execution": False,
            "real_money_execution": False,
            "protected_reserve_accessed": False,
        },
    }

    assert_outcome_blind_payload(payload)

    raw = (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")

    output_path = repo / DEFAULT_OUTPUT_RELATIVE_PATH
    if output_path.exists() and output_path.read_bytes() != raw:
        _fail(f"refusing non-identical overwrite: {output_path}")
    if not output_path.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(raw)

    digest = hashlib.sha256(raw).hexdigest()
    return payload, output_path, digest


def main() -> int:
    payload, output, digest = materialize(".")
    print("Checkpoint 21N-Y-B V2 outcome-blind July 10 path materialization: PASS")
    print(f"Output: {output}")
    print(f"SHA256: {digest}")
    print("Dynamic ticker union:", payload["dynamic_ticker_union_count"])
    print("Policy scenarios:", len(payload["policy_results"]))
    print("Candidate E nonstructural scoring: YES — DEVELOPMENT ONLY")
    print("Settlement outcomes: NOT ACCESSED")
    print("Settlement-dependent P&L: NOT RUN")
    print("Network requests: 0")
    print("Predexon purchases: 0")
    print("Orders: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
