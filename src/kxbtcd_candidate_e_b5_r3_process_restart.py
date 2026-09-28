"""Checkpoint 21N-Z-E-B5-R3: offline process-restart orchestration.

This module integrates already-accepted restart components without adding new
market/model/execution semantics.

It proves, in a noncanonical validation database only:
- a new process creates a new runtime session;
- prior clean/unclean process state is classified by the B1 store;
- B2 pending raw evidence is reconciled to VERIFIED or RAW_EVIDENCE_GAP;
- no pending raw-durability row may remain before durability PASS;
- read-only strategy restart state must be explicitly neutral/non-actionable;
- old process Coinbase/Kalshi objects cannot authorize the new process because
  B4 source readiness remains bound to the current runtime session;
- the existing B3 gate is the only authority for READY_READ_ONLY.

No network client, Candidate-E probability/signal computation, cohort arm,
paper/demo broker, order submission, cancellation, fill, position, or P&L path
exists here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .kxbtcd_candidate_e_b5_r2_live_reconnect import (
    ReconnectGenerationController,
)
from .kxbtcd_candidate_e_restart_durable_state_store import (
    RestartDurableStateStore,
    RestartDurableStateStoreError,
)
from .kxbtcd_candidate_e_restart_gate_state_machine import (
    CohortStatus,
    GateStatus,
    RestartGateStateMachine,
)
from .kxbtcd_candidate_e_restart_reconciliation import (
    RestartReconciliationError,
    reconcile_pending_decisions,
    validate_arm_manifest_identity,
)
from .kxbtcd_candidate_e_restart_source_readiness import (
    BootIdentityEvidence,
    ChronyTrackingEvidence,
    CoinbaseReadinessEvidence,
    KalshiReadinessEvidence,
    build_current_source_gate_snapshot,
)


EXPECTED_PARENT_RECEIPT = (
    "3041a628329c94914c297553139d0e52a7a5d94d"
)
EXPECTED_B5_R3_DESIGN_FINGERPRINT = (
    "0623977817c055b5557296b6e9a58ea371c0ea680728c6a68a52a1c5abfdffea"
)
EXPECTED_MICRO_PRODUCTION_POLICY_FINGERPRINT = (
    "57e7e5c88bd296128927362119c0f3705d4be9ce5f0d8a13c1fd652ddd2e2677"
)

NETWORK_ENABLED = False
CANONICAL_PROSPECTIVE_DB_CREATED = False
COHORT_ARMED = False
SIGNALS_COMPUTED = 0
ORDERS_SUBMITTED = 0
PRODUCTION_WRITES = 0


class B5R3ProcessRestartError(RuntimeError):
    pass


def _parse_utc(value: str, name: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise B5R3ProcessRestartError(
            f"{name} must be ISO-8601"
        ) from exc
    if dt.tzinfo is None:
        raise B5R3ProcessRestartError(
            f"{name} must be timezone-aware"
        )
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class IdentityCohortEvidence:
    identity_status: GateStatus
    cohort_status: CohortStatus
    reason: str
    cohort_id: str | None
    arm_time_utc: str | None
    fixed_end_time_utc: str | None


@dataclass(frozen=True)
class DurabilityReconciliationEvidence:
    status: GateStatus
    reason: str
    current_session_id: str
    prior_session_id: str | None
    prior_shutdown_status: str | None
    pending_before: int
    pending_examined: int
    verified: int
    raw_evidence_gaps: int
    pending_after: int


@dataclass(frozen=True)
class StrategyRestartState:
    """Explicit in-memory restart state that must be neutral before readiness."""

    prior_signal_reusable: bool = False
    current_atm_window_restored: bool = False
    current_candidate_probability_restored: bool = False
    current_signal_selection_restored: bool = False
    reentry_state_restored: bool = False
    fills_loaded: bool = False
    positions_loaded: bool = False
    orders_loaded: bool = False
    cash_state_loaded: bool = False
    execution_mode_disabled: bool = True


@dataclass(frozen=True)
class StrategyReconciliationEvidence:
    status: GateStatus
    reason: str
    restored_or_actionable_fields: tuple[str, ...]
    prior_signal_reusable: bool
    execution_mode_disabled: bool


@dataclass(frozen=True)
class StartupReconciliationEvidence:
    identity_cohort: IdentityCohortEvidence
    durability: DurabilityReconciliationEvidence
    strategy: StrategyReconciliationEvidence


def evaluate_validation_identity_and_cohort(
    *,
    store: RestartDurableStateStore,
    manifest_path: str | Path,
    current_git_commit: str,
    evaluated_utc: str,
) -> IdentityCohortEvidence:
    """Use the frozen B2 identity contract, then classify cohort time.

    This helper is validation-only because the B1/B2 store itself refuses
    canonical prospective paths. It never arms or mutates a cohort.
    """
    try:
        result = validate_arm_manifest_identity(
            store=store,
            manifest_path=manifest_path,
            current_git_commit=current_git_commit,
        )
        manifest = json_load(Path(manifest_path))
        now = _parse_utc(evaluated_utc, "evaluated_utc")
        arm = _parse_utc(manifest["arm_time_utc"], "arm_time_utc")
        end = _parse_utc(
            manifest["fixed_end_time_utc"],
            "fixed_end_time_utc",
        )
    except (
        OSError,
        KeyError,
        ValueError,
        RestartReconciliationError,
        B5R3ProcessRestartError,
    ) as exc:
        return IdentityCohortEvidence(
            identity_status=GateStatus.FATAL,
            cohort_status=CohortStatus.UNKNOWN,
            reason=f"IDENTITY_OR_COHORT_VALIDATION_FAILED:{type(exc).__name__}",
            cohort_id=None,
            arm_time_utc=None,
            fixed_end_time_utc=None,
        )

    if result["status"] == "ENDED" or now >= end:
        cohort = CohortStatus.ENDED
        reason = "COHORT_ENDED"
    elif now < arm:
        cohort = CohortStatus.UNKNOWN
        reason = "COHORT_NOT_STARTED"
    else:
        cohort = CohortStatus.ACTIVE
        reason = "PASS"

    return IdentityCohortEvidence(
        identity_status=GateStatus.PASS,
        cohort_status=cohort,
        reason=reason,
        cohort_id=str(result["cohort_id"]),
        arm_time_utc=str(manifest["arm_time_utc"]),
        fixed_end_time_utc=str(result["fixed_end_time_utc"]),
    )


def json_load(path: Path) -> dict:
    import json

    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("JSON root must be object")
    return value


def reconcile_restart_durability(
    *,
    store: RestartDurableStateStore,
    current_session_id: str,
    raw_segments: Mapping[tuple[str, str], str | Path],
) -> DurabilityReconciliationEvidence:
    """Reconcile old audit evidence before the durability gate can pass.

    A prior RAW_EVIDENCE_GAP is an accepted classification, not reconstructed
    state. The new process may continue toward fresh readiness once every
    pending decision has been classified.
    """
    session_id = str(current_session_id)
    pending_before = 0
    prior_session_id: str | None = None
    prior_shutdown_status: str | None = None

    try:
        store.verify_integrity()
        store.verify_schema()
        store.verify_pragmas()

        current = store.session(session_id)
        if current["shutdown_status"] != "RUNNING":
            raise B5R3ProcessRestartError(
                "current restart session must be RUNNING"
            )

        prior_session_id = current["prior_session_id"]
        if prior_session_id is not None:
            prior = store.session(prior_session_id)
            prior_shutdown_status = str(prior["shutdown_status"])
            if prior_shutdown_status not in {
                "CLEAN",
                "UNCLEAN_DETECTED",
            }:
                raise B5R3ProcessRestartError(
                    "prior session not durably classified"
                )

        pending_before = int(
            store.connection.execute(
                """
                SELECT COUNT(*)
                FROM decision_records
                WHERE integrity_status='PENDING_RAW_DURABILITY'
                """
            ).fetchone()[0]
        )

        result = reconcile_pending_decisions(
            store=store,
            raw_segments=raw_segments,
        )

        pending_after = int(
            store.connection.execute(
                """
                SELECT COUNT(*)
                FROM decision_records
                WHERE integrity_status='PENDING_RAW_DURABILITY'
                """
            ).fetchone()[0]
        )
        if pending_after != 0:
            raise B5R3ProcessRestartError(
                "pending raw-durability decisions remain"
            )

        return DurabilityReconciliationEvidence(
            status=GateStatus.PASS,
            reason="PASS",
            current_session_id=session_id,
            prior_session_id=prior_session_id,
            prior_shutdown_status=prior_shutdown_status,
            pending_before=pending_before,
            pending_examined=int(result["pending_examined"]),
            verified=int(result["verified"]),
            raw_evidence_gaps=int(result["raw_evidence_gaps"]),
            pending_after=pending_after,
        )
    except (
        OSError,
        RestartDurableStateStoreError,
        RestartReconciliationError,
        B5R3ProcessRestartError,
    ) as exc:
        try:
            pending_after = int(
                store.connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM decision_records
                    WHERE integrity_status='PENDING_RAW_DURABILITY'
                    """
                ).fetchone()[0]
            )
        except Exception:
            pending_after = -1

        return DurabilityReconciliationEvidence(
            status=GateStatus.FATAL,
            reason=f"DURABILITY_RECONCILIATION_FAILED:{type(exc).__name__}",
            current_session_id=session_id,
            prior_session_id=prior_session_id,
            prior_shutdown_status=prior_shutdown_status,
            pending_before=pending_before,
            pending_examined=0,
            verified=0,
            raw_evidence_gaps=0,
            pending_after=pending_after,
        )


