"""Independent raw-first Coinbase REST candle fetch for frozen V2 input."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import time
from typing import Any, Mapping

from .kxbtcd_candidate_e_coinbase_rest_trade_paginator import (
    COINBASE_EXCHANGE_BASE,
    COINBASE_PRODUCT,
)
from .kxbtcd_candidate_e_prospective_live_collector import (
    CoinbaseCompletedCandleUnavailable,
    completed_minute_target,
)
from .kxbtcd_candidate_e_soak_coinbase_rest_transport import (
    CANDLE_GRANULARITY_SECONDS,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    HttpSessionLike,
)


class V2RestCandleTransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class V2ExactCandleRequest:
    url: str
    params: Mapping[str, Any]
    target_minute_start_s: int
    target_minute_end_s: int


@dataclass
class V2RestCandlePollingPolicy:
    """Bound retries for one independently polled completed candle minute."""
    maximum_attempts_per_minute: int = 5
    minimum_interval_ns: int = 1_000_000_000
    target: tuple[int, int] | None = None
    attempts: int = 0
    successful_target: tuple[int, int] | None = None
    last_attempt_ns: int | None = None

    def allow(self, *, decision_epoch_s: int, now_monotonic_ns: int) -> bool:
        target = completed_minute_target(int(decision_epoch_s))
        if target != self.target:
            self.target = target
            self.attempts = 0
            self.successful_target = None
            self.last_attempt_ns = None
        if self.successful_target == target or self.attempts >= self.maximum_attempts_per_minute:
            return False
        if self.last_attempt_ns is not None and now_monotonic_ns - self.last_attempt_ns < self.minimum_interval_ns:
            return False
        self.attempts += 1
        self.last_attempt_ns = int(now_monotonic_ns)
        return True

    def record_success(self, *, decision_epoch_s: int) -> None:
        target = completed_minute_target(int(decision_epoch_s))
        if self.target != target:
            raise V2RestCandleTransportError("successful candle target was not attempted")
        self.successful_target = target


def _utc_text(epoch_s: int) -> str:
    return datetime.fromtimestamp(int(epoch_s), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def exact_v2_candle_request(*, decision_epoch_s: int) -> V2ExactCandleRequest:
    start, end = completed_minute_target(int(decision_epoch_s))
    return V2ExactCandleRequest(
        url=f"{COINBASE_EXCHANGE_BASE}/products/{COINBASE_PRODUCT}/candles",
        params={"granularity": CANDLE_GRANULARITY_SECONDS,
                "start": _utc_text(start), "end": _utc_text(end)},
        target_minute_start_s=start,
        target_minute_end_s=end,
    )


def fetch_v2_exact_completed_candle(*, session: HttpSessionLike, core,
                                    decision_epoch_s: int,
                                    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
                                    monotonic_ns=time.monotonic_ns,
                                    utc_now_text=None):
    """Fetch one frozen target minute independent of any WebSocket state.

    Returns the bound candle, or ``None`` when Coinbase has not published the
    just-closed minute yet. Network/HTTP/integrity failures still propagate.
    """
    if timeout_seconds <= 0:
        raise V2RestCandleTransportError("timeout_seconds must be positive")
    request = exact_v2_candle_request(decision_epoch_s=int(decision_epoch_s))
    if utc_now_text is None:
        utc_now_text = lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    started_ns = int(monotonic_ns())
    response = session.get(request.url, params=request.params, timeout=float(timeout_seconds))
    received_ns = int(monotonic_ns())
    received_utc = str(utc_now_text())
    core.record_rest_latency(started_ns=started_ns, ended_ns=received_ns)
    core.persist_v2_coinbase_rest_candle_response(
        raw_text=response.text, received_monotonic_ns=received_ns,
        received_utc=received_utc,
        request_identity={"method": "GET", "url": request.url,
                          "params": request.params,
                          "status_code": int(response.status_code),
                          "elapsed_monotonic_ns": received_ns - started_ns},
    )
    response.raise_for_status()
    try:
        return core.bind_persisted_v2_coinbase_rest_candle(
            raw_text=response.text, received_monotonic_ns=received_ns,
            received_utc=received_utc,
            target_minute_start_s=request.target_minute_start_s,
        )
    except CoinbaseCompletedCandleUnavailable:
        return None


def run_v2_rest_candle_polling_supervisor(*, stop_event: threading.Event,
                                           session: HttpSessionLike, core,
                                           epoch_seconds=time.time,
                                           monotonic_ns=time.monotonic_ns,
                                           sleep_seconds=time.sleep,
                                           utc_now_text=None,
                                           policy: V2RestCandlePollingPolicy | None = None,
                                           idle_sleep_seconds: float = 0.1) -> None:
    """Continuously refresh V2's REST input without any WebSocket dependency."""
    if idle_sleep_seconds <= 0:
        raise V2RestCandleTransportError("idle_sleep_seconds must be positive")
    if policy is None:
        policy = V2RestCandlePollingPolicy()
    while not stop_event.is_set():
        decision_s = int(epoch_seconds())
        now_ns = int(monotonic_ns())
        if policy.allow(decision_epoch_s=decision_s, now_monotonic_ns=now_ns):
            try:
                bound = fetch_v2_exact_completed_candle(
                    session=session, core=core, decision_epoch_s=decision_s,
                    monotonic_ns=monotonic_ns, utc_now_text=utc_now_text,
                )
            except Exception:
                # A transient HTTP transport failure leaves V2 blocked once
                # the current exact candle ages out. A core integrity failure
                # is deliberately not hidden by this polling loop.
                from .kxbtcd_candidate_e_soak_failure_policy import is_local_fatal_exception
                import sys
                if is_local_fatal_exception(sys.exception()):
                    raise
            else:
                if bound is not None:
                    policy.record_success(decision_epoch_s=decision_s)
        sleep_seconds(float(idle_sleep_seconds))
