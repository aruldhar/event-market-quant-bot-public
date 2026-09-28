#!/usr/bin/env python3
"""Stress the frozen H3 protected-50%-target rule under slower latency.

The primary H3 entry decision remains the previously selected first observation
with 240 < seconds remaining <= 300 and a favored midpoint from 90 cents
inclusive to 98 cents exclusive.  The strategy still uses a $100 maximum
budget, archived full depth, conservative taker fees, a protected target equal
to 50% of the filled trade's maximum net settlement profit, and a ten-second
preclose fallback.

Only observation-to-execution latency changes.  The diagnostic compares:

* combined: both entry and exit latency are 1, 2, 3, or 5 seconds;
* exit_only: entry remains at the frozen one second while exit latency is
  1, 2, 3, or 5 seconds.

Every setting is matched by trigger market.  The one-second result must exactly
reproduce the accepted target-protection scenarios.  The holdout stays sealed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import (
    EXPECTED_ELIGIBLE_MARKETS,
    LATENCY_SECONDS,
    MAX_BUDGET,
    SimulationError,
    Snapshot,
    best_ask,
    buy_with_budget,
    first_index_at_or_after,
    load_outcomes,
    load_snapshots,
    sell_quantity,
    validate_fee_inputs,
    write_csv,
)
from analyze_kxbtc15m_h3_exit_policies import (
    EXPECTED_PRIMARY_TRIGGERS,
    PRECLOSE_EXIT_SECONDS,
    ExitPolicyError,
    load_primary_triggers,
    percentage_target,
)
from analyze_kxbtc15m_h3_late_convergence import favored_quote
from analyze_kxbtc15m_h3_target_protection import parse_bool
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    parse_time,
    safe_extract_zip,
    select_development_manifests,
)


LATENCY_GRID_SECONDS = (1.0, 2.0, 3.0, 5.0)
STRESS_MODES = ("combined", "exit_only")
TARGET_FRACTION = Decimal("0.50")
BASELINE_POLICY = "protected_target_50pct_max_or_preclose"


class LatencyStressError(RuntimeError):
    """Raised when a latency-stress input or invariant is violated."""


def scenario_name(mode: str, latency_seconds: float) -> str:
    if mode not in STRESS_MODES:
        raise LatencyStressError(f"invalid stress mode: {mode}")
    if latency_seconds not in LATENCY_GRID_SECONDS:
        raise LatencyStressError(f"invalid latency: {latency_seconds}")
    return f"{mode}_{int(latency_seconds)}s"


def scenario_grid() -> tuple[tuple[str, float, float, float], ...]:
    rows: list[tuple[str, float, float, float]] = []
    for mode in STRESS_MODES:
        for latency in LATENCY_GRID_SECONDS:
            entry_latency = latency if mode == "combined" else LATENCY_SECONDS
            rows.append((scenario_name(mode, latency), mode, entry_latency, latency))
    return tuple(rows)


def load_prior_baseline(path: Path) -> dict[str, float]:
    required = {
        "ticker", "exit_policy", "pnl", "holdout_read", "external_btc_data_used",
    }
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = required - fields
        if missing:
            raise LatencyStressError(
                f"prior target-protection CSV missing fields: {sorted(missing)}"
            )
        all_rows = list(reader)
    if any(parse_bool(row["holdout_read"]) for row in all_rows):
        raise LatencyStressError("prior target-protection input reports a holdout read")
    if any(parse_bool(row["external_btc_data_used"]) for row in all_rows):
        raise LatencyStressError(
            "prior target-protection input reports external BTC data"
        )
    rows = [row for row in all_rows if row["exit_policy"] == BASELINE_POLICY]
    if len(rows) != EXPECTED_PRIMARY_TRIGGERS:
        raise LatencyStressError(
            f"expected {EXPECTED_PRIMARY_TRIGGERS} protected baseline rows; "
            f"found {len(rows)}"
        )
    baseline = {str(row["ticker"]): float(row["pnl"]) for row in rows}
    if len(baseline) != EXPECTED_PRIMARY_TRIGGERS:
        raise LatencyStressError("protected baseline tickers are not unique")
    return baseline


def find_protected_target_exit(
    *,
    snapshots: Sequence[Snapshot],
    start_index: int,
    stop_time: datetime,
    side: str,
    quantity: Decimal,
    outflow: Decimal,
    target: Decimal,
    latency_seconds: float,
) -> tuple[Any | None, datetime | None, datetime | None, int, int]:
    """Find the first delayed full sale that still meets the protected target."""

    if latency_seconds <= 0:
        raise LatencyStressError("exit latency must be positive")
    signal_count = 0
    rejected_count = 0
    index = start_index
    while index < len(snapshots):
        observed = snapshots[index]
        if observed.observed_at >= stop_time:
            break
        hypothetical = sell_quantity(observed.book.bid_levels(side), quantity)
        if hypothetical.quantity != quantity or hypothetical.sell_inflow - outflow < target:
            index += 1
            continue
        signal_count += 1
        delayed_index = first_index_at_or_after(
            snapshots,
            index + 1,
            observed.observed_at + timedelta(seconds=latency_seconds),
        )
        if delayed_index is None or snapshots[delayed_index].observed_at >= stop_time:
            rejected_count += 1
            break
        executed_at = snapshots[delayed_index].observed_at
        executed = sell_quantity(snapshots[delayed_index].book.bid_levels(side), quantity)
        if executed.quantity == quantity and executed.sell_inflow - outflow >= target:
            return executed, executed_at, observed.observed_at, signal_count, rejected_count
        rejected_count += 1
        index = delayed_index + 1
    return None, None, None, signal_count, rejected_count


def find_preclose_exit(
    *,
    snapshots: Sequence[Snapshot],
    start_index: int,
    start_time: datetime,
    close_time: datetime,
    side: str,
    quantity: Decimal,
    latency_seconds: float,
) -> tuple[Any | None, datetime | None, datetime | None]:
    """Attempt a delayed full-depth preclose sale using the stressed latency."""

    if latency_seconds <= 0:
        raise LatencyStressError("preclose latency must be positive")
    index = first_index_at_or_after(snapshots, start_index, start_time)
    while index is not None and index < len(snapshots):
        observed = snapshots[index]
        delayed_index = first_index_at_or_after(
            snapshots,
            index + 1,
            observed.observed_at + timedelta(seconds=latency_seconds),
        )
        if delayed_index is None or snapshots[delayed_index].observed_at >= close_time:
            break
        executed_at = snapshots[delayed_index].observed_at
        executed = sell_quantity(snapshots[delayed_index].book.bid_levels(side), quantity)
        if executed.quantity == quantity:
            return executed, executed_at, observed.observed_at
        index = delayed_index + 1
    return None, None, None


def _no_entry_row(
    *, trigger: Mapping[str, Any], scenario: str, mode: str,
    entry_latency: float, exit_latency: float, reason: str,
) -> dict[str, Any]:
    return {
        "ticker": trigger["ticker"],
        "diagnostic_segment": trigger["diagnostic_segment"],
        "scenario": scenario,
        "stress_mode": mode,
        "configured_entry_latency_seconds": entry_latency,
        "configured_exit_latency_seconds": exit_latency,
        "status": reason,
        "entry_filled": False,
        "pnl": 0.0,
        "profitable": False,
        "target_filled": False,
        "fallback_used": False,
        "full_capital_loss": False,
        "holdout_read": False,
        "external_btc_data_used": False,
    }


def simulate_latency_scenario(
    *,
    snapshots: Sequence[Snapshot],
    decision_index: int,
    close_time: datetime,
    winning_side: str,
    trigger: Mapping[str, Any],
    scenario: str,
    mode: str,
    entry_latency_seconds: float,
    exit_latency_seconds: float,
) -> dict[str, Any]:
    if entry_latency_seconds <= 0 or exit_latency_seconds <= 0:
        raise LatencyStressError("entry and exit latency must be positive")
    decision = snapshots[decision_index]
    quote = favored_quote(decision.book)
    if quote is None:
        raise LatencyStressError(f"{trigger['ticker']}: favored quote unavailable")
    side, midpoint, decision_ask = quote
    seconds_remaining = (close_time - decision.observed_at).total_seconds()
    if not (
        240 < seconds_remaining <= 300
        and Decimal("0.90") <= midpoint < Decimal("0.98")
    ):
        raise LatencyStressError(
            f"{trigger['ticker']}: frozen trigger no longer satisfies H3"
        )

    entry_index = first_index_at_or_after(
        snapshots,
        decision_index + 1,
        decision.observed_at + timedelta(seconds=entry_latency_seconds),
    )
    if entry_index is None or snapshots[entry_index].observed_at >= close_time:
        return _no_entry_row(
            trigger=trigger, scenario=scenario, mode=mode,
            entry_latency=entry_latency_seconds, exit_latency=exit_latency_seconds,
            reason="entry_missed_close",
        )
    entry_snapshot = snapshots[entry_index]
    entry_ask = best_ask(entry_snapshot.book, side)
    if entry_ask is None:
        return _no_entry_row(
            trigger=trigger, scenario=scenario, mode=mode,
            entry_latency=entry_latency_seconds, exit_latency=exit_latency_seconds,
            reason="entry_book_unavailable",
        )
    entry = buy_with_budget(entry_snapshot.book.ask_levels(side), MAX_BUDGET)
    if entry.quantity <= 0:
        return _no_entry_row(
            trigger=trigger, scenario=scenario, mode=mode,
            entry_latency=entry_latency_seconds, exit_latency=exit_latency_seconds,
            reason="entry_unfilled",
        )

    quantity = entry.quantity
    outflow = entry.buy_outflow
    maximum_profit = quantity - outflow
    if maximum_profit <= 0:
        raise LatencyStressError(f"{trigger['ticker']}: nonpositive maximum profit")
    target = percentage_target(maximum_profit, TARGET_FRACTION)
    settlement_gross = quantity if side == winning_side else Decimal("0")
    settlement_pnl = settlement_gross - outflow
    preclose_time = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
    execution, exit_time, signal_time, signals, rejected = find_protected_target_exit(
        snapshots=snapshots,
        start_index=entry_index + 1,
        stop_time=preclose_time,
        side=side,
        quantity=quantity,
        outflow=outflow,
        target=target,
        latency_seconds=exit_latency_seconds,
    )
    target_filled = execution is not None
    fallback_used = not target_filled
    fallback_liquidity_failure = False
    if target_filled:
        assert exit_time is not None and signal_time is not None
        exit_reason = "protected_profit_target"
        exit_gross = execution.gross
        exit_fee = execution.fee
        pnl = execution.sell_inflow - outflow
    else:
        execution, exit_time, signal_time = find_preclose_exit(
            snapshots=snapshots,
            start_index=entry_index + 1,
            start_time=preclose_time,
            close_time=close_time,
            side=side,
            quantity=quantity,
            latency_seconds=exit_latency_seconds,
        )
        if execution is None:
            fallback_liquidity_failure = True
            exit_reason = "settlement_after_preclose_liquidity_failure"
            exit_time = close_time
            signal_time = None
            exit_gross = settlement_gross
            exit_fee = Decimal("0")
            pnl = settlement_pnl
        else:
            assert exit_time is not None and signal_time is not None
            exit_reason = "preclose_time_exit"
            exit_gross = execution.gross
            exit_fee = execution.fee
            pnl = execution.sell_inflow - outflow

    return {
        "ticker": trigger["ticker"],
        "diagnostic_segment": trigger["diagnostic_segment"],
        "scenario": scenario,
        "stress_mode": mode,
        "configured_entry_latency_seconds": entry_latency_seconds,
        "configured_exit_latency_seconds": exit_latency_seconds,
        "status": "completed",
        "decision_time": decision.observed_at.isoformat(),
        "seconds_remaining": seconds_remaining,
        "side": side,
        "favored_side_won": side == winning_side,
        "decision_favored_midpoint": float(midpoint),
        "decision_favored_ask": float(decision_ask),
        "entry_filled": True,
        "entry_execution_time": entry_snapshot.observed_at.isoformat(),
        "entry_realized_delay_seconds": (
            entry_snapshot.observed_at - decision.observed_at
        ).total_seconds(),
        "entry_best_ask": float(entry_ask),
        "entry_average_price": float(entry.gross / quantity),
        "entry_price_change_from_decision_ask": float(entry.gross / quantity - decision_ask),
        "contracts": float(quantity),
        "cash_deployed": float(outflow),
        "budget_utilization": float(outflow / MAX_BUDGET),
        "entry_fee": float(entry.fee),
        "maximum_settlement_profit": float(maximum_profit),
        "target_fraction_of_maximum": float(TARGET_FRACTION),
        "target_amount": float(target),
        "target_signal_count": signals,
        "target_rejected_after_latency_count": rejected,
        "target_filled": target_filled,
        "fallback_used": fallback_used,
        "fallback_liquidity_failure": fallback_liquidity_failure,
        "exit_signal_time": "" if signal_time is None else signal_time.isoformat(),
        "exit_execution_time": exit_time.isoformat(),
        "exit_realized_delay_seconds": (
            "" if signal_time is None else (exit_time - signal_time).total_seconds()
        ),
        "exit_reason": exit_reason,
        "exit_gross": float(exit_gross),
        "exit_fee": float(exit_fee),
        "total_fees": float(entry.fee + exit_fee),
        "pnl": float(pnl),
        "profitable": pnl > 0,
        "full_capital_loss": pnl <= -Decimal("0.90") * outflow,
        "settlement_counterfactual_pnl": float(settlement_pnl),
        "holdout_read": False,
        "external_btc_data_used": False,
    }


def verify_one_second_reproduction(
    baseline: Mapping[str, float], rows: Sequence[Mapping[str, Any]]
) -> None:
    for mode in STRESS_MODES:
        selected = {
            str(row["ticker"]): float(row["pnl"])
            for row in rows
            if row["scenario"] == scenario_name(mode, 1.0)
        }
        if set(selected) != set(baseline):
            raise LatencyStressError(f"{mode}: one-second ticker set mismatch")
        mismatches = [
            ticker for ticker, expected in baseline.items()
            if abs(selected[ticker] - expected) > 1e-9
        ]
        if mismatches:
            ticker = mismatches[0]
            raise LatencyStressError(
                f"{mode}: one-second reproduction failed for {len(mismatches)} "
                f"market(s); first={ticker} expected={baseline[ticker]} "
                f"actual={selected[ticker]}"
            )


def _bootstrap(values: Sequence[float]) -> tuple[float, float, float]:
    if not values:
        return math.nan, math.nan, math.nan
    mean = statistics.mean(values)
    if len(values) < 2:
        return mean, math.nan, math.nan
    rng = random.Random(20260813)
    samples = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(2_000)]
    samples.sort()
    return mean, samples[49], samples[1949]


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def _mean_numeric(rows: Sequence[Mapping[str, Any]], field: str) -> float:
    values = [
        float(row[field]) for row in rows
        if str(row.get(field, "")).strip() not in {"", "nan"}
    ]
    return statistics.mean(values) if values else math.nan


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key = {
        (str(row["ticker"]), str(row["scenario"])): float(row["pnl"])
        for row in rows
    }
    output: list[dict[str, Any]] = []
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        source = list(rows) if segment == "all_96" else [
            row for row in rows
            if row["diagnostic_segment"] == (
                "earlier_64" if segment == "earlier_64_diagnostic" else "later_32"
            )
        ]
        for scenario, mode, entry_latency, exit_latency in scenario_grid():
            selected = [row for row in source if row["scenario"] == scenario]
            filled = [row for row in selected if bool(row["entry_filled"])]
            pnl = [float(row["pnl"]) for row in selected]
            mean, low, high = _bootstrap(pnl)
            baseline_scenario = scenario_name(mode, 1.0)
            paired = [
                float(row["pnl"]) - by_key[(str(row["ticker"]), baseline_scenario)]
                for row in selected
            ]
            output.append({
                "segment": segment,
                "scenario": scenario,
                "stress_mode": mode,
                "configured_entry_latency_seconds": entry_latency,
                "configured_exit_latency_seconds": exit_latency,
                "triggered_markets": len(selected),
                "entry_fill_rate": statistics.mean(
                    bool(row["entry_filled"]) for row in selected
                ) if selected else math.nan,
                "mean_pnl_per_trigger": mean,
                "bootstrap_ci_low": low,
                "bootstrap_ci_high": high,
                "mean_paired_difference_vs_mode_1s": statistics.mean(paired)
                if paired else math.nan,
                "positive_pnl_rate_per_trigger": statistics.mean(
                    float(row["pnl"]) > 0 for row in selected
                ) if selected else math.nan,
                "protected_target_fill_rate": statistics.mean(
                    bool(row["target_filled"]) for row in filled
                ) if filled else math.nan,
                "preclose_fallback_rate": statistics.mean(
                    bool(row["fallback_used"]) for row in filled
                ) if filled else math.nan,
                "fallback_liquidity_failure_rate": statistics.mean(
                    bool(row["fallback_liquidity_failure"]) for row in filled
                ) if filled else math.nan,
                "full_capital_loss_rate": statistics.mean(
                    bool(row["full_capital_loss"]) for row in filled
                ) if filled else math.nan,
                "mean_rejected_target_signals": _mean_numeric(
                    filled, "target_rejected_after_latency_count"
                ),
                "mean_realized_entry_delay_seconds": _mean_numeric(
                    filled, "entry_realized_delay_seconds"
                ),
                "mean_realized_exit_delay_seconds": _mean_numeric(
                    filled, "exit_realized_delay_seconds"
                ),
                "mean_entry_price_change_from_decision_ask": _mean_numeric(
                    filled, "entry_price_change_from_decision_ask"
                ),
                "pnl_05_quantile": _quantile(pnl, 0.05),
                "worst_pnl": min(pnl) if pnl else math.nan,
                "holdout_read": False,
                "external_btc_data_used": False,
            })
    return output


def _money(value: float) -> str:
    return "n/a" if math.isnan(value) else f"${value:.2f}"


def _percent(value: float) -> str:
    return "n/a" if math.isnan(value) else f"{value:.1%}"


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    all_rows = [row for row in summary if row["segment"] == "all_96"]
    lines = [
        "# KXBTC15M H3 latency stress diagnostic",
        "",
        "**Matched development execution stress; rule frozen; holdout sealed.**",
        "",
        "The same 52 H3 first-trigger decisions use a $100 maximum budget, archived full "
        "depth, conservative fees, a protected target equal to 50% of maximum net "
        "settlement profit, and a ten-second preclose fallback. Combined stress slows both "
        "entry and exit. Exit-only stress keeps entry at one second and slows only exit. "
        "Every retry and the preclose fallback receive the configured exit delay.",
        "",
        "The one-second rows exactly reproduce the accepted protected-target baseline.",
        "",
        "| Stress | Entry / exit delay | Filled | Mean P&L | vs mode 1s | Bootstrap 95% CI | Positive | Target filled | Fallback | Full loss | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in all_rows:
        lines.append(
            f"| {row['stress_mode']} | "
            f"{float(row['configured_entry_latency_seconds']):g}s / "
            f"{float(row['configured_exit_latency_seconds']):g}s | "
            f"{_percent(float(row['entry_fill_rate']))} | "
            f"{_money(float(row['mean_pnl_per_trigger']))} | "
            f"{_money(float(row['mean_paired_difference_vs_mode_1s']))} | "
            f"{_money(float(row['bootstrap_ci_low']))} to "
            f"{_money(float(row['bootstrap_ci_high']))} | "
            f"{_percent(float(row['positive_pnl_rate_per_trigger']))} | "
            f"{_percent(float(row['protected_target_fill_rate']))} | "
            f"{_percent(float(row['preclose_fallback_rate']))} | "
            f"{_percent(float(row['full_capital_loss_rate']))} | "
            f"{_money(float(row['pnl_05_quantile']))} | "
            f"{_money(float(row['worst_pnl']))} |"
        )
    lines.extend([
        "",
        "## Chronological stability",
        "",
        "| Stress | Entry / exit delay | Earlier mean | Later mean |",
        "|---|---:|---:|---:|",
    ])
    for scenario, mode, entry_latency, exit_latency in scenario_grid():
        earlier = next(
            row for row in summary
            if row["segment"] == "earlier_64_diagnostic" and row["scenario"] == scenario
        )
        later = next(
            row for row in summary
            if row["segment"] == "later_32_diagnostic" and row["scenario"] == scenario
        )
        lines.append(
            f"| {mode} | {entry_latency:g}s / {exit_latency:g}s | "
            f"{_money(float(earlier['mean_pnl_per_trigger']))} | "
            f"{_money(float(later['mean_pnl_per_trigger']))} |"
        )
    lines.extend([
        "",
        "Configured latency is a minimum wait: execution uses the first archived snapshot "
        "at or after that time, so realized latency can be slightly longer. This diagnostic "
        "does not model within-snapshot queue changes, network outages, or order rejection. "
        "It uses no external BTC data and does not open the holdout.",
    ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_zip", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--triggers-csv", type=Path, required=True)
    parser.add_argument("--prior-protection-scenarios-csv", type=Path, required=True)
    parser.add_argument("--outcomes-csv", type=Path, required=True)
    parser.add_argument("--series-csv", type=Path, required=True)
    parser.add_argument("--fee-changes-csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("analysis/kxbtc15m_h3_latency_stress"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    triggers = load_primary_triggers(args.triggers_csv)
    baseline = load_prior_baseline(args.prior_protection_scenarios_csv)
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    trigger_by_ticker = {row["ticker"]: row for row in triggers}
    if set(baseline) != set(trigger_by_ticker):
        raise LatencyStressError("baseline and primary-trigger ticker sets differ")
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_h3_latency_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise SimulationError(
                f"expected {EXPECTED_ELIGIBLE_MARKETS} eligible markets; found {len(eligible)}"
            )
        if set(outcomes) != {market.ticker for market in eligible}:
            raise SimulationError("outcome ticker set does not equal development set")
        triggered = [market for market in eligible if market.ticker in trigger_by_ticker]
        if len(triggered) != EXPECTED_PRIMARY_TRIGGERS:
            raise LatencyStressError("eligible trigger-market set mismatch")

        for number, market in enumerate(triggered, start=1):
            trigger = trigger_by_ticker[market.ticker]
            snapshots = load_snapshots(market, args.repo_root)
            decision_time = parse_time(trigger["decision_time"])
            decision_index = first_index_at_or_after(snapshots, 0, decision_time)
            if decision_index is None or snapshots[decision_index].observed_at != decision_time:
                raise LatencyStressError(f"{market.ticker}: exact trigger not found")
            for scenario, mode, entry_latency, exit_latency in scenario_grid():
                rows.append(simulate_latency_scenario(
                    snapshots=snapshots,
                    decision_index=decision_index,
                    close_time=market_close_utc(market.ticker),
                    winning_side=outcomes[market.ticker],
                    trigger=trigger,
                    scenario=scenario,
                    mode=mode,
                    entry_latency_seconds=entry_latency,
                    exit_latency_seconds=exit_latency,
                ))
            print(f"[{number:02d}/{EXPECTED_PRIMARY_TRIGGERS}] {market.ticker}")

    expected_rows = EXPECTED_PRIMARY_TRIGGERS * len(scenario_grid())
    if len(rows) != expected_rows:
        raise LatencyStressError(f"expected {expected_rows} scenarios; found {len(rows)}")
    verify_one_second_reproduction(baseline, rows)
    summary = summarize(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_h3_latency_stress_scenarios.csv", rows)
    write_csv(args.output_dir / "kxbtc15m_h3_latency_stress_summary.csv", summary)
    report_path = args.output_dir / "KXBTC15M_H3_LATENCY_STRESS.md"
    report_path.write_text(markdown_report(summary), encoding="utf-8")

    print("KXBTC15M H3 latency stress diagnostic: PASS")
    print(f"Frozen primary triggers: {EXPECTED_PRIMARY_TRIGGERS}")
    print(f"Matched scenario rows: {len(rows)}")
    print("Latencies: 1, 2, 3, 5 seconds")
    print("Stress modes: combined entry/exit; exit-only")
    print("Exit: protected 50%-of-maximum target; 10-second preclose fallback")
    print("One-second prior reproduction: PASS")
    print("External BTC data used: no")
    print("Holdout read: False")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (
        AuditError, ExitPolicyError, LatencyStressError, OSError,
        SimulationError, ValueError, json.JSONDecodeError,
    ) as exc:
        raise SystemExit(f"H3 latency stress error: {exc}") from exc
