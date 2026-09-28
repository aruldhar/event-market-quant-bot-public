"""Prepare sealed 203-repair Candidate-E disk caches. Strategy is not run.

This real-data runner intentionally has no --simulate mode. It requires the
repair implementation and frozen plan to already be committed before building
new evidence caches.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import gc
import json
import os
from pathlib import Path
import subprocess
import uuid

import materialize_kxbtcd_candidate_e_v2_paths_replay_precision as y_a3
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from src.kxbtcd_candidate_e_july10_outcome_blind_binding import (
    BACKFILL_ROOT_RELATIVE_PATH,
    EXPECTED_PAID_TICKS_SHA256,
    PAID_TICKS_RELATIVE_PATH,
    REPLAY_TICKER_ROOT_RELATIVE_PATH,
)
from src.kxbtcd_candidate_e_v2_disk_timeline import DiskTimeline, file_sha256
from src.kxbtcd_candidate_e_v2_repair_materialization import (
    EXPECTED_PLAN_SHA256,
    build_repair_timeline,
    load_repair_plan,
    repairs_for_ticker,
    require,
    validate_repair_cache,
)
from src.kxbtcd_candidate_e_v2_replay_precision import precision_audit

PLAN = Path("configs/kxbtcd_candidate_e_v2_repair_materialization_plan_203.json")
CACHE_ROOT = Path("data/analysis/predexon_credit_efficiency/v2_repair_203_cache")
PARENT_COVERAGE = Path("data/analysis/predexon_credit_efficiency/v2_y_a3_replay_precision_cache/coverage_full.json")
EXPECTED_PARENT_COVERAGE_SHA256 = "5b78812350bbcd3cea77f9c109dac2cce636de9577426edbaf523179859da1ab"
IMPLEMENTATION_FILES = (
    "configs/kxbtcd_candidate_e_v2_repair_materialization_plan_203.json",
    "src/kxbtcd_candidate_e_v2_repair_materialization.py",
    "validate_kxbtcd_candidate_e_v2_repair_materialization_203.py",
    "materialize_kxbtcd_candidate_e_v2_repair_cache_203.py",
    "tests/test_kxbtcd_candidate_e_v2_repair_materialization.py",
)


PAID_COLUMNS = ("ticker", "timestamp", "sequence", "side", "price_dollars", "delta_fp")


def load_paid_rows_exact_for_ticker(parquet_path: Path, ticker: str) -> list[dict]:
    """Preserve A4's timestamp/sequence/original-source-row ordering exactly."""
    selected = pa.array([ticker], type=pa.string())
    parquet = pq.ParquetFile(parquet_path)
    rows = []
    scanned = 0
    for batch in parquet.iter_batches(batch_size=131072, columns=list(PAID_COLUMNS)):
        ticker_column = batch.column(batch.schema.get_field_index("ticker"))
        mask = pc.fill_null(pc.is_in(ticker_column, value_set=selected), False)
        filtered = batch.filter(mask)
        source_indices = pc.indices_nonzero(mask).to_pylist()
        for row, offset in zip(filtered.to_pylist(), source_indices):
            row = dict(row)
            row["source_row_number_1based"] = scanned + int(offset) + 1
            rows.append(row)
        scanned += batch.num_rows
    require(rows, f"zero paid deltas for dynamic ticker {ticker}")
    rows.sort(
        key=lambda row: (
            int(row["timestamp"]),
            int(row["sequence"]),
            int(row["source_row_number_1based"]),
        )
    )
    return rows


def require_committed_implementation(repo: Path) -> None:
    for relative in IMPLEMENTATION_FILES:
        local = repo / relative
        require(local.is_file(), f"implementation file missing: {relative}")
        result = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        require(result.returncode == 0, f"close/push repair-cache checkpoint before real build: {relative}")
        require(
            result.stdout.replace(b"\r\n", b"\n") == local.read_bytes().replace(b"\r\n", b"\n"),
            f"committed/local implementation mismatch: {relative}",
        )


