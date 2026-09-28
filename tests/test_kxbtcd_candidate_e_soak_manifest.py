import json
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_soak_archive import (
    write_json_atomic,
)
from src.kxbtcd_candidate_e_soak_manifest import (
    DESIGN_FINGERPRINT,
    EXECUTION_MODE,
    SCHEMA_VERSION,
    SoakManifestError,
    SoakRunManifest,
    validate_soak_run_manifest,
)


GIT_HEAD = "b" * 40

IMAGE_DIGEST = (
    "sha256:"
    + "a" * 64
)

BOOT_ID = (
    "11111111-2222-3333-4444-555555555555"
)

STARTED_UTC = (
    "2026-09-05T07:00:00Z"
)


def s(
    seconds,
):
    return int(
        seconds
        * 1_000_000_000
    )


def new_manifest(
    tmp_path,
    **overrides,
):
    values = {
        "manifest_path": (
            tmp_path
            / "run.json"
        ),
        "run_id": (
            "candidate_e_soak_test_001"
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
            BOOT_ID
        ),
        "requested_active_duration_seconds": (
            3600
        ),
        "started_utc": (
            STARTED_UTC
        ),
        "started_monotonic_ns": (
            0
        ),
        "initial_filesystem_free_bytes": (
            50_000_000_000
        ),
        "execution_mode": (
            EXECUTION_MODE
        ),
        "credential_presence": {
            "kalshi_api_key_id": True,
            "kalshi_private_key_file": True,
        },
    }

    values.update(
        overrides
    )

    return SoakRunManifest(
        **values
    )


def test_running_manifest_is_written_before_any_external_work(
    tmp_path,
):
    manifest = new_manifest(
        tmp_path
    )

    assert (
        manifest.manifest_path.exists()
    )

    document = (
        validate_soak_run_manifest(
            manifest.manifest_path
        )
    )

    assert (
        document[
            "schema_version"
        ]
        == SCHEMA_VERSION
    )

    assert (
        document[
            "lifecycle_state"
        ]
        == "RUNNING"
    )

    assert (
        document[
            "execution_mode"
        ]
        == "disabled"
    )

    assert (
        document[
            "design_fingerprint"
        ]
        == DESIGN_FINGERPRINT
    )

    assert (
        document[
            "artifact_descriptors"
        ]
        == []
    )


def test_existing_manifest_is_never_replaced_on_initial_create(
    tmp_path,
):
    path = (
        tmp_path
        / "run.json"
    )

    path.write_text(
        '{"existing":true}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        SoakManifestError,
        match="refusing to replace existing soak manifest",
    ):
        new_manifest(
            tmp_path,
            manifest_path=path,
        )

    assert json.loads(
        path.read_text(
            encoding="utf-8"
        )
    ) == {
        "existing": True
    }


def test_wrong_design_fingerprint_fails_before_manifest_write(
    tmp_path,
):
    with pytest.raises(
        SoakManifestError,
        match="design_fingerprint",
    ):
        new_manifest(
            tmp_path,
            design_fingerprint=(
                "0" * 64
            ),
        )

    assert not (
        tmp_path
        / "run.json"
    ).exists()


def test_execution_mode_must_be_disabled(
    tmp_path,
):
    with pytest.raises(
        SoakManifestError,
        match="execution_mode",
    ):
        new_manifest(
            tmp_path,
            execution_mode="enabled",
        )


def test_only_frozen_active_durations_are_allowed(
    tmp_path,
):
    with pytest.raises(
        SoakManifestError,
        match="3600 or 86400",
    ):
        new_manifest(
            tmp_path,
            requested_active_duration_seconds=7200,
        )


def test_credential_presence_accepts_booleans_not_values(
    tmp_path,
):
    with pytest.raises(
        SoakManifestError,
        match="boolean only",
    ):
        new_manifest(
            tmp_path,
            credential_presence={
                "kalshi_api_key_id": (
                    "secret-value"
                ),
            },
        )


