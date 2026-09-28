"""Checkpoint 21N-Z-F long-running Coinbase reconnect supervisor.

This layer repeatedly invokes the already-tested single-generation WebSocket
transport.

Important separation:
- recoverable source/network failures -> frozen 1,2,4,8,15 second retry;
- local evidence/integrity failures -> HARD FAIL, never hidden by reconnect;
- global stop -> clean exit;
- no model, signal, P&L, order, or production-write behavior.

Tests inject a fake generation runner and fake clock/sleeper.  They perform
zero real network access.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

from .kxbtcd_candidate_e_soak_failure_policy import (
    is_local_fatal_exception,
)
from .kxbtcd_candidate_e_soak_coinbase_worker import (
    CoinbaseReadOnlyWorkerSession,
)


class CoinbaseReconnectSupervisorError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class CoinbaseReconnectSummary:
    generations_started: int
    recoverable_failures: int
    hard_failures: int
    stopped_cleanly: bool


def _disconnect_current_if_open(
    worker: CoinbaseReadOnlyWorkerSession,
    *,
    observed_monotonic_ns: int,
    count_as_failure: bool,
):
    current = (
        worker.core.connections
        .current_coinbase
    )

    if (
        current is None
        or not current.connected
    ):
        return None

    # The worker session normally owns the same current binding.
    # If it does not, that is a local state invariant failure.
    if (
        worker.binding is None
        or worker.binding.generation
        != current.generation
    ):
        raise CoinbaseReconnectSupervisorError(
            "Coinbase worker/current-generation identity mismatch"
        )

    return worker.disconnect(
        closed_monotonic_ns=(
            observed_monotonic_ns
        ),
        count_as_failure=count_as_failure,
    )


def run_coinbase_reconnect_supervisor(
    *,
    worker: CoinbaseReadOnlyWorkerSession,
    stop_event: threading.Event,
    run_generation: Callable[[], object],
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    sleep_seconds: Callable[[float], None] = time.sleep,
) -> CoinbaseReconnectSummary:
    """Run Coinbase generations until global stop or a local hard failure."""

    generations = 0
    recoverable_failures = 0
    hard_failures = 0

    while not stop_event.is_set():
        # The previous recoverable failure may have armed a frozen retry time.
        while (
            not stop_event.is_set()
            and not worker.core.source_retry_allowed(
                "coinbase",
                now_monotonic_ns=int(
                    monotonic_ns()
                ),
            )
        ):
            # Short bounded sleep lets global shutdown remain responsive.
            sleep_seconds(0.1)

        if stop_event.is_set():
            break

        generations += 1

        try:
            run_generation()

            # A generation should only return normally because the global
            # stop condition was requested.
            if not stop_event.is_set():
                raise CoinbaseReconnectSupervisorError(
                    "Coinbase generation returned without global stop"
                )

        except BaseException as exc:
            observed_ns = int(
                monotonic_ns()
            )

            if is_local_fatal_exception(exc):
                hard_failures += 1

                _disconnect_current_if_open(
                    worker,
                    observed_monotonic_ns=(
                        observed_ns
                    ),
                    count_as_failure=False,
                )

                raise

            # Anything not classified as a local evidence/invariant failure
            # is treated as a recoverable source-generation failure.
            recoverable_failures += 1

            current = (
                worker.core.connections
                .current_coinbase
            )

            if (
                current is not None
                and current.connected
            ):
                _disconnect_current_if_open(
                    worker,
                    observed_monotonic_ns=(
                        observed_ns
                    ),
                    count_as_failure=True,
                )
            else:
                # The single-generation transport may already have closed the
                # connection and recorded this failure. Do not double-count.
                backoff = (
                    worker.core.coinbase_backoff
                )

                if (
                    backoff
                    .consecutive_failures
                    == 0
                ):
                    worker.core.record_source_failure(
                        "coinbase",
                        observed_monotonic_ns=(
                            observed_ns
                        ),
                    )

            continue

    # Global stop: never convert it into a failure/retry.
    if stop_event.is_set():
        _disconnect_current_if_open(
            worker,
            observed_monotonic_ns=int(
                monotonic_ns()
            ),
            count_as_failure=False,
        )

    return CoinbaseReconnectSummary(
        generations_started=generations,
        recoverable_failures=(
            recoverable_failures
        ),
        hard_failures=hard_failures,
        stopped_cleanly=(
            stop_event.is_set()
        ),
    )
