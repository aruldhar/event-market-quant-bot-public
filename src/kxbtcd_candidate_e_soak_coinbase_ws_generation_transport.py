"""Checkpoint 21N-Z-F thin Coinbase WebSocket generation transport.

One invocation owns exactly ONE Coinbase WebSocket connection generation.

Primary path:
    WebSocket matches + heartbeat

Repair-only path:
    REST exact-minute seed or exact trade-gap recovery when the already-tested
    worker policy explicitly requests it.

Reconnect scheduling is NOT implemented here.  The outer soak orchestrator owns
the frozen 1,2,4,8,15-second reconnect lifecycle.

No authentication, Candidate-E signal, P&L, order, or write endpoint exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import threading
import time
from typing import Any, Callable

from .kxbtcd_candidate_e_coinbase_ws_transport import (
    COINBASE_WS_URL,
    subscription_command,
)
from .kxbtcd_candidate_e_soak_coinbase_rest_transport import (
    fetch_exact_seed_candle,
    fetch_trade_gap_recovery,
)
from .kxbtcd_candidate_e_soak_failure_policy import (
    is_local_fatal_exception,
)
from .kxbtcd_candidate_e_soak_coinbase_worker import (
    CoinbaseReadOnlyWorkerSession,
    CoinbaseWorkerAction,
)


class CoinbaseWsGenerationTransportError(
    RuntimeError
):
    pass


@dataclass
class CoinbaseCandleSeedRetryPolicy:
    """Bound transient unpublished-candle retries without reconnecting a healthy WS."""
    maximum_attempts_per_minute: int = 5
    minimum_interval_ns: int = 1_000_000_000
    target: tuple[int, int] | None = None
    attempts: int = 0
    last_attempt_ns: int | None = None

    def allow(self, action: CoinbaseWorkerAction, *, now_monotonic_ns: int) -> bool:
        if action.kind != "REST_CANDLE_SEED_REQUIRED":
            return True
        target = (action.target_minute_start_s, action.target_minute_end_s)
        if None in target:
            raise CoinbaseWsGenerationTransportError("candle seed action lacks exact target")
        if target != self.target:
            self.target, self.attempts, self.last_attempt_ns = target, 0, None
        if self.attempts >= self.maximum_attempts_per_minute:
            return False
        if self.last_attempt_ns is not None and now_monotonic_ns - self.last_attempt_ns < self.minimum_interval_ns:
            return False
        self.attempts += 1
        self.last_attempt_ns = now_monotonic_ns
        return True


@dataclass(frozen=True)
class CoinbaseGenerationRunResult:
    connection_generation: int
    received_frame_count: int
    final_action_kind: str
    intentional_stop: bool
    reconnect_decision: Any | None


def _default_connect():
    from websockets.sync.client import connect
    return connect


def _utc_now_text() -> str:
    from datetime import datetime, timezone

    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _safe_close_code(exc: BaseException) -> int | None:
    """Return an optional numeric transport close code without exception text."""
    code = getattr(exc, "code", None)
    if isinstance(code, bool) or not isinstance(code, int):
        return None
    if not 1000 <= code <= 4999:
        return None
    return code


def _handle_repair_action(
    *,
    action: CoinbaseWorkerAction,
    worker: CoinbaseReadOnlyWorkerSession,
    http_session,
    decision_epoch_s: int,
    now_monotonic_ns: int,
    monotonic_ns: Callable[[], int],
    utc_now_text: Callable[[], str],
    candle_seed_retry_policy: CoinbaseCandleSeedRetryPolicy | None = None,
) -> CoinbaseWorkerAction:
    if action.kind == "REST_CANDLE_SEED_REQUIRED":
        if candle_seed_retry_policy is not None and not candle_seed_retry_policy.allow(
            action, now_monotonic_ns=now_monotonic_ns
        ):
            return action
        if http_session is None:
            return action

        return fetch_exact_seed_candle(
            session=http_session,
            worker=worker,
            action=action,
            decision_epoch_s=(
                decision_epoch_s
            ),
            monotonic_ns=monotonic_ns,
            utc_now_text=utc_now_text,
        )

    if action.kind == "REST_GAP_RECOVERY_REQUIRED":
        if http_session is None:
            return action

        return fetch_trade_gap_recovery(
            session=http_session,
            worker=worker,
            action=action,
            decision_epoch_s=(
                decision_epoch_s
            ),
            now_monotonic_ns=(
                now_monotonic_ns
            ),
        )

    return action


def run_one_coinbase_generation(
    *,
    worker: CoinbaseReadOnlyWorkerSession,
    stop_event: threading.Event,
    decision_epoch_s: Callable[[], int],
    http_session=None,
    connect_fn=None,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    utc_now_text: Callable[[], str] = _utc_now_text,
    recv_timeout_seconds: float = 0.5,
    candle_seed_retry_policy: CoinbaseCandleSeedRetryPolicy | None = None,
) -> CoinbaseGenerationRunResult:
    """Run exactly one Coinbase WebSocket connection generation."""

    if recv_timeout_seconds <= 0:
        raise CoinbaseWsGenerationTransportError(
            "recv_timeout_seconds must be positive"
        )

    if connect_fn is None:
        connect_fn = _default_connect()

    binding = worker.start_generation(
        opened_monotonic_ns=(
            int(monotonic_ns())
        )
    )

    received = 0

    final_action = CoinbaseWorkerAction(
        kind="BLOCKED",
        reason="COINBASE_GENERATION_OPENED",
        connection_generation=(
            binding.generation
        ),
    )

    reconnect_decision = None
    intentional_stop = False
    if candle_seed_retry_policy is None:
        candle_seed_retry_policy = CoinbaseCandleSeedRetryPolicy()

    try:
        with connect_fn(
            COINBASE_WS_URL,
            open_timeout=10,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=5,
        ) as ws:
            command = subscription_command()

            # Coinbase is public/read-only.  The only outbound application
            # message is the channel subscription.
            ws.send(
                json.dumps(command)
            )

            while not stop_event.is_set():
                try:
                    raw = ws.recv(
                        timeout=recv_timeout_seconds
                    )
                except TimeoutError:
                    continue

                if not isinstance(raw, str):
                    raise (
                        CoinbaseWsGenerationTransportError(
                            "binary Coinbase frame not supported"
                        )
                    )

                recv_ns = int(
                    monotonic_ns()
                )

                # Worker -> core owns the raw-before-transform invariant.
                action = worker.ingest_ws_frame(
                    raw_text=raw,
                    received_monotonic_ns=recv_ns,
                    received_utc=(
                        utc_now_text()
                    ),
                    decision_epoch_s=int(
                        decision_epoch_s()
                    ),
                )

                received += 1

                final_action = (
                    _handle_repair_action(
                        action=action,
                        worker=worker,
                        http_session=(
                            http_session
                        ),
                        decision_epoch_s=int(
                            decision_epoch_s()
                        ),
                        now_monotonic_ns=(
                            recv_ns
                        ),
                        monotonic_ns=(
                            monotonic_ns
                        ),
                        utc_now_text=(
                            utc_now_text
                        ),
                        candle_seed_retry_policy=candle_seed_retry_policy,
                    )
                )

            intentional_stop = True

    except BaseException as exc:
        current = (
            worker.core.connections
            .current_coinbase
        )

        if (
            current is not None
            and current.connected
        ):
            local_fatal = (
                is_local_fatal_exception(
                    exc
                )
            )

            reconnect_decision = (
                worker.disconnect(
                    closed_monotonic_ns=int(
                        monotonic_ns()
                    ),
                    count_as_failure=(
                        not local_fatal
                    ),
                )
            )

            # Persist only a safe exception class and optional numeric close
            # code, never exception text or a transport object. This
            # distinguishes remote closes/timeouts from local parser failures
            # in the next read-only soak's evidence.
            observer = worker.core.observability
            if observer is not None:
                observer.record_source_event(
                    source="coinbase",
                    event="transport_error",
                    generation=current.generation,
                    monotonic_ns=int(monotonic_ns()),
                    failure_class=type(exc).__name__,
                    close_code=_safe_close_code(exc),
                )

        raise

    current = (
        worker.core.connections
        .current_coinbase
    )

    if (
        current is not None
        and current.connected
    ):
        worker.disconnect(
            closed_monotonic_ns=int(
                monotonic_ns()
            ),
            count_as_failure=False,
        )

    return CoinbaseGenerationRunResult(
        connection_generation=(
            binding.generation
        ),
        received_frame_count=received,
        final_action_kind=(
            final_action.kind
        ),
        intentional_stop=(
            intentional_stop
        ),
        reconnect_decision=(
            reconnect_decision
        ),
    )
