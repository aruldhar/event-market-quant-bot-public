"""Checkpoint 21N-D bounded Strategy-v1 development failure analysis.

Reads only already-exposed 21N-B development economics artifacts. It performs
predeclared descriptive diagnostics on the frozen 3c / displayed-quote policy.
It does not fit, optimize, select, access C1/C2/C3/reserve, or execute orders.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CONFIG_PATH = Path("configs/kxbtcd_candidate_e_quoted_entry_hold_v1_failure_analysis.json")
RESULT_CLOSEOUT_PATH = Path("configs/kxbtcd_candidate_e_quoted_entry_hold_v1_development_result_closeout.json")

EXPECTED_ANALYSIS_ID = "kxbtcd_candidate_e_quoted_entry_hold_v1_development_failure_analysis.v1"
EXPECTED_STRATEGY_ID = "kxbtcd_candidate_e_quoted_entry_hold_v1"
EXPECTED_EVALUATION_FINGERPRINT = "8fa076035ed55cd950d744190b4c88cdacfce07bd57bfe5f7b9ff6f9e76a25bc"
EXPECTED_RESULT_CLOSEOUT_FINGERPRINT = "9837823342eeb7b7c7d44a264b1507cd718310c2dccb83c837f9bb0bc4d1b392"
EXPECTED_PREDECLARATION_FINGERPRINT = "33fb68841a174d50971d40aefae73ab564f96adcb8aefafcf5e86aa16d21bc8b"
PRIMARY_THRESHOLD = Decimal("0.03")
PRIMARY_STRESS = Decimal("0.00")
EXPECTED_PRIMARY_ENTRIES = 159

SLICE_FIELDS = (
    "slice_dimension","slice_value","entry_count","win_count","win_rate",
    "mean_purchase_price","mean_side_fair_probability",
    "calibration_gap_win_rate_minus_fair","mean_quoted_net_edge",
    "mean_entry_fee","gross_pnl_before_fee","total_fee","total_net_pnl",
    "mean_net_pnl_per_trade","mean_winning_trade","mean_losing_trade","worst_trade",
)
TAIL_FIELDS = (
    "scope","rank","event_ticker","stage","block_id","market_ticker","structural_role",
    "ttc_target_minutes","side","candidate_probability","side_fair_probability",
    "quoted_purchase_price","quoted_net_edge_per_contract","entry_fee","outcome",
    "realized_pnl",
)
REGIME_FIELDS = (
    "comparison","metric","left_value","right_value","right_minus_left",
)


class FailureAnalysisError(RuntimeError):
    pass


def _error(message: str) -> None:
    raise FailureAnalysisError(message)


def _dec(value: Any, name: str) -> Decimal:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise FailureAnalysisError(f"{name} must be decimal-compatible") from exc
    if not d.is_finite():
        _error(f"{name} must be finite")
    return d


def _fmt(value: Decimal) -> str:
    text = format(value, "f")
    if "." not in text:
        return text + ".0"
    text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        _error(f"JSON object required: {path}")
    return value


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def write_csv(path: str | Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def validate_predeclaration(path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    doc = load_json(path)
    if doc.get("analysis_id") != EXPECTED_ANALYSIS_ID:
        _error("analysis_id mismatch")
    if doc.get("strategy_id") != EXPECTED_STRATEGY_ID:
        _error("strategy_id mismatch")
    if doc.get("development_evaluation_fingerprint") != EXPECTED_EVALUATION_FINGERPRINT:
        _error("development evaluation fingerprint mismatch")
    if doc.get("development_result_closeout_fingerprint") != EXPECTED_RESULT_CLOSEOUT_FINGERPRINT:
        _error("result closeout fingerprint mismatch")
    supplied = doc.get("failure_analysis_predeclaration_fingerprint")
    copy = dict(doc)
    copy.pop("failure_analysis_predeclaration_fingerprint", None)
    expected = canonical_sha256(copy)
    if supplied != expected or supplied != EXPECTED_PREDECLARATION_FINGERPRINT:
        _error("failure-analysis predeclaration fingerprint mismatch")
    contract = doc.get("interpretation_contract", {})
    required_true = (
        "descriptive_only","no_new_threshold_search","no_ttc_selection","no_role_selection",
        "no_side_selection","no_price_bucket_selection","no_edge_bucket_selection",
        "no_successor_fit","no_successor_strategy_selection","no_c1_c2_strategy_pnl",
        "no_c3_access","no_protected_reserve_access","no_execution",
    )
    for key in required_true:
        if contract.get(key) is not True:
            _error(f"interpretation contract changed: {key}")
    return doc


def validate_result_binding(result_dir: str | Path, config: Mapping[str, Any]) -> dict[str, Path]:
    result_dir = Path(result_dir)
    paths = {
        "evaluation": result_dir / "development_economic_evaluation.json",
        "event_pnl_scenarios": result_dir / "development_event_pnl_scenarios.csv",
        "receipt": result_dir / "development_economic_receipt.json",
        "threshold_scores": result_dir / "development_threshold_scores.csv",
    }
    expected_hashes = config["expected_result_file_sha256s"]
    for key, path in paths.items():
        if not path.is_file():
            _error(f"required result artifact missing: {path}")
        actual = sha256_file(path)
        if actual != expected_hashes[key]:
            _error(f"{key} SHA-256 mismatch: {actual} != {expected_hashes[key]}")
    evaluation = load_json(paths["evaluation"])
    if evaluation.get("evaluation_fingerprint") != EXPECTED_EVALUATION_FINGERPRINT:
        _error("evaluation fingerprint mismatch")
    selection = evaluation.get("selection", {})
    if selection.get("status") != "FAIL_NO_THRESHOLD":
        _error("canonical development status is not FAIL_NO_THRESHOLD")
    if selection.get("selected_threshold") not in (None, ""):
        _error("canonical development result unexpectedly selected a threshold")
    safety = evaluation.get("safety", {})
    for key in ("c1_c2_strategy_pnl_accessed","c3_accessed","protected_reserve_accessed",
                "network_accessed","orders_submitted","paper_broker_used",
                "demo_execution_used","real_execution_used"):
        if safety.get(key) is not False:
            _error(f"canonical evaluation safety flag changed: {key}")
    return paths


def _side_fair(row: Mapping[str, str]) -> Decimal:
    p = _dec(row["candidate_probability"], "candidate_probability")
    side = row["side"]
    if side == "YES":
        return p
    if side == "NO":
        return Decimal("1") - p
    _error(f"unexpected side {side!r}")


def primary_trade_rows(rows: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if _dec(row["threshold_dollars"], "threshold") != PRIMARY_THRESHOLD:
            continue
        if _dec(row["stress_dollars"], "stress") != PRIMARY_STRESS:
            continue
        if row["action"] != "ENTER":
            continue
        if row.get("scenario_valid") != "true":
            _error("primary 3c base scenario contains invalid trade")
        price = _dec(row["scenario_purchase_price"], "scenario_purchase_price")
        fee = _dec(row["scenario_standard_entry_fee"], "scenario_entry_fee")
        pnl = _dec(row["scenario_realized_pnl"], "scenario_realized_pnl")
        payout = _dec(row["side_payout"], "side_payout")
        fair = _side_fair(row)
        edge = _dec(row["quoted_net_edge_per_contract"], "quoted_net_edge")
        out.append({
            **row,
            "_price": price,
            "_fee": fee,
            "_pnl": pnl,
            "_payout": payout,
            "_fair": fair,
            "_edge": edge,
            "_win": int(payout == Decimal("1")),
            "_gross": payout - price,
        })
    if len(out) != EXPECTED_PRIMARY_ENTRIES:
        _error(f"primary 3c entry count changed: {len(out)} != {EXPECTED_PRIMARY_ENTRIES}")
    out.sort(key=lambda r: (r["event_close_time_utc"], r["event_ticker"]))
    return out


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {
            "entry_count": 0, "win_count": 0, "win_rate": None,
            "mean_purchase_price": None, "mean_side_fair_probability": None,
            "calibration_gap_win_rate_minus_fair": None, "mean_quoted_net_edge": None,
            "mean_entry_fee": None, "gross_pnl_before_fee": "0",
            "total_fee": "0", "total_net_pnl": "0", "mean_net_pnl_per_trade": None,
            "mean_winning_trade": None, "mean_losing_trade": None, "worst_trade": None,
        }
    wins = sum(int(r["_win"]) for r in rows)
    win_rate = Decimal(wins) / Decimal(n)
    mean_fair = _mean([r["_fair"] for r in rows])
    pnls = [r["_pnl"] for r in rows]
    win_pnls = [r["_pnl"] for r in rows if r["_pnl"] > 0]
    loss_pnls = [r["_pnl"] for r in rows if r["_pnl"] < 0]
    return {
        "entry_count": n,
        "win_count": wins,
        "win_rate": float(win_rate),
        "mean_purchase_price": _fmt(_mean([r["_price"] for r in rows])),
        "mean_side_fair_probability": _fmt(mean_fair),
        "calibration_gap_win_rate_minus_fair": _fmt(win_rate - mean_fair),
        "mean_quoted_net_edge": _fmt(_mean([r["_edge"] for r in rows])),
        "mean_entry_fee": _fmt(_mean([r["_fee"] for r in rows])),
        "gross_pnl_before_fee": _fmt(sum((r["_gross"] for r in rows), Decimal("0"))),
        "total_fee": _fmt(sum((r["_fee"] for r in rows), Decimal("0"))),
        "total_net_pnl": _fmt(sum(pnls, Decimal("0"))),
        "mean_net_pnl_per_trade": _fmt(_mean(pnls)),
        "mean_winning_trade": _fmt(_mean(win_pnls)) if win_pnls else None,
        "mean_losing_trade": _fmt(_mean(loss_pnls)) if loss_pnls else None,
        "worst_trade": _fmt(min(pnls)),
    }


def _bucket(value: Decimal, specs: Sequence[Mapping[str, Any]]) -> str:
    for spec in specs:
        if _dec(spec["lower"], "bucket lower") <= value < _dec(spec["upper"], "bucket upper"):
            return str(spec["id"])
    _error(f"value {value} did not fit predeclared bucket set")


def build_slice_rows(trades: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> list[dict[str, Any]]:
    scope = config["analysis_scope"]
    groups: list[tuple[str, str, list[Mapping[str, Any]]]] = []
    for value in scope["comparison_stages"]:
        groups.append(("stage", value, [r for r in trades if r["stage"] == value]))
    for value in scope["comparison_blocks"]:
        groups.append(("block_id", value, [r for r in trades if r["block_id"] == value]))
    for field in scope["categorical_slices"]:
        values = sorted({r[field] for r in trades})
        for value in values:
            groups.append((field, value, [r for r in trades if r[field] == value]))
    bucket_defs = [
        ("purchase_price_bucket", scope["purchase_price_buckets"], "_price"),
        ("side_fair_probability_bucket", scope["side_fair_probability_buckets"], "_fair"),
        ("quoted_net_edge_bucket", scope["quoted_net_edge_buckets"], "_edge"),
    ]
    for dim, specs, key in bucket_defs:
        for spec in specs:
            value = spec["id"]
            rows = [r for r in trades if _bucket(r[key], specs) == value]
            groups.append((dim, value, rows))

    result = []
    for dim, value, rows in groups:
        result.append({"slice_dimension": dim, "slice_value": value, **metrics(rows)})
    return result


def _loss_concentration(rows: Sequence[Mapping[str, Any]], n_values: Sequence[int]) -> dict[str, Any]:
    losses = sorted((-r["_pnl"] for r in rows if r["_pnl"] < 0), reverse=True)
    total = sum(losses, Decimal("0"))
    result = {"losing_trade_count": len(losses), "total_negative_loss_magnitude": _fmt(total)}
    for n in n_values:
        share = (sum(losses[:n], Decimal("0")) / total) if total > 0 else Decimal("0")
        result[f"worst_{n}_share_of_negative_loss"] = float(share)
    return result


def build_tail_rows(trades: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    scopes = {
        "ALL_3C": list(trades),
        "H3_3C": [r for r in trades if r["stage"] == "H3"],
        "B4_3C": [r for r in trades if r["block_id"] == "B4"],
    }
    n = int(config["analysis_scope"]["tail_bottom_n"])
    n_values = list(config["analysis_scope"]["loss_concentration_n"])
    out: list[dict[str, Any]] = []
    concentration: dict[str, Any] = {}
    for scope, rows in scopes.items():
        ranked = sorted(rows, key=lambda r: (r["_pnl"], r["event_close_time_utc"], r["event_ticker"]))
        for rank, r in enumerate(ranked[:n], start=1):
            out.append({
                "scope": scope, "rank": rank, "event_ticker": r["event_ticker"],
                "stage": r["stage"], "block_id": r["block_id"], "market_ticker": r["market_ticker"],
                "structural_role": r["structural_role"], "ttc_target_minutes": r["ttc_target_minutes"],
                "side": r["side"], "candidate_probability": r["candidate_probability"],
                "side_fair_probability": _fmt(r["_fair"]),
                "quoted_purchase_price": _fmt(r["_price"]),
                "quoted_net_edge_per_contract": _fmt(r["_edge"]),
                "entry_fee": _fmt(r["_fee"]), "outcome": r["outcome"],
                "realized_pnl": _fmt(r["_pnl"]),
            })
        concentration[scope] = _loss_concentration(rows, n_values)
    return out, concentration


def build_regime_comparisons(trades: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    fields = {
        "entry_count": lambda m: Decimal(m["entry_count"]),
        "win_rate": lambda m: Decimal(str(m["win_rate"])) if m["win_rate"] is not None else None,
        "mean_purchase_price": lambda m: _dec(m["mean_purchase_price"], "mean_purchase_price"),
        "mean_side_fair_probability": lambda m: _dec(m["mean_side_fair_probability"], "mean_fair"),
        "calibration_gap_win_rate_minus_fair": lambda m: _dec(m["calibration_gap_win_rate_minus_fair"], "calibration_gap"),
        "mean_quoted_net_edge": lambda m: _dec(m["mean_quoted_net_edge"], "mean_edge"),
        "mean_entry_fee": lambda m: _dec(m["mean_entry_fee"], "mean_fee"),
        "gross_pnl_before_fee": lambda m: _dec(m["gross_pnl_before_fee"], "gross_pnl"),
        "total_fee": lambda m: _dec(m["total_fee"], "total_fee"),
        "total_net_pnl": lambda m: _dec(m["total_net_pnl"], "total_net_pnl"),
        "mean_net_pnl_per_trade": lambda m: _dec(m["mean_net_pnl_per_trade"], "mean_pnl"),
        "mean_losing_trade": lambda m: _dec(m["mean_losing_trade"], "mean_losing_trade") if m["mean_losing_trade"] is not None else None,
        "worst_trade": lambda m: _dec(m["worst_trade"], "worst_trade"),
    }
    for left, right in config["analysis_scope"]["fixed_regime_comparisons"]:
        dimension = "stage" if left.startswith("H") else "block_id"
        left_rows = [r for r in trades if r[dimension] == left]
        right_rows = [r for r in trades if r[dimension] == right]
        lm, rm = metrics(left_rows), metrics(right_rows)
        for name, convert in fields.items():
            lv, rv = convert(lm), convert(rm)
            diff = (rv - lv) if lv is not None and rv is not None else None
            result.append({
                "comparison": f"{left}_vs_{right}",
                "metric": name,
                "left_value": _fmt(lv) if isinstance(lv, Decimal) else "",
                "right_value": _fmt(rv) if isinstance(rv, Decimal) else "",
                "right_minus_left": _fmt(diff) if isinstance(diff, Decimal) else "",
            })
    return result


def build_analysis(
    scenario_rows: Sequence[Mapping[str, str]],
    config: Mapping[str, Any],
    source_sha256s: Mapping[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    trades = primary_trade_rows(scenario_rows)
    slices = build_slice_rows(trades, config)
    tails, concentration = build_tail_rows(trades, config)
    comparisons = build_regime_comparisons(trades, config)

    stage_metrics = {stage: metrics([r for r in trades if r["stage"] == stage])
                     for stage in config["analysis_scope"]["comparison_stages"]}
    block_metrics = {block: metrics([r for r in trades if r["block_id"] == block])
                     for block in config["analysis_scope"]["comparison_blocks"]}

    summary = {
        "schema_version": "kxbtcd_candidate_e_quoted_entry_hold_v1_failure_analysis_summary.v1",
        "analysis_id": EXPECTED_ANALYSIS_ID,
        "failure_analysis_predeclaration_fingerprint": EXPECTED_PREDECLARATION_FINGERPRINT,
        "development_evaluation_fingerprint": EXPECTED_EVALUATION_FINGERPRINT,
        "development_result_closeout_fingerprint": EXPECTED_RESULT_CLOSEOUT_FINGERPRINT,
        "primary_population": {
            "threshold_dollars": "0.03",
            "stress_dollars": "0",
            "entry_count": len(trades),
            "metrics": metrics(trades),
        },
        "stage_metrics": stage_metrics,
        "block_metrics": block_metrics,
        "loss_concentration": concentration,
        "source_sha256s": dict(sorted(source_sha256s.items())),
        "interpretation": {
            "descriptive_only": True,
            "successor_selected": False,
            "new_strategy_rule_selected": False,
            "new_threshold_selected": False,
        },
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
    summary["analysis_fingerprint"] = canonical_sha256(summary)
    return summary, slices, tails, comparisons
