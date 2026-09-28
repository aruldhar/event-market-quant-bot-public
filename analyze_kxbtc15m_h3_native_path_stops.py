#!/usr/bin/env python3
"""Describe native H3 drawdown paths and progressive stop feasibility.

This adaptive diagnostic uses only the frozen 96-market development partition.
It first reproduces the accepted 57-entry causal-native H3 baseline, then maps
every fully executable after-fee liquidation path until the protected target.
A small descriptive stop grid estimates false stops and delayed progressive
liquidation mechanics.  It selects no H3 v2 rule and never reads the opened
holdout partition.
"""

from __future__ import annotations

import argparse
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import (
    EXPECTED_ELIGIBLE_MARKETS,
    LATENCY_SECONDS,
    Snapshot,
    first_index_at_or_after,
    load_outcomes,
    sell_quantity,
    validate_fee_inputs,
    write_csv,
)
from analyze_kxbtc15m_h3_exit_policies import PRECLOSE_EXIT_SECONDS
from analyze_kxbtc15m_h3_frequency import (
    TARGET_FRACTION,
    _average_price,
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
from analyze_kxbtc15m_h3_time_windows import (
    _bootstrap,
    _mean,
    _money,
    _percent,
    _quantile,
)
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    parse_time,
    safe_extract_zip,
    select_development_manifests,
)


STOP_DOLLARS = tuple(Decimal(value) for value in ("2", "5", "10", "15", "20"))
POLICIES = (
    ("baseline_no_stop", "Baseline: no stop", "baseline", None),
    *((f"stop_{int(value)}usd", f"Progressive stop -${int(value)}", "loss", value)
      for value in STOP_DOLLARS),
    ("liquidity_guard", "Progressive exit on lost full depth", "liquidity", None),
)
FULL_LOSS_FRACTION = Decimal("0.90")


class NativePathStopError(RuntimeError):
    """Raised when the development-only diagnostic fails closed."""


@dataclass(frozen=True)
class ProgressiveExit:
    pnl: Decimal
    gross: Decimal
    fee: Decimal
    quantity_sold: Decimal
    remaining_quantity: Decimal
    attempts: int
    fill_events: int
    first_execution_time: datetime | None
    last_execution_time: datetime | None
    settled_residual: bool


def _policy_label(name: str) -> str:
    return next(label for key, label, _mode, _value in POLICIES if key == name)


def _best_bid(snapshot: Snapshot, side: str) -> Decimal | None:
    levels = snapshot.book.bid_levels(side)
    return levels[-1][0] if levels else None


def _path_category(minimum_pnl: float | None) -> str:
    if minimum_pnl is None:
        return "no_full_depth_mark"
    if minimum_pnl >= 0:
        return "never_negative"
    if minimum_pnl > -2:
        return "dip_0_to_2"
    if minimum_pnl > -5:
        return "dip_2_to_5"
    if minimum_pnl > -10:
        return "dip_5_to_10"
    if minimum_pnl > -20:
        return "dip_10_to_20"
    return "dip_20_or_more"


