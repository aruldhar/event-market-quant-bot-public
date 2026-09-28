#!/usr/bin/env python3
"""Compare protected and unprotected 50%-max H3 exits on native entries."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import (
    EXPECTED_ELIGIBLE_MARKETS,
    MAX_BUDGET,
    Snapshot,
    load_outcomes,
    validate_fee_inputs,
    write_csv,
)
from analyze_kxbtc15m_h3_exit_policies import (
    PRECLOSE_EXIT_SECONDS,
    _find_preclose_exit,
    _find_target_exit,
    percentage_target,
)
from analyze_kxbtc15m_h3_frequency import (
    TARGET_FRACTION,
    _average_price,
    _decimal_text,
    _raw_snapshot_sets,
    simulate_market as simulate_frequency_market,
)
from analyze_kxbtc15m_h3_native_exit_policies import (
    EXPECTED_NATIVE_ENTRIES,
    _base_row,
    find_native_entry,
    simulate_policy,
    verify_baseline_reproduction,
)
from analyze_kxbtc15m_h3_time_windows import _bootstrap, _mean, _money, _percent, _quantile
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    safe_extract_zip,
    select_development_manifests,
)


POLICIES = (
    ("unprotected_50pct_max", "Unprotected 50%"),
    ("protected_50pct_max", "Protected 50%"),
)
BASELINE = "protected_50pct_max"


class NativeTargetProtectionError(RuntimeError):
    """Raised when the native target-protection comparison fails closed."""


def simulate_unprotected(
    *, snapshots: Sequence[Snapshot], close_time, winning_side: str,
    ticker: str, segment: str, entry_context,
) -> dict[str, Any]:
    row = _base_row(
        ticker=ticker,
        segment=segment,
        policy="unprotected_50pct_max",
        close_time=close_time,
    )
    row["target_protection_mode"] = "unprotected"
    if entry_context is None:
        return row
    decision_index, entry_index, side, midpoint, decision_ask, entry = entry_context
    decision = snapshots[decision_index]
    entry_snapshot = snapshots[entry_index]
    maximum_profit = entry.quantity - entry.buy_outflow
    target = percentage_target(maximum_profit, TARGET_FRACTION)
    settlement_gross = entry.quantity if side == winning_side else Decimal("0")
    settlement_pnl = settlement_gross - entry.buy_outflow
    preclose = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
    execution, exit_time, signal_seen, target_achieved, missed = _find_target_exit(
        snapshots=snapshots,
        start_index=entry_index + 1,
        stop_time=preclose,
        side=side,
        quantity=entry.quantity,
        outflow=entry.buy_outflow,
        target=target,
    )
    exit_reason = "unprotected_profit_target_signal"
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
        "triggered": True,
        "entry_filled": True,
        "status": "completed",
        "decision_time": decision.observed_at.isoformat(),
        "seconds_remaining": f"{(close_time - decision.observed_at).total_seconds():.6f}",
        "side": side,
        "favored_side_won": side == winning_side,
        "decision_favored_midpoint": _decimal_text(midpoint),
        "decision_favored_ask": _decimal_text(decision_ask),
        "entry_execution_time": entry_snapshot.observed_at.isoformat(),
        "contracts": _decimal_text(entry.quantity),
        "entry_gross": _decimal_text(entry.gross),
        "entry_fee": _decimal_text(entry.fee),
        "cash_deployed": _decimal_text(entry.buy_outflow),
        "entry_average_price": _decimal_text(_average_price(entry)),
        "maximum_settlement_profit": _decimal_text(maximum_profit),
        "settlement_counterfactual_pnl": _decimal_text(settlement_pnl),
        "target_amount": _decimal_text(target),
        "target_fraction_of_maximum": _decimal_text(TARGET_FRACTION),
        "target_signal_seen": signal_seen,
        "target_missed_full_depth_count": missed,
        "target_achieved_after_latency": target_achieved,
        "target_shortfall_after_latency": (
            _decimal_text(max(Decimal("0"), target - pnl))
            if exit_reason == "unprotected_profit_target_signal" else ""
        ),
        "target_filled": exit_reason == "unprotected_profit_target_signal",
        "fallback_used": exit_reason != "unprotected_profit_target_signal",
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


def normalize_protected(row: dict[str, Any]) -> dict[str, Any]:
    row["target_protection_mode"] = "protected"
    row["target_signal_seen"] = bool(int(row.get("target_signal_count", 0) or 0))
    row["target_missed_full_depth_count"] = row.get(
        "target_rejected_after_latency_count", 0
    )
    row["target_achieved_after_latency"] = bool(row.get("target_filled", False))
    row["target_shortfall_after_latency"] = ""
    return row


def verify_matched_entries(
    unprotected: Mapping[str, Any], protected: Mapping[str, Any]
) -> None:
    fields = (
        "status", "triggered", "entry_filled", "decision_time",
        "entry_execution_time", "side", "contracts", "cash_deployed",
    )
    mismatches = [
        field for field in fields
        if unprotected.get(field, "") != protected.get(field, "")
    ]
    if mismatches:
        raise NativeTargetProtectionError(
            f"{protected['ticker']}: unmatched protection entry: {mismatches}"
        )


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        source = list(rows) if segment == "all_96" else [
            row for row in rows
            if row["diagnostic_segment"]
            == ("earlier_64" if segment.startswith("earlier") else "later_32")
        ]
        protected = {
            str(row["ticker"]): float(row["pnl"] or 0.0)
            for row in source if row["exit_policy"] == BASELINE
        }
        for policy, label in POLICIES:
            selected = [row for row in source if row["exit_policy"] == policy]
            completed = [row for row in selected if row["status"] == "completed"]
            pnl_market = [float(row["pnl"] or 0.0) for row in selected]
            pnl_filled = [float(row["pnl"]) for row in completed]
            estimate, low, high = _bootstrap(pnl_market)
            differences = [
                float(row["pnl"] or 0.0) - protected[str(row["ticker"])]
                for row in selected
            ]
            diff, diff_low, diff_high = _bootstrap(differences)
            unprotected_target_exits = [
                row for row in completed
                if row["exit_reason"] == "unprotected_profit_target_signal"
            ]
            output.append({
                "segment": segment,
                "exit_policy": policy,
                "display_policy": label,
                "eligible_markets": len(selected),
                "triggered_markets": sum(bool(row["triggered"]) for row in selected),
                "entry_filled_markets": len(completed),
                "mean_pnl_per_eligible_market": estimate,
                "bootstrap_ci_low_per_eligible_market": low,
                "bootstrap_ci_high_per_eligible_market": high,
                "mean_paired_difference_vs_protected": diff,
                "paired_difference_ci_low": diff_low,
                "paired_difference_ci_high": diff_high,
                "mean_pnl_per_filled_entry": _mean(pnl_filled),
                "profitable_rate_per_filled_entry": _mean(
                    [bool(row["profitable"]) for row in completed]
                ),
                "target_exit_rate": _mean(
                    [bool(row["target_filled"]) for row in completed]
                ),
                "delayed_target_achievement_rate": _mean(
                    [bool(row["target_achieved_after_latency"]) for row in completed]
                ),
                "unprotected_below_target_exit_rate": _mean([
                    not bool(row["target_achieved_after_latency"])
                    for row in unprotected_target_exits
                ]) if unprotected_target_exits else 0.0,
                "fallback_rate": _mean(
                    [bool(row["fallback_used"]) for row in completed]
                ),
                "full_capital_loss_rate": _mean(
                    [bool(row["full_capital_loss"]) for row in completed]
                ),
                "mean_exposure_seconds": _mean(
                    [float(row["exposure_seconds"]) for row in completed]
                ),
                "median_exposure_seconds": statistics.median(
                    float(row["exposure_seconds"]) for row in completed
                ) if completed else math.nan,
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
        if row["segment"] == "all_96" and row["exit_policy"] == BASELINE
    )
    if int(baseline["entry_filled_markets"]) != EXPECTED_NATIVE_ENTRIES:
        raise NativeTargetProtectionError(
            f"expected 57 native entries; found {baseline['entry_filled_markets']}"
        )
    if abs(float(baseline["mean_paired_difference_vs_protected"])) > 1e-12:
        raise NativeTargetProtectionError("protected baseline paired difference is not zero")


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    rows = [row for row in summary if row["segment"] == "all_96"]
    lines = [
        "# KXBTC15M H3 causal-native 50% target-protection diagnostic",
        "",
        "**Matched development execution-mechanics test; holdout sealed.**",
        "",
        "Both policies use the identical 57 causal-native entries, 50%-of-maximum target, "
        "one-second exit delay, full archived depth, fees, and ten-second preclose fallback. "
        "Unprotected execution sells after the first target signal even if the delayed full sale "
        "has slipped below target. Protected execution rejects that delayed sale and continues "
        "monitoring until a full sale still meets the target.",
        "",
        "| Mode | Filled | Mean / market | 95% CI | vs protected | Paired 95% CI | Mean / fill | Profitable | Target exit | Delayed target met | Below-target exits | Fallback | Full loss | Mean exposure | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['display_policy']} | {row['entry_filled_markets']} | "
            f"{_money(row['mean_pnl_per_eligible_market'])} | "
            f"{_money(row['bootstrap_ci_low_per_eligible_market'])} to "
            f"{_money(row['bootstrap_ci_high_per_eligible_market'])} | "
            f"{_money(row['mean_paired_difference_vs_protected'])} | "
            f"{_money(row['paired_difference_ci_low'])} to "
            f"{_money(row['paired_difference_ci_high'])} | "
            f"{_money(row['mean_pnl_per_filled_entry'])} | "
            f"{_percent(row['profitable_rate_per_filled_entry'])} | "
            f"{_percent(row['target_exit_rate'])} | "
            f"{_percent(row['delayed_target_achievement_rate'])} | "
            f"{_percent(row['unprotected_below_target_exit_rate'])} | "
            f"{_percent(row['fallback_rate'])} | "
            f"{_percent(row['full_capital_loss_rate'])} | "
            f"{float(row['mean_exposure_seconds']):.1f}s | "
            f"{_money(row['pnl_05_quantile_per_filled_entry'])} | "
            f"{_money(row['worst_pnl_per_filled_entry'])} |"
        )
    lines.extend([
        "",
        "Mean P&L per eligible market counts no-trigger markets as $0. The paired comparison "
        "isolates only target protection because entries, signals, latency, sizing, and fallback "
        "are matched.",
        "",
        "The protected row must exactly reproduce the accepted causal-native H3 result before "
        "this report is written. This remains adaptive development evidence, not an unbiased "
        "future-return estimate. No external BTC data, authentication, order, or holdout "
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
        "--output-dir",
        type=Path,
        default=Path("analysis/kxbtc15m_h3_native_target_protection"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="kxbtc15m_native_protection_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise NativeTargetProtectionError(
                f"expected 96 eligible markets; found {len(eligible)}"
            )
        if set(outcomes) != {market.ticker for market in eligible}:
            raise NativeTargetProtectionError("development outcome ticker mismatch")
        for number, market in enumerate(eligible, start=1):
            _legacy, snapshots = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            segment = "earlier_64" if market.index <= 64 else "later_32"
            context = find_native_entry(snapshots, close)
            unprotected = simulate_unprotected(
                snapshots=snapshots,
                close_time=close,
                winning_side=outcomes[market.ticker],
                ticker=market.ticker,
                segment=segment,
                entry_context=context,
            )
            protected = normalize_protected(simulate_policy(
                snapshots=snapshots,
                close_time=close,
                winning_side=outcomes[market.ticker],
                ticker=market.ticker,
                segment=segment,
                policy=BASELINE,
                kind="fraction",
                value=TARGET_FRACTION,
                entry_context=context,
            ))
            verify_matched_entries(unprotected, protected)
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
            verify_baseline_reproduction(protected, frequency)
            rows.extend((unprotected, protected))
            print(f"[{number:02d}/96] {market.ticker}")
    summary = summarize(rows)
    verify_summary(summary)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "kxbtc15m_h3_native_target_protection_scenarios.csv",
        rows,
    )
    write_csv(
        args.output_dir / "kxbtc15m_h3_native_target_protection_summary.csv",
        summary,
    )
    report_path = args.output_dir / "KXBTC15M_H3_NATIVE_TARGET_PROTECTION.md"
    report_path.write_text(markdown_report(summary), encoding="utf-8")
    print("KXBTC15M H3 causal-native target-protection diagnostic: PASS")
    print("Eligible development markets: 96")
    print("Matched causal-native entries: 57")
    print("Protected 50% native baseline reproduced: True")
    print("Holdout read: False")
    print("Orders placed: False")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (
        AuditError,
        NativeTargetProtectionError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise SystemExit(f"KXBTC15M H3 native protection error: {exc}") from exc
