import json

import pytest

from src.kxbtcd_candidate_e_restart_durable_state_store import (
    RestartDurableStateStore,
)
from src.kxbtcd_candidate_e_restart_gate_state_machine import (
    ClockHealth,
    CohortStatus,
    GateStatus,
    MAX_ABSOLUTE_CLOCK_OFFSET_MS,
    RestartGateError,
    RestartGateSnapshot,
    RestartGateStateMachine,
    resolve_restart_state,
)


COMMIT = "b3f54c89b3ab3f8794e4b9e2458b5538e4ab6477"


def make_store(tmp_path):
    s = RestartDurableStateStore(
        tmp_path / "state.sqlite3",
        validation_mode=True,
    )
    sid = s.start_session(
        boot_id="synthetic-boot",
        git_commit=COMMIT,
        started_utc="2026-09-04T06:30:00Z",
        started_monotonic_ns=100,
        session_id="session-b3",
    )
    return s, sid


def ready_snapshot():
    return RestartGateSnapshot(
        identity=GateStatus.PASS,
        cohort=CohortStatus.ACTIVE,
        durability=GateStatus.PASS,
        clock=GateStatus.PASS,
        coinbase=GateStatus.PASS,
        kalshi=GateStatus.PASS,
        strategy_reconciliation=GateStatus.PASS,
        execution_mode_disabled=True,
    )


def test_initial_state_is_startup_disabled(tmp_path):
    s, sid = make_store(tmp_path)
    with s:
        machine = RestartGateStateMachine(
            store=s,
            session_id=sid,
        )
        assert machine.state == "STARTUP_DISABLED"
        assert machine.signal_eligible is False
        assert machine.prior_signal_reusable is False


def test_all_unknown_fails_closed_at_identity():
    assert resolve_restart_state(
        RestartGateSnapshot()
    ) == "BLOCKED_IDENTITY"


def test_fatal_identity_dominates():
    snap = ready_snapshot()
    snap = RestartGateSnapshot(
        **{
            **snap.__dict__,
            "identity": GateStatus.FATAL,
        }
    )
    assert resolve_restart_state(snap) == "FATAL"


def test_execution_not_disabled_is_fatal():
    snap = ready_snapshot()
    snap = RestartGateSnapshot(
        **{
            **snap.__dict__,
            "execution_mode_disabled": False,
        }
    )
    assert resolve_restart_state(snap) == "FATAL"


def test_cohort_ended_is_terminal_no_signal():
    snap = ready_snapshot()
    snap = RestartGateSnapshot(
        **{
            **snap.__dict__,
            "cohort": CohortStatus.ENDED,
        }
    )
    assert resolve_restart_state(snap) == "COHORT_ENDED"


def test_clock_unknown_blocks():
    health = ClockHealth.from_signed_offset_ms(None)
    assert health.known is False
    assert health.gate_status == GateStatus.BLOCKED


def test_clock_250_ms_exactly_passes():
    health = ClockHealth.from_signed_offset_ms(
        MAX_ABSOLUTE_CLOCK_OFFSET_MS
    )
    assert health.healthy is True
    assert health.gate_status == GateStatus.PASS


def test_clock_negative_250_ms_exactly_passes():
    health = ClockHealth.from_signed_offset_ms(
        -MAX_ABSOLUTE_CLOCK_OFFSET_MS
    )
    assert health.healthy is True


def test_clock_over_250_ms_blocks():
    health = ClockHealth.from_signed_offset_ms(250.0001)
    assert health.healthy is False
    assert health.gate_status == GateStatus.BLOCKED


def test_startup_clock_unhealthy_frozen_case():
    health = ClockHealth.from_signed_offset_ms(300.0)
    snap = RestartGateSnapshot.with_clock_health(
        clock_health=health,
        identity=GateStatus.PASS,
        cohort=CohortStatus.ACTIVE,
        durability=GateStatus.PASS,
        coinbase=GateStatus.PASS,
        kalshi=GateStatus.PASS,
        strategy_reconciliation=GateStatus.PASS,
    )
    assert resolve_restart_state(snap) == "BLOCKED_CLOCK"


def test_ready_requires_every_gate():
    assert resolve_restart_state(
        ready_snapshot()
    ) == "READY_READ_ONLY"


def test_blocking_precedence_follows_frozen_gate_order():
    snap = RestartGateSnapshot(
        identity=GateStatus.PASS,
        cohort=CohortStatus.ACTIVE,
        durability=GateStatus.BLOCKED,
        clock=GateStatus.BLOCKED,
        coinbase=GateStatus.BLOCKED,
        kalshi=GateStatus.BLOCKED,
        strategy_reconciliation=GateStatus.BLOCKED,
    )
    assert resolve_restart_state(snap) == "BLOCKED_DURABILITY"


