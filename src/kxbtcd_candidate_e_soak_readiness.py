"""Checkpoint 21N-Z-F infrastructure-only soak readiness coordinator.

This is deliberately NOT the strategy/prospective restart gate.

The AWS read-only soak does not arm a prospective cohort, perform strategy
reconciliation, compute Candidate-E probabilities, score P&L, or authorize
execution.

READY_READ_ONLY requires, in order:

1. execution mode remains disabled;
2. real production Linux runtime identity is valid;
3. the Linux boot ID still equals the run's immutable starting boot ID;
4. current real host-clock bridge evidence passes;
5. clock evidence refers to the same boot and time namespace as this runtime;
6. current Coinbase source generation passes readiness;
7. current Kalshi source generation passes readiness.

Hard-fail conditions dominate blocked conditions.

A hard failure is latched for the lifetime of this coordinator. A BLOCKED
condition may recover on later fresh evidence.

No network or trading behavior exists here.
"""
from __future__ import annotations

from dataclasses import dataclass

from .kxbtcd_candidate_e_clock_evidence_bridge import (
    ClockEvidenceBridgeResult,
)
from .kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from .kxbtcd_candidate_e_restart_source_readiness import (
    CoinbaseReadinessEvidence,
    KalshiReadinessEvidence,
)
from .kxbtcd_candidate_e_soak_linux_runtime_identity import (
    RuntimeLinuxIdentityEvidence,
)


SOAK_READINESS_STATES = (
    "BLOCKED_IDENTITY",
    "BLOCKED_CLOCK",
    "BLOCKED_COINBASE",
    "BLOCKED_KALSHI",
    "READY_READ_ONLY",
    "FATAL",
)


class SoakReadinessError(RuntimeError):
    pass


@dataclass(frozen=True)
class SoakReadinessResult:
    state: str
    status: GateStatus
    reason: str
    ready_read_only: bool
    expected_boot_id: str
    current_boot_id: str | None
    current_time_namespace_id: str | None
    identity_reason: str
    clock_reason: str
    coinbase_reason: str
    kalshi_reason: str


def _result(
    *,
    state: str,
    status: GateStatus,
    reason: str,
    expected_boot_id: str,
    identity: RuntimeLinuxIdentityEvidence,
    clock: ClockEvidenceBridgeResult,
    coinbase: CoinbaseReadinessEvidence,
    kalshi: KalshiReadinessEvidence,
) -> SoakReadinessResult:
    if state not in SOAK_READINESS_STATES:
        raise SoakReadinessError(
            "readiness state outside frozen soak state set"
        )

    return SoakReadinessResult(
        state=state,
        status=status,
        reason=reason,
        ready_read_only=(
            state == "READY_READ_ONLY"
        ),
        expected_boot_id=expected_boot_id,
        current_boot_id=identity.boot_id,
        current_time_namespace_id=(
            identity.time_namespace_id
        ),
        identity_reason=identity.reason,
        clock_reason=clock.reason,
        coinbase_reason=coinbase.reason,
        kalshi_reason=kalshi.reason,
    )


