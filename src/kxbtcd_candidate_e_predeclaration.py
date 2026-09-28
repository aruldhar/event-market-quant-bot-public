"""Checkpoint-19E Candidate-E predeclaration validator and pure feature helpers.

This module freezes design only. It performs no network I/O, loads no outcomes,
fits no model, and contains no execution path.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_PREDECLARATION_PATH = Path("configs/kxbtcd_candidate_e_predeclaration.json")
FROZEN_PREDECLARATION_FINGERPRINT = "9775be58f01375ca6f2b04212a63578ce5e8cf7084498e6ce9d3ae68685d59a9"
FAMILY_ID = "kxbtcd_independent_btc_offset_successor.v1"
DISTANCE_CANDIDATE_ID = "kxbtcd_btc_distance_offset_logistic.v1"
MOMENTUM_CANDIDATE_ID = "kxbtcd_btc_distance_momentum_offset_logistic.v1"
PARENT_PROTOCOL_FINGERPRINT = "b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8"
PARENT_SOURCE_POLICY_FINGERPRINT = "6b0d98c16a65b2e638b36991d5006031e1bd37048bd04a47a3f67d936df0ee18"
MODEL_LOGIT_CLIP = 0.001
FEATURE_SCALE = 10000.0


class KxbtcdCandidateEPredeclarationError(RuntimeError):
    """Raised when the frozen Candidate-E predeclaration is violated."""


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdCandidateEPredeclarationError(
            f"could not read Candidate-E predeclaration {path}: {exc}"
        ) from exc
    if not isinstance(value, Mapping):
        raise KxbtcdCandidateEPredeclarationError(
            "Candidate-E predeclaration root must be an object"
        )
    return value


def validate_candidate_e_predeclaration(
    path: str | Path = DEFAULT_PREDECLARATION_PATH,
) -> str:
    """Validate the exact frozen predeclaration and return its fingerprint."""
    document = dict(_load_json(Path(path)))
    observed = document.get("predeclaration_fingerprint")
    if observed != FROZEN_PREDECLARATION_FINGERPRINT:
        raise KxbtcdCandidateEPredeclarationError(
            "Candidate-E predeclaration fingerprint field changed"
        )
    payload = {k: v for k, v in document.items() if k != "predeclaration_fingerprint"}
    recomputed = _canonical_sha256(payload)
    if recomputed != FROZEN_PREDECLARATION_FINGERPRINT:
        raise KxbtcdCandidateEPredeclarationError(
            "Candidate-E predeclaration canonical fingerprint mismatch"
        )
    if document.get("schema_version") != "kxbtcd_candidate_e_predeclaration.v1":
        raise KxbtcdCandidateEPredeclarationError("Candidate-E schema version changed")
    if document.get("checkpoint_id") != "19E":
        raise KxbtcdCandidateEPredeclarationError("Candidate-E checkpoint changed")
    if document.get("family_id") != FAMILY_ID:
        raise KxbtcdCandidateEPredeclarationError("Candidate-E family changed")
    if document.get("parent_protocol_fingerprint") != PARENT_PROTOCOL_FINGERPRINT:
        raise KxbtcdCandidateEPredeclarationError("Checkpoint-19A parent changed")
    if document.get("parent_source_policy_fingerprint") != PARENT_SOURCE_POLICY_FINGERPRINT:
        raise KxbtcdCandidateEPredeclarationError("Checkpoint-19D-B parent changed")

    boundary = document["evidence_boundary"]
    if boundary["e1_outcomes_used_to_freeze_this_specification"] is not False:
        raise KxbtcdCandidateEPredeclarationError("predeclaration indicates E1 outcome use")
    if boundary["checkpoint17_terminal_used"] is not False:
        raise KxbtcdCandidateEPredeclarationError("terminal evidence boundary violated")
    if boundary["candidate_e_fit_performed"] is not False:
        raise KxbtcdCandidateEPredeclarationError("Candidate-E fit occurred before freeze")
    if boundary["execution_authorized"] is not False:
        raise KxbtcdCandidateEPredeclarationError("execution unexpectedly authorized")

    fit = document["fit_contract"]
    if fit["regularization"] != "none":
        raise KxbtcdCandidateEPredeclarationError("Candidate-E regularization changed")
    if fit["feature_standardization"] != "none":
        raise KxbtcdCandidateEPredeclarationError("Candidate-E scaling changed")
    if fit["hyperparameter_search"] is not False or fit["hyperparameter_grid"] != []:
        raise KxbtcdCandidateEPredeclarationError("Candidate-E tuning changed")
    expected_optimizer = {
        "algorithm": "deterministic_damped_Newton",
        "max_iterations": 100,
        "gradient_l2_tolerance": "1e-8",
        "armijo_constant": "1e-4",
        "minimum_step_scale": "2^-40",
        "non_convergence": "fail_closed",
        "singular_hessian": "fail_closed",
    }
    if fit["optimizer"] != expected_optimizer:
        raise KxbtcdCandidateEPredeclarationError("Candidate-E optimizer changed")

    features = document["features"]
    if features["btc_strike_log_distance_bps.v1"]["formula"] != "10000 * ln(S_t / K)":
        raise KxbtcdCandidateEPredeclarationError("distance feature changed")
    if features["btc_return_5m_bps.v1"]["formula"] != "10000 * ln(S_t / S_t_minus_300s)":
        raise KxbtcdCandidateEPredeclarationError("5m return feature changed")

    candidates = document["candidate_menu"]
    if [c["candidate_id"] for c in candidates] != [
        DISTANCE_CANDIDATE_ID,
        MOMENTUM_CANDIDATE_ID,
    ]:
        raise KxbtcdCandidateEPredeclarationError("Candidate-E menu changed")

    schedule = document["state_materialization"]
    if schedule["scored_ttc_target_minutes"] != [55, 50, 45, 40, 35, 30]:
        raise KxbtcdCandidateEPredeclarationError("Candidate-E TTC schedule changed")
    if schedule["structural_strike_quantiles"] != [0.1, 0.3, 0.5, 0.7, 0.9]:
        raise KxbtcdCandidateEPredeclarationError("Candidate-E strike roles changed")
    if schedule["common_candidate_row_universe"]["requires_5m_lookback"] is not True:
        raise KxbtcdCandidateEPredeclarationError("Candidate-E row universe changed")

    cohort = document["e1_cohort"]
    expected_minimums = (168, 7, 168, 24)
    observed_minimums = (
        cohort["minimum_eligible_events"],
        cohort["minimum_distinct_utc_dates"],
        cohort["minimum_chronological_span_hours"],
        cohort["required_utc_hour_of_day_bins"],
    )
    if observed_minimums != expected_minimums:
        raise KxbtcdCandidateEPredeclarationError("E1 minimums changed")
    if cohort["outcome_dependent_stopping_allowed"] is not False:
        raise KxbtcdCandidateEPredeclarationError("outcome-dependent stopping enabled")

    expected_folds = [
        {"fold": 1, "fit_blocks": ["B0", "B1"], "score_block": "B2"},
        {"fold": 2, "fit_blocks": ["B0", "B1", "B2"], "score_block": "B3"},
        {"fold": 3, "fit_blocks": ["B0", "B1", "B2", "B3"], "score_block": "B4"},
        {"fold": 4, "fit_blocks": ["B0", "B1", "B2", "B3", "B4"], "score_block": "B5"},
        {"fold": 5, "fit_blocks": ["B0", "B1", "B2", "B3", "B4", "B5"], "score_block": "B6"},
    ]
    if document["e1_chronological_layout"]["rolling_origin_folds"] != expected_folds:
        raise KxbtcdCandidateEPredeclarationError("E1 rolling-origin folds changed")

    if document["safety"]["read_only"] is not True:
        raise KxbtcdCandidateEPredeclarationError("read-only boundary changed")
    for key in (
        "candidate_fit_authorized_by_this_checkpoint",
        "paper_execution",
        "demo_execution",
        "real_money_execution",
        "order_creation",
        "order_cancellation",
        "transfers",
    ):
        if document["safety"][key] is not False:
            raise KxbtcdCandidateEPredeclarationError(f"safety flag changed: {key}")
    return recomputed


def candidate_e_predeclaration(
    path: str | Path = DEFAULT_PREDECLARATION_PATH,
) -> dict[str, Any]:
    validate_candidate_e_predeclaration(path)
    return dict(_load_json(Path(path)))


def market_logit_offset(q_market: float) -> float:
    """Frozen 0.001-clipped market-logit used only as the model offset."""
    if not math.isfinite(q_market) or not 0.0 <= q_market <= 1.0:
        raise KxbtcdCandidateEPredeclarationError("q_market must be finite in [0,1]")
    q = min(max(q_market, MODEL_LOGIT_CLIP), 1.0 - MODEL_LOGIT_CLIP)
    value = math.log(q / (1.0 - q))
    if not math.isfinite(value):
        raise KxbtcdCandidateEPredeclarationError("market logit became non-finite")
    return value


def btc_strike_log_distance_bps(spot: float, strike: float) -> float:
    """Return 10,000*ln(spot/strike), i.e. log-distance in basis-point units."""
    if not all(math.isfinite(x) and x > 0.0 for x in (spot, strike)):
        raise KxbtcdCandidateEPredeclarationError("spot and strike must be positive finite")
    value = FEATURE_SCALE * math.log(spot / strike)
    if not math.isfinite(value):
        raise KxbtcdCandidateEPredeclarationError("distance feature became non-finite")
    return value


def btc_return_5m_bps(spot_now: float, spot_5m: float) -> float:
    """Return 10,000*ln(spot_now/spot_5m), a causal five-minute log return."""
    if not all(math.isfinite(x) and x > 0.0 for x in (spot_now, spot_5m)):
        raise KxbtcdCandidateEPredeclarationError(
            "current and lookback spot must be positive finite"
        )
    value = FEATURE_SCALE * math.log(spot_now / spot_5m)
    if not math.isfinite(value):
        raise KxbtcdCandidateEPredeclarationError("5m return feature became non-finite")
    return value


def balanced_seven_block_sizes(event_count: int) -> tuple[int, ...]:
    """Outcome-blind contiguous block sizes; earlier blocks receive the remainder."""
    if event_count < 7:
        raise KxbtcdCandidateEPredeclarationError("need at least seven E1 events")
    base, remainder = divmod(event_count, 7)
    return tuple(base + (1 if i < remainder else 0) for i in range(7))


def passes_raw_advancement_gate(
    *,
    pooled_log_loss_delta: float,
    pooled_brier_delta: float,
    score_block_log_loss_deltas: Sequence[float],
    median_event_log_loss_delta: float,
    all_fits_valid: bool,
    beta_distance_by_fold: Sequence[float],
    structural_coverage_ok: bool,
    policy_firewall_ok: bool,
) -> bool:
    """Pure implementation of the frozen raw-benchmark advancement gate."""
    if len(score_block_log_loss_deltas) != 5 or len(beta_distance_by_fold) != 5:
        raise KxbtcdCandidateEPredeclarationError("raw gate requires five score folds")
    numeric = [
        pooled_log_loss_delta,
        pooled_brier_delta,
        median_event_log_loss_delta,
        *score_block_log_loss_deltas,
        *beta_distance_by_fold,
    ]
    if any(not math.isfinite(x) for x in numeric):
        return False
    return (
        pooled_log_loss_delta > 0.0
        and pooled_brier_delta >= 0.0
        and sum(delta > 0.0 for delta in score_block_log_loss_deltas) >= 4
        and score_block_log_loss_deltas[-1] > 0.0
        and median_event_log_loss_delta > 0.0
        and all_fits_valid
        and all(beta > 0.0 for beta in beta_distance_by_fold)
        and structural_coverage_ok
        and policy_firewall_ok
    )


def passes_nested_complexity_gate(
    *,
    pooled_log_loss_delta_distance_minus_momentum: float,
    pooled_brier_delta_distance_minus_momentum: float,
    score_block_log_loss_deltas_distance_minus_momentum: Sequence[float],
    median_event_log_loss_delta_distance_minus_momentum: float,
) -> bool:
    """Return whether the extra momentum coefficient earns its added complexity."""
    if len(score_block_log_loss_deltas_distance_minus_momentum) != 5:
        raise KxbtcdCandidateEPredeclarationError("complexity gate requires five score folds")
    numeric = [
        pooled_log_loss_delta_distance_minus_momentum,
        pooled_brier_delta_distance_minus_momentum,
        median_event_log_loss_delta_distance_minus_momentum,
        *score_block_log_loss_deltas_distance_minus_momentum,
    ]
    if any(not math.isfinite(x) for x in numeric):
        return False
    return (
        pooled_log_loss_delta_distance_minus_momentum > 0.0
        and pooled_brier_delta_distance_minus_momentum >= 0.0
        and sum(
            delta > 0.0
            for delta in score_block_log_loss_deltas_distance_minus_momentum
        ) >= 4
        and score_block_log_loss_deltas_distance_minus_momentum[-1] > 0.0
        and median_event_log_loss_delta_distance_minus_momentum > 0.0
    )


def select_candidate_e(
    *,
    distance_passes_raw: bool,
    momentum_passes_raw: bool,
    momentum_passes_complexity: bool,
) -> str:
    """Frozen family selection rule after the two one-time E1 evaluations."""
    if not distance_passes_raw and not momentum_passes_raw:
        return "family_FAIL"
    if distance_passes_raw and not momentum_passes_raw:
        return DISTANCE_CANDIDATE_ID
    if momentum_passes_raw and not distance_passes_raw:
        return MOMENTUM_CANDIDATE_ID
    return MOMENTUM_CANDIDATE_ID if momentum_passes_complexity else DISTANCE_CANDIDATE_ID
