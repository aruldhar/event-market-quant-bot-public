#!/usr/bin/env python3
"""Re-evaluate the full executable final five minutes of frozen H3.

Monitoring is fixed to every causally received archived HTTP response.  The
90%-to-below-98% favored-midpoint band, one-second latency, $100 maximum
budget, full-depth execution, conservative fees, protected 50%-of-maximum
target, and ten-second preclose fallback remain unchanged.  Only the entry
time within the final five minutes changes.  The final ten seconds are not an
entry window because the frozen strategy is already attempting to exit then.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import (
    EXPECTED_ELIGIBLE_MARKETS,
    load_outcomes,
    validate_fee_inputs,
    write_csv,
)
from analyze_kxbtc15m_h3_exit_policies import PRECLOSE_EXIT_SECONDS
from analyze_kxbtc15m_h3_frequency import (
    _raw_snapshot_sets,
    simulate_market as simulate_frequency_market,
)
from analyze_kxbtc15m_h3_time_windows import (
    TimeWindowError,
    _bootstrap,
    _mean,
    _money,
    _percent,
    _quantile,
    simulate_window,
    verify_frequency_baseline,
)
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    safe_extract_zip,
    select_development_manifests,
)


WINDOWS = (
    ("04_240_300s", "4-5m", 300, 240),
    ("03_180_240s", "3-4m", 240, 180),
    ("02_120_180s", "2-3m", 180, 120),
    ("01_060_120s", "1-2m", 120, 60),
    ("00_010_060s", "10s-1m", 60, 10),
)
EXPANDED = ("expanded_first_010_300s", "first 10s-5m", 300, 10)
BASELINE = "04_240_300s"
EXPECTED_BASELINE_ENTRIES = 57


class LastFiveMinutesError(TimeWindowError):
    """Raised when the last-five-minute diagnostic fails closed."""


def scenario_names() -> list[str]:
    return [name for name, _label, _start, _end in WINDOWS] + [EXPANDED[0]]


def _label(scenario: str) -> str:
    labels = {name: label for name, label, _start, _end in (*WINDOWS, EXPANDED)}
    return labels[scenario]


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        source = list(rows) if segment == "all_96" else [
            row for row in rows
            if row["diagnostic_segment"]
            == ("earlier_64" if segment.startswith("earlier") else "later_32")
        ]
        baseline = {
            str(row["ticker"]): row for row in source if row["scenario"] == BASELINE
        }
        for scenario in scenario_names():
            selected = [row for row in source if row["scenario"] == scenario]
            completed = [row for row in selected if row["status"] == "completed"]
            pnl_market = [float(row["pnl"] or 0.0) for row in selected]
            pnl_filled = [float(row["pnl"]) for row in completed]
            mean_market, low, high = _bootstrap(pnl_market)
            differences = [
                float(row["pnl"] or 0.0)
                - float(baseline[str(row["ticker"])]["pnl"] or 0.0)
                for row in selected
            ]
            diff_mean, diff_low, diff_high = _bootstrap(differences)
            additional = [
                row for row in completed
                if baseline[str(row["ticker"])]["status"] != "completed"
            ]
            sample = selected[0] if selected else {}
            output.append({
                "segment": segment,
                "scenario": scenario,
                "display_window": _label(scenario),
                "window_start_seconds_remaining": sample.get(
                    "window_start_seconds_remaining", ""
                ),
                "window_end_seconds_remaining_exclusive": sample.get(
                    "window_end_seconds_remaining_exclusive", ""
                ),
                "eligible_markets": len(selected),
                "triggered_markets": sum(bool(row["triggered"]) for row in selected),
                "entry_filled_markets": len(completed),
                "additional_filled_markets_vs_4_5m": len(additional),
                "entry_after_preclose_cutoff_markets": sum(
                    row["status"] == "entry_after_preclose_cutoff" for row in selected
                ),
                "trigger_rate_per_market": _mean(
                    [bool(row["triggered"]) for row in selected]
                ),
                "mean_window_coverage_rate": _mean(
                    [float(row["window_coverage_rate"]) for row in selected]
                ),
                "minimum_window_coverage_rate": min(
                    (float(row["window_coverage_rate"]) for row in selected),
                    default=math.nan,
                ),
                "mean_pnl_per_eligible_market": mean_market,
                "bootstrap_ci_low_per_eligible_market": low,
                "bootstrap_ci_high_per_eligible_market": high,
                "mean_paired_difference_vs_4_5m_per_market": diff_mean,
                "paired_difference_ci_low": diff_low,
                "paired_difference_ci_high": diff_high,
                "mean_pnl_per_filled_entry": _mean(pnl_filled),
                "profitable_rate_per_filled_entry": _mean(
                    [bool(row["profitable"]) for row in completed]
                ),
                "protected_target_fill_rate": _mean(
                    [bool(row["target_filled"]) for row in completed]
                ),
                "fallback_rate": _mean(
                    [bool(row["fallback_used"]) for row in completed]
                ),
                "favored_side_won_rate": _mean(
                    [bool(row["favored_side_won"]) for row in completed]
                ),
                "full_capital_loss_rate": _mean(
                    [bool(row["full_capital_loss"]) for row in completed]
                ),
                "median_decision_seconds_remaining": statistics.median(
                    float(row["seconds_remaining"]) for row in completed
                ) if completed else math.nan,
                "mean_entry_average_price": _mean(
                    [float(row["entry_average_price"]) for row in completed]
                ),
                "pnl_05_quantile_per_filled_entry": _quantile(pnl_filled, 0.05),
                "worst_pnl_per_filled_entry": min(pnl_filled)
                if pnl_filled else math.nan,
                "holdout_read": False,
                "external_btc_data_used": False,
                "orders_placed": False,
            })
    return output


def verify_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    all_rows = [row for row in rows]
    baseline = {
        str(row["ticker"]): row for row in all_rows if row["scenario"] == BASELINE
    }
    expanded = {
        str(row["ticker"]): row
        for row in all_rows if row["scenario"] == EXPANDED[0]
    }
    if len(baseline) != EXPECTED_ELIGIBLE_MARKETS or set(baseline) != set(expanded):
        raise LastFiveMinutesError("baseline/expanded ticker set mismatch")
    fields = (
        "status", "decision_time", "entry_execution_time", "exit_reason", "pnl"
    )
    for ticker, baseline_row in baseline.items():
        if baseline_row["status"] != "completed":
            continue
        mismatches = [
            field for field in fields
            if baseline_row.get(field, "") != expanded[ticker].get(field, "")
        ]
        if mismatches:
            raise LastFiveMinutesError(
                f"{ticker}: expanded policy does not preserve earliest 4-5m fill: {mismatches}"
            )


def verify_summary(summary: Sequence[Mapping[str, Any]]) -> None:
    baseline = next(
        row for row in summary
        if row["segment"] == "all_96" and row["scenario"] == BASELINE
    )
    if int(baseline["entry_filled_markets"]) != EXPECTED_BASELINE_ENTRIES:
        raise LastFiveMinutesError(
            "expected 57 causal-native 4-5m entries; found "
            f"{baseline['entry_filled_markets']}"
        )
    if abs(float(baseline["mean_paired_difference_vs_4_5m_per_market"])) > 1e-12:
        raise LastFiveMinutesError("4-5m baseline paired difference is not zero")


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    rows = [row for row in summary if row["segment"] == "all_96"]
    lines = [
        "# KXBTC15M H3 last-five-minute timing diagnostic",
        "",
        "**Adaptive development diagnostic; native monitoring frozen; holdout sealed.**",
        "",
        "Every scenario checks every causally received archived response. The favored-midpoint "
        "band remains 90% to below 98%; one-second latency, $100 sizing, full-depth execution, "
        "fees, protected 50%-of-maximum target, and ten-second preclose fallback are unchanged.",
        "",
        "The five disjoint rows ask where a standalone first entry works within the executable "
        "part of the last five minutes. The expanded row starts at five minutes and keeps "
        "monitoring until the ten-second cutoff, taking the first qualifying trigger. The final "
        "ten seconds are deliberately excluded because the frozen policy is already attempting "
        "to exit exposure; a delayed fill at or after that cutoff is rejected.",
        "",
        "| Window | Trigger | Filled | Added vs 4-5m | Late-fill reject | Coverage min | Mean / market | 95% CI | vs 4-5m | Paired 95% CI | Mean / fill | Profitable | Target fill | Favored won | Full loss | Median sec left | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        median_seconds = float(row["median_decision_seconds_remaining"])
        median_text = "n/a" if math.isnan(median_seconds) else f"{median_seconds:.1f}"
        lines.append(
            f"| {row['display_window']} | {_percent(row['trigger_rate_per_market'])} | "
            f"{row['entry_filled_markets']} | {row['additional_filled_markets_vs_4_5m']} | "
            f"{row['entry_after_preclose_cutoff_markets']} | "
            f"{_percent(row['minimum_window_coverage_rate'])} | "
            f"{_money(row['mean_pnl_per_eligible_market'])} | "
            f"{_money(row['bootstrap_ci_low_per_eligible_market'])} to "
            f"{_money(row['bootstrap_ci_high_per_eligible_market'])} | "
            f"{_money(row['mean_paired_difference_vs_4_5m_per_market'])} | "
            f"{_money(row['paired_difference_ci_low'])} to "
            f"{_money(row['paired_difference_ci_high'])} | "
            f"{_money(row['mean_pnl_per_filled_entry'])} | "
            f"{_percent(row['profitable_rate_per_filled_entry'])} | "
            f"{_percent(row['protected_target_fill_rate'])} | "
            f"{_percent(row['favored_side_won_rate'])} | "
            f"{_percent(row['full_capital_loss_rate'])} | {median_text} | "
            f"{_money(row['pnl_05_quantile_per_filled_entry'])} | "
            f"{_money(row['worst_pnl_per_filled_entry'])} |"
        )
    lines.extend([
        "",
        "Mean P&L per eligible market counts no-trades as $0. The paired interval compares each "
        "row with the frozen native 4-5m baseline on the same 96 markets. For the expanded row, "
        "the paired difference is the direct incremental consequence of continuing to search "
        "after a market has no 4-5m entry.",
        "",
        "This test was requested after observing the earlier window result, so it is explicitly "
        "adaptive and subject to multiple-comparison bias. It can reject unsafe timing or define "
        "a candidate for the sealed holdout; it cannot turn the best development row into an "
        "unbiased profitability estimate.",
        "",
        "No external BTC data, authentication, order, or holdout observation is used.",
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
        default=Path("analysis/kxbtc15m_h3_last_five_minutes"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_last_five_minutes_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise LastFiveMinutesError(
                f"expected 96 eligible markets; found {len(eligible)}"
            )
        if set(outcomes) != {market.ticker for market in eligible}:
            raise LastFiveMinutesError(
                "outcome ticker set does not equal development market set"
            )

        for number, market in enumerate(eligible, start=1):
            _legacy, snapshots = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            segment = "earlier_64" if market.index <= 64 else "later_32"
            market_rows: list[dict[str, Any]] = []
            for scenario, _label_text, start_seconds, end_seconds in (*WINDOWS, EXPANDED):
                market_rows.append(simulate_window(
                    snapshots=snapshots,
                    close_time=close,
                    winning_side=outcomes[market.ticker],
                    ticker=market.ticker,
                    scenario=scenario,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    segment=segment,
                    entry_deadline_seconds_before_close=PRECLOSE_EXIT_SECONDS,
                ))
            frequency_baseline = simulate_frequency_market(
                snapshots=snapshots,
                close_time=close,
                winning_side=outcomes[market.ticker],
                ticker=market.ticker,
                frequency="native",
                entry_mode="unprotected",
                clock_basis="causal_response_receipt",
                diagnostic_segment=segment,
            )
            verify_frequency_baseline(market_rows[0], frequency_baseline)
            rows.extend(market_rows)
            print(f"[{number:02d}/96] {market.ticker}")

    verify_rows(rows)
    summary = summarize(rows)
    verify_summary(summary)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = args.output_dir / "kxbtc15m_h3_last_five_minutes_scenarios.csv"
    summary_path = args.output_dir / "kxbtc15m_h3_last_five_minutes_summary.csv"
    report_path = args.output_dir / "KXBTC15M_H3_LAST_FIVE_MINUTES.md"
    write_csv(scenario_path, rows)
    write_csv(summary_path, summary)
    report_path.write_text(markdown_report(summary), encoding="utf-8")

    print("KXBTC15M H3 last-five-minute timing diagnostic: PASS")
    print("Eligible development markets: 96")
    print("Monitoring: every causal archived response")
    print("Entry band: 90% to below 98% (unchanged)")
    print("Entry cutoff: 10 seconds before close")
    print("Causal native 4-5m baseline reproduced: True")
    print("Holdout read: False")
    print("Orders placed: False")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (
        AuditError,
        LastFiveMinutesError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise SystemExit(f"KXBTC15M H3 last-five-minute error: {exc}") from exc
