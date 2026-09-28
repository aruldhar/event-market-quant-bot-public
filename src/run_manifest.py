"""Per-run collection manifests with atomic lifecycle updates."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

from .data_integrity import (
    DataIntegrityError,
    inspect_csv,
    inspect_raw_jsonl,
    inspect_runtime_event_jsonl,
)


_SENSITIVE_NAME_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "secret",
    "signature",
    "token",
)


class RunManifestError(RuntimeError):
    """Raised when a required collection manifest cannot be created or finalized."""


class CollectionRunManifest:
    """Write a durable receipt for one command-line collection run.

    A manifest begins in ``running`` state. Successful finalization atomically
    replaces it with ``completed``; exception handling may replace it with
    ``failed``. If the process crashes, the last durable state remains
    ``running``, which is intentionally treated as an incomplete run.
    """

    LEGACY_SCHEMA_VERSION = "collection_run_manifest.v1"
    SCHEMA_VERSION = "collection_run_manifest.v2"

    def __init__(
        self,
        *,
        collector_name: str,
        arguments: Mapping[str, Any],
        manifest_root: str | Path,
        repository_root: str | Path = ".",
        source_sessions: Iterable[Mapping[str, Any]] = (),
        utc_now: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
        git_info_provider: Callable[[Path], dict[str, Any]] | None = None,
        runtime_observability: bool = False,
    ) -> None:
        self.collector_name = collector_name
        self.arguments = _sanitize_mapping(arguments)
        self.manifest_root = Path(manifest_root)
        self.repository_root = Path(repository_root).resolve()
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._git_info_provider = git_info_provider or capture_git_info
        self.runtime_observability = runtime_observability
        self.schema_version = (
            self.SCHEMA_VERSION
            if runtime_observability
            else self.LEGACY_SCHEMA_VERSION
        )

        started_at = _ensure_utc(self._utc_now())
        compact_time = started_at.strftime("%Y%m%dT%H%M%S%fZ")
        self.run_id = f"{collector_name}_{compact_time}_{self._id_factory()[:8]}"
        self.started_at_utc = _format_utc(started_at)
        self.manifest_path = (
            self.manifest_root
            / f"{started_at.year:04d}"
            / f"{started_at.month:02d}"
            / f"{started_at.day:02d}"
            / f"{self.run_id}.json"
        )
        self._source_sessions = [_json_safe(dict(item)) for item in source_sessions]
        self._state = self._base_state()
        try:
            self._write_state(self._state)
        except (OSError, TypeError, ValueError) as exc:
            raise RunManifestError(
                f"Could not create running manifest {self.manifest_path}: {exc}"
            ) from exc

    @property
    def status(self) -> str:
        return str(self._state["status"])

    def complete(
        self,
        *,
        raw_files: Iterable[str | Path],
        derived_csv_files: Iterable[str | Path] = (),
        runtime_event_files: Iterable[str | Path] = (),
        result: Mapping[str, Any] | None = None,
    ) -> Path:
        """Inspect artifacts and atomically finalize the manifest as completed."""

        if self.status != "running":
            raise RunManifestError(
                f"Run {self.run_id} cannot complete from status {self.status!r}"
            )
        try:
            runtime_paths = tuple(runtime_event_files)
            if self.runtime_observability and not runtime_paths:
                raise DataIntegrityError(
                    "Runtime-observable runs require a runtime event artifact"
                )
            files = self._inspect_files(
                raw_files,
                derived_csv_files,
                runtime_paths,
            )
            if self.runtime_observability:
                self._validate_completed_runtime_relationship(files)
            completed_at = _format_utc(_ensure_utc(self._utc_now()))
            final_state = {
                **self._state,
                "status": "completed",
                "completed_at_utc": completed_at,
                "files": files,
                "summary": _summarize_files(
                    files,
                    include_runtime=self.runtime_observability,
                ),
                "result": _json_safe(result or {}),
                "failure": None,
            }
            self._write_state(final_state)
            self._state = final_state
            return self.manifest_path
        except (DataIntegrityError, OSError, TypeError, ValueError) as exc:
            raise RunManifestError(
                f"Could not finalize completed manifest {self.manifest_path}: {exc}"
            ) from exc

    def fail(
        self,
        exc: BaseException,
        *,
        raw_files: Iterable[str | Path] = (),
        derived_csv_files: Iterable[str | Path] = (),
        runtime_event_files: Iterable[str | Path] = (),
        result: Mapping[str, Any] | None = None,
    ) -> Path:
        """Atomically finalize the manifest as failed while preserving artifacts."""

        if self.status != "running":
            return self.manifest_path

        files: list[dict[str, Any]] = []
        inspection_errors: list[str] = []
        try:
            files = self._inspect_files(
                [path for path in raw_files if Path(path).exists()],
                [path for path in derived_csv_files if Path(path).exists()],
                [path for path in runtime_event_files if Path(path).exists()],
            )
        except (DataIntegrityError, OSError, TypeError, ValueError) as inspect_exc:
            inspection_errors.append(str(inspect_exc))

        final_state = {
            **self._state,
            "status": "failed",
            "completed_at_utc": _format_utc(_ensure_utc(self._utc_now())),
            "files": files,
            "summary": _summarize_files(
                files,
                include_runtime=self.runtime_observability,
            ),
            "result": _json_safe(result or {}),
            "failure": {
                "type": type(exc).__name__,
                "message": str(exc),
                "artifact_inspection_errors": inspection_errors,
            },
        }
        try:
            self._write_state(final_state)
        except (OSError, TypeError, ValueError) as write_exc:
            raise RunManifestError(
                f"Run failed with {type(exc).__name__}, and the failed manifest "
                f"could not be saved: {write_exc}"
            ) from write_exc
        self._state = final_state
        return self.manifest_path

    def _base_state(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "collector": {"name": self.collector_name},
            "status": "running",
            "started_at_utc": self.started_at_utc,
            "completed_at_utc": None,
            "arguments": self.arguments,
            "code": self._git_info_provider(self.repository_root),
            "environment": {
                "python_version": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "platform": platform.platform(),
            },
            "source_sessions": self._source_sessions,
            "files": [],
            "summary": _summarize_files(
                [],
                include_runtime=self.runtime_observability,
            ),
            "result": {},
            "failure": None,
        }

    def _inspect_files(
        self,
        raw_files: Iterable[str | Path],
        derived_csv_files: Iterable[str | Path],
        runtime_event_files: Iterable[str | Path],
    ) -> list[dict[str, Any]]:
        descriptors: list[dict[str, Any]] = []
        for path in sorted({Path(item).resolve() for item in raw_files}):
            descriptor = inspect_raw_jsonl(path)
            descriptor["path"] = _stored_path(path, self.repository_root)
            descriptors.append(descriptor)
        for path in sorted({Path(item).resolve() for item in derived_csv_files}):
            descriptor = inspect_csv(path)
            descriptor["path"] = _stored_path(path, self.repository_root)
            descriptors.append(descriptor)
        for path in sorted({Path(item).resolve() for item in runtime_event_files}):
            descriptor = inspect_runtime_event_jsonl(path)
            descriptor["path"] = _stored_path(path, self.repository_root)
            descriptors.append(descriptor)
        return descriptors

    def _validate_completed_runtime_relationship(
        self,
        files: Iterable[Mapping[str, Any]],
    ) -> None:
        runtime_files = [
            item for item in files if item.get("role") == "runtime_event_log"
        ]
        if len(runtime_files) != 1:
            raise DataIntegrityError(
                "A completed manifest v2 requires exactly one runtime event log"
            )

        descriptor = runtime_files[0]
        if descriptor.get("run_ids") != [self.run_id]:
            raise DataIntegrityError(
                "Runtime event log run_id does not match the manifest run_id"
            )
        if descriptor.get("collectors") != [self.collector_name]:
            raise DataIntegrityError(
                "Runtime event log collector does not match the manifest collector"
            )

        event_names = set(descriptor.get("event_names", []))
        required_events = {"collector.started", "collector.completed"}
        missing_events = sorted(required_events.difference(event_names))
        if missing_events:
            raise DataIntegrityError(
                "Completed manifest runtime event log is missing lifecycle "
                f"events: {missing_events}"
            )
        if "collector.failed" in event_names:
            raise DataIntegrityError(
                "Completed manifest runtime event log contains collector.failed"
            )
        severity_counts = descriptor.get("severity_counts", {})
        if severity_counts.get("critical") != 0:
            raise DataIntegrityError(
                "Completed manifest runtime event log contains a critical event"
            )

    def _write_state(self, state: Mapping[str, Any]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.manifest_path.with_name(
            f".{self.manifest_path.name}.{self._id_factory()[:8]}.tmp"
        )
        serialized = json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        try:
            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.manifest_path)
        except OSError:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise


def capture_git_info(repository_root: Path) -> dict[str, Any]:
    """Capture the exact Git commit and whether tracked files are modified."""

    try:
        commit = _run_git(repository_root, "rev-parse", "HEAD")
        status = _run_git(
            repository_root,
            "status",
            "--porcelain",
            "--untracked-files=no",
        )
        return {
            "git_commit": commit,
            "git_worktree_dirty": bool(status),
            "git_error": None,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "git_commit": None,
            "git_worktree_dirty": None,
            "git_error": str(exc),
        }


def _run_git(repository_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return completed.stdout.strip()


def _summarize_files(
    files: Iterable[Mapping[str, Any]],
    *,
    include_runtime: bool,
) -> dict[str, int]:
    files_list = list(files)
    raw = [item for item in files_list if item.get("role") == "raw_api_archive"]
    derived = [item for item in files_list if item.get("role") == "derived_csv"]
    runtime = [item for item in files_list if item.get("role") == "runtime_event_log"]
    summary = {
        "raw_file_count": len(raw),
        "raw_record_count": sum(int(item["record_count"]) for item in raw),
        "raw_error_record_count": sum(
            int(item["error_record_count"]) for item in raw
        ),
        "derived_csv_count": len(derived),
        "derived_row_count": sum(int(item["data_row_count"]) for item in derived),
    }
    if include_runtime:
        summary.update(
            {
                "runtime_event_file_count": len(runtime),
                "runtime_event_count": sum(
                    int(item["event_count"]) for item in runtime
                ),
                "runtime_error_event_count": sum(
                    int(item["error_event_count"]) for item in runtime
                ),
            }
        )
    return summary


def _stored_path(path: Path, repository_root: Path) -> dict[str, str]:
    try:
        relative = path.relative_to(repository_root)
    except ValueError:
        return {"kind": "absolute", "value": str(path)}
    return {"kind": "repository_relative", "value": relative.as_posix()}


def resolve_stored_path(path_spec: Mapping[str, Any], repository_root: Path) -> Path:
    """Resolve a manifest path descriptor without guessing its base directory."""

    kind = path_spec.get("kind")
    value = path_spec.get("value")
    if not isinstance(value, str) or not value:
        raise RunManifestError("Manifest file path value must be non-empty text")
    if kind == "repository_relative":
        candidate = (repository_root / Path(value)).resolve()
        try:
            candidate.relative_to(repository_root.resolve())
        except ValueError as exc:
            raise RunManifestError(
                f"Repository-relative manifest path escapes the repository: {value!r}"
            ) from exc
        return candidate
    if kind == "absolute":
        return Path(value)
    raise RunManifestError(f"Unsupported manifest path kind: {kind!r}")


def _sanitize_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in values.items():
        string_key = str(key)
        normalized = string_key.lower().replace("-", "_")
        if any(fragment in normalized for fragment in _SENSITIVE_NAME_FRAGMENTS):
            safe[string_key] = "[REDACTED]"
        elif isinstance(value, Mapping):
            safe[string_key] = _sanitize_mapping(value)
        else:
            safe[string_key] = _json_safe(value)
    return safe


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("UTC clock function returned a naive datetime")
    return value.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
