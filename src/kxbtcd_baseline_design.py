"""Frozen pre-outcome design utilities for the first KXBTCD baseline pilot.

This module is intentionally outcome-blind. It consumes only the already-created
Checkpoint-10 BTC-family quote-feasibility artifacts. It selects synchronized
same-minute quote cross-sections, assigns an immutable chronological
 development/holdout partition, and exposes pure scoring/projection utilities
whose definitions are frozen before any Kalshi result field is materialized.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class KxbtcdBaselineDesignError(RuntimeError):
    """Raised when the pre-outcome baseline design contract is violated."""


EXPERIMENT_ID = "kxbtcd_three_probe_monotone_baseline.v1"
PREOUTCOME_SCHEMA_VERSION = "kxbtcd_baseline_preoutcome.v1"
SOURCE_COLLECTOR = "collect_btc_family_quote_feasibility"
TARGET_FAMILY = "KXBTCD"
TARGET_REGIME_ID = "brti_60s_simple_mean_untrimmed"
EXPECTED_SOURCE_CLUSTER_COUNT = 20
PROBE_ROLES = ("q25", "q50", "q75")
TIME_BANDS = ("early", "middle", "late")
BAND_TARGET_NORMALIZED_REMAINING = {
    "early": Decimal("0.833333333333333333"),
    "middle": Decimal("0.5"),
    "late": Decimal("0.166666666666666667"),
}
MIN_SYNCHRONIZED_ALL_BAND_CLUSTER_COVERAGE = Decimal("0.50")
DEVELOPMENT_FRACTION = Decimal("0.666666666666666667")
LOG_LOSS_EPSILON = Decimal("0.000001")

CLUSTER_OUTPUT_FIELDS = (
    "schema_version",
    "experiment_id",
    "design_fingerprint",
    "source_run_id",
    "inventory_run_id",
    "family",
    "event_ticker",
    "source_cluster_id",
    "regime_id",
    "primitive_ids_json",
    "open_time",
    "close_time",
    "duration_seconds",
    "source_selection_hash",
    "synchronized_band_count",
    "primary_eligible",
    "partition",
    "chronological_rank",
)

CROSS_SECTION_OUTPUT_FIELDS = (
    "schema_version",
    "experiment_id",
    "design_fingerprint",
    "source_run_id",
    "inventory_run_id",
    "family",
    "event_ticker",
    "source_cluster_id",
    "partition",
    "time_band",
    "target_normalized_time_remaining",
    "selected_end_period_ts",
    "selected_normalized_time_remaining",
    "target_distance",
    "cross_section_id",
    "ticker",
    "probe_role",
    "strike_type",
    "floor_strike",
    "cap_strike",
    "functional_strike",
    "yes_bid_close",
    "yes_ask_close",
    "q_raw",
    "spread",
    "quote_raw_source",
    "quote_raw_session_id",
    "quote_raw_request_id",
    "quote_route_tier",
)

SUMMARY_OUTPUT_FIELDS = (
    "schema_version",
    "experiment_id",
    "design_fingerprint",
    "source_run_id",
    "inventory_run_id",
    "family",
    "source_cluster_count",
    "primary_eligible_cluster_count",
    "primary_eligible_cluster_coverage",
    "development_cluster_count",
    "holdout_cluster_count",
    "selected_cross_section_count",
    "selected_prediction_row_count",
    "synchronization_gate_pass",
    "status",
)

FORBIDDEN_PREOUTCOME_FIELDS = frozenset(
    {
        "result",
        "outcome",
        "settlement_value",
        "expiration_value",
        "label",
        "y",
        "resolved_yes",
    }
)


@dataclass(frozen=True)
class PreOutcomeInputs:
    source_manifest_path: Path
    source_run_id: str
    source_manifest_sha256: str
    inventory_run_id: str
    clusters: tuple[dict[str, str], ...]
    cross_sections: tuple[dict[str, str], ...]
    summary: dict[str, str]


@dataclass(frozen=True)
class SourceArtifacts:
    manifest_path: Path
    manifest: Mapping[str, Any]
    clusters_path: Path
    probes_path: Path
    observations_path: Path
    summaries_path: Path


def frozen_design_contract() -> dict[str, Any]:
    """Return the canonical, outcome-blind design definition.

    The fingerprint of this object is written to every pre-outcome row. Any
    material change requires a new experiment version/fingerprint before labels
    are opened.
    """

    return {
        "experiment_id": EXPERIMENT_ID,
        "source_collector": SOURCE_COLLECTOR,
        "target_family": TARGET_FAMILY,
        "target_regime_id": TARGET_REGIME_ID,
        "source_cluster_count": EXPECTED_SOURCE_CLUSTER_COUNT,
        "probe_roles": list(PROBE_ROLES),
        "time_bands": list(TIME_BANDS),
        "band_target_normalized_remaining": {
            key: str(value) for key, value in BAND_TARGET_NORMALIZED_REMAINING.items()
        },
        "cross_section_rule": (
            "exact_common_end_period_ts_across_all_three_probes_within_band; "
            "choose_min_abs_normalized_distance_to_band_center; tie=earliest_timestamp"
        ),
        "primary_eligibility": "all_three_bands_have_synchronized_three_probe_cross_section",
        "min_primary_eligible_cluster_coverage": str(
            MIN_SYNCHRONIZED_ALL_BAND_CLUSTER_COVERAGE
        ),
        "partition_rule": (
            "chronological_close_time_ascending_among_primary_eligible_clusters; "
            "first_floor_2n_over_3=development; remainder=holdout"
        ),
        "primitive_leakage_rule": "development_and_holdout_primitive_id_sets_must_be_disjoint",
        "raw_baseline": "same-minute_yes_bid_ask_midpoint_per_probe",
        "cross_strike_baseline": (
            "equal_weight_l2_isotonic_projection_of_three_raw_midpoints_onto_"
            "nonincreasing_probability_by_increasing_strike"
        ),
        "primary_metric": "cluster_weighted_log_loss_raw_vs_monotone",
        "secondary_metrics": [
            "cluster_weighted_brier_raw_vs_monotone_structural_diagnostic",
            "raw_monotonicity_violation_rate",
            "mean_absolute_monotone_adjustment",
            "max_absolute_monotone_adjustment",
        ],
        "weighting_rule": "equal_cluster_then_equal_band_then_equal_probe",
        "log_loss_epsilon": str(LOG_LOSS_EPSILON),
        "holdout_rule": (
            "initial outcome materialization may open development only; if design/code changes "
            "after development outcomes are viewed, v1 holdout is invalidated; otherwise holdout "
            "must be opened regardless of development score"
        ),
        "outcome_source_rule": (
            "Kalshi finalized market result only, raw-first with exact lineage; no external BTC "
            "feed or reconstructed settlement value"
        ),
        "outcome_consistency_rule": (
            "within each threshold ladder cross-section, realized binary outcomes must be "
            "nonincreasing with strike or analysis fails closed"
        ),
        "interpretation_limits": [
            "baseline pilot only",
            "no profitability claim",
            "no executable-fill claim",
            "three structural probes do not reconstruct the full ladder distribution",
            "Brier non-worsening under L2 projection is structural when outcomes are monotone",
            "no p-value or statistical-significance claim from this small pilot",
        ],
    }


def design_fingerprint() -> str:
    payload = json.dumps(
        frozen_design_contract(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_design_contract() -> None:
    if TARGET_FAMILY != "KXBTCD":
        raise KxbtcdBaselineDesignError("baseline family changed")
    if TARGET_REGIME_ID != "brti_60s_simple_mean_untrimmed":
        raise KxbtcdBaselineDesignError("baseline settlement regime changed")
    if PROBE_ROLES != ("q25", "q50", "q75"):
        raise KxbtcdBaselineDesignError("probe-role contract changed")
    if set(BAND_TARGET_NORMALIZED_REMAINING) != set(TIME_BANDS):
        raise KxbtcdBaselineDesignError("time-band center contract changed")
    if not Decimal("0") < MIN_SYNCHRONIZED_ALL_BAND_CLUSTER_COVERAGE <= Decimal("1"):
        raise KxbtcdBaselineDesignError("invalid synchronization coverage gate")
    if not Decimal("0") < DEVELOPMENT_FRACTION < Decimal("1"):
        raise KxbtcdBaselineDesignError("invalid development fraction")
    if not Decimal("0") < LOG_LOSS_EPSILON < Decimal("0.5"):
        raise KxbtcdBaselineDesignError("invalid log-loss epsilon")
    for fields in (CLUSTER_OUTPUT_FIELDS, CROSS_SECTION_OUTPUT_FIELDS, SUMMARY_OUTPUT_FIELDS):
        if len(fields) != len(set(fields)):
            raise KxbtcdBaselineDesignError("duplicate pre-outcome schema field")
        bad = FORBIDDEN_PREOUTCOME_FIELDS.intersection(fields)
        if bad:
            raise KxbtcdBaselineDesignError(
                f"pre-outcome schema contains forbidden fields: {sorted(bad)}"
            )


def load_latest_source_artifacts(repository_root: str | Path = ".") -> SourceArtifacts:
    repo = Path(repository_root).resolve()
    manifest_root = repo / "data" / "manifests"
    candidates = sorted(
        manifest_root.rglob(f"{SOURCE_COLLECTOR}_*.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for path in candidates:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            manifest.get("status") == "completed"
            and manifest.get("collector", {}).get("name") == SOURCE_COLLECTOR
        ):
            return SourceArtifacts(
                manifest_path=path.resolve(),
                manifest=manifest,
                clusters_path=_manifest_file(repo, manifest, "btc_family_clusters"),
                probes_path=_manifest_file(repo, manifest, "btc_family_probe_markets"),
                observations_path=_manifest_file(repo, manifest, "btc_family_quote_observations"),
                summaries_path=_manifest_file(repo, manifest, "btc_family_quote_summary"),
            )
    raise KxbtcdBaselineDesignError(
        "no completed BTC-family quote-feasibility manifest was found"
    )


def prepare_preoutcome_inputs(
    artifacts: SourceArtifacts,
) -> PreOutcomeInputs:
    validate_design_contract()
    source_run_id = _required(artifacts.manifest, "run_id")
    source_manifest_sha256 = hashlib.sha256(artifacts.manifest_path.read_bytes()).hexdigest()
    cluster_rows = _read_csv(artifacts.clusters_path)
    probe_rows = _read_csv(artifacts.probes_path)
    observation_rows = _read_csv(artifacts.observations_path)
    summary_rows = _read_csv(artifacts.summaries_path)
    _reject_outcome_columns(cluster_rows, "source clusters")
    _reject_outcome_columns(probe_rows, "source probes")
    _reject_outcome_columns(observation_rows, "source observations")
    _reject_outcome_columns(summary_rows, "source summaries")

    source_summary = _one(
        [row for row in summary_rows if row.get("family") == TARGET_FAMILY],
        "KXBTCD family summary",
    )
    if source_summary.get("status") != "quote_feasibility_pass":
        raise KxbtcdBaselineDesignError(
            "KXBTCD did not pass the frozen source quote-feasibility gate"
        )
    if _int(source_summary.get("cluster_count"), "summary.cluster_count") != EXPECTED_SOURCE_CLUSTER_COUNT:
        raise KxbtcdBaselineDesignError("source KXBTCD cluster count changed")

    clusters = [row for row in cluster_rows if row.get("family") == TARGET_FAMILY]
    probes = [row for row in probe_rows if row.get("family") == TARGET_FAMILY]
    observations = [row for row in observation_rows if row.get("family") == TARGET_FAMILY]
    if len(clusters) != EXPECTED_SOURCE_CLUSTER_COUNT:
        raise KxbtcdBaselineDesignError(
            f"expected {EXPECTED_SOURCE_CLUSTER_COUNT} KXBTCD clusters, found {len(clusters)}"
        )
    inventory_ids = {_required(row, "inventory_run_id") for row in clusters}
    if len(inventory_ids) != 1:
        raise KxbtcdBaselineDesignError("KXBTCD source clusters mix inventory runs")
    inventory_run_id = next(iter(inventory_ids))

    probes_by_cluster: dict[str, list[dict[str, str]]] = {}
    observations_by_cluster: dict[str, list[dict[str, str]]] = {}
    for row in probes:
        probes_by_cluster.setdefault(_required(row, "source_cluster_id"), []).append(row)
    for row in observations:
        observations_by_cluster.setdefault(_required(row, "source_cluster_id"), []).append(row)

    fingerprint = design_fingerprint()
    provisional_clusters: list[dict[str, str]] = []
    provisional_sections: list[dict[str, str]] = []

    for cluster in clusters:
        cluster_id = _required(cluster, "source_cluster_id")
        event = _required(cluster, "event_ticker")
        if _required(cluster, "regime_id") != TARGET_REGIME_ID:
            raise KxbtcdBaselineDesignError(
                f"cluster {cluster_id} is not in frozen modern KXBTCD regime"
            )
        cluster_probes = probes_by_cluster.get(cluster_id, [])
        _validate_three_probes(cluster_id, cluster_probes)
        _validate_shared_active_window(cluster_id, cluster_probes)
        strike_order = sorted(cluster_probes, key=_probe_strike_anchor)
        ordered_roles = tuple(row["probe_role"] for row in strike_order)
        if ordered_roles != PROBE_ROLES:
            raise KxbtcdBaselineDesignError(
                f"cluster {cluster_id} probe roles are not ordered q25/q50/q75 by strike: {ordered_roles}"
            )

        cluster_obs = observations_by_cluster.get(cluster_id, [])
        selected_bands = 0
        for band in TIME_BANDS:
            section = select_synchronized_cross_section(
                cluster_id=cluster_id,
                probes=strike_order,
                observations=cluster_obs,
                time_band=band,
            )
            if section:
                selected_bands += 1
                provisional_sections.extend(
                    _build_cross_section_rows(
                        section=section,
                        source_run_id=source_run_id,
                        inventory_run_id=inventory_run_id,
                        fingerprint=fingerprint,
                        event_ticker=event,
                        cluster_id=cluster_id,
                        time_band=band,
                    )
                )

        provisional_clusters.append(
            {
                "schema_version": PREOUTCOME_SCHEMA_VERSION,
                "experiment_id": EXPERIMENT_ID,
                "design_fingerprint": fingerprint,
                "source_run_id": source_run_id,
                "inventory_run_id": inventory_run_id,
                "family": TARGET_FAMILY,
                "event_ticker": event,
                "source_cluster_id": cluster_id,
                "regime_id": _required(cluster, "regime_id"),
                "primitive_ids_json": _required(cluster, "primitive_ids_json"),
                "open_time": _required(cluster, "open_time"),
                "close_time": _required(cluster, "close_time"),
                "duration_seconds": _required(cluster, "duration_seconds"),
                "source_selection_hash": _required(cluster, "selection_hash"),
                "synchronized_band_count": str(selected_bands),
                "primary_eligible": _bool_text(selected_bands == len(TIME_BANDS)),
                "partition": "",
                "chronological_rank": "",
            }
        )

    eligible = [row for row in provisional_clusters if row["primary_eligible"] == "true"]
    coverage = Decimal(len(eligible)) / Decimal(EXPECTED_SOURCE_CLUSTER_COUNT)
    gate_pass = coverage >= MIN_SYNCHRONIZED_ALL_BAND_CLUSTER_COVERAGE
    if not gate_pass:
        raise KxbtcdBaselineDesignError(
            "synchronized three-probe/all-three-band coverage failed frozen 50% gate: "
            f"{coverage}"
        )

    partition_by_cluster = assign_chronological_partitions(eligible)
    cluster_lookup = {row["source_cluster_id"]: row for row in provisional_clusters}
    for cluster_id, (partition, rank) in partition_by_cluster.items():
        cluster_lookup[cluster_id]["partition"] = partition
        cluster_lookup[cluster_id]["chronological_rank"] = str(rank)
    for row in provisional_sections:
        info = partition_by_cluster.get(row["source_cluster_id"])
        if info is None:
            row["partition"] = "descriptive_partial"
        else:
            row["partition"] = info[0]

    _validate_partition_primitive_disjointness(
        [row for row in provisional_clusters if row["primary_eligible"] == "true"]
    )
    _validate_preoutcome_rows(provisional_clusters, provisional_sections)

    dev_count = sum(row["partition"] == "development" for row in provisional_clusters)
    holdout_count = sum(row["partition"] == "holdout" for row in provisional_clusters)
    selected_cross_section_count = len(provisional_sections) // len(PROBE_ROLES)
    summary = {
        "schema_version": PREOUTCOME_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "design_fingerprint": fingerprint,
        "source_run_id": source_run_id,
        "inventory_run_id": inventory_run_id,
        "family": TARGET_FAMILY,
        "source_cluster_count": str(EXPECTED_SOURCE_CLUSTER_COUNT),
        "primary_eligible_cluster_count": str(len(eligible)),
        "primary_eligible_cluster_coverage": _decimal_text(coverage),
        "development_cluster_count": str(dev_count),
        "holdout_cluster_count": str(holdout_count),
        "selected_cross_section_count": str(selected_cross_section_count),
        "selected_prediction_row_count": str(len(provisional_sections)),
        "synchronization_gate_pass": _bool_text(gate_pass),
        "status": "preoutcome_design_inputs_frozen",
    }
    return PreOutcomeInputs(
        source_manifest_path=artifacts.manifest_path,
        source_run_id=source_run_id,
        source_manifest_sha256=source_manifest_sha256,
        inventory_run_id=inventory_run_id,
        clusters=tuple(sorted(provisional_clusters, key=lambda row: (row["close_time"], row["event_ticker"]))),
        cross_sections=tuple(
            sorted(
                provisional_sections,
                key=lambda row: (
                    row["selected_end_period_ts"],
                    row["event_ticker"],
                    TIME_BANDS.index(row["time_band"]),
                    PROBE_ROLES.index(row["probe_role"]),
                ),
            )
        ),
        summary=summary,
    )


def select_synchronized_cross_section(
    *,
    cluster_id: str,
    probes: Sequence[Mapping[str, str]],
    observations: Sequence[Mapping[str, str]],
    time_band: str,
) -> dict[str, dict[str, str]]:
    """Select one exact same-minute three-probe cross-section for a time band."""

    if time_band not in TIME_BANDS:
        raise KxbtcdBaselineDesignError(f"unsupported time band {time_band!r}")
    roles = {_required(row, "probe_role") for row in probes}
    if roles != set(PROBE_ROLES):
        raise KxbtcdBaselineDesignError(f"cluster {cluster_id} does not have three frozen probes")
    by_role_ts: dict[str, dict[int, dict[str, str]]] = {role: {} for role in PROBE_ROLES}
    for row in observations:
        if row.get("source_cluster_id") != cluster_id:
            continue
        role = row.get("probe_role")
        if role not in by_role_ts or row.get("time_band") != time_band:
            continue
        if row.get("valid_quote_observation") != "true":
            continue
        ts = _int(row.get("end_period_ts"), "observation.end_period_ts")
        if ts in by_role_ts[role]:
            raise KxbtcdBaselineDesignError(
                f"cluster {cluster_id} role {role} has duplicate valid quote timestamp {ts}"
            )
        by_role_ts[role][ts] = dict(row)
    common: set[int] | None = None
    for role in PROBE_ROLES:
        timestamps = set(by_role_ts[role])
        common = timestamps if common is None else common.intersection(timestamps)
    if not common:
        return {}

    target = BAND_TARGET_NORMALIZED_REMAINING[time_band]
    candidates: list[tuple[Decimal, int, Decimal]] = []
    for ts in common:
        normalized = {
            _decimal(by_role_ts[role][ts].get("normalized_time_remaining"), "normalized_time_remaining")
            for role in PROBE_ROLES
        }
        if len(normalized) != 1:
            raise KxbtcdBaselineDesignError(
                f"cluster {cluster_id} synchronized timestamp {ts} has inconsistent normalized time"
            )
        value = next(iter(normalized))
        candidates.append((abs(value - target), ts, value))
    _distance, selected_ts, _normalized = min(candidates, key=lambda item: (item[0], item[1]))
    return {role: by_role_ts[role][selected_ts] for role in PROBE_ROLES}


def assign_chronological_partitions(
    eligible_clusters: Sequence[Mapping[str, str]],
) -> dict[str, tuple[str, int]]:
    if len(eligible_clusters) < 2:
        raise KxbtcdBaselineDesignError("at least two eligible clusters are required")
    ordered = sorted(
        eligible_clusters,
        key=lambda row: (_parse_utc(_required(row, "close_time"), "close_time"), _required(row, "event_ticker")),
    )
    n = len(ordered)
    development_count = (2 * n) // 3
    if development_count <= 0 or development_count >= n:
        raise KxbtcdBaselineDesignError("chronological split would create an empty partition")
    output: dict[str, tuple[str, int]] = {}
    for index, row in enumerate(ordered, start=1):
        partition = "development" if index <= development_count else "holdout"
        output[_required(row, "source_cluster_id")] = (partition, index)
    return output


def project_nonincreasing_l2(probabilities: Sequence[float | Decimal]) -> tuple[Decimal, ...]:
    """Equal-weight PAVA projection onto p1 >= p2 >= ... >= pn."""

    values = [_probability(value, "probability") for value in probabilities]
    if not values:
        raise KxbtcdBaselineDesignError("probability vector must not be empty")
    # Convert nonincreasing p to nondecreasing -p, run PAVA, then negate.
    blocks: list[dict[str, Any]] = []
    for value in values:
        blocks.append({"sum": -value, "weight": Decimal(1), "count": 1})
        while len(blocks) >= 2:
            left = blocks[-2]["sum"] / blocks[-2]["weight"]
            right = blocks[-1]["sum"] / blocks[-1]["weight"]
            if left <= right:
                break
            b = blocks.pop()
            a = blocks.pop()
            blocks.append(
                {
                    "sum": a["sum"] + b["sum"],
                    "weight": a["weight"] + b["weight"],
                    "count": a["count"] + b["count"],
                }
            )
    projected: list[Decimal] = []
    for block in blocks:
        mean = -(block["sum"] / block["weight"])
        projected.extend([mean] * block["count"])
    return tuple(projected)


def binary_log_loss(probability: float | Decimal, outcome: int) -> Decimal:
    p = _probability(probability, "probability")
    if outcome not in (0, 1):
        raise KxbtcdBaselineDesignError("binary outcome must be 0 or 1")
    eps = LOG_LOSS_EPSILON
    clipped = min(max(p, eps), Decimal(1) - eps)
    pf = float(clipped)
    value = -math.log(pf) if outcome == 1 else -math.log(1.0 - pf)
    return Decimal(str(value))


def brier_score(probability: float | Decimal, outcome: int) -> Decimal:
    p = _probability(probability, "probability")
    if outcome not in (0, 1):
        raise KxbtcdBaselineDesignError("binary outcome must be 0 or 1")
    y = Decimal(outcome)
    return (p - y) ** 2


def write_preoutcome_inputs(
    output_dir: str | Path,
    *,
    inputs: PreOutcomeInputs,
) -> tuple[Path, Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    prefix = inputs.source_run_id
    clusters_path = root / f"{prefix}_kxbtcd_baseline_preoutcome_clusters.csv"
    sections_path = root / f"{prefix}_kxbtcd_baseline_preoutcome_cross_sections.csv"
    receipt_path = root / f"{prefix}_kxbtcd_baseline_preoutcome_receipt.json"
    _write_csv(clusters_path, CLUSTER_OUTPUT_FIELDS, inputs.clusters)
    _write_csv(sections_path, CROSS_SECTION_OUTPUT_FIELDS, inputs.cross_sections)
    receipt = {
        **inputs.summary,
        "source_manifest": _stored_path(inputs.source_manifest_path, Path.cwd().resolve()),
        "source_manifest_sha256": inputs.source_manifest_sha256,
        "frozen_design_contract": frozen_design_contract(),
        "artifacts": {
            "clusters_csv": _file_receipt(clusters_path),
            "cross_sections_csv": _file_receipt(sections_path),
        },
        "safety": {
            "api_requests_made": 0,
            "authentication_used": False,
            "outcomes_materialized": False,
            "external_predictive_feed_used": False,
            "orders_placed": 0,
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return clusters_path, sections_path, receipt_path


def _build_cross_section_rows(
    *,
    section: Mapping[str, Mapping[str, str]],
    source_run_id: str,
    inventory_run_id: str,
    fingerprint: str,
    event_ticker: str,
    cluster_id: str,
    time_band: str,
) -> list[dict[str, str]]:
    target = BAND_TARGET_NORMALIZED_REMAINING[time_band]
    selected_ts = {_required(row, "end_period_ts") for row in section.values()}
    normalized = {_required(row, "normalized_time_remaining") for row in section.values()}
    if len(selected_ts) != 1 or len(normalized) != 1:
        raise KxbtcdBaselineDesignError("cross-section is not exactly synchronized")
    ts = next(iter(selected_ts))
    norm = _decimal(next(iter(normalized)), "normalized_time_remaining")
    cross_section_id = hashlib.sha256(
        f"{cluster_id}|{time_band}|{ts}".encode("utf-8")
    ).hexdigest()
    rows: list[dict[str, str]] = []
    for role in PROBE_ROLES:
        row = section[role]
        rows.append(
            {
                "schema_version": PREOUTCOME_SCHEMA_VERSION,
                "experiment_id": EXPERIMENT_ID,
                "design_fingerprint": fingerprint,
                "source_run_id": source_run_id,
                "inventory_run_id": inventory_run_id,
                "family": TARGET_FAMILY,
                "event_ticker": event_ticker,
                "source_cluster_id": cluster_id,
                "partition": "",
                "time_band": time_band,
                "target_normalized_time_remaining": _decimal_text(target),
                "selected_end_period_ts": ts,
                "selected_normalized_time_remaining": _decimal_text(norm),
                "target_distance": _decimal_text(abs(norm - target)),
                "cross_section_id": cross_section_id,
                "ticker": _required(row, "ticker"),
                "probe_role": role,
                "strike_type": str(row.get("strike_type") or ""),
                "floor_strike": str(row.get("floor_strike") or ""),
                "cap_strike": str(row.get("cap_strike") or ""),
                "functional_strike": str(row.get("functional_strike") or ""),
                "yes_bid_close": _required(row, "yes_bid_close"),
                "yes_ask_close": _required(row, "yes_ask_close"),
                "q_raw": _required(row, "q_mid"),
                "spread": _required(row, "spread"),
                "quote_raw_source": _required(row, "raw_source"),
                "quote_raw_session_id": _required(row, "raw_session_id"),
                "quote_raw_request_id": _required(row, "raw_request_id"),
                "quote_route_tier": _required(row, "route_tier"),
            }
        )
    return rows


def _validate_three_probes(cluster_id: str, probes: Sequence[Mapping[str, str]]) -> None:
    if len(probes) != len(PROBE_ROLES):
        raise KxbtcdBaselineDesignError(
            f"cluster {cluster_id} expected three probes, found {len(probes)}"
        )
    roles = [_required(row, "probe_role") for row in probes]
    if set(roles) != set(PROBE_ROLES) or len(roles) != len(set(roles)):
        raise KxbtcdBaselineDesignError(f"cluster {cluster_id} probe roles changed: {roles}")


def _validate_shared_active_window(cluster_id: str, probes: Sequence[Mapping[str, str]]) -> None:
    opens = {_required(row, "open_time") for row in probes}
    closes = {_required(row, "close_time") for row in probes}
    if len(opens) != 1 or len(closes) != 1:
        raise KxbtcdBaselineDesignError(
            f"cluster {cluster_id} probe markets do not share one active window"
        )


def _validate_partition_primitive_disjointness(clusters: Sequence[Mapping[str, str]]) -> None:
    by_partition = {"development": set(), "holdout": set()}
    for row in clusters:
        partition = _required(row, "partition")
        if partition not in by_partition:
            raise KxbtcdBaselineDesignError(f"unexpected primary partition {partition!r}")
        try:
            primitives = json.loads(_required(row, "primitive_ids_json"))
        except json.JSONDecodeError as exc:
            raise KxbtcdBaselineDesignError("primitive_ids_json is invalid JSON") from exc
        if not isinstance(primitives, list) or not primitives or any(
            not isinstance(item, str) or not item for item in primitives
        ):
            raise KxbtcdBaselineDesignError("primitive_ids_json must be a non-empty text list")
        by_partition[partition].update(primitives)
    overlap = by_partition["development"].intersection(by_partition["holdout"])
    if overlap:
        raise KxbtcdBaselineDesignError(
            f"development/holdout primitive leakage detected: {sorted(overlap)[:5]}"
        )


def _validate_preoutcome_rows(
    clusters: Sequence[Mapping[str, str]],
    sections: Sequence[Mapping[str, str]],
) -> None:
    for label, rows, fields in (
        ("cluster", clusters, CLUSTER_OUTPUT_FIELDS),
        ("cross_section", sections, CROSS_SECTION_OUTPUT_FIELDS),
    ):
        for row in rows:
            if tuple(row.keys()) != tuple(fields):
                raise KxbtcdBaselineDesignError(f"{label} output fields changed")
            bad = FORBIDDEN_PREOUTCOME_FIELDS.intersection(row.keys())
            if bad:
                raise KxbtcdBaselineDesignError(
                    f"{label} output contains forbidden outcome fields: {sorted(bad)}"
                )
    groups: dict[str, list[Mapping[str, str]]] = {}
    for row in sections:
        groups.setdefault(_required(row, "cross_section_id"), []).append(row)
    for cross_id, rows in groups.items():
        if len(rows) != len(PROBE_ROLES):
            raise KxbtcdBaselineDesignError(
                f"cross-section {cross_id} does not contain exactly three probes"
            )
        roles = tuple(row["probe_role"] for row in rows)
        if set(roles) != set(PROBE_ROLES):
            raise KxbtcdBaselineDesignError(f"cross-section {cross_id} probe roles changed")
        raw = [_probability(row["q_raw"], "q_raw") for row in sorted(rows, key=lambda r: PROBE_ROLES.index(r["probe_role"]))]
        if any(p < Decimal(0) or p > Decimal(1) for p in raw):
            raise KxbtcdBaselineDesignError(f"cross-section {cross_id} q_raw outside [0,1]")



def _reject_outcome_columns(rows: Sequence[Mapping[str, Any]], label: str) -> None:
    if not rows:
        raise KxbtcdBaselineDesignError(f"{label} are empty")
    columns = set(rows[0].keys())
    bad = FORBIDDEN_PREOUTCOME_FIELDS.intersection(columns)
    if bad:
        raise KxbtcdBaselineDesignError(
            f"{label} unexpectedly contain outcome-like columns: {sorted(bad)}"
        )


def _probe_strike_anchor(row: Mapping[str, str]) -> Decimal:
    floor = _decimal_or_none(row.get("floor_strike"))
    cap = _decimal_or_none(row.get("cap_strike"))
    functional = _decimal_or_none(row.get("functional_strike"))
    if floor is not None and cap is not None:
        return (floor + cap) / Decimal(2)
    if floor is not None:
        return floor
    if cap is not None:
        return cap
    if functional is not None:
        return functional
    raise KxbtcdBaselineDesignError(f"probe {_required(row, 'ticker')} has no strike anchor")


def _manifest_file(repo: Path, manifest: Mapping[str, Any], name_contains: str) -> Path:
    matches: list[Path] = []
    for item in manifest.get("files", []):
        if not isinstance(item, Mapping) or item.get("role") != "derived_csv":
            continue
        spec = item.get("path")
        if not isinstance(spec, Mapping):
            continue
        value = spec.get("value")
        if not isinstance(value, str) or name_contains not in value:
            continue
        kind = spec.get("kind")
        path = (repo / value).resolve() if kind == "repository_relative" else Path(value).resolve()
        matches.append(path)
    if len(matches) != 1:
        raise KxbtcdBaselineDesignError(
            f"expected one source artifact containing {name_contains!r}, found {len(matches)}"
        )
    if not matches[0].exists():
        raise KxbtcdBaselineDesignError(f"source artifact is missing: {matches[0]}")
    return matches[0]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _file_receipt(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def _stored_path(path: Path, repo: Path) -> dict[str, str]:
    try:
        relative = path.resolve().relative_to(repo)
    except ValueError:
        return {"kind": "absolute", "value": str(path.resolve())}
    return {"kind": "repository_relative", "value": relative.as_posix()}


def _one(rows: Sequence[Mapping[str, str]], label: str) -> Mapping[str, str]:
    if len(rows) != 1:
        raise KxbtcdBaselineDesignError(f"expected exactly one {label}, found {len(rows)}")
    return rows[0]


def _required(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if value is None or not str(value).strip():
        raise KxbtcdBaselineDesignError(f"required field {field!r} is missing")
    return str(value).strip()


def _int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise KxbtcdBaselineDesignError(f"{field} must be integer")
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise KxbtcdBaselineDesignError(f"{field} must be integer") from exc


def _decimal(value: Any, field: str) -> Decimal:
    if value in (None, "") or isinstance(value, bool):
        raise KxbtcdBaselineDesignError(f"{field} must be decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise KxbtcdBaselineDesignError(f"{field} must be decimal") from exc
    if not result.is_finite():
        raise KxbtcdBaselineDesignError(f"{field} must be finite")
    return result


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return _decimal(value, "optional decimal")


def _probability(value: Any, field: str) -> Decimal:
    result = _decimal(value, field)
    if not Decimal(0) <= result <= Decimal(1):
        raise KxbtcdBaselineDesignError(f"{field} must lie in [0,1]")
    return result


def _parse_utc(value: str, field: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise KxbtcdBaselineDesignError(f"{field} must be ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise KxbtcdBaselineDesignError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f") if value != 0 else "0"


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


validate_design_contract()
