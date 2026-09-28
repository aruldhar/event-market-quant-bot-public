from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

CONFIG_PATH = Path("configs/kxbtcd_candidate_e_executable_convergence_liquidation_v1_fee_accounting_amendment.json")
EXPECTED_SCHEMA = "kxbtcd_candidate_e_executable_convergence_liquidation_v1_fee_accounting_amendment.v1"
EXPECTED_STRATEGY = "kxbtcd_candidate_e_executable_convergence_liquidation_v1"
EXPECTED_BASE_FP = "61ede2de623d2ffca6b303895a860fa78de40ea36f0da7fe6b57835ac98d52f6"
EXPECTED_PARENT_CHECKPOINT = "b281be1f32e59578cf0464e2d82178b19d394d2d"
EXPECTED_PARENT_RECEIPT = "09caa0a00be69112ecef83bb1e4e91751d5dc081"

class FeeAccountingAmendmentError(RuntimeError):
    pass

def canonical_fingerprint(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("amendment_fingerprint", None)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

def load_amendment(path: Path | str = CONFIG_PATH) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise FeeAccountingAmendmentError("amendment root must be object")
    return document

def validate_amendment(document: Mapping[str, Any]) -> None:
    if document.get("schema_version") != EXPECTED_SCHEMA:
        raise FeeAccountingAmendmentError("schema mismatch")
    if document.get("strategy_id") != EXPECTED_STRATEGY:
        raise FeeAccountingAmendmentError("strategy mismatch")
    parent = document.get("parent_21n_q")
    if not isinstance(parent, Mapping):
        raise FeeAccountingAmendmentError("parent_21n_q missing")
    if parent.get("base_predeclaration_fingerprint") != EXPECTED_BASE_FP:
        raise FeeAccountingAmendmentError("base fingerprint mismatch")
    if parent.get("checkpoint_commit") != EXPECTED_PARENT_CHECKPOINT:
        raise FeeAccountingAmendmentError("parent checkpoint mismatch")
    if parent.get("receipt_commit") != EXPECTED_PARENT_RECEIPT:
        raise FeeAccountingAmendmentError("parent receipt mismatch")

    reason = document.get("reason")
    if not isinstance(reason, Mapping):
        raise FeeAccountingAmendmentError("reason missing")
    for key in (
        "strategy_logic_changed", "candidate_e_changed", "entry_rule_changed",
        "liquidation_rule_changed", "threshold_menu_changed", "latency_menu_changed",
        "outcomes_accessed_before_amendment", "strategy_pnl_calculated_before_amendment",
    ):
        if reason.get(key) is not False:
            raise FeeAccountingAmendmentError(f"reason.{key} must remain false")

    regime = document.get("accounting_regime")
    if not isinstance(regime, Mapping):
        raise FeeAccountingAmendmentError("accounting_regime missing")
    if regime.get("primary_counterfactual_member_type") != "direct_member":
        raise FeeAccountingAmendmentError("member type changed")
    if regime.get("target_balance_precision_dollars") != "0.0001":
        raise FeeAccountingAmendmentError("balance precision changed")
    if regime.get("minimum_contract_quantity") != "0.01":
        raise FeeAccountingAmendmentError("quantity granularity changed")

    fee = document.get("trade_fee_policy")
    if not isinstance(fee, Mapping):
        raise FeeAccountingAmendmentError("trade_fee_policy missing")
    if fee.get("taker_model_fee_formula") != "0.07*C*P*(1-P)":
        raise FeeAccountingAmendmentError("fee formula changed")
    if fee.get("per_synthetic_fill_trade_fee") != "ceil_to_0.000001(model_fee)":
        raise FeeAccountingAmendmentError("trade-fee precision changed")

    cash = document.get("fill_cash_rounding_policy")
    if not isinstance(cash, Mapping):
        raise FeeAccountingAmendmentError("fill_cash_rounding_policy missing")
    if cash.get("accumulator_scope") != "one_counterfactual_IOC_order_across_all_of_its_synthetic_fills":
        raise FeeAccountingAmendmentError("accumulator scope changed")
    if cash.get("accumulator_resets_between_orders") is not True:
        raise FeeAccountingAmendmentError("accumulator reset rule changed")
    if cash.get("net_fee_must_be_nonnegative") is not True:
        raise FeeAccountingAmendmentError("negative fee unexpectedly allowed")

    supersession = document.get("supersession")
    if not isinstance(supersession, Mapping):
        raise FeeAccountingAmendmentError("supersession missing")
    expected_fields = {
        "fee_and_cash_rounding.trade_fee_rounding",
        "fee_and_cash_rounding.cash_rounding",
        "fee_and_cash_rounding.rounding_accumulator",
    }
    if set(supersession.get("base_fields_superseded", ())) != expected_fields:
        raise FeeAccountingAmendmentError("superseded field set changed")
    if supersession.get("all_non_fee_strategy_rules_remain_frozen_under_base_predeclaration") is not True:
        raise FeeAccountingAmendmentError("non-fee strategy freeze removed")

    safety = document.get("safety")
    if not isinstance(safety, Mapping):
        raise FeeAccountingAmendmentError("safety missing")
    for key in (
        "outcomes_accessed", "strategy_pnl_calculated", "orders_submitted",
        "paper_broker", "demo_execution", "real_money_execution",
        "new_predexon_purchase_authorized", "protected_evidence_access_authorized",
    ):
        if safety.get(key) is not False:
            raise FeeAccountingAmendmentError(f"safety.{key} must remain false")

    observed = document.get("amendment_fingerprint")
    if observed != canonical_fingerprint(document):
        raise FeeAccountingAmendmentError("amendment fingerprint mismatch")
