import json
import threading

import pytest

from src.kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from src.kxbtcd_candidate_e_soak_manifest import (
    DESIGN_FINGERPRINT,
    EXECUTION_MODE,
    SoakRunManifest,
)
from src.kxbtcd_candidate_e_soak_readiness import (
    SoakReadinessResult,
)
from src.kxbtcd_candidate_e_soak_runner_shell import (
    SoakRunnerShellError,
    run_soak_runner_shell,
)


BOOT = (
    "11111111-2222-3333-4444-555555555555"
)

GIT_HEAD = (
    "b" * 40
)

IMAGE_DIGEST = (
    "sha256:"
    + "a" * 64
)


class JumpClock:
    """Fake monotonic clock that makes long frozen durations cheap to test."""

    def __init__(
        self,
        *,
        jump_seconds=3600,
    ):
        self.ns = 0
        self.jump_ns = int(
            jump_seconds
            * 1_000_000_000
        )

    def monotonic_ns(self):
        return self.ns

    def sleep(self, seconds):
        # Deliberately ignore the requested sleep duration in this offline
        # test. The runner still validates that its configured polling
        # interval is <=5 seconds; this simply advances fake time quickly.
        self.ns += self.jump_ns


def ready():
    return SoakReadinessResult(
        state="READY_READ_ONLY",
        status=GateStatus.PASS,
        reason="PASS",
        ready_read_only=True,
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


def wait_supervisor(
    stop_event,
):
    stop_event.wait()


def test_real_running_manifest_exists_before_either_supervisor_executes(
    tmp_path,
):
    clock = JumpClock()

    manifest_path = (
        tmp_path
        / "run.json"
    )

    created = {
        "manifest": None,
    }

    observations = []
    observation_lock = (
        threading.Lock()
    )

    def prepare_manifest():
        created[
            "manifest"
        ] = SoakRunManifest(
            manifest_path=(
                manifest_path
            ),
            run_id=(
                "candidate_e_soak_boundary_001"
            ),
            run_role=(
                "AWS_SHAKEDOWN"
            ),
            design_fingerprint=(
                DESIGN_FINGERPRINT
            ),
            git_head=(
                GIT_HEAD
            ),
            docker_image_digest=(
                IMAGE_DIGEST
            ),
            host_boot_id=(
                BOOT
            ),
            requested_active_duration_seconds=(
                3600
            ),
            started_utc=(
                "2026-09-05T07:00:00Z"
            ),
            started_monotonic_ns=(
                0
            ),
            initial_filesystem_free_bytes=(
                50_000_000_000
            ),
            execution_mode=(
                EXECUTION_MODE
            ),
            credential_presence={
                "kalshi_api_key_id": True,
                "kalshi_private_key_file": True,
            },
        )

    def observe_then_wait(
        source_name,
        stop_event,
    ):
        assert (
            manifest_path.exists()
        )

        document = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        with observation_lock:
            observations.append(
                (
                    source_name,
                    document[
                        "lifecycle_state"
                    ],
                    document[
                        "execution_mode"
                    ],
                    document[
                        "run_id"
                    ],
                )
            )

        stop_event.wait()

    result = run_soak_runner_shell(
        expected_boot_id=(
            BOOT
        ),
        requested_active_duration_seconds=(
            3600
        ),
        run_coinbase_supervisor=lambda stop: (
            observe_then_wait(
                "coinbase",
                stop,
            )
        ),
        run_kalshi_supervisor=lambda stop: (
            observe_then_wait(
                "kalshi",
                stop,
            )
        ),
        sample_readiness=lambda _: (
            ready()
        ),
        started_monotonic_ns=(
            0
        ),
        readiness_evaluation_interval_seconds=(
            1
        ),
        source_join_timeout_seconds=(
            1
        ),
        monotonic_ns=(
            clock.monotonic_ns
        ),
        sleep_seconds=(
            clock.sleep
        ),
        before_source_start=(
            prepare_manifest
        ),
    )

    assert (
        result.run.state
        == "MEASUREMENT_COMPLETE"
    )

    assert (
        created[
            "manifest"
        ]
        is not None
    )

    assert sorted(
        observations
    ) == [
        (
            "coinbase",
            "RUNNING",
            "disabled",
            "candidate_e_soak_boundary_001",
        ),
        (
            "kalshi",
            "RUNNING",
            "disabled",
            "candidate_e_soak_boundary_001",
        ),
    ]


def test_manifest_preparation_failure_starts_zero_supervisors():
    clock = JumpClock()

    calls = {
        "coinbase": 0,
        "kalshi": 0,
        "prepare": 0,
    }

    def fail_prepare():
        calls[
            "prepare"
        ] += 1

        raise RuntimeError(
            "synthetic manifest persistence failure"
        )

    def coinbase(
        stop_event,
    ):
        calls[
            "coinbase"
        ] += 1

    def kalshi(
        stop_event,
    ):
        calls[
            "kalshi"
        ] += 1

    with pytest.raises(
        SoakRunnerShellError,
        match=(
            "before_source_start failed "
            "before source threads started"
        ),
    ):
        run_soak_runner_shell(
            expected_boot_id=(
                BOOT
            ),
            requested_active_duration_seconds=(
                3600
            ),
            run_coinbase_supervisor=(
                coinbase
            ),
            run_kalshi_supervisor=(
                kalshi
            ),
            sample_readiness=lambda _: (
                ready()
            ),
            started_monotonic_ns=(
                0
            ),
            readiness_evaluation_interval_seconds=(
                1
            ),
            monotonic_ns=(
                clock.monotonic_ns
            ),
            sleep_seconds=(
                clock.sleep
            ),
            before_source_start=(
                fail_prepare
            ),
        )

    assert calls == {
        "coinbase": 0,
        "kalshi": 0,
        "prepare": 1,
    }


def test_pre_start_hook_runs_exactly_once():
    clock = JumpClock()

    calls = {
        "prepare": 0,
    }

    def prepare():
        calls[
            "prepare"
        ] += 1

    result = run_soak_runner_shell(
        expected_boot_id=(
            BOOT
        ),
        requested_active_duration_seconds=(
            3600
        ),
        run_coinbase_supervisor=(
            wait_supervisor
        ),
        run_kalshi_supervisor=(
            wait_supervisor
        ),
        sample_readiness=lambda _: (
            ready()
        ),
        started_monotonic_ns=(
            0
        ),
        readiness_evaluation_interval_seconds=(
            1
        ),
        source_join_timeout_seconds=(
            1
        ),
        monotonic_ns=(
            clock.monotonic_ns
        ),
        sleep_seconds=(
            clock.sleep
        ),
        before_source_start=(
            prepare
        ),
    )

    assert (
        result.run.measurement_complete
    )

    assert calls[
        "prepare"
    ] == 1


def test_invalid_runner_configuration_fails_before_pre_start_hook():
    calls = {
        "prepare": 0,
    }

    def prepare():
        calls[
            "prepare"
        ] += 1

    with pytest.raises(
        SoakRunnerShellError,
        match="5-second maximum",
    ):
        run_soak_runner_shell(
            expected_boot_id=(
                BOOT
            ),
            requested_active_duration_seconds=(
                3600
            ),
            run_coinbase_supervisor=(
                wait_supervisor
            ),
            run_kalshi_supervisor=(
                wait_supervisor
            ),
            sample_readiness=lambda _: (
                ready()
            ),
            started_monotonic_ns=(
                0
            ),
            readiness_evaluation_interval_seconds=(
                5.1
            ),
            before_source_start=(
                prepare
            ),
        )

    assert calls[
        "prepare"
    ] == 0
