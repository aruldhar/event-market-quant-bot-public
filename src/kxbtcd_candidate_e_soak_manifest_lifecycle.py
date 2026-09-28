"""Checkpoint 21N-Z-F soak manifest / runner lifecycle coordinator.

This layer composes two already-tested components:

- SoakRunManifest
- run_soak_runner_shell

It does not implement network transports, source logic, model logic, signals,
settlement access, P&L, orders, or production writes.

Frozen ordering:

1. capture start identity;
2. runner validates its own configuration;
3. durable RUNNING manifest is created and revalidated;
4. only then may Coinbase/Kalshi source threads start;
5. runner reaches a terminal timing state and stops/joins both sources;
6. only after both source threads are stopped may artifacts be hashed and the
   manifest become TERMINAL.

If the runner itself unexpectedly raises after the RUNNING manifest exists,
this coordinator deliberately leaves that manifest RUNNING rather than
inventing terminal duration/classification evidence.

If terminal manifest persistence or artifact verification fails, the attempt
must not be reported as successfully terminalized.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Callable, Iterable, Mapping

from .kxbtcd_candidate_e_soak_manifest import (
    SoakManifestError,
    SoakRunManifest,
)
from .kxbtcd_candidate_e_soak_readiness import (
    SoakReadinessResult,
)
from .kxbtcd_candidate_e_soak_runner_shell import (
    DEFAULT_SOURCE_JOIN_TIMEOUT_SECONDS,
    SoakRunnerShellResult,
    run_soak_runner_shell,
)


class SoakManifestLifecycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class SoakManifestLifecycleResult:
    runner: SoakRunnerShellResult
    manifest_path: Path
    terminal_manifest: Mapping[str, object]


def classify_runner_terminal(
    result: SoakRunnerShellResult,
) -> tuple[str, str]:
    """Map runner evidence to frozen manifest safety/operational fields."""

    if result.source_failure is not None:
        return (
            "FAIL",
            "HARD_FAIL",
        )

    if result.run.state == "FATAL":
        return (
            "FAIL",
            "HARD_FAIL",
        )

    if (
        result.run.state
        == "INITIAL_READINESS_TIMEOUT"
    ):
        return (
            "PASS",
            "INITIAL_READINESS_TIMEOUT",
        )

    if (
        result.run.state
        == "MEASUREMENT_COMPLETE"
    ):
        return (
            "PASS",
            "MEASUREMENT_COMPLETE",
        )

    raise SoakManifestLifecycleError(
        "runner returned without a recognized terminal state"
    )


def run_soak_with_manifest_lifecycle(
    *,
    manifest_path: str | Path,
    run_id: str,
    run_role: str,
    design_fingerprint: str,
    git_head: str,
    docker_image_digest: str,
    host_boot_id: str,
    requested_active_duration_seconds: int,
    initial_filesystem_free_bytes: int,
    expected_boot_id: str,
    run_coinbase_supervisor,
    run_kalshi_supervisor,
    sample_readiness: Callable[
        [int],
        SoakReadinessResult,
    ],
    credential_presence: (
        Mapping[str, object]
        | None
    ) = None,
    artifact_files: Iterable[
        tuple[
            str,
            str | Path,
        ]
    ] = (),
    artifact_root: str | Path | None = None,
    readiness_evaluation_interval_seconds: float = 1.0,
    source_join_timeout_seconds: float = DEFAULT_SOURCE_JOIN_TIMEOUT_SECONDS,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    sleep_seconds: Callable[[float], None] = time.sleep,
    utc_now_text: Callable[[], str],
    observability=None,
    close_runtime_artifacts: Callable[[], Iterable[tuple[str, str | Path]]] | None = None,
) -> SoakManifestLifecycleResult:
    """Run one offline/live-capable shell attempt with its frozen manifest."""

    start_ns = int(
        monotonic_ns()
    )

    started_utc = str(
        utc_now_text()
    )

    holder: dict[
        str,
        SoakRunManifest,
    ] = {}

    def prepare_running_manifest() -> None:
        holder[
            "manifest"
        ] = SoakRunManifest(
            manifest_path=(
                manifest_path
            ),
            run_id=run_id,
            run_role=run_role,
            design_fingerprint=(
                design_fingerprint
            ),
            git_head=git_head,
            docker_image_digest=(
                docker_image_digest
            ),
            host_boot_id=(
                host_boot_id
            ),
            requested_active_duration_seconds=(
                requested_active_duration_seconds
            ),
            started_utc=(
                started_utc
            ),
            started_monotonic_ns=(
                start_ns
            ),
            initial_filesystem_free_bytes=(
                initial_filesystem_free_bytes
            ),
            execution_mode=(
                "disabled"
            ),
            credential_presence=(
                credential_presence
            ),
        )

        if observability is not None:
            observability.start(run_id=run_id, started_monotonic_ns=start_ns)

    # On an unexpected exception, release telemetry handles and re-raise.
    # Preserve RUNNING rather than inventing terminal timing evidence.
    try:
        runner_result = (
            run_soak_runner_shell(
                expected_boot_id=(
                    expected_boot_id
                ),
                requested_active_duration_seconds=(
                    requested_active_duration_seconds
                ),
                run_coinbase_supervisor=(
                    run_coinbase_supervisor
                ),
                run_kalshi_supervisor=(
                    run_kalshi_supervisor
                ),
                sample_readiness=(
                    sample_readiness
                ),
                started_monotonic_ns=(
                    start_ns
                ),
                readiness_evaluation_interval_seconds=(
                    readiness_evaluation_interval_seconds
                ),
                source_join_timeout_seconds=(
                    source_join_timeout_seconds
                ),
                monotonic_ns=(
                    monotonic_ns
                ),
                sleep_seconds=(
                    sleep_seconds
                ),
                before_source_start=(
                    prepare_running_manifest
                ),
                observe_snapshot=(observability.observe if observability is not None else None),
            )
        )
    except BaseException:
        if observability is not None:
            observability.abort()
        raise

    manifest = holder.get(
        "manifest"
    )

    if manifest is None:
        raise SoakManifestLifecycleError(
            "runner returned without a persisted RUNNING soak manifest"
        )

    # Do not freeze artifact hashes while a supposedly stopped source can
    # still be changing runtime evidence.
    if not (
        runner_result.coinbase_thread_stopped
        and runner_result.kalshi_thread_stopped
    ):
        raise SoakManifestLifecycleError(
            "cannot terminalize soak manifest while a source supervisor "
            "remains alive"
        )

    (
        safety_status,
        operational_classification,
    ) = classify_runner_terminal(
        runner_result
    )

    # All source writers are stopped above. Close/verify raw segments before
    # sealing telemetry and before discovering the final artifact inventory.
    try:
        final_artifacts = list(artifact_files)
        if close_runtime_artifacts is not None:
            final_artifacts.extend(close_runtime_artifacts())
        if observability is not None:
            final_artifacts.extend(observability.finish(runner_result, safety_status))
    except BaseException:
        if observability is not None:
            observability.abort()
        raise

    ended_utc = str(
        utc_now_text()
    )

    # Use the runner's final evaluated monotonic timestamp rather than taking a
    # new measurement. This binds terminal timing to the same evidence returned
    # by the runner and avoids adding post-run time to the attempt.
    ended_monotonic_ns = int(
        runner_result.run.evaluated_monotonic_ns
    )

    try:
        terminal_manifest = (
            manifest.terminalize(
                ended_utc=(
                    ended_utc
                ),
                ended_monotonic_ns=(
                    ended_monotonic_ns
                ),
                active_duration_seconds=(
                    runner_result.run.active_elapsed_seconds
                ),
                measurement_complete=(
                    runner_result.run.measurement_complete
                ),
                safety_invariant_status=(
                    safety_status
                ),
                operational_classification=(
                    operational_classification
                ),
                orders=0,
                production_writes=0,
                artifact_files=(
                    final_artifacts
                ),
                artifact_root=(
                    artifact_root
                ),
            )
        )
    except SoakManifestError as exc:
        raise SoakManifestLifecycleError(
            "terminal soak manifest persistence or integrity validation failed"
        ) from exc

    return SoakManifestLifecycleResult(
        runner=(
            runner_result
        ),
        manifest_path=(
            Path(
                manifest_path
            )
        ),
        terminal_manifest=(
            terminal_manifest
        ),
    )
