"""Incremental Candidate-E edge + conditional-alpha entry score v1.

Checkpoint 21N-N-C-B implementation only.

Frozen score:
    S_beta = z(Candidate-E net quoted edge) + beta*z(logit(alpha))

Scientific purpose:
- beta=0 is the mandatory edge-only benchmark.
- beta>0 is allowed only to test whether alpha adds incremental economic
  ranking value beyond Candidate-E net quoted edge.
- the parent Candidate-E trade population is fixed before this diagnostic.
- entry coverage is fixed at top 25% = 128 of 512 parent ENTER opportunities.
- no real H2/H3 incremental-score P&L may be run until 21N-N-C-B is safely
  closed and pushed.

This module is deterministic, network-free, and has no execution surface.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_conditional_alpha_reliability_v1 import (
    SIDE_ORDER,
    canonical_sha256,
)
from .kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1 import (
    DECISION_FIELDS as PARENT_DECISION_FIELDS,
    DECISION_SCHEMA as PARENT_DECISION_SCHEMA,
    DIAGNOSTIC_ID as PARENT_DIAGNOSTIC_ID,
    RECEIPT_SCHEMA as PARENT_RECEIPT_SCHEMA,
    RESULT_SCHEMA as PARENT_RESULT_SCHEMA,
)

DIAGNOSTIC_ID = "kxbtcd_candidate_e_incremental_alpha_entry_score.v1"
PREDECLARATION_PATH = Path(
    "configs/kxbtcd_candidate_e_incremental_alpha_entry_score_v1_predeclaration.json"
)

EXPECTED_PREDECLARATION_FINGERPRINT = "bb341361f191621564459fef3f68d893181498cb687e131e39183441a3eb27fa"
EXPECTED_PARENT_PREDECLARATION_FINGERPRINT = "2d8db11742b4f88deb61b810266111b246faf7164ea0c019ad5528cf7326b55e"
EXPECTED_PARENT_IMPLEMENTATION_FINGERPRINT = "2bc7d625fa7889ee071322a3d3785becc49fd66fcf409e47713de8dc2405bc0d"
EXPECTED_PARENT_RESULT_FINGERPRINT = "54d2a3588c1e06d4a6cd79234b91c59e4aafecff95e33a7a218e2fac85811d3b"
EXPECTED_PARENT_RECEIPT_FINGERPRINT = "513a27890e5921f7d95b6abd2ddb89bcc5b10e82386124fde050dc44e59a9845"

BETA_GRID = (0.0, 0.25, 0.5, 1.0, 2.0)
EXPECTED_PARENT_EVENT_COUNT = 1500
EXPECTED_PARENT_ENTRY_COUNT = 512
SELECTED_COUNT = 128
SCORE_STAGES = ("H2", "H3")
MIN_STD = 1e-12

RESULT_SCHEMA = "kxbtcd_candidate_e_incremental_alpha_entry_score_result.v1"
RECEIPT_SCHEMA = "kxbtcd_candidate_e_incremental_alpha_entry_score_receipt.v1"
BETA_SCORE_SCHEMA = "kxbtcd_candidate_e_incremental_alpha_entry_score_row.v1"

BETA_SCORE_FIELDS = (
    "schema_version",
    "diagnostic_id",
    "beta",
    "selected",
    "selection_rank",
    "stage",
    "event_ticker",
    "event_close_time_utc",
    "market_ticker",
    "side",
    "candidate_e_net_edge_per_contract",
    "conditional_alpha",
    "logit_alpha",
    "z_edge",
    "z_logit_alpha",
    "score",
    "base_realized_net_pnl",
    "plus_1c_realized_net_pnl",
)

C_B_REQUIRED_COMMITTED_PATHS = {
    "configs/kxbtcd_candidate_e_incremental_alpha_entry_score_v1_implementation_freeze.json",
    "docs/KXBTCD_CANDIDATE_E_INCREMENTAL_ALPHA_ENTRY_SCORE_V1_IMPLEMENTATION.md",
    "evaluate_kxbtcd_candidate_e_incremental_alpha_entry_score_v1.py",
    "src/kxbtcd_candidate_e_incremental_alpha_entry_score_v1.py",
    "validate_kxbtcd_candidate_e_incremental_alpha_entry_score_v1_implementation.py",
    "validate_kxbtcd_candidate_e_incremental_alpha_entry_score_v1_result.py",
}


class IncrementalAlphaScoreError(RuntimeError):
    pass


def _error(message: str) -> None:
    raise IncrementalAlphaScoreError(message)


def _finite(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise IncrementalAlphaScoreError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise IncrementalAlphaScoreError(f"{name} must be decimal-compatible") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        _error(f"JSON object required: {path}")
    return value


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(
    path: str | Path,
    fields: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> None:
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


def validate_predeclaration(path: str | Path = PREDECLARATION_PATH) -> dict[str, Any]:
    doc = load_json(path)
    if doc.get("schema_version") != "kxbtcd_candidate_e_incremental_alpha_entry_score_v1_predeclaration.v1":
        _error("incremental-alpha predeclaration schema mismatch")
    if doc.get("diagnostic_id") != DIAGNOSTIC_ID:
        _error("incremental-alpha diagnostic ID mismatch")
    supplied = str(doc.get("predeclaration_fingerprint", ""))
    copy = dict(doc)
    copy.pop("predeclaration_fingerprint", None)
    if canonical_sha256(copy) != supplied or supplied != EXPECTED_PREDECLARATION_FINGERPRINT:
        _error("incremental-alpha predeclaration fingerprint mismatch")

    if tuple(float(x) for x in doc["beta_tuning"]["grid"]) != BETA_GRID:
        _error("beta grid changed")
    if float(doc["selection_policy"]["selection_fraction"]) != 0.25:
        _error("selection fraction changed")
    if int(doc["selection_policy"]["selected_count_expected"]) != SELECTED_COUNT:
        _error("selected count changed")
    if doc["selection_policy"]["coverage_search_allowed"] is not False:
        _error("coverage search must remain prohibited")
    if doc["selection_policy"]["absolute_threshold_search_allowed"] is not False:
        _error("absolute threshold search must remain prohibited")
    return doc


def validate_c_b_closeout_receipt(path: str | Path) -> dict[str, Any]:
    receipt = load_json(path)
    if receipt.get("schema") != "checkpoint_closeout_receipt.v1":
        _error("21N-N-C-B closeout receipt schema mismatch")
    if not str(receipt.get("checkpoint_message", "")).startswith("Checkpoint 21N-N-C-B"):
        _error("latest closeout receipt is not Checkpoint 21N-N-C-B")
    committed = {str(x) for x in receipt.get("committed_paths", ())}
    missing = sorted(C_B_REQUIRED_COMMITTED_PATHS - committed)
    if missing:
        _error(
            "21N-N-C-B closeout missing required implementation paths: "
            + ", ".join(missing)
        )
    safety = receipt.get("safety", {})
    for key in (
        "blocked_path_check",
        "staged_path_exact_match",
        "staged_diff_check",
        "high_confidence_secret_scan",
    ):
        if safety.get(key) != "PASS":
            _error(f"21N-N-C-B closeout safety.{key} must be PASS")
    if safety.get("remote_synchronized_before_commit") is not True:
        _error("21N-N-C-B closeout baseline was not synchronized")
    if safety.get("worktree_clean_after_checkpoint_commit") is not True:
        _error("21N-N-C-B closeout did not record clean worktree")
    return receipt


def validate_parent_artifacts(
    *,
    result_path: str | Path,
    receipt_path: str | Path,
    decisions_path: str | Path,
    decision_rows: Sequence[Mapping[str, Any]] | None = None,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], tuple[dict[str, Any], ...]]:
    result = load_json(result_path)
    receipt = load_json(receipt_path)
    rows = tuple(
        dict(r)
        for r in (
            read_csv(decisions_path) if decision_rows is None else decision_rows
        )
    )

    if result.get("schema_version") != PARENT_RESULT_SCHEMA:
        _error("parent result schema mismatch")
    if result.get("diagnostic_id") != PARENT_DIAGNOSTIC_ID:
        _error("parent diagnostic ID mismatch")
    if result.get("predeclaration_fingerprint") != EXPECTED_PARENT_PREDECLARATION_FINGERPRINT:
        _error("parent predeclaration fingerprint changed")
    if result.get("result_fingerprint") != EXPECTED_PARENT_RESULT_FINGERPRINT:
        _error("parent result fingerprint changed")
    if result.get("triage", {}).get("label") != "PROMISING_EXPLORATORY_SIGNAL":
        _error("parent triage label changed")
    if result.get("triage", {}).get("strategy_pass") is not False:
        _error("parent diagnostic must remain non-strategy")
    if result.get("threshold_search_performed") is not False:
        _error("parent threshold search boundary changed")
    if int(result["reporting"]["pooled"]["baseline"]["entry_count"]) != EXPECTED_PARENT_ENTRY_COUNT:
        _error("parent reported entry count changed")

    copy_result = dict(result)
    supplied_result = copy_result.pop("result_fingerprint")
    if canonical_sha256(copy_result) != supplied_result:
        _error("parent result canonical fingerprint invalid")

    if receipt.get("schema_version") != PARENT_RECEIPT_SCHEMA:
        _error("parent receipt schema mismatch")
    if receipt.get("diagnostic_id") != PARENT_DIAGNOSTIC_ID:
        _error("parent receipt diagnostic mismatch")
    if receipt.get("predeclaration_fingerprint") != EXPECTED_PARENT_PREDECLARATION_FINGERPRINT:
        _error("parent receipt predeclaration fingerprint changed")
    if receipt.get("result_fingerprint") != EXPECTED_PARENT_RESULT_FINGERPRINT:
        _error("parent receipt result fingerprint changed")
    if receipt.get("receipt_fingerprint") != EXPECTED_PARENT_RECEIPT_FINGERPRINT:
        _error("parent receipt fingerprint changed")

    copy_receipt = dict(receipt)
    supplied_receipt = copy_receipt.pop("receipt_fingerprint")
    if canonical_sha256(copy_receipt) != supplied_receipt:
        _error("parent receipt canonical fingerprint invalid")
    if receipt["output_sha256s"]["result_sha256"] != sha256_file(result_path):
        _error("parent result SHA mismatch")
    if receipt["output_sha256s"]["decisions_sha256"] != sha256_file(decisions_path):
        _error("parent decisions SHA mismatch")

    validate_parent_decisions(rows, enforce_frozen_counts=enforce_frozen_counts)
    return result, receipt, rows


def validate_parent_decisions(
    rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> None:
    if not rows:
        _error("parent decisions are empty")
    seen_events: set[str] = set()
    enter_count = 0
    for i, row in enumerate(rows):
        if row.get("schema_version") != PARENT_DECISION_SCHEMA:
            _error(f"parent decision row[{i}] schema mismatch")
        if row.get("diagnostic_id") != PARENT_DIAGNOSTIC_ID:
            _error(f"parent decision row[{i}] diagnostic ID mismatch")
        stage = str(row.get("stage", ""))
        if stage not in SCORE_STAGES:
            _error(f"parent decision row[{i}] unauthorized stage")
        event = str(row.get("event_ticker", "")).strip()
        if not event or event in seen_events:
            _error(f"parent decision row[{i}] missing/duplicate event")
        seen_events.add(event)

        action = str(row.get("action", ""))
        if action not in {"ENTER", "ABSTAIN"}:
            _error(f"parent decision row[{i}] invalid action")
        if action == "ENTER":
            enter_count += 1
            market = str(row.get("market_ticker", "")).strip()
            side = str(row.get("side", ""))
            if not market or side not in SIDE_ORDER:
                _error(f"parent ENTER row[{i}] identity/side invalid")
            edge = _finite(
                row.get("candidate_e_net_edge_per_contract"),
                "candidate_e_net_edge_per_contract",
            )
            alpha = _finite(row.get("conditional_alpha"), "conditional_alpha")
            _finite(row.get("base_realized_net_pnl"), "base_realized_net_pnl")
            _finite(row.get("plus_1c_realized_net_pnl"), "plus_1c_realized_net_pnl")
            if edge < -1e-15:
                _error("parent Candidate-E selected edge became negative")
            if not 0.0 < alpha < 1.0:
                _error("parent alpha must remain strict interior")

    if enforce_frozen_counts:
        if len(rows) != EXPECTED_PARENT_EVENT_COUNT:
            _error("parent event-decision count changed")
        if enter_count != EXPECTED_PARENT_ENTRY_COUNT:
            _error("parent ENTER count changed")


def extract_population(
    decisions: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_count: bool = True,
) -> tuple[dict[str, Any], ...]:
    """Project only fields needed by the frozen score.

    No outcome or P&L field participates in scaling or score construction.
    P&L is carried only so economics can be evaluated after each top-128 set is
    selected.
    """
    result: list[dict[str, Any]] = []
    for row in decisions:
        if row["action"] != "ENTER":
            continue
        alpha = _finite(row["conditional_alpha"], "conditional_alpha")
        edge = _finite(
            row["candidate_e_net_edge_per_contract"],
            "candidate_e_net_edge_per_contract",
        )
        logit_alpha = math.log(alpha / (1.0 - alpha))
        if not math.isfinite(logit_alpha):
            _error("logit(alpha) became non-finite")
        result.append({
            "stage": str(row["stage"]),
            "event_ticker": str(row["event_ticker"]),
            "event_close_time_utc": str(row["event_close_time_utc"]),
            "market_ticker": str(row["market_ticker"]),
            "side": str(row["side"]),
            "candidate_e_net_edge_per_contract": edge,
            "conditional_alpha": alpha,
            "logit_alpha": logit_alpha,
            "base_realized_net_pnl": _decimal(
                row["base_realized_net_pnl"], "base_realized_net_pnl"
            ),
            "plus_1c_realized_net_pnl": _decimal(
                row["plus_1c_realized_net_pnl"], "plus_1c_realized_net_pnl"
            ),
        })
    if enforce_frozen_count and len(result) != EXPECTED_PARENT_ENTRY_COUNT:
        _error("incremental-alpha population count changed")
    return tuple(result)


@dataclass(frozen=True)
class OutcomeBlindScaler:
    mean_edge: float
    sd_edge: float
    mean_logit_alpha: float
    sd_logit_alpha: float

    def as_dict(self) -> dict[str, float]:
        return {
            "mean_edge": self.mean_edge,
            "sd_edge": self.sd_edge,
            "mean_logit_alpha": self.mean_logit_alpha,
            "sd_logit_alpha": self.sd_logit_alpha,
        }


def fit_outcome_blind_scaler(
    population: Sequence[Mapping[str, Any]],
) -> OutcomeBlindScaler:
    if not population:
        _error("cannot scale empty population")
    edges = [_finite(r["candidate_e_net_edge_per_contract"], "edge") for r in population]
    logits = [_finite(r["logit_alpha"], "logit_alpha") for r in population]
    n = len(population)
    mean_edge = math.fsum(edges) / n
    mean_logit = math.fsum(logits) / n
    var_edge = math.fsum((x - mean_edge) ** 2 for x in edges) / n
    var_logit = math.fsum((x - mean_logit) ** 2 for x in logits) / n
    sd_edge = math.sqrt(var_edge)
    sd_logit = math.sqrt(var_logit)
    if not all(math.isfinite(x) for x in (mean_edge, mean_logit, sd_edge, sd_logit)):
        _error("scaler became non-finite")
    if sd_edge <= MIN_STD:
        _error("Candidate-E edge population standard deviation <= 1e-12")
    if sd_logit <= MIN_STD:
        _error("logit-alpha population standard deviation <= 1e-12")
    return OutcomeBlindScaler(mean_edge, sd_edge, mean_logit, sd_logit)


def score_population(
    population: Sequence[Mapping[str, Any]],
    *,
    scaler: OutcomeBlindScaler,
    beta: float,
) -> tuple[dict[str, Any], ...]:
    beta = float(beta)
    if beta not in BETA_GRID:
        _error("beta outside frozen grid")
    result: list[dict[str, Any]] = []
    for row in population:
        edge = _finite(row["candidate_e_net_edge_per_contract"], "edge")
        logit_alpha = _finite(row["logit_alpha"], "logit_alpha")
        z_edge = (edge - scaler.mean_edge) / scaler.sd_edge
        z_alpha = (logit_alpha - scaler.mean_logit_alpha) / scaler.sd_logit_alpha
        score = z_edge + beta * z_alpha
        if not all(math.isfinite(x) for x in (z_edge, z_alpha, score)):
            _error("score became non-finite")
        result.append({
            **dict(row),
            "beta": beta,
            "z_edge": z_edge,
            "z_logit_alpha": z_alpha,
            "score": score,
        })
    return tuple(result)


def select_top(
    scored: Sequence[Mapping[str, Any]],
    *,
    selected_count: int = SELECTED_COUNT,
) -> tuple[dict[str, Any], ...]:
    """Rank without consulting any outcome/P&L field."""
    if selected_count <= 0 or selected_count > len(scored):
        _error("selected_count outside population")
    ordered = sorted(
        (dict(row) for row in scored),
        key=lambda r: (
            -_finite(r["score"], "score"),
            str(r["event_close_time_utc"]),
            str(r["event_ticker"]),
            str(r["market_ticker"]),
            SIDE_ORDER[str(r["side"])],
        ),
    )
    selected = []
    for rank, row in enumerate(ordered[:selected_count], start=1):
        out = dict(row)
        out["selection_rank"] = rank
        selected.append(out)
    return tuple(selected)


def _mean_decimal(values: Sequence[Decimal]) -> Decimal:
    if not values:
        _error("mean requires at least one value")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _mean_float(values: Sequence[float]) -> float:
    if not values:
        _error("mean requires at least one value")
    return math.fsum(values) / len(values)


def _scope_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "entry_count": 0,
            "base_pnl_per_entry": None,
            "plus_1c_pnl_per_entry": None,
            "positive_base_realized_pnl_fraction": None,
        }
    base = [_decimal(r["base_realized_net_pnl"], "base pnl") for r in rows]
    plus1 = [_decimal(r["plus_1c_realized_net_pnl"], "+1c pnl") for r in rows]
    return {
        "entry_count": len(rows),
        "base_pnl_per_entry": format(_mean_decimal(base), "f"),
        "plus_1c_pnl_per_entry": format(_mean_decimal(plus1), "f"),
        "positive_base_realized_pnl_fraction": sum(1 for x in base if x > 0) / len(base),
    }


def summarize_beta(
    selected: Sequence[Mapping[str, Any]],
    *,
    beta: float,
) -> dict[str, Any]:
    if len(selected) != SELECTED_COUNT:
        _error("beta selected-entry count changed")
    pooled = _scope_metrics(selected)
    h2_rows = [r for r in selected if r["stage"] == "H2"]
    h3_rows = [r for r in selected if r["stage"] == "H3"]
    return {
        "beta": float(beta),
        "selected_entry_count": len(selected),
        "H2_selected_entry_count": len(h2_rows),
        "H3_selected_entry_count": len(h3_rows),
        "mean_score": _mean_float([_finite(r["score"], "score") for r in selected]),
        "mean_candidate_e_net_quoted_edge": _mean_float([
            _finite(r["candidate_e_net_edge_per_contract"], "edge")
            for r in selected
        ]),
        "mean_conditional_alpha": _mean_float([
            _finite(r["conditional_alpha"], "alpha")
            for r in selected
        ]),
        "pooled": pooled,
        "H2": _scope_metrics(h2_rows),
        "H3": _scope_metrics(h3_rows),
    }


def select_beta(beta_summaries: Sequence[Mapping[str, Any]]) -> float:
    if {float(r["beta"]) for r in beta_summaries} != set(BETA_GRID):
        _error("beta summary grid changed")
    ordered = sorted(
        beta_summaries,
        key=lambda r: (
            -_decimal(
                r["pooled"]["plus_1c_pnl_per_entry"],
                "pooled +1c pnl per entry",
            ),
            float(r["beta"]),
        ),
    )
    return float(ordered[0]["beta"])


def _metric(summary: Mapping[str, Any], scope: str, field: str) -> Decimal:
    value = summary[scope][field]
    if value is None:
        _error(f"{scope}.{field} unavailable")
    return Decimal(str(value))


def build_incremental_gate(
    beta_summaries: Sequence[Mapping[str, Any]],
    *,
    selected_beta: float,
) -> dict[str, Any]:
    by_beta = {float(r["beta"]): r for r in beta_summaries}
    selected = by_beta[float(selected_beta)]
    edge_only = by_beta[0.0]
    conditions = {
        "selected_beta_gt_zero": float(selected_beta) > 0.0,
        "pooled_base_gt_edge_only": (
            _metric(selected, "pooled", "base_pnl_per_entry")
            > _metric(edge_only, "pooled", "base_pnl_per_entry")
        ),
        "pooled_plus_1c_gt_edge_only": (
            _metric(selected, "pooled", "plus_1c_pnl_per_entry")
            > _metric(edge_only, "pooled", "plus_1c_pnl_per_entry")
        ),
        "H2_base_gt_edge_only": (
            _metric(selected, "H2", "base_pnl_per_entry")
            > _metric(edge_only, "H2", "base_pnl_per_entry")
        ),
        "H3_base_gt_edge_only": (
            _metric(selected, "H3", "base_pnl_per_entry")
            > _metric(edge_only, "H3", "base_pnl_per_entry")
        ),
        "selected_pooled_base_gt_zero": (
            _metric(selected, "pooled", "base_pnl_per_entry") > 0
        ),
        "selected_pooled_plus_1c_gt_zero": (
            _metric(selected, "pooled", "plus_1c_pnl_per_entry") > 0
        ),
    }
    return {
        "status": (
            "INCREMENTAL_ALPHA_SIGNAL"
            if all(conditions.values())
            else "NO_INCREMENTAL_ALPHA_SIGNAL"
        ),
        "conditions": conditions,
        "strategy_pass": False,
        "fresh_validation_claim": False,
    }


def _score_csv_rows(
    all_scored: Mapping[float, Sequence[Mapping[str, Any]]],
    selected_by_beta: Mapping[float, Sequence[Mapping[str, Any]]],
) -> tuple[dict[str, Any], ...]:
    selected_keys = {
        beta: {
            (
                r["event_ticker"],
                r["market_ticker"],
                r["side"],
            ): int(r["selection_rank"])
            for r in selected
        }
        for beta, selected in selected_by_beta.items()
    }
    result = []
    for beta in BETA_GRID:
        for row in all_scored[beta]:
            key = (row["event_ticker"], row["market_ticker"], row["side"])
            rank = selected_keys[beta].get(key)
            result.append({
                "schema_version": BETA_SCORE_SCHEMA,
                "diagnostic_id": DIAGNOSTIC_ID,
                "beta": repr(float(beta)),
                "selected": "true" if rank is not None else "false",
                "selection_rank": "" if rank is None else str(rank),
                "stage": str(row["stage"]),
                "event_ticker": str(row["event_ticker"]),
                "event_close_time_utc": str(row["event_close_time_utc"]),
                "market_ticker": str(row["market_ticker"]),
                "side": str(row["side"]),
                "candidate_e_net_edge_per_contract": repr(float(row["candidate_e_net_edge_per_contract"])),
                "conditional_alpha": repr(float(row["conditional_alpha"])),
                "logit_alpha": repr(float(row["logit_alpha"])),
                "z_edge": repr(float(row["z_edge"])),
                "z_logit_alpha": repr(float(row["z_logit_alpha"])),
                "score": repr(float(row["score"])),
                "base_realized_net_pnl": format(
                    _decimal(row["base_realized_net_pnl"], "base pnl"), "f"
                ),
                "plus_1c_realized_net_pnl": format(
                    _decimal(row["plus_1c_realized_net_pnl"], "+1c pnl"), "f"
                ),
            })
    return tuple(result)


def build_diagnostic_result(
    parent_decisions: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    validate_parent_decisions(
        parent_decisions,
        enforce_frozen_counts=enforce_frozen_counts,
    )
    population = extract_population(
        parent_decisions,
        enforce_frozen_count=enforce_frozen_counts,
    )
    scaler = fit_outcome_blind_scaler(population)

    all_scored: dict[float, tuple[dict[str, Any], ...]] = {}
    selected_by_beta: dict[float, tuple[dict[str, Any], ...]] = {}
    summaries: list[dict[str, Any]] = []
    for beta in BETA_GRID:
        scored = score_population(population, scaler=scaler, beta=beta)
        selected = select_top(
            scored,
            selected_count=(
                SELECTED_COUNT
                if enforce_frozen_counts
                else max(1, len(scored) // 4)
            ),
        )
        if enforce_frozen_counts and len(selected) != SELECTED_COUNT:
            _error("frozen selected count changed")
        all_scored[beta] = scored
        selected_by_beta[beta] = selected
        # Synthetic tests may use smaller populations. In that case summarize
        # directly without the frozen 128 assertion.
        if enforce_frozen_counts:
            summaries.append(summarize_beta(selected, beta=beta))
        else:
            pooled = _scope_metrics(selected)
            h2 = _scope_metrics([r for r in selected if r["stage"] == "H2"])
            h3 = _scope_metrics([r for r in selected if r["stage"] == "H3"])
            summaries.append({
                "beta": beta,
                "selected_entry_count": len(selected),
                "H2_selected_entry_count": h2["entry_count"],
                "H3_selected_entry_count": h3["entry_count"],
                "mean_score": _mean_float([_finite(r["score"], "score") for r in selected]),
                "mean_candidate_e_net_quoted_edge": _mean_float([
                    _finite(r["candidate_e_net_edge_per_contract"], "edge")
                    for r in selected
                ]),
                "mean_conditional_alpha": _mean_float([
                    _finite(r["conditional_alpha"], "alpha")
                    for r in selected
                ]),
                "pooled": pooled,
                "H2": h2,
                "H3": h3,
            })

    selected_beta = select_beta(summaries)
    gate = build_incremental_gate(summaries, selected_beta=selected_beta)

    result = {
        "schema_version": RESULT_SCHEMA,
        "diagnostic_id": DIAGNOSTIC_ID,
        "predeclaration_fingerprint": EXPECTED_PREDECLARATION_FINGERPRINT,
        "parent_predeclaration_fingerprint": EXPECTED_PARENT_PREDECLARATION_FINGERPRINT,
        "parent_implementation_fingerprint": EXPECTED_PARENT_IMPLEMENTATION_FINGERPRINT,
        "parent_result_fingerprint": EXPECTED_PARENT_RESULT_FINGERPRINT,
        "parent_receipt_fingerprint": EXPECTED_PARENT_RECEIPT_FINGERPRINT,
        "evidence_role": "FULLY_EXPOSED_DEVELOPMENT_EXPLORATORY_ONLY",
        "population_entry_count": len(population),
        "selection_count_per_beta": (
            SELECTED_COUNT if enforce_frozen_counts else max(1, len(population) // 4)
        ),
        "beta_grid": list(BETA_GRID),
        "scaler": scaler.as_dict(),
        "beta_summaries": summaries,
        "selected_beta": selected_beta,
        "incremental_alpha_gate": gate,
        "coverage_search_performed": False,
        "absolute_threshold_search_performed": False,
        "strategy_pass": False,
        "safety": {
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
    return result, _score_csv_rows(all_scored, selected_by_beta)


def build_receipt(
    *,
    result: Mapping[str, Any],
    result_path: str | Path,
    score_path: str | Path,
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
            "beta_scores_sha256": sha256_file(score_path),
        },
        "safety": dict(result["safety"]),
    }
    receipt["receipt_fingerprint"] = canonical_sha256(receipt)
    return receipt


__all__ = [
    "BETA_GRID",
    "BETA_SCORE_FIELDS",
    "BETA_SCORE_SCHEMA",
    "DIAGNOSTIC_ID",
    "EXPECTED_PREDECLARATION_FINGERPRINT",
    "IncrementalAlphaScoreError",
    "OutcomeBlindScaler",
    "RECEIPT_SCHEMA",
    "RESULT_SCHEMA",
    "SELECTED_COUNT",
    "build_diagnostic_result",
    "build_incremental_gate",
    "build_receipt",
    "extract_population",
    "fit_outcome_blind_scaler",
    "load_json",
    "read_csv",
    "score_population",
    "select_beta",
    "select_top",
    "sha256_file",
    "validate_c_b_closeout_receipt",
    "validate_parent_artifacts",
    "validate_parent_decisions",
    "validate_predeclaration",
    "write_csv",
]
