"""Validation of completed collection-run manifests and referenced artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from .data_integrity import (
    DataIntegrityError,
    inspect_csv,
    inspect_raw_jsonl,
    inspect_runtime_event_jsonl,
)
from .run_manifest import CollectionRunManifest, RunManifestError, resolve_stored_path


class RunValidationError(RuntimeError):
    """Raised when a manifest or any referenced artifact fails validation."""


_RAW_REQUEST_EVENT_NAMES = {
    "api.request.succeeded",
    "api.request.failed",
}

_REQUIRED_ORDERBOOK_LINEAGE_COLUMNS = (
    "run_id",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "ticker",
)


def validate_run_manifest(
    manifest_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    """Recompute and compare every recorded artifact integrity field."""

    path = Path(manifest_path)
    repo_root = Path(repository_root).resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunValidationError(f"Could not read manifest {path}: {exc}") from exc

    _validate_manifest_envelope(manifest)
    if manifest["status"] != "completed":
        raise RunValidationError(
            f"Run status is {manifest['status']!r}; only completed runs pass validation"
        )

    observed_files: list[dict[str, Any]] = []
    try:
        for expected in manifest["files"]:
            artifact_path = resolve_stored_path(expected["path"], repo_root)
            if not artifact_path.is_file():
                raise RunValidationError(f"Referenced artifact is missing: {artifact_path}")

            role = expected["role"]
            if role == "raw_api_archive":
                observed = inspect_raw_jsonl(artifact_path)
            elif role == "derived_csv":
                observed = inspect_csv(artifact_path)
            elif role == "runtime_event_log":
                observed = inspect_runtime_event_jsonl(artifact_path)
            else:
                raise RunValidationError(f"Unsupported artifact role: {role!r}")

            _compare_descriptor(expected, observed, artifact_path)
            observed_with_path = {**observed, "path": expected["path"]}
            observed_files.append(observed_with_path)
    except (DataIntegrityError, RunManifestError) as exc:
        raise RunValidationError(str(exc)) from exc

    observed_summary = _summary(
        observed_files,
        schema_version=manifest["schema_version"],
    )
    if manifest["summary"] != observed_summary:
        raise RunValidationError(
            "Manifest summary does not match recomputed artifact totals: "
            f"expected {manifest['summary']!r}, observed {observed_summary!r}"
        )

    if manifest["schema_version"] == CollectionRunManifest.SCHEMA_VERSION:
        _validate_runtime_event_relationship(manifest)
        _validate_runtime_to_raw_correlation(manifest, repo_root)

    if manifest["collector"]["name"] == "record_orderbook":
        _validate_record_orderbook_lineage(manifest, repo_root)

    return {
        "manifest_path": str(path),
        "run_id": manifest["run_id"],
        "collector": manifest["collector"]["name"],
        "status": manifest["status"],
        "git_commit": manifest["code"].get("git_commit"),
        "git_worktree_dirty": manifest["code"].get("git_worktree_dirty"),
        "summary": observed_summary,
    }


def find_latest_manifest(manifest_root: str | Path) -> Path:
    """Return the most recently modified manifest under a root directory."""

    root = Path(manifest_root)
    candidates = [path for path in root.rglob("*.json") if path.is_file()]
    if not candidates:
        raise RunValidationError(f"No manifest files found under {root}")
    return max(candidates, key=lambda item: item.stat().st_mtime_ns)


def _validate_record_orderbook_lineage(
    manifest: Mapping[str, Any],
    repository_root: Path,
) -> None:
    """Reconcile each derived order-book row to one exact raw API record."""

    declared_sessions = {
        (session["source"], session["session_id"])
        for session in manifest["source_sessions"]
    }

    raw_descriptors = [
        item
        for item in manifest["files"]
        if item.get("role") == "raw_api_archive"
    ]
    derived_descriptors = [
        item
        for item in manifest["files"]
        if item.get("role") == "derived_csv"
    ]

    if not raw_descriptors:
        raise RunValidationError(
            "record_orderbook manifest references no raw API archive"
        )
    if not derived_descriptors:
        raise RunValidationError(
            "record_orderbook manifest references no derived CSV"
        )

    raw_index: dict[tuple[str, str, str], dict[str, Any]] = {}
    derivable_raw_keys: set[tuple[str, str, str]] = set()

    for descriptor in raw_descriptors:
        raw_path = resolve_stored_path(
            descriptor["path"],
            repository_root,
        )

        try:
            with raw_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise RunValidationError(
                            f"{raw_path}:{line_number}: invalid JSON during "
                            f"lineage validation: {exc}"
                        ) from exc

                    source = record["source"]
                    session_id = record["session_id"]
                    request_id = record["request"]["request_id"]
                    session_key = (source, session_id)
                    raw_key = (source, session_id, request_id)

                    if session_key not in declared_sessions:
                        raise RunValidationError(
                            f"{raw_path}:{line_number}: raw record belongs to "
                            f"undeclared source session {session_key!r}"
                        )

                    if raw_key in raw_index:
                        raise RunValidationError(
                            "Duplicate raw lineage key across run artifacts: "
                            f"{raw_key!r}"
                        )

                    raw_index[raw_key] = record

                    if _derivable_orderbook_ticker(record) is not None:
                        derivable_raw_keys.add(raw_key)
        except OSError as exc:
            raise RunValidationError(
                f"Could not read raw artifact for lineage validation "
                f"{raw_path}: {exc}"
            ) from exc

    derived_raw_keys: set[tuple[str, str, str]] = set()

    for descriptor in derived_descriptors:
        csv_path = resolve_stored_path(
            descriptor["path"],
            repository_root,
        )

        try:
            with csv_path.open("r", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)

                if reader.fieldnames is None:
                    raise RunValidationError(
                        f"Derived CSV has no header row: {csv_path}"
                    )

                missing_columns = sorted(
                    set(_REQUIRED_ORDERBOOK_LINEAGE_COLUMNS).difference(
                        reader.fieldnames
                    )
                )
                if missing_columns:
                    raise RunValidationError(
                        f"Derived CSV {csv_path} is missing lineage columns: "
                        f"{missing_columns}"
                    )

                for row_number, row in enumerate(reader, start=2):
                    for column in _REQUIRED_ORDERBOOK_LINEAGE_COLUMNS:
                        value = row.get(column)
                        if not isinstance(value, str) or not value:
                            raise RunValidationError(
                                f"{csv_path}:{row_number}: {column} must be "
                                "non-empty text"
                            )

                    if row["run_id"] != manifest["run_id"]:
                        raise RunValidationError(
                            f"{csv_path}:{row_number}: row run_id "
                            f"{row['run_id']!r} does not match manifest run_id "
                            f"{manifest['run_id']!r}"
                        )

                    session_key = (
                        row["raw_source"],
                        row["raw_session_id"],
                    )
                    if session_key not in declared_sessions:
                        raise RunValidationError(
                            f"{csv_path}:{row_number}: row references undeclared "
                            f"source session {session_key!r}"
                        )

                    raw_key = (
                        row["raw_source"],
                        row["raw_session_id"],
                        row["raw_request_id"],
                    )

                    if raw_key in derived_raw_keys:
                        raise RunValidationError(
                            f"{csv_path}:{row_number}: duplicate derived "
                            f"reference to raw record {raw_key!r}"
                        )

                    raw_record = raw_index.get(raw_key)
                    if raw_record is None:
                        raise RunValidationError(
                            f"{csv_path}:{row_number}: lineage reference "
                            f"{raw_key!r} does not match any raw record"
                        )

                    raw_ticker = _derivable_orderbook_ticker(raw_record)
                    if raw_ticker is None:
                        raise RunValidationError(
                            f"{csv_path}:{row_number}: referenced raw record "
                            "is not a successful derivable order-book response"
                        )

                    if row["ticker"] != raw_ticker:
                        raise RunValidationError(
                            f"{csv_path}:{row_number}: CSV ticker "
                            f"{row['ticker']!r} does not match raw request "
                            f"ticker {raw_ticker!r}"
                        )

                    derived_raw_keys.add(raw_key)
        except (OSError, csv.Error) as exc:
            raise RunValidationError(
                f"Could not read derived CSV for lineage validation "
                f"{csv_path}: {exc}"
            ) from exc

    missing_derived_rows = derivable_raw_keys.difference(derived_raw_keys)
    if missing_derived_rows:
        examples = sorted(missing_derived_rows)[:3]
        raise RunValidationError(
            "Successful derivable raw order-book records are missing derived "
            f"CSV rows; examples: {examples!r}"
        )


def _derivable_orderbook_ticker(
    record: Mapping[str, Any],
) -> str | None:
    """Return the raw request ticker when the response can produce a CSV row."""

    if record.get("error") is not None:
        return None

    request = record.get("request")
    response = record.get("response")
    if not isinstance(request, Mapping) or not isinstance(response, Mapping):
        return None

    if request.get("method") != "GET":
        return None

    ticker = _ticker_from_orderbook_path(request.get("path"))
    if ticker is None:
        return None

    status_code = response.get("status_code")
    if (
        not isinstance(status_code, int)
        or isinstance(status_code, bool)
        or not 200 <= status_code < 300
    ):
        return None

    if response.get("json_parse_error") is not None:
        return None

    body_text = response.get("body_text")
    if not isinstance(body_text, str):
        return None

    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    if not isinstance(payload.get("orderbook_fp"), dict):
        return None

    return ticker


def _ticker_from_orderbook_path(value: Any) -> str | None:
    """Extract a ticker from the exact public order-book endpoint path."""

    if not isinstance(value, str):
        return None

    prefix = "/markets/"
    suffix = "/orderbook"

    if not value.startswith(prefix) or not value.endswith(suffix):
        return None

    ticker = value[len(prefix) : -len(suffix)]
    if not ticker or "/" in ticker:
        return None

    return ticker


def _validate_manifest_envelope(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        raise RunValidationError("Manifest must be a JSON object")
    required = {
        "schema_version",
        "run_id",
        "collector",
        "status",
        "started_at_utc",
        "completed_at_utc",
        "arguments",
        "code",
        "environment",
        "source_sessions",
        "files",
        "summary",
        "result",
        "failure",
    }
    missing = sorted(required.difference(manifest))
    if missing:
        raise RunValidationError(f"Manifest missing fields: {missing}")
    supported_versions = {
        CollectionRunManifest.LEGACY_SCHEMA_VERSION,
        CollectionRunManifest.SCHEMA_VERSION,
    }
    if manifest["schema_version"] not in supported_versions:
        raise RunValidationError(
            f"Unsupported manifest schema_version: {manifest['schema_version']!r}"
        )
    if not isinstance(manifest["run_id"], str) or not manifest["run_id"]:
        raise RunValidationError("Manifest run_id must be non-empty text")
    if not isinstance(manifest["collector"], dict) or not isinstance(
        manifest["collector"].get("name"), str
    ):
        raise RunValidationError("Manifest collector.name must be text")
    if manifest["status"] not in {"running", "completed", "failed"}:
        raise RunValidationError(f"Unsupported manifest status: {manifest['status']!r}")
    if not isinstance(manifest["source_sessions"], list):
        raise RunValidationError("Manifest source_sessions must be a list")
    for index, session in enumerate(manifest["source_sessions"]):
        if not isinstance(session, dict):
            raise RunValidationError(
                f"Manifest source_sessions[{index}] must be an object"
            )
        for field in ("source", "session_id"):
            if not isinstance(session.get(field), str) or not session[field]:
                raise RunValidationError(
                    f"Manifest source_sessions[{index}].{field} must be non-empty text"
                )
    if not isinstance(manifest["files"], list):
        raise RunValidationError("Manifest files must be a list")
    if not isinstance(manifest["summary"], dict):
        raise RunValidationError("Manifest summary must be an object")


def _compare_descriptor(
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
    path: Path,
) -> None:
    for field, observed_value in observed.items():
        if expected.get(field) != observed_value:
            raise RunValidationError(
                f"Artifact mismatch for {path}: field {field!r} expected "
                f"{expected.get(field)!r}, observed {observed_value!r}"
            )


def _validate_runtime_to_raw_correlation(
    manifest: Mapping[str, Any],
    repository_root: Path,
) -> None:
    """Reconcile persisted request events to the exact raw exchange records."""

    declared_sessions = {
        (session["source"], session["session_id"])
        for session in manifest["source_sessions"]
    }
    raw_records: dict[tuple[str, str, str], Mapping[str, Any]] = {}

    for descriptor in manifest["files"]:
        if descriptor.get("role") != "raw_api_archive":
            continue
        raw_path = resolve_stored_path(descriptor["path"], repository_root)
        try:
            with raw_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    record = json.loads(line)
                    key = (
                        record["source"],
                        record["session_id"],
                        record["request"]["request_id"],
                    )
                    if key[:2] not in declared_sessions:
                        raise RunValidationError(
                            f"{raw_path}:{line_number}: runtime-observable raw "
                            f"record belongs to undeclared source session {key[:2]!r}"
                        )
                    if key in raw_records:
                        raise RunValidationError(
                            "Duplicate raw request key across v2 run artifacts: "
                            f"{key!r}"
                        )
                    raw_records[key] = record
        except (OSError, json.JSONDecodeError) as exc:
            raise RunValidationError(
                f"Could not read raw artifact for runtime correlation "
                f"{raw_path}: {exc}"
            ) from exc

    runtime_descriptor = next(
        item
        for item in manifest["files"]
        if item.get("role") == "runtime_event_log"
    )
    runtime_path = resolve_stored_path(
        runtime_descriptor["path"],
        repository_root,
    )
    request_events: dict[tuple[str, str, str], str] = {}

    try:
        with runtime_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                event = json.loads(line)
                event_name = event["event_name"]
                correlation = event["correlation"]

                if event_name in _RAW_REQUEST_EVENT_NAMES and correlation is None:
                    raise RunValidationError(
                        f"{runtime_path}:{line_number}: {event_name} requires "
                        "raw-record correlation"
                    )
                if event_name == "api.raw.persistence.failed" and correlation is not None:
                    raise RunValidationError(
                        f"{runtime_path}:{line_number}: raw-persistence failure "
                        "must not claim a durable raw-record correlation"
                    )
                if correlation is None:
                    continue

                key = (
                    correlation["raw_source"],
                    correlation["raw_session_id"],
                    correlation["raw_request_id"],
                )
                raw_record = raw_records.get(key)
                if raw_record is None:
                    raise RunValidationError(
                        f"{runtime_path}:{line_number}: runtime correlation "
                        f"{key!r} does not match any run raw record"
                    )

                if event_name not in _RAW_REQUEST_EVENT_NAMES:
                    continue
                if key in request_events:
                    raise RunValidationError(
                        f"{runtime_path}:{line_number}: duplicate API request "
                        f"event for raw record {key!r}"
                    )

                expected_event = (
                    "api.request.succeeded"
                    if raw_record["error"] is None
                    else "api.request.failed"
                )
                if event_name != expected_event:
                    raise RunValidationError(
                        f"{runtime_path}:{line_number}: {event_name} does not "
                        f"match raw error state for {key!r}; expected "
                        f"{expected_event}"
                    )
                request_events[key] = event_name
    except (OSError, json.JSONDecodeError) as exc:
        raise RunValidationError(
            f"Could not read runtime artifact for raw correlation "
            f"{runtime_path}: {exc}"
        ) from exc

    missing_request_events = set(raw_records).difference(request_events)
    if missing_request_events:
        examples = sorted(missing_request_events)[:3]
        raise RunValidationError(
            "Raw request records are missing matching API request events; "
            f"examples: {examples!r}"
        )


def _validate_runtime_event_relationship(manifest: Mapping[str, Any]) -> None:
    runtime_descriptors = [
        item
        for item in manifest["files"]
        if item.get("role") == "runtime_event_log"
    ]
    if len(runtime_descriptors) != 1:
        raise RunValidationError(
            "Manifest v2 must reference exactly one runtime event log"
        )

    descriptor = runtime_descriptors[0]
    if descriptor.get("run_ids") != [manifest["run_id"]]:
        raise RunValidationError(
            "Runtime event log run_id does not match the manifest run_id"
        )
    collector_name = manifest["collector"]["name"]
    if descriptor.get("collectors") != [collector_name]:
        raise RunValidationError(
            "Runtime event log collector does not match the manifest collector"
        )

    event_names = set(descriptor.get("event_names", []))
    if "collector.started" not in event_names:
        raise RunValidationError(
            "Runtime event log is missing collector.started"
        )
    if "collector.completed" not in event_names:
        raise RunValidationError(
            "Completed manifest runtime event log is missing collector.completed"
        )
    if "collector.failed" in event_names:
        raise RunValidationError(
            "Completed manifest runtime event log contains collector.failed"
        )
    severity_counts = descriptor.get("severity_counts", {})
    if severity_counts.get("critical") != 0:
        raise RunValidationError(
            "Completed manifest runtime event log contains a critical event"
        )


def _summary(
    files: list[Mapping[str, Any]],
    *,
    schema_version: str,
) -> dict[str, int]:
    raw = [item for item in files if item.get("role") == "raw_api_archive"]
    derived = [item for item in files if item.get("role") == "derived_csv"]
    runtime = [item for item in files if item.get("role") == "runtime_event_log"]
    summary = {
        "raw_file_count": len(raw),
        "raw_record_count": sum(int(item["record_count"]) for item in raw),
        "raw_error_record_count": sum(
            int(item["error_record_count"]) for item in raw
        ),
        "derived_csv_count": len(derived),
        "derived_row_count": sum(int(item["data_row_count"]) for item in derived),
    }
    if schema_version == CollectionRunManifest.SCHEMA_VERSION:
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
