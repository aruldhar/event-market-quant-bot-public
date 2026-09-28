#!/usr/bin/env python3
"""Reassess H3 cash-exit policies on causal native 4-5m entries.

The first 90%-to-below-98% favored-midpoint state is detected at every raw HTTP
response receipt during the frozen 4-to-5-minute entry window.  Every policy
receives the same one-second-delayed full-depth entry, $100 maximum budget, and
fees.  Only the cash-exit rule changes.  The separate holdout remains sealed.
"""

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
from analyze_kxbtc15m_h3_exit_policies import (
    PRECLOSE_EXIT_SECONDS,
    _find_preclose_exit,
    percentage_target,
)
from analyze_kxbtc15m_h3_frequency import (
    HIGH_EXCLUSIVE,
    LOW,
    TARGET_FRACTION,
    _average_price,
    _decimal_text,
    _raw_snapshot_sets,
    simulate_market as simulate_frequency_market,
)
from analyze_kxbtc15m_h3_late_convergence import favored_quote
from analyze_kxbtc15m_h3_target_protection import find_protected_target_exit
from analyze_kxbtc15m_h3_time_windows import _bootstrap, _mean, _money, _percent, _quantile
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    safe_extract_zip,
    select_development_manifests,
)


WINDOW_START_SECONDS = 300
WINDOW_END_SECONDS = 240
EXPECTED_NATIVE_ENTRIES = 57
POLICIES = (
    ("protected_fixed_1usd", "Protected $1", "fixed", Decimal("1")),
    ("protected_25pct_max", "Protected 25% max", "fraction", Decimal("0.25")),
    ("protected_50pct_max", "Protected 50% max", "fraction", TARGET_FRACTION),
    ("protected_75pct_max", "Protected 75% max", "fraction", Decimal("0.75")),
    ("hold_to_settlement", "Hold to settlement", "settlement", Decimal("0")),
)
BASELINE_POLICY = "protected_50pct_max"


class NativeExitPolicyError(RuntimeError):
    """Raised when the native exit-policy diagnostic fails closed."""


def _policy_label(policy: str) -> str:
    return next(label for name, label, _kind, _value in POLICIES if name == policy)


def _base_row(
    *, ticker: str, segment: str, policy: str, close_time: datetime
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "diagnostic_segment": segment,
        "exit_policy": policy,
        "clock_basis": "causal_response_receipt",
        "monitoring_frequency": "native_archived_response",
        "entry_window": "240 < seconds_remaining <= 300",
        "entry_band": "0.90 <= favored_midpoint < 0.98",
        "close_time": close_time.isoformat(),
        "status": "no_trigger",
        "triggered": False,
        "entry_filled": False,
        "pnl": "",
        "holdout_read": False,
        "external_btc_data_used": False,
        "orders_placed": False,
    }


