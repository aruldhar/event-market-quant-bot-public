#!/usr/bin/env python3
"""Describe native 5-7.5m paths behind H3 initial-state entries.

The subgroup is defined by a future observation: the first native response in
the frozen 4-to-5-minute window is already in the 90%-to-below-98% favored
band.  Consequently, every earlier-entry result in this module is labelled as
a lookahead-selected development counterfactual, never as a causal rule.
"""

from __future__ import annotations

import argparse
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
    Snapshot,
    buy_with_budget,
    first_index_at_or_after,
    load_outcomes,
    validate_fee_inputs,
    write_csv,
)
from analyze_kxbtc15m_h3_frequency import (
    HIGH_EXCLUSIVE,
    LOW,
    TARGET_FRACTION,
    _raw_snapshot_sets,
    simulate_market as simulate_frequency_market,
)
from analyze_kxbtc15m_h3_late_convergence import favored_quote
from analyze_kxbtc15m_h3_native_exit_policies import (
    BASELINE_POLICY,
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
    safe_extract_zip,
    select_development_manifests,
)


LOOKBACK_START_SECONDS = 450
LOOKBACK_END_SECONDS = 300
EXPECTED_NATIVE_ENTRIES = 57
EXPECTED_INITIAL_STATE_ENTRIES = 35
PERSISTENCE_MILESTONES_SECONDS = (5, 15, 30, 60)
BASELINE = "baseline_4_5m_initial_state"
FIRST_EARLIER = "first_same_side_band_5_7_5m"
FINAL_EPISODE_START = "final_episode_start_lookahead"


class InitialStateLookbackError(RuntimeError):
    """Raised when the initial-state lookback diagnostic fails closed."""


def relative_state(snapshot: Snapshot, baseline_side: str) -> str:
    """Classify a native observation relative to the later baseline side."""
    quote = favored_quote(snapshot.book)
    if quote is None:
        return "unavailable"
    side, midpoint, _ask = quote
    if side != baseline_side:
        return "other_favored_side"
    if midpoint < LOW:
        return "same_side_below_band"
    if midpoint >= HIGH_EXCLUSIVE:
        return "same_side_above_band"
    return "same_side_in_band"


def band_episodes(
    snapshots: Sequence[Snapshot],
    *,
    baseline_side: str,
    start_time: datetime,
    stop_index: int,
) -> list[dict[str, Any]]:
    """Return consecutive same-side in-band episodes through stop_index."""
    indices = [
        index for index in range(stop_index + 1)
        if snapshots[index].observed_at >= start_time
    ]
    episodes: list[dict[str, Any]] = []
    active: list[int] = []
    for index in indices:
        if relative_state(snapshots[index], baseline_side) == "same_side_in_band":
            active.append(index)
            continue
        if active:
            episodes.append(_episode_row(snapshots, active, stop_index))
            active = []
    if active:
        episodes.append(_episode_row(snapshots, active, stop_index))
    return episodes


def _episode_row(
    snapshots: Sequence[Snapshot], indices: Sequence[int], stop_index: int
) -> dict[str, Any]:
    start = snapshots[indices[0]].observed_at
    end = snapshots[indices[-1]].observed_at
    return {
        "start_index": indices[0],
        "end_index": indices[-1],
        "start_time": start,
        "end_time": end,
        "observations": len(indices),
        "observed_span_seconds": (end - start).total_seconds(),
        "reaches_baseline_decision": indices[-1] == stop_index,
    }


def final_episode_start_index(
    snapshots: Sequence[Snapshot], decision_index: int, baseline_side: str
) -> int:
    """Find the start of the consecutive band episode containing the baseline."""
    if relative_state(snapshots[decision_index], baseline_side) != "same_side_in_band":
        raise InitialStateLookbackError("baseline decision is not same-side in-band")
    index = decision_index
    while (
        index > 0
        and relative_state(snapshots[index - 1], baseline_side)
        == "same_side_in_band"
    ):
        index -= 1
    return index


