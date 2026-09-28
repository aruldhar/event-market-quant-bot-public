from src.kxbtcd_candidate_e_clock_evidence_bridge import (
    ClockEvidenceBridgeResult,
)
from src.kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from src.kxbtcd_candidate_e_restart_source_readiness import (
    ChronyTrackingEvidence,
    CoinbaseReadinessEvidence,
    KalshiReadinessEvidence,
)
from src.kxbtcd_candidate_e_soak_linux_runtime_identity import (
    RuntimeLinuxIdentityEvidence,
)
from src.kxbtcd_candidate_e_soak_readiness import (
    SoakReadinessCoordinator,
    resolve_soak_readiness,
)


BOOT = (
    "11111111-2222-3333-4444-555555555555"
)

OTHER_BOOT = (
    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
)

TIME_NS = "time:[4026531834]"


def identity(
    *,
    status=GateStatus.PASS,
    reason="PASS",
    boot=BOOT,
    time_ns=TIME_NS,
):
    return RuntimeLinuxIdentityEvidence(
        status=status,
        reason=reason,
        boot_id=boot,
        time_namespace_id=time_ns,
        boot_source="linux_kernel_boot_id",
    )


def clock(
    *,
    status=GateStatus.PASS,
    reason="PASS",
    host_boot=BOOT,
    host_time_ns=TIME_NS,
):
    return ClockEvidenceBridgeResult(
        status=status,
        reason=reason,
        chrony=ChronyTrackingEvidence(
            status=(
                GateStatus.PASS
                if status == GateStatus.PASS
                else status
            ),
            signed_system_time_offset_ms=(
                1.0
                if status == GateStatus.PASS
                else None
            ),
            absolute_system_time_offset_ms=(
                1.0
                if status == GateStatus.PASS
                else None
            ),
            leap_status=(
                "Normal"
                if status == GateStatus.PASS
                else None
            ),
            reason=reason,
        ),
        evidence_age_ns=1_000_000_000,
        publisher_instance_id="publisher-a",
        host_boot_id=host_boot,
        host_time_namespace_id=(
            host_time_ns
        ),
    )


def coinbase(
    *,
    status=GateStatus.PASS,
    reason="PASS",
):
    return CoinbaseReadinessEvidence(
        status=status,
        reason=reason,
        target_minute_start_s=1_788_534_000,
        target_minute_end_s=1_788_534_060,
        builder_status="COMPLETE",
        close_trade_id=123,
        connection_generation=1,
    )


def kalshi(
    *,
    status=GateStatus.PASS,
    reason="PASS",
):
    return KalshiReadinessEvidence(
        status=status,
        reason=reason,
        event_ticker="KXBTCD-26SEP0416",
        expected_tickers=(
            "KXBTCD-26SEP0416-T110000.00",
        ),
        generation=1,
        last_seq=10,
        subscription_sid=1,
        connection_generation=1,
        transport_reason="PASS",
    )


def resolve(**overrides):
    values = {
        "expected_boot_id": BOOT,
        "execution_mode_disabled": True,
        "identity": identity(),
        "clock": clock(),
        "coinbase": coinbase(),
        "kalshi": kalshi(),
    }

    values.update(
        overrides
    )

    return resolve_soak_readiness(
        **values
    )


def test_every_required_infrastructure_gate_passes_ready():
    result = resolve()

    assert result.state == (
        "READY_READ_ONLY"
    )
    assert result.status == (
        GateStatus.PASS
    )
    assert result.ready_read_only
    assert result.reason == "PASS"


def test_execution_mode_enabled_is_immediate_fatal():
    result = resolve(
        execution_mode_disabled=False
    )

    assert result.state == "FATAL"
    assert result.reason == (
        "EXECUTION_MODE_NOT_DISABLED"
    )


def test_explicit_fatal_clock_dominates_blocked_identity():
    result = resolve(
        identity=identity(
            status=GateStatus.BLOCKED,
            reason="BOOT_ID_UNAVAILABLE_OR_INVALID",
            boot=None,
            time_ns=None,
        ),
        clock=clock(
            status=GateStatus.FATAL,
            reason=(
                "SYNTHETIC_OR_NONPRODUCTION_CLOCK_EVIDENCE"
            ),
        ),
    )

    assert result.state == "FATAL"
    assert result.reason == (
        "CLOCK_FATAL:"
        "SYNTHETIC_OR_NONPRODUCTION_CLOCK_EVIDENCE"
    )


def test_missing_production_identity_blocks():
    result = resolve(
        identity=identity(
            status=GateStatus.BLOCKED,
            reason="PRODUCTION_REQUIRES_LINUX_BOOT_ID",
            boot=None,
            time_ns=None,
        )
    )

    assert result.state == (
        "BLOCKED_IDENTITY"
    )


