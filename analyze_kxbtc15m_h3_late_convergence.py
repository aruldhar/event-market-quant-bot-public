#!/usr/bin/env python3
"""Development-only KXBTC15M H3 late-convergence diagnostic.

H3 asks whether the currently favored Kalshi side, when already expensive late
in the 15-minute market, continues converging enough to support an executable
profit.  The diagnostic uses only archived Kalshi order books available at the
decision timestamp.  It does not use an underlying BTC value, final settlement
margin, authenticated data, or any observation from the frozen holdout.

Rows are sampled on a five-second grid during the final five minutes.  They are
overlapping state diagnostics, not simultaneous portfolio trades.  Every entry
crosses archived full depth after one second, charges conservative taker fees,
and uses a fixed $100 maximum budget.
"""

from __future__ import annotations

import argparse
import csv
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
    NET_PROFIT_TARGET,
    SimulationError,
    Snapshot,
    best_ask,
    buy_with_budget,
    clustered_mean_ci,
    first_index_at_or_after,
    load_outcomes,
    load_snapshots,
    sell_quantity,
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


GRID_SECONDS = 5
DIAGNOSTIC_WINDOW_SECONDS = 300
LAST_ANCHOR_SECONDS_BEFORE_CLOSE = 5
MAX_ANCHOR_LAG_SECONDS = 2.0
PRECLOSE_EXIT_SECONDS = 10
DIAGNOSTIC_SPLIT_MARKETS = 64

EXIT_POLICIES = (
    "hold_to_settlement",
    "target_or_settlement",
    "target_or_preclose_10s",
)


def best_bid(book: Any, side: str) -> Decimal | None:
    levels = book.bid_levels(side)
    return levels[-1][0] if levels else None


def midpoint(book: Any, side: str) -> Decimal | None:
    bid = best_bid(book, side)
    ask = best_ask(book, side)
    if bid is None or ask is None:
        return None
    return (bid + ask) / Decimal("2")


def favored_quote(book: Any) -> tuple[str, Decimal, Decimal] | None:
    """Return favored side, midpoint, and executable ask.

    Direction is selected using the midpoint so a wider spread cannot make a
    side look favored merely because its ask is high.  The actual entry price
    remains the executable ask after latency.
    """

    yes_mid = midpoint(book, "YES")
    no_mid = midpoint(book, "NO")
    if yes_mid is None or no_mid is None or yes_mid == no_mid:
        return None
    side = "YES" if yes_mid > no_mid else "NO"
    ask = best_ask(book, side)
    if ask is None:
        return None
    return side, (yes_mid if side == "YES" else no_mid), ask


def probability_band(value: float) -> str:
    if value < 0.60:
        return "01_50_60c"
    if value < 0.70:
        return "02_60_70c"
    if value < 0.80:
        return "03_70_80c"
    if value < 0.90:
        return "04_80_90c"
    if value < 0.95:
        return "05_90_95c"
    if value < 0.98:
        return "06_95_98c"
    return "07_98_100c"


def remaining_time_band(seconds: float) -> str:
    if seconds > 240:
        return "01_240_300s"
    if seconds > 180:
        return "02_180_240s"
    if seconds > 120:
        return "03_120_180s"
    if seconds > 90:
        return "04_90_120s"
    if seconds > 60:
        return "05_60_90s"
    if seconds > 30:
        return "06_30_60s"
    return "07_0_30s"


def _settlement_result(
    *, side: str, winning_side: str, quantity: Decimal, outflow: Decimal
) -> tuple[Decimal, Decimal]:
    inflow = quantity if side == winning_side else Decimal("0")
    return inflow, inflow - outflow


