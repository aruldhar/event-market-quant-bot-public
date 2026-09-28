"""Checkpoint 21N-Z-F B5-R5-B soak run-manifest lifecycle.

This module implements only the frozen B5-R5-B run-manifest contract.

It performs no:
- network access;
- credential loading;
- source startup;
- model or signal computation;
- settlement access;
- P&L computation;
- order placement;
- production writes.

Frozen safety boundary:

1. A RUNNING manifest must exist durably before any live source starts.
2. Start identity is immutable for the lifetime of the attempt.
3. Terminalization atomically updates lifecycle evidence only.
4. Execution mode is always "disabled".
5. Credential values are never accepted by this schema; optional credential
   presence evidence may contain booleans only.
6. Terminal artifact descriptors contain only role/path/size/SHA-256.
7. A manifest never includes its own SHA-256 descriptor.
8. Artifact size/hash verification is fail-closed.
"""
from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from uuid import UUID

from .kxbtcd_candidate_e_soak_archive import (
    SoakArchiveError,
    file_sha256,
    write_json_atomic,
)


SCHEMA_VERSION = (
    "candidate_e_b5_r5_b_soak_manifest.v1"
)

DESIGN_FINGERPRINT = (
    "715b55824746fe59467d7484599d1a928"
    "94e0810d5bc9be972d81577005c1ed6"
)

EXECUTION_MODE = "disabled"

SHAKEDOWN_ACTIVE_SECONDS = 3600
CANONICAL_SOAK_ACTIVE_SECONDS = 86400

ALLOWED_ACTIVE_DURATIONS = frozenset(
    {
        SHAKEDOWN_ACTIVE_SECONDS,
        CANONICAL_SOAK_ACTIVE_SECONDS,
    }
)

DEFAULT_MANIFEST_ROOT = Path(
    "data/runtime/"
    "kxbtcd_candidate_e_b5_r5_b/"
    "manifests"
)

