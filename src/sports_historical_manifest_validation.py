"""Offline semantic validation for Checkpoint-08 Sports historical datasets.

This validator reconciles every normalized pre-staleness row to the exact raw
HTTP exchange declared by the run manifest. It intentionally does not parse or
validate final YES/NO outcomes.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kalshi_historical_validation import HistoricalCutoff
from .sports_historical_collector import (
    SportsHistoricalCollectionError,
    SportsHistoricalRows,
    build_anchor_row,
    build_candle_rows,
    build_event_row,
    build_market_row,
    validate_collected_rows,
)
from .sports_historical_schema import (
    ANCHOR_FIELDS,
    CANDLE_FIELDS,
    EVENT_FIELDS,
    MARKET_FIELDS,
)


class SportsHistoricalManifestValidationError(RuntimeError):
    """Raised when manifest/raw/derived reconciliation fails."""


@dataclass(frozen=True)
class _Ref:
    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class _Response:
    payload: dict[str, Any]
    raw_record: _Ref
    request_started_at_utc: str = ""
    request_started_monotonic_ns: int = 0
    received_at_utc: str = ""
    received_monotonic_ns: int = 0


def validate_sports_historical_manifest(
    manifest_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    path = Path(manifest_path)
    repo_root = Path(repository_root).resolve()
    manifest = _load_json(path, "manifest")

    collector = manifest.get("collector")
    if not isinstance(collector, Mapping) or collector.get("name") != "collect_sports_historical":
        raise SportsHistoricalManifestValidationError(
            "manifest is not for collect_sports_historical"
        )
    if manifest.get("status") != "completed":
        raise SportsHistoricalManifestValidationError(
            "Sports historical validation requires a completed manifest"
        )
    run_id = _required_text(manifest.get("run_id"), "manifest.run_id")
    result = manifest.get("result")
    if not isinstance(result, Mapping):
        raise SportsHistoricalManifestValidationError("manifest.result must be an object")
    if result.get("outcomes_materialized") is not False:
        raise SportsHistoricalManifestValidationError(
            "pre-staleness manifest must explicitly state outcomes_materialized=false"
        )
    if result.get("calibration_run") is not False:
        raise SportsHistoricalManifestValidationError(
            "collector manifest must state calibration_run=false"
        )

    raw_records = _load_raw_records(manifest, repo_root)
    csv_paths = _find_table_csvs(manifest, repo_root, run_id)
    events = tuple(_read_csv(csv_paths["events"], EVENT_FIELDS))
    markets = tuple(_read_csv(csv_paths["markets"], MARKET_FIELDS))
    anchors = tuple(_read_csv(csv_paths["anchors"], ANCHOR_FIELDS))
    candles = tuple(_read_csv(csv_paths["candles"], CANDLE_FIELDS))

    cutoff = HistoricalCutoff(
        market_settled_ts=_parse_timestamp(result.get("market_settled_cutoff"), "market_settled_cutoff"),
        trades_created_ts=_parse_timestamp(result.get("trades_created_cutoff"), "trades_created_cutoff"),
        orders_updated_ts=_parse_timestamp(result.get("orders_updated_cutoff"), "orders_updated_cutoff"),
        market_positions_last_updated_ts=_optional_timestamp(
            result.get("market_positions_last_updated_cutoff"),
            "market_positions_last_updated_cutoff",
        ),
    )
    rows = SportsHistoricalRows(
        events=events,
        markets=markets,
        anchors=anchors,
        candles=candles,
        cutoff=cutoff,
        cutoff_raw_source=_required_text(result.get("cutoff_raw_source"), "cutoff_raw_source"),
        cutoff_raw_session_id=_required_text(result.get("cutoff_raw_session_id"), "cutoff_raw_session_id"),
        cutoff_raw_request_id=_required_text(result.get("cutoff_raw_request_id"), "cutoff_raw_request_id"),
        event_pages_scanned=int(result.get("event_pages_scanned", 0)),
    )

    try:
        summary = validate_collected_rows(rows, run_id=run_id)
    except (SportsHistoricalCollectionError, ValueError) as exc:
        raise SportsHistoricalManifestValidationError(str(exc)) from exc

    _validate_cutoff_raw(rows, raw_records)
    _validate_event_rows(events, raw_records, run_id)
    _validate_market_rows(markets, raw_records, run_id)
    _validate_anchor_and_candle_rows(anchors, candles, raw_records, run_id)

    return {
        "manifest_path": str(path),
        "run_id": run_id,
        **summary,
        "raw_record_count": len(raw_records),
        "outcomes_materialized": False,
        "validation": "PASS",
    }


def _validate_cutoff_raw(
    rows: SportsHistoricalRows,
    raw_records: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> None:
    key = (rows.cutoff_raw_source, rows.cutoff_raw_session_id, rows.cutoff_raw_request_id)
    record = _required_raw(raw_records, key)
    request = record["request"]
    if request.get("path") != "/historical/cutoff":
        raise SportsHistoricalManifestValidationError("cutoff raw reference has wrong request path")
    payload = _payload(record)
    for field, expected in (
        ("market_settled_ts", rows.cutoff.market_settled_ts),
        ("trades_created_ts", rows.cutoff.trades_created_ts),
        ("orders_updated_ts", rows.cutoff.orders_updated_ts),
    ):
        if _parse_timestamp(payload.get(field), field) != expected:
            raise SportsHistoricalManifestValidationError(f"cutoff field {field} differs from raw")


def _validate_event_rows(
    rows: Sequence[Mapping[str, str]],
    raw_records: Mapping[tuple[str, str, str], Mapping[str, Any]],
    run_id: str,
) -> None:
    for index, row in enumerate(rows, start=2):
        record, response = _row_raw_response(row, raw_records)
        request = record["request"]
        if request.get("path") != "/events":
            raise SportsHistoricalManifestValidationError(f"event row {index} raw path is not /events")
        payload_events = response.payload.get("events")
        if not isinstance(payload_events, list):
            raise SportsHistoricalManifestValidationError(f"event row {index} raw payload has no events list")
        matches = [item for item in payload_events if isinstance(item, Mapping) and item.get("event_ticker") == row["event_ticker"]]
        if len(matches) != 1:
            raise SportsHistoricalManifestValidationError(f"event row {index} does not map to exactly one raw event")
        rebuilt = build_event_row(run_id=run_id, event=matches[0], response=response)
        _compare_row(row, rebuilt, EVENT_FIELDS, f"event row {index}")


def _validate_market_rows(
    rows: Sequence[Mapping[str, str]],
    raw_records: Mapping[tuple[str, str, str], Mapping[str, Any]],
    run_id: str,
) -> None:
    for index, row in enumerate(rows, start=2):
        record, response = _row_raw_response(row, raw_records)
        expected_path = "/historical/markets" if row["route_tier"] == "historical" else "/markets"
        if record["request"].get("path") != expected_path:
            raise SportsHistoricalManifestValidationError(f"market row {index} raw path disagrees with route tier")
        payload_markets = response.payload.get("markets")
        if not isinstance(payload_markets, list):
            raise SportsHistoricalManifestValidationError(f"market row {index} raw payload has no markets list")
        matches = [item for item in payload_markets if isinstance(item, Mapping) and item.get("ticker") == row["ticker"]]
        if len(matches) != 1:
            raise SportsHistoricalManifestValidationError(f"market row {index} does not map to exactly one raw market")
        rebuilt = build_market_row(
            run_id=run_id,
            market=matches[0],
            route_tier=row["route_tier"],
            response=response,
        )
        _compare_row(row, rebuilt, MARKET_FIELDS, f"market row {index}")


def _validate_anchor_and_candle_rows(
    anchors: Sequence[Mapping[str, str]],
    candles: Sequence[Mapping[str, str]],
    raw_records: Mapping[tuple[str, str, str], Mapping[str, Any]],
    run_id: str,
) -> None:
    candles_by_anchor: dict[tuple[str, str], list[Mapping[str, str]]] = {}
    for row in candles:
        candles_by_anchor.setdefault((row["ticker"], row["anchor_name"]), []).append(row)

    for index, anchor in enumerate(anchors, start=2):
        record, response = _row_raw_response(anchor, raw_records)
        path = record["request"].get("path")
        if anchor["route_tier"] == "historical":
            expected = f"/historical/markets/{anchor['ticker']}/candlesticks"
            if path != expected:
                raise SportsHistoricalManifestValidationError(f"anchor row {index} historical raw path mismatch")
        else:
            if not isinstance(path, str) or not path.endswith(f"/markets/{anchor['ticker']}/candlesticks") or not path.startswith("/series/"):
                raise SportsHistoricalManifestValidationError(f"anchor row {index} live raw path mismatch")

        params = record["request"].get("params")
        if not isinstance(params, Mapping):
            raise SportsHistoricalManifestValidationError(f"anchor row {index} raw params missing")
        expected_params = {
            "start_ts": int(anchor["window_start_ts"]),
            "end_ts": int(anchor["window_end_ts"]),
            "period_interval": 1,
        }
        for key, value in expected_params.items():
            if params.get(key) != value:
                raise SportsHistoricalManifestValidationError(f"anchor row {index} raw param {key} mismatch")
        if anchor["route_tier"] == "live" and str(params.get("include_latest_before_start")).lower() != "false":
            raise SportsHistoricalManifestValidationError(
                f"anchor row {index} did not explicitly disable synthetic live candle"
            )

        rebuilt_candles = build_candle_rows(
            run_id=run_id,
            ticker=anchor["ticker"],
            anchor_name=anchor["anchor_name"],
            anchor_ts=int(anchor["anchor_ts"]),
            window_start_ts=int(anchor["window_start_ts"]),
            route_tier=anchor["route_tier"],
            response=response,
        )
        rebuilt_anchor = build_anchor_row(
            run_id=run_id,
            ticker=anchor["ticker"],
            anchor_name=anchor["anchor_name"],
            anchor_ts=int(anchor["anchor_ts"]),
            window_start_ts=int(anchor["window_start_ts"]),
            route_tier=anchor["route_tier"],
            response=response,
            normalized_candles=rebuilt_candles,
            expected_candle_count=len(rebuilt_candles),
            expected_quote_pair_count=sum(1 for row in rebuilt_candles if row["quote_pair_present"] == "true"),
        )
        _compare_row(anchor, rebuilt_anchor, ANCHOR_FIELDS, f"anchor row {index}")

        actual = sorted(
            candles_by_anchor.get((anchor["ticker"], anchor["anchor_name"]), []),
            key=lambda row: int(row["end_period_ts"]),
        )
        if len(actual) != len(rebuilt_candles):
            raise SportsHistoricalManifestValidationError(f"anchor row {index} derived candle count differs from raw")
        for offset, (actual_row, rebuilt_row) in enumerate(zip(actual, rebuilt_candles), start=1):
            _compare_row(actual_row, rebuilt_row, CANDLE_FIELDS, f"anchor row {index} candle {offset}")


def _row_raw_response(
    row: Mapping[str, str],
    raw_records: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> tuple[Mapping[str, Any], _Response]:
    key = (row["raw_source"], row["raw_session_id"], row["raw_request_id"])
    record = _required_raw(raw_records, key)
    return record, _Response(payload=_payload(record), raw_record=_Ref(*key))


def _required_raw(
    records: Mapping[tuple[str, str, str], Mapping[str, Any]],
    key: tuple[str, str, str],
) -> Mapping[str, Any]:
    record = records.get(key)
    if record is None:
        raise SportsHistoricalManifestValidationError(f"unknown raw lineage key {key!r}")
    if record.get("error") is not None:
        raise SportsHistoricalManifestValidationError(f"raw lineage key {key!r} points to an error record")
    request = record.get("request")
    response = record.get("response")
    if not isinstance(request, Mapping) or not isinstance(response, Mapping):
        raise SportsHistoricalManifestValidationError(f"raw lineage key {key!r} is malformed")
    if request.get("method") != "GET":
        raise SportsHistoricalManifestValidationError(f"raw lineage key {key!r} is not GET")
    status = response.get("status_code")
    if not isinstance(status, int) or not 200 <= status < 300:
        raise SportsHistoricalManifestValidationError(f"raw lineage key {key!r} is not HTTP success")
    if response.get("json_parse_error") is not None:
        raise SportsHistoricalManifestValidationError(f"raw lineage key {key!r} has JSON parse error")
    return record


def _payload(record: Mapping[str, Any]) -> dict[str, Any]:
    response = record["response"]
    body = response.get("body_text")
    if not isinstance(body, str):
        raise SportsHistoricalManifestValidationError("raw response body_text must be text")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SportsHistoricalManifestValidationError(f"raw response body is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SportsHistoricalManifestValidationError("raw response top-level JSON must be object")
    return payload


def _load_raw_records(
    manifest: Mapping[str, Any],
    repository_root: Path,
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    records: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for descriptor in manifest.get("files", []):
        if not isinstance(descriptor, Mapping) or descriptor.get("role") != "raw_api_archive":
            continue
        raw_path = _resolve_path(descriptor.get("path"), repository_root)
        try:
            with raw_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    record = json.loads(line)
                    key = (
                        record["source"],
                        record["session_id"],
                        record["request"]["request_id"],
                    )
                    if key in records:
                        raise SportsHistoricalManifestValidationError(
                            f"duplicate raw key at {raw_path}:{line_number}: {key!r}"
                        )
                    records[key] = record
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise SportsHistoricalManifestValidationError(f"could not index raw file {raw_path}: {exc}") from exc
    if not records:
        raise SportsHistoricalManifestValidationError("manifest contains no raw API records")
    return records


def _find_table_csvs(
    manifest: Mapping[str, Any],
    repository_root: Path,
    run_id: str,
) -> dict[str, Path]:
    found: dict[str, Path] = {}
    allowed = {"events", "markets", "anchors", "candles"}
    for descriptor in manifest.get("files", []):
        if not isinstance(descriptor, Mapping) or descriptor.get("role") != "derived_csv":
            continue
        path = _resolve_path(descriptor.get("path"), repository_root)
        name = path.name
        prefix = f"{run_id}_"
        if not name.startswith(prefix) or not name.endswith(".csv"):
            raise SportsHistoricalManifestValidationError(f"unexpected derived CSV name {name!r}")
        table = name[len(prefix):-4]
        if table not in allowed:
            raise SportsHistoricalManifestValidationError(
                f"pre-staleness manifest contains unexpected derived table {table!r}"
            )
        if table in found:
            raise SportsHistoricalManifestValidationError(f"duplicate derived table {table!r}")
        found[table] = path
    missing = allowed - set(found)
    if missing:
        raise SportsHistoricalManifestValidationError(f"manifest is missing derived tables: {sorted(missing)}")
    return found


def _read_csv(path: Path, fields: Sequence[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(fields):
                raise SportsHistoricalManifestValidationError(
                    f"unexpected CSV columns in {path}: {reader.fieldnames!r}"
                )
            return [dict(row) for row in reader]
    except (OSError, csv.Error) as exc:
        raise SportsHistoricalManifestValidationError(f"could not read CSV {path}: {exc}") from exc


def _compare_row(
    actual: Mapping[str, str],
    expected: Mapping[str, str],
    fields: Sequence[str],
    label: str,
) -> None:
    for field in fields:
        if actual.get(field) != expected.get(field):
            raise SportsHistoricalManifestValidationError(
                f"{label} field {field!r} differs from raw evidence"
            )


def _resolve_path(spec: Any, repository_root: Path) -> Path:
    if not isinstance(spec, Mapping):
        raise SportsHistoricalManifestValidationError("manifest path descriptor must be object")
    kind = spec.get("kind")
    value = spec.get("value")
    if not isinstance(value, str) or not value:
        raise SportsHistoricalManifestValidationError("manifest path value must be non-empty text")
    if kind == "absolute":
        return Path(value)
    if kind == "repository_relative":
        candidate = (repository_root / value).resolve()
        try:
            candidate.relative_to(repository_root)
        except ValueError as exc:
            raise SportsHistoricalManifestValidationError("repository-relative path escapes repository") from exc
        return candidate
    raise SportsHistoricalManifestValidationError(f"unsupported manifest path kind {kind!r}")


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SportsHistoricalManifestValidationError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SportsHistoricalManifestValidationError(f"{label} must be a JSON object")
    return value


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SportsHistoricalManifestValidationError(f"{field} must be non-empty text")
    return value


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise SportsHistoricalManifestValidationError(f"{field} must be timestamp text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SportsHistoricalManifestValidationError(f"{field} is not valid timestamp") from exc
    if parsed.tzinfo is None:
        raise SportsHistoricalManifestValidationError(f"{field} must include timezone")
    return parsed


def _optional_timestamp(value: Any, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    return _parse_timestamp(value, field)