def _completed_row(
    *,
    base: Mapping[str, Any],
    policy: str,
    exit_reason: str,
    exit_time: datetime,
    exit_gross: Decimal,
    exit_fee: Decimal,
    entry_fee: Decimal,
    pnl: Decimal,
    quantity: Decimal,
    outflow: Decimal,
    target_signal_seen: bool,
    target_achieved_after_latency: bool,
    missed_target_signals: int,
) -> dict[str, Any]:
    return {
        **base,
        "exit_policy": policy,
        "status": "completed",
        "contracts": float(quantity),
        "cash_deployed": float(outflow),
        "budget_utilization": float(outflow / MAX_BUDGET),
        "entry_fee": float(entry_fee),
        "exit_time": exit_time.isoformat(),
        "exit_reason": exit_reason,
        "exit_gross": float(exit_gross),
        "exit_fee": float(exit_fee),
        "total_fees": float(entry_fee + exit_fee),
        "pnl": float(pnl),
        "return_on_max_budget": float(pnl / MAX_BUDGET),
        "return_on_deployed": float(pnl / outflow),
        "profitable": pnl > 0,
        "target_signal_seen": target_signal_seen,
        "target_achieved_after_latency": target_achieved_after_latency,
        "missed_target_signals": missed_target_signals,
    }


