"""Checkpoint 21N-Y-B amended outcome-blind July 10 V2 path runner.

This runner preserves the frozen 21N-Y-A implementation and adds only the
21N-Y-A1 execution-quantity transport adapter before decision/execution use.
Settlement outcomes remain inaccessible.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.kxbtcd_candidate_e_continuous_btc_materialization import load_materialization
from src.kxbtcd_candidate_e_continuous_july10_source_binding import (
    EXPECTED_BINDING_FINGERPRINT,
    validate_binding,
)
from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    LATENCY_MS,
    THRESHOLDS,
)
from src.kxbtcd_candidate_e_july10_outcome_blind_binding import (
    EXPECTED_PAID_TICKS_SHA256,
    EXPECTED_REPLAY_SUMMARY_SHA256,
    PAID_TICKS_RELATIVE_PATH,
    collect_paid_tickers,
    derive_structural_universe,
    sha256_file,
    validate_file_set_alignment,
)
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
    validate_freeze as validate_y_a_freeze,
)
from materialize_kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_paths import (
    build_dynamic_timelines,
    load_paid_rows_for_tickers,
)
from src.kxbtcd_candidate_e_v2_execution_quantity_transport_amendment import (
    canonicalize_timeline_map,
)
from src.kxbtcd_candidate_e_v2_execution_quantity_transport_amendment_freeze import (
    EXPECTED_AMENDMENT_FINGERPRINT,
    validate_amendment,
)

DEFAULT_OUTPUT_RELATIVE_PATH = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_spot_relative_liquidity_convergence_reentry_v2_"
    "outcome_blind_paths.json"
)


class V2AmendedPathMaterializationError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise V2AmendedPathMaterializationError(message)


def materialize(repo_root: str | Path = "."):
    repo = Path(repo_root)

    parents = validate_parents(repo)
    y_a = validate_y_a_freeze(repo)
    amendment = validate_amendment(repo)

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
    if binding.get("full_ladder_replay_summary_sha256") != EXPECTED_REPLAY_SUMMARY_SHA256:
        _fail("full-ladder replay binding mismatch")

    paid_tickers = collect_paid_tickers(paid_path)
    validate_file_set_alignment(repo_root=repo, paid_tickers=paid_tickers)

    structural = derive_structural_universe(paid_tickers)
    ladders = build_event_ladders(paid_tickers, structural)

    dynamic_tickers = required_dynamic_tickers(
        event_ladders=ladders,
        btc_rows=btc_rows,
    )
    paid_rows = load_paid_rows_for_tickers(paid_path, dynamic_tickers)

    # Frozen Y-A replay reconstruction is unchanged.
    raw_timelines = build_dynamic_timelines(
        repo_root=repo,
        selected_tickers=dynamic_tickers,
        paid_rows_by_ticker=paid_rows,
    )

    # Y-A1 amendment boundary: only quantity representation entering V2
    # decision/execution is canonicalized.
    timelines = canonicalize_timeline_map(raw_timelines)

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
        "implementation_fingerprint": y_a["implementation_fingerprint"],
        "execution_quantity_transport_amendment_fingerprint": (
            amendment["amendment_fingerprint"]
        ),
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
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
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
    print("Checkpoint 21N-Y-B amended V2 outcome-blind July 10 path materialization: PASS")
    print(f"Output: {output}")
    print(f"SHA256: {digest}")
    print(
        "Quantity-transport amendment:",
        payload["execution_quantity_transport_amendment_fingerprint"],
    )
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