def resolve_soak_readiness(
    *,
    expected_boot_id: str,
    execution_mode_disabled: bool,
    identity: RuntimeLinuxIdentityEvidence,
    clock: ClockEvidenceBridgeResult,
    coinbase: CoinbaseReadinessEvidence,
    kalshi: KalshiReadinessEvidence,
) -> SoakReadinessResult:
    """Resolve one infrastructure-only read-only readiness state."""

    expected_boot = str(
        expected_boot_id
    ).strip()

    if not expected_boot:
        raise SoakReadinessError(
            "expected_boot_id must be non-empty"
        )

    # Execution is outside the authorization boundary for this soak.
    if not execution_mode_disabled:
        return _result(
            state="FATAL",
            status=GateStatus.FATAL,
            reason="EXECUTION_MODE_NOT_DISABLED",
            expected_boot_id=expected_boot,
            identity=identity,
            clock=clock,
            coinbase=coinbase,
            kalshi=kalshi,
        )

    # Explicit FATAL evidence dominates every ordinary BLOCKED gate.
    fatal_inputs = (
        ("IDENTITY_FATAL", identity),
        ("CLOCK_FATAL", clock),
        ("COINBASE_FATAL", coinbase),
        ("KALSHI_FATAL", kalshi),
    )

    for prefix, evidence in fatal_inputs:
        if evidence.status == GateStatus.FATAL:
            return _result(
                state="FATAL",
                status=GateStatus.FATAL,
                reason=(
                    prefix
                    + ":"
                    + str(evidence.reason)
                ),
                expected_boot_id=expected_boot,
                identity=identity,
                clock=clock,
                coinbase=coinbase,
                kalshi=kalshi,
            )

    if identity.status != GateStatus.PASS:
        return _result(
            state="BLOCKED_IDENTITY",
            status=GateStatus.BLOCKED,
            reason=identity.reason,
            expected_boot_id=expected_boot,
            identity=identity,
            clock=clock,
            coinbase=coinbase,
            kalshi=kalshi,
        )

    current_boot = str(
        identity.boot_id or ""
    ).strip()

    current_time_ns = str(
        identity.time_namespace_id or ""
    ).strip()

    # A production identity claiming PASS without both identity components is
    # internally contradictory and cannot be treated as ordinary source
    # unavailability.
    if not current_boot:
        return _result(
            state="FATAL",
            status=GateStatus.FATAL,
            reason="IDENTITY_PASS_WITHOUT_BOOT_ID",
            expected_boot_id=expected_boot,
            identity=identity,
            clock=clock,
            coinbase=coinbase,
            kalshi=kalshi,
        )

    if not current_time_ns:
        return _result(
            state="FATAL",
            status=GateStatus.FATAL,
            reason="IDENTITY_PASS_WITHOUT_TIME_NAMESPACE",
            expected_boot_id=expected_boot,
            identity=identity,
            clock=clock,
            coinbase=coinbase,
            kalshi=kalshi,
        )

    # The continuous shakedown/soak is defined to remain on one host boot.
    # A reboot must not silently become a new valid run after chronyd recovers.
    if current_boot != expected_boot:
        return _result(
            state="FATAL",
            status=GateStatus.FATAL,
            reason="UNEXPECTED_LINUX_BOOT_ID_CHANGE",
            expected_boot_id=expected_boot,
            identity=identity,
            clock=clock,
            coinbase=coinbase,
            kalshi=kalshi,
        )

    # If the bridge says PASS, its provenance identities must still agree
    # exactly with the independently resolved runtime identities. These checks
    # defend against impossible/internally inconsistent PASS evidence.
    if clock.status == GateStatus.PASS:
        if (
            str(clock.host_boot_id or "").strip()
            != current_boot
        ):
            return _result(
                state="FATAL",
                status=GateStatus.FATAL,
                reason=(
                    "CLOCK_PASS_WITH_BOOT_ID_MISMATCH"
                ),
                expected_boot_id=expected_boot,
                identity=identity,
                clock=clock,
                coinbase=coinbase,
                kalshi=kalshi,
            )

        if (
            str(
                clock.host_time_namespace_id
                or ""
            ).strip()
            != current_time_ns
        ):
            return _result(
                state="FATAL",
                status=GateStatus.FATAL,
                reason=(
                    "CLOCK_PASS_WITH_TIME_NAMESPACE_MISMATCH"
                ),
                expected_boot_id=expected_boot,
                identity=identity,
                clock=clock,
                coinbase=coinbase,
                kalshi=kalshi,
            )

    if clock.status != GateStatus.PASS:
        return _result(
            state="BLOCKED_CLOCK",
            status=GateStatus.BLOCKED,
            reason=clock.reason,
            expected_boot_id=expected_boot,
            identity=identity,
            clock=clock,
            coinbase=coinbase,
            kalshi=kalshi,
        )

    if coinbase.status != GateStatus.PASS:
        return _result(
            state="BLOCKED_COINBASE",
            status=GateStatus.BLOCKED,
            reason=coinbase.reason,
            expected_boot_id=expected_boot,
            identity=identity,
            clock=clock,
            coinbase=coinbase,
            kalshi=kalshi,
        )

    if kalshi.status != GateStatus.PASS:
        return _result(
            state="BLOCKED_KALSHI",
            status=GateStatus.BLOCKED,
            reason=kalshi.reason,
            expected_boot_id=expected_boot,
            identity=identity,
            clock=clock,
            coinbase=coinbase,
            kalshi=kalshi,
        )

    return _result(
        state="READY_READ_ONLY",
        status=GateStatus.PASS,
        reason="PASS",
        expected_boot_id=expected_boot,
        identity=identity,
        clock=clock,
        coinbase=coinbase,
        kalshi=kalshi,
    )


class SoakReadinessCoordinator:
    """Stateful hard-fail/monotonic wrapper around pure readiness resolution."""

    def __init__(
        self,
        *,
        expected_boot_id: str,
    ) -> None:
        expected = str(
            expected_boot_id
        ).strip()

        if not expected:
            raise SoakReadinessError(
                "expected_boot_id must be non-empty"
            )

        self.expected_boot_id = expected
        self.last_monotonic_ns: int | None = None
        self.latched_fatal_reason: str | None = None

    def evaluate(
        self,
        *,
        evaluated_monotonic_ns: int,
        execution_mode_disabled: bool,
        identity: RuntimeLinuxIdentityEvidence,
        clock: ClockEvidenceBridgeResult,
        coinbase: CoinbaseReadinessEvidence,
        kalshi: KalshiReadinessEvidence,
    ) -> SoakReadinessResult:
        ns = evaluated_monotonic_ns

        if (
            isinstance(ns, bool)
            or not isinstance(ns, int)
            or ns < 0
        ):
            self.latched_fatal_reason = (
                "LOCAL_MONOTONIC_TIME_INVALID"
            )

        elif (
            self.last_monotonic_ns is not None
            and ns < self.last_monotonic_ns
        ):
            self.latched_fatal_reason = (
                "LOCAL_MONOTONIC_TIME_REGRESSION"
            )

        if self.latched_fatal_reason is not None:
            return _result(
                state="FATAL",
                status=GateStatus.FATAL,
                reason=self.latched_fatal_reason,
                expected_boot_id=(
                    self.expected_boot_id
                ),
                identity=identity,
                clock=clock,
                coinbase=coinbase,
                kalshi=kalshi,
            )

        self.last_monotonic_ns = ns

        result = resolve_soak_readiness(
            expected_boot_id=(
                self.expected_boot_id
            ),
            execution_mode_disabled=(
                execution_mode_disabled
            ),
            identity=identity,
            clock=clock,
            coinbase=coinbase,
            kalshi=kalshi,
        )

        if result.status == GateStatus.FATAL:
            self.latched_fatal_reason = (
                result.reason
            )

        return result
