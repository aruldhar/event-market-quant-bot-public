#!/usr/bin/env python3
"""Causal entry-state audit for bounded KXBTC15M reversion."""

from __future__ import annotations

import argparse
import math
import statistics
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import (
    EXPECTED_ELIGIBLE_MARKETS,
    SimulationError,
    Snapshot,
    best_ask,
    choose_lower_side,
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


ANCHOR_MINUTES = tuple(range(5))
TRANCHE_COUNT = 3
FIXED_STOP = Decimal("5")
DIAGNOSTIC_SPLIT_MARKETS = 64


def decimal_float(value: Decimal | None) -> float:
    return math.nan if value is None else float(value)


def side_bid(snapshot: Snapshot, side: str) -> Decimal | None:
    levels = snapshot.book.bid_levels(side)
    return levels[-1][0] if levels else None


def near_depth(
    levels: Sequence[tuple[Decimal, Decimal]],
    *,
    side: str,
    is_ask: bool,
    cents: Decimal = Decimal("0.05"),
) -> Decimal:
    if not levels:
        return Decimal("0")
    ordered = tuple(levels) if is_ask else tuple(reversed(levels))
    best = ordered[0][0]
    if is_ask:
        return sum((quantity for price, quantity in ordered if price <= best + cents), Decimal("0"))
    return sum((quantity for price, quantity in ordered if price >= best - cents), Decimal("0"))


def trailing_prices(
    snapshots: Sequence[Snapshot],
    decision_index: int,
    side: str,
    seconds: float,
) -> list[tuple[float, Decimal]]:
    decision_time = snapshots[decision_index].observed_at
    start = decision_time - timedelta(seconds=seconds)
    values: list[tuple[float, Decimal]] = []
    for snapshot in snapshots[: decision_index + 1]:
        if snapshot.observed_at < start:
            continue
        price = best_ask(snapshot.book, side)
        if price is not None:
            values.append(((snapshot.observed_at - decision_time).total_seconds(), price))
    return values


def path_features(values: Sequence[tuple[float, Decimal]]) -> dict[str, float]:
    if len(values) < 2:
        return {
            "move": math.nan,
            "range": math.nan,
            "efficiency": math.nan,
            "drawdown": math.nan,
            "rebound": math.nan,
            "direction_changes": math.nan,
        }
    prices = [item[1] for item in values]
    changes = [float(later - earlier) for earlier, later in zip(prices, prices[1:])]
    path = sum(abs(change) for change in changes)
    signs = [1 if change > 0 else -1 for change in changes if change != 0]
    return {
        "move": float(prices[-1] - prices[0]),
        "range": float(max(prices) - min(prices)),
        "efficiency": 0.0 if path == 0 else float(prices[-1] - prices[0]) / path,
        "drawdown": float(max(prices) - prices[-1]),
        "rebound": float(prices[-1] - min(prices)),
        "direction_changes": float(sum(a != b for a, b in zip(signs, signs[1:]))),
    }


def entry_features(
    snapshots: Sequence[Snapshot], decision_index: int
) -> dict[str, Any]:
    decision = snapshots[decision_index]
    side = choose_lower_side(decision.book)
    if side is None:
        return {"feature_status": "side_unavailable"}
    ask = best_ask(decision.book, side)
    bid = side_bid(decision, side)
    assert ask is not None
    asks = decision.book.ask_levels(side)
    bids = decision.book.bid_levels(side)
    ask_depth = near_depth(asks, side=side, is_ask=True)
    bid_depth = near_depth(bids, side=side, is_ask=False)
    denominator = ask_depth + bid_depth
    depth_balance = (
        Decimal("0") if denominator == 0 else (bid_depth - ask_depth) / denominator
    )
    features: dict[str, Any] = {
        "feature_status": "complete",
        "decision_side": side,
        "decision_ask": float(ask),
        "decision_bid": decimal_float(bid),
        "decision_spread": math.nan if bid is None else float(ask - bid),
        "ask_depth_5c": float(ask_depth),
        "bid_depth_5c": float(bid_depth),
        "depth_balance_5c": float(depth_balance),
    }
    for window in (10, 30, 60):
        path = path_features(trailing_prices(snapshots, decision_index, side, window))
        for name, value in path.items():
            features[f"{name}_{window}s"] = value
    features["state_30s"] = state_30s(features)
    return features


def state_30s(row: Mapping[str, Any]) -> str:
    drawdown = float(row.get("drawdown_30s", math.nan))
    move10 = float(row.get("move_10s", math.nan))
    if math.isnan(drawdown) or math.isnan(move10):
        return "insufficient_history"
    if drawdown < 0.05:
        return "no_deep_drawdown"
    if move10 >= 0.01:
        return "deep_drawdown_rebounding"
    if move10 <= -0.01:
        return "deep_drawdown_still_falling"
    return "deep_drawdown_stabilizing"


def price_band(value: float) -> str:
    if math.isnan(value):
        return "missing"
    cents = int(value * 100)
    lower = min((cents // 10) * 10, 40)
    return f"{lower:02d}_{lower + 10:02d}c"


def signed_move_band(value: float) -> str:
    if math.isnan(value):
        return "missing"
    if value <= -0.05:
        return "01_down_5c_plus"
    if value <= -0.02:
        return "02_down_2_to_5c"
    if value < 0.02:
        return "03_flat_within_2c"
    if value < 0.05:
        return "04_up_2_to_5c"
    return "05_up_5c_plus"


def efficiency_band(value: float) -> str:
    if math.isnan(value):
        return "missing"
    if value <= -0.5:
        return "01_directional_fall"
    if value < 0.5:
        return "02_choppy"
    return "03_directional_rise"


def nonnegative_band(value: float) -> str:
    if math.isnan(value):
        return "missing"
    if value < 0.02:
        return "01_under_2c"
    if value < 0.05:
        return "02_2_to_5c"
    if value < 0.10:
        return "03_5_to_10c"
    return "04_10c_plus"


def spread_band(value: float) -> str:
    if math.isnan(value):
        return "missing"
    if value <= 0.01:
        return "01_1c_or_less"
    if value <= 0.02:
        return "02_1_to_2c"
    return "03_over_2c"


def depth_balance_band(value: float) -> str:
    if math.isnan(value):
        return "missing"
    if value <= -0.25:
        return "01_ask_heavy"
    if value < 0.25:
        return "02_balanced"
    return "03_bid_heavy"


FEATURE_BINS: tuple[tuple[str, Callable[[Mapping[str, Any]], str]], ...] = (
    ("anchor_minute", lambda row: str(row["anchor_minute"])),
    ("entry_price_band", lambda row: price_band(float(row["decision_ask"]))),
    ("spread_band", lambda row: spread_band(float(row["decision_spread"]))),
    ("move_10s_band", lambda row: signed_move_band(float(row["move_10s"]))),
    ("move_30s_band", lambda row: signed_move_band(float(row["move_30s"]))),
    ("efficiency_30s_band", lambda row: efficiency_band(float(row["efficiency_30s"]))),
    ("range_30s_band", lambda row: nonnegative_band(float(row["range_30s"]))),
    ("drawdown_30s_band", lambda row: nonnegative_band(float(row["drawdown_30s"]))),
    ("rebound_30s_band", lambda row: nonnegative_band(float(row["rebound_30s"]))),
    ("depth_balance_5c_band", lambda row: depth_balance_band(float(row["depth_balance_5c"]))),
    ("state_30s", lambda row: str(row["state_30s"])),
)


def percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def summarize_bins(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    segments = (
        ("all_96", lambda row: True),
        ("earlier_64_diagnostic", lambda row: row["diagnostic_segment"] == "earlier_64"),
        ("later_32_diagnostic", lambda row: row["diagnostic_segment"] == "later_32"),
    )
    for segment_name, predicate in segments:
        segment = [row for row in rows if predicate(row) and row["status"] == "completed"]
        for feature_name, classifier in FEATURE_BINS:
            values = sorted({classifier(row) for row in segment})
            for value in values:
                subset = [row for row in segment if classifier(row) == value]
                pnl = [float(row["pnl"]) for row in subset]
                mean, low, high = clustered_mean_ci(subset, "pnl")
                output.append({
                    "segment": segment_name,
                    "feature": feature_name,
                    "value": value,
                    "scenarios": len(subset),
                    "markets": len({row["ticker"] for row in subset}),
                    "mean_pnl_equal_market_weighted": mean,
                    "mean_pnl_clustered_ci_low": low,
                    "mean_pnl_clustered_ci_high": high,
                    "median_pnl": statistics.median(pnl) if pnl else math.nan,
                    "pnl_05_quantile": percentile(pnl, 0.05),
                    "profitable_rate": statistics.mean(bool(row["profitable"]) for row in subset) if subset else math.nan,
                    "profit_target_rate": statistics.mean(bool(row["target_achieved_after_latency"]) for row in subset) if subset else math.nan,
                    "stop_execution_rate": statistics.mean(bool(row["loss_stop_executed"]) for row in subset) if subset else math.nan,
                })
    return output


def markdown_report(summary: Sequence[Mapping[str, Any]], scenario_count: int) -> str:
    eligible = [
        row for row in summary
        if row["segment"] == "all_96" and row["markets"] >= 20 and row["scenarios"] >= 40
    ]
    ranked = sorted(eligible, key=lambda row: row["mean_pnl_equal_market_weighted"], reverse=True)
    lines = [
        "# KXBTC15M causal entry-state audit",
        "",
        "**Development-only diagnostic; holdout sealed.**",
        "",
        f"Entry scenarios: {scenario_count:,}. The exit policy is frozen to three equal-dollar "
        "tranches with the immediate executable -$5 stop, the least-negative simple exit policy.",
        "",
        "Every feature uses only order-book observations at or before the decision timestamp. "
        "No outcome, future quote, external BTC value, or holdout observation enters a feature.",
        "",
        "## Highest-mean broad state bins",
        "",
        "Only bins represented by at least 40 scenarios and 20 markets appear here. The full "
        "all/earlier/later diagnostic table is in `kxbtc15m_entry_state_bins.csv`.",
        "",
        "| Feature | State | Scenarios | Markets | Mean P&L | Clustered 95% CI | Profitable | Stop executed |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in ranked[:15]:
        lines.append(
            f"| {row['feature']} | {row['value']} | {row['scenarios']} | {row['markets']} | "
            f"${row['mean_pnl_equal_market_weighted']:.2f} | "
            f"${row['mean_pnl_clustered_ci_low']:.2f} to ${row['mean_pnl_clustered_ci_high']:.2f} | "
            f"{row['profitable_rate']:.1%} | {row['stop_execution_rate']:.1%} |"
        )
    lines.extend([
        "",
        "These are univariate descriptive bins, not a selected trading rule. A candidate state "
        "must show the same direction in the earlier-64 and later-32 diagnostic segments before "
        "we define a small causal filter or interpretable model. Because all 96 markets informed "
        "earlier strategy work, the split is a stability diagnostic rather than a pristine holdout.",
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
        default=Path("analysis/kxbtc15m_entry_states"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_entry_states_") as temporary:
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

        for eligible_order, market in enumerate(eligible, start=1):
            snapshots = load_snapshots(market, args.repo_root)
            close = market_close_utc(market.ticker)
            open_time = close - timedelta(minutes=15)
            segment = "earlier_64" if eligible_order <= DIAGNOSTIC_SPLIT_MARKETS else "later_32"
            for minute in ANCHOR_MINUTES:
                decision_index = first_index_at_or_after(
                    snapshots, 0, open_time + timedelta(minutes=minute)
                )
                if decision_index is None:
                    continue
                features = entry_features(snapshots, decision_index)
                result = simulate_policy(
                    snapshots=snapshots,
                    decision_index=decision_index,
                    close_time=close,
                    winning_side=outcomes[market.ticker],
                    tranche_count=TRANCHE_COUNT,
                    net_loss_stop=FIXED_STOP,
                )
                result.update(features)
                result.update({
                    "market_index": market.index,
                    "eligible_market_order": eligible_order,
                    "ticker": market.ticker,
                    "anchor_minute": minute,
                    "diagnostic_segment": segment,
                    "holdout_read": False,
                })
                rows.append(result)
            print(f"[{eligible_order:02d}/96] {market.ticker}")

    complete = [row for row in rows if row.get("feature_status") == "complete"]
    summary = summarize_bins(complete)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_entry_state_scenarios.csv", rows)
    write_csv(args.output_dir / "kxbtc15m_entry_state_bins.csv", summary)
    report_path = args.output_dir / "KXBTC15M_ENTRY_STATES.md"
    report_path.write_text(markdown_report(summary, len(rows)), encoding="utf-8")

    print("KXBTC15M causal entry-state audit: PASS")
    print(f"Eligible development markets: {len(eligible)}")
    print(f"Entry scenario rows: {len(rows)}")
    print(f"Complete causal feature rows: {len(complete)}")
    print("Fixed exit: 3 tranches, immediate -$5 executable stop")
    print("Features: decision price/spread/depth plus trailing 10/30/60-second path state")
    print("Diagnostic stability split: earlier 64 / later 32 eligible markets")
    print("External BTC data used: no")
    print("Holdout read: False")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, OSError, SimulationError, ValueError) as exc:
        raise SystemExit(f"Entry-state audit error: {exc}") from exc
