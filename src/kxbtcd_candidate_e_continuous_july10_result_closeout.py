"""Checkpoint 21N-V outcome-blind continuous result closeout validator."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.kxbtcd_candidate_e_continuous_july10_source_binding import (
    EXPECTED_BINDING_FINGERPRINT,
    validate_binding,
)
from src.kxbtcd_candidate_e_july10_outcome_blind_binding import sha256_file

DEFAULT_CLOSEOUT_PATH = Path(
    "configs/kxbtcd_candidate_e_continuous_july10_outcome_blind_result_closeout.json"
)
EXPECTED_RESULT_CLOSEOUT_FINGERPRINT = "c55bf6ca462cb4c5d0676a11cac9f37541fe001ce0770d7b08f9fe0721eede35"
EXPECTED_PATH_SHA256 = "b46281f5b7877c26b2b310e874f0f04aa7679ba02e9876800c6e2af1b1f195bf"
EXPECTED_PATH_RELATIVE_PATH = Path("data/analysis/predexon_credit_efficiency/july10_candidate_e_continuous_convergence_reentry_v1_outcome_blind_paths.json")
EXPECTED_IMPLEMENTATION_FINGERPRINT = "cf93bbdd7704ae46954feba8ce73e15a734f117a1791837d87a130e50a15764f"
EXPECTED_SOURCE_BINDING_FINGERPRINT = "8cf8ead70da5f56def1a0d67619b2cda75316e6345383e8ebdcf79f9c4cf62b7"

class ContinuousResultCloseoutError(RuntimeError):
    pass

def _fail(message: str) -> None:
    raise ContinuousResultCloseoutError(message)

def canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("result_closeout_fingerprint", None)
    raw = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def validate_result_closeout(repo_root: str | Path = ".") -> Mapping[str, Any]:
    repo = Path(repo_root)
    p = repo / DEFAULT_CLOSEOUT_PATH
    if not p.is_file():
        _fail(f"result closeout missing: {p}")
    payload = json.loads(p.read_text(encoding="utf-8"))

    if payload.get("schema_version") != "kxbtcd_candidate_e_continuous_july10_outcome_blind_result_closeout.v1":
        _fail("result closeout schema mismatch")
    if payload.get("classification") != "NON_EVALUABLE_STRUCTURAL_UNIVERSE_LIQUIDITY_MISMATCH":
        _fail("result classification changed")
    if payload.get("result_closeout_fingerprint") != EXPECTED_RESULT_CLOSEOUT_FINGERPRINT:
        _fail("result closeout fingerprint field changed")
    if canonical_fingerprint(payload) != EXPECTED_RESULT_CLOSEOUT_FINGERPRINT:
        _fail("result closeout canonical fingerprint changed")

    binding = validate_binding(repo)
    if binding.get("source_binding_fingerprint") != EXPECTED_SOURCE_BINDING_FINGERPRINT:
        _fail("source binding mismatch")

    frozen = payload.get("frozen_bindings", {})
    if frozen.get("implementation_fingerprint") != EXPECTED_IMPLEMENTATION_FINGERPRINT:
        _fail("implementation fingerprint mismatch")
    if frozen.get("source_binding_fingerprint") != EXPECTED_SOURCE_BINDING_FINGERPRINT:
        _fail("closeout source binding mismatch")

    path = repo / EXPECTED_PATH_RELATIVE_PATH
    if not path.is_file():
        _fail(f"outcome-blind path artifact missing: {path}")
    if sha256_file(path) != EXPECTED_PATH_SHA256:
        _fail("outcome-blind path artifact SHA mismatch")

    path_payload = json.loads(path.read_text(encoding="utf-8"))
    if path_payload.get("implementation_fingerprint") != EXPECTED_IMPLEMENTATION_FINGERPRINT:
        _fail("path implementation fingerprint mismatch")
    if path_payload.get("source_binding_fingerprint") != EXPECTED_SOURCE_BINDING_FINGERPRINT:
        _fail("path source binding fingerprint mismatch")
    results = path_payload.get("policy_results")
    if not isinstance(results, list) or len(results) != 60:
        _fail("expected 60 frozen policy scenarios")

    attempts = 0
    trades = 0
    terminal = {}
    for row in results:
        result = row.get("policy_result", {})
        attempts += len(result.get("entry_attempts", []))
        trades += len(result.get("trades", []))
        t = result.get("terminal_state")
        terminal[t] = terminal.get(t, 0) + 1

    if attempts != 0 or trades != 0:
        _fail("frozen path unexpectedly contains entry attempts or trades")
    if terminal != {"NO_FILLED_ENTRY": 60}:
        _fail(f"unexpected terminal states: {terminal}")

    policy = payload.get("frozen_policy_result", {})
    if policy.get("entry_attempt_count") != 0:
        _fail("closeout entry attempts changed")
    if policy.get("filled_trade_count") != 0:
        _fail("closeout filled trades changed")
    if policy.get("terminal_state_counts") != {"NO_FILLED_ENTRY": 60}:
        _fail("closeout terminal-state counts changed")

    gate = payload.get("entry_gate_diagnostic", {})
    if gate.get("market_evaluation_count") != 17550:
        _fail("entry-gate evaluation count changed")
    if gate.get("evaluable_market_state_count") != 0:
        _fail("entry-gate evaluable count changed")

    ladder = payload.get("full_ladder_exploratory_diagnostic", {})
    if ladder.get("ticker_count") != 623:
        _fail("full-ladder ticker count changed")
    if ladder.get("ticker_count_with_any_valid_two_sided_state") != 45:
        _fail("two-sided ticker count changed")
    if ladder.get("frozen_structural_ticker_count_with_any_valid_two_sided_state") != 0:
        _fail("structural two-sided ticker count changed")

    consequence = payload.get("research_consequence", {})
    if consequence.get("continuous_v1_result_status") != "CLOSED_NON_EVALUABLE":
        _fail("v1 closeout status changed")
    if consequence.get("open_settlement_outcomes_for_v1_authorized") is not False:
        _fail("settlement outcomes must remain closed for v1")
    if consequence.get("modify_v1_market_universe_authorized") is not False:
        _fail("v1 market universe must remain frozen")

    safety = payload.get("safety", {})
    exact = {
        "candidate_e_refit": False,
        "nonstructural_candidate_e_scoring_performed": False,
        "outcomes_accessed": False,
        "settlement_dependent_pnl_calculated": False,
        "network_requests": 0,
        "predexon_paid_purchases": 0,
        "orders_placed": 0,
        "paper_broker": False,
        "demo_execution": False,
        "real_money_execution": False,
        "protected_reserve_accessed": False,
    }
    for k, v in exact.items():
        if safety.get(k) != v:
            _fail(f"safety invariant changed: {k}")
    return payload