def test_ready_transition_records_event_and_generation(tmp_path):
    s, sid = make_store(tmp_path)
    with s:
        machine = RestartGateStateMachine(
            store=s,
            session_id=sid,
        )
        state = machine.evaluate(
            ready_snapshot(),
            evaluated_utc="2026-09-04T06:30:01Z",
            evaluated_monotonic_ns=200,
        )
        assert state == "READY_READ_ONLY"
        assert machine.signal_eligible is True
        assert machine.may_recompute_fresh_signal is True
        assert machine.prior_signal_reusable is False
        assert machine.readiness_generation == 1

        row = s.connection.execute(
            """
            SELECT event_type,payload_json
            FROM runtime_events
            WHERE session_id=?
            """,
            (sid,),
        ).fetchone()
        assert row["event_type"] == "restart_gate.transition"
        payload = json.loads(row["payload_json"])
        assert payload["prior_signal_reusable"] is False


def test_ready_to_clock_block_immediately_opens_gap(tmp_path):
    s, sid = make_store(tmp_path)
    with s:
        machine = RestartGateStateMachine(
            store=s,
            session_id=sid,
        )
        machine.evaluate(
            ready_snapshot(),
            evaluated_utc="2026-09-04T06:30:01Z",
            evaluated_monotonic_ns=200,
        )

        blocked = ready_snapshot()
        blocked = RestartGateSnapshot(
            **{
                **blocked.__dict__,
                "clock": GateStatus.BLOCKED,
            }
        )
        state = machine.evaluate(
            blocked,
            evaluated_utc="2026-09-04T06:30:02Z",
            evaluated_monotonic_ns=300,
        )

        assert state == "BLOCKED_CLOCK"
        assert machine.signal_eligible is False
        assert machine.prior_signal_reusable is False

        gap = s.connection.execute(
            """
            SELECT *
            FROM observation_gaps
            WHERE reason='READY_GATE_REGRESSION'
            """
        ).fetchone()
        assert gap is not None
        assert gap["start_utc"] == "2026-09-04T06:30:02Z"
        assert gap["end_utc"] is None
        assert gap["canonical_backfill_allowed"] == 0


def test_recovery_closes_gap_and_requires_new_ready_generation(tmp_path):
    s, sid = make_store(tmp_path)
    with s:
        machine = RestartGateStateMachine(
            store=s,
            session_id=sid,
        )
        machine.evaluate(
            ready_snapshot(),
            evaluated_utc="2026-09-04T06:30:01Z",
            evaluated_monotonic_ns=200,
        )

        blocked = RestartGateSnapshot(
            **{
                **ready_snapshot().__dict__,
                "kalshi": GateStatus.BLOCKED,
            }
        )
        machine.evaluate(
            blocked,
            evaluated_utc="2026-09-04T06:30:02Z",
            evaluated_monotonic_ns=300,
        )
        machine.evaluate(
            ready_snapshot(),
            evaluated_utc="2026-09-04T06:30:05Z",
            evaluated_monotonic_ns=400,
        )

        assert machine.state == "READY_READ_ONLY"
        assert machine.readiness_generation == 2

        gap = s.connection.execute(
            """
            SELECT *
            FROM observation_gaps
            WHERE reason='READY_GATE_REGRESSION'
            """
        ).fetchone()
        assert gap["end_utc"] == "2026-09-04T06:30:05Z"


def test_prior_raw_evidence_gap_does_not_permanently_block_fresh_recovery(
    tmp_path,
):
    s, sid = make_store(tmp_path)
    with s:
        # Historical prior gap exists.
        s.connection.execute(
            """
            INSERT INTO observation_gaps (
                gap_id,gap_kind,reason,start_utc,end_utc,start_basis,
                prior_session_id,next_session_id,source_id,
                canonical_backfill_allowed
            ) VALUES (
                'old-gap',
                'DURABILITY_RECONCILIATION',
                'MISSING_OR_DAMAGED_RAW_REFERENCE',
                '2026-09-04T06:20:00Z',
                '2026-09-04T06:20:00Z',
                'DECISION_UTC_EVIDENCE_GAP',
                'old-session',
                NULL,
                NULL,
                0
            )
            """
        )

        machine = RestartGateStateMachine(
            store=s,
            session_id=sid,
        )
        assert machine.evaluate(
            ready_snapshot(),
            evaluated_utc="2026-09-04T06:30:01Z",
            evaluated_monotonic_ns=200,
        ) == "READY_READ_ONLY"


def test_monotonic_regression_within_session_fails(tmp_path):
    s, sid = make_store(tmp_path)
    with s:
        machine = RestartGateStateMachine(
            store=s,
            session_id=sid,
        )
        machine.evaluate(
            ready_snapshot(),
            evaluated_utc="2026-09-04T06:30:01Z",
            evaluated_monotonic_ns=200,
        )
        with pytest.raises(RestartGateError):
            machine.evaluate(
                ready_snapshot(),
                evaluated_utc="2026-09-04T06:30:02Z",
                evaluated_monotonic_ns=199,
            )


def test_state_machine_has_no_signal_or_order_table_side_effects(tmp_path):
    s, sid = make_store(tmp_path)
    with s:
        machine = RestartGateStateMachine(
            store=s,
            session_id=sid,
        )
        machine.evaluate(
            ready_snapshot(),
            evaluated_utc="2026-09-04T06:30:01Z",
            evaluated_monotonic_ns=200,
        )

        tables = {
            row[0].lower()
            for row in s.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "signals" not in tables
        assert "orders" not in tables
        assert "fills" not in tables
        assert "positions" not in tables
