#!/usr/bin/env python3
"""Evaluate bounded partial time exits for the opened H3 evidence.

The diagnostic compares 25%, 50%, 75%, and 100% whole-contract cash exits at
75, 90, and 105 seconds remaining.  Partial policies continue monitoring the
remaining position, but the original whole-trade target is preserved through
cumulative net-proceeds accounting.  All 122 markets are adaptive development
evidence; no result is a new holdout or authorization to trade.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import (
    LATENCY_SECONDS,
    Snapshot,
    first_index_at_or_after,
    load_outcomes,
    sell_quantity,
    validate_fee_inputs,
    write_csv,
)
from analyze_kxbtc15m_h3_exit_policies import PRECLOSE_EXIT_SECONDS, _find_preclose_exit
from analyze_kxbtc15m_h3_frequency import (
    TARGET_FRACTION,
    _decimal_text,
    _raw_snapshot_sets,
    simulate_market as simulate_frequency_market,
)
from analyze_kxbtc15m_h3_native_exit_policies import (
    BASELINE_POLICY,
    EXPECTED_NATIVE_ENTRIES,
    find_native_entry,
    simulate_policy,
    verify_baseline_reproduction,
)
from analyze_kxbtc15m_h3_stop_candidates import (
    EXPECTED_HOLDOUT_ENTRIES,
    EXPECTED_HOLDOUT_TOTAL_PNL,
    EXPECTED_TOTAL_ENTRIES,
    EXPECTED_TOTAL_MARKETS,
    FULL_LOSS_FRACTION,
    _market_partition,
    load_opened_baseline,
    load_opened_holdout_outcomes,
    select_opened_manifests,
    verify_opened_baseline_row,
)
from analyze_kxbtc15m_h3_time_windows import _bootstrap, _mean, _money, _quantile
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    safe_extract_zip,
    select_development_manifests,
)


TIMEOUT_SECONDS = (75, 90, 105)
CASHOUT_FRACTIONS = (
    Decimal("0.25"), Decimal("0.50"), Decimal("0.75"), Decimal("1.00")
)
BASELINE_KEY = "baseline_10s"
FULL_90_KEY = "timeout90_fraction100"
EXPECTED_FULL_90_TOTAL_PNL = 167.18


class PartialTimeExitError(RuntimeError):
    """Raised when a partial-time diagnostic invariant fails closed."""


@dataclass(frozen=True)
class PartialTimePolicy:
    key: str
    label: str
    timeout_seconds_remaining: int | None
    cashout_fraction: Decimal | None


@dataclass(frozen=True)
class TrancheExecution:
    requested_quantity: Decimal
    quantity_sold: Decimal
    gross: Decimal
    fee: Decimal
    attempts: int
    fill_events: int
    first_execution_time: datetime | None
    last_execution_time: datetime | None
    next_index: int

    @property
    def net_inflow(self) -> Decimal:
        return self.gross - self.fee

    @property
    def fully_sold(self) -> bool:
        return self.quantity_sold == self.requested_quantity


def _fraction_key(value: Decimal) -> int:
    return int(value * Decimal("100"))


def _build_policies() -> tuple[PartialTimePolicy, ...]:
    policies = [PartialTimePolicy(
        BASELINE_KEY, "Original H3: protected target + 10s fallback", None, None
    )]
    for timeout in TIMEOUT_SECONDS:
        for fraction in CASHOUT_FRACTIONS:
            percent = _fraction_key(fraction)
            policies.append(PartialTimePolicy(
                key=f"timeout{timeout}_fraction{percent}",
                label=f"Sell {percent}% at {timeout}s; manage remainder",
                timeout_seconds_remaining=timeout,
                cashout_fraction=fraction,
            ))
    return tuple(policies)


POLICIES = _build_policies()


def tranche_quantity(total_quantity: Decimal, fraction: Decimal) -> Decimal:
    """Sell at least the declared fraction using whole contracts."""

    if total_quantity <= 0:
        raise PartialTimeExitError("total quantity must be positive")
    if fraction <= 0 or fraction > 1:
        raise PartialTimeExitError("cashout fraction must be in (0, 1]")
    requested = (total_quantity * fraction).to_integral_value(rounding=ROUND_CEILING)
    return min(total_quantity, requested)


def cumulative_pnl(
    *, realized_net_inflow: Decimal, remaining_net_inflow: Decimal,
    original_outflow: Decimal,
) -> Decimal:
    return realized_net_inflow + remaining_net_inflow - original_outflow


def execute_tranche(
    *, snapshots: Sequence[Snapshot], signal_index: int, close_time: datetime,
    side: str, quantity: Decimal,
) -> TrancheExecution:
    """Progressively sell only the requested tranche after one-second delays."""

    remaining = quantity
    gross = Decimal("0")
    fee = Decimal("0")
    attempts = 0
    fill_events = 0
    first_time: datetime | None = None
    last_time: datetime | None = None
    decision_index = signal_index
    next_index = signal_index + 1
    while remaining > 0 and decision_index < len(snapshots):
        decision = snapshots[decision_index]
        execution_index = first_index_at_or_after(
            snapshots,
            decision_index + 1,
            decision.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if execution_index is None:
            next_index = len(snapshots)
            break
        execution_snapshot = snapshots[execution_index]
        if execution_snapshot.observed_at >= close_time:
            next_index = execution_index
            break
        attempts += 1
        execution = sell_quantity(execution_snapshot.book.bid_levels(side), remaining)
        if execution.quantity > 0:
            if first_time is None:
                first_time = execution_snapshot.observed_at
            last_time = execution_snapshot.observed_at
            fill_events += 1
            remaining -= execution.quantity
            gross += execution.gross
            fee += execution.fee
        next_index = execution_index + 1
        decision_index = next_index
    return TrancheExecution(
        requested_quantity=quantity,
        quantity_sold=quantity - remaining,
        gross=gross,
        fee=fee,
        attempts=attempts,
        fill_events=fill_events,
        first_execution_time=first_time,
        last_execution_time=last_time,
        next_index=next_index,
    )


def _candidate_fields(policy: PartialTimePolicy) -> dict[str, Any]:
    return {
        "partial_time_policy": policy.key,
        "partial_time_display_policy": policy.label,
        "timeout_seconds_remaining": (
            "" if policy.timeout_seconds_remaining is None
            else policy.timeout_seconds_remaining
        ),
        "cashout_fraction": (
            "" if policy.cashout_fraction is None
            else _decimal_text(policy.cashout_fraction)
        ),
        "cashout_percent": (
            "" if policy.cashout_fraction is None
            else _fraction_key(policy.cashout_fraction)
        ),
        "timeout_signal": False,
        "timeout_signal_time": "",
        "timeout_signal_seconds_remaining": "",
        "timeout_signal_executable_full_pnl": "",
        "timeout_requested_quantity": "0",
        "timeout_quantity_sold": "0",
        "timeout_gross": "0",
        "timeout_fee": "0",
        "timeout_net_inflow": "0",
        "timeout_attempts": 0,
        "timeout_fill_events": 0,
        "timeout_first_execution_time": "",
        "timeout_last_execution_time": "",
        "timeout_tranche_fully_sold": False,
        "remaining_quantity_after_timeout": "0",
        "cumulative_target_accounting": False,
        "post_timeout_target_filled": False,
        "post_timeout_fallback_filled": False,
        "residual_settlement_quantity": "0",
        "cash_liquidated_quantity": "0",
        "cash_liquidation_complete": False,
    }


def _finalize_row(
    row: dict[str, Any], *, entry: Any, entry_time: datetime,
    side: str, winning_side: str, close_time: datetime,
    timeout: TrancheExecution,
    remaining_execution: Any | None,
    remaining_quantity: Decimal,
    exit_time: datetime,
    exit_reason: str,
    target_signals: int,
    target_rejections: int,
    target_filled: bool,
    fallback_filled: bool,
) -> dict[str, Any]:
    timeout_net = timeout.net_inflow
    residual_settlement = Decimal("0")
    remaining_gross = Decimal("0")
    remaining_fee = Decimal("0")
    remaining_cash_quantity = Decimal("0")
    if remaining_execution is not None:
        remaining_gross = remaining_execution.gross
        remaining_fee = remaining_execution.fee
        remaining_cash_quantity = remaining_execution.quantity
    else:
        residual_settlement = remaining_quantity
        if side != winning_side:
            remaining_gross = Decimal("0")
        else:
            remaining_gross = remaining_quantity
    total_gross = timeout.gross + remaining_gross
    total_fee = timeout.fee + remaining_fee
    pnl = total_gross - total_fee - entry.buy_outflow
    cash_quantity = timeout.quantity_sold + remaining_cash_quantity
    row.update({
        "target_filled": target_filled,
        "target_signal_count": target_signals,
        "target_rejected_after_latency_count": target_rejections,
        "fallback_used": not target_filled,
        "exit_reason": exit_reason,
        "exit_execution_time": exit_time.isoformat(),
        "exit_gross": _decimal_text(total_gross),
        "exit_fee": _decimal_text(total_fee),
        "exit_average_price": _decimal_text(total_gross / entry.quantity),
        "pnl": _decimal_text(pnl),
        "profitable": pnl > 0,
        "full_capital_loss": pnl <= -FULL_LOSS_FRACTION * entry.buy_outflow,
        "post_timeout_target_filled": target_filled,
        "post_timeout_fallback_filled": fallback_filled,
        "residual_settlement_quantity": _decimal_text(residual_settlement),
        "cash_liquidated_quantity": _decimal_text(cash_quantity),
        "cash_liquidation_complete": cash_quantity == entry.quantity,
        "exposure_seconds": f"{(exit_time - entry_time).total_seconds():.6f}",
    })
    return row


def simulate_partial_time_policy(
    *, snapshots: Sequence[Snapshot], close_time: datetime, winning_side: str,
    baseline: Mapping[str, Any],
    entry_context: tuple[int, int, str, Decimal, Decimal, Any],
    policy: PartialTimePolicy,
) -> dict[str, Any]:
    """Apply one causal timeout/fraction rule with cumulative target accounting."""

    row = dict(baseline)
    row.update(_candidate_fields(policy))
    if policy.key == BASELINE_KEY:
        return row
    assert policy.timeout_seconds_remaining is not None
    assert policy.cashout_fraction is not None
    _decision_index, entry_index, side, _midpoint, _ask, entry = entry_context
    entry_time = snapshots[entry_index].observed_at
    target = (entry.quantity - entry.buy_outflow) * TARGET_FRACTION
    preclose = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
    index = entry_index + 1
    target_signals = 0
    target_rejections = 0
    signal_index: int | None = None

    # Phase one: retain the original full-position protected target until timeout.
    while index < len(snapshots):
        observed = snapshots[index]
        if observed.observed_at >= preclose:
            break
        full_sale = sell_quantity(observed.book.bid_levels(side), entry.quantity)
        full_pnl = (
            full_sale.sell_inflow - entry.buy_outflow
            if full_sale.quantity == entry.quantity else None
        )
        if full_pnl is not None and full_pnl >= target:
            target_signals += 1
            delayed_index = first_index_at_or_after(
                snapshots,
                index + 1,
                observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
            )
            if delayed_index is None or snapshots[delayed_index].observed_at >= preclose:
                target_rejections += 1
                break
            executed = sell_quantity(
                snapshots[delayed_index].book.bid_levels(side), entry.quantity
            )
            if (
                executed.quantity == entry.quantity
                and executed.sell_inflow - entry.buy_outflow >= target
            ):
                return row
            target_rejections += 1
            index = delayed_index + 1
            continue
        seconds_remaining = (close_time - observed.observed_at).total_seconds()
        if seconds_remaining <= policy.timeout_seconds_remaining:
            signal_index = index
            row.update({
                "timeout_signal": True,
                "timeout_signal_time": observed.observed_at.isoformat(),
                "timeout_signal_seconds_remaining": seconds_remaining,
                "timeout_signal_executable_full_pnl": (
                    "" if full_pnl is None else _decimal_text(full_pnl)
                ),
            })
            break
        index += 1

    # If no timeout observation occurred, the frozen baseline remains exact.
    if signal_index is None:
        return row

    requested = tranche_quantity(entry.quantity, policy.cashout_fraction)
    timeout = execute_tranche(
        snapshots=snapshots,
        signal_index=signal_index,
        close_time=close_time,
        side=side,
        quantity=requested,
    )
    remaining = entry.quantity - timeout.quantity_sold
    row.update({
        "timeout_requested_quantity": _decimal_text(timeout.requested_quantity),
        "timeout_quantity_sold": _decimal_text(timeout.quantity_sold),
        "timeout_gross": _decimal_text(timeout.gross),
        "timeout_fee": _decimal_text(timeout.fee),
        "timeout_net_inflow": _decimal_text(timeout.net_inflow),
        "timeout_attempts": timeout.attempts,
        "timeout_fill_events": timeout.fill_events,
        "timeout_first_execution_time": (
            "" if timeout.first_execution_time is None
            else timeout.first_execution_time.isoformat()
        ),
        "timeout_last_execution_time": (
            "" if timeout.last_execution_time is None
            else timeout.last_execution_time.isoformat()
        ),
        "timeout_tranche_fully_sold": timeout.fully_sold,
        "remaining_quantity_after_timeout": _decimal_text(remaining),
        "cumulative_target_accounting": remaining > 0,
    })

    if remaining == 0:
        exit_time = timeout.last_execution_time or close_time
        return _finalize_row(
            row,
            entry=entry,
            entry_time=entry_time,
            side=side,
            winning_side=winning_side,
            close_time=close_time,
            timeout=timeout,
            remaining_execution=None,
            remaining_quantity=Decimal("0"),
            exit_time=exit_time,
            exit_reason="full_timeout_cash_exit",
            target_signals=target_signals,
            target_rejections=target_rejections,
            target_filled=False,
            fallback_filled=False,
        )

    # If the timeout tranche could not finish before close, all unsold contracts settle.
    if not timeout.fully_sold or timeout.next_index >= len(snapshots):
        return _finalize_row(
            row,
            entry=entry,
            entry_time=entry_time,
            side=side,
            winning_side=winning_side,
            close_time=close_time,
            timeout=timeout,
            remaining_execution=None,
            remaining_quantity=remaining,
            exit_time=close_time,
            exit_reason="partial_timeout_with_settlement_residual",
            target_signals=target_signals,
            target_rejections=target_rejections,
            target_filled=False,
            fallback_filled=False,
        )

    # Phase two: the remainder must offset the realized partial sale and still
    # achieve the original whole-position target after fees and latency.
    index = timeout.next_index
    while index < len(snapshots):
        observed = snapshots[index]
        if observed.observed_at >= preclose:
            break
        hypothetical = sell_quantity(observed.book.bid_levels(side), remaining)
        if (
            hypothetical.quantity == remaining
            and cumulative_pnl(
                realized_net_inflow=timeout.net_inflow,
                remaining_net_inflow=hypothetical.sell_inflow,
                original_outflow=entry.buy_outflow,
            ) >= target
        ):
            target_signals += 1
            delayed_index = first_index_at_or_after(
                snapshots,
                index + 1,
                observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
            )
            if delayed_index is None or snapshots[delayed_index].observed_at >= preclose:
                target_rejections += 1
                break
            executed = sell_quantity(
                snapshots[delayed_index].book.bid_levels(side), remaining
            )
            if (
                executed.quantity == remaining
                and cumulative_pnl(
                    realized_net_inflow=timeout.net_inflow,
                    remaining_net_inflow=executed.sell_inflow,
                    original_outflow=entry.buy_outflow,
                ) >= target
            ):
                return _finalize_row(
                    row,
                    entry=entry,
                    entry_time=entry_time,
                    side=side,
                    winning_side=winning_side,
                    close_time=close_time,
                    timeout=timeout,
                    remaining_execution=executed,
                    remaining_quantity=remaining,
                    exit_time=snapshots[delayed_index].observed_at,
                    exit_reason="cumulative_protected_target_after_partial_timeout",
                    target_signals=target_signals,
                    target_rejections=target_rejections,
                    target_filled=True,
                    fallback_filled=False,
                )
            target_rejections += 1
            index = delayed_index + 1
            continue
        index += 1

    fallback, fallback_time = _find_preclose_exit(
        snapshots=snapshots,
        start_index=timeout.next_index,
        start_time=preclose,
        close_time=close_time,
        side=side,
        quantity=remaining,
    )
    if fallback is not None and fallback_time is not None:
        return _finalize_row(
            row,
            entry=entry,
            entry_time=entry_time,
            side=side,
            winning_side=winning_side,
            close_time=close_time,
            timeout=timeout,
            remaining_execution=fallback,
            remaining_quantity=remaining,
            exit_time=fallback_time,
            exit_reason="partial_timeout_then_preclose_exit",
            target_signals=target_signals,
            target_rejections=target_rejections,
            target_filled=False,
            fallback_filled=True,
        )
    return _finalize_row(
        row,
        entry=entry,
        entry_time=entry_time,
        side=side,
        winning_side=winning_side,
        close_time=close_time,
        timeout=timeout,
        remaining_execution=None,
        remaining_quantity=remaining,
        exit_time=close_time,
        exit_reason="partial_timeout_then_settlement_after_preclose_liquidity_failure",
        target_signals=target_signals,
        target_rejections=target_rejections,
        target_filled=False,
        fallback_filled=False,
    )


def _group_rows(rows: Sequence[Mapping[str, Any]], group: str) -> list[Mapping[str, Any]]:
    if group == "combined_122":
        return list(rows)
    if group == "development_96":
        return [row for row in rows if row["evidence_partition"] == "development_96"]
    if group == "opened_26":
        return [row for row in rows if row["evidence_partition"] == "opened_26"]
    if group == "earlier_64_diagnostic":
        return [row for row in rows if row["diagnostic_segment"] == "earlier_64"]
    if group == "later_32_diagnostic":
        return [row for row in rows if row["diagnostic_segment"] == "later_32"]
    raise PartialTimeExitError(f"unknown group: {group}")


def summarize_policies(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for group in (
        "development_96", "opened_26", "combined_122",
        "earlier_64_diagnostic", "later_32_diagnostic",
    ):
        source = _group_rows(rows, group)
        by_key = {
            policy.key: [row for row in source if row["partial_time_policy"] == policy.key]
            for policy in POLICIES
        }
        baseline = {
            str(row["ticker"]): float(row["pnl"] or 0.0)
            for row in by_key[BASELINE_KEY]
        }
        full_90 = {
            str(row["ticker"]): float(row["pnl"] or 0.0)
            for row in by_key[FULL_90_KEY]
        }
        winners = {ticker for ticker, pnl in baseline.items() if pnl > 0}
        losers = {ticker for ticker, pnl in baseline.items() if pnl < 0}
        for policy in POLICIES:
            selected = by_key[policy.key]
            completed = [row for row in selected if row["status"] == "completed"]
            pnl_market = [float(row["pnl"] or 0.0) for row in selected]
            pnl_filled = [float(row["pnl"]) for row in completed]
            differences = [
                float(row["pnl"] or 0.0) - baseline[str(row["ticker"])]
                for row in selected
            ]
            vs_90 = [
                float(row["pnl"] or 0.0) - full_90[str(row["ticker"])]
                for row in selected
            ]
            winner_rows = [row for row in completed if row["ticker"] in winners]
            loser_rows = [row for row in completed if row["ticker"] in losers]
            loser_savings = sum(
                float(row["pnl"]) - baseline[str(row["ticker"])] for row in loser_rows
            )
            winner_cost = sum(
                max(0.0, baseline[str(row["ticker"])] - float(row["pnl"]))
                for row in winner_rows
            )
            mean_market, ci_low, ci_high = _bootstrap(pnl_market)
            diff_mean, diff_low, diff_high = _bootstrap(differences)
            timeout_rows = [row for row in completed if bool(row["timeout_signal"])]
            output.append({
                "group": group,
                "partial_time_policy": policy.key,
                "display_policy": policy.label,
                "timeout_seconds_remaining": (
                    "" if policy.timeout_seconds_remaining is None
                    else policy.timeout_seconds_remaining
                ),
                "cashout_fraction": (
                    "" if policy.cashout_fraction is None
                    else float(policy.cashout_fraction)
                ),
                "cashout_percent": (
                    "" if policy.cashout_fraction is None
                    else _fraction_key(policy.cashout_fraction)
                ),
                "eligible_markets": len(selected),
                "entry_filled_markets": len(completed),
                "baseline_winning_entries": len(winners),
                "baseline_losing_entries": len(losers),
                "timeout_signals": len(timeout_rows),
                "timeout_stopped_winners": sum(row["ticker"] in winners for row in timeout_rows),
                "timeout_stopped_losers": sum(row["ticker"] in losers for row in timeout_rows),
                "total_pnl": sum(pnl_market),
                "mean_pnl_per_eligible_market": mean_market,
                "bootstrap_ci_low_per_eligible_market": ci_low,
                "bootstrap_ci_high_per_eligible_market": ci_high,
                "total_difference_vs_original": sum(differences),
                "mean_difference_vs_original": diff_mean,
                "paired_difference_ci_low": diff_low,
                "paired_difference_ci_high": diff_high,
                "total_difference_vs_full_90": sum(vs_90),
                "mean_pnl_per_filled_entry": _mean(pnl_filled),
                "profitable_rate_per_filled_entry": _mean(
                    [bool(row["profitable"]) for row in completed]
                ),
                "target_fill_rate": _mean([bool(row["target_filled"]) for row in completed]),
                "loser_savings_vs_original": loser_savings,
                "winner_gross_opportunity_cost": winner_cost,
                "net_savings_minus_winner_cost": loser_savings - winner_cost,
                "full_capital_losses": sum(bool(row["full_capital_loss"]) for row in completed),
                "timeout_tranches_fully_sold": sum(
                    bool(row["timeout_tranche_fully_sold"]) for row in timeout_rows
                ),
                "cash_liquidation_complete_rate": _mean(
                    [bool(row["cash_liquidation_complete"]) for row in timeout_rows]
                ),
                "residual_settlement_positions": sum(
                    Decimal(str(row["residual_settlement_quantity"])) > 0
                    for row in completed
                ),
                "pnl_05_quantile_per_filled_entry": _quantile(pnl_filled, 0.05),
                "worst_pnl_per_filled_entry": min(pnl_filled) if pnl_filled else math.nan,
                "pareto_frontier_total_vs_worst": False,
                "adaptive_development_only": True,
            })
    mark_pareto_frontier(output)
    return output


def mark_pareto_frontier(summaries: Sequence[dict[str, Any]]) -> None:
    combined = [row for row in summaries if row["group"] == "combined_122"]
    for row in combined:
        total = float(row["total_pnl"])
        worst = float(row["worst_pnl_per_filled_entry"])
        dominated = any(
            other["partial_time_policy"] != row["partial_time_policy"]
            and float(other["total_pnl"]) >= total
            and float(other["worst_pnl_per_filled_entry"]) >= worst
            and (
                float(other["total_pnl"]) > total
                or float(other["worst_pnl_per_filled_entry"]) > worst
            )
            for other in combined
        )
        row["pareto_frontier_total_vs_worst"] = not dominated


def verify_results(
    rows: Sequence[Mapping[str, Any]], summaries: Sequence[Mapping[str, Any]],
) -> None:
    expected = EXPECTED_TOTAL_MARKETS * len(POLICIES)
    if len(rows) != expected:
        raise PartialTimeExitError(f"expected {expected} rows; found {len(rows)}")
    lookup = {(row["group"], row["partial_time_policy"]): row for row in summaries}
    development = lookup[("development_96", BASELINE_KEY)]
    opened = lookup[("opened_26", BASELINE_KEY)]
    combined = lookup[("combined_122", BASELINE_KEY)]
    full_90 = lookup[("combined_122", FULL_90_KEY)]
    if int(development["entry_filled_markets"]) != EXPECTED_NATIVE_ENTRIES:
        raise PartialTimeExitError("development baseline did not reproduce 57 entries")
    if abs(float(development["mean_pnl_per_eligible_market"]) - 2.32) > 0.01:
        raise PartialTimeExitError("development baseline mean no longer reproduces H3")
    if int(opened["entry_filled_markets"]) != EXPECTED_HOLDOUT_ENTRIES:
        raise PartialTimeExitError("opened baseline did not reproduce 14 entries")
    if abs(float(opened["total_pnl"]) - EXPECTED_HOLDOUT_TOTAL_PNL) > 0.02:
        raise PartialTimeExitError("opened baseline did not reproduce -$46.55")
    if int(opened["full_capital_losses"]) != 1:
        raise PartialTimeExitError("opened baseline did not reproduce one full loss")
    if int(combined["entry_filled_markets"]) != EXPECTED_TOTAL_ENTRIES:
        raise PartialTimeExitError("combined baseline did not reproduce 71 entries")
    if abs(float(full_90["total_pnl"]) - EXPECTED_FULL_90_TOTAL_PNL) > 0.03:
        raise PartialTimeExitError("full 90-second rule did not reproduce $167.18")
    if int(full_90["full_capital_losses"]) != 0:
        raise PartialTimeExitError("full 90-second rule did not remove the full loss")


def markdown_report(
    scenario_rows: Sequence[Mapping[str, Any]], summaries: Sequence[Mapping[str, Any]],
) -> str:
    combined = [row for row in summaries if row["group"] == "combined_122"]
    baseline = next(row for row in combined if row["partial_time_policy"] == BASELINE_KEY)
    full_90 = next(row for row in combined if row["partial_time_policy"] == FULL_90_KEY)
    candidates = [row for row in combined if row["partial_time_policy"] != BASELINE_KEY]
    frontier = [row for row in combined if bool(row["pareto_frontier_total_vs_worst"])]
    baseline_losses = {
        str(row["ticker"]): float(row["pnl"])
        for row in scenario_rows
        if row["partial_time_policy"] == BASELINE_KEY
        and row["status"] == "completed" and float(row["pnl"]) < 0
    }
    lines = [
        "# KXBTC15M H3 partial time-exit risk frontier",
        "",
        "**Adaptive hypothesis-generation test; all 122 markets are opened development evidence.**",
        "",
        "The frozen H3 entry and protected whole-position target are unchanged. At the first "
        "causal native response at or below 75, 90, or 105 seconds remaining, a policy that "
        "has not already reached its target sells 25%, 50%, 75%, or 100% of whole contracts "
        "after one-second latency. A partial policy continues managing the remainder, but all "
        "realized partial proceeds count toward the original whole-trade target. The ten-second "
        "preclose fallback remains active for the remainder.",
        "",
        "## Fixed comparators",
        "",
        "| Comparator | Combined P&L | vs original | Full losses | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|",
        f"| {baseline['display_policy']} | {_money(baseline['total_pnl'])} | "
        f"{_money(baseline['total_difference_vs_original'])} | "
        f"{baseline['full_capital_losses']} | "
        f"{_money(baseline['pnl_05_quantile_per_filled_entry'])} | "
        f"{_money(baseline['worst_pnl_per_filled_entry'])} |",
        f"| {full_90['display_policy']} | {_money(full_90['total_pnl'])} | "
        f"{_money(full_90['total_difference_vs_original'])} | "
        f"{full_90['full_capital_losses']} | "
        f"{_money(full_90['pnl_05_quantile_per_filled_entry'])} | "
        f"{_money(full_90['worst_pnl_per_filled_entry'])} |",
        "",
        "## Joint time and cash-out surface",
        "",
        "| Time | Sold | Signals W/L | Target fill | Combined P&L | vs original | vs full 90 | Loser saved | Winner cost | Full losses | 5% tail | Worst | Pareto |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in candidates:
        lines.append(
            f"| {row['timeout_seconds_remaining']}s | {row['cashout_percent']}% | "
            f"{row['timeout_stopped_winners']}/{row['timeout_stopped_losers']} | "
            f"{100 * float(row['target_fill_rate']):.1f}% | "
            f"{_money(row['total_pnl'])} | {_money(row['total_difference_vs_original'])} | "
            f"{_money(row['total_difference_vs_full_90'])} | "
            f"{_money(row['loser_savings_vs_original'])} | "
            f"{_money(row['winner_gross_opportunity_cost'])} | "
            f"{row['full_capital_losses']} | "
            f"{_money(row['pnl_05_quantile_per_filled_entry'])} | "
            f"{_money(row['worst_pnl_per_filled_entry'])} | "
            f"{row['pareto_frontier_total_vs_worst']} |"
        )
    lines.extend([
        "",
        "## Known-loss execution",
        "",
        "| Time | Sold | Signal sec left | Full P&L at signal | Tranche qty | Net timeout inflow | Residual settlement qty | Result P&L | Saved |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in scenario_rows:
        if row["partial_time_policy"] == BASELINE_KEY or row["ticker"] not in baseline_losses:
            continue
        lines.append(
            f"| {row['timeout_seconds_remaining']}s | {row['cashout_percent']}% | "
            f"{row['timeout_signal_seconds_remaining'] or 'n/a'} | "
            f"{_money(row['timeout_signal_executable_full_pnl']) if row['timeout_signal_executable_full_pnl'] != '' else 'n/a'} | "
            f"{row['timeout_quantity_sold']} | {_money(row['timeout_net_inflow'])} | "
            f"{row['residual_settlement_quantity']} | {_money(row['pnl'])} | "
            f"{_money(float(row['pnl']) - baseline_losses[str(row['ticker'])])} |"
        )
    lines.extend([
        "",
        "## P&L–worst-loss Pareto frontier",
        "",
        "A policy is on this descriptive frontier when no other tested rule has both higher "
        "combined P&L and an equal-or-better worst filled-trade outcome.",
        "",
        "Frontier policies: " + ", ".join(
            f"`{row['partial_time_policy']}`" for row in frontier
        ),
        "",
        "The frontier is a risk trade-off map, not an automatic selection rule. All parameters "
        "were examined on opened evidence containing only one baseline loser. Any chosen H3 v2 "
        "policy must be frozen before a newly collected chronological confirmation sample is "
        "evaluated. No external BTC data, authentication, or order placement is used.",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_zip", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--development-outcomes-csv", type=Path, required=True)
    parser.add_argument("--opened-holdout-outcomes-csv", type=Path, required=True)
    parser.add_argument("--opened-holdout-scenarios-csv", type=Path, required=True)
    parser.add_argument("--series-csv", type=Path, required=True)
    parser.add_argument("--fee-changes-csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("analysis/kxbtc15m_h3_partial_time_exits"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    development_outcomes = load_outcomes(args.development_outcomes_csv)
    opened_outcomes = load_opened_holdout_outcomes(args.opened_holdout_outcomes_csv)
    opened_baseline = load_opened_baseline(args.opened_holdout_scenarios_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    scenario_rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_h3_partial_time_") as temporary:
        audit_root = Path(temporary)
        safe_extract_zip(args.audit_zip, audit_root)
        dev_all = [
            assess_market(index, manifest, audit_root)
            for index, manifest in enumerate(select_development_manifests(audit_root), start=1)
        ]
        dev_markets = [market for market in dev_all if market.eligible]
        holdout_markets = [
            assess_market(index, manifest, audit_root)
            for index, manifest in enumerate(select_opened_manifests(audit_root), start=101)
        ]
        if len(dev_markets) != 96 or len(holdout_markets) != 26:
            raise PartialTimeExitError(
                "expected 96 eligible development plus 26 opened markets"
            )
        if any(not market.eligible for market in holdout_markets):
            raise PartialTimeExitError("opened partition failed its frozen quality gate")
        if set(development_outcomes) != {market.ticker for market in dev_markets}:
            raise PartialTimeExitError("development outcomes do not match markets")
        if set(opened_outcomes) != {market.ticker for market in holdout_markets}:
            raise PartialTimeExitError("opened outcomes do not match markets")
        if set(opened_baseline) != {market.ticker for market in holdout_markets}:
            raise PartialTimeExitError("opened baseline rows do not match markets")

        work = (
            _market_partition(dev_markets, "development_96")
            + _market_partition(holdout_markets, "opened_26")
        )
        for number, (market, partition, segment) in enumerate(work, start=1):
            outcomes = development_outcomes if partition == "development_96" else opened_outcomes
            _legacy, snapshots = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            context = find_native_entry(snapshots, close)
            baseline = simulate_policy(
                snapshots=snapshots,
                close_time=close,
                winning_side=outcomes[market.ticker],
                ticker=market.ticker,
                segment=segment,
                policy=BASELINE_POLICY,
                kind="fraction",
                value=TARGET_FRACTION,
                entry_context=context,
            )
            frequency = simulate_frequency_market(
                snapshots=snapshots,
                close_time=close,
                winning_side=outcomes[market.ticker],
                ticker=market.ticker,
                frequency="native",
                entry_mode="unprotected",
                clock_basis="causal_response_receipt",
                diagnostic_segment=segment,
            )
            verify_baseline_reproduction(baseline, frequency)
            if partition == "opened_26":
                verify_opened_baseline_row(baseline, opened_baseline[market.ticker])
            baseline.update({
                "market_index": market.index,
                "evidence_partition": partition,
                "diagnostic_segment": segment,
                "baseline_pnl": baseline["pnl"],
                "adaptive_development_only": True,
                "external_btc_data_used": False,
                "authentication_used": False,
                "orders_placed": 0,
            })
            for policy in POLICIES:
                if baseline["status"] != "completed":
                    row = dict(baseline)
                    row.update(_candidate_fields(policy))
                else:
                    if context is None:
                        raise PartialTimeExitError(
                            f"{market.ticker}: completed baseline lacks entry context"
                        )
                    row = simulate_partial_time_policy(
                        snapshots=snapshots,
                        close_time=close,
                        winning_side=outcomes[market.ticker],
                        baseline=baseline,
                        entry_context=context,
                        policy=policy,
                    )
                row.update({
                    "market_index": market.index,
                    "evidence_partition": partition,
                    "diagnostic_segment": segment,
                    "baseline_pnl": baseline["pnl"],
                    "pnl_difference_vs_baseline": (
                        float(row["pnl"] or 0.0) - float(baseline["pnl"] or 0.0)
                    ),
                    "adaptive_development_only": True,
                    "external_btc_data_used": False,
                    "authentication_used": False,
                    "orders_placed": 0,
                })
                scenario_rows.append(row)
            print(f"[{number:03d}/{len(work)}] {market.ticker}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = args.output_dir / "kxbtc15m_h3_partial_time_exit_scenarios.csv"
    write_csv(scenario_path, scenario_rows)
    summaries = summarize_policies(scenario_rows)
    verify_results(scenario_rows, summaries)
    summary_path = args.output_dir / "kxbtc15m_h3_partial_time_exit_summary.csv"
    frontier_path = args.output_dir / "kxbtc15m_h3_partial_time_exit_pareto.csv"
    report_path = args.output_dir / "KXBTC15M_H3_PARTIAL_TIME_EXITS.md"
    write_csv(summary_path, summaries)
    write_csv(frontier_path, [
        row for row in summaries
        if row["group"] == "combined_122" and row["pareto_frontier_total_vs_worst"]
    ])
    report_path.write_text(markdown_report(scenario_rows, summaries), encoding="utf-8")

    combined = [row for row in summaries if row["group"] == "combined_122"]
    frontier = [row for row in combined if row["pareto_frontier_total_vs_worst"]]
    print("KXBTC15M H3 partial time-exit risk-frontier diagnostic: PASS")
    print(f"Eligible markets: {EXPECTED_TOTAL_MARKETS}")
    print(f"Baseline entries: {EXPECTED_TOTAL_ENTRIES}")
    print(f"Policies including original comparator: {len(POLICIES)}")
    print(f"Pareto-frontier policies: {len(frontier)}")
    print("H3 v2 selected: no")
    print("Fresh validation performed: no")
    print("Authentication used: no")
    print("Orders placed: 0")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, PartialTimeExitError, OSError, ValueError) as exc:
        raise SystemExit(f"KXBTC15M H3 partial-time exit error: {exc}") from exc
