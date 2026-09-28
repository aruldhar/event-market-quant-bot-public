"""Outcome-blind heterogeneity profiling for the Checkpoint-09 Crypto branch.

The profiler uses only derived event/market identity and quote-availability rows
from an already validated historical-feasibility run. It never reads outcomes,
never estimates calibration, and never evaluates profitability.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import csv
import json
from statistics import median
from typing import Any, Mapping, Sequence

from .historical_feasibility_manifest_validation import validate_historical_feasibility_manifest
from .historical_feasibility_schema import EVENT_FIELDS, MARKET_FIELDS, OBSERVATION_FIELDS

CRYPTO_HETEROGENEITY_SCHEMA_VERSION = "crypto_heterogeneity_profile.v1"
CRYPTO_TAXONOMY_VERSION = "crypto_series_taxonomy.v1"
VALID_TIME_BANDS = ("early_5d_to_7d", "middle_3d_to_5d", "late_1d_to_3d")


class CryptoHeterogeneityError(RuntimeError):
    """Raised when outcome-blind Crypto heterogeneity profiling cannot be trusted."""


def classify_series_ticker(series_ticker: str) -> dict[str, str]:
    """Classify a Crypto series conservatively from source ticker text only.

    These labels are structural diagnostics, not claims that all members of a
    group share the same economic process.
    """

    ticker = _required_text(series_ticker, "series_ticker").upper().replace("-", "")

    # Asset/driver identity. Cross-asset must be checked before the BTC prefix.
    if ticker.startswith("KXBTCETH"):
        asset_group = "CrossAssetBTCETH"
        asset_confidence = "high"
    elif ticker.startswith("KXBTC"):
        asset_group = "Bitcoin"
        asset_confidence = "high"
    elif ticker.startswith("KXETH"):
        asset_group = "Ethereum"
        asset_confidence = "high"
    elif ticker.startswith("KXBNB"):
        asset_group = "BNB"
        asset_confidence = "high"
    elif ticker.startswith("KXZEC"):
        asset_group = "ZEC"
        asset_confidence = "high"
    elif ticker.startswith("KXFDV"):
        asset_group = "ProjectOrTokenSpecific"
        asset_confidence = "high"
    else:
        asset_group = "Other/Unclassified"
        asset_confidence = "unclassified"

    # Contract-template identity. Labels intentionally track source-ticker
    # structure rather than inferred settlement/economic semantics.
    template_matches: list[str] = []
    if ticker.startswith("KXFDV"):
        template_matches.append("fdv_family")
    if "MINY" in ticker or "MAXY" in ticker:
        template_matches.append("min_or_max_family")
    if "TOKENLAUNCH" in ticker or "MAINNET" in ticker or "DEPLOY" in ticker:
        template_matches.append("launch_or_deployment_family")
    if "VS" in ticker or "ATH" in ticker:
        template_matches.append("relative_or_ath_family")

    if len(template_matches) == 1:
        template_family = template_matches[0]
        template_confidence = "high"
    elif len(template_matches) > 1:
        template_family = "ambiguous_template_family"
        template_confidence = "ambiguous"
    else:
        template_family = "other_or_unclassified_template_family"
        template_confidence = "unclassified"

    return {
        "taxonomy_version": CRYPTO_TAXONOMY_VERSION,
        "asset_group": asset_group,
        "asset_classification_confidence": asset_confidence,
        "template_family": template_family,
        "template_classification_confidence": template_confidence,
    }


def build_crypto_heterogeneity_profile(
    events: Sequence[Mapping[str, str]],
    markets: Sequence[Mapping[str, str]],
    observations: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Build deterministic outcome-blind Crypto subgroup summaries."""

    _reject_outcomes((events, markets, observations))
    if any(row.get("category") != "Crypto" for row in events):
        raise CryptoHeterogeneityError("profile requires Crypto event rows only")
    if any(row.get("category") != "Crypto" for row in markets):
        raise CryptoHeterogeneityError("profile requires Crypto market rows only")
    if any(row.get("category") != "Crypto" for row in observations):
        raise CryptoHeterogeneityError("profile requires Crypto observation rows only")

    event_by_ticker: dict[str, Mapping[str, str]] = {}
    event_map: list[dict[str, str]] = []
    for row in events:
        event_ticker = _required_text(row.get("event_ticker"), "event.event_ticker")
        if event_ticker in event_by_ticker:
            raise CryptoHeterogeneityError(f"duplicate event_ticker {event_ticker}")
        series = _required_text(row.get("series_ticker"), "event.series_ticker")
        classification = classify_series_ticker(series)
        event_by_ticker[event_ticker] = row
        event_map.append({"event_ticker": event_ticker, "series_ticker": series, **classification})

    market_events: dict[str, str] = {}
    market_count_by_event: Counter[str] = Counter()
    for row in markets:
        ticker = _required_text(row.get("ticker"), "market.ticker")
        event_ticker = _required_text(row.get("event_ticker"), "market.event_ticker")
        if event_ticker not in event_by_ticker:
            raise CryptoHeterogeneityError(f"market references unknown event {event_ticker}")
        if ticker in market_events and market_events[ticker] != event_ticker:
            raise CryptoHeterogeneityError(f"market {ticker} maps to multiple events")
        market_events[ticker] = event_ticker
        market_count_by_event[event_ticker] += 1

    valid_obs_by_event: Counter[str] = Counter()
    bands_by_event: dict[str, set[str]] = defaultdict(set)
    for row in observations:
        event_ticker = _required_text(row.get("event_ticker"), "observation.event_ticker")
        ticker = _required_text(row.get("ticker"), "observation.ticker")
        if event_ticker not in event_by_ticker:
            raise CryptoHeterogeneityError(f"observation references unknown event {event_ticker}")
        if market_events.get(ticker) != event_ticker:
            raise CryptoHeterogeneityError(
                f"observation market/event mismatch for {ticker}/{event_ticker}"
            )
        if row.get("valid_quote_observation") != "true":
            continue
        valid_obs_by_event[event_ticker] += 1
        band = row.get("time_band", "")
        if band in VALID_TIME_BANDS:
            bands_by_event[event_ticker].add(band)

    class_by_event = {row["event_ticker"]: row for row in event_map}
    asset_summary = _summaries_for_dimension(
        events, market_count_by_event, valid_obs_by_event, bands_by_event, class_by_event, "asset_group"
    )
    template_summary = _summaries_for_dimension(
        events, market_count_by_event, valid_obs_by_event, bands_by_event, class_by_event, "template_family"
    )
    cross_summary = _summaries_for_cross(
        events, market_count_by_event, valid_obs_by_event, bands_by_event, class_by_event
    )

    total_events = len(events)
    high_asset = sum(1 for row in event_map if row["asset_classification_confidence"] == "high")
    high_template = sum(
        1 for row in event_map if row["template_classification_confidence"] == "high"
    )
    return {
        "schema_version": CRYPTO_HETEROGENEITY_SCHEMA_VERSION,
        "taxonomy_version": CRYPTO_TAXONOMY_VERSION,
        "scope": "descriptive_pre_outcome",
        "event_count": total_events,
        "market_count": len(markets),
        "valid_quote_observation_count": sum(valid_obs_by_event.values()),
        "high_confidence_asset_event_count": high_asset,
        "high_confidence_asset_event_share": _share(high_asset, total_events),
        "high_confidence_template_event_count": high_template,
        "high_confidence_template_event_share": _share(high_template, total_events),
        "event_map": sorted(event_map, key=lambda row: row["event_ticker"]),
        "asset_group_summary": asset_summary,
        "template_family_summary": template_summary,
        "asset_template_summary": cross_summary,
        "outcomes_materialized": False,
        "calibration_analysis_run": False,
        "strategy_model_analysis_run": False,
        "profitability_analysis_run": False,
        "general_crypto_conclusion_authorized": False,
    }


