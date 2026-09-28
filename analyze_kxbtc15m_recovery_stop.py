#!/usr/bin/env python3
"""Recovery-aware stop diagnostic for bounded KXBTC15M reversion."""

from __future__ import annotations

import argparse
import math
import statistics
from datetime import timedelta
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


GRACE_SECONDS = (10.0, 20.0, 30.0)
STOP_DOLLARS = (Decimal("5"), Decimal("10"))
CONFIRMATION_SECONDS = 2.0
ANCHOR_MINUTES = tuple(range(5))
TRANCHE_COUNT = 3


def policy_label(grace: float | None, stop: Decimal | None) -> str:
    if grace is None or stop is None:
        return "no_stop"
    return f"grace_{int(grace)}s_stop_{int(stop)}"


def percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    policies: list[tuple[float | None, Decimal | None]] = [(None, None)]
    policies.extend((grace, stop) for grace in GRACE_SECONDS for stop in STOP_DOLLARS)
    output: list[dict[str, Any]] = []
    for grace, stop in policies:
        label = policy_label(grace, stop)
        subset = [
            row for row in rows
            if row["policy_label"] == label and row["status"] == "completed"
        ]
        stopped = [row for row in subset if row["loss_stop_executed"]]
        pnl = [float(row["pnl"]) for row in subset]
        mean, low, high = clustered_mean_ci(subset, "pnl")
        output.append({
            "policy_label": label,
            "grace_seconds": "" if grace is None else grace,
            "stop_dollars": "" if stop is None else float(stop),
            "confirmation_seconds": "" if stop is None else CONFIRMATION_SECONDS,
            "completed_scenarios": len(subset),
            "markets": len({row["ticker"] for row in subset}),
            "mean_pnl_equal_market_weighted": mean,
            "mean_pnl_clustered_ci_low": low,
            "mean_pnl_clustered_ci_high": high,
            "median_pnl": statistics.median(pnl) if pnl else math.nan,
            "pnl_05_quantile": percentile(pnl, 0.05),
            "worst_pnl": min(pnl) if pnl else math.nan,
            "profitable_rate": statistics.mean(bool(row["profitable"]) for row in subset) if subset else math.nan,
            "profit_target_rate": statistics.mean(bool(row["target_achieved_after_latency"]) for row in subset) if subset else math.nan,
            "stop_execution_rate": len(stopped) / len(subset) if subset else math.nan,
            "stopped_then_baseline_recovered_rate": statistics.mean(bool(row["baseline_profitable"]) for row in stopped) if stopped else 0.0,
            "mean_pnl_delta_vs_no_stop": statistics.mean(float(row["pnl_delta_vs_no_stop"]) for row in subset) if subset else math.nan,
            "mean_realized_stopped_pnl": statistics.mean(float(row["pnl"]) for row in stopped) if stopped else math.nan,
            "mean_total_fees": statistics.mean(float(row["total_fees"]) for row in subset) if subset else math.nan,
        })
    return output


def markdown_report(summary: Sequence[Mapping[str, Any]], scenario_count: int) -> str:
    lines = [
        "# KXBTC15M recovery-aware stop diagnostic",
        "",
        "**Final simple-rule development diagnostic; holdout sealed.**",
        "",
        f"Scenario rows: {scenario_count:,}. Each stop policy is matched to the exact no-stop counterfactual.",
        "",
        "All policies keep three equal-dollar tranches, a $100 maximum budget, first-five-minute "
        "anchors, 5-cent additions, full depth, fees, a $1 target, and one-second execution latency. "
        "An addition is evaluated before the stop. The stop arms only after the grace period from "
        "the latest filled tranche, must remain breached for two seconds, and then executes one second later.",
        "",
        "| Policy | Mean P&L | Clustered 95% CI | Profitable | Stop executed | Stopped but baseline recovered | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['policy_label']} | ${row['mean_pnl_equal_market_weighted']:.2f} | "
            f"${row['mean_pnl_clustered_ci_low']:.2f} to ${row['mean_pnl_clustered_ci_high']:.2f} | "
            f"{row['profitable_rate']:.1%} | {row['stop_execution_rate']:.1%} | "
            f"{row['stopped_then_baseline_recovered_rate']:.1%} | "
            f"${row['pnl_05_quantile']:.2f} | ${row['worst_pnl']:.2f} |"
        )
    lines.extend([
        "",
        "This is the last simple-rule reversion diagnostic on this development sample. If no policy "
        "has positive mean P&L with a clustered interval supporting improvement, close the branch. "
        "If one appears promising, validate it prospectively on newly collected markets rather than "
        "opening the existing holdout after this expanded search.",
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
        default=Path("analysis/kxbtc15m_recovery_stop"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_recovery_stop_") as temporary:
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
                decision_index = first_index_at_or_after(
                    snapshots, 0, open_time + timedelta(minutes=minute)
                )
                if decision_index is None:
                    continue
                baseline = simulate_policy(
                    snapshots=snapshots,
                    decision_index=decision_index,
                    close_time=close,
                    winning_side=outcomes[market.ticker],
                    tranche_count=TRANCHE_COUNT,
                )
                policies: list[tuple[float | None, Decimal | None]] = [(None, None)]
                policies.extend((grace, stop) for grace in GRACE_SECONDS for stop in STOP_DOLLARS)
                for grace, stop in policies:
                    result = baseline.copy() if stop is None else simulate_policy(
                        snapshots=snapshots,
                        decision_index=decision_index,
                        close_time=close,
                        winning_side=outcomes[market.ticker],
                        tranche_count=TRANCHE_COUNT,
                        net_loss_stop=stop,
                        loss_stop_grace_seconds=grace or 0.0,
                        loss_stop_confirmation_seconds=CONFIRMATION_SECONDS,
                        additions_before_stop=True,
                    )
                    result.update({
                        "market_index": market.index,
                        "ticker": market.ticker,
                        "anchor_minute": minute,
                        "policy_label": policy_label(grace, stop),
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

    summary = summarize(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_recovery_stop_scenarios.csv", rows)
    write_csv(args.output_dir / "kxbtc15m_recovery_stop_summary.csv", summary)
    report_path = args.output_dir / "KXBTC15M_RECOVERY_STOP.md"
    report_path.write_text(markdown_report(summary, len(rows)), encoding="utf-8")

    print("KXBTC15M recovery-aware stop diagnostic: PASS")
    print(f"Eligible development markets: {len(eligible)}")
    print(f"Scenario rows: {len(rows)}")
    print("Policy: 3 equal-dollar buy-ins; first-five-minute anchors")
    print("Grace periods: 10, 20, 30 seconds after latest fill")
    print("Stops: -$5, -$10 executable net P&L")
    print("Confirmation: 2 seconds; execution latency: 1 second")
    print("Additions evaluated before stop: yes")
    print("Holdout read: False")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, OSError, SimulationError, ValueError) as exc:
        raise SystemExit(f"Recovery-stop simulation error: {exc}") from exc
