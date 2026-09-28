"""Outcome-blind heterogeneity profiling for Sports Calibration V2.

The profiler intentionally uses only the already-derived identity and quote
availability tables. It never parses final market outcomes and it does not
estimate calibration or profitability.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import csv
import json
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from .historical_feasibility_manifest_validation import (
    HistoricalFeasibilityManifestValidationError,
    validate_historical_feasibility_manifest,
)
from .historical_feasibility_schema import EVENT_FIELDS, MARKET_FIELDS, OBSERVATION_FIELDS

SPORTS_V2_HETEROGENEITY_SCHEMA_VERSION = "sports_v2_heterogeneity_profile.v1"
SPORTS_V2_TAXONOMY_VERSION = "sports_v2_ticker_taxonomy.v1"
VALID_TIME_BANDS = ("early_5d_to_7d", "middle_3d_to_5d", "late_1d_to_3d")


class SportsV2HeterogeneityError(RuntimeError):
    """Raised when outcome-blind subgroup profiling cannot be trusted."""


# Classification is deliberately source-ticker only. High-confidence tokens are
# frozen before the 100-event profile is inspected. Ambiguous/unseen series stay
# unclassified instead of being guessed from external knowledge.
SPORT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("MLB", ("MLB",)),
    ("NBA", ("NBA",)),
    ("NFL", ("NFL",)),
    ("NHL", ("NHL",)),
    ("College Basketball", ("NCAAB", "CBB", "MARCHMADNESS")),
    ("College Football", ("NCAAF", "CFB")),
    ("Soccer", ("SOCCER", "FIFA", "EPL", "UCL", "MLS", "WORLD CUP", "WORLDCUP")),
    ("Combat Sports", ("UFC", "MMA", "BOXING", "BOX")),
    ("Golf", ("GOLF",)),
    ("Tennis", ("TENNIS", "ATP", "WTA")),
    ("Motorsports", ("NASCAR", "FORMULA1", "F1")),
)

PRODUCT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("debut_or_first_appearance", ("DEBUT", "FIRSTAPPEAR", "FIRSTPLAY")),
    ("team_destination_or_roster", ("NEXTTEAM", "TEAMANNOUNCE", "TRADE", "SIGNWITH")),
    ("coach_or_manager_status", ("COACH", "MANAGER")),
    ("retirement", ("RETIRE",)),
    ("championship_or_title_future", ("CHAMP", "3PEAT", "MAJOR", "TITLE")),
    ("record_or_milestone", ("RECORD", "PTREC", "MILESTONE")),
    ("appearance_or_scheduling", ("FIGHTNEXT", "PLAYNEXT", "STARTNEXT")),
)


def classify_series_ticker(series_ticker: str) -> dict[str, str]:
    ticker = _required_text(series_ticker, "series_ticker").upper()
    sport_matches = [label for label, tokens in SPORT_RULES if _contains_any(ticker, tokens)]
    if len(sport_matches) == 1:
        sport_group = sport_matches[0]
        sport_confidence = "high"
    elif len(sport_matches) > 1:
        sport_group = "Ambiguous"
        sport_confidence = "ambiguous"
    else:
        sport_group = "Other/Unclassified"
        sport_confidence = "unclassified"

    product_matches = [label for label, tokens in PRODUCT_RULES if _contains_any(ticker, tokens)]
    if len(product_matches) == 1:
        product_family = product_matches[0]
        product_confidence = "high"
    elif len(product_matches) > 1:
        product_family = "ambiguous_product_family"
        product_confidence = "ambiguous"
    else:
        product_family = "other_or_unclassified_product_family"
        product_confidence = "unclassified"

    return {
        "taxonomy_version": SPORTS_V2_TAXONOMY_VERSION,
        "sport_group": sport_group,
        "sport_classification_confidence": sport_confidence,
        "product_family": product_family,
        "product_classification_confidence": product_confidence,
    }


def build_heterogeneity_profile(
    events: Sequence[Mapping[str, str]],
    markets: Sequence[Mapping[str, str]],
    observations: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Build deterministic subgroup summaries from outcome-blind tables."""

    _reject_outcomes((events, markets, observations))
    if any(row.get("category") != "Sports" for row in events):
        raise SportsV2HeterogeneityError("heterogeneity profile requires Sports event rows only")
    if any(row.get("category") != "Sports" for row in markets):
        raise SportsV2HeterogeneityError("heterogeneity profile requires Sports market rows only")
    if any(row.get("category") != "Sports" for row in observations):
        raise SportsV2HeterogeneityError("heterogeneity profile requires Sports observation rows only")

    event_by_ticker: dict[str, Mapping[str, str]] = {}
    event_map: list[dict[str, str]] = []
    for row in events:
        event_ticker = _required_text(row.get("event_ticker"), "event.event_ticker")
        if event_ticker in event_by_ticker:
            raise SportsV2HeterogeneityError(f"duplicate event_ticker {event_ticker}")
        series = _required_text(row.get("series_ticker"), "event.series_ticker")
        classification = classify_series_ticker(series)
        event_by_ticker[event_ticker] = row
        event_map.append(
            {
                "event_ticker": event_ticker,
                "series_ticker": series,
                **classification,
            }
        )

    market_events: dict[str, str] = {}
    market_count_by_event: Counter[str] = Counter()
    for row in markets:
        ticker = _required_text(row.get("ticker"), "market.ticker")
        event_ticker = _required_text(row.get("event_ticker"), "market.event_ticker")
        if event_ticker not in event_by_ticker:
            raise SportsV2HeterogeneityError(f"market references unknown event {event_ticker}")
        if ticker in market_events and market_events[ticker] != event_ticker:
            raise SportsV2HeterogeneityError(f"market {ticker} maps to multiple events")
        market_events[ticker] = event_ticker
        market_count_by_event[event_ticker] += 1

    valid_obs_by_event: Counter[str] = Counter()
    valid_obs_by_market: Counter[str] = Counter()
    bands_by_event: dict[str, set[str]] = defaultdict(set)
    for row in observations:
        event_ticker = _required_text(row.get("event_ticker"), "observation.event_ticker")
        ticker = _required_text(row.get("ticker"), "observation.ticker")
        if event_ticker not in event_by_ticker:
            raise SportsV2HeterogeneityError(f"observation references unknown event {event_ticker}")
        if market_events.get(ticker) != event_ticker:
            raise SportsV2HeterogeneityError(
                f"observation market/event mismatch for {ticker}/{event_ticker}"
            )
        if row.get("valid_quote_observation") != "true":
            continue
        valid_obs_by_event[event_ticker] += 1
        valid_obs_by_market[ticker] += 1
        band = row.get("time_band", "")
        if band in VALID_TIME_BANDS:
            bands_by_event[event_ticker].add(band)

    class_by_event = {row["event_ticker"]: row for row in event_map}
    sport_summary = _summaries_for_dimension(
        events=events,
        market_count_by_event=market_count_by_event,
        valid_obs_by_event=valid_obs_by_event,
        bands_by_event=bands_by_event,
        class_by_event=class_by_event,
        dimension="sport_group",
    )
    product_summary = _summaries_for_dimension(
        events=events,
        market_count_by_event=market_count_by_event,
        valid_obs_by_event=valid_obs_by_event,
        bands_by_event=bands_by_event,
        class_by_event=class_by_event,
        dimension="product_family",
    )
    cross_summary = _summaries_for_cross(
        events=events,
        market_count_by_event=market_count_by_event,
        valid_obs_by_event=valid_obs_by_event,
        bands_by_event=bands_by_event,
        class_by_event=class_by_event,
    )

    total_events = len(events)
    high_sport_events = sum(
        1 for row in event_map if row["sport_classification_confidence"] == "high"
    )
    high_product_events = sum(
        1 for row in event_map if row["product_classification_confidence"] == "high"
    )
    return {
        "schema_version": SPORTS_V2_HETEROGENEITY_SCHEMA_VERSION,
        "taxonomy_version": SPORTS_V2_TAXONOMY_VERSION,
        "scope": "descriptive_pre_outcome",
        "event_count": total_events,
        "market_count": len(markets),
        "valid_quote_observation_count": sum(valid_obs_by_event.values()),
        "high_confidence_sport_event_count": high_sport_events,
        "high_confidence_sport_event_share": _share(high_sport_events, total_events),
        "high_confidence_product_event_count": high_product_events,
        "high_confidence_product_event_share": _share(high_product_events, total_events),
        "event_map": sorted(event_map, key=lambda row: row["event_ticker"]),
        "sport_group_summary": sport_summary,
        "product_family_summary": product_summary,
        "sport_product_summary": cross_summary,
        "outcomes_materialized": False,
        "calibration_analysis_run": False,
        "profitability_analysis_run": False,
        "general_sports_conclusion_authorized": False,
    }


