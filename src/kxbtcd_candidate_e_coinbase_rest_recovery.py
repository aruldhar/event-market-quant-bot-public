"""Coinbase REST trade-recovery evidence contract.

This module performs no network access.

A production paginator supplies consecutive REST trade pages starting from the
latest page and proceeding toward older history using Coinbase's `after` cursor.

Recovery coverage is proven only when the collected pages contain BOTH:

1. the exact pre-gap trade ID already known locally; and
2. the exact heartbeat/recovery target trade ID.

We deliberately do NOT assume that every integer trade_id must exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class CoinbaseRestRecoveryError(RuntimeError):
    pass


def _trade_id(row: Mapping[str, Any]) -> int:
    value = row.get("trade_id")

    if isinstance(value, bool) or not isinstance(value, int):
        raise CoinbaseRestRecoveryError(
            "REST trade_id must be integer"
        )

    if value < 0:
        raise CoinbaseRestRecoveryError(
            "REST trade_id must be nonnegative"
        )

    return value


@dataclass(frozen=True)
class CoinbaseRestRecoveryEvidence:
    start_exclusive_trade_id: int
    target_inclusive_trade_id: int
    page_count: int
    raw_row_count: int
    boundary_trade_seen: bool
    target_trade_seen: bool
    coverage_proven: bool
    interval_rows: tuple[Mapping[str, Any], ...]


def build_recovery_evidence(
    *,
    pages: Sequence[Sequence[Mapping[str, Any]]],
    start_exclusive_trade_id: int,
    target_inclusive_trade_id: int,
) -> CoinbaseRestRecoveryEvidence:
    start = int(start_exclusive_trade_id)
    target = int(target_inclusive_trade_id)

    if start < 0 or target < 0:
        raise CoinbaseRestRecoveryError(
            "recovery trade IDs must be nonnegative"
        )

    if target <= start:
        raise CoinbaseRestRecoveryError(
            "recovery target must be above start boundary"
        )

    seen: dict[int, Mapping[str, Any]] = {}
    raw_row_count = 0

    for page_index, page in enumerate(pages):
        if not isinstance(page, Sequence):
            raise CoinbaseRestRecoveryError(
                f"page {page_index} must be a sequence"
            )

        for row_index, row in enumerate(page):
            if not isinstance(row, Mapping):
                raise CoinbaseRestRecoveryError(
                    f"page {page_index} row {row_index} "
                    "must be an object"
                )

            raw_row_count += 1
            tid = _trade_id(row)

            prior = seen.get(tid)

            if prior is not None:
                # Pagination overlap is acceptable only when the repeated
                # trade is identical. Conflicting evidence fails closed.
                if dict(prior) != dict(row):
                    raise CoinbaseRestRecoveryError(
                        f"conflicting REST evidence for trade_id {tid}"
                    )
                continue

            seen[tid] = dict(row)

    boundary_seen = start in seen
    target_seen = target in seen

    # Exact boundary + exact target prove the requested interval is bracketed
    # by the consecutive cursor pages supplied by the paginator.
    coverage_proven = boundary_seen and target_seen

    interval = tuple(
        seen[tid]
        for tid in sorted(seen)
        if start < tid <= target
    )

    return CoinbaseRestRecoveryEvidence(
        start_exclusive_trade_id=start,
        target_inclusive_trade_id=target,
        page_count=len(pages),
        raw_row_count=raw_row_count,
        boundary_trade_seen=boundary_seen,
        target_trade_seen=target_seen,
        coverage_proven=coverage_proven,
        interval_rows=interval,
    )
