"""Outcome-blind subgroup cross-classification and eligibility for Sports V2.

This module consumes the independently rebuildable Sports V2 heterogeneity
report. It uses identity and quote-availability information only. It never
reads final market outcomes and never estimates calibration or profitability.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import csv
import json
from typing import Any, Mapping, Sequence

from .sports_v2_heterogeneity import (
    SportsV2HeterogeneityError,
    _portable_path,
    _required_text,
    validate_profile_report,
)

SPORTS_V2_SUBGROUP_ELIGIBILITY_SCHEMA_VERSION = "sports_v2_subgroup_eligibility.v1"
SPORTS_V2_SUBGROUP_POLICY_VERSION = "sports_v2_subgroup_policy.v1"

# Frozen before Sports V2 outcome materialization. These are *pilot support*
# gates for deciding which strata deserve predeclared robustness checks later.
# They are not calibration, profitability, or execution gates.
MIN_EVENTS = 10
MIN_EVENT_QUOTE_COVERAGE = 0.80
MIN_EACH_BAND_EVENT_COVERAGE = 0.50
MIN_ALL_THREE_BAND_EVENT_COVERAGE = 0.50
MIN_DISTINCT_SERIES = 2
MIN_DISTINCT_SPORTS_FOR_PRODUCT = 2
SERIES_CONCENTRATION_WARNING_SHARE = 0.50
SERIES_CONCENTRATION_BLOCK_SHARE = 0.75
SPORT_CONCENTRATION_WARNING_SHARE = 0.60
SPORT_CONCENTRATION_BLOCK_SHARE = 0.80

EXCLUDED_SPORT_GROUPS = {"Other/Unclassified", "Ambiguous"}
EXCLUDED_PRODUCT_FAMILIES = {
    "other_or_unclassified_product_family",
    "ambiguous_product_family",
}


class SportsV2SubgroupEligibilityError(RuntimeError):
    """Raised when subgroup eligibility cannot be computed outcome-blindly."""


def build_subgroup_eligibility(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Cross-classify sport × product and apply frozen outcome-blind support gates."""

    _reject_outcome_keys(profile)
    if profile.get("outcomes_materialized") is not False:
        raise SportsV2SubgroupEligibilityError("source profile must be outcome-blind")
    if profile.get("calibration_analysis_run") is not False:
        raise SportsV2SubgroupEligibilityError("source profile must precede calibration")

    event_map = profile.get("event_map")
    if not isinstance(event_map, Sequence) or isinstance(event_map, (str, bytes)):
        raise SportsV2SubgroupEligibilityError("source profile event_map must be a sequence")

    sport_rows = _assess_dimension(
        summaries=_mapping_rows(profile.get("sport_group_summary"), "sport_group_summary"),
        event_map=event_map,
        dimension="sport_group",
    )
    product_rows = _assess_dimension(
        summaries=_mapping_rows(profile.get("product_family_summary"), "product_family_summary"),
        event_map=event_map,
        dimension="product_family",
    )
    cross_rows = _assess_cross(
        summaries=_mapping_rows(profile.get("sport_product_summary"), "sport_product_summary"),
        event_map=event_map,
    )
    matrix_rows = _cross_tab_matrix(event_map)

    eligible_sports = [row["group_label"] for row in sport_rows if row["eligibility_status"] == "eligible_robustness_stratum"]
    eligible_products = [row["group_label"] for row in product_rows if row["eligibility_status"] == "eligible_robustness_stratum"]
    eligible_cross = [row["group_label"] for row in cross_rows if row["eligibility_status"] == "eligible_robustness_stratum"]

    return {
        "schema_version": SPORTS_V2_SUBGROUP_ELIGIBILITY_SCHEMA_VERSION,
        "policy_version": SPORTS_V2_SUBGROUP_POLICY_VERSION,
        "scope": "pre_outcome_subgroup_support_only",
        "policy": {
            "min_events": MIN_EVENTS,
            "min_event_quote_coverage": _float_text(MIN_EVENT_QUOTE_COVERAGE),
            "min_each_band_event_coverage": _float_text(MIN_EACH_BAND_EVENT_COVERAGE),
            "min_all_three_band_event_coverage": _float_text(MIN_ALL_THREE_BAND_EVENT_COVERAGE),
            "min_distinct_series": MIN_DISTINCT_SERIES,
            "min_distinct_sports_for_product": MIN_DISTINCT_SPORTS_FOR_PRODUCT,
            "series_concentration_warning_share": _float_text(SERIES_CONCENTRATION_WARNING_SHARE),
            "series_concentration_block_share": _float_text(SERIES_CONCENTRATION_BLOCK_SHARE),
            "sport_concentration_warning_share": _float_text(SPORT_CONCENTRATION_WARNING_SHARE),
            "sport_concentration_block_share": _float_text(SPORT_CONCENTRATION_BLOCK_SHARE),
        },
        "event_count": int(profile.get("event_count", 0)),
        "sport_group_eligibility": sport_rows,
        "product_family_eligibility": product_rows,
        "sport_product_eligibility": cross_rows,
        "sport_product_event_count_matrix": matrix_rows,
        "eligible_sport_groups": eligible_sports,
        "eligible_product_families": eligible_products,
        "eligible_sport_product_groups": eligible_cross,
        "outcomes_materialized": False,
        "calibration_analysis_run": False,
        "profitability_analysis_run": False,
        "subgroup_edge_conclusion_authorized": False,
        "general_sports_conclusion_authorized": False,
    }


