"""Validate the frozen 203-pair repair plan against the completed Y-A3 evidence.

This is a pre-cache gate. It does not build caches or run Candidate-E.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True

from src.kxbtcd_candidate_e_july10_outcome_blind_binding import BACKFILL_ROOT_RELATIVE_PATH
from src.kxbtcd_candidate_e_v2_disk_timeline import file_sha256
from src.kxbtcd_candidate_e_v2_repair_materialization import (
    EXPECTED_PLAN_SHA256,
    compose_snapshot_order,
    load_repair_plan,
    repairs_for_ticker,
    require,
)
from src.predexon_full_ladder_replay import load_backfill_snapshots

PLAN = Path("configs/kxbtcd_candidate_e_v2_repair_materialization_plan_203.json")
PARENT_CACHE = Path("data/analysis/predexon_credit_efficiency/v2_y_a3_replay_precision_cache")
PARENT_COVERAGE = PARENT_CACHE / "coverage_full.json"
EXPECTED_PARENT_COVERAGE_SHA256 = "5b78812350bbcd3cea77f9c109dac2cce636de9577426edbaf523179859da1ab"


def validate(repo: Path) -> dict:
    repo = repo.resolve()
    plan = load_repair_plan(repo / PLAN)
    require(file_sha256(repo / PARENT_COVERAGE) == EXPECTED_PARENT_COVERAGE_SHA256,
            "Y-A3 parent coverage SHA mismatch")
    coverage = json.loads((repo / PARENT_COVERAGE).read_text(encoding="utf-8"))
    reports = {r["ticker"]: r for r in coverage["ticker_reports"]}
    require(len(reports) == 47, "expected 47 Y-A3 ticker reports")

    addressed_global = set()
    residual_total = 0
    operation_total = 0
    quarantined_total = 0

    for ticker, report in sorted(reports.items()):
        failed = {int(p["pair_index"]) for p in report["remaining_unreconciled_pairs"]}
        repairs = repairs_for_ticker(plan, ticker)
        operation_total += len(repairs)
        addressed = {
            int(i)
            for repair in repairs
            for i in repair["original_failed_pair_indices_addressed"]
        }
        require(addressed.issubset(failed), f"{ticker}: repair addresses nonfailed parent pair")
        for pair_index in addressed:
            key = (ticker, pair_index)
            require(key not in addressed_global, f"duplicate global addressed pair: {key}")
            addressed_global.add(key)

        snapshot_path = repo / BACKFILL_ROOT_RELATIVE_PATH / f"{ticker}_raw_pages.jsonl"
        snapshots = load_backfill_snapshots(snapshot_path, ticker=ticker)
        require(len(snapshots) == report["after"]["snapshot_count"],
                f"{ticker}: snapshot count changed")

        for repair in repairs:
            context = [int(x) for x in repair["original_context_snapshot_indices"]]
            declared = {int(x) for x in repair["original_failed_pair_indices_addressed"]}
            in_context = {i for i in failed if context[0] <= i < context[-1]}
            require(
                declared == in_context,
                f"{ticker}/{repair['repair_id']}: repair context contains undeclared failed pair(s): "
                f"{sorted(declared ^ in_context)}",
            )
        order = compose_snapshot_order(len(snapshots), repairs)
        quarantined_total += len(snapshots) - len(order)
        timestamps = [int(snapshots[i]["timestamp"]) for i in order]
        require(timestamps == sorted(timestamps), f"{ticker}: revised order moves backward in time")
        residual_total += len(failed - addressed)

    require(operation_total == 110, f"operation total {operation_total} != 110")
    require(len(addressed_global) == 203, f"addressed total {len(addressed_global)} != 203")
    require(residual_total == 545, f"residual total {residual_total} != 545")

    return {
        "repair_operations": operation_total,
        "addressed_pairs": len(addressed_global),
        "residual_hard_boundaries": residual_total,
        "quarantined_snapshots": quarantined_total,
        "plan_sha256": EXPECTED_PLAN_SHA256,
    }


def main() -> int:
    try:
        result = validate(Path("."))
    except Exception as error:
        print(f"CANDIDATE-E 203-PAIR REPAIR MATERIALIZATION PRE-CACHE GATE: FAIL CLOSED")
        print(f"{type(error).__name__}: {error}")
        return 1
    print("CANDIDATE-E 203-PAIR REPAIR MATERIALIZATION PRE-CACHE GATE: PASS")
    print("Repair operations:", result["repair_operations"])
    print("Addressed failed pairs:", result["addressed_pairs"])
    print("Residual hard boundaries:", result["residual_hard_boundaries"])
    print("Quarantined snapshots:", result["quarantined_snapshots"])
    print("Plan SHA256:", result["plan_sha256"])
    print("Cache: NOT BUILT | Strategy: NOT RUN | Outcomes: NOT ACCESSED | P&L: NOT CALCULATED | Orders: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
