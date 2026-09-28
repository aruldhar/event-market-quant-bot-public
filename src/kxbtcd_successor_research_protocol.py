"""Checkpoint 19A successor-research protocol and outcome-blind feasibility contract.

This module freezes the evidence roles and the minimum information boundary for
future KXBTCD successors.  It intentionally does not fit Candidate E, load
outcomes, access the network, or authorize execution.

The central research rule is that any successor eligible for advancement must
add at least one contemporaneous BTC-state feature whose source is independent
of Kalshi's KXBTCD market probability.  The exact Candidate-E formula remains
unfrozen until an outcome-blind source-alignment feasibility audit is complete.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Mapping, Sequence


class KxbtcdSuccessorProtocolError(ValueError):
    """Raised when Checkpoint-19A evidence or feasibility invariants are violated."""


PROTOCOL_SCHEMA_VERSION = "kxbtcd_successor_research_protocol.v1"
FEASIBILITY_ROW_SCHEMA_VERSION = "kxbtcd_independent_btc_feasibility_row.v1"
SUCCESSOR_PREDECLARATION_SCHEMA_VERSION = "kxbtcd_successor_predeclaration.v1"
CHECKPOINT_ID = "19A"

# Permanent contamination boundaries inherited from completed checkpoints.
EXPOSED_DEVELOPMENT_EVENT_COUNT = 231
EXPOSED_DEVELOPMENT_ROW_COUNT = 5364
CHECKPOINT17_TERMINAL_EVENT_COUNT = 64
CHECKPOINT17_TERMINAL_ROW_COUNT = 1014
CHECKPOINT17_TERMINAL_PROCEDURE_FINGERPRINT = (
    "bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa"
)
CHECKPOINT17_CANDIDATE_C_MODEL_FINGERPRINT = (
    "13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f"
)
CHECKPOINT18C_CANDIDATE_D_RESULT_FINGERPRINT = (
    "b72617517d7bbc3bc1e01ff332496efaf5ba0c64c5eb445f82574e63fa4a47ab"
)

EVIDENCE_TIERS = ("E0_exploratory", "E1_successor_design", "E2_final_fit", "E3_prospective_test")
INDEPENDENT_SOURCE_FAMILIES = ("coinbase", "kraken")
RAW_BENCHMARK_ID = "raw_kalshi_midpoint"
PRIMARY_METRIC = "event_equal_log_loss"
SECONDARY_METRIC = "event_equal_brier"

# CP19A does not freeze a model.  This must remain false until a later checkpoint.
CANDIDATE_E_FORMULA_FROZEN = False
CANDIDATE_E_FITTING_AUTHORIZED = False
OUTCOME_ACCESS_AUTHORIZED = False
EXECUTION_AUTHORIZED = False

FORBIDDEN_OUTCOME_FIELDS = frozenset(
    {
        "result",
        "outcome",
        "label",
        "y",
        "resolved_yes",
        "settled_yes",
        "settlement_value",
        "settlement_value_dollars",
        "expiration_value",
        "prediction",
        "p_yes",
        "candidate_probability",
        "log_loss",
        "brier",
        "raw_log_loss",
        "candidate_log_loss",
    }
)

FORBIDDEN_EXECUTION_FIELDS = frozenset(
    {
        "order_id",
        "client_order_id",
        "order_type",
        "limit_price",
        "quantity",
        "side",
        "place_order",
        "cancel_order",
        "transfer",
        "broker_action",
    }
)

FEASIBILITY_ROW_FIELDS = (
    "schema_version",
    "protocol_fingerprint",
    "state_id",
    "event_ticker",
    "market_ticker",
    "as_of_utc",
    "time_to_close_seconds",
    "strike_dollars",
    "q_market",
    "spread",
    "kalshi_raw_observation_refs",
    "coinbase_observation_available",
    "coinbase_source_id",
    "coinbase_source_event_time_utc",
    "coinbase_price",
    "coinbase_age_seconds",
    "coinbase_raw_observation_refs",
    "kraken_observation_available",
    "kraken_source_id",
    "kraken_source_event_time_utc",
    "kraken_price",
    "kraken_age_seconds",
    "kraken_raw_observation_refs",
    "cross_source_price_disagreement_bps",
    "five_minute_lookback_available_coinbase",
    "five_minute_lookback_available_kraken",
    "structurally_usable_for_design",
    "exclusion_reasons",
)


@dataclass(frozen=True)
class EvidenceTierRule:
    tier: str
    role: str
    outcomes_may_be_used: bool
    may_select_model_family: bool
    may_select_hyperparameters: bool
    may_fit_final_parameters: bool
    may_support_untouched_test_claim: bool


EVIDENCE_RULES = (
    EvidenceTierRule(
        tier="E0_exploratory",
        role="fully_exposed_historical_hypothesis_generation_only",
        outcomes_may_be_used=True,
        may_select_model_family=False,
        may_select_hyperparameters=False,
        may_fit_final_parameters=False,
        may_support_untouched_test_claim=False,
    ),
    EvidenceTierRule(
        tier="E1_successor_design",
        role="new_post_freeze_chronological_successor_selection",
        outcomes_may_be_used=True,
        may_select_model_family=True,
        may_select_hyperparameters=True,
        may_fit_final_parameters=False,
        may_support_untouched_test_claim=False,
    ),
    EvidenceTierRule(
        tier="E2_final_fit",
        role="later_chronological_parameter_estimation_for_already_selected_model",
        outcomes_may_be_used=True,
        may_select_model_family=False,
        may_select_hyperparameters=False,
        may_fit_final_parameters=True,
        may_support_untouched_test_claim=False,
    ),
    EvidenceTierRule(
        tier="E3_prospective_test",
        role="genuinely_future_one_time_terminal_evaluation_after_final_model_freeze",
        outcomes_may_be_used=True,
        may_select_model_family=False,
        may_select_hyperparameters=False,
        may_fit_final_parameters=False,
        may_support_untouched_test_claim=True,
    ),
)


def _error(message: str) -> None:
    raise KxbtcdSuccessorProtocolError(message)


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KxbtcdSuccessorProtocolError(f"{name} must be numeric") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _parse_utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be a non-empty UTC timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise KxbtcdSuccessorProtocolError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _error(f"{name} must be UTC")
    return parsed.astimezone(timezone.utc)


def _require_nonempty_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be non-empty text")
    return value.strip()


def _require_string_list(value: Any, name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        _error(f"{name} must be a list")
    if not allow_empty and not value:
        _error(f"{name} must not be empty")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_require_nonempty_text(item, f"{name}[{index}]"))
    if len(result) != len(set(result)):
        _error(f"{name} contains duplicate values")
    return tuple(result)


def protocol_definition() -> dict[str, Any]:
    """Return the exact outcome-blind Checkpoint-19A protocol definition."""

    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "checkpoint_id": CHECKPOINT_ID,
        "research_status": "protocol_and_feasibility_only",
        "contamination_boundary": {
            "E0_development_events": EXPOSED_DEVELOPMENT_EVENT_COUNT,
            "E0_development_rows": EXPOSED_DEVELOPMENT_ROW_COUNT,
            "E0_role": "fully_exposed_exploratory_evidence_only",
            "checkpoint17_terminal_events": CHECKPOINT17_TERMINAL_EVENT_COUNT,
            "checkpoint17_terminal_rows": CHECKPOINT17_TERMINAL_ROW_COUNT,
            "checkpoint17_terminal_use": "permanently_prohibited_for_successor_design_fit_or_test",
            "checkpoint17_terminal_procedure_fingerprint": CHECKPOINT17_TERMINAL_PROCEDURE_FINGERPRINT,
            "checkpoint17_candidate_c_model_fingerprint": CHECKPOINT17_CANDIDATE_C_MODEL_FINGERPRINT,
            "checkpoint18c_candidate_d_result_fingerprint": CHECKPOINT18C_CANDIDATE_D_RESULT_FINGERPRINT,
        },
        "evidence_tiers": [rule.__dict__ for rule in EVIDENCE_RULES],
        "chronology_rule": "E1_starts_after_protocol_freeze; E2_starts_after_successor_freeze; E3_starts_after_final_model_freeze",
        "non_reuse_rule": "once_outcomes_in_a_tier_are_used_that_tier_can_never_be_upgraded_to_a_stronger_evidentiary_role",
        "successor_information_rule": {
            "raw_benchmark": RAW_BENCHMARK_ID,
            "must_include_independent_btc_state": True,
            "minimum_independent_feature_count": 1,
            "initial_independent_source_families": list(INDEPENDENT_SOURCE_FAMILIES),
            "exact_source_ids_must_be_registered_and_frozen_before_E1": True,
            "kalshi_probability_only_successor_eligible": False,
            "subsecond_lead_lag_authorized": False,
        },
        "checkpoint19a_feasibility_scope": {
            "outcome_blind": True,
            "network_collection_implementation_in_this_module": False,
            "describe_source_age": True,
            "describe_cross_source_disagreement": True,
            "describe_five_minute_lookback_coverage": True,
            "derive_candidate_formula": False,
            "fit_candidate": False,
            "score_candidate": False,
            "select_event_count_from_outcomes": False,
            "sample_size_rule": "freeze_E1_E2_E3_minimum_event_and_calendar_coverage_after_outcome_blind_availability_audit",
        },
        "future_scoring_boundary": {
            "primary_metric": PRIMARY_METRIC,
            "secondary_metric": SECONDARY_METRIC,
            "benchmark": RAW_BENCHMARK_ID,
            "temporal_stability_required_for_advancement": True,
            "exact_gate_not_frozen_in_19A": True,
        },
        "candidate_e_formula_frozen": CANDIDATE_E_FORMULA_FROZEN,
        "candidate_e_fitting_authorized": CANDIDATE_E_FITTING_AUTHORIZED,
        "outcome_access_authorized": OUTCOME_ACCESS_AUTHORIZED,
        "execution_authorized": EXECUTION_AUTHORIZED,
    }


def protocol_fingerprint() -> str:
    payload = json.dumps(protocol_definition(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# Filled after the protocol object is finalized.  validate_protocol() makes drift fail closed.
FROZEN_PROTOCOL_FINGERPRINT = "b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8"


def validate_protocol() -> None:
    if tuple(rule.tier for rule in EVIDENCE_RULES) != EVIDENCE_TIERS:
        _error("evidence tier order changed")
    if CANDIDATE_E_FORMULA_FROZEN:
        _error("Checkpoint 19A must not freeze Candidate E's exact formula")
    if CANDIDATE_E_FITTING_AUTHORIZED or OUTCOME_ACCESS_AUTHORIZED or EXECUTION_AUTHORIZED:
        _error("Checkpoint 19A must remain no-fit, outcome-blind, and execution-free")
    if protocol_definition()["successor_information_rule"]["must_include_independent_btc_state"] is not True:
        _error("independent BTC-state requirement was removed")
    if protocol_definition()["successor_information_rule"]["kalshi_probability_only_successor_eligible"] is not False:
        _error("Kalshi-probability-only successors must remain ineligible")
    if protocol_fingerprint() != FROZEN_PROTOCOL_FINGERPRINT:
        _error("Checkpoint-19A protocol fingerprint changed")


def validate_evidence_transition(*, from_tier: str, to_tier: str, source_outcomes_used: bool) -> None:
    """Fail closed when evidence is reused or upgraded after outcome exposure."""

    if from_tier not in EVIDENCE_TIERS or to_tier not in EVIDENCE_TIERS:
        _error("unknown evidence tier")
    from_index = EVIDENCE_TIERS.index(from_tier)
    to_index = EVIDENCE_TIERS.index(to_tier)
    if source_outcomes_used and to_index > from_index:
        _error("outcome-exposed evidence cannot be upgraded to a stronger evidentiary role")
    if to_index < from_index:
        _error("later evidence cohorts cannot be reassigned backward")


def validate_successor_predeclaration(spec: Mapping[str, Any]) -> None:
    """Validate the minimum future successor boundary without defining Candidate E now."""

    if not isinstance(spec, Mapping):
        _error("successor predeclaration must be a mapping")
    if spec.get("schema_version") != SUCCESSOR_PREDECLARATION_SCHEMA_VERSION:
        _error("successor predeclaration schema_version mismatch")
    if spec.get("protocol_fingerprint") != FROZEN_PROTOCOL_FINGERPRINT:
        _error("successor predeclaration does not bind the frozen Checkpoint-19A protocol")
    _require_nonempty_text(spec.get("model_id"), "model_id")

    if spec.get("benchmark") != RAW_BENCHMARK_ID:
        _error("raw Kalshi midpoint must remain the benchmark")
    if spec.get("uses_checkpoint17_terminal") is not False:
        _error("Checkpoint-17 terminal evidence is permanently prohibited")
    if spec.get("uses_exposed_E0_for_advancement") is not False:
        _error("E0 may not support successor advancement")
    if spec.get("subsecond_lead_lag") is not False:
        _error("sub-second lead/lag remains unauthorized")
    if spec.get("execution_authorized") is not False:
        _error("execution remains unauthorized")

    features = spec.get("features")
    if not isinstance(features, list) or not features:
        _error("successor must declare features")
    independent_count = 0
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping):
            _error(f"features[{index}] must be a mapping")
        _require_nonempty_text(feature.get("name"), f"features[{index}].name")
        source_family = _require_nonempty_text(feature.get("source_family"), f"features[{index}].source_family")
        independent = feature.get("independent_of_kalshi_probability")
        if independent is True:
            independent_count += 1
            if source_family not in INDEPENDENT_SOURCE_FAMILIES:
                _error(
                    f"independent feature source_family {source_family!r} is not in the frozen initial source-family set"
                )
    if independent_count < 1:
        _error("advancing successor must include at least one independent BTC-state feature")


def validate_feasibility_row(row: Mapping[str, Any]) -> None:
    """Validate one outcome-blind source-alignment diagnostic row."""

    validate_protocol()
    if not isinstance(row, Mapping):
        _error("feasibility row must be a mapping")
    missing = set(FEASIBILITY_ROW_FIELDS) - set(row)
    extra = set(row) - set(FEASIBILITY_ROW_FIELDS)
    if missing:
        _error(f"feasibility row missing fields: {sorted(missing)}")
    if extra:
        _error(f"feasibility row contains unexpected fields: {sorted(extra)}")
    leaked = FORBIDDEN_OUTCOME_FIELDS.intersection(row)
    if leaked:
        _error(f"feasibility row contains outcome/model-score fields: {sorted(leaked)}")
    execution = FORBIDDEN_EXECUTION_FIELDS.intersection(row)
    if execution:
        _error(f"feasibility row contains execution fields: {sorted(execution)}")

    if row["schema_version"] != FEASIBILITY_ROW_SCHEMA_VERSION:
        _error("feasibility row schema_version mismatch")
    if row["protocol_fingerprint"] != FROZEN_PROTOCOL_FINGERPRINT:
        _error("feasibility row protocol fingerprint mismatch")

    for field in ("state_id", "event_ticker", "market_ticker"):
        _require_nonempty_text(row[field], field)
    as_of = _parse_utc(row["as_of_utc"], "as_of_utc")
    ttc = _decimal(row["time_to_close_seconds"], "time_to_close_seconds")
    strike = _decimal(row["strike_dollars"], "strike_dollars")
    q_market = _decimal(row["q_market"], "q_market")
    spread = _decimal(row["spread"], "spread")
    if ttc < 0 or strike <= 0 or q_market < 0 or q_market > 1 or spread < 0:
        _error("invalid KXBTCD state values")
    _require_string_list(row["kalshi_raw_observation_refs"], "kalshi_raw_observation_refs")

    availability: dict[str, bool] = {}
    for family in INDEPENDENT_SOURCE_FAMILIES:
        available = row[f"{family}_observation_available"]
        if not isinstance(available, bool):
            _error(f"{family}_observation_available must be boolean")
        availability[family] = available
        refs = row[f"{family}_raw_observation_refs"]
        if available:
            source_id = _require_nonempty_text(row[f"{family}_source_id"], f"{family}_source_id")
            if family not in source_id.lower():
                _error(f"{family}_source_id must identify the {family} source family")
            source_time = _parse_utc(row[f"{family}_source_event_time_utc"], f"{family}_source_event_time_utc")
            if source_time > as_of:
                _error(f"{family} observation is from the future relative to as_of_utc")
            price = _decimal(row[f"{family}_price"], f"{family}_price")
            age = _decimal(row[f"{family}_age_seconds"], f"{family}_age_seconds")
            if price <= 0 or age < 0:
                _error(f"{family} price must be positive and age nonnegative")
            _require_string_list(refs, f"{family}_raw_observation_refs")
        else:
            if row[f"{family}_source_id"] is not None:
                _error(f"{family}_source_id must be null when unavailable")
            if row[f"{family}_source_event_time_utc"] is not None:
                _error(f"{family}_source_event_time_utc must be null when unavailable")
            if row[f"{family}_price"] is not None or row[f"{family}_age_seconds"] is not None:
                _error(f"{family} price/age must be null when unavailable")
            if refs != []:
                _error(f"{family}_raw_observation_refs must be empty when unavailable")

        lookback = row[f"five_minute_lookback_available_{family}"]
        if not isinstance(lookback, bool):
            _error(f"five_minute_lookback_available_{family} must be boolean")
        if lookback and not available:
            _error(f"five-minute {family} lookback cannot be available without contemporaneous observation")

    disagreement = row["cross_source_price_disagreement_bps"]
    if availability["coinbase"] and availability["kraken"]:
        if disagreement is None:
            _error("cross-source disagreement must be populated when both sources are available")
        if _decimal(disagreement, "cross_source_price_disagreement_bps") < 0:
            _error("cross-source disagreement must be nonnegative")
    elif disagreement is not None:
        _error("cross-source disagreement must be null unless both sources are available")

    usable = row["structurally_usable_for_design"]
    if not isinstance(usable, bool):
        _error("structurally_usable_for_design must be boolean")
    reasons = _require_string_list(row["exclusion_reasons"], "exclusion_reasons", allow_empty=True)
    if usable and reasons:
        _error("usable feasibility row cannot contain exclusion reasons")
    if not usable and not reasons:
        _error("unusable feasibility row must state at least one exclusion reason")


def feasibility_contract_definition() -> dict[str, Any]:
    return {
        "schema_version": FEASIBILITY_ROW_SCHEMA_VERSION,
        "protocol_fingerprint": FROZEN_PROTOCOL_FINGERPRINT,
        "fields": list(FEASIBILITY_ROW_FIELDS),
        "outcome_fields_allowed": False,
        "future_observations_allowed": False,
        "interpolation_allowed": False,
        "descriptive_only": True,
        "candidate_formula_selection_allowed": False,
        "candidate_fitting_allowed": False,
        "execution_authorized": False,
    }
