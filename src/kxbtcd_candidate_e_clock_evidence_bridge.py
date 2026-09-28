"""Checkpoint 21N-Z-F host-clock evidence consumer.

The production-shaped runtime container does NOT access chronyd directly.

A host-managed publisher records real chronyd tracking evidence into an atomic
JSON file.  This module validates that evidence fail-closed before adapting the
raw chronyc output through the already-accepted B4 parser.

No network, credentials, model, signal, P&L, or execution behavior exists here.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .kxbtcd_candidate_e_restart_gate_state_machine import GateStatus
from .kxbtcd_candidate_e_restart_source_readiness import (
    ChronyTrackingEvidence,
    parse_chronyc_tracking,
)


CLOCK_EVIDENCE_SCHEMA = "candidate_e_host_clock_evidence.v1"
REAL_EVIDENCE_SOURCE = "real_host_chronyd"
MAX_CLOCK_EVIDENCE_AGE_NS = 5_000_000_000


class ClockEvidenceBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClockEvidenceBridgeResult:
    status: GateStatus
    reason: str
    chrony: ChronyTrackingEvidence
    evidence_age_ns: int | None
    publisher_instance_id: str | None
    host_boot_id: str | None
    host_time_namespace_id: str | None


def _blocked(
    reason: str,
    *,
    age_ns: int | None = None,
    publisher_instance_id: str | None = None,
    host_boot_id: str | None = None,
    host_time_namespace_id: str | None = None,
) -> ClockEvidenceBridgeResult:
    return ClockEvidenceBridgeResult(
        status=GateStatus.BLOCKED,
        reason=reason,
        chrony=ChronyTrackingEvidence(
            status=GateStatus.BLOCKED,
            signed_system_time_offset_ms=None,
            absolute_system_time_offset_ms=None,
            leap_status=None,
            reason=reason,
        ),
        evidence_age_ns=age_ns,
        publisher_instance_id=publisher_instance_id,
        host_boot_id=host_boot_id,
        host_time_namespace_id=host_time_namespace_id,
    )


def _fatal(reason: str) -> ClockEvidenceBridgeResult:
    return ClockEvidenceBridgeResult(
        status=GateStatus.FATAL,
        reason=reason,
        chrony=ChronyTrackingEvidence(
            status=GateStatus.FATAL,
            signed_system_time_offset_ms=None,
            absolute_system_time_offset_ms=None,
            leap_status=None,
            reason=reason,
        ),
        evidence_age_ns=None,
        publisher_instance_id=None,
        host_boot_id=None,
        host_time_namespace_id=None,
    )


def read_clock_evidence_json(path: str | Path) -> dict[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
        value = json.loads(raw)
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ClockEvidenceBridgeError(
            "clock evidence file is unreadable or invalid JSON"
        ) from exc

    if not isinstance(value, dict):
        raise ClockEvidenceBridgeError(
            "clock evidence JSON root must be an object"
        )
    return value


def evaluate_clock_evidence_record(
    record: Mapping[str, Any],
    *,
    now_monotonic_ns: int,
    current_boot_id: str,
    current_time_namespace_id: str,
) -> ClockEvidenceBridgeResult:
    """Evaluate one host clock evidence record without host I/O.

    This pure evaluator is used by Windows offline tests and by the Linux
    packaged-runtime file adapter.
    """
    required = (
        "schema_version",
        "evidence_source",
        "publisher_instance_id",
        "captured_utc",
        "captured_monotonic_ns",
        "host_boot_id",
        "host_time_namespace_id",
        "chronyc_returncode",
        "chronyc_tracking_raw",
        "publisher_status",
    )

    if any(name not in record for name in required):
        return _blocked("CLOCK_EVIDENCE_REQUIRED_FIELD_MISSING")

    if record.get("schema_version") != CLOCK_EVIDENCE_SCHEMA:
        return _blocked("CLOCK_EVIDENCE_SCHEMA_INVALID")

    # Positive provenance marker.  This is deliberately stricter than merely
    # checking for an explicit "synthetic=true" flag: production evidence must
    # affirmatively identify itself as coming from the real host chronyd bridge.
    if record.get("evidence_source") != REAL_EVIDENCE_SOURCE:
        return _fatal("SYNTHETIC_OR_NONPRODUCTION_CLOCK_EVIDENCE")

    publisher = str(record.get("publisher_instance_id", "")).strip()
    host_boot = str(record.get("host_boot_id", "")).strip()
    host_time_ns = str(record.get("host_time_namespace_id", "")).strip()

    if not publisher:
        return _blocked("CLOCK_EVIDENCE_PUBLISHER_ID_INVALID")

    if str(record.get("publisher_status", "")).strip() != "PASS":
        return _blocked(
            "CLOCK_EVIDENCE_PUBLISHER_NOT_PASS",
            publisher_instance_id=publisher,
            host_boot_id=host_boot or None,
            host_time_namespace_id=host_time_ns or None,
        )

    captured = record.get("captured_monotonic_ns")
    if (
        isinstance(captured, bool)
        or not isinstance(captured, int)
        or captured < 0
    ):
        return _blocked("CLOCK_EVIDENCE_MONOTONIC_INVALID")

    if (
        isinstance(now_monotonic_ns, bool)
        or not isinstance(now_monotonic_ns, int)
        or now_monotonic_ns < 0
    ):
        raise ClockEvidenceBridgeError(
            "now_monotonic_ns must be a nonnegative integer"
        )

    age_ns = now_monotonic_ns - captured

    if age_ns < 0:
        return _blocked(
            "CLOCK_EVIDENCE_NEGATIVE_AGE",
            age_ns=age_ns,
            publisher_instance_id=publisher,
            host_boot_id=host_boot or None,
            host_time_namespace_id=host_time_ns or None,
        )

    if age_ns > MAX_CLOCK_EVIDENCE_AGE_NS:
        return _blocked(
            "CLOCK_EVIDENCE_STALE",
            age_ns=age_ns,
            publisher_instance_id=publisher,
            host_boot_id=host_boot or None,
            host_time_namespace_id=host_time_ns or None,
        )

    if not host_boot or host_boot != str(current_boot_id).strip():
        return _blocked(
            "CLOCK_EVIDENCE_BOOT_ID_MISMATCH",
            age_ns=age_ns,
            publisher_instance_id=publisher,
            host_boot_id=host_boot or None,
            host_time_namespace_id=host_time_ns or None,
        )

    if (
        not host_time_ns
        or host_time_ns != str(current_time_namespace_id).strip()
    ):
        return _blocked(
            "CLOCK_EVIDENCE_TIME_NAMESPACE_MISMATCH",
            age_ns=age_ns,
            publisher_instance_id=publisher,
            host_boot_id=host_boot,
            host_time_namespace_id=host_time_ns or None,
        )

    rc = record.get("chronyc_returncode")
    if isinstance(rc, bool) or not isinstance(rc, int) or rc != 0:
        return _blocked(
            "CLOCK_EVIDENCE_CHRONYC_FAILED",
            age_ns=age_ns,
            publisher_instance_id=publisher,
            host_boot_id=host_boot,
            host_time_namespace_id=host_time_ns,
        )

    raw = record.get("chronyc_tracking_raw")
    if not isinstance(raw, str) or not raw.strip():
        return _blocked(
            "CLOCK_EVIDENCE_CHRONYC_OUTPUT_INVALID",
            age_ns=age_ns,
            publisher_instance_id=publisher,
            host_boot_id=host_boot,
            host_time_namespace_id=host_time_ns,
        )

    chrony = parse_chronyc_tracking(raw)
    if chrony.status != GateStatus.PASS:
        return ClockEvidenceBridgeResult(
            status=GateStatus.BLOCKED,
            reason="CLOCK_EVIDENCE_CHRONY_PARSE_NOT_PASS",
            chrony=chrony,
            evidence_age_ns=age_ns,
            publisher_instance_id=publisher,
            host_boot_id=host_boot,
            host_time_namespace_id=host_time_ns,
        )

    return ClockEvidenceBridgeResult(
        status=GateStatus.PASS,
        reason="PASS",
        chrony=chrony,
        evidence_age_ns=age_ns,
        publisher_instance_id=publisher,
        host_boot_id=host_boot,
        host_time_namespace_id=host_time_ns,
    )


def evaluate_clock_evidence_file(
    path: str | Path,
    *,
    now_monotonic_ns: int,
    current_boot_id: str,
    current_time_namespace_id: str,
) -> ClockEvidenceBridgeResult:
    try:
        record = read_clock_evidence_json(path)
    except FileNotFoundError:
        return _blocked("CLOCK_EVIDENCE_FILE_MISSING")
    except ClockEvidenceBridgeError:
        return _blocked("CLOCK_EVIDENCE_JSON_INVALID")

    return evaluate_clock_evidence_record(
        record,
        now_monotonic_ns=now_monotonic_ns,
        current_boot_id=current_boot_id,
        current_time_namespace_id=current_time_namespace_id,
    )