def entry_context(
    snapshots: Sequence[Snapshot],
    *,
    decision_index: int,
    required_side: str,
    execution_deadline: datetime | None,
) -> tuple[int, int, str, Decimal, Decimal, Any] | None:
    """Build the standard one-second, full-depth H3 entry context."""
    decision = snapshots[decision_index]
    quote = favored_quote(decision.book)
    if quote is None:
        return None
    side, midpoint, ask = quote
    if side != required_side or not (LOW <= midpoint < HIGH_EXCLUSIVE):
        return None
    fill_index = first_index_at_or_after(
        snapshots,
        decision_index + 1,
        decision.observed_at + timedelta(seconds=LATENCY_SECONDS),
    )
    if fill_index is None:
        return None
    if execution_deadline is not None and snapshots[fill_index].observed_at >= execution_deadline:
        return None
    entry = buy_with_budget(snapshots[fill_index].book.ask_levels(side), MAX_BUDGET)
    if entry.quantity <= 0 or entry.quantity - entry.buy_outflow <= 0:
        return None
    return decision_index, fill_index, side, midpoint, ask, entry


def first_earlier_context(
    snapshots: Sequence[Snapshot],
    *,
    close_time: datetime,
    required_side: str,
) -> tuple[int, int, str, Decimal, Decimal, Any] | None:
    begin = close_time - timedelta(seconds=LOOKBACK_START_SECONDS)
    boundary = close_time - timedelta(seconds=LOOKBACK_END_SECONDS)
    for index, snapshot in enumerate(snapshots):
        if snapshot.observed_at < begin:
            continue
        if snapshot.observed_at >= boundary:
            break
        context = entry_context(
            snapshots,
            decision_index=index,
            required_side=required_side,
            execution_deadline=boundary,
        )
        if context is not None:
            return context
    return None


def milestone_context(
    snapshots: Sequence[Snapshot],
    *,
    episode_start_index: int,
    episode_end_index: int,
    required_side: str,
    elapsed_seconds: int,
    execution_deadline: datetime,
) -> tuple[int, int, str, Decimal, Decimal, Any] | None:
    target = snapshots[episode_start_index].observed_at + timedelta(seconds=elapsed_seconds)
    for index in range(episode_start_index, episode_end_index + 1):
        snapshot = snapshots[index]
        if snapshot.observed_at < target:
            continue
        if snapshot.observed_at >= execution_deadline:
            return None
        return entry_context(
            snapshots,
            decision_index=index,
            required_side=required_side,
            execution_deadline=execution_deadline,
        )
    return None


def _transition_count(states: Sequence[str], predicate: Any) -> int:
    return sum(predicate(left, right) for left, right in zip(states, states[1:]))


