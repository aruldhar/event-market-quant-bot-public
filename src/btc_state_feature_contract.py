"""Minimal shared BTC-state feature contract for Checkpoint 12.

This module is intentionally model-free and execution-free. It defines
versioned contracts for six separated layers:

1. raw/source observation references,
2. synchronized contemporaneous BTC state,
3. product-specific labels,
4. model outputs,
5. product-specific valuation/economics,
6. read-only research decision policy.

The validators are deterministic and side-effect free. They do not perform
network access, open labels, fit models, or place/cancel orders.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


class BtcStateFeatureContractError(ValueError):
    """Raised when a row violates the shared BTC-state feature contract."""


CONTRACT_SCHEMA_VERSION = "btc_state_feature_contract.v1"
RAW_OBSERVATION_REF_SCHEMA_VERSION = "btc_raw_source_observation_ref.v1"
STATE_SCHEMA_VERSION = "btc_synchronized_state.v1"
LABEL_SCHEMA_VERSION = "btc_product_label.v1"
MODEL_OUTPUT_SCHEMA_VERSION = "btc_model_output.v1"
ECONOMICS_SCHEMA_VERSION = "btc_product_economics.v1"
DECISION_SCHEMA_VERSION = "btc_research_decision.v1"

PRODUCT_HEADS = frozenset({"KXBTCD", "KXBTCPERP"})
PRIMARY_PRODUCT_HEAD = "KXBTCD"
SECONDARY_PRODUCT_HEAD = "KXBTCPERP"

STATE_VIEW_VALUES = frozenset({"live_first_seen", "historical_reconstructed"})

STATE_QUALITY_VALUES = frozenset(
    {
        "usable",
        "blocked_clock_health",
        "blocked_continuity_gap",
        "blocked_stale_data",
        "blocked_source_unavailable",
        "blocked_schema_drift",
        "blocked_incomplete_state",
    }
)

CLOCK_HEALTH_VALUES = frozenset({"unresolved", "not_required", "pass", "fail"})

RAW_OBSERVATION_REF_FIELDS = (
    "schema_version",
    "raw_observation_id",
    "source_id",
    "instrument_id",
    "source_session_id",
    "source_sequence_or_message_id",
    "source_event_time_utc",
    "relay_or_publication_time_utc",
    "local_receive_utc",
    "local_receive_monotonic_ns",
    "raw_payload_reference",
    "raw_payload_sha256",
)

FEATURE_FIELDS = (
    "feature_id",
    "source_id",
    "instrument_id",
    "feature_class",
    "value",
    "source_observation_refs",
    "lookback_seconds",
    "lead_lag_seconds",
)

STATE_FIELDS = (
    "schema_version",
    "state_id",
    "product_head",
    "state_view",
    "as_of_utc",
    "as_of_local_monotonic_ns",
    "alignment_epoch_id",
    "state_quality",
    "clock_health_status",
    "raw_observation_refs",
    "btc_features",
    "source_age_seconds_by_source",
    "product_context",
)

KXBTCD_CONTEXT_FIELDS = (
    "event_ticker",
    "market_ticker",
    "settlement_regime_id",
    "strike_dollars",
    "time_to_close_seconds",
    "yes_bid",
    "yes_ask",
    "midpoint",
    "spread",
)

KXBTCPERP_CONTEXT_FIELDS = (
    "instrument_id",
    "mark_or_mid_price",
)

LABEL_FIELDS = (
    "schema_version",
    "label_id",
    "product_head",
    "label_type",
    "value",
    "label_source",
    "raw_observation_refs",
    "product_context",
)

MODEL_OUTPUT_FIELDS = (
    "schema_version",
    "model_output_id",
    "product_head",
    "state_id",
    "model_id",
    "model_version",
    "output_type",
    "value",
    "created_at_utc",
    "training_window_id",
)

ECONOMICS_FIELDS = (
    "schema_version",
    "economics_id",
    "product_head",
    "state_id",
    "model_output_id",
    "valuation_type",
    "inputs",
    "outputs",
)

DECISION_FIELDS = (
    "schema_version",
    "decision_id",
    "product_head",
    "state_id",
    "economics_id",
    "policy_id",
    "decision",
    "blocked_reasons",
)

FORBIDDEN_STATE_FIELDS = frozenset(
    {
        "result",
        "outcome",
        "label",
        "y",
        "settled_yes",
        "settlement_value",
        "settlement_value_dollars",
        "expiration_value",
        "future_return",
        "forward_return",
        "future_volatility",
        "realized_future_volatility",
        "p_yes",
        "prediction",
        "model_output",
        "gross_edge",
        "net_edge",
        "expected_pnl",
        "decision",
        "action",
        "order",
        "order_id",
    }
)

FORBIDDEN_FEATURE_ID_TOKENS = (
    "future_",
    "forward_return",
    "future_return",
    "future_volatility",
    "settled",
    "settlement_value",
    "expiration_value",
    "outcome",
    "label",
)

FORBIDDEN_EXECUTION_FIELDS = frozenset(
    {
        "order_id",
        "client_order_id",
        "order_type",
        "limit_price",
        "quantity",
        "side",
        "cancel_order",
        "place_order",
        "transfer",
        "portfolio_transfer",
        "broker_action",
    }
)

RESEARCH_DECISIONS = frozenset(
    {
        "no_signal",
        "research_yes_candidate",
        "research_no_candidate",
        "research_long_candidate",
        "research_short_candidate",
        "blocked_data_quality",
        "blocked_clock_health",
        "blocked_policy",
    }
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _error(message: str) -> None:
    raise BtcStateFeatureContractError(message)


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _error(f"{name} must be a mapping")
    return value


def _require_exact_keys(row: Mapping[str, Any], expected: Sequence[str], name: str) -> None:
    expected_set = set(expected)
    actual_set = set(row)
    missing = expected_set - actual_set
    extra = actual_set - expected_set
    if missing:
        _error(f"{name} missing required fields: {sorted(missing)}")
    if extra:
        _error(f"{name} contains unexpected fields: {sorted(extra)}")


def _require_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be a non-empty string")
    return value.strip()


def _require_optional_string(value: Any, name: str) -> None:
    if value is not None and not isinstance(value, str):
        _error(f"{name} must be text or null")


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BtcStateFeatureContractError(f"{name} must be numeric") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _nonnegative_decimal(value: Any, name: str) -> Decimal:
    result = _decimal(value, name)
    if result < 0:
        _error(f"{name} must be nonnegative")
    return result


def _probability(value: Any, name: str) -> Decimal:
    result = _decimal(value, name)
    if result < 0 or result > 1:
        _error(f"{name} must be within [0, 1]")
    return result


def _require_string_list(value: Any, name: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list):
        _error(f"{name} must be a list")
    if nonempty and not value:
        _error(f"{name} must not be empty")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_require_nonempty_string(item, f"{name}[{index}]"))
    if len(result) != len(set(result)):
        _error(f"{name} contains duplicate identifiers")
    return tuple(result)


def _reject_forbidden_fields(row: Mapping[str, Any], forbidden: frozenset[str], name: str) -> None:
    present = forbidden.intersection(row)
    if present:
        _error(f"{name} contains forbidden fields: {sorted(present)}")


def contract_definition() -> dict[str, Any]:
    """Return the versioned contract definition used for fingerprinting."""

    return {
        "contract_schema_version": CONTRACT_SCHEMA_VERSION,
        "architecture": "shared_btc_state_with_separate_product_heads",
        "product_heads": sorted(PRODUCT_HEADS),
        "primary_product_head": PRIMARY_PRODUCT_HEAD,
        "secondary_product_head": SECONDARY_PRODUCT_HEAD,
        "joint_multitask_model_authorized": False,
        "raw_preservation_required_before_transformation": True,
        "raw_observation_ref_fields": list(RAW_OBSERVATION_REF_FIELDS),
        "feature_fields": list(FEATURE_FIELDS),
        "state_fields": list(STATE_FIELDS),
        "state_view_values": sorted(STATE_VIEW_VALUES),
        "kxbtcd_context_fields": list(KXBTCD_CONTEXT_FIELDS),
        "kxbtcperp_context_fields": list(KXBTCPERP_CONTEXT_FIELDS),
        "label_fields": list(LABEL_FIELDS),
        "model_output_fields": list(MODEL_OUTPUT_FIELDS),
        "economics_fields": list(ECONOMICS_FIELDS),
        "decision_fields": list(DECISION_FIELDS),
        "forbidden_state_fields": sorted(FORBIDDEN_STATE_FIELDS),
        "subsecond_lead_lag_policy": "blocked_until_clock_health_policy_resolved",
        "model_use_quality_rule": "state_quality_must_equal_usable",
        "historical_reconstruction_rule": (
            "historical_reconstructed states are valid for offline analysis only; "
            "local_receive_monotonic_ns records reconstruction-time availability and "
            "must not be interpreted as historical live causality"
        ),
        "live_causal_rule": "live decision paths require state_view=live_first_seen",
        "decision_scope": "read_only_research_only",
        "execution_authorized": False,
    }


def contract_fingerprint() -> str:
    payload = json.dumps(contract_definition(), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def validate_schema_contract() -> None:
    schemas = {
        "raw_observation_ref": RAW_OBSERVATION_REF_FIELDS,
        "feature": FEATURE_FIELDS,
        "state": STATE_FIELDS,
        "kxbtcd_context": KXBTCD_CONTEXT_FIELDS,
        "kxbtcperp_context": KXBTCPERP_CONTEXT_FIELDS,
        "label": LABEL_FIELDS,
        "model_output": MODEL_OUTPUT_FIELDS,
        "economics": ECONOMICS_FIELDS,
        "decision": DECISION_FIELDS,
    }
    for name, fields in schemas.items():
        if len(fields) != len(set(fields)):
            _error(f"{name} schema contains duplicate fields")

    leaked = FORBIDDEN_STATE_FIELDS.intersection(STATE_FIELDS)
    if leaked:
        _error(f"state schema contains forbidden cross-layer fields: {sorted(leaked)}")

    for required in ("strike_dollars", "time_to_close_seconds"):
        if required not in KXBTCD_CONTEXT_FIELDS:
            _error(f"KXBTCD context missing mandatory state variable {required}")

    if contract_definition()["joint_multitask_model_authorized"] is not False:
        _error("joint multitask modeling must remain unauthorized")
    if contract_definition()["execution_authorized"] is not False:
        _error("execution must remain unauthorized")


def validate_raw_observation_ref(row: Mapping[str, Any]) -> None:
    row = _require_mapping(row, "raw observation ref")
    _require_exact_keys(row, RAW_OBSERVATION_REF_FIELDS, "raw observation ref")
    if row["schema_version"] != RAW_OBSERVATION_REF_SCHEMA_VERSION:
        _error("raw observation ref schema_version mismatch")

    for field in (
        "raw_observation_id",
        "source_id",
        "instrument_id",
        "source_session_id",
        "local_receive_utc",
        "raw_payload_reference",
        "raw_payload_sha256",
    ):
        _require_nonempty_string(row[field], f"raw observation ref.{field}")

    for field in (
        "source_sequence_or_message_id",
        "source_event_time_utc",
        "relay_or_publication_time_utc",
    ):
        _require_optional_string(row[field], f"raw observation ref.{field}")

    monotonic_ns = row["local_receive_monotonic_ns"]
    if not isinstance(monotonic_ns, int) or isinstance(monotonic_ns, bool) or monotonic_ns < 0:
        _error("raw observation ref.local_receive_monotonic_ns must be a nonnegative integer")

    digest = row["raw_payload_sha256"]
    if not _SHA256_RE.fullmatch(digest):
        _error("raw observation ref.raw_payload_sha256 must be a lowercase SHA-256 digest")


def validate_feature(feature: Mapping[str, Any], *, state_raw_refs: set[str]) -> None:
    feature = _require_mapping(feature, "feature")
    _require_exact_keys(feature, FEATURE_FIELDS, "feature")

    feature_id = _require_nonempty_string(feature["feature_id"], "feature.feature_id")
    _require_nonempty_string(feature["source_id"], "feature.source_id")
    _require_nonempty_string(feature["instrument_id"], "feature.instrument_id")
    feature_class = _require_nonempty_string(feature["feature_class"], "feature.feature_class")
    _decimal(feature["value"], "feature.value")

    lowered = feature_id.lower()
    if any(token in lowered for token in FORBIDDEN_FEATURE_ID_TOKENS):
        _error(f"feature.feature_id appears to encode a future/label field: {feature_id!r}")

    refs = set(_require_string_list(feature["source_observation_refs"], "feature.source_observation_refs"))
    unknown = refs - state_raw_refs
    if unknown:
        _error(f"feature references raw observations absent from state lineage: {sorted(unknown)}")

    lookback = feature["lookback_seconds"]
    if lookback is not None:
        _nonnegative_decimal(lookback, "feature.lookback_seconds")

    lead_lag = feature["lead_lag_seconds"]
    if lead_lag is not None:
        lead_lag_value = _decimal(lead_lag, "feature.lead_lag_seconds")
        if feature_class != "lead_lag":
            _error("feature.lead_lag_seconds may be set only for feature_class='lead_lag'")
        if abs(lead_lag_value) < Decimal("1"):
            _error("sub-second lead/lag features are blocked until clock-health policy is resolved")
    elif feature_class == "lead_lag":
        _error("lead_lag features must declare lead_lag_seconds")


def validate_kxbtcd_product_context(context: Mapping[str, Any]) -> None:
    context = _require_mapping(context, "KXBTCD product_context")
    _require_exact_keys(context, KXBTCD_CONTEXT_FIELDS, "KXBTCD product_context")

    _require_nonempty_string(context["event_ticker"], "KXBTCD product_context.event_ticker")
    _require_nonempty_string(context["market_ticker"], "KXBTCD product_context.market_ticker")
    _require_nonempty_string(
        context["settlement_regime_id"], "KXBTCD product_context.settlement_regime_id"
    )

    strike = _decimal(context["strike_dollars"], "KXBTCD product_context.strike_dollars")
    if strike <= 0:
        _error("KXBTCD product_context.strike_dollars must be positive")

    _nonnegative_decimal(
        context["time_to_close_seconds"], "KXBTCD product_context.time_to_close_seconds"
    )
    bid = _probability(context["yes_bid"], "KXBTCD product_context.yes_bid")
    ask = _probability(context["yes_ask"], "KXBTCD product_context.yes_ask")
    midpoint = _probability(context["midpoint"], "KXBTCD product_context.midpoint")
    spread = _nonnegative_decimal(context["spread"], "KXBTCD product_context.spread")

    if bid > ask:
        _error("KXBTCD YES bid must not exceed YES ask")
    expected_midpoint = (bid + ask) / Decimal("2")
    expected_spread = ask - bid
    tolerance = Decimal("0.000000001")
    if abs(midpoint - expected_midpoint) > tolerance:
        _error("KXBTCD midpoint must equal (yes_bid + yes_ask) / 2")
    if abs(spread - expected_spread) > tolerance:
        _error("KXBTCD spread must equal yes_ask - yes_bid")


def validate_kxbtcperp_product_context(context: Mapping[str, Any]) -> None:
    context = _require_mapping(context, "KXBTCPERP product_context")
    _require_exact_keys(context, KXBTCPERP_CONTEXT_FIELDS, "KXBTCPERP product_context")
    _require_nonempty_string(context["instrument_id"], "KXBTCPERP product_context.instrument_id")
    price = _decimal(context["mark_or_mid_price"], "KXBTCPERP product_context.mark_or_mid_price")
    if price <= 0:
        _error("KXBTCPERP product_context.mark_or_mid_price must be positive")


def validate_synchronized_state(row: Mapping[str, Any]) -> None:
    row = _require_mapping(row, "synchronized state")
    _require_exact_keys(row, STATE_FIELDS, "synchronized state")
    _reject_forbidden_fields(row, FORBIDDEN_STATE_FIELDS, "synchronized state")

    if row["schema_version"] != STATE_SCHEMA_VERSION:
        _error("synchronized state schema_version mismatch")

    _require_nonempty_string(row["state_id"], "synchronized state.state_id")
    product_head = _require_nonempty_string(row["product_head"], "synchronized state.product_head")
    if product_head not in PRODUCT_HEADS:
        _error(f"unsupported product_head: {product_head!r}")
    state_view = _require_nonempty_string(row["state_view"], "synchronized state.state_view")
    if state_view not in STATE_VIEW_VALUES:
        _error(f"unsupported state_view: {state_view!r}")
    _require_nonempty_string(row["as_of_utc"], "synchronized state.as_of_utc")
    monotonic_ns = row["as_of_local_monotonic_ns"]
    if not isinstance(monotonic_ns, int) or isinstance(monotonic_ns, bool) or monotonic_ns < 0:
        _error("synchronized state.as_of_local_monotonic_ns must be a nonnegative integer")
    _require_nonempty_string(row["alignment_epoch_id"], "synchronized state.alignment_epoch_id")

    state_quality = _require_nonempty_string(row["state_quality"], "synchronized state.state_quality")
    if state_quality not in STATE_QUALITY_VALUES:
        _error(f"unsupported state_quality: {state_quality!r}")
    clock_health = _require_nonempty_string(
        row["clock_health_status"], "synchronized state.clock_health_status"
    )
    if clock_health not in CLOCK_HEALTH_VALUES:
        _error(f"unsupported clock_health_status: {clock_health!r}")

    raw_refs = set(_require_string_list(row["raw_observation_refs"], "synchronized state.raw_observation_refs"))

    features = row["btc_features"]
    if not isinstance(features, list):
        _error("synchronized state.btc_features must be a list")
    feature_ids: set[str] = set()
    for feature in features:
        validate_feature(feature, state_raw_refs=raw_refs)
        feature_id = str(feature["feature_id"])
        if feature_id in feature_ids:
            _error(f"duplicate feature_id in synchronized state: {feature_id!r}")
        feature_ids.add(feature_id)

    source_ages = _require_mapping(
        row["source_age_seconds_by_source"], "synchronized state.source_age_seconds_by_source"
    )
    for source_id, age in source_ages.items():
        _require_nonempty_string(source_id, "source_age_seconds_by_source key")
        _nonnegative_decimal(age, f"source_age_seconds_by_source[{source_id!r}]")

    context = _require_mapping(row["product_context"], "synchronized state.product_context")
    if product_head == "KXBTCD":
        validate_kxbtcd_product_context(context)
    elif product_head == "KXBTCPERP":
        validate_kxbtcperp_product_context(context)


def validate_state_for_model_use(row: Mapping[str, Any]) -> None:
    """Fail closed unless a synchronized state is explicitly usable for modeling."""

    validate_synchronized_state(row)
    if row["state_quality"] != "usable":
        _error(f"state is not usable for model input: {row['state_quality']!r}")


def validate_state_for_live_causal_use(row: Mapping[str, Any]) -> None:
    """Fail closed unless a state was actually first-seen in the live causal view."""

    validate_state_for_model_use(row)
    if row["state_view"] != "live_first_seen":
        _error(
            "historical_reconstructed state cannot be used as live-causal input; "
            "reconstruction-time receipt does not prove historical live availability"
        )


def validate_product_label(row: Mapping[str, Any]) -> None:
    row = _require_mapping(row, "product label")
    _require_exact_keys(row, LABEL_FIELDS, "product label")
    if row["schema_version"] != LABEL_SCHEMA_VERSION:
        _error("product label schema_version mismatch")
    _require_nonempty_string(row["label_id"], "product label.label_id")
    product_head = _require_nonempty_string(row["product_head"], "product label.product_head")
    if product_head not in PRODUCT_HEADS:
        _error(f"unsupported product label head: {product_head!r}")
    label_type = _require_nonempty_string(row["label_type"], "product label.label_type")
    _require_nonempty_string(row["label_source"], "product label.label_source")
    _require_string_list(row["raw_observation_refs"], "product label.raw_observation_refs")
    context = _require_mapping(row["product_context"], "product label.product_context")

    if product_head == "KXBTCD":
        if label_type != "kxbtcd_settled_yes":
            _error("KXBTCD label_type must be 'kxbtcd_settled_yes'")
        value = _decimal(row["value"], "product label.value")
        if value not in {Decimal("0"), Decimal("1")}:
            _error("KXBTCD settled label must be 0 or 1")
        for required in (
            "event_ticker",
            "market_ticker",
            "settlement_primitive_id",
            "settlement_regime_id",
        ):
            _require_nonempty_string(context.get(required), f"product label.product_context.{required}")
    else:
        if label_type not in {"forward_return", "realized_volatility"}:
            _error("KXBTCPERP label_type must be forward_return or realized_volatility")
        _decimal(row["value"], "product label.value")
        if "horizon_seconds" not in context:
            _error("KXBTCPERP product label must declare horizon_seconds")
        _nonnegative_decimal(context["horizon_seconds"], "product label.product_context.horizon_seconds")


def validate_model_output(row: Mapping[str, Any]) -> None:
    row = _require_mapping(row, "model output")
    _require_exact_keys(row, MODEL_OUTPUT_FIELDS, "model output")
    if row["schema_version"] != MODEL_OUTPUT_SCHEMA_VERSION:
        _error("model output schema_version mismatch")
    for field in (
        "model_output_id",
        "product_head",
        "state_id",
        "model_id",
        "model_version",
        "output_type",
        "created_at_utc",
        "training_window_id",
    ):
        _require_nonempty_string(row[field], f"model output.{field}")
    if row["product_head"] not in PRODUCT_HEADS:
        _error(f"unsupported model output head: {row['product_head']!r}")

    if row["product_head"] == "KXBTCD":
        if row["output_type"] != "p_yes":
            _error("KXBTCD model output_type must be 'p_yes'")
        _probability(row["value"], "model output.value")
    else:
        if row["output_type"] not in {"expected_forward_return", "expected_realized_volatility"}:
            _error("unsupported KXBTCPERP output_type")
        _decimal(row["value"], "model output.value")


def validate_product_economics(row: Mapping[str, Any]) -> None:
    row = _require_mapping(row, "product economics")
    _require_exact_keys(row, ECONOMICS_FIELDS, "product economics")
    if row["schema_version"] != ECONOMICS_SCHEMA_VERSION:
        _error("product economics schema_version mismatch")
    for field in (
        "economics_id",
        "product_head",
        "state_id",
        "model_output_id",
        "valuation_type",
    ):
        _require_nonempty_string(row[field], f"product economics.{field}")
    if row["product_head"] not in PRODUCT_HEADS:
        _error(f"unsupported product economics head: {row['product_head']!r}")
    inputs = _require_mapping(row["inputs"], "product economics.inputs")
    outputs = _require_mapping(row["outputs"], "product economics.outputs")
    _reject_forbidden_fields(inputs, FORBIDDEN_EXECUTION_FIELDS, "product economics.inputs")
    _reject_forbidden_fields(outputs, FORBIDDEN_EXECUTION_FIELDS, "product economics.outputs")


def validate_research_decision(row: Mapping[str, Any]) -> None:
    row = _require_mapping(row, "research decision")
    _require_exact_keys(row, DECISION_FIELDS, "research decision")
    if row["schema_version"] != DECISION_SCHEMA_VERSION:
        _error("research decision schema_version mismatch")
    for field in (
        "decision_id",
        "product_head",
        "state_id",
        "economics_id",
        "policy_id",
        "decision",
    ):
        _require_nonempty_string(row[field], f"research decision.{field}")
    if row["product_head"] not in PRODUCT_HEADS:
        _error(f"unsupported research decision head: {row['product_head']!r}")
    if row["decision"] not in RESEARCH_DECISIONS:
        _error(f"execution or unsupported decision is prohibited: {row['decision']!r}")
    _require_string_list(row["blocked_reasons"], "research decision.blocked_reasons", nonempty=False)
    _reject_forbidden_fields(row, FORBIDDEN_EXECUTION_FIELDS, "research decision")


validate_schema_contract()
