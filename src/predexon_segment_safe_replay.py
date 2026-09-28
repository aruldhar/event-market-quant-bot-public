from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, MutableMapping, Sequence

EPSILON = Decimal("0.000000001")


@dataclass(frozen=True)
class ReplayPairResult:
    exact: bool
    total_mismatches: int
    bid_mismatches: int
    ask_mismatches: int
    start_cut: int
    end_cut: int
    start_batch_rows: int
    middle_rows: int
    end_batch_rows: int


@dataclass(frozen=True)
class ReplaySegment:
    start_snapshot_index: int
    end_snapshot_index: int
    start_timestamp: int
    end_timestamp: int
    snapshot_count: int
    pair_count: int
    exact_pair_count: int
    boundary_reason: str


def _d(value: object) -> Decimal:
    return Decimal(str(value))


def snapshot_book(snapshot: Mapping[str, object]) -> tuple[dict[Decimal, Decimal], dict[Decimal, Decimal]]:
    bids = {
        _d(level["price"]) / Decimal("100"): _d(level["size"])
        for level in snapshot["yes_bids"]  # type: ignore[index]
    }
    asks = {
        _d(level["price"]) / Decimal("100"): _d(level["size"])
        for level in snapshot["yes_asks"]  # type: ignore[index]
    }
    return bids, asks


def apply_delta(
    bids: MutableMapping[Decimal, Decimal],
    asks: MutableMapping[Decimal, Decimal],
    row: Mapping[str, object],
    *,
    epsilon: Decimal = EPSILON,
) -> None:
    """Apply one exact paid order-book delta.

    ``epsilon`` is retained only for backward-compatible call signatures. Paid
    ``price_dollars`` and ``delta_fp`` are exact fixed-point fields and are not
    repaired or rounded with epsilon. Numerical tolerance belongs only in
    snapshot-to-replay comparison.
    """
    del epsilon

    price = _d(row["price_dollars"])
    delta = _d(row["delta_fp"])
    side = str(row["side"])

    if side == "yes":
        book = bids
        level = price
    elif side == "no":
        book = asks
        level = Decimal("1") - price
    else:
        raise ValueError(f"unexpected side: {side}")

    old_size = book.get(level, Decimal("0"))
    new_size = old_size + delta
    if new_size < 0:
        raise ValueError(
            f"paid delta would create negative resting size at {level}: "
            f"{old_size} + {delta} = {new_size}"
        )
    if new_size == 0:
        book.pop(level, None)
    else:
        book[level] = new_size


def mismatch_count(
    actual: Mapping[Decimal, Decimal],
    expected: Mapping[Decimal, Decimal],
    *,
    epsilon: Decimal = EPSILON,
) -> int:
    return sum(
        abs(actual.get(price, Decimal("0")) - expected.get(price, Decimal("0"))) > epsilon
        for price in set(actual) | set(expected)
    )


def sequence_reset(previous_snapshot: Mapping[str, object], next_snapshot: Mapping[str, object]) -> bool:
    """Return whether the displayed snapshot sequence number decreased.

    This is diagnostic metadata only. Predexon ``live_early`` and ``websocket``
    snapshots can use non-comparable sequence domains, so a decrease must never
    create a hard replay boundary unless the actual book reconstruction also
    fails.
    """
    previous = previous_snapshot.get("sequence")
    current = next_snapshot.get("sequence")
    if previous is None or current is None:
        return False
    return int(current) < int(previous)