def path_row(
    *,
    ticker: str,
    segment: str,
    snapshots: Sequence[Snapshot],
    close_time: datetime,
    baseline: Mapping[str, Any],
    decision_index: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    side = str(baseline["side"])
    begin = close_time - timedelta(seconds=LOOKBACK_START_SECONDS)
    boundary = close_time - timedelta(seconds=LOOKBACK_END_SECONDS)
    before_boundary = [
        index for index, snapshot in enumerate(snapshots)
        if begin <= snapshot.observed_at < boundary
    ]
    states = [relative_state(snapshots[index], side) for index in before_boundary]
    usable = [state for state in states if state != "unavailable"]
    same_side = [state for state in usable if state != "other_favored_side"]
    in_band = [state for state in usable if state == "same_side_in_band"]
    final_start = final_episode_start_index(snapshots, decision_index, side)
    final_start_time = snapshots[final_start].observed_at
    age = (snapshots[decision_index].observed_at - final_start_time).total_seconds()
    episodes = band_episodes(
        snapshots,
        baseline_side=side,
        start_time=begin,
        stop_index=decision_index,
    )
    episode_rows: list[dict[str, Any]] = []
    for number, episode in enumerate(episodes, start=1):
        episode_rows.append({
            "ticker": ticker,
            "diagnostic_segment": segment,
            "episode_number": number,
            "start_time": episode["start_time"].isoformat(),
            "end_time": episode["end_time"].isoformat(),
            "start_seconds_remaining": (
                close_time - episode["start_time"]
            ).total_seconds(),
            "end_seconds_remaining": (
                close_time - episode["end_time"]
            ).total_seconds(),
            "observations": episode["observations"],
            "observed_span_seconds": episode["observed_span_seconds"],
            "reaches_baseline_decision": episode["reaches_baseline_decision"],
            "future_defined_subgroup": True,
            "holdout_read": False,
        })
    coverage = 0.0
    if before_boundary:
        covered_begin = max(begin, snapshots[before_boundary[0]].observed_at)
        covered_end = min(boundary, snapshots[before_boundary[-1]].observed_at)
        coverage = max(0.0, (covered_end - covered_begin).total_seconds()) / (
            LOOKBACK_START_SECONDS - LOOKBACK_END_SECONDS
        )
    first_band_index = next(
        (
            index for index in before_boundary
            if relative_state(snapshots[index], side) == "same_side_in_band"
        ),
        None,
    )
    first_seconds = (
        (close_time - snapshots[first_band_index].observed_at).total_seconds()
        if first_band_index is not None else math.nan
    )
    row = {
        "ticker": ticker,
        "diagnostic_segment": segment,
        "future_defined_subgroup": "initial_state_at_5m",
        "baseline_side": side,
        "baseline_decision_time": baseline["decision_time"],
        "baseline_decision_seconds_remaining": baseline["seconds_remaining"],
        "baseline_entry_execution_time": baseline["entry_execution_time"],
        "baseline_pnl": baseline["pnl"],
        "baseline_favored_side_won": baseline["favored_side_won"],
        "lookback_start_seconds_remaining": LOOKBACK_START_SECONDS,
        "lookback_end_seconds_remaining_exclusive": LOOKBACK_END_SECONDS,
        "lookback_coverage_rate": min(1.0, coverage),
        "lookback_native_observations": len(before_boundary),
        "lookback_usable_quote_observations": len(usable),
        "lookback_in_band_observations": len(in_band),
        "lookback_in_band_observation_fraction": (
            len(in_band) / len(usable) if usable else math.nan
        ),
        "lookback_same_side_observation_fraction": (
            len(same_side) / len(usable) if usable else math.nan
        ),
        "lookback_band_episode_count": sum(
            episode["start_time"] < boundary for episode in episodes
        ),
        "lookback_band_exit_count": _transition_count(
            states,
            lambda left, right: left == "same_side_in_band"
            and right != "same_side_in_band",
        ),
        "lookback_side_change_count": _transition_count(
            states,
            lambda left, right: (
                left == "other_favored_side"
            ) != (right == "other_favored_side"),
        ),
        "lookback_below_band_observations": states.count("same_side_below_band"),
        "lookback_above_band_observations": states.count("same_side_above_band"),
        "lookback_other_side_observations": states.count("other_favored_side"),
        "first_same_side_band_seconds_remaining": first_seconds,
        "final_episode_start_time": final_start_time.isoformat(),
        "final_episode_start_seconds_remaining": (
            close_time - final_start_time
        ).total_seconds(),
        "final_episode_age_at_baseline_seconds": age,
        "final_episode_observations_through_baseline": decision_index - final_start + 1,
        "final_episode_censored_at_7_5m": final_start_time <= begin,
        "final_episode_started_before_5m": final_start_time < boundary,
        "holdout_read": False,
        "external_btc_data_used": False,
        "orders_placed": False,
    }
    return row, episode_rows, final_start


def _counterfactual_base(
    *, ticker: str, segment: str, policy: str, baseline_pnl: str
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "diagnostic_segment": segment,
        "policy": policy,
        "status": "no_earlier_entry",
        "entry_filled": False,
        "pnl": "",
        "baseline_pnl": baseline_pnl,
        "future_defined_subgroup": True,
        "lookahead_selected_episode": policy != FIRST_EARLIER and policy != BASELINE,
        "holdout_read": False,
        "external_btc_data_used": False,
        "orders_placed": False,
    }


def _counterfactual_row(
    *,
    ticker: str,
    segment: str,
    policy: str,
    baseline: Mapping[str, Any],
    snapshots: Sequence[Snapshot],
    close_time: datetime,
    winning_side: str,
    context: tuple[int, int, str, Decimal, Decimal, Any] | None,
) -> dict[str, Any]:
    row = _counterfactual_base(
        ticker=ticker,
        segment=segment,
        policy=policy,
        baseline_pnl=str(baseline["pnl"]),
    )
    if policy == BASELINE:
        row.update(dict(baseline))
        row.update({
            "policy": policy,
            "baseline_pnl": baseline["pnl"],
            "future_defined_subgroup": True,
            "lookahead_selected_episode": False,
        })
        return row
    simulated = simulate_policy(
        snapshots=snapshots,
        close_time=close_time,
        winning_side=winning_side,
        ticker=ticker,
        segment=segment,
        policy=policy,
        kind="fraction",
        value=TARGET_FRACTION,
        entry_context=context,
    )
    row.update(simulated)
    row.update({
        "policy": policy,
        "baseline_pnl": baseline["pnl"],
        "future_defined_subgroup": True,
        "lookahead_selected_episode": policy != FIRST_EARLIER,
        "holdout_read": False,
        "external_btc_data_used": False,
        "orders_placed": False,
    })
    return row


def analyze_selected_market(
    *,
    ticker: str,
    segment: str,
    snapshots: Sequence[Snapshot],
    close_time: datetime,
    winning_side: str,
    frequency_row: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    native_context = find_native_entry(snapshots, close_time)
    baseline = simulate_policy(
        snapshots=snapshots,
        close_time=close_time,
        winning_side=winning_side,
        ticker=ticker,
        segment=segment,
        policy=BASELINE_POLICY,
        kind="fraction",
        value=TARGET_FRACTION,
        entry_context=native_context,
    )
    verify_baseline_reproduction(baseline, frequency_row)
    if native_context is None:
        raise InitialStateLookbackError(f"{ticker}: selected market lacks native entry")
    decision_index = native_context[0]
    path, episodes, final_start = path_row(
        ticker=ticker,
        segment=segment,
        snapshots=snapshots,
        close_time=close_time,
        baseline=baseline,
        decision_index=decision_index,
    )
    boundary = close_time - timedelta(seconds=LOOKBACK_END_SECONDS)
    side = str(baseline["side"])
    contexts: list[tuple[str, Any]] = [
        (BASELINE, native_context),
        (
            FIRST_EARLIER,
            first_earlier_context(
                snapshots,
                close_time=close_time,
                required_side=side,
            ),
        ),
        (
            FINAL_EPISODE_START,
            entry_context(
                snapshots,
                decision_index=final_start,
                required_side=side,
                execution_deadline=boundary,
            ),
        ),
    ]
    for seconds in PERSISTENCE_MILESTONES_SECONDS:
        contexts.append((
            f"final_episode_after_{seconds}s_lookahead",
            milestone_context(
                snapshots,
                episode_start_index=final_start,
                episode_end_index=decision_index,
                required_side=side,
                elapsed_seconds=seconds,
                execution_deadline=boundary,
            ),
        ))
    counterfactuals = [
        _counterfactual_row(
            ticker=ticker,
            segment=segment,
            policy=policy,
            baseline=baseline,
            snapshots=snapshots,
            close_time=close_time,
            winning_side=winning_side,
            context=context,
        )
        for policy, context in contexts
    ]
    first_row = next(row for row in counterfactuals if row["policy"] == FIRST_EARLIER)
    path["first_earlier_entry_filled"] = bool(first_row["entry_filled"])
    path["first_earlier_pnl"] = first_row["pnl"]
    path["first_earlier_increment_vs_baseline"] = (
        float(first_row["pnl"]) - float(baseline["pnl"])
        if first_row["entry_filled"] else math.nan
    )
    return path, episodes, counterfactuals


def _policy_order() -> list[str]:
    return [
        BASELINE,
        FIRST_EARLIER,
        FINAL_EPISODE_START,
        *(f"final_episode_after_{seconds}s_lookahead" for seconds in PERSISTENCE_MILESTONES_SECONDS),
    ]


def summarize_counterfactuals(
    rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment in ("all_35", "earlier_64_diagnostic", "later_32_diagnostic"):
        source = list(rows) if segment == "all_35" else [
            row for row in rows
            if row["diagnostic_segment"]
            == ("earlier_64" if segment.startswith("earlier") else "later_32")
        ]
        baseline = {
            str(row["ticker"]): float(row["pnl"])
            for row in source if row["policy"] == BASELINE
        }
        for policy in _policy_order():
            selected = [row for row in source if row["policy"] == policy]
            completed = [row for row in selected if row["status"] == "completed"]
            pnl_market = [float(row["pnl"] or 0.0) for row in selected]
            estimate, low, high = _bootstrap(pnl_market)
            differences = [
                float(row["pnl"] or 0.0) - baseline[str(row["ticker"])]
                for row in selected
            ]
            difference, diff_low, diff_high = _bootstrap(differences)
            pnl_filled = [float(row["pnl"]) for row in completed]
            output.append({
                "segment": segment,
                "policy": policy,
                "future_defined_markets": len(selected),
                "earlier_entries": len(completed) if policy != BASELINE else 0,
                "completed_entries": len(completed),
                "mean_pnl_per_future_defined_market": estimate,
                "bootstrap_ci_low_per_future_defined_market": low,
                "bootstrap_ci_high_per_future_defined_market": high,
                "mean_increment_vs_baseline": difference,
                "paired_difference_ci_low": diff_low,
                "paired_difference_ci_high": diff_high,
                "mean_pnl_per_filled_entry": _mean(pnl_filled),
                "profitable_rate_per_filled_entry": _mean(
                    [bool(row["profitable"]) for row in completed]
                ),
                "protected_target_rate": _mean(
                    [bool(row["target_filled"]) for row in completed]
                ),
                "full_loss_rate": _mean(
                    [bool(row["full_capital_loss"]) for row in completed]
                ),
                "pnl_05_quantile": _quantile(pnl_filled, 0.05),
                "worst_pnl": min(pnl_filled) if pnl_filled else math.nan,
                "lookahead_selected": policy not in (BASELINE, FIRST_EARLIER),
                "holdout_read": False,
            })
    return output


def _ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        rank = (cursor + 1 + end) / 2.0
        for original, _value in indexed[cursor:end]:
            ranks[original] = rank
        cursor = end
    return ranks


def spearman(values_x: Sequence[float], values_y: Sequence[float]) -> float:
    if len(values_x) != len(values_y) or len(values_x) < 3:
        return math.nan
    ranks_x = _ranks(values_x)
    ranks_y = _ranks(values_y)
    mean_x = statistics.mean(ranks_x)
    mean_y = statistics.mean(ranks_y)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(ranks_x, ranks_y))
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x in ranks_x)
        * sum((y - mean_y) ** 2 for y in ranks_y)
    )
    return numerator / denominator if denominator else math.nan


