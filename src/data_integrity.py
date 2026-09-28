"""Integrity inspection for raw and derived collection artifacts.

The functions in this module are deterministic and side-effect free except for
reading files. They are shared by run-manifest creation and the standalone
validator so both paths use the same counting and schema rules.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


RAW_RECORD_SCHEMA_VERSION = "raw_http_exchange.v1"
RUNTIME_EVENT_SCHEMA_VERSION = "runtime_event.v1"
RUNTIME_EVENT_SEVERITIES = {"info", "warning", "error", "critical"}
_RUNTIME_EVENT_NAME_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+$"
)


class DataIntegrityError(RuntimeError):
    """Raised when an artifact cannot be parsed or violates its baseline schema."""


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 digest of a file's exact bytes."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_raw_jsonl(path: str | Path) -> dict[str, Any]:
    """Inspect one raw JSONL file and return reproducible integrity metadata."""

    file_path = Path(path)
    record_count = 0
    error_record_count = 0
    schema_versions: set[str] = set()
    session_ids: set[str] = set()
    request_ids: set[str] = set()

    try:
        with file_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise DataIntegrityError(
                        f"{file_path}: blank JSONL line at {line_number}"
                    )
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DataIntegrityError(
                        f"{file_path}: invalid JSON on line {line_number}: {exc}"
                    ) from exc

                validate_raw_record(record, file_path=file_path, line_number=line_number)
                record_count += 1
                schema_versions.add(record["schema_version"])
                session_ids.add(record["session_id"])

                request_id = record["request"]["request_id"]
                if request_id in request_ids:
                    raise DataIntegrityError(
                        f"{file_path}: duplicate request_id {request_id!r}"
                    )
                request_ids.add(request_id)

                if record["error"] is not None:
                    error_record_count += 1
    except OSError as exc:
        raise DataIntegrityError(f"Could not read raw file {file_path}: {exc}") from exc

    if record_count == 0:
        raise DataIntegrityError(f"Raw JSONL file contains no records: {file_path}")

    return {
        "role": "raw_api_archive",
        "size_bytes": file_path.stat().st_size,
        "sha256": sha256_file(file_path),
        "record_count": record_count,
        "error_record_count": error_record_count,
        "schema_versions": sorted(schema_versions),
        "session_ids": sorted(session_ids),
    }


def inspect_runtime_event_jsonl(path: str | Path) -> dict[str, Any]:
    """Inspect one structured runtime-event JSONL file."""

    file_path = Path(path)
    event_count = 0
    error_event_count = 0
    schema_versions: set[str] = set()
    run_ids: set[str] = set()
    collectors: set[str] = set()
    event_names: set[str] = set()
    event_ids: set[str] = set()
    severity_counts = {severity: 0 for severity in sorted(RUNTIME_EVENT_SEVERITIES)}
    previous_monotonic_ns: int | None = None

    try:
        with file_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise DataIntegrityError(
                        f"{file_path}: blank JSONL line at {line_number}"
                    )
                try:
                    record = json.loads(
                        line,
                        parse_constant=_reject_nonstandard_json_constant,
                    )
                except (json.JSONDecodeError, ValueError) as exc:
                    raise DataIntegrityError(
                        f"{file_path}: invalid strict JSON on line "
                        f"{line_number}: {exc}"
                    ) from exc

                validate_runtime_event_record(
                    record,
                    file_path=file_path,
                    line_number=line_number,
                )

                expected_sequence = event_count + 1
                if record["sequence"] != expected_sequence:
                    raise DataIntegrityError(
                        f"{file_path}:{line_number}: expected sequence "
                        f"{expected_sequence}, observed {record['sequence']}"
                    )
                if record["event_id"] in event_ids:
                    raise DataIntegrityError(
                        f"{file_path}: duplicate event_id {record['event_id']!r}"
                    )
                current_monotonic_ns = record["occurred_monotonic_ns"]
                if (
                    previous_monotonic_ns is not None
                    and current_monotonic_ns < previous_monotonic_ns
                ):
                    raise DataIntegrityError(
                        f"{file_path}:{line_number}: monotonic event time moved "
                        "backward"
                    )

                event_count += 1
                previous_monotonic_ns = current_monotonic_ns
                event_ids.add(record["event_id"])
                schema_versions.add(record["schema_version"])
                run_ids.add(record["run_id"])
                collectors.add(record["collector"])
                event_names.add(record["event_name"])
                severity_counts[record["severity"]] += 1
                if record["severity"] in {"error", "critical"}:
                    error_event_count += 1
    except OSError as exc:
        raise DataIntegrityError(
            f"Could not read runtime event file {file_path}: {exc}"
        ) from exc

    if event_count == 0:
        raise DataIntegrityError(
            f"Runtime event JSONL file contains no records: {file_path}"
        )

    return {
        "role": "runtime_event_log",
        "size_bytes": file_path.stat().st_size,
        "sha256": sha256_file(file_path),
        "event_count": event_count,
        "error_event_count": error_event_count,
        "schema_versions": sorted(schema_versions),
        "run_ids": sorted(run_ids),
        "collectors": sorted(collectors),
        "event_names": sorted(event_names),
        "severity_counts": severity_counts,
    }


def inspect_csv(path: str | Path) -> dict[str, Any]:
    """Inspect one derived CSV file without assigning semantic meaning to rows."""

    file_path = Path(path)
    try:
        with file_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise DataIntegrityError(f"CSV has no header row: {file_path}")
            columns = list(reader.fieldnames)
            row_count = sum(1 for _ in reader)
    except (OSError, csv.Error) as exc:
        raise DataIntegrityError(f"Could not inspect CSV file {file_path}: {exc}") from exc

    return {
        "role": "derived_csv",
        "size_bytes": file_path.stat().st_size,
        "sha256": sha256_file(file_path),
        "data_row_count": row_count,
        "columns": columns,
    }


def validate_raw_record(
    record: Any,
    *,
    file_path: Path | None = None,
    line_number: int | None = None,
) -> None:
    """Validate the required raw-envelope fields and cross-field invariants.

    This is deliberately a baseline envelope validator, not an endpoint schema
    validator. It does not interpret Kalshi payload fields or settlement meaning.
    """

    location = _location(file_path, line_number)
    if not isinstance(record, dict):
        raise DataIntegrityError(f"{location}raw record must be a JSON object")

    required_top_level = {
        "schema_version",
        "source",
        "session_id",
        "request",
        "timing",
        "response",
        "source_timestamps",
        "error",
    }
    missing = sorted(required_top_level.difference(record))
    if missing:
        raise DataIntegrityError(f"{location}missing top-level fields: {missing}")

    if record["schema_version"] != RAW_RECORD_SCHEMA_VERSION:
        raise DataIntegrityError(
            f"{location}unsupported raw schema_version: "
            f"{record['schema_version']!r}"
        )
    _require_nonempty_string(record["source"], "source", location)
    _require_nonempty_string(record["session_id"], "session_id", location)

    request = record["request"]
    if not isinstance(request, dict):
        raise DataIntegrityError(f"{location}request must be an object")
    for field in (
        "request_id",
        "method",
        "base_url",
        "path",
        "params",
        "started_at_utc",
        "started_monotonic_ns",
    ):
        if field not in request:
            raise DataIntegrityError(f"{location}request missing field {field!r}")
    for field in ("request_id", "method", "base_url", "path", "started_at_utc"):
        _require_nonempty_string(request[field], f"request.{field}", location)
    if not isinstance(request["params"], dict):
        raise DataIntegrityError(f"{location}request.params must be an object")
    _require_nonnegative_int(
        request["started_monotonic_ns"],
        "request.started_monotonic_ns",
        location,
    )

    timing = record["timing"]
    if not isinstance(timing, dict):
        raise DataIntegrityError(f"{location}timing must be an object")
    for field in (
        "received_at_utc",
        "received_monotonic_ns",
        "elapsed_monotonic_ns",
    ):
        if field not in timing:
            raise DataIntegrityError(f"{location}timing missing field {field!r}")
    _require_nonempty_string(
        timing["received_at_utc"], "timing.received_at_utc", location
    )
    _require_nonnegative_int(
        timing["received_monotonic_ns"],
        "timing.received_monotonic_ns",
        location,
    )
    _require_nonnegative_int(
        timing["elapsed_monotonic_ns"],
        "timing.elapsed_monotonic_ns",
        location,
    )
    expected_elapsed = (
        timing["received_monotonic_ns"] - request["started_monotonic_ns"]
    )
    if timing["elapsed_monotonic_ns"] != expected_elapsed:
        raise DataIntegrityError(
            f"{location}elapsed_monotonic_ns does not equal receive minus start"
        )

    if not isinstance(record["source_timestamps"], list):
        raise DataIntegrityError(f"{location}source_timestamps must be a list")
    for index, item in enumerate(record["source_timestamps"]):
        if not isinstance(item, dict) or set(item) != {"json_path", "value"}:
            raise DataIntegrityError(
                f"{location}source_timestamps[{index}] must contain "
                "json_path and value"
            )
        _require_nonempty_string(
            item["json_path"],
            f"source_timestamps[{index}].json_path",
            location,
        )

    error = record["error"]
    if error is not None:
        if not isinstance(error, dict):
            raise DataIntegrityError(f"{location}error must be null or an object")
        for field in ("stage", "type", "message"):
            if field not in error:
                raise DataIntegrityError(f"{location}error missing field {field!r}")
            _require_nonempty_string(error[field], f"error.{field}", location)

    response = record["response"]
    if response is None:
        if error is None or error.get("stage") != "transport":
            raise DataIntegrityError(
                f"{location}null response requires a transport-stage error"
            )
        return

    if not isinstance(response, dict):
        raise DataIntegrityError(f"{location}response must be null or an object")
    for field in (
        "status_code",
        "reason",
        "url",
        "headers",
        "body_text",
        "body_size_bytes",
        "body_sha256",
        "json_parse_error",
    ):
        if field not in response:
            raise DataIntegrityError(f"{location}response missing field {field!r}")
    if not isinstance(response["status_code"], int):
        raise DataIntegrityError(f"{location}response.status_code must be an integer")
    if response["reason"] is not None and not isinstance(response["reason"], str):
        raise DataIntegrityError(f"{location}response.reason must be text or null")
    if response["url"] is not None and not isinstance(response["url"], str):
        raise DataIntegrityError(f"{location}response.url must be text or null")
    if not isinstance(response["headers"], dict):
        raise DataIntegrityError(f"{location}response.headers must be an object")
    if not isinstance(response["body_text"], str):
        raise DataIntegrityError(f"{location}response.body_text must be text")
    _require_nonnegative_int(
        response["body_size_bytes"], "response.body_size_bytes", location
    )
    body_digest = response["body_sha256"]
    if not isinstance(body_digest, str) or len(body_digest) != 64:
        raise DataIntegrityError(
            f"{location}response.body_sha256 must be a 64-character digest"
        )
    try:
        int(body_digest, 16)
    except ValueError as exc:
        raise DataIntegrityError(
            f"{location}response.body_sha256 must be hexadecimal"
        ) from exc
    if response["json_parse_error"] is not None and not isinstance(
        response["json_parse_error"], str
    ):
        raise DataIntegrityError(
            f"{location}response.json_parse_error must be text or null"
        )


def validate_runtime_event_record(
    record: Any,
    *,
    file_path: Path | None = None,
    line_number: int | None = None,
) -> None:
    """Validate the stable runtime-event envelope."""

    location = _location(file_path, line_number)
    if not isinstance(record, dict):
        raise DataIntegrityError(f"{location}runtime event must be a JSON object")

    required = {
        "schema_version",
        "event_id",
        "sequence",
        "event_name",
        "severity",
        "occurred_at_utc",
        "occurred_monotonic_ns",
        "run_id",
        "collector",
        "message",
        "correlation",
        "context",
        "error",
    }
    missing = sorted(required.difference(record))
    if missing:
        raise DataIntegrityError(
            f"{location}runtime event missing fields: {missing}"
        )

    if record["schema_version"] != RUNTIME_EVENT_SCHEMA_VERSION:
        raise DataIntegrityError(
            f"{location}unsupported runtime schema_version: "
            f"{record['schema_version']!r}"
        )
    for field in (
        "event_id",
        "event_name",
        "occurred_at_utc",
        "run_id",
        "collector",
        "message",
    ):
        _require_nonempty_string(record[field], field, location)
    if not _RUNTIME_EVENT_NAME_PATTERN.fullmatch(record["event_name"]):
        raise DataIntegrityError(
            f"{location}event_name must use lowercase dot-separated segments"
        )
    _require_utc_timestamp(
        record["occurred_at_utc"],
        "occurred_at_utc",
        location,
    )
    if record["severity"] not in RUNTIME_EVENT_SEVERITIES:
        raise DataIntegrityError(
            f"{location}unsupported runtime severity: {record['severity']!r}"
        )
    if (
        not isinstance(record["sequence"], int)
        or isinstance(record["sequence"], bool)
        or record["sequence"] <= 0
    ):
        raise DataIntegrityError(
            f"{location}sequence must be a positive integer"
        )
    _require_nonnegative_int(
        record["occurred_monotonic_ns"],
        "occurred_monotonic_ns",
        location,
    )
    if not isinstance(record["context"], dict):
        raise DataIntegrityError(f"{location}context must be an object")

    correlation = record["correlation"]
    if correlation is not None:
        if not isinstance(correlation, dict):
            raise DataIntegrityError(
                f"{location}correlation must be null or an object"
            )
        required_correlation = {
            "raw_source",
            "raw_session_id",
            "raw_request_id",
        }
        if set(correlation) != required_correlation:
            raise DataIntegrityError(
                f"{location}correlation must contain exactly "
                f"{sorted(required_correlation)}"
            )
        for field in sorted(required_correlation):
            _require_nonempty_string(
                correlation[field],
                f"correlation.{field}",
                location,
            )

    error = record["error"]
    if error is not None:
        if not isinstance(error, dict):
            raise DataIntegrityError(f"{location}error must be null or an object")
        for field in ("type", "message"):
            if field not in error:
                raise DataIntegrityError(
                    f"{location}runtime error missing field {field!r}"
                )
            _require_nonempty_string(
                error[field],
                f"error.{field}",
                location,
            )


def _reject_nonstandard_json_constant(value: str) -> None:
    raise ValueError(f"Non-standard JSON constant {value!r} is not allowed")


def _location(file_path: Path | None, line_number: int | None) -> str:
    if file_path is None:
        return ""
    if line_number is None:
        return f"{file_path}: "
    return f"{file_path}:{line_number}: "


def _require_nonempty_string(value: Any, field: str, location: str) -> None:
    if not isinstance(value, str) or not value:
        raise DataIntegrityError(f"{location}{field} must be non-empty text")


def _require_utc_timestamp(value: Any, field: str, location: str) -> None:
    _require_nonempty_string(value, field, location)
    if not value.endswith("Z"):
        raise DataIntegrityError(f"{location}{field} must end with 'Z'")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataIntegrityError(
            f"{location}{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise DataIntegrityError(f"{location}{field} must be UTC")


def _require_nonnegative_int(value: Any, field: str, location: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DataIntegrityError(f"{location}{field} must be a non-negative integer")