def build_executable_path(
    *,
    snapshots: Sequence[Snapshot],
    close_time: datetime,
    ticker: str,
    segment: str,
    entry_context: tuple[int, int, str, Decimal, Decimal, Any],
    baseline: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return native signal-time liquidation marks through the baseline exit."""

    _decision_index, entry_index, side, _midpoint, _ask, entry = entry_context
    entry_time = snapshots[entry_index].observed_at
    exit_time = parse_time(str(baseline["exit_execution_time"]))
    points: list[dict[str, Any]] = []
    full_marks: list[tuple[datetime, float]] = []
    prior_full_mark: float | None = None

    for index in range(entry_index + 1, len(snapshots)):
        snapshot = snapshots[index]
        if snapshot.observed_at > exit_time:
            break
        attempted = sell_quantity(snapshot.book.bid_levels(side), entry.quantity)
        full = attempted.quantity == entry.quantity
        pnl = attempted.sell_inflow - entry.buy_outflow if full else None
        average_bid = (
            _average_price(attempted) if attempted.quantity > 0 else None
        )
        pnl_float = float(pnl) if pnl is not None else None
        if pnl_float is not None:
            full_marks.append((snapshot.observed_at, pnl_float))
        points.append({
            "ticker": ticker,
            "diagnostic_segment": segment,
            "observation_time": snapshot.observed_at.isoformat(),
            "seconds_since_entry": (
                snapshot.observed_at - entry_time
            ).total_seconds(),
            "seconds_remaining": (close_time - snapshot.observed_at).total_seconds(),
            "side": side,
            "position_quantity": _decimal_text(entry.quantity),
            "position_best_bid": (
                "" if _best_bid(snapshot, side) is None
                else _decimal_text(_best_bid(snapshot, side) or Decimal("0"))
            ),
            "liquidatable_quantity": _decimal_text(attempted.quantity),
            "liquidatable_fraction": float(attempted.quantity / entry.quantity),
            "full_liquidation_available": full,
            "liquidation_average_bid": (
                "" if average_bid is None else _decimal_text(average_bid)
            ),
            "full_liquidation_gross": _decimal_text(attempted.gross) if full else "",
            "full_liquidation_fee": _decimal_text(attempted.fee) if full else "",
            "full_liquidation_pnl": "" if pnl is None else _decimal_text(pnl),
            "pnl_change_from_prior_full_mark": (
                "" if pnl_float is None or prior_full_mark is None
                else pnl_float - prior_full_mark
            ),
            "baseline_exit_time": exit_time.isoformat(),
            "baseline_pnl": baseline["pnl"],
            "holdout_read": False,
            "external_btc_data_used": False,
            "orders_placed": False,
        })
        if pnl_float is not None:
            prior_full_mark = pnl_float

    if not points:
        raise NativePathStopError(f"{ticker}: no native path observations after entry")

    minimum = min((value for _time, value in full_marks), default=None)
    minimum_time = next(
        (time for time, value in full_marks if value == minimum), None
    )
    peak = -math.inf
    max_peak_to_trough = 0.0
    nondecreasing = True
    prior: float | None = None
    for _time, value in full_marks:
        if prior is not None and value < prior - 1e-12:
            nondecreasing = False
        prior = value
        peak = max(peak, value)
        max_peak_to_trough = min(max_peak_to_trough, value - peak)

    underwater_seconds = 0.0
    for offset, point in enumerate(points):
        value = point["full_liquidation_pnl"]
        if value == "" or float(value) >= 0:
            continue
        start = parse_time(str(point["observation_time"]))
        stop = (
            parse_time(str(points[offset + 1]["observation_time"]))
            if offset + 1 < len(points) else exit_time
        )
        underwater_seconds += max(0.0, (stop - start).total_seconds())

    first_nonnegative_time = next(
        (time for time, value in full_marks if value >= 0), None
    )
    ever_negative = minimum is not None and minimum < 0
    row = {
        "ticker": ticker,
        "diagnostic_segment": segment,
        "side": side,
        "entry_time": entry_time.isoformat(),
        "baseline_exit_time": exit_time.isoformat(),
        "seconds_entry_to_target_exit": (exit_time - entry_time).total_seconds(),
        "baseline_pnl": baseline["pnl"],
        "path_observations": len(points),
        "full_depth_observations": len(full_marks),
        "full_depth_observation_fraction": len(full_marks) / len(points),
        "ever_full_depth_unavailable": len(full_marks) != len(points),
        "minimum_liquidatable_fraction": min(
            float(point["liquidatable_fraction"]) for point in points
        ),
        "minimum_full_liquidation_pnl": "" if minimum is None else minimum,
        "minimum_pnl_time": "" if minimum_time is None else minimum_time.isoformat(),
        "seconds_entry_to_minimum_pnl": (
            "" if minimum_time is None else (minimum_time - entry_time).total_seconds()
        ),
        "seconds_minimum_to_target_exit": (
            "" if minimum_time is None else (exit_time - minimum_time).total_seconds()
        ),
        "ever_negative_full_liquidation_pnl": ever_negative,
        "recovered_after_negative_pnl": ever_negative,
        "first_nonnegative_time": (
            "" if first_nonnegative_time is None else first_nonnegative_time.isoformat()
        ),
        "seconds_entry_to_first_nonnegative": (
            "" if first_nonnegative_time is None
            else (first_nonnegative_time - entry_time).total_seconds()
        ),
        "estimated_seconds_underwater": underwater_seconds,
        "full_mark_path_nondecreasing": nondecreasing,
        "maximum_peak_to_trough_pnl_drawdown": max_peak_to_trough,
        "path_category": _path_category(minimum),
        "holdout_read": False,
        "external_btc_data_used": False,
        "orders_placed": False,
    }
    return points, row


def progressive_liquidation(
    *,
    snapshots: Sequence[Snapshot],
    signal_index: int,
    close_time: datetime,
    side: str,
    quantity: Decimal,
    outflow: Decimal,
    winning_side: str,
) -> ProgressiveExit:
    """Repeatedly sweep available delayed bid depth until flat or settlement."""

    remaining = quantity
    total_gross = Decimal("0")
    total_fee = Decimal("0")
    attempts = 0
    fill_events = 0
    first_time: datetime | None = None
    last_time: datetime | None = None
    decision_index = signal_index

    while remaining > 0 and decision_index < len(snapshots):
        decision = snapshots[decision_index]
        execution_index = first_index_at_or_after(
            snapshots,
            decision_index + 1,
            decision.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if execution_index is None:
            break
        execution_snapshot = snapshots[execution_index]
        if execution_snapshot.observed_at >= close_time:
            break
        attempts += 1
        execution = sell_quantity(
            execution_snapshot.book.bid_levels(side), remaining
        )
        if execution.quantity > 0:
            if first_time is None:
                first_time = execution_snapshot.observed_at
            last_time = execution_snapshot.observed_at
            fill_events += 1
            remaining -= execution.quantity
            total_gross += execution.gross
            total_fee += execution.fee
        next_decision = execution_index + 1
        if next_decision >= len(snapshots):
            break
        decision_index = next_decision

    settlement_gross = remaining if side == winning_side else Decimal("0")
    pnl = total_gross - total_fee + settlement_gross - outflow
    return ProgressiveExit(
        pnl=pnl,
        gross=total_gross + settlement_gross,
        fee=total_fee,
        quantity_sold=quantity - remaining,
        remaining_quantity=remaining,
        attempts=attempts,
        fill_events=fill_events,
        first_execution_time=first_time,
        last_execution_time=last_time,
        settled_residual=remaining > 0,
    )


def simulate_stop_overlay(
    *,
    snapshots: Sequence[Snapshot],
    close_time: datetime,
    winning_side: str,
    baseline: Mapping[str, Any],
    entry_context: tuple[int, int, str, Decimal, Decimal, Any],
    policy: str,
    mode: str,
    threshold: Decimal | None,
) -> dict[str, Any]:
    """Interleave protected target priority with one progressive risk exit."""

    row = dict(baseline)
    row.update({
        "stop_policy": policy,
        "stop_display_policy": _policy_label(policy),
        "stop_mode": mode,
        "stop_threshold_dollars": "" if threshold is None else _decimal_text(threshold),
        "stop_signal": False,
        "stop_signal_time": "",
        "stop_signal_executable_pnl": "",
        "stop_signal_liquidatable_fraction": "",
        "progressive_exit_attempts": 0,
        "progressive_exit_fill_events": 0,
        "progressive_quantity_sold": "0",
        "progressive_remaining_at_settlement": "0",
        "progressive_fully_liquidated": False,
        "progressive_settlement_residual": False,
    })
    if mode == "baseline":
        return row

    _decision_index, entry_index, side, _midpoint, _ask, entry = entry_context
    target = (entry.quantity - entry.buy_outflow) * TARGET_FRACTION
    preclose = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
    index = entry_index + 1
    target_signals = 0
    target_rejections = 0
    while index < len(snapshots):
        observed = snapshots[index]
        if observed.observed_at >= preclose:
            break
        hypothetical = sell_quantity(observed.book.bid_levels(side), entry.quantity)
        full = hypothetical.quantity == entry.quantity
        observed_pnl = hypothetical.sell_inflow - entry.buy_outflow if full else None

        # The protected profit target always has priority at a shared snapshot.
        if full and observed_pnl is not None and observed_pnl >= target:
            target_signals += 1
            delayed_index = first_index_at_or_after(
                snapshots,
                index + 1,
                observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
            )
            if delayed_index is None or snapshots[delayed_index].observed_at >= preclose:
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

        stop_signal = (
            mode == "loss"
            and full
            and observed_pnl is not None
            and threshold is not None
            and observed_pnl <= -threshold
        ) or (mode == "liquidity" and not full)
        if not stop_signal:
            index += 1
            continue

        result = progressive_liquidation(
            snapshots=snapshots,
            signal_index=index,
            close_time=close_time,
            side=side,
            quantity=entry.quantity,
            outflow=entry.buy_outflow,
            winning_side=winning_side,
        )
        exit_time = result.last_execution_time or close_time
        if result.settled_residual:
            exit_time = close_time
        row.update({
            "stop_signal": True,
            "stop_signal_time": observed.observed_at.isoformat(),
            "stop_signal_executable_pnl": (
                "" if observed_pnl is None else _decimal_text(observed_pnl)
            ),
            "stop_signal_liquidatable_fraction": float(
                hypothetical.quantity / entry.quantity
            ),
            "target_filled": False,
            "target_signal_count": target_signals,
            "target_rejected_after_latency_count": target_rejections,
            "fallback_used": False,
            "exit_reason": (
                "progressive_risk_exit_with_settlement_residual"
                if result.settled_residual else "progressive_risk_exit"
            ),
            "exit_execution_time": exit_time.isoformat(),
            "exit_gross": _decimal_text(result.gross),
            "exit_fee": _decimal_text(result.fee),
            "exit_average_price": _decimal_text(result.gross / entry.quantity),
            "pnl": _decimal_text(result.pnl),
            "profitable": result.pnl > 0,
            "full_capital_loss": (
                result.pnl <= -FULL_LOSS_FRACTION * entry.buy_outflow
            ),
            "progressive_exit_attempts": result.attempts,
            "progressive_exit_fill_events": result.fill_events,
            "progressive_quantity_sold": _decimal_text(result.quantity_sold),
            "progressive_remaining_at_settlement": _decimal_text(
                result.remaining_quantity
            ),
            "progressive_fully_liquidated": result.remaining_quantity == 0,
            "progressive_settlement_residual": result.settled_residual,
            "exposure_seconds": (
                f"{(exit_time - snapshots[entry_index].observed_at).total_seconds():.6f}"
            ),
        })
        return row
    return row


def summarize_paths(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(rows) != EXPECTED_NATIVE_ENTRIES:
        raise NativePathStopError(
            f"expected {EXPECTED_NATIVE_ENTRIES} entry paths; found {len(rows)}"
        )
    minima = [
        float(row["minimum_full_liquidation_pnl"])
        for row in rows if row["minimum_full_liquidation_pnl"] != ""
    ]
    target_seconds = [float(row["seconds_entry_to_target_exit"]) for row in rows]
    underwater = [float(row["estimated_seconds_underwater"]) for row in rows]
    return {
        "entry_paths": len(rows),
        "never_negative_paths": sum(row["path_category"] == "never_negative" for row in rows),
        "ever_negative_paths": sum(bool(row["ever_negative_full_liquidation_pnl"]) for row in rows),
        "recovered_after_negative_paths": sum(bool(row["recovered_after_negative_pnl"]) for row in rows),
        "nondecreasing_paths": sum(bool(row["full_mark_path_nondecreasing"]) for row in rows),
        "paths_with_full_depth_gap": sum(bool(row["ever_full_depth_unavailable"]) for row in rows),
        "median_minimum_executable_pnl": statistics.median(minima),
        "p25_minimum_executable_pnl": _quantile(minima, 0.25),
        "p05_minimum_executable_pnl": _quantile(minima, 0.05),
        "worst_minimum_executable_pnl": min(minima),
        "median_seconds_to_target": statistics.median(target_seconds),
        "p95_seconds_to_target": _quantile(target_seconds, 0.95),
        "median_seconds_underwater": statistics.median(underwater),
        "p95_seconds_underwater": _quantile(underwater, 0.95),
        "minimum_liquidatable_fraction": min(
            float(row["minimum_liquidatable_fraction"]) for row in rows
        ),
        "holdout_read": False,
        "external_btc_data_used": False,
        "orders_placed": False,
    }


def summarize_stops(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment_name, segment_value in (
        ("all_96", None),
        ("earlier_64_diagnostic", "earlier_64"),
        ("later_32_diagnostic", "later_32"),
    ):
        source = list(rows) if segment_value is None else [
            row for row in rows if row["diagnostic_segment"] == segment_value
        ]
        baseline = {
            str(row["ticker"]): float(row["pnl"] or 0.0)
            for row in source if row["stop_policy"] == "baseline_no_stop"
        }
        for policy, label, mode, threshold in POLICIES:
            selected = [row for row in source if row["stop_policy"] == policy]
            completed = [row for row in selected if row["status"] == "completed"]
            pnl_market = [float(row["pnl"] or 0.0) for row in selected]
            pnl_filled = [float(row["pnl"]) for row in completed]
            differences = [
                float(row["pnl"] or 0.0) - baseline[str(row["ticker"])]
                for row in selected
            ]
            mean_market, ci_low, ci_high = _bootstrap(pnl_market)
            diff_mean, diff_low, diff_high = _bootstrap(differences)
            stopped = [row for row in completed if bool(row["stop_signal"])]
            output.append({
                "segment": segment_name,
                "stop_policy": policy,
                "display_policy": label,
                "stop_mode": mode,
                "stop_threshold_dollars": "" if threshold is None else float(threshold),
                "eligible_markets": len(selected),
                "entry_filled_markets": len(completed),
                "stop_signals": len(stopped),
                "stop_rate_per_filled_entry": len(stopped) / len(completed) if completed else math.nan,
                "mean_pnl_per_eligible_market": mean_market,
                "bootstrap_ci_low_per_eligible_market": ci_low,
                "bootstrap_ci_high_per_eligible_market": ci_high,
                "mean_paired_difference_vs_baseline": diff_mean,
                "paired_difference_ci_low": diff_low,
                "paired_difference_ci_high": diff_high,
                "mean_pnl_per_filled_entry": _mean(pnl_filled),
                "profitable_rate_per_filled_entry": _mean(
                    [bool(row["profitable"]) for row in completed]
                ),
                "baseline_winners_stopped": len(stopped),
                "progressive_full_liquidation_rate": _mean(
                    [bool(row["progressive_fully_liquidated"]) for row in stopped]
                ),
                "settlement_residual_rate": _mean(
                    [bool(row["progressive_settlement_residual"]) for row in stopped]
                ),
                "full_capital_loss_rate": _mean(
                    [bool(row["full_capital_loss"]) for row in completed]
                ),
                "pnl_05_quantile_per_filled_entry": _quantile(pnl_filled, 0.05),
                "worst_pnl_per_filled_entry": min(pnl_filled) if pnl_filled else math.nan,
                "holdout_read": False,
                "external_btc_data_used": False,
                "orders_placed": False,
            })
    return output


def verify_results(
    path_rows: Sequence[Mapping[str, Any]],
    stop_rows: Sequence[Mapping[str, Any]],
    summary: Sequence[Mapping[str, Any]],
) -> None:
    if len(path_rows) != EXPECTED_NATIVE_ENTRIES:
        raise NativePathStopError("native path count did not reproduce 57 entries")
    expected_stop_rows = EXPECTED_ELIGIBLE_MARKETS * len(POLICIES)
    if len(stop_rows) != expected_stop_rows:
        raise NativePathStopError(
            f"expected {expected_stop_rows} stop scenarios; found {len(stop_rows)}"
        )
    baseline = next(
        row for row in summary
        if row["segment"] == "all_96" and row["stop_policy"] == "baseline_no_stop"
    )
    if int(baseline["entry_filled_markets"]) != EXPECTED_NATIVE_ENTRIES:
        raise NativePathStopError("baseline did not reproduce 57 native entries")
    if abs(float(baseline["mean_pnl_per_eligible_market"]) - 2.32) > 0.01:
        raise NativePathStopError(
            "baseline mean P&L no longer reproduces the accepted native result"
        )
    baseline_completed = [
        row for row in stop_rows
        if row["stop_policy"] == "baseline_no_stop" and row["status"] == "completed"
    ]
    if any(not bool(row["target_filled"]) for row in baseline_completed):
        raise NativePathStopError("development baseline contains a non-target exit")
    if any(bool(row["full_capital_loss"]) for row in baseline_completed):
        raise NativePathStopError("development baseline contains a full-capital loss")


def markdown_report(
    path_summary: Mapping[str, Any],
    path_rows: Sequence[Mapping[str, Any]],
    stop_summary: Sequence[Mapping[str, Any]],
) -> str:
    all_rows = [row for row in stop_summary if row["segment"] == "all_96"]
    segment_lookup = {
        (str(row["segment"]), str(row["stop_policy"])): row for row in stop_summary
    }
    categories = [
        (category, sum(row["path_category"] == category for row in path_rows))
        for category in (
            "never_negative", "dip_0_to_2", "dip_2_to_5", "dip_5_to_10",
            "dip_10_to_20", "dip_20_or_more", "no_full_depth_mark",
        )
    ]
    lines = [
        "# KXBTC15M H3 causal-native path and stop-feasibility diagnostic",
        "",
        "**Adaptive development-only diagnostic; opened holdout prohibited and unread.**",
        "",
        "The accepted 57-entry native H3 development baseline is reproduced first. For each "
        "entry, every later causal response through the protected target is marked using a "
        "full-position sale through archived bid depth after fees. The stop rows are descriptive "
        "counterfactuals, not a selected H3 v2 policy.",
        "",
        "## Path structure of the 57 eventual target exits",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Entries | {path_summary['entry_paths']} |",
        f"| Ever showed negative full-exit P&L | {path_summary['ever_negative_paths']} "
        f"({_percent(path_summary['ever_negative_paths'] / path_summary['entry_paths'])}) |",
        f"| Recovered after negative P&L | {path_summary['recovered_after_negative_paths']} |",
        f"| Fully nondecreasing executable path | {path_summary['nondecreasing_paths']} |",
        f"| Lost full-position exit depth before target | {path_summary['paths_with_full_depth_gap']} |",
        f"| Median minimum executable P&L | {_money(path_summary['median_minimum_executable_pnl'])} |",
        f"| 25th-percentile minimum P&L | {_money(path_summary['p25_minimum_executable_pnl'])} |",
        f"| 5th-percentile minimum P&L | {_money(path_summary['p05_minimum_executable_pnl'])} |",
        f"| Worst pre-target minimum P&L | {_money(path_summary['worst_minimum_executable_pnl'])} |",
        f"| Median time to target exit | {path_summary['median_seconds_to_target']:.1f}s |",
        f"| 95th-percentile time to target exit | {path_summary['p95_seconds_to_target']:.1f}s |",
        f"| Median estimated time underwater | {path_summary['median_seconds_underwater']:.1f}s |",
        f"| Minimum observed liquidatable fraction | {_percent(path_summary['minimum_liquidatable_fraction'])} |",
        "",
        "| Pre-target path category | Entries |",
        "|---|---:|",
    ]
    lines.extend(f"| {name} | {count} |" for name, count in categories)
    lines.extend([
        "",
        "## Descriptive progressive-stop surface",
        "",
        "A loss stop signals only when the entire position is executable at or below its threshold. "
        "The liquidity guard signals when full-position depth first disappears. After a signal, "
        "execution waits one second, sells every available contract, and repeats delayed attempts "
        "until flat or settlement. The protected target has priority at the same observation.",
        "",
        "| Policy | Stops / 57 | Mean / market | 95% CI | vs baseline | Paired 95% CI | Earlier-64 diff | Later-32 diff | Profitable | Fully liquidated after stop | Residual settlement | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in all_rows:
        earlier = segment_lookup[("earlier_64_diagnostic", str(row["stop_policy"]))]
        later = segment_lookup[("later_32_diagnostic", str(row["stop_policy"]))]
        lines.append(
            f"| {row['display_policy']} | {row['stop_signals']} | "
            f"{_money(row['mean_pnl_per_eligible_market'])} | "
            f"{_money(row['bootstrap_ci_low_per_eligible_market'])} to "
            f"{_money(row['bootstrap_ci_high_per_eligible_market'])} | "
            f"{_money(row['mean_paired_difference_vs_baseline'])} | "
            f"{_money(row['paired_difference_ci_low'])} to "
            f"{_money(row['paired_difference_ci_high'])} | "
            f"{_money(earlier['mean_paired_difference_vs_baseline'])} | "
            f"{_money(later['mean_paired_difference_vs_baseline'])} | "
            f"{_percent(row['profitable_rate_per_filled_entry'])} | "
            f"{_percent(row['progressive_full_liquidation_rate'])} | "
            f"{_percent(row['settlement_residual_rate'])} | "
            f"{_money(row['pnl_05_quantile_per_filled_entry'])} | "
            f"{_money(row['worst_pnl_per_filled_entry'])} |"
        )
    lines.extend([
        "",
        "Every stop in this table acts only on development trades that ultimately reached the "
        "baseline protected target, so its stop count is also its observed false-stop count. "
        "This sample can reveal how much normal recovery a stop destroys, but its zero baseline "
        "losses cannot estimate how often the overlay saves a genuine loser.",
        "",
        "No rule is selected here. The opened 26-market holdout is neither read nor reused. Any "
        "H3 v2 threshold must be preregistered and developed on newly collected chronological "
        "markets, with a separate future holdout. No authentication, order, or external BTC feed "
        "is used.",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_zip", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--outcomes-csv", type=Path, required=True)
    parser.add_argument("--series-csv", type=Path, required=True)
    parser.add_argument("--fee-changes-csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analysis/kxbtc15m_h3_native_path_stops"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    path_points: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    stop_rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_h3_native_path_stops_") as temporary:
        audit_root = Path(temporary)
        safe_extract_zip(args.audit_zip, audit_root)
        manifests = select_development_manifests(audit_root)
        markets = [
            assess_market(index, manifest, audit_root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise NativePathStopError(
                f"expected {EXPECTED_ELIGIBLE_MARKETS} eligible development markets; "
                f"found {len(eligible)}"
            )
        if set(outcomes) != {market.ticker for market in eligible}:
            raise NativePathStopError(
                "development outcome ticker set does not equal eligible market set"
            )

        for number, market in enumerate(eligible, start=1):
            _legacy, snapshots = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            segment = "earlier_64" if market.index <= 64 else "later_32"
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
            baseline.update({
                "market_index": market.index,
                "diagnostic_segment": segment,
                "holdout_read": False,
                "external_btc_data_used": False,
                "orders_placed": False,
            })
            if baseline["status"] != "completed":
                for policy, _label, mode, threshold in POLICIES:
                    row = dict(baseline)
                    row.update({
                        "stop_policy": policy,
                        "stop_display_policy": _policy_label(policy),
                        "stop_mode": mode,
                        "stop_threshold_dollars": (
                            "" if threshold is None else _decimal_text(threshold)
                        ),
                        "stop_signal": False,
                    })
                    stop_rows.append(row)
                print(f"[{number:02d}/96] {market.ticker}")
                continue

            if context is None:
                raise NativePathStopError(f"{market.ticker}: completed row lacks entry context")
            points, path_row = build_executable_path(
                snapshots=snapshots,
                close_time=close,
                ticker=market.ticker,
                segment=segment,
                entry_context=context,
                baseline=baseline,
            )
            path_points.extend(points)
            path_rows.append(path_row)
            for policy, _label, mode, threshold in POLICIES:
                row = simulate_stop_overlay(
                    snapshots=snapshots,
                    close_time=close,
                    winning_side=outcomes[market.ticker],
                    baseline=baseline,
                    entry_context=context,
                    policy=policy,
                    mode=mode,
                    threshold=threshold,
                )
                row.update({
                    "market_index": market.index,
                    "diagnostic_segment": segment,
                    "baseline_pnl": baseline["pnl"],
                    "pnl_difference_vs_baseline": (
                        float(row["pnl"]) - float(baseline["pnl"])
                    ),
                    "holdout_read": False,
                    "external_btc_data_used": False,
                    "orders_placed": False,
                })
                stop_rows.append(row)
            print(f"[{number:02d}/96] {market.ticker}")

    path_summary = summarize_paths(path_rows)
    stop_summary = summarize_stops(stop_rows)
    verify_results(path_rows, stop_rows, stop_summary)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path_points_path = args.output_dir / "kxbtc15m_h3_native_path_points.csv"
    path_rows_path = args.output_dir / "kxbtc15m_h3_native_entry_paths.csv"
    stop_rows_path = args.output_dir / "kxbtc15m_h3_native_stop_scenarios.csv"
    stop_summary_path = args.output_dir / "kxbtc15m_h3_native_stop_summary.csv"
    report_path = args.output_dir / "KXBTC15M_H3_NATIVE_PATH_STOPS.md"
    write_csv(path_points_path, path_points)
    write_csv(path_rows_path, path_rows)
    write_csv(stop_rows_path, stop_rows)
    write_csv(stop_summary_path, stop_summary)
    report_path.write_text(
        markdown_report(path_summary, path_rows, stop_summary), encoding="utf-8"
    )

    print("KXBTC15M H3 causal-native path/stop diagnostic: PASS")
    print("Eligible development markets: 96")
    print("Native entries reproduced: 57")
    print(f"Native path points: {len(path_points)}")
    print(f"Descriptive stop policies: {len(POLICIES)}")
    print("H3 v2 rule selected: no")
    print("Holdout read: False")
    print("Authentication used: no")
    print("Orders placed: 0")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, NativePathStopError, OSError, ValueError) as exc:
        raise SystemExit(f"KXBTC15M H3 native path/stop error: {exc}") from exc
