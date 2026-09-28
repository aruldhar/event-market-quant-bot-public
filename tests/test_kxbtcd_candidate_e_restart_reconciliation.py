from hashlib import sha256
import json
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_restart_durable_state_store import (
    RestartDurableStateStore,
)
from src.kxbtcd_candidate_e_restart_reconciliation import (
    RestartReconciliationError,
    RestartSessionRawJournal,
    audit_raw_segment,
    build_validation_arm_manifest,
    commit_validation_decision,
    install_validation_cohort_identity,
    reconcile_pending_decisions,
    validate_arm_manifest_identity,
    write_validation_arm_manifest_once,
)


COMMIT = "f26221ce28c567d1664aedeb33b8e3ab9e9775e3"


def store(tmp_path):
    return RestartDurableStateStore(
        tmp_path / "state.sqlite3",
        validation_mode=True,
    )


def start(s):
    return s.start_session(
        boot_id="synthetic-boot",
        git_commit=COMMIT,
        started_utc="2026-09-04T06:00:00Z",
        started_monotonic_ns=100,
        session_id="session-1",
    )


def make_manifest(tmp_path, s):
    sid = start(s)
    m = build_validation_arm_manifest(
        cohort_id="validation-cohort",
        arm_time_utc="2026-09-04T06:00:00Z",
        arm_git_commit=COMMIT,
    )
    p = tmp_path / "arm_manifest.json"
    manifest_sha = write_validation_arm_manifest_once(p, m)
    install_validation_cohort_identity(
        store=s,
        manifest_path=p,
        armed_by_session_id=sid,
    )
    return sid, p, manifest_sha


def test_validation_arm_identity_matches_sqlite(tmp_path):
    with store(tmp_path) as s:
        _, p, expected_sha = make_manifest(tmp_path, s)
        result = validate_arm_manifest_identity(
            store=s,
            manifest_path=p,
            current_git_commit=COMMIT,
        )
        assert result["manifest_sha256"] == expected_sha
        assert result["cohort_id"] == "validation-cohort"


def test_git_commit_mismatch_fails_closed(tmp_path):
    with store(tmp_path) as s:
        _, p, _ = make_manifest(tmp_path, s)
        with pytest.raises(RestartReconciliationError):
            validate_arm_manifest_identity(
                store=s,
                manifest_path=p,
                current_git_commit="different-commit",
            )


def test_manifest_sqlite_sha_mismatch_fails_closed(tmp_path):
    with store(tmp_path) as s:
        _, p, _ = make_manifest(tmp_path, s)
        s.connection.execute(
            """
            UPDATE cohort_state
            SET arm_manifest_sha256='bad'
            WHERE singleton_id=1
            """
        )
        with pytest.raises(RestartReconciliationError):
            validate_arm_manifest_identity(
                store=s,
                manifest_path=p,
                current_git_commit=COMMIT,
            )


def test_manifest_fixed_end_must_equal_168_hours(tmp_path):
    with store(tmp_path) as s:
        sid = start(s)
        m = build_validation_arm_manifest(
            cohort_id="validation-cohort",
            arm_time_utc="2026-09-04T06:00:00Z",
            arm_git_commit=COMMIT,
        )
        m["fixed_end_time_utc"] = "2026-09-12T06:00:01Z"
        p = tmp_path / "bad_manifest.json"
        write_validation_arm_manifest_once(p, m)

        # Install matching bad values so the failure specifically comes from
        # the immutable 168-hour relation, not SQLite mismatch.
        raw_sha = sha256(p.read_bytes()).hexdigest()
        s.connection.execute(
            """
            INSERT INTO cohort_state (
                singleton_id,cohort_id,status,
                arm_time_utc,fixed_end_time_utc,
                duration_hours,arm_git_commit,
                arm_manifest_sha256,armed_by_session_id,ended_utc
            ) VALUES (1,?,'ARMED',?,?,?,?,?,?,NULL)
            """,
            (
                m["cohort_id"],
                m["arm_time_utc"],
                m["fixed_end_time_utc"],
                168,
                COMMIT,
                raw_sha,
                sid,
            ),
        )
        with pytest.raises(RestartReconciliationError):
            validate_arm_manifest_identity(
                store=s,
                manifest_path=p,
                current_git_commit=COMMIT,
            )


def test_manifest_create_once(tmp_path):
    m = build_validation_arm_manifest(
        cohort_id="c",
        arm_time_utc="2026-09-04T06:00:00Z",
        arm_git_commit=COMMIT,
    )
    p = tmp_path / "arm.json"
    write_validation_arm_manifest_once(p, m)
    before = p.read_bytes()
    with pytest.raises(RestartReconciliationError):
        write_validation_arm_manifest_once(p, m)
    assert p.read_bytes() == before


