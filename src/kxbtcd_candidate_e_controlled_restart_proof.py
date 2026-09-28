"""Offline acceptance checks for a read-only controlled-restart proof."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class ControlledRestartProofError(ValueError):
    pass


@dataclass(frozen=True)
class ControlledRestartProofReceipt:
    accepted_soak_run_id: str
    restart_run_id: str
    restart_evidence_id: str
    fresh_clock_evidence: bool
    fresh_coinbase_completed_candle: bool
    fresh_kalshi_discovery: bool
    fresh_kalshi_snapshot: bool
    reached_ready_read_only: bool


def _text(payload: Mapping[str, object], field: str) -> str:
    value = str(payload.get(field, "")).strip()
    if not value:
        raise ControlledRestartProofError("controlled-restart identity field is blank")
    return value


def validate_controlled_restart_proof(payload: Mapping[str, object]) -> ControlledRestartProofReceipt:
    """Accept only a fresh, non-trading source-recovery proof."""
    required = (
        "accepted_soak_run_id", "restart_run_id", "restart_evidence_id",
        "fresh_clock_evidence", "fresh_coinbase_completed_candle",
        "fresh_kalshi_discovery", "fresh_kalshi_snapshot",
        "reached_ready_read_only", "orders", "signals", "production_writes",
    )
    if any(field not in payload for field in required):
        raise ControlledRestartProofError("missing controlled-restart evidence")
    soak_run = _text(payload, "accepted_soak_run_id")
    restart_run = _text(payload, "restart_run_id")
    if soak_run == restart_run:
        raise ControlledRestartProofError("restart must use a new run identifier")
    fresh_fields = (
        "fresh_clock_evidence", "fresh_coinbase_completed_candle",
        "fresh_kalshi_discovery", "fresh_kalshi_snapshot", "reached_ready_read_only",
    )
    if any(payload[field] is not True for field in fresh_fields):
        raise ControlledRestartProofError("controlled restart does not prove fresh read-only recovery")
    for field in ("orders", "signals", "production_writes"):
        if isinstance(payload[field], bool) or payload[field] != 0:
            raise ControlledRestartProofError("controlled restart contains prohibited trading activity")
    return ControlledRestartProofReceipt(
        accepted_soak_run_id=soak_run,
        restart_run_id=restart_run,
        restart_evidence_id=_text(payload, "restart_evidence_id"),
        fresh_clock_evidence=True,
        fresh_coinbase_completed_candle=True,
        fresh_kalshi_discovery=True,
        fresh_kalshi_snapshot=True,
        reached_ready_read_only=True,
    )
