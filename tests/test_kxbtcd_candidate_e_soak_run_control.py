from dataclasses import replace

from src.kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from src.kxbtcd_candidate_e_soak_readiness import (
    SoakReadinessResult,
)
from src.kxbtcd_candidate_e_soak_run_control import (
    SoakRunController,
)


BOOT = (
    "11111111-2222-3333-4444-555555555555"
)


def readiness(
    *,
    state="READY_READ_ONLY",
    status=GateStatus.PASS,
    reason="PASS",
):
    return SoakReadinessResult(
        state=state,
        status=status,
        reason=reason,
        ready_read_only=(
            state == "READY_READ_ONLY"
        ),
        expected_boot_id=BOOT,
        current_boot_id=BOOT,
        current_time_namespace_id=(
            "time:[4026531834]"
        ),
        identity_reason="PASS",
        clock_reason="PASS",
        coinbase_reason="PASS",
        kalshi_reason="PASS",
    )


def blocked(
    state,
    reason,
):
    return readiness(
        state=state,
        status=GateStatus.BLOCKED,
        reason=reason,
    )


def fatal(reason):
    return readiness(
        state="FATAL",
        status=GateStatus.FATAL,
        reason=reason,
    )


def s(value):
    return int(
        value * 1_000_000_000
    )


def test_starts_active_timer_at_first_ready():
    run = SoakRunController(
        started_monotonic_ns=s(10),
        requested_active_duration_seconds=3600,
    )

    waiting = run.observe(
        evaluated_monotonic_ns=s(100),
        readiness=blocked(
            "BLOCKED_COINBASE",
            "COINBASE_HEARTBEAT_STALE",
        ),
    )

    assert waiting.state == (
        "WAITING_INITIAL_READY"
    )

    active = run.observe(
        evaluated_monotonic_ns=s(110),
        readiness=readiness(),
    )

    assert active.state == "ACTIVE"
    assert (
        active.first_ready_monotonic_ns
        == s(110)
    )
    assert (
        active.active_deadline_monotonic_ns
        == s(3710)
    )


def test_first_ready_exactly_at_300_seconds_is_allowed():
    run = SoakRunController(
        started_monotonic_ns=s(100),
        requested_active_duration_seconds=3600,
    )

    result = run.observe(
        evaluated_monotonic_ns=s(400),
        readiness=readiness(),
    )

    assert result.state == "ACTIVE"
    assert result.first_ready_monotonic_ns == (
        s(400)
    )


def test_first_ready_after_300_seconds_is_timeout():
    run = SoakRunController(
        started_monotonic_ns=s(100),
        requested_active_duration_seconds=3600,
    )

    result = run.observe(
        evaluated_monotonic_ns=s(401),
        readiness=readiness(),
    )

    assert result.state == (
        "INITIAL_READINESS_TIMEOUT"
    )
    assert not result.measurement_complete


def test_still_blocked_at_exact_timeout_is_timeout():
    run = SoakRunController(
        started_monotonic_ns=0,
        requested_active_duration_seconds=3600,
    )

    result = run.observe(
        evaluated_monotonic_ns=s(300),
        readiness=blocked(
            "BLOCKED_CLOCK",
            "CLOCK_EVIDENCE_STALE",
        ),
    )

    assert result.state == (
        "INITIAL_READINESS_TIMEOUT"
    )


def test_blocked_time_does_not_pause_active_timer():
    run = SoakRunController(
        started_monotonic_ns=0,
        requested_active_duration_seconds=10,
    )

    run.observe(
        evaluated_monotonic_ns=s(1),
        readiness=readiness(),
    )

    run.observe(
        evaluated_monotonic_ns=s(4),
        readiness=blocked(
            "BLOCKED_KALSHI",
            "KALSHI_PONG_STALE",
        ),
    )

    run.observe(
        evaluated_monotonic_ns=s(9),
        readiness=readiness(),
    )

    final = run.observe(
        evaluated_monotonic_ns=s(11),
        readiness=readiness(),
    )

    assert final.state == (
        "MEASUREMENT_COMPLETE"
    )

    assert final.active_elapsed_seconds == 10

    # [1,4): READY = 3s
    # [4,9): BLOCKED = 5s
    # [9,11): READY = 2s
    assert final.ready_duration_seconds == 5
    assert final.blocked_duration_seconds == 5


def test_poll_overshoot_is_capped_exactly_at_deadline():
    run = SoakRunController(
        started_monotonic_ns=0,
        requested_active_duration_seconds=10,
    )

    run.observe(
        evaluated_monotonic_ns=s(1),
        readiness=readiness(),
    )

    final = run.observe(
        evaluated_monotonic_ns=s(14),
        readiness=readiness(),
    )

    assert final.state == (
        "MEASUREMENT_COMPLETE"
    )

    assert final.active_elapsed_seconds == 10
    assert final.ready_duration_seconds == 10
    assert final.blocked_duration_seconds == 0


def test_fatal_readiness_terminates_before_duration_complete():
    run = SoakRunController(
        started_monotonic_ns=0,
        requested_active_duration_seconds=10,
    )

    run.observe(
        evaluated_monotonic_ns=s(1),
        readiness=readiness(),
    )

    result = run.observe(
        evaluated_monotonic_ns=s(5),
        readiness=fatal(
            "UNEXPECTED_LINUX_BOOT_ID_CHANGE"
        ),
    )

    assert result.state == "FATAL"
    assert result.reason == (
        "UNEXPECTED_LINUX_BOOT_ID_CHANGE"
    )
    assert not result.measurement_complete
    assert result.active_elapsed_seconds == 4
    assert result.ready_duration_seconds == 4


def test_monotonic_regression_is_fatal():
    run = SoakRunController(
        started_monotonic_ns=s(10),
        requested_active_duration_seconds=10,
    )

    run.observe(
        evaluated_monotonic_ns=s(11),
        readiness=readiness(),
    )

    result = run.observe(
        evaluated_monotonic_ns=s(10.5),
        readiness=readiness(),
    )

    assert result.state == "FATAL"
    assert result.reason == (
        "LOCAL_MONOTONIC_TIME_REGRESSION"
    )


def test_terminal_state_cannot_be_recovered_by_fresh_readiness():
    run = SoakRunController(
        started_monotonic_ns=0,
        requested_active_duration_seconds=10,
    )

    run.observe(
        evaluated_monotonic_ns=s(301),
        readiness=blocked(
            "BLOCKED_CLOCK",
            "CLOCK_EVIDENCE_STALE",
        ),
    )

    later = run.observe(
        evaluated_monotonic_ns=s(302),
        readiness=readiness(),
    )

    assert later.state == (
        "INITIAL_READINESS_TIMEOUT"
    )
    assert not later.measurement_complete


def test_completion_can_end_while_currently_blocked():
    run = SoakRunController(
        started_monotonic_ns=0,
        requested_active_duration_seconds=10,
    )

    run.observe(
        evaluated_monotonic_ns=s(1),
        readiness=readiness(),
    )

    run.observe(
        evaluated_monotonic_ns=s(5),
        readiness=blocked(
            "BLOCKED_COINBASE",
            "COINBASE_HEARTBEAT_STALE",
        ),
    )

    final = run.observe(
        evaluated_monotonic_ns=s(11),
        readiness=blocked(
            "BLOCKED_COINBASE",
            "COINBASE_HEARTBEAT_STALE",
        ),
    )

    assert final.state == (
        "MEASUREMENT_COMPLETE"
    )
    assert final.active_elapsed_seconds == 10
    assert final.ready_duration_seconds == 4
    assert final.blocked_duration_seconds == 6
