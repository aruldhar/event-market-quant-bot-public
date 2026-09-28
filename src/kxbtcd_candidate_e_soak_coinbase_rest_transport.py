"""Checkpoint 21N-Z-F Coinbase read-only REST transport adapter.

Network-capable only when a caller supplies a real HTTP session.

Responsibilities:
- exact required completed-minute Coinbase candle request;
- raw response persistence BEFORE HTTP status handling or parsing;
- reuse existing REST trade-gap paginator unchanged.

No authentication, Candidate-E signal, P&L, order, or write endpoint exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any, Mapping, Protocol

from .kxbtcd_candidate_e_coinbase_rest_trade_paginator import (
    COINBASE_EXCHANGE_BASE,
    COINBASE_PRODUCT,
    fetch_recovery_pages,
)
from .kxbtcd_candidate_e_soak_coinbase_worker import (
    CoinbaseReadOnlyWorkerSession,
    CoinbaseWorkerAction,
)
from .kxbtcd_candidate_e_soak_runtime_core import (
    COINBASE_REST_SOURCE,
)
from .kxbtcd_candidate_e_prospective_live_collector import (
    CoinbaseCompletedCandleUnavailable,
)


CANDLE_GRANULARITY_SECONDS = 60
DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0


class CoinbaseRestTransportError(RuntimeError):
    pass


class HttpResponseLike(Protocol):
    status_code: int
    text: str

    def raise_for_status(self) -> None:
        ...


class HttpSessionLike(Protocol):
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any],
        timeout: float,
    ) -> HttpResponseLike:
        ...


@dataclass(frozen=True)
class ExactCandleRequest:
    url: str
    params: Mapping[str, Any]
    target_minute_start_s: int
    target_minute_end_s: int


def _iso_epoch_second(epoch_s: int) -> str:
    return (
        datetime.fromtimestamp(
            int(epoch_s),
            tz=timezone.utc,
        )
        .isoformat()
        .replace("+00:00", "Z")
    )


def exact_candle_request(
    action: CoinbaseWorkerAction,
) -> ExactCandleRequest:
    if action.kind != "REST_CANDLE_SEED_REQUIRED":
        raise CoinbaseRestTransportError(
            "exact candle request requires REST_CANDLE_SEED_REQUIRED action"
        )

    start = action.target_minute_start_s
    end = action.target_minute_end_s

    if (
        start is None
        or end is None
        or start % 60 != 0
        or end != start + 60
    ):
        raise CoinbaseRestTransportError(
            "worker action lacks exact aligned completed minute"
        )

    url = (
        f"{COINBASE_EXCHANGE_BASE}/products/"
        f"{COINBASE_PRODUCT}/candles"
    )

    # Explicit start/end are used even though Coinbase may return nearby
    # buckets. The core parser must still select exactly target_start.
    params = {
        "granularity": CANDLE_GRANULARITY_SECONDS,
        "start": _iso_epoch_second(start),
        "end": _iso_epoch_second(end),
    }

    return ExactCandleRequest(
        url=url,
        params=params,
        target_minute_start_s=start,
        target_minute_end_s=end,
    )


def fetch_exact_seed_candle(
    *,
    session: HttpSessionLike,
    worker: CoinbaseReadOnlyWorkerSession,
    action: CoinbaseWorkerAction,
    decision_epoch_s: int,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    monotonic_ns=time.monotonic_ns,
    utc_now_text=None,
) -> CoinbaseWorkerAction:
    """Fetch one exact completed-minute candle, raw-first."""

    if timeout_seconds <= 0:
        raise CoinbaseRestTransportError(
            "timeout_seconds must be positive"
        )

    request = exact_candle_request(
        action
    )

    if utc_now_text is None:
        utc_now_text = lambda: (
            datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    start_ns = int(monotonic_ns())

    response = session.get(
        request.url,
        params=request.params,
        timeout=float(timeout_seconds),
    )

    recv_ns = int(monotonic_ns())
    recv_utc = str(utc_now_text())
    worker.core.record_rest_latency(
        started_ns=start_ns,
        ended_ns=recv_ns,
    )

    # HARD REQUIREMENT: exact body is flushed before status handling.
    worker.core.manager(
        COINBASE_REST_SOURCE
    ).append(
        transport="https_rest",
        raw_text=response.text,
        received_monotonic_ns=recv_ns,
        received_utc=recv_utc,
        request_identity={
            "method": "GET",
            "url": request.url,
            "params": request.params,
            "status_code": int(
                response.status_code
            ),
            "elapsed_monotonic_ns": (
                recv_ns - start_ns
            ),
        },
    )

    # Only now may HTTP status or JSON/candle interpretation occur.
    response.raise_for_status()

    try:
        return worker.apply_persisted_rest_candle_seed(
            raw_text=response.text,
            received_monotonic_ns=recv_ns,
            received_utc=recv_utc,
            decision_epoch_s=(
                decision_epoch_s
            ),
        )
    except CoinbaseCompletedCandleUnavailable as exc:
        # Coinbase may publish a just-closed bucket after the first read. The
        # response is durable, but this is not a WebSocket failure.  Preserve
        # the current healthy generation and retry from a later heartbeat
        # rather than needlessly reconnecting the source.
        return action


def fetch_trade_gap_recovery(
    *,
    session: HttpSessionLike,
    worker: CoinbaseReadOnlyWorkerSession,
    action: CoinbaseWorkerAction,
    decision_epoch_s: int,
    now_monotonic_ns: int,
    max_pages: int = 10,
    max_latest_attempts: int = 10,
    latest_retry_sleep_seconds: float = 0.5,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> CoinbaseWorkerAction:
    """Execute an already-frozen exact trade-ID recovery interval."""

    if action.kind != "REST_GAP_RECOVERY_REQUIRED":
        raise CoinbaseRestTransportError(
            "trade recovery requires REST_GAP_RECOVERY_REQUIRED action"
        )

    start = action.recovery_from_trade_id
    target = action.recovery_target_trade_id

    if (
        start is None
        or target is None
        or target <= start
    ):
        raise CoinbaseRestTransportError(
            "worker action lacks valid recovery interval"
        )

    fetched = fetch_recovery_pages(
        session=session,
        journal=worker.core.journal(
            COINBASE_REST_SOURCE
        ),
        start_exclusive_trade_id=start,
        target_inclusive_trade_id=target,
        max_pages=max_pages,
        max_latest_attempts=(
            max_latest_attempts
        ),
        latest_retry_sleep_seconds=(
            latest_retry_sleep_seconds
        ),
        timeout_seconds=timeout_seconds,
    )

    return worker.apply_rest_gap_recovery(
        evidence=fetched.evidence,
        decision_epoch_s=(
            decision_epoch_s
        ),
        now_monotonic_ns=(
            now_monotonic_ns
        ),
    )
