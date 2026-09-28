"""Offline terminal acceptance check for a read-only soak evidence pair."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class ReadOnlySoakAcceptanceError(ValueError):
    pass


@dataclass(frozen=True)
class ReadOnlySoakAcceptanceReceipt:
    run_id: str


def accept_terminal_read_only_soak(*, summary: Mapping[str, object],
                                  manifest: Mapping[str, object]) -> ReadOnlySoakAcceptanceReceipt:
    """Accept only consistent, terminal, non-trading read-only evidence."""
    run_id = str(summary.get("run_id", "")).strip()
    manifest_run_id = str(manifest.get("run_id", "")).strip()
    if not run_id or run_id != manifest_run_id:
        raise ReadOnlySoakAcceptanceError("summary and manifest run identifiers do not match")
    if summary.get("measurement_complete") is not True or manifest.get("measurement_complete") is not True:
        raise ReadOnlySoakAcceptanceError("read-only soak did not complete measurement")
    if manifest.get("lifecycle_state") != "TERMINAL" or manifest.get("operational_classification") != "MEASUREMENT_COMPLETE":
        raise ReadOnlySoakAcceptanceError("read-only soak is not terminal measurement-complete")
    if summary.get("safety_invariant_status") != "PASS" or manifest.get("safety_invariant_status") != "PASS":
        raise ReadOnlySoakAcceptanceError("read-only soak safety invariant failed")
    if summary.get("execution_mode") != "disabled":
        raise ReadOnlySoakAcceptanceError("soak execution mode was not disabled")
    if summary.get("readiness_input_contract") != "v2_exact_rest_candle_and_kalshi":
        raise ReadOnlySoakAcceptanceError("soak did not use the frozen V2 REST-candle input contract")
    for counter in ("orders", "signals", "production_writes"):
        if summary.get(counter) != 0:
            raise ReadOnlySoakAcceptanceError("read-only soak contains prohibited trading activity")
    return ReadOnlySoakAcceptanceReceipt(run_id=run_id)
