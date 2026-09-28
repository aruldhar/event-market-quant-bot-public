"""Checkpoint 21N-Z-E-B5-R4: bounded live whole-process restart helpers.

This module is network-free.  It contains validation contracts shared by the
B5-R4 supervisor/children and offline tests.

B5-R4 is strictly read-only:
- no Candidate-E signal computation;
- no canonical prospective DB/cohort arm;
- no order/cancel/fill/position/cash path;
- no production write endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .kxbtcd_candidate_e_restart_source_readiness import (
    KALSHI_WS_MAX_PONG_AGE_NS,
)


EXPECTED_B5_R4_A_RECEIPT = (
    "7bad4d50def3e44744347aedb11dfabe3d21c1ba"
)
EXPECTED_B5_R4_DESIGN_FINGERPRINT = (
    "17f4626e09c7231c0d65002d3e9f7f05d3046ccf054d59407619adea667aa0a9"
)

LIVE_NETWORK_ENABLED_BY_DEFAULT = False
CANONICAL_PROSPECTIVE_DB_CREATED = False
COHORT_ARMED = False
SIGNALS_COMPUTED = 0
ORDERS_SUBMITTED = 0
PRODUCTION_WRITES = 0

MIN_SOURCE_WAIT_SECONDS = 70
MAX_SOURCE_WAIT_SECONDS = 180
DEFAULT_SOURCE_WAIT_SECONDS = 120

SECRET_MARKERS = (
    b"kalshi-access-key",
    b"kalshi-access-signature",
    b"kalshi-access-timestamp",
    b"authorization:",
    b"bearer ",
    b"-----begin private key-----",
    b"-----begin rsa private key-----",
    b"-----begin ec private key-----",
)


class B5R4ValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ManualPongAttemptDecision:
    record_successful_pong: bool
    reason: str
    prior_pong_age_ns: int | None


def manual_ping_payload(
    runtime_session_id: str,
    attempt_sequence: int,
) -> bytes:
    """Return a unique payload for one manual Ping attempt.

    websockets forbids reusing the same Ping payload while an earlier matching
    Pong is still outstanding. A unique sequence lets B5-R4 retry liveness
    proof after a timeout without turning that timeout into a concurrency
    failure.
    """
    session = str(runtime_session_id).strip()
    if not session:
        raise B5R4ValidationError("runtime_session_id must be non-empty")
    if (
        isinstance(attempt_sequence, bool)
        or not isinstance(attempt_sequence, int)
        or attempt_sequence <= 0
    ):
        raise B5R4ValidationError(
            "manual Ping attempt sequence must be a positive integer"
        )
    return f"b5r4-{session}-p{attempt_sequence}".encode("ascii")


def classify_manual_pong_attempt(
    *,
    pong_received: bool,
    last_successful_pong_monotonic_ns: int | None,
    observed_monotonic_ns: int,
) -> ManualPongAttemptDecision:
    """Classify one observable manual Ping/Pong attempt.

    A successful Pong refreshes the current-connection liveness timestamp.

    A timeout never fabricates a refresh and never, by itself, overrides the
    already-frozen B4 liveness rule. The B4 evaluator remains authoritative:
    current transport liveness is PASS while the most recent proven Pong is no
    more than 15s + 5s old, and becomes KALSHI_PONG_STALE after that.

    If no Pong has ever been proven, readiness remains blocked until the
    transport either schedules a fresh connection generation or obtains a
    later successful Ping/Pong proof.
    """
    if not isinstance(pong_received, bool):
        raise B5R4ValidationError("pong_received must be boolean")
    if (
        isinstance(observed_monotonic_ns, bool)
        or not isinstance(observed_monotonic_ns, int)
        or observed_monotonic_ns < 0
    ):
        raise B5R4ValidationError(
            "observed_monotonic_ns must be a nonnegative integer"
        )

    prior = last_successful_pong_monotonic_ns
    if prior is not None:
        if (
            isinstance(prior, bool)
            or not isinstance(prior, int)
            or prior < 0
            or prior > observed_monotonic_ns
        ):
            raise B5R4ValidationError(
                "prior successful Pong monotonic timestamp invalid"
            )
        age_ns = observed_monotonic_ns - prior
    else:
        age_ns = None

    if pong_received:
        return ManualPongAttemptDecision(
            record_successful_pong=True,
            reason="PONG_RECEIVED_RECORD_CURRENT_TIME",
            prior_pong_age_ns=age_ns,
        )

    if age_ns is None:
        reason = "PONG_MISSED_NO_PRIOR_PROOF"
    elif age_ns > KALSHI_WS_MAX_PONG_AGE_NS:
        reason = "PONG_MISSED_PRIOR_PROOF_STALE"
    else:
        reason = "PONG_MISSED_PRIOR_PROOF_WITHIN_FROZEN_AGE"

    return ManualPongAttemptDecision(
        record_successful_pong=False,
        reason=reason,
        prior_pong_age_ns=age_ns,
    )


def validate_source_wait_seconds(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise B5R4ValidationError(
            "source wait seconds must be an integer"
        )
    if not MIN_SOURCE_WAIT_SECONDS <= value <= MAX_SOURCE_WAIT_SECONDS:
        raise B5R4ValidationError(
            "source wait seconds outside frozen B5-R4 bounds"
        )
    return int(value)


def file_sha256(path: str | Path) -> str:
    p = Path(path)
    h = sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json_atomic(path: str | Path, value: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    if tmp.exists():
        raise B5R4ValidationError(
            f"temporary output already exists: {tmp}"
        )
    payload = json.dumps(
        dict(value),
        indent=2,
        sort_keys=True,
    ) + "\n"
    with tmp.open("x", encoding="utf-8", newline="\n") as f:
        f.write(payload)
        f.flush()
        import os
        os.fsync(f.fileno())
    if p.exists():
        tmp.unlink(missing_ok=True)
        raise B5R4ValidationError(
            f"refusing to replace existing artifact: {p}"
        )
    tmp.replace(p)


def read_json_object(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise B5R4ValidationError("JSON artifact root must be object")
    return value


@dataclass(frozen=True)
class SecretScanResult:
    files_scanned: int
    bytes_scanned: int
    marker_counts: dict[str, int]

    @property
    def total_hits(self) -> int:
        return sum(self.marker_counts.values())


def scan_paths_for_secret_markers(
    paths: list[str | Path],
) -> SecretScanResult:
    counts = {
        marker.decode("ascii", errors="replace"): 0
        for marker in SECRET_MARKERS
    }
    files_scanned = 0
    bytes_scanned = 0

    for raw_path in paths:
        p = Path(raw_path)
        if not p.is_file():
            continue
        data = p.read_bytes()
        lowered = data.lower()
        files_scanned += 1
        bytes_scanned += len(data)
        for marker in SECRET_MARKERS:
            key = marker.decode("ascii", errors="replace")
            counts[key] += lowered.count(marker)

    return SecretScanResult(
        files_scanned=files_scanned,
        bytes_scanned=bytes_scanned,
        marker_counts=counts,
    )


def validate_final_live_summary(summary: Mapping[str, Any]) -> None:
    """Fail closed unless every frozen two-process assertion is proven."""
    required_exact = {
        "schema_version":
            "candidate_e_b5_r4_live_process_restart_validation.v1",
        "design_fingerprint": EXPECTED_B5_R4_DESIGN_FINGERPRINT,
        "process_1_prior_shutdown_status": "UNCLEAN_DETECTED",
        "process_2_initial_state": "BLOCKED_COINBASE",
        "process_2_final_state": "READY_READ_ONLY",
        "process_2_pending_after": 0,
        "process_2_prior_signal_reusable": False,
        "process_gap_canonical_backfill_allowed": False,
        "execution_mode_disabled": True,
        "raw_secret_marker_hits": 0,
        "canonical_prospective_db_created": False,
        "cohort_armed": False,
        "signals_computed": 0,
        "orders": 0,
        "production_writes": 0,
    }
    for key, expected in required_exact.items():
        if summary.get(key) != expected:
            raise B5R4ValidationError(
                f"live summary assertion failed: {key}="
                f"{summary.get(key)!r}, expected {expected!r}"
            )

    pid1 = summary.get("process_1_pid")
    pid2 = summary.get("process_2_pid")
    if (
        isinstance(pid1, bool)
        or isinstance(pid2, bool)
        or not isinstance(pid1, int)
        or not isinstance(pid2, int)
        or pid1 <= 0
        or pid2 <= 0
        or pid1 == pid2
    ):
        raise B5R4ValidationError(
            "process IDs must be distinct positive integers"
        )

    sid1 = str(summary.get("process_1_runtime_session_id", ""))
    sid2 = str(summary.get("process_2_runtime_session_id", ""))
    if not sid1 or not sid2 or sid1 == sid2:
        raise B5R4ValidationError(
            "runtime session IDs must be distinct and non-empty"
        )

    if summary.get("process_2_pending_examined", 0) < 1:
        raise B5R4ValidationError(
            "successor did not reconcile a pending durability decision"
        )
    if summary.get("process_2_verified", 0) < 1:
        raise B5R4ValidationError(
            "successor did not verify pending raw evidence"
        )

    for key in (
        "process_1_coinbase_reason",
        "process_1_kalshi_reason",
        "process_2_coinbase_reason",
        "process_2_kalshi_reason",
    ):
        if summary.get(key) != "PASS":
            raise B5R4ValidationError(
                f"fresh live source readiness failed: {key}"
            )

    if summary.get("process_2_coinbase_runtime_session_bound") is not True:
        raise B5R4ValidationError(
            "successor Coinbase state not bound to new runtime session"
        )
    if summary.get("process_2_kalshi_runtime_session_bound") is not True:
        raise B5R4ValidationError(
            "successor Kalshi state not bound to new runtime session"
        )