def build_eligibility_from_profile_report(
    profile_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    profile_path = Path(profile_path)
    repo_root = Path(repository_root).resolve()
    try:
        profile = validate_profile_report(profile_path, repository_root=repo_root)
    except SportsV2HeterogeneityError as exc:
        raise SportsV2SubgroupEligibilityError(str(exc)) from exc
    result = build_subgroup_eligibility(profile)
    return {
        **result,
        "source_run_id": _required_text(profile.get("source_run_id"), "profile.source_run_id"),
        "source_heterogeneity_report": _portable_path(profile_path, repo_root),
        "source_heterogeneity_report_sha256": _sha256_file(profile_path),
        "source_heterogeneity_report_validation": "PASS",
    }


def write_eligibility_artifacts(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> dict[str, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_id = _required_text(report.get("source_run_id"), "report.source_run_id")
    json_path = out / f"{run_id}_sports_v2_subgroup_eligibility.json"
    sports_path = out / f"{run_id}_sports_v2_eligible_sport_groups.csv"
    products_path = out / f"{run_id}_sports_v2_eligible_product_families.csv"
    cross_path = out / f"{run_id}_sports_v2_eligible_sport_product_groups.csv"
    matrix_path = out / f"{run_id}_sports_v2_sport_product_event_matrix.csv"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(sports_path, report["sport_group_eligibility"])
    _write_csv(products_path, report["product_family_eligibility"])
    _write_csv(cross_path, report["sport_product_eligibility"])
    _write_csv(matrix_path, report["sport_product_event_count_matrix"])
    return {
        "report": json_path,
        "sport_groups": sports_path,
        "product_families": products_path,
        "sport_product_groups": cross_path,
        "matrix": matrix_path,
    }


def validate_eligibility_report(
    report_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    report_path = Path(report_path)
    report = _load_json(report_path)
    if report.get("schema_version") != SPORTS_V2_SUBGROUP_ELIGIBILITY_SCHEMA_VERSION:
        raise SportsV2SubgroupEligibilityError("subgroup eligibility schema version mismatch")
    source = report.get("source_heterogeneity_report")
    source_path = _resolve_report_source(source, Path(repository_root).resolve())
    expected_hash = _required_text(
        report.get("source_heterogeneity_report_sha256"),
        "source_heterogeneity_report_sha256",
    )
    if _sha256_file(source_path) != expected_hash:
        raise SportsV2SubgroupEligibilityError("source heterogeneity report hash differs")
    rebuilt = build_eligibility_from_profile_report(source_path, repository_root=repository_root)
    if rebuilt != report:
        raise SportsV2SubgroupEligibilityError("subgroup eligibility report does not deterministically rebuild")
    return report


def _assess_dimension(
    *,
    summaries: Sequence[Mapping[str, Any]],
    event_map: Sequence[Mapping[str, Any]],
    dimension: str,
) -> list[dict[str, Any]]:
    assessed: list[dict[str, Any]] = []
    for summary in summaries:
        label = _required_text(summary.get("group_label"), f"{dimension}.group_label")
        members = [row for row in event_map if row.get(dimension) == label]
        reasons = _base_gate_reasons(summary)
        warnings: list[str] = []

        series_counts = Counter(_required_text(row.get("series_ticker"), "event_map.series_ticker") for row in members)
        distinct_series = len(series_counts)
        dominant_series, dominant_series_count = _dominant(series_counts)
        dominant_series_share = (dominant_series_count / len(members)) if members else 0.0

        if dimension == "sport_group":
            if label in EXCLUDED_SPORT_GROUPS:
                reasons.append("sport_identity_not_high_confidence")
            if distinct_series < MIN_DISTINCT_SERIES:
                reasons.append("insufficient_series_diversity")
            if dominant_series_share > SERIES_CONCENTRATION_BLOCK_SHARE:
                reasons.append("dominant_series_share_above_block_threshold")
            elif dominant_series_share > SERIES_CONCENTRATION_WARNING_SHARE:
                warnings.append("dominant_series_concentration_warning")
        elif dimension == "product_family":
            if label in EXCLUDED_PRODUCT_FAMILIES:
                reasons.append("product_identity_not_high_confidence")
            high_conf_sports = Counter(
                _required_text(row.get("sport_group"), "event_map.sport_group")
                for row in members
                if row.get("sport_classification_confidence") == "high"
            )
            if len(high_conf_sports) < MIN_DISTINCT_SPORTS_FOR_PRODUCT:
                reasons.append("insufficient_cross_sport_diversity")
            dominant_sport, dominant_sport_count = _dominant(high_conf_sports)
            classified_n = sum(high_conf_sports.values())
            dominant_sport_share = (dominant_sport_count / classified_n) if classified_n else 0.0
            if classified_n and dominant_sport_share > SPORT_CONCENTRATION_BLOCK_SHARE:
                reasons.append("dominant_sport_share_above_block_threshold")
            elif classified_n and dominant_sport_share > SPORT_CONCENTRATION_WARNING_SHARE:
                warnings.append("dominant_sport_concentration_warning")
            assessed.append(
                _finalize_row(
                    summary,
                    reasons,
                    warnings,
                    distinct_series=distinct_series,
                    dominant_series=dominant_series,
                    dominant_series_event_share=dominant_series_share,
                    distinct_high_confidence_sports=len(high_conf_sports),
                    dominant_high_confidence_sport=dominant_sport,
                    dominant_high_confidence_sport_share=dominant_sport_share,
                )
            )
            continue
        else:
            raise SportsV2SubgroupEligibilityError(f"unsupported dimension {dimension!r}")

        assessed.append(
            _finalize_row(
                summary,
                reasons,
                warnings,
                distinct_series=distinct_series,
                dominant_series=dominant_series,
                dominant_series_event_share=dominant_series_share,
            )
        )
    return sorted(assessed, key=lambda row: (-int(row["event_count"]), str(row["group_label"])))


def _assess_cross(
    *,
    summaries: Sequence[Mapping[str, Any]],
    event_map: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    assessed: list[dict[str, Any]] = []
    for summary in summaries:
        sport = _required_text(summary.get("sport_group"), "cross.sport_group")
        product = _required_text(summary.get("product_family"), "cross.product_family")
        members = [
            row for row in event_map
            if row.get("sport_group") == sport and row.get("product_family") == product
        ]
        reasons = _base_gate_reasons(summary)
        warnings: list[str] = []
        if sport in EXCLUDED_SPORT_GROUPS:
            reasons.append("sport_identity_not_high_confidence")
        if product in EXCLUDED_PRODUCT_FAMILIES:
            reasons.append("product_identity_not_high_confidence")

        series_counts = Counter(_required_text(row.get("series_ticker"), "event_map.series_ticker") for row in members)
        distinct_series = len(series_counts)
        dominant_series, dominant_series_count = _dominant(series_counts)
        dominant_series_share = (dominant_series_count / len(members)) if members else 0.0
        if distinct_series < MIN_DISTINCT_SERIES:
            reasons.append("insufficient_series_diversity")
        if dominant_series_share > SERIES_CONCENTRATION_BLOCK_SHARE:
            reasons.append("dominant_series_share_above_block_threshold")
        elif dominant_series_share > SERIES_CONCENTRATION_WARNING_SHARE:
            warnings.append("dominant_series_concentration_warning")

        assessed.append(
            _finalize_row(
                summary,
                reasons,
                warnings,
                distinct_series=distinct_series,
                dominant_series=dominant_series,
                dominant_series_event_share=dominant_series_share,
            )
        )
    return sorted(assessed, key=lambda row: (-int(row["event_count"]), str(row["group_label"])))


def _base_gate_reasons(summary: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if _int_value(summary.get("event_count"), "event_count") < MIN_EVENTS:
        reasons.append("fewer_than_minimum_events")
    if _float_value(summary.get("event_quote_coverage"), "event_quote_coverage") < MIN_EVENT_QUOTE_COVERAGE:
        reasons.append("event_quote_coverage_below_threshold")
    for key in ("early_event_coverage", "middle_event_coverage", "late_event_coverage"):
        if _float_value(summary.get(key), key) < MIN_EACH_BAND_EVENT_COVERAGE:
            reasons.append(f"{key}_below_threshold")
    if _float_value(summary.get("all_three_band_event_coverage"), "all_three_band_event_coverage") < MIN_ALL_THREE_BAND_EVENT_COVERAGE:
        reasons.append("all_three_band_event_coverage_below_threshold")
    return reasons


def _finalize_row(
    summary: Mapping[str, Any],
    reasons: Sequence[str],
    warnings: Sequence[str],
    **extra: Any,
) -> dict[str, Any]:
    status = "eligible_robustness_stratum" if not reasons else "descriptive_only"
    return {
        **dict(summary),
        **extra,
        "dominant_series_event_share": _float_text(float(extra.get("dominant_series_event_share", 0.0))),
        **({"dominant_high_confidence_sport_share": _float_text(float(extra.get("dominant_high_confidence_sport_share", 0.0)))} if "dominant_high_confidence_sport_share" in extra else {}),
        "eligibility_status": status,
        "eligibility_reasons": ";".join(sorted(set(reasons))) if reasons else "none",
        "warnings": ";".join(sorted(set(warnings))) if warnings else "none",
        "standalone_calibration_claim_authorized": False,
    }


def _cross_tab_matrix(event_map: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    products = sorted({_required_text(row.get("product_family"), "event_map.product_family") for row in event_map})
    sports = sorted({_required_text(row.get("sport_group"), "event_map.sport_group") for row in event_map})
    counts: dict[tuple[str, str], int] = Counter(
        (
            _required_text(row.get("sport_group"), "event_map.sport_group"),
            _required_text(row.get("product_family"), "event_map.product_family"),
        )
        for row in event_map
    )
    rows: list[dict[str, Any]] = []
    for sport in sports:
        row: dict[str, Any] = {"sport_group": sport}
        total = 0
        for product in products:
            count = counts.get((sport, product), 0)
            row[product] = count
            total += count
        row["total_events"] = total
        rows.append(row)
    return rows


def _mapping_rows(value: Any, name: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise SportsV2SubgroupEligibilityError(f"{name} must be a sequence")
    rows: list[Mapping[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise SportsV2SubgroupEligibilityError(f"{name} contains a non-object row")
        rows.append(row)
    return rows


def _dominant(counts: Mapping[str, int]) -> tuple[str, int]:
    if not counts:
        return "none", 0
    label, count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return label, int(count)


def _reject_outcome_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() == "result":
                raise SportsV2SubgroupEligibilityError("forbidden outcome key 'result'")
            _reject_outcome_keys(child)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            _reject_outcome_keys(child)


def _resolve_report_source(value: Any, repo_root: Path) -> Path:
    text = _required_text(value, "source_heterogeneity_report")
    path = Path(text)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
        try:
            path.relative_to(repo_root)
        except ValueError as exc:
            raise SportsV2SubgroupEligibilityError("source report path escapes repository root") from exc
    return path.resolve()


def _int_value(value: Any, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SportsV2SubgroupEligibilityError(f"{name} must be an integer") from exc


def _float_value(value: Any, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SportsV2SubgroupEligibilityError(f"{name} must be numeric") from exc


def _float_text(value: float) -> str:
    return f"{value:.6f}"


def _sha256_file(path: Path) -> str:
    try:
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise SportsV2SubgroupEligibilityError(f"could not hash {path}: {exc}") from exc


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SportsV2SubgroupEligibilityError(f"could not read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SportsV2SubgroupEligibilityError(f"{path} must contain a JSON object")
    return value


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
