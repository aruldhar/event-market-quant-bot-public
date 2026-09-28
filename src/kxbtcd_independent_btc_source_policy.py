"""Frozen Checkpoint-19D-B independent-BTC source policy helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

POLICY_PATH = Path("configs/kxbtcd_independent_btc_source_policy.json")
EXPECTED_SCHEMA = "kxbtcd_independent_btc_source_policy.v1"
EXPECTED_POLICY_ID = "kxbtcd_independent_btc_source_policy.v1"
EXPECTED_POLICY_FINGERPRINT = "6b0d98c16a65b2e638b36991d5006031e1bd37048bd04a47a3f67d936df0ee18"
EXPECTED_PROTOCOL_FINGERPRINT = "b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8"
EXPECTED_19C_AUDIT_FINGERPRINT = "4cdb9b8f2cd5d4396d470df04e4c3f88ff1e3f91cce25cd3e57543ea97c8490d"
EXPECTED_19D_A_AUDIT_FINGERPRINT = "023ca51e1e21180b9adecd1d4b78fd4c3372f1aab3a986988c8eb4bc4806721c"

LIVE_PRIMARY_SOURCE_ID = "coinbase.exchange.public_rest.product_book.btc_usd.v1"
LIVE_VERIFIER_SOURCE_ID = "kraken.spot.public_rest.pretrade.btc_usd.v1"
HISTORICAL_PRIMARY_SOURCE_ID = "coinbase.exchange.public_rest.product_candles.btc_usd.1m.v1"
HISTORICAL_VERIFIER_SOURCE_ID = "kraken.spot.public_rest.posttrade.btc_usd.v1"


class KxbtcdIndependentBtcSourcePolicyError(RuntimeError):
    """Raised when the frozen 19D-B source policy is violated."""


@dataclass(frozen=True)
class LiveSourceDecision:
    eligible: bool
    primary_price: float | None
    verifier_price: float | None
    disagreement_bps: float | None
    exclusion_reasons: tuple[str, ...]


def _canonical_without_fingerprint(data: Mapping[str, Any]) -> bytes:
    body = dict(data)
    body.pop("policy_fingerprint", None)
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def load_and_validate_policy(path: str | Path = POLICY_PATH) -> dict[str, Any]:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdIndependentBtcSourcePolicyError(
            f"Could not load source policy {path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise KxbtcdIndependentBtcSourcePolicyError("source policy root must be object")

    required = {
        "schema_version",
        "policy_id",
        "checkpoint_id",
        "parent_protocol_fingerprint",
        "parent_19c_audit_fingerprint",
        "parent_19d_a_audit_fingerprint",
        "evidence_boundary",
        "source_roles",
        "live_construction",
        "historical_construction",
        "live_quality_gates",
        "causal_lookback_policy",
        "evidence_tiers",
        "cohort_extension_rule",
        "outcome_blind_evidence_used",
        "policy_fingerprint",
    }
    if set(data) != required:
        raise KxbtcdIndependentBtcSourcePolicyError(
            f"source policy keys mismatch: missing={sorted(required-set(data))}, "
            f"extra={sorted(set(data)-required)}"
        )

    exact = {
        "schema_version": EXPECTED_SCHEMA,
        "policy_id": EXPECTED_POLICY_ID,
        "checkpoint_id": "19D-B",
        "parent_protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "parent_19c_audit_fingerprint": EXPECTED_19C_AUDIT_FINGERPRINT,
        "parent_19d_a_audit_fingerprint": EXPECTED_19D_A_AUDIT_FINGERPRINT,
        "policy_fingerprint": EXPECTED_POLICY_FINGERPRINT,
    }
    for key, expected in exact.items():
        if data[key] != expected:
            raise KxbtcdIndependentBtcSourcePolicyError(
                f"{key} mismatch: expected {expected!r}, got {data[key]!r}"
            )

    actual_fp = hashlib.sha256(_canonical_without_fingerprint(data)).hexdigest()
    if actual_fp != EXPECTED_POLICY_FINGERPRINT:
        raise KxbtcdIndependentBtcSourcePolicyError(
            f"source policy content fingerprint mismatch: {actual_fp}"
        )

    boundary = data["evidence_boundary"]
    forbidden_true = (
        "outcomes_used_to_select_policy",
        "checkpoint17_terminal_used",
        "candidate_e_formula_frozen",
        "candidate_e_fitting_authorized",
        "execution_authorized",
        "subsecond_lead_lag_authorized",
    )
    for key in forbidden_true:
        if boundary.get(key) is not False:
            raise KxbtcdIndependentBtcSourcePolicyError(
                f"evidence boundary requires {key}=false"
            )

    roles = data["source_roles"]
    expected_roles = {
        "live_primary": LIVE_PRIMARY_SOURCE_ID,
        "live_verifier": LIVE_VERIFIER_SOURCE_ID,
        "historical_primary": HISTORICAL_PRIMARY_SOURCE_ID,
        "historical_verifier": HISTORICAL_VERIFIER_SOURCE_ID,
    }
    if roles != expected_roles:
        raise KxbtcdIndependentBtcSourcePolicyError("source roles changed")

    gates = data["live_quality_gates"]
    expected_gate_values = {
        "max_coinbase_local_first_seen_age_seconds": 5.0,
        "max_kraken_local_first_seen_age_seconds": 5.0,
        "max_coinbase_source_event_age_seconds": 10.0,
        "max_kraken_conservative_bbo_publication_age_seconds": 60.0,
        "max_cross_source_receive_skew_seconds": 1.0,
        "max_cross_source_disagreement_bps": 5.0,
        "max_abs_local_clock_offset_seconds": 1.0,
    }
    for key, expected in expected_gate_values.items():
        if gates.get(key) != expected:
            raise KxbtcdIndependentBtcSourcePolicyError(
                f"frozen live gate changed: {key}"
            )

    tiers = data["evidence_tiers"]
    expected_tiers = {
        "E1": (168, 7, 168),
        "E2": (168, 7, 168),
        "E3": (336, 14, 336),
    }
    for tier, (events, dates, span) in expected_tiers.items():
        item = tiers.get(tier)
        if not isinstance(item, dict):
            raise KxbtcdIndependentBtcSourcePolicyError(f"missing tier {tier}")
        if (
            item.get("minimum_eligible_events") != events
            or item.get("minimum_distinct_utc_dates") != dates
            or item.get("minimum_chronological_span_hours") != span
            or item.get("required_utc_hour_of_day_bins") != 24
            or item.get("minimum_tier_source_eligible_state_rate") != 0.90
            or abs(item.get("minimum_per_event_source_eligible_state_fraction", -1) - 2/3) > 1e-15
            or item.get("outcome_dependent_stopping_allowed") is not False
        ):
            raise KxbtcdIndependentBtcSourcePolicyError(
                f"frozen evidence-tier gate changed: {tier}"
            )

    return data


def midpoint(best_bid: float, best_ask: float) -> float:
    bid = float(best_bid)
    ask = float(best_ask)
    if bid <= 0 or ask <= 0 or bid > ask:
        raise KxbtcdIndependentBtcSourcePolicyError(
            "BBO requires positive prices with bid <= ask"
        )
    return (bid + ask) / 2.0


def disagreement_bps(a: float, b: float) -> float:
    a = float(a)
    b = float(b)
    if a <= 0 or b <= 0:
        raise KxbtcdIndependentBtcSourcePolicyError(
            "disagreement prices must be positive"
        )
    return abs(a - b) / ((a + b) / 2.0) * 10000.0


def evaluate_live_source_state(
    *,
    coinbase_best_bid: float,
    coinbase_best_ask: float,
    kraken_best_bid: float,
    kraken_best_ask: float,
    coinbase_local_first_seen_age_seconds: float,
    kraken_local_first_seen_age_seconds: float,
    coinbase_source_event_age_seconds: float,
    kraken_best_bid_publication_age_seconds: float,
    kraken_best_ask_publication_age_seconds: float,
    cross_source_receive_skew_seconds: float,
    local_clock_offset_seconds: float,
    policy: Mapping[str, Any] | None = None,
) -> LiveSourceDecision:
    policy = dict(policy or load_and_validate_policy())
    gates = policy["live_quality_gates"]
    reasons: list[str] = []

    try:
        primary = midpoint(coinbase_best_bid, coinbase_best_ask)
    except KxbtcdIndependentBtcSourcePolicyError:
        primary = None
        reasons.append("coinbase_invalid_bbo")

    try:
        verifier = midpoint(kraken_best_bid, kraken_best_ask)
    except KxbtcdIndependentBtcSourcePolicyError:
        verifier = None
        reasons.append("kraken_invalid_bbo")

    numeric_checks = (
        (
            "coinbase_local_first_seen_stale",
            coinbase_local_first_seen_age_seconds,
            gates["max_coinbase_local_first_seen_age_seconds"],
        ),
        (
            "kraken_local_first_seen_stale",
            kraken_local_first_seen_age_seconds,
            gates["max_kraken_local_first_seen_age_seconds"],
        ),
        (
            "coinbase_source_event_stale",
            coinbase_source_event_age_seconds,
            gates["max_coinbase_source_event_age_seconds"],
        ),
        (
            "cross_source_receive_skew_exceeded",
            cross_source_receive_skew_seconds,
            gates["max_cross_source_receive_skew_seconds"],
        ),
    )
    for reason, value, maximum in numeric_checks:
        try:
            value = float(value)
        except (TypeError, ValueError):
            reasons.append(reason + "_invalid")
            continue
        if value < 0 or value > maximum:
            reasons.append(reason)

    try:
        conservative_kraken_age = max(
            float(kraken_best_bid_publication_age_seconds),
            float(kraken_best_ask_publication_age_seconds),
        )
    except (TypeError, ValueError):
        conservative_kraken_age = None
        reasons.append("kraken_publication_age_invalid")
    if (
        conservative_kraken_age is not None
        and (
            conservative_kraken_age < 0
            or conservative_kraken_age
            > gates["max_kraken_conservative_bbo_publication_age_seconds"]
        )
    ):
        reasons.append("kraken_conservative_bbo_stale")

    try:
        clock_offset = abs(float(local_clock_offset_seconds))
    except (TypeError, ValueError):
        clock_offset = None
        reasons.append("clock_offset_invalid")
    if (
        clock_offset is not None
        and clock_offset > gates["max_abs_local_clock_offset_seconds"]
    ):
        reasons.append("clock_offset_exceeded")

    disagreement = None
    if primary is not None and verifier is not None:
        disagreement = disagreement_bps(primary, verifier)
        if disagreement > gates["max_cross_source_disagreement_bps"]:
            reasons.append("cross_source_disagreement_exceeded")

    return LiveSourceDecision(
        eligible=not reasons,
        primary_price=primary if not reasons else None,
        verifier_price=verifier,
        disagreement_bps=disagreement,
        exclusion_reasons=tuple(reasons),
    )


def causal_lookback_eligible(
    *,
    target_time_utc: datetime,
    observation_time_utc: datetime,
    max_target_gap_seconds: float | None = None,
) -> bool:
    if target_time_utc.tzinfo is None or observation_time_utc.tzinfo is None:
        raise KxbtcdIndependentBtcSourcePolicyError("lookback timestamps must be timezone-aware")
    target = target_time_utc.astimezone(timezone.utc)
    observation = observation_time_utc.astimezone(timezone.utc)
    if observation > target:
        return False
    policy = load_and_validate_policy()
    maximum = (
        policy["causal_lookback_policy"]["live_max_target_gap_seconds"]
        if max_target_gap_seconds is None
        else float(max_target_gap_seconds)
    )
    gap = (target - observation).total_seconds()
    return 0.0 <= gap <= maximum


def tier_ready(
    tier: str,
    *,
    eligible_event_count: int,
    distinct_utc_dates: int,
    chronological_span_hours: float,
    utc_hour_of_day_bins: Iterable[int],
    tier_source_eligible_state_rate: float,
    per_event_source_eligible_state_fractions: Iterable[float],
    policy: Mapping[str, Any] | None = None,
) -> tuple[bool, tuple[str, ...]]:
    policy = dict(policy or load_and_validate_policy())
    try:
        rule = policy["evidence_tiers"][tier]
    except KeyError as exc:
        raise KxbtcdIndependentBtcSourcePolicyError(f"unknown evidence tier {tier}") from exc

    reasons: list[str] = []
    if int(eligible_event_count) < rule["minimum_eligible_events"]:
        reasons.append("insufficient_eligible_events")
    if int(distinct_utc_dates) < rule["minimum_distinct_utc_dates"]:
        reasons.append("insufficient_utc_dates")
    if float(chronological_span_hours) < rule["minimum_chronological_span_hours"]:
        reasons.append("insufficient_chronological_span")
    bins = {int(x) for x in utc_hour_of_day_bins}
    if bins != set(range(24)):
        reasons.append("incomplete_utc_hour_of_day_coverage")
    if float(tier_source_eligible_state_rate) < rule["minimum_tier_source_eligible_state_rate"]:
        reasons.append("insufficient_tier_source_eligible_state_rate")
    fractions = [float(x) for x in per_event_source_eligible_state_fractions]
    if len(fractions) < int(eligible_event_count):
        reasons.append("missing_per_event_source_coverage")
    elif any(
        value < rule["minimum_per_event_source_eligible_state_fraction"]
        for value in fractions[: int(eligible_event_count)]
    ):
        reasons.append("event_below_minimum_source_eligible_fraction")
    return not reasons, tuple(reasons)
