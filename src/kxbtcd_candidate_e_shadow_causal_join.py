"""Causally join reconstructed Coinbase candles to Kalshi book observations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Iterator, Sequence

from .kxbtcd_candidate_e_shadow_coinbase_candle_replay import (
    ReconstructedCoinbaseCandle,
)
from .kxbtcd_candidate_e_shadow_kalshi_replay import ReconstructedKalshiBook


class ShadowCausalJoinError(RuntimeError):
    pass


@dataclass(frozen=True)
class CausalShadowBookPoint:
    book: ReconstructedKalshiBook
    completed_candle: ReconstructedCoinbaseCandle


def _utc_epoch_s(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShadowCausalJoinError("archive receipt UTC is invalid") from exc
    if parsed.tzinfo is None:
        raise ShadowCausalJoinError("archive receipt UTC lacks timezone")
    return int(parsed.astimezone(timezone.utc).timestamp())


def iter_causal_book_points(
    candles: Sequence[ReconstructedCoinbaseCandle],
    books: Iterable[ReconstructedKalshiBook],
) -> Iterator[CausalShadowBookPoint]:
    """Join each book to the newest previously received completed candle.

    Inputs must be receipt-monotonic.  A candle becomes eligible only after its
    own one-minute interval ended and it was received before the book frame.
    Missing causal state is skipped, never backfilled from a future response.
    """
    previous_candle_receipt_ns = -1
    for candle in candles:
        if candle.received_monotonic_ns < previous_candle_receipt_ns:
            raise ShadowCausalJoinError("Coinbase candles are not receipt ordered")
        previous_candle_receipt_ns = candle.received_monotonic_ns

    index = 0
    available: ReconstructedCoinbaseCandle | None = None
    previous_book_receipt_ns = -1
    for book in books:
        if book.received_monotonic_ns < previous_book_receipt_ns:
            raise ShadowCausalJoinError("Kalshi books are not receipt ordered")
        previous_book_receipt_ns = book.received_monotonic_ns
        book_epoch_s = _utc_epoch_s(book.received_utc)
        while (
            index < len(candles)
            and candles[index].received_monotonic_ns <= book.received_monotonic_ns
        ):
            candidate = candles[index]
            index += 1
            if candidate.minute_start_epoch_s + 60 <= book_epoch_s:
                available = candidate
        if available is not None:
            yield CausalShadowBookPoint(book=book, completed_candle=available)
