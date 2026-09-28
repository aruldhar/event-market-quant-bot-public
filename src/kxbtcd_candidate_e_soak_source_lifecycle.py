"""Checkpoint 21N-Z-F source reconnect and rollover policy.

Pure/network-free policy only.

Responsibilities:
- frozen reconnect schedule: 1, 2, 4, 8, 15 seconds, capped at 15;
- backoff resets only after current-source readiness PASS;
- intentional event rollover starts immediately;
- stale source state never authorizes reuse;
- selected KXBTCD event closing or ceasing to be current requires rollover.

Connection generations themselves remain owned by the already-accepted
ReconnectGenerationController.
"""
from __future__ import annotations

from dataclasses import dataclass


RECONNECT_BACKOFF_SECONDS = (1, 2, 4, 8, 15)
RECONNECT_BACKOFF_CAP_SECONDS = 15
# KXBTCD is an hourly price ladder.  After an event closes, accepting a
# substantially later ladder hides a missing successor and loses an entire
# interval of observability.  Ninety minutes permits normal listing delay and
# still rejects the multi-hour jump observed in r31.
MAXIMUM_HOURLY_SUCCESSOR_LEAD_MS = 90 * 60 * 1000


class SoakSourceLifecycleError(RuntimeError):
    pass


class KalshiHourlySuccessorUnavailable(RuntimeError):
    """The raw response is valid, but lacks a near-term hourly successor."""

    pass


def reconnect_delay_seconds(
    consecutive_failures: int,
) -> int:
    if (
        isinstance(consecutive_failures, bool)
        or not isinstance(consecutive_failures, int)
        or consecutive_failures <= 0
    ):
        raise SoakSourceLifecycleError(
            "consecutive_failures must be a positive integer"
        )

    index = min(
        consecutive_failures - 1,
        len(RECONNECT_BACKOFF_SECONDS) - 1,
    )

    delay = RECONNECT_BACKOFF_SECONDS[index]

    if delay > RECONNECT_BACKOFF_CAP_SECONDS:
        raise SoakSourceLifecycleError(
            "reconnect delay exceeds frozen cap"
        )

    return delay


@dataclass(frozen=True)
class ReconnectDecision:
    consecutive_failures: int
    delay_seconds: int
    retry_not_before_monotonic_ns: int


class ReconnectBackoff:
    """Per-source consecutive-failure backoff.

    A successful socket open does NOT reset the schedule. Reset occurs only
    after fresh readiness PASS for the current generation.
    """

    def __init__(self) -> None:
        self.consecutive_failures = 0
        self.retry_not_before_monotonic_ns = 0

    def record_failure(
        self,
        *,
        observed_monotonic_ns: int,
    ) -> ReconnectDecision:
        now = _nonnegative_ns(
            observed_monotonic_ns,
            "observed_monotonic_ns",
        )

        self.consecutive_failures += 1

        delay = reconnect_delay_seconds(
            self.consecutive_failures
        )

        self.retry_not_before_monotonic_ns = (
            now + delay * 1_000_000_000
        )

        return ReconnectDecision(
            consecutive_failures=(
                self.consecutive_failures
            ),
            delay_seconds=delay,
            retry_not_before_monotonic_ns=(
                self.retry_not_before_monotonic_ns
            ),
        )

    def readiness_passed(self) -> None:
        self.consecutive_failures = 0
        self.retry_not_before_monotonic_ns = 0

    def retry_allowed(
        self,
        *,
        now_monotonic_ns: int,
    ) -> bool:
        now = _nonnegative_ns(
            now_monotonic_ns,
            "now_monotonic_ns",
        )

        return (
            now
            >= self.retry_not_before_monotonic_ns
        )

    def intentional_rollover(self) -> None:
        """Allow immediate new-generation attempt for planned rollover.

        This is not evidence of source health, so it does not count as a
        readiness reset. If the rollover attempt fails, record_failure()
        resumes/increments the failure sequence.
        """
        self.retry_not_before_monotonic_ns = 0