def find_native_entry(
    snapshots: Sequence[Snapshot], close_time: datetime
) -> tuple[int, int, str, Decimal, Decimal, Any] | None:
    start = close_time - timedelta(seconds=WINDOW_START_SECONDS)
    stop = close_time - timedelta(seconds=WINDOW_END_SECONDS)
    for decision_index, decision in enumerate(snapshots):
        if decision.observed_at < start:
            continue
        if decision.observed_at >= stop:
            break
        quote = favored_quote(decision.book)
        if quote is None:
            continue
        side, midpoint, ask = quote
        if not (LOW <= midpoint < HIGH_EXCLUSIVE):
            continue
        entry_index = first_index_at_or_after(
            snapshots,
            decision_index + 1,
            decision.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if entry_index is None or snapshots[entry_index].observed_at >= close_time:
            return None
        entry = buy_with_budget(snapshots[entry_index].book.ask_levels(side), MAX_BUDGET)
        if entry.quantity <= 0:
            return None
        maximum_profit = entry.quantity - entry.buy_outflow
        if maximum_profit <= 0:
            return None
        return decision_index, entry_index, side, midpoint, ask, entry
    return None


def simulate_policy(
    *, snapshots: Sequence[Snapshot], close_time: datetime, winning_side: str,
    ticker: str, segment: str, policy: str, kind: str, value: Decimal,
    entry_context: tuple[int, int, str, Decimal, Decimal, Any] | None,
) -> dict[str, Any]:
    row = _base_row(
        ticker=ticker, segment=segment, policy=policy, close_time=close_time
    )
    if entry_context is None:
        return row
    decision_index, entry_index, side, midpoint, decision_ask, entry = entry_context
    decision = snapshots[decision_index]
    entry_snapshot = snapshots[entry_index]
    maximum_profit = entry.quantity - entry.buy_outflow
    settlement_gross = entry.quantity if side == winning_side else Decimal("0")
    settlement_pnl = settlement_gross - entry.buy_outflow
    row.update({
        "triggered": True,
        "entry_filled": True,
        "status": "completed",
        "decision_time": decision.observed_at.isoformat(),
        "seconds_remaining": _decimal_text(
            Decimal(str((close_time - decision.observed_at).total_seconds()))
        ),
        "side": side,
        "favored_side_won": side == winning_side,
        "decision_favored_midpoint": _decimal_text(midpoint),
        "decision_favored_ask": _decimal_text(decision_ask),
        "entry_execution_time": entry_snapshot.observed_at.isoformat(),
        "realized_entry_delay_seconds": f"{(entry_snapshot.observed_at - decision.observed_at).total_seconds():.6f}",
        "contracts": _decimal_text(entry.quantity),
        "entry_gross": _decimal_text(entry.gross),
        "entry_fee": _decimal_text(entry.fee),
        "cash_deployed": _decimal_text(entry.buy_outflow),
        "entry_average_price": _decimal_text(_average_price(entry)),
        "maximum_settlement_profit": _decimal_text(maximum_profit),
        "settlement_counterfactual_pnl": _decimal_text(settlement_pnl),
    })

    if kind == "settlement":
        row.update({
            "target_amount": "",
            "target_fraction_of_maximum": "",
            "target_signal_count": 0,
            "target_rejected_after_latency_count": 0,
            "target_filled": False,
            "fallback_used": False,
            "exit_reason": "settlement",
            "exit_execution_time": close_time.isoformat(),
            "exit_gross": _decimal_text(settlement_gross),
            "exit_fee": "0",
            "exit_average_price": "1" if side == winning_side else "0",
            "pnl": _decimal_text(settlement_pnl),
            "profitable": settlement_pnl > 0,
            "full_capital_loss": settlement_pnl <= -Decimal("0.90") * entry.buy_outflow,
            "exposure_seconds": f"{(close_time - entry_snapshot.observed_at).total_seconds():.6f}",
        })
        return row

    target = value if kind == "fixed" else percentage_target(maximum_profit, value)
    preclose = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
    execution, exit_time, target_signals, target_rejected = find_protected_target_exit(
        snapshots=snapshots,
        start_index=entry_index + 1,
        stop_time=preclose,
        side=side,
        quantity=entry.quantity,
        outflow=entry.buy_outflow,
        target=target,
    )
    exit_reason = "protected_profit_target"
    if execution is None:
        execution, exit_time = _find_preclose_exit(
            snapshots=snapshots,
            start_index=entry_index + 1,
            start_time=preclose,
            close_time=close_time,
            side=side,
            quantity=entry.quantity,
        )
        exit_reason = "preclose_time_exit"

    if execution is None:
        pnl = settlement_pnl
        exit_reason = "settlement_after_preclose_liquidity_failure"
        exit_time = close_time
        exit_gross = settlement_gross
        exit_fee = Decimal("0")
        exit_average = Decimal("1") if side == winning_side else Decimal("0")
    else:
        pnl = execution.sell_inflow - entry.buy_outflow
        exit_gross = execution.gross
        exit_fee = execution.fee
        exit_average = _average_price(execution)

    row.update({
        "target_amount": _decimal_text(target),
        "target_fraction_of_maximum": _decimal_text(value) if kind == "fraction" else "",
        "target_signal_count": target_signals,
        "target_rejected_after_latency_count": target_rejected,
        "target_filled": exit_reason == "protected_profit_target",
        "fallback_used": exit_reason != "protected_profit_target",
        "exit_reason": exit_reason,
        "exit_execution_time": exit_time.isoformat(),
        "exit_gross": _decimal_text(exit_gross),
        "exit_fee": _decimal_text(exit_fee),
        "exit_average_price": _decimal_text(exit_average),
        "pnl": _decimal_text(pnl),
        "profitable": pnl > 0,
        "full_capital_loss": pnl <= -Decimal("0.90") * entry.buy_outflow,
        "exposure_seconds": f"{(exit_time - entry_snapshot.observed_at).total_seconds():.6f}",
    })
    return row


def verify_baseline_reproduction(
    baseline: Mapping[str, Any], frequency: Mapping[str, Any]
) -> None:
    fields = (
        "status", "triggered", "entry_filled", "decision_time",
        "entry_execution_time", "exit_reason", "pnl",
    )
    mismatches = [
        field for field in fields
        if baseline.get(field, "") != frequency.get(field, "")
    ]
    if mismatches:
        raise NativeExitPolicyError(
            f"{baseline['ticker']}: protected-50% native reproduction mismatch: {mismatches}"
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
            for row in source if row["exit_policy"] == BASELINE_POLICY
        }
        for policy, label, _kind, _value in POLICIES:
            selected = [row for row in source if row["exit_policy"] == policy]
            completed = [row for row in selected if row["status"] == "completed"]
            pnl_market = [float(row["pnl"] or 0.0) for row in selected]
            pnl_filled = [float(row["pnl"]) for row in completed]
            mean_market, ci_low, ci_high = _bootstrap(pnl_market)
            differences = [
                float(row["pnl"] or 0.0) - baseline[str(row["ticker"])]
                for row in selected
            ]
            diff_mean, diff_low, diff_high = _bootstrap(differences)
            exposure = [float(row["exposure_seconds"]) for row in completed]
            output.append({
                "segment": segment,
                "exit_policy": policy,
                "display_policy": label,
                "eligible_markets": len(selected),
                "triggered_markets": sum(bool(row["triggered"]) for row in selected),
                "entry_filled_markets": len(completed),
                "mean_pnl_per_eligible_market": mean_market,
                "bootstrap_ci_low_per_eligible_market": ci_low,
                "bootstrap_ci_high_per_eligible_market": ci_high,
                "mean_paired_difference_vs_protected_50pct": diff_mean,
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
                "settlement_exit_rate": _mean(
                    ["settlement" in str(row["exit_reason"]) for row in completed]
                ),
                "favored_side_won_rate": _mean(
                    [bool(row["favored_side_won"]) for row in completed]
                ),
                "full_capital_loss_rate": _mean(
                    [bool(row["full_capital_loss"]) for row in completed]
                ),
                "mean_exposure_seconds": _mean(exposure),
                "median_exposure_seconds": statistics.median(exposure)
                if exposure else math.nan,
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
        if row["segment"] == "all_96" and row["exit_policy"] == BASELINE_POLICY
    )
    if int(baseline["entry_filled_markets"]) != EXPECTED_NATIVE_ENTRIES:
        raise NativeExitPolicyError(
            f"expected 57 native entries; found {baseline['entry_filled_markets']}"
        )
    if abs(float(baseline["mean_paired_difference_vs_protected_50pct"])) > 1e-12:
        raise NativeExitPolicyError("protected-50% paired difference is not zero")


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    rows = [row for row in summary if row["segment"] == "all_96"]
    lines = [
        "# KXBTC15M H3 causal-native exit-policy reassessment",
        "",
        "**Matched development cash-exit diagnostic; entry frozen; holdout sealed.**",
        "",
        "All policies regenerate the same first causal native 90%-to-below-98% entry during "
        "4-to-5 minutes remaining. Every entry uses a one-second delay, archived full depth, "
        "$100 maximum budget, and conservative fees. Target policies monitor every subsequent "
        "causal response and execute only when the one-second-delayed full sale still meets the "
        "target after fees. Otherwise they keep monitoring, then attempt the frozen ten-second "
        "preclose cash fallback.",
        "",
        "| Exit policy | Filled | Mean / market | 95% CI | vs protected 50% | Paired 95% CI | Mean / fill | Profitable | Target fill | Fallback | Settlement | Full loss | Mean exposure | Median exposure | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['display_policy']} | {row['entry_filled_markets']} | "
            f"{_money(row['mean_pnl_per_eligible_market'])} | "
            f"{_money(row['bootstrap_ci_low_per_eligible_market'])} to "
            f"{_money(row['bootstrap_ci_high_per_eligible_market'])} | "
            f"{_money(row['mean_paired_difference_vs_protected_50pct'])} | "
            f"{_money(row['paired_difference_ci_low'])} to "
            f"{_money(row['paired_difference_ci_high'])} | "
            f"{_money(row['mean_pnl_per_filled_entry'])} | "
            f"{_percent(row['profitable_rate_per_filled_entry'])} | "
            f"{_percent(row['protected_target_fill_rate'])} | "
            f"{_percent(row['fallback_rate'])} | "
            f"{_percent(row['settlement_exit_rate'])} | "
            f"{_percent(row['full_capital_loss_rate'])} | "
            f"{float(row['mean_exposure_seconds']):.1f}s | "
            f"{float(row['median_exposure_seconds']):.1f}s | "
            f"{_money(row['pnl_05_quantile_per_filled_entry'])} | "
            f"{_money(row['worst_pnl_per_filled_entry'])} |"
        )
    lines.extend([
        "",
        "Mean P&L per eligible market counts the 39 no-trigger markets as $0 and is the primary "
        "comparison. Mean per fill and exposure duration are secondary. Hold-to-settlement is a "
        "risk/upside counterfactual, not a cash-out policy.",
        "",
        "The protected-50% row must reproduce the accepted causal-native H3 result market by "
        "market before this report is written. This is still an adaptive development comparison; "
        "the best row is not an unbiased expected return or a guarantee. No external BTC data, "
        "authentication, order, or holdout observation is used.",
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
        default=Path("analysis/kxbtc15m_h3_native_exit_policies"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_native_exit_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise NativeExitPolicyError(
                f"expected 96 eligible markets; found {len(eligible)}"
            )
        if set(outcomes) != {market.ticker for market in eligible}:
            raise NativeExitPolicyError(
                "outcome ticker set does not equal development market set"
            )

        for number, market in enumerate(eligible, start=1):
            _legacy, snapshots = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            segment = "earlier_64" if market.index <= 64 else "later_32"
            context = find_native_entry(snapshots, close)
            market_rows = [
                simulate_policy(
                    snapshots=snapshots,
                    close_time=close,
                    winning_side=outcomes[market.ticker],
                    ticker=market.ticker,
                    segment=segment,
                    policy=policy,
                    kind=kind,
                    value=value,
                    entry_context=context,
                )
                for policy, _label, kind, value in POLICIES
            ]
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
            baseline = next(
                row for row in market_rows if row["exit_policy"] == BASELINE_POLICY
            )
            verify_baseline_reproduction(baseline, frequency)
            rows.extend(market_rows)
            print(f"[{number:02d}/96] {market.ticker}")

    summary = summarize(rows)
    verify_summary(summary)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = args.output_dir / "kxbtc15m_h3_native_exit_policy_scenarios.csv"
    summary_path = args.output_dir / "kxbtc15m_h3_native_exit_policy_summary.csv"
    report_path = args.output_dir / "KXBTC15M_H3_NATIVE_EXIT_POLICIES.md"
    write_csv(scenario_path, rows)
    write_csv(summary_path, summary)
    report_path.write_text(markdown_report(summary), encoding="utf-8")

    print("KXBTC15M H3 causal-native exit-policy reassessment: PASS")
    print("Eligible development markets: 96")
    print("Causal native entries: 57")
    print(f"Matched exit policies: {len(POLICIES)}")
    print("Protected 50% native baseline reproduced: True")
    print("Holdout read: False")
    print("Orders placed: False")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (
        AuditError,
        NativeExitPolicyError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise SystemExit(f"KXBTC15M H3 native exit-policy error: {exc}") from exc
