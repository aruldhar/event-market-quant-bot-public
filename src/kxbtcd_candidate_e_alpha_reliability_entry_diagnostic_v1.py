"""Candidate-E / conditional-alpha entry-ranking diagnostic v1.

Checkpoint 21N-N-B implementation only.

Scientific separation:
- Candidate E supplies valuation probability.
- conditional_alpha is ranking information only.
- adjusted_yes_probability is never used to select or value a trade.
- H2/H3 are exposed development evidence only.
- the real-data CLI is closeout-locked until 21N-N-B is safely closed.

This module is deterministic, network-free, and contains no execution surface.
"""
from __future__ import annotations

import csv
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_conditional_alpha_reliability_v1 import (
    ANCHOR_ORDER,
    SIDE_ORDER,
    SIDES,
    canonical_sha256,
    standard_entry_fee,
)
from .kxbtcd_candidate_e_conditional_alpha_reliability_v2_development import (
    CANDIDATE_ID as PARENT_CANDIDATE_ID,
    DEVELOPMENT_EVALUATION_SCHEMA as PARENT_EVALUATION_SCHEMA,
    DEVELOPMENT_RECEIPT_SCHEMA as PARENT_RECEIPT_SCHEMA,
    ROLLING_PREDICTION_SCHEMA as PARENT_PREDICTION_SCHEMA,
)

DIAGNOSTIC_ID = "kxbtcd_candidate_e_alpha_reliability_entry_diagnostic.v1"
PREDECLARATION_PATH = Path(
    "configs/kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1_predeclaration.json"
)
EXPECTED_PREDECLARATION_FINGERPRINT = "2d8db11742b4f88deb61b810266111b246faf7164ea0c019ad5528cf7326b55e"
EXPECTED_PARENT_EVALUATION_FINGERPRINT = "fa1f6f34ec830ea6c2520a1513f27c3ca1f0d69bf2ddc73e1c90660abfc3efe0"
EXPECTED_PARENT_RECEIPT_FINGERPRINT = "cafcae196ccaa7f352e3685a9d3132e2d0d5356bb5f041c9035adc27db8d90eb"
EXPECTED_PARENT_SELECTED_LAMBDA = 0.001
SCORE_STAGES = ("H2", "H3")
EXPECTED_STAGE_EVENTS = {"H2": 750, "H3": 750}
EXPECTED_SCORE_EVENTS = 1500
QUARTILES = ("Q1", "Q2", "Q3", "Q4")
ONE_CENT = Decimal("0.01")

RESULT_SCHEMA = "kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_result.v1"
RECEIPT_SCHEMA = "kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_receipt.v1"
DECISION_SCHEMA = "kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_decision.v1"

DECISION_FIELDS = (
    "schema_version",
    "diagnostic_id",
    "stage",
    "event_ticker",
    "event_close_time_utc",
    "action",
    "ttc_target_minutes",
    "decision_time_utc",
    "market_ticker",
    "structural_role",
    "side",
    "outcome_yes",
    "candidate_probability",
    "conditional_alpha",
    "quoted_purchase_price",
    "standard_entry_fee",
    "candidate_e_net_edge_per_contract",
    "alpha_quartile",
    "base_realized_net_pnl",
    "plus_1c_realized_net_pnl",
)

N_B_REQUIRED_COMMITTED_PATHS = {
    "configs/kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1_implementation_freeze.json",
    "docs/KXBTCD_CANDIDATE_E_ALPHA_RELIABILITY_ENTRY_DIAGNOSTIC_V1_IMPLEMENTATION.md",
    "evaluate_kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1.py",
    "src/kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1.py",
    "validate_kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1_implementation.py",
    "validate_kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1_result.py",
}


class AlphaEntryDiagnosticError(RuntimeError):
    pass


def _error(message: str) -> None:
    raise AlphaEntryDiagnosticError(message)


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise AlphaEntryDiagnosticError(f"{name} must be decimal-compatible") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise AlphaEntryDiagnosticError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result


