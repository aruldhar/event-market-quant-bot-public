"""Checkpoint 21N-Z-E-B2: offline identity and raw-reference reconciliation.

This module extends the frozen restart work without arming the real prospective
cohort and without connecting to Coinbase or Kalshi.

It provides:
- noncanonical validation arm-manifest identity checking;
- create-exclusive runtime-session raw segments with exact raw references;
- offline raw-segment auditing that preserves partial trailing bytes;
- validation decision/source-watermark atomic commits;
- pending decision reconciliation to VERIFIED or RAW_EVIDENCE_GAP.

No signal generation, paper/demo execution, or order path exists here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from src.kxbtcd_candidate_e_raw_journal_security import (
    RawJournalSecurityError,
    sanitize_request_identity,
)
from src.kxbtcd_candidate_e_restart_durable_state_store import (
    RestartDurableStateStore,
    RestartDurableStateStoreError,
)


EXPECTED_RESTART_DESIGN_FINGERPRINT = "40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda"
EXPECTED_ARCHITECTURE_FINGERPRINT = "3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7"
EXPECTED_CANDIDATE_FINGERPRINT = "b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc"
EXPECTED_PROSPECTIVE_WEEK_SHA256 = "60f24fd8424aff93a65006a87e31ef150417f3f393bf0a5de19f65ceeb4f2869"
EXPECTED_STRATEGY_ID = "kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2"
EXPECTED_PRIMARY_THRESHOLD = "0.02"
EXECUTION_MODE = "disabled"

RAW_SCHEMA = "candidate_e_runtime_raw_record.v2"
CANONICAL_PREFIX = Path("data/prospective/candidate_e")

ALLOWED_SOURCES = frozenset({
    "coinbase_exchange_ws",
    "coinbase_exchange_rest",
    "kalshi_production_ws",
    "kalshi_production_rest",
})


class RestartReconciliationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise RestartReconciliationError(message)


def _parse_utc(value: str, name: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RestartReconciliationError(
            f"{name} must be ISO-8601"
        ) from exc
    if dt.tzinfo is None:
        fail(f"{name} must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _contains_canonical_prefix(path: Path) -> bool:
    parts = tuple(part.lower() for part in path.parts)
    wanted = tuple(part.lower() for part in CANONICAL_PREFIX.parts)
    for i in range(0, len(parts) - len(wanted) + 1):
        if parts[i:i + len(wanted)] == wanted:
            return True
    return False


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class RawRecordRef:
    runtime_session_id: str
    raw_segment_id: str
    raw_record_index: int
    line_sha256: str

    def jsonable(self) -> dict[str, Any]:
        return {
            "runtime_session_id": self.runtime_session_id,
            "raw_segment_id": self.raw_segment_id,
            "raw_record_index": self.raw_record_index,
            "line_sha256": self.line_sha256,
        }


@dataclass(frozen=True)
class RawSegmentAudit:
    path: str
    runtime_session_id: str
    raw_segment_id: str
    valid_record_count: int
    valid_refs: tuple[RawRecordRef, ...]
    partial_trailing_bytes_present: bool
    partial_trailing_bytes_sha256: str | None
    full_file_sha256: str


class RestartSessionRawJournal:
    """Create-exclusive raw segment tied to one runtime session.

    This does not replace the already-accepted Z-D smoke journal. It is the
    restart-aware segment format for later long-running runtime integration.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        runtime_session_id: str,
        raw_segment_id: str,
        fsync_interval_ns: int = 1_000_000_000,
    ) -> None:
        self.path = Path(path)
        if _contains_canonical_prefix(self.path):
            fail("B2 refuses canonical prospective raw paths")

        self.runtime_session_id = str(runtime_session_id).strip()
        self.raw_segment_id = str(raw_segment_id).strip()
        if not self.runtime_session_id:
            fail("runtime_session_id required")
        if not self.raw_segment_id:
            fail("raw_segment_id required")
        if int(fsync_interval_ns) <= 0:
            fail("fsync_interval_ns must be positive")

        self.fsync_interval_ns = int(fsync_interval_ns)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # x = create exclusive: never append into an old session segment.
        try:
            self._file = self.path.open(
                "x",
                encoding="utf-8",
                newline="\n",
            )
        except FileExistsError as exc:
            raise RestartReconciliationError(
                "raw segment already exists; restart may not append to it"
            ) from exc

        self._closed = False
        self._last_append_ns: int | None = None
        self._last_fsync_ns: int | None = None
        self.record_count = 0

    def append(
        self,
        *,
        source: str,
        transport: str,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        request_identity: Mapping[str, Any] | None = None,
    ) -> RawRecordRef:
        if self._closed:
            fail("raw journal closed")
        if source not in ALLOWED_SOURCES:
            fail("unregistered raw source")

        ns = int(received_monotonic_ns)
        if ns < 0:
            fail("received_monotonic_ns must be nonnegative")
        if (
            self._last_append_ns is not None
            and ns < self._last_append_ns
        ):
            fail("monotonic receive time regressed within session")

        _parse_utc(received_utc, "received_utc")

        try:
            safe_request_identity = sanitize_request_identity(request_identity)
        except RawJournalSecurityError as exc:
            raise RestartReconciliationError(str(exc)) from exc

        index = self.record_count + 1
        base = {
            "schema_version": RAW_SCHEMA,
            "runtime_session_id": self.runtime_session_id,
            "raw_segment_id": self.raw_segment_id,
            "raw_record_index": index,
            "source": source,
            "transport": str(transport),
            "received_utc": str(received_utc),
            "received_monotonic_ns": ns,
            "request_identity": safe_request_identity,
            "raw_text": str(raw_text),
        }

        payload_without_hash = _canonical_json(base)
        payload_sha = sha256(
            payload_without_hash.encode("utf-8")
        ).hexdigest()

        record = dict(base)
        record["payload_sha256"] = payload_sha

        line = _canonical_json(record) + "\n"
        line_sha = sha256(line.encode("utf-8")).hexdigest()

        self._file.write(line)
        self._file.flush()

        self.record_count = index
        self._last_append_ns = ns

        if (
            self._last_fsync_ns is None
            or ns - self._last_fsync_ns >= self.fsync_interval_ns
        ):
            os.fsync(self._file.fileno())
            self._last_fsync_ns = ns

        return RawRecordRef(
            runtime_session_id=self.runtime_session_id,
            raw_segment_id=self.raw_segment_id,
            raw_record_index=index,
            line_sha256=line_sha,
        )

    def force_fsync(self) -> None:
        if self._closed:
            fail("raw journal closed")
        self._file.flush()
        os.fsync(self._file.fileno())
        if self._last_append_ns is not None:
            self._last_fsync_ns = self._last_append_ns

    def close(self) -> None:
        if self._closed:
            return
        self._file.flush()
        os.fsync(self._file.fileno())
        self._file.close()
        self._closed = True

    def __enter__(self) -> "RestartSessionRawJournal":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def audit_raw_segment(
    path: str | Path,
    *,
    expected_runtime_session_id: str,
    expected_raw_segment_id: str,
) -> RawSegmentAudit:
    """Audit complete newline-terminated records without modifying the file."""
    p = Path(path)
    data = p.read_bytes()

    full_hash = sha256(data).hexdigest()

    complete_end = data.rfind(b"\n")
    if complete_end < 0:
        complete = b""
        trailing = data
    else:
        complete = data[:complete_end + 1]
        trailing = data[complete_end + 1:]

    refs: list[RawRecordRef] = []
    expected_index = 1

    for raw_line in complete.splitlines(keepends=True):
        if not raw_line.endswith(b"\n"):
            fail("internal audit error: complete line missing newline")

        try:
            text = raw_line[:-1].decode("utf-8")
            record = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RestartReconciliationError(
                "malformed complete raw record"
            ) from exc

        if record.get("schema_version") != RAW_SCHEMA:
            fail("raw schema mismatch")
        if record.get("runtime_session_id") != expected_runtime_session_id:
            fail("raw runtime session mismatch")
        if record.get("raw_segment_id") != expected_raw_segment_id:
            fail("raw segment ID mismatch")
        if int(record.get("raw_record_index", -1)) != expected_index:
            fail("raw record index discontinuity")

        stored_payload_sha = record.get("payload_sha256")
        unhashed = dict(record)
        unhashed.pop("payload_sha256", None)
        actual_payload_sha = sha256(
            _canonical_json(unhashed).encode("utf-8")
        ).hexdigest()
        if stored_payload_sha != actual_payload_sha:
            fail("raw payload SHA mismatch")

        refs.append(
            RawRecordRef(
                runtime_session_id=expected_runtime_session_id,
                raw_segment_id=expected_raw_segment_id,
                raw_record_index=expected_index,
                line_sha256=sha256(raw_line).hexdigest(),
            )
        )
        expected_index += 1

    trailing_hash = (
        sha256(trailing).hexdigest()
        if trailing
        else None
    )

    return RawSegmentAudit(
        path=str(p),
        runtime_session_id=expected_runtime_session_id,
        raw_segment_id=expected_raw_segment_id,
        valid_record_count=len(refs),
        valid_refs=tuple(refs),
        partial_trailing_bytes_present=bool(trailing),
        partial_trailing_bytes_sha256=trailing_hash,
        full_file_sha256=full_hash,
    )


