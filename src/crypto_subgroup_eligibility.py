"""Outcome-blind subgroup eligibility for the Checkpoint-09 Crypto branch.

This module consumes an independently rebuildable Crypto heterogeneity report.
It applies the same frozen numerical pilot-support gates used for Sports V2,
adapted only to Crypto's identity dimensions (asset/driver and contract template).
It never reads final outcomes and never evaluates calibration or profitability.
"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path
import csv
import json
from typing import Any, Mapping, Sequence

from .crypto_heterogeneity import (
    CryptoHeterogeneityError,
    _portable_path,
    _required_text,
    validate_profile_report,
)

CRYPTO_SUBGROUP_ELIGIBILITY_SCHEMA_VERSION = "crypto_subgroup_eligibility.v1"
CRYPTO_SUBGROUP_POLICY_VERSION = "crypto_subgroup_policy.v1"

# Frozen before any Crypto outcome materialization. These numerical support
# gates intentionally match the Sports V2 subgroup policy. Only the identity
# dimension names differ.
MIN_EVENTS = 10
MIN_EVENT_QUOTE_COVERAGE = 0.80
MIN_EACH_BAND_EVENT_COVERAGE = 0.50
MIN_ALL_THREE_BAND_EVENT_COVERAGE = 0.50
MIN_DISTINCT_SERIES = 2
MIN_DISTINCT_ASSET_GROUPS_FOR_TEMPLATE = 2
SERIES_CONCENTRATION_WARNING_SHARE = 0.50
SERIES_CONCENTRATION_BLOCK_SHARE = 0.75
ASSET_CONCENTRATION_WARNING_SHARE = 0.60
ASSET_CONCENTRATION_BLOCK_SHARE = 0.80

EXCLUDED_ASSET_GROUPS = {"Other/Unclassified", "Ambiguous"}
EXCLUDED_TEMPLATE_FAMILIES = {
    "other_or_unclassified_template_family",
    "ambiguous_template_family",
}


class CryptoSubgroupEligibilityError(RuntimeError):
    """Raised when Crypto subgroup eligibility cannot be computed safely."""


def build_subgroup_eligibility(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Apply frozen, outcome-blind support gates to Crypto subgroup summaries."""

    _reject_outcome_keys(profile)
    if profile.get("outcomes_materialized") is not False:
        raise CryptoSubgroupEligibilityError("source profile must be outcome-blind")
    if profile.get("calibration_analysis_run") is not False:
        raise CryptoSubgroupEligibilityError("source profile must precede calibration")
    if profile.get("strategy_model_analysis_run") is not False:
        raise CryptoSubgroupEligibilityError("source profile must precede strategy/model analysis")

    event_map = profile.get("event_map")
    if not isinstance(event_map, Sequence) or isinstance(event_map, (str, bytes)):
        raise CryptoSubgroupEligibilityError("source profile event_map must be a sequence")

    asset_rows = _assess_dimension(
        summaries=_mapping_rows(profile.get("asset_group_summary"), "asset_group_summary"),
        event_map=event_map,
        dimension="asset_group",
    )
    template_rows = _assess_dimension(
        summaries=_mapping_rows(profile.get("template_family_summary"), "template_family_summary"),
        event_map=event_map,
        dimension="template_family",
    )
    cross_rows = _assess_cross(
        summaries=_mapping_rows(profile.get("asset_template_summary"), "asset_template_summary"),
        event_map=event_map,
    )
    matrix_rows = _cross_tab_matrix(event_map)

    eligible_assets = [
        row["group_label"] for row in asset_rows
        if row["eligibility_status"] == "eligible_robustness_stratum"
    ]
    eligible_templates = [
        row["group_label"] for row in template_rows
        if row["eligibility_status"] == "eligible_robustness_stratum"
    ]
    eligible_cross = [
        row["group_label"] for row in cross_rows
        if row["eligibility_status"] == "eligible_robustness_stratum"
    ]

    return {
        "schema_version": CRYPTO_SUBGROUP_ELIGIBILITY_SCHEMA_VERSION,
        "policy_version": CRYPTO_SUBGROUP_POLICY_VERSION,
        "scope": "pre_outcome_subgroup_support_only",
        "policy": {
            "min_events": MIN_EVENTS,
            "min_event_quote_coverage": _float_text(MIN_EVENT_QUOTE_COVERAGE),
            "min_each_band_event_coverage": _float_text(MIN_EACH_BAND_EVENT_COVERAGE),
            "min_all_three_band_event_coverage": _float_text(MIN_ALL_THREE_BAND_EVENT_COVERAGE),
            "min_distinct_series": MIN_DISTINCT_SERIES,
            "min_distinct_asset_groups_for_template": MIN_DISTINCT_ASSET_GROUPS_FOR_TEMPLATE,
            "series_concentration_warning_share": _float_text(SERIES_CONCENTRATION_WARNING_SHARE),
            "series_concentration_block_share": _float_text(SERIES_CONCENTRATION_BLOCK_SHARE),
            "asset_concentration_warning_share": _float_text(ASSET_CONCENTRATION_WARNING_SHARE),
            "asset_concentration_block_share": _float_text(ASSET_CONCENTRATION_BLOCK_SHARE),
            "sports_policy_numeric_parity": True,
        },
        "event_count": int(profile.get("event_count", 0)),
        "asset_group_eligibility": asset_rows,
        "template_family_eligibility": template_rows,
        "asset_template_eligibility": cross_rows,
        "asset_template_event_count_matrix": matrix_rows,
        "eligible_asset_groups": eligible_assets,
        "eligible_template_families": eligible_templates,
        "eligible_asset_template_groups": eligible_cross,
        "outcomes_materialized": False,
        "calibration_analysis_run": False,
        "strategy_model_analysis_run": False,
        "profitability_analysis_run": False,
        "subgroup_edge_conclusion_authorized": False,
        "general_crypto_conclusion_authorized": False,
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
    except CryptoHeterogeneityError as exc:
        raise CryptoSubgroupEligibilityError(str(exc)) from exc
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
    json_path = out / f"{run_id}_crypto_subgroup_eligibility.json"
    assets_path = out / f"{run_id}_crypto_eligible_asset_groups.csv"
    templates_path = out / f"{run_id}_crypto_eligible_template_families.csv"
    cross_path = out / f"{run_id}_crypto_eligible_asset_template_groups.csv"
    matrix_path = out / f"{run_id}_crypto_asset_template_event_matrix.csv"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(assets_path, report["asset_group_eligibility"])
    _write_csv(templates_path, report["template_family_eligibility"])
    _write_csv(cross_path, report["asset_template_eligibility"])
    _write_csv(matrix_path, report["asset_template_event_count_matrix"])
    return {
        "report": json_path,
        "asset_groups": assets_path,
        "template_families": templates_path,
        "asset_template_groups": cross_path,
        "matrix": matrix_path,
    }


def validate_eligibility_report(
    report_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    report_path = Path(report_path)
    report = _load_json(report_path)
    if report.get("schema_version") != CRYPTO_SUBGROUP_ELIGIBILITY_SCHEMA_VERSION:
        raise CryptoSubgroupEligibilityError("Crypto subgroup eligibility schema version mismatch")
    source = report.get("source_heterogeneity_report")
    source_path = _resolve_report_source(source, Path(repository_root).resolve())
    expected_hash = _required_text(
        report.get("source_heterogeneity_report_sha256"),
        "source_heterogeneity_report_sha256",
    )
    if _sha256_file(source_path) != expected_hash:
        raise CryptoSubgroupEligibilityError("source heterogeneity report hash differs")
    rebuilt = build_eligibility_from_profile_report(source_path, repository_root=repository_root)
    if rebuilt != report:
        raise CryptoSubgroupEligibilityError("Crypto subgroup eligibility report does not deterministically rebuild")
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

        series_counts = Counter(
            _required_text(row.get("series_ticker"), "event_map.series_ticker") for row in members
        )
        distinct_series = len(series_counts)
        dominant_series, dominant_series_count = _dominant(series_counts)
        dominant_series_share = (dominant_series_count / len(members)) if members else 0.0

        if dimension == "asset_group":
            if label in EXCLUDED_ASSET_GROUPS:
                reasons.append("asset_identity_not_high_confidence")
            if distinct_series < MIN_DISTINCT_SERIES:
                reasons.append("insufficient_series_diversity")
            if dominant_series_share > SERIES_CONCENTRATION_BLOCK_SHARE:
                reasons.append("dominant_series_share_above_block_threshold")
            elif dominant_series_share > SERIES_CONCENTRATION_WARNING_SHARE:
                warnings.append("dominant_series_concentration_warning")
        elif dimension == "template_family":
            if label in EXCLUDED_TEMPLATE_FAMILIES:
                reasons.append("template_identity_not_high_confidence")
            high_conf_assets = Counter(
                _required_text(row.get("asset_group"), "event_map.asset_group")
                for row in members
                if row.get("asset_classification_confidence") == "high"
            )
            if len(high_conf_assets) < MIN_DISTINCT_ASSET_GROUPS_FOR_TEMPLATE:
                reasons.append("insufficient_cross_asset_diversity")
            dominant_asset, dominant_asset_count = _dominant(high_conf_assets)
            classified_n = sum(high_conf_assets.values())
            dominant_asset_share = (dominant_asset_count / classified_n) if classified_n else 0.0
            if classified_n and dominant_asset_share > ASSET_CONCENTRATION_BLOCK_SHARE:
                reasons.append("dominant_asset_share_above_block_threshold")
            elif classified_n and dominant_asset_share > ASSET_CONCENTRATION_WARNING_SHARE:
                warnings.append("dominant_asset_concentration_warning")
            assessed.append(
                _finalize_row(
                    summary,
                    reasons,
                    warnings,
                    distinct_series=distinct_series,
                    dominant_series=dominant_series,
                    dominant_series_event_share=dominant_series_share,
                    distinct_high_confidence_asset_groups=len(high_conf_assets),
                    dominant_high_confidence_asset_group=dominant_asset,
                    dominant_high_confidence_asset_group_share=dominant_asset_share,
                )
            )
            continue
        else:
            raise CryptoSubgroupEligibilityError(f"unsupported dimension {dimension!r}")

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
        asset = _required_text(summary.get("asset_group"), "cross.asset_group")
        template = _required_text(summary.get("template_family"), "cross.template_family")
        members = [
            row for row in event_map
            if row.get("asset_group") == asset and row.get("template_family") == template
        ]
        reasons = _base_gate_reasons(summary)
        warnings: list[str] = []
        if asset in EXCLUDED_ASSET_GROUPS:
            reasons.append("asset_identity_not_high_confidence")
        if template in EXCLUDED_TEMPLATE_FAMILIES:
            reasons.append("template_identity_not_high_confidence")

        series_counts = Counter(
            _required_text(row.get("series_ticker"), "event_map.series_ticker") for row in members
        )
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
    row = {
        **dict(summary),
        **extra,
        "dominant_series_event_share": _float_text(float(extra.get("dominant_series_event_share", 0.0))),
        "eligibility_status": status,
        "eligibility_reasons": ";".join(sorted(set(reasons))) if reasons else "none",
        "warnings": ";".join(sorted(set(warnings))) if warnings else "none",
        "standalone_calibration_or_strategy_claim_authorized": False,
    }
    if "dominant_high_confidence_asset_group_share" in extra:
        row["dominant_high_confidence_asset_group_share"] = _float_text(
            float(extra.get("dominant_high_confidence_asset_group_share", 0.0))
        )
    return row


def _cross_tab_matrix(event_map: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    templates = sorted({_required_text(row.get("template_family"), "event_map.template_family") for row in event_map})
    assets = sorted({_required_text(row.get("asset_group"), "event_map.asset_group") for row in event_map})
    counts: dict[tuple[str, str], int] = Counter(
        (
            _required_text(row.get("asset_group"), "event_map.asset_group"),
            _required_text(row.get("template_family"), "event_map.template_family"),
        )
        for row in event_map
    )
    rows: list[dict[str, Any]] = []
    for asset in assets:
        row: dict[str, Any] = {"asset_group": asset}
        total = 0
        for template in templates:
            count = counts.get((asset, template), 0)
            row[template] = count
            total += count
        row["total_events"] = total
        rows.append(row)
    return rows


def _mapping_rows(value: Any, name: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise CryptoSubgroupEligibilityError(f"{name} must be a sequence")
    rows: list[Mapping[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise CryptoSubgroupEligibilityError(f"{name} contains a non-object row")
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
                raise CryptoSubgroupEligibilityError("forbidden outcome key 'result'")
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
            raise CryptoSubgroupEligibilityError("source report path escapes repository root") from exc
    return path.resolve()


def _int_value(value: Any, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CryptoSubgroupEligibilityError(f"{name} must be an integer") from exc


def _float_value(value: Any, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise CryptoSubgroupEligibilityError(f"{name} must be numeric") from exc


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
        raise CryptoSubgroupEligibilityError(f"could not hash {path}: {exc}") from exc


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CryptoSubgroupEligibilityError(f"could not read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CryptoSubgroupEligibilityError(f"{path} must contain a JSON object")
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