def _outcome(value: Any) -> int:
    text = str(value).strip()
    if text not in {"0", "1", "0.0", "1.0"}:
        _error("outcome must be 0 or 1")
    return int(float(text))


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: str | Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for i, row in enumerate(rows):
            if set(row) != set(fields):
                _error(f"CSV row[{i}] field set mismatch")
            writer.writerow({field: row[field] for field in fields})
    temp.replace(target)


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        _error(f"JSON object required: {path}")
    return value


def validate_predeclaration(path: str | Path = PREDECLARATION_PATH) -> dict[str, Any]:
    doc = load_json(path)
    if doc.get("schema_version") != "kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_predeclaration.v1":
        _error("alpha-entry predeclaration schema mismatch")
    if doc.get("diagnostic_id") != DIAGNOSTIC_ID:
        _error("alpha-entry diagnostic ID mismatch")
    supplied = str(doc.get("predeclaration_fingerprint", ""))
    copy = dict(doc)
    copy.pop("predeclaration_fingerprint", None)
    if canonical_sha256(copy) != supplied or supplied != EXPECTED_PREDECLARATION_FINGERPRINT:
        _error("alpha-entry predeclaration fingerprint mismatch")
    if doc["valuation_policy"]["probability_source"] != "Candidate E candidate_probability only":
        _error("Candidate E must remain valuation probability")
    if doc["valuation_policy"]["conditional_adjusted_probability_used_for_valuation"] is not False:
        _error("adjusted probability use is prohibited")
    if doc["alpha_ranking_policy"]["fixed_alpha_threshold_search"] is not False:
        _error("alpha threshold search must remain prohibited")
    return doc


def validate_n_b_closeout_receipt(path: str | Path) -> dict[str, Any]:
    receipt = load_json(path)
    if receipt.get("schema") != "checkpoint_closeout_receipt.v1":
        _error("21N-N-B closeout receipt schema mismatch")
    if not str(receipt.get("checkpoint_message", "")).startswith("Checkpoint 21N-N-B"):
        _error("latest closeout receipt is not Checkpoint 21N-N-B")
    committed = {str(x) for x in receipt.get("committed_paths", ())}
    missing = sorted(N_B_REQUIRED_COMMITTED_PATHS - committed)
    if missing:
        _error("21N-N-B closeout missing required diagnostic implementation paths: " + ", ".join(missing))
    safety = receipt.get("safety", {})
    for key in (
        "blocked_path_check",
        "staged_path_exact_match",
        "staged_diff_check",
        "high_confidence_secret_scan",
    ):
        if safety.get(key) != "PASS":
            _error(f"21N-N-B closeout safety.{key} must be PASS")
    if safety.get("remote_synchronized_before_commit") is not True:
        _error("21N-N-B closeout baseline was not synchronized")
    if safety.get("worktree_clean_after_checkpoint_commit") is not True:
        _error("21N-N-B closeout did not record clean worktree")
    return receipt


def validate_parent_result(
    *,
    evaluation_path: str | Path,
    receipt_path: str | Path,
    prediction_path: str | Path,
    prediction_rows: Sequence[Mapping[str, Any]] | None = None,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], tuple[dict[str, Any], ...]]:
    evaluation = load_json(evaluation_path)
    receipt = load_json(receipt_path)
    rows = tuple(dict(r) for r in (
        read_csv(prediction_path) if prediction_rows is None else prediction_rows
    ))

    if evaluation.get("schema_version") != PARENT_EVALUATION_SCHEMA:
        _error("parent evaluation schema mismatch")
    if evaluation.get("candidate_id") != PARENT_CANDIDATE_ID:
        _error("parent candidate mismatch")
    if evaluation.get("overall_status") != "FAIL_PROBABILITY_GATE":
        _error("parent result must remain FAIL_PROBABILITY_GATE")
    if float(evaluation.get("selected_lambda")) != EXPECTED_PARENT_SELECTED_LAMBDA:
        _error("parent selected lambda changed")
    if evaluation.get("evaluation_fingerprint") != EXPECTED_PARENT_EVALUATION_FINGERPRINT:
        _error("parent evaluation fingerprint changed")

    copy_eval = dict(evaluation)
    supplied_eval = copy_eval.pop("evaluation_fingerprint")
    if canonical_sha256(copy_eval) != supplied_eval:
        _error("parent evaluation canonical fingerprint invalid")

    if receipt.get("schema_version") != PARENT_RECEIPT_SCHEMA:
        _error("parent receipt schema mismatch")
    if receipt.get("candidate_id") != PARENT_CANDIDATE_ID:
        _error("parent receipt candidate mismatch")
    if receipt.get("evaluation_fingerprint") != EXPECTED_PARENT_EVALUATION_FINGERPRINT:
        _error("parent receipt evaluation fingerprint changed")
    if receipt.get("receipt_fingerprint") != EXPECTED_PARENT_RECEIPT_FINGERPRINT:
        _error("parent receipt fingerprint changed")
    copy_receipt = dict(receipt)
    supplied_receipt = copy_receipt.pop("receipt_fingerprint")
    if canonical_sha256(copy_receipt) != supplied_receipt:
        _error("parent receipt canonical fingerprint invalid")

    if receipt["output_sha256s"]["evaluation_sha256"] != sha256_file(evaluation_path):
        _error("parent evaluation SHA mismatch")
    if receipt["output_sha256s"]["rolling_predictions_sha256"] != sha256_file(prediction_path):
        _error("parent rolling prediction SHA mismatch")
    if receipt["output_sha256s"]["entry_decisions_sha256"] is not None:
        _error("parent probability-gate failure unexpectedly has entry artifact")

    validate_prediction_rows(rows, enforce_frozen_counts=enforce_frozen_counts)
    return evaluation, receipt, rows


