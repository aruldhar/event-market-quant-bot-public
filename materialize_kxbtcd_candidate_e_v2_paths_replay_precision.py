"""21N-Y-A3 snapshot-normalized disk-backed runner for the frozen 60-scenario Y-B experiment.

Default: prepare/cache verified books only. --simulate explicitly advances to
the outcome-blind policy loop. No source collection or outcomes are available.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid

import materialize_kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_paths_amended as parent
from src.kxbtcd_candidate_e_july10_outcome_blind_binding import (
    BACKFILL_ROOT_RELATIVE_PATH, REPLAY_TICKER_ROOT_RELATIVE_PATH,
)
from src.predexon_full_ladder_replay import load_backfill_snapshots
from src.kxbtcd_candidate_e_v2_disk_timeline import DiskTimeline, file_sha256
from src.kxbtcd_candidate_e_v2_disk_policy import simulate_policy
from src.kxbtcd_candidate_e_v2_replay_precision_freeze import validate_precision_amendment
from src.kxbtcd_candidate_e_v2_replay_precision import build_precision_timeline, validate_precision_cache

CACHE_ROOT = Path("data/analysis/predexon_credit_efficiency/v2_y_a3_replay_precision_cache")
OUTPUT = Path("data/analysis/predexon_credit_efficiency/july10_candidate_e_v2_outcome_blind_paths_replay_precision.json")


class Progress:
    def __init__(self):
        self.started = time.monotonic()
        self.stage = "starting"
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def report(self, message):
        self.stage = message
        print(f"[{time.monotonic() - self.started:.0f}s] {message}", flush=True)

    def _heartbeat(self):
        while not self.stop.wait(15):
            print(f"[{time.monotonic() - self.started:.0f}s] Working: {self.stage}", flush=True)

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=1)


def require_committed_amendment(repo: Path, amendment: dict) -> None:
    paths = ["configs/kxbtcd_candidate_e_v2_replay_precision_amendment.json",
             "src/kxbtcd_candidate_e_v2_replay_precision_freeze.py", *amendment["frozen_files"]]
    for relative in paths:
        result = subprocess.run(["git", "show", f"HEAD:{relative}"], cwd=repo,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode or result.stdout.replace(b"\r\n", b"\n") != (repo / relative).read_bytes().replace(b"\r\n", b"\n"):
            raise RuntimeError("Close/push 21N-Y-A3 before real-data preparation: " + relative)


@contextmanager
def run_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "RUNNING.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise RuntimeError(f"Run lock exists: {lock}. Check for an active runner before removing a stale lock.") from None
    try:
        with handle:
            handle.write(f"pid={os.getpid()}\n")
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        lock.unlink()


def open_sealed_cache(path: Path, identity: dict) -> DiskTimeline:
    seal_path = path.with_suffix(".seal.json")
    if not path.is_file() or not seal_path.is_file():
        raise RuntimeError(f"Unsealed ticker cache: {path}; preserve/rename it before rebuilding.")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    if seal.get("identity") != identity or seal.get("sha256") != file_sha256(path):
        raise RuntimeError(f"Ticker cache source/hash mismatch: {path}")
    timeline = DiskTimeline(path)
    if timeline.metadata["identity"] != identity or timeline.ticker != identity["ticker"]:
        timeline.close()
        raise RuntimeError(f"Ticker cache metadata mismatch: {path}")
    return timeline


def prepare_ticker(*, repo: Path, root: Path, ticker: str, paid_path: Path,
                   amendment_fp: str, progress) -> Path:
    snapshots_path = repo / BACKFILL_ROOT_RELATIVE_PATH / f"{ticker}_raw_pages.jsonl"
    replay_path = repo / REPLAY_TICKER_ROOT_RELATIVE_PATH / f"{ticker}.json"
    identity = {"ticker": ticker, "paid_sha256": parent.EXPECTED_PAID_TICKS_SHA256,
                "snapshot_sha256": file_sha256(snapshots_path),
                "replay_sha256": file_sha256(replay_path), "memory_amendment_fingerprint": "f7a590cb0f8415e3330fa82077d16b6b93105717f573e69e8580a3f3ac1ffe03",
                "replay_precision_amendment_fingerprint": amendment_fp,
                "quantity_amendment_fingerprint": parent.EXPECTED_AMENDMENT_FINGERPRINT}
    target = root / f"{ticker}.sqlite"
    if target.exists() or target.with_suffix(".seal.json").exists():
        progress(f"{ticker}: checking completed cache")
        timeline = open_sealed_cache(target, identity)
        try:
            validate_precision_cache(timeline)
        finally:
            timeline.close()
        progress(f"{ticker}: reused verified cache")
        return target

    temporary = root / f"{ticker}.{uuid.uuid4().hex}.building.sqlite"
    seal_temporary = temporary.with_suffix(".seal.json")
    try:
        progress(f"{ticker}: loading this ticker's source rows")
        paid = parent.load_paid_rows_for_tickers(paid_path, (ticker,))[ticker]
        snapshots = load_backfill_snapshots(snapshots_path, ticker=ticker)
        progress(f"{ticker}: {len(paid):,} deltas / {len(snapshots):,} snapshots")
        build_precision_timeline(path=temporary, ticker=ticker, snapshots=snapshots, paid_rows=paid,
                            identity=identity, baseline_path=replay_path, progress=progress)
        del paid, snapshots
        gc.collect()
        timeline = DiskTimeline(temporary)
        try:
            validate_precision_cache(timeline)
            states = sum(s.state_count for s in timeline.segments)
        finally:
            timeline.close()
        # Refuse to seal bytes if local raw inputs changed during construction.
        if file_sha256(snapshots_path) != identity["snapshot_sha256"] or file_sha256(replay_path) != identity["replay_sha256"]:
            raise RuntimeError(f"Source changed while building {ticker}")
        seal = {"identity": identity, "sha256": file_sha256(temporary)}
        with seal_temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(seal, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        os.replace(seal_temporary, target.with_suffix(".seal.json"))
        progress(f"{ticker}: SEALED {states:,} states; {target.stat().st_size / 1024**2:.1f} MiB on disk")
        return target
    finally:
        for temporary_path in (temporary, seal_temporary, Path(str(temporary) + "-journal")):
            if temporary_path.exists():
                temporary_path.unlink()


def write_output(path: Path, payload: dict) -> str:
    parent.assert_outcome_blind_payload(payload)
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if path.exists():
        if path.read_bytes() != raw:
            raise RuntimeError(f"refusing non-identical overwrite: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
    return hashlib.sha256(raw).hexdigest()


def materialize(repo_root=".", *, simulate=False, max_tickers=None):
    repo = Path(repo_root).resolve()
    if max_tickers is not None and (max_tickers < 1 or simulate):
        raise ValueError("--max-tickers requires preparation-only mode and a positive count")
    with Progress() as progress:
        progress.report("validating frozen parents and replay precision amendment")
        amendment = validate_precision_amendment(repo)
        require_committed_amendment(repo, amendment)
        original_path = repo / amendment["original_path_relative"]
        if not original_path.is_file() or file_sha256(original_path) != amendment["original_path_sha256"]:
            raise RuntimeError("Preserved original Y-B output is missing or changed; inspect before rebuilding")
        parents = parent.validate_parents(repo)
        y_a = parent.validate_y_a_freeze(repo)
        quantity = parent.validate_amendment(repo)
        binding = parent.validate_binding(repo)
        if binding.get("source_binding_fingerprint") != parent.EXPECTED_BINDING_FINGERPRINT:
            raise RuntimeError("source binding fingerprint mismatch")
        btc_block = binding["continuous_btc_materialization"]
        btc_path = repo / btc_block["relative_path"]
        if file_sha256(btc_path) != btc_block["sha256"]:
            raise RuntimeError("bound continuous Coinbase artifact changed")
        btc_rows = parent.load_materialization(btc_path)
        paid_path = repo / parent.PAID_TICKS_RELATIVE_PATH
        progress.report("checking paid shard hash and full source set")
        if file_sha256(paid_path) != parent.EXPECTED_PAID_TICKS_SHA256:
            raise RuntimeError("paid Predexon shard hash mismatch")
        if binding.get("full_ladder_replay_summary_sha256") != parent.EXPECTED_REPLAY_SUMMARY_SHA256:
            raise RuntimeError("full-ladder replay binding mismatch")
        paid_tickers = parent.collect_paid_tickers(paid_path)
        parent.validate_file_set_alignment(repo_root=repo, paid_tickers=paid_tickers)
        structural = parent.derive_structural_universe(paid_tickers)
        ladders = parent.build_event_ladders(paid_tickers, structural)
        dynamic_tickers = parent.required_dynamic_tickers(event_ladders=ladders, btc_rows=btc_rows)
        selected = dynamic_tickers if max_tickers is None else dynamic_tickers[:max_tickers]
        root = repo / CACHE_ROOT
        with run_lock(root):
            paths = {}
            for index, ticker in enumerate(selected, 1):
                progress.report(f"ticker {index}/{len(selected)}; dynamic union {len(dynamic_tickers)}")
                paths[ticker] = prepare_ticker(repo=repo, root=root, ticker=ticker, paid_path=paid_path,
                    amendment_fp=amendment["amendment_fingerprint"], progress=progress.report)
            # The shard is immutable evidence; verify it again before scoring.
            if file_sha256(paid_path) != parent.EXPECTED_PAID_TICKS_SHA256:
                raise RuntimeError("paid shard changed during preparation")
            reports = []
            for ticker in selected:
                timeline = DiskTimeline(paths[ticker])
                try:
                    reports.append(validate_precision_cache(timeline))
                finally:
                    timeline.close()
            coverage = {"schema_version": "candidate_e_v2_replay_precision_coverage.v1",
                "replay_precision_amendment_fingerprint": amendment["amendment_fingerprint"],
                "dynamic_ticker_union_count": len(dynamic_tickers), "prepared_ticker_count": len(paths),
                "ticker_reports": reports, "outcomes_accessed": False, "strategy_pnl_calculated": False,
                "candidate_e_scored": False, "orders_placed": 0, "network_requests": 0}
            coverage_path = root / ("coverage_full.json" if max_tickers is None else f"coverage_first_{max_tickers}.json")
            coverage_digest = write_output(coverage_path, coverage)
            print(f"Coverage report: {coverage_path}\nSHA256: {coverage_digest}", flush=True)
            if not simulate:
                progress.report(f"PREPARATION PASS: {len(paths)}/{len(dynamic_tickers)} tickers cached; scoring NOT STARTED")
                return None
            results = []
            for event in sorted(ladders):
                timelines = {}
                try:
                    for ticker in dynamic_tickers:
                        if ticker.rsplit("-T", 1)[0] == event:
                            # prepare_ticker already checked each cache's seal in this run.
                            timelines[ticker] = DiskTimeline(paths[ticker])
                    for threshold in parent.THRESHOLDS:
                        for latency_ms in parent.LATENCY_MS:
                            progress.report(f"scenario {len(results)+1}/60: {event}, margin={threshold}, latency={latency_ms}ms")
                            results.append({"event_ticker": event, "threshold_dollars": threshold, "latency_ms": latency_ms,
                                "policy_result": simulate_policy(event_ticker=event, event_ladder=ladders[event],
                                    timelines=timelines, btc_rows=btc_rows, threshold=threshold, latency_ms=latency_ms)})
                finally:
                    for timeline in timelines.values():
                        timeline.close()
            if len(results) != 60:
                raise RuntimeError("expected exactly 60 policy scenarios")
            payload = {
                "schema_version": "kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_outcome_blind_paths.v1",
                "checkpoint_id": "21N-Y-B", "strategy_id": parent.STRATEGY_ID,
                "evidence_role": "four_event_july10_development_and_mechanics_only", "advancement_gate": "NONE_N_EQ_4",
                "frozen_parents": parents, "implementation_fingerprint": y_a["implementation_fingerprint"],
                "execution_quantity_transport_amendment_fingerprint": quantity["amendment_fingerprint"],
                "memory_transport_amendment_fingerprint": amendment["parent_memory_amendment"],
                "replay_precision_amendment_fingerprint": amendment["amendment_fingerprint"],
                "supersedes_path_sha256": amendment["original_path_sha256"],
                "source_binding_fingerprint": binding["source_binding_fingerprint"],
                "dynamic_ticker_union_count": len(dynamic_tickers), "dynamic_ticker_union": list(dynamic_tickers),
                "replay_precision_coverage_sha256": coverage_digest,
                "policy_results": parent.jsonable(results),
                "safety": {"candidate_e_refit": False, "candidate_e_nonstructural_scoring_performed": True,
                    "outcomes_accessed": False, "strategy_pnl_calculated": False, "network_requests": 0,
                    "predexon_paid_purchases": 0, "orders_placed": 0, "paper_broker": False,
                    "demo_execution": False, "real_money_execution": False, "protected_reserve_accessed": False},
            }
            digest = write_output(repo / OUTPUT, payload)
            progress.report("Checkpoint 21N-Y-B replay-precision outcome-blind path materialization: PASS")
            print(f"Output: {OUTPUT}\nSHA256: {digest}\nPolicy scenarios: 60", flush=True)
            return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulate", action="store_true", help="run all 60 frozen policies after full cache preparation")
    parser.add_argument("--max-tickers", type=int, help="prepare only the first N deterministic tickers; no scoring")
    args = parser.parse_args()
    try:
        materialize(simulate=args.simulate, max_tickers=args.max_tickers)
    except KeyboardInterrupt:
        print("Interrupted. Completed sealed ticker caches retained; no completed result asserted.", flush=True)
        return 130
    print("Settlement outcomes: NOT ACCESSED\nStrategy P&L: NOT RUN\nOrders: 0", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
