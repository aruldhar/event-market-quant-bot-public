"""Checkpoint 21N-B frozen Strategy-v1 development economic evaluator primitives.

This module may score only the already-exposed H1_OOF/H2/H3 settlement outcomes
after the implementation is safely closed. It binds the exact 21N-A opportunity
audit and selection CSV before calculating any realized economic metric.

It has no network, order, paper-broker, demo, or real-execution surface.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CONFIG_PATH = Path("configs/kxbtcd_candidate_e_quoted_entry_hold_v1_development_economics.json")
STRATEGY_CONFIG_PATH = Path("configs/kxbtcd_candidate_e_quoted_entry_hold_v1.json")

STRATEGY_ID = "kxbtcd_candidate_e_quoted_entry_hold_v1"
CANDIDATE_ID = "kxbtcd_btc_distance_offset_logistic.v1"
EXPECTED_STRATEGY_FINGERPRINT = "5abea8adcaa782a57c9f69ef96b638fe1779370774e9f1c99a81b4340d42a8a6"
EXPECTED_AUDIT_FINGERPRINT = "7175175f11bb2714d4bbfc9dc59d9d23d7be721fa0295d7ed664d598a1036ae0"
EXPECTED_STRATEGY_CONFIG_SHA256 = "3e7516745b6780815099149bda408771884e59c6fc638488ee68c04ba1a739fb"
EXPECTED_SELECTION_SHA256 = "3c43d7c489dac9d761f442f594af24e1a52d478fe2e3bfdfc9e92eb84e636121"
EXPECTED_ECONOMICS_FINGERPRINT = "692b7239067b3024db908fc0e0809f33f900f685faec97c45743195e19d364e5"

DEVELOPMENT_STAGES = ("H1_OOF", "H2", "H3")
PREDICTION_SCHEMAS = {
    "H1_OOF": "kxbtcd_candidate_e_h1_oof_prediction.v1",
    "H2": "kxbtcd_candidate_e_h2_prediction.v1",
    "H3": "kxbtcd_candidate_e_h3_prediction.v1",
}
EXPECTED_PREDICTION_SHA256S = {
    "H1_OOF": "867a77cbbf034a574983cb6fb301a77614674d3254297f8e15db377d5c34df16",
    "H2": "4aa6efe3c3bdc231fc8289f11fe01e1ad5a65910ae0ea92d2586447fd6b7d3d6",
    "H3": "091affc5ac088aa61db43a5df18f15178bceeea2ee26bd266b61fd059fd08380",
}
EXPECTED_ROW_COUNTS = {"H1_OOF": 31656, "H2": 22354, "H3": 22409}
EXPECTED_EVENT_COUNTS = {"H1_OOF": 1070, "H2": 750, "H3": 750}
EXPECTED_TOTAL_EVENTS = 2570
EXPECTED_SELECTION_ROWS_PER_THRESHOLD = 2570
EXPECTED_ENTER_COUNTS = {
    Decimal("0.00"): 820,
    Decimal("0.01"): 542,
    Decimal("0.02"): 306,
    Decimal("0.03"): 159,
    Decimal("0.05"): 33,
}

THRESHOLDS = (
    Decimal("0.00"),
    Decimal("0.01"),
    Decimal("0.02"),
    Decimal("0.03"),
    Decimal("0.05"),
)
SELECTION_ELIGIBLE_THRESHOLDS = (
    Decimal("0.00"),
    Decimal("0.01"),
    Decimal("0.02"),
    Decimal("0.03"),
)
STRESSES = (
    Decimal("0.00"),
    Decimal("0.01"),
    Decimal("0.02"),
    Decimal("0.03"),
)
BLOCK_COUNT = 5
EVENTS_PER_BLOCK = 514
ONE_CENT = Decimal("0.01")
FEE_RATE = Decimal("0.07")

SELECTION_SCHEMA = "kxbtcd_candidate_e_quoted_entry_threshold_event_selection.v1"
EVALUATION_SCHEMA = "kxbtcd_candidate_e_quoted_entry_hold_development_economic_evaluation.v1"
RECEIPT_SCHEMA = "kxbtcd_candidate_e_quoted_entry_hold_development_economic_receipt.v1"

SCENARIO_FIELDS = (
    "schema_version",
    "strategy_id",
    "threshold_dollars",
    "stress_dollars",
    "event_ticker",
    "event_close_time_utc",
    "block_id",
    "stage",
    "action",
    "market_ticker",
    "structural_role",
    "ttc_target_minutes",
    "side",
    "candidate_probability",
    "quoted_purchase_price",
    "quoted_standard_entry_fee",
    "quoted_net_edge_per_contract",
    "outcome",
    "side_payout",
    "scenario_valid",
    "scenario_purchase_price",
    "scenario_standard_entry_fee",
    "scenario_capital_deployed",
    "scenario_realized_pnl",
)

THRESHOLD_SCORE_FIELDS = (
    "threshold_dollars",
    "selection_eligible",
    "entry_count",
    "abstention_count",
    "base_mean_pnl_per_event",
    "plus_1c_mean_pnl_per_event",
    "base_positive_block_count",
    "base_newest_block_positive",
    "base_h3_mean_pnl_per_event",
    "condition_base_pooled_positive",
    "condition_plus_1c_pooled_positive",
    "condition_at_least_4_of_5_blocks_positive",
    "condition_newest_block_positive",
    "condition_h3_positive",
    "development_gate_pass",
)


class DevelopmentEconomicsError(RuntimeError):
    """Raised when the frozen economic evaluation contract is violated."""


def _error(message: str) -> None:
    raise DevelopmentEconomicsError(message)


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DevelopmentEconomicsError(f"{name} must be decimal-compatible") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _unit(value: Any, name: str) -> Decimal:
    result = _decimal(value, name)
    if result < 0 or result > 1:
        _error(f"{name} must be in [0,1]")
    return result


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    text = format(value, "f")
    if "." not in text:
        return text + ".0"
    stripped = text.rstrip("0").rstrip(".")
    return stripped if stripped else "0"


def _parse_outcome(value: Any, name: str) -> int:
    text = str(value).strip()
    if text not in {"0", "1", "0.0", "1.0"}:
        _error(f"{name} must be binary 0/1")
    return int(float(text))


def _parse_utc(value: Any, name: str) -> datetime:
    text = str(value).strip()
    if not text:
        _error(f"{name} is empty")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise DevelopmentEconomicsError(f"{name} is not ISO timestamp") from exc
    if dt.tzinfo is None:
        _error(f"{name} must be timezone-aware")
    return dt.astimezone(timezone.utc)


def canonical_sha256(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: str | Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        _error(f"JSON object required: {path}")
    return value


def validate_economics_predeclaration(path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    document = load_json(path)
    if document.get("schema_version") != "kxbtcd_candidate_e_quoted_entry_hold_development_economics_predeclaration.v1":
        _error("development economics schema mismatch")
    if document.get("strategy_id") != STRATEGY_ID:
        _error("strategy identity mismatch")
    if document.get("parent_strategy_predeclaration_fingerprint") != EXPECTED_STRATEGY_FINGERPRINT:
        _error("parent Strategy-v1 fingerprint mismatch")
    binding = document.get("opportunity_audit_binding")
    if not isinstance(binding, dict) or binding.get("audit_fingerprint") != EXPECTED_AUDIT_FINGERPRINT:
        _error("opportunity audit fingerprint mismatch")
    if tuple(_decimal(v, "threshold") for v in document["strategy_policies"]["all_thresholds_dollars"]) != THRESHOLDS:
        _error("threshold menu changed")
    if tuple(_decimal(v, "eligible threshold") for v in document["strategy_policies"]["selection_eligible_thresholds_dollars"]) != SELECTION_ELIGIBLE_THRESHOLDS:
        _error("selection-eligible threshold menu changed")
    if tuple(_decimal(v, "stress") for v in document["stress_policy"]["adverse_purchase_price_stress_dollars"]) != STRESSES:
        _error("stress menu changed")
    if document["development_scope"].get("chronological_block_count") != BLOCK_COUNT:
        _error("development block count changed")
    if document["development_scope"].get("events_per_block") != EVENTS_PER_BLOCK:
        _error("development block size changed")
    safety = document.get("safety")
    if not isinstance(safety, dict):
        _error("safety object missing")
    for key in (
        "development_strategy_pnl_calculated_before_implementation_freeze",
        "c1_c2_strategy_pnl_authorized",
        "c3_accessed",
        "protected_reserve_accessed",
        "network_access_authorized",
        "paper_broker_authorized",
        "demo_execution_authorized",
        "real_money_execution_authorized",
        "orders_authorized",
    ):
        if safety.get(key) is not False:
            _error(f"safety.{key} must be false")
    supplied = str(document.get("development_economics_predeclaration_fingerprint", "")).strip()
    copy = dict(document)
    copy.pop("development_economics_predeclaration_fingerprint", None)
    expected = canonical_sha256(copy)
    if supplied != expected:
        _error(f"development economics fingerprint mismatch: {supplied} != {expected}")
    if supplied != EXPECTED_ECONOMICS_FINGERPRINT:
        _error("development economics fingerprint is not the frozen 21N-B value")
    return document


def validate_strategy_config_file(path: str | Path = STRATEGY_CONFIG_PATH) -> dict[str, Any]:
    if sha256_file(path) != EXPECTED_STRATEGY_CONFIG_SHA256:
        _error("Strategy-v1 config file hash changed from opportunity audit")
    document = load_json(path)
    if document.get("strategy_id") != STRATEGY_ID:
        _error("Strategy-v1 config identity mismatch")
    if document.get("strategy_predeclaration_fingerprint") != EXPECTED_STRATEGY_FINGERPRINT:
        _error("Strategy-v1 config fingerprint mismatch")
    return document


def validate_opportunity_audit_summary(summary: Mapping[str, Any]) -> None:
    if summary.get("strategy_id") != STRATEGY_ID:
        _error("opportunity summary strategy mismatch")
    supplied = str(summary.get("audit_fingerprint", "")).strip()
    if supplied != EXPECTED_AUDIT_FINGERPRINT:
        _error("opportunity audit fingerprint is not frozen 21N-A result")
    copy = dict(summary)
    copy.pop("audit_fingerprint", None)
    output_hashes = copy.pop("output_sha256s", None)
    if canonical_sha256(copy) != EXPECTED_AUDIT_FINGERPRINT:
        _error("opportunity summary does not reproduce audit fingerprint")
    if not isinstance(output_hashes, dict):
        _error("opportunity summary missing output hashes")
    if output_hashes.get("threshold_event_selections") != EXPECTED_SELECTION_SHA256:
        _error("opportunity summary selection hash mismatch")
    safety = summary.get("safety")
    if not isinstance(safety, dict):
        _error("opportunity summary safety missing")
    for key in (
        "settlement_outcomes_used",
        "realized_pnl_calculated",
        "threshold_winner_selected",
        "c1_c2_strategy_pnl_accessed",
        "c3_accessed",
        "protected_reserve_accessed",
        "network_accessed",
        "orders_submitted",
    ):
        if safety.get(key) is not False:
            _error(f"opportunity summary safety changed: {key}")


def validate_selection_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    selection_path: str | Path | None = None,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, str], ...]:
    if selection_path is not None and sha256_file(selection_path) != EXPECTED_SELECTION_SHA256:
        _error("threshold-event selection file hash changed from 21N-A audit")

    projected: list[dict[str, str]] = []
    seen: set[tuple[Decimal, str]] = set()
    per_threshold_events: dict[Decimal, set[str]] = {t: set() for t in THRESHOLDS}
    enter_counts: dict[Decimal, int] = {t: 0 for t in THRESHOLDS}
    event_identity: dict[str, tuple[str, str]] = {}

    for index, source in enumerate(rows):
        if source.get("schema_version") != SELECTION_SCHEMA:
            _error(f"selection row[{index}] schema mismatch")
        if source.get("strategy_id") != STRATEGY_ID:
            _error(f"selection row[{index}] strategy mismatch")
        threshold = _decimal(source.get("threshold_dollars"), f"selection[{index}].threshold")
        if threshold not in THRESHOLDS:
            _error(f"selection row[{index}] threshold outside frozen menu")
        event = str(source.get("event_ticker", "")).strip()
        close = str(source.get("event_close_time_utc", "")).strip()
        stage = str(source.get("stage", "")).strip()
        action = str(source.get("action", "")).strip()
        if not event or not close or stage not in DEVELOPMENT_STAGES:
            _error(f"selection row[{index}] incomplete event identity")
        _parse_utc(close, f"selection[{index}].event_close_time_utc")
        key = (threshold, event)
        if key in seen:
            _error(f"duplicate threshold/event selection: {threshold} {event}")
        seen.add(key)
        per_threshold_events[threshold].add(event)
        prior = event_identity.setdefault(event, (close, stage))
        if prior != (close, stage):
            _error(f"event {event} identity differs across thresholds")
        if action not in {"ENTER", "ABSTAIN"}:
            _error(f"selection row[{index}] action invalid")

        row = {str(k): str(v) for k, v in source.items()}
        if action == "ENTER":
            enter_counts[threshold] += 1
            side = row.get("side", "").strip()
            if side not in {"YES", "NO"}:
                _error(f"selection row[{index}] side invalid")
            if not row.get("market_ticker", "").strip():
                _error(f"selection row[{index}] entered market missing")
            _unit(row.get("quoted_purchase_price"), f"selection[{index}].quoted_purchase_price")
            _unit(row.get("standard_entry_fee"), f"selection[{index}].standard_entry_fee")
            _decimal(row.get("net_edge_per_contract"), f"selection[{index}].net_edge_per_contract")
        projected.append(row)

    if enforce_frozen_counts:
        if len(event_identity) != EXPECTED_TOTAL_EVENTS:
            _error(f"development event count changed: {len(event_identity)} != {EXPECTED_TOTAL_EVENTS}")
        canonical_events: set[str] | None = None
        for threshold in THRESHOLDS:
            events = per_threshold_events[threshold]
            if len(events) != EXPECTED_SELECTION_ROWS_PER_THRESHOLD:
                _error(f"threshold {threshold} event count changed")
            if canonical_events is None:
                canonical_events = events
            elif events != canonical_events:
                _error("threshold policies do not share the same event universe")
            if enter_counts[threshold] != EXPECTED_ENTER_COUNTS[threshold]:
                _error(
                    f"threshold {threshold} enter count changed: "
                    f"{enter_counts[threshold]} != {EXPECTED_ENTER_COUNTS[threshold]}"
                )
        if len(projected) != EXPECTED_TOTAL_EVENTS * len(THRESHOLDS):
            _error("selection row count changed")

    projected.sort(
        key=lambda row: (
            _decimal(row["threshold_dollars"], "threshold"),
            _parse_utc(row["event_close_time_utc"], "event_close"),
            row["event_ticker"],
        )
    )
    return tuple(projected)


def build_outcome_map(
    sources_by_stage: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    source_paths: Mapping[str, str | Path] | None = None,
    enforce_frozen_counts: bool = True,
) -> dict[tuple[str, str, str], int]:
    if set(sources_by_stage) != set(DEVELOPMENT_STAGES):
        _error("outcome sources must be exactly H1_OOF, H2, H3")
    if source_paths is not None:
        for stage, expected in EXPECTED_PREDICTION_SHA256S.items():
            path = source_paths.get(stage)
            if path is None or sha256_file(path) != expected:
                _error(f"{stage} prediction source hash changed")

    result: dict[tuple[str, str, str], int] = {}
    stage_rows = {stage: 0 for stage in DEVELOPMENT_STAGES}
    stage_events = {stage: set() for stage in DEVELOPMENT_STAGES}
    state_seen = {stage: set() for stage in DEVELOPMENT_STAGES}
    for stage in DEVELOPMENT_STAGES:
        schema = PREDICTION_SCHEMAS[stage]
        for index, source in enumerate(sources_by_stage[stage]):
            if source.get("schema_version") != schema:
                _error(f"{stage} outcome row[{index}] schema mismatch")
            if source.get("candidate_id") != CANDIDATE_ID:
                continue
            state = str(source.get("state_id", "")).strip()
            event = str(source.get("event_ticker", "")).strip()
            market = str(source.get("market_ticker", "")).strip()
            if not state or not event or not market:
                _error(f"{stage} outcome row[{index}] identity missing")
            if state in state_seen[stage]:
                _error(f"duplicate {stage} state {state}")
            state_seen[stage].add(state)
            stage_rows[stage] += 1
            stage_events[stage].add(event)
            outcome = _parse_outcome(source.get("outcome"), f"{stage}[{index}].outcome")
            key = (stage, event, market)
            prior = result.setdefault(key, outcome)
            if prior != outcome:
                _error(f"inconsistent outcome for {stage}/{event}/{market}")
    if enforce_frozen_counts:
        for stage in DEVELOPMENT_STAGES:
            if stage_rows[stage] != EXPECTED_ROW_COUNTS[stage]:
                _error(f"{stage} Candidate-E outcome row count changed")
            if len(stage_events[stage]) != EXPECTED_EVENT_COUNTS[stage]:
                _error(f"{stage} Candidate-E event count changed")
    return result


def build_event_blocks(selection_rows: Sequence[Mapping[str, str]]) -> dict[str, str]:
    events: dict[str, tuple[datetime, str]] = {}
    for row in selection_rows:
        event = row["event_ticker"]
        close_text = row["event_close_time_utc"]
        close = _parse_utc(close_text, f"{event}.event_close_time_utc")
        prior = events.setdefault(event, (close, close_text))
        if prior[0] != close:
            _error(f"event {event} close time inconsistent")
    ordered = sorted(events, key=lambda event: (events[event][0], event))
    if len(ordered) != EXPECTED_TOTAL_EVENTS:
        _error("development event universe changed before block construction")
    if len(ordered) != BLOCK_COUNT * EVENTS_PER_BLOCK:
        _error("development events no longer divide into frozen 5x514 blocks")
    return {
        event: f"B{index // EVENTS_PER_BLOCK}"
        for index, event in enumerate(ordered)
    }


def standard_entry_fee(price: Decimal) -> Decimal:
    price = _unit(price, "fee price")
    raw = FEE_RATE * price * (Decimal("1") - price)
    return raw.quantize(ONE_CENT, rounding=ROUND_CEILING)


def realized_side_payout(side: str, outcome: int) -> Decimal:
    if side == "YES":
        return Decimal(outcome)
    if side == "NO":
        return Decimal(1 - outcome)
    _error("side must be YES or NO")


def realized_trade_scenario(
    *,
    side: str,
    outcome: int,
    quoted_purchase_price: Any,
    stress: Decimal,
) -> dict[str, Any]:
    price = _unit(quoted_purchase_price, "quoted_purchase_price") + stress
    if price < 0 or price > 1:
        return {
            "valid": False,
            "purchase_price": None,
            "fee": None,
            "capital_deployed": None,
            "pnl": None,
            "payout": realized_side_payout(side, outcome),
        }
    fee = standard_entry_fee(price)
    payout = realized_side_payout(side, outcome)
    capital = price + fee
    pnl = payout - capital
    return {
        "valid": True,
        "purchase_price": price,
        "fee": fee,
        "capital_deployed": capital,
        "pnl": pnl,
        "payout": payout,
    }


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        _error("cannot average empty sequence")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _maximum_drawdown(event_pnls: Sequence[Decimal]) -> Decimal:
    cumulative = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    for pnl in event_pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def _scenario_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    invalid = [row for row in rows if row["scenario_valid"] != "true"]
    entries = [row for row in rows if row["action"] == "ENTER"]
    abstains = [row for row in rows if row["action"] == "ABSTAIN"]
    if invalid:
        return {
            "valid": False,
            "invalid_trade_count": len(invalid),
            "event_count": len(rows),
            "entry_count": len(entries),
            "abstention_count": len(abstains),
            "mean_pnl_per_event": None,
            "mean_pnl_per_trade": None,
            "total_pnl": None,
            "total_capital_deployed": None,
            "return_on_deployed_capital": None,
            "win_rate": None,
            "maximum_drawdown": None,
            "worst_trade": None,
        }
    event_pnls = [_decimal(row["scenario_realized_pnl"], "scenario pnl") for row in rows]
    trade_rows = [row for row in entries]
    trade_pnls = [_decimal(row["scenario_realized_pnl"], "trade pnl") for row in trade_rows]
    capital = sum(
        (_decimal(row["scenario_capital_deployed"], "capital") for row in trade_rows),
        Decimal("0"),
    )
    wins = sum(1 for row in trade_rows if _decimal(row["scenario_realized_pnl"], "trade pnl") > 0)
    total = sum(event_pnls, Decimal("0"))
    return {
        "valid": True,
        "invalid_trade_count": 0,
        "event_count": len(rows),
        "entry_count": len(entries),
        "abstention_count": len(abstains),
        "mean_pnl_per_event": _format_decimal(total / Decimal(len(rows))),
        "mean_pnl_per_trade": _format_decimal(_mean(trade_pnls)) if trade_pnls else None,
        "total_pnl": _format_decimal(total),
        "total_capital_deployed": _format_decimal(capital),
        "return_on_deployed_capital": (
            _format_decimal(total / capital) if capital != 0 else None
        ),
        "win_rate": (wins / len(trade_rows)) if trade_rows else None,
        "maximum_drawdown": _format_decimal(_maximum_drawdown(event_pnls)),
        "worst_trade": _format_decimal(min(trade_pnls)) if trade_pnls else None,
    }


def build_development_economic_evaluation(
    selection_rows: Sequence[Mapping[str, str]],
    outcome_map: Mapping[tuple[str, str, str], int],
) -> tuple[dict[str, Any], tuple[dict[str, str], ...], tuple[dict[str, Any], ...]]:
    blocks = build_event_blocks(selection_rows)
    by_threshold: dict[Decimal, list[Mapping[str, str]]] = {t: [] for t in THRESHOLDS}
    for row in selection_rows:
        threshold = _decimal(row["threshold_dollars"], "threshold")
        by_threshold[threshold].append(row)

    scenario_rows: list[dict[str, str]] = []
    threshold_results: dict[str, Any] = {}
    score_rows: list[dict[str, Any]] = []

    for threshold in THRESHOLDS:
        selections = sorted(
            by_threshold[threshold],
            key=lambda row: (_parse_utc(row["event_close_time_utc"], "event close"), row["event_ticker"]),
        )
        scenario_by_stress: dict[Decimal, list[dict[str, str]]] = {s: [] for s in STRESSES}
        for selection in selections:
            action = selection["action"]
            stage = selection["stage"]
            event = selection["event_ticker"]
            block = blocks[event]
            if action == "ENTER":
                market = selection["market_ticker"]
                key = (stage, event, market)
                if key not in outcome_map:
                    _error(f"selected market outcome missing: {key}")
                outcome = outcome_map[key]
            else:
                outcome = None

            for stress in STRESSES:
                base = {
                    "schema_version": "kxbtcd_candidate_e_quoted_entry_hold_event_pnl_scenario.v1",
                    "strategy_id": STRATEGY_ID,
                    "threshold_dollars": _format_decimal(threshold),
                    "stress_dollars": _format_decimal(stress),
                    "event_ticker": event,
                    "event_close_time_utc": selection["event_close_time_utc"],
                    "block_id": block,
                    "stage": stage,
                    "action": action,
                    "market_ticker": selection.get("market_ticker", ""),
                    "structural_role": selection.get("structural_role", ""),
                    "ttc_target_minutes": selection.get("ttc_target_minutes", ""),
                    "side": selection.get("side", ""),
                    "candidate_probability": selection.get("candidate_probability", ""),
                    "quoted_purchase_price": selection.get("quoted_purchase_price", ""),
                    "quoted_standard_entry_fee": selection.get("standard_entry_fee", ""),
                    "quoted_net_edge_per_contract": selection.get("net_edge_per_contract", ""),
                }
                if action == "ABSTAIN":
                    base.update(
                        {
                            "outcome": "",
                            "side_payout": "",
                            "scenario_valid": "true",
                            "scenario_purchase_price": "",
                            "scenario_standard_entry_fee": "",
                            "scenario_capital_deployed": "0",
                            "scenario_realized_pnl": "0",
                        }
                    )
                else:
                    result = realized_trade_scenario(
                        side=selection["side"],
                        outcome=outcome,
                        quoted_purchase_price=selection["quoted_purchase_price"],
                        stress=stress,
                    )
                    base.update(
                        {
                            "outcome": str(outcome),
                            "side_payout": _format_decimal(result["payout"]),
                            "scenario_valid": "true" if result["valid"] else "false",
                            "scenario_purchase_price": _format_decimal(result["purchase_price"]),
                            "scenario_standard_entry_fee": _format_decimal(result["fee"]),
                            "scenario_capital_deployed": _format_decimal(result["capital_deployed"]),
                            "scenario_realized_pnl": _format_decimal(result["pnl"]),
                        }
                    )
                scenario_rows.append(base)
                scenario_by_stress[stress].append(base)

        stress_metrics = {
            _format_decimal(stress): _scenario_metrics(scenario_by_stress[stress])
            for stress in STRESSES
        }
        base_rows = scenario_by_stress[Decimal("0.00")]
        stage_metrics = {
            stage: _scenario_metrics([row for row in base_rows if row["stage"] == stage])
            for stage in DEVELOPMENT_STAGES
        }
        block_metrics = {
            f"B{i}": _scenario_metrics([row for row in base_rows if row["block_id"] == f"B{i}"])
            for i in range(BLOCK_COUNT)
        }
        positive_blocks = sum(
            1
            for value in block_metrics.values()
            if value["valid"] and _decimal(value["mean_pnl_per_event"], "block mean") > 0
        )
        base = stress_metrics["0"]
        plus1 = stress_metrics["0.01"]
        conditions = {
            "base_pooled_positive": (
                base["valid"] and _decimal(base["mean_pnl_per_event"], "base mean") > 0
            ),
            "plus_1c_pooled_positive": (
                plus1["valid"] and _decimal(plus1["mean_pnl_per_event"], "+1c mean") > 0
            ),
            "at_least_4_of_5_blocks_positive": positive_blocks >= 4,
            "newest_block_positive": (
                block_metrics["B4"]["valid"]
                and _decimal(block_metrics["B4"]["mean_pnl_per_event"], "B4 mean") > 0
            ),
            "h3_positive": (
                stage_metrics["H3"]["valid"]
                and _decimal(stage_metrics["H3"]["mean_pnl_per_event"], "H3 mean") > 0
            ),
        }
        gate_pass = all(conditions.values())
        eligible = threshold in SELECTION_ELIGIBLE_THRESHOLDS
        key = _format_decimal(threshold)
        threshold_results[key] = {
            "threshold_dollars": key,
            "selection_eligible": eligible,
            "stress_metrics": stress_metrics,
            "base_stage_metrics": stage_metrics,
            "base_block_metrics": block_metrics,
            "base_positive_block_count": positive_blocks,
            "gate_conditions": conditions,
            "development_gate_pass": gate_pass,
        }
        score_rows.append(
            {
                "threshold_dollars": key,
                "selection_eligible": eligible,
                "entry_count": base["entry_count"],
                "abstention_count": base["abstention_count"],
                "base_mean_pnl_per_event": base["mean_pnl_per_event"],
                "plus_1c_mean_pnl_per_event": plus1["mean_pnl_per_event"],
                "base_positive_block_count": positive_blocks,
                "base_newest_block_positive": conditions["newest_block_positive"],
                "base_h3_mean_pnl_per_event": stage_metrics["H3"]["mean_pnl_per_event"],
                "condition_base_pooled_positive": conditions["base_pooled_positive"],
                "condition_plus_1c_pooled_positive": conditions["plus_1c_pooled_positive"],
                "condition_at_least_4_of_5_blocks_positive": conditions["at_least_4_of_5_blocks_positive"],
                "condition_newest_block_positive": conditions["newest_block_positive"],
                "condition_h3_positive": conditions["h3_positive"],
                "development_gate_pass": gate_pass,
            }
        )

    passing = []
    for threshold in SELECTION_ELIGIBLE_THRESHOLDS:
        result = threshold_results[_format_decimal(threshold)]
        if result["development_gate_pass"]:
            plus1 = result["stress_metrics"]["0.01"]
            if not plus1["valid"]:
                continue
            passing.append(
                (
                    _decimal(plus1["mean_pnl_per_event"], "+1c selection metric"),
                    threshold,
                )
            )
    if passing:
        passing.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected_threshold = passing[0][1]
        status = "PASS_THRESHOLD_SELECTED"
    else:
        selected_threshold = None
        status = "FAIL_NO_THRESHOLD"

    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "strategy_id": STRATEGY_ID,
        "strategy_predeclaration_fingerprint": EXPECTED_STRATEGY_FINGERPRINT,
        "opportunity_audit_fingerprint": EXPECTED_AUDIT_FINGERPRINT,
        "scope": {
            "stages": list(DEVELOPMENT_STAGES),
            "events": EXPECTED_TOTAL_EVENTS,
            "chronological_blocks": BLOCK_COUNT,
            "events_per_block": EVENTS_PER_BLOCK,
        },
        "threshold_results": threshold_results,
        "selection": {
            "eligible_thresholds": [_format_decimal(x) for x in SELECTION_ELIGIBLE_THRESHOLDS],
            "diagnostic_only_thresholds": ["0.05"],
            "winner_metric": "+1c stressed pooled mean P&L per event",
            "exact_tie_rule": "higher_threshold",
            "selected_threshold": _format_decimal(selected_threshold),
            "status": status,
        },
        "future_c1_c2_confirmation_authorized_by_this_result": bool(selected_threshold is not None),
        "safety": {
            "development_strategy_pnl_calculated": True,
            "c1_c2_strategy_pnl_accessed": False,
            "c3_accessed": False,
            "protected_reserve_accessed": False,
            "network_accessed": False,
            "orders_submitted": False,
            "paper_broker_used": False,
            "demo_execution_used": False,
            "real_execution_used": False,
            "historical_fill_claim": False,
            "profitability_guarantee_claim": False,
        },
    }
    evaluation["evaluation_fingerprint"] = canonical_sha256(evaluation)
    scenario_rows.sort(
        key=lambda row: (
            _decimal(row["threshold_dollars"], "threshold"),
            _decimal(row["stress_dollars"], "stress"),
            _parse_utc(row["event_close_time_utc"], "event close"),
            row["event_ticker"],
        )
    )
    return evaluation, tuple(scenario_rows), tuple(score_rows)
