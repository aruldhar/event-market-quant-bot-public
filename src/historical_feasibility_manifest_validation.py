"""Offline raw-to-derived validation for Checkpoint-09 historical feasibility."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .historical_feasibility import (
    HistoricalCutoff,
    HistoricalFeasibilityError,
    HistoricalFeasibilityRows,
    build_category_summary_rows,
    build_event_row,
    build_market_row,
    build_observation_rows,
    build_window_row,
    validate_collected_rows,
)
from .historical_feasibility_schema import (
    CATEGORY_SUMMARY_FIELDS,
    EVENT_FIELDS,
    MARKET_FIELDS,
    MIN_FEASIBILITY_EVENTS_PER_CATEGORY,
    OBSERVATION_FIELDS,
    TARGET_CATEGORIES,
    WINDOW_FIELDS,
)


class HistoricalFeasibilityManifestValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class _Ref:
    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class _Response:
    payload: dict[str, Any]
    raw_record: _Ref


def validate_historical_feasibility_manifest(
    manifest_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    path = Path(manifest_path)
    repo_root = Path(repository_root).resolve()
    manifest = _load_json(path, "manifest")
    collector = manifest.get("collector")
    collector_name = collector.get("name") if isinstance(collector, Mapping) else None
    if collector_name not in {"collect_historical_feasibility", "collect_sports_v2_scalability"}:
        raise HistoricalFeasibilityManifestValidationError(
            "manifest is not for a supported historical feasibility collector"
        )
    if manifest.get("status") != "completed":
        raise HistoricalFeasibilityManifestValidationError(
            "historical feasibility validation requires completed manifest"
        )
    run_id = _required_text(manifest.get("run_id"), "manifest.run_id")
    result = manifest.get("result")
    if not isinstance(result, Mapping):
        raise HistoricalFeasibilityManifestValidationError("manifest.result must be object")
    if result.get("outcomes_materialized") is not False:
        raise HistoricalFeasibilityManifestValidationError(
            "manifest must state outcomes_materialized=false"
        )
    if result.get("strategy_analysis_run") is not False:
        raise HistoricalFeasibilityManifestValidationError(
            "manifest must state strategy_analysis_run=false"
        )
    if int(result.get("min_feasibility_events_per_category", 0)) != MIN_FEASIBILITY_EVENTS_PER_CATEGORY:
        raise HistoricalFeasibilityManifestValidationError(
            "manifest feasibility event gate differs from the frozen predeclared value"
        )

    raw_records = _load_raw_records(manifest, repo_root)
    csv_paths = _find_table_csvs(manifest, repo_root, run_id)
    events = tuple(_read_csv(csv_paths["events"], EVENT_FIELDS))
    markets = tuple(_read_csv(csv_paths["markets"], MARKET_FIELDS))
    windows = tuple(_read_csv(csv_paths["windows"], WINDOW_FIELDS))
    observations = tuple(_read_csv(csv_paths["observations"], OBSERVATION_FIELDS))
    category_summary = tuple(_read_csv(csv_paths["category_summary"], CATEGORY_SUMMARY_FIELDS))

    cutoff = HistoricalCutoff(
        market_settled_ts=_parse_timestamp(result.get("market_settled_cutoff"), "market_settled_cutoff"),
        trades_created_ts=_parse_timestamp(result.get("trades_created_cutoff"), "trades_created_cutoff"),
        orders_updated_ts=_parse_timestamp(result.get("orders_updated_cutoff"), "orders_updated_cutoff"),
        market_positions_last_updated_ts=_optional_timestamp(
            result.get("market_positions_last_updated_cutoff"),
            "market_positions_last_updated_cutoff",
        ),
    )
    rows = HistoricalFeasibilityRows(
        events=events,
        markets=markets,
        windows=windows,
        observations=observations,
        category_summary=category_summary,
        cutoff=cutoff,
        cutoff_raw_source=_required_text(result.get("cutoff_raw_source"), "cutoff_raw_source"),
        cutoff_raw_session_id=_required_text(result.get("cutoff_raw_session_id"), "cutoff_raw_session_id"),
        cutoff_raw_request_id=_required_text(result.get("cutoff_raw_request_id"), "cutoff_raw_request_id"),
        event_pages_scanned=int(result.get("event_pages_scanned", 0)),
        cross_tier_observation_count=int(result.get("cross_tier_observation_count", 0)),
        cross_tier_market_count=int(result.get("cross_tier_market_count", 0)),
        cross_tier_recovery_fetch_count=int(result.get("cross_tier_recovery_fetch_count", 0)),
        unclassifiable_event_count=int(result.get("unclassifiable_event_count", 0)),
        target_events_per_category=int(result.get("target_events_per_category", 0)),
        max_markets_per_event=int(result.get("max_markets_per_event", 0)),
    )
    try:
        summary = validate_collected_rows(rows, run_id=run_id)
    except (HistoricalFeasibilityError, ValueError) as exc:
        raise HistoricalFeasibilityManifestValidationError(str(exc)) from exc

    _validate_cutoff_raw(rows, raw_records)
    _validate_event_rows(events, raw_records, run_id)
    market_source_objects = _validate_market_rows(markets, raw_records, run_id)
    _validate_windows_and_observations(
        rows,
        raw_records,
        market_source_objects=market_source_objects,
        run_id=run_id,
    )
    rebuilt_summary = build_category_summary_rows(
        HistoricalFeasibilityRows(**{**rows.__dict__, "category_summary": ()})
    )
    if tuple(rebuilt_summary) != category_summary:
        raise HistoricalFeasibilityManifestValidationError(
            "category summary does not rebuild from outcome-blind rows"
        )

    scalability = None
    categories = list(TARGET_CATEGORIES)
    if collector_name == "collect_sports_v2_scalability":
        from .sports_calibration_v2_scalability import (
            SPORTS_V2_MAX_MARKETS_PER_EVENT,
            SPORTS_V2_SCALABILITY_MIN_EVENTS,
            build_sports_v2_scalability_summary,
        )
        if result.get("collection_categories") != ["Sports"]:
            raise HistoricalFeasibilityManifestValidationError(
                "Sports V2 manifest must state collection_categories=['Sports']"
            )
        if int(result.get("sports_v2_scalability_min_events", 0)) != SPORTS_V2_SCALABILITY_MIN_EVENTS:
            raise HistoricalFeasibilityManifestValidationError(
                "Sports V2 manifest minimum-event gate differs from frozen value"
            )
        if int(result.get("max_markets_per_event", 0)) != SPORTS_V2_MAX_MARKETS_PER_EVENT:
            raise HistoricalFeasibilityManifestValidationError(
                "Sports V2 manifest market sampling differs from frozen value"
            )
        scalability = build_sports_v2_scalability_summary(rows)
        if result.get("sports_v2_scalability") != scalability:
            raise HistoricalFeasibilityManifestValidationError(
                "Sports V2 scalability summary does not rebuild from outcome-blind rows"
            )
        categories = ["Sports"]

    return {
        "manifest_path": str(path),
        "run_id": run_id,
        "collector_name": collector_name,
        **summary,
        "raw_record_count": len(raw_records),
        "categories": categories,
        "sports_v2_scalability": scalability,
        "outcomes_materialized": False,
        "validation": "PASS",
    }


def _validate_cutoff_raw(
    rows: HistoricalFeasibilityRows,
    raw_records: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> None:
    key = (rows.cutoff_raw_source, rows.cutoff_raw_session_id, rows.cutoff_raw_request_id)
    record = _required_raw(raw_records, key)
    if record["request"].get("path") != "/historical/cutoff":
        raise HistoricalFeasibilityManifestValidationError("cutoff raw path mismatch")
    payload = _payload(record)
    if _parse_timestamp(payload.get("market_settled_ts"), "market_settled_ts") != rows.cutoff.market_settled_ts:
        raise HistoricalFeasibilityManifestValidationError("cutoff differs from raw evidence")


def _validate_event_rows(
    rows: Sequence[Mapping[str, str]],
    raw_records: Mapping[tuple[str, str, str], Mapping[str, Any]],
    run_id: str,
) -> None:
    for index, row in enumerate(rows, start=2):
        record, response = _row_raw_response(row, raw_records)
        if record["request"].get("path") != "/events":
            raise HistoricalFeasibilityManifestValidationError(
                f"event row {index} raw path is not /events"
            )
        source_items = response.payload.get("events")
        if not isinstance(source_items, list):
            raise HistoricalFeasibilityManifestValidationError(
                f"event row {index} raw payload has no events list"
            )
        matches = [
            item for item in source_items
            if isinstance(item, Mapping) and item.get("event_ticker") == row["event_ticker"]
        ]
        if len(matches) != 1:
            raise HistoricalFeasibilityManifestValidationError(
                f"event row {index} does not map to exactly one raw event"
            )
        rebuilt = build_event_row(run_id=run_id, event=matches[0], response=response)
        _compare_row(row, rebuilt, EVENT_FIELDS, f"event row {index}")


def _validate_market_rows(
    rows: Sequence[Mapping[str, str]],
    raw_records: Mapping[tuple[str, str, str], Mapping[str, Any]],
    run_id: str,
) -> dict[str, Mapping[str, Any]]:
    source_objects: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows, start=2):
        record, response = _row_raw_response(row, raw_records)
        path = record["request"].get("path")
        if row["route_tier"] == "historical":
            allowed = {"/historical/markets", f"/historical/markets/{row['ticker']}"}
        else:
            allowed = {"/markets", f"/markets/{row['ticker']}"}
        if path not in allowed:
            raise HistoricalFeasibilityManifestValidationError(
                f"market row {index} raw path disagrees with canonical tier"
            )
        if path.endswith(row["ticker"]):
            market = response.payload.get("market")
            matches = [market] if isinstance(market, Mapping) else []
        else:
            markets = response.payload.get("markets")
            matches = [
                item for item in markets if isinstance(item, Mapping) and item.get("ticker") == row["ticker"]
            ] if isinstance(markets, list) else []
        if len(matches) != 1:
            raise HistoricalFeasibilityManifestValidationError(
                f"market row {index} does not map to exactly one raw market"
            )
        rebuilt = build_market_row(
            run_id=run_id,
            market=matches[0],
            category=row["category"],
            route_tier=row["route_tier"],
            response=response,
        )
        _compare_row(row, rebuilt, MARKET_FIELDS, f"market row {index}")
        source_objects[row["ticker"]] = matches[0]
    return source_objects


def _validate_windows_and_observations(
    rows: HistoricalFeasibilityRows,
    raw_records: Mapping[tuple[str, str, str], Mapping[str, Any]],
    *,
    market_source_objects: Mapping[str, Mapping[str, Any]],
    run_id: str,
) -> None:
    observations_by_raw: dict[tuple[str, str, str, str], list[Mapping[str, str]]] = {}
    for row in rows.observations:
        key = (row["ticker"], row["raw_source"], row["raw_session_id"], row["raw_request_id"])
        observations_by_raw.setdefault(key, []).append(row)

    event_series = {row["event_ticker"]: row["series_ticker"] for row in rows.events}
    for index, window in enumerate(rows.windows, start=2):
        record, response = _row_raw_response(window, raw_records)
        ticker = window["ticker"]
        path = record["request"].get("path")
        if window["route_tier"] == "historical":
            expected_path = f"/historical/markets/{ticker}/candlesticks"
        else:
            series = event_series[window["event_ticker"]]
            expected_path = f"/series/{series}/markets/{ticker}/candlesticks"
        if path != expected_path:
            raise HistoricalFeasibilityManifestValidationError(
                f"window row {index} candlestick raw path mismatch"
            )
        params = record["request"].get("params")
        if not isinstance(params, Mapping):
            raise HistoricalFeasibilityManifestValidationError(
                f"window row {index} raw params missing"
            )
        for key, value in (
            ("start_ts", int(window["request_start_ts"])),
            ("end_ts", int(window["request_end_ts"])),
            ("period_interval", 1),
        ):
            if params.get(key) != value:
                raise HistoricalFeasibilityManifestValidationError(
                    f"window row {index} raw param {key} mismatch"
                )
        if window["route_tier"] == "live" and str(params.get("include_latest_before_start")).lower() != "false":
            raise HistoricalFeasibilityManifestValidationError(
                f"window row {index} did not disable synthetic continuity"
            )

        market = market_source_objects[ticker]
        close = _parse_timestamp(market.get("close_time"), "market.close_time")
        rebuilt_obs = build_observation_rows(
            run_id=run_id,
            ticker=ticker,
            event_ticker=window["event_ticker"],
            category=window["category"],
            close_time=close,
            window_start_ts=int(window["window_start_ts"]),
            window_end_ts=int(window["window_end_ts"]),
            route_tier=window["route_tier"],
            response=response,
        )
        rebuilt_window = build_window_row(
            run_id=run_id,
            ticker=ticker,
            event_ticker=window["event_ticker"],
            category=window["category"],
            window_start_ts=int(window["window_start_ts"]),
            window_end_ts=int(window["window_end_ts"]),
            request_chunk_index=int(window["request_chunk_index"]),
            request_start_ts=int(window["request_start_ts"]),
            request_end_ts=int(window["request_end_ts"]),
            route_tier=window["route_tier"],
            response=response,
            observations=rebuilt_obs,
        )
        _compare_row(window, rebuilt_window, WINDOW_FIELDS, f"window row {index}")
        raw_key = (ticker, window["raw_source"], window["raw_session_id"], window["raw_request_id"])
        actual_obs = sorted(
            observations_by_raw.get(raw_key, []), key=lambda row: int(row["end_period_ts"])
        )
        if len(actual_obs) != len(rebuilt_obs):
            raise HistoricalFeasibilityManifestValidationError(
                f"window row {index} observation count differs from raw"
            )
        for offset, (actual, expected) in enumerate(zip(actual_obs, rebuilt_obs), start=1):
            _compare_row(actual, expected, OBSERVATION_FIELDS, f"window {index} observation {offset}")


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
        raise HistoricalFeasibilityManifestValidationError(f"unknown raw lineage key {key!r}")
    if record.get("error") is not None:
        raise HistoricalFeasibilityManifestValidationError(f"raw lineage key {key!r} is error record")
    request = record.get("request")
    response = record.get("response")
    if not isinstance(request, Mapping) or not isinstance(response, Mapping):
        raise HistoricalFeasibilityManifestValidationError(f"raw lineage key {key!r} malformed")
    if request.get("method") != "GET":
        raise HistoricalFeasibilityManifestValidationError(f"raw lineage key {key!r} is not GET")
    status = response.get("status_code")
    if not isinstance(status, int) or not 200 <= status < 300:
        raise HistoricalFeasibilityManifestValidationError(f"raw lineage key {key!r} is not HTTP success")
    if response.get("json_parse_error") is not None:
        raise HistoricalFeasibilityManifestValidationError(f"raw lineage key {key!r} has JSON parse error")
    return record


def _payload(record: Mapping[str, Any]) -> dict[str, Any]:
    body = record["response"].get("body_text")
    if not isinstance(body, str):
        raise HistoricalFeasibilityManifestValidationError("raw body_text must be text")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HistoricalFeasibilityManifestValidationError(f"raw body is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HistoricalFeasibilityManifestValidationError("raw top-level JSON must be object")
    return payload


def _load_raw_records(
    manifest: Mapping[str, Any], repository_root: Path
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
                        raise HistoricalFeasibilityManifestValidationError(
                            f"duplicate raw key at {raw_path}:{line_number}: {key!r}"
                        )
                    records[key] = record
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise HistoricalFeasibilityManifestValidationError(
                f"could not index raw file {raw_path}: {exc}"
            ) from exc
    if not records:
        raise HistoricalFeasibilityManifestValidationError("manifest contains no raw API records")
    return records


def _find_table_csvs(
    manifest: Mapping[str, Any], repository_root: Path, run_id: str
) -> dict[str, Path]:
    allowed = {"events", "markets", "windows", "observations", "category_summary"}
    found: dict[str, Path] = {}
    for descriptor in manifest.get("files", []):
        if not isinstance(descriptor, Mapping) or descriptor.get("role") != "derived_csv":
            continue
        path = _resolve_path(descriptor.get("path"), repository_root)
        prefix = f"{run_id}_"
        if not path.name.startswith(prefix) or not path.name.endswith(".csv"):
            raise HistoricalFeasibilityManifestValidationError(
                f"unexpected derived CSV name {path.name!r}"
            )
        table = path.name[len(prefix):-4]
        if table not in allowed:
            raise HistoricalFeasibilityManifestValidationError(
                f"unexpected feasibility derived table {table!r}"
            )
        if table in found:
            raise HistoricalFeasibilityManifestValidationError(f"duplicate derived table {table!r}")
        found[table] = path
    missing = allowed - set(found)
    if missing:
        raise HistoricalFeasibilityManifestValidationError(
            f"manifest missing derived tables: {sorted(missing)}"
        )
    return found


def _read_csv(path: Path, fields: Sequence[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(fields):
                raise HistoricalFeasibilityManifestValidationError(
                    f"unexpected CSV columns in {path}: {reader.fieldnames!r}"
                )
            rows = [dict(row) for row in reader]
    except (OSError, csv.Error) as exc:
        raise HistoricalFeasibilityManifestValidationError(f"could not read CSV {path}: {exc}") from exc
    for row in rows:
        if "result" in row:
            raise HistoricalFeasibilityManifestValidationError("outcome column leaked into feasibility CSV")
    return rows


def _compare_row(
    actual: Mapping[str, str], expected: Mapping[str, str], fields: Sequence[str], label: str
) -> None:
    for field in fields:
        if actual.get(field) != expected.get(field):
            raise HistoricalFeasibilityManifestValidationError(
                f"{label} field {field!r} differs from raw evidence"
            )


def _resolve_path(spec: Any, repository_root: Path) -> Path:
    if not isinstance(spec, Mapping):
        raise HistoricalFeasibilityManifestValidationError("manifest path descriptor must be object")
    kind = spec.get("kind")
    value = spec.get("value")
    if not isinstance(value, str) or not value:
        raise HistoricalFeasibilityManifestValidationError("manifest path value must be text")
    if kind == "absolute":
        return Path(value)
    if kind == "repository_relative":
        candidate = (repository_root / value).resolve()
        try:
            candidate.relative_to(repository_root)
        except ValueError as exc:
            raise HistoricalFeasibilityManifestValidationError("repository-relative path escapes root") from exc
        return candidate
    raise HistoricalFeasibilityManifestValidationError(f"unsupported manifest path kind {kind!r}")


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HistoricalFeasibilityManifestValidationError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HistoricalFeasibilityManifestValidationError(f"{label} must be JSON object")
    return value


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise HistoricalFeasibilityManifestValidationError(f"{field} must be non-empty text")
    return value


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise HistoricalFeasibilityManifestValidationError(f"{field} must be timestamp text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoricalFeasibilityManifestValidationError(f"{field} invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise HistoricalFeasibilityManifestValidationError(f"{field} must include timezone")
    return parsed


def _optional_timestamp(value: Any, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    return _parse_timestamp(value, field)