def _find_target_exit(
    *,
    snapshots: Sequence[Snapshot],
    start_index: int,
    stop_time: datetime,
    side: str,
    quantity: Decimal,
    outflow: Decimal,
) -> tuple[Any | None, datetime | None, bool, bool, int]:
    target_signal_seen = False
    missed = 0
    for index in range(start_index, len(snapshots)):
        observed = snapshots[index]
        if observed.observed_at >= stop_time:
            break
        hypothetical = sell_quantity(observed.book.bid_levels(side), quantity)
        if (
            hypothetical.quantity != quantity
            or hypothetical.sell_inflow - outflow < NET_PROFIT_TARGET
        ):
            continue
        target_signal_seen = True
        delayed_index = first_index_at_or_after(
            snapshots,
            index + 1,
            observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if delayed_index is None or snapshots[delayed_index].observed_at >= stop_time:
            missed += 1
            continue
        executed = sell_quantity(
            snapshots[delayed_index].book.bid_levels(side), quantity
        )
        if executed.quantity != quantity:
            missed += 1
            continue
        pnl = executed.sell_inflow - outflow
        return (
            executed,
            snapshots[delayed_index].observed_at,
            target_signal_seen,
            pnl >= NET_PROFIT_TARGET,
            missed,
        )
    return None, None, target_signal_seen, False, missed


def _find_preclose_exit(
    *,
    snapshots: Sequence[Snapshot],
    start_index: int,
    start_time: datetime,
    close_time: datetime,
    side: str,
    quantity: Decimal,
) -> tuple[Any | None, datetime | None]:
    index = first_index_at_or_after(snapshots, start_index, start_time)
    while index is not None and index < len(snapshots):
        observed = snapshots[index]
        delayed_index = first_index_at_or_after(
            snapshots,
            index + 1,
            observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if delayed_index is None or snapshots[delayed_index].observed_at >= close_time:
            break
        executed = sell_quantity(
            snapshots[delayed_index].book.bid_levels(side), quantity
        )
        if executed.quantity == quantity:
            return executed, snapshots[delayed_index].observed_at
        index = delayed_index + 1
    return None, None


def simulate_h3_entry(
    *,
    snapshots: Sequence[Snapshot],
    decision_index: int,
    close_time: datetime,
    winning_side: str,
) -> list[dict[str, Any]]:
    decision = snapshots[decision_index]
    seconds_remaining = (close_time - decision.observed_at).total_seconds()
    quote = favored_quote(decision.book)
    base: dict[str, Any] = {
        "decision_time": decision.observed_at.isoformat(),
        "seconds_remaining": seconds_remaining,
        "time_remaining_band": remaining_time_band(seconds_remaining),
        "max_budget": float(MAX_BUDGET),
    }
    if quote is None:
        return [{**base, "exit_policy": policy, "status": "favored_side_unavailable"}
                for policy in EXIT_POLICIES]
    side, favored_midpoint, decision_ask = quote
    base.update({
        "side": side,
        "decision_favored_midpoint": float(favored_midpoint),
        "decision_favored_ask": float(decision_ask),
        "favored_probability_band": probability_band(float(favored_midpoint)),
        "favored_side_won": side == winning_side,
    })

    execution_index = first_index_at_or_after(
        snapshots,
        decision_index + 1,
        decision.observed_at + timedelta(seconds=LATENCY_SECONDS),
    )
    if execution_index is None or snapshots[execution_index].observed_at >= close_time:
        return [{**base, "exit_policy": policy, "status": "entry_missed_close"}
                for policy in EXIT_POLICIES]
    entry_snapshot = snapshots[execution_index]
    fill_ask = best_ask(entry_snapshot.book, side)
    if fill_ask is None:
        return [{**base, "exit_policy": policy, "status": "entry_book_unavailable"}
                for policy in EXIT_POLICIES]
    entry = buy_with_budget(entry_snapshot.book.ask_levels(side), MAX_BUDGET)
    if entry.quantity <= 0:
        return [{**base, "exit_policy": policy, "status": "entry_unfilled"}
                for policy in EXIT_POLICIES]

    quantity = entry.quantity
    outflow = entry.buy_outflow
    settlement_gross, settlement_pnl = _settlement_result(
        side=side,
        winning_side=winning_side,
        quantity=quantity,
        outflow=outflow,
    )
    base.update({
        "entry_execution_time": entry_snapshot.observed_at.isoformat(),
        "entry_best_ask": float(fill_ask),
        "entry_average_price": float(entry.gross / quantity),
    })

    output = [
        _completed_row(
            base=base,
            policy="hold_to_settlement",
            exit_reason="settlement",
            exit_time=close_time,
            exit_gross=settlement_gross,
            exit_fee=Decimal("0"),
            entry_fee=entry.fee,
            pnl=settlement_pnl,
            quantity=quantity,
            outflow=outflow,
            target_signal_seen=False,
            target_achieved_after_latency=False,
            missed_target_signals=0,
        )
    ]

    target_execution, target_time, signal, achieved, missed = _find_target_exit(
        snapshots=snapshots,
        start_index=execution_index + 1,
        stop_time=close_time,
        side=side,
        quantity=quantity,
        outflow=outflow,
    )
    if target_execution is None:
        output.append(_completed_row(
            base=base,
            policy="target_or_settlement",
            exit_reason="settlement_after_no_target",
            exit_time=close_time,
            exit_gross=settlement_gross,
            exit_fee=Decimal("0"),
            entry_fee=entry.fee,
            pnl=settlement_pnl,
            quantity=quantity,
            outflow=outflow,
            target_signal_seen=signal,
            target_achieved_after_latency=False,
            missed_target_signals=missed,
        ))
    else:
        output.append(_completed_row(
            base=base,
            policy="target_or_settlement",
            exit_reason="profit_target",
            exit_time=target_time,
            exit_gross=target_execution.gross,
            exit_fee=target_execution.fee,
            entry_fee=entry.fee,
            pnl=target_execution.sell_inflow - outflow,
            quantity=quantity,
            outflow=outflow,
            target_signal_seen=signal,
            target_achieved_after_latency=achieved,
            missed_target_signals=missed,
        ))

    preclose_start = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
    target_execution, target_time, signal, achieved, missed = _find_target_exit(
        snapshots=snapshots,
        start_index=execution_index + 1,
        stop_time=preclose_start,
        side=side,
        quantity=quantity,
        outflow=outflow,
    )
    if target_execution is not None:
        output.append(_completed_row(
            base=base,
            policy="target_or_preclose_10s",
            exit_reason="profit_target",
            exit_time=target_time,
            exit_gross=target_execution.gross,
            exit_fee=target_execution.fee,
            entry_fee=entry.fee,
            pnl=target_execution.sell_inflow - outflow,
            quantity=quantity,
            outflow=outflow,
            target_signal_seen=signal,
            target_achieved_after_latency=achieved,
            missed_target_signals=missed,
        ))
    else:
        forced, forced_time = _find_preclose_exit(
            snapshots=snapshots,
            start_index=execution_index + 1,
            start_time=preclose_start,
            close_time=close_time,
            side=side,
            quantity=quantity,
        )
        if forced is None:
            output.append(_completed_row(
                base=base,
                policy="target_or_preclose_10s",
                exit_reason="settlement_after_preclose_liquidity_failure",
                exit_time=close_time,
                exit_gross=settlement_gross,
                exit_fee=Decimal("0"),
                entry_fee=entry.fee,
                pnl=settlement_pnl,
                quantity=quantity,
                outflow=outflow,
                target_signal_seen=signal,
                target_achieved_after_latency=False,
                missed_target_signals=missed,
            ))
        else:
            output.append(_completed_row(
                base=base,
                policy="target_or_preclose_10s",
                exit_reason="preclose_time_exit",
                exit_time=forced_time,
                exit_gross=forced.gross,
                exit_fee=forced.fee,
                entry_fee=entry.fee,
                pnl=forced.sell_inflow - outflow,
                quantity=quantity,
                outflow=outflow,
                target_signal_seen=signal,
                target_achieved_after_latency=False,
                missed_target_signals=missed,
            ))
    return output


def _segment_rows(rows: Sequence[Mapping[str, Any]], segment: str) -> list[Mapping[str, Any]]:
    if segment == "all_96":
        return list(rows)
    key = "earlier_64" if segment == "earlier_64_diagnostic" else "later_32"
    return [row for row in rows if row["diagnostic_segment"] == key]


def _summary_row(
    rows: Sequence[Mapping[str, Any]], *, label_fields: Mapping[str, Any]
) -> dict[str, Any]:
    completed = [row for row in rows if row["status"] == "completed"]
    mean, low, high = clustered_mean_ci(completed, "pnl")
    return {
        **label_fields,
        "scenarios": len(completed),
        "markets": len({row["ticker"] for row in completed}),
        "mean_pnl_equal_market_weighted": mean,
        "mean_pnl_clustered_ci_low": low,
        "mean_pnl_clustered_ci_high": high,
        "median_pnl": statistics.median(float(row["pnl"]) for row in completed)
        if completed else math.nan,
        "profitable_rate": statistics.mean(bool(row["profitable"]) for row in completed)
        if completed else math.nan,
        "favored_side_win_rate": statistics.mean(bool(row["favored_side_won"]) for row in completed)
        if completed else math.nan,
        "target_hit_rate": statistics.mean(bool(row["target_achieved_after_latency"]) for row in completed)
        if completed else math.nan,
        "settlement_exit_rate": statistics.mean("settlement" in row["exit_reason"] for row in completed)
        if completed else math.nan,
        "mean_total_fees": statistics.mean(float(row["total_fees"]) for row in completed)
        if completed else math.nan,
    }


def summarize_core(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        source = _segment_rows(rows, segment)
        for policy in EXIT_POLICIES:
            subset = [
                row for row in source
                if row["exit_policy"] == policy
                and float(row.get("seconds_remaining", math.inf)) <= 120
                and float(row.get("decision_favored_midpoint", -math.inf)) >= 0.80
            ]
            output.append(_summary_row(
                subset,
                label_fields={
                    "segment": segment,
                    "definition": "within_120s_midpoint_80c_plus",
                    "exit_policy": policy,
                },
            ))
    return output


def summarize_cells(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    completed = [row for row in rows if row["status"] == "completed"]
    output: list[dict[str, Any]] = []
    for policy in EXIT_POLICIES:
        policy_rows = [row for row in completed if row["exit_policy"] == policy]
        time_values = sorted({str(row["time_remaining_band"]) for row in policy_rows})
        price_values = sorted({str(row["favored_probability_band"]) for row in policy_rows})
        for time_value in time_values:
            for price_value in price_values:
                subset = [
                    row for row in policy_rows
                    if row["time_remaining_band"] == time_value
                    and row["favored_probability_band"] == price_value
                ]
                if subset:
                    output.append(_summary_row(
                        subset,
                        label_fields={
                            "exit_policy": policy,
                            "time_remaining_band": time_value,
                            "favored_probability_band": price_value,
                        },
                    ))
    return output


def summarize_threshold_grid(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    completed = [row for row in rows if row["status"] == "completed"]
    for policy in EXIT_POLICIES:
        for maximum_seconds in (300, 180, 120, 90, 60):
            for minimum_probability in (0.70, 0.80, 0.90, 0.95):
                subset = [
                    row for row in completed
                    if row["exit_policy"] == policy
                    and float(row["seconds_remaining"]) <= maximum_seconds
                    and float(row["decision_favored_midpoint"]) >= minimum_probability
                ]
                output.append(_summary_row(
                    subset,
                    label_fields={
                        "exit_policy": policy,
                        "maximum_seconds_remaining": maximum_seconds,
                        "minimum_favored_midpoint": minimum_probability,
                    },
                ))
    return output


def _money(value: float) -> str:
    return "n/a" if math.isnan(value) else f"${value:.2f}"


def _percent(value: float) -> str:
    return "n/a" if math.isnan(value) else f"{value:.1%}"


def markdown_report(
    core: Sequence[Mapping[str, Any]],
    cells: Sequence[Mapping[str, Any]],
    scenario_count: int,
) -> str:
    lines = [
        "# KXBTC15M H3 late-convergence diagnostic",
        "",
        "**Development-only causal state study; holdout sealed.**",
        "",
        f"Scenario rows, including three matched exits per state: {scenario_count:,}.",
        "",
        "Every five seconds during the final five minutes, the diagnostic identifies the side "
        "with the higher order-book midpoint, waits one second, crosses archived full depth with "
        "at most $100, and charges conservative taker fees. No BTC index value or final settlement "
        "margin enters the decision.",
        "",
        "## Original H3 region",
        "",
        "The original Kalshi-only H3 region is a favored midpoint of at least 80 cents with no "
        "more than 120 seconds remaining.",
        "",
        "| Segment | Exit policy | Scenarios | Markets | Mean P&L / $100 | Clustered 95% CI | Profitable | Favored side won | Target hit |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in core:
        lines.append(
            f"| {row['segment']} | {row['exit_policy']} | {row['scenarios']} | "
            f"{row['markets']} | {_money(float(row['mean_pnl_equal_market_weighted']))} | "
            f"{_money(float(row['mean_pnl_clustered_ci_low']))} to "
            f"{_money(float(row['mean_pnl_clustered_ci_high']))} | "
            f"{_percent(float(row['profitable_rate']))} | "
            f"{_percent(float(row['favored_side_win_rate']))} | "
            f"{_percent(float(row['target_hit_rate']))} |"
        )

    eligible = [
        row for row in cells
        if row["exit_policy"] == "target_or_preclose_10s"
        and int(row["scenarios"]) >= 40
        and int(row["markets"]) >= 20
    ]
    ranked = sorted(
        eligible,
        key=lambda row: float(row["mean_pnl_equal_market_weighted"]),
        reverse=True,
    )
    lines.extend([
        "",
        "## Highest-mean executable cash-out cells",
        "",
        "Only target-or-preclose cells with at least 40 states and 20 markets are shown.",
        "",
        "| Time remaining | Favored midpoint | Scenarios | Markets | Mean P&L | Clustered 95% CI | Profitable | Target hit |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for row in ranked[:15]:
        lines.append(
            f"| {row['time_remaining_band']} | {row['favored_probability_band']} | "
            f"{row['scenarios']} | {row['markets']} | "
            f"{_money(float(row['mean_pnl_equal_market_weighted']))} | "
            f"{_money(float(row['mean_pnl_clustered_ci_low']))} to "
            f"{_money(float(row['mean_pnl_clustered_ci_high']))} | "
            f"{_percent(float(row['profitable_rate']))} | "
            f"{_percent(float(row['target_hit_rate']))} |"
        )
    lines.extend([
        "",
        "Rows overlap within a market and are not independent or additive trades. This diagnostic "
        "may identify a state region worth converting into one first-trigger-per-market rule, but "
        "it cannot itself authorize a holdout read. The same 96 development markets have already "
        "been explored extensively; any apparent H3 edge ultimately needs prospective validation.",
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
        default=Path("analysis/kxbtc15m_h3_late_convergence"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_h3_") as temporary:
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
                f"expected {EXPECTED_ELIGIBLE_MARKETS} eligible markets; found {len(eligible)}"
            )
        if set(outcomes) != {market.ticker for market in eligible}:
            raise SimulationError("outcome ticker set does not equal eligible development set")

        for number, market in enumerate(eligible, start=1):
            snapshots = load_snapshots(market, args.repo_root)
            close_time = market_close_utc(market.ticker)
            segment = "earlier_64" if market.index <= DIAGNOSTIC_SPLIT_MARKETS else "later_32"
            grid_start = close_time - timedelta(seconds=DIAGNOSTIC_WINDOW_SECONDS)
            for offset in range(
                0,
                DIAGNOSTIC_WINDOW_SECONDS - LAST_ANCHOR_SECONDS_BEFORE_CLOSE + 1,
                GRID_SECONDS,
            ):
                target = grid_start + timedelta(seconds=offset)
                decision_index = first_index_at_or_after(snapshots, 0, target)
                if decision_index is None:
                    continue
                decision = snapshots[decision_index]
                lag = (decision.observed_at - target).total_seconds()
                if lag < 0 or lag > MAX_ANCHOR_LAG_SECONDS:
                    continue
                scenario_rows = simulate_h3_entry(
                    snapshots=snapshots,
                    decision_index=decision_index,
                    close_time=close_time,
                    winning_side=outcomes[market.ticker],
                )
                for row in scenario_rows:
                    row.update({
                        "market_index": market.index,
                        "ticker": market.ticker,
                        "diagnostic_segment": segment,
                        "anchor_target_time": target.isoformat(),
                        "anchor_lag_seconds": lag,
                        "holdout_read": False,
                        "external_btc_data_used": False,
                    })
                    rows.append(row)
            print(f"[{number:02d}/96] {market.ticker}")

    core = summarize_core(rows)
    cells = summarize_cells(rows)
    threshold_grid = summarize_threshold_grid(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_h3_late_convergence_scenarios.csv", rows)
    write_csv(args.output_dir / "kxbtc15m_h3_late_convergence_core.csv", core)
    write_csv(args.output_dir / "kxbtc15m_h3_late_convergence_cells.csv", cells)
    write_csv(args.output_dir / "kxbtc15m_h3_late_convergence_threshold_grid.csv", threshold_grid)
    report_path = args.output_dir / "KXBTC15M_H3_LATE_CONVERGENCE.md"
    report_path.write_text(markdown_report(core, cells, len(rows)), encoding="utf-8")

    print("KXBTC15M H3 late-convergence diagnostic: PASS")
    print(f"Eligible development markets: {len(eligible)}")
    print(f"Scenario rows: {len(rows)}")
    print("Grid: every 5 seconds during final 5 minutes")
    print("H3 core: favored midpoint >= $0.80; <= 120 seconds remaining")
    print("Exit policies: hold, $1 target-or-settlement, $1 target-or-10s-preclose exit")
    print("Maximum budget per state: $100.00")
    print("Execution latency: 1.0 seconds")
    print("External BTC data used: no")
    print("Holdout read: False")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, OSError, SimulationError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"H3 diagnostic error: {exc}") from exc
