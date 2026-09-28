#!/usr/bin/env python3
"""Compare frozen H3 mechanics across predeclared time-to-close windows.

Monitoring is fixed to every causally available archived HTTP response.  The
90%-to-below-98% favored-midpoint band, one-second latency, $100 maximum budget,
full-depth execution, conservative fees, protected 50%-of-maximum target, and
ten-second preclose fallback remain unchanged.  Only the entry window changes.
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
from analyze_kxbtc15m_h3_exit_policies import (
    PRECLOSE_EXIT_SECONDS,
    _find_preclose_exit,
    percentage_target,
)
from analyze_kxbtc15m_h3_frequency import (
    HIGH_EXCLUSIVE,
    LOW,
    TARGET_FRACTION,
    FrequencyError,
    _average_price,
    _decimal_text,
    _origin,
    _raw_snapshot_sets,
    simulate_market as simulate_frequency_market,
)
from analyze_kxbtc15m_h3_late_convergence import favored_quote
from analyze_kxbtc15m_h3_target_protection import find_protected_target_exit
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    safe_extract_zip,
    select_development_manifests,
)


WINDOWS = (
    ("04_240_300s", 300, 240),
    ("05_300_450s", 450, 300),
    ("06_450_600s", 600, 450),
    ("07_600_900s", 900, 600),
)
EXPANDED = ("expanded_first_240_900s", 900, 240)
BASELINE = "04_240_300s"
EXPECTED_BASELINE_ENTRIES = 57


class TimeWindowError(FrequencyError):
    """Raised when a time-window input or reproduction invariant fails."""


def native_points(
    snapshots: Sequence[Snapshot], close_time: datetime,
    start_seconds: int, end_seconds: int
) -> list[int]:
    if not 0 <= end_seconds < start_seconds <= 900:
        raise TimeWindowError("invalid time-to-close window")
    begin = close_time - timedelta(seconds=start_seconds)
    end = close_time - timedelta(seconds=end_seconds)
    return [
        index for index, snapshot in enumerate(snapshots)
        if begin <= snapshot.observed_at < end
    ]


def coverage_rate(
    snapshots: Sequence[Snapshot], close_time: datetime,
    start_seconds: int, end_seconds: int
) -> float:
    if not snapshots:
        return 0.0
    begin = close_time - timedelta(seconds=start_seconds)
    end = close_time - timedelta(seconds=end_seconds)
    covered_begin = max(begin, snapshots[0].observed_at)
    covered_end = min(end, snapshots[-1].observed_at)
    covered = max(0.0, (covered_end - covered_begin).total_seconds())
    return min(1.0, covered / float(start_seconds - end_seconds))


def _base(
    *, ticker: str, scenario: str, start_seconds: int, end_seconds: int,
    segment: str, coverage: float, point_count: int
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "diagnostic_segment": segment,
        "scenario": scenario,
        "window_start_seconds_remaining": start_seconds,
        "window_end_seconds_remaining_exclusive": end_seconds,
        "monitoring_frequency": "native_archived_response",
        "clock_basis": "causal_response_receipt",
        "entry_protection_mode": "unprotected",
        "window_coverage_rate": f"{coverage:.8f}",
        "monitoring_points": point_count,
        "status": "no_trigger",
        "triggered": False,
        "entry_filled": False,
        "pnl": "",
        "holdout_read": False,
        "external_btc_data_used": False,
        "orders_placed": False,
    }


def simulate_window(
    *, snapshots: Sequence[Snapshot], close_time: datetime, winning_side: str,
    ticker: str, scenario: str, start_seconds: int, end_seconds: int,
    segment: str, entry_deadline_seconds_before_close: int | None = None,
    band_low: Decimal = LOW, band_high_exclusive: Decimal = HIGH_EXCLUSIVE,
) -> dict[str, Any]:
    if not Decimal("0") <= band_low < band_high_exclusive <= Decimal("1"):
        raise TimeWindowError("invalid favored-midpoint band")
    indices = native_points(snapshots, close_time, start_seconds, end_seconds)
    row = _base(
        ticker=ticker,
        scenario=scenario,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        segment=segment,
        coverage=coverage_rate(snapshots, close_time, start_seconds, end_seconds),
        point_count=len(indices),
    )
    prior_quote: tuple[str, Decimal, Decimal] | None = None
    for index in indices:
        decision = snapshots[index]
        quote = favored_quote(decision.book)
        if quote is None:
            prior_quote = None
            continue
        side, midpoint, ask = quote
        qualifies = band_low <= midpoint < band_high_exclusive
        if qualifies and band_low == LOW and band_high_exclusive == HIGH_EXCLUSIVE:
            origin = _origin(prior_quote, quote)
        elif qualifies:
            if prior_quote is None:
                origin = "initial_state"
            elif prior_quote[0] != side:
                origin = "side_changed_into_band"
            elif prior_quote[1] >= band_high_exclusive:
                origin = "above_band_to_band"
            elif prior_quote[1] < band_low:
                origin = "below_band_to_band"
            else:
                origin = "already_in_band"
        else:
            origin = ""
        prior_quote = quote
        if not qualifies:
            continue

        row.update({
            "triggered": True,
            "status": "entry_latency_unavailable",
            "decision_time": decision.observed_at.isoformat(),
            "seconds_remaining": f"{(close_time - decision.observed_at).total_seconds():.6f}",
            "side": side,
            "favored_side_won": side == winning_side,
            "signal_origin": origin,
            "decision_favored_midpoint": _decimal_text(midpoint),
            "decision_favored_ask": _decimal_text(ask),
        })
        entry_index = first_index_at_or_after(
            snapshots,
            index + 1,
            decision.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if entry_index is None or snapshots[entry_index].observed_at >= close_time:
            return row
        entry_snapshot = snapshots[entry_index]
        if (
            entry_deadline_seconds_before_close is not None
            and entry_snapshot.observed_at
            >= close_time - timedelta(seconds=entry_deadline_seconds_before_close)
        ):
            row["status"] = "entry_after_preclose_cutoff"
            row["entry_execution_time"] = entry_snapshot.observed_at.isoformat()
            row["entry_cutoff_seconds_before_close"] = entry_deadline_seconds_before_close
            return row
        entry = buy_with_budget(entry_snapshot.book.ask_levels(side), MAX_BUDGET)
        if entry.quantity <= 0:
            row["status"] = "entry_unfilled"
            return row
        maximum_profit = entry.quantity - entry.buy_outflow
        if maximum_profit <= 0:
            row["status"] = "nonpositive_maximum_profit"
            return row

        target = percentage_target(maximum_profit, TARGET_FRACTION)
        preclose = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
        exit_execution, exit_time, target_signals, target_rejected = find_protected_target_exit(
            snapshots=snapshots,
            start_index=entry_index + 1,
            stop_time=preclose,
            side=side,
            quantity=entry.quantity,
            outflow=entry.buy_outflow,
            target=target,
        )
        exit_reason = "protected_profit_target"
        if exit_execution is None:
            exit_execution, exit_time = _find_preclose_exit(
                snapshots=snapshots,
                start_index=entry_index + 1,
                start_time=preclose,
                close_time=close_time,
                side=side,
                quantity=entry.quantity,
            )
            exit_reason = "preclose_time_exit"
        if exit_execution is None:
            settlement_gross = entry.quantity if side == winning_side else Decimal("0")
            pnl = settlement_gross - entry.buy_outflow
            exit_reason = "settlement_after_preclose_liquidity_failure"
            exit_time = close_time
            exit_gross = settlement_gross
            exit_fee = Decimal("0")
            exit_average = ""
        else:
            pnl = exit_execution.sell_inflow - entry.buy_outflow
            exit_gross = exit_execution.gross
            exit_fee = exit_execution.fee
            exit_average = _decimal_text(_average_price(exit_execution))

        row.update({
            "status": "completed",
            "entry_filled": True,
            "entry_execution_time": entry_snapshot.observed_at.isoformat(),
            "realized_entry_delay_seconds": f"{(entry_snapshot.observed_at - decision.observed_at).total_seconds():.6f}",
            "entry_average_price": _decimal_text(_average_price(entry)),
            "contracts": _decimal_text(entry.quantity),
            "entry_gross": _decimal_text(entry.gross),
            "entry_fee": _decimal_text(entry.fee),
            "cash_deployed": _decimal_text(entry.buy_outflow),
            "maximum_settlement_profit": _decimal_text(maximum_profit),
            "target_amount": _decimal_text(target),
            "target_signal_count": target_signals,
            "target_rejected_after_latency_count": target_rejected,
            "target_filled": exit_reason == "protected_profit_target",
            "fallback_used": exit_reason != "protected_profit_target",
            "exit_reason": exit_reason,
            "exit_execution_time": exit_time.isoformat() if exit_time else "",
            "exit_gross": _decimal_text(exit_gross),
            "exit_fee": _decimal_text(exit_fee),
            "exit_average_price": exit_average,
            "pnl": _decimal_text(pnl),
            "profitable": pnl > 0,
            "full_capital_loss": pnl <= -Decimal("0.90") * entry.buy_outflow,
        })
        return row
    return row


def verify_frequency_baseline(
    window_row: Mapping[str, Any], frequency_row: Mapping[str, Any]
) -> None:
    fields = (
        "status", "triggered", "entry_filled", "decision_time",
        "entry_execution_time", "exit_reason", "pnl",
    )
    mismatches = [field for field in fields if window_row.get(field, "") != frequency_row.get(field, "")]
    if mismatches:
        raise TimeWindowError(
            f"{window_row['ticker']}: native 4-5m frequency reproduction mismatch: {mismatches}"
        )


def _bootstrap(values: Sequence[float]) -> tuple[float, float, float]:
    if not values:
        return math.nan, math.nan, math.nan
    estimate = statistics.mean(values)
    if len(values) < 2:
        return estimate, math.nan, math.nan
    rng = random.Random(20260813)
    draws = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(2_000)]
    draws.sort()
    return estimate, draws[49], draws[1949]


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def _mean(values: Sequence[Any]) -> float:
    return statistics.mean(values) if values else math.nan


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    scenarios = [name for name, _start, _end in WINDOWS] + [EXPANDED[0]]
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        source = list(rows) if segment == "all_96" else [
            row for row in rows
            if row["diagnostic_segment"] == ("earlier_64" if segment.startswith("earlier") else "later_32")
        ]
        baseline = {
            str(row["ticker"]): float(row["pnl"] or 0.0)
            for row in source if row["scenario"] == BASELINE
        }
        for scenario in scenarios:
            selected = [row for row in source if row["scenario"] == scenario]
            completed = [row for row in selected if row["status"] == "completed"]
            pnl_market = [float(row["pnl"] or 0.0) for row in selected]
            pnl_filled = [float(row["pnl"]) for row in completed]
            mean_market, low, high = _bootstrap(pnl_market)
            differences = [
                float(row["pnl"] or 0.0) - baseline[str(row["ticker"])]
                for row in selected
            ]
            diff_mean, diff_low, diff_high = _bootstrap(differences)
            sample = selected[0] if selected else {}
            output.append({
                "segment": segment,
                "scenario": scenario,
                "window_start_seconds_remaining": sample.get("window_start_seconds_remaining", ""),
                "window_end_seconds_remaining_exclusive": sample.get("window_end_seconds_remaining_exclusive", ""),
                "eligible_markets": len(selected),
                "triggered_markets": sum(bool(row["triggered"]) for row in selected),
                "entry_filled_markets": len(completed),
                "trigger_rate_per_market": _mean([bool(row["triggered"]) for row in selected]),
                "mean_window_coverage_rate": _mean([float(row["window_coverage_rate"]) for row in selected]),
                "minimum_window_coverage_rate": min(float(row["window_coverage_rate"]) for row in selected) if selected else math.nan,
                "mean_pnl_per_eligible_market": mean_market,
                "bootstrap_ci_low_per_eligible_market": low,
                "bootstrap_ci_high_per_eligible_market": high,
                "mean_paired_difference_vs_4_5m_per_market": diff_mean,
                "paired_difference_ci_low": diff_low,
                "paired_difference_ci_high": diff_high,
                "mean_pnl_per_filled_entry": _mean(pnl_filled),
                "profitable_rate_per_filled_entry": _mean([bool(row["profitable"]) for row in completed]),
                "protected_target_fill_rate": _mean([bool(row["target_filled"]) for row in completed]),
                "fallback_rate": _mean([bool(row["fallback_used"]) for row in completed]),
                "favored_side_won_rate": _mean([bool(row["favored_side_won"]) for row in completed]),
                "full_capital_loss_rate": _mean([bool(row["full_capital_loss"]) for row in completed]),
                "median_decision_seconds_remaining": statistics.median(
                    float(row["seconds_remaining"]) for row in completed
                ) if completed else math.nan,
                "mean_entry_average_price": _mean([float(row["entry_average_price"]) for row in completed]),
                "pnl_05_quantile_per_filled_entry": _quantile(pnl_filled, 0.05),
                "worst_pnl_per_filled_entry": min(pnl_filled) if pnl_filled else math.nan,
                "holdout_read": False,
                "external_btc_data_used": False,
                "orders_placed": False,
            })
    return output


def verify_summary(summary: Sequence[Mapping[str, Any]]) -> None:
    baseline = next(
        row for row in summary if row["segment"] == "all_96" and row["scenario"] == BASELINE
    )
    if int(baseline["entry_filled_markets"]) != EXPECTED_BASELINE_ENTRIES:
        raise TimeWindowError(
            f"expected 57 causal native 4-5m entries; found {baseline['entry_filled_markets']}"
        )
    if abs(float(baseline["mean_paired_difference_vs_4_5m_per_market"])) > 1e-12:
        raise TimeWindowError("4-5m baseline paired difference is not zero")


def _money(value: Any) -> str:
    number = float(value)
    return "n/a" if math.isnan(number) else f"${number:.2f}"


def _percent(value: Any) -> str:
    number = float(value)
    return "n/a" if math.isnan(number) else f"{number:.1%}"


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    rows = [row for row in summary if row["segment"] == "all_96"]
    lines = [
        "# KXBTC15M H3 causal time-window diagnostic",
        "",
        "**Matched development window study; monitoring and rule frozen; holdout sealed.**",
        "",
        "Every scenario checks each causally received archived response. The favored-midpoint "
        "band remains 90% to below 98%; entry latency, $100 sizing, full-depth execution, fees, "
        "protected 50%-of-maximum target, and ten-second preclose fallback are unchanged.",
        "",
        "The four disjoint windows are counterfactual alternatives and are not additive trades. "
        "The expanded row is the first qualifying trigger across 4 to 15 minutes remaining and "
        "represents the direct operational consequence of opening monitoring earlier.",
        "",
        "| Scenario | Trigger | Filled | Coverage min | Mean / market | 95% CI | vs 4-5m | Paired 95% CI | Mean / fill | Profitable | Target fill | Favored won | Full loss | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['scenario']} | {_percent(row['trigger_rate_per_market'])} | "
            f"{row['entry_filled_markets']} | {_percent(row['minimum_window_coverage_rate'])} | "
            f"{_money(row['mean_pnl_per_eligible_market'])} | "
            f"{_money(row['bootstrap_ci_low_per_eligible_market'])} to {_money(row['bootstrap_ci_high_per_eligible_market'])} | "
            f"{_money(row['mean_paired_difference_vs_4_5m_per_market'])} | "
            f"{_money(row['paired_difference_ci_low'])} to {_money(row['paired_difference_ci_high'])} | "
            f"{_money(row['mean_pnl_per_filled_entry'])} | {_percent(row['profitable_rate_per_filled_entry'])} | "
            f"{_percent(row['protected_target_fill_rate'])} | {_percent(row['favored_side_won_rate'])} | "
            f"{_percent(row['full_capital_loss_rate'])} | {_money(row['pnl_05_quantile_per_filled_entry'])} | "
            f"{_money(row['worst_pnl_per_filled_entry'])} |"
        )
    lines.extend([
        "",
        "Mean P&L per eligible market assigns $0 to no-trade markets. The paired interval is "
        "the primary comparison against the frozen causal-native 4-5 minute baseline. Earlier/"
        "later chronological rows and individual signal origins remain in the CSVs.",
        "",
        "This is a bounded multi-window development diagnostic, not authorization to choose the "
        "largest row as an unbiased edge. No external BTC data, authentication, order, or holdout "
        "observation is used.",
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
        default=Path("analysis/kxbtc15m_h3_time_windows"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_time_windows_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise TimeWindowError(f"expected 96 eligible markets; found {len(eligible)}")
        if set(outcomes) != {market.ticker for market in eligible}:
            raise TimeWindowError("outcome ticker set does not equal development market set")

        for number, market in enumerate(eligible, start=1):
            _legacy, snapshots = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            segment = "earlier_64" if market.index <= 64 else "later_32"
            market_rows: list[dict[str, Any]] = []
            for scenario, start_seconds, end_seconds in (*WINDOWS, EXPANDED):
                market_rows.append(simulate_window(
                    snapshots=snapshots,
                    close_time=close,
                    winning_side=outcomes[market.ticker],
                    ticker=market.ticker,
                    scenario=scenario,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    segment=segment,
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

    summary = summarize(rows)
    verify_summary(summary)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = args.output_dir / "kxbtc15m_h3_time_windows_scenarios.csv"
    summary_path = args.output_dir / "kxbtc15m_h3_time_windows_summary.csv"
    report_path = args.output_dir / "KXBTC15M_H3_TIME_WINDOWS.md"
    write_csv(scenario_path, rows)
    write_csv(summary_path, summary)
    report_path.write_text(markdown_report(summary), encoding="utf-8")

    print("KXBTC15M H3 causal time-window diagnostic: PASS")
    print("Eligible development markets: 96")
    print("Monitoring: every causal archived response")
    print("Entry band: 90% to below 98% (unchanged)")
    print("Causal native 4-5m baseline reproduced: True")
    print("Holdout read: False")
    print("Orders placed: False")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, TimeWindowError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"KXBTC15M H3 time-window error: {exc}") from exc