def _bootstrap_spearman(pairs: Sequence[tuple[float, float]]) -> tuple[float, float, float]:
    estimate = spearman([pair[0] for pair in pairs], [pair[1] for pair in pairs])
    if len(pairs) < 4 or math.isnan(estimate):
        return estimate, math.nan, math.nan
    rng = random.Random(20260813)
    draws: list[float] = []
    for _ in range(2_000):
        sample = rng.choices(pairs, k=len(pairs))
        value = spearman([pair[0] for pair in sample], [pair[1] for pair in sample])
        if not math.isnan(value):
            draws.append(value)
    if not draws:
        return estimate, math.nan, math.nan
    draws.sort()
    return estimate, draws[max(0, math.ceil(0.025 * len(draws)) - 1)], draws[
        max(0, math.ceil(0.975 * len(draws)) - 1)
    ]


CORRELATION_FEATURES = (
    "final_episode_age_at_baseline_seconds",
    "lookback_in_band_observation_fraction",
    "lookback_same_side_observation_fraction",
    "lookback_band_episode_count",
    "lookback_side_change_count",
    "first_same_side_band_seconds_remaining",
)
CORRELATION_OUTCOMES = (
    "first_earlier_pnl",
    "first_earlier_increment_vs_baseline",
)


def correlation_table(path_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment in ("all_35", "earlier_64_diagnostic", "later_32_diagnostic"):
        source = list(path_rows) if segment == "all_35" else [
            row for row in path_rows
            if row["diagnostic_segment"]
            == ("earlier_64" if segment.startswith("earlier") else "later_32")
        ]
        for feature in CORRELATION_FEATURES:
            for outcome in CORRELATION_OUTCOMES:
                pairs: list[tuple[float, float]] = []
                for row in source:
                    try:
                        x = float(row[feature])
                        y = float(row[outcome])
                    except (TypeError, ValueError):
                        continue
                    if math.isnan(x) or math.isnan(y):
                        continue
                    pairs.append((x, y))
                estimate, low, high = _bootstrap_spearman(pairs)
                output.append({
                    "segment": segment,
                    "feature": feature,
                    "outcome": outcome,
                    "markets": len(pairs),
                    "spearman_rho": estimate,
                    "bootstrap_ci_low": low,
                    "bootstrap_ci_high": high,
                    "future_defined_subgroup": True,
                    "holdout_read": False,
                })
    return output


def verify_results(
    path_rows: Sequence[Mapping[str, Any]],
    counterfactuals: Sequence[Mapping[str, Any]],
    native_entry_count: int,
) -> None:
    if native_entry_count != EXPECTED_NATIVE_ENTRIES:
        raise InitialStateLookbackError(
            f"expected 57 native entries; found {native_entry_count}"
        )
    if len(path_rows) != EXPECTED_INITIAL_STATE_ENTRIES:
        raise InitialStateLookbackError(
            f"expected 35 initial-state entries; found {len(path_rows)}"
        )
    expected_rows = len(path_rows) * len(_policy_order())
    if len(counterfactuals) != expected_rows:
        raise InitialStateLookbackError("counterfactual row-count mismatch")
    for row in path_rows:
        if float(row["lookback_coverage_rate"]) < 0.95:
            raise InitialStateLookbackError(
                f"{row['ticker']}: insufficient native 5-7.5m lookback coverage"
            )


def _number(value: Any, digits: int = 2) -> str:
    number = float(value)
    return "n/a" if math.isnan(number) else f"{number:.{digits}f}"


def markdown_report(
    path_rows: Sequence[Mapping[str, Any]],
    counterfactual_summary: Sequence[Mapping[str, Any]],
    correlations: Sequence[Mapping[str, Any]],
) -> str:
    all_rows = [row for row in counterfactual_summary if row["segment"] == "all_35"]
    filled_earlier = sum(bool(row["first_earlier_entry_filled"]) for row in path_rows)
    ages = [float(row["final_episode_age_at_baseline_seconds"]) for row in path_rows]
    episode_counts = [int(row["lookback_band_episode_count"]) for row in path_rows]
    side_changes = [int(row["lookback_side_change_count"]) for row in path_rows]
    lines = [
        "# KXBTC15M H3 initial-state native lookback diagnostic",
        "",
        "**Descriptive adaptive development test; future-defined subgroup; holdout sealed.**",
        "",
        "This report traces the native 5-to-7.5-minute histories of the 35 entries whose "
        "first causal observation inside the frozen 4-to-5-minute window was already in the "
        "90%-to-below-98% favored band. The subgroup label is known only at five minutes, so "
        "none of the earlier-entry rows is a deployable strategy.",
        "",
        "## Lookback structure",
        "",
        f"- Initial-state entries: {len(path_rows)} of 57 native H3 entries.",
        f"- Same-side earlier band opportunity: {filled_earlier} of {len(path_rows)}.",
        f"- Median age of the final in-band episode at baseline: {statistics.median(ages):.1f}s.",
        f"- Median same-side band episodes in the lookback: {statistics.median(episode_counts):.1f}.",
        f"- Markets with at least one favored-side change: {sum(value > 0 for value in side_changes)}.",
        "",
        "## Lookahead-selected earlier-entry counterfactuals",
        "",
        "Every row retains one-second latency, full archived depth, fees, $100 maximum sizing, "
        "the protected 50%-of-maximum target, and the ten-second preclose fallback. Missing "
        "earlier entries count as $0 in mean P&L per future-defined market.",
        "",
        "| Counterfactual | Earlier entries | Mean / selected market | 95% CI | Increment vs baseline | Paired 95% CI | Mean / fill | Profitable | Target | Full loss | Worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in all_rows:
        lines.append(
            f"| {row['policy']} | {row['earlier_entries']} | "
            f"{_money(row['mean_pnl_per_future_defined_market'])} | "
            f"{_money(row['bootstrap_ci_low_per_future_defined_market'])} to "
            f"{_money(row['bootstrap_ci_high_per_future_defined_market'])} | "
            f"{_money(row['mean_increment_vs_baseline'])} | "
            f"{_money(row['paired_difference_ci_low'])} to "
            f"{_money(row['paired_difference_ci_high'])} | "
            f"{_money(row['mean_pnl_per_filled_entry'])} | "
            f"{_percent(row['profitable_rate_per_filled_entry'])} | "
            f"{_percent(row['protected_target_rate'])} | "
            f"{_percent(row['full_loss_rate'])} | {_money(row['worst_pnl'])} |"
        )
    lines.extend([
        "",
        "`first_same_side_band_5_7_5m` uses the first earlier same-side band observation but "
        "is evaluated only inside the future-defined 35-market subgroup. The final-episode "
        "rows additionally know which episode survives until the baseline observation; they "
        "are diagnostic upper-bound descriptions, not causal policies.",
        "",
        "## Rank correlations with the first-earlier counterfactual",
        "",
        "Spearman correlations below use path descriptors from the native lookback. Wide "
        "intervals, disagreement between chronological segments, or small sample sizes are "
        "evidence against defining a persistence rule.",
        "",
        "| Feature | Outcome | Markets | Rho | Bootstrap 95% CI | Earlier-64 rho | Later-32 rho |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    all_correlations = [row for row in correlations if row["segment"] == "all_35"]
    lookup = {
        (str(row["segment"]), str(row["feature"]), str(row["outcome"])): row
        for row in correlations
    }
    for row in all_correlations:
        earlier = lookup[("earlier_64_diagnostic", row["feature"], row["outcome"])]
        later = lookup[("later_32_diagnostic", row["feature"], row["outcome"])]
        lines.append(
            f"| {row['feature']} | {row['outcome']} | {row['markets']} | "
            f"{_number(row['spearman_rho'])} | {_number(row['bootstrap_ci_low'])} to "
            f"{_number(row['bootstrap_ci_high'])} | {_number(earlier['spearman_rho'])} | "
            f"{_number(later['spearman_rho'])} |"
        )
    lines.extend([
        "",
        "A causal earlier-entry strategy must next be defined and tested across all 96 markets "
        "using only information available at its decision time. These results may motivate "
        "one bounded rule, but they cannot validate it. No external BTC data, authentication, "
        "order, or holdout observation is used.",
    ])
    return "\n".join(lines)


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
        default=Path("analysis/kxbtc15m_h3_initial_state_lookback"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    path_rows: list[dict[str, Any]] = []
    episode_rows: list[dict[str, Any]] = []
    counterfactuals: list[dict[str, Any]] = []
    native_entry_count = 0
    with TemporaryDirectory(prefix="kxbtc15m_initial_state_lookback_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise InitialStateLookbackError(
                f"expected 96 eligible markets; found {len(eligible)}"
            )
        if set(outcomes) != {market.ticker for market in eligible}:
            raise InitialStateLookbackError("development outcome ticker mismatch")
        for number, market in enumerate(eligible, start=1):
            _legacy, snapshots = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            segment = "earlier_64" if market.index <= 64 else "later_32"
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
            if frequency["status"] == "completed":
                native_entry_count += 1
            if not (
                frequency["status"] == "completed"
                and frequency.get("signal_origin") == "initial_state"
            ):
                print(f"[{number:02d}/96] {market.ticker} not selected")
                continue
            path, episodes, rows = analyze_selected_market(
                ticker=market.ticker,
                segment=segment,
                snapshots=snapshots,
                close_time=close,
                winning_side=outcomes[market.ticker],
                frequency_row=frequency,
            )
            path_rows.append(path)
            episode_rows.extend(episodes)
            counterfactuals.extend(rows)
            print(f"[{number:02d}/96] {market.ticker} initial_state")
    verify_results(path_rows, counterfactuals, native_entry_count)
    summary = summarize_counterfactuals(counterfactuals)
    correlations = correlation_table(path_rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_h3_initial_state_paths.csv", path_rows)
    write_csv(args.output_dir / "kxbtc15m_h3_initial_state_episodes.csv", episode_rows)
    write_csv(
        args.output_dir / "kxbtc15m_h3_initial_state_counterfactuals.csv",
        counterfactuals,
    )
    write_csv(
        args.output_dir / "kxbtc15m_h3_initial_state_counterfactual_summary.csv",
        summary,
    )
    write_csv(
        args.output_dir / "kxbtc15m_h3_initial_state_correlations.csv",
        correlations,
    )
    report_path = args.output_dir / "KXBTC15M_H3_INITIAL_STATE_LOOKBACK.md"
    report_path.write_text(
        markdown_report(path_rows, summary, correlations), encoding="utf-8"
    )
    print("KXBTC15M H3 initial-state native lookback diagnostic: PASS")
    print("Eligible development markets: 96")
    print("Native H3 entries reproduced: 57")
    print("Initial-state subgroup reproduced: 35")
    print("Lookback: native 5-7.5 minutes")
    print("Future-defined subgroup: True")
    print("Holdout read: False")
    print("Orders placed: False")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (
        AuditError,
        InitialStateLookbackError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise SystemExit(f"KXBTC15M H3 initial-state lookback error: {exc}") from exc
