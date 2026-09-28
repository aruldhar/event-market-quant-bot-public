"""Offline reconstruction of one Kalshi book generation from closed raw data."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Iterator, Sequence

from .kxbtcd_candidate_e_prospective_live_collector import KalshiBookCache
from .kxbtcd_candidate_e_shadow_archive_reader import ArchivedRawRecord


class ShadowKalshiReplayError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReconstructedKalshiBook:
    market_ticker: str
    received_utc: str
    received_monotonic_ns: int
    book_state: object


def reconstruct_kalshi_generation(
    records: Iterable[ArchivedRawRecord], *, subscribed_tickers: Sequence[str]
) -> Iterator[ReconstructedKalshiBook]:
    """Rebuild a single complete subscription generation from archived frames.

    The caller supplies the exact event ladder selected at generation start.
    Sequence gaps, records from another source, malformed wrappers, and frames
    outside that ladder all stop replay rather than yielding partial books.
    """
    cache = KalshiBookCache(subscribed_tickers)
    for archived in records:
        if archived.source != "kalshi_production_ws":
            raise ShadowKalshiReplayError("replay accepts Kalshi WebSocket records only")
        wrapper = archived.record
        if wrapper.get("source") != "kalshi_production_ws":
            raise ShadowKalshiReplayError("raw wrapper source does not match descriptor")
        received_utc = wrapper.get("received_utc")
        received_monotonic_ns = wrapper.get("received_monotonic_ns")
        if not isinstance(received_utc, str) or not received_utc:
            raise ShadowKalshiReplayError("raw wrapper is missing receipt UTC")
        if (
            isinstance(received_monotonic_ns, bool)
            or not isinstance(received_monotonic_ns, int)
            or received_monotonic_ns < 0
        ):
            raise ShadowKalshiReplayError("raw wrapper has invalid receipt monotonic time")
        raw_text = wrapper.get("raw_text")
        if not isinstance(raw_text, str):
            raise ShadowKalshiReplayError("raw wrapper is missing text frame")
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ShadowKalshiReplayError("Kalshi frame is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ShadowKalshiReplayError("Kalshi frame root must be object")
        try:
            result = cache.apply_message(payload)
        except Exception as exc:
            raise ShadowKalshiReplayError("Kalshi archived frame is not replayable") from exc
        if result.get("gap"):
            raise ShadowKalshiReplayError("Kalshi sequence gap in archived generation")
        if result.get("type") not in {"orderbook_snapshot", "orderbook_delta"}:
            continue
        if not cache.all_ready():
            continue
        ticker = result["ticker"]
        yield ReconstructedKalshiBook(
            market_ticker=ticker,
            received_utc=received_utc,
            received_monotonic_ns=received_monotonic_ns,
            book_state=cache.books[ticker].to_book_state(
                cache.books[ticker].last_source_ts_ms
                if cache.books[ticker].last_source_ts_ms is not None
                else 0
            ),
        )
