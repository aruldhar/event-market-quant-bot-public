"""Recover exact completed Coinbase one-minute candles from closed raw data."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, Iterator, Mapping

from .kxbtcd_candidate_e_shadow_archive_reader import ArchivedRawRecord


class ShadowCoinbaseCandleReplayError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReconstructedCoinbaseCandle:
    minute_start_epoch_s: int
    close: Decimal
    received_utc: str
    received_monotonic_ns: int


def _parse_utc_second(value: object) -> int:
    if not isinstance(value, str) or not value:
        raise ShadowCoinbaseCandleReplayError("candle request lacks UTC boundary")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShadowCoinbaseCandleReplayError("candle request has invalid UTC boundary") from exc
    if parsed.tzinfo is None:
        raise ShadowCoinbaseCandleReplayError("candle request boundary must be UTC")
    return int(parsed.astimezone(timezone.utc).timestamp())


def _receipt(wrapper: Mapping[str, object]) -> tuple[str, int]:
    received_utc = wrapper.get("received_utc")
    received_ns = wrapper.get("received_monotonic_ns")
    if not isinstance(received_utc, str) or not received_utc:
        raise ShadowCoinbaseCandleReplayError("raw wrapper is missing receipt UTC")
    if isinstance(received_ns, bool) or not isinstance(received_ns, int) or received_ns < 0:
        raise ShadowCoinbaseCandleReplayError("raw wrapper has invalid receipt monotonic time")
    return received_utc, received_ns


def iter_exact_completed_candles(
    records: Iterable[ArchivedRawRecord],
) -> Iterator[ReconstructedCoinbaseCandle]:
    """Yield only exact, successfully persisted completed-minute candle closes.

    A temporary empty response and any malformed/mismatched request is rejected
    instead of becoming a stale or inferred price in an offline scenario.
    """
    for archived in records:
        if archived.source != "coinbase_exchange_rest":
            raise ShadowCoinbaseCandleReplayError("replay accepts Coinbase REST records only")
        wrapper = archived.record
        if wrapper.get("source") != "coinbase_exchange_rest":
            raise ShadowCoinbaseCandleReplayError("raw wrapper source does not match descriptor")
        received_utc, received_ns = _receipt(wrapper)
        request = wrapper.get("request_identity")
        if not isinstance(request, Mapping):
            raise ShadowCoinbaseCandleReplayError("raw wrapper lacks request identity")
        if request.get("method") != "GET" or request.get("status_code") != 200:
            raise ShadowCoinbaseCandleReplayError("candle response is not successful exact GET")
        params = request.get("params")
        if not isinstance(params, Mapping) or params.get("granularity") != 60:
            raise ShadowCoinbaseCandleReplayError("candle request is not one-minute granularity")
        start = _parse_utc_second(params.get("start"))
        end = _parse_utc_second(params.get("end"))
        if start % 60 != 0 or end != start + 60:
            raise ShadowCoinbaseCandleReplayError("candle request is not one exact completed minute")
        raw_text = wrapper.get("raw_text")
        if not isinstance(raw_text, str):
            raise ShadowCoinbaseCandleReplayError("raw wrapper is missing candle text")
        try:
            rows = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ShadowCoinbaseCandleReplayError("candle response is invalid JSON") from exc
        if not isinstance(rows, list):
            raise ShadowCoinbaseCandleReplayError("candle response root must be list")
        matching = [row for row in rows if isinstance(row, list) and len(row) == 6 and row[0] == start]
        if len(matching) != 1:
            raise ShadowCoinbaseCandleReplayError("candle response lacks one exact requested minute")
        try:
            close = Decimal(str(matching[0][4]))
        except InvalidOperation as exc:
            raise ShadowCoinbaseCandleReplayError("candle close is invalid") from exc
        if not close.is_finite() or close <= Decimal("0"):
            raise ShadowCoinbaseCandleReplayError("candle close must be positive finite")
        yield ReconstructedCoinbaseCandle(
            minute_start_epoch_s=start, close=close,
            received_utc=received_utc, received_monotonic_ns=received_ns,
        )
