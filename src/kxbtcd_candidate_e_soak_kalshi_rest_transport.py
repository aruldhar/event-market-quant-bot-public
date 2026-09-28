"""Checkpoint 21N-Z-F Kalshi read-only REST discovery transport.

Responsibilities:
- request currently open KXBTCD markets;
- use the maximum frozen single-page request limit;
- persist the exact HTTP body BEFORE status handling or parsing;
- reject nonempty pagination cursors fail-closed;
- delegate deterministic current-event selection to the runtime core.

This module has no Kalshi write endpoint, order path, Candidate-E signal,
settlement access, or P&L behavior.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Callable, Mapping, Protocol

from .kxbtcd_candidate_e_prospective_live_collector import (
    KALSHI_REST_BASE,
    READ_ONLY_KALSHI_REST_PATH,
)
from .kxbtcd_candidate_e_soak_runtime_core import (
    EventDiscoveryResult,
    KALSHI_REST_SOURCE,
    SoakSourceRuntimeCore,
)


KALSHI_MARKETS_LIMIT = 1000
DEFAULT_HTTP_TIMEOUT_SECONDS = 15.0


class KalshiRestDiscoveryTransportError(
    RuntimeError
):
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


def _utc_now_text() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def discovery_request():
    """Return the frozen strategy-independent current KXBTCD query."""

    return (
        KALSHI_REST_BASE
        + READ_ONLY_KALSHI_REST_PATH,
        {
            "series_ticker": "KXBTCD",
            "status": "open",
            "limit": KALSHI_MARKETS_LIMIT,
        },
    )


def fetch_current_kxbtcd_event(
    *,
    session: HttpSessionLike,
    core: SoakSourceRuntimeCore,
    now_timestamp_ms: int,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    utc_now_text: Callable[[], str] = _utc_now_text,
) -> EventDiscoveryResult:
    """Fetch and bind one complete current-event discovery response."""

    if timeout_seconds <= 0:
        raise KalshiRestDiscoveryTransportError(
            "timeout_seconds must be positive"
        )

    url, params = discovery_request()

    start_ns = int(
        monotonic_ns()
    )

    response = session.get(
        url,
        params=params,
        timeout=float(
            timeout_seconds
        ),
    )

    recv_ns = int(
        monotonic_ns()
    )

    recv_utc = str(
        utc_now_text()
    )

    core.record_rest_latency(
        started_ns=start_ns,
        ended_ns=recv_ns,
    )

    # HARD REQUIREMENT:
    # persist exact body before HTTP status handling, JSON parsing,
    # pagination inspection, or event selection.
    core.manager(
        KALSHI_REST_SOURCE
    ).append(
        transport="https_rest",
        raw_text=response.text,
        received_monotonic_ns=recv_ns,
        received_utc=recv_utc,
        request_identity={
            "method": "GET",
            "url": url,
            "params": params,
            "status_code": int(
                response.status_code
            ),
            "elapsed_monotonic_ns": (
                recv_ns - start_ns
            ),
        },
    )

    # Only after raw persistence may transport status be interpreted.
    response.raise_for_status()

    # Core parsing includes the fail-closed nonempty-cursor guard.
    return core.bind_persisted_kalshi_discovery_response(
        raw_text=response.text,
        now_timestamp_ms=(
            now_timestamp_ms
        ),
    )


def fetch_kalshi_final_market_settlement(
    *, session: HttpSessionLike, core: SoakSourceRuntimeCore, market_ticker: str,
    timeout_seconds: float = 2.0, monotonic_ns: Callable[[], int] = time.monotonic_ns,
    utc_now_text: Callable[[], str] = _utc_now_text,
) -> bool:
    """Archive one public market response, then publish it only if finalized.

    This is optional dashboard instrumentation. Callers intentionally catch
    transport errors so a delayed public final-result endpoint can never alter
    source readiness or the evidence soak lifecycle.
    """
    if not isinstance(market_ticker, str) or not market_ticker or timeout_seconds <= 0:
        raise KalshiRestDiscoveryTransportError("final market settlement request is invalid")
    url = KALSHI_REST_BASE + "/markets/" + market_ticker
    start_ns = int(monotonic_ns())
    response = session.get(url, params={}, timeout=float(timeout_seconds))
    recv_ns = int(monotonic_ns())
    recv_utc = str(utc_now_text())
    core.record_rest_latency(started_ns=start_ns, ended_ns=recv_ns)
    core.manager(KALSHI_REST_SOURCE).append(
        transport="https_rest", raw_text=response.text,
        received_monotonic_ns=recv_ns, received_utc=recv_utc,
        request_identity={
            "method": "GET", "url": url, "params": {},
            "status_code": int(response.status_code),
            "elapsed_monotonic_ns": recv_ns - start_ns,
        },
    )
    response.raise_for_status()
    return core.bind_persisted_kalshi_market_settlement_response(
        raw_text=response.text, market_ticker=market_ticker, received_utc=recv_utc,
    )
