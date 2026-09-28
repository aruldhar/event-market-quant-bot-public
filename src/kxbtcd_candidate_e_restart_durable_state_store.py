"""Checkpoint 21N-Z-E-B1: offline restart durable-state SQLite core.

This module implements only the persistence/session-lifecycle slice frozen by
Checkpoint 21N-Z-E-A.

It has no network client, no Coinbase/Kalshi transport, no Candidate-E signal
path, no prospective cohort arm path, no paper/demo broker, and no order path.

The only writable databases authorized by this B1 module are explicitly marked
noncanonical validation databases. Canonical prospective state remains blocked
until a later checkpoint implements the arm manifest and arm authorization.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator
from uuid import uuid4


EXPECTED_RESTART_DESIGN_FINGERPRINT = "40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda"
EXPECTED_ARCHITECTURE_FINGERPRINT = "3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7"
EXPECTED_CANDIDATE_FINGERPRINT = "b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc"
EXPECTED_PROSPECTIVE_WEEK_SHA256 = "60f24fd8424aff93a65006a87e31ef150417f3f393bf0a5de19f65ceeb4f2869"
EXPECTED_STRATEGY_ID = "kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2"
EXPECTED_PRIMARY_THRESHOLD = "0.02"

SCHEMA_VERSION = "candidate_e_restart_durable_state_store.v1"
EXECUTION_MODE = "disabled"

EXPECTED_TABLES = frozenset({
    "runtime_identity",
    "cohort_state",
    "runtime_sessions",
    "runtime_events",
    "source_watermarks",
    "decision_records",
    "observation_gaps",
})

CANONICAL_RELATIVE_PREFIX = Path("data/prospective/candidate_e")


class RestartDurableStateStoreError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise RestartDurableStateStoreError(message)


def _parse_utc(value: str, name: str) -> datetime:
    text = str(value).strip()
    if not text:
        fail(f"{name} must be non-empty")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RestartDurableStateStoreError(
            f"{name} must be ISO-8601 UTC"
        ) from exc
    if dt.tzinfo is None:
        fail(f"{name} must be timezone-aware")
    dt = dt.astimezone(timezone.utc)
    if dt.utcoffset() != timezone.utc.utcoffset(dt):
        fail(f"{name} must normalize to UTC")
    return dt


def _nonnegative_ns(value: int, name: str) -> int:
    try:
        result = int(value)
    except Exception as exc:
        raise RestartDurableStateStoreError(
            f"{name} must be integer-compatible"
        ) from exc
    if result < 0:
        fail(f"{name} must be nonnegative")
    return result


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class RestartDurableStateStore:
    """Offline-only SQLite durability/session core.

    The constructor intentionally requires ``validation_mode=True`` and refuses
    paths under the canonical prospective-data prefix. This prevents B1 from
    accidentally arming or creating a production-shaped canonical cohort DB.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        validation_mode: bool,
    ) -> None:
        if validation_mode is not True:
            fail(
                "B1 only authorizes noncanonical validation databases"
            )

        self.path = Path(path)
        normalized = Path(*self.path.parts)

        # Refuse obvious canonical prospective locations even in tests.
        parts_lower = tuple(part.lower() for part in normalized.parts)
        canonical_parts = tuple(
            part.lower() for part in CANONICAL_RELATIVE_PREFIX.parts
        )
        for i in range(
            0,
            len(parts_lower) - len(canonical_parts) + 1,
        ):
            if parts_lower[i:i + len(canonical_parts)] == canonical_parts:
                fail(
                    "B1 refuses canonical prospective database paths"
                )

        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.connection = sqlite3.connect(
            str(self.path),
            isolation_level=None,
            timeout=5.0,
        )
        self.connection.row_factory = sqlite3.Row

        try:
            self._configure_pragmas()
            self._create_schema()
            self._initialize_identity()
            self.verify_integrity()
            self.verify_schema()
            self.verify_pragmas()
        except Exception:
            self.connection.close()
            raise

    def _configure_pragmas(self) -> None:
        journal = self.connection.execute(
            "PRAGMA journal_mode=WAL"
        ).fetchone()[0]
        if str(journal).lower() != "wal":
            fail("SQLite WAL journal mode unavailable")

        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute("PRAGMA locking_mode=NORMAL")

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            BEGIN IMMEDIATE;

            CREATE TABLE IF NOT EXISTS runtime_identity (
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                schema_version TEXT NOT NULL,
                restart_design_fingerprint TEXT NOT NULL,
                architecture_fingerprint TEXT NOT NULL,
                candidate_fingerprint TEXT NOT NULL,
                prospective_week_sha256 TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                primary_threshold_dollars TEXT NOT NULL,
                execution_mode TEXT NOT NULL
                    CHECK(execution_mode='disabled'),
                created_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cohort_state (
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                cohort_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK(status IN ('ARMED','ENDED')),
                arm_time_utc TEXT NOT NULL,
                fixed_end_time_utc TEXT NOT NULL,
                duration_hours INTEGER NOT NULL CHECK(duration_hours=168),
                arm_git_commit TEXT NOT NULL,
                arm_manifest_sha256 TEXT NOT NULL,
                armed_by_session_id TEXT NOT NULL,
                ended_utc TEXT
            );

            CREATE TABLE IF NOT EXISTS runtime_sessions (
                session_id TEXT PRIMARY KEY,
                prior_session_id TEXT,
                boot_id TEXT NOT NULL,
                git_commit TEXT NOT NULL,
                started_utc TEXT NOT NULL,
                started_monotonic_ns INTEGER NOT NULL,
                last_heartbeat_utc TEXT NOT NULL,
                last_heartbeat_monotonic_ns INTEGER NOT NULL,
                ended_utc TEXT,
                ended_monotonic_ns INTEGER,
                shutdown_status TEXT NOT NULL
                    CHECK(shutdown_status IN (
                        'RUNNING','CLEAN','UNCLEAN_DETECTED'
                    )),
                unclean_detected_by_session_id TEXT
            );

            CREATE TABLE IF NOT EXISTS runtime_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                session_event_seq INTEGER NOT NULL,
                event_utc TEXT NOT NULL,
                event_monotonic_ns INTEGER,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(session_id, session_event_seq)
            );

            CREATE TABLE IF NOT EXISTS source_watermarks (
                session_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                last_raw_segment_id TEXT,
                last_raw_record_index INTEGER,
                last_source_identity_json TEXT,
                last_received_utc TEXT,
                last_received_monotonic_ns INTEGER,
                source_status TEXT NOT NULL,
                PRIMARY KEY(session_id, source_id)
            );

            CREATE TABLE IF NOT EXISTS decision_records (
                decision_record_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                session_decision_seq INTEGER NOT NULL,
                decision_utc TEXT NOT NULL,
                decision_monotonic_ns INTEGER NOT NULL,
                trigger_type TEXT NOT NULL,
                event_ticker TEXT NOT NULL,
                coinbase_minute_start_s INTEGER NOT NULL,
                coinbase_close_trade_id INTEGER,
                kalshi_book_generation INTEGER NOT NULL,
                kalshi_last_seq INTEGER,
                result_status TEXT NOT NULL,
                result_json TEXT NOT NULL,
                source_raw_refs_json TEXT NOT NULL,
                integrity_status TEXT NOT NULL
                    CHECK(integrity_status IN (
                        'PENDING_RAW_DURABILITY',
                        'VERIFIED',
                        'RAW_EVIDENCE_GAP'
                    )),
                UNIQUE(session_id, session_decision_seq)
            );

            CREATE TABLE IF NOT EXISTS observation_gaps (
                gap_id TEXT PRIMARY KEY,
                gap_kind TEXT NOT NULL,
                reason TEXT NOT NULL,
                start_utc TEXT NOT NULL,
                end_utc TEXT,
                start_basis TEXT NOT NULL,
                prior_session_id TEXT,
                next_session_id TEXT,
                source_id TEXT,
                canonical_backfill_allowed INTEGER NOT NULL
                    CHECK(canonical_backfill_allowed=0)
            );

            COMMIT;
            """
        )

    def _initialize_identity(self) -> None:
        row = self.connection.execute(
            "SELECT * FROM runtime_identity WHERE singleton_id=1"
        ).fetchone()

        if row is None:
            # Fixed synthetic creation timestamp: B1 identity exists only to
            # validate immutable fields and schema behavior.
            self.connection.execute(
                """
                INSERT INTO runtime_identity (
                    singleton_id,
                    schema_version,
                    restart_design_fingerprint,
                    architecture_fingerprint,
                    candidate_fingerprint,
                    prospective_week_sha256,
                    strategy_id,
                    primary_threshold_dollars,
                    execution_mode,
                    created_utc
                ) VALUES (1,?,?,?,?,?,?,?,?,?)
                """,
                (
                    SCHEMA_VERSION,
                    EXPECTED_RESTART_DESIGN_FINGERPRINT,
                    EXPECTED_ARCHITECTURE_FINGERPRINT,
                    EXPECTED_CANDIDATE_FINGERPRINT,
                    EXPECTED_PROSPECTIVE_WEEK_SHA256,
                    EXPECTED_STRATEGY_ID,
                    EXPECTED_PRIMARY_THRESHOLD,
                    EXECUTION_MODE,
                    "1970-01-01T00:00:00Z",
                ),
            )
            return

        expected = {
            "schema_version": SCHEMA_VERSION,
            "restart_design_fingerprint":
                EXPECTED_RESTART_DESIGN_FINGERPRINT,
            "architecture_fingerprint":
                EXPECTED_ARCHITECTURE_FINGERPRINT,
            "candidate_fingerprint":
                EXPECTED_CANDIDATE_FINGERPRINT,
            "prospective_week_sha256":
                EXPECTED_PROSPECTIVE_WEEK_SHA256,
            "strategy_id": EXPECTED_STRATEGY_ID,
            "primary_threshold_dollars":
                EXPECTED_PRIMARY_THRESHOLD,
            "execution_mode": EXECUTION_MODE,
        }
        for key, value in expected.items():
            if row[key] != value:
                fail(f"runtime identity mismatch: {key}")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    def verify_integrity(self) -> None:
        rows = self.connection.execute(
            "PRAGMA integrity_check"
        ).fetchall()
        values = [str(row[0]) for row in rows]
        if values != ["ok"]:
            fail(
                "SQLite integrity_check failed: "
                + "; ".join(values)
            )

    def verify_schema(self) -> None:
        actual = {
            str(row[0])
            for row in self.connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        if actual != EXPECTED_TABLES:
            fail(
                "SQLite table set mismatch: "
                f"actual={sorted(actual)}"
            )

    def verify_pragmas(self) -> dict[str, Any]:
        values = {
            "journal_mode": str(
                self.connection.execute(
                    "PRAGMA journal_mode"
                ).fetchone()[0]
            ).lower(),
            "synchronous": int(
                self.connection.execute(
                    "PRAGMA synchronous"
                ).fetchone()[0]
            ),
            "foreign_keys": int(
                self.connection.execute(
                    "PRAGMA foreign_keys"
                ).fetchone()[0]
            ),
            "busy_timeout_ms": int(
                self.connection.execute(
                    "PRAGMA busy_timeout"
                ).fetchone()[0]
            ),
            "locking_mode": str(
                self.connection.execute(
                    "PRAGMA locking_mode"
                ).fetchone()[0]
            ).lower(),
        }

        expected = {
            "journal_mode": "wal",
            "synchronous": 2,  # SQLite numeric value for FULL
            "foreign_keys": 1,
            "busy_timeout_ms": 5000,
            "locking_mode": "normal",
        }
        if values != expected:
            fail(
                "SQLite pragma mismatch: "
                f"actual={values} expected={expected}"
            )
        return values

    def _latest_session(self) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT *
            FROM runtime_sessions
            ORDER BY started_utc DESC, session_id DESC
            LIMIT 1
            """
        ).fetchone()

    def start_session(
        self,
        *,
        boot_id: str,
        git_commit: str,
        started_utc: str,
        started_monotonic_ns: int,
        session_id: str | None = None,
    ) -> str:
        boot = str(boot_id).strip()
        commit = str(git_commit).strip()
        if not boot:
            fail("boot_id must be non-empty")
        if not commit:
            fail("git_commit must be non-empty")

        started_dt = _parse_utc(started_utc, "started_utc")
        started_ns = _nonnegative_ns(
            started_monotonic_ns,
            "started_monotonic_ns",
        )

        sid = (
            str(session_id).strip()
            if session_id is not None
            else str(uuid4())
        )
        if not sid:
            fail("session_id must be non-empty")

        with self.transaction():
            prior = self._latest_session()

            if prior is not None:
                prior_started = _parse_utc(
                    prior["started_utc"],
                    "prior.started_utc",
                )
                if started_dt < prior_started:
                    fail(
                        "new session UTC start precedes prior session start"
                    )

                prior_status = prior["shutdown_status"]

                if prior_status == "RUNNING":
                    gap_start = prior["last_heartbeat_utc"]
                    _parse_utc(
                        gap_start,
                        "prior.last_heartbeat_utc",
                    )
                    if started_dt < _parse_utc(
                        gap_start,
                        "prior.last_heartbeat_utc",
                    ):
                        fail(
                            "new session starts before prior durable heartbeat"
                        )

                    self.connection.execute(
                        """
                        UPDATE runtime_sessions
                        SET shutdown_status='UNCLEAN_DETECTED',
                            unclean_detected_by_session_id=?
                        WHERE session_id=?
                          AND shutdown_status='RUNNING'
                        """,
                        (sid, prior["session_id"]),
                    )

                    self._insert_gap(
                        gap_kind="PROCESS_DISCONTINUITY",
                        reason="UNCLEAN_PRIOR_SESSION",
                        start_utc=gap_start,
                        end_utc=started_utc,
                        start_basis="PRIOR_DURABLE_HEARTBEAT",
                        prior_session_id=prior["session_id"],
                        next_session_id=sid,
                    )

                elif prior_status == "CLEAN":
                    if prior["ended_utc"] is None:
                        fail("CLEAN prior session missing ended_utc")

                    prior_end = _parse_utc(
                        prior["ended_utc"],
                        "prior.ended_utc",
                    )
                    if started_dt < prior_end:
                        fail(
                            "new session starts before clean prior end"
                        )

                    if started_dt > prior_end:
                        self._insert_gap(
                            gap_kind="PROCESS_DISCONTINUITY",
                            reason="CLEAN_PROCESS_STOP",
                            start_utc=prior["ended_utc"],
                            end_utc=started_utc,
                            start_basis="PRIOR_CLEAN_END",
                            prior_session_id=prior["session_id"],
                            next_session_id=sid,
                        )

                elif prior_status == "UNCLEAN_DETECTED":
                    # The prior crash was already classified by an earlier
                    # successor. It is historical and must not be reclassified.
                    pass
                else:
                    fail("unknown prior shutdown status")

                prior_session_id = prior["session_id"]
            else:
                prior_session_id = None

            try:
                self.connection.execute(
                    """
                    INSERT INTO runtime_sessions (
                        session_id,
                        prior_session_id,
                        boot_id,
                        git_commit,
                        started_utc,
                        started_monotonic_ns,
                        last_heartbeat_utc,
                        last_heartbeat_monotonic_ns,
                        ended_utc,
                        ended_monotonic_ns,
                        shutdown_status,
                        unclean_detected_by_session_id
                    ) VALUES (?,?,?,?,?,?,?,?,NULL,NULL,'RUNNING',NULL)
                    """,
                    (
                        sid,
                        prior_session_id,
                        boot,
                        commit,
                        started_utc,
                        started_ns,
                        started_utc,
                        started_ns,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise RestartDurableStateStoreError(
                    "session insert failed"
                ) from exc

        return sid

    def _insert_gap(
        self,
        *,
        gap_kind: str,
        reason: str,
        start_utc: str,
        end_utc: str | None,
        start_basis: str,
        prior_session_id: str | None,
        next_session_id: str | None,
        source_id: str | None = None,
    ) -> str:
        _parse_utc(start_utc, "gap.start_utc")
        if end_utc is not None:
            if _parse_utc(end_utc, "gap.end_utc") < _parse_utc(
                start_utc,
                "gap.start_utc",
            ):
                fail("gap end precedes gap start")

        gap_id = str(uuid4())

        self.connection.execute(
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
            ) VALUES (?,?,?,?,?,?,?,?,?,0)
            """,
            (
                gap_id,
                str(gap_kind),
                str(reason),
                start_utc,
                end_utc,
                str(start_basis),
                prior_session_id,
                next_session_id,
                source_id,
            ),
        )
        return gap_id

    def heartbeat(
        self,
        session_id: str,
        *,
        heartbeat_utc: str,
        heartbeat_monotonic_ns: int,
    ) -> None:
        heartbeat_dt = _parse_utc(
            heartbeat_utc,
            "heartbeat_utc",
        )
        heartbeat_ns = _nonnegative_ns(
            heartbeat_monotonic_ns,
            "heartbeat_monotonic_ns",
        )

        with self.transaction():
            row = self.connection.execute(
                """
                SELECT *
                FROM runtime_sessions
                WHERE session_id=?
                """,
                (str(session_id),),
            ).fetchone()
            if row is None:
                fail("heartbeat session not found")
            if row["shutdown_status"] != "RUNNING":
                fail("heartbeat requires RUNNING session")

            prior_dt = _parse_utc(
                row["last_heartbeat_utc"],
                "prior heartbeat UTC",
            )
            prior_ns = int(
                row["last_heartbeat_monotonic_ns"]
            )

            if heartbeat_dt < prior_dt:
                fail("heartbeat UTC moved backwards")
            if heartbeat_ns < prior_ns:
                fail(
                    "heartbeat monotonic time moved backwards "
                    "within session"
                )

            self.connection.execute(
                """
                UPDATE runtime_sessions
                SET last_heartbeat_utc=?,
                    last_heartbeat_monotonic_ns=?
                WHERE session_id=?
                  AND shutdown_status='RUNNING'
                """,
                (
                    heartbeat_utc,
                    heartbeat_ns,
                    str(session_id),
                ),
            )

    def clean_shutdown(
        self,
        session_id: str,
        *,
        ended_utc: str,
        ended_monotonic_ns: int,
    ) -> None:
        ended_dt = _parse_utc(
            ended_utc,
            "ended_utc",
        )
        ended_ns = _nonnegative_ns(
            ended_monotonic_ns,
            "ended_monotonic_ns",
        )

        with self.transaction():
            row = self.connection.execute(
                """
                SELECT *
                FROM runtime_sessions
                WHERE session_id=?
                """,
                (str(session_id),),
            ).fetchone()
            if row is None:
                fail("clean shutdown session not found")
            if row["shutdown_status"] != "RUNNING":
                fail("clean shutdown requires RUNNING session")

            if ended_dt < _parse_utc(
                row["last_heartbeat_utc"],
                "last heartbeat UTC",
            ):
                fail("clean end UTC precedes last heartbeat")
            if ended_ns < int(
                row["last_heartbeat_monotonic_ns"]
            ):
                fail(
                    "clean end monotonic precedes last heartbeat"
                )

            self.connection.execute(
                """
                UPDATE runtime_sessions
                SET last_heartbeat_utc=?,
                    last_heartbeat_monotonic_ns=?,
                    ended_utc=?,
                    ended_monotonic_ns=?,
                    shutdown_status='CLEAN'
                WHERE session_id=?
                  AND shutdown_status='RUNNING'
                """,
                (
                    ended_utc,
                    ended_ns,
                    ended_utc,
                    ended_ns,
                    str(session_id),
                ),
            )

    def session(self, session_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT *
            FROM runtime_sessions
            WHERE session_id=?
            """,
            (str(session_id),),
        ).fetchone()
        if row is None:
            fail("session not found")
        return dict(row)

    def sessions(self) -> tuple[dict[str, Any], ...]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM runtime_sessions
            ORDER BY started_utc, session_id
            """
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def observation_gaps(
        self,
    ) -> tuple[dict[str, Any], ...]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM observation_gaps
            ORDER BY start_utc, gap_id
            """
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def identity(self) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT *
            FROM runtime_identity
            WHERE singleton_id=1
            """
        ).fetchone()
        if row is None:
            fail("runtime identity missing")
        return dict(row)

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None  # type: ignore[assignment]

    def __enter__(self) -> "RestartDurableStateStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
