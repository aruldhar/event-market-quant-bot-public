#!/usr/bin/env python3
"""Compare matched exit policies on the frozen H3 first-trigger entries.

The entry rule is not searched again: one trade per development market at the
previously selected first 90c <= favored midpoint < 98c observation with
240 < seconds_remaining <= 300.  Every policy receives the same one-second
entry latency, archived full-depth fill, $100 maximum budget, fee model, and
winning-side outcome.  Only the exit rule changes.

This is an expanded development diagnostic.  It never opens the sealed
holdout and it does not use an external or authenticated BTC value.
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
    NET_PROFIT_TARGET,
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
from analyze_kxbtc15m_h3_late_convergence import favored_quote
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    parse_time,
    safe_extract_zip,
    select_development_manifests,
)


PRIMARY_CANDIDATE = "primary_90_98c"
EXPECTED_PRIMARY_TRIGGERS = 52
PRECLOSE_EXIT_SECONDS = 10
PERCENTAGE_TARGETS = (Decimal("0.25"), Decimal("0.50"), Decimal("0.75"))
CONDITIONAL_BID_THRESHOLDS = (Decimal("0.90"), Decimal("0.95"), Decimal("0.98"))


class ExitPolicyError(RuntimeError):
    """Raised when an H3 exit-policy input or invariant is violated."""


def parse_bool(value: Any) -> bool:
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    raise ExitPolicyError(f"invalid boolean value: {value!r}")


def load_primary_triggers(path: Path) -> list[dict[str, str]]:
    required = {
        "candidate",
        "ticker",
        "diagnostic_segment",
        "decision_time",
        "pnl",
        "exit_reason",
        "holdout_read",
        "external_btc_data_used",
    }
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = required - fields
        if missing:
            raise ExitPolicyError(f"trigger CSV missing fields: {sorted(missing)}")
        rows = [row for row in reader if row["candidate"] == PRIMARY_CANDIDATE]
    if len(rows) != EXPECTED_PRIMARY_TRIGGERS:
        raise ExitPolicyError(
            f"expected {EXPECTED_PRIMARY_TRIGGERS} primary triggers; found {len(rows)}"
        )
    if len({row["ticker"] for row in rows}) != EXPECTED_PRIMARY_TRIGGERS:
        raise ExitPolicyError("primary trigger tickers are not unique")
    if any(parse_bool(row["holdout_read"]) for row in rows):
        raise ExitPolicyError("trigger input reports a holdout read")
    if any(parse_bool(row["external_btc_data_used"]) for row in rows):
        raise ExitPolicyError("trigger input reports external BTC data")
    return sorted(rows, key=lambda row: row["ticker"])


def policy_names() -> tuple[str, ...]:
    percentage_preclose = tuple(
        f"target_{int(fraction * 100)}pct_max_or_preclose"
        for fraction in PERCENTAGE_TARGETS
    )
    percentage_settlement = tuple(
        f"target_{int(fraction * 100)}pct_max_or_settlement"
        for fraction in PERCENTAGE_TARGETS
    )
    conditional = tuple(
        f"target_1usd_then_hold_if_preclose_bid_{int(level * 100)}c"
        for level in CONDITIONAL_BID_THRESHOLDS
    )
    return (
        "baseline_1usd_or_preclose",
        "target_1usd_or_settlement",
        "hold_to_settlement",
        *percentage_preclose,
        *percentage_settlement,
        *conditional,
    )


def percentage_target(maximum_settlement_profit: Decimal, fraction: Decimal) -> Decimal:
    if maximum_settlement_profit <= 0:
        raise ExitPolicyError("maximum settlement profit must be positive")
    if fraction <= 0 or fraction >= 1:
        raise ExitPolicyError("target fraction must be strictly between zero and one")
    return maximum_settlement_profit * fraction


def _settlement_values(
    *, side: str, winning_side: str, quantity: Decimal, outflow: Decimal
) -> tuple[Decimal, Decimal]:
    gross = quantity if side == winning_side else Decimal("0")
    return gross, gross - outflow


def _find_target_exit(
    *,
    snapshots: Sequence[Snapshot],
    start_index: int,
    stop_time: datetime,
    side: str,
    quantity: Decimal,
    outflow: Decimal,
    target: Decimal,
) -> tuple[Any | None, datetime | None, bool, bool, int]:
    signal_seen = False
    missed = 0
    for index in range(start_index, len(snapshots)):
        observed = snapshots[index]
        if observed.observed_at >= stop_time:
            break
        hypothetical = sell_quantity(observed.book.bid_levels(side), quantity)
        if hypothetical.quantity != quantity or hypothetical.sell_inflow - outflow < target:
            continue
        signal_seen = True
        delayed_index = first_index_at_or_after(
            snapshots,
            index + 1,
            observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if delayed_index is None or snapshots[delayed_index].observed_at >= stop_time:
            missed += 1
            continue
        executed = sell_quantity(snapshots[delayed_index].book.bid_levels(side), quantity)
        if executed.quantity != quantity:
            missed += 1
            continue
        achieved = executed.sell_inflow - outflow >= target
        return executed, snapshots[delayed_index].observed_at, signal_seen, achieved, missed
    return None, None, signal_seen, False, missed


def _find_preclose_exit(
    *,
    snapshots: Sequence[Snapshot],
    start_index: int,
    start_time: datetime,
    close_time: datetime,
    side: str,
    quantity: Decimal,
) -> tuple[Any | None, datetime | None]:
    index = first_index_at_or_after(snapshots, start_index, start_time)
    while index is not None and index < len(snapshots):
        observed = snapshots[index]
        delayed_index = first_index_at_or_after(
            snapshots,
            index + 1,
            observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if delayed_index is None or snapshots[delayed_index].observed_at >= close_time:
            break
        executed = sell_quantity(snapshots[delayed_index].book.bid_levels(side), quantity)
        if executed.quantity == quantity:
            return executed, snapshots[delayed_index].observed_at
        index = delayed_index + 1
    return None, None


def preclose_executable_average_bid(
    *, snapshots: Sequence[Snapshot], start_index: int, preclose_time: datetime,
    side: str, quantity: Decimal,
) -> tuple[Decimal | None, int | None]:
    index = first_index_at_or_after(snapshots, start_index, preclose_time)
    if index is None:
        return None, None
    execution = sell_quantity(snapshots[index].book.bid_levels(side), quantity)
    if execution.quantity != quantity or quantity <= 0:
        return None, index
    return execution.gross / quantity, index


def _row(
    *,
    base: Mapping[str, Any],
    policy: str,
    exit_reason: str,
    exit_time: datetime,
    exit_gross: Decimal,
    exit_fee: Decimal,
    entry_fee: Decimal,
    pnl: Decimal,
    quantity: Decimal,
    outflow: Decimal,
    maximum_settlement_profit: Decimal,
    settlement_pnl: Decimal,
    target_amount: Decimal | None = None,
    target_fraction: Decimal | None = None,
    target_hit: bool = False,
    target_signal_seen: bool = False,
    missed_target_signals: int = 0,
    conditional_threshold: Decimal | None = None,
    conditional_reference_bid: Decimal | None = None,
    conditional_action: str = "",
) -> dict[str, Any]:
    return {
        **base,
        "exit_policy": policy,
        "status": "completed",
        "contracts": float(quantity),
        "cash_deployed": float(outflow),
        "entry_fee": float(entry_fee),
        "exit_time": exit_time.isoformat(),
        "exit_reason": exit_reason,
        "exit_gross": float(exit_gross),
        "exit_fee": float(exit_fee),
        "total_fees": float(entry_fee + exit_fee),
        "pnl": float(pnl),
        "profitable": pnl > 0,
        "maximum_settlement_profit": float(maximum_settlement_profit),
        "settlement_counterfactual_pnl": float(settlement_pnl),
        "target_amount": "" if target_amount is None else float(target_amount),
        "target_fraction_of_maximum": "" if target_fraction is None else float(target_fraction),
        "target_signal_seen": target_signal_seen,
        "target_achieved_after_latency": target_hit,
        "missed_target_signals": missed_target_signals,
        "conditional_preclose_bid_threshold": (
            "" if conditional_threshold is None else float(conditional_threshold)
        ),
        "conditional_preclose_executable_average_bid": (
            "" if conditional_reference_bid is None else float(conditional_reference_bid)
        ),
        "conditional_action": conditional_action,
        "holdout_read": False,
        "external_btc_data_used": False,
    }


def simulate_exit_policies(
    *,
    snapshots: Sequence[Snapshot],
    decision_index: int,
    close_time: datetime,
    winning_side: str,
    trigger: Mapping[str, Any],
) -> list[dict[str, Any]]:
    decision = snapshots[decision_index]
    quote = favored_quote(decision.book)
    if quote is None:
        raise ExitPolicyError(f"{trigger['ticker']}: favored quote unavailable at trigger")
    side, midpoint, decision_ask = quote
    seconds_remaining = (close_time - decision.observed_at).total_seconds()
    if not (240 < seconds_remaining <= 300 and Decimal("0.90") <= midpoint < Decimal("0.98")):
        raise ExitPolicyError(f"{trigger['ticker']}: trigger no longer satisfies primary rule")

    execution_index = first_index_at_or_after(
        snapshots,
        decision_index + 1,
        decision.observed_at + timedelta(seconds=LATENCY_SECONDS),
    )
    if execution_index is None or snapshots[execution_index].observed_at >= close_time:
        raise ExitPolicyError(f"{trigger['ticker']}: entry cannot execute before close")
    entry_snapshot = snapshots[execution_index]
    entry_ask = best_ask(entry_snapshot.book, side)
    if entry_ask is None:
        raise ExitPolicyError(f"{trigger['ticker']}: entry ask unavailable")
    entry = buy_with_budget(entry_snapshot.book.ask_levels(side), MAX_BUDGET)
    if entry.quantity <= 0:
        raise ExitPolicyError(f"{trigger['ticker']}: entry unfilled")

    quantity, outflow = entry.quantity, entry.buy_outflow
    maximum_profit = quantity - outflow
    if maximum_profit <= 0:
        raise ExitPolicyError(f"{trigger['ticker']}: nonpositive maximum settlement profit")
    settlement_gross, settlement_pnl = _settlement_values(
        side=side, winning_side=winning_side, quantity=quantity, outflow=outflow
    )
    base = {
        "ticker": trigger["ticker"],
        "diagnostic_segment": trigger["diagnostic_segment"],
        "decision_time": decision.observed_at.isoformat(),
        "seconds_remaining": seconds_remaining,
        "side": side,
        "favored_side_won": side == winning_side,
        "decision_favored_midpoint": float(midpoint),
        "decision_favored_ask": float(decision_ask),
        "entry_execution_time": entry_snapshot.observed_at.isoformat(),
        "entry_best_ask": float(entry_ask),
        "entry_average_price": float(entry.gross / quantity),
        "max_budget": float(MAX_BUDGET),
    }
    output: list[dict[str, Any]] = []

    output.append(_row(
        base=base, policy="hold_to_settlement", exit_reason="settlement",
        exit_time=close_time, exit_gross=settlement_gross, exit_fee=Decimal("0"),
        entry_fee=entry.fee, pnl=settlement_pnl, quantity=quantity, outflow=outflow,
        maximum_settlement_profit=maximum_profit, settlement_pnl=settlement_pnl,
        conditional_action="hold",
    ))

    target, target_time, signal, achieved, missed = _find_target_exit(
        snapshots=snapshots, start_index=execution_index + 1, stop_time=close_time,
        side=side, quantity=quantity, outflow=outflow, target=NET_PROFIT_TARGET,
    )
    if target is None:
        output.append(_row(
            base=base, policy="target_1usd_or_settlement",
            exit_reason="settlement_after_no_target", exit_time=close_time,
            exit_gross=settlement_gross, exit_fee=Decimal("0"), entry_fee=entry.fee,
            pnl=settlement_pnl, quantity=quantity, outflow=outflow,
            maximum_settlement_profit=maximum_profit, settlement_pnl=settlement_pnl,
            target_amount=NET_PROFIT_TARGET, target_hit=False,
            target_signal_seen=signal, missed_target_signals=missed,
            conditional_action="hold",
        ))
    else:
        output.append(_row(
            base=base, policy="target_1usd_or_settlement", exit_reason="profit_target",
            exit_time=target_time, exit_gross=target.gross, exit_fee=target.fee,
            entry_fee=entry.fee, pnl=target.sell_inflow - outflow, quantity=quantity,
            outflow=outflow, maximum_settlement_profit=maximum_profit,
            settlement_pnl=settlement_pnl, target_amount=NET_PROFIT_TARGET,
            target_hit=achieved, target_signal_seen=signal, missed_target_signals=missed,
            conditional_action="sell",
        ))

    for fraction in PERCENTAGE_TARGETS:
        target_amount = percentage_target(maximum_profit, fraction)
        target, target_time, signal, achieved, missed = _find_target_exit(
            snapshots=snapshots, start_index=execution_index + 1,
            stop_time=close_time, side=side, quantity=quantity,
            outflow=outflow, target=target_amount,
        )
        policy = f"target_{int(fraction * 100)}pct_max_or_settlement"
        if target is None:
            output.append(_row(
                base=base, policy=policy,
                exit_reason="settlement_after_no_percentage_target",
                exit_time=close_time, exit_gross=settlement_gross,
                exit_fee=Decimal("0"), entry_fee=entry.fee, pnl=settlement_pnl,
                quantity=quantity, outflow=outflow,
                maximum_settlement_profit=maximum_profit,
                settlement_pnl=settlement_pnl, target_amount=target_amount,
                target_fraction=fraction, target_hit=False,
                target_signal_seen=signal, missed_target_signals=missed,
                conditional_action="hold",
            ))
        else:
            output.append(_row(
                base=base, policy=policy, exit_reason="profit_target",
                exit_time=target_time, exit_gross=target.gross,
                exit_fee=target.fee, entry_fee=entry.fee,
                pnl=target.sell_inflow - outflow, quantity=quantity,
                outflow=outflow, maximum_settlement_profit=maximum_profit,
                settlement_pnl=settlement_pnl, target_amount=target_amount,
                target_fraction=fraction, target_hit=achieved,
                target_signal_seen=signal, missed_target_signals=missed,
                conditional_action="sell",
            ))

    preclose_time = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)

    def target_or_preclose(
        *, policy: str, target_amount: Decimal, fraction: Decimal | None
    ) -> dict[str, Any]:
        execution, exit_time, seen, hit, missed_signals = _find_target_exit(
            snapshots=snapshots, start_index=execution_index + 1,
            stop_time=preclose_time, side=side, quantity=quantity,
            outflow=outflow, target=target_amount,
        )
        if execution is not None:
            return _row(
                base=base, policy=policy, exit_reason="profit_target",
                exit_time=exit_time, exit_gross=execution.gross, exit_fee=execution.fee,
                entry_fee=entry.fee, pnl=execution.sell_inflow - outflow,
                quantity=quantity, outflow=outflow,
                maximum_settlement_profit=maximum_profit, settlement_pnl=settlement_pnl,
                target_amount=target_amount, target_fraction=fraction, target_hit=hit,
                target_signal_seen=seen, missed_target_signals=missed_signals,
                conditional_action="sell",
            )
        forced, forced_time = _find_preclose_exit(
            snapshots=snapshots, start_index=execution_index + 1,
            start_time=preclose_time, close_time=close_time, side=side, quantity=quantity,
        )
        if forced is None:
            return _row(
                base=base, policy=policy,
                exit_reason="settlement_after_preclose_liquidity_failure",
                exit_time=close_time, exit_gross=settlement_gross,
                exit_fee=Decimal("0"), entry_fee=entry.fee, pnl=settlement_pnl,
                quantity=quantity, outflow=outflow,
                maximum_settlement_profit=maximum_profit, settlement_pnl=settlement_pnl,
                target_amount=target_amount, target_fraction=fraction,
                target_signal_seen=seen, missed_target_signals=missed_signals,
                conditional_action="hold_liquidity_failure",
            )
        return _row(
            base=base, policy=policy, exit_reason="preclose_time_exit",
            exit_time=forced_time, exit_gross=forced.gross, exit_fee=forced.fee,
            entry_fee=entry.fee, pnl=forced.sell_inflow - outflow,
            quantity=quantity, outflow=outflow,
            maximum_settlement_profit=maximum_profit, settlement_pnl=settlement_pnl,
            target_amount=target_amount, target_fraction=fraction,
            target_signal_seen=seen, missed_target_signals=missed_signals,
            conditional_action="sell",
        )

    output.append(target_or_preclose(
        policy="baseline_1usd_or_preclose", target_amount=NET_PROFIT_TARGET,
        fraction=None,
    ))
    for fraction in PERCENTAGE_TARGETS:
        output.append(target_or_preclose(
            policy=f"target_{int(fraction * 100)}pct_max_or_preclose",
            target_amount=percentage_target(maximum_profit, fraction),
            fraction=fraction,
        ))

    for threshold in CONDITIONAL_BID_THRESHOLDS:
        policy = f"target_1usd_then_hold_if_preclose_bid_{int(threshold * 100)}c"
        target, target_time, signal, achieved, missed = _find_target_exit(
            snapshots=snapshots, start_index=execution_index + 1,
            stop_time=preclose_time, side=side, quantity=quantity,
            outflow=outflow, target=NET_PROFIT_TARGET,
        )
        if target is not None:
            output.append(_row(
                base=base, policy=policy, exit_reason="profit_target",
                exit_time=target_time, exit_gross=target.gross, exit_fee=target.fee,
                entry_fee=entry.fee, pnl=target.sell_inflow - outflow,
                quantity=quantity, outflow=outflow,
                maximum_settlement_profit=maximum_profit, settlement_pnl=settlement_pnl,
                target_amount=NET_PROFIT_TARGET, target_hit=achieved,
                target_signal_seen=signal, missed_target_signals=missed,
                conditional_threshold=threshold, conditional_action="sell_target",
            ))
            continue
        reference_bid, reference_index = preclose_executable_average_bid(
            snapshots=snapshots, start_index=execution_index + 1,
            preclose_time=preclose_time, side=side, quantity=quantity,
        )
        if reference_bid is not None and reference_bid >= threshold:
            output.append(_row(
                base=base, policy=policy, exit_reason="conditional_hold_to_settlement",
                exit_time=close_time, exit_gross=settlement_gross,
                exit_fee=Decimal("0"), entry_fee=entry.fee, pnl=settlement_pnl,
                quantity=quantity, outflow=outflow,
                maximum_settlement_profit=maximum_profit, settlement_pnl=settlement_pnl,
                target_amount=NET_PROFIT_TARGET, target_signal_seen=signal,
                missed_target_signals=missed, conditional_threshold=threshold,
                conditional_reference_bid=reference_bid, conditional_action="hold",
            ))
            continue
        forced_start = (
            snapshots[reference_index].observed_at
            if reference_index is not None else preclose_time
        )
        forced, forced_time = _find_preclose_exit(
            snapshots=snapshots, start_index=execution_index + 1,
            start_time=forced_start, close_time=close_time, side=side, quantity=quantity,
        )
        if forced is None:
            output.append(_row(
                base=base, policy=policy,
                exit_reason="settlement_after_conditional_sell_liquidity_failure",
                exit_time=close_time, exit_gross=settlement_gross,
                exit_fee=Decimal("0"), entry_fee=entry.fee, pnl=settlement_pnl,
                quantity=quantity, outflow=outflow,
                maximum_settlement_profit=maximum_profit, settlement_pnl=settlement_pnl,
                target_amount=NET_PROFIT_TARGET, target_signal_seen=signal,
                missed_target_signals=missed, conditional_threshold=threshold,
                conditional_reference_bid=reference_bid,
                conditional_action="hold_liquidity_failure",
            ))
        else:
            output.append(_row(
                base=base, policy=policy, exit_reason="conditional_preclose_sell",
                exit_time=forced_time, exit_gross=forced.gross, exit_fee=forced.fee,
                entry_fee=entry.fee, pnl=forced.sell_inflow - outflow,
                quantity=quantity, outflow=outflow,
                maximum_settlement_profit=maximum_profit, settlement_pnl=settlement_pnl,
                target_amount=NET_PROFIT_TARGET, target_signal_seen=signal,
                missed_target_signals=missed, conditional_threshold=threshold,
                conditional_reference_bid=reference_bid, conditional_action="sell",
            ))

    if {row["exit_policy"] for row in output} != set(policy_names()):
        raise ExitPolicyError("internal policy set mismatch")
    return output


def _bootstrap_mean(values: Sequence[float]) -> tuple[float, float, float]:
    if not values:
        return math.nan, math.nan, math.nan
    estimate = statistics.mean(values)
    if len(values) < 2:
        return estimate, math.nan, math.nan
    rng = random.Random(20260813)
    samples = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(2_000)]
    samples.sort()
    return estimate, samples[49], samples[1949]


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    baseline_by_ticker = {
        row["ticker"]: float(row["pnl"])
        for row in rows if row["exit_policy"] == "baseline_1usd_or_preclose"
    }
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        if segment == "all_96":
            source = list(rows)
        else:
            key = "earlier_64" if segment == "earlier_64_diagnostic" else "later_32"
            source = [row for row in rows if row["diagnostic_segment"] == key]
        for policy in policy_names():
            selected = [row for row in source if row["exit_policy"] == policy]
            pnl = [float(row["pnl"]) for row in selected]
            mean, low, high = _bootstrap_mean(pnl)
            sold_winners = [
                row for row in selected
                if bool(row["favored_side_won"]) and "settlement" not in row["exit_reason"]
            ]
            sold_losers = [
                row for row in selected
                if not bool(row["favored_side_won"]) and "settlement" not in row["exit_reason"]
            ]
            output.append({
                "segment": segment,
                "exit_policy": policy,
                "triggered_markets": len(selected),
                "mean_pnl": mean,
                "bootstrap_ci_low": low,
                "bootstrap_ci_high": high,
                "mean_pnl_difference_vs_baseline": (
                    statistics.mean(
                        float(row["pnl"]) - baseline_by_ticker[row["ticker"]]
                        for row in selected
                    ) if selected else math.nan
                ),
                "profitable_rate": statistics.mean(bool(row["profitable"]) for row in selected)
                if selected else math.nan,
                "target_hit_rate": statistics.mean(bool(row["target_achieved_after_latency"]) for row in selected)
                if selected else math.nan,
                "settlement_exit_rate": statistics.mean("settlement" in row["exit_reason"] for row in selected)
                if selected else math.nan,
                "full_capital_loss_rate": statistics.mean(
                    float(row["pnl"]) <= -0.90 * float(row["cash_deployed"])
                    for row in selected
                ) if selected else math.nan,
                "pnl_05_quantile": _quantile(pnl, 0.05),
                "worst_pnl": min(pnl) if pnl else math.nan,
                "mean_profit_sacrificed_on_sold_winners": statistics.mean(
                    float(row["settlement_counterfactual_pnl"]) - float(row["pnl"])
                    for row in sold_winners
                ) if sold_winners else 0.0,
                "mean_loss_avoided_on_sold_losers": statistics.mean(
                    float(row["pnl"]) - float(row["settlement_counterfactual_pnl"])
                    for row in sold_losers
                ) if sold_losers else 0.0,
                "holdout_read": False,
                "external_btc_data_used": False,
            })
    return output


def verify_baseline_reproduction(
    triggers: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]
) -> None:
    expected = {row["ticker"]: float(row["pnl"]) for row in triggers}
    actual = {
        row["ticker"]: float(row["pnl"])
        for row in rows if row["exit_policy"] == "baseline_1usd_or_preclose"
    }
    if set(expected) != set(actual):
        raise ExitPolicyError("baseline reproduction ticker set mismatch")
    mismatches = [ticker for ticker in expected if abs(expected[ticker] - actual[ticker]) > 1e-9]
    if mismatches:
        raise ExitPolicyError(
            f"baseline reproduction failed for {len(mismatches)} trigger(s); first={mismatches[0]}"
        )


def _money(value: float) -> str:
    return "n/a" if math.isnan(value) else f"${value:.2f}"


def _percent(value: float) -> str:
    return "n/a" if math.isnan(value) else f"{value:.1%}"


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    all_rows = [row for row in summary if row["segment"] == "all_96"]
    lines = [
        "# KXBTC15M H3 matched exit-policy diagnostic",
        "",
        "**Expanded development diagnostic; first-trigger entries frozen; holdout sealed.**",
        "",
        "All policies reuse the same 52 first-trigger 90–98 cent entries from four to five "
        "minutes before close. The existing $1-target/10-second-preclose result is reproduced "
        "before comparison. Percentage targets are fractions of each filled trade's maximum "
        "net settlement profit, after its actual entry cost and fee. Each percentage target "
        "is tested twice: once with a ten-second preclose fallback and once with settlement "
        "as the fallback.",
        "",
        "The Kalshi-only conditional policies take the $1 target when available. Otherwise, "
        "at ten seconds before close they hold to settlement only when the archived full-position "
        "executable average bid is at least 90, 95, or 98 cents; lower states attempt a "
        "one-second-delayed full-depth sale.",
        "",
        "| Exit policy | Mean P&L | Bootstrap 95% CI | vs baseline | Profitable | Target hit | Settlement exit | Full-capital loss | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in all_rows:
        lines.append(
            f"| {row['exit_policy']} | {_money(float(row['mean_pnl']))} | "
            f"{_money(float(row['bootstrap_ci_low']))} to {_money(float(row['bootstrap_ci_high']))} | "
            f"{_money(float(row['mean_pnl_difference_vs_baseline']))} | "
            f"{_percent(float(row['profitable_rate']))} | "
            f"{_percent(float(row['target_hit_rate']))} | "
            f"{_percent(float(row['settlement_exit_rate']))} | "
            f"{_percent(float(row['full_capital_loss_rate']))} | "
            f"{_money(float(row['pnl_05_quantile']))} | {_money(float(row['worst_pnl']))} |"
        )
    lines.extend([
        "",
        "## Chronological stability",
        "",
        "| Exit policy | Earlier mean | Later mean |",
        "|---|---:|---:|",
    ])
    for policy in policy_names():
        earlier = next(row for row in summary if row["segment"] == "earlier_64_diagnostic" and row["exit_policy"] == policy)
        later = next(row for row in summary if row["segment"] == "later_32_diagnostic" and row["exit_policy"] == policy)
        lines.append(
            f"| {policy} | {_money(float(earlier['mean_pnl']))} | {_money(float(later['mean_pnl']))} |"
        )
    lines.extend([
        "",
        "These policies are matched counterfactuals on an already explored development sample. "
        "The comparison can diagnose exit mechanics, but selecting the highest row would still "
        "be post-selection. Do not open the existing holdout. A final policy needs prospective "
        "or explicitly reserved validation.",
    ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_zip", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--triggers-csv", type=Path, required=True)
    parser.add_argument("--outcomes-csv", type=Path, required=True)
    parser.add_argument("--series-csv", type=Path, required=True)
    parser.add_argument("--fee-changes-csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("analysis/kxbtc15m_h3_exit_policies"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    triggers = load_primary_triggers(args.triggers_csv)
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    trigger_by_ticker = {row["ticker"]: row for row in triggers}
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_h3_exit_") as temporary:
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
            raise SimulationError("outcome ticker set does not equal eligible development set")

        triggered_markets = [market for market in eligible if market.ticker in trigger_by_ticker]
        if len(triggered_markets) != EXPECTED_PRIMARY_TRIGGERS:
            raise ExitPolicyError("eligible trigger-market set mismatch")
        for number, market in enumerate(triggered_markets, start=1):
            trigger = trigger_by_ticker[market.ticker]
            snapshots = load_snapshots(market, args.repo_root)
            decision_time = parse_time(trigger["decision_time"])
            decision_index = first_index_at_or_after(snapshots, 0, decision_time)
            if decision_index is None or snapshots[decision_index].observed_at != decision_time:
                raise ExitPolicyError(f"{market.ticker}: exact trigger snapshot not found")
            rows.extend(simulate_exit_policies(
                snapshots=snapshots,
                decision_index=decision_index,
                close_time=market_close_utc(market.ticker),
                winning_side=outcomes[market.ticker],
                trigger=trigger,
            ))
            print(f"[{number:02d}/{EXPECTED_PRIMARY_TRIGGERS}] {market.ticker}")

    verify_baseline_reproduction(triggers, rows)
    summary = summarize(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_h3_exit_policy_scenarios.csv", rows)
    write_csv(args.output_dir / "kxbtc15m_h3_exit_policy_summary.csv", summary)
    report_path = args.output_dir / "KXBTC15M_H3_EXIT_POLICIES.md"
    report_path.write_text(markdown_report(summary), encoding="utf-8")

    print("KXBTC15M H3 matched exit-policy diagnostic: PASS")
    print(f"Frozen primary triggers: {EXPECTED_PRIMARY_TRIGGERS}")
    print(f"Matched exit policies: {len(policy_names())}")
    print(f"Scenario rows: {len(rows)}")
    print("Percentage targets: 25%, 50%, 75% of actual maximum net settlement profit")
    print("Conditional preclose executable-bid thresholds: 90c, 95c, 98c")
    print("Baseline reproduction: PASS")
    print("External BTC data used: no")
    print("Holdout read: False")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, ExitPolicyError, OSError, SimulationError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"H3 exit-policy error: {exc}") from exc