def test_raw_segment_is_create_exclusive(tmp_path):
    p = tmp_path / "raw.jsonl"
    with RestartSessionRawJournal(
        p,
        runtime_session_id="s",
        raw_segment_id="seg",
    ):
        pass
    before = p.read_bytes()
    with pytest.raises(RestartReconciliationError):
        RestartSessionRawJournal(
            p,
            runtime_session_id="s2",
            raw_segment_id="seg2",
        )
    assert p.read_bytes() == before


def test_raw_record_contains_exact_restart_identity(tmp_path):
    p = tmp_path / "raw.jsonl"
    with RestartSessionRawJournal(
        p,
        runtime_session_id="session-1",
        raw_segment_id="segment-1",
    ) as j:
        ref = j.append(
            source="coinbase_exchange_ws",
            transport="wss",
            raw_text='{"type":"match"}',
            received_monotonic_ns=100,
            received_utc="2026-09-04T06:00:01Z",
        )

    record = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert record["runtime_session_id"] == "session-1"
    assert record["raw_segment_id"] == "segment-1"
    assert record["raw_record_index"] == 1
    assert ref.raw_record_index == 1


def test_raw_audit_detects_partial_trailing_bytes_without_modifying(tmp_path):
    p = tmp_path / "raw.jsonl"
    with RestartSessionRawJournal(
        p,
        runtime_session_id="session-1",
        raw_segment_id="segment-1",
    ) as j:
        j.append(
            source="coinbase_exchange_ws",
            transport="wss",
            raw_text="one",
            received_monotonic_ns=100,
            received_utc="2026-09-04T06:00:01Z",
        )

    with p.open("ab") as f:
        f.write(b'{"partial":true')

    before = p.read_bytes()
    audit = audit_raw_segment(
        p,
        expected_runtime_session_id="session-1",
        expected_raw_segment_id="segment-1",
    )
    after = p.read_bytes()

    assert before == after
    assert audit.valid_record_count == 1
    assert audit.partial_trailing_bytes_present is True
    assert audit.partial_trailing_bytes_sha256 == sha256(
        b'{"partial":true'
    ).hexdigest()


def test_valid_pending_decision_becomes_verified(tmp_path):
    raw = tmp_path / "raw.jsonl"
    with RestartSessionRawJournal(
        raw,
        runtime_session_id="session-1",
        raw_segment_id="segment-1",
    ) as j:
        ref = j.append(
            source="kalshi_production_ws",
            transport="wss",
            raw_text="snapshot",
            received_monotonic_ns=200,
            received_utc="2026-09-04T06:00:02Z",
        )

    with store(tmp_path) as s:
        start(s)
        decision_id = commit_validation_decision(
            store=s,
            session_id="session-1",
            session_decision_seq=1,
            decision_utc="2026-09-04T06:00:03Z",
            decision_monotonic_ns=300,
            event_ticker="KXBTCD-TEST",
            raw_refs=[ref],
            source_id="kalshi_production_ws",
            raw_segment_id="segment-1",
            last_raw_record_index=1,
        )

        result = reconcile_pending_decisions(
            store=s,
            raw_segments={
                ("session-1", "segment-1"): raw,
            },
        )
        row = s.connection.execute(
            """
            SELECT integrity_status
            FROM decision_records
            WHERE decision_record_id=?
            """,
            (decision_id,),
        ).fetchone()
        assert result == {
            "pending_examined": 1,
            "verified": 1,
            "raw_evidence_gaps": 0,
        }
        assert row["integrity_status"] == "VERIFIED"


def test_missing_raw_reference_becomes_gap_not_backfill(tmp_path):
    raw = tmp_path / "raw.jsonl"
    with RestartSessionRawJournal(
        raw,
        runtime_session_id="session-1",
        raw_segment_id="segment-1",
    ) as j:
        ref = j.append(
            source="kalshi_production_ws",
            transport="wss",
            raw_text="snapshot",
            received_monotonic_ns=200,
            received_utc="2026-09-04T06:00:02Z",
        )

    with store(tmp_path) as s:
        start(s)
        decision_id = commit_validation_decision(
            store=s,
            session_id="session-1",
            session_decision_seq=1,
            decision_utc="2026-09-04T06:00:03Z",
            decision_monotonic_ns=300,
            event_ticker="KXBTCD-TEST",
            raw_refs=[ref],
            source_id="kalshi_production_ws",
            raw_segment_id="segment-1",
            last_raw_record_index=1,
        )

        result = reconcile_pending_decisions(
            store=s,
            raw_segments={},
        )
        row = s.connection.execute(
            """
            SELECT integrity_status
            FROM decision_records
            WHERE decision_record_id=?
            """,
            (decision_id,),
        ).fetchone()
        gaps = s.observation_gaps()

        assert result["raw_evidence_gaps"] == 1
        assert row["integrity_status"] == "RAW_EVIDENCE_GAP"
        assert gaps[-1]["canonical_backfill_allowed"] == 0


