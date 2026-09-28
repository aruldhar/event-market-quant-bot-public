"""Checkpoint 21N-Z-F offline-testable combined soak runner shell.

This layer coordinates already-tested components. It does not itself implement
Coinbase, Kalshi, clock, Docker, credentials, model logic, or execution.

Responsibilities:
- start one Coinbase supervisor thread;
- start one Kalshi supervisor thread;
- evaluate infrastructure readiness at <=5-second intervals;
- feed readiness into the frozen soak run controller;
- preserve the 300-second initial-readiness timeout;
- preserve the non-pausing active timer;
- stop both source supervisors on terminal run state;
- hard-fail if either source supervisor exits unexpectedly;
- hard-fail if a source supervisor raises;
- require both source threads to stop cleanly after the stop signal.

This shell is NOT yet the production CLI runner. A later layer must write the
run manifest before live sources start, bind real clock/identity adapters,
instantiate concrete source transports, and package the runtime in Docker.

No signal, P&L, settlement, order, cancel, or production-write path exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

from .kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from .kxbtcd_candidate_e_soak_readiness import (
    SoakReadinessResult,
)
from .kxbtcd_candidate_e_soak_run_control import (
    SoakRunControlSnapshot,
    SoakRunController,
)


MAX_READINESS_EVALUATION_INTERVAL_SECONDS = 5.0
DEFAULT_READINESS_EVALUATION_INTERVAL_SECONDS = 1.0
# A source can be in the frozen five-second manual Pong wait when shutdown is
# requested, then needs up to the WebSocket five-second close handshake. Keep
# a bounded margin for scheduling rather than terminalizing while that source
# still owns raw-evidence files.
DEFAULT_SOURCE_JOIN_TIMEOUT_SECONDS = 12.0


class SoakRunnerShellError(RuntimeError):
    pass


@dataclass(frozen=True)
class SoakRunnerShellResult:
    run: SoakRunControlSnapshot
    final_readiness_state: str
    final_readiness_reason: str
    coinbase_thread_started: bool
    kalshi_thread_started: bool
    coinbase_thread_stopped: bool
    kalshi_thread_stopped: bool
    source_failure: str | None


@dataclass
class _WorkerState:
    name: str
    started: bool = False
    returned: bool = False
    exception: BaseException | None = None


def _fatal_readiness(
    *,
    reason: str,
    expected_boot_id: str,
) -> SoakReadinessResult:
    """Create runner-originated fatal evidence for the run controller."""

    return SoakReadinessResult(
        state="FATAL",
        status=GateStatus.FATAL,
        reason=str(reason),
        ready_read_only=False,
        expected_boot_id=str(
            expected_boot_id
        ),
        current_boot_id=None,
        current_time_namespace_id=None,
        identity_reason="RUNNER_FATAL",
        clock_reason="RUNNER_FATAL",
        coinbase_reason="RUNNER_FATAL",
        kalshi_reason="RUNNER_FATAL",
    )


def _validate_positive_seconds(
    value: float,
    name: str,
) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise SoakRunnerShellError(
            f"{name} must be numeric"
        ) from exc

    if result <= 0:
        raise SoakRunnerShellError(
            f"{name} must be positive"
        )

    return result


def run_soak_runner_shell(
    *,
    expected_boot_id: str,
    requested_active_duration_seconds: int,
    run_coinbase_supervisor: Callable[
        [threading.Event],
        object,
    ],
    run_kalshi_supervisor: Callable[
        [threading.Event],
        object,
    ],
    sample_readiness: Callable[
        [int],
        SoakReadinessResult,
    ],
    started_monotonic_ns: int | None = None,
    readiness_evaluation_interval_seconds: float = (
        DEFAULT_READINESS_EVALUATION_INTERVAL_SECONDS
    ),
    source_join_timeout_seconds: float = (
        DEFAULT_SOURCE_JOIN_TIMEOUT_SECONDS
    ),
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    sleep_seconds: Callable[[float], None] = time.sleep,
    before_source_start: Callable[[], object] | None = None,
    observe_snapshot: Callable[[SoakReadinessResult, SoakRunControlSnapshot], None] | None = None,
) -> SoakRunnerShellResult:
    """Coordinate source-supervisor threads and infrastructure readiness."""

    expected_boot = str(
        expected_boot_id
    ).strip()

    if not expected_boot:
        raise SoakRunnerShellError(
            "expected_boot_id must be non-empty"
        )

    interval = _validate_positive_seconds(
        readiness_evaluation_interval_seconds,
        "readiness_evaluation_interval_seconds",
    )

    if interval > MAX_READINESS_EVALUATION_INTERVAL_SECONDS:
        raise SoakRunnerShellError(
            "readiness evaluation interval exceeds frozen 5-second maximum"
        )

    join_timeout = _validate_positive_seconds(
        source_join_timeout_seconds,
        "source_join_timeout_seconds",
    )

    if started_monotonic_ns is None:
        start_ns = int(
            monotonic_ns()
        )
    else:
        if (
            isinstance(started_monotonic_ns, bool)
            or not isinstance(started_monotonic_ns, int)
            or started_monotonic_ns < 0
        ):
            raise SoakRunnerShellError(
                "started_monotonic_ns must be a nonnegative integer"
            )

        start_ns = int(
            started_monotonic_ns
        )

    run_control = SoakRunController(
        started_monotonic_ns=start_ns,
        requested_active_duration_seconds=(
            requested_active_duration_seconds
        ),
    )

    stop_event = threading.Event()
    lock = threading.Lock()

    coinbase_state = _WorkerState(
        name="coinbase"
    )

    kalshi_state = _WorkerState(
        name="kalshi"
    )

    def worker_wrapper(
        state: _WorkerState,
        target: Callable[
            [threading.Event],
            object,
        ],
    ) -> None:
        with lock:
            state.started = True

        try:
            target(
                stop_event
            )
        except BaseException as exc:
            with lock:
                state.exception = exc
        finally:
            with lock:
                state.returned = True

    coinbase_thread = threading.Thread(
        target=worker_wrapper,
        args=(
            coinbase_state,
            run_coinbase_supervisor,
        ),
        name="candidate-e-soak-coinbase",
        daemon=False,
    )

    kalshi_thread = threading.Thread(
        target=worker_wrapper,
        args=(
            kalshi_state,
            run_kalshi_supervisor,
        ),
        name="candidate-e-soak-kalshi",
        daemon=False,
    )

    # Frozen B5-R5-B ordering boundary:
    #
    # Any required durable pre-live evidence, especially the RUNNING soak
    # manifest, must be created and validated before either source thread is
    # allowed to execute. If this hook raises, Thread.start() is never reached.
    if before_source_start is not None:
        try:
            before_source_start()
        except Exception as exc:
            raise SoakRunnerShellError(
                "before_source_start failed before source threads started: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    coinbase_thread.start()
    kalshi_thread.start()

    final_readiness = _fatal_readiness(
        reason="READINESS_NOT_EVALUATED",
        expected_boot_id=expected_boot,
    )

    source_failure: str | None = None

    try:
        while True:
            now_ns = int(
                monotonic_ns()
            )

            with lock:
                cb_exception = (
                    coinbase_state.exception
                )
                ka_exception = (
                    kalshi_state.exception
                )
                cb_returned = (
                    coinbase_state.returned
                )
                ka_returned = (
                    kalshi_state.returned
                )

            if cb_exception is not None:
                source_failure = (
                    "COINBASE_SUPERVISOR_EXCEPTION:"
                    + type(cb_exception).__name__
                )

                final_readiness = _fatal_readiness(
                    reason=source_failure,
                    expected_boot_id=expected_boot,
                )

            elif ka_exception is not None:
                source_failure = (
                    "KALSHI_SUPERVISOR_EXCEPTION:"
                    + type(ka_exception).__name__
                )

                final_readiness = _fatal_readiness(
                    reason=source_failure,
                    expected_boot_id=expected_boot,
                )

            elif (
                cb_returned
                and not stop_event.is_set()
            ):
                source_failure = (
                    "COINBASE_SUPERVISOR_EXITED_UNEXPECTEDLY"
                )

                final_readiness = _fatal_readiness(
                    reason=source_failure,
                    expected_boot_id=expected_boot,
                )

            elif (
                ka_returned
                and not stop_event.is_set()
            ):
                source_failure = (
                    "KALSHI_SUPERVISOR_EXITED_UNEXPECTEDLY"
                )

                final_readiness = _fatal_readiness(
                    reason=source_failure,
                    expected_boot_id=expected_boot,
                )

            else:
                try:
                    final_readiness = (
                        sample_readiness(
                            now_ns
                        )
                    )
                except BaseException as exc:
                    source_failure = (
                        "READINESS_SAMPLER_EXCEPTION:"
                        + type(exc).__name__
                    )

                    final_readiness = (
                        _fatal_readiness(
                            reason=source_failure,
                            expected_boot_id=(
                                expected_boot
                            ),
                        )
                    )

            snapshot = run_control.observe(
                evaluated_monotonic_ns=(
                    now_ns
                ),
                readiness=final_readiness,
            )

            # Evidence failure escapes through the stop/join finally block.
            # The lifecycle must retain RUNNING instead of claiming success.
            if observe_snapshot is not None:
                observe_snapshot(final_readiness, snapshot)

            if snapshot.terminal:
                stop_event.set()
                break

            sleep_seconds(
                interval
            )

    finally:
        stop_event.set()

        coinbase_thread.join(
            timeout=join_timeout
        )

        kalshi_thread.join(
            timeout=join_timeout
        )

    cb_stopped = not (
        coinbase_thread.is_alive()
    )

    ka_stopped = not (
        kalshi_thread.is_alive()
    )

    # Joining writers is outside the measurement window. Re-sampling time here
    # would add shutdown time to a fatal attempt without readiness accounting.
    final_snapshot = snapshot

    # A source process that ignores the global stop boundary is itself a
    # hard runner failure. This happens after the timing controller has already
    # reached a terminal state, so expose it explicitly in the returned result.
    if not cb_stopped:
        source_failure = (
            "COINBASE_SUPERVISOR_STOP_TIMEOUT"
        )

    elif not ka_stopped:
        source_failure = (
            "KALSHI_SUPERVISOR_STOP_TIMEOUT"
        )

    elif coinbase_state.exception is not None:
        source_failure = "COINBASE_SUPERVISOR_EXCEPTION:" + type(coinbase_state.exception).__name__
    elif kalshi_state.exception is not None:
        source_failure = "KALSHI_SUPERVISOR_EXCEPTION:" + type(kalshi_state.exception).__name__

    return SoakRunnerShellResult(
        run=final_snapshot,
        final_readiness_state=(
            final_readiness.state
        ),
        final_readiness_reason=(
            final_readiness.reason
        ),
        coinbase_thread_started=(
            coinbase_state.started
        ),
        kalshi_thread_started=(
            kalshi_state.started
        ),
        coinbase_thread_stopped=(
            cb_stopped
        ),
        kalshi_thread_stopped=(
            ka_stopped
        ),
        source_failure=source_failure,
    )