def evaluate_strategy_reconciliation(
    state: StrategyRestartState,
) -> StrategyReconciliationEvidence:
    """Prove the new process inherited no actionable read-only strategy state."""
    if not state.execution_mode_disabled:
        return StrategyReconciliationEvidence(
            status=GateStatus.FATAL,
            reason="EXECUTION_MODE_NOT_DISABLED",
            restored_or_actionable_fields=("execution_mode",),
            prior_signal_reusable=bool(state.prior_signal_reusable),
            execution_mode_disabled=False,
        )

    fields = (
        "prior_signal_reusable",
        "current_atm_window_restored",
        "current_candidate_probability_restored",
        "current_signal_selection_restored",
        "reentry_state_restored",
        "fills_loaded",
        "positions_loaded",
        "orders_loaded",
        "cash_state_loaded",
    )
    restored = tuple(
        name for name in fields if bool(getattr(state, name))
    )

    if restored:
        return StrategyReconciliationEvidence(
            status=GateStatus.BLOCKED,
            reason="STRATEGY_STATE_NOT_NEUTRAL",
            restored_or_actionable_fields=restored,
            prior_signal_reusable=bool(state.prior_signal_reusable),
            execution_mode_disabled=True,
        )

    return StrategyReconciliationEvidence(
        status=GateStatus.PASS,
        reason="PASS_NEUTRAL_FRESH_RECOMPUTATION_REQUIRED",
        restored_or_actionable_fields=(),
        prior_signal_reusable=False,
        execution_mode_disabled=True,
    )


