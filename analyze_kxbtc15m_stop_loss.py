#!/usr/bin/env python3
"""Matched development-only stop-loss study for bounded KXBTC15M reversion."""

from __future__ import annotations

import argparse
import csv
from datetime import timedelta
import math
import statistics
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import (
    EXPECTED_ELIGIBLE_MARKETS,
    SimulationError,
    clustered_mean_ci,
    first_index_at_or_after,
    load_outcomes,
    load_snapshots,
    simulate_policy,
    validate_fee_inputs,
    write_csv,
)
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    safe_extract_zip,
    select_development_manifests,
)


STOP_LEVELS: tuple[Decimal | None, ...] = (
    None,
    Decimal("5"),
    Decimal("10"),
    Decimal("15"),
    Decimal("20"),
)
ANCHOR_MINUTES = tuple(range(5))
TRANCHE_COUNT = 3


def percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def summarize_stop_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for stop in STOP_LEVELS:
        label = "no_stop" if stop is None else f"minus_{int(stop)}"
        subset = [row for row in rows if row["stop_label"] == label and row["status"] == "completed"]
        stopped = [row for row in subset if row["loss_stop_executed"]]
        pnl_values = [float(row["pnl"]) for row in subset]
        mean_pnl, ci_low, ci_high = clustered_mean_ci(subset, "pnl")
        output.append({
            "stop_label": label,
            "stop_dollars": "" if stop is None else float(stop),
            "completed_scenarios": len(subset),
            "markets": len({row["ticker"] for row in subset}),
            "mean_pnl_equal_market_weighted": mean_pnl,
            "mean_pnl_clustered_ci_low": ci_low,
            "mean_pnl_clustered_ci_high": ci_high,
            "median_pnl": statistics.median(pnl_values) if pnl_values else math.nan,
            "pnl_05_quantile": percentile(pnl_values, 0.05),
            "worst_pnl": min(pnl_values) if pnl_values else math.nan,
            "profitable_rate": statistics.mean(bool(row["profitable"]) for row in subset) if subset else math.nan,
            "profit_target_rate": statistics.mean(bool(row["target_achieved_after_latency"]) for row in subset) if subset else math.nan,
            "stop_execution_rate": len(stopped) / len(subset) if subset else math.nan,
            "stopped_then_baseline_recovered_rate": statistics.mean(bool(row["baseline_profitable"]) for row in stopped) if stopped else 0.0,
            "mean_pnl_delta_vs_no_stop": statistics.mean(float(row["pnl_delta_vs_no_stop"]) for row in subset) if subset else math.nan,
            "mean_realized_stopped_pnl": statistics.mean(float(row["pnl"]) for row in stopped) if stopped else math.nan,
            "mean_total_fees": statistics.mean(float(row["total_fees"]) for row in subset) if subset else math.nan,
            "mean_budget_utilization": statistics.mean(float(row["budget_utilization"]) for row in subset) if subset else math.nan,
        })
    return output


def markdown_report(summary: Sequence[Mapping[str, Any]], scenario_count: int) -> str:
    lines = [
        "# KXBTC15M executable stop-loss diagnostic",
        "",
        "**Development-only matched study; holdout sealed.**",
        "",
        f"Scenario rows: {scenario_count:,}. Every stopped scenario is matched to its exact no-stop counterfactual.",
        "",
        "The study keeps three staged buy-ins, first-five-minute anchors, a $100 maximum budget, "
        "5-cent additions, a $1 net-profit target, one-second latency, full depth, fees, and the "
        "two-minute time stop. Only the executable net-P&L stop changes.",
        "",
        "| Stop | Mean P&L | Clustered 95% CI | Profitable | Stop executed | Stopped but baseline recovered | 5% tail P&L | Worst P&L |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['stop_label']} | ${row['mean_pnl_equal_market_weighted']:.2f} | "
            f"${row['mean_pnl_clustered_ci_low']:.2f} to ${row['mean_pnl_clustered_ci_high']:.2f} | "
            f"{row['profitable_rate']:.1%} | {row['stop_execution_rate']:.1%} | "
            f"{row['stopped_then_baseline_recovered_rate']:.1%} | "
            f"${row['pnl_05_quantile']:.2f} | ${row['worst_pnl']:.2f} |"
        )
    lines.extend([
        "",
        "A useful stop must improve equal-market-weighted mean P&L and the loss tail without "
        "destroying too many eventual recoveries. A positive development mean does not itself "
        "authorize holdout access; one rule would first need to be frozen.",
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
        "--output-dir", type=Path,
        default=Path("analysis/kxbtc15m_stop_loss"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_stop_loss_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise SimulationError(f"expected 96 eligible markets; found {len(eligible)}")
        if set(outcomes) != {market.ticker for market in eligible}:
            raise SimulationError("outcome ticker set does not equal eligible development set")

        for number, market in enumerate(eligible, start=1):
            snapshots = load_snapshots(market, args.repo_root)
            close = market_close_utc(market.ticker)
            open_time = close - timedelta(minutes=15)
            for minute in ANCHOR_MINUTES:
                target = open_time + timedelta(minutes=minute)
                decision_index = first_index_at_or_after(snapshots, 0, target)
                if decision_index is None:
                    continue
                baseline = simulate_policy(
                    snapshots=snapshots,
                    decision_index=decision_index,
                    close_time=close,
                    winning_side=outcomes[market.ticker],
                    tranche_count=TRANCHE_COUNT,
                    net_loss_stop=None,
                )
                for stop in STOP_LEVELS:
                    result = baseline.copy() if stop is None else simulate_policy(
                        snapshots=snapshots,
                        decision_index=decision_index,
                        close_time=close,
                        winning_side=outcomes[market.ticker],
                        tranche_count=TRANCHE_COUNT,
                        net_loss_stop=stop,
                    )
                    label = "no_stop" if stop is None else f"minus_{int(stop)}"
                    result.update({
                        "market_index": market.index,
                        "ticker": market.ticker,
                        "anchor_minute": minute,
                        "stop_label": label,
                        "baseline_pnl": baseline.get("pnl", math.nan),
                        "baseline_profitable": baseline.get("profitable", False),
                        "pnl_delta_vs_no_stop": (
                            float(result.get("pnl", math.nan)) - float(baseline.get("pnl", math.nan))
                            if result.get("status") == baseline.get("status") == "completed"
                            else math.nan
                        ),
                        "holdout_read": False,
                    })
                    rows.append(result)
            print(f"[{number:02d}/96] {market.ticker}")

    summary = summarize_stop_rows(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = args.output_dir / "kxbtc15m_stop_loss_scenarios.csv"
    summary_path = args.output_dir / "kxbtc15m_stop_loss_summary.csv"
    report_path = args.output_dir / "KXBTC15M_STOP_LOSS.md"
    write_csv(scenario_path, rows)
    write_csv(summary_path, summary)
    report_path.write_text(markdown_report(summary, len(rows)), encoding="utf-8")

    print("KXBTC15M executable stop-loss diagnostic: PASS")
    print(f"Eligible development markets: {len(eligible)}")
    print(f"Scenario rows: {len(rows)}")
    print("Policy: 3 buy-ins; first-five-minute anchors")
    print("Stops compared: none, -$5, -$10, -$15, -$20")
    print("Execution latency: 1.0 seconds")
    print("Holdout read: False")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, OSError, SimulationError, ValueError) as exc:
        raise SystemExit(f"Stop-loss simulation error: {exc}") from exc