def reconcile_pair(
    start_snapshot: Mapping[str, object],
    end_snapshot: Mapping[str, object],
    rows: Sequence[Mapping[str, object]],
    *,
    epsilon: Decimal = EPSILON,
) -> ReplayPairResult:
    """Find the best legal boundary cuts for one adjacent snapshot pair.

    Snapshots have millisecond timestamps, so a snapshot may have been captured
    partway through a group of deltas sharing that timestamp. Search legal
    start/end cuts without reordering the paid deltas.
    """
    start_ts = int(start_snapshot["timestamp"])
    end_ts = int(end_snapshot["timestamp"])
    if end_ts < start_ts:
        raise ValueError("snapshot timestamps moved backward")

    ordered = sorted(rows, key=lambda r: (int(r["timestamp"]), int(r["sequence"])))

    start_bids, start_asks = snapshot_book(start_snapshot)
    end_bids, end_asks = snapshot_book(end_snapshot)

    if start_ts == end_ts:
        batch = [r for r in ordered if int(r["timestamp"]) == start_ts]
        best: tuple[int, int, int, int, int] | None = None
        for start_cut in range(len(batch) + 1):
            for end_cut in range(start_cut, len(batch) + 1):
                bids = dict(start_bids)
                asks = dict(start_asks)
                try:
                    for row in batch[start_cut:end_cut]:
                        apply_delta(bids, asks, row)
                except ValueError:
                    continue
                bid_mm = mismatch_count(bids, end_bids, epsilon=epsilon)
                ask_mm = mismatch_count(asks, end_asks, epsilon=epsilon)
                candidate = (bid_mm + ask_mm, bid_mm, ask_mm, start_cut, end_cut)
                if best is None or candidate < best:
                    best = candidate
        if best is None:
            return ReplayPairResult(False, -1, -1, -1, 0, 0, len(batch), 0, len(batch))
        return ReplayPairResult(
            exact=best[0] == 0,
            total_mismatches=best[0],
            bid_mismatches=best[1],
            ask_mismatches=best[2],
            start_cut=best[3],
            end_cut=best[4],
            start_batch_rows=len(batch),
            middle_rows=0,
            end_batch_rows=len(batch),
        )

    start_batch = [r for r in ordered if int(r["timestamp"]) == start_ts]
    middle = [r for r in ordered if start_ts < int(r["timestamp"]) < end_ts]
    end_batch = [r for r in ordered if int(r["timestamp"]) == end_ts]

    best2: tuple[int, int, int, int, int] | None = None
    for start_cut in range(len(start_batch) + 1):
        bids = dict(start_bids)
        asks = dict(start_asks)

        try:
            for row in start_batch[start_cut:]:
                apply_delta(bids, asks, row)
            for row in middle:
                apply_delta(bids, asks, row)
        except ValueError:
            continue

        end_bids_work = dict(bids)
        end_asks_work = dict(asks)

        for end_cut in range(len(end_batch) + 1):
            if end_cut:
                try:
                    apply_delta(
                        end_bids_work,
                        end_asks_work,
                        end_batch[end_cut - 1],
                    )
                except ValueError:
                    break
            bid_mm = mismatch_count(end_bids_work, end_bids, epsilon=epsilon)
            ask_mm = mismatch_count(end_asks_work, end_asks, epsilon=epsilon)
            candidate = (bid_mm + ask_mm, bid_mm, ask_mm, start_cut, end_cut)
            if best2 is None or candidate < best2:
                best2 = candidate

    if best2 is None:
        return ReplayPairResult(False, -1, -1, -1, 0, 0, len(start_batch), len(middle), len(end_batch))

    return ReplayPairResult(
        exact=best2[0] == 0,
        total_mismatches=best2[0],
        bid_mismatches=best2[1],
        ask_mismatches=best2[2],
        start_cut=best2[3],
        end_cut=best2[4],
        start_batch_rows=len(start_batch),
        middle_rows=len(middle),
        end_batch_rows=len(end_batch),
    )


def build_verified_segments(
    snapshots: Sequence[Mapping[str, object]],
    rows_by_pair: Sequence[Sequence[Mapping[str, object]]],
    *,
    epsilon: Decimal = EPSILON,
) -> tuple[list[ReplaySegment], list[ReplayPairResult]]:
    """Build fail-closed replay segments from actual book reconciliation.

    Every adjacent pair is tested. A displayed sequence decrease is diagnostic
    only. A segment ends only before an adjacent pair that cannot be exactly
    reconciled (or on a fatal exception such as backward timestamps). Book
    state is never carried across an unreconciled pair.
    """
    if len(rows_by_pair) != max(0, len(snapshots) - 1):
        raise ValueError("rows_by_pair must have exactly snapshot_count - 1 entries")
    if not snapshots:
        return [], []

    pair_results: list[ReplayPairResult] = []
    segments: list[ReplaySegment] = []
    seg_start = 0
    seg_exact_pairs = 0

    def close_segment(end_index: int, reason: str) -> None:
        nonlocal seg_start, seg_exact_pairs
        segments.append(
            ReplaySegment(
                start_snapshot_index=seg_start,
                end_snapshot_index=end_index,
                start_timestamp=int(snapshots[seg_start]["timestamp"]),
                end_timestamp=int(snapshots[end_index]["timestamp"]),
                snapshot_count=end_index - seg_start + 1,
                pair_count=max(0, end_index - seg_start),
                exact_pair_count=seg_exact_pairs,
                boundary_reason=reason,
            )
        )

    for i in range(len(snapshots) - 1):
        a = snapshots[i]
        b = snapshots[i + 1]

        result = reconcile_pair(a, b, rows_by_pair[i], epsilon=epsilon)
        pair_results.append(result)

        if not result.exact:
            close_segment(i, "unreconciled_adjacent_snapshot_pair")
            seg_start = i + 1
            seg_exact_pairs = 0
            continue

        seg_exact_pairs += 1

    close_segment(len(snapshots) - 1, "end_of_evidence")
    return segments, pair_results
