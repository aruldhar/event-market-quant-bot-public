import json
import threading
import time

import pytest

from src.kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from src.kxbtcd_candidate_e_soak_manifest import (
    DESIGN_FINGERPRINT,
    SoakManifestError,
    SoakRunManifest,
)
from src.kxbtcd_candidate_e_soak_manifest_lifecycle import (
    SoakManifestLifecycleError,
    classify_runner_terminal,
    run_soak_with_manifest_lifecycle,
)
from src.kxbtcd_candidate_e_soak_readiness import (
    SoakReadinessResult,
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
    def __init__(
        self,
        *,
        jump_seconds,
    ):
        self.ns = 0
        self.jump_ns = int(
            jump_seconds
            * 1_000_000_000
        )

    def monotonic_ns(self):
        return self.ns

    def sleep(self, seconds):
        self.ns += (
            self.jump_ns
        )


class FakeUtc:
    def __init__(
        self,
        values,
    ):
        self.values = list(
            values
        )

    def __call__(self):
        if not self.values:
            raise AssertionError(
                "unexpected UTC clock read"
            )

        return self.values.pop(
            0
        )


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


def blocked():
    return SoakReadinessResult(
        state="BLOCKED_CLOCK",
        status=GateStatus.BLOCKED,
        reason="CLOCK_EVIDENCE_STALE",
        ready_read_only=False,
        expected_boot_id=BOOT,
        current_boot_id=BOOT,
        current_time_namespace_id=(
            "time:[4026531834]"
        ),
        identity_reason="PASS",
        clock_reason=(
            "CLOCK_EVIDENCE_STALE"
        ),
        coinbase_reason="PASS",
        kalshi_reason="PASS",
    )


def wait_supervisor(
    stop_event,
):
    stop_event.wait()


def common_kwargs(
    tmp_path,
    *,
    clock,
    utc,
    sample=None,
):
    artifact_root = (
        tmp_path
        / "artifacts"
    )

    artifact_root.mkdir(
        exist_ok=True
    )

    metrics = (
        artifact_root
        / "metrics.jsonl"
    )

    metrics.write_bytes(
        b'{"metric":"synthetic"}\n'
    )

    return {
        "manifest_path": (
            tmp_path
            / "run.json"
        ),
        "run_id": (
            "candidate_e_soak_lifecycle_001"
        ),
        "run_role": (
            "AWS_SHAKEDOWN"
        ),
        "design_fingerprint": (
            DESIGN_FINGERPRINT
        ),
        "git_head": (
            GIT_HEAD
        ),
        "docker_image_digest": (
            IMAGE_DIGEST
        ),
        "host_boot_id": (
            BOOT
        ),
        "requested_active_duration_seconds": (
            3600
        ),
        "initial_filesystem_free_bytes": (
            50_000_000_000
        ),
        "expected_boot_id": (
            BOOT
        ),
        "run_coinbase_supervisor": (
            wait_supervisor
        ),
        "run_kalshi_supervisor": (
            wait_supervisor
        ),
        "sample_readiness": (
            sample
            if sample is not None
            else (
                lambda _: ready()
            )
        ),
        "credential_presence": {
            "kalshi_api_key_id": True,
            "kalshi_private_key_file": True,
        },
        "artifact_files": [
            (
                "runtime_metrics",
                metrics,
            )
        ],
        "artifact_root": (
            artifact_root
        ),
        "readiness_evaluation_interval_seconds": (
            1
        ),
        "source_join_timeout_seconds": (
            1
        ),
        "monotonic_ns": (
            clock.monotonic_ns
        ),
        "sleep_seconds": (
            clock.sleep
        ),
        "utc_now_text": (
            utc
        ),
    }


def test_measurement_complete_terminalizes_manifest_after_sources_stop(
    tmp_path,
    monkeypatch,
):
    clock = JumpClock(
        jump_seconds=3600
    )

    utc = FakeUtc(
        [
            "2026-09-05T07:00:00Z",
            "2026-09-05T08:00:00Z",
        ]
    )

    coinbase_stopped = (
        threading.Event()
    )

    kalshi_stopped = (
        threading.Event()
    )

    def coinbase(
        stop_event,
    ):
        stop_event.wait()
        coinbase_stopped.set()

    def kalshi(
        stop_event,
    ):
        stop_event.wait()
        kalshi_stopped.set()

    real_terminalize = (
        SoakRunManifest.terminalize
    )

    def checked_terminalize(
        self,
        **kwargs,
    ):
        assert (
            coinbase_stopped.is_set()
        )

        assert (
            kalshi_stopped.is_set()
        )

        return real_terminalize(
            self,
            **kwargs,
        )

    monkeypatch.setattr(
        SoakRunManifest,
        "terminalize",
        checked_terminalize,
    )

    kwargs = common_kwargs(
        tmp_path,
        clock=clock,
        utc=utc,
    )

    kwargs[
        "run_coinbase_supervisor"
    ] = coinbase

    kwargs[
        "run_kalshi_supervisor"
    ] = kalshi

    result = (
        run_soak_with_manifest_lifecycle(
            **kwargs
        )
    )

    document = (
        result.terminal_manifest
    )

    assert (
        document[
            "lifecycle_state"
        ]
        == "TERMINAL"
    )

    assert (
        document[
            "measurement_complete"
        ]
        is True
    )

    assert (
        document[
            "active_duration_seconds"
        ]
        == 3600
    )

    assert (
        document[
            "safety_invariant_status"
        ]
        == "PASS"
    )

    assert (
        document[
            "operational_classification"
        ]
        == "MEASUREMENT_COMPLETE"
    )

    assert (
        document[
            "orders"
        ]
        == 0
    )

    assert (
        document[
            "production_writes"
        ]
        == 0
    )

    assert len(
        document[
            "artifact_descriptors"
        ]
    ) == 1


def test_initial_readiness_timeout_is_not_mislabeled_as_safety_failure(
    tmp_path,
):
    clock = JumpClock(
        jump_seconds=300
    )

    utc = FakeUtc(
        [
            "2026-09-05T07:00:00Z",
            "2026-09-05T07:05:00Z",
        ]
    )

    kwargs = common_kwargs(
        tmp_path,
        clock=clock,
        utc=utc,
        sample=lambda _: blocked(),
    )

    result = (
        run_soak_with_manifest_lifecycle(
            **kwargs
        )
    )

    document = (
        result.terminal_manifest
    )

    assert (
        document[
            "measurement_complete"
        ]
        is False
    )

    assert (
        document[
            "active_duration_seconds"
        ]
        == 0
    )

    assert (
        document[
            "safety_invariant_status"
        ]
        == "PASS"
    )

    assert (
        document[
            "operational_classification"
        ]
        == "INITIAL_READINESS_TIMEOUT"
    )


def test_source_supervisor_exception_terminalizes_hard_fail(
    tmp_path,
):
    clock = JumpClock(
        jump_seconds=1
    )

    utc = FakeUtc(
        [
            "2026-09-05T07:00:00Z",
            "2026-09-05T07:00:01Z",
        ]
    )

    started = (
        threading.Event()
    )

    def fail_coinbase(
        stop_event,
    ):
        started.set()

        raise RuntimeError(
            "synthetic supervisor crash"
        )

    def sample(_):
        started.wait(
            timeout=1
        )

        return ready()

    kwargs = common_kwargs(
        tmp_path,
        clock=clock,
        utc=utc,
        sample=sample,
    )

    kwargs[
        "run_coinbase_supervisor"
    ] = fail_coinbase

    result = (
        run_soak_with_manifest_lifecycle(
            **kwargs
        )
    )

    assert (
        result.runner.source_failure
        == (
            "COINBASE_SUPERVISOR_EXCEPTION:"
            "RuntimeError"
        )
    )

    assert (
        result.terminal_manifest[
            "safety_invariant_status"
        ]
        == "FAIL"
    )

    assert (
        result.terminal_manifest[
            "operational_classification"
        ]
        == "HARD_FAIL"
    )

    assert (
        result.terminal_manifest[
            "measurement_complete"
        ]
        is False
    )


def test_manifest_creation_failure_still_starts_zero_sources(
    tmp_path,
):
    clock = JumpClock(
        jump_seconds=3600
    )

    utc = FakeUtc(
        [
            "2026-09-05T07:00:00Z",
        ]
    )

    manifest_path = (
        tmp_path
        / "run.json"
    )

    manifest_path.write_text(
        '{"already":"exists"}\n',
        encoding="utf-8",
    )

    calls = {
        "coinbase": 0,
        "kalshi": 0,
    }

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

    kwargs = common_kwargs(
        tmp_path,
        clock=clock,
        utc=utc,
    )

    kwargs[
        "manifest_path"
    ] = manifest_path

    kwargs[
        "run_coinbase_supervisor"
    ] = coinbase

    kwargs[
        "run_kalshi_supervisor"
    ] = kalshi

    with pytest.raises(
        Exception,
        match=(
            "before_source_start failed "
            "before source threads started"
        ),
    ):
        run_soak_with_manifest_lifecycle(
            **kwargs
        )

    assert calls == {
        "coinbase": 0,
        "kalshi": 0,
    }


def test_artifact_integrity_failure_cannot_return_successful_terminal_result(
    tmp_path,
    monkeypatch,
):
    clock = JumpClock(
        jump_seconds=3600
    )

    utc = FakeUtc(
        [
            "2026-09-05T07:00:00Z",
            "2026-09-05T08:00:00Z",
        ]
    )

    def fail_terminalize(
        self,
        **kwargs,
    ):
        raise SoakManifestError(
            "synthetic terminal integrity failure"
        )

    monkeypatch.setattr(
        SoakRunManifest,
        "terminalize",
        fail_terminalize,
    )

    kwargs = common_kwargs(
        tmp_path,
        clock=clock,
        utc=utc,
    )

    with pytest.raises(
        SoakManifestLifecycleError,
        match=(
            "terminal soak manifest persistence "
            "or integrity validation failed"
        ),
    ):
        run_soak_with_manifest_lifecycle(
            **kwargs
        )

    document = json.loads(
        (
            tmp_path
            / "run.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    # We did not fabricate successful terminal evidence.
    assert (
        document[
            "lifecycle_state"
        ]
        == "RUNNING"
    )


def test_runner_crash_after_running_manifest_leaves_running_receipt(
    tmp_path,
):
    clock = JumpClock(
        jump_seconds=1
    )

    utc = FakeUtc(
        [
            "2026-09-05T07:00:00Z",
        ]
    )

    kwargs = common_kwargs(
        tmp_path,
        clock=clock,
        utc=utc,
    )

    def explode_sleep(
        seconds,
    ):
        raise RuntimeError(
            "synthetic coordinator-visible runner crash"
        )

    kwargs[
        "sleep_seconds"
    ] = explode_sleep

    with pytest.raises(
        RuntimeError,
        match="runner crash",
    ):
        run_soak_with_manifest_lifecycle(
            **kwargs
        )

    document = json.loads(
        (
            tmp_path
            / "run.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert (
        document[
            "lifecycle_state"
        ]
        == "RUNNING"
    )


def test_nonstopped_supervisor_blocks_terminalization(
    tmp_path,
):
    clock = JumpClock(
        jump_seconds=3600
    )

    utc = FakeUtc(
        [
            "2026-09-05T07:00:00Z",
        ]
    )

    release = (
        threading.Event()
    )

    def stubborn(
        stop_event,
    ):
        # Ignore the runner stop signal long enough to exceed the tiny join
        # timeout, but do eventually return so the unit-test process can exit.
        release.wait(
            timeout=0.25
        )

    kwargs = common_kwargs(
        tmp_path,
        clock=clock,
        utc=utc,
    )

    kwargs[
        "run_coinbase_supervisor"
    ] = stubborn

    kwargs[
        "source_join_timeout_seconds"
    ] = 0.01

    try:
        with pytest.raises(
            SoakManifestLifecycleError,
            match=(
                "source supervisor remains alive"
            ),
        ):
            run_soak_with_manifest_lifecycle(
                **kwargs
            )
    finally:
        release.set()

        # Allow the non-daemon synthetic worker to observe release.
        time.sleep(
            0.02
        )

    document = json.loads(
        (
            tmp_path
            / "run.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert (
        document[
            "lifecycle_state"
        ]
        == "RUNNING"
    )