def test_terminalization_preserves_start_identity_and_hashes_artifacts(
    tmp_path,
):
    manifest = new_manifest(
        tmp_path
    )

    artifact_root = (
        tmp_path
        / "artifacts"
    )

    artifact_root.mkdir()

    metrics = (
        artifact_root
        / "metrics.jsonl"
    )

    metrics.write_bytes(
        b'{"cpu":1}\n'
    )

    before = (
        validate_soak_run_manifest(
            manifest.manifest_path
        )
    )

    final = (
        manifest.terminalize(
            ended_utc=(
                "2026-09-05T08:01:00Z"
            ),
            ended_monotonic_ns=(
                s(3660)
            ),
            active_duration_seconds=3600,
            measurement_complete=True,
            safety_invariant_status=(
                "PASS"
            ),
            operational_classification=(
                "MEASUREMENT_COMPLETE"
            ),
            orders=0,
            production_writes=0,
            artifact_files=[
                (
                    "runtime_metrics",
                    metrics,
                )
            ],
            artifact_root=(
                artifact_root
            ),
        )
    )

    assert (
        final[
            "lifecycle_state"
        ]
        == "TERMINAL"
    )

    immutable = (
        "run_id",
        "run_role",
        "design_fingerprint",
        "git_head",
        "docker_image_digest",
        "host_boot_id",
        "requested_active_duration_seconds",
        "started_utc",
        "started_monotonic_ns",
        "initial_filesystem_free_bytes",
        "execution_mode",
    )

    for field in immutable:
        assert (
            final[
                field
            ]
            == before[
                field
            ]
        )

    assert (
        final[
            "artifact_descriptors"
        ][0][
            "path"
        ]
        == "metrics.jsonl"
    )

    assert (
        final[
            "artifact_descriptors"
        ][0][
            "size_bytes"
        ]
        == metrics.stat().st_size
    )

    assert len(
        final[
            "artifact_descriptors"
        ][0][
            "sha256"
        ]
    ) == 64


def test_measurement_complete_requires_exact_requested_duration(
    tmp_path,
):
    manifest = new_manifest(
        tmp_path
    )

    with pytest.raises(
        SoakManifestError,
        match="exact requested active duration",
    ):
        manifest.terminalize(
            ended_utc=(
                "2026-09-05T08:01:00Z"
            ),
            ended_monotonic_ns=(
                s(3660)
            ),
            active_duration_seconds=3599,
            measurement_complete=True,
            safety_invariant_status="PASS",
            operational_classification=(
                "MEASUREMENT_COMPLETE"
            ),
            orders=0,
            production_writes=0,
        )


def test_persisted_start_identity_tamper_blocks_terminalization(
    tmp_path,
):
    manifest = new_manifest(
        tmp_path
    )

    document = json.loads(
        manifest.manifest_path.read_text(
            encoding="utf-8"
        )
    )

    document[
        "git_head"
    ] = "c" * 40

    write_json_atomic(
        manifest.manifest_path,
        document,
    )

    with pytest.raises(
        SoakManifestError,
        match="start identity changed",
    ):
        manifest.terminalize(
            ended_utc=(
                "2026-09-05T07:01:00Z"
            ),
            ended_monotonic_ns=s(60),
            active_duration_seconds=0,
            measurement_complete=False,
            safety_invariant_status="PASS",
            operational_classification=(
                "INITIAL_READINESS_TIMEOUT"
            ),
            orders=0,
            production_writes=0,
        )


