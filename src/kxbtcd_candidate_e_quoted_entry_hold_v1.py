"""Checkpoint 21N-A Candidate-E quoted-entry / hold strategy primitives.

This module is intentionally read-only and outcome-independent.  It translates
frozen Candidate-E probabilities plus frozen contemporaneous two-sided quotes
into standard-fee quoted economic edge, then applies the predeclared
first-qualifying-anchor selection rule.  It does not read settlement outcomes,
calculate realized P&L, access C1/C2/C3, simulate fills, or expose any order API.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CONFIG_PATH = Path("configs/kxbtcd_candidate_e_quoted_entry_hold_v1.json")
STRATEGY_ID = "kxbtcd_candidate_e_quoted_entry_hold_v1"
CANDIDATE_ID = "kxbtcd_btc_distance_offset_logistic.v1"
CHAMPION_FINAL_FINGERPRINT = "b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc"
PRIOR_STRATEGY_ID = "kxbtcd_candidate_e_strategy_replay_v1"
PRIOR_STRATEGY_FINGERPRINT = "afc1b397c850e8b2a2dfd32d6656e05f4622c59f1596f5b91295e96debb0d046"

DEVELOPMENT_STAGES = ("H1_OOF", "H2", "H3")
PREOUTCOME_STAGE_BY_STAGE = {"H1_OOF": "H1", "H2": "H2", "H3": "H3"}
PREDICTION_SCHEMA_BY_STAGE = {
    "H1_OOF": "kxbtcd_candidate_e_h1_oof_prediction.v1",
    "H2": "kxbtcd_candidate_e_h2_prediction.v1",
    "H3": "kxbtcd_candidate_e_h3_prediction.v1",
}
EXPECTED_ROW_COUNTS = {"H1_OOF": 31656, "H2": 22354, "H3": 22409}
EXPECTED_EVENT_COUNTS = {"H1_OOF": 1070, "H2": 750, "H3": 750}
EXPECTED_TOTAL_ROWS = 76419
EXPECTED_TOTAL_EVENTS = 2570

ANCHOR_ORDER = (55, 50, 45, 40, 35, 30)
STRUCTURAL_ROLES = ("q10", "q30", "q50", "q70", "q90")
SIDES = ("YES", "NO")
SIDE_ORDER = {"YES": 0, "NO": 1}
THRESHOLDS = (
    Decimal("0.00"),
    Decimal("0.01"),
    Decimal("0.02"),
    Decimal("0.03"),
    Decimal("0.05"),
)
ONE_CONTRACT = 1
FEE_RATE = Decimal("0.07")
ONE_CENT = Decimal("0.01")

CANDIDATE_STATE_FIELDS = (
    "schema_version",
    "strategy_id",
    "stage",
    "state_id",
    "event_ticker",
    "event_close_time_utc",
    "market_ticker",
    "structural_role",
    "ttc_target_minutes",
    "decision_time_utc",
    "side",
    "candidate_probability",
    "side_fair_probability",
    "yes_bid",
    "yes_ask",
    "quoted_purchase_price",
    "standard_entry_fee",
    "net_edge_per_contract",
)

SELECTION_FIELDS = (
    "schema_version",
    "strategy_id",
    "threshold_dollars",
    "event_ticker",
    "event_close_time_utc",
    "action",
    "stage",
    "ttc_target_minutes",
    "decision_time_utc",
    "market_ticker",
    "structural_role",
    "side",
    "candidate_probability",
    "quoted_purchase_price",
    "standard_entry_fee",
    "net_edge_per_contract",
)


class QuotedEntryHoldError(RuntimeError):
    """Raised when the frozen quoted-entry contract fails closed."""


def _error(message: str) -> None:
    raise QuotedEntryHoldError(message)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be non-empty text")
    return value.strip()


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise QuotedEntryHoldError(f"{name} must be decimal-compatible") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _unit_interval(value: Any, name: str) -> Decimal:
    result = _decimal(value, name)
    if result < 0 or result > 1:
        _error(f"{name} must be in [0, 1]")
    return result


def _format_decimal(value: Decimal) -> str:
    # Fixed-point serialization avoids scientific notation and unstable float text.
    text = format(value, "f")
    if "." not in text:
        return text + ".0"
    return text.rstrip("0").rstrip(".") if "." in text else text


def canonical_sha256(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def state_id_from_preoutcome(row: Mapping[str, Any]) -> str:
    event = _text(row.get("event_ticker"), "preoutcome.event_ticker")
    market = _text(row.get("market_ticker"), "preoutcome.market_ticker")
    role = _text(row.get("structural_role"), "preoutcome.structural_role")
    if role not in STRUCTURAL_ROLES:
        _error(f"unexpected structural role {role!r}")
    try:
        ttc = int(row.get("ttc_target_minutes"))
    except (TypeError, ValueError) as exc:
        raise QuotedEntryHoldError("preoutcome.ttc_target_minutes must be integer") from exc
    if ttc not in ANCHOR_ORDER:
        _error(f"unexpected TTC anchor {ttc}")
    return f"{event}|{market}|TTC{ttc}|{role}"


def quoted_purchase_price(*, side: str, yes_bid: Any, yes_ask: Any) -> Decimal:
    side = _text(side, "side").upper()
    if side not in SIDES:
        _error("side must be YES or NO")
    bid = _unit_interval(yes_bid, "yes_bid")
    ask = _unit_interval(yes_ask, "yes_ask")
    if bid > ask:
        _error("crossed quote")
    return ask if side == "YES" else Decimal("1") - bid


def side_fair_probability(*, side: str, candidate_probability: Any) -> Decimal:
    side = _text(side, "side").upper()
    if side not in SIDES:
        _error("side must be YES or NO")
    p = _unit_interval(candidate_probability, "candidate_probability")
    return p if side == "YES" else Decimal("1") - p


def standard_entry_fee(*, price: Any, contracts: int = ONE_CONTRACT) -> Decimal:
    if contracts != ONE_CONTRACT:
        _error("quoted-entry hold v1 is frozen to exactly one whole contract")
    p = _unit_interval(price, "price")
    raw = FEE_RATE * Decimal(contracts) * p * (Decimal("1") - p)
    return raw.quantize(ONE_CENT, rounding=ROUND_CEILING)


def net_edge_per_contract(
    *, side: str, candidate_probability: Any, yes_bid: Any, yes_ask: Any
) -> tuple[Decimal, Decimal, Decimal]:
    price = quoted_purchase_price(side=side, yes_bid=yes_bid, yes_ask=yes_ask)
    fair = side_fair_probability(side=side, candidate_probability=candidate_probability)
    fee = standard_entry_fee(price=price, contracts=ONE_CONTRACT)
    return fair - price - fee, price, fee


def validate_predeclaration(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    document = json.loads(config_path.read_text(encoding="utf-8"))
    if document.get("schema_version") != "kxbtcd_candidate_e_quoted_entry_hold_predeclaration.v1":
        _error("predeclaration schema mismatch")
    if document.get("strategy_id") != STRATEGY_ID:
        _error("strategy_id mismatch")
    if document.get("candidate_id") != CANDIDATE_ID:
        _error("candidate_id mismatch")
    if document.get("champion_final_fingerprint") != CHAMPION_FINAL_FINGERPRINT:
        _error("Champion-Final fingerprint mismatch")
    prior = document.get("prior_strategy_design")
    if not isinstance(prior, dict):
        _error("prior_strategy_design missing")
    if prior.get("strategy_id") != PRIOR_STRATEGY_ID:
        _error("prior strategy identity mismatch")
    if prior.get("strategy_predeclaration_fingerprint") != PRIOR_STRATEGY_FINGERPRINT:
        _error("prior strategy fingerprint mismatch")
    if prior.get("status") != "superseded_before_economic_scoring":
        _error("prior strategy must be superseded before scoring")
    if prior.get("strategy_pnl_inspected") is not False:
        _error("prior strategy P&L exposure must be false")

    policy = document.get("signal_policy")
    if not isinstance(policy, dict):
        _error("signal_policy missing")
    if tuple(policy.get("anchor_order_ttc_minutes", ())) != ANCHOR_ORDER:
        _error("anchor order changed")
    thresholds = tuple(_decimal(x, "threshold") for x in policy.get("net_edge_thresholds_dollars_per_contract", ()))
    if thresholds != THRESHOLDS:
        _error("threshold menu changed")
    if policy.get("whole_contract_quantity") != ONE_CONTRACT:
        _error("quantity changed")
    if policy.get("maximum_entries_per_event") != 1:
        _error("maximum entries changed")

    status = document.get("research_status")
    if not isinstance(status, dict):
        _error("research_status missing")
    required_false = (
        "candidate_e_refit_authorized",
        "model2_repair_authorized",
        "strategy_pnl_calculated_before_this_freeze",
        "c3_strategy_economics_opened",
        "protected_reserve_accessed",
        "order_execution_authorized",
        "paper_broker_authorized",
        "demo_execution_authorized",
        "real_money_execution_authorized",
    )
    for key in required_false:
        if status.get(key) is not False:
            _error(f"research_status.{key} must be false")

    supplied = _text(
        document.get("strategy_predeclaration_fingerprint"),
        "strategy_predeclaration_fingerprint",
    )
    copy = dict(document)
    copy.pop("strategy_predeclaration_fingerprint", None)
    expected = canonical_sha256(copy)
    if supplied != expected:
        _error(f"predeclaration fingerprint mismatch: {supplied} != {expected}")
    return document


def _prediction_projection(
    rows: Sequence[Mapping[str, Any]],
    *,
    stage: str,
    enforce_frozen_counts: bool,
) -> dict[str, dict[str, str]]:
    expected_schema = PREDICTION_SCHEMA_BY_STAGE[stage]
    projected: dict[str, dict[str, str]] = {}
    for index, source in enumerate(rows):
        if source.get("schema_version") != expected_schema:
            _error(f"{stage} prediction row[{index}] schema mismatch")
        if source.get("candidate_id") != CANDIDATE_ID:
            # H1 OOF can contain a rejected challenger. It is never part of Strategy-v1.
            continue
        state = _text(source.get("state_id"), f"{stage}[{index}].state_id")
        if state in projected:
            _error(f"duplicate {stage} Candidate-E state_id {state}")
        projected[state] = {
            "state_id": state,
            "event_ticker": _text(source.get("event_ticker"), f"{stage}[{index}].event_ticker"),
            "market_ticker": _text(source.get("market_ticker"), f"{stage}[{index}].market_ticker"),
            "candidate_probability": _text(
                str(source.get("candidate_probability", "")),
                f"{stage}[{index}].candidate_probability",
            ),
        }
    if not projected:
        _error(f"{stage} Candidate-E prediction projection is empty")
    if enforce_frozen_counts:
        if len(projected) != EXPECTED_ROW_COUNTS[stage]:
            _error(f"{stage} row count changed: {len(projected)} != {EXPECTED_ROW_COUNTS[stage]}")
        events = {row["event_ticker"] for row in projected.values()}
        if len(events) != EXPECTED_EVENT_COUNTS[stage]:
            _error(f"{stage} event count changed: {len(events)} != {EXPECTED_EVENT_COUNTS[stage]}")
    return projected


def _preoutcome_index(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if str(row.get("stage", "")) not in {"H1", "H2", "H3"}:
            continue
        state = state_id_from_preoutcome(row)
        if state in result:
            _error(f"duplicate preoutcome state {state}")
        result[state] = row
    if not result:
        _error("preoutcome index is empty")
    return result


def build_candidate_side_states(
    *,
    preoutcome_rows: Sequence[Mapping[str, Any]],
    h1_prediction_rows: Sequence[Mapping[str, Any]],
    h2_prediction_rows: Sequence[Mapping[str, Any]],
    h3_prediction_rows: Sequence[Mapping[str, Any]],
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, str], ...]:
    predictions = {
        "H1_OOF": _prediction_projection(
            h1_prediction_rows, stage="H1_OOF", enforce_frozen_counts=enforce_frozen_counts
        ),
        "H2": _prediction_projection(
            h2_prediction_rows, stage="H2", enforce_frozen_counts=enforce_frozen_counts
        ),
        "H3": _prediction_projection(
            h3_prediction_rows, stage="H3", enforce_frozen_counts=enforce_frozen_counts
        ),
    }
    preoutcome = _preoutcome_index(preoutcome_rows)
    result: list[dict[str, str]] = []
    seen_event_stage: dict[str, str] = {}

    for stage in DEVELOPMENT_STAGES:
        expected_source_stage = PREOUTCOME_STAGE_BY_STAGE[stage]
        for state, prediction in predictions[stage].items():
            source = preoutcome.get(state)
            if source is None:
                _error(f"{stage} state {state} missing from preoutcome source")
            if source.get("stage") != expected_source_stage:
                _error(f"{state} preoutcome stage mismatch")
            event = _text(source.get("event_ticker"), f"{state}.event_ticker")
            market = _text(source.get("market_ticker"), f"{state}.market_ticker")
            if event != prediction["event_ticker"] or market != prediction["market_ticker"]:
                _error(f"{state} prediction/preoutcome identity mismatch")
            prior_stage = seen_event_stage.setdefault(event, stage)
            if prior_stage != stage:
                _error(f"event {event} crosses development stages")
            role = _text(source.get("structural_role"), f"{state}.structural_role")
            if role not in STRUCTURAL_ROLES:
                _error(f"{state} structural role mismatch")
            try:
                ttc = int(source.get("ttc_target_minutes"))
            except (TypeError, ValueError) as exc:
                raise QuotedEntryHoldError(f"{state} TTC must be integer") from exc
            if ttc not in ANCHOR_ORDER:
                _error(f"{state} unexpected TTC")
            yes_bid = _unit_interval(source.get("yes_bid"), f"{state}.yes_bid")
            yes_ask = _unit_interval(source.get("yes_ask"), f"{state}.yes_ask")
            if yes_bid > yes_ask:
                _error(f"{state} crossed quote")
            candidate_probability = _unit_interval(
                prediction["candidate_probability"], f"{state}.candidate_probability"
            )
            event_close = _text(source.get("event_close_time_utc"), f"{state}.event_close_time_utc")
            decision = _text(source.get("decision_target_utc"), f"{state}.decision_target_utc")

            for side in SIDES:
                edge, price, fee = net_edge_per_contract(
                    side=side,
                    candidate_probability=candidate_probability,
                    yes_bid=yes_bid,
                    yes_ask=yes_ask,
                )
                fair = side_fair_probability(side=side, candidate_probability=candidate_probability)
                result.append(
                    {
                        "schema_version": "kxbtcd_candidate_e_quoted_entry_candidate_side_state.v1",
                        "strategy_id": STRATEGY_ID,
                        "stage": stage,
                        "state_id": state,
                        "event_ticker": event,
                        "event_close_time_utc": event_close,
                        "market_ticker": market,
                        "structural_role": role,
                        "ttc_target_minutes": str(ttc),
                        "decision_time_utc": decision,
                        "side": side,
                        "candidate_probability": _format_decimal(candidate_probability),
                        "side_fair_probability": _format_decimal(fair),
                        "yes_bid": _format_decimal(yes_bid),
                        "yes_ask": _format_decimal(yes_ask),
                        "quoted_purchase_price": _format_decimal(price),
                        "standard_entry_fee": _format_decimal(fee),
                        "net_edge_per_contract": _format_decimal(edge),
                    }
                )

    if enforce_frozen_counts:
        if len(result) != EXPECTED_TOTAL_ROWS * 2:
            _error(f"candidate side-state count changed: {len(result)} != {EXPECTED_TOTAL_ROWS * 2}")
        events = {row["event_ticker"] for row in result}
        if len(events) != EXPECTED_TOTAL_EVENTS:
            _error(f"development event count changed: {len(events)} != {EXPECTED_TOTAL_EVENTS}")
    result.sort(
        key=lambda row: (
            DEVELOPMENT_STAGES.index(row["stage"]),
            row["event_close_time_utc"],
            row["event_ticker"],
            -int(row["ttc_target_minutes"]),
            row["market_ticker"],
            SIDE_ORDER[row["side"]],
        )
    )
    return tuple(result)


def _candidate_sort_key(row: Mapping[str, str]) -> tuple[Any, ...]:
    edge = _decimal(row["net_edge_per_contract"], "net_edge_per_contract")
    return (-edge, row["market_ticker"], SIDE_ORDER[row["side"]])


def select_threshold_events(
    side_states: Sequence[Mapping[str, str]],
    *,
    threshold: Decimal,
) -> tuple[dict[str, str], ...]:
    if threshold not in THRESHOLDS:
        _error(f"threshold {threshold} is outside frozen menu")

    by_event: dict[str, list[Mapping[str, str]]] = {}
    for row in side_states:
        stage = _text(row.get("stage"), "side_state.stage")
        if stage not in DEVELOPMENT_STAGES:
            _error(f"unauthorized stage {stage}")
        by_event.setdefault(_text(row.get("event_ticker"), "event_ticker"), []).append(row)

    selections: list[dict[str, str]] = []
    for event, rows in by_event.items():
        stage_set = {row["stage"] for row in rows}
        if len(stage_set) != 1:
            _error(f"event {event} crosses stages")
        event_close_set = {row["event_close_time_utc"] for row in rows}
        if len(event_close_set) != 1:
            _error(f"event {event} has inconsistent close time")
        stage = next(iter(stage_set))
        event_close = next(iter(event_close_set))
        selected: Mapping[str, str] | None = None

        for ttc in ANCHOR_ORDER:
            qualifying = [
                row for row in rows
                if int(row["ttc_target_minutes"]) == ttc
                and _decimal(row["net_edge_per_contract"], "net_edge_per_contract") >= threshold
            ]
            if qualifying:
                qualifying.sort(key=_candidate_sort_key)
                selected = qualifying[0]
                break

        base = {
            "schema_version": "kxbtcd_candidate_e_quoted_entry_threshold_event_selection.v1",
            "strategy_id": STRATEGY_ID,
            "threshold_dollars": _format_decimal(threshold),
            "event_ticker": event,
            "event_close_time_utc": event_close,
        }
        if selected is None:
            base.update(
                {
                    "action": "ABSTAIN",
                    "stage": stage,
                    "ttc_target_minutes": "",
                    "decision_time_utc": "",
                    "market_ticker": "",
                    "structural_role": "",
                    "side": "",
                    "candidate_probability": "",
                    "quoted_purchase_price": "",
                    "standard_entry_fee": "",
                    "net_edge_per_contract": "",
                }
            )
        else:
            base.update(
                {
                    "action": "ENTER",
                    "stage": selected["stage"],
                    "ttc_target_minutes": selected["ttc_target_minutes"],
                    "decision_time_utc": selected["decision_time_utc"],
                    "market_ticker": selected["market_ticker"],
                    "structural_role": selected["structural_role"],
                    "side": selected["side"],
                    "candidate_probability": selected["candidate_probability"],
                    "quoted_purchase_price": selected["quoted_purchase_price"],
                    "standard_entry_fee": selected["standard_entry_fee"],
                    "net_edge_per_contract": selected["net_edge_per_contract"],
                }
            )
        selections.append(base)

    selections.sort(key=lambda row: (row["event_close_time_utc"], row["event_ticker"]))
    return tuple(selections)


def _count_by(rows: Sequence[Mapping[str, str]], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        value = row.get(field, "")
        if not value:
            continue
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def build_opportunity_summary(
    *,
    side_states: Sequence[Mapping[str, str]],
    selections_by_threshold: Mapping[Decimal, Sequence[Mapping[str, str]]],
    input_sha256s: Mapping[str, str],
    config_document: Mapping[str, Any],
) -> dict[str, Any]:
    threshold_summaries: dict[str, Any] = {}
    for threshold in THRESHOLDS:
        rows = list(selections_by_threshold[threshold])
        enters = [row for row in rows if row["action"] == "ENTER"]
        abstains = len(rows) - len(enters)
        edges = [_decimal(row["net_edge_per_contract"], "edge") for row in enters]
        threshold_summaries[_format_decimal(threshold)] = {
            "event_count": len(rows),
            "enter_count": len(enters),
            "abstain_count": abstains,
            "enter_rate": (len(enters) / len(rows)) if rows else None,
            "side_counts": _count_by(enters, "side"),
            "ttc_counts": _count_by(enters, "ttc_target_minutes"),
            "structural_role_counts": _count_by(enters, "structural_role"),
            "stage_counts": _count_by(enters, "stage"),
            "mean_selected_net_edge": (
                float(sum(edges, Decimal("0")) / Decimal(len(edges))) if edges else None
            ),
            "min_selected_net_edge": float(min(edges)) if edges else None,
            "max_selected_net_edge": float(max(edges)) if edges else None,
        }

    state_edges = [_decimal(row["net_edge_per_contract"], "edge") for row in side_states]
    document = {
        "schema_version": "kxbtcd_candidate_e_quoted_entry_opportunity_audit_summary.v1",
        "strategy_id": STRATEGY_ID,
        "strategy_predeclaration_fingerprint": config_document[
            "strategy_predeclaration_fingerprint"
        ],
        "scope": {
            "stages": list(DEVELOPMENT_STAGES),
            "event_count": len({row["event_ticker"] for row in side_states}),
            "candidate_probability_row_count": len(side_states) // 2,
            "candidate_side_state_count": len(side_states),
        },
        "input_sha256s": dict(sorted(input_sha256s.items())),
        "threshold_summaries": threshold_summaries,
        "all_candidate_side_state_net_edge": {
            "mean": float(sum(state_edges, Decimal("0")) / Decimal(len(state_edges))) if state_edges else None,
            "min": float(min(state_edges)) if state_edges else None,
            "max": float(max(state_edges)) if state_edges else None,
        },
        "safety": {
            "settlement_outcomes_used": False,
            "realized_pnl_calculated": False,
            "threshold_winner_selected": False,
            "c1_c2_strategy_pnl_accessed": False,
            "c3_accessed": False,
            "protected_reserve_accessed": False,
            "network_accessed": False,
            "orders_submitted": False,
        },
    }
    document["audit_fingerprint"] = canonical_sha256(document)
    return document