class OfflineProcessRestartOrchestrator:
    """One-process offline restart coordinator around frozen B1-B5-R2 pieces."""

    def __init__(
        self,
        *,
        store: RestartDurableStateStore,
        session_id: str,
    ) -> None:
        self.store = store
        self.session_id = str(session_id).strip()
        if not self.session_id:
            raise B5R3ProcessRestartError("session_id required")

        row = self.store.session(self.session_id)
        if row["shutdown_status"] != "RUNNING":
            raise B5R3ProcessRestartError(
                "orchestrator requires RUNNING session"
            )

        self.gate = RestartGateStateMachine(
            store=self.store,
            session_id=self.session_id,
        )
        self.connections = ReconnectGenerationController(
            self.session_id
        )

    @classmethod
    def start_new_process(
        cls,
        *,
        store: RestartDurableStateStore,
        boot_id: str,
        git_commit: str,
        started_utc: str,
        started_monotonic_ns: int,
        session_id: str | None = None,
    ) -> "OfflineProcessRestartOrchestrator":
        sid = store.start_session(
            boot_id=boot_id,
            git_commit=git_commit,
            started_utc=started_utc,
            started_monotonic_ns=started_monotonic_ns,
            session_id=session_id,
        )
        return cls(store=store, session_id=sid)

    def reconcile_startup(
        self,
        *,
        manifest_path: str | Path,
        current_git_commit: str,
        evaluated_utc: str,
        raw_segments: Mapping[
            tuple[str, str],
            str | Path,
        ],
        strategy_state: StrategyRestartState | None = None,
    ) -> StartupReconciliationEvidence:
        identity = evaluate_validation_identity_and_cohort(
            store=self.store,
            manifest_path=manifest_path,
            current_git_commit=current_git_commit,
            evaluated_utc=evaluated_utc,
        )
        durability = reconcile_restart_durability(
            store=self.store,
            current_session_id=self.session_id,
            raw_segments=raw_segments,
        )
        strategy = evaluate_strategy_reconciliation(
            strategy_state or StrategyRestartState()
        )
        return StartupReconciliationEvidence(
            identity_cohort=identity,
            durability=durability,
            strategy=strategy,
        )

    def evaluate_current_readiness(
        self,
        *,
        startup: StartupReconciliationEvidence,
        boot_identity: BootIdentityEvidence,
        clock_evidence: ChronyTrackingEvidence,
        coinbase_evidence: CoinbaseReadinessEvidence,
        kalshi_evidence: KalshiReadinessEvidence,
        evaluated_utc: str,
        evaluated_monotonic_ns: int,
    ) -> str:
        snapshot = build_current_source_gate_snapshot(
            frozen_identity_status=(
                startup.identity_cohort.identity_status
            ),
            boot_identity=boot_identity,
            cohort_status=(
                startup.identity_cohort.cohort_status
            ),
            durability_status=startup.durability.status,
            clock_evidence=clock_evidence,
            coinbase_evidence=coinbase_evidence,
            kalshi_evidence=kalshi_evidence,
            strategy_reconciliation_status=(
                startup.strategy.status
            ),
            execution_mode_disabled=(
                startup.strategy.execution_mode_disabled
            ),
        )
        return self.gate.evaluate(
            snapshot,
            evaluated_utc=evaluated_utc,
            evaluated_monotonic_ns=int(
                evaluated_monotonic_ns
            ),
        )
