"""Checkpoint 21N-Z-E-B3: offline startup/restart gate state machine.

Implements the frozen Z-E-A state machine and clock gate using injected,
offline gate observations only.

No Coinbase/Kalshi network client, Candidate-E probability computation,
prospective cohort arm, paper/demo broker, or order path exists here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
from typing import Any
from uuid import uuid4

from src.kxbtcd_candidate_e_restart_durable_state_store import (
    RestartDurableStateStore,
    RestartDurableStateStoreError,
)


MAX_ABSOLUTE_CLOCK_OFFSET_MS = 250.0

FROZEN_STATES = (
    "STARTUP_DISABLED",
    "BLOCKED_IDENTITY",
    "BLOCKED_COHORT",
    "BLOCKED_DURABILITY",
    "BLOCKED_CLOCK",
    "BLOCKED_COINBASE",
    "BLOCKED_KALSHI",
    "BLOCKED_STRATEGY_RECONCILIATION",
    "READY_READ_ONLY",
    "COHORT_ENDED",
    "FATAL",
)


class RestartGateError(RuntimeError):
    pass


class GateStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    FATAL = "FATAL"


class CohortStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    FATAL = "FATAL"


@dataclass(frozen=True)
class ClockHealth:
    known: bool
    absolute_offset_ms: float | None

    @classmethod
    def from_signed_offset_ms(
        cls,
        signed_offset_ms: float | int | None,
    ) -> "ClockHealth":
        if signed_offset_ms is None:
            return cls(
                known=False,
                absolute_offset_ms=None,
            )

        value = float(signed_offset_ms)
        if not math.isfinite(value):
            return cls(
                known=False,
                absolute_offset_ms=None,
            )

        return cls(
            known=True,
            absolute_offset_ms=abs(value),
        )

    @property
    def healthy(self) -> bool:
        return (
            self.known
            and self.absolute_offset_ms is not None
            and self.absolute_offset_ms
            <= MAX_ABSOLUTE_CLOCK_OFFSET_MS
        )

    @property
    def gate_status(self) -> GateStatus:
        return (
            GateStatus.PASS
            if self.healthy
            else GateStatus.BLOCKED
        )


@dataclass(frozen=True)
class RestartGateSnapshot:
    identity: GateStatus = GateStatus.UNKNOWN
    cohort: CohortStatus = CohortStatus.UNKNOWN
    durability: GateStatus = GateStatus.UNKNOWN
    clock: GateStatus = GateStatus.UNKNOWN
    coinbase: GateStatus = GateStatus.UNKNOWN
    kalshi: GateStatus = GateStatus.UNKNOWN
    strategy_reconciliation: GateStatus = GateStatus.UNKNOWN
    execution_mode_disabled: bool = True

    @classmethod
    def with_clock_health(
        cls,
        *,
        clock_health: ClockHealth,
        identity: GateStatus = GateStatus.UNKNOWN,
        cohort: CohortStatus = CohortStatus.UNKNOWN,
        durability: GateStatus = GateStatus.UNKNOWN,
        coinbase: GateStatus = GateStatus.UNKNOWN,
        kalshi: GateStatus = GateStatus.UNKNOWN,
        strategy_reconciliation: GateStatus = GateStatus.UNKNOWN,
        execution_mode_disabled: bool = True,
    ) -> "RestartGateSnapshot":
        return cls(
            identity=identity,
            cohort=cohort,
            durability=durability,
            clock=clock_health.gate_status,
            coinbase=coinbase,
            kalshi=kalshi,
            strategy_reconciliation=strategy_reconciliation,
            execution_mode_disabled=execution_mode_disabled,
        )


def resolve_restart_state(
    snapshot: RestartGateSnapshot,
) -> str:
    """Resolve one frozen state with deterministic fail-closed precedence.

    Fatal conditions dominate. A known-ended cohort is terminal no-signal.
    Otherwise gates are checked in the same order as the frozen ready
    requirements: identity -> cohort -> durability -> clock -> Coinbase ->
    Kalshi -> strategy reconciliation -> execution-disabled.
    """

    if not snapshot.execution_mode_disabled:
        return "FATAL"

    if (
        snapshot.identity == GateStatus.FATAL
        or snapshot.cohort == CohortStatus.FATAL
        or snapshot.durability == GateStatus.FATAL
        or snapshot.clock == GateStatus.FATAL
        or snapshot.coinbase == GateStatus.FATAL
        or snapshot.kalshi == GateStatus.FATAL
        or snapshot.strategy_reconciliation == GateStatus.FATAL
    ):
        return "FATAL"

    if snapshot.cohort == CohortStatus.ENDED:
        return "COHORT_ENDED"

    if snapshot.identity != GateStatus.PASS:
        return "BLOCKED_IDENTITY"

    if snapshot.cohort != CohortStatus.ACTIVE:
        return "BLOCKED_COHORT"

    if snapshot.durability != GateStatus.PASS:
        return "BLOCKED_DURABILITY"

    if snapshot.clock != GateStatus.PASS:
        return "BLOCKED_CLOCK"

    if snapshot.coinbase != GateStatus.PASS:
        return "BLOCKED_COINBASE"

    if snapshot.kalshi != GateStatus.PASS:
        return "BLOCKED_KALSHI"

    if snapshot.strategy_reconciliation != GateStatus.PASS:
        return "BLOCKED_STRATEGY_RECONCILIATION"

    return "READY_READ_ONLY"


class RestartGateStateMachine:
    """Persisted transition recorder around the frozen pure state resolver.

    B3 only decides *read-only readiness*. It never computes or emits a
    Candidate-E signal.
    """

    def __init__(
        self,
        *,
        store: RestartDurableStateStore,
        session_id: str,
    ) -> None:
        self.store = store
        self.session_id = str(session_id)
        if not self.session_id:
            raise RestartGateError(
                "session_id must be non-empty"
            )

        row = self.store.connection.execute(
            """
            SELECT shutdown_status
            FROM runtime_sessions
            WHERE session_id=?
            """,
            (self.session_id,),
        ).fetchone()
        if row is None:
            raise RestartGateError(
                "runtime session does not exist"
            )
        if row["shutdown_status"] != "RUNNING":
            raise RestartGateError(
                "gate state machine requires RUNNING session"
            )

        self.state = "STARTUP_DISABLED"
        self.readiness_generation = 0
        self._open_regression_gap_id: str | None = None
        self._last_monotonic_ns: int | None = None

    @property
    def signal_eligible(self) -> bool:
        # Eligibility means a fresh signal may be recomputed now.
        # It never means a prior signal may be reused.
        return self.state == "READY_READ_ONLY"

    @property
    def prior_signal_reusable(self) -> bool:
        return False

    @property
    def may_recompute_fresh_signal(self) -> bool:
        return self.signal_eligible

    def _next_event_seq(self) -> int:
        row = self.store.connection.execute(
            """
            SELECT COALESCE(MAX(session_event_seq),0)
            FROM runtime_events
            WHERE session_id=?
            """,
            (self.session_id,),
        ).fetchone()
        return int(row[0]) + 1

    def _insert_transition_event(
        self,
        *,
        prior_state: str,
        next_state: str,
        evaluated_utc: str,
        evaluated_monotonic_ns: int,
        snapshot: RestartGateSnapshot,
    ) -> None:
        payload = {
            "prior_state": prior_state,
            "next_state": next_state,
            "signal_eligible":
                next_state == "READY_READ_ONLY",
            "prior_signal_reusable": False,
            "readiness_generation":
                self.readiness_generation,
            "snapshot": {
                "identity": snapshot.identity.value,
                "cohort": snapshot.cohort.value,
                "durability": snapshot.durability.value,
                "clock": snapshot.clock.value,
                "coinbase": snapshot.coinbase.value,
                "kalshi": snapshot.kalshi.value,
                "strategy_reconciliation":
                    snapshot.strategy_reconciliation.value,
                "execution_mode_disabled":
                    snapshot.execution_mode_disabled,
            },
        }

        self.store.connection.execute(
            """
            INSERT INTO runtime_events (
                session_id,
                session_event_seq,
                event_utc,
                event_monotonic_ns,
                event_type,
                severity,
                payload_json
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                self.session_id,
                self._next_event_seq(),
                str(evaluated_utc),
                int(evaluated_monotonic_ns),
                "restart_gate.transition",
                (
                    "error"
                    if next_state == "FATAL"
                    else "warning"
                    if next_state.startswith("BLOCKED_")
                    or next_state == "COHORT_ENDED"
                    else "info"
                ),
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )

    def _open_gate_regression_gap(
        self,
        *,
        evaluated_utc: str,
    ) -> None:
        if self._open_regression_gap_id is not None:
            return

        gap_id = str(uuid4())
        self.store.connection.execute(
            """
            INSERT INTO observation_gaps (
                gap_id,
                gap_kind,
                reason,
                start_utc,
                end_utc,
                start_basis,
                prior_session_id,
                next_session_id,
                source_id,
                canonical_backfill_allowed
            ) VALUES (
                ?,
                'PROSPECTIVE_OBSERVATION_GAP',
                'READY_GATE_REGRESSION',
                ?,
                NULL,
                'GATE_REGRESSION_UTC',
                ?,
                ?,
                NULL,
                0
            )
            """,
            (
                gap_id,
                str(evaluated_utc),
                self.session_id,
                self.session_id,
            ),
        )
        self._open_regression_gap_id = gap_id

    def _close_gate_regression_gap(
        self,
        *,
        evaluated_utc: str,
    ) -> None:
        if self._open_regression_gap_id is None:
            return

        self.store.connection.execute(
            """
            UPDATE observation_gaps
            SET end_utc=?
            WHERE gap_id=?
              AND end_utc IS NULL
            """,
            (
                str(evaluated_utc),
                self._open_regression_gap_id,
            ),
        )
        self._open_regression_gap_id = None

    def evaluate(
        self,
        snapshot: RestartGateSnapshot,
        *,
        evaluated_utc: str,
        evaluated_monotonic_ns: int,
    ) -> str:
        ns = int(evaluated_monotonic_ns)
        if ns < 0:
            raise RestartGateError(
                "evaluated_monotonic_ns must be nonnegative"
            )
        if (
            self._last_monotonic_ns is not None
            and ns < self._last_monotonic_ns
        ):
            raise RestartGateError(
                "gate evaluation monotonic time regressed within session"
            )

        next_state = resolve_restart_state(snapshot)
        if next_state not in FROZEN_STATES:
            raise RestartGateError(
                "resolved state is outside frozen state set"
            )

        prior_state = self.state

        with self.store.transaction():
            if (
                prior_state == "READY_READ_ONLY"
                and next_state != "READY_READ_ONLY"
            ):
                self._open_gate_regression_gap(
                    evaluated_utc=evaluated_utc,
                )

            if (
                prior_state != "READY_READ_ONLY"
                and next_state == "READY_READ_ONLY"
            ):
                self.readiness_generation += 1
                self._close_gate_regression_gap(
                    evaluated_utc=evaluated_utc,
                )

            if next_state != prior_state:
                self._insert_transition_event(
                    prior_state=prior_state,
                    next_state=next_state,
                    evaluated_utc=evaluated_utc,
                    evaluated_monotonic_ns=ns,
                    snapshot=snapshot,
                )

        self.state = next_state
        self._last_monotonic_ns = ns
        return self.state