def build_report_from_manifest(
    manifest_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    repo_root = Path(repository_root).resolve()
    validated = validate_historical_feasibility_manifest(manifest_path, repository_root=repo_root)
    if validated.get("collector_name") != "collect_sports_v2_scalability":
        raise SportsV2HeterogeneityError("source manifest is not a Sports V2 scalability run")
    if validated.get("outcomes_materialized") is not False:
        raise SportsV2HeterogeneityError("source manifest must be outcome-blind")

    manifest = _load_json(manifest_path)
    paths = _find_source_csvs(manifest, repo_root, validated["run_id"])
    events = _read_csv(paths["events"], EVENT_FIELDS)
    markets = _read_csv(paths["markets"], MARKET_FIELDS)
    observations = _read_csv(paths["observations"], OBSERVATION_FIELDS)
    profile = build_heterogeneity_profile(events, markets, observations)
    return {
        **profile,
        "source_run_id": validated["run_id"],
        "source_manifest": _portable_path(manifest_path, repo_root),
        "source_manifest_sha256": _sha256_file(manifest_path),
        "source_manifest_validation": "PASS",
    }


def write_profile_artifacts(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> dict[str, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_id = _required_text(report.get("source_run_id"), "report.source_run_id")
    json_path = out / f"{run_id}_sports_v2_heterogeneity.json"
    event_map_path = out / f"{run_id}_sports_v2_event_subgroups.csv"
    sport_path = out / f"{run_id}_sports_v2_sport_groups.csv"
    product_path = out / f"{run_id}_sports_v2_product_families.csv"
    cross_path = out / f"{run_id}_sports_v2_sport_product_groups.csv"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(event_map_path, report["event_map"])
    _write_csv(sport_path, report["sport_group_summary"])
    _write_csv(product_path, report["product_family_summary"])
    _write_csv(cross_path, report["sport_product_summary"])
    return {
        "report": json_path,
        "event_map": event_map_path,
        "sport_groups": sport_path,
        "product_families": product_path,
        "sport_product_groups": cross_path,
    }


def validate_profile_report(
    report_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    report_path = Path(report_path)
    report = _load_json(report_path)
    if report.get("schema_version") != SPORTS_V2_HETEROGENEITY_SCHEMA_VERSION:
        raise SportsV2HeterogeneityError("heterogeneity report schema version mismatch")
    manifest_path = _resolve_path(report.get("source_manifest"), Path(repository_root).resolve())
    expected_hash = _required_text(report.get("source_manifest_sha256"), "source_manifest_sha256")
    if _sha256_file(manifest_path) != expected_hash:
        raise SportsV2HeterogeneityError("source manifest hash differs from heterogeneity report")
    rebuilt = build_report_from_manifest(manifest_path, repository_root=repository_root)
    if rebuilt != report:
        raise SportsV2HeterogeneityError("heterogeneity report does not deterministically rebuild")
    return report


def _summaries_for_dimension(
    *,
    events: Sequence[Mapping[str, str]],
    market_count_by_event: Mapping[str, int],
    valid_obs_by_event: Mapping[str, int],
    bands_by_event: Mapping[str, set[str]],
    class_by_event: Mapping[str, Mapping[str, str]],
    dimension: str,
) -> list[dict[str, str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for event in events:
        event_ticker = event["event_ticker"]
        groups[class_by_event[event_ticker][dimension]].append(event_ticker)
    rows = []
    for label in sorted(groups):
        rows.append(
            _summary_row(
                group_type=dimension,
                group_label=label,
                event_tickers=groups[label],
                events=events,
                market_count_by_event=market_count_by_event,
                valid_obs_by_event=valid_obs_by_event,
                bands_by_event=bands_by_event,
            )
        )
    return sorted(rows, key=lambda row: (-int(row["event_count"]), row["group_label"]))


def _summaries_for_cross(
    *,
    events: Sequence[Mapping[str, str]],
    market_count_by_event: Mapping[str, int],
    valid_obs_by_event: Mapping[str, int],
    bands_by_event: Mapping[str, set[str]],
    class_by_event: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for event in events:
        event_ticker = event["event_ticker"]
        row = class_by_event[event_ticker]
        groups[(row["sport_group"], row["product_family"])].append(event_ticker)
    rows = []
    for (sport, product), tickers in sorted(groups.items()):
        rows.append(
            {
                **_summary_row(
                    group_type="sport_x_product",
                    group_label=f"{sport} | {product}",
                    event_tickers=tickers,
                    events=events,
                    market_count_by_event=market_count_by_event,
                    valid_obs_by_event=valid_obs_by_event,
                    bands_by_event=bands_by_event,
                ),
                "sport_group": sport,
                "product_family": product,
            }
        )
    return sorted(rows, key=lambda row: (-int(row["event_count"]), row["group_label"]))


def _summary_row(
    *,
    group_type: str,
    group_label: str,
    event_tickers: Sequence[str],
    events: Sequence[Mapping[str, str]],
    market_count_by_event: Mapping[str, int],
    valid_obs_by_event: Mapping[str, int],
    bands_by_event: Mapping[str, set[str]],
) -> dict[str, str]:
    event_set = set(event_tickers)
    series = {row["series_ticker"] for row in events if row["event_ticker"] in event_set}
    event_count = len(event_tickers)
    obs_counts = [int(valid_obs_by_event.get(event, 0)) for event in event_tickers]
    valid_event_count = sum(1 for count in obs_counts if count > 0)
    total_obs = sum(obs_counts)
    max_event_share = (max(obs_counts) / total_obs) if total_obs else 0.0
    top_n = max(1, (event_count + 9) // 10) if event_count else 0
    top_decile = (sum(sorted(obs_counts, reverse=True)[:top_n]) / total_obs) if total_obs else 0.0
    early = sum(1 for event in event_tickers if "early_5d_to_7d" in bands_by_event.get(event, set()))
    middle = sum(1 for event in event_tickers if "middle_3d_to_5d" in bands_by_event.get(event, set()))
    late = sum(1 for event in event_tickers if "late_1d_to_3d" in bands_by_event.get(event, set()))
    all_three = sum(1 for event in event_tickers if set(VALID_TIME_BANDS) <= bands_by_event.get(event, set()))
    return {
        "group_type": group_type,
        "group_label": group_label,
        "event_count": str(event_count),
        "unique_series_count": str(len(series)),
        "market_count": str(sum(int(market_count_by_event.get(event, 0)) for event in event_tickers)),
        "valid_quote_event_count": str(valid_event_count),
        "event_quote_coverage": _share(valid_event_count, event_count),
        "valid_quote_observation_count": str(total_obs),
        "median_valid_observations_per_event": _decimal_text(Decimal(str(median(obs_counts))) if obs_counts else Decimal(0)),
        "early_event_coverage": _share(early, event_count),
        "middle_event_coverage": _share(middle, event_count),
        "late_event_coverage": _share(late, event_count),
        "all_three_band_event_coverage": _share(all_three, event_count),
        "max_event_observation_share": _float_text(max_event_share),
        "top_decile_event_observation_share": _float_text(top_decile),
        "interpretation_scope": "descriptive_pre_outcome",
    }


def _contains_any(ticker: str, tokens: Iterable[str]) -> bool:
    compact = ticker.replace("-", "").replace("_", "").replace(" ", "")
    return any(token.replace(" ", "") in compact for token in tokens)


def _reject_outcomes(tables: Iterable[Sequence[Mapping[str, str]]]) -> None:
    for table in tables:
        for row in table:
            if "result" in row:
                raise SportsV2HeterogeneityError("forbidden outcome field 'result' in profile input")


def _find_source_csvs(manifest: Mapping[str, Any], repo_root: Path, run_id: str) -> dict[str, Path]:
    wanted = {"events", "markets", "observations"}
    found: dict[str, Path] = {}
    for descriptor in manifest.get("files", []):
        if not isinstance(descriptor, Mapping) or descriptor.get("role") != "derived_csv":
            continue
        path = _resolve_path(descriptor.get("path"), repo_root)
        prefix = f"{run_id}_"
        if not path.name.startswith(prefix) or not path.name.endswith(".csv"):
            continue
        table = path.name[len(prefix):-4]
        if table in wanted:
            found[table] = path
    missing = wanted - set(found)
    if missing:
        raise SportsV2HeterogeneityError(f"source manifest missing required tables: {sorted(missing)}")
    return found


def _read_csv(path: Path, fields: Sequence[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(fields):
                raise SportsV2HeterogeneityError(f"unexpected CSV columns in {path}")
            rows = [dict(row) for row in reader]
    except (OSError, csv.Error) as exc:
        raise SportsV2HeterogeneityError(f"could not read {path}: {exc}") from exc
    _reject_outcomes((rows,))
    return rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SportsV2HeterogeneityError(f"could not load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SportsV2HeterogeneityError(f"JSON {path} must contain an object")
    return value


def _resolve_path(value: object, repo_root: Path) -> Path:
    """Resolve canonical manifest path descriptors or portable report paths.

    Collection manifests store paths as structured ``{kind, value}`` objects,
    while the heterogeneity report stores its source-manifest reference as a
    portable string. Supporting both forms keeps the profiler aligned with
    the existing manifest contract without weakening path-escape checks.
    """
    if isinstance(value, Mapping):
        kind = value.get("kind")
        text = _required_text(value.get("value"), "path.value")
        if kind == "absolute":
            return Path(text).resolve()
        if kind == "repository_relative":
            path = (repo_root / text).resolve()
            try:
                path.relative_to(repo_root)
            except ValueError as exc:
                raise SportsV2HeterogeneityError(
                    "repository-relative path escapes repository root"
                ) from exc
            return path
        raise SportsV2HeterogeneityError(f"unsupported path kind {kind!r}")

    text = _required_text(value, "path")
    path = Path(text)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def _portable_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SportsV2HeterogeneityError(f"could not hash {path}: {exc}") from exc
    return digest.hexdigest()


def _share(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.000000"
    return _decimal_text(Decimal(numerator) / Decimal(denominator))


def _float_text(value: float) -> str:
    return _decimal_text(Decimal(str(value)))


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000")), "f")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SportsV2HeterogeneityError(f"{field} must be non-empty text")
    return value