def test_offline_validation_detects_artifact_tamper(
    tmp_path,
):
    manifest = new_manifest(
        tmp_path
    )

    artifact_root = (
        tmp_path
        / "artifacts"
    )

    artifact_root.mkdir()

    metrics = (
        artifact_root
        / "metrics.jsonl"
    )

    metrics.write_bytes(
        b"original\n"
    )

    manifest.terminalize(
        ended_utc=(
            "2026-09-05T08:01:00Z"
        ),
        ended_monotonic_ns=(
            s(3660)
        ),
        active_duration_seconds=3600,
        measurement_complete=True,
        safety_invariant_status="PASS",
        operational_classification=(
            "MEASUREMENT_COMPLETE"
        ),
        orders=0,
        production_writes=0,
        artifact_files=[
            (
                "runtime_metrics",
                metrics,
            )
        ],
        artifact_root=(
            artifact_root
        ),
    )

    metrics.write_bytes(
        b"tampered evidence\n"
    )

    with pytest.raises(
        SoakManifestError,
        match="size mismatch|SHA-256 mismatch",
    ):
        validate_soak_run_manifest(
            manifest.manifest_path,
            artifact_root=(
                artifact_root
            ),
            verify_artifacts=True,
        )


def test_safety_pass_cannot_hide_nonzero_orders(
    tmp_path,
):
    manifest = new_manifest(
        tmp_path
    )

    with pytest.raises(
        SoakManifestError,
        match="safety PASS",
    ):
        manifest.terminalize(
            ended_utc=(
                "2026-09-05T07:00:10Z"
            ),
            ended_monotonic_ns=s(10),
            active_duration_seconds=5,
            measurement_complete=False,
            safety_invariant_status="PASS",
            operational_classification=(
                "HARD_FAIL"
            ),
            orders=1,
            production_writes=0,
        )


def test_failed_attempt_can_truthfully_preserve_nonzero_order_count(
    tmp_path,
):
    manifest = new_manifest(
        tmp_path
    )

    final = (
        manifest.terminalize(
            ended_utc=(
                "2026-09-05T07:00:10Z"
            ),
            ended_monotonic_ns=s(10),
            active_duration_seconds=5,
            measurement_complete=False,
            safety_invariant_status="FAIL",
            operational_classification=(
                "HARD_FAIL"
            ),
            orders=1,
            production_writes=0,
        )
    )

    assert (
        final[
            "safety_invariant_status"
        ]
        == "FAIL"
    )

    assert (
        final[
            "orders"
        ]
        == 1
    )


def test_manifest_cannot_describe_its_own_sha256(
    tmp_path,
):
    manifest = new_manifest(
        tmp_path
    )

    with pytest.raises(
        SoakManifestError,
        match="self SHA-256",
    ):
        manifest.terminalize(
            ended_utc=(
                "2026-09-05T07:00:10Z"
            ),
            ended_monotonic_ns=s(10),
            active_duration_seconds=5,
            measurement_complete=False,
            safety_invariant_status="PASS",
            operational_classification=(
                "HARD_FAIL"
            ),
            orders=0,
            production_writes=0,
            artifact_files=[
                (
                    "manifest",
                    manifest.manifest_path,
                )
            ],
        )


def test_terminal_manifest_cannot_be_terminalized_twice(
    tmp_path,
):
    manifest = new_manifest(
        tmp_path
    )

    manifest.terminalize(
        ended_utc=(
            "2026-09-05T07:05:00Z"
        ),
        ended_monotonic_ns=s(300),
        active_duration_seconds=0,
        measurement_complete=False,
        safety_invariant_status="PASS",
        operational_classification=(
            "INITIAL_READINESS_TIMEOUT"
        ),
        orders=0,
        production_writes=0,
    )

    with pytest.raises(
        SoakManifestError,
        match="already terminal",
    ):
        manifest.terminalize(
            ended_utc=(
                "2026-09-05T07:06:00Z"
            ),
            ended_monotonic_ns=s(360),
            active_duration_seconds=0,
            measurement_complete=False,
            safety_invariant_status="PASS",
            operational_classification=(
                "INITIAL_READINESS_TIMEOUT"
            ),
            orders=0,
            production_writes=0,
        )
