"""Outcome-blind quote-age and missingness pilot for Kalshi Sports history.

This module intentionally reads only the derived Events, Markets, and Anchors
CSV tables from a previously validated ``collect_sports_historical`` manifest.
It never opens raw HTTP archives, candle CSVs, trade CSVs, or outcome data.

The threshold decision rule is predeclared in code so it cannot be adjusted
after seeing final YES/NO outcomes (which are not available to this module).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .sports_historical_schema import ANCHOR_DAYS, ANCHOR_FIELDS, EVENT_FIELDS, MARKET_FIELDS

PILOT_SCHEMA_VERSION = "sports_staleness_pilot.v1"
CANDIDATE_THRESHOLDS_SECONDS = (60, 300, 900, 1800, 3600)
OVERALL_QUOTE_RETENTION_GATE = 0.90
PER_ANCHOR_QUOTE_RETENTION_GATE = 0.80
FREEZE_MIN_UNIQUE_EVENTS = 100


class SportsStalenessPilotError(RuntimeError):
    """Raised when an outcome-blind staleness pilot cannot be trusted."""


@dataclass(frozen=True)
class PilotInput:
    manifest_path: Path
    run_id: str
    anchor_lookback_hours: int
    events_path: Path
    markets_path: Path
    anchors_path: Path


@dataclass(frozen=True)
class PilotResult:
    report: dict[str, Any]
    threshold_rows: tuple[dict[str, str], ...]


def analyze_staleness_manifest(
    manifest_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> PilotResult:
    """Analyze quote age and missingness without opening outcomes or raw payloads."""

    pilot_input = _load_pilot_input(manifest_path, repository_root=repository_root)
    events = _read_exact_csv(pilot_input.events_path, EVENT_FIELDS, "events")
    markets = _read_exact_csv(pilot_input.markets_path, MARKET_FIELDS, "markets")
    anchors = _read_exact_csv(pilot_input.anchors_path, ANCHOR_FIELDS, "anchors")

    run_id = pilot_input.run_id
    _require_run_id(events, run_id, "events")
    _require_run_id(markets, run_id, "markets")
    _require_run_id(anchors, run_id, "anchors")

    event_by_ticker = _validate_events(events)
    market_to_event = _validate_markets(markets, event_by_ticker)
    anchor_rows = _validate_anchors(
        anchors,
        market_to_event=market_to_event,
        lookback_seconds=pilot_input.anchor_lookback_hours * 3600,
    )

    quote_ages = [item["quote_age_seconds"] for item in anchor_rows if item["quote_age_seconds"] is not None]
    total_anchors = len(anchor_rows)
    quote_anchor_count = len(quote_ages)
    missing_anchor_count = total_anchors - quote_anchor_count

    by_anchor: dict[str, dict[str, Any]] = {}
    for anchor_name in ANCHOR_DAYS:
        group = [item for item in anchor_rows if item["anchor_name"] == anchor_name]
        ages = [item["quote_age_seconds"] for item in group if item["quote_age_seconds"] is not None]
        by_anchor[anchor_name] = {
            "anchor_rows": len(group),
            "quote_anchor_rows": len(ages),
            "missing_quote_anchor_rows": len(group) - len(ages),
            "quote_availability_rate": _rate(len(ages), len(group)),
            "quote_age_seconds": _age_summary(ages),
        }

    threshold_rows: list[dict[str, str]] = []
    qualifying_thresholds: list[int] = []
    for threshold in CANDIDATE_THRESHOLDS_SECONDS:
        retained = [
            item
            for item in anchor_rows
            if item["quote_age_seconds"] is not None
            and item["quote_age_seconds"] <= threshold
        ]
        retained_quote = len(retained)
        overall_quote_retention = _rate(retained_quote, quote_anchor_count)
        total_anchor_retention = _rate(retained_quote, total_anchors)
        per_anchor_rates: dict[str, float | None] = {}
        per_anchor_counts: dict[str, int] = {}
        per_anchor_denominators: dict[str, int] = {}
        per_anchor_gate_pass = True
        for anchor_name in ANCHOR_DAYS:
            quote_group = [
                item
                for item in anchor_rows
                if item["anchor_name"] == anchor_name
                and item["quote_age_seconds"] is not None
            ]
            retained_group = [
                item for item in quote_group if item["quote_age_seconds"] <= threshold
            ]
            rate = _rate(len(retained_group), len(quote_group))
            per_anchor_rates[anchor_name] = rate
            per_anchor_counts[anchor_name] = len(retained_group)
            per_anchor_denominators[anchor_name] = len(quote_group)
            if rate is None or rate < PER_ANCHOR_QUOTE_RETENTION_GATE:
                per_anchor_gate_pass = False

        qualifies = (
            overall_quote_retention is not None
            and overall_quote_retention >= OVERALL_QUOTE_RETENTION_GATE
            and per_anchor_gate_pass
        )
        if qualifies:
            qualifying_thresholds.append(threshold)

        retained_events = {item["event_ticker"] for item in retained}
        threshold_rows.append(
            {
                "threshold_seconds": str(threshold),
                "threshold_label": _threshold_label(threshold),
                "retained_quote_anchors": str(retained_quote),
                "quote_anchor_denominator": str(quote_anchor_count),
                "quote_anchor_retention_rate": _format_rate(overall_quote_retention),
                "total_anchor_denominator": str(total_anchors),
                "total_anchor_retention_rate": _format_rate(total_anchor_retention),
                "retained_unique_events": str(len(retained_events)),
                "7d_quote_retention_rate": _format_rate(per_anchor_rates["7d"]),
                "3d_quote_retention_rate": _format_rate(per_anchor_rates["3d"]),
                "1d_quote_retention_rate": _format_rate(per_anchor_rates["1d"]),
                "qualifies_retention_rule": "true" if qualifies else "false",
            }
        )

    candidate_threshold = min(qualifying_thresholds) if qualifying_thresholds else None
    unique_events = len(event_by_ticker)
    if candidate_threshold is None:
        recommendation_status = "blocked_no_freshness_candidate_meets_retention_gates"
        freeze_eligible = False
    elif unique_events < FREEZE_MIN_UNIQUE_EVENTS:
        recommendation_status = "preliminary_sample_too_small"
        freeze_eligible = False
    else:
        recommendation_status = "freeze_candidate_available"
        freeze_eligible = True

    report = {
        "schema_version": PILOT_SCHEMA_VERSION,
        "input_manifest": _portable_manifest_path(pilot_input.manifest_path, Path(repository_root)),
        "input_run_id": run_id,
        "analysis_scope": {
            "outcome_blind": True,
            "opened_tables": ["events", "markets", "anchors"],
            "raw_http_opened": False,
            "candles_opened": False,
            "trades_opened": False,
            "outcomes_opened": False,
            "calibration_run": False,
        },
        "predeclared_rule": {
            "candidate_thresholds_seconds": list(CANDIDATE_THRESHOLDS_SECONDS),
            "overall_quote_retention_gate": OVERALL_QUOTE_RETENTION_GATE,
            "per_anchor_quote_retention_gate": PER_ANCHOR_QUOTE_RETENTION_GATE,
            "freeze_min_unique_events": FREEZE_MIN_UNIQUE_EVENTS,
            "maximum_candidate_seconds": max(CANDIDATE_THRESHOLDS_SECONDS),
            "selection": "smallest candidate meeting overall and every-anchor quote-retention gates",
        },
        "sample": {
            "unique_events": unique_events,
            "markets": len(market_to_event),
            "anchors": total_anchors,
            "quote_anchors": quote_anchor_count,
            "missing_quote_anchors": missing_anchor_count,
            "quote_availability_rate": _rate(quote_anchor_count, total_anchors),
            "anchor_lookback_hours": pilot_input.anchor_lookback_hours,
        },
        "quote_age_seconds": _age_summary(quote_ages),
        "by_anchor": by_anchor,
        "recommendation": {
            "status": recommendation_status,
            "candidate_threshold_seconds": candidate_threshold,
            "candidate_threshold_label": (
                None if candidate_threshold is None else _threshold_label(candidate_threshold)
            ),
            "freeze_eligible": freeze_eligible,
            "threshold_frozen": False,
            "reason": _recommendation_reason(
                recommendation_status,
                unique_events=unique_events,
                candidate_threshold=candidate_threshold,
            ),
        },
    }
    return PilotResult(report=report, threshold_rows=tuple(threshold_rows))


def write_staleness_report(
    result: PilotResult,
    *,
    output_root: str | Path = "data/derived/sports_staleness",
) -> tuple[Path, Path]:
    """Write a JSON report plus threshold-comparison CSV atomically enough for offline research."""

    run_id = str(result.report.get("input_run_id", ""))
    if not run_id:
        raise SportsStalenessPilotError("pilot report is missing input_run_id")
    output_dir = Path(output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{run_id}_staleness_pilot.json"
    csv_path = output_dir / f"{run_id}_staleness_thresholds.csv"

    _write_text_atomic(json_path, json.dumps(result.report, indent=2, sort_keys=True) + "\n")
    fields = (
        "threshold_seconds",
        "threshold_label",
        "retained_quote_anchors",
        "quote_anchor_denominator",
        "quote_anchor_retention_rate",
        "total_anchor_denominator",
        "total_anchor_retention_rate",
        "retained_unique_events",
        "7d_quote_retention_rate",
        "3d_quote_retention_rate",
        "1d_quote_retention_rate",
        "qualifies_retention_rule",
    )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temp = csv_path.with_name(f".{csv_path.name}.tmp")
    try:
        with temp.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fields))
            writer.writeheader()
            for row in result.threshold_rows:
                writer.writerow(row)
            handle.flush()
        temp.replace(csv_path)
    except (OSError, csv.Error) as exc:
        temp.unlink(missing_ok=True)
        raise SportsStalenessPilotError(f"could not write threshold CSV: {exc}") from exc
    return json_path, csv_path


def _load_pilot_input(
    manifest_path: str | Path,
    *,
    repository_root: str | Path,
) -> PilotInput:
    path = Path(manifest_path).resolve()
    repo_root = Path(repository_root).resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SportsStalenessPilotError(f"could not read manifest {path}: {exc}") from exc
    if not isinstance(manifest, Mapping):
        raise SportsStalenessPilotError("manifest must be a JSON object")
    collector = manifest.get("collector")
    if not isinstance(collector, Mapping) or collector.get("name") != "collect_sports_historical":
        raise SportsStalenessPilotError("manifest is not for collect_sports_historical")
    if manifest.get("status") != "completed":
        raise SportsStalenessPilotError("staleness pilot requires a completed collection manifest")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise SportsStalenessPilotError("manifest run_id is missing")
    result = manifest.get("result")
    if not isinstance(result, Mapping):
        raise SportsStalenessPilotError("manifest result must be an object")
    if result.get("outcomes_materialized") is not False:
        raise SportsStalenessPilotError("pilot requires outcomes_materialized=false")
    if result.get("calibration_run") is not False:
        raise SportsStalenessPilotError("pilot requires calibration_run=false")
    if result.get("staleness_threshold_frozen") is not False:
        raise SportsStalenessPilotError("pilot requires staleness_threshold_frozen=false")
    arguments = manifest.get("arguments")
    if not isinstance(arguments, Mapping):
        raise SportsStalenessPilotError("manifest arguments must be an object")
    lookback = arguments.get("anchor_lookback_hours")
    if not isinstance(lookback, int) or isinstance(lookback, bool) or not 1 <= lookback <= 48:
        raise SportsStalenessPilotError("manifest anchor_lookback_hours is invalid")

    tables: dict[str, Path] = {}
    for descriptor in manifest.get("files", []):
        if not isinstance(descriptor, Mapping) or descriptor.get("role") != "derived_csv":
            continue
        path_spec = descriptor.get("path")
        if not isinstance(path_spec, Mapping):
            continue
        candidate = _resolve_stored_path(path_spec, repo_root)
        name = candidate.name
        for table in ("events", "markets", "anchors"):
            expected_suffix = f"_{table}.csv"
            if name == f"{run_id}{expected_suffix}":
                if table in tables:
                    raise SportsStalenessPilotError(f"duplicate {table} CSV descriptor")
                tables[table] = candidate

    missing = {"events", "markets", "anchors"} - set(tables)
    if missing:
        raise SportsStalenessPilotError(f"manifest is missing pilot-safe CSVs: {sorted(missing)}")

    return PilotInput(
        manifest_path=path,
        run_id=run_id,
        anchor_lookback_hours=lookback,
        events_path=tables["events"],
        markets_path=tables["markets"],
        anchors_path=tables["anchors"],
    )


def _read_exact_csv(path: Path, fields: Sequence[str], table: str) -> list[dict[str, str]]:
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(fields):
                raise SportsStalenessPilotError(
                    f"{table} CSV columns differ from frozen schema: {reader.fieldnames!r}"
                )
            return [dict(row) for row in reader]
    except (OSError, csv.Error) as exc:
        raise SportsStalenessPilotError(f"could not read {table} CSV {path}: {exc}") from exc


def _require_run_id(rows: Iterable[Mapping[str, str]], run_id: str, table: str) -> None:
    for index, row in enumerate(rows, start=2):
        if row.get("run_id") != run_id:
            raise SportsStalenessPilotError(f"{table} row {index} run_id mismatch")


def _validate_events(rows: Sequence[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    result: dict[str, Mapping[str, str]] = {}
    for row in rows:
        ticker = row.get("event_ticker", "")
        if not ticker or ticker in result:
            raise SportsStalenessPilotError("events table has blank or duplicate event_ticker")
        if row.get("category") != "Sports":
            raise SportsStalenessPilotError(f"event {ticker!r} is not Sports")
        result[ticker] = row
    if not result:
        raise SportsStalenessPilotError("events table is empty")
    return result


def _validate_markets(
    rows: Sequence[Mapping[str, str]],
    events: Mapping[str, Mapping[str, str]],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        ticker = row.get("ticker", "")
        event_ticker = row.get("event_ticker", "")
        if not ticker or ticker in result:
            raise SportsStalenessPilotError("markets table has blank or duplicate ticker")
        if event_ticker not in events:
            raise SportsStalenessPilotError(f"market {ticker!r} references unknown event")
        if row.get("market_type") != "binary" or row.get("status") != "finalized":
            raise SportsStalenessPilotError(f"market {ticker!r} is outside baseline contract")
        result[ticker] = event_ticker
    if not result:
        raise SportsStalenessPilotError("markets table is empty")
    return result


def _validate_anchors(
    rows: Sequence[Mapping[str, str]],
    *,
    market_to_event: Mapping[str, str],
    lookback_seconds: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        ticker = row.get("ticker", "")
        anchor_name = row.get("anchor_name", "")
        key = (ticker, anchor_name)
        if ticker not in market_to_event:
            raise SportsStalenessPilotError(f"anchor references unknown market {ticker!r}")
        if anchor_name not in ANCHOR_DAYS or key in seen:
            raise SportsStalenessPilotError(f"invalid or duplicate anchor {key!r}")
        seen.add(key)
        quote_pair_count = _nonnegative_int(row.get("quote_pair_count"), "quote_pair_count")
        age_text = row.get("latest_quote_age_seconds", "")
        if quote_pair_count == 0:
            if age_text:
                raise SportsStalenessPilotError(f"anchor {key!r} has age but zero quote_pair_count")
            age = None
        else:
            age = _nonnegative_int(age_text, "latest_quote_age_seconds")
            if age > lookback_seconds:
                raise SportsStalenessPilotError(
                    f"anchor {key!r} quote age exceeds the engineering lookback window"
                )
        result.append(
            {
                "ticker": ticker,
                "event_ticker": market_to_event[ticker],
                "anchor_name": anchor_name,
                "quote_age_seconds": age,
            }
        )

    expected = {(ticker, anchor) for ticker in market_to_event for anchor in ANCHOR_DAYS}
    if seen != expected:
        missing = sorted(expected - seen)[:5]
        extra = sorted(seen - expected)[:5]
        raise SportsStalenessPilotError(
            f"anchor set does not equal three predeclared anchors per market; missing={missing!r}, extra={extra!r}"
        )
    return result


def _age_summary(values: Sequence[int]) -> dict[str, int | None]:
    if not values:
        return {"count": 0, "min": None, "p50": None, "p75": None, "p90": None, "p95": None, "max": None}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "p50": _nearest_rank(ordered, 0.50),
        "p75": _nearest_rank(ordered, 0.75),
        "p90": _nearest_rank(ordered, 0.90),
        "p95": _nearest_rank(ordered, 0.95),
        "max": ordered[-1],
    }


def _nearest_rank(ordered: Sequence[int], probability: float) -> int:
    rank = max(1, math.ceil(probability * len(ordered)))
    return ordered[rank - 1]


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _format_rate(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def _threshold_label(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    return f"{seconds // 60}m"


def _recommendation_reason(status: str, *, unique_events: int, candidate_threshold: int | None) -> str:
    if status == "blocked_no_freshness_candidate_meets_retention_gates":
        return "No candidate at or below 1h retains enough quote-bearing anchors overall and within every horizon."
    if status == "preliminary_sample_too_small":
        return (
            f"The smallest retention-qualified candidate is {_threshold_label(candidate_threshold or 0)}, "
            f"but only {unique_events} unique events are present; at least {FREEZE_MIN_UNIQUE_EVENTS} are required before freezing."
        )
    if status == "freeze_candidate_available":
        return (
            f"{_threshold_label(candidate_threshold or 0)} is the smallest predeclared candidate meeting all retention gates, "
            f"and the sample contains at least {FREEZE_MIN_UNIQUE_EVENTS} unique events."
        )
    raise AssertionError(status)


def _nonnegative_int(value: Any, field: str) -> int:
    if not isinstance(value, str) or not value:
        raise SportsStalenessPilotError(f"{field} must be non-empty integer text")
    try:
        parsed = int(value)
    except ValueError as exc:
        raise SportsStalenessPilotError(f"{field} must be integer text") from exc
    if parsed < 0:
        raise SportsStalenessPilotError(f"{field} must be nonnegative")
    return parsed


def _resolve_stored_path(path_spec: Mapping[str, Any], repo_root: Path) -> Path:
    kind = path_spec.get("kind")
    value = path_spec.get("value")
    if not isinstance(value, str) or not value:
        raise SportsStalenessPilotError("manifest path value must be non-empty text")
    if kind == "repository_relative":
        candidate = (repo_root / value).resolve()
        try:
            candidate.relative_to(repo_root)
        except ValueError as exc:
            raise SportsStalenessPilotError("manifest repository-relative path escapes repository") from exc
        return candidate
    if kind == "absolute":
        return Path(value).resolve()
    raise SportsStalenessPilotError(f"unsupported manifest path kind {kind!r}")


def _portable_manifest_path(path: Path, repo_root: Path) -> dict[str, str]:
    resolved_root = repo_root.resolve()
    try:
        relative = path.resolve().relative_to(resolved_root)
    except ValueError:
        return {"kind": "absolute", "value": str(path.resolve())}
    return {"kind": "repository_relative", "value": relative.as_posix()}


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(text, encoding="utf-8", newline="\n")
        temp.replace(path)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise SportsStalenessPilotError(f"could not write report {path}: {exc}") from exc
