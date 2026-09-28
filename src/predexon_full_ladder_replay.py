from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .predexon_segment_safe_replay import EPSILON, ReplayPairResult, ReplaySegment, build_verified_segments
from .predexon_subcent_backfill import decode_body, inspect_resume_file


class PredexonFullLadderReplayError(RuntimeError):
    pass


@dataclass(frozen=True)
class TickerReplaySummary:
    ticker: str
    event_ticker: str
    paid_delta_count: int
    snapshot_count: int
    pair_count: int
    exact_pair_count: int
    unreconciled_pair_count: int
    segment_count: int
    verified_gap_ms: int
    excluded_gap_ms: int
    snapshot_span_ms: int
    verified_time_fraction: float | None
    largest_excluded_gap_ms: int
    longest_verified_segment_ms: int


def load_backfill_snapshots(path: Path, *, ticker: str) -> list[dict[str, Any]]:
    state = inspect_resume_file(path, ticker=ticker)
    if not state.complete:
        raise PredexonFullLadderReplayError(f"{ticker}: snapshot backfill incomplete")
    snapshots: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise PredexonFullLadderReplayError(f"{path}:{line_number}: envelope must be object")
            body = decode_body(record.get("body"))
            for snapshot in body["snapshots"]:
                if not isinstance(snapshot, dict):
                    raise PredexonFullLadderReplayError(f"{ticker}: snapshot must be object")
                snapshots.append(dict(snapshot))
    if not snapshots:
        raise PredexonFullLadderReplayError(f"{ticker}: zero snapshots")
    snapshots.sort(key=lambda s: (int(s["timestamp"]), int(s["sequence"])))
    ids = [(int(s["timestamp"]), int(s["sequence"])) for s in snapshots]
    if len(ids) != len(set(ids)):
        raise PredexonFullLadderReplayError(f"{ticker}: duplicate timestamp/sequence snapshot")
    return snapshots


def rows_by_snapshot_pair(snapshots: Sequence[Mapping[str, Any]], paid_rows: Sequence[Mapping[str, Any]]) -> list[Sequence[Mapping[str, Any]]]:
    if len(snapshots) < 2:
        return []
    timestamps = [int(r["timestamp"]) for r in paid_rows]
    if timestamps != sorted(timestamps):
        raise PredexonFullLadderReplayError("paid rows must be chronological within ticker")
    out = []
    for a, b in zip(snapshots, snapshots[1:]):
        a_ts, b_ts = int(a["timestamp"]), int(b["timestamp"])
        if b_ts < a_ts:
            raise PredexonFullLadderReplayError("snapshot timestamps moved backward")
        out.append(paid_rows[bisect_left(timestamps, a_ts):bisect_right(timestamps, b_ts)])
    return out


def audit_ticker(*, ticker: str, snapshots: Sequence[Mapping[str, Any]], paid_rows: Sequence[Mapping[str, Any]]):
    if not paid_rows:
        raise PredexonFullLadderReplayError(f"{ticker}: zero paid deltas")
    ordered = sorted(paid_rows, key=lambda r: (int(r["timestamp"]), int(r["sequence"])))
    if list(paid_rows) != ordered:
        raise PredexonFullLadderReplayError(f"{ticker}: paid deltas not already ordered")
    rows_by_pair = rows_by_snapshot_pair(snapshots, paid_rows)
    segments, pair_results = build_verified_segments(snapshots, rows_by_pair, epsilon=EPSILON)
    gaps = [max(0, int(b["timestamp"]) - int(a["timestamp"])) for a, b in zip(snapshots, snapshots[1:])]
    exact = sum(r.exact for r in pair_results)
    failed = len(pair_results) - exact
    verified = sum(g for g, r in zip(gaps, pair_results) if r.exact)
    excluded = sum(g for g, r in zip(gaps, pair_results) if not r.exact)
    span = int(snapshots[-1]["timestamp"]) - int(snapshots[0]["timestamp"])
    summary = TickerReplaySummary(
        ticker=ticker,
        event_ticker=ticker.rsplit("-T", 1)[0],
        paid_delta_count=len(paid_rows),
        snapshot_count=len(snapshots),
        pair_count=len(pair_results),
        exact_pair_count=exact,
        unreconciled_pair_count=failed,
        segment_count=len(segments),
        verified_gap_ms=verified,
        excluded_gap_ms=excluded,
        snapshot_span_ms=span,
        verified_time_fraction=(verified / span if span > 0 else None),
        largest_excluded_gap_ms=max([g for g, r in zip(gaps, pair_results) if not r.exact], default=0),
        longest_verified_segment_ms=max([max(0, s.end_timestamp - s.start_timestamp) for s in segments], default=0),
    )
    return summary, segments, pair_results


def summary_to_dict(s: TickerReplaySummary) -> dict[str, Any]:
    return s.__dict__.copy()


def segment_to_dict(s: ReplaySegment) -> dict[str, Any]:
    return {
        "start_snapshot_index": s.start_snapshot_index,
        "end_snapshot_index": s.end_snapshot_index,
        "start_timestamp": s.start_timestamp,
        "end_timestamp": s.end_timestamp,
        "snapshot_count": s.snapshot_count,
        "pair_count": s.pair_count,
        "exact_pair_count": s.exact_pair_count,
        "boundary_reason": s.boundary_reason,
    }
