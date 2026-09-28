import pytest

from src.kxbtcd_candidate_e_micro_probe_readiness import (
    MicroProbeReadinessError,
    validate_micro_probe_readiness,
)
from tests.test_kxbtcd_candidate_e_micro_probe_preflight import payload as preflight_payload


def ready_payload(**overrides):
    return {
        "preflight": preflight_payload(), "accepted_read_only_soak": True,
        "accepted_controlled_restart": True, "accepted_soak_run_id": "soak_24h_1",
        "accepted_restart_evidence_id": "restart_1",
        "explicit_user_run_approval_id": "user_approval_1", **overrides,
    }


def test_readiness_requires_all_evidence_and_explicit_run_approval():
    receipt = validate_micro_probe_readiness(ready_payload())
    assert receipt.accepted_soak_run_id == "soak_24h_1"


def test_readiness_fails_closed_before_soak_restart_or_approval_evidence():
    with pytest.raises(MicroProbeReadinessError, match="24-hour"):
        validate_micro_probe_readiness(ready_payload(accepted_read_only_soak=False))
    with pytest.raises(MicroProbeReadinessError, match="restart"):
        validate_micro_probe_readiness(ready_payload(accepted_controlled_restart=False))
    with pytest.raises(MicroProbeReadinessError, match="identity"):
        validate_micro_probe_readiness(ready_payload(explicit_user_run_approval_id=""))
