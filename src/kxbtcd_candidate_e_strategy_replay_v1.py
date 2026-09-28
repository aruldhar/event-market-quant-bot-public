"""Checkpoint 21K-A: frozen baseline strategy-replay predeclaration.

This module is deliberately offline and execution-free.  It validates the
predeclared Strategy Replay v1 contract and exposes only small deterministic
helpers needed to test the contract.  It performs no HTTP/WebSocket requests,
model fitting, historical backfill, paper execution, demo execution, or orders.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


CONFIG_PATH = Path("configs/kxbtcd_candidate_e_strategy_replay_v1.json")
SCHEMA_VERSION = "kxbtcd_candidate_e_strategy_replay_predeclaration.v1"
CHECKPOINT_ID = "21K-A"
STRATEGY_ID = "kxbtcd_candidate_e_strategy_replay_v1"
CANDIDATE_ID = "kxbtcd_btc_distance_offset_logistic.v1"
CHAMPION_FINAL_FINGERPRINT = (
    "b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc"
)
PRIMARY_EVENT_COUNT = 4070
PRIMARY_ROW_COUNT = 118862
UNTOUCHED_RESERVE_EVENT_COUNT = 4676
PRIMARY_NET_EDGE = 0.04
PLANNED_CONTRACTS = 10


class StrategyReplayPredeclarationError(RuntimeError):
    """Raised when Strategy Replay v1 no longer matches its frozen contract."""


def _error(message: str) -> None:
    raise StrategyReplayPredeclarationError(message)


def canonical_fingerprint(document: Mapping[str, Any]) -> str:
    payload = {
        key: value
        for key, value in document.items()
        if key != "strategy_predeclaration_fingerprint"
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _require_probability(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        _error(f"{name} must be a finite probability in [0,1]")
    return result


def _require_nonnegative(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        _error(f"{name} must be finite and nonnegative")
    return result


def h1_state_id(
    event_ticker: str,
    market_ticker: str,
    ttc_target_minutes: int,
    structural_role: str,
) -> str:
    return (
        f"{event_ticker}|{market_ticker}|"
        f"TTC{int(ttc_target_minutes)}|{structural_role}"
    )


def signal_executable_price(*, side: str, yes_bid: float, yes_ask: float) -> float:
    bid = _require_probability(yes_bid, "yes_bid")
    ask = _require_probability(yes_ask, "yes_ask")
    if bid > ask:
        _error("YES quote is crossed")
    normalized = side.upper()
    if normalized == "YES":
        return ask
    if normalized == "NO":
        return 1.0 - bid
    _error(f"unsupported side {side!r}")
    raise AssertionError


def side_fair_probability(*, side: str, candidate_probability: float) -> float:
    p = _require_probability(candidate_probability, "candidate_probability")
    normalized = side.upper()
    if normalized == "YES":
        return p
    if normalized == "NO":
        return 1.0 - p
    _error(f"unsupported side {side!r}")
    raise AssertionError


def signal_net_edge(
    *,
    side_fair_probability_value: float,
    executable_price: float,
    fee_total_dollars: float,
    planned_contracts: int = PLANNED_CONTRACTS,
) -> float:
    fair = _require_probability(side_fair_probability_value, "side_fair_probability")
    price = _require_probability(executable_price, "executable_price")
    fee = _require_nonnegative(fee_total_dollars, "fee_total_dollars")
    quantity = int(planned_contracts)
    if quantity <= 0:
        _error("planned_contracts must be positive")
    return fair - price - fee / float(quantity)


def stressed_probability(*, q_market: float, candidate_probability: float) -> float:
    q = _require_probability(q_market, "q_market")
    p = _require_probability(candidate_probability, "candidate_probability")
    result = q + 0.75 * (p - q)
    return _require_probability(result, "stressed_probability")


def validate_strategy_predeclaration(
    path: str | Path = CONFIG_PATH,
) -> dict[str, Any]:
    target = Path(path)
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StrategyReplayPredeclarationError(
            f"could not read strategy predeclaration {target}: {exc}"
        ) from exc
    if not isinstance(document, dict):
        _error("strategy predeclaration root must be an object")

    expected_scalars = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": CHECKPOINT_ID,
        "strategy_id": STRATEGY_ID,
        "candidate_id": CANDIDATE_ID,
        "champion_final_fingerprint": CHAMPION_FINAL_FINGERPRINT,
    }
    for key, expected in expected_scalars.items():
        if document.get(key) != expected:
            _error(f"strategy predeclaration {key} changed")

    research = document.get("research_status")
    if not isinstance(research, Mapping):
        _error("research_status missing")
    for key in (
        "strategy_pnl_inspected_before_freeze",
        "historical_execution_backfill_started_before_freeze",
        "model_refit_authorized",
        "candidate_selection_authorized",
        "order_execution_authorized",
        "paper_broker_authorized",
        "demo_execution_authorized",
        "real_money_execution_authorized",
    ):
        if research.get(key) is not False:
            _error(f"research_status {key} must remain false")

    scope = document.get("primary_evidence_scope")
    if not isinstance(scope, Mapping):
        _error("primary_evidence_scope missing")
    if scope.get("total_event_count") != PRIMARY_EVENT_COUNT:
        _error("primary event count changed")
    if scope.get("total_prediction_row_count") != PRIMARY_ROW_COUNT:
        _error("primary prediction-row count changed")
    stages = scope.get("stages")
    expected_stages = {
        "H1_OOF": (1070, 31656),
        "H2": (750, 22354),
        "H3": (750, 22409),
        "C1": (500, 14887),
        "C2": (500, 14007),
        "C3": (500, 13549),
    }
    if not isinstance(stages, Mapping) or set(stages) != set(expected_stages):
        _error("primary stage set changed")
    for stage, (events, rows) in expected_stages.items():
        value = stages.get(stage)
        if not isinstance(value, Mapping):
            _error(f"stage {stage} missing")
        if value.get("event_count") != events or value.get("row_count") != rows:
            _error(f"stage {stage} counts changed")
    if sum(item[0] for item in expected_stages.values()) != PRIMARY_EVENT_COUNT:
        _error("internal event-count arithmetic failed")
    if sum(item[1] for item in expected_stages.values()) != PRIMARY_ROW_COUNT:
        _error("internal row-count arithmetic failed")

    reserve = document.get("reserve_policy")
    if not isinstance(reserve, Mapping):
        _error("reserve_policy missing")
    if reserve.get("remaining_untouched_historical_reserve_events") != UNTOUCHED_RESERVE_EVENT_COUNT:
        _error("untouched reserve count changed")
    if reserve.get("reserve_access_allowed") is not False:
        _error("untouched reserve access became allowed")
    if reserve.get("reserve_may_be_used_to_repair_or_tune_v1") is not False:
        _error("untouched reserve repair/tuning became allowed")

    signal = document.get("signal_policy")
    if not isinstance(signal, Mapping):
        _error("signal_policy missing")
    if signal.get("anchor_order_ttc_minutes") != [55, 50, 45, 40, 35, 30]:
        _error("anchor order changed")
    if signal.get("structural_roles") != ["q10", "q30", "q50", "q70", "q90"]:
        _error("structural-role set changed")
    if signal.get("sides") != ["YES", "NO"]:
        _error("side set changed")
    if signal.get("maximum_entries_per_event") != 1:
        _error("maximum entries per event changed")
    if signal.get("primary_minimum_net_edge_dollars_per_contract") != PRIMARY_NET_EDGE:
        _error("primary net-edge threshold changed")
    if signal.get("predeclared_sensitivity_net_edge_dollars_per_contract") != [0.03, 0.05]:
        _error("edge sensitivity set changed")
    sizing = signal.get("position_sizing")
    if not isinstance(sizing, Mapping) or sizing.get("planned_contracts") != PLANNED_CONTRACTS:
        _error("planned fixed size changed")
    for key in ("compounding", "averaging_down", "loss_chasing", "side_switching_after_entry"):
        if sizing.get(key) is not False:
            _error(f"position sizing {key} became enabled")

    execution = document.get("historical_execution_policy")
    if not isinstance(execution, Mapping):
        _error("historical_execution_policy missing")
    if execution.get("time_resolution_minutes") != 1:
        _error("historical replay resolution changed")
    if execution.get("same_minute_signal_fill_allowed") is not False:
        _error("same-minute signal fill became allowed")
    if execution.get("maximum_adverse_entry_move_dollars") != 0.01:
        _error("entry slippage cap changed")
    conservative = execution.get("conservative_case")
    if not isinstance(conservative, Mapping) or conservative.get("minute_volume_participation_cap") != 0.10:
        _error("conservative participation cap changed")

    exit_policy = document.get("exit_policy")
    if not isinstance(exit_policy, Mapping):
        _error("exit_policy missing")
    if exit_policy.get("target_fraction_of_initial_model_surplus") != 0.50:
        _error("cash-out target fraction changed")
    if exit_policy.get("force_exit_ttc_minutes") != [5, 4, 3, 2, 1]:
        _error("force-exit window changed")
    if exit_policy.get("hold_to_settlement_benchmark") is not True:
        _error("hold benchmark removed")
    if exit_policy.get("hold_benchmark_may_replace_primary_policy_after_results") is not False:
        _error("hold benchmark became post-hoc replacement policy")

    uncertainty = document.get("model_uncertainty_policy")
    if not isinstance(uncertainty, Mapping) or uncertainty.get("stress_shrinkage_factor") != 0.75:
        _error("uncertainty stress changed")

    gate = document.get("advancement_gate")
    if not isinstance(gate, Mapping):
        _error("advancement_gate missing")
    if gate.get("minimum_conservative_filled_entries") != 200:
        _error("minimum conservative fill gate changed")
    if gate.get("minimum_positive_later_cohorts") != 3:
        _error("later-cohort gate changed")
    if gate.get("gate_pass_does_not_authorize_demo_execution") is not True:
        _error("strategy gate became demo authorization")

    future = document.get("future_strategy_research")
    if not isinstance(future, Mapping):
        _error("future_strategy_research missing")
    required_true = (
        "additional_strategies_allowed_regardless_of_v1_result",
        "each_future_strategy_must_be_separately_versioned",
        "v1_may_not_be_silently_repaired_after_pnl_is_seen",
        "after_v1_economics_are_inspected_the_4070_event_pool_is_strategy_development_evidence",
        "future_variants_on_the_same_pool_may_not_claim_fresh_strategy_validation",
    )
    for key in required_true:
        if future.get(key) is not True:
            _error(f"future strategy rule {key} changed")

    observed = document.get("strategy_predeclaration_fingerprint")
    if not isinstance(observed, str) or len(observed) != 64:
        _error("strategy predeclaration fingerprint missing or invalid")
    expected = canonical_fingerprint(document)
    if observed != expected:
        _error(
            "strategy predeclaration fingerprint mismatch; "
            f"observed={observed}, expected={expected}"
        )
    return document