_START_IDENTITY_FIELDS = (
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

_TERMINAL_SCALAR_FIELDS = (
    "ended_utc",
    "ended_monotonic_ns",
    "active_duration_seconds",
    "measurement_complete",
    "safety_invariant_status",
    "operational_classification",
    "orders",
    "production_writes",
)

_REQUIRED_ARTIFACT_DESCRIPTOR_FIELDS = frozenset(
    {
        "logical_role",
        "path",
        "size_bytes",
        "sha256",
    }
)

_TOKEN_RE = re.compile(
    r"^[A-Za-z0-9._:-]{1,160}$"
)

_GIT_HEAD_RE = re.compile(
    r"^[0-9a-f]{40}$"
)

_SHA256_RE = re.compile(
    r"^[0-9a-f]{64}$"
)

_DOCKER_DIGEST_RE = re.compile(
    r"^sha256:[0-9a-f]{64}$"
)


class SoakManifestError(RuntimeError):
    """Raised when the frozen soak manifest contract is violated."""


def _required_token(
    value: Any,
    name: str,
) -> str:
    if (
        not isinstance(value, str)
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise SoakManifestError(
            f"{name} must be a non-empty safe identifier token"
        )

    return value


def _required_text(
    value: Any,
    name: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\x00" in value
    ):
        raise SoakManifestError(
            f"{name} must be non-empty text"
        )

    return value


def _nonnegative_int(
    value: Any,
    name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise SoakManifestError(
            f"{name} must be a nonnegative integer"
        )

    return int(value)


def _nonnegative_seconds(
    value: Any,
    name: str,
) -> int | float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise SoakManifestError(
            f"{name} must be numeric"
        )

    numeric = float(value)

    if (
        not math.isfinite(numeric)
        or numeric < 0
    ):
        raise SoakManifestError(
            f"{name} must be finite and nonnegative"
        )

    if numeric.is_integer():
        return int(numeric)

    return numeric


def _utc_timestamp(
    value: Any,
    name: str,
) -> datetime:
    text = _required_text(
        value,
        name,
    )

    if not text.endswith("Z"):
        raise SoakManifestError(
            f"{name} must be an explicit UTC Z timestamp"
        )

    try:
        parsed = datetime.fromisoformat(
            text[:-1] + "+00:00"
        )
    except ValueError as exc:
        raise SoakManifestError(
            f"{name} is not a valid UTC timestamp"
        ) from exc

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or parsed.utcoffset().total_seconds() != 0
    ):
        raise SoakManifestError(
            f"{name} must be UTC"
        )

    return parsed


def _git_head(
    value: Any,
) -> str:
    if (
        not isinstance(value, str)
        or not _GIT_HEAD_RE.fullmatch(value)
    ):
        raise SoakManifestError(
            "git_head must be a lowercase 40-character Git commit SHA"
        )

    return value


def _docker_digest(
    value: Any,
) -> str:
    if (
        not isinstance(value, str)
        or not _DOCKER_DIGEST_RE.fullmatch(
            value
        )
    ):
        raise SoakManifestError(
            "docker_image_digest must be sha256:<64 lowercase hex>"
        )

    return value


def _host_boot_id(
    value: Any,
) -> str:
    text = _required_text(
        value,
        "host_boot_id",
    )

    try:
        parsed = UUID(
            text
        )
    except ValueError as exc:
        raise SoakManifestError(
            "host_boot_id must be a canonical UUID"
        ) from exc

    if text != str(parsed):
        raise SoakManifestError(
            "host_boot_id must be a canonical lowercase UUID"
        )

    return text


def _credential_presence(
    value: Mapping[str, Any] | None,
) -> dict[str, bool]:
    if value is None:
        return {}

    if not isinstance(
        value,
        Mapping,
    ):
        raise SoakManifestError(
            "credential_presence must be a mapping of booleans"
        )

    normalized: dict[str, bool] = {}

    for key, present in value.items():
        safe_key = _required_token(
            key,
            "credential_presence key",
        )

        if not isinstance(
            present,
            bool,
        ):
            raise SoakManifestError(
                "credential_presence values must be boolean only; "
                "credential values are prohibited"
            )

        normalized[
            safe_key
        ] = present

    return normalized


def _load_json_object(
    path: str | Path,
) -> dict[str, Any]:
    p = Path(
        path
    )

    try:
        value = json.loads(
            p.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise SoakManifestError(
            f"could not read soak manifest {p}: {exc}"
        ) from exc

    if not isinstance(
        value,
        dict,
    ):
        raise SoakManifestError(
            "soak manifest root must be a JSON object"
        )

    return value


def _start_identity_from_document(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    if document.get(
        "schema_version"
    ) != SCHEMA_VERSION:
        raise SoakManifestError(
            "soak manifest schema_version mismatch"
        )

    run_id = _required_token(
        document.get(
            "run_id"
        ),
        "run_id",
    )

    run_role = _required_token(
        document.get(
            "run_role"
        ),
        "run_role",
    )

    design_fingerprint = document.get(
        "design_fingerprint"
    )

    if (
        design_fingerprint
        != DESIGN_FINGERPRINT
    ):
        raise SoakManifestError(
            "design_fingerprint differs from the frozen B5-R5-B design"
        )

    git_head = _git_head(
        document.get(
            "git_head"
        )
    )

    docker_image_digest = (
        _docker_digest(
            document.get(
                "docker_image_digest"
            )
        )
    )

    host_boot_id = _host_boot_id(
        document.get(
            "host_boot_id"
        )
    )

    requested = _nonnegative_int(
        document.get(
            "requested_active_duration_seconds"
        ),
        "requested_active_duration_seconds",
    )

    if requested not in (
        ALLOWED_ACTIVE_DURATIONS
    ):
        raise SoakManifestError(
            "requested_active_duration_seconds must be "
            "3600 or 86400"
        )

    started_utc = _required_text(
        document.get(
            "started_utc"
        ),
        "started_utc",
    )

    _utc_timestamp(
        started_utc,
        "started_utc",
    )

    started_monotonic_ns = (
        _nonnegative_int(
            document.get(
                "started_monotonic_ns"
            ),
            "started_monotonic_ns",
        )
    )

    initial_free = (
        _nonnegative_int(
            document.get(
                "initial_filesystem_free_bytes"
            ),
            "initial_filesystem_free_bytes",
        )
    )

    execution_mode = document.get(
        "execution_mode"
    )

    if execution_mode != EXECUTION_MODE:
        raise SoakManifestError(
            "execution_mode must be exactly 'disabled'"
        )

    return {
        "run_id": run_id,
        "run_role": run_role,
        "design_fingerprint": (
            design_fingerprint
        ),
        "git_head": git_head,
        "docker_image_digest": (
            docker_image_digest
        ),
        "host_boot_id": host_boot_id,
        "requested_active_duration_seconds": (
            requested
        ),
        "started_utc": started_utc,
        "started_monotonic_ns": (
            started_monotonic_ns
        ),
        "initial_filesystem_free_bytes": (
            initial_free
        ),
        "execution_mode": (
            execution_mode
        ),
    }


def _validate_artifact_descriptors(
    value: Any,
) -> list[dict[str, Any]]:
    if not isinstance(
        value,
        list,
    ):
        raise SoakManifestError(
            "artifact_descriptors must be a list"
        )

    normalized: list[
        dict[str, Any]
    ] = []

    seen: set[
        tuple[str, str]
    ] = set()

    for index, item in enumerate(
        value
    ):
        if not isinstance(
            item,
            Mapping,
        ):
            raise SoakManifestError(
                f"artifact_descriptors[{index}] must be an object"
            )

        if set(
            item
        ) != set(
            _REQUIRED_ARTIFACT_DESCRIPTOR_FIELDS
        ):
            raise SoakManifestError(
                f"artifact_descriptors[{index}] must contain exactly "
                "logical_role, path, size_bytes, sha256"
            )

        logical_role = (
            _required_token(
                item.get(
                    "logical_role"
                ),
                (
                    f"artifact_descriptors[{index}]."
                    "logical_role"
                ),
            )
        )

        path = _required_text(
            item.get(
                "path"
            ),
            (
                f"artifact_descriptors[{index}]."
                "path"
            ),
        )

        size_bytes = (
            _nonnegative_int(
                item.get(
                    "size_bytes"
                ),
                (
                    f"artifact_descriptors[{index}]."
                    "size_bytes"
                ),
            )
        )

        digest = item.get(
            "sha256"
        )

        if (
            not isinstance(
                digest,
                str,
            )
            or not _SHA256_RE.fullmatch(
                digest
            )
        ):
            raise SoakManifestError(
                f"artifact_descriptors[{index}].sha256 "
                "must be 64 lowercase hexadecimal characters"
            )

        key = (
            logical_role,
            path,
        )

        if key in seen:
            raise SoakManifestError(
                "duplicate artifact descriptor"
            )

        seen.add(
            key
        )

        normalized.append(
            {
                "logical_role": (
                    logical_role
                ),
                "path": path,
                "size_bytes": (
                    size_bytes
                ),
                "sha256": digest,
            }
        )

    return normalized


def _validate_terminal_fields(
    document: Mapping[str, Any],
) -> None:
    ended_utc = _required_text(
        document.get(
            "ended_utc"
        ),
        "ended_utc",
    )

    start_dt = _utc_timestamp(
        document.get(
            "started_utc"
        ),
        "started_utc",
    )

    end_dt = _utc_timestamp(
        ended_utc,
        "ended_utc",
    )

    if end_dt < start_dt:
        raise SoakManifestError(
            "ended_utc cannot precede started_utc"
        )

    started_ns = _nonnegative_int(
        document.get(
            "started_monotonic_ns"
        ),
        "started_monotonic_ns",
    )

    ended_ns = _nonnegative_int(
        document.get(
            "ended_monotonic_ns"
        ),
        "ended_monotonic_ns",
    )

    if ended_ns < started_ns:
        raise SoakManifestError(
            "ended_monotonic_ns cannot precede started_monotonic_ns"
        )

    active_seconds = (
        _nonnegative_seconds(
            document.get(
                "active_duration_seconds"
            ),
            "active_duration_seconds",
        )
    )

    requested = _nonnegative_int(
        document.get(
            "requested_active_duration_seconds"
        ),
        "requested_active_duration_seconds",
    )

    elapsed_seconds = (
        ended_ns
        - started_ns
    ) / 1_000_000_000

    if (
        float(
            active_seconds
        )
        > elapsed_seconds
        + 1e-9
    ):
        raise SoakManifestError(
            "active_duration_seconds cannot exceed total monotonic run time"
        )

    if (
        float(
            active_seconds
        )
        > float(
            requested
        )
        + 1e-9
    ):
        raise SoakManifestError(
            "active_duration_seconds cannot exceed the requested duration"
        )

    measurement_complete = (
        document.get(
            "measurement_complete"
        )
    )

    if not isinstance(
        measurement_complete,
        bool,
    ):
        raise SoakManifestError(
            "measurement_complete must be boolean"
        )

    if (
        measurement_complete
        and not math.isclose(
            float(
                active_seconds
            ),
            float(
                requested
            ),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    ):
        raise SoakManifestError(
            "measurement_complete requires the exact requested active duration"
        )

    safety_status = document.get(
        "safety_invariant_status"
    )

    if safety_status not in {
        "PASS",
        "FAIL",
    }:
        raise SoakManifestError(
            "safety_invariant_status must be PASS or FAIL"
        )

    _required_token(
        document.get(
            "operational_classification"
        ),
        "operational_classification",
    )

    orders = _nonnegative_int(
        document.get(
            "orders"
        ),
        "orders",
    )

    production_writes = (
        _nonnegative_int(
            document.get(
                "production_writes"
            ),
            "production_writes",
        )
    )

    # A violated zero-order/write invariant may still be preserved truthfully
    # in a FAIL manifest. It may never be labeled a safety PASS.
    if (
        safety_status == "PASS"
        and (
            orders != 0
            or production_writes != 0
        )
    ):
        raise SoakManifestError(
            "safety PASS cannot contain nonzero orders or production writes"
        )

    _validate_artifact_descriptors(
        document.get(
            "artifact_descriptors"
        )
    )


def _validate_document(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    identity = (
        _start_identity_from_document(
            document
        )
    )

    _credential_presence(
        document.get(
            "credential_presence"
        )
    )

    lifecycle = document.get(
        "lifecycle_state"
    )

    if lifecycle not in {
        "RUNNING",
        "TERMINAL",
    }:
        raise SoakManifestError(
            "lifecycle_state must be RUNNING or TERMINAL"
        )

    if lifecycle == "RUNNING":
        for field in (
            _TERMINAL_SCALAR_FIELDS
        ):
            if document.get(
                field
            ) is not None:
                raise SoakManifestError(
                    f"RUNNING manifest terminal field {field} must be null"
                )

        if document.get(
            "artifact_descriptors"
        ) != []:
            raise SoakManifestError(
                "RUNNING manifest artifact_descriptors must be empty"
            )

    else:
        _validate_terminal_fields(
            document
        )

    return identity


def _resolve_artifact_path(
    stored_path: str,
    *,
    artifact_root: str | Path | None,
) -> Path:
    candidate = Path(
        stored_path
    )

    if candidate.is_absolute():
        return candidate.resolve()

    if artifact_root is None:
        raise SoakManifestError(
            "relative artifact path requires artifact_root for verification"
        )

    root = Path(
        artifact_root
    ).resolve()

    resolved = (
        root
        / candidate
    ).resolve()

    try:
        resolved.relative_to(
            root
        )
    except ValueError as exc:
        raise SoakManifestError(
            f"artifact path escapes artifact_root: {stored_path!r}"
        ) from exc

    return resolved


def _verify_terminal_artifacts(
    document: Mapping[str, Any],
    *,
    artifact_root: str | Path | None,
) -> None:
    descriptors = (
        _validate_artifact_descriptors(
            document.get(
                "artifact_descriptors"
            )
        )
    )

    for descriptor in descriptors:
        path = _resolve_artifact_path(
            descriptor[
                "path"
            ],
            artifact_root=(
                artifact_root
            ),
        )

        if (
            not path.exists()
            or not path.is_file()
        ):
            raise SoakManifestError(
                f"manifest artifact is missing: {path}"
            )

        actual_size = (
            path.stat().st_size
        )

        if (
            actual_size
            != descriptor[
                "size_bytes"
            ]
        ):
            raise SoakManifestError(
                f"artifact size mismatch: {path}"
            )

        actual_sha = (
            file_sha256(
                path
            )
        )

        if (
            actual_sha
            != descriptor[
                "sha256"
            ]
        ):
            raise SoakManifestError(
                f"artifact SHA-256 mismatch: {path}"
            )


def build_artifact_descriptor(
    *,
    logical_role: str,
    path: str | Path,
    artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    role = _required_token(
        logical_role,
        "logical_role",
    )

    artifact = Path(
        path
    ).resolve()

    if (
        not artifact.exists()
        or not artifact.is_file()
    ):
        raise SoakManifestError(
            f"artifact does not exist: {artifact}"
        )

    if artifact_root is None:
        stored_path = str(
            artifact
        )
    else:
        root = Path(
            artifact_root
        ).resolve()

        try:
            relative = (
                artifact.relative_to(
                    root
                )
            )
        except ValueError as exc:
            raise SoakManifestError(
                f"artifact is outside artifact_root: {artifact}"
            ) from exc

        stored_path = (
            relative.as_posix()
        )

    return {
        "logical_role": role,
        "path": stored_path,
        "size_bytes": (
            artifact.stat().st_size
        ),
        "sha256": (
            file_sha256(
                artifact
            )
        ),
    }


def validate_soak_run_manifest(
    path: str | Path,
    *,
    artifact_root: str | Path | None = None,
    verify_artifacts: bool = False,
) -> dict[str, Any]:
    document = (
        _load_json_object(
            path
        )
    )

    _validate_document(
        document
    )

    if (
        verify_artifacts
        and document.get(
            "lifecycle_state"
        )
        == "TERMINAL"
    ):
        _verify_terminal_artifacts(
            document,
            artifact_root=(
                artifact_root
            ),
        )

    return document


class SoakRunManifest:
    """One B5-R5-B lifecycle manifest with immutable start identity."""

    def __init__(
        self,
        *,
        manifest_path: str | Path,
        run_id: str,
        run_role: str,
        design_fingerprint: str,
        git_head: str,
        docker_image_digest: str,
        host_boot_id: str,
        requested_active_duration_seconds: int,
        started_utc: str,
        started_monotonic_ns: int,
        initial_filesystem_free_bytes: int,
        execution_mode: str,
        credential_presence: (
            Mapping[str, Any]
            | None
        ) = None,
    ) -> None:
        self.manifest_path = Path(
            manifest_path
        )

        if self.manifest_path.exists():
            raise SoakManifestError(
                f"refusing to replace existing soak manifest: "
                f"{self.manifest_path}"
            )

        start_state: dict[
            str,
            Any,
        ] = {
            "schema_version": (
                SCHEMA_VERSION
            ),
            "lifecycle_state": (
                "RUNNING"
            ),
            "run_id": run_id,
            "run_role": run_role,
            "design_fingerprint": (
                design_fingerprint
            ),
            "git_head": git_head,
            "docker_image_digest": (
                docker_image_digest
            ),
            "host_boot_id": (
                host_boot_id
            ),
            "requested_active_duration_seconds": (
                requested_active_duration_seconds
            ),
            "started_utc": (
                started_utc
            ),
            "started_monotonic_ns": (
                started_monotonic_ns
            ),
            "initial_filesystem_free_bytes": (
                initial_filesystem_free_bytes
            ),
            "execution_mode": (
                execution_mode
            ),
            "credential_presence": (
                _credential_presence(
                    credential_presence
                )
            ),
            "ended_utc": None,
            "ended_monotonic_ns": None,
            "active_duration_seconds": None,
            "measurement_complete": None,
            "safety_invariant_status": None,
            "operational_classification": None,
            "orders": None,
            "production_writes": None,
            "artifact_descriptors": [],
        }

        self._start_identity = (
            _validate_document(
                start_state
            )
        )

        self._write(
            start_state
        )

        persisted = (
            validate_soak_run_manifest(
                self.manifest_path
            )
        )

        persisted_identity = (
            _start_identity_from_document(
                persisted
            )
        )

        if (
            persisted_identity
            != self._start_identity
        ):
            raise SoakManifestError(
                "persisted start identity differs from requested identity"
            )

    def _write(
        self,
        document: dict[str, Any],
    ) -> None:
        try:
            write_json_atomic(
                self.manifest_path,
                document,
            )
        except (
            SoakArchiveError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            raise SoakManifestError(
                f"could not persist soak manifest "
                f"{self.manifest_path}: {exc}"
            ) from exc

    def _load_current(
        self,
    ) -> dict[str, Any]:
        document = (
            validate_soak_run_manifest(
                self.manifest_path
            )
        )

        identity = (
            _start_identity_from_document(
                document
            )
        )

        if (
            identity
            != self._start_identity
        ):
            raise SoakManifestError(
                "persisted start identity changed after manifest creation"
            )

        return document

    def terminalize(
        self,
        *,
        ended_utc: str,
        ended_monotonic_ns: int,
        active_duration_seconds: int | float,
        measurement_complete: bool,
        safety_invariant_status: str,
        operational_classification: str,
        orders: int,
        production_writes: int,
        artifact_files: Iterable[
            tuple[
                str,
                str | Path,
            ]
        ] = (),
        artifact_root: str | Path | None = None,
    ) -> dict[str, Any]:
        current = (
            self._load_current()
        )

        if current.get(
            "lifecycle_state"
        ) != "RUNNING":
            raise SoakManifestError(
                "soak manifest is already terminal"
            )

        descriptors: list[
            dict[str, Any]
        ] = []

        manifest_resolved = (
            self.manifest_path.resolve()
        )

        for (
            logical_role,
            artifact_path,
        ) in artifact_files:
            candidate = Path(
                artifact_path
            ).resolve()

            if (
                candidate
                == manifest_resolved
            ):
                raise SoakManifestError(
                    "manifest self SHA-256 descriptor is prohibited"
                )

            descriptors.append(
                build_artifact_descriptor(
                    logical_role=(
                        logical_role
                    ),
                    path=candidate,
                    artifact_root=(
                        artifact_root
                    ),
                )
            )

        # Validate duplicates and exact descriptor shape before writing.
        descriptors = (
            _validate_artifact_descriptors(
                descriptors
            )
        )

        final_state = {
            **current,
            "lifecycle_state": (
                "TERMINAL"
            ),
            "ended_utc": (
                ended_utc
            ),
            "ended_monotonic_ns": (
                ended_monotonic_ns
            ),
            "active_duration_seconds": (
                _nonnegative_seconds(
                    active_duration_seconds,
                    "active_duration_seconds",
                )
            ),
            "measurement_complete": (
                measurement_complete
            ),
            "safety_invariant_status": (
                safety_invariant_status
            ),
            "operational_classification": (
                operational_classification
            ),
            "orders": orders,
            "production_writes": (
                production_writes
            ),
            "artifact_descriptors": (
                descriptors
            ),
        }

        final_identity = (
            _validate_document(
                final_state
            )
        )

        if (
            final_identity
            != self._start_identity
        ):
            raise SoakManifestError(
                "terminalization attempted to alter immutable start identity"
            )

        _verify_terminal_artifacts(
            final_state,
            artifact_root=(
                artifact_root
            ),
        )

        self._write(
            final_state
        )

        persisted = (
            validate_soak_run_manifest(
                self.manifest_path,
                artifact_root=(
                    artifact_root
                ),
                verify_artifacts=True,
            )
        )

        persisted_identity = (
            _start_identity_from_document(
                persisted
            )
        )

        if (
            persisted_identity
            != self._start_identity
        ):
            raise SoakManifestError(
                "terminal persisted start identity mismatch"
            )

        return persisted