def validate_prediction_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> None:
    if not rows:
        _error("rolling prediction rows are empty")
    events_by_stage = {stage: set() for stage in SCORE_STAGES}
    event_stage: dict[str, str] = {}
    seen_states: set[str] = set()
    for i, row in enumerate(rows):
        if row.get("schema_version") != PARENT_PREDICTION_SCHEMA:
            _error(f"prediction row[{i}] schema mismatch")
        if row.get("candidate_id") != PARENT_CANDIDATE_ID:
            _error(f"prediction row[{i}] candidate mismatch")
        if float(row.get("selected_lambda")) != EXPECTED_PARENT_SELECTED_LAMBDA:
            _error(f"prediction row[{i}] selected lambda mismatch")
        stage = str(row.get("stage", ""))
        if stage not in SCORE_STAGES:
            _error(f"prediction row[{i}] unauthorized stage")
        state = str(row.get("state_id", "")).strip()
        event = str(row.get("event_ticker", "")).strip()
        market = str(row.get("market_ticker", "")).strip()
        if not state or not event or not market:
            _error(f"prediction row[{i}] identity incomplete")
        if state in seen_states:
            _error(f"duplicate prediction state {state}")
        seen_states.add(state)
        prior = event_stage.setdefault(event, stage)
        if prior != stage:
            _error(f"event {event} crosses score stages")
        events_by_stage[stage].add(event)

        p_e = _decimal(row.get("candidate_probability"), "candidate_probability")
        alpha = _decimal(row.get("conditional_alpha"), "conditional_alpha")
        bid = _decimal(row.get("yes_bid"), "yes_bid")
        ask = _decimal(row.get("yes_ask"), "yes_ask")
        _outcome(row.get("outcome"))
        if not (Decimal("0") <= p_e <= Decimal("1")):
            _error("Candidate-E probability outside [0,1]")
        if not (Decimal("0") < alpha < Decimal("1")):
            _error("conditional alpha must be strict interior")
        if not (Decimal("0") <= bid <= ask <= Decimal("1")):
            _error("invalid quote")
        try:
            ttc = int(str(row.get("ttc_target_minutes")))
        except ValueError as exc:
            raise AlphaEntryDiagnosticError("ttc must be integer") from exc
        if ttc not in ANCHOR_ORDER:
            _error("unexpected TTC anchor")

    if enforce_frozen_counts:
        if len(event_stage) != EXPECTED_SCORE_EVENTS:
            _error("score event count changed")
        for stage, expected in EXPECTED_STAGE_EVENTS.items():
            if len(events_by_stage[stage]) != expected:
                _error(f"{stage} event count changed")


