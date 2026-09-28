#!/usr/bin/env python3
"""Evaluate causal multihorizon executable-P&L velocity stops for H3.

All 122 markets are already-opened adaptive development evidence.  The command
reproduces the original H3 baseline and opened holdout rows before evaluating
5-, 10-, 20-, and 30-second rolling adverse velocities.  Each velocity rule is
tested both with the original ten-second fallback and with the simple 90-second
no-target risk benchmark.  No rule is selected and no hybrid beyond that fixed
fallback pairing is searched.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
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
from analyze_kxbtc15m_h3_exit_policies import PRECLOSE_EXIT_SECONDS
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
from analyze_kxbtc15m_h3_native_path_stops import progressive_liquidation
from analyze_kxbtc15m_h3_stop_candidates import (
    EXPECTED_HOLDOUT_ENTRIES,
    EXPECTED_HOLDOUT_TOTAL_PNL,
    EXPECTED_TOTAL_ENTRIES,
    EXPECTED_TOTAL_MARKETS,
    FULL_LOSS_FRACTION,
    MATERIAL_LOSER_SAVINGS,
    MAX_WINNER_COST_SHARE,
    _market_partition,
    load_opened_baseline,
    load_opened_holdout_outcomes,
    select_opened_manifests,
    verify_opened_baseline_row,
)
from analyze_kxbtc15m_h3_time_windows import _bootstrap, _mean, _money, _percent, _quantile
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    parse_time,
    safe_extract_zip,
    select_development_manifests,
)


LOOKBACK_SECONDS = (5, 10, 20, 30)
DROP_RATES = (Decimal("0.50"), Decimal("0.75"), Decimal("1.00"))
LOSS_FLOORS = (Decimal("10"), Decimal("15"))
BASELINE_KEY = "baseline_10s"
FALLBACK_90_KEY = "fallback_90s"


class VelocityStopError(RuntimeError):
    """Raised when a velocity diagnostic invariant fails closed."""


@dataclass(frozen=True)
class ExecutableMark:
    observed_at: datetime
    pnl: Decimal


@dataclass(frozen=True)
class VelocityMeasure:
    reference_time: datetime
    reference_pnl: Decimal
    elapsed_seconds: float
    drop_dollars: Decimal
    drop_rate_dollars_per_second: Decimal


@dataclass(frozen=True)
class VelocityPolicy:
    key: str
    label: str
    family: str
    lookback_seconds: int | None = None
    drop_rate: Decimal | None = None
    loss_floor: Decimal | None = None
    fallback_90_seconds: bool = False


def _rate_key(rate: Decimal) -> str:
    return _decimal_text(rate).replace(".", "p")


def _build_policies() -> tuple[VelocityPolicy, ...]:
    rows = [
        VelocityPolicy(BASELINE_KEY, "Original H3: 10s fallback", "baseline"),
        VelocityPolicy(
            FALLBACK_90_KEY, "Simple no-target cash exit at 90s", "fallback",
            fallback_90_seconds=True,
        ),
    ]
    for fallback in (False, True):
        suffix = "plus90" if fallback else "only"
        for lookback in LOOKBACK_SECONDS:
            for rate in DROP_RATES:
                for floor in LOSS_FLOORS:
                    key = (
                        f"velocity_{lookback}s_{_rate_key(rate)}ps_"
                        f"floor{int(floor)}_{suffix}"
                    )
                    label = (
                        f"{lookback}s >= ${float(rate):.2f}/s, P&L <= -${int(floor)}"
                        + (" + 90s fallback" if fallback else "")
                    )
                    rows.append(VelocityPolicy(
                        key=key,
                        label=label,
                        family="velocity_plus_90" if fallback else "velocity_only",
                        lookback_seconds=lookback,
                        drop_rate=rate,
                        loss_floor=floor,
                        fallback_90_seconds=fallback,
                    ))
    return tuple(rows)


POLICIES = _build_policies()


def latest_reference_mark(
    marks: Sequence[ExecutableMark], boundary: datetime
) -> ExecutableMark | None:
    """Return the latest causal full-depth mark at or before the boundary."""

    for mark in reversed(marks):
        if mark.observed_at <= boundary:
            return mark
    return None


def calculate_velocity(
    *, marks: Sequence[ExecutableMark], current_time: datetime,
    current_pnl: Decimal, lookback_seconds: int,
) -> VelocityMeasure | None:
    reference = latest_reference_mark(
        marks, current_time - timedelta(seconds=lookback_seconds)
    )
    if reference is None:
        return None
    elapsed = (current_time - reference.observed_at).total_seconds()
    if elapsed < lookback_seconds or elapsed <= 0:
        return None
    drop = reference.pnl - current_pnl
    return VelocityMeasure(
        reference_time=reference.observed_at,
        reference_pnl=reference.pnl,
        elapsed_seconds=elapsed,
        drop_dollars=drop,
        drop_rate_dollars_per_second=drop / Decimal(str(elapsed)),
    )


def velocity_trigger(
    policy: VelocityPolicy,
    *, current_pnl: Decimal | None, measure: VelocityMeasure | None,
) -> bool:
    if policy.lookback_seconds is None:
        return False
    if current_pnl is None or measure is None:
        return False
    assert policy.loss_floor is not None and policy.drop_rate is not None
    return (
        current_pnl <= -policy.loss_floor
        and measure.drop_rate_dollars_per_second >= policy.drop_rate
    )


def _candidate_fields(policy: VelocityPolicy) -> dict[str, Any]:
    return {
        "velocity_policy": policy.key,
        "velocity_display_policy": policy.label,
        "velocity_family": policy.family,
        "velocity_lookback_seconds": (
            "" if policy.lookback_seconds is None else policy.lookback_seconds
        ),
        "velocity_threshold_dollars_per_second": (
            "" if policy.drop_rate is None else _decimal_text(policy.drop_rate)
        ),
        "velocity_loss_floor_dollars": (
            "" if policy.loss_floor is None else _decimal_text(policy.loss_floor)
        ),
        "candidate_90s_fallback_enabled": policy.fallback_90_seconds,
        "candidate_risk_signal": False,
        "candidate_signal_kind": "",
        "candidate_signal_time": "",
        "candidate_signal_seconds_remaining": "",
        "candidate_signal_executable_pnl": "",
        "candidate_velocity_reference_time": "",
        "candidate_velocity_reference_pnl": "",
        "candidate_velocity_elapsed_seconds": "",
        "candidate_velocity_drop_dollars": "",
        "candidate_velocity_rate_dollars_per_second": "",
        "candidate_progressive_attempts": 0,
        "candidate_progressive_fill_events": 0,
        "candidate_quantity_sold": "0",
        "candidate_remaining_at_settlement": "0",
        "candidate_fully_liquidated": False,
        "candidate_settlement_residual": False,
    }


def simulate_velocity_overlay(
    *, snapshots: Sequence[Snapshot], close_time: datetime, winning_side: str,
    baseline: Mapping[str, Any],
    entry_context: tuple[int, int, str, Decimal, Decimal, Any],
    policy: VelocityPolicy,
) -> dict[str, Any]:
    """Interleave protected target priority with velocity and optional 90s exit."""

    row = dict(baseline)
    row.update(_candidate_fields(policy))
    if policy.family == "baseline":
        return row

    _decision_index, entry_index, side, _midpoint, _ask, entry = entry_context
    target = (entry.quantity - entry.buy_outflow) * TARGET_FRACTION
    preclose = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
    marks: list[ExecutableMark] = []
    entry_mark = sell_quantity(snapshots[entry_index].book.bid_levels(side), entry.quantity)
    if entry_mark.quantity == entry.quantity:
        marks.append(ExecutableMark(
            snapshots[entry_index].observed_at,
            entry_mark.sell_inflow - entry.buy_outflow,
        ))
    index = entry_index + 1
    target_signals = 0
    target_rejections = 0

    while index < len(snapshots):
        observed = snapshots[index]
        if observed.observed_at >= preclose:
            break
        attempted = sell_quantity(observed.book.bid_levels(side), entry.quantity)
        full = attempted.quantity == entry.quantity
        current_pnl = attempted.sell_inflow - entry.buy_outflow if full else None
        measure = None
        if full and current_pnl is not None and policy.lookback_seconds is not None:
            measure = calculate_velocity(
                marks=marks,
                current_time=observed.observed_at,
                current_pnl=current_pnl,
                lookback_seconds=policy.lookback_seconds,
            )
        if full and current_pnl is not None:
            marks.append(ExecutableMark(observed.observed_at, current_pnl))

        # Frozen protected target retains priority on a shared observation.
        if full and current_pnl is not None and current_pnl >= target:
            target_signals += 1
            delayed_index = first_index_at_or_after(
                snapshots,
                index + 1,
                observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
            )
            if delayed_index is None or snapshots[delayed_index].observed_at >= preclose:
                break
            delayed_snapshot = snapshots[delayed_index]
            executed = sell_quantity(
                delayed_snapshot.book.bid_levels(side), entry.quantity
            )
            if (
                executed.quantity == entry.quantity
                and executed.sell_inflow - entry.buy_outflow >= target
            ):
                return row
            target_rejections += 1
            # The delayed execution response is now causal information. Preserve
            # its full-depth mark for later rolling-velocity decisions.
            if executed.quantity == entry.quantity:
                marks.append(ExecutableMark(
                    delayed_snapshot.observed_at,
                    executed.sell_inflow - entry.buy_outflow,
                ))
            index = delayed_index + 1
            continue

        is_velocity = velocity_trigger(
            policy, current_pnl=current_pnl, measure=measure
        )
        seconds_remaining = (close_time - observed.observed_at).total_seconds()
        is_fallback = policy.fallback_90_seconds and seconds_remaining <= 90
        if not is_velocity and not is_fallback:
            index += 1
            continue

        signal_kind = "velocity" if is_velocity else "fallback_90s"
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
            "candidate_risk_signal": True,
            "candidate_signal_kind": signal_kind,
            "candidate_signal_time": observed.observed_at.isoformat(),
            "candidate_signal_seconds_remaining": seconds_remaining,
            "candidate_signal_executable_pnl": (
                "" if current_pnl is None else _decimal_text(current_pnl)
            ),
            "candidate_velocity_reference_time": (
                "" if measure is None else measure.reference_time.isoformat()
            ),
            "candidate_velocity_reference_pnl": (
                "" if measure is None else _decimal_text(measure.reference_pnl)
            ),
            "candidate_velocity_elapsed_seconds": (
                "" if measure is None else measure.elapsed_seconds
            ),
            "candidate_velocity_drop_dollars": (
                "" if measure is None else _decimal_text(measure.drop_dollars)
            ),
            "candidate_velocity_rate_dollars_per_second": (
                "" if measure is None
                else _decimal_text(measure.drop_rate_dollars_per_second)
            ),
            "target_filled": False,
            "target_signal_count": target_signals,
            "target_rejected_after_latency_count": target_rejections,
            "fallback_used": signal_kind == "fallback_90s",
            "exit_reason": (
                f"candidate_{signal_kind}_exit_with_settlement_residual"
                if result.settled_residual else f"candidate_{signal_kind}_exit"
            ),
            "exit_execution_time": exit_time.isoformat(),
            "exit_gross": _decimal_text(result.gross),
            "exit_fee": _decimal_text(result.fee),
            "exit_average_price": _decimal_text(result.gross / entry.quantity),
            "pnl": _decimal_text(result.pnl),
            "profitable": result.pnl > 0,
            "full_capital_loss": result.pnl <= -FULL_LOSS_FRACTION * entry.buy_outflow,
            "candidate_progressive_attempts": result.attempts,
            "candidate_progressive_fill_events": result.fill_events,
            "candidate_quantity_sold": _decimal_text(result.quantity_sold),
            "candidate_remaining_at_settlement": _decimal_text(result.remaining_quantity),
            "candidate_fully_liquidated": result.remaining_quantity == 0,
            "candidate_settlement_residual": result.settled_residual,
            "exposure_seconds": (
                f"{(exit_time - snapshots[entry_index].observed_at).total_seconds():.6f}"
            ),
        })
        return row
    return row


def _phase(seconds_since_entry: float) -> str:
    if seconds_since_entry < 30:
        return "entry_age_0_30s"
    if seconds_since_entry < 60:
        return "entry_age_30_60s"
    return "entry_age_60s_plus"


def build_velocity_path_points(
    *, snapshots: Sequence[Snapshot], close_time: datetime,
    entry_context: tuple[int, int, str, Decimal, Decimal, Any],
    baseline: Mapping[str, Any], partition: str, segment: str,
) -> list[dict[str, Any]]:
    """Materialize all causal multihorizon executable velocities before baseline exit."""

    _decision_index, entry_index, side, _midpoint, _ask, entry = entry_context
    entry_time = snapshots[entry_index].observed_at
    baseline_exit = parse_time(str(baseline["exit_execution_time"]))
    stop_time = min(
        baseline_exit, close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
    )
    marks: list[ExecutableMark] = []
    initial = sell_quantity(snapshots[entry_index].book.bid_levels(side), entry.quantity)
    if initial.quantity == entry.quantity:
        marks.append(ExecutableMark(entry_time, initial.sell_inflow - entry.buy_outflow))
    output: list[dict[str, Any]] = []
    for index in range(entry_index + 1, len(snapshots)):
        snapshot = snapshots[index]
        if snapshot.observed_at >= stop_time:
            break
        execution = sell_quantity(snapshot.book.bid_levels(side), entry.quantity)
        if execution.quantity != entry.quantity:
            continue
        current_pnl = execution.sell_inflow - entry.buy_outflow
        age = (snapshot.observed_at - entry_time).total_seconds()
        for lookback in LOOKBACK_SECONDS:
            measure = calculate_velocity(
                marks=marks,
                current_time=snapshot.observed_at,
                current_pnl=current_pnl,
                lookback_seconds=lookback,
            )
            if measure is None:
                continue
            output.append({
                "ticker": baseline["ticker"],
                "evidence_partition": partition,
                "diagnostic_segment": segment,
                "baseline_profitable": bool(baseline["profitable"]),
                "baseline_full_capital_loss": bool(baseline["full_capital_loss"]),
                "observation_time": snapshot.observed_at.isoformat(),
                "seconds_since_entry": age,
                "seconds_remaining": (close_time - snapshot.observed_at).total_seconds(),
                "entry_age_phase": _phase(age),
                "lookback_seconds": lookback,
                "reference_time": measure.reference_time.isoformat(),
                "reference_pnl": _decimal_text(measure.reference_pnl),
                "current_executable_pnl": _decimal_text(current_pnl),
                "actual_elapsed_seconds": measure.elapsed_seconds,
                "drop_dollars": _decimal_text(measure.drop_dollars),
                "drop_rate_dollars_per_second": _decimal_text(
                    measure.drop_rate_dollars_per_second
                ),
                "adaptive_development_only": True,
                "external_btc_data_used": False,
                "authentication_used": False,
                "orders_placed": 0,
            })
        marks.append(ExecutableMark(snapshot.observed_at, current_pnl))
    return output


def summarize_velocity_paths(
    points: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lookback in LOOKBACK_SECONDS:
        for phase in ("entry_age_0_30s", "entry_age_30_60s", "entry_age_60s_plus"):
            selected = [
                point for point in points
                if int(point["lookback_seconds"]) == lookback
                and point["entry_age_phase"] == phase
            ]
            per_market: dict[str, float] = {}
            profitable: dict[str, bool] = {}
            for point in selected:
                ticker = str(point["ticker"])
                rate = float(point["drop_rate_dollars_per_second"])
                per_market[ticker] = max(rate, per_market.get(ticker, -math.inf))
                profitable[ticker] = bool(point["baseline_profitable"])
            winner_values = [
                value for ticker, value in per_market.items() if profitable[ticker]
            ]
            loser_values = [
                value for ticker, value in per_market.items() if not profitable[ticker]
            ]
            loser_max = max(loser_values) if loser_values else math.nan
            rows.append({
                "lookback_seconds": lookback,
                "entry_age_phase": phase,
                "winner_markets": len(winner_values),
                "loser_markets": len(loser_values),
                "winner_median_max_adverse_rate": (
                    _quantile(winner_values, 0.50) if winner_values else math.nan
                ),
                "winner_p95_max_adverse_rate": (
                    _quantile(winner_values, 0.95) if winner_values else math.nan
                ),
                "winner_max_adverse_rate": max(winner_values) if winner_values else math.nan,
                "loser_max_adverse_rate": loser_max,
                "winners_at_or_above_loser_rate": sum(
                    value >= loser_max for value in winner_values
                ) if loser_values else 0,
                "adaptive_development_only": True,
            })
    return rows


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
    raise VelocityStopError(f"unknown summary group: {group}")


def summarize_policies(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for group in (
        "development_96", "opened_26", "combined_122",
        "earlier_64_diagnostic", "later_32_diagnostic",
    ):
        source = _group_rows(rows, group)
        by_key = {
            policy.key: [row for row in source if row["velocity_policy"] == policy.key]
            for policy in POLICIES
        }
        baseline = {
            str(row["ticker"]): float(row["pnl"] or 0.0)
            for row in by_key[BASELINE_KEY]
        }
        fallback = {
            str(row["ticker"]): float(row["pnl"] or 0.0)
            for row in by_key[FALLBACK_90_KEY]
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
            comparator = fallback if policy.fallback_90_seconds else baseline
            comparator_differences = [
                float(row["pnl"] or 0.0) - comparator[str(row["ticker"])]
                for row in selected
            ]
            loser_rows = [row for row in completed if row["ticker"] in losers]
            winner_rows = [row for row in completed if row["ticker"] in winners]
            loser_savings = sum(
                float(row["pnl"]) - baseline[str(row["ticker"])] for row in loser_rows
            )
            winner_cost = sum(
                max(0.0, baseline[str(row["ticker"])] - float(row["pnl"]))
                for row in winner_rows
            )
            signals = [row for row in completed if bool(row["candidate_risk_signal"])]
            velocity_signals = [
                row for row in signals if row["candidate_signal_kind"] == "velocity"
            ]
            velocity_loser_signals = sum(
                row["ticker"] in losers for row in velocity_signals
            )
            fully_liquidated = all(
                bool(row["candidate_fully_liquidated"]) for row in signals
            ) if signals else False
            full_losses = sum(bool(row["full_capital_loss"]) for row in completed)
            cost_share = winner_cost / loser_savings if loser_savings > 0 else math.inf
            basic = (
                group == "combined_122"
                and policy.lookback_seconds is not None
                and velocity_loser_signals >= 1
                and loser_savings >= MATERIAL_LOSER_SAVINGS
                and sum(differences) > 0
                and cost_share <= MAX_WINNER_COST_SHARE
                and full_losses == 0
                and fully_liquidated
            )
            mean_market, ci_low, ci_high = _bootstrap(pnl_market)
            diff_mean, diff_low, diff_high = _bootstrap(differences)
            output.append({
                "group": group,
                "velocity_policy": policy.key,
                "display_policy": policy.label,
                "velocity_family": policy.family,
                "lookback_seconds": (
                    "" if policy.lookback_seconds is None else policy.lookback_seconds
                ),
                "drop_rate_threshold": (
                    "" if policy.drop_rate is None else float(policy.drop_rate)
                ),
                "loss_floor_dollars": (
                    "" if policy.loss_floor is None else float(policy.loss_floor)
                ),
                "fallback_90_seconds": policy.fallback_90_seconds,
                "eligible_markets": len(selected),
                "entry_filled_markets": len(completed),
                "baseline_winning_entries": len(winners),
                "baseline_losing_entries": len(losers),
                "risk_exit_signals": len(signals),
                "velocity_exit_signals": len(velocity_signals),
                "velocity_stopped_winners": sum(row["ticker"] in winners for row in velocity_signals),
                "velocity_stopped_losers": velocity_loser_signals,
                "fallback_90_exit_signals": sum(
                    row["candidate_signal_kind"] == "fallback_90s" for row in signals
                ),
                "total_pnl": sum(pnl_market),
                "mean_pnl_per_eligible_market": mean_market,
                "bootstrap_ci_low_per_eligible_market": ci_low,
                "bootstrap_ci_high_per_eligible_market": ci_high,
                "total_difference_vs_original_baseline": sum(differences),
                "mean_difference_vs_original_baseline": diff_mean,
                "paired_difference_ci_low": diff_low,
                "paired_difference_ci_high": diff_high,
                "total_increment_vs_family_comparator": sum(comparator_differences),
                "mean_pnl_per_filled_entry": _mean(pnl_filled),
                "profitable_rate_per_filled_entry": _mean(
                    [bool(row["profitable"]) for row in completed]
                ),
                "loser_savings_vs_original_baseline": loser_savings,
                "winner_gross_opportunity_cost": winner_cost,
                "winner_cost_share_of_loser_savings": cost_share,
                "full_capital_losses": full_losses,
                "all_signaled_positions_fully_liquidated": fully_liquidated,
                "settlement_residuals": sum(
                    bool(row["candidate_settlement_residual"]) for row in signals
                ),
                "pnl_05_quantile_per_filled_entry": _quantile(pnl_filled, 0.05),
                "worst_pnl_per_filled_entry": min(pnl_filled) if pnl_filled else math.nan,
                "basic_velocity_screen": basic,
                "passing_adjacent_neighbors": 0,
                "robust_velocity_screen": False,
                "adaptive_development_only": True,
            })
    mark_neighbor_robustness(output)
    return output


def _adjacent(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    if bool(left["fallback_90_seconds"]) != bool(right["fallback_90_seconds"]):
        return False
    values = (
        (LOOKBACK_SECONDS, int(left["lookback_seconds"]), int(right["lookback_seconds"])),
        (tuple(float(value) for value in DROP_RATES), float(left["drop_rate_threshold"]), float(right["drop_rate_threshold"])),
        (tuple(float(value) for value in LOSS_FLOORS), float(left["loss_floor_dollars"]), float(right["loss_floor_dollars"])),
    )
    differing = 0
    for ordered, a, b in values:
        if a == b:
            continue
        differing += 1
        if abs(ordered.index(a) - ordered.index(b)) != 1:
            return False
    return differing == 1


def mark_neighbor_robustness(summaries: Sequence[dict[str, Any]]) -> None:
    combined = [
        row for row in summaries
        if row["group"] == "combined_122" and row["lookback_seconds"] != ""
    ]
    passing = [row for row in combined if bool(row["basic_velocity_screen"])]
    for row in combined:
        count = sum(
            other["velocity_policy"] != row["velocity_policy"] and _adjacent(row, other)
            for other in passing
        )
        row["passing_adjacent_neighbors"] = count
        row["robust_velocity_screen"] = bool(row["basic_velocity_screen"]) and count >= 1


def verify_results(
    rows: Sequence[Mapping[str, Any]], summaries: Sequence[Mapping[str, Any]]
) -> None:
    expected = EXPECTED_TOTAL_MARKETS * len(POLICIES)
    if len(rows) != expected:
        raise VelocityStopError(f"expected {expected} policy rows; found {len(rows)}")
    lookup = {(row["group"], row["velocity_policy"]): row for row in summaries}
    development = lookup[("development_96", BASELINE_KEY)]
    opened = lookup[("opened_26", BASELINE_KEY)]
    combined = lookup[("combined_122", BASELINE_KEY)]
    if int(development["entry_filled_markets"]) != EXPECTED_NATIVE_ENTRIES:
        raise VelocityStopError("development baseline did not reproduce 57 entries")
    if abs(float(development["mean_pnl_per_eligible_market"]) - 2.32) > 0.01:
        raise VelocityStopError("development baseline mean no longer reproduces H3")
    if int(opened["entry_filled_markets"]) != EXPECTED_HOLDOUT_ENTRIES:
        raise VelocityStopError("opened baseline did not reproduce 14 entries")
    if abs(float(opened["total_pnl"]) - EXPECTED_HOLDOUT_TOTAL_PNL) > 0.02:
        raise VelocityStopError("opened baseline did not reproduce -$46.55")
    if int(opened["full_capital_losses"]) != 1:
        raise VelocityStopError("opened baseline did not reproduce one full loss")
    if int(combined["entry_filled_markets"]) != EXPECTED_TOTAL_ENTRIES:
        raise VelocityStopError("combined baseline did not reproduce 71 entries")


def _optional_money(value: Any) -> str:
    if value is None or str(value) == "":
        return "n/a"
    return _money(value)


def _rate(value: Any) -> str:
    if value is None or str(value) == "" or math.isnan(float(value)):
        return "n/a"
    return f"${float(value):.2f}/s"


def markdown_report(
    scenario_rows: Sequence[Mapping[str, Any]],
    summaries: Sequence[Mapping[str, Any]],
    path_summary: Sequence[Mapping[str, Any]],
) -> str:
    combined = [row for row in summaries if row["group"] == "combined_122"]
    comparators = [row for row in combined if row["lookback_seconds"] == ""]
    candidates = [row for row in combined if row["lookback_seconds"] != ""]
    robust = [row for row in candidates if bool(row["robust_velocity_screen"])]
    baseline_losses = {
        str(row["ticker"]): float(row["pnl"])
        for row in scenario_rows
        if row["velocity_policy"] == BASELINE_KEY
        and row["status"] == "completed" and float(row["pnl"]) < 0
    }
    lines = [
        "# KXBTC15M H3 causal multihorizon velocity-stop diagnostic",
        "",
        "**Adaptive hypothesis-generation test; all 122 markets are development evidence.**",
        "",
        "Executable full-position P&L velocity is evaluated continuously using only causally "
        "received native responses. Each current mark uses the latest prior fully executable "
        "mark at or before the 5-, 10-, 20-, or 30-second lookback boundary and divides by the "
        "actual elapsed time. The protected target has priority, every risk exit waits one "
        "second, and actual archived depth and fees determine liquidation.",
        "",
        "## Fixed comparators",
        "",
        "| Comparator | Combined P&L | vs original | Full losses | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in comparators:
        lines.append(
            f"| {row['display_policy']} | {_money(row['total_pnl'])} | "
            f"{_money(row['total_difference_vs_original_baseline'])} | "
            f"{row['full_capital_losses']} | "
            f"{_money(row['pnl_05_quantile_per_filled_entry'])} | "
            f"{_money(row['worst_pnl_per_filled_entry'])} |"
        )
    lines.extend([
        "",
        "## Maximum adverse velocity by horizon and entry age",
        "",
        "| Lookback | Entry-age phase | Winner markets | Winner median max | Winner 95% max | Winner maximum | Loser maximum | Winners >= loser |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ])
    for row in path_summary:
        lines.append(
            f"| {row['lookback_seconds']}s | {row['entry_age_phase']} | "
            f"{row['winner_markets']} | {_rate(row['winner_median_max_adverse_rate'])} | "
            f"{_rate(row['winner_p95_max_adverse_rate'])} | "
            f"{_rate(row['winner_max_adverse_rate'])} | "
            f"{_rate(row['loser_max_adverse_rate'])} | "
            f"{row['winners_at_or_above_loser_rate']} |"
        )
    lines.extend([
        "",
        "## Velocity policy surface",
        "",
        "`vs comparator` means versus original H3 for velocity-only rows and versus the simple "
        "90-second exit for velocity-plus-90 rows.",
        "",
        "| Mode | Window | Rate | Loss floor | Velocity stops W/L | 90s exits | Combined P&L | vs original | vs comparator | Loser saved | Winner cost | Full losses | Basic | Passing neighbors | Robust |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in candidates:
        lines.append(
            f"| {row['velocity_family']} | {row['lookback_seconds']}s | "
            f"{_rate(row['drop_rate_threshold'])} | "
            f"-{_money(row['loss_floor_dollars'])} | "
            f"{row['velocity_stopped_winners']}/{row['velocity_stopped_losers']} | "
            f"{row['fallback_90_exit_signals']} | {_money(row['total_pnl'])} | "
            f"{_money(row['total_difference_vs_original_baseline'])} | "
            f"{_money(row['total_increment_vs_family_comparator'])} | "
            f"{_money(row['loser_savings_vs_original_baseline'])} | "
            f"{_money(row['winner_gross_opportunity_cost'])} | "
            f"{row['full_capital_losses']} | {row['basic_velocity_screen']} | "
            f"{row['passing_adjacent_neighbors']} | {row['robust_velocity_screen']} |"
        )
    lines.extend([
        "",
        "## Known-loss execution for the best fitted velocity rows",
        "",
        "| Policy | Signal kind | Signal sec left | Signal P&L | Measured rate | Result P&L | Saved |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    top_keys = {
        row["velocity_policy"] for row in sorted(
            candidates,
            key=lambda item: float(item["total_difference_vs_original_baseline"]),
            reverse=True,
        )[:12]
    }
    for row in scenario_rows:
        if row["velocity_policy"] not in top_keys or row["ticker"] not in baseline_losses:
            continue
        lines.append(
            f"| {row['velocity_display_policy']} | "
            f"{row['candidate_signal_kind'] or 'none'} | "
            f"{row['candidate_signal_seconds_remaining'] or 'n/a'} | "
            f"{_optional_money(row['candidate_signal_executable_pnl'])} | "
            f"{_rate(row['candidate_velocity_rate_dollars_per_second'])} | "
            f"{_money(row['pnl'])} | "
            f"{_money(float(row['pnl']) - baseline_losses[str(row['ticker'])])} |"
        )
    lines.extend([
        "",
        "## Robustness screen",
        "",
        "A basic velocity row must stop the known loser through velocity rather than merely the "
        "90-second fallback, save at least $25, improve combined P&L, limit gross winner cost "
        "to 50% of loser savings, create zero full-capital losses, and fully liquidate every "
        "signal. A robust row must also have at least one passing adjacent lookback, rate, or "
        "loss-floor neighbor under the same fallback mode.",
        "",
        "Robust velocity candidates: "
        + (", ".join(f"`{row['velocity_policy']}`" for row in robust) if robust else "none"),
        "",
        "No row is selected here. The best observed row is adaptively biased, and there is only "
        "one baseline loser. Robust regions may motivate one staged or multiscale H3 v2 rule; "
        "any final rule requires a newly collected chronological confirmation sample. No "
        "external BTC data, authentication, or order placement is used.",
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
        default=Path("analysis/kxbtc15m_h3_velocity_stops"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    development_outcomes = load_outcomes(args.development_outcomes_csv)
    opened_outcomes = load_opened_holdout_outcomes(args.opened_holdout_outcomes_csv)
    opened_baseline = load_opened_baseline(args.opened_holdout_scenarios_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    scenario_rows: list[dict[str, Any]] = []
    path_points: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_h3_velocity_stops_") as temporary:
        audit_root = Path(temporary)
        safe_extract_zip(args.audit_zip, audit_root)
        dev_all = [
            assess_market(index, manifest, audit_root)
            for index, manifest in enumerate(
                select_development_manifests(audit_root), start=1
            )
        ]
        dev_markets = [market for market in dev_all if market.eligible]
        holdout_markets = [
            assess_market(index, manifest, audit_root)
            for index, manifest in enumerate(
                select_opened_manifests(audit_root), start=101
            )
        ]
        if len(dev_markets) != 96 or len(holdout_markets) != 26:
            raise VelocityStopError("expected 96 eligible development plus 26 opened markets")
        if any(not market.eligible for market in holdout_markets):
            raise VelocityStopError("opened partition failed its frozen quality gate")
        if set(development_outcomes) != {market.ticker for market in dev_markets}:
            raise VelocityStopError("development outcomes do not match eligible markets")
        if set(opened_outcomes) != {market.ticker for market in holdout_markets}:
            raise VelocityStopError("opened outcomes do not match opened markets")
        if set(opened_baseline) != {market.ticker for market in holdout_markets}:
            raise VelocityStopError("opened baseline rows do not match opened markets")

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
            if baseline["status"] == "completed":
                if context is None:
                    raise VelocityStopError(
                        f"{market.ticker}: completed baseline lacks entry context"
                    )
                path_points.extend(build_velocity_path_points(
                    snapshots=snapshots,
                    close_time=close,
                    entry_context=context,
                    baseline=baseline,
                    partition=partition,
                    segment=segment,
                ))
            for policy in POLICIES:
                if baseline["status"] != "completed":
                    row = dict(baseline)
                    row.update(_candidate_fields(policy))
                else:
                    assert context is not None
                    row = simulate_velocity_overlay(
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
    scenario_path = args.output_dir / "kxbtc15m_h3_velocity_stop_scenarios.csv"
    point_path = args.output_dir / "kxbtc15m_h3_velocity_path_points.csv"
    write_csv(scenario_path, scenario_rows)
    write_csv(point_path, path_points)
    summaries = summarize_policies(scenario_rows)
    path_summary = summarize_velocity_paths(path_points)
    verify_results(scenario_rows, summaries)
    summary_path = args.output_dir / "kxbtc15m_h3_velocity_stop_summary.csv"
    path_summary_path = args.output_dir / "kxbtc15m_h3_velocity_path_summary.csv"
    screen_path = args.output_dir / "kxbtc15m_h3_velocity_robustness_screen.csv"
    report_path = args.output_dir / "KXBTC15M_H3_VELOCITY_STOPS.md"
    combined_candidates = [
        row for row in summaries
        if row["group"] == "combined_122" and row["lookback_seconds"] != ""
    ]
    write_csv(summary_path, summaries)
    write_csv(path_summary_path, path_summary)
    write_csv(screen_path, combined_candidates)
    report_path.write_text(
        markdown_report(scenario_rows, summaries, path_summary), encoding="utf-8"
    )

    robust = [row for row in combined_candidates if row["robust_velocity_screen"]]
    print("KXBTC15M H3 causal multihorizon velocity-stop diagnostic: PASS")
    print(f"Eligible markets: {EXPECTED_TOTAL_MARKETS}")
    print(f"Baseline entries: {EXPECTED_TOTAL_ENTRIES}")
    print(f"Policies including comparators: {len(POLICIES)}")
    print(f"Velocity path points: {len(path_points)}")
    print(f"Robust velocity screens: {len(robust)}")
    print("H3 v2 selected: no")
    print("Fresh validation performed: no")
    print("Authentication used: no")
    print("Orders placed: 0")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, VelocityStopError, OSError, ValueError) as exc:
        raise SystemExit(f"KXBTC15M H3 velocity-stop error: {exc}") from exc
