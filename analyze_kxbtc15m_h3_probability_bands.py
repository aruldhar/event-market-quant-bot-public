#!/usr/bin/env python3
"""Compare frozen H3 mechanics across favored-midpoint probability bands.

The 4-to-5-minute entry window and native causal monitoring are frozen from the
prior development diagnostics.  Entry latency, sizing, full-depth execution,
fees, protected target, and preclose fallback are unchanged.  Only the favored
midpoint band changes.  The separate holdout remains sealed.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from decimal import Decimal
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


WINDOW_START_SECONDS = 300
WINDOW_END_SECONDS = 240
SCENARIOS = (
    ("baseline_090_098", "90-98% combined", Decimal("0.90"), Decimal("0.98")),
    ("band_080_090", "80-90%", Decimal("0.80"), Decimal("0.90")),
    ("band_090_095", "90-95%", Decimal("0.90"), Decimal("0.95")),
    ("band_095_098", "95-98%", Decimal("0.95"), Decimal("0.98")),
)
BASELINE = SCENARIOS[0][0]
EXPECTED_BASELINE_ENTRIES = 57


class ProbabilityBandError(TimeWindowError):
    """Raised when the probability-band diagnostic fails closed."""


def _scenario_label(scenario: str) -> str:
    return next(label for name, label, _low, _high in SCENARIOS if name == scenario)


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
        baseline_filled = {
            ticker for ticker, row in baseline.items() if row["status"] == "completed"
        }
        for scenario, label, low, high in SCENARIOS:
            selected = [row for row in source if row["scenario"] == scenario]
            completed = [row for row in selected if row["status"] == "completed"]
            completed_tickers = {str(row["ticker"]) for row in completed}
            pnl_market = [float(row["pnl"] or 0.0) for row in selected]
            pnl_filled = [float(row["pnl"]) for row in completed]
            mean_market, low_ci, high_ci = _bootstrap(pnl_market)
            differences = [
                float(row["pnl"] or 0.0)
                - float(baseline[str(row["ticker"])]["pnl"] or 0.0)
                for row in selected
            ]
            diff_mean, diff_low, diff_high = _bootstrap(differences)
            output.append({
                "segment": segment,
                "scenario": scenario,
                "display_band": label,
                "band_low_inclusive": format(low, "f"),
                "band_high_exclusive": format(high, "f"),
                "eligible_markets": len(selected),
                "triggered_markets": sum(bool(row["triggered"]) for row in selected),
                "entry_filled_markets": len(completed),
                "overlap_filled_with_90_98": len(completed_tickers & baseline_filled),
                "new_filled_vs_90_98": len(completed_tickers - baseline_filled),
                "missed_filled_vs_90_98": len(baseline_filled - completed_tickers),
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
                "bootstrap_ci_low_per_eligible_market": low_ci,
                "bootstrap_ci_high_per_eligible_market": high_ci,
                "mean_paired_difference_vs_90_98_per_market": diff_mean,
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
                "mean_maximum_settlement_profit": _mean(
                    [float(row["maximum_settlement_profit"]) for row in completed]
                ),
                "pnl_05_quantile_per_filled_entry": _quantile(pnl_filled, 0.05),
                "worst_pnl_per_filled_entry": min(pnl_filled)
                if pnl_filled else math.nan,
                "holdout_read": False,
                "external_btc_data_used": False,
                "orders_placed": False,
            })
    return output


def verify_summary(summary: Sequence[Mapping[str, Any]]) -> None:
    baseline = next(
        row for row in summary
        if row["segment"] == "all_96" and row["scenario"] == BASELINE
    )
    if int(baseline["entry_filled_markets"]) != EXPECTED_BASELINE_ENTRIES:
        raise ProbabilityBandError(
            "expected 57 causal-native 90-98% entries; found "
            f"{baseline['entry_filled_markets']}"
        )
    if abs(float(baseline["mean_paired_difference_vs_90_98_per_market"])) > 1e-12:
        raise ProbabilityBandError("90-98% baseline paired difference is not zero")


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    rows = [row for row in summary if row["segment"] == "all_96"]
    lines = [
        "# KXBTC15M H3 probability-band diagnostic",
        "",
        "**Adaptive development diagnostic; native 4-5m timing frozen; holdout sealed.**",
        "",
        "Every scenario checks every causally received archived response during the frozen "
        "4-to-5-minute entry window. One-second latency, $100 sizing, full-depth execution, "
        "fees, unprotected delayed entry, protected 50%-of-maximum target, and ten-second "
        "preclose fallback are unchanged. Only the favored-midpoint band changes.",
        "",
        "The 80-90%, 90-95%, and 95-98% rows are standalone counterfactual alternatives, not "
        "additive trades. The 90-98% combined row must exactly reproduce the accepted 57-entry "
        "native-frequency baseline.",
        "",
        "| Band | Trigger | Filled | Overlap | New | Missed | Mean / market | 95% CI | vs 90-98 | Paired 95% CI | Mean / fill | Avg entry | Avg max profit | Profitable | Target fill | Favored won | Full loss | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['display_band']} | {_percent(row['trigger_rate_per_market'])} | "
            f"{row['entry_filled_markets']} | {row['overlap_filled_with_90_98']} | "
            f"{row['new_filled_vs_90_98']} | {row['missed_filled_vs_90_98']} | "
            f"{_money(row['mean_pnl_per_eligible_market'])} | "
            f"{_money(row['bootstrap_ci_low_per_eligible_market'])} to "
            f"{_money(row['bootstrap_ci_high_per_eligible_market'])} | "
            f"{_money(row['mean_paired_difference_vs_90_98_per_market'])} | "
            f"{_money(row['paired_difference_ci_low'])} to "
            f"{_money(row['paired_difference_ci_high'])} | "
            f"{_money(row['mean_pnl_per_filled_entry'])} | "
            f"{_percent(row['mean_entry_average_price'])} | "
            f"{_money(row['mean_maximum_settlement_profit'])} | "
            f"{_percent(row['profitable_rate_per_filled_entry'])} | "
            f"{_percent(row['protected_target_fill_rate'])} | "
            f"{_percent(row['favored_side_won_rate'])} | "
            f"{_percent(row['full_capital_loss_rate'])} | "
            f"{_money(row['pnl_05_quantile_per_filled_entry'])} | "
            f"{_money(row['worst_pnl_per_filled_entry'])} |"
        )
    lines.extend([
        "",
        "Overlap is the number of filled markets shared with the combined 90-98% baseline. "
        "New and missed counts show how splitting the band changes market selection. Mean P&L "
        "per eligible market counts no-trades as $0 and is the primary metric; conditional mean "
        "per fill is secondary.",
        "",
        "This is an adaptive, multiple-comparison development test. It may reject a band or "
        "define a candidate for the sealed holdout, but the best row is not an unbiased expected "
        "return estimate. No external BTC data, authentication, order, or holdout observation "
        "is used.",
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
        default=Path("analysis/kxbtc15m_h3_probability_bands"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_probability_bands_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise ProbabilityBandError(
                f"expected 96 eligible markets; found {len(eligible)}"
            )
        if set(outcomes) != {market.ticker for market in eligible}:
            raise ProbabilityBandError(
                "outcome ticker set does not equal development market set"
            )

        for number, market in enumerate(eligible, start=1):
            _legacy, snapshots = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            segment = "earlier_64" if market.index <= 64 else "later_32"
            market_rows: list[dict[str, Any]] = []
            for scenario, _label, low, high in SCENARIOS:
                row = simulate_window(
                    snapshots=snapshots,
                    close_time=close,
                    winning_side=outcomes[market.ticker],
                    ticker=market.ticker,
                    scenario=scenario,
                    start_seconds=WINDOW_START_SECONDS,
                    end_seconds=WINDOW_END_SECONDS,
                    segment=segment,
                    entry_deadline_seconds_before_close=PRECLOSE_EXIT_SECONDS,
                    band_low=low,
                    band_high_exclusive=high,
                )
                row["band_low_inclusive"] = format(low, "f")
                row["band_high_exclusive"] = format(high, "f")
                market_rows.append(row)
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

    summary = summarize(rows)
    verify_summary(summary)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = args.output_dir / "kxbtc15m_h3_probability_bands_scenarios.csv"
    summary_path = args.output_dir / "kxbtc15m_h3_probability_bands_summary.csv"
    report_path = args.output_dir / "KXBTC15M_H3_PROBABILITY_BANDS.md"
    write_csv(scenario_path, rows)
    write_csv(summary_path, summary)
    report_path.write_text(markdown_report(summary), encoding="utf-8")

    print("KXBTC15M H3 probability-band diagnostic: PASS")
    print("Eligible development markets: 96")
    print("Monitoring: every causal archived response")
    print("Entry window: 4 to 5 minutes before close")
    print("Causal native 90-98% baseline reproduced: True")
    print("Holdout read: False")
    print("Orders placed: False")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (
        AuditError,
        ProbabilityBandError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise SystemExit(f"KXBTC15M H3 probability-band error: {exc}") from exc
