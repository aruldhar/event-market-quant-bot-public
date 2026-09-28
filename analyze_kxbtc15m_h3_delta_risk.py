#!/usr/bin/env python3
"""Test causal Kalshi-delta and executable-loss overlays on frozen H3 entries.

The 52 H3 first-trigger decisions, protected 50%-of-maximum target, full-depth
execution, fee model, preclose fallback, and eight prior latency scenarios are
frozen.  This diagnostic adds a small predeclared risk-policy grid.  Every
chart lookup uses the last Kalshi live-data observation at or before the order-
book signal timestamp.  Every resulting sale still waits the scenario's exit
latency and crosses archived full depth.

Development only.  No authentication, external BTC feed, order placement, or
holdout access is permitted.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import random
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import (
    EXPECTED_ELIGIBLE_MARKETS,
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
from analyze_kxbtc15m_h3_latency_stress import (
    TARGET_FRACTION,
    find_preclose_exit,
    scenario_grid,
)
from analyze_kxbtc15m_h3_target_protection import parse_bool
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    parse_time,
    safe_extract_zip,
    select_development_manifests,
)


EXPECTED_LIVE_MARKETS = 96
EXPECTED_LIVE_POINTS = 345_696
EXPECTED_POINTS_PER_MARKET = 3_601
MAX_CAUSAL_CHART_AGE_SECONDS = 2.0
EXPECTED_PRIOR_LATENCY_ROWS = EXPECTED_PRIMARY_TRIGGERS * len(scenario_grid())


class DeltaRiskError(RuntimeError):
    """Raised when a delta-risk input or causal invariant is violated."""


@dataclass(frozen=True)
class ChartPoint:
    observed_at: datetime
    value: Decimal


@dataclass(frozen=True)
class ChartSeries:
    target: Decimal
    timestamps: tuple[datetime, ...]
    points: tuple[ChartPoint, ...]


@dataclass(frozen=True)
class RiskPolicy:
    name: str
    mode: str
    delta_threshold: Decimal | None = None
    loss_fraction: Decimal | None = None


@dataclass(frozen=True)
class ExitSelection:
    execution: Any | None
    exit_time: datetime | None
    signal_time: datetime | None
    reason: str | None
    target_signals: int
    target_rejections: int
    risk_signals: int
    risk_liquidity_failures: int
    signal_aligned_delta: Decimal | None
    signal_executable_pnl: Decimal | None
    signal_chart_age_seconds: float | None
    minimum_aligned_delta_seen: Decimal | None


RISK_POLICIES = (
    RiskPolicy("baseline_no_risk_overlay", "none"),
    RiskPolicy("delta_cross_0usd", "delta", delta_threshold=Decimal("0")),
    RiskPolicy("delta_buffer_5usd", "delta", delta_threshold=Decimal("5")),
    RiskPolicy("delta_buffer_10usd", "delta", delta_threshold=Decimal("10")),
    RiskPolicy("loss_stop_5pct", "loss", loss_fraction=Decimal("0.05")),
    RiskPolicy("loss_stop_10pct", "loss", loss_fraction=Decimal("0.10")),
    RiskPolicy(
        "delta_5usd_or_loss_10pct",
        "or",
        delta_threshold=Decimal("5"),
        loss_fraction=Decimal("0.10"),
    ),
    RiskPolicy(
        "delta_5usd_and_loss_5pct",
        "and",
        delta_threshold=Decimal("5"),
        loss_fraction=Decimal("0.05"),
    ),
)


def policy_names() -> tuple[str, ...]:
    return tuple(policy.name for policy in RISK_POLICIES)


def parse_csv_flag(value: Any, *, field: str) -> bool:
    text = str(value).strip().lower()
    if text in {"1", "true"}:
        return True
    if text in {"0", "false"}:
        return False
    raise DeltaRiskError(f"invalid {field} flag: {value!r}")


def load_prior_latency_scenarios(path: Path) -> dict[tuple[str, str], float]:
    required = {
        "ticker", "scenario", "pnl", "entry_filled", "holdout_read",
        "external_btc_data_used",
    }
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = required - fields
        if missing:
            raise DeltaRiskError(
                f"prior latency CSV missing fields: {sorted(missing)}"
            )
        rows = list(reader)
    if len(rows) != EXPECTED_PRIOR_LATENCY_ROWS:
        raise DeltaRiskError(
            f"expected {EXPECTED_PRIOR_LATENCY_ROWS} prior latency rows; "
            f"found {len(rows)}"
        )
    if any(parse_bool(row["holdout_read"]) for row in rows):
        raise DeltaRiskError("prior latency input reports a holdout read")
    if any(parse_bool(row["external_btc_data_used"]) for row in rows):
        raise DeltaRiskError("prior latency input reports external BTC data")
    if any(not parse_bool(row["entry_filled"]) for row in rows):
        raise DeltaRiskError("prior latency input contains an unfilled entry")
    output = {
        (str(row["ticker"]), str(row["scenario"])): float(row["pnl"])
        for row in rows
    }
    if len(output) != EXPECTED_PRIOR_LATENCY_ROWS:
        raise DeltaRiskError("prior latency ticker/scenario keys are not unique")
    return output


def load_chart_series(
    summary_path: Path,
    timeseries_path: Path,
    *,
    required_tickers: set[str],
) -> dict[str, ChartSeries]:
    summary_required = {
        "ticker", "target_price", "timeseries_point_count", "holdout_read",
        "authentication_used", "target_matches_rounded_preopen_reference",
        "audit_only_final_matches_expiration_rounded",
    }
    with summary_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = summary_required - fields
        if missing:
            raise DeltaRiskError(
                f"live-data summary missing fields: {sorted(missing)}"
            )
        summaries = list(reader)
    if len(summaries) != EXPECTED_LIVE_MARKETS:
        raise DeltaRiskError(
            f"expected {EXPECTED_LIVE_MARKETS} live-data summaries; "
            f"found {len(summaries)}"
        )
    summary_by_ticker = {str(row["ticker"]): row for row in summaries}
    if len(summary_by_ticker) != EXPECTED_LIVE_MARKETS:
        raise DeltaRiskError("live-data summary tickers are not unique")
    if not required_tickers.issubset(summary_by_ticker):
        raise DeltaRiskError("live-data summary is missing triggered markets")
    for row in summaries:
        if parse_csv_flag(row["holdout_read"], field="holdout_read"):
            raise DeltaRiskError("live-data summary reports a holdout read")
        if parse_csv_flag(row["authentication_used"], field="authentication_used"):
            raise DeltaRiskError("live-data summary reports authentication")
        if not parse_csv_flag(
            row["target_matches_rounded_preopen_reference"],
            field="target_matches_rounded_preopen_reference",
        ):
            raise DeltaRiskError("live-data summary contains a target mismatch")
        if not parse_csv_flag(
            row["audit_only_final_matches_expiration_rounded"],
            field="audit_only_final_matches_expiration_rounded",
        ):
            raise DeltaRiskError("live-data summary contains a final-value mismatch")
        if int(row["timeseries_point_count"]) != EXPECTED_POINTS_PER_MARKET:
            raise DeltaRiskError(
                f"{row['ticker']}: unexpected live-data point count"
            )

    required_fields = {
        "ticker", "target_price", "observed_at_utc", "value", "holdout_read"
    }
    # The v1 collector stores holdout status in the summary rather than each
    # timeseries row.  Accept that exact schema while rejecting other omissions.
    required_fields.remove("holdout_read")
    points: dict[str, list[ChartPoint]] = {ticker: [] for ticker in required_tickers}
    counts: dict[str, int] = {}
    prior_time: dict[str, datetime] = {}
    total = 0
    with timeseries_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = required_fields - fields
        if missing:
            raise DeltaRiskError(
                f"live-data timeseries missing fields: {sorted(missing)}"
            )
        for row_number, row in enumerate(reader, start=2):
            total += 1
            ticker = str(row["ticker"])
            if ticker not in summary_by_ticker:
                raise DeltaRiskError(
                    f"timeseries row {row_number} has unknown ticker {ticker}"
                )
            target = Decimal(str(row["target_price"]))
            expected_target = Decimal(str(summary_by_ticker[ticker]["target_price"]))
            if target != expected_target:
                raise DeltaRiskError(
                    f"{ticker}: timeseries target differs from summary"
                )
            observed_at = parse_time(str(row["observed_at_utc"]))
            if ticker in prior_time and observed_at <= prior_time[ticker]:
                raise DeltaRiskError(
                    f"{ticker}: live-data timestamps are not strictly increasing"
                )
            prior_time[ticker] = observed_at
            counts[ticker] = counts.get(ticker, 0) + 1
            if ticker in points:
                points[ticker].append(
                    ChartPoint(observed_at, Decimal(str(row["value"])))
                )
    if total != EXPECTED_LIVE_POINTS:
        raise DeltaRiskError(
            f"expected {EXPECTED_LIVE_POINTS} live-data rows; found {total}"
        )
    if set(counts) != set(summary_by_ticker):
        raise DeltaRiskError("live-data summary/timeseries ticker sets differ")
    if any(count != EXPECTED_POINTS_PER_MARKET for count in counts.values()):
        raise DeltaRiskError("live-data timeseries has an unexpected market count")

    output: dict[str, ChartSeries] = {}
    for ticker in sorted(required_tickers):
        market_points = tuple(points[ticker])
        if len(market_points) != EXPECTED_POINTS_PER_MARKET:
            raise DeltaRiskError(f"{ticker}: incomplete retained chart series")
        output[ticker] = ChartSeries(
            target=Decimal(str(summary_by_ticker[ticker]["target_price"])),
            timestamps=tuple(point.observed_at for point in market_points),
            points=market_points,
        )
    return output


def latest_chart_point(series: ChartSeries, at: datetime) -> tuple[ChartPoint, float]:
    index = bisect.bisect_right(series.timestamps, at) - 1
    if index < 0:
        raise DeltaRiskError("no causal chart observation at decision time")
    point = series.points[index]
    age = (at - point.observed_at).total_seconds()
    if age < 0 or age >= MAX_CAUSAL_CHART_AGE_SECONDS:
        raise DeltaRiskError(f"causal chart observation is stale by {age:.6f}s")
    return point, age


def side_aligned_delta(*, side: str, value: Decimal, target: Decimal) -> Decimal:
    if side == "YES":
        return value - target
    if side == "NO":
        return target - value
    raise DeltaRiskError(f"invalid side: {side}")


def risk_signal(
    policy: RiskPolicy,
    *,
    aligned_delta: Decimal,
    executable_pnl: Decimal | None,
    outflow: Decimal,
) -> bool:
    if outflow <= 0:
        raise DeltaRiskError("risk evaluation requires positive outflow")
    delta_breach = (
        policy.delta_threshold is not None
        and aligned_delta <= policy.delta_threshold
    )
    loss_breach = (
        policy.loss_fraction is not None
        and executable_pnl is not None
        and executable_pnl <= -(policy.loss_fraction * outflow)
    )
    if policy.mode == "none":
        return False
    if policy.mode == "delta":
        return delta_breach
    if policy.mode == "loss":
        return loss_breach
    if policy.mode == "or":
        return delta_breach or loss_breach
    if policy.mode == "and":
        return delta_breach and loss_breach
    raise DeltaRiskError(f"invalid risk-policy mode: {policy.mode}")


def find_protected_or_risk_exit(
    *,
    snapshots: Sequence[Snapshot],
    chart: ChartSeries,
    start_index: int,
    stop_time: datetime,
    side: str,
    quantity: Decimal,
    outflow: Decimal,
    target_amount: Decimal,
    exit_latency_seconds: float,
    policy: RiskPolicy,
) -> ExitSelection:
    if exit_latency_seconds <= 0:
        raise DeltaRiskError("exit latency must be positive")
    target_signals = 0
    target_rejections = 0
    risk_signals = 0
    risk_liquidity_failures = 0
    minimum_delta: Decimal | None = None
    index = start_index
    while index < len(snapshots):
        observed = snapshots[index]
        if observed.observed_at >= stop_time:
            break
        chart_point, chart_age = latest_chart_point(chart, observed.observed_at)
        aligned = side_aligned_delta(
            side=side, value=chart_point.value, target=chart.target
        )
        minimum_delta = aligned if minimum_delta is None else min(minimum_delta, aligned)
        hypothetical = sell_quantity(observed.book.bid_levels(side), quantity)
        full_depth = hypothetical.quantity == quantity
        signal_pnl = hypothetical.sell_inflow - outflow if full_depth else None

        if full_depth and signal_pnl is not None and signal_pnl >= target_amount:
            target_signals += 1
            delayed_index = first_index_at_or_after(
                snapshots,
                index + 1,
                observed.observed_at + timedelta(seconds=exit_latency_seconds),
            )
            if delayed_index is None or snapshots[delayed_index].observed_at >= stop_time:
                target_rejections += 1
                break
            delayed = snapshots[delayed_index]
            execution = sell_quantity(delayed.book.bid_levels(side), quantity)
            if (
                execution.quantity == quantity
                and execution.sell_inflow - outflow >= target_amount
            ):
                return ExitSelection(
                    execution, delayed.observed_at, observed.observed_at,
                    "protected_profit_target", target_signals,
                    target_rejections, risk_signals, risk_liquidity_failures,
                    aligned, signal_pnl, chart_age, minimum_delta,
                )
            target_rejections += 1
            index = delayed_index + 1
            continue

        if risk_signal(
            policy,
            aligned_delta=aligned,
            executable_pnl=signal_pnl,
            outflow=outflow,
        ):
            risk_signals += 1
            delayed_index = first_index_at_or_after(
                snapshots,
                index + 1,
                observed.observed_at + timedelta(seconds=exit_latency_seconds),
            )
            if delayed_index is None or snapshots[delayed_index].observed_at >= stop_time:
                risk_liquidity_failures += 1
                break
            delayed = snapshots[delayed_index]
            execution = sell_quantity(delayed.book.bid_levels(side), quantity)
            if execution.quantity == quantity:
                return ExitSelection(
                    execution, delayed.observed_at, observed.observed_at,
                    "risk_overlay_exit", target_signals, target_rejections,
                    risk_signals, risk_liquidity_failures, aligned, signal_pnl,
                    chart_age, minimum_delta,
                )
            risk_liquidity_failures += 1
            index = delayed_index + 1
            continue
        index += 1

    return ExitSelection(
        None, None, None, None, target_signals, target_rejections,
        risk_signals, risk_liquidity_failures, None, None, None, minimum_delta,
    )


def simulate_delta_policy(
    *,
    snapshots: Sequence[Snapshot],
    chart: ChartSeries,
    decision_index: int,
    close_time: datetime,
    winning_side: str,
    trigger: Mapping[str, Any],
    scenario: str,
    stress_mode: str,
    entry_latency_seconds: float,
    exit_latency_seconds: float,
    policy: RiskPolicy,
) -> dict[str, Any]:
    decision = snapshots[decision_index]
    quote = favored_quote(decision.book)
    if quote is None:
        raise DeltaRiskError(f"{trigger['ticker']}: favored quote unavailable")
    side, midpoint, decision_ask = quote
    seconds_remaining = (close_time - decision.observed_at).total_seconds()
    if not (
        240 < seconds_remaining <= 300
        and Decimal("0.90") <= midpoint < Decimal("0.98")
    ):
        raise DeltaRiskError(f"{trigger['ticker']}: frozen H3 trigger drifted")

    decision_chart, decision_chart_age = latest_chart_point(
        chart, decision.observed_at
    )
    decision_delta = side_aligned_delta(
        side=side, value=decision_chart.value, target=chart.target
    )
    entry_index = first_index_at_or_after(
        snapshots,
        decision_index + 1,
        decision.observed_at + timedelta(seconds=entry_latency_seconds),
    )
    if entry_index is None or snapshots[entry_index].observed_at >= close_time:
        raise DeltaRiskError(f"{trigger['ticker']}: frozen entry no longer fills")
    entry_snapshot = snapshots[entry_index]
    entry_ask = best_ask(entry_snapshot.book, side)
    if entry_ask is None:
        raise DeltaRiskError(f"{trigger['ticker']}: entry book unavailable")
    entry = buy_with_budget(entry_snapshot.book.ask_levels(side), MAX_BUDGET)
    if entry.quantity <= 0:
        raise DeltaRiskError(f"{trigger['ticker']}: entry unfilled")
    entry_chart, entry_chart_age = latest_chart_point(
        chart, entry_snapshot.observed_at
    )
    entry_delta = side_aligned_delta(
        side=side, value=entry_chart.value, target=chart.target
    )

    quantity = entry.quantity
    outflow = entry.buy_outflow
    maximum_profit = quantity - outflow
    if maximum_profit <= 0:
        raise DeltaRiskError(f"{trigger['ticker']}: nonpositive maximum profit")
    target_amount = percentage_target(maximum_profit, TARGET_FRACTION)
    settlement_gross = quantity if side == winning_side else Decimal("0")
    settlement_pnl = settlement_gross - outflow
    preclose_time = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
    selection = find_protected_or_risk_exit(
        snapshots=snapshots,
        chart=chart,
        start_index=entry_index + 1,
        stop_time=preclose_time,
        side=side,
        quantity=quantity,
        outflow=outflow,
        target_amount=target_amount,
        exit_latency_seconds=exit_latency_seconds,
        policy=policy,
    )

    target_filled = selection.reason == "protected_profit_target"
    risk_exited = selection.reason == "risk_overlay_exit"
    fallback_used = selection.execution is None
    fallback_liquidity_failure = False
    if selection.execution is not None:
        assert selection.exit_time is not None
        exit_time = selection.exit_time
        signal_time = selection.signal_time
        exit_reason = str(selection.reason)
        exit_gross = selection.execution.gross
        exit_fee = selection.execution.fee
        pnl = selection.execution.sell_inflow - outflow
    else:
        forced, exit_time, signal_time = find_preclose_exit(
            snapshots=snapshots,
            start_index=entry_index + 1,
            start_time=preclose_time,
            close_time=close_time,
            side=side,
            quantity=quantity,
            latency_seconds=exit_latency_seconds,
        )
        if forced is None:
            fallback_liquidity_failure = True
            exit_time = close_time
            signal_time = None
            exit_reason = "settlement_after_preclose_liquidity_failure"
            exit_gross = settlement_gross
            exit_fee = Decimal("0")
            pnl = settlement_pnl
        else:
            exit_reason = "preclose_time_exit"
            exit_gross = forced.gross
            exit_fee = forced.fee
            pnl = forced.sell_inflow - outflow

    return {
        "ticker": trigger["ticker"],
        "diagnostic_segment": trigger["diagnostic_segment"],
        "scenario": scenario,
        "stress_mode": stress_mode,
        "configured_entry_latency_seconds": entry_latency_seconds,
        "configured_exit_latency_seconds": exit_latency_seconds,
        "risk_policy": policy.name,
        "risk_mode": policy.mode,
        "delta_threshold_usd": "" if policy.delta_threshold is None else float(policy.delta_threshold),
        "loss_fraction_of_cash_deployed": "" if policy.loss_fraction is None else float(policy.loss_fraction),
        "status": "completed",
        "decision_time": decision.observed_at.isoformat(),
        "seconds_remaining": seconds_remaining,
        "side": side,
        "favored_side_won": side == winning_side,
        "decision_favored_midpoint": float(midpoint),
        "decision_favored_ask": float(decision_ask),
        "target_price": float(chart.target),
        "decision_chart_time": decision_chart.observed_at.isoformat(),
        "decision_chart_value": float(decision_chart.value),
        "decision_chart_age_seconds": decision_chart_age,
        "decision_side_aligned_delta": float(decision_delta),
        "entry_execution_time": entry_snapshot.observed_at.isoformat(),
        "entry_realized_delay_seconds": (
            entry_snapshot.observed_at - decision.observed_at
        ).total_seconds(),
        "entry_best_ask": float(entry_ask),
        "entry_average_price": float(entry.gross / quantity),
        "entry_price_change_from_decision_ask": float(entry.gross / quantity - decision_ask),
        "entry_chart_time": entry_chart.observed_at.isoformat(),
        "entry_chart_value": float(entry_chart.value),
        "entry_chart_age_seconds": entry_chart_age,
        "entry_side_aligned_delta": float(entry_delta),
        "contracts": float(quantity),
        "cash_deployed": float(outflow),
        "budget_utilization": float(outflow / MAX_BUDGET),
        "entry_fee": float(entry.fee),
        "maximum_settlement_profit": float(maximum_profit),
        "target_fraction_of_maximum": float(TARGET_FRACTION),
        "target_amount": float(target_amount),
        "target_signal_count": selection.target_signals,
        "target_rejected_after_latency_count": selection.target_rejections,
        "target_filled": target_filled,
        "risk_signal_count": selection.risk_signals,
        "risk_liquidity_failure_count": selection.risk_liquidity_failures,
        "risk_exited": risk_exited,
        "risk_signal_side_aligned_delta": "" if selection.signal_aligned_delta is None else float(selection.signal_aligned_delta),
        "risk_signal_executable_pnl": "" if selection.signal_executable_pnl is None else float(selection.signal_executable_pnl),
        "risk_signal_chart_age_seconds": "" if selection.signal_chart_age_seconds is None else selection.signal_chart_age_seconds,
        "minimum_side_aligned_delta_seen": "" if selection.minimum_aligned_delta_seen is None else float(selection.minimum_aligned_delta_seen),
        "fallback_used": fallback_used,
        "fallback_liquidity_failure": fallback_liquidity_failure,
        "exit_signal_time": "" if signal_time is None else signal_time.isoformat(),
        "exit_execution_time": exit_time.isoformat(),
        "exit_realized_delay_seconds": "" if signal_time is None else (exit_time - signal_time).total_seconds(),
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
        "authenticated_kalshi_data_used": False,
    }


def verify_baseline_reproduction(
    prior: Mapping[tuple[str, str], float],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    actual = {
        (str(row["ticker"]), str(row["scenario"])): float(row["pnl"])
        for row in rows
        if row["risk_policy"] == "baseline_no_risk_overlay"
    }
    if set(actual) != set(prior):
        raise DeltaRiskError("baseline reproduction key set mismatch")
    mismatches = [
        key for key, expected in prior.items()
        if abs(actual[key] - expected) > 1e-9
    ]
    if mismatches:
        key = mismatches[0]
        raise DeltaRiskError(
            f"baseline reproduction failed for {len(mismatches)} row(s); "
            f"first={key} expected={prior[key]} actual={actual[key]}"
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


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    baseline = {
        (str(row["ticker"]), str(row["scenario"])): float(row["pnl"])
        for row in rows
        if row["risk_policy"] == "baseline_no_risk_overlay"
    }
    output: list[dict[str, Any]] = []
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        segment_rows = list(rows) if segment == "all_96" else [
            row for row in rows
            if row["diagnostic_segment"] == (
                "earlier_64" if segment == "earlier_64_diagnostic" else "later_32"
            )
        ]
        for scenario, mode, entry_latency, exit_latency in scenario_grid():
            for policy in RISK_POLICIES:
                selected = [
                    row for row in segment_rows
                    if row["scenario"] == scenario and row["risk_policy"] == policy.name
                ]
                pnl = [float(row["pnl"]) for row in selected]
                mean, low, high = _bootstrap(pnl)
                paired = [
                    float(row["pnl"]) - baseline[(str(row["ticker"]), scenario)]
                    for row in selected
                ]
                output.append({
                    "segment": segment,
                    "scenario": scenario,
                    "stress_mode": mode,
                    "configured_entry_latency_seconds": entry_latency,
                    "configured_exit_latency_seconds": exit_latency,
                    "risk_policy": policy.name,
                    "risk_mode": policy.mode,
                    "delta_threshold_usd": "" if policy.delta_threshold is None else float(policy.delta_threshold),
                    "loss_fraction_of_cash_deployed": "" if policy.loss_fraction is None else float(policy.loss_fraction),
                    "triggered_markets": len(selected),
                    "mean_pnl": mean,
                    "bootstrap_ci_low": low,
                    "bootstrap_ci_high": high,
                    "mean_paired_difference_vs_no_overlay": statistics.mean(paired) if paired else math.nan,
                    "profitable_rate": statistics.mean(float(row["pnl"]) > 0 for row in selected) if selected else math.nan,
                    "protected_target_fill_rate": statistics.mean(bool(row["target_filled"]) for row in selected) if selected else math.nan,
                    "risk_exit_rate": statistics.mean(bool(row["risk_exited"]) for row in selected) if selected else math.nan,
                    "risk_exit_baseline_winner_rate": statistics.mean(
                        bool(row["risk_exited"])
                        and baseline[(str(row["ticker"]), scenario)] > 0
                        for row in selected
                    ) if selected else math.nan,
                    "full_capital_loss_rate": statistics.mean(bool(row["full_capital_loss"]) for row in selected) if selected else math.nan,
                    "pnl_05_quantile": _quantile(pnl, 0.05),
                    "worst_pnl": min(pnl) if pnl else math.nan,
                    "holdout_read": False,
                    "external_btc_data_used": False,
                    "authenticated_kalshi_data_used": False,
                })
    return output


def _money(value: float) -> str:
    return "n/a" if math.isnan(value) else f"${value:.2f}"


def _percent(value: float) -> str:
    return "n/a" if math.isnan(value) else f"{value:.1%}"


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    displayed_scenarios = (
        "combined_1s", "combined_3s", "combined_5s", "exit_only_5s"
    )
    lines = [
        "# KXBTC15M H3 causal delta-risk diagnostic",
        "",
        "**Matched development risk overlay; entries and latency scenarios frozen; holdout sealed.**",
        "",
        "All policies retain the protected 50%-of-maximum profit target and ten-second "
        "preclose fallback. Delta is side-aligned: positive means the Kalshi BTC chart "
        "is on the purchased side of the target. A risk signal waits the configured "
        "latency and then attempts a full-depth sale. The target has priority when both "
        "signals occur at the same observation.",
        "",
        "The table shows normal execution plus the three prior settings that produced a "
        "full-capital loss. All eight latency settings are available in the summary CSV.",
        "",
        "| Latency scenario | Risk policy | Mean P&L | vs no overlay | 95% CI | Positive | Risk exit | Baseline winner stopped | Full loss | 5% tail | Worst |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scenario in displayed_scenarios:
        for policy in RISK_POLICIES:
            row = next(
                item for item in summary
                if item["segment"] == "all_96"
                and item["scenario"] == scenario
                and item["risk_policy"] == policy.name
            )
            lines.append(
                f"| {scenario} | {policy.name} | {_money(float(row['mean_pnl']))} | "
                f"{_money(float(row['mean_paired_difference_vs_no_overlay']))} | "
                f"{_money(float(row['bootstrap_ci_low']))} to {_money(float(row['bootstrap_ci_high']))} | "
                f"{_percent(float(row['profitable_rate']))} | "
                f"{_percent(float(row['risk_exit_rate']))} | "
                f"{_percent(float(row['risk_exit_baseline_winner_rate']))} | "
                f"{_percent(float(row['full_capital_loss_rate']))} | "
                f"{_money(float(row['pnl_05_quantile']))} | "
                f"{_money(float(row['worst_pnl']))} |"
            )
    lines.extend([
        "",
        "This is a bounded mechanics diagnostic on 52 already-explored entries. The small "
        "threshold grid estimates the cost and potential tail protection of simple rules; "
        "it does not authorize choosing the best row as an unbiased edge. Keep the existing "
        "holdout sealed and validate a surviving rule prospectively.",
    ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_zip", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--triggers-csv", type=Path, required=True)
    parser.add_argument("--prior-latency-scenarios-csv", type=Path, required=True)
    parser.add_argument("--live-data-summary-csv", type=Path, required=True)
    parser.add_argument("--live-data-timeseries-csv", type=Path, required=True)
    parser.add_argument("--outcomes-csv", type=Path, required=True)
    parser.add_argument("--series-csv", type=Path, required=True)
    parser.add_argument("--fee-changes-csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("analysis/kxbtc15m_h3_delta_risk"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    triggers = load_primary_triggers(args.triggers_csv)
    trigger_by_ticker = {row["ticker"]: row for row in triggers}
    prior = load_prior_latency_scenarios(args.prior_latency_scenarios_csv)
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    charts = load_chart_series(
        args.live_data_summary_csv,
        args.live_data_timeseries_csv,
        required_tickers=set(trigger_by_ticker),
    )
    if {ticker for ticker, _ in prior} != set(trigger_by_ticker):
        raise DeltaRiskError("prior latency and trigger ticker sets differ")
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_h3_delta_risk_") as temporary:
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
                f"expected {EXPECTED_ELIGIBLE_MARKETS} eligible markets; "
                f"found {len(eligible)}"
            )
        if set(outcomes) != {market.ticker for market in eligible}:
            raise SimulationError("outcome ticker set does not equal development set")
        triggered = [market for market in eligible if market.ticker in trigger_by_ticker]
        if len(triggered) != EXPECTED_PRIMARY_TRIGGERS:
            raise DeltaRiskError("eligible trigger-market set mismatch")

        for number, market in enumerate(triggered, start=1):
            trigger = trigger_by_ticker[market.ticker]
            snapshots = load_snapshots(market, args.repo_root)
            decision_time = parse_time(trigger["decision_time"])
            decision_index = first_index_at_or_after(snapshots, 0, decision_time)
            if decision_index is None or snapshots[decision_index].observed_at != decision_time:
                raise DeltaRiskError(f"{market.ticker}: exact trigger not found")
            for scenario, mode, entry_latency, exit_latency in scenario_grid():
                for policy in RISK_POLICIES:
                    rows.append(simulate_delta_policy(
                        snapshots=snapshots,
                        chart=charts[market.ticker],
                        decision_index=decision_index,
                        close_time=market_close_utc(market.ticker),
                        winning_side=outcomes[market.ticker],
                        trigger=trigger,
                        scenario=scenario,
                        stress_mode=mode,
                        entry_latency_seconds=entry_latency,
                        exit_latency_seconds=exit_latency,
                        policy=policy,
                    ))
            print(f"[{number:02d}/{EXPECTED_PRIMARY_TRIGGERS}] {market.ticker}")

    expected_rows = EXPECTED_PRIMARY_TRIGGERS * len(scenario_grid()) * len(RISK_POLICIES)
    if len(rows) != expected_rows:
        raise DeltaRiskError(f"expected {expected_rows} scenarios; found {len(rows)}")
    verify_baseline_reproduction(prior, rows)
    summary = summarize(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_h3_delta_risk_scenarios.csv", rows)
    write_csv(args.output_dir / "kxbtc15m_h3_delta_risk_summary.csv", summary)
    report_path = args.output_dir / "KXBTC15M_H3_DELTA_RISK.md"
    report_path.write_text(markdown_report(summary), encoding="utf-8")

    print("KXBTC15M H3 causal delta-risk diagnostic: PASS")
    print(f"Frozen primary triggers: {EXPECTED_PRIMARY_TRIGGERS}")
    print(f"Risk policies: {len(RISK_POLICIES)}")
    print(f"Latency settings: {len(scenario_grid())}")
    print(f"Matched scenario rows: {len(rows)}")
    print("Prior latency reproduction: PASS")
    print("Causal Kalshi live-data rows validated: 345696")
    print("Authenticated Kalshi data used: no")
    print("External BTC data used: no")
    print("Holdout read: False")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (
        AuditError, DeltaRiskError, ExitPolicyError, OSError, SimulationError,
        ValueError, json.JSONDecodeError,
    ) as exc:
        raise SystemExit(f"H3 delta-risk error: {exc}") from exc