def build_validation_arm_manifest(
    *,
    cohort_id: str,
    arm_time_utc: str,
    arm_git_commit: str,
) -> dict[str, Any]:
    """Build a synthetic validation manifest only; this does not arm anything."""
    arm_dt = _parse_utc(arm_time_utc, "arm_time_utc")
    end_dt = arm_dt + timedelta(hours=168)

    return {
        "schema_version": "candidate_e_prospective_arm_manifest.v1",
        "validation_only": True,
        "cohort_id": str(cohort_id),
        "arm_time_utc": arm_dt.isoformat().replace("+00:00", "Z"),
        "fixed_end_time_utc":
            end_dt.isoformat().replace("+00:00", "Z"),
        "duration_hours": 168,
        "arm_git_commit": str(arm_git_commit),
        "restart_design_fingerprint":
            EXPECTED_RESTART_DESIGN_FINGERPRINT,
        "architecture_fingerprint":
            EXPECTED_ARCHITECTURE_FINGERPRINT,
        "candidate_fingerprint":
            EXPECTED_CANDIDATE_FINGERPRINT,
        "prospective_week_sha256":
            EXPECTED_PROSPECTIVE_WEEK_SHA256,
        "strategy_id": EXPECTED_STRATEGY_ID,
        "primary_net_edge_threshold_dollars":
            EXPECTED_PRIMARY_THRESHOLD,
        "execution_mode": EXECUTION_MODE,
    }


