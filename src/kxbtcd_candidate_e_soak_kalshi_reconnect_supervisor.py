"""Checkpoint 21N-Z-F long-running Kalshi reconnect/rollover supervisor.

This layer owns source lifecycle orchestration, not market-data parsing.

Flow:

INITIAL:
    if no current KXBTCD event exists -> REST rediscovery callback

NORMAL WS:
    run exactly one already-tested Kalshi WS generation

RECOVERABLE SOURCE FAILURE:
    BLOCK
    retain selected event
    frozen 1/2/4/8/15 second backoff
    fresh WS generation

EVENT ROLLOVER:
    BLOCK
    clear any pending retry wait WITHOUT resetting failure history
    REST rediscover current KXBTCD event
    fresh WS generation
    fresh complete ladder + Pong required before readiness PASS

LOCAL EVIDENCE / CONFIG / INVARIANT FAILURE:
    HARD FAIL
    never converted into reconnect backoff

The supplied rediscovery callback is expected to use the already-tested
raw-first Kalshi REST transport. Tests remain fully network-free.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

from .kxbtcd_candidate_e_soak_failure_policy import (
    is_local_fatal_exception,
)
from .kxbtcd_candidate_e_soak_kalshi_worker import (
    KalshiReadOnlyWorkerSession,
)


class KalshiReconnectSupervisorError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class KalshiReconnectSummary:
    generations_started: int
    recoverable_failures: int
    rollovers: int
    rediscovery_attempts: int
    rediscovery_failures: int
    stopped_cleanly: bool


def _disconnect_current_if_open(
    worker: KalshiReadOnlyWorkerSession,
    *,
    observed_monotonic_ns: int,
    count_as_failure: bool,
):
    current = (
        worker.core.connections
        .current_kalshi
    )

    if (
        current is None
        or not current.connected
    ):
        return None

    if (
        worker.binding is None
        or worker.binding.generation
        != current.generation
    ):
        raise KalshiReconnectSupervisorError(
            "Kalshi worker/current-generation identity mismatch"
        )

    return worker.disconnect(
        closed_monotonic_ns=(
            observed_monotonic_ns
        ),
        count_as_failure=(
            count_as_failure
        ),
    )


def _ensure_one_recoverable_failure_recorded(
    worker: KalshiReadOnlyWorkerSession,
    *,
    failure_count_before: int,
    observed_monotonic_ns: int,
) -> None:
    """Ensure exactly one backoff failure was recorded for this attempt.

    The one-generation transport normally records its own failure while
    closing the generation. This helper avoids double-counting but also keeps
    the supervisor safe if a failure happens before the transport records it.
    """

    backoff = worker.core.kalshi_backoff

    after = int(
        backoff.consecutive_failures
    )

    current = (
        worker.core.connections
        .current_kalshi
    )

    if (
        current is not None
        and current.connected
    ):
        _disconnect_current_if_open(
            worker,
            observed_monotonic_ns=(
                observed_monotonic_ns
            ),
            count_as_failure=(
                after
                == failure_count_before
            ),
        )

        return

    if after == failure_count_before:
        worker.core.record_source_failure(
            "kalshi",
            observed_monotonic_ns=(
                observed_monotonic_ns
            ),
        )


def _wait_until_retry_allowed(
    *,
    worker: KalshiReadOnlyWorkerSession,
    stop_event: threading.Event,
    monotonic_ns: Callable[[], int],
    sleep_seconds: Callable[[float], None],
) -> None:
    while (
        not stop_event.is_set()
        and not worker.core.source_retry_allowed(
            "kalshi",
            now_monotonic_ns=int(
                monotonic_ns()
            ),
        )
    ):
        # Keep shutdown responsive while respecting the frozen absolute
        # retry-not-before timestamp.
        sleep_seconds(
            0.1
        )


def run_kalshi_reconnect_supervisor(
    *,
    worker: KalshiReadOnlyWorkerSession,
    stop_event: threading.Event,
    run_generation: Callable[[], object],
    rediscover_current_event: Callable[[], object],
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    sleep_seconds: Callable[[float], None] = time.sleep,
) -> KalshiReconnectSummary:
    """Run Kalshi until global stop or a fail-closed local failure."""

    generations = 0
    recoverable_failures = 0
    rollovers = 0
    rediscovery_attempts = 0
    rediscovery_failures = 0

    needs_rediscovery = (
        worker.core.current_event
        is None
    )

    while not stop_event.is_set():
        _wait_until_retry_allowed(
            worker=worker,
            stop_event=stop_event,
            monotonic_ns=(
                monotonic_ns
            ),
            sleep_seconds=(
                sleep_seconds
            ),
        )

        if stop_event.is_set():
            break

        # Initial startup or an intentional KXBTCD rollover must obtain a
        # fresh current-event REST discovery before another WS generation.
        if needs_rediscovery:
            rediscovery_attempts += 1

            failure_count_before = int(
                worker.core
                .kalshi_backoff
                .consecutive_failures
            )

            try:
                rediscover_current_event()

            except Exception as exc:
                observed_ns = int(
                    monotonic_ns()
                )

                if is_local_fatal_exception(
                    exc
                ):
                    _disconnect_current_if_open(
                        worker,
                        observed_monotonic_ns=(
                            observed_ns
                        ),
                        count_as_failure=False,
                    )

                    raise

                rediscovery_failures += 1
                recoverable_failures += 1

                _ensure_one_recoverable_failure_recorded(
                    worker,
                    failure_count_before=(
                        failure_count_before
                    ),
                    observed_monotonic_ns=(
                        observed_ns
                    ),
                )

                continue

            if (
                worker.core.current_event
                is None
            ):
                raise (
                    KalshiReconnectSupervisorError(
                        "Kalshi rediscovery returned without binding current event"
                    )
                )

            needs_rediscovery = False

        failure_count_before = int(
            worker.core
            .kalshi_backoff
            .consecutive_failures
        )

        generations += 1

        try:
            result = run_generation()

        except Exception as exc:
            observed_ns = int(
                monotonic_ns()
            )

            if is_local_fatal_exception(
                exc
            ):
                _disconnect_current_if_open(
                    worker,
                    observed_monotonic_ns=(
                        observed_ns
                    ),
                    count_as_failure=False,
                )

                raise

            recoverable_failures += 1

            _ensure_one_recoverable_failure_recorded(
                worker,
                failure_count_before=(
                    failure_count_before
                ),
                observed_monotonic_ns=(
                    observed_ns
                ),
            )

            continue

        intentional_stop = bool(
            getattr(
                result,
                "intentional_stop",
                False,
            )
        )

        if intentional_stop:
            if not stop_event.is_set():
                raise (
                    KalshiReconnectSupervisorError(
                        "Kalshi generation reported intentional stop "
                        "without global stop request"
                    )
                )

            break

        kind = str(
            getattr(
                result,
                "final_action_kind",
                "",
            )
        )

        if kind == "RECONNECT_REQUIRED":
            # The tested one-generation wrapper closes the generation and
            # records exactly one source failure before returning this action.
            reconnect_decision = getattr(
                result,
                "reconnect_decision",
                None,
            )

            if reconnect_decision is None:
                raise (
                    KalshiReconnectSupervisorError(
                        "reconnect action returned without reconnect decision"
                    )
                )

            recoverable_failures += 1

            continue

        if kind == "ROLLOVER_REQUIRED":
            # Planned rollover is not evidence of source health or failure.
            #
            # Clear only the pending wait. Preserve consecutive failure count.
            worker.core.kalshi_backoff.intentional_rollover()

            rollovers += 1
            needs_rediscovery = True

            continue

        raise KalshiReconnectSupervisorError(
            "Kalshi generation returned without stop/reconnect/rollover"
        )

    _disconnect_current_if_open(
        worker,
        observed_monotonic_ns=int(
            monotonic_ns()
        ),
        count_as_failure=False,
    )

    return KalshiReconnectSummary(
        generations_started=generations,
        recoverable_failures=(
            recoverable_failures
        ),
        rollovers=rollovers,
        rediscovery_attempts=(
            rediscovery_attempts
        ),
        rediscovery_failures=(
            rediscovery_failures
        ),
        stopped_cleanly=(
            stop_event.is_set()
        ),
    )