def test_unexpected_boot_change_is_hard_failure():
    result = resolve(
        identity=identity(
            boot=OTHER_BOOT
        ),
        clock=clock(
            status=GateStatus.BLOCKED,
            reason=(
                "CLOCK_EVIDENCE_BOOT_ID_MISMATCH"
            ),
            host_boot=OTHER_BOOT,
        ),
    )

    # Host reboot must dominate ordinary clock BLOCKED behavior.
    assert result.state == "FATAL"
    assert result.reason == (
        "UNEXPECTED_LINUX_BOOT_ID_CHANGE"
    )


def test_clock_unhealthy_blocks_but_does_not_hard_fail():
    result = resolve(
        clock=clock(
            status=GateStatus.BLOCKED,
            reason="CLOCK_EVIDENCE_STALE",
        )
    )

    assert result.state == (
        "BLOCKED_CLOCK"
    )
    assert result.status == (
        GateStatus.BLOCKED
    )


def test_pass_clock_with_boot_identity_contradiction_is_fatal():
    result = resolve(
        clock=clock(
            host_boot=OTHER_BOOT
        )
    )

    assert result.state == "FATAL"
    assert result.reason == (
        "CLOCK_PASS_WITH_BOOT_ID_MISMATCH"
    )


def test_pass_clock_with_namespace_contradiction_is_fatal():
    result = resolve(
        clock=clock(
            host_time_ns=(
                "time:[9999999999]"
            )
        )
    )

    assert result.state == "FATAL"
    assert result.reason == (
        "CLOCK_PASS_WITH_TIME_NAMESPACE_MISMATCH"
    )


def test_coinbase_blocked_precedes_kalshi_blocked():
    result = resolve(
        coinbase=coinbase(
            status=GateStatus.BLOCKED,
            reason="COINBASE_HEARTBEAT_STALE",
        ),
        kalshi=kalshi(
            status=GateStatus.BLOCKED,
            reason="KALSHI_PONG_STALE",
        ),
    )

    assert result.state == (
        "BLOCKED_COINBASE"
    )
    assert result.reason == (
        "COINBASE_HEARTBEAT_STALE"
    )


def test_kalshi_blocks_after_other_gates_pass():
    result = resolve(
        kalshi=kalshi(
            status=GateStatus.BLOCKED,
            reason="KALSHI_BOOK_NOT_READY",
        )
    )

    assert result.state == (
        "BLOCKED_KALSHI"
    )


def test_blocked_condition_can_recover_to_ready():
    coordinator = SoakReadinessCoordinator(
        expected_boot_id=BOOT
    )

    first = coordinator.evaluate(
        evaluated_monotonic_ns=100,
        execution_mode_disabled=True,
        identity=identity(),
        clock=clock(
            status=GateStatus.BLOCKED,
            reason="CLOCK_EVIDENCE_STALE",
        ),
        coinbase=coinbase(),
        kalshi=kalshi(),
    )

    assert first.state == (
        "BLOCKED_CLOCK"
    )

    second = coordinator.evaluate(
        evaluated_monotonic_ns=200,
        execution_mode_disabled=True,
        identity=identity(),
        clock=clock(),
        coinbase=coinbase(),
        kalshi=kalshi(),
    )

    assert second.state == (
        "READY_READ_ONLY"
    )


def test_monotonic_regression_is_hard_failure_and_latches():
    coordinator = SoakReadinessCoordinator(
        expected_boot_id=BOOT
    )

    first = coordinator.evaluate(
        evaluated_monotonic_ns=200,
        execution_mode_disabled=True,
        identity=identity(),
        clock=clock(),
        coinbase=coinbase(),
        kalshi=kalshi(),
    )

    assert first.state == (
        "READY_READ_ONLY"
    )

    second = coordinator.evaluate(
        evaluated_monotonic_ns=199,
        execution_mode_disabled=True,
        identity=identity(),
        clock=clock(),
        coinbase=coinbase(),
        kalshi=kalshi(),
    )

    assert second.state == "FATAL"
    assert second.reason == (
        "LOCAL_MONOTONIC_TIME_REGRESSION"
    )

    # Fresh-looking evidence cannot recover a hard failure.
    third = coordinator.evaluate(
        evaluated_monotonic_ns=300,
        execution_mode_disabled=True,
        identity=identity(),
        clock=clock(),
        coinbase=coinbase(),
        kalshi=kalshi(),
    )

    assert third.state == "FATAL"
    assert third.reason == (
        "LOCAL_MONOTONIC_TIME_REGRESSION"
    )


def test_hard_failure_from_evidence_latches():
    coordinator = SoakReadinessCoordinator(
        expected_boot_id=BOOT
    )

    first = coordinator.evaluate(
        evaluated_monotonic_ns=100,
        execution_mode_disabled=False,
        identity=identity(),
        clock=clock(),
        coinbase=coinbase(),
        kalshi=kalshi(),
    )

    assert first.state == "FATAL"

    second = coordinator.evaluate(
        evaluated_monotonic_ns=200,
        execution_mode_disabled=True,
        identity=identity(),
        clock=clock(),
        coinbase=coinbase(),
        kalshi=kalshi(),
    )

    assert second.state == "FATAL"
    assert second.reason == (
        "EXECUTION_MODE_NOT_DISABLED"
    )