def _candidate_e_opportunity(
    row: Mapping[str, Any],
    side: str,
) -> tuple[Decimal, Decimal, Decimal]:
    p_e = _decimal(row["candidate_probability"], "candidate_probability")
    bid = _decimal(row["yes_bid"], "yes_bid")
    ask = _decimal(row["yes_ask"], "yes_ask")
    if side == "YES":
        p_side = p_e
        price = ask
    elif side == "NO":
        p_side = Decimal("1") - p_e
        price = Decimal("1") - bid
    else:
        _error("side must be YES/NO")
    fee = standard_entry_fee(price)
    edge = p_side - price - fee
    return edge, price, fee


def select_candidate_e_entries(
    rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], ...]:
    """Select at most one Candidate-E-valued opportunity per event.

    Alpha and outcome are carried through only after the trade is chosen. Neither
    participates in the selection key.
    """
    validate_prediction_rows(rows, enforce_frozen_counts=enforce_frozen_counts)
    by_event: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_event.setdefault(str(row["event_ticker"]), []).append(row)

    decisions: list[dict[str, Any]] = []
    for event, event_rows in by_event.items():
        stage_values = {str(r["stage"]) for r in event_rows}
        close_values = {str(r["event_close_time_utc"]) for r in event_rows}
        if len(stage_values) != 1 or len(close_values) != 1:
            _error(f"event {event} metadata inconsistent")
        chosen = None
        for ttc in ANCHOR_ORDER:
            candidates = []
            for row in event_rows:
                if int(str(row["ttc_target_minutes"])) != ttc:
                    continue
                for side in SIDES:
                    edge, price, fee = _candidate_e_opportunity(row, side)
                    if edge >= 0:
                        candidates.append((
                            -edge,
                            str(row["market_ticker"]),
                            SIDE_ORDER[side],
                            row,
                            side,
                            price,
                            fee,
                            edge,
                        ))
            if candidates:
                candidates.sort(key=lambda x: (x[0], x[1], x[2]))
                chosen = candidates[0]
                break

        base = {
            "schema_version": DECISION_SCHEMA,
            "diagnostic_id": DIAGNOSTIC_ID,
            "stage": next(iter(stage_values)),
            "event_ticker": event,
            "event_close_time_utc": next(iter(close_values)),
        }
        if chosen is None:
            decisions.append({
                **base,
                "action": "ABSTAIN",
                "ttc_target_minutes": "",
                "decision_time_utc": "",
                "market_ticker": "",
                "structural_role": "",
                "side": "",
                "outcome_yes": "",
                "candidate_probability": "",
                "conditional_alpha": "",
                "quoted_purchase_price": "",
                "standard_entry_fee": "",
                "candidate_e_net_edge_per_contract": "",
                "alpha_quartile": "",
                "base_realized_net_pnl": "",
                "plus_1c_realized_net_pnl": "",
            })
            continue

        _, _, _, row, side, price, fee, edge = chosen
        # The chosen row is already fixed. Only now attach outcome and alpha.
        alpha = _decimal(row["conditional_alpha"], "conditional_alpha")
        y_yes = _outcome(row["outcome"])
        decisions.append({
            **base,
            "action": "ENTER",
            "ttc_target_minutes": str(row["ttc_target_minutes"]),
            "decision_time_utc": str(row["decision_time_utc"]),
            "market_ticker": str(row["market_ticker"]),
            "structural_role": str(row["structural_role"]),
            "side": side,
            "outcome_yes": str(y_yes),
            "candidate_probability": str(row["candidate_probability"]),
            "conditional_alpha": format(alpha, "f"),
            "quoted_purchase_price": format(price, "f"),
            "standard_entry_fee": format(fee, "f"),
            "candidate_e_net_edge_per_contract": format(edge, "f"),
            "alpha_quartile": "",
            "base_realized_net_pnl": "",
            "plus_1c_realized_net_pnl": "",
        })

    decisions.sort(key=lambda r: (r["event_close_time_utc"], r["event_ticker"]))
    if enforce_frozen_counts and len(decisions) != EXPECTED_SCORE_EVENTS:
        _error("decision event count changed")
    return tuple(decisions)


