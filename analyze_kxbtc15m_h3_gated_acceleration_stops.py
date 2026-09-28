#!/usr/bin/env python3
"""Evaluate bounded age-, persistence-, and acceleration-gated H3 stops.

All 122 previously opened markets are adaptive development evidence.  This
diagnostic reproduces the original causal-native H3 policy and the fixed
90-second no-target comparator, then evaluates a deliberately small family of
20-second executable-P&L velocity rules.  It never authenticates, accesses an
external BTC feed, places an order, or treats the opened evidence as holdout.
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
from analyze_kxbtc15m_h3_time_windows import _bootstrap, _mean, _money, _quantile
from analyze_kxbtc15m_h3_velocity_stops import (
    ExecutableMark,
    VelocityMeasure,
    calculate_velocity,
    latest_reference_mark,
)
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    parse_time,
    safe_extract_zip,
    select_development_manifests,
)


BASELINE_KEY = "baseline_10s"
FALLBACK_90_KEY = "fallback_90s"
VELOCITY_LOOKBACK_SECONDS = 20
RECENT_ACCELERATION_SECONDS = 10
ACTIVATION_AGES = (45, 60)
DROP_RATES = (Decimal("0.50"), Decimal("0.75"))
PERSISTENCE_SECONDS = (0, 10, 20)
LOSS_FLOOR = Decimal("15")
ACCELERATION_INCREASES = (Decimal("0.25"), Decimal("0.50"))
EXPECTED_FALLBACK_90_TOTAL_PNL = 167.18


class GatedAccelerationError(RuntimeError):
    """Raised when a diagnostic invariant fails closed."""


@dataclass(frozen=True)
class AccelerationMeasure:
    previous_reference_time: datetime
    recent_reference_time: datetime
    previous_adverse_rate: Decimal
    recent_adverse_rate: Decimal
    adverse_rate_increase: Decimal


@dataclass(frozen=True)
class GatedPolicy:
    key: str
    label: str
    family: str
    activation_age_seconds: int | None = None
    drop_rate: Decimal | None = None
    persistence_seconds: int | None = None
    acceleration_increase: Decimal | None = None
    fallback_90_seconds: bool = False


@dataclass
class GatedSignalState:
    qualifying_since: datetime | None = None


def _rate_key(value: Decimal) -> str:
    return _decimal_text(value).replace(".", "p")


def _build_policies() -> tuple[GatedPolicy, ...]:
    policies = [
        GatedPolicy(BASELINE_KEY, "Original H3: 10s fallback", "baseline"),
        GatedPolicy(
            FALLBACK_90_KEY,
            "Simple no-target cash exit at 90s",
            "fallback",
            fallback_90_seconds=True,
        ),
    ]
    for age in ACTIVATION_AGES:
        for rate in DROP_RATES:
            for persistence in PERSISTENCE_SECONDS:
                policies.append(GatedPolicy(
                    key=(
                        f"age{age}_velocity20_{_rate_key(rate)}ps_"
                        f"floor15_persist{persistence}"
                    ),
                    label=(
                        f"age >= {age}s; 20s drop >= ${float(rate):.2f}/s; "
                        f"P&L <= -$15; persist {persistence}s"
                    ),
                    family="age_persistent_velocity",
                    activation_age_seconds=age,
                    drop_rate=rate,
                    persistence_seconds=persistence,
                ))
    for age in ACTIVATION_AGES:
        for increase in ACCELERATION_INCREASES:
            policies.append(GatedPolicy(
                key=f"age{age}_accel10_{_rate_key(increase)}ps_floor15",
                label=(
                    f"age >= {age}s; 20s drop >= $0.50/s for 10s; "
                    f"10s rate increase >= ${float(increase):.2f}/s; P&L <= -$15"
                ),
                family="acceleration_confirmed",
                activation_age_seconds=age,
                drop_rate=Decimal("0.50"),
                persistence_seconds=10,
                acceleration_increase=increase,
            ))
    return tuple(policies)


POLICIES = _build_policies()


def calculate_acceleration(
    *, marks: Sequence[ExecutableMark], current_time: datetime,
    current_pnl: Decimal, window_seconds: int = RECENT_ACCELERATION_SECONDS,
) -> AccelerationMeasure | None:
    """Compare recent and preceding non-overlapping adverse P&L slopes."""

    recent = latest_reference_mark(
        marks, current_time - timedelta(seconds=window_seconds)
    )
    previous = latest_reference_mark(
        marks, current_time - timedelta(seconds=2 * window_seconds)
    )
    if recent is None or previous is None or previous.observed_at >= recent.observed_at:
        return None
    recent_elapsed = (current_time - recent.observed_at).total_seconds()
    previous_elapsed = (recent.observed_at - previous.observed_at).total_seconds()
    if recent_elapsed < window_seconds or previous_elapsed <= 0:
        return None
    recent_rate = (recent.pnl - current_pnl) / Decimal(str(recent_elapsed))
    previous_rate = (previous.pnl - recent.pnl) / Decimal(str(previous_elapsed))
    return AccelerationMeasure(
        previous_reference_time=previous.observed_at,
        recent_reference_time=recent.observed_at,
        previous_adverse_rate=previous_rate,
        recent_adverse_rate=recent_rate,
        adverse_rate_increase=recent_rate - previous_rate,
    )


def gated_signal(
    policy: GatedPolicy,
    state: GatedSignalState,
    *, observed_at: datetime, seconds_since_entry: float,
    current_pnl: Decimal | None, velocity: VelocityMeasure | None,
    acceleration: AccelerationMeasure | None,
) -> tuple[bool, str]:
    """Advance one causal signal state and return whether the rule fires."""

    if policy.family not in {"age_persistent_velocity", "acceleration_confirmed"}:
        return False, ""
    assert policy.activation_age_seconds is not None
    assert policy.drop_rate is not None
    assert policy.persistence_seconds is not None
    qualifies = (
        seconds_since_entry >= policy.activation_age_seconds
        and current_pnl is not None
        and current_pnl <= -LOSS_FLOOR
        and velocity is not None
        and velocity.drop_rate_dollars_per_second >= policy.drop_rate
    )
    if not qualifies:
        state.qualifying_since = None
        return False, ""
    if state.qualifying_since is None:
        state.qualifying_since = observed_at
    elapsed = (observed_at - state.qualifying_since).total_seconds()
    if elapsed < policy.persistence_seconds:
        return False, ""
    if policy.acceleration_increase is not None:
        if acceleration is None:
            return False, ""
        if acceleration.adverse_rate_increase < policy.acceleration_increase:
            return False, ""
        return True, "acceleration_confirmed_velocity"
    return True, "age_persistent_velocity"


def _candidate_fields(policy: GatedPolicy) -> dict[str, Any]:
    return {
        "gated_policy": policy.key,
        "gated_display_policy": policy.label,
        "gated_family": policy.family,
        "activation_age_seconds": (
            "" if policy.activation_age_seconds is None
            else policy.activation_age_seconds
        ),
        "velocity_lookback_seconds": (
            "" if policy.drop_rate is None else VELOCITY_LOOKBACK_SECONDS
        ),
        "velocity_threshold_dollars_per_second": (
            "" if policy.drop_rate is None else _decimal_text(policy.drop_rate)
        ),
        "loss_floor_dollars": (
            "" if policy.drop_rate is None else _decimal_text(LOSS_FLOOR)
        ),
        "velocity_persistence_seconds": (
            "" if policy.persistence_seconds is None else policy.persistence_seconds
        ),
        "acceleration_window_seconds": (
            "" if policy.acceleration_increase is None
            else RECENT_ACCELERATION_SECONDS
        ),
        "acceleration_threshold_rate_increase": (
            "" if policy.acceleration_increase is None
            else _decimal_text(policy.acceleration_increase)
        ),
        "candidate_risk_signal": False,
        "candidate_signal_kind": "",
        "candidate_signal_time": "",
        "candidate_signal_seconds_remaining": "",
        "candidate_signal_seconds_since_entry": "",
        "candidate_signal_executable_pnl": "",
        "candidate_velocity_reference_time": "",
        "candidate_velocity_reference_pnl": "",
        "candidate_velocity_elapsed_seconds": "",
        "candidate_velocity_rate_dollars_per_second": "",
        "candidate_qualifying_since": "",
        "candidate_qualifying_duration_seconds": "",
        "candidate_previous_adverse_rate": "",
        "candidate_recent_adverse_rate": "",
        "candidate_adverse_rate_increase": "",
        "candidate_progressive_attempts": 0,
        "candidate_progressive_fill_events": 0,
        "candidate_quantity_sold": "0",
        "candidate_remaining_at_settlement": "0",
        "candidate_fully_liquidated": False,
        "candidate_settlement_residual": False,
    }


def simulate_gated_overlay(
    *, snapshots: Sequence[Snapshot], close_time: datetime, winning_side: str,
    baseline: Mapping[str, Any],
    entry_context: tuple[int, int, str, Decimal, Decimal, Any],
    policy: GatedPolicy,
) -> dict[str, Any]:
    """Interleave protected target priority with one bounded risk rule."""

    row = dict(baseline)
    row.update(_candidate_fields(policy))
    if policy.family == "baseline":
        return row

    _decision_index, entry_index, side, _midpoint, _ask, entry = entry_context
    entry_time = snapshots[entry_index].observed_at
    target = (entry.quantity - entry.buy_outflow) * TARGET_FRACTION
    preclose = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
    marks: list[ExecutableMark] = []
    state = GatedSignalState()
    initial = sell_quantity(snapshots[entry_index].book.bid_levels(side), entry.quantity)
    if initial.quantity == entry.quantity:
        marks.append(ExecutableMark(entry_time, initial.sell_inflow - entry.buy_outflow))
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
        velocity = None
        acceleration = None
        if full and current_pnl is not None:
            velocity = calculate_velocity(
                marks=marks,
                current_time=observed.observed_at,
                current_pnl=current_pnl,
                lookback_seconds=VELOCITY_LOOKBACK_SECONDS,
            )
            acceleration = calculate_acceleration(
                marks=marks,
                current_time=observed.observed_at,
                current_pnl=current_pnl,
            )

        # The protected target keeps priority at a shared causal observation.
        if full and current_pnl is not None and current_pnl >= target:
            target_signals += 1
            delayed_index = first_index_at_or_after(
                snapshots,
                index + 1,
                observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
            )
            if delayed_index is None or snapshots[delayed_index].observed_at >= preclose:
                break
            delayed = snapshots[delayed_index]
            execution = sell_quantity(delayed.book.bid_levels(side), entry.quantity)
            if (
                execution.quantity == entry.quantity
                and execution.sell_inflow - entry.buy_outflow >= target
            ):
                return row
            target_rejections += 1
            if execution.quantity == entry.quantity:
                marks.append(ExecutableMark(
                    delayed.observed_at,
                    execution.sell_inflow - entry.buy_outflow,
                ))
            state.qualifying_since = None
            index = delayed_index + 1
            continue

        age = (observed.observed_at - entry_time).total_seconds()
        signal, reason = gated_signal(
            policy,
            state,
            observed_at=observed.observed_at,
            seconds_since_entry=age,
            current_pnl=current_pnl,
            velocity=velocity,
            acceleration=acceleration,
        )
        seconds_remaining = (close_time - observed.observed_at).total_seconds()
        fallback = policy.fallback_90_seconds and seconds_remaining <= 90
        if full and current_pnl is not None:
            marks.append(ExecutableMark(observed.observed_at, current_pnl))
        if not signal and not fallback:
            index += 1
            continue

        signal_kind = reason if signal else "fallback_90s"
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
        qualifying_duration = (
            "" if state.qualifying_since is None else
            (observed.observed_at - state.qualifying_since).total_seconds()
        )
        row.update({
            "candidate_risk_signal": True,
            "candidate_signal_kind": signal_kind,
            "candidate_signal_time": observed.observed_at.isoformat(),
            "candidate_signal_seconds_remaining": seconds_remaining,
            "candidate_signal_seconds_since_entry": age,
            "candidate_signal_executable_pnl": (
                "" if current_pnl is None else _decimal_text(current_pnl)
            ),
            "candidate_velocity_reference_time": (
                "" if velocity is None else velocity.reference_time.isoformat()
            ),
            "candidate_velocity_reference_pnl": (
                "" if velocity is None else _decimal_text(velocity.reference_pnl)
            ),
            "candidate_velocity_elapsed_seconds": (
                "" if velocity is None else velocity.elapsed_seconds
            ),
            "candidate_velocity_rate_dollars_per_second": (
                "" if velocity is None
                else _decimal_text(velocity.drop_rate_dollars_per_second)
            ),
            "candidate_qualifying_since": (
                "" if state.qualifying_since is None
                else state.qualifying_since.isoformat()
            ),
            "candidate_qualifying_duration_seconds": qualifying_duration,
            "candidate_previous_adverse_rate": (
                "" if acceleration is None
                else _decimal_text(acceleration.previous_adverse_rate)
            ),
            "candidate_recent_adverse_rate": (
                "" if acceleration is None
                else _decimal_text(acceleration.recent_adverse_rate)
            ),
            "candidate_adverse_rate_increase": (
                "" if acceleration is None
                else _decimal_text(acceleration.adverse_rate_increase)
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
            "exposure_seconds": f"{(exit_time - entry_time).total_seconds():.6f}",
        })
        return row
    return row


def _phase(age: float) -> str:
    if age < 30:
        return "entry_age_0_30s"
    if age < 45:
        return "entry_age_30_45s"
    if age < 60:
        return "entry_age_45_60s"
    return "entry_age_60s_plus"


def build_path_points(
    *, snapshots: Sequence[Snapshot], close_time: datetime,
    entry_context: tuple[int, int, str, Decimal, Decimal, Any],
    baseline: Mapping[str, Any], partition: str, segment: str,
) -> list[dict[str, Any]]:
    """Materialize causal velocity, acceleration, and below-floor durations."""

    _decision_index, entry_index, side, _midpoint, _ask, entry = entry_context
    entry_time = snapshots[entry_index].observed_at
    baseline_exit = parse_time(str(baseline["exit_execution_time"]))
    stop_time = min(baseline_exit, close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS))
    marks: list[ExecutableMark] = []
    initial = sell_quantity(snapshots[entry_index].book.bid_levels(side), entry.quantity)
    if initial.quantity == entry.quantity:
        marks.append(ExecutableMark(entry_time, initial.sell_inflow - entry.buy_outflow))
    below_since: dict[Decimal, datetime | None] = {
        Decimal("0"): None,
        Decimal("5"): None,
        Decimal("10"): None,
        Decimal("15"): None,
    }
    output: list[dict[str, Any]] = []
    for index in range(entry_index + 1, len(snapshots)):
        snapshot = snapshots[index]
        if snapshot.observed_at >= stop_time:
            break
        execution = sell_quantity(snapshot.book.bid_levels(side), entry.quantity)
        if execution.quantity != entry.quantity:
            continue
        pnl = execution.sell_inflow - entry.buy_outflow
        age = (snapshot.observed_at - entry_time).total_seconds()
        for floor in below_since:
            if pnl <= -floor:
                if below_since[floor] is None:
                    below_since[floor] = snapshot.observed_at
            else:
                below_since[floor] = None
        velocity = calculate_velocity(
            marks=marks,
            current_time=snapshot.observed_at,
            current_pnl=pnl,
            lookback_seconds=VELOCITY_LOOKBACK_SECONDS,
        )
        acceleration = calculate_acceleration(
            marks=marks,
            current_time=snapshot.observed_at,
            current_pnl=pnl,
        )
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
            "current_executable_pnl": _decimal_text(pnl),
            "seconds_continuously_nonpositive": (
                0 if below_since[Decimal("0")] is None else
                (snapshot.observed_at - below_since[Decimal("0")]).total_seconds()
            ),
            "seconds_continuously_below_minus5": (
                0 if below_since[Decimal("5")] is None else
                (snapshot.observed_at - below_since[Decimal("5")]).total_seconds()
            ),
            "seconds_continuously_below_minus10": (
                0 if below_since[Decimal("10")] is None else
                (snapshot.observed_at - below_since[Decimal("10")]).total_seconds()
            ),
            "seconds_continuously_below_minus15": (
                0 if below_since[Decimal("15")] is None else
                (snapshot.observed_at - below_since[Decimal("15")]).total_seconds()
            ),
            "velocity_20s_reference_time": (
                "" if velocity is None else velocity.reference_time.isoformat()
            ),
            "velocity_20s_actual_elapsed_seconds": (
                "" if velocity is None else velocity.elapsed_seconds
            ),
            "adverse_velocity_20s": (
                "" if velocity is None
                else _decimal_text(velocity.drop_rate_dollars_per_second)
            ),
            "previous_adverse_velocity_10s": (
                "" if acceleration is None
                else _decimal_text(acceleration.previous_adverse_rate)
            ),
            "recent_adverse_velocity_10s": (
                "" if acceleration is None
                else _decimal_text(acceleration.recent_adverse_rate)
            ),
            "adverse_velocity_increase_10s": (
                "" if acceleration is None
                else _decimal_text(acceleration.adverse_rate_increase)
            ),
            "adaptive_development_only": True,
            "external_btc_data_used": False,
            "authentication_used": False,
            "orders_placed": 0,
        })
        marks.append(ExecutableMark(snapshot.observed_at, pnl))
    return output


def summarize_path_separation(points: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    metrics = (
        ("adverse_velocity_20s", "max_adverse_velocity_20s"),
        ("adverse_velocity_increase_10s", "max_adverse_rate_increase_10s"),
        ("seconds_continuously_below_minus15", "max_seconds_below_minus15"),
    )
    for phase in (
        "entry_age_0_30s", "entry_age_30_45s",
        "entry_age_45_60s", "entry_age_60s_plus",
    ):
        selected = [point for point in points if point["entry_age_phase"] == phase]
        for source_field, metric in metrics:
            per_market: dict[str, float] = {}
            profitable: dict[str, bool] = {}
            for point in selected:
                value = point[source_field]
                if value == "":
                    continue
                ticker = str(point["ticker"])
                per_market[ticker] = max(float(value), per_market.get(ticker, -math.inf))
                profitable[ticker] = bool(point["baseline_profitable"])
            winners = [value for ticker, value in per_market.items() if profitable[ticker]]
            losers = [value for ticker, value in per_market.items() if not profitable[ticker]]
            loser_max = max(losers) if losers else math.nan
            rows.append({
                "entry_age_phase": phase,
                "metric": metric,
                "winner_markets": len(winners),
                "loser_markets": len(losers),
                "winner_median_max": _quantile(winners, 0.50) if winners else math.nan,
                "winner_p95_max": _quantile(winners, 0.95) if winners else math.nan,
                "winner_max": max(winners) if winners else math.nan,
                "loser_max": loser_max,
                "winners_at_or_above_loser": (
                    sum(value >= loser_max for value in winners) if losers else 0
                ),
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
    raise GatedAccelerationError(f"unknown group: {group}")


def summarize_policies(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for group in (
        "development_96", "opened_26", "combined_122",
        "earlier_64_diagnostic", "later_32_diagnostic",
    ):
        source = _group_rows(rows, group)
        by_key = {
            policy.key: [row for row in source if row["gated_policy"] == policy.key]
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
            fallback_differences = [
                float(row["pnl"] or 0.0) - fallback[str(row["ticker"])]
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
            signals = [row for row in completed if bool(row["candidate_risk_signal"])]
            candidate_signals = [
                row for row in signals if row["candidate_signal_kind"] != "fallback_90s"
            ]
            loser_signals = sum(row["ticker"] in losers for row in candidate_signals)
            fully_liquidated = (
                all(bool(row["candidate_fully_liquidated"]) for row in signals)
                if signals else False
            )
            full_losses = sum(bool(row["full_capital_loss"]) for row in completed)
            cost_share = winner_cost / loser_savings if loser_savings > 0 else math.inf
            basic = (
                group == "combined_122"
                and policy.family in {"age_persistent_velocity", "acceleration_confirmed"}
                and loser_signals >= 1
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
                "gated_policy": policy.key,
                "display_policy": policy.label,
                "gated_family": policy.family,
                "activation_age_seconds": (
                    "" if policy.activation_age_seconds is None
                    else policy.activation_age_seconds
                ),
                "velocity_threshold": (
                    "" if policy.drop_rate is None else float(policy.drop_rate)
                ),
                "persistence_seconds": (
                    "" if policy.persistence_seconds is None
                    else policy.persistence_seconds
                ),
                "acceleration_threshold": (
                    "" if policy.acceleration_increase is None
                    else float(policy.acceleration_increase)
                ),
                "eligible_markets": len(selected),
                "entry_filled_markets": len(completed),
                "baseline_winning_entries": len(winners),
                "baseline_losing_entries": len(losers),
                "risk_exit_signals": len(signals),
                "candidate_stopped_winners": sum(
                    row["ticker"] in winners for row in candidate_signals
                ),
                "candidate_stopped_losers": loser_signals,
                "total_pnl": sum(pnl_market),
                "mean_pnl_per_eligible_market": mean_market,
                "bootstrap_ci_low_per_eligible_market": ci_low,
                "bootstrap_ci_high_per_eligible_market": ci_high,
                "total_difference_vs_original": sum(differences),
                "mean_difference_vs_original": diff_mean,
                "paired_difference_ci_low": diff_low,
                "paired_difference_ci_high": diff_high,
                "total_difference_vs_90s": sum(fallback_differences),
                "mean_pnl_per_filled_entry": _mean(pnl_filled),
                "profitable_rate_per_filled_entry": _mean(
                    [bool(row["profitable"]) for row in completed]
                ),
                "loser_savings_vs_original": loser_savings,
                "winner_gross_opportunity_cost": winner_cost,
                "winner_cost_share_of_loser_savings": cost_share,
                "full_capital_losses": full_losses,
                "all_signaled_positions_fully_liquidated": fully_liquidated,
                "settlement_residuals": sum(
                    bool(row["candidate_settlement_residual"]) for row in signals
                ),
                "pnl_05_quantile_per_filled_entry": _quantile(pnl_filled, 0.05),
                "worst_pnl_per_filled_entry": min(pnl_filled) if pnl_filled else math.nan,
                "basic_screen": basic,
                "passing_adjacent_neighbors": 0,
                "robust_screen": False,
                "adaptive_development_only": True,
            })
    mark_neighbor_robustness(output)
    return output


def _adjacent(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    if left["gated_family"] != right["gated_family"]:
        return False
    dimensions: list[tuple[Sequence[float], float, float]] = [
        (ACTIVATION_AGES, float(left["activation_age_seconds"]), float(right["activation_age_seconds"])),
    ]
    if left["gated_family"] == "age_persistent_velocity":
        dimensions.extend([
            (tuple(float(v) for v in DROP_RATES), float(left["velocity_threshold"]), float(right["velocity_threshold"])),
            (PERSISTENCE_SECONDS, float(left["persistence_seconds"]), float(right["persistence_seconds"])),
        ])
    elif left["gated_family"] == "acceleration_confirmed":
        dimensions.append((
            tuple(float(v) for v in ACCELERATION_INCREASES),
            float(left["acceleration_threshold"]),
            float(right["acceleration_threshold"]),
        ))
    else:
        return False
    differing = 0
    for ordered, a, b in dimensions:
        ordered_float = tuple(float(v) for v in ordered)
        if a == b:
            continue
        differing += 1
        if abs(ordered_float.index(a) - ordered_float.index(b)) != 1:
            return False
    return differing == 1


def mark_neighbor_robustness(summaries: Sequence[dict[str, Any]]) -> None:
    combined = [
        row for row in summaries
        if row["group"] == "combined_122"
        and row["gated_family"] in {"age_persistent_velocity", "acceleration_confirmed"}
    ]
    passing = [row for row in combined if bool(row["basic_screen"])]
    for row in combined:
        neighbors = sum(
            other["gated_policy"] != row["gated_policy"] and _adjacent(row, other)
            for other in passing
        )
        row["passing_adjacent_neighbors"] = neighbors
        row["robust_screen"] = bool(row["basic_screen"]) and neighbors >= 1


def verify_results(
    rows: Sequence[Mapping[str, Any]], summaries: Sequence[Mapping[str, Any]],
) -> None:
    expected = EXPECTED_TOTAL_MARKETS * len(POLICIES)
    if len(rows) != expected:
        raise GatedAccelerationError(f"expected {expected} rows; found {len(rows)}")
    lookup = {(row["group"], row["gated_policy"]): row for row in summaries}
    development = lookup[("development_96", BASELINE_KEY)]
    opened = lookup[("opened_26", BASELINE_KEY)]
    combined = lookup[("combined_122", BASELINE_KEY)]
    fallback = lookup[("combined_122", FALLBACK_90_KEY)]
    if int(development["entry_filled_markets"]) != EXPECTED_NATIVE_ENTRIES:
        raise GatedAccelerationError("development baseline did not reproduce 57 entries")
    if abs(float(development["mean_pnl_per_eligible_market"]) - 2.32) > 0.01:
        raise GatedAccelerationError("development baseline mean no longer reproduces H3")
    if int(opened["entry_filled_markets"]) != EXPECTED_HOLDOUT_ENTRIES:
        raise GatedAccelerationError("opened baseline did not reproduce 14 entries")
    if abs(float(opened["total_pnl"]) - EXPECTED_HOLDOUT_TOTAL_PNL) > 0.02:
        raise GatedAccelerationError("opened baseline did not reproduce -$46.55")
    if int(opened["full_capital_losses"]) != 1:
        raise GatedAccelerationError("opened baseline did not reproduce one full loss")
    if int(combined["entry_filled_markets"]) != EXPECTED_TOTAL_ENTRIES:
        raise GatedAccelerationError("combined baseline did not reproduce 71 entries")
    if abs(float(fallback["total_pnl"]) - EXPECTED_FALLBACK_90_TOTAL_PNL) > 0.03:
        raise GatedAccelerationError("90-second comparator did not reproduce $167.18")
    if int(fallback["full_capital_losses"]) != 0:
        raise GatedAccelerationError("90-second comparator did not remove the full loss")


def _optional_money(value: Any) -> str:
    if value is None or str(value) == "":
        return "n/a"
    return _money(value)


def _optional_rate(value: Any) -> str:
    if value is None or str(value) == "" or math.isnan(float(value)):
        return "n/a"
    return f"${float(value):.2f}/s"


def _metric_value(metric: str, value: Any) -> str:
    if value is None or math.isnan(float(value)):
        return "n/a"
    if "seconds" in metric:
        return f"{float(value):.1f}s"
    return f"${float(value):.2f}/s"


def markdown_report(
    scenario_rows: Sequence[Mapping[str, Any]],
    summaries: Sequence[Mapping[str, Any]],
    path_summary: Sequence[Mapping[str, Any]],
) -> str:
    combined = [row for row in summaries if row["group"] == "combined_122"]
    comparators = [
        row for row in combined if row["gated_family"] in {"baseline", "fallback"}
    ]
    candidates = [
        row for row in combined
        if row["gated_family"] in {"age_persistent_velocity", "acceleration_confirmed"}
    ]
    robust = [row for row in candidates if bool(row["robust_screen"])]
    baseline_losses = {
        str(row["ticker"]): float(row["pnl"])
        for row in scenario_rows
        if row["gated_policy"] == BASELINE_KEY
        and row["status"] == "completed" and float(row["pnl"]) < 0
    }
    lines = [
        "# KXBTC15M H3 age-, persistence-, and acceleration-gated stop diagnostic",
        "",
        "**Adaptive hypothesis-generation test; all 122 markets are opened development evidence.**",
        "",
        "The original H3 and simple 90-second no-target exit are fixed comparators. "
        "Candidates use a 20-second causal executable-P&L slope, a -$15 full-sale "
        "P&L floor, entry-age activation, and either continuous qualifying persistence "
        "or a causal increase in adverse 10-second velocity. Protected target exits retain "
        "priority and every risk execution waits one second.",
        "",
        "## Fixed comparators",
        "",
        "| Comparator | Combined P&L | vs original | Full losses | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in comparators:
        lines.append(
            f"| {row['display_policy']} | {_money(row['total_pnl'])} | "
            f"{_money(row['total_difference_vs_original'])} | "
            f"{row['full_capital_losses']} | "
            f"{_money(row['pnl_05_quantile_per_filled_entry'])} | "
            f"{_money(row['worst_pnl_per_filled_entry'])} |"
        )
    lines.extend([
        "",
        "## Causal path separation",
        "",
        "Each value is the per-market maximum within the stated entry-age phase. The "
        "winner-overlap count is the number of baseline winners whose maximum matched or "
        "exceeded the known loser's maximum.",
        "",
        "| Entry age | Metric | Winner markets | Winner median | Winner 95% | Winner max | Loser max | Winners >= loser |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for row in path_summary:
        lines.append(
            f"| {row['entry_age_phase']} | {row['metric']} | {row['winner_markets']} | "
            f"{_metric_value(str(row['metric']), row['winner_median_max'])} | "
            f"{_metric_value(str(row['metric']), row['winner_p95_max'])} | "
            f"{_metric_value(str(row['metric']), row['winner_max'])} | "
            f"{_metric_value(str(row['metric']), row['loser_max'])} | "
            f"{row['winners_at_or_above_loser']} |"
        )
    lines.extend([
        "",
        "## Bounded candidate surface",
        "",
        "| Family | Age | Rate | Persist | Accel increase | Stops W/L | Combined P&L | vs original | vs 90s | Loser saved | Winner cost | Full losses | Basic | Neighbors | Robust |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in candidates:
        lines.append(
            f"| {row['gated_family']} | {row['activation_age_seconds']}s | "
            f"{_optional_rate(row['velocity_threshold'])} | "
            f"{row['persistence_seconds']}s | "
            f"{_optional_rate(row['acceleration_threshold'])} | "
            f"{row['candidate_stopped_winners']}/{row['candidate_stopped_losers']} | "
            f"{_money(row['total_pnl'])} | {_money(row['total_difference_vs_original'])} | "
            f"{_money(row['total_difference_vs_90s'])} | "
            f"{_money(row['loser_savings_vs_original'])} | "
            f"{_money(row['winner_gross_opportunity_cost'])} | "
            f"{row['full_capital_losses']} | {row['basic_screen']} | "
            f"{row['passing_adjacent_neighbors']} | {row['robust_screen']} |"
        )
    lines.extend([
        "",
        "## Known-loss execution",
        "",
        "| Policy | Signal | Age | Sec left | Signal P&L | 20s rate | Rate increase | Result P&L | Saved |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in scenario_rows:
        if row["gated_policy"] in {BASELINE_KEY, FALLBACK_90_KEY}:
            continue
        if row["ticker"] not in baseline_losses:
            continue
        lines.append(
            f"| {row['gated_display_policy']} | {row['candidate_signal_kind'] or 'none'} | "
            f"{row['candidate_signal_seconds_since_entry'] or 'n/a'} | "
            f"{row['candidate_signal_seconds_remaining'] or 'n/a'} | "
            f"{_optional_money(row['candidate_signal_executable_pnl'])} | "
            f"{_optional_rate(row['candidate_velocity_rate_dollars_per_second'])} | "
            f"{_optional_rate(row['candidate_adverse_rate_increase'])} | "
            f"{_money(row['pnl'])} | "
            f"{_money(float(row['pnl']) - baseline_losses[str(row['ticker'])])} |"
        )
    lines.extend([
        "",
        "## Evidence screen",
        "",
        "A basic candidate must stop the known loser, save at least $25, improve combined "
        "P&L versus original H3, keep gross winner cost to at most 50% of loser savings, "
        "create zero full-capital losses, and fully liquidate every signal. A robust candidate "
        "also needs a passing adjacent setting within its own family.",
        "",
        "Robust gated candidates: "
        + (", ".join(f"`{row['gated_policy']}`" for row in robust) if robust else "none"),
        "",
        "No policy is selected automatically. The 90-second rule remains a fixed comparator. "
        "With only one baseline loser, any favorable row is an adaptively fitted hypothesis "
        "that requires a newly collected chronological confirmation sample. No external BTC "
        "data, authentication, or order placement is used.",
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
        default=Path("analysis/kxbtc15m_h3_gated_acceleration_stops"),
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

    with TemporaryDirectory(prefix="kxbtc15m_h3_gated_acceleration_") as temporary:
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
            raise GatedAccelerationError(
                "expected 96 eligible development plus 26 opened markets"
            )
        if any(not market.eligible for market in holdout_markets):
            raise GatedAccelerationError("opened partition failed its frozen quality gate")
        if set(development_outcomes) != {market.ticker for market in dev_markets}:
            raise GatedAccelerationError("development outcomes do not match markets")
        if set(opened_outcomes) != {market.ticker for market in holdout_markets}:
            raise GatedAccelerationError("opened outcomes do not match markets")
        if set(opened_baseline) != {market.ticker for market in holdout_markets}:
            raise GatedAccelerationError("opened baseline rows do not match markets")

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
                    raise GatedAccelerationError(
                        f"{market.ticker}: completed baseline lacks entry context"
                    )
                path_points.extend(build_path_points(
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
                    row = simulate_gated_overlay(
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
    scenario_path = args.output_dir / "kxbtc15m_h3_gated_acceleration_scenarios.csv"
    point_path = args.output_dir / "kxbtc15m_h3_gated_acceleration_path_points.csv"
    write_csv(scenario_path, scenario_rows)
    write_csv(point_path, path_points)
    summaries = summarize_policies(scenario_rows)
    path_summary = summarize_path_separation(path_points)
    verify_results(scenario_rows, summaries)
    summary_path = args.output_dir / "kxbtc15m_h3_gated_acceleration_summary.csv"
    path_summary_path = args.output_dir / "kxbtc15m_h3_gated_acceleration_path_summary.csv"
    report_path = args.output_dir / "KXBTC15M_H3_GATED_ACCELERATION_STOPS.md"
    write_csv(summary_path, summaries)
    write_csv(path_summary_path, path_summary)
    report_path.write_text(
        markdown_report(scenario_rows, summaries, path_summary), encoding="utf-8"
    )

    combined_candidates = [
        row for row in summaries
        if row["group"] == "combined_122"
        and row["gated_family"] in {"age_persistent_velocity", "acceleration_confirmed"}
    ]
    robust = [row for row in combined_candidates if row["robust_screen"]]
    print("KXBTC15M H3 gated acceleration-stop diagnostic: PASS")
    print(f"Eligible markets: {EXPECTED_TOTAL_MARKETS}")
    print(f"Baseline entries: {EXPECTED_TOTAL_ENTRIES}")
    print(f"Policies including comparators: {len(POLICIES)}")
    print(f"Path points: {len(path_points)}")
    print(f"Robust screens: {len(robust)}")
    print("H3 v2 selected: no")
    print("Fresh validation performed: no")
    print("Authentication used: no")
    print("Orders placed: 0")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, GatedAccelerationError, OSError, ValueError) as exc:
        raise SystemExit(f"KXBTC15M H3 gated-acceleration error: {exc}") from exc