def _nonnegative_ns(
    value: int,
    name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise SoakSourceLifecycleError(
            f"{name} must be a nonnegative integer"
        )

    return int(value)


@dataclass(frozen=True)
class EventRolloverDecision:
    rollover_required: bool
    reason: str
    prior_event_ticker: str
    rediscovered_event_ticker: str | None


def classify_event_rollover(
    *,
    current_event_ticker: str,
    current_event_close_timestamp_ms: int,
    now_timestamp_ms: int,
    rediscovered_current_event_ticker: str | None = None,
) -> EventRolloverDecision:
    ticker = str(current_event_ticker).strip()

    if not ticker:
        raise SoakSourceLifecycleError(
            "current_event_ticker must be non-empty"
        )

    if (
        isinstance(current_event_close_timestamp_ms, bool)
        or not isinstance(
            current_event_close_timestamp_ms,
            int,
        )
        or current_event_close_timestamp_ms < 0
    ):
        raise SoakSourceLifecycleError(
            "current_event_close_timestamp_ms invalid"
        )

    if (
        isinstance(now_timestamp_ms, bool)
        or not isinstance(now_timestamp_ms, int)
        or now_timestamp_ms < 0
    ):
        raise SoakSourceLifecycleError(
            "now_timestamp_ms invalid"
        )

    rediscovered = None

    if rediscovered_current_event_ticker is not None:
        rediscovered = str(
            rediscovered_current_event_ticker
        ).strip()

        if not rediscovered:
            raise SoakSourceLifecycleError(
                "rediscovered event ticker cannot be blank"
            )

    if now_timestamp_ms >= current_event_close_timestamp_ms:
        return EventRolloverDecision(
            rollover_required=True,
            reason="SELECTED_EVENT_CLOSED",
            prior_event_ticker=ticker,
            rediscovered_event_ticker=rediscovered,
        )

    if (
        rediscovered is not None
        and rediscovered != ticker
    ):
        return EventRolloverDecision(
            rollover_required=True,
            reason="SELECTED_EVENT_NO_LONGER_CURRENT",
            prior_event_ticker=ticker,
            rediscovered_event_ticker=rediscovered,
        )

    return EventRolloverDecision(
        rollover_required=False,
        reason="CURRENT_EVENT_STILL_VALID",
        prior_event_ticker=ticker,
        rediscovered_event_ticker=rediscovered,
    )


def choose_current_event_ladder(
    ladders,
    *,
    now_timestamp_ms: int,
):
    """Choose the strategy-independent current KXBTCD event.

    Current means the earliest active/future event by close timestamp.

    This selector deliberately does NOT inspect:
    - Candidate-E probabilities;
    - strategy TTC windows;
    - order-book prices/spreads;
    - liquidity;
    - expected edge;
    - settlement outcomes.
    """
    if (
        isinstance(now_timestamp_ms, bool)
        or not isinstance(now_timestamp_ms, int)
        or now_timestamp_ms < 0
    ):
        raise SoakSourceLifecycleError(
            "now_timestamp_ms must be a nonnegative integer"
        )

    future = tuple(
        ladder
        for ladder in ladders
        if int(ladder.close_timestamp_ms)
        > now_timestamp_ms
    )

    if not future:
        raise SoakSourceLifecycleError(
            "no active/future KXBTCD event available"
        )

    selected = min(
        future,
        key=lambda ladder: (
            int(ladder.close_timestamp_ms),
            str(ladder.event_ticker),
        ),
    )
    if (
        int(selected.close_timestamp_ms) - now_timestamp_ms
        > MAXIMUM_HOURLY_SUCCESSOR_LEAD_MS
    ):
        raise KalshiHourlySuccessorUnavailable(
            "no near-term hourly KXBTCD successor is available"
        )
    return selected