def realized_pnl(decision: Mapping[str, Any], stress: Decimal) -> Decimal:
    if decision["action"] != "ENTER":
        return Decimal("0")
    quoted = _decimal(decision["quoted_purchase_price"], "quoted_purchase_price")
    price = quoted + stress
    if not (Decimal("0") <= price <= Decimal("1")):
        _error(f"stressed price outside [0,1] for {decision['event_ticker']}")
    fee = standard_entry_fee(price)
    y_yes = int(str(decision["outcome_yes"]))
    side = str(decision["side"])
    win = y_yes if side == "YES" else 1 - y_yes
    return Decimal(win) - price - fee


def assign_alpha_quartiles(decisions: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Assign pooled H2+H3 equal-count quartiles without using outcome/P&L."""
    result = [dict(row) for row in decisions]
    enter_indexes = [i for i, row in enumerate(result) if row["action"] == "ENTER"]
    ordered = sorted(
        enter_indexes,
        key=lambda i: (
            _decimal(result[i]["conditional_alpha"], "conditional_alpha"),
            result[i]["event_ticker"],
            result[i]["market_ticker"],
            SIDE_ORDER[result[i]["side"]],
        ),
    )
    n = len(ordered)
    if n == 0:
        return tuple(result)
    base = n // 4
    remainder = n % 4
    sizes = [base + (1 if q < remainder else 0) for q in range(4)]
    cursor = 0
    for q, size in zip(QUARTILES, sizes):
        for idx in ordered[cursor:cursor + size]:
            result[idx]["alpha_quartile"] = q
        cursor += size
    if cursor != n:
        _error("quartile assignment count mismatch")
    return tuple(result)


def attach_realized_pnl(decisions: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    result = []
    for row in decisions:
        out = dict(row)
        if out["action"] == "ENTER":
            out["base_realized_net_pnl"] = format(realized_pnl(out, Decimal("0.00")), "f")
            out["plus_1c_realized_net_pnl"] = format(realized_pnl(out, ONE_CENT), "f")
        result.append(out)
    return tuple(result)


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _average_ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda x: (x[1], x[0]))
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i + 1
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg = ((i + 1) + j) / 2.0
        for k in range(i, j):
            ranks[indexed[k][0]] = avg
        i = j
    return ranks


def spearman_rank_correlation(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rx = _average_ranks(xs)
    ry = _average_ranks(ys)
    mx = math.fsum(rx) / len(rx)
    my = math.fsum(ry) / len(ry)
    dx = [x - mx for x in rx]
    dy = [y - my for y in ry]
    vx = math.fsum(v * v for v in dx)
    vy = math.fsum(v * v for v in dy)
    if vx == 0.0 or vy == 0.0:
        return None
    corr = math.fsum(a * b for a, b in zip(dx, dy)) / math.sqrt(vx * vy)
    if not math.isfinite(corr):
        _error("Spearman correlation became non-finite")
    return corr


def _fmt(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def summarize_entries(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entered = [r for r in rows if r["action"] == "ENTER"]
    base = [_decimal(r["base_realized_net_pnl"], "base pnl") for r in entered]
    plus1 = [_decimal(r["plus_1c_realized_net_pnl"], "+1c pnl") for r in entered]
    alphas = [_decimal(r["conditional_alpha"], "alpha") for r in entered]
    edges = [_decimal(r["candidate_e_net_edge_per_contract"], "edge") for r in entered]
    return {
        "entry_count": len(entered),
        "mean_alpha": _fmt(_mean(alphas)),
        "mean_candidate_e_quoted_net_edge": _fmt(_mean(edges)),
        "base_pnl_per_entry": _fmt(_mean(base)),
        "plus_1c_pnl_per_entry": _fmt(_mean(plus1)),
        "positive_base_realized_pnl_fraction": (
            None if not base else sum(1 for x in base if x > 0) / len(base)
        ),
        "spearman_alpha_vs_base_realized_pnl": spearman_rank_correlation(
            [float(x) for x in alphas],
            [float(x) for x in base],
        ),
    }


def _subset(
    decisions: Sequence[Mapping[str, Any]],
    *,
    stage: str | None = None,
    quartiles: Sequence[str] | None = None,
) -> list[Mapping[str, Any]]:
    allowed_q = None if quartiles is None else set(quartiles)
    return [
        row for row in decisions
        if (stage is None or row["stage"] == stage)
        and (allowed_q is None or row.get("alpha_quartile") in allowed_q)
    ]


def _metric_decimal(summary: Mapping[str, Any], field: str) -> Decimal | None:
    value = summary.get(field)
    return None if value is None else Decimal(str(value))


def _strict_gt(a: Decimal | None, b: Decimal | None) -> bool:
    return a is not None and b is not None and a > b


def build_diagnostic_result(
    prediction_rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    decisions = select_candidate_e_entries(
        prediction_rows,
        enforce_frozen_counts=enforce_frozen_counts,
    )
    decisions = assign_alpha_quartiles(decisions)
    decisions = attach_realized_pnl(decisions)

    reporting: dict[str, Any] = {}
    for label, stage in (("pooled", None), ("H2", "H2"), ("H3", "H3")):
        scope = _subset(decisions, stage=stage)
        by_q = {
            q: summarize_entries(_subset(scope, quartiles=(q,)))
            for q in QUARTILES
        }
        lower = summarize_entries(_subset(scope, quartiles=("Q1", "Q2")))
        upper = summarize_entries(_subset(scope, quartiles=("Q3", "Q4")))
        baseline = summarize_entries(scope)
        q1 = by_q["Q1"]
        q4 = by_q["Q4"]

        q4_q1_base = (
            None
            if q4["base_pnl_per_entry"] is None or q1["base_pnl_per_entry"] is None
            else format(
                Decimal(q4["base_pnl_per_entry"]) - Decimal(q1["base_pnl_per_entry"]),
                "f",
            )
        )
        q4_q1_plus1 = (
            None
            if q4["plus_1c_pnl_per_entry"] is None or q1["plus_1c_pnl_per_entry"] is None
            else format(
                Decimal(q4["plus_1c_pnl_per_entry"]) - Decimal(q1["plus_1c_pnl_per_entry"]),
                "f",
            )
        )
        upper_lower_base = (
            None
            if upper["base_pnl_per_entry"] is None or lower["base_pnl_per_entry"] is None
            else format(
                Decimal(upper["base_pnl_per_entry"]) - Decimal(lower["base_pnl_per_entry"]),
                "f",
            )
        )
        upper_lower_plus1 = (
            None
            if upper["plus_1c_pnl_per_entry"] is None or lower["plus_1c_pnl_per_entry"] is None
            else format(
                Decimal(upper["plus_1c_pnl_per_entry"]) - Decimal(lower["plus_1c_pnl_per_entry"]),
                "f",
            )
        )
        reporting[label] = {
            "baseline": baseline,
            "by_alpha_quartile": by_q,
            "lower_half_Q1_Q2": lower,
            "upper_half_Q3_Q4": upper,
            "contrasts": {
                "Q4_minus_Q1_base_pnl_per_entry": q4_q1_base,
                "Q4_minus_Q1_plus_1c_pnl_per_entry": q4_q1_plus1,
                "upper_minus_lower_base_pnl_per_entry": upper_lower_base,
                "upper_minus_lower_plus_1c_pnl_per_entry": upper_lower_plus1,
            },
        }

    p = reporting["pooled"]
    h2 = reporting["H2"]
    h3 = reporting["H3"]
    conds = {
        "pooled_Q4_base_gt_Q1": _strict_gt(
            _metric_decimal(p["by_alpha_quartile"]["Q4"], "base_pnl_per_entry"),
            _metric_decimal(p["by_alpha_quartile"]["Q1"], "base_pnl_per_entry"),
        ),
        "pooled_Q4_plus_1c_gt_Q1": _strict_gt(
            _metric_decimal(p["by_alpha_quartile"]["Q4"], "plus_1c_pnl_per_entry"),
            _metric_decimal(p["by_alpha_quartile"]["Q1"], "plus_1c_pnl_per_entry"),
        ),
        "pooled_upper_half_base_gt_lower_half": _strict_gt(
            _metric_decimal(p["upper_half_Q3_Q4"], "base_pnl_per_entry"),
            _metric_decimal(p["lower_half_Q1_Q2"], "base_pnl_per_entry"),
        ),
        "pooled_upper_half_plus_1c_gt_lower_half": _strict_gt(
            _metric_decimal(p["upper_half_Q3_Q4"], "plus_1c_pnl_per_entry"),
            _metric_decimal(p["lower_half_Q1_Q2"], "plus_1c_pnl_per_entry"),
        ),
        "H2_Q4_base_gt_Q1": _strict_gt(
            _metric_decimal(h2["by_alpha_quartile"]["Q4"], "base_pnl_per_entry"),
            _metric_decimal(h2["by_alpha_quartile"]["Q1"], "base_pnl_per_entry"),
        ),
        "H3_Q4_base_gt_Q1": _strict_gt(
            _metric_decimal(h3["by_alpha_quartile"]["Q4"], "base_pnl_per_entry"),
            _metric_decimal(h3["by_alpha_quartile"]["Q1"], "base_pnl_per_entry"),
        ),
        "pooled_spearman_alpha_base_pnl_gt_zero": (
            p["baseline"]["spearman_alpha_vs_base_realized_pnl"] is not None
            and p["baseline"]["spearman_alpha_vs_base_realized_pnl"] > 0
        ),
    }
    result = {
        "schema_version": RESULT_SCHEMA,
        "diagnostic_id": DIAGNOSTIC_ID,
        "predeclaration_fingerprint": EXPECTED_PREDECLARATION_FINGERPRINT,
        "parent_candidate_id": PARENT_CANDIDATE_ID,
        "parent_selected_lambda": EXPECTED_PARENT_SELECTED_LAMBDA,
        "parent_evaluation_fingerprint": EXPECTED_PARENT_EVALUATION_FINGERPRINT,
        "parent_receipt_fingerprint": EXPECTED_PARENT_RECEIPT_FINGERPRINT,
        "evidence_role": "EXPOSED_DEVELOPMENT_EXPLORATORY_ONLY",
        "candidate_e_remains_valuation_probability": True,
        "conditional_alpha_role": "ranking_only",
        "threshold_search_performed": False,
        "reporting": reporting,
        "triage": {
            "label": (
                "PROMISING_EXPLORATORY_SIGNAL"
                if all(conds.values())
                else "NO_CLEAR_SIGNAL"
            ),
            "conditions": conds,
            "strategy_pass": False,
            "fresh_validation_claim": False,
        },
        "safety": {
            "H1_economic_scoring": False,
            "C1_C2_accessed": False,
            "C3_accessed": False,
            "protected_reserve_accessed": False,
            "network_accessed": False,
            "paper_execution": False,
            "demo_execution": False,
            "real_money_execution": False,
            "orders_submitted": False,
        },
    }
    result["result_fingerprint"] = canonical_sha256(result)
    return result, decisions


def build_receipt(
    *,
    result: Mapping[str, Any],
    result_path: str | Path,
    decision_path: str | Path,
    input_hashes: Mapping[str, str],
) -> dict[str, Any]:
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "diagnostic_id": DIAGNOSTIC_ID,
        "predeclaration_fingerprint": EXPECTED_PREDECLARATION_FINGERPRINT,
        "result_fingerprint": result["result_fingerprint"],
        "input_sha256s": dict(input_hashes),
        "output_sha256s": {
            "result_sha256": sha256_file(result_path),
            "decisions_sha256": sha256_file(decision_path),
        },
        "safety": dict(result["safety"]),
    }
    receipt["receipt_fingerprint"] = canonical_sha256(receipt)
    return receipt


__all__ = [
    "AlphaEntryDiagnosticError",
    "DECISION_FIELDS",
    "DIAGNOSTIC_ID",
    "EXPECTED_PREDECLARATION_FINGERPRINT",
    "RESULT_SCHEMA",
    "RECEIPT_SCHEMA",
    "assign_alpha_quartiles",
    "attach_realized_pnl",
    "build_diagnostic_result",
    "build_receipt",
    "load_json",
    "read_csv",
    "realized_pnl",
    "select_candidate_e_entries",
    "sha256_file",
    "spearman_rank_correlation",
    "summarize_entries",
    "validate_n_b_closeout_receipt",
    "validate_parent_result",
    "validate_predeclaration",
    "validate_prediction_rows",
    "write_csv",
]
