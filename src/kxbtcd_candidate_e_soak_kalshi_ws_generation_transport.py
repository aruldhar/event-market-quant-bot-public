"""Checkpoint 21N-Z-F thin Kalshi WebSocket generation transport.

One invocation owns exactly ONE authenticated Kalshi WebSocket connection
generation for the already-selected current KXBTCD event ladder.

Responsibilities:
- reuse the existing production credential/signing boundary;
- validate the existing read-only orderbook_delta subscription command;
- use one application-owned Ping/Pong liveness proof;
- feed every text WS frame through the worker/core raw-first path;
- reconnect on real sequence-gap / stale-Pong source failures;
- return cleanly for planned event rollover;
- never convert local persistence/state failures into network backoff.

No signal, P&L, settlement, order, cancel, or production-write path exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import threading
import time
from typing import Callable, Mapping

from .kxbtcd_candidate_e_prospective_live_collector import (
    KALSHI_WS_URL,
    assert_read_only_ws_command,
    make_subscribe_command,
)
from .kxbtcd_candidate_e_soak_kalshi_credentials import (
    create_kalshi_ws_headers,
    kalshi_read_only_credentials,
)
from .kxbtcd_candidate_e_soak_failure_policy import (
    is_local_fatal_exception,
)
from .kxbtcd_candidate_e_soak_kalshi_worker import (
    KalshiReadOnlyWorkerSession,
    KalshiWorkerAction,
)


class KalshiWsGenerationTransportError(
    RuntimeError
):
    pass


# Keep the frozen maximum 20-second proof horizon with one application-owned
# Ping/Pong state machine.  The websockets library automatic keepalive is
# disabled because it otherwise runs a competing background control-frame
# thread whose timeout is not part of the worker's proven liveness state.
KALSHI_APPLICATION_PING_INTERVAL_SECONDS = 10
KALSHI_APPLICATION_PONG_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class KalshiGenerationRunResult:
    connection_generation: int
    received_frame_count: int
    manual_ping_attempts: int
    manual_pong_successes: int
    manual_pong_timeouts: int
    final_action_kind: str
    final_action_reason: str
    intentional_stop: bool
    reconnect_decision: object | None


def _default_connect():
    from websockets.sync.client import connect

    return connect


def _default_auth_headers(
    repo_root: Path,
) -> Mapping[str, str]:
    key_id, key_path = (
        kalshi_read_only_credentials(
            repo_root
        )
    )

    return create_kalshi_ws_headers(
        key_id,
        key_path,
    )


def _now_timestamp_ms() -> int:
    return int(
        time.time() * 1000
    )


def _utc_now_text() -> str:
    from datetime import datetime, timezone

    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _finish_terminal_action(
    *,
    worker: KalshiReadOnlyWorkerSession,
    action: KalshiWorkerAction,
    closed_monotonic_ns: int,
    received_frames: int,
    ping_attempts: int,
    pong_successes: int,
    pong_timeouts: int,
) -> KalshiGenerationRunResult:
    if action.kind not in {
        "RECONNECT_REQUIRED",
        "ROLLOVER_REQUIRED",
    }:
        raise KalshiWsGenerationTransportError(
            "terminal helper received nonterminal action"
        )

    count_as_failure = (
        action.kind == "RECONNECT_REQUIRED"
    )

    reconnect_decision = worker.disconnect(
        closed_monotonic_ns=(
            closed_monotonic_ns
        ),
        count_as_failure=(
            count_as_failure
        ),
        reconnect_reason=(action.reason if count_as_failure else None),
    )

    return KalshiGenerationRunResult(
        connection_generation=(
            action.connection_generation
        ),
        received_frame_count=(
            received_frames
        ),
        manual_ping_attempts=(
            ping_attempts
        ),
        manual_pong_successes=(
            pong_successes
        ),
        manual_pong_timeouts=(
            pong_timeouts
        ),
        final_action_kind=(
            action.kind
        ),
        final_action_reason=(
            action.reason
        ),
        intentional_stop=False,
        reconnect_decision=(
            reconnect_decision
        ),
    )


def run_one_kalshi_generation(
    *,
    worker: KalshiReadOnlyWorkerSession,
    stop_event: threading.Event,
    repo_root: str | Path = ".",
    connect_fn=None,
    auth_headers_factory=None,
    monotonic_ns: Callable[[], int] = (
        time.monotonic_ns
    ),
    now_timestamp_ms: Callable[[], int] = (
        _now_timestamp_ms
    ),
    utc_now_text: Callable[[], str] = (
        _utc_now_text
    ),
    observe_optional_instrumentation: Callable[[], None] | None = None,
    recv_timeout_seconds: float = 0.5,
) -> KalshiGenerationRunResult:
    """Run exactly one Kalshi connection generation."""

    if recv_timeout_seconds <= 0:
        raise KalshiWsGenerationTransportError(
            "recv_timeout_seconds must be positive"
        )

    event = worker.core.current_event

    if event is None:
        raise KalshiWsGenerationTransportError(
            "Kalshi WebSocket requires discovered current event"
        )

    tickers = tuple(
        market.market_ticker
        for market in event.markets
    )

    # Validate all locally generated application commands BEFORE opening a
    # source generation. A code/allowlist failure is not a network outage.
    command = make_subscribe_command(
        tickers
    )

    assert_read_only_ws_command(
        command
    )

    if auth_headers_factory is None:
        auth_headers_factory = (
            _default_auth_headers
        )

    # Credential/configuration failure occurs before generation opening and
    # therefore can never arm source reconnect backoff.
    headers = dict(
        auth_headers_factory(
            Path(repo_root)
        )
    )

    if connect_fn is None:
        connect_fn = _default_connect()

    binding = worker.start_generation(
        opened_monotonic_ns=int(
            monotonic_ns()
        )
    )

    received_frames = 0
    ping_attempts = 0
    pong_successes = 0
    pong_timeouts = 0

    final_action = worker.evaluate(
        now_timestamp_ms=int(
            now_timestamp_ms()
        ),
        now_monotonic_ns=int(
            monotonic_ns()
        ),
    )

    if final_action.kind in {
        "RECONNECT_REQUIRED",
        "ROLLOVER_REQUIRED",
    }:
        return _finish_terminal_action(
            worker=worker,
            action=final_action,
            closed_monotonic_ns=int(
                monotonic_ns()
            ),
            received_frames=(
                received_frames
            ),
            ping_attempts=ping_attempts,
            pong_successes=pong_successes,
            pong_timeouts=pong_timeouts,
        )

    try:
        with connect_fn(
            KALSHI_WS_URL,
            additional_headers=headers,
            open_timeout=10,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=5,
        ) as ws:
            ws.send(
                json.dumps(command)
            )

            pending_pong = None
            pending_ping_monotonic_ns = None
            next_ping_monotonic_ns = (
                binding.opened_monotonic_ns
                + int(KALSHI_APPLICATION_PING_INTERVAL_SECONDS * 1_000_000_000)
            )

            while not stop_event.is_set():
                loop_ns = int(
                    monotonic_ns()
                )

                # Optional dashboard evidence must never affect the source
                # generation. Its callback owns all failure isolation.
                if observe_optional_instrumentation is not None:
                    observe_optional_instrumentation()

                final_action = None
                if pending_pong is not None:
                    if pending_pong.is_set():
                        pong_successes += 1
                        final_action = worker.record_pong(
                            pong_monotonic_ns=loop_ns,
                            now_timestamp_ms=int(now_timestamp_ms()))
                        pending_pong = None
                        pending_ping_monotonic_ns = None
                        next_ping_monotonic_ns = (
                            loop_ns
                            + int(KALSHI_APPLICATION_PING_INTERVAL_SECONDS * 1_000_000_000)
                        )
                    elif (loop_ns - pending_ping_monotonic_ns
                          >= int(KALSHI_APPLICATION_PONG_TIMEOUT_SECONDS * 1_000_000_000)):
                        pong_timeouts += 1
                        final_action = worker.reconnect_for_unproven_pong()
                elif loop_ns >= next_ping_monotonic_ns:
                    pending_pong = ws.ping()
                    pending_ping_monotonic_ns = loop_ns
                    ping_attempts += 1
                    worker.core.record_kalshi_ping_sent(
                        ping_monotonic_ns=loop_ns)

                if (
                    final_action is not None
                    and final_action.kind in {
                        "RECONNECT_REQUIRED",
                        "ROLLOVER_REQUIRED",
                    }
                ):
                    return _finish_terminal_action(
                        worker=worker,
                        action=final_action,
                        closed_monotonic_ns=loop_ns,
                        received_frames=received_frames,
                        ping_attempts=ping_attempts,
                        pong_successes=pong_successes,
                        pong_timeouts=pong_timeouts,
                    )

                # Even with no market frames, event expiry and stale Pong
                # evidence must be able to terminate this generation.
                final_action = worker.evaluate(
                    now_timestamp_ms=int(
                        now_timestamp_ms()
                    ),
                    now_monotonic_ns=(
                        loop_ns
                    ),
                )

                if final_action.kind in {
                    "RECONNECT_REQUIRED",
                    "ROLLOVER_REQUIRED",
                }:
                    return _finish_terminal_action(
                        worker=worker,
                        action=final_action,
                        closed_monotonic_ns=(
                            loop_ns
                        ),
                        received_frames=(
                            received_frames
                        ),
                        ping_attempts=(
                            ping_attempts
                        ),
                        pong_successes=(
                            pong_successes
                        ),
                        pong_timeouts=(
                            pong_timeouts
                        ),
                    )

                try:
                    raw = ws.recv(
                        timeout=(
                            recv_timeout_seconds
                        )
                    )
                except TimeoutError:
                    continue

                if not isinstance(
                    raw,
                    str,
                ):
                    raise (
                        KalshiWsGenerationTransportError(
                            "binary Kalshi frame not supported"
                        )
                    )

                recv_ns = int(
                    monotonic_ns()
                )

                # Worker -> core owns RAW BEFORE PARSE/APPLY.
                final_action = (
                    worker.ingest_ws_frame(
                        raw_text=raw,
                        received_monotonic_ns=(
                            recv_ns
                        ),
                        received_utc=(
                            utc_now_text()
                        ),
                        now_timestamp_ms=int(
                            now_timestamp_ms()
                        ),
                    )
                )

                received_frames += 1

                if final_action.kind in {
                    "RECONNECT_REQUIRED",
                    "ROLLOVER_REQUIRED",
                }:
                    return (
                        _finish_terminal_action(
                            worker=worker,
                            action=final_action,
                            closed_monotonic_ns=(
                                recv_ns
                            ),
                            received_frames=(
                                received_frames
                            ),
                            ping_attempts=(
                                ping_attempts
                            ),
                            pong_successes=(
                                pong_successes
                            ),
                            pong_timeouts=(
                                pong_timeouts
                            ),
                        )
                    )

        # Global stop is a clean lifecycle boundary, never a source failure.
        current = (
            worker.core.connections
            .current_kalshi
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

        return KalshiGenerationRunResult(
            connection_generation=(
                binding.generation
            ),
            received_frame_count=(
                received_frames
            ),
            manual_ping_attempts=(
                ping_attempts
            ),
            manual_pong_successes=(
                pong_successes
            ),
            manual_pong_timeouts=(
                pong_timeouts
            ),
            final_action_kind=(
                final_action.kind
            ),
            final_action_reason=(
                final_action.reason
            ),
            intentional_stop=True,
            reconnect_decision=None,
        )

    except BaseException as exc:
        worker.core.record_kalshi_transport_error(
            failure_class=type(exc).__name__,
            observed_monotonic_ns=int(monotonic_ns()))
        current = (
            worker.core.connections
            .current_kalshi
        )

        if (
            current is not None
            and current.connected
        ):
            worker.disconnect(
                closed_monotonic_ns=int(
                    monotonic_ns()
                ),
                count_as_failure=(
                    not is_local_fatal_exception(
                        exc
                    )
                ),
            )

        raise
