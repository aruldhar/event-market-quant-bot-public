#!/usr/bin/env python3
"""Test one strictly bounded H3 re-entry after a protected cash exit."""

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
    EXPECTED_NATIVE_ENTRIES,
    find_native_entry,
    simulate_policy,
    verify_baseline_reproduction,
)
from analyze_kxbtc15m_h3_time_windows import _bootstrap, _mean, _money, _percent, _quantile
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    parse_time,
    safe_extract_zip,
    select_development_manifests,
)


REENTRY_CUTOFF_SECONDS = 240
POLICIES = (
    ("single_cycle_baseline", "Single cycle"),
    ("one_strict_bounded_reentry", "One bounded re-entry"),
)
BASELINE = POLICIES[0][0]


class BoundedReentryError(RuntimeError):
    """Raised when the bounded re-entry diagnostic fails closed."""


def find_strict_reentry(
    *, snapshots: Sequence[Snapshot], close_time: datetime,
    first_exit_time: datetime, original_side: str,
) -> tuple[tuple[int, int, str, Decimal, Decimal, Any] | None, dict[str, Any]]:
    """Require same-side out-of-band evidence followed by a fresh band entry."""
    cutoff = close_time - timedelta(seconds=REENTRY_CUTOFF_SECONDS)
    cursor = first_index_at_or_after(snapshots, 0, first_exit_time)
    diagnostics = {
        "reentry_search_available": cursor is not None and first_exit_time < cutoff,
        "reentry_armed_after_outside_band": False,
        "reentry_signal_seen": False,
        "reentry_rejected_after_cutoff": False,
        "reentry_rejected_unfilled": False,
    }
    if cursor is None or first_exit_time >= cutoff:
        return None, diagnostics
    armed = False
    for decision_index in range(cursor, len(snapshots)):
        decision = snapshots[decision_index]
        if decision.observed_at <= first_exit_time:
            continue
        if decision.observed_at >= cutoff:
            break
        quote = favored_quote(decision.book)
        if quote is None or quote[0] != original_side:
            continue
        side, midpoint, ask = quote
        if midpoint < LOW or midpoint >= HIGH_EXCLUSIVE:
            armed = True
            diagnostics["reentry_armed_after_outside_band"] = True
            continue
        if not armed:
            continue
        diagnostics["reentry_signal_seen"] = True
        entry_index = first_index_at_or_after(
            snapshots,
            decision_index + 1,
            decision.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if entry_index is None or snapshots[entry_index].observed_at >= cutoff:
            diagnostics["reentry_rejected_after_cutoff"] = True
            return None, diagnostics
        entry = buy_with_budget(
            snapshots[entry_index].book.ask_levels(side), MAX_BUDGET
        )
        if entry.quantity <= 0 or entry.quantity - entry.buy_outflow <= 0:
            diagnostics["reentry_rejected_unfilled"] = True
            return None, diagnostics
        return (
            decision_index, entry_index, side, midpoint, ask, entry
        ), diagnostics
    return None, diagnostics


def _base(
    *, ticker: str, segment: str, policy: str, first: Mapping[str, Any]
) -> dict[str, Any]:
    first_completed = first["status"] == "completed"
    first_pnl = str(first["pnl"]) if first_completed else ""
    return {
        "ticker": ticker,
        "diagnostic_segment": segment,
        "policy": policy,
        "clock_basis": "causal_response_receipt",
        "monitoring_frequency": "native_archived_response",
        "maximum_concurrent_budget": "100",
        "profit_compounded": False,
        "maximum_cycles": 1 if policy == BASELINE else 2,
        "status": "completed_first_cycle" if first_completed else "no_initial_trigger",
        "initial_triggered": bool(first.get("triggered", False)),
        "first_cycle_completed": first_completed,
        "first_cycle_pnl": first_pnl,
        "second_cycle_completed": False,
        "second_cycle_pnl": "",
        "total_pnl": first_pnl,
        "holdout_read": False,
        "external_btc_data_used": False,
        "orders_placed": False,
    }


def simulate_market_policies(
    *, snapshots: Sequence[Snapshot], close_time: datetime, winning_side: str,
    ticker: str, segment: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    first_context = find_native_entry(snapshots, close_time)
    first = simulate_policy(
        snapshots=snapshots,
        close_time=close_time,
        winning_side=winning_side,
        ticker=ticker,
        segment=segment,
        policy=BASELINE_POLICY,
        kind="fraction",
        value=TARGET_FRACTION,
        entry_context=first_context,
    )
    baseline = _base(ticker=ticker, segment=segment, policy=BASELINE, first=first)
    reentry = _base(
        ticker=ticker, segment=segment,
        policy="one_strict_bounded_reentry", first=first
    )
    diagnostic = {
        "reentry_search_available": False,
        "reentry_armed_after_outside_band": False,
        "reentry_signal_seen": False,
        "reentry_rejected_after_cutoff": False,
        "reentry_rejected_unfilled": False,
    }
    if first["status"] != "completed" or first["exit_reason"] != "protected_profit_target":
        return [baseline, reentry], first
    first_exit_time = parse_time(str(first["exit_execution_time"]))
    second_context, diagnostic = find_strict_reentry(
        snapshots=snapshots,
        close_time=close_time,
        first_exit_time=first_exit_time,
        original_side=str(first["side"]),
    )
    reentry.update(diagnostic)
    if second_context is None:
        reentry["status"] = (
            "completed_first_cycle_no_reentry"
            if reentry["first_cycle_completed"] else "no_initial_trigger"
        )
        return [baseline, reentry], first
    second = simulate_policy(
        snapshots=snapshots,
        close_time=close_time,
        winning_side=winning_side,
        ticker=ticker,
        segment=segment,
        policy=BASELINE_POLICY,
        kind="fraction",
        value=TARGET_FRACTION,
        entry_context=second_context,
    )
    if second["status"] != "completed":
        raise BoundedReentryError(f"{ticker}: filled re-entry did not complete")
    combined = Decimal(str(first["pnl"])) + Decimal(str(second["pnl"]))
    reentry.update({
        "status": "completed_two_cycles",
        "second_cycle_completed": True,
        "second_decision_time": second["decision_time"],
        "second_entry_execution_time": second["entry_execution_time"],
        "second_side": second["side"],
        "second_entry_average_price": second["entry_average_price"],
        "second_cash_deployed": second["cash_deployed"],
        "second_exit_reason": second["exit_reason"],
        "second_exit_execution_time": second["exit_execution_time"],
        "second_cycle_pnl": second["pnl"],
        "second_cycle_profitable": second["profitable"],
        "second_cycle_full_capital_loss": second["full_capital_loss"],
        "total_pnl": format(combined, "f"),
    })
    return [baseline, reentry], first


def verify_baseline_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    baseline = [row for row in rows if row["policy"] == BASELINE]
    reentry = [row for row in rows if row["policy"] == "one_strict_bounded_reentry"]
    if not baseline or len(baseline) != len(reentry):
        raise BoundedReentryError("policy row count mismatch")
    by_ticker = {str(row["ticker"]): row for row in baseline}
    for row in reentry:
        prior = by_ticker[str(row["ticker"])]
        if not bool(row["second_cycle_completed"]):
            if row.get("total_pnl", "") != prior.get("total_pnl", ""):
                raise BoundedReentryError(
                    f"{row['ticker']}: no-reentry policy changed baseline P&L"
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
            str(row["ticker"]): float(row["total_pnl"] or 0.0)
            for row in source if row["policy"] == BASELINE
        }
        for policy, label in POLICIES:
            selected = [row for row in source if row["policy"] == policy]
            pnl_market = [float(row["total_pnl"] or 0.0) for row in selected]
            estimate, low, high = _bootstrap(pnl_market)
            differences = [
                float(row["total_pnl"] or 0.0) - baseline[str(row["ticker"])]
                for row in selected
            ]
            diff, diff_low, diff_high = _bootstrap(differences)
            second = [row for row in selected if bool(row["second_cycle_completed"])]
            second_pnl = [float(row["second_cycle_pnl"]) for row in second]
            output.append({
                "segment": segment,
                "policy": policy,
                "display_policy": label,
                "eligible_markets": len(selected),
                "initial_entries": sum(bool(row["first_cycle_completed"]) for row in selected),
                "reentry_search_available_markets": sum(
                    bool(row.get("reentry_search_available", False)) for row in selected
                ),
                "reentry_armed_markets": sum(
                    bool(row.get("reentry_armed_after_outside_band", False)) for row in selected
                ),
                "reentry_signal_markets": sum(
                    bool(row.get("reentry_signal_seen", False)) for row in selected
                ),
                "second_entries": len(second),
                "mean_total_pnl_per_eligible_market": estimate,
                "bootstrap_ci_low_per_eligible_market": low,
                "bootstrap_ci_high_per_eligible_market": high,
                "mean_incremental_pnl_vs_single_cycle": diff,
                "paired_difference_ci_low": diff_low,
                "paired_difference_ci_high": diff_high,
                "mean_second_cycle_pnl": _mean(second_pnl),
                "second_cycle_profitable_rate": _mean(
                    [bool(row["second_cycle_profitable"]) for row in second]
                ),
                "second_cycle_full_loss_rate": _mean(
                    [bool(row["second_cycle_full_capital_loss"]) for row in second]
                ),
                "second_cycle_05_quantile": _quantile(second_pnl, 0.05),
                "second_cycle_worst_pnl": min(second_pnl) if second_pnl else math.nan,
                "holdout_read": False,
                "external_btc_data_used": False,
                "orders_placed": False,
            })
    return output


def verify_summary(summary: Sequence[Mapping[str, Any]]) -> None:
    baseline = next(
        row for row in summary
        if row["segment"] == "all_96" and row["policy"] == BASELINE
    )
    if int(baseline["initial_entries"]) != EXPECTED_NATIVE_ENTRIES:
        raise BoundedReentryError(
            f"expected 57 initial entries; found {baseline['initial_entries']}"
        )
    if int(baseline["eligible_markets"]) != EXPECTED_ELIGIBLE_MARKETS:
        raise BoundedReentryError(
            f"expected 96 eligible markets; found {baseline['eligible_markets']}"
        )
    if abs(float(baseline["mean_incremental_pnl_vs_single_cycle"])) > 1e-12:
        raise BoundedReentryError("single-cycle baseline difference is not zero")


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    rows = [row for row in summary if row["segment"] == "all_96"]
    lines = [
        "# KXBTC15M H3 strict bounded re-entry diagnostic",
        "",
        "**Matched adaptive development test; protected baseline frozen; holdout sealed.**",
        "",
        "Both policies use the accepted causal-native 4-to-5-minute, 90%-to-below-98%, "
        "protected-50% first cycle. The re-entry policy may deploy the same non-compounded "
        "$100 budget one additional time only after the first position has fully exited for "
        "protected profit. It requires the original favored side to be observed outside the "
        "entry band and then freshly re-enter the band. The second delayed fill must occur "
        "before four minutes remaining. Positions never overlap.",
        "",
        "| Policy | Initial entries | Search available | Armed | Signals | Second entries | Mean total / market | 95% CI | Increment vs single | Paired 95% CI | Mean second cycle | Second profitable | Second full loss | Second 5% tail | Second worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['display_policy']} | {row['initial_entries']} | "
            f"{row['reentry_search_available_markets']} | {row['reentry_armed_markets']} | "
            f"{row['reentry_signal_markets']} | {row['second_entries']} | "
            f"{_money(row['mean_total_pnl_per_eligible_market'])} | "
            f"{_money(row['bootstrap_ci_low_per_eligible_market'])} to "
            f"{_money(row['bootstrap_ci_high_per_eligible_market'])} | "
            f"{_money(row['mean_incremental_pnl_vs_single_cycle'])} | "
            f"{_money(row['paired_difference_ci_low'])} to "
            f"{_money(row['paired_difference_ci_high'])} | "
            f"{_money(row['mean_second_cycle_pnl'])} | "
            f"{_percent(row['second_cycle_profitable_rate'])} | "
            f"{_percent(row['second_cycle_full_loss_rate'])} | "
            f"{_money(row['second_cycle_05_quantile'])} | "
            f"{_money(row['second_cycle_worst_pnl'])} |"
        )
    lines.extend([
        "",
        "Search available means the first protected cash exit completed before the four-minute "
        "entry cutoff. Armed means a same-side out-of-band observation occurred afterward. A "
        "signal additionally requires a fresh return into 90%-to-below-98% with enough time for "
        "the one-second delayed fill.",
        "",
        "Mean total P&L per eligible market counts no-trades as $0. The paired incremental result "
        "is primary. This is an adaptive development test, not an unbiased expected return or "
        "guarantee. No external BTC data, authentication, order, or holdout observation is used.",
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
        default=Path("analysis/kxbtc15m_h3_bounded_reentry"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="kxbtc15m_bounded_reentry_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise BoundedReentryError(
                f"expected 96 eligible markets; found {len(eligible)}"
            )
        if set(outcomes) != {market.ticker for market in eligible}:
            raise BoundedReentryError("development outcome ticker mismatch")
        for number, market in enumerate(eligible, start=1):
            _legacy, snapshots = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            segment = "earlier_64" if market.index <= 64 else "later_32"
            market_rows, first = simulate_market_policies(
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
            verify_baseline_reproduction(first, frequency)
            rows.extend(market_rows)
            print(f"[{number:02d}/96] {market.ticker}")
    verify_baseline_rows(rows)
    summary = summarize(rows)
    verify_summary(summary)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_h3_bounded_reentry_scenarios.csv", rows)
    write_csv(args.output_dir / "kxbtc15m_h3_bounded_reentry_summary.csv", summary)
    report_path = args.output_dir / "KXBTC15M_H3_BOUNDED_REENTRY.md"
    report_path.write_text(markdown_report(summary), encoding="utf-8")
    print("KXBTC15M H3 strict bounded re-entry diagnostic: PASS")
    print("Eligible development markets: 96")
    print("Initial causal-native entries: 57")
    print("Maximum cycles: 2")
    print("Maximum concurrent budget: $100; no compounding")
    print("Protected 50% native baseline reproduced: True")
    print("Holdout read: False")
    print("Orders placed: False")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (
        AuditError,
        BoundedReentryError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise SystemExit(f"KXBTC15M H3 bounded re-entry error: {exc}") from exc