def build_report_from_manifest(
    manifest_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    repo_root = Path(repository_root).resolve()
    validated = validate_historical_feasibility_manifest(manifest_path, repository_root=repo_root)
    if validated.get("collector_name") != "collect_historical_feasibility":
        raise CryptoHeterogeneityError("source manifest is not a cross-category feasibility run")
    if validated.get("outcomes_materialized") is not False:
        raise CryptoHeterogeneityError("source manifest must be outcome-blind")

    manifest = _load_json(manifest_path)
    paths = _find_source_csvs(manifest, repo_root, validated["run_id"])
    events = [row for row in _read_csv(paths["events"], EVENT_FIELDS) if row["category"] == "Crypto"]
    markets = [row for row in _read_csv(paths["markets"], MARKET_FIELDS) if row["category"] == "Crypto"]
    observations = [
        row for row in _read_csv(paths["observations"], OBSERVATION_FIELDS) if row["category"] == "Crypto"
    ]
    if not events:
        raise CryptoHeterogeneityError("source run contains no Crypto event rows")
    profile = build_crypto_heterogeneity_profile(events, markets, observations)
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
    json_path = out / f"{run_id}_crypto_heterogeneity.json"
    event_map_path = out / f"{run_id}_crypto_event_subgroups.csv"
    asset_path = out / f"{run_id}_crypto_asset_groups.csv"
    template_path = out / f"{run_id}_crypto_template_families.csv"
    cross_path = out / f"{run_id}_crypto_asset_template_groups.csv"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(event_map_path, report["event_map"])
    _write_csv(asset_path, report["asset_group_summary"])
    _write_csv(template_path, report["template_family_summary"])
    _write_csv(cross_path, report["asset_template_summary"])
    return {
        "report": json_path,
        "event_map": event_map_path,
        "asset_groups": asset_path,
        "template_families": template_path,
        "asset_template_groups": cross_path,
    }


def validate_profile_report(
    report_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    report_path = Path(report_path)
    report = _load_json(report_path)
    if report.get("schema_version") != CRYPTO_HETEROGENEITY_SCHEMA_VERSION:
        raise CryptoHeterogeneityError("Crypto heterogeneity report schema version mismatch")
    manifest_path = _resolve_path(report.get("source_manifest"), Path(repository_root).resolve())
    expected_hash = _required_text(report.get("source_manifest_sha256"), "source_manifest_sha256")
    if _sha256_file(manifest_path) != expected_hash:
        raise CryptoHeterogeneityError("source manifest hash differs from Crypto heterogeneity report")
    rebuilt = build_report_from_manifest(manifest_path, repository_root=repository_root)
    if rebuilt != report:
        raise CryptoHeterogeneityError("Crypto heterogeneity report does not deterministically rebuild")
    return report


def _summaries_for_dimension(events, market_counts, obs_counts, bands, classes, dimension):
    groups: dict[str, list[str]] = defaultdict(list)
    for event in events:
        ticker = event["event_ticker"]
        groups[classes[ticker][dimension]].append(ticker)
    return sorted(
        [
            _summary_row(label, tickers, events, market_counts, obs_counts, bands, dimension)
            for label, tickers in groups.items()
        ],
        key=lambda row: (-int(row["event_count"]), row["group_label"]),
    )


def _summaries_for_cross(events, market_counts, obs_counts, bands, classes):
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for event in events:
        ticker = event["event_ticker"]
        row = classes[ticker]
        groups[(row["asset_group"], row["template_family"])].append(ticker)
    rows = []
    for (asset, template), tickers in groups.items():
        rows.append(
            {
                **_summary_row(
                    f"{asset} | {template}", tickers, events, market_counts, obs_counts, bands, "asset_x_template"
                ),
                "asset_group": asset,
                "template_family": template,
            }
        )
    return sorted(rows, key=lambda row: (-int(row["event_count"]), row["group_label"]))


def _summary_row(label, event_tickers, events, market_counts, obs_counts, bands, group_type):
    event_set = set(event_tickers)
    series = {row["series_ticker"] for row in events if row["event_ticker"] in event_set}
    event_count = len(event_tickers)
    counts = [int(obs_counts.get(event, 0)) for event in event_tickers]
    valid_events = sum(1 for count in counts if count > 0)
    total_obs = sum(counts)
    max_share = (max(counts) / total_obs) if total_obs else 0.0
    top_n = max(1, (event_count + 9) // 10) if event_count else 0
    top_decile = (sum(sorted(counts, reverse=True)[:top_n]) / total_obs) if total_obs else 0.0
    early = sum(1 for event in event_tickers if "early_5d_to_7d" in bands.get(event, set()))
    middle = sum(1 for event in event_tickers if "middle_3d_to_5d" in bands.get(event, set()))
    late = sum(1 for event in event_tickers if "late_1d_to_3d" in bands.get(event, set()))
    all_three = sum(1 for event in event_tickers if set(VALID_TIME_BANDS) <= bands.get(event, set()))
    return {
        "group_type": group_type,
        "group_label": label,
        "event_count": str(event_count),
        "unique_series_count": str(len(series)),
        "market_count": str(sum(int(market_counts.get(event, 0)) for event in event_tickers)),
        "valid_quote_event_count": str(valid_events),
        "event_quote_coverage": _share(valid_events, event_count),
        "valid_quote_observation_count": str(total_obs),
        "median_valid_observations_per_event": _decimal_text(Decimal(str(median(counts))) if counts else Decimal(0)),
        "early_event_coverage": _share(early, event_count),
        "middle_event_coverage": _share(middle, event_count),
        "late_event_coverage": _share(late, event_count),
        "all_three_band_event_coverage": _share(all_three, event_count),
        "max_event_observation_share": _decimal_text(Decimal(str(max_share))),
        "top_decile_event_observation_share": _decimal_text(Decimal(str(top_decile))),
        "interpretation_scope": "descriptive_pre_outcome",
    }


def _reject_outcomes(tables):
    for table in tables:
        for row in table:
            if "result" in row:
                raise CryptoHeterogeneityError("forbidden outcome field 'result' in profile input")


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
        raise CryptoHeterogeneityError(f"source manifest missing required tables: {sorted(missing)}")
    return found


def _read_csv(path: Path, fields: Sequence[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(fields):
                raise CryptoHeterogeneityError(f"unexpected CSV columns in {path}")
            rows = [dict(row) for row in reader]
    except (OSError, csv.Error) as exc:
        raise CryptoHeterogeneityError(f"could not read {path}: {exc}") from exc
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
        raise CryptoHeterogeneityError(f"could not load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CryptoHeterogeneityError(f"JSON {path} must contain an object")
    return value


def _resolve_path(value: object, repo_root: Path) -> Path:
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
                raise CryptoHeterogeneityError("repository-relative path escapes repository root") from exc
            return path
        raise CryptoHeterogeneityError(f"unsupported path kind {kind!r}")
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
        raise CryptoHeterogeneityError(f"could not hash {path}: {exc}") from exc
    return digest.hexdigest()


def _share(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.000000"
    return _decimal_text(Decimal(numerator) / Decimal(denominator))


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000")), "f")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CryptoHeterogeneityError(f"{field} must be non-empty text")
    return value
