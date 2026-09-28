from pathlib import Path
import sqlite3

import pytest

from src.kxbtcd_candidate_e_restart_durable_state_store import (
    EXPECTED_TABLES,
    RestartDurableStateStore,
    RestartDurableStateStoreError,
)


COMMIT = "ca539b12de88980ada4ae8e8b0f0ed574017b29f"
BOOT_A = "synthetic-boot-a"
BOOT_B = "synthetic-boot-b"


def open_store(tmp_path: Path) -> RestartDurableStateStore:
    return RestartDurableStateStore(
        tmp_path / "state.sqlite3",
        validation_mode=True,
    )


def test_schema_has_exact_seven_tables(tmp_path):
    with open_store(tmp_path) as store:
        actual = {
            row[0]
            for row in store.connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        assert actual == EXPECTED_TABLES


def test_required_pragmas_are_active(tmp_path):
    with open_store(tmp_path) as store:
        assert store.verify_pragmas() == {
            "journal_mode": "wal",
            "synchronous": 2,
            "foreign_keys": 1,
            "busy_timeout_ms": 5000,
            "locking_mode": "normal",
        }


def test_integrity_check_is_ok(tmp_path):
    with open_store(tmp_path) as store:
        store.verify_integrity()
        assert (
            store.connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
            == "ok"
        )


def test_identity_is_disabled_and_frozen(tmp_path):
    with open_store(tmp_path) as store:
        identity = store.identity()
        assert identity["execution_mode"] == "disabled"
        assert identity["primary_threshold_dollars"] == "0.02"


def test_b1_refuses_canonical_prospective_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    canonical = (
        Path("data")
        / "prospective"
        / "candidate_e"
        / "cohort-x"
        / "runtime_state.sqlite3"
    )
    with pytest.raises(RestartDurableStateStoreError):
        RestartDurableStateStore(
            canonical,
            validation_mode=True,
        )


def test_b1_requires_validation_mode(tmp_path):
    with pytest.raises(RestartDurableStateStoreError):
        RestartDurableStateStore(
            tmp_path / "state.sqlite3",
            validation_mode=False,
        )


def test_new_process_gets_new_session_id_same_boot(tmp_path):
    with open_store(tmp_path) as store:
        s1 = store.start_session(
            boot_id=BOOT_A,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:00Z",
            started_monotonic_ns=1000,
        )
        store.clean_shutdown(
            s1,
            ended_utc="2026-09-04T05:00:10Z",
            ended_monotonic_ns=2000,
        )
        s2 = store.start_session(
            boot_id=BOOT_A,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:20Z",
            started_monotonic_ns=10,
        )

        assert s2 != s1
        assert store.session(s2)["prior_session_id"] == s1


def test_new_session_monotonic_may_restart_lower(tmp_path):
    with open_store(tmp_path) as store:
        s1 = store.start_session(
            boot_id=BOOT_A,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:00Z",
            started_monotonic_ns=9_000_000,
        )
        store.clean_shutdown(
            s1,
            ended_utc="2026-09-04T05:00:10Z",
            ended_monotonic_ns=10_000_000,
        )
        s2 = store.start_session(
            boot_id=BOOT_B,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:20Z",
            started_monotonic_ns=1,
        )
        assert store.session(s2)["started_monotonic_ns"] == 1


def test_heartbeat_advances_running_session(tmp_path):
    with open_store(tmp_path) as store:
        s = store.start_session(
            boot_id=BOOT_A,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:00Z",
            started_monotonic_ns=100,
        )
        store.heartbeat(
            s,
            heartbeat_utc="2026-09-04T05:00:05Z",
            heartbeat_monotonic_ns=200,
        )
        row = store.session(s)
        assert row["last_heartbeat_utc"] == "2026-09-04T05:00:05Z"
        assert row["last_heartbeat_monotonic_ns"] == 200


def test_heartbeat_monotonic_cannot_regress_within_session(tmp_path):
    with open_store(tmp_path) as store:
        s = store.start_session(
            boot_id=BOOT_A,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:00Z",
            started_monotonic_ns=100,
        )
        store.heartbeat(
            s,
            heartbeat_utc="2026-09-04T05:00:05Z",
            heartbeat_monotonic_ns=200,
        )
        with pytest.raises(RestartDurableStateStoreError):
            store.heartbeat(
                s,
                heartbeat_utc="2026-09-04T05:00:06Z",
                heartbeat_monotonic_ns=199,
            )


def test_heartbeat_utc_cannot_regress(tmp_path):
    with open_store(tmp_path) as store:
        s = store.start_session(
            boot_id=BOOT_A,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:00Z",
            started_monotonic_ns=100,
        )
        store.heartbeat(
            s,
            heartbeat_utc="2026-09-04T05:00:05Z",
            heartbeat_monotonic_ns=200,
        )
        with pytest.raises(RestartDurableStateStoreError):
            store.heartbeat(
                s,
                heartbeat_utc="2026-09-04T05:00:04Z",
                heartbeat_monotonic_ns=201,
            )


def test_clean_shutdown_sets_final_heartbeat_and_clean(tmp_path):
    with open_store(tmp_path) as store:
        s = store.start_session(
            boot_id=BOOT_A,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:00Z",
            started_monotonic_ns=100,
        )
        store.clean_shutdown(
            s,
            ended_utc="2026-09-04T05:00:10Z",
            ended_monotonic_ns=500,
        )
        row = store.session(s)
        assert row["shutdown_status"] == "CLEAN"
        assert row["last_heartbeat_utc"] == row["ended_utc"]
        assert row["last_heartbeat_monotonic_ns"] == row["ended_monotonic_ns"]


def test_clean_restart_records_process_gap_from_clean_end(tmp_path):
    with open_store(tmp_path) as store:
        s1 = store.start_session(
            boot_id=BOOT_A,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:00Z",
            started_monotonic_ns=100,
        )
        store.clean_shutdown(
            s1,
            ended_utc="2026-09-04T05:00:10Z",
            ended_monotonic_ns=200,
        )
        s2 = store.start_session(
            boot_id=BOOT_A,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:20Z",
            started_monotonic_ns=1,
        )

        gaps = store.observation_gaps()
        assert len(gaps) == 1
        assert gaps[0]["reason"] == "CLEAN_PROCESS_STOP"
        assert gaps[0]["start_utc"] == "2026-09-04T05:00:10Z"
        assert gaps[0]["end_utc"] == "2026-09-04T05:00:20Z"
        assert gaps[0]["prior_session_id"] == s1
        assert gaps[0]["next_session_id"] == s2
        assert gaps[0]["canonical_backfill_allowed"] == 0


def test_unclean_restart_marks_prior_and_uses_last_durable_heartbeat(tmp_path):
    db = tmp_path / "state.sqlite3"

    with RestartDurableStateStore(
        db,
        validation_mode=True,
    ) as store:
        s1 = store.start_session(
            boot_id=BOOT_A,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:00Z",
            started_monotonic_ns=100,
        )
        store.heartbeat(
            s1,
            heartbeat_utc="2026-09-04T05:00:05Z",
            heartbeat_monotonic_ns=200,
        )
        # Intentionally close the SQLite handle without clean_shutdown.
        # The session therefore remains RUNNING, simulating a hard stop.

    with RestartDurableStateStore(
        db,
        validation_mode=True,
    ) as store:
        s2 = store.start_session(
            boot_id=BOOT_B,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:20Z",
            started_monotonic_ns=1,
        )

        prior = store.session(s1)
        assert prior["shutdown_status"] == "UNCLEAN_DETECTED"
        assert prior["unclean_detected_by_session_id"] == s2

        gaps = store.observation_gaps()
        assert len(gaps) == 1
        assert gaps[0]["reason"] == "UNCLEAN_PRIOR_SESSION"
        assert gaps[0]["start_basis"] == "PRIOR_DURABLE_HEARTBEAT"
        assert gaps[0]["start_utc"] == "2026-09-04T05:00:05Z"
        assert gaps[0]["end_utc"] == "2026-09-04T05:00:20Z"
        assert gaps[0]["canonical_backfill_allowed"] == 0


def test_clean_shutdown_cannot_be_repeated(tmp_path):
    with open_store(tmp_path) as store:
        s = store.start_session(
            boot_id=BOOT_A,
            git_commit=COMMIT,
            started_utc="2026-09-04T05:00:00Z",
            started_monotonic_ns=100,
        )
        store.clean_shutdown(
            s,
            ended_utc="2026-09-04T05:00:10Z",
            ended_monotonic_ns=200,
        )
        with pytest.raises(RestartDurableStateStoreError):
            store.clean_shutdown(
                s,
                ended_utc="2026-09-04T05:00:11Z",
                ended_monotonic_ns=201,
            )


def test_database_constraint_forbids_backfill_flag_one(tmp_path):
    with open_store(tmp_path) as store:
        with pytest.raises(sqlite3.IntegrityError):
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
                    'bad-gap',
                    'PROCESS_DISCONTINUITY',
                    'TEST',
                    '2026-09-04T05:00:00Z',
                    '2026-09-04T05:00:01Z',
                    'TEST',
                    NULL,
                    NULL,
                    NULL,
                    1
                )
                """
            )


def test_no_order_fill_position_tables_exist(tmp_path):
    with open_store(tmp_path) as store:
        names = {
            row[0].lower()
            for row in store.connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table'
                """
            )
        }
        assert "orders" not in names
        assert "fills" not in names
        assert "positions" not in names
