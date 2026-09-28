#!/usr/bin/env python3
"""Test a preregistered causal early-entry persistence ladder for H3."""

from __future__ import annotations

import argparse
import json
import math
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
    simulate_window,
)
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    safe_extract_zip,
    select_development_manifests,
)


EARLY_START_SECONDS = 450
EARLY_END_SECONDS = 300
THRESHOLDS_SECONDS = (0, 1, 2, 5)
EXPECTED_NATIVE_ENTRIES = 57
EXPECTED_IMMEDIATE_EARLY_ENTRIES = 52
BASELINE = "baseline_4_5m"
HISTORICAL_CONTROL = "historical_immediate_5_7_5m_decision_window"


class EarlyPersistenceError(RuntimeError):
    """Raised when the causal persistence diagnostic fails closed."""


def _qualifying_quote(snapshot: Snapshot) -> tuple[str, Decimal, Decimal] | None:
    quote = favored_quote(snapshot.book)
    if quote is None:
        return None
    side, midpoint, ask = quote
    return quote if LOW <= midpoint < HIGH_EXCLUSIVE else None


def find_persistent_entry(
    snapshots: Sequence[Snapshot],
    *,
    close_time: datetime,
    threshold_seconds: int,
    require_fill_before_boundary: bool = True,
) -> tuple[tuple[int, int, str, Decimal, Decimal, Any] | None, dict[str, Any]]:
    """Find the first uninterrupted native in-band episode reaching threshold."""
    if threshold_seconds not in THRESHOLDS_SECONDS:
        raise EarlyPersistenceError(f"undeclared persistence threshold: {threshold_seconds}")
    begin = close_time - timedelta(seconds=EARLY_START_SECONDS)
    boundary = close_time - timedelta(seconds=EARLY_END_SECONDS)
    armed_side: str | None = None
    armed_at: datetime | None = None
    episode_observations = 0
    diagnostics = {
        "threshold_seconds": threshold_seconds,
        "early_window_native_observations": 0,
        "episodes_armed": 0,
        "episode_resets": 0,
        "persistent_signal_seen": False,
        "entry_rejected_after_cutoff": False,
        "entry_rejected_unfilled": False,
        "confirmation_observations": 0,
        "confirmation_elapsed_seconds": "",
        "strict_fill_before_5m": require_fill_before_boundary,
        "entry_crossed_5m_boundary": False,
    }
    for decision_index, decision in enumerate(snapshots):
        if decision.observed_at < begin:
            continue
        if decision.observed_at >= boundary:
            break
        diagnostics["early_window_native_observations"] += 1
        quote = _qualifying_quote(decision)
        if quote is None:
            if armed_side is not None:
                diagnostics["episode_resets"] += 1
            armed_side = None
            armed_at = None
            episode_observations = 0
            continue
        side, midpoint, ask = quote
        if armed_side != side:
            if armed_side is not None:
                diagnostics["episode_resets"] += 1
            armed_side = side
            armed_at = decision.observed_at
            episode_observations = 1
            diagnostics["episodes_armed"] += 1
        else:
            episode_observations += 1
        assert armed_at is not None
        elapsed = (decision.observed_at - armed_at).total_seconds()
        if elapsed < threshold_seconds:
            continue
        diagnostics["persistent_signal_seen"] = True
        diagnostics["confirmation_observations"] = episode_observations
        diagnostics["confirmation_elapsed_seconds"] = f"{elapsed:.6f}"
        fill_index = first_index_at_or_after(
            snapshots,
            decision_index + 1,
            decision.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        deadline = boundary if require_fill_before_boundary else close_time
        if fill_index is None or snapshots[fill_index].observed_at >= deadline:
            diagnostics["entry_rejected_after_cutoff"] = True
            return None, diagnostics
        diagnostics["entry_crossed_5m_boundary"] = (
            snapshots[fill_index].observed_at >= boundary
        )
        entry = buy_with_budget(
            snapshots[fill_index].book.ask_levels(side), MAX_BUDGET
        )
        if entry.quantity <= 0 or entry.quantity - entry.buy_outflow <= 0:
            diagnostics["entry_rejected_unfilled"] = True
            return None, diagnostics
        return (
            decision_index,
            fill_index,
            side,
            midpoint,
            ask,
            entry,
        ), diagnostics
    return None, diagnostics


def _policy_name(threshold: int, combined: bool) -> str:
    suffix = "early_else_baseline" if combined else "early_only"
    return f"persistent_{threshold}s_{suffix}"


def policy_order() -> list[str]:
    return [
        BASELINE,
        HISTORICAL_CONTROL,
        *(_policy_name(threshold, False) for threshold in THRESHOLDS_SECONDS),
        *(_policy_name(threshold, True) for threshold in THRESHOLDS_SECONDS),
    ]


def _decorate(
    simulation: Mapping[str, Any],
    *,
    policy: str,
    threshold: int | str,
    variant: str,
    entry_source: str,
    diagnostics: Mapping[str, Any],
) -> dict[str, Any]:
    row = dict(simulation)
    row.update({
        "policy": policy,
        "persistence_threshold_seconds": threshold,
        "variant": variant,
        "entry_source": entry_source,
        "maximum_cycles": 1,
        "profit_compounded": False,
        "future_information_used": False,
        "holdout_read": False,
        "external_btc_data_used": False,
        "orders_placed": False,
    })
    row.update(diagnostics)
    return row


def simulate_market_policies(
    *,
    snapshots: Sequence[Snapshot],
    close_time: datetime,
    winning_side: str,
    ticker: str,
    segment: str,
) -> tuple[list[dict[str, Any]], Mapping[str, Any], Mapping[str, Any]]:
    baseline_context = find_native_entry(snapshots, close_time)
    baseline_simulation = simulate_policy(
        snapshots=snapshots,
        close_time=close_time,
        winning_side=winning_side,
        ticker=ticker,
        segment=segment,
        policy=BASELINE_POLICY,
        kind="fraction",
        value=TARGET_FRACTION,
        entry_context=baseline_context,
    )
    rows = [
        _decorate(
            baseline_simulation,
            policy=BASELINE,
            threshold="",
            variant="baseline",
            entry_source=(
                "baseline_4_5m"
                if baseline_simulation["status"] == "completed" else "none"
            ),
            diagnostics={},
        )
    ]
    historical_context, historical_diagnostics = find_persistent_entry(
        snapshots,
        close_time=close_time,
        threshold_seconds=0,
        require_fill_before_boundary=False,
    )
    historical_simulation = simulate_policy(
        snapshots=snapshots,
        close_time=close_time,
        winning_side=winning_side,
        ticker=ticker,
        segment=segment,
        policy=BASELINE_POLICY,
        kind="fraction",
        value=TARGET_FRACTION,
        entry_context=historical_context,
    )
    rows.append(_decorate(
        historical_simulation,
        policy=HISTORICAL_CONTROL,
        threshold=0,
        variant="historical_control",
        entry_source=(
            "historical_early_5_7_5m"
            if historical_simulation["status"] == "completed" else "none"
        ),
        diagnostics=historical_diagnostics,
    ))
    for threshold in THRESHOLDS_SECONDS:
        early_context, diagnostics = find_persistent_entry(
            snapshots,
            close_time=close_time,
            threshold_seconds=threshold,
        )
        early = simulate_policy(
            snapshots=snapshots,
            close_time=close_time,
            winning_side=winning_side,
            ticker=ticker,
            segment=segment,
            policy=BASELINE_POLICY,
            kind="fraction",
            value=TARGET_FRACTION,
            entry_context=early_context,
        )
        rows.append(_decorate(
            early,
            policy=_policy_name(threshold, False),
            threshold=threshold,
            variant="early_only",
            entry_source="early_5_7_5m" if early["status"] == "completed" else "none",
            diagnostics=diagnostics,
        ))
        selected = early if early["status"] == "completed" else baseline_simulation
        if early["status"] == "completed":
            source = "early_5_7_5m"
        elif baseline_simulation["status"] == "completed":
            source = "fallback_4_5m"
        else:
            source = "none"
        rows.append(_decorate(
            selected,
            policy=_policy_name(threshold, True),
            threshold=threshold,
            variant="early_else_baseline",
            entry_source=source,
            diagnostics=diagnostics,
        ))
    return rows, baseline_simulation, historical_simulation


def verify_immediate_reproduction(
    immediate: Mapping[str, Any], window: Mapping[str, Any]
) -> None:
    fields = (
        "status",
        "triggered",
        "entry_filled",
        "decision_time",
        "entry_execution_time",
        "exit_reason",
        "pnl",
    )
    mismatches = [
        field for field in fields
        if immediate.get(field, "") != window.get(field, "")
    ]
    if mismatches:
        raise EarlyPersistenceError(
            f"{window['ticker']}: immediate 5-7.5m reproduction mismatch: {mismatches}"
        )


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        source = list(rows) if segment == "all_96" else [
            row for row in rows
            if row["diagnostic_segment"]
            == ("earlier_64" if segment.startswith("earlier") else "later_32")
        ]
        baseline = {
            str(row["ticker"]): float(row["pnl"] or 0.0)
            for row in source if row["policy"] == BASELINE
        }
        for policy in policy_order():
            selected = [row for row in source if row["policy"] == policy]
            completed = [row for row in selected if row["status"] == "completed"]
            pnl_market = [float(row["pnl"] or 0.0) for row in selected]
            estimate, low, high = _bootstrap(pnl_market)
            differences = [
                float(row["pnl"] or 0.0) - baseline[str(row["ticker"])]
                for row in selected
            ]
            diff, diff_low, diff_high = _bootstrap(differences)
            pnl_filled = [float(row["pnl"]) for row in completed]
            sample = selected[0] if selected else {}
            output.append({
                "segment": segment,
                "policy": policy,
                "variant": sample.get("variant", ""),
                "persistence_threshold_seconds": sample.get(
                    "persistence_threshold_seconds", ""
                ),
                "eligible_markets": len(selected),
                "persistent_signal_markets": sum(
                    bool(row.get("persistent_signal_seen", False)) for row in selected
                ),
                "early_entries": sum(
                    "early_5_7_5m" in str(row.get("entry_source", ""))
                    for row in selected
                ),
                "fallback_entries": sum(
                    row.get("entry_source") == "fallback_4_5m" for row in selected
                ),
                "total_entries": len(completed),
                "mean_pnl_per_eligible_market": estimate,
                "bootstrap_ci_low_per_eligible_market": low,
                "bootstrap_ci_high_per_eligible_market": high,
                "mean_paired_difference_vs_baseline": diff,
                "paired_difference_ci_low": diff_low,
                "paired_difference_ci_high": diff_high,
                "mean_pnl_per_filled_entry": _mean(pnl_filled),
                "profitable_rate_per_filled_entry": _mean(
                    [bool(row["profitable"]) for row in completed]
                ),
                "protected_target_rate": _mean(
                    [bool(row["target_filled"]) for row in completed]
                ),
                "favored_side_won_rate": _mean(
                    [bool(row["favored_side_won"]) for row in completed]
                ),
                "full_loss_count": sum(
                    bool(row["full_capital_loss"]) for row in completed
                ),
                "full_loss_rate": _mean(
                    [bool(row["full_capital_loss"]) for row in completed]
                ),
                "entry_crossed_5m_boundary_count": sum(
                    bool(row.get("entry_crossed_5m_boundary", False))
                    for row in selected
                ),
                "median_decision_seconds_remaining": statistics.median(
                    float(row["seconds_remaining"]) for row in completed
                ) if completed else math.nan,
                "pnl_05_quantile": _quantile(pnl_filled, 0.05),
                "worst_pnl": min(pnl_filled) if pnl_filled else math.nan,
                "holdout_read": False,
                "orders_placed": False,
            })
    return output


def selection_table(summary: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    lookup = {
        (str(row["segment"]), str(row["policy"])): row for row in summary
    }
    output: list[dict[str, Any]] = []
    selected_threshold: int | None = None
    for threshold in THRESHOLDS_SECONDS:
        policy = _policy_name(threshold, True)
        overall = lookup[("all_96", policy)]
        earlier = lookup[("earlier_64_diagnostic", policy)]
        later = lookup[("later_32_diagnostic", policy)]
        no_full_losses = int(overall["full_loss_count"]) == 0
        overall_positive = float(overall["mean_paired_difference_vs_baseline"]) > 0
        earlier_positive = float(earlier["mean_paired_difference_vs_baseline"]) > 0
        later_positive = float(later["mean_paired_difference_vs_baseline"]) > 0
        passes = (
            no_full_losses
            and overall_positive
            and earlier_positive
            and later_positive
        )
        if passes and selected_threshold is None:
            selected_threshold = threshold
        output.append({
            "persistence_threshold_seconds": threshold,
            "combined_policy": policy,
            "full_loss_count": overall["full_loss_count"],
            "mean_paired_difference_all_96": overall[
                "mean_paired_difference_vs_baseline"
            ],
            "mean_paired_difference_earlier_64": earlier[
                "mean_paired_difference_vs_baseline"
            ],
            "mean_paired_difference_later_32": later[
                "mean_paired_difference_vs_baseline"
            ],
            "passes_zero_full_loss_gate": no_full_losses,
            "passes_positive_all_96_gate": overall_positive,
            "passes_positive_both_segments_gate": (
                earlier_positive and later_positive
            ),
            "passes_all_gates": passes,
            "selected_shortest_passing_threshold": (
                passes and threshold == selected_threshold
            ),
            "selection_rule": "shortest threshold passing every preregistered gate",
            "holdout_read": False,
        })
    return output


def verify_results(
    summary: Sequence[Mapping[str, Any]], selection: Sequence[Mapping[str, Any]]
) -> None:
    baseline = next(
        row for row in summary
        if row["segment"] == "all_96" and row["policy"] == BASELINE
    )
    immediate = next(
        row for row in summary
        if row["segment"] == "all_96"
        and row["policy"] == HISTORICAL_CONTROL
    )
    if int(baseline["total_entries"]) != EXPECTED_NATIVE_ENTRIES:
        raise EarlyPersistenceError(
            f"expected 57 baseline entries; found {baseline['total_entries']}"
        )
    if int(immediate["early_entries"]) != EXPECTED_IMMEDIATE_EARLY_ENTRIES:
        raise EarlyPersistenceError(
            f"expected 52 immediate early entries; found {immediate['early_entries']}"
        )
    selected = [
        row for row in selection if row["selected_shortest_passing_threshold"]
    ]
    if len(selected) > 1:
        raise EarlyPersistenceError("more than one persistence threshold selected")


def markdown_report(
    summary: Sequence[Mapping[str, Any]], selection: Sequence[Mapping[str, Any]]
) -> str:
    rows = [row for row in summary if row["segment"] == "all_96"]
    lines = [
        "# KXBTC15M H3 causal early-persistence diagnostic",
        "",
        "**Preregistered adaptive development test; causal-native monitoring; holdout sealed.**",
        "",
        "The frozen 4-to-5-minute H3 baseline is compared with 0-, 1-, 2-, and "
        "5-second uninterrupted persistence in the 5-to-7.5-minute window. An episode resets "
        "on any native response that leaves the 90%-to-below-98% band, changes favored side, "
        "or lacks a usable quote. Every delayed fill must execute before five minutes remain.",
        "",
        "All policies retain one-second latency, full archived depth, fees, $100 maximum sizing, "
        "the protected 50%-of-maximum target, and the ten-second preclose fallback. Combined "
        "policies take at most one cycle: an early fill replaces the baseline; otherwise the "
        "frozen 4-to-5-minute rule is attempted.",
        "",
        "The historical immediate control retains the earlier diagnostic's decision-window "
        "definition, under which a signal before five minutes may fill just after that boundary. "
        "It is included only to reproduce the prior 52-entry result. Every policy eligible for "
        "selection enforces the new strict pre-five-minute fill cutoff.",
        "",
        "| Policy | Signals | Early | Fallback | Total | Mean / market | 95% CI | vs baseline | Paired 95% CI | Mean / fill | Profitable | Target | Favored won | Full losses | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['policy']} | {row['persistent_signal_markets']} | "
            f"{row['early_entries']} | {row['fallback_entries']} | {row['total_entries']} | "
            f"{_money(row['mean_pnl_per_eligible_market'])} | "
            f"{_money(row['bootstrap_ci_low_per_eligible_market'])} to "
            f"{_money(row['bootstrap_ci_high_per_eligible_market'])} | "
            f"{_money(row['mean_paired_difference_vs_baseline'])} | "
            f"{_money(row['paired_difference_ci_low'])} to "
            f"{_money(row['paired_difference_ci_high'])} | "
            f"{_money(row['mean_pnl_per_filled_entry'])} | "
            f"{_percent(row['profitable_rate_per_filled_entry'])} | "
            f"{_percent(row['protected_target_rate'])} | "
            f"{_percent(row['favored_side_won_rate'])} | {row['full_loss_count']} | "
            f"{_money(row['pnl_05_quantile'])} | {_money(row['worst_pnl'])} |"
        )
    lines.extend([
        "",
        "Mean P&L per eligible market counts no-trades as $0. The historical control must "
        "reproduce the prior causal 5-to-7.5-minute result with 52 entries; the baseline must "
        "reproduce all 57 accepted native entries. The strict zero-second row may contain fewer "
        "entries when a delayed execution crosses the five-minute boundary.",
        "",
        "## Preregistered combined-policy gate",
        "",
        "A threshold passes only if its combined policy has zero full losses and a positive "
        "paired mean improvement overall, in the earlier-64 segment, and in the later-32 "
        "segment. If several pass, the shortest threshold is selected rather than the highest "
        "observed mean.",
        "",
        "| Threshold | Full losses | All-96 difference | Earlier-64 | Later-32 | Zero-loss | Positive overall | Positive both segments | Passes | Selected |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in selection:
        lines.append(
            f"| {row['persistence_threshold_seconds']}s | {row['full_loss_count']} | "
            f"{_money(row['mean_paired_difference_all_96'])} | "
            f"{_money(row['mean_paired_difference_earlier_64'])} | "
            f"{_money(row['mean_paired_difference_later_32'])} | "
            f"{row['passes_zero_full_loss_gate']} | "
            f"{row['passes_positive_all_96_gate']} | "
            f"{row['passes_positive_both_segments_gate']} | "
            f"{row['passes_all_gates']} | "
            f"{row['selected_shortest_passing_threshold']} |"
        )
    chosen = next(
        (
            row for row in selection
            if row["selected_shortest_passing_threshold"]
        ),
        None,
    )
    lines.extend([
        "",
        (
            f"Gate result: {chosen['persistence_threshold_seconds']} seconds is the shortest "
            "passing development threshold."
            if chosen is not None else
            "Gate result: no threshold passes every preregistered development gate."
        ),
        "",
        "This remains adaptive development evidence, not an unbiased future-return estimate "
        "or guarantee. No external BTC data, authentication, order, or holdout observation is "
        "used.",
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
        default=Path("analysis/kxbtc15m_h3_early_persistence"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="kxbtc15m_early_persistence_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise EarlyPersistenceError(
                f"expected 96 eligible markets; found {len(eligible)}"
            )
        if set(outcomes) != {market.ticker for market in eligible}:
            raise EarlyPersistenceError("development outcome ticker mismatch")
        for number, market in enumerate(eligible, start=1):
            _legacy, snapshots = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            segment = "earlier_64" if market.index <= 64 else "later_32"
            market_rows, baseline, historical_control = simulate_market_policies(
                snapshots=snapshots,
                close_time=close,
                winning_side=outcomes[market.ticker],
                ticker=market.ticker,
                segment=segment,
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
            prior_window = simulate_window(
                snapshots=snapshots,
                close_time=close,
                winning_side=outcomes[market.ticker],
                ticker=market.ticker,
                scenario="05_300_450s",
                start_seconds=450,
                end_seconds=300,
                segment=segment,
            )
            verify_immediate_reproduction(historical_control, prior_window)
            rows.extend(market_rows)
            print(f"[{number:02d}/96] {market.ticker}")
    summary = summarize(rows)
    selection = selection_table(summary)
    verify_results(summary, selection)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_h3_early_persistence_scenarios.csv", rows)
    write_csv(args.output_dir / "kxbtc15m_h3_early_persistence_summary.csv", summary)
    write_csv(args.output_dir / "kxbtc15m_h3_early_persistence_selection.csv", selection)
    report_path = args.output_dir / "KXBTC15M_H3_EARLY_PERSISTENCE.md"
    report_path.write_text(markdown_report(summary, selection), encoding="utf-8")
    print("KXBTC15M H3 causal early-persistence diagnostic: PASS")
    print("Eligible development markets: 96")
    print("Persistence thresholds: 0s, 1s, 2s, 5s")
    print("Native 4-5m baseline entries reproduced: 57")
    print("Historical immediate native 5-7.5m entries reproduced: 52")
    print("Holdout read: False")
    print("Orders placed: False")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (
        AuditError,
        EarlyPersistenceError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise SystemExit(f"KXBTC15M H3 early-persistence error: {exc}") from exc
