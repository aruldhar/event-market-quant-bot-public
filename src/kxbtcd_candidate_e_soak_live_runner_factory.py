"""Compose the explicit live gate with observed read-only soak components."""
from __future__ import annotations

from .kxbtcd_candidate_e_soak_runtime_command import dispatch_runtime_command


def run_gated_read_only_soak(*, argv, run_preflight, run_assembled_live):
    """Run preflight by default; invoke the assembled live callable only on acknowledgement."""
    return dispatch_runtime_command(
        argv=argv, run_preflight=run_preflight,
        run_read_only_live=run_assembled_live)