def write_validation_arm_manifest_once(
    path: str | Path,
    manifest: Mapping[str, Any],
) -> str:
    """Create a noncanonical validation manifest atomically and fsync the file.

    Directory fsync is deferred to Linux production integration because Windows
    does not expose portable directory fsync semantics through Python.
    This B2 helper is validation-only and is explicitly refused on canonical
    prospective paths.
    """
    p = Path(path)
    if _contains_canonical_prefix(p):
        fail("B2 refuses canonical prospective manifest paths")
    if p.exists():
        fail("validation arm manifest already exists")

    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + "." + str(uuid4()) + ".tmp")

    data = (
        json.dumps(
            dict(manifest),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")

    try:
        with tmp.open("xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink()

    return sha256(data).hexdigest()


def validate_arm_manifest_identity(
    *,
    store: RestartDurableStateStore,
    manifest_path: str | Path,
    current_git_commit: str,
) -> dict[str, Any]:
    p = Path(manifest_path)
    if _contains_canonical_prefix(p):
        fail("B2 refuses canonical prospective manifest paths")

    raw = p.read_bytes()
    manifest_sha = sha256(raw).hexdigest()
    try:
        m = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RestartReconciliationError(
            "arm manifest malformed"
        ) from exc

    required = {
        "cohort_id",
        "arm_time_utc",
        "fixed_end_time_utc",
        "duration_hours",
        "arm_git_commit",
        "restart_design_fingerprint",
        "architecture_fingerprint",
        "candidate_fingerprint",
        "prospective_week_sha256",
        "strategy_id",
        "primary_net_edge_threshold_dollars",
        "execution_mode",
    }
    missing = sorted(required - set(m))
    if missing:
        fail(f"arm manifest missing fields: {missing}")

    if m.get("validation_only") is not True:
        fail("B2 accepts synthetic validation manifests only")
    if m["duration_hours"] != 168:
        fail("arm duration mismatch")
    if m["execution_mode"] != EXECUTION_MODE:
        fail("arm execution mode mismatch")
    if m["restart_design_fingerprint"] != EXPECTED_RESTART_DESIGN_FINGERPRINT:
        fail("restart design fingerprint mismatch")
    if m["architecture_fingerprint"] != EXPECTED_ARCHITECTURE_FINGERPRINT:
        fail("architecture fingerprint mismatch")
    if m["candidate_fingerprint"] != EXPECTED_CANDIDATE_FINGERPRINT:
        fail("candidate fingerprint mismatch")
    if m["prospective_week_sha256"] != EXPECTED_PROSPECTIVE_WEEK_SHA256:
        fail("prospective-week SHA mismatch")
    if m["strategy_id"] != EXPECTED_STRATEGY_ID:
        fail("strategy ID mismatch")
    if m["primary_net_edge_threshold_dollars"] != EXPECTED_PRIMARY_THRESHOLD:
        fail("primary threshold mismatch")

    arm = _parse_utc(m["arm_time_utc"], "arm_time_utc")
    end = _parse_utc(m["fixed_end_time_utc"], "fixed_end_time_utc")
    if end != arm + timedelta(hours=168):
        fail("fixed end is not exactly arm + 168 hours")

    if str(current_git_commit) != str(m["arm_git_commit"]):
        fail("current Git commit does not equal arm Git commit")

    row = store.connection.execute(
        "SELECT * FROM cohort_state WHERE singleton_id=1"
    ).fetchone()
    if row is None:
        fail("SQLite cohort_state missing")

    checks = {
        "cohort_id": m["cohort_id"],
        "arm_time_utc": m["arm_time_utc"],
        "fixed_end_time_utc": m["fixed_end_time_utc"],
        "duration_hours": 168,
        "arm_git_commit": m["arm_git_commit"],
        "arm_manifest_sha256": manifest_sha,
    }
    for key, expected in checks.items():
        if row[key] != expected:
            fail(f"manifest/SQLite identity mismatch: {key}")

    if row["status"] not in ("ARMED", "ENDED"):
        fail("invalid synthetic cohort status")

    return {
        "cohort_id": m["cohort_id"],
        "manifest_sha256": manifest_sha,
        "status": row["status"],
        "fixed_end_time_utc": m["fixed_end_time_utc"],
    }


def install_validation_cohort_identity(
    *,
    store: RestartDurableStateStore,
    manifest_path: str | Path,
    armed_by_session_id: str,
) -> None:
    """Populate the B1 cohort table only inside a noncanonical validation DB."""
    if _contains_canonical_prefix(store.path):
        fail("validation cohort install refuses canonical store")

    p = Path(manifest_path)
    raw = p.read_bytes()
    manifest_sha = sha256(raw).hexdigest()
    m = json.loads(raw.decode("utf-8"))
    if m.get("validation_only") is not True:
        fail("validation_only manifest required")

    with store.transaction():
        existing = store.connection.execute(
            "SELECT singleton_id FROM cohort_state WHERE singleton_id=1"
        ).fetchone()
        if existing is not None:
            fail("validation cohort identity already installed")

        store.connection.execute(
            """
            INSERT INTO cohort_state (
                singleton_id,
                cohort_id,
                status,
                arm_time_utc,
                fixed_end_time_utc,
                duration_hours,
                arm_git_commit,
                arm_manifest_sha256,
                armed_by_session_id,
                ended_utc
            ) VALUES (1,?,'ARMED',?,?,?,?,?,?,NULL)
            """,
            (
                m["cohort_id"],
                m["arm_time_utc"],
                m["fixed_end_time_utc"],
                168,
                m["arm_git_commit"],
                manifest_sha,
                str(armed_by_session_id),
            ),
        )


def commit_validation_decision(
    *,
    store: RestartDurableStateStore,
    session_id: str,
    session_decision_seq: int,
    decision_utc: str,
    decision_monotonic_ns: int,
    event_ticker: str,
    raw_refs: Sequence[RawRecordRef],
    source_id: str,
    raw_segment_id: str,
    last_raw_record_index: int,
) -> str:
    """Atomically commit a synthetic decision and source watermark."""
    _parse_utc(decision_utc, "decision_utc")
    if int(session_decision_seq) <= 0:
        fail("session_decision_seq must be positive")
    if int(decision_monotonic_ns) < 0:
        fail("decision_monotonic_ns must be nonnegative")
    if not raw_refs:
        fail("at least one raw reference required")

    decision_id = str(uuid4())

    refs_json = _canonical_json(
        [ref.jsonable() for ref in raw_refs]
    )
    result_json = _canonical_json({
        "research_role":
            "B2_VALIDATION_ONLY_NO_SIGNAL_NO_EXECUTION",
        "primary_signal": None,
    })

    with store.transaction():
        session = store.connection.execute(
            """
            SELECT shutdown_status
            FROM runtime_sessions
            WHERE session_id=?
            """,
            (str(session_id),),
        ).fetchone()
        if session is None:
            fail("decision session missing")
        if session["shutdown_status"] != "RUNNING":
            fail("decision requires RUNNING session")

        store.connection.execute(
            """
            INSERT INTO decision_records (
                decision_record_id,
                session_id,
                session_decision_seq,
                decision_utc,
                decision_monotonic_ns,
                trigger_type,
                event_ticker,
                coinbase_minute_start_s,
                coinbase_close_trade_id,
                kalshi_book_generation,
                kalshi_last_seq,
                result_status,
                result_json,
                source_raw_refs_json,
                integrity_status
            ) VALUES (
                ?,?,?,?,?,?,
                ?,0,NULL,0,NULL,
                'VALIDATION_ONLY',
                ?,?,
                'PENDING_RAW_DURABILITY'
            )
            """,
            (
                decision_id,
                str(session_id),
                int(session_decision_seq),
                decision_utc,
                int(decision_monotonic_ns),
                "B2_SYNTHETIC",
                str(event_ticker),
                result_json,
                refs_json,
            ),
        )

        store.connection.execute(
            """
            INSERT INTO source_watermarks (
                session_id,
                source_id,
                last_raw_segment_id,
                last_raw_record_index,
                last_source_identity_json,
                last_received_utc,
                last_received_monotonic_ns,
                source_status
            ) VALUES (?,?,?,?,?,?,?,'VALIDATION_ONLY')
            ON CONFLICT(session_id,source_id)
            DO UPDATE SET
                last_raw_segment_id=excluded.last_raw_segment_id,
                last_raw_record_index=excluded.last_raw_record_index,
                last_source_identity_json=excluded.last_source_identity_json,
                last_received_utc=excluded.last_received_utc,
                last_received_monotonic_ns=excluded.last_received_monotonic_ns,
                source_status=excluded.source_status
            """,
            (
                str(session_id),
                str(source_id),
                str(raw_segment_id),
                int(last_raw_record_index),
                _canonical_json({"validation_only": True}),
                decision_utc,
                int(decision_monotonic_ns),
            ),
        )

    return decision_id


def reconcile_pending_decisions(
    *,
    store: RestartDurableStateStore,
    raw_segments: Mapping[
        tuple[str, str],
        str | Path,
    ],
) -> dict[str, int]:
    """Reconcile pending decisions without reconstructing missing evidence."""
    audits: dict[
        tuple[str, str],
        RawSegmentAudit,
    ] = {}

    def audit_for(session_id: str, segment_id: str) -> RawSegmentAudit | None:
        key = (session_id, segment_id)
        if key in audits:
            return audits[key]
        path = raw_segments.get(key)
        if path is None:
            return None
        audit = audit_raw_segment(
            path,
            expected_runtime_session_id=session_id,
            expected_raw_segment_id=segment_id,
        )
        audits[key] = audit
        return audit

    rows = store.connection.execute(
        """
        SELECT *
        FROM decision_records
        WHERE integrity_status='PENDING_RAW_DURABILITY'
        ORDER BY session_id, session_decision_seq
        """
    ).fetchall()

    verified = 0
    gaps = 0

    for row in rows:
        try:
            refs_payload = json.loads(row["source_raw_refs_json"])
        except json.JSONDecodeError:
            refs_payload = None

        ok = isinstance(refs_payload, list) and bool(refs_payload)

        if ok:
            for item in refs_payload:
                if not isinstance(item, dict):
                    ok = False
                    break

                session_id = str(item.get("runtime_session_id", ""))
                segment_id = str(item.get("raw_segment_id", ""))
                try:
                    index = int(item.get("raw_record_index"))
                except Exception:
                    ok = False
                    break
                wanted_sha = str(item.get("line_sha256", ""))

                audit = audit_for(session_id, segment_id)
                if audit is None:
                    ok = False
                    break

                by_index = {
                    ref.raw_record_index: ref
                    for ref in audit.valid_refs
                }
                actual = by_index.get(index)
                if actual is None or actual.line_sha256 != wanted_sha:
                    ok = False
                    break

        with store.transaction():
            if ok:
                store.connection.execute(
                    """
                    UPDATE decision_records
                    SET integrity_status='VERIFIED'
                    WHERE decision_record_id=?
                      AND integrity_status='PENDING_RAW_DURABILITY'
                    """,
                    (row["decision_record_id"],),
                )
                verified += 1
            else:
                store.connection.execute(
                    """
                    UPDATE decision_records
                    SET integrity_status='RAW_EVIDENCE_GAP'
                    WHERE decision_record_id=?
                      AND integrity_status='PENDING_RAW_DURABILITY'
                    """,
                    (row["decision_record_id"],),
                )
                store.connection.execute(
                    """
                    INSERT INTO observation_gaps (
                        gap_id,
                        gap_kind,
                        reason,
                        start_utc,
                        end_utc,
                        start_basis,
                        prior_session_id,
                        next_session_id,
                        source_id,
                        canonical_backfill_allowed
                    ) VALUES (
                        ?,
                        'DURABILITY_RECONCILIATION',
                        'MISSING_OR_DAMAGED_RAW_REFERENCE',
                        ?,?,
                        'DECISION_UTC_EVIDENCE_GAP',
                        ?,NULL,NULL,0
                    )
                    """,
                    (
                        str(uuid4()),
                        row["decision_utc"],
                        row["decision_utc"],
                        row["session_id"],
                    ),
                )
                gaps += 1

    return {
        "pending_examined": len(rows),
        "verified": verified,
        "raw_evidence_gaps": gaps,
    }
