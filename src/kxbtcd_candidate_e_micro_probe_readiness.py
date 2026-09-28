"""Offline authorization gate for a future exact micro-probe run."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .kxbtcd_candidate_e_micro_probe_preflight import (
    MicroProbePreflightReceipt,
    validate_micro_probe_preflight,
)


class MicroProbeReadinessError(ValueError):
    pass


@dataclass(frozen=True)
class MicroProbeReadinessReceipt:
    preflight: MicroProbePreflightReceipt
    accepted_soak_run_id: str
    accepted_restart_evidence_id: str
    explicit_user_run_approval_id: str


def validate_micro_probe_readiness(payload: Mapping[str, object]) -> MicroProbeReadinessReceipt:
    """Validate evidence gates only; this cannot authorize a transport call."""
    preflight_raw = payload.get("preflight")
    if not isinstance(preflight_raw, Mapping):
        raise MicroProbeReadinessError("preflight receipt is required")
    preflight = validate_micro_probe_preflight(preflight_raw)
    if payload.get("accepted_read_only_soak") is not True:
        raise MicroProbeReadinessError("accepted 24-hour read-only soak is required")
    if payload.get("accepted_controlled_restart") is not True:
        raise MicroProbeReadinessError("accepted controlled restart is required")
    identities = {}
    for field in (
        "accepted_soak_run_id", "accepted_restart_evidence_id",
        "explicit_user_run_approval_id",
    ):
        value = str(payload.get(field, "")).strip()
        if not value:
            raise MicroProbeReadinessError("readiness identity field is blank")
        identities[field] = value
    return MicroProbeReadinessReceipt(preflight=preflight, **identities)
