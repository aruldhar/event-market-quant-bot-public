"""Additive repair-aware disk materialization for Candidate-E July 10 evidence.

The frozen Y-A3 replay remains unchanged. This module consumes a separately
frozen repair plan whose operations are expressed in Y-A3 normalized snapshot
indices. Only plan-pinned local contexts may change adjacency/order. Every
pinned cut pair is replayed independently and must reconstruct the authoritative
endpoint snapshot exactly at zero tolerance. Unsupported pairs remain hard
segment boundaries.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from contextlib import closing
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    ExecutableConvergenceSimulatorError,
    _book_state_from_maps,
    _same_book,
)
from .kxbtcd_candidate_e_v2_disk_timeline import (
    DiskTimeline,
    SCHEMA as DISK_SCHEMA,
    configure,
    decode_book,
    encode_book,
    top_key,
)
from .kxbtcd_candidate_e_v2_execution_quantity_transport_amendment import (
    canonicalize_book_state,
)
from .predexon_segment_safe_replay import (
    apply_delta,
    mismatch_count,
    reconcile_pair,
    snapshot_book,
)

PLAN_SCHEMA = "candidate_e_repair_materialization_plan.v1"
AUDIT_SCHEMA = "candidate_e_repair_cache_audit.v1"
EXPECTED_PLAN_SHA256 = "e95fe1c8d170dad1da9a51fe11e892c1efa70a124f52bbe9acf687c50edbb32b"
ZERO = Decimal("0")


def paid_row_key(row: Mapping[str, Any]) -> tuple[int, int, int]:
    """A4's exact paid-row authority: timestamp, sequence, original source row."""
    require("source_row_number_1based" in row, "paid row missing original source-row identity")
    return (
        int(row["timestamp"]),
        int(row["sequence"]),
        int(row["source_row_number_1based"]),
    )


class RepairMaterializationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RepairMaterializationError(message)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_repair_plan(path: Path, *, expected_sha256: str = EXPECTED_PLAN_SHA256) -> dict[str, Any]:
    require(path.is_file(), f"repair plan missing: {path}")
    observed = file_sha256(path)
    require(observed == expected_sha256,
            f"repair plan SHA mismatch: expected {expected_sha256}, got {observed}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(payload.get("schema_version") == PLAN_SCHEMA, "repair plan schema mismatch")
    counts = payload.get("counts", {})
    require(counts.get("repair_operations") == 110, "repair operation count mismatch")
    require(counts.get("original_failed_pairs_addressed") == 203, "addressed-pair count mismatch")
    require(counts.get("remaining_original_failed_pairs_expected") == 545, "residual-pair count mismatch")
    require(counts.get("cross_repair_context_overlap_count") == 0, "repair contexts are not disjoint")
    contract = payload.get("materialization_contract", {})
    for key in (
        "raw_snapshots_mutated",
        "paid_rows_mutated",
        "strategy_run_in_builder_checkpoint",
        "outcomes_accessed",
        "strategy_pnl_calculated",
    ):
        require(contract.get(key) is False, f"repair plan safety mismatch: {key}")
    require(contract.get("changed_adjacencies_must_use_required_cut_chain_exactly") is True,
            "repair plan does not pin cut chains")
    require(contract.get("remaining_545_failed_pairs_are_hard_segment_boundaries") is True,
            "repair plan does not preserve unresolved boundaries")
    validate_repair_operations(payload["repairs"])
    return payload


def validate_repair_operations(repairs: Sequence[Mapping[str, Any]]) -> None:
    require(len(repairs) == 110, "expected 110 repair operations")
    addressed = set()
    contexts_by_ticker: dict[str, list[set[int]]] = {}
    for repair in repairs:
        ticker = str(repair["ticker"])
        context = [int(x) for x in repair["original_context_snapshot_indices"]]
        order = [int(x) for x in repair["required_snapshot_order_original_indices"]]
        cuts = [int(x) for x in repair["required_cut_chain"]]
        pairs = [int(x) for x in repair["original_failed_pair_indices_addressed"]]
        require(context == list(range(context[0], context[-1] + 1)),
                f"{repair['repair_id']}: context is not contiguous original indices")
        require(len(cuts) == len(order),
                f"{repair['repair_id']}: cut-chain length must equal revised order length")
        require(set(order).issubset(set(context)),
                f"{repair['repair_id']}: revised order escapes context")
        omitted = sorted(set(context) - set(order))
        require(omitted == [int(x) for x in repair.get("quarantined_snapshot_indices", [])],
                f"{repair['repair_id']}: quarantine list mismatch")
        for pair_index in pairs:
            key = (ticker, pair_index)
            require(key not in addressed, f"failed pair addressed twice: {key}")
            addressed.add(key)
        prior = contexts_by_ticker.setdefault(ticker, [])
        current = set(context)
        require(all(not current.intersection(other) for other in prior),
                f"{repair['repair_id']}: context overlaps another repair")
        prior.append(current)
    require(len(addressed) == 203, "repair plan does not address 203 unique failed pairs")


def repairs_for_ticker(plan: Mapping[str, Any], ticker: str) -> list[dict[str, Any]]:
    return [dict(r) for r in plan["repairs"] if r["ticker"] == ticker]


def compose_snapshot_order(snapshot_count: int, repairs: Sequence[Mapping[str, Any]]) -> list[int]:
    by_start: dict[int, Mapping[str, Any]] = {}
    for repair in repairs:
        context = [int(x) for x in repair["original_context_snapshot_indices"]]
        require(0 <= context[0] <= context[-1] < snapshot_count,
                f"{repair['repair_id']}: context outside snapshot universe")
        require(context[0] not in by_start, f"duplicate repair start index {context[0]}")
        by_start[context[0]] = repair
    output: list[int] = []
    i = 0
    while i < snapshot_count:
        repair = by_start.get(i)
        if repair is None:
            output.append(i)
            i += 1
            continue
        context = [int(x) for x in repair["original_context_snapshot_indices"]]
        require(context == list(range(i, context[-1] + 1)),
                f"{repair['repair_id']}: noncontiguous replacement")
        output.extend(int(x) for x in repair["required_snapshot_order_original_indices"])
        i = context[-1] + 1
    require(len(output) == len(set(output)), "revised snapshot order contains duplicate indices")
    return output


def edge_overrides(repairs: Sequence[Mapping[str, Any]]) -> dict[tuple[int, int], dict[str, Any]]:
    overrides: dict[tuple[int, int], dict[str, Any]] = {}
    for repair in repairs:
        order = [int(x) for x in repair["required_snapshot_order_original_indices"]]
        cuts = [int(x) for x in repair["required_cut_chain"]]
        for k, (a, b) in enumerate(zip(order, order[1:])):
            key = (a, b)
            require(key not in overrides, f"changed adjacency pinned twice: {key}")
            overrides[key] = {
                "repair_id": repair["repair_id"],
                "source": repair["source"],
                "kind": repair["kind"],
                "start_cut": cuts[k],
                "end_cut": cuts[k + 1],
            }
    return overrides


class PaidWindow:
    def __init__(self, rows: Sequence[Mapping[str, Any]]):
        self.rows = list(rows)
        ordered = sorted(self.rows, key=paid_row_key)
        require(
            self.rows == ordered,
            "paid rows must already be ordered by timestamp/sequence/source-row",
        )
        self.timestamps = [int(r["timestamp"]) for r in self.rows]

    def between(self, start_ts: int, end_ts: int) -> list[Mapping[str, Any]]:
        require(start_ts <= end_ts, "revised adjacency moved backward in time")
        lo = bisect_left(self.timestamps, start_ts)
        hi = bisect_right(self.timestamps, end_ts)
        return self.rows[lo:hi]


def selected_rows_for_cuts(
    start_snapshot: Mapping[str, Any],
    end_snapshot: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    start_cut: int,
    end_cut: int,
) -> list[Mapping[str, Any]]:
    start_ts = int(start_snapshot["timestamp"])
    end_ts = int(end_snapshot["timestamp"])
    require(start_ts <= end_ts, "snapshot timestamps moved backward")
    ordered = sorted(rows, key=paid_row_key)
    if start_ts == end_ts:
        batch = [r for r in ordered if int(r["timestamp"]) == start_ts]
        require(0 <= start_cut <= end_cut <= len(batch),
                f"illegal same-timestamp cuts {start_cut},{end_cut} for {len(batch)} rows")
        return list(batch[start_cut:end_cut])
    start_batch = [r for r in ordered if int(r["timestamp"]) == start_ts]
    middle = [r for r in ordered if start_ts < int(r["timestamp"]) < end_ts]
    end_batch = [r for r in ordered if int(r["timestamp"]) == end_ts]
    require(0 <= start_cut <= len(start_batch), "illegal start cut")
    require(0 <= end_cut <= len(end_batch), "illegal end cut")
    return [*start_batch[start_cut:], *middle, *end_batch[:end_cut]]


def verify_edge_and_rows(
    start_snapshot: Mapping[str, Any],
    end_snapshot: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    start_cut: int,
    end_cut: int,
) -> list[Mapping[str, Any]]:
    selected = selected_rows_for_cuts(
        start_snapshot, end_snapshot, rows, start_cut=start_cut, end_cut=end_cut
    )
    bids, asks = snapshot_book(start_snapshot)
    for row in selected:
        apply_delta(bids, asks, row)
    expected_bids, expected_asks = snapshot_book(end_snapshot)
    require(
        mismatch_count(bids, expected_bids, epsilon=ZERO) == 0
        and mismatch_count(asks, expected_asks, epsilon=ZERO) == 0,
        "pinned/reconciled edge does not exactly reconstruct endpoint book",
    )
    return selected


def _failed_indices(precision_report: Mapping[str, Any]) -> set[int]:
    return {int(p["pair_index"]) for p in precision_report["remaining_unreconciled_pairs"]}


def build_repaired_edge_specs(
    *,
    snapshots: Sequence[Mapping[str, Any]],
    paid_rows: Sequence[Mapping[str, Any]],
    precision_report: Mapping[str, Any],
    repairs: Sequence[Mapping[str, Any]],
) -> tuple[list[int], list[dict[str, Any]], set[int], set[int]]:
    failed = _failed_indices(precision_report)
    addressed = {
        int(i)
        for repair in repairs
        for i in repair["original_failed_pair_indices_addressed"]
    }
    require(addressed.issubset(failed), "repair plan addresses a pair not failed in Y-A3")

    # A repair may not silently leap across another unresolved failure.
    for repair in repairs:
        context = [int(x) for x in repair["original_context_snapshot_indices"]]
        failures_in_context = {i for i in failed if context[0] <= i < context[-1]}
        declared = {int(i) for i in repair["original_failed_pair_indices_addressed"]}
        require(
            failures_in_context == declared,
            f"{repair['repair_id']}: context contains undeclared/omitted failed pairs "
            f"{sorted(failures_in_context ^ declared)}",
        )

    residual = failed - addressed
    order = compose_snapshot_order(len(snapshots), repairs)
    overrides = edge_overrides(repairs)
    paid = PaidWindow(paid_rows)
    edges: list[dict[str, Any]] = []

    for revised_pair_index, (a, b) in enumerate(zip(order, order[1:])):
        start = snapshots[a]
        end = snapshots[b]
        start_ts = int(start["timestamp"])
        end_ts = int(end["timestamp"])
        require(start_ts <= end_ts, "repair plan creates timestamp reversal")
        nearby = paid.between(start_ts, end_ts)
        override = overrides.get((a, b))
        if override is not None:
            selected = verify_edge_and_rows(
                start,
                end,
                nearby,
                start_cut=int(override["start_cut"]),
                end_cut=int(override["end_cut"]),
            )
            edges.append({
                "revised_pair_index": revised_pair_index,
                "original_start_snapshot_index": a,
                "original_end_snapshot_index": b,
                "exact": True,
                "start_cut": int(override["start_cut"]),
                "end_cut": int(override["end_cut"]),
                "selected_delta_count": len(selected),
                "repair_id": override["repair_id"],
                "repair_source": override["source"],
                "repair_kind": override["kind"],
            })
            continue

        require(b == a + 1, f"unplanned changed adjacency {a}->{b}")
        result = reconcile_pair(start, end, nearby, epsilon=ZERO)
        if result.exact:
            selected = verify_edge_and_rows(
                start, end, nearby, start_cut=result.start_cut, end_cut=result.end_cut
            )
        else:
            selected = []
        edges.append({
            "revised_pair_index": revised_pair_index,
            "original_start_snapshot_index": a,
            "original_end_snapshot_index": b,
            "exact": bool(result.exact),
            "start_cut": int(result.start_cut),
            "end_cut": int(result.end_cut),
            "selected_delta_count": len(selected),
            "repair_id": None,
            "repair_source": None,
            "repair_kind": None,
        })

    edge_by_original = {
        (e["original_start_snapshot_index"], e["original_end_snapshot_index"]): e
        for e in edges
    }
    for pair_index in residual:
        edge = edge_by_original.get((pair_index, pair_index + 1))
        require(edge is not None, f"residual failed pair silently removed: {pair_index}")
        require(edge["exact"] is False, f"residual failed pair unexpectedly crossed: {pair_index}")
    return order, edges, addressed, residual


def segment_edge_ranges(order: Sequence[int], edges: Sequence[Mapping[str, Any]]) -> list[tuple[int, int]]:
    """Return inclusive positions in revised snapshot order for each segment."""
    if not order:
        return []
    ranges = []
    start_pos = 0
    for edge_pos, edge in enumerate(edges):
        if not edge["exact"]:
            ranges.append((start_pos, edge_pos))
            start_pos = edge_pos + 1
    ranges.append((start_pos, len(order) - 1))
    return ranges


def build_repair_timeline(
    *,
    path: Path,
    ticker: str,
    snapshots: Sequence[Mapping[str, Any]],
    paid_rows: Sequence[Mapping[str, Any]],
    identity: dict[str, Any],
    precision_report: Mapping[str, Any],
    repairs: Sequence[Mapping[str, Any]],
    repair_plan_sha256: str = EXPECTED_PLAN_SHA256,
    progress: Callable[[str], None] = lambda message: None,
) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite cache: {path}")
    order, edges, addressed, residual = build_repaired_edge_specs(
        snapshots=snapshots,
        paid_rows=paid_rows,
        precision_report=precision_report,
        repairs=repairs,
    )
    ranges = segment_edge_ranges(order, edges)
    paid = PaidWindow(paid_rows)

    with closing(sqlite3.connect(path)) as db:
        configure(db, writable=True)
        db.executescript("""
            CREATE TABLE metadata(payload TEXT NOT NULL);
            CREATE TABLE segments(segment INTEGER PRIMARY KEY,start INTEGER,end INTEGER,state_count INTEGER);
            CREATE TABLE states(segment INTEGER,ts INTEGER,book TEXT NOT NULL,top TEXT NOT NULL,
                                PRIMARY KEY(segment,ts)) WITHOUT ROWID;
            CREATE TABLE staging(ts INTEGER PRIMARY KEY,book TEXT NOT NULL);
        """)
        total_raw_writes = 0
        for segment_index, (start_pos, end_pos) in enumerate(ranges):
            progress(f"{ticker}: reconstructing repaired segment {segment_index + 1}/{len(ranges)}")
            db.execute("DELETE FROM staging")

            def stage_maps(timestamp_ms: int, bids, asks) -> None:
                nonlocal total_raw_writes
                state = _book_state_from_maps(timestamp_ms, bids, asks)
                db.execute("INSERT OR REPLACE INTO staging VALUES (?,?)",
                           (timestamp_ms, encode_book(state)))
                total_raw_writes += 1

            first_index = order[start_pos]
            first = snapshots[first_index]
            bids, asks = snapshot_book(first)
            stage_maps(int(first["timestamp"]), bids, asks)

            for edge_pos in range(start_pos, end_pos):
                edge = edges[edge_pos]
                require(edge["exact"], "segment contains failed edge")
                a = edge["original_start_snapshot_index"]
                b = edge["original_end_snapshot_index"]
                start = snapshots[a]
                end = snapshots[b]
                bids, asks = snapshot_book(start)
                stage_maps(int(start["timestamp"]), bids, asks)
                nearby = paid.between(int(start["timestamp"]), int(end["timestamp"]))
                selected = selected_rows_for_cuts(
                    start, end, nearby,
                    start_cut=int(edge["start_cut"]),
                    end_cut=int(edge["end_cut"]),
                )
                for row in selected:
                    apply_delta(bids, asks, row)
                    stage_maps(int(row["timestamp"]), bids, asks)
                expected_bids, expected_asks = snapshot_book(end)
                require(
                    mismatch_count(bids, expected_bids, epsilon=ZERO) == 0
                    and mismatch_count(asks, expected_asks, epsilon=ZERO) == 0,
                    "endpoint changed between edge planning and cache construction",
                )
                stage_maps(int(end["timestamp"]), expected_bids, expected_asks)

            previous_raw = None
            previous_ts = None
            count = 0
            for timestamp_ms, payload in db.execute("SELECT ts,book FROM staging ORDER BY ts"):
                if previous_ts is not None:
                    require(timestamp_ms > previous_ts, "staging timestamps not strictly increasing")
                previous_ts = timestamp_ms
                raw = decode_book(timestamp_ms, payload)
                if previous_raw is None or not _same_book(previous_raw, raw):
                    canonical = canonicalize_book_state(raw)
                    db.execute(
                        "INSERT INTO states VALUES (?,?,?,?)",
                        (segment_index, timestamp_ms, encode_book(canonical), top_key(canonical)),
                    )
                    previous_raw = raw
                    count += 1
            require(count > 0, "verified segment must contain at least one state")
            start_ts = int(snapshots[order[start_pos]]["timestamp"])
            end_ts = int(snapshots[order[end_pos]]["timestamp"])
            db.execute("INSERT INTO segments VALUES (?,?,?,?)",
                       (segment_index, start_ts, end_ts, count))
            db.commit()

        db.execute("DROP TABLE staging")
        segment_bounds = [
            [int(snapshots[order[a]]["timestamp"]), int(snapshots[order[b]]["timestamp"])]
            for a, b in ranges
        ]
        repaired_edges = [e for e in edges if e["repair_id"] is not None]
        audit = {
            "schema_version": AUDIT_SCHEMA,
            "ticker": ticker,
            "repair_plan_sha256": repair_plan_sha256,
            "original_snapshot_count": len(snapshots),
            "revised_snapshot_count": len(order),
            "quarantined_snapshot_indices": sorted(set(range(len(snapshots))) - set(order)),
            "repair_operation_ids": [r["repair_id"] for r in repairs],
            "repair_operation_count": len(repairs),
            "original_failed_pair_count": len(_failed_indices(precision_report)),
            "original_failed_pairs_addressed": sorted(addressed),
            "remaining_unreconciled_pair_count": len(residual),
            "remaining_unreconciled_pair_indices": sorted(residual),
            "revised_pair_count": len(edges),
            "repaired_adjacency_count": len(repaired_edges),
            "segment_count": len(ranges),
            "segment_bounds": segment_bounds,
            "revised_snapshot_order_sha256": hashlib.sha256(
                json.dumps(order, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "pinned_changed_adjacencies": repaired_edges,
            "safety": {
                "raw_snapshots_mutated": False,
                "paid_rows_mutated": False,
                "candidate_e_scored": False,
                "strategy_run": False,
                "outcomes_accessed": False,
                "strategy_pnl_calculated": False,
                "network_requests": 0,
                "orders_placed": 0,
            },
        }
        metadata = {
            "schema": DISK_SCHEMA,
            "ticker": ticker,
            "complete": True,
            "identity": identity,
            "replay_precision_audit_parent": precision_report,
            "repair_materialization_audit": audit,
        }
        db.execute("INSERT INTO metadata VALUES (?)", (json.dumps(metadata, sort_keys=True),))
        db.commit()
        progress(f"{ticker}: compacting repaired cache")
        db.execute("VACUUM")

    timeline = DiskTimeline(path)
    try:
        validate_repair_cache(timeline, expected_plan_sha256=repair_plan_sha256)
    finally:
        timeline.close()
    return audit


def validate_repair_cache(
    timeline: DiskTimeline,
    *,
    expected_plan_sha256: str = EXPECTED_PLAN_SHA256,
) -> dict[str, Any]:
    audit = timeline.metadata.get("repair_materialization_audit", {})
    require(audit.get("schema_version") == AUDIT_SCHEMA, "repair cache audit schema mismatch")
    require(audit.get("ticker") == timeline.ticker, "repair cache ticker mismatch")
    require(audit.get("repair_plan_sha256") == expected_plan_sha256, "repair plan binding mismatch")
    observed = [[s.start_timestamp_ms, s.end_timestamp_ms] for s in timeline.segments]
    require(audit.get("segment_bounds") == observed, "repair cache segment bounds mismatch")
    require(audit.get("segment_count") == len(timeline.segments), "repair cache segment count mismatch")
    safety = audit.get("safety", {})
    for key in (
        "raw_snapshots_mutated",
        "paid_rows_mutated",
        "candidate_e_scored",
        "strategy_run",
        "outcomes_accessed",
        "strategy_pnl_calculated",
    ):
        require(safety.get(key) is False, f"repair cache safety mismatch: {key}")
    for key in ("network_requests", "orders_placed"):
        require(type(safety.get(key)) is int and safety[key] == 0,
                f"repair cache safety mismatch: {key}")
    return audit
