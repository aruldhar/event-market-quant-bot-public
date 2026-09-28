import threading

import pytest

from src.kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from src.kxbtcd_candidate_e_soak_readiness import (
    SoakReadinessResult,
)
from src.kxbtcd_candidate_e_soak_runner_shell import (
    DEFAULT_SOURCE_JOIN_TIMEOUT_SECONDS,
    SoakRunnerShellError,
    run_soak_runner_shell,
)


BOOT = (
    "11111111-2222-3333-4444-555555555555"
)


class FakeClock:
    def __init__(
        self,
        *,
        start_ns=0,
    ):
        self.ns = int(
            start_ns
        )

    def monotonic_ns(self):
        return self.ns

    def sleep(self, seconds):
        self.ns += int(
            float(seconds)
            * 1_000_000_000
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


def blocked():
    return readiness(
        state="BLOCKED_COINBASE",
        status=GateStatus.BLOCKED,
        reason="COINBASE_HEARTBEAT_STALE",
    )


def wait_supervisor(
    stop_event,
):
    stop_event.wait()


def test_default_shutdown_window_covers_pong_and_websocket_close_bounds():
    # Manual Pong wait and WebSocket close each allow five seconds. The
    # production runner needs a bounded scheduling margin before it can safely
    # hash terminal evidence.
    assert DEFAULT_SOURCE_JOIN_TIMEOUT_SECONDS >= 12


def test_combined_shell_completes_duration_and_stops_both_sources():
    clock = FakeClock()

    result = run_soak_runner_shell(
        expected_boot_id=BOOT,
        requested_active_duration_seconds=10,
        run_coinbase_supervisor=(
            wait_supervisor
        ),
        run_kalshi_supervisor=(
            wait_supervisor
        ),
        sample_readiness=lambda _: (
            readiness()
        ),
        started_monotonic_ns=0,
        readiness_evaluation_interval_seconds=1,
        source_join_timeout_seconds=1,
        monotonic_ns=(
            clock.monotonic_ns
        ),
        sleep_seconds=(
            clock.sleep
        ),
    )

    assert result.run.state == (
        "MEASUREMENT_COMPLETE"
    )

    assert result.run.measurement_complete

    assert (
        result.run.active_elapsed_seconds
        == 10
    )

    assert (
        result.run.ready_duration_seconds
        == 10
    )

    assert (
        result.run.blocked_duration_seconds
        == 0
    )

    assert result.coinbase_thread_started
    assert result.kalshi_thread_started
    assert result.coinbase_thread_stopped
    assert result.kalshi_thread_stopped
    assert result.source_failure is None


def test_blocked_intervals_do_not_pause_combined_shell_timer():
    clock = FakeClock()

    def sample(now_ns):
        seconds = (
            now_ns
            / 1_000_000_000
        )

        if 3 <= seconds < 8:
            return blocked()

        return readiness()

    result = run_soak_runner_shell(
        expected_boot_id=BOOT,
        requested_active_duration_seconds=10,
        run_coinbase_supervisor=(
            wait_supervisor
        ),
        run_kalshi_supervisor=(
            wait_supervisor
        ),
        sample_readiness=sample,
        started_monotonic_ns=0,
        readiness_evaluation_interval_seconds=1,
        source_join_timeout_seconds=1,
        monotonic_ns=(
            clock.monotonic_ns
        ),
        sleep_seconds=clock.sleep,
    )

    assert result.run.state == (
        "MEASUREMENT_COMPLETE"
    )

    assert (
        result.run.active_elapsed_seconds
        == 10
    )

    assert (
        result.run.ready_duration_seconds
        == 5
    )

    assert (
        result.run.blocked_duration_seconds
        == 5
    )


def test_initial_readiness_timeout_stops_both_supervisors():
    clock = FakeClock()

    result = run_soak_runner_shell(
        expected_boot_id=BOOT,
        requested_active_duration_seconds=10,
        run_coinbase_supervisor=(
            wait_supervisor
        ),
        run_kalshi_supervisor=(
            wait_supervisor
        ),
        sample_readiness=lambda _: (
            blocked()
        ),
        started_monotonic_ns=0,
        readiness_evaluation_interval_seconds=5,
        source_join_timeout_seconds=1,
        monotonic_ns=(
            clock.monotonic_ns
        ),
        sleep_seconds=clock.sleep,
    )

    assert result.run.state == (
        "INITIAL_READINESS_TIMEOUT"
    )

    assert not (
        result.run.measurement_complete
    )

    assert result.coinbase_thread_stopped
    assert result.kalshi_thread_stopped


def test_coinbase_supervisor_exception_becomes_fatal():
    clock = FakeClock()

    started = threading.Event()

    def fail(stop_event):
        started.set()

        raise ConnectionError(
            "synthetic Coinbase supervisor failure"
        )

    def sample(_):
        # Give the worker thread a deterministic chance to execute before
        # readiness could otherwise complete the tiny fake run.
        started.wait(
            timeout=1
        )

        return readiness()

    result = run_soak_runner_shell(
        expected_boot_id=BOOT,
        requested_active_duration_seconds=100,
        run_coinbase_supervisor=fail,
        run_kalshi_supervisor=(
            wait_supervisor
        ),
        sample_readiness=sample,
        started_monotonic_ns=0,
        readiness_evaluation_interval_seconds=1,
        source_join_timeout_seconds=1,
        monotonic_ns=clock.monotonic_ns,
        sleep_seconds=clock.sleep,
    )

    assert result.run.state == "FATAL"

    assert result.source_failure == (
        "COINBASE_SUPERVISOR_EXCEPTION:"
        "ConnectionError"
    )

    assert result.coinbase_thread_stopped
    assert result.kalshi_thread_stopped


def test_segment_manager_failure_uses_safe_exception_class_only():
    clock = FakeClock()
    started = threading.Event()

    def fail(stop_event):
        started.set()
        from src.kxbtcd_candidate_e_soak_segment_manager import SoakSegmentManagerError
        raise SoakSegmentManagerError("unsafe path /var/lib/kxbtcd-secrets/key.pem")

    def sample(_):
        started.wait(timeout=1)
        # The worker signals immediately before raising; yield once so its
        # wrapper can capture the exception before the fake clock advances.
        threading.Event().wait(timeout=0.01)
        return readiness()

    result = run_soak_runner_shell(
        expected_boot_id=BOOT,
        requested_active_duration_seconds=100,
        run_coinbase_supervisor=wait_supervisor,
        run_kalshi_supervisor=fail,
        sample_readiness=sample,
        started_monotonic_ns=0,
        readiness_evaluation_interval_seconds=1,
        source_join_timeout_seconds=1,
        monotonic_ns=clock.monotonic_ns,
        sleep_seconds=clock.sleep,
    )

    assert result.run.state == "FATAL"
    assert result.source_failure == "KALSHI_SUPERVISOR_EXCEPTION:SoakSegmentManagerError"
    assert "unsafe" not in result.final_readiness_reason
    assert "/" not in result.final_readiness_reason


def test_unexpected_normal_supervisor_exit_is_fatal():
    clock = FakeClock()

    exited = threading.Event()

    def return_immediately(
        stop_event,
    ):
        exited.set()
        return None

    def sample(_):
        exited.wait(
            timeout=1
        )
        return readiness()

    result = run_soak_runner_shell(
        expected_boot_id=BOOT,
        requested_active_duration_seconds=100,
        run_coinbase_supervisor=(
            return_immediately
        ),
        run_kalshi_supervisor=(
            wait_supervisor
        ),
        sample_readiness=sample,
        started_monotonic_ns=0,
        readiness_evaluation_interval_seconds=1,
        source_join_timeout_seconds=1,
        monotonic_ns=clock.monotonic_ns,
        sleep_seconds=clock.sleep,
    )

    assert result.run.state == "FATAL"

    assert result.source_failure == (
        "COINBASE_SUPERVISOR_EXITED_UNEXPECTEDLY"
    )


def test_readiness_sampler_exception_becomes_fatal():
    clock = FakeClock()

    def sample(_):
        raise RuntimeError(
            "synthetic readiness failure"
        )

    result = run_soak_runner_shell(
        expected_boot_id=BOOT,
        requested_active_duration_seconds=10,
        run_coinbase_supervisor=(
            wait_supervisor
        ),
        run_kalshi_supervisor=(
            wait_supervisor
        ),
        sample_readiness=sample,
        started_monotonic_ns=0,
        readiness_evaluation_interval_seconds=1,
        source_join_timeout_seconds=1,
        monotonic_ns=clock.monotonic_ns,
        sleep_seconds=clock.sleep,
    )

    assert result.run.state == "FATAL"

    assert result.source_failure == (
        "READINESS_SAMPLER_EXCEPTION:"
        "RuntimeError"
    )


def test_interval_above_five_seconds_is_rejected_before_threads_start():
    with pytest.raises(
        SoakRunnerShellError,
        match="5-second maximum",
    ):
        run_soak_runner_shell(
            expected_boot_id=BOOT,
            requested_active_duration_seconds=10,
            run_coinbase_supervisor=(
                wait_supervisor
            ),
            run_kalshi_supervisor=(
                wait_supervisor
            ),
            sample_readiness=lambda _: (
                readiness()
            ),
            started_monotonic_ns=0,
            readiness_evaluation_interval_seconds=5.1,
        )


def test_no_signal_or_execution_fields_exist_in_runner_result():
    fields = set(
        getattr(
            __import__(
                "src.kxbtcd_candidate_e_soak_runner_shell",
                fromlist=[
                    "SoakRunnerShellResult"
                ],
            ),
            "SoakRunnerShellResult",
        ).__dataclass_fields__
    )

    forbidden = {
        "signal",
        "probability",
        "pnl",
        "order",
        "orders",
        "fills",
        "position",
    }

    assert not (
        fields
        & forbidden
    )
