"""Checkpoint 21N-Y-E2: July-10 settlement sensitivity evaluator.

This module implements only the E1-predeclared post-outcome sensitivity analyses.
It reuses the already-validated D2 partition-aware settlement transport helpers.

Important interpretation:
- the official July-10 result remains immutable: 27 EXACT / 33 CENSORED,
  15/15 official policy settings INCONCLUSIVE;
- the 27 EXACT scenarios retain their official P&L unchanged;
- only the 3 liquidation-only censored scenarios may become coherent point
  counterfactuals by terminalizing known residual quantity at settlement;
- selection/rearm-censored traces are descriptive only, not complete policy P&L;
- observed filled entries may be scored independently to settlement, but those
  entry rows must not be summed as a causal hold-all trading strategy;
- no policy ranking/selection, retuning, strategy rerun, or order placement.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from . import kxbtcd_candidate_e_v2_july10_settlement_evaluator as base
from . import kxbtcd_candidate_e_v2_july10_settlement_sensitivity_predeclaration as e1

SENSITIVITY_CACHE_DIR = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_v2_sensitivity_settlement_cache"
)
SENSITIVITY_SETTLEMENT_MANIFEST_PATH = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_v2_sensitivity_settlements.json"
)
SENSITIVITY_REPORT_PATH = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_v2_settlement_sensitivity.json"
)

EXPECTED_IMPLEMENTATION_CHECKPOINT_MESSAGE = (
    "Checkpoint 21N-Y-E2 - July10 Settlement Sensitivity Evaluator"
)
REQUIRED_CLOSEOUT_PATHS = (
    "src/kxbtcd_candidate_e_v2_july10_settlement_sensitivity_evaluator.py",
    "collect_kxbtcd_candidate_e_v2_july10_settlement_sensitivity.py",
    "validate_kxbtcd_candidate_e_v2_july10_settlement_sensitivity_readiness.py",
    "tests/test_kxbtcd_candidate_e_v2_july10_settlement_sensitivity_evaluator.py",
    "docs/PROJECT_STATE.md",
    "docs/AI_HANDOFF.md",
    "docs/DECISIONS.md",
    "docs/EXPERIMENT_LOG.md",
    "docs/BACKLOG.md",
)

class SensitivityEvaluationError(RuntimeError):
    pass

def require(condition: bool, message: str) -> None:
    if not condition:
        raise SensitivityEvaluationError(message)

def d(value: Any, name: str) -> Decimal:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise SensitivityEvaluationError(f"{name} must be decimal-compatible") from exc
    require(out.is_finite(), f"{name} must be finite")
    return out

def decimal_text(value: Any) -> str:
    text = format(d(value, "decimal"), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"

def scenario_key(row: Mapping[str, Any]) -> tuple[str, str, int]:
    threshold = row.get("threshold_dollars", row.get("threshold"))
    return (
        str(row["event_ticker"]),
        decimal_text(threshold),
        int(row["latency_ms"]),
    )

def policy_key(row: Mapping[str, Any]) -> tuple[str, int]:
    threshold = row.get("threshold_dollars", row.get("threshold"))
    return (decimal_text(threshold), int(row["latency_ms"]))

def censorship_subclass(row: Mapping[str, Any]) -> str:
    path_class = str(row["path_observation_class"])
    selection = bool(row["selection_or_rearm_censored"])
    liquidation = bool(row["explicit_liquidation_censored"])
    if path_class == "EXACT":
        require(not selection and not liquidation, "EXACT row has censorship flag")
        return "EXACT"
    require(path_class == "CENSORED", f"unknown path class {path_class!r}")
    if selection and liquidation:
        return "CENSORED_BOTH"
    if selection:
        return "CENSORED_SELECTION_REARM_ONLY"
    if liquidation:
        return "CENSORED_LIQUIDATION_ONLY"
    raise SensitivityEvaluationError("CENSORED row has no censorship reason")

def git_text(repo: Path, *args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    require(cp.returncode == 0, f"git {' '.join(args)} failed: {(cp.stderr or cp.stdout).strip()}")
    return cp.stdout.strip()

def require_collection_closeout_gate(repo: Path) -> dict[str, Any]:
    receipt_path = repo / "docs/LAST_CHECKPOINT_CLOSEOUT.json"
    require(receipt_path.is_file(), "missing closeout receipt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    require(
        receipt.get("checkpoint_message") == EXPECTED_IMPLEMENTATION_CHECKPOINT_MESSAGE,
        "E2 implementation has not been safely closed/pushed",
    )
    require(
        set(receipt.get("committed_paths", [])) == set(REQUIRED_CLOSEOUT_PATHS),
        "E2 closeout path set mismatch",
    )
    checkpoint = str(receipt.get("checkpoint_commit", ""))
    require(checkpoint, "E2 receipt missing checkpoint commit")
    require(
        git_text(repo, "show", "-s", "--format=%s", checkpoint)
        == EXPECTED_IMPLEMENTATION_CHECKPOINT_MESSAGE,
        "E2 checkpoint message mismatch",
    )
    require(git_text(repo, "branch", "--show-current") == "main", "collection requires main")
    head = git_text(repo, "rev-parse", "HEAD")
    origin = git_text(repo, "rev-parse", "origin/main")
    require(head == origin, "HEAD and origin/main differ")
    require(git_text(repo, "status", "--porcelain") == "", "worktree must be clean")
    return receipt

def load_frozen_e1(repo: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    predecl = e1.validate_predeclaration(repo)
    observed = e1.load_json(repo / e1.OBSERVED_MANIFEST_PATH)
    e1.validate_observed_manifest(
        observed,
        expected_sha=predecl["observed_entry_manifest"]["sha256"],
    )
    contract = base.load_json(repo / base.CONTRACT_PATH)
    return predecl, observed, contract

def sensitivity_cache_path(repo: Path, ticker: str) -> Path:
    base.market_filter_params(ticker)
    return repo / SENSITIVITY_CACHE_DIR / f"{ticker}.json"

def load_one_cached_record(repo: Path, ticker: str) -> tuple[dict[str, Any] | None, str | None]:
    path = sensitivity_cache_path(repo, ticker)
    if path.is_file():
        record = base.validate_cached_settlement_record(base.load_json(path), ticker)
        return record, "sensitivity_cache"

    official_path = base.settlement_cache_path(repo, ticker)
    if official_path.is_file():
        record = base.validate_cached_settlement_record(base.load_json(official_path), ticker)
        return record, "reused_official_exact_cache"
    return None, None

def load_cached_settlements(
    repo: Path,
    tickers: Sequence[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    records: dict[str, dict[str, Any]] = {}
    origins: dict[str, str] = {}
    for ticker in tickers:
        record, origin = load_one_cached_record(repo, ticker)
        if record is None:
            continue
        records[ticker] = record
        assert origin is not None
        origins[ticker] = origin
    return records, origins

def settlement_yes_value(record: Mapping[str, Any]) -> Decimal:
    market = record["market"]
    value = d(market["settlement_value_dollars"], "settlement YES value")
    require(value in {Decimal("0"), Decimal("1")}, "settlement must be binary")
    return value

def settlement_cash(
    *,
    record: Mapping[str, Any],
    side: str,
    quantity: Any,
) -> Decimal:
    q = d(quantity, "settlement quantity")
    require(q >= 0, "settlement quantity cannot be negative")
    yes = settlement_yes_value(record)
    side_u = str(side).upper()
    require(side_u in {"YES", "NO"}, "side must be YES or NO")
    unit = yes if side_u == "YES" else Decimal("1") - yes
    return q * unit

def build_settlement_manifest(
    *,
    predecl: Mapping[str, Any],
    records: Mapping[str, Mapping[str, Any]],
    origins: Mapping[str, str],
    raw_files_current_run: Sequence[Mapping[str, str]],
    network_requests_current_run: int,
) -> dict[str, Any]:
    tickers = tuple(predecl["future_settlement_access"]["exact_ticker_universe"])
    require(set(records) == set(tickers), "sensitivity settlement set incomplete")
    require(set(origins) == set(tickers), "sensitivity settlement origin set incomplete")
    tier_counts = Counter()
    origin_counts = Counter()
    rows = []
    for ticker in tickers:
        record = base.validate_cached_settlement_record(records[ticker], ticker)
        tier_counts[str(record["source_tier"])] += 1
        origin_counts[str(origins[ticker])] += 1
        rows.append(
            {
                "ticker": ticker,
                "cache_origin": origins[ticker],
                "record": record,
            }
        )
    return {
        "schema_version": "candidate_e_v2_july10_sensitivity_settlements.v1",
        "analysis_role": "post_outcome_exploratory_sensitivity_only",
        "e1_predeclaration_sha256": base.sha256_file(e1.PREDECLARATION_PATH),
        "observed_entry_manifest_sha256": predecl["observed_entry_manifest"]["sha256"],
        "official_settlement_manifest_sha256": predecl["official_result_binding"][
            "settlement_manifest_sha256"
        ],
        "ticker_count": len(tickers),
        "tickers": list(tickers),
        "source_tier_counts": dict(sorted(tier_counts.items())),
        "cache_origin_counts": dict(sorted(origin_counts.items())),
        "network_requests_current_run": int(network_requests_current_run),
        "raw_files_current_run": list(raw_files_current_run),
        "settlements": rows,
        "safety": {
            "policy_ranking_or_selection_performed": False,
            "strategy_rerun": False,
            "orders_placed": 0,
        },
    }

def _classification_map(contract: Mapping[str, Any]) -> dict[tuple[str, str, int], dict[str, Any]]:
    out = {}
    for row in contract["scenario_classification"]:
        key = scenario_key(row)
        require(key not in out, f"duplicate scenario classification {key}")
        out[key] = dict(row)
    require(len(out) == 60, "expected 60 scenario classifications")
    return out

def _official_exact_pnl_map(official: Mapping[str, Any]) -> dict[tuple[str, str, int], Decimal]:
    out = {}
    rows = official.get("scenario_results")
    require(isinstance(rows, list) and len(rows) == 60, "official report scenario grid changed")
    for row in rows:
        key = scenario_key(row)
        if row["path_observation_class"] != "EXACT":
            continue
        point = row.get("point_pnl_dollars")
        require(point is not None, f"EXACT official row missing point P&L {key}")
        out[key] = d(point, "official point P&L")
    require(len(out) == 27, "expected 27 official exact point P&Ls")
    return out

def _official_policy_class_map(official: Mapping[str, Any]) -> dict[tuple[str, int], str]:
    out = {}
    rows = official.get("policy_settings")
    require(isinstance(rows, list) and len(rows) == 15, "official policy grid changed")
    for row in rows:
        key = policy_key(row)
        require(key not in out, f"duplicate official policy row {key}")
        out[key] = str(row["robustness_classification"])
    require(Counter(out.values()) == Counter({"INCONCLUSIVE": 15}), "official result is no longer 15 INCONCLUSIVE")
    return out

def _observed_trades_by_scenario(
    observed: Mapping[str, Any],
) -> dict[tuple[str, str, int], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for trade in observed["observed_filled_trades"]:
        grouped[scenario_key(trade)].append(dict(trade))
    for rows in grouped.values():
        rows.sort(key=lambda r: (int(r["trade_number"]), int(r["arrival_timestamp_ms"]), r["market_ticker"]))
    return grouped

def observed_trace_terminal_value(
    *,
    trades: Sequence[Mapping[str, Any]],
    settlement_records: Mapping[str, Mapping[str, Any]],
) -> Decimal:
    total = Decimal("0")
    for trade in trades:
        ticker = str(trade["market_ticker"])
        require(ticker in settlement_records, f"missing settlement for {ticker}")
        total += d(trade["entry_net_cash_change_total"], "entry cash")
        exit_cash = trade.get("known_exit_net_cash_change_total")
        if exit_cash is not None:
            total += d(exit_cash, "known exit cash")
        residual = d(trade["known_residual_settlement_quantity"], "known residual")
        total += settlement_cash(
            record=settlement_records[ticker],
            side=str(trade["side"]),
            quantity=residual,
        )
    return total

def entry_settlement_diagnostic(
    trade: Mapping[str, Any],
    settlement_records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    ticker = str(trade["market_ticker"])
    require(ticker in settlement_records, f"missing settlement for {ticker}")
    record = settlement_records[ticker]
    quantity = d(trade["entry_filled_quantity"], "entry filled quantity")
    terminal = settlement_cash(record=record, side=str(trade["side"]), quantity=quantity)
    pnl = d(trade["entry_net_cash_change_total"], "entry cash") + terminal
    market = record["market"]
    return {
        "event_ticker": trade["event_ticker"],
        "threshold_dollars": trade["threshold_dollars"],
        "latency_ms": int(trade["latency_ms"]),
        "censorship_subclass": trade["censorship_subclass"],
        "trade_number": int(trade["trade_number"]),
        "market_ticker": ticker,
        "side": trade["side"],
        "entry_filled_quantity": trade["entry_filled_quantity"],
        "entry_net_cash_change_total": trade["entry_net_cash_change_total"],
        "settlement_result": market["result"],
        "settlement_yes_value_dollars": market["settlement_value_dollars"],
        "terminal_cash_dollars": decimal_text(terminal),
        "side_settled_in_the_money": terminal > 0,
        "independent_hold_to_settlement_pnl_dollars": decimal_text(pnl),
        "pnl_sign": "POSITIVE" if pnl > 0 else "NEGATIVE" if pnl < 0 else "ZERO",
    }

def build_sensitivity_report(
    *,
    repo: Path,
    predecl: Mapping[str, Any],
    observed: Mapping[str, Any],
    contract: Mapping[str, Any],
    settlement_records: Mapping[str, Mapping[str, Any]],
    settlement_manifest_sha256: str,
) -> dict[str, Any]:
    official_path = repo / e1.OFFICIAL_PNL_REPORT_PATH
    require(
        base.sha256_file(official_path)
        == predecl["official_result_binding"]["pnl_report_sha256"],
        "official P&L report SHA changed",
    )
    official = base.load_json(official_path)
    exact_pnl = _official_exact_pnl_map(official)
    official_policy_class = _official_policy_class_map(official)
    classes = _classification_map(contract)
    trades_by_scenario = _observed_trades_by_scenario(observed)

    required_tickers = set(predecl["future_settlement_access"]["exact_ticker_universe"])
    require(set(settlement_records) == required_tickers, "settlement record universe mismatch")

    lower_universal = d(
        contract["censored_path_accounting"]["pnl_lower_bound_dollars"],
        "universal lower bound",
    )
    upper_universal = d(
        contract["censored_path_accounting"]["pnl_upper_bound_dollars"],
        "universal upper bound",
    )

    scenario_rows = []
    component_bounds: dict[tuple[str, str, int], tuple[Decimal, Decimal]] = {}
    observed_trace_signs = Counter()

    for key in sorted(
        classes,
        key=lambda x: (Decimal(x[1]), x[2], x[0]),
    ):
        cls = classes[key]
        subclass = censorship_subclass(cls)
        trades = trades_by_scenario.get(key, [])
        row: dict[str, Any] = {
            "event_ticker": key[0],
            "threshold_dollars": key[1],
            "latency_ms": key[2],
            "path_observation_class": cls["path_observation_class"],
            "censorship_subclass": subclass,
            "observed_filled_trade_count": len(trades),
        }

        if subclass == "EXACT":
            require(key in exact_pnl, f"missing official exact P&L {key}")
            point = exact_pnl[key]
            component_bounds[key] = (point, point)
            row.update(
                {
                    "hybrid_component_type": "OFFICIAL_EXACT_PNL_UNCHANGED",
                    "hybrid_point_pnl_dollars": decimal_text(point),
                    "hybrid_interval_dollars": [decimal_text(point), decimal_text(point)],
                    "observed_trace_terminal_value_dollars": None,
                    "strategy_level_complete_under_sensitivity": True,
                }
            )
        else:
            trace = observed_trace_terminal_value(
                trades=trades,
                settlement_records=settlement_records,
            )
            trace_sign = "POSITIVE" if trace > 0 else "NEGATIVE" if trace < 0 else "ZERO"
            observed_trace_signs[trace_sign] += 1
            row["observed_trace_terminal_value_dollars"] = decimal_text(trace)
            row["observed_trace_value_sign"] = trace_sign

            if subclass == "CENSORED_LIQUIDATION_ONLY":
                component_bounds[key] = (trace, trace)
                row.update(
                    {
                        "hybrid_component_type": "LIQUIDATION_ONLY_SETTLEMENT_TERMINALIZED",
                        "hybrid_point_pnl_dollars": decimal_text(trace),
                        "hybrid_interval_dollars": [decimal_text(trace), decimal_text(trace)],
                        "strategy_level_complete_under_sensitivity": True,
                    }
                )
            else:
                component_bounds[key] = (lower_universal, upper_universal)
                row.update(
                    {
                        "hybrid_component_type": "SELECTION_REARM_CENSORSHIP_RETAINS_UNIVERSAL_INTERVAL",
                        "hybrid_point_pnl_dollars": None,
                        "hybrid_interval_dollars": [
                            decimal_text(lower_universal),
                            decimal_text(upper_universal),
                        ],
                        "strategy_level_complete_under_sensitivity": False,
                    }
                )
        scenario_rows.append(row)

    require(len(scenario_rows) == 60, "sensitivity scenario grid is not 60")

    events = tuple(contract["frozen_evidence"]["events"])
    policy_rows = []
    zero_relations = Counter()
    for threshold in ("0", "0.01", "0.02", "0.03", "0.05"):
        for latency in (0, 500, 1000):
            keys = [(event, threshold, latency) for event in events]
            require(all(key in component_bounds for key in keys), "policy/event component missing")
            low = sum((component_bounds[key][0] for key in keys), Decimal("0"))
            high = sum((component_bounds[key][1] for key in keys), Decimal("0"))
            mean_low = low / Decimal(len(events))
            mean_high = high / Decimal(len(events))
            relation = (
                "STRICTLY_POSITIVE"
                if low > 0
                else "STRICTLY_NEGATIVE"
                if high < 0
                else "CROSSES_OR_TOUCHES_ZERO"
            )
            zero_relations[relation] += 1
            subclasses = Counter(censorship_subclass(classes[key]) for key in keys)
            policy_rows.append(
                {
                    "threshold_dollars": threshold,
                    "latency_ms": latency,
                    "official_robustness_classification": official_policy_class[(threshold, latency)],
                    "official_result_unchanged": True,
                    "exact_official_point_count": subclasses["EXACT"],
                    "liquidation_only_terminalized_point_count": subclasses[
                        "CENSORED_LIQUIDATION_ONLY"
                    ],
                    "selection_or_rearm_incomplete_count": (
                        subclasses["CENSORED_SELECTION_REARM_ONLY"]
                        + subclasses["CENSORED_BOTH"]
                    ),
                    "hybrid_four_event_sum_interval_dollars": [
                        decimal_text(low),
                        decimal_text(high),
                    ],
                    "hybrid_event_equal_mean_interval_dollars": [
                        decimal_text(mean_low),
                        decimal_text(mean_high),
                    ],
                    "hybrid_interval_zero_relation": relation,
                    "hybrid_is_official_gate": False,
                }
            )

    entry_rows = [
        entry_settlement_diagnostic(trade, settlement_records)
        for trade in observed["observed_filled_trades"]
    ]
    require(len(entry_rows) == 93, "entry diagnostic count changed")
    entry_signs = Counter(row["pnl_sign"] for row in entry_rows)
    itm = sum(1 for row in entry_rows if row["side_settled_in_the_money"])

    subclass_entry_summary: dict[str, dict[str, int]] = {}
    for subclass in (
        "EXACT",
        "CENSORED_SELECTION_REARM_ONLY",
        "CENSORED_LIQUIDATION_ONLY",
        "CENSORED_BOTH",
    ):
        rows = [row for row in entry_rows if row["censorship_subclass"] == subclass]
        subclass_entry_summary[subclass] = {
            "entry_count": len(rows),
            "settled_in_the_money_count": sum(
                1 for row in rows if row["side_settled_in_the_money"]
            ),
            "positive_hold_pnl_count": sum(1 for row in rows if row["pnl_sign"] == "POSITIVE"),
            "negative_hold_pnl_count": sum(1 for row in rows if row["pnl_sign"] == "NEGATIVE"),
            "zero_hold_pnl_count": sum(1 for row in rows if row["pnl_sign"] == "ZERO"),
        }

    return {
        "schema_version": "candidate_e_v2_july10_settlement_sensitivity_report.v1",
        "analysis_role": "post_outcome_exploratory_sensitivity_only",
        "bindings": {
            "e1_predeclaration_sha256": base.sha256_file(repo / e1.PREDECLARATION_PATH),
            "observed_entry_manifest_sha256": predecl["observed_entry_manifest"]["sha256"],
            "official_settlement_manifest_sha256": predecl["official_result_binding"][
                "settlement_manifest_sha256"
            ],
            "official_pnl_report_sha256": predecl["official_result_binding"]["pnl_report_sha256"],
            "sensitivity_settlement_manifest_sha256": settlement_manifest_sha256,
        },
        "official_result": {
            "exact_scenarios": 27,
            "censored_scenarios": 33,
            "robustness_classification_counts": {"INCONCLUSIVE": 15},
            "immutable_and_unchanged": True,
        },
        "hybrid_analysis": {
            "exact_official_pnl_preserved_count": 27,
            "liquidation_only_terminalized_count": 3,
            "selection_or_rearm_incomplete_count": 30,
            "policy_interval_zero_relation_counts": dict(sorted(zero_relations.items())),
            "official_gate": False,
            "policy_selection_or_ranking_performed": False,
        },
        "observed_trace_analysis": {
            "censored_scenario_count": 33,
            "trace_value_sign_counts": dict(sorted(observed_trace_signs.items())),
            "selection_or_rearm_trace_is_complete_strategy_pnl": False,
        },
        "independent_entry_diagnostic_summary": {
            "entry_count": len(entry_rows),
            "settled_in_the_money_count": itm,
            "settled_out_of_the_money_count": len(entry_rows) - itm,
            "hold_pnl_sign_counts": dict(sorted(entry_signs.items())),
            "rows_are_not_independent": True,
            "sum_as_causal_hold_all_strategy_forbidden": True,
            "by_censorship_subclass": subclass_entry_summary,
        },
        "policy_setting_sensitivity": policy_rows,
        "scenario_sensitivity": scenario_rows,
        "independent_entry_settlement_diagnostics": entry_rows,
        "interpretation": {
            "cannot_override_official_inconclusive_result": True,
            "policy_ranking_or_selection_forbidden": True,
            "retuning_forbidden": True,
            "july10_role": "development_mechanics_evidence_only",
        },
        "safety": {
            "strategy_rerun": False,
            "orders_placed": 0,
            "production_execution_authorized": False,
        },
    }
