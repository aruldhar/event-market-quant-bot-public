"""Outcome-blind 60-scenario runner over the frozen 203-repair cache.

This is additive to Y-A3. It never rebuilds repair caches, never opens settlement
outcomes, and never calculates strategy P&L. The only scoring performed here is
the already-frozen Candidate-E policy/path mechanics over the repaired, sealed
DiskTimeline evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

import materialize_kxbtcd_candidate_e_v2_paths_replay_precision as y_a3
import materialize_kxbtcd_candidate_e_v2_repair_cache_203 as repair_cache
from src.kxbtcd_candidate_e_july10_outcome_blind_binding import (
    BACKFILL_ROOT_RELATIVE_PATH,
    REPLAY_TICKER_ROOT_RELATIVE_PATH,
)
from src.kxbtcd_candidate_e_v2_disk_timeline import DiskTimeline, file_sha256
from src.kxbtcd_candidate_e_v2_disk_policy import simulate_policy
from src.kxbtcd_candidate_e_v2_repair_materialization import (
    EXPECTED_PLAN_SHA256,
    validate_repair_cache,
)
from src.kxbtcd_candidate_e_v2_replay_precision_freeze import (
    validate_precision_amendment,
)

REPAIR_CACHE_ROOT = Path("data/analysis/predexon_credit_efficiency/v2_repair_203_cache")
REPAIR_COVERAGE = REPAIR_CACHE_ROOT / "coverage_full.json"
EXPECTED_REPAIR_COVERAGE_SHA256 = "b8b535d6131f01250690d1015861a4737fd0cd4888251f1cbf4941eb7dceeab0"
EXPECTED_PARENT_REPLAY_PRECISION_COVERAGE_SHA256 = (
    "5b78812350bbcd3cea77f9c109dac2cce636de9577426edbaf523179859da1ab"
)
SUPERSEDED_Y_A3_PATH = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_v2_outcome_blind_paths_replay_precision.json"
)
EXPECTED_SUPERSEDED_Y_A3_PATH_SHA256 = (
    "3b1bfadd61f003343d385fc1f62b6192ce5b53fda87d3f1977d84f604ebb4780"
)
OUTPUT = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_v2_outcome_blind_paths_repair_203.json"
)
RUN_LOCK_ROOT = Path(
    "data/analysis/predexon_credit_efficiency/v2_repair_203_path_materialization"
)
CHECKPOINT_ID = "21N-Y-B-R203"

RUNNER_FILES = (
    "materialize_kxbtcd_candidate_e_v2_paths_repair_203.py",
    "validate_kxbtcd_candidate_e_v2_repair_203_path_readiness.py",
    "tests/test_kxbtcd_candidate_e_v2_paths_repair_203.py",
)


class RepairPathError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RepairPathError(message)


def require_committed_runner(repo: Path) -> None:
    for relative in RUNNER_FILES:
        local = repo / relative
        require(local.is_file(), f"runner file missing: {relative}")
        result = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        require(
            result.returncode == 0,
            f"close/push repair-path checkpoint before --simulate: {relative}",
        )
        require(
            result.stdout.replace(b"\r\n", b"\n")
            == local.read_bytes().replace(b"\r\n", b"\n"),
            f"committed/local runner mismatch: {relative}",
        )


def validate_coverage_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    require(
        payload.get("schema_version") == "candidate_e_v2_repair_203_coverage.v1",
        "repair coverage schema mismatch",
    )
    require(payload.get("checkpoint_id") == "21N-Y-A5", "repair coverage checkpoint mismatch")
    require(payload.get("prepared_ticker_count") == 47, "repair coverage prepared ticker count mismatch")
    require(payload.get("full_ticker_count") == 47, "repair coverage full ticker count mismatch")
    require(payload.get("repair_operation_count") == 110, "repair operation count mismatch")
    require(payload.get("original_failed_pairs_addressed") == 203, "addressed pair count mismatch")
    require(payload.get("remaining_unreconciled_pair_count") == 545, "residual boundary count mismatch")
    require(payload.get("repair_plan_sha256") == EXPECTED_PLAN_SHA256, "repair plan binding mismatch")
    require(
        payload.get("parent_replay_precision_coverage_sha256")
        == EXPECTED_PARENT_REPLAY_PRECISION_COVERAGE_SHA256,
        "parent replay-precision coverage binding mismatch",
    )

    safety = payload.get("safety", {})
    for key in ("candidate_e_scored", "strategy_run", "outcomes_accessed", "strategy_pnl_calculated"):
        require(safety.get(key) is False, f"repair coverage safety mismatch: {key}")
    for key in ("network_requests", "orders_placed"):
        require(type(safety.get(key)) is int and safety[key] == 0, f"repair coverage safety mismatch: {key}")

    audits = list(payload.get("ticker_audits", []))
    require(len(audits) == 47, "repair coverage must contain 47 ticker audits")
    by_ticker: dict[str, dict[str, Any]] = {}
    ops = addressed = residual = quarantined = changed = original_failed = 0
    for audit in audits:
        ticker = str(audit["ticker"])
        require(ticker not in by_ticker, f"duplicate ticker audit: {ticker}")
        by_ticker[ticker] = dict(audit)
        local_addressed = len(audit["original_failed_pairs_addressed"])
        local_residual = int(audit["remaining_unreconciled_pair_count"])
        local_original = int(audit["original_failed_pair_count"])
        require(
            local_original == local_addressed + local_residual,
            f"{ticker}: original failure accounting mismatch",
        )
        require(audit["repair_plan_sha256"] == EXPECTED_PLAN_SHA256, f"{ticker}: repair plan mismatch")
        require(
            all(edge.get("exact") is True for edge in audit["pinned_changed_adjacencies"]),
            f"{ticker}: non-exact pinned changed adjacency",
        )
        audit_safety = audit["safety"]
        for key in (
            "candidate_e_scored",
            "raw_snapshots_mutated",
            "paid_rows_mutated",
            "strategy_run",
            "outcomes_accessed",
            "strategy_pnl_calculated",
        ):
            require(audit_safety.get(key) is False, f"{ticker}: audit safety mismatch: {key}")
        for key in ("network_requests", "orders_placed"):
            require(
                type(audit_safety.get(key)) is int and audit_safety[key] == 0,
                f"{ticker}: audit safety mismatch: {key}",
            )
        original_failed += local_original
        ops += int(audit["repair_operation_count"])
        addressed += local_addressed
        residual += local_residual
        quarantined += len(audit["quarantined_snapshot_indices"])
        changed += int(audit["repaired_adjacency_count"])

    require(original_failed == 748, f"original failed-pair total {original_failed} != 748")
    require(ops == 110, f"ticker audit operation sum {ops} != 110")
    require(addressed == 203, f"ticker audit addressed sum {addressed} != 203")
    require(residual == 545, f"ticker audit residual sum {residual} != 545")
    require(quarantined == 93, f"quarantined snapshot sum {quarantined} != 93")
    require(changed == 364, f"repaired adjacency sum {changed} != 364")
    return by_ticker


def load_repair_coverage(repo: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    path = repo / REPAIR_COVERAGE
    require(path.is_file(), f"repair coverage missing: {path}")
    observed = file_sha256(path)
    require(
        observed == EXPECTED_REPAIR_COVERAGE_SHA256,
        f"repair coverage SHA mismatch: expected {EXPECTED_REPAIR_COVERAGE_SHA256}, got {observed}",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload, validate_coverage_payload(payload)


def expected_cache_identity(repo: Path, ticker: str) -> dict[str, Any]:
    snapshot_path = repo / BACKFILL_ROOT_RELATIVE_PATH / f"{ticker}_raw_pages.jsonl"
    replay_path = repo / REPLAY_TICKER_ROOT_RELATIVE_PATH / f"{ticker}.json"
    builder_path = repo / "src/kxbtcd_candidate_e_v2_repair_materialization.py"
    require(snapshot_path.is_file(), f"snapshot source missing: {ticker}")
    require(replay_path.is_file(), f"replay source missing: {ticker}")
    return {
        "ticker": ticker,
        "paid_sha256": repair_cache.EXPECTED_PAID_TICKS_SHA256,
        "snapshot_sha256": file_sha256(snapshot_path),
        "replay_sha256": file_sha256(replay_path),
        "parent_replay_precision_coverage_sha256": EXPECTED_PARENT_REPLAY_PRECISION_COVERAGE_SHA256,
        "repair_plan_sha256": EXPECTED_PLAN_SHA256,
        "repair_builder_sha256": file_sha256(builder_path),
        "memory_amendment_fingerprint": "f7a590cb0f8415e3330fa82077d16b6b93105717f573e69e8580a3f3ac1ffe03",
        "replay_precision_amendment_fingerprint": "82c4d05994cf97c723672b82428a7a139e20f96ae5aeea622e6dfaf1429a1370",
        "quantity_amendment_fingerprint": "2cbd8836045ae811eb4c52d48834953a54b1be3afac094be4cf349b8cac2abce",
    }


def validate_one_cache(
    repo: Path,
    ticker: str,
    coverage_audit: Mapping[str, Any],
) -> Path:
    path = repo / REPAIR_CACHE_ROOT / f"{ticker}.sqlite"
    identity = expected_cache_identity(repo, ticker)
    timeline = repair_cache.open_sealed_repair_cache(path, identity)
    try:
        audit = validate_repair_cache(timeline)
        require(audit == coverage_audit, f"{ticker}: sealed cache audit differs from coverage_full.json")
    finally:
        timeline.close()
    return path


def scenario_specs(ladders: Mapping[str, Any]) -> list[tuple[str, Any, int]]:
    specs = [
        (event, threshold, latency_ms)
        for event in sorted(ladders)
        for threshold in y_a3.parent.THRESHOLDS
        for latency_ms in y_a3.parent.LATENCY_MS
    ]
    require(len(specs) == 60, f"expected 60 frozen scenario specs, got {len(specs)}")
    return specs


def scenario_key(event: str, threshold: Any, latency_ms: int) -> tuple[str, str, int]:
    """Compare scenario identity in the same JSON representation as frozen artifacts."""
    return (
        str(event),
        str(y_a3.parent.jsonable(threshold)),
        int(latency_ms),
    )


def scenario_keys_from_specs(
    specs: Sequence[tuple[str, Any, int]],
) -> list[tuple[str, str, int]]:
    return [scenario_key(event, threshold, latency_ms) for event, threshold, latency_ms in specs]


def scenario_keys_from_payload(payload: Mapping[str, Any]) -> list[tuple[str, str, int]]:
    return [
        scenario_key(row["event_ticker"], row["threshold_dollars"], int(row["latency_ms"]))
        for row in payload["policy_results"]
    ]


def validate_readiness(
    repo_root: str | Path = ".",
    *,
    verify_cache_hashes: bool = True,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    coverage, audits = load_repair_coverage(repo)

    precision = validate_precision_amendment(repo)
    parents = y_a3.parent.validate_parents(repo)
    y_a = y_a3.parent.validate_y_a_freeze(repo)
    quantity = y_a3.parent.validate_amendment(repo)
    binding = y_a3.parent.validate_binding(repo)

    superseded = repo / SUPERSEDED_Y_A3_PATH
    require(superseded.is_file(), "superseded Y-A3 outcome-blind path artifact missing")
    require(
        file_sha256(superseded) == EXPECTED_SUPERSEDED_Y_A3_PATH_SHA256,
        "superseded Y-A3 path SHA mismatch",
    )
    old_payload = json.loads(superseded.read_text(encoding="utf-8"))
    y_a3.parent.assert_outcome_blind_payload(old_payload)
    require(old_payload["safety"]["outcomes_accessed"] is False, "old path unexpectedly accessed outcomes")
    require(old_payload["safety"]["strategy_pnl_calculated"] is False, "old path unexpectedly contains P&L")

    btc_block = binding["continuous_btc_materialization"]
    btc_path = repo / btc_block["relative_path"]
    require(file_sha256(btc_path) == btc_block["sha256"], "bound continuous Coinbase artifact changed")
    btc_rows = y_a3.parent.load_materialization(btc_path)

    paid_path = repo / y_a3.parent.PAID_TICKS_RELATIVE_PATH
    require(
        file_sha256(paid_path) == y_a3.parent.EXPECTED_PAID_TICKS_SHA256,
        "paid Predexon shard hash mismatch",
    )
    paid_tickers = y_a3.parent.collect_paid_tickers(paid_path)
    y_a3.parent.validate_file_set_alignment(repo_root=repo, paid_tickers=paid_tickers)
    structural = y_a3.parent.derive_structural_universe(paid_tickers)
    ladders = y_a3.parent.build_event_ladders(paid_tickers, structural)
    dynamic_tickers = tuple(y_a3.parent.required_dynamic_tickers(event_ladders=ladders, btc_rows=btc_rows))

    require(len(dynamic_tickers) == 47, f"dynamic ticker union changed: {len(dynamic_tickers)}")
    require(set(dynamic_tickers) == set(audits), "repair coverage ticker set != frozen dynamic union")
    require(tuple(old_payload["dynamic_ticker_union"]) == dynamic_tickers, "dynamic ticker order changed from Y-A3")

    specs = scenario_specs(ladders)
    require(
        scenario_keys_from_payload(old_payload) == scenario_keys_from_specs(specs),
        "frozen 60-scenario grid differs from superseded Y-A3 artifact",
    )

    cache_paths: dict[str, Path] = {}
    if verify_cache_hashes:
        for ticker in dynamic_tickers:
            cache_paths[ticker] = validate_one_cache(repo, ticker, audits[ticker])

    return {
        "repo": repo,
        "coverage": coverage,
        "coverage_audits": audits,
        "precision": precision,
        "parents": parents,
        "y_a": y_a,
        "quantity": quantity,
        "binding": binding,
        "btc_rows": btc_rows,
        "ladders": ladders,
        "dynamic_tickers": dynamic_tickers,
        "scenario_specs": specs,
        "cache_paths": cache_paths,
    }


def materialize(repo_root: str | Path = ".", *, simulate: bool = False):
    repo = Path(repo_root).resolve()
    with y_a3.Progress() as progress:
        progress.report("validating frozen repair-cache coverage and 60-scenario lineage")
        ready = validate_readiness(repo, verify_cache_hashes=True)
        progress.report("47/47 sealed repair caches validated")

        if not simulate:
            progress.report("REPAIR-203 PATH READINESS PASS: strategy NOT STARTED")
            print("Repair coverage SHA256:", EXPECTED_REPAIR_COVERAGE_SHA256)
            print("Policy scenarios frozen:", len(ready["scenario_specs"]))
            print("Strategy: NOT RUN | Outcomes: NOT ACCESSED | P&L: NOT CALCULATED | Orders: 0")
            return None

        require_committed_runner(repo)
        paid_path = repo / y_a3.parent.PAID_TICKS_RELATIVE_PATH
        cache_paths = ready["cache_paths"]
        results = []

        with y_a3.run_lock(repo / RUN_LOCK_ROOT):
            for event in sorted(ready["ladders"]):
                timelines: dict[str, DiskTimeline] = {}
                try:
                    for ticker in ready["dynamic_tickers"]:
                        if ticker.rsplit("-T", 1)[0] == event:
                            timelines[ticker] = DiskTimeline(cache_paths[ticker])
                    for threshold in y_a3.parent.THRESHOLDS:
                        for latency_ms in y_a3.parent.LATENCY_MS:
                            progress.report(
                                f"scenario {len(results)+1}/60: "
                                f"{event}, margin={threshold}, latency={latency_ms}ms"
                            )
                            results.append(
                                {
                                    "event_ticker": event,
                                    "threshold_dollars": threshold,
                                    "latency_ms": latency_ms,
                                    "policy_result": simulate_policy(
                                        event_ticker=event,
                                        event_ladder=ready["ladders"][event],
                                        timelines=timelines,
                                        btc_rows=ready["btc_rows"],
                                        threshold=threshold,
                                        latency_ms=latency_ms,
                                    ),
                                }
                            )
                finally:
                    for timeline in timelines.values():
                        timeline.close()

            require(len(results) == 60, "expected exactly 60 policy results")
            require(
                scenario_keys_from_specs(
                    [(r["event_ticker"], r["threshold_dollars"], int(r["latency_ms"])) for r in results]
                )
                == scenario_keys_from_specs(ready["scenario_specs"]),
                "materialized scenario order differs from frozen scenario grid",
            )
            require(
                file_sha256(repo / REPAIR_COVERAGE) == EXPECTED_REPAIR_COVERAGE_SHA256,
                "repair coverage changed during scoring",
            )
            require(
                file_sha256(paid_path) == y_a3.parent.EXPECTED_PAID_TICKS_SHA256,
                "paid shard changed during scoring",
            )

            payload = {
                "schema_version": (
                    "kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_"
                    "outcome_blind_paths.v1"
                ),
                "checkpoint_id": CHECKPOINT_ID,
                "strategy_id": y_a3.parent.STRATEGY_ID,
                "evidence_role": "four_event_july10_development_and_mechanics_only",
                "advancement_gate": "NONE_N_EQ_4",
                "frozen_parents": ready["parents"],
                "implementation_fingerprint": ready["y_a"]["implementation_fingerprint"],
                "execution_quantity_transport_amendment_fingerprint": (
                    ready["quantity"]["amendment_fingerprint"]
                ),
                "memory_transport_amendment_fingerprint": (
                    ready["precision"]["parent_memory_amendment"]
                ),
                "replay_precision_amendment_fingerprint": (
                    ready["precision"]["amendment_fingerprint"]
                ),
                "repair_plan_sha256": EXPECTED_PLAN_SHA256,
                "repair_cache_coverage_sha256": EXPECTED_REPAIR_COVERAGE_SHA256,
                "repair_cache_parent_replay_precision_coverage_sha256": (
                    EXPECTED_PARENT_REPLAY_PRECISION_COVERAGE_SHA256
                ),
                "supersedes_path_sha256": EXPECTED_SUPERSEDED_Y_A3_PATH_SHA256,
                "source_binding_fingerprint": ready["binding"]["source_binding_fingerprint"],
                "dynamic_ticker_union_count": len(ready["dynamic_tickers"]),
                "dynamic_ticker_union": list(ready["dynamic_tickers"]),
                "policy_results": y_a3.parent.jsonable(results),
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
            digest = y_a3.write_output(repo / OUTPUT, payload)
            progress.report("REPAIR-203 60-SCENARIO OUTCOME-BLIND PATH MATERIALIZATION: PASS")
            print("Output:", OUTPUT)
            print("SHA256:", digest)
            print("Policy scenarios:", len(results))
            print("Settlement outcomes: NOT ACCESSED")
            print("Strategy P&L: NOT RUN")
            print("Orders: 0")
            return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="run the frozen 60 outcome-blind policies after validating all repaired caches",
    )
    args = parser.parse_args()
    try:
        materialize(".", simulate=args.simulate)
    except KeyboardInterrupt:
        print("Interrupted. No completed repaired-path result asserted.", flush=True)
        return 130
    except Exception as error:
        print(f"REPAIR-203 PATH MATERIALIZATION: FAIL CLOSED: {type(error).__name__}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
