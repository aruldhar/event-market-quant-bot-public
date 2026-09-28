"""Checkpoint 21N-F Candidate-E reliability-shrinkage Strategy-v2 primitives.

Outcome-independent only. Candidate E remains unchanged. This module shrinks
Candidate-E's selected-side probability toward the contemporaneous Kalshi
YES-midpoint (or its NO complement), then applies the frozen one-contract,
first-qualifying-anchor policy at adjusted net edge >= 0.

No settlement outcomes, realized P&L, network, order, paper, demo, or live
execution surfaces are present.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CONFIG_PATH = Path("configs/kxbtcd_candidate_e_reliability_shrinkage_entry_v2.json")
STRATEGY_ID = "kxbtcd_candidate_e_reliability_shrinkage_entry_v2"
CANDIDATE_ID = "kxbtcd_btc_distance_offset_logistic.v1"
CHAMPION_FINAL_FINGERPRINT = "b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc"
PARENT_STRATEGY_ID = "kxbtcd_candidate_e_quoted_entry_hold_v1"
PARENT_STRATEGY_FINGERPRINT = "5abea8adcaa782a57c9f69ef96b638fe1779370774e9f1c99a81b4340d42a8a6"
EXPECTED_V1_CONFIG_SHA256 = "3e7516745b6780815099149bda408771884e59c6fc638488ee68c04ba1a739fb"
EXPECTED_V1_ALL_SELECTION_SHA256 = "3c43d7c489dac9d761f442f594af24e1a52d478fe2e3bfdfc9e92eb84e636121"
EXPECTED_V1_ZERO_CENT_ENTERS = 820
EXPECTED_PREDECLARATION_FINGERPRINT = "b3fd3a3c71c5750604ef4e6eddd23043a75952d2c06a48cbb39ae6ef1066bd50"
EXPECTED_PREDICTION_SHA256S = {
    "H1_OOF": "867a77cbbf034a574983cb6fb301a77614674d3254297f8e15db377d5c34df16",
    "H2": "4aa6efe3c3bdc231fc8289f11fe01e1ad5a65910ae0ea92d2586447fd6b7d3d6",
    "H3": "091affc5ac088aa61db43a5df18f15178bceeea2ee26bd266b61fd059fd08380",
}
DEVELOPMENT_STAGES = ("H1_OOF", "H2", "H3")
EXPECTED_STAGE_EVENTS = {"H1_OOF": 1070, "H2": 750, "H3": 750}
EXPECTED_TOTAL_EVENTS = 2570
ANCHOR_ORDER = (55, 50, 45, 40, 35, 30)
STRUCTURAL_ROLES = ("q10", "q30", "q50", "q70", "q90")
SIDES = ("YES", "NO")
SIDE_ORDER = {"YES": 0, "NO": 1}
CANDIDATE_ALPHAS = (Decimal("0.25"), Decimal("0.50"), Decimal("0.75"))
REFERENCE_ALPHA = Decimal("1.00")
ALL_ALPHAS = CANDIDATE_ALPHAS + (REFERENCE_ALPHA,)
ZERO = Decimal("0")
MIN_TOTAL_ENTRIES = 100
MIN_STAGE_ENTRIES = 20
MIN_MATERIAL_CHANGE_FRACTION = Decimal("0.10")

ADJUSTED_STATE_FIELDS = (
    "schema_version","strategy_id","alpha","stage","state_id","event_ticker",
    "event_close_time_utc","market_ticker","structural_role","ttc_target_minutes",
    "decision_time_utc","side","candidate_probability","candidate_side_probability",
    "market_midpoint_yes_probability","market_anchor_side_probability",
    "adjusted_side_probability","yes_bid","yes_ask","quoted_purchase_price",
    "standard_entry_fee","adjusted_net_edge_per_contract",
)
SELECTION_FIELDS = (
    "schema_version","strategy_id","alpha","event_ticker","event_close_time_utc",
    "action","stage","ttc_target_minutes","decision_time_utc","market_ticker",
    "structural_role","side","candidate_probability","market_midpoint_yes_probability",
    "candidate_side_probability","adjusted_side_probability","quoted_purchase_price",
    "standard_entry_fee","adjusted_net_edge_per_contract",
)


class ReliabilityShrinkageError(RuntimeError):
    pass


def _error(message: str) -> None:
    raise ReliabilityShrinkageError(message)


def _text(value: Any, name: str) -> str:
    text = str(value).strip()
    if not text:
        _error(f"{name} must be non-empty")
    return text


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ReliabilityShrinkageError(f"{name} must be decimal-compatible") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _unit(value: Any, name: str) -> Decimal:
    value = _decimal(value, name)
    if value < 0 or value > 1:
        _error(f"{name} must be in [0,1]")
    return value


def _fmt(value: Decimal) -> str:
    text = format(value, "f")
    if "." not in text:
        return text + ".0"
    stripped = text.rstrip("0").rstrip(".")
    return stripped if stripped else "0"


def canonical_sha256(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def write_csv(path: str | Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def validate_predeclaration(path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema_version") != "kxbtcd_candidate_e_reliability_shrinkage_entry_v2_predeclaration.v1":
        _error("Strategy-v2 predeclaration schema mismatch")
    if doc.get("strategy_id") != STRATEGY_ID:
        _error("Strategy-v2 identity mismatch")
    if doc.get("candidate_id") != CANDIDATE_ID:
        _error("Candidate-E identity mismatch")
    if doc.get("champion_final_fingerprint") != CHAMPION_FINAL_FINGERPRINT:
        _error("Champion-Final fingerprint mismatch")
    parent = doc.get("parent_strategy", {})
    if parent.get("strategy_id") != PARENT_STRATEGY_ID:
        _error("parent Strategy-v1 identity mismatch")
    if parent.get("strategy_predeclaration_fingerprint") != PARENT_STRATEGY_FINGERPRINT:
        _error("parent Strategy-v1 fingerprint mismatch")

    adjustment = doc.get("reliability_adjustment", {})
    candidates = tuple(_decimal(x, "candidate alpha") for x in adjustment.get("candidate_alphas", ()))
    if candidates != CANDIDATE_ALPHAS:
        _error("candidate alpha menu changed")
    if _decimal(adjustment.get("diagnostic_reference_alpha"), "reference alpha") != REFERENCE_ALPHA:
        _error("diagnostic alpha changed")
    if adjustment.get("flat_edge_haircut_used") is not False:
        _error("flat edge haircut must remain false")

    policy = doc.get("entry_policy", {})
    if tuple(policy.get("anchor_order_ttc_minutes", ())) != ANCHOR_ORDER:
        _error("anchor order changed")
    if tuple(policy.get("structural_roles", ())) != STRUCTURAL_ROLES:
        _error("structural roles changed")
    if tuple(policy.get("sides", ())) != SIDES:
        _error("sides changed")
    if policy.get("whole_contract_quantity") != 1 or policy.get("maximum_entries_per_event") != 1:
        _error("quantity/entry limit changed")
    if policy.get("qualification_rule") != "adjusted_net_edge >= 0":
        _error("qualification rule changed")

    audit = doc.get("outcome_independent_opportunity_audit", {})
    if audit.get("required_before_any_strategy_v2_pnl") is not True:
        _error("outcome-independent audit must precede Strategy-v2 P&L")
    if audit.get("alpha_winner_selected") is not False:
        _error("alpha winner must not be selected in 21N-F")
    screen = audit.get("economic_selection_eligibility_screen_for_later_checkpoint", {})
    if screen.get("minimum_total_entries") != MIN_TOTAL_ENTRIES:
        _error("minimum total opportunity count changed")
    if screen.get("minimum_entries_per_stage") != MIN_STAGE_ENTRIES:
        _error("minimum per-stage opportunity count changed")
    materiality = audit.get("continuation_materiality_screen", {})
    if _decimal(materiality.get("minimum_action_or_choice_changed_fraction_vs_alpha1"), "materiality fraction") != MIN_MATERIAL_CHANGE_FRACTION:
        _error("opportunity materiality screen changed")
    if materiality.get("requires_sample_eligibility_too") is not True:
        _error("materiality screen must also require sample eligibility")

    firewall = doc.get("evidence_firewall", {})
    required_false = (
        "c1_c2_strategy_v1_economics_access_allowed",
        "c1_c2_strategy_v2_economics_access_allowed",
        "c3_access_allowed",
        "protected_reserve_access_allowed",
        "network_access_allowed","paper_broker_allowed","demo_execution_allowed",
        "real_execution_allowed","orders_allowed",
    )
    for key in required_false:
        if firewall.get(key) is not False:
            _error(f"evidence_firewall.{key} must be false")

    supplied = doc.get("strategy_v2_predeclaration_fingerprint")
    copy = dict(doc)
    copy.pop("strategy_v2_predeclaration_fingerprint", None)
    expected = canonical_sha256(copy)
    if supplied != expected or supplied != EXPECTED_PREDECLARATION_FINGERPRINT:
        _error("Strategy-v2 predeclaration fingerprint mismatch")
    return doc


def market_anchor_side_probability(*, side: str, yes_bid: Any, yes_ask: Any) -> tuple[Decimal, Decimal]:
    side = _text(side, "side").upper()
    if side not in SIDES:
        _error("side must be YES or NO")
    bid = _unit(yes_bid, "yes_bid")
    ask = _unit(yes_ask, "yes_ask")
    if bid > ask:
        _error("crossed quote")
    q_yes = (bid + ask) / Decimal("2")
    q_side = q_yes if side == "YES" else Decimal("1") - q_yes
    return q_yes, q_side


def adjusted_side_probability(
    *, side: str, candidate_probability: Any, yes_bid: Any, yes_ask: Any, alpha: Any
) -> tuple[Decimal, Decimal, Decimal]:
    alpha = _decimal(alpha, "alpha")
    if alpha not in ALL_ALPHAS:
        _error("alpha outside frozen menu")
    side = _text(side, "side").upper()
    if side not in SIDES:
        _error("side must be YES or NO")
    p_yes = _unit(candidate_probability, "candidate_probability")
    p_side = p_yes if side == "YES" else Decimal("1") - p_yes
    q_yes, q_side = market_anchor_side_probability(side=side, yes_bid=yes_bid, yes_ask=yes_ask)
    p_adj = q_side + alpha * (p_side - q_side)
    return p_adj, q_yes, q_side


def adjust_base_side_state(row: Mapping[str, Any], *, alpha: Decimal) -> dict[str, str]:
    side = _text(row.get("side"), "side").upper()
    p_adj, q_yes, q_side = adjusted_side_probability(
        side=side,
        candidate_probability=row.get("candidate_probability"),
        yes_bid=row.get("yes_bid"),
        yes_ask=row.get("yes_ask"),
        alpha=alpha,
    )
    price = _unit(row.get("quoted_purchase_price"), "quoted_purchase_price")
    fee = _decimal(row.get("standard_entry_fee"), "standard_entry_fee")
    if fee < 0:
        _error("entry fee cannot be negative")
    candidate_side = _unit(row.get("side_fair_probability"), "side_fair_probability")
    edge = p_adj - price - fee
    return {
        "schema_version": "kxbtcd_candidate_e_reliability_shrinkage_side_state.v1",
        "strategy_id": STRATEGY_ID,
        "alpha": _fmt(alpha),
        "stage": _text(row.get("stage"), "stage"),
        "state_id": _text(row.get("state_id"), "state_id"),
        "event_ticker": _text(row.get("event_ticker"), "event_ticker"),
        "event_close_time_utc": _text(row.get("event_close_time_utc"), "event_close_time_utc"),
        "market_ticker": _text(row.get("market_ticker"), "market_ticker"),
        "structural_role": _text(row.get("structural_role"), "structural_role"),
        "ttc_target_minutes": _text(row.get("ttc_target_minutes"), "ttc_target_minutes"),
        "decision_time_utc": _text(row.get("decision_time_utc"), "decision_time_utc"),
        "side": side,
        "candidate_probability": _text(row.get("candidate_probability"), "candidate_probability"),
        "candidate_side_probability": _fmt(candidate_side),
        "market_midpoint_yes_probability": _fmt(q_yes),
        "market_anchor_side_probability": _fmt(q_side),
        "adjusted_side_probability": _fmt(p_adj),
        "yes_bid": _text(row.get("yes_bid"), "yes_bid"),
        "yes_ask": _text(row.get("yes_ask"), "yes_ask"),
        "quoted_purchase_price": _fmt(price),
        "standard_entry_fee": _fmt(fee),
        "adjusted_net_edge_per_contract": _fmt(edge),
    }


def build_adjusted_side_states(
    base_side_states: Sequence[Mapping[str, Any]], *, alpha: Decimal
) -> tuple[dict[str, str], ...]:
    if alpha not in ALL_ALPHAS:
        _error("alpha outside frozen menu")
    return tuple(adjust_base_side_state(row, alpha=alpha) for row in base_side_states)


def _candidate_sort_key(row: Mapping[str, str]) -> tuple[Any, ...]:
    return (
        -_decimal(row["adjusted_net_edge_per_contract"], "adjusted edge"),
        row["market_ticker"],
        SIDE_ORDER[row["side"]],
    )


def select_alpha_events(
    adjusted_states: Sequence[Mapping[str, str]], *, alpha: Decimal
) -> tuple[dict[str, str], ...]:
    if alpha not in ALL_ALPHAS:
        _error("alpha outside frozen menu")
    expected_alpha = _fmt(alpha)
    event_meta: dict[str, tuple[str, str]] = {}
    by_event_anchor: dict[tuple[str, int], list[Mapping[str, str]]] = {}

    for index, row in enumerate(adjusted_states):
        if row.get("strategy_id") != STRATEGY_ID:
            _error(f"adjusted state[{index}] strategy mismatch")
        if _decimal(row.get("alpha"), "row alpha") != alpha:
            _error(f"adjusted state[{index}] alpha mismatch")
        event = _text(row.get("event_ticker"), "event_ticker")
        stage = _text(row.get("stage"), "stage")
        close = _text(row.get("event_close_time_utc"), "event_close_time_utc")
        if stage not in DEVELOPMENT_STAGES:
            _error("unexpected development stage")
        prior = event_meta.setdefault(event, (stage, close))
        if prior != (stage, close):
            _error(f"inconsistent event metadata for {event}")
        try:
            ttc = int(row.get("ttc_target_minutes"))
        except (TypeError, ValueError) as exc:
            raise ReliabilityShrinkageError("TTC must be integer") from exc
        if ttc not in ANCHOR_ORDER:
            _error("unexpected TTC anchor")
        by_event_anchor.setdefault((event, ttc), []).append(row)

    if len(event_meta) != EXPECTED_TOTAL_EVENTS:
        _error(f"development event count changed: {len(event_meta)} != {EXPECTED_TOTAL_EVENTS}")

    result: list[dict[str, str]] = []
    for event, (stage, close) in sorted(event_meta.items(), key=lambda item: (item[1][1], item[0])):
        chosen: Mapping[str, str] | None = None
        for ttc in ANCHOR_ORDER:
            qualifying = [
                row for row in by_event_anchor.get((event, ttc), ())
                if _decimal(row["adjusted_net_edge_per_contract"], "adjusted edge") >= ZERO
            ]
            if qualifying:
                chosen = sorted(qualifying, key=_candidate_sort_key)[0]
                break

        base = {
            "schema_version": "kxbtcd_candidate_e_reliability_shrinkage_event_selection.v1",
            "strategy_id": STRATEGY_ID,
            "alpha": expected_alpha,
            "event_ticker": event,
            "event_close_time_utc": close,
            "stage": stage,
        }
        if chosen is None:
            result.append({
                **base, "action": "ABSTAIN",
                "ttc_target_minutes": "", "decision_time_utc": "", "market_ticker": "",
                "structural_role": "", "side": "", "candidate_probability": "",
                "market_midpoint_yes_probability": "", "candidate_side_probability": "",
                "adjusted_side_probability": "", "quoted_purchase_price": "",
                "standard_entry_fee": "", "adjusted_net_edge_per_contract": "",
            })
        else:
            result.append({
                **base, "action": "ENTER",
                "ttc_target_minutes": chosen["ttc_target_minutes"],
                "decision_time_utc": chosen["decision_time_utc"],
                "market_ticker": chosen["market_ticker"],
                "structural_role": chosen["structural_role"],
                "side": chosen["side"],
                "candidate_probability": chosen["candidate_probability"],
                "market_midpoint_yes_probability": chosen["market_midpoint_yes_probability"],
                "candidate_side_probability": chosen["candidate_side_probability"],
                "adjusted_side_probability": chosen["adjusted_side_probability"],
                "quoted_purchase_price": chosen["quoted_purchase_price"],
                "standard_entry_fee": chosen["standard_entry_fee"],
                "adjusted_net_edge_per_contract": chosen["adjusted_net_edge_per_contract"],
            })
    return tuple(result)


def _enter_map(rows: Sequence[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    return {r["event_ticker"]: r for r in rows if r["action"] == "ENTER"}


def _choice_identity(row: Mapping[str, str]) -> tuple[str, ...]:
    return (
        row.get("ttc_target_minutes", ""),
        row.get("decision_time_utc", ""),
        row.get("market_ticker", ""),
        row.get("structural_role", ""),
        row.get("side", ""),
    )


def assert_alpha1_reproduces_v1(
    *, v1_zero_rows: Sequence[Mapping[str, str]], alpha1_rows: Sequence[Mapping[str, str]]
) -> None:
    if len(v1_zero_rows) != EXPECTED_TOTAL_EVENTS or len(alpha1_rows) != EXPECTED_TOTAL_EVENTS:
        _error("alpha=1 reproduction row count mismatch")
    v1 = {r["event_ticker"]: r for r in v1_zero_rows}
    v2 = {r["event_ticker"]: r for r in alpha1_rows}
    if set(v1) != set(v2):
        _error("alpha=1 event universe mismatch")
    enter_count = 0
    for event in sorted(v1):
        if v1[event]["action"] != v2[event]["action"]:
            _error(f"alpha=1 action mismatch for {event}")
        if v1[event]["action"] == "ENTER":
            enter_count += 1
            if _choice_identity(v1[event]) != _choice_identity(v2[event]):
                _error(f"alpha=1 chosen state mismatch for {event}")
    if enter_count != EXPECTED_V1_ZERO_CENT_ENTERS:
        _error(f"alpha=1 enter count changed: {enter_count}")


def summarize_alpha(
    rows: Sequence[Mapping[str, str]],
    *,
    alpha: Decimal,
    reference_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    enter = _enter_map(rows)
    ref = _enter_map(reference_rows)
    new_events = set(enter) - set(ref)
    if alpha != REFERENCE_ALPHA and new_events:
        _error(f"alpha={alpha} created new entry events outside alpha=1 set")
    overlap = set(enter) & set(ref)
    same = sum(_choice_identity(enter[e]) == _choice_identity(ref[e]) for e in overlap)
    changed = len(overlap) - same
    stage_counts = {stage: sum(r["action"] == "ENTER" and r["stage"] == stage for r in rows)
                    for stage in DEVELOPMENT_STAGES}
    side_counts = {side: sum(r["action"] == "ENTER" and r["side"] == side for r in rows) for side in SIDES}
    ttc_counts = {str(ttc): sum(r["action"] == "ENTER" and r["ttc_target_minutes"] == str(ttc) for r in rows)
                  for ttc in ANCHOR_ORDER}
    role_counts = {role: sum(r["action"] == "ENTER" and r["structural_role"] == role for r in rows)
                   for role in STRUCTURAL_ROLES}
    count = len(enter)
    sample_eligible = (
        alpha in CANDIDATE_ALPHAS
        and count >= MIN_TOTAL_ENTRIES
        and all(stage_counts[s] >= MIN_STAGE_ENTRIES for s in DEVELOPMENT_STAGES)
    )
    changed_decisions = len(set(ref) - set(enter)) + changed
    changed_fraction = (Decimal(changed_decisions) / Decimal(len(ref))) if ref else Decimal("0")
    materiality_pass = (
        alpha in CANDIDATE_ALPHAS
        and sample_eligible
        and changed_fraction >= MIN_MATERIAL_CHANGE_FRACTION
    )
    return {
        "alpha": _fmt(alpha),
        "enter_count": count,
        "abstain_count": EXPECTED_TOTAL_EVENTS - count,
        "enter_rate": count / EXPECTED_TOTAL_EVENTS,
        "stage_counts": stage_counts,
        "side_counts": side_counts,
        "ttc_counts": ttc_counts,
        "role_counts": role_counts,
        "overlap_with_alpha1_enter_events": len(overlap),
        "retained_fraction_of_alpha1_entries": (len(overlap) / len(ref)) if ref else 0.0,
        "removed_vs_alpha1_count": len(set(ref) - set(enter)),
        "new_vs_alpha1_count": len(new_events),
        "same_choice_vs_alpha1_count": same,
        "changed_choice_vs_alpha1_count": changed,
        "action_or_choice_changed_count": changed_decisions,
        "action_or_choice_changed_fraction_vs_alpha1": float(changed_fraction),
        "later_economics_sample_eligible": sample_eligible,
        "opportunity_materiality_pass": materiality_pass,
        "later_economics_design_eligible": materiality_pass,
    }


def build_opportunity_summary(
    *,
    selections_by_alpha: Mapping[Decimal, Sequence[Mapping[str, str]]],
    input_sha256s: Mapping[str, str],
    v1_reproduction_sha256: str,
) -> dict[str, Any]:
    reference = selections_by_alpha[REFERENCE_ALPHA]
    alpha_summaries = {
        _fmt(alpha): summarize_alpha(rows, alpha=alpha, reference_rows=reference)
        for alpha, rows in selections_by_alpha.items()
    }
    summary = {
        "schema_version": "kxbtcd_candidate_e_reliability_shrinkage_opportunity_audit.v1",
        "strategy_id": STRATEGY_ID,
        "strategy_v2_predeclaration_fingerprint": EXPECTED_PREDECLARATION_FINGERPRINT,
        "scope": {
            "event_count": EXPECTED_TOTAL_EVENTS,
            "stages": list(DEVELOPMENT_STAGES),
            "settlement_outcomes_used": False,
            "realized_pnl_calculated": False,
        },
        "alpha_summaries": alpha_summaries,
        "continuation": {
            "any_candidate_materiality_pass": any(
                alpha_summaries[_fmt(alpha)]["opportunity_materiality_pass"]
                for alpha in CANDIDATE_ALPHAS
            ),
            "if_false": "STOP_SIMPLE_SHRINKAGE_OPPORTUNITY_IMMATERIAL",
            "if_true": "ELIGIBLE_FOR_SEPARATE_STRATEGY_V2_ECONOMICS_PREDECLARATION",
            "alpha_winner_selected": False,
        },
        "v1_reproduction": {
            "all_threshold_selection_sha256": v1_reproduction_sha256,
            "expected_sha256": EXPECTED_V1_ALL_SELECTION_SHA256,
            "exact_match": v1_reproduction_sha256 == EXPECTED_V1_ALL_SELECTION_SHA256,
            "alpha1_zero_cent_exact_action_choice_match": True,
            "alpha1_enter_count": EXPECTED_V1_ZERO_CENT_ENTERS,
        },
        "selection": {
            "alpha_winner_selected": False,
            "strategy_v2_pnl_authorized": False,
        },
        "input_sha256s": dict(sorted(input_sha256s.items())),
        "safety": {
            "c1_c2_strategy_pnl_accessed": False,
            "c3_accessed": False,
            "protected_reserve_accessed": False,
            "network_accessed": False,
            "orders_submitted": False,
            "paper_broker_used": False,
            "demo_execution_used": False,
            "real_execution_used": False,
        },
    }
    summary["audit_fingerprint"] = canonical_sha256(summary)
    return summary