def test_crash_after_raw_before_decision_leaves_orphan_raw_only(tmp_path):
    raw = tmp_path / "raw.jsonl"
    with RestartSessionRawJournal(
        raw,
        runtime_session_id="session-1",
        raw_segment_id="segment-1",
    ) as j:
        j.append(
            source="coinbase_exchange_ws",
            transport="wss",
            raw_text="orphan-after-crash",
            received_monotonic_ns=100,
            received_utc="2026-09-04T06:00:01Z",
        )

    with store(tmp_path) as s:
        start(s)
        result = reconcile_pending_decisions(
            store=s,
            raw_segments={
                ("session-1", "segment-1"): raw,
            },
        )
        assert result == {
            "pending_examined": 0,
            "verified": 0,
            "raw_evidence_gaps": 0,
        }
        count = s.connection.execute(
            "SELECT COUNT(*) FROM decision_records"
        ).fetchone()[0]
        assert count == 0


def test_crash_loses_referenced_last_record_marks_gap(tmp_path):
    raw = tmp_path / "raw.jsonl"
    with RestartSessionRawJournal(
        raw,
        runtime_session_id="session-1",
        raw_segment_id="segment-1",
    ) as j:
        ref1 = j.append(
            source="coinbase_exchange_ws",
            transport="wss",
            raw_text="durable-1",
            received_monotonic_ns=100,
            received_utc="2026-09-04T06:00:01Z",
        )
        ref2 = j.append(
            source="coinbase_exchange_ws",
            transport="wss",
            raw_text="may-be-lost-2",
            received_monotonic_ns=101,
            received_utc="2026-09-04T06:00:02Z",
        )

    lines = raw.read_bytes().splitlines(keepends=True)
    # Simulate post-crash disk state where record 2 never became durable.
    raw.write_bytes(lines[0])

    with store(tmp_path) as s:
        start(s)
        decision_id = commit_validation_decision(
            store=s,
            session_id="session-1",
            session_decision_seq=1,
            decision_utc="2026-09-04T06:00:03Z",
            decision_monotonic_ns=300,
            event_ticker="KXBTCD-TEST",
            raw_refs=[ref1, ref2],
            source_id="coinbase_exchange_ws",
            raw_segment_id="segment-1",
            last_raw_record_index=2,
        )

        result = reconcile_pending_decisions(
            store=s,
            raw_segments={
                ("session-1", "segment-1"): raw,
            },
        )
        row = s.connection.execute(
            """
            SELECT integrity_status
            FROM decision_records
            WHERE decision_record_id=?
            """,
            (decision_id,),
        ).fetchone()

        assert result["raw_evidence_gaps"] == 1
        assert row["integrity_status"] == "RAW_EVIDENCE_GAP"


def test_decision_and_watermark_commit_together(tmp_path):
    raw = tmp_path / "raw.jsonl"
    with RestartSessionRawJournal(
        raw,
        runtime_session_id="session-1",
        raw_segment_id="segment-1",
    ) as j:
        ref = j.append(
            source="coinbase_exchange_ws",
            transport="wss",
            raw_text="one",
            received_monotonic_ns=100,
            received_utc="2026-09-04T06:00:01Z",
        )

    with store(tmp_path) as s:
        start(s)
        commit_validation_decision(
            store=s,
            session_id="session-1",
            session_decision_seq=1,
            decision_utc="2026-09-04T06:00:02Z",
            decision_monotonic_ns=200,
            event_ticker="KXBTCD-TEST",
            raw_refs=[ref],
            source_id="coinbase_exchange_ws",
            raw_segment_id="segment-1",
            last_raw_record_index=1,
        )

        assert s.connection.execute(
            "SELECT COUNT(*) FROM decision_records"
        ).fetchone()[0] == 1
        assert s.connection.execute(
            "SELECT COUNT(*) FROM source_watermarks"
        ).fetchone()[0] == 1


def test_no_signal_order_fill_position_objects_added(tmp_path):
    with store(tmp_path) as s:
        names = {
            row[0].lower()
            for row in s.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "orders" not in names
        assert "fills" not in names
        assert "positions" not in names
        assert "signals" not in names