def open_sealed_repair_cache(path: Path, identity: dict) -> DiskTimeline:
    seal_path = path.with_suffix(".seal.json")
    require(path.is_file() and seal_path.is_file(), f"unsealed repair cache: {path}")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    require(seal.get("identity") == identity, f"repair cache identity mismatch: {path}")
    require(seal.get("sha256") == file_sha256(path), f"repair cache hash mismatch: {path}")
    timeline = DiskTimeline(path)
    try:
        require(timeline.metadata.get("identity") == identity, f"repair cache metadata identity mismatch: {path}")
        validate_repair_cache(timeline)
    except BaseException:
        timeline.close()
        raise
    return timeline


def prepare_ticker(
    *,
    repo: Path,
    root: Path,
    ticker: str,
    paid_path: Path,
    parent_report: dict,
    plan: dict,
    progress,
) -> tuple[Path, dict]:
    snapshot_path = repo / BACKFILL_ROOT_RELATIVE_PATH / f"{ticker}_raw_pages.jsonl"
    replay_path = repo / REPLAY_TICKER_ROOT_RELATIVE_PATH / f"{ticker}.json"
    builder_path = repo / "src/kxbtcd_candidate_e_v2_repair_materialization.py"
    identity = {
        "ticker": ticker,
        "paid_sha256": EXPECTED_PAID_TICKS_SHA256,
        "snapshot_sha256": file_sha256(snapshot_path),
        "replay_sha256": file_sha256(replay_path),
        "parent_replay_precision_coverage_sha256": EXPECTED_PARENT_COVERAGE_SHA256,
        "repair_plan_sha256": EXPECTED_PLAN_SHA256,
        "repair_builder_sha256": file_sha256(builder_path),
        "memory_amendment_fingerprint": "f7a590cb0f8415e3330fa82077d16b6b93105717f573e69e8580a3f3ac1ffe03",
        "replay_precision_amendment_fingerprint": "82c4d05994cf97c723672b82428a7a139e20f96ae5aeea622e6dfaf1429a1370",
        "quantity_amendment_fingerprint": "2cbd8836045ae811eb4c52d48834953a54b1be3afac094be4cf349b8cac2abce",
    }
    target = root / f"{ticker}.sqlite"
    if target.exists() or target.with_suffix(".seal.json").exists():
        progress(f"{ticker}: checking completed repair cache")
        timeline = open_sealed_repair_cache(target, identity)
        try:
            audit = validate_repair_cache(timeline)
        finally:
            timeline.close()
        progress(f"{ticker}: reused verified repair cache")
        return target, audit

    temporary = root / f"{ticker}.{uuid.uuid4().hex}.building.sqlite"
    seal_temporary = temporary.with_suffix(".seal.json")
    try:
        progress(f"{ticker}: loading exact source rows")
        paid_rows = load_paid_rows_exact_for_ticker(paid_path, ticker)
        snapshots = y_a3.load_backfill_snapshots(snapshot_path, ticker=ticker)
        normalized, precision_report = precision_audit(
            ticker=ticker,
            snapshots=snapshots,
            paid_rows=paid_rows,
            baseline_path=replay_path,
        )
        require(precision_report == parent_report, f"{ticker}: Y-A3 precision report changed")
        ticker_repairs = repairs_for_ticker(plan, ticker)
        progress(
            f"{ticker}: {len(paid_rows):,} deltas / {len(snapshots):,} snapshots / "
            f"{len(ticker_repairs)} repair operations"
        )
        audit = build_repair_timeline(
            path=temporary,
            ticker=ticker,
            snapshots=normalized,
            paid_rows=paid_rows,
            identity=identity,
            precision_report=precision_report,
            repairs=ticker_repairs,
            progress=progress,
        )
        del paid_rows, snapshots, normalized
        gc.collect()

        timeline = DiskTimeline(temporary)
        try:
            validate_repair_cache(timeline)
            states = sum(s.state_count for s in timeline.segments)
        finally:
            timeline.close()

        require(file_sha256(snapshot_path) == identity["snapshot_sha256"],
                f"{ticker}: snapshot source changed during build")
        require(file_sha256(replay_path) == identity["replay_sha256"],
                f"{ticker}: replay source changed during build")
        seal = {"identity": identity, "sha256": file_sha256(temporary)}
        with seal_temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(seal, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        os.replace(seal_temporary, target.with_suffix(".seal.json"))
        progress(
            f"{ticker}: SEALED {states:,} states / "
            f"{audit['remaining_unreconciled_pair_count']} residual boundaries"
        )
        return target, audit
    finally:
        for p in (temporary, seal_temporary, Path(str(temporary) + "-journal")):
            if p.exists():
                p.unlink()


def materialize(repo_root=".", *, max_tickers=None):
    repo = Path(repo_root).resolve()
    if max_tickers is not None:
        require(max_tickers >= 1, "--max-tickers must be positive")
    with y_a3.Progress() as progress:
        progress.report("validating committed repair-cache implementation")
        require_committed_implementation(repo)
        plan = load_repair_plan(repo / PLAN)
        require(file_sha256(repo / PARENT_COVERAGE) == EXPECTED_PARENT_COVERAGE_SHA256,
                "Y-A3 parent coverage SHA mismatch")
        coverage = json.loads((repo / PARENT_COVERAGE).read_text(encoding="utf-8"))
        reports = {r["ticker"]: r for r in coverage["ticker_reports"]}
        require(len(reports) == 47, "expected 47 parent ticker reports")
        tickers = sorted(reports)
        selected = tickers if max_tickers is None else tickers[:max_tickers]

        paid_path = repo / PAID_TICKS_RELATIVE_PATH
        require(file_sha256(paid_path) == EXPECTED_PAID_TICKS_SHA256, "paid shard SHA mismatch")
        root = repo / CACHE_ROOT
        with y_a3.run_lock(root):
            audits = []
            for number, ticker in enumerate(selected, 1):
                progress.report(f"repair-cache ticker {number}/{len(selected)}")
                _, audit = prepare_ticker(
                    repo=repo,
                    root=root,
                    ticker=ticker,
                    paid_path=paid_path,
                    parent_report=reports[ticker],
                    plan=plan,
                    progress=progress.report,
                )
                audits.append(audit)

            addressed = sum(len(a["original_failed_pairs_addressed"]) for a in audits)
            residual = sum(a["remaining_unreconciled_pair_count"] for a in audits)
            operations = sum(a["repair_operation_count"] for a in audits)
            payload = {
                "schema_version": "candidate_e_v2_repair_203_coverage.v1",
                "checkpoint_id": "21N-Y-A5",
                "repair_plan_sha256": EXPECTED_PLAN_SHA256,
                "parent_replay_precision_coverage_sha256": EXPECTED_PARENT_COVERAGE_SHA256,
                "prepared_ticker_count": len(audits),
                "full_ticker_count": len(tickers),
                "repair_operation_count": operations,
                "original_failed_pairs_addressed": addressed,
                "remaining_unreconciled_pair_count": residual,
                "ticker_audits": audits,
                "safety": {
                    "candidate_e_scored": False,
                    "strategy_run": False,
                    "outcomes_accessed": False,
                    "strategy_pnl_calculated": False,
                    "network_requests": 0,
                    "orders_placed": 0,
                },
            }
            if max_tickers is None:
                require(operations == 110, f"full build operation count {operations} != 110")
                require(addressed == 203, f"full build addressed count {addressed} != 203")
                require(residual == 545, f"full build residual count {residual} != 545")
            output = root / ("coverage_full.json" if max_tickers is None
                             else f"coverage_first_{max_tickers}.json")
            digest = y_a3.write_output(output, payload)
            progress.report(
                f"REPAIR-CACHE PREPARATION PASS: {len(audits)}/{len(tickers)} tickers; "
                "strategy NOT STARTED"
            )
            print("Coverage report:", output)
            print("SHA256:", digest)
            print("Repair operations applied:", operations)
            print("Failed pairs addressed:", addressed)
            print("Residual hard boundaries:", residual)
            print("Strategy: NOT RUN | Outcomes: NOT ACCESSED | P&L: NOT CALCULATED | Orders: 0")
            return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-tickers", type=int)
    args = parser.parse_args()
    try:
        materialize(".", max_tickers=args.max_tickers)
    except KeyboardInterrupt:
        print("Interrupted. Completed sealed repair caches retained; no completion asserted.")
        return 130
    except Exception as error:
        print(f"REPAIR-CACHE PREPARATION: FAIL CLOSED: {type(error).__name__}: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
