"""Offline consistency gate that binds future micro-probe evidence receipts."""
from __future__ import annotations

from dataclasses import dataclass

from .kxbtcd_candidate_e_controlled_restart_proof import ControlledRestartProofReceipt
from .kxbtcd_candidate_e_micro_probe_market_terms import MicroProbeMarketTermsReceipt
from .kxbtcd_candidate_e_micro_probe_readiness import MicroProbeReadinessReceipt


class MicroProbeLaunchPlanError(ValueError):
    pass


@dataclass(frozen=True)
class MicroProbeLaunchPlan:
    market_ticker: str
    accepted_soak_run_id: str
    restart_run_id: str
    explicit_user_run_approval_id: str


def bind_micro_probe_launch_plan(*, terms: MicroProbeMarketTermsReceipt,
                                 restart: ControlledRestartProofReceipt,
                                 readiness: MicroProbeReadinessReceipt) -> MicroProbeLaunchPlan:
    """Bind reviewed offline facts only; this has no execution capability."""
    if readiness.preflight.market_ticker != terms.market_ticker:
        raise MicroProbeLaunchPlanError("market-terms receipt does not match preflight market")
    if readiness.accepted_soak_run_id != restart.accepted_soak_run_id:
        raise MicroProbeLaunchPlanError("restart proof does not match accepted soak")
    if readiness.accepted_restart_evidence_id != restart.restart_evidence_id:
        raise MicroProbeLaunchPlanError("restart evidence identifier does not match readiness")
    return MicroProbeLaunchPlan(
        market_ticker=terms.market_ticker,
        accepted_soak_run_id=restart.accepted_soak_run_id,
        restart_run_id=restart.restart_run_id,
        explicit_user_run_approval_id=readiness.explicit_user_run_approval_id,
    )
