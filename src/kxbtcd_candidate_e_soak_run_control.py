"""Checkpoint 21N-Z-F pure soak-duration and availability controller.

This module contains NO network, Docker, credential, source-client, model,
signal, P&L, or execution behavior.

Frozen timing contract:

- maximum 300 seconds to first READY_READ_ONLY;
- first READY at exactly 300 seconds is still accepted;
- active measurement starts at the first READY_READ_ONLY observation;
- active duration is measured only with local monotonic time;
- once active, BLOCKED intervals DO NOT pause or extend the timer;
- READY/BLOCKED accounting is capped exactly at the requested deadline;
- a FATAL readiness observation terminates immediately;
- monotonic regression is a hard failure.

This controller deliberately does not decide operational adequacy. It records
measurement timing evidence. Later reporting may reject a safety-clean run for
poor availability or resource behavior.
"""
from __future__ import annotations

from dataclasses import dataclass

from .kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from .kxbtcd_candidate_e_soak_readiness import (
    SoakReadinessResult,
)


INITIAL_READINESS_TIMEOUT_SECONDS = 300

RUN_CONTROL_STATES = (
    "WAITING_INITIAL_READY",
    "ACTIVE",
    "MEASUREMENT_COMPLETE",
    "INITIAL_READINESS_TIMEOUT",
    "FATAL",
)


class SoakRunControlError(RuntimeError):
    pass


@dataclass(frozen=True)
class SoakRunControlSnapshot:
    state: str
    reason: str
    terminal: bool
    measurement_complete: bool
    started_monotonic_ns: int
    first_ready_monotonic_ns: int | None
    active_deadline_monotonic_ns: int | None
    evaluated_monotonic_ns: int
    initial_readiness_elapsed_seconds: float
    active_elapsed_seconds: float
    ready_duration_seconds: float
    blocked_duration_seconds: float
    requested_active_duration_seconds: int


