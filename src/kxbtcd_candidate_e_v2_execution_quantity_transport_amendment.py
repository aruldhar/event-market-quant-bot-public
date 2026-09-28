"""Checkpoint 21N-Y-A1 execution-quantity transport amendment.

The verified replay remains untouched.  This adapter canonicalizes only the
quantity representation presented to V2 decision/execution code.

Rule:
* nearest 0.01 quantity is accepted only when absolute residue <= 1e-9;
* accepted values are replaced by that exact 0.01-grid Decimal;
* materially off-grid values fail closed.

No prices, timestamps, segment boundaries, source availability, or strategy
economics are changed.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    BookLevel,
    BookState,
    VerifiedSegmentTimeline,
    VerifiedTickerTimeline,
)

QUANTITY_QUANTUM = Decimal("0.01")
MAX_TRANSPORT_RESIDUE = Decimal("0.000000001")
ZERO = Decimal("0")


class V2QuantityTransportAmendmentError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise V2QuantityTransportAmendmentError(message)


def canonicalize_execution_quantity(value: Decimal) -> Decimal:
    """Return exact 0.01-grid quantity when residue is demonstrably transport noise."""
    quantity = Decimal(str(value))
    if not quantity.is_finite():
        _fail("book quantity must be finite")
    if quantity < ZERO:
        _fail("book quantity must be nonnegative")

    nearest = (
        quantity / QUANTITY_QUANTUM
    ).to_integral_value(rounding=ROUND_HALF_UP) * QUANTITY_QUANTUM

    residue = abs(quantity - nearest)
    if residue > MAX_TRANSPORT_RESIDUE:
        _fail(
            f"book quantity {quantity} is {residue} away from 0.01 grid; "
            f"maximum transport residue is {MAX_TRANSPORT_RESIDUE}"
        )
    return nearest


def canonicalize_book_state(state: BookState) -> BookState:
    def levels(values: Iterable[BookLevel]) -> tuple[BookLevel, ...]:
        return tuple(
            BookLevel(
                price=level.price,
                quantity=canonicalize_execution_quantity(level.quantity),
            )
            for level in values
        )

    return BookState(
        timestamp_ms=state.timestamp_ms,
        yes_bids=levels(state.yes_bids),
        yes_asks=levels(state.yes_asks),
    )


def canonicalize_verified_ticker_timeline(
    timeline: VerifiedTickerTimeline,
) -> VerifiedTickerTimeline:
    """Preserve verified segmentation/timestamps while normalizing execution quantities."""
    segments = []
    for segment in timeline.segments:
        states = tuple(canonicalize_book_state(state) for state in segment.states)

        # Canonicalization may reveal duplicate economic states at adjacent
        # timestamps.  Keep timestamps/states exactly as verified here; the
        # existing decision clock independently suppresses unchanged top-level
        # signatures and state_changes suppresses unchanged full books.
        segments.append(
            VerifiedSegmentTimeline(
                segment_index=segment.segment_index,
                start_timestamp_ms=segment.start_timestamp_ms,
                end_timestamp_ms=segment.end_timestamp_ms,
                states=states,
            )
        )

    return VerifiedTickerTimeline(
        ticker=timeline.ticker,
        segments=tuple(segments),
    )


def canonicalize_timeline_map(
    timelines: dict[str, VerifiedTickerTimeline],
) -> dict[str, VerifiedTickerTimeline]:
    return {
        ticker: canonicalize_verified_ticker_timeline(timeline)
        for ticker, timeline in timelines.items()
    }