class SoakRunController:
    """Stateful monotonic run controller for one shakedown/soak attempt."""

    def __init__(
        self,
        *,
        started_monotonic_ns: int,
        requested_active_duration_seconds: int,
        initial_readiness_timeout_seconds: int = (
            INITIAL_READINESS_TIMEOUT_SECONDS
        ),
    ) -> None:
        self.started_monotonic_ns = self._ns(
            started_monotonic_ns,
            "started_monotonic_ns",
        )

        if (
            isinstance(
                requested_active_duration_seconds,
                bool,
            )
            or not isinstance(
                requested_active_duration_seconds,
                int,
            )
            or requested_active_duration_seconds <= 0
        ):
            raise SoakRunControlError(
                "requested_active_duration_seconds must be a positive integer"
            )

        if (
            isinstance(
                initial_readiness_timeout_seconds,
                bool,
            )
            or not isinstance(
                initial_readiness_timeout_seconds,
                int,
            )
            or initial_readiness_timeout_seconds <= 0
        ):
            raise SoakRunControlError(
                "initial_readiness_timeout_seconds must be a positive integer"
            )

        self.requested_active_duration_seconds = int(
            requested_active_duration_seconds
        )

        self.initial_readiness_timeout_seconds = int(
            initial_readiness_timeout_seconds
        )

        self.initial_deadline_ns = (
            self.started_monotonic_ns
            + self.initial_readiness_timeout_seconds
            * 1_000_000_000
        )

        self.state = "WAITING_INITIAL_READY"
        self.reason = "WAITING_FOR_FIRST_READY"

        self.first_ready_monotonic_ns: int | None = None
        self.active_deadline_monotonic_ns: int | None = None

        self.last_evaluated_monotonic_ns = (
            self.started_monotonic_ns
        )

        # Once active, this is the readiness state that applies from the most
        # recent evaluation until the next evaluation.
        self.last_active_readiness_state: str | None = None

        self.ready_duration_ns = 0
        self.blocked_duration_ns = 0

    @staticmethod
    def _ns(
        value: int,
        name: str,
    ) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            raise SoakRunControlError(
                f"{name} must be a nonnegative integer"
            )

        return int(value)

    @property
    def terminal(self) -> bool:
        return self.state in {
            "MEASUREMENT_COMPLETE",
            "INITIAL_READINESS_TIMEOUT",
            "FATAL",
        }

    def _accumulate_active_interval(
        self,
        *,
        now_ns: int,
    ) -> None:
        if (
            self.first_ready_monotonic_ns is None
            or self.active_deadline_monotonic_ns is None
            or self.last_active_readiness_state is None
        ):
            return

        start_ns = max(
            self.last_evaluated_monotonic_ns,
            self.first_ready_monotonic_ns,
        )

        end_ns = min(
            now_ns,
            self.active_deadline_monotonic_ns,
        )

        if end_ns <= start_ns:
            return

        delta = end_ns - start_ns

        if (
            self.last_active_readiness_state
            == "READY_READ_ONLY"
        ):
            self.ready_duration_ns += delta
        else:
            self.blocked_duration_ns += delta

    def _fatal(
        self,
        reason: str,
    ) -> None:
        self.state = "FATAL"
        self.reason = str(reason)

    def observe(
        self,
        *,
        evaluated_monotonic_ns: int,
        readiness: SoakReadinessResult,
    ) -> SoakRunControlSnapshot:
        now_ns = self._ns(
            evaluated_monotonic_ns,
            "evaluated_monotonic_ns",
        )

        if self.terminal:
            return self.snapshot(
                evaluated_monotonic_ns=now_ns
            )

        if now_ns < self.last_evaluated_monotonic_ns:
            self._fatal(
                "LOCAL_MONOTONIC_TIME_REGRESSION"
            )

            return self.snapshot(
                evaluated_monotonic_ns=now_ns
            )

        # Account for the prior observed readiness state up to this evaluation
        # before interpreting the newly observed state.
        self._accumulate_active_interval(
            now_ns=now_ns
        )

        if readiness.status == GateStatus.FATAL:
            self._fatal(
                readiness.reason
            )

            self.last_evaluated_monotonic_ns = now_ns

            return self.snapshot(
                evaluated_monotonic_ns=now_ns
            )

        if self.state == "WAITING_INITIAL_READY":
            if readiness.state == "READY_READ_ONLY":
                # "Within 300 seconds" is inclusive at the exact boundary.
                if now_ns > self.initial_deadline_ns:
                    self.state = (
                        "INITIAL_READINESS_TIMEOUT"
                    )
                    self.reason = (
                        "INITIAL_READINESS_TIMEOUT"
                    )
                else:
                    self.first_ready_monotonic_ns = (
                        now_ns
                    )

                    self.active_deadline_monotonic_ns = (
                        now_ns
                        + self.requested_active_duration_seconds
                        * 1_000_000_000
                    )

                    self.state = "ACTIVE"
                    self.reason = (
                        "ACTIVE_MEASUREMENT"
                    )

                    self.last_active_readiness_state = (
                        "READY_READ_ONLY"
                    )

            elif now_ns >= self.initial_deadline_ns:
                self.state = (
                    "INITIAL_READINESS_TIMEOUT"
                )
                self.reason = (
                    "INITIAL_READINESS_TIMEOUT"
                )

        elif self.state == "ACTIVE":
            self.last_active_readiness_state = (
                readiness.state
            )

            assert (
                self.active_deadline_monotonic_ns
                is not None
            )

            if now_ns >= self.active_deadline_monotonic_ns:
                self.state = (
                    "MEASUREMENT_COMPLETE"
                )
                self.reason = (
                    "REQUESTED_ACTIVE_DURATION_COMPLETE"
                )

        self.last_evaluated_monotonic_ns = now_ns

        return self.snapshot(
            evaluated_monotonic_ns=now_ns
        )

    def snapshot(
        self,
        *,
        evaluated_monotonic_ns: int,
    ) -> SoakRunControlSnapshot:
        now_ns = self._ns(
            evaluated_monotonic_ns,
            "evaluated_monotonic_ns",
        )

        initial_elapsed_ns = max(
            0,
            min(
                now_ns,
                (
                    self.first_ready_monotonic_ns
                    if self.first_ready_monotonic_ns
                    is not None
                    else now_ns
                ),
            )
            - self.started_monotonic_ns,
        )

        if self.first_ready_monotonic_ns is None:
            active_elapsed_ns = 0
        else:
            active_end = now_ns

            if self.active_deadline_monotonic_ns is not None:
                active_end = min(
                    active_end,
                    self.active_deadline_monotonic_ns,
                )

            active_elapsed_ns = max(
                0,
                active_end
                - self.first_ready_monotonic_ns,
            )

        return SoakRunControlSnapshot(
            state=self.state,
            reason=self.reason,
            terminal=self.terminal,
            measurement_complete=(
                self.state
                == "MEASUREMENT_COMPLETE"
            ),
            started_monotonic_ns=(
                self.started_monotonic_ns
            ),
            first_ready_monotonic_ns=(
                self.first_ready_monotonic_ns
            ),
            active_deadline_monotonic_ns=(
                self.active_deadline_monotonic_ns
            ),
            evaluated_monotonic_ns=now_ns,
            initial_readiness_elapsed_seconds=(
                initial_elapsed_ns
                / 1_000_000_000
            ),
            active_elapsed_seconds=(
                active_elapsed_ns
                / 1_000_000_000
            ),
            ready_duration_seconds=(
                self.ready_duration_ns
                / 1_000_000_000
            ),
            blocked_duration_seconds=(
                self.blocked_duration_ns
                / 1_000_000_000
            ),
            requested_active_duration_seconds=(
                self.requested_active_duration_seconds
            ),
        )
