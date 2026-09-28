#!/usr/bin/env python3
"""Compare full H3 cash exit with principal recovery plus a bounded runner."""

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
    first_index_at_or_after,
    load_outcomes,
    sell_quantity,
    validate_fee_inputs,
    write_csv,
)
from analyze_kxbtc15m_h3_exit_policies import PRECLOSE_EXIT_SECONDS, _find_preclose_exit
from analyze_kxbtc15m_h3_frequency import (
    TARGET_FRACTION,
    _average_price,
    _decimal_text,
    _raw_snapshot_sets,
    simulate_market as simulate_frequency_market,
)
from analyze_kxbtc15m_h3_native_exit_policies import (
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


POLICIES = (
    ("full_protected_50pct_cash_exit", "Full protected cash exit"),
    ("principal_runner_preclose", "Recover principal + preclose runner"),
    ("principal_runner_settlement", "Recover principal + settlement runner"),
)
BASELINE = POLICIES[0][0]


class PrincipalRunnerError(RuntimeError):
    """Raised when the principal-recovery runner diagnostic fails closed."""


def minimum_principal_recovery_sale(
    bid_levels: Sequence[tuple[Decimal, Decimal]],
    total_quantity: Decimal,
    cash_outflow: Decimal,
):
    """Return the smallest whole-contract full-depth sale recovering outflow."""
    total = int(total_quantity)
    for contracts in range(1, total + 1):
        execution = sell_quantity(bid_levels, Decimal(contracts))
        if (
            execution.quantity == Decimal(contracts)
            and execution.sell_inflow >= cash_outflow
        ):
            return execution
    raise PrincipalRunnerError("full target exit cannot recover principal")


def _base_row(
    *, first: Mapping[str, Any], ticker: str, segment: str, policy: str
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "diagnostic_segment": segment,
        "policy": policy,
        "clock_basis": "causal_response_receipt",
        "monitoring_frequency": "native_archived_response",
        "status": "no_trigger" if first["status"] != "completed" else "completed",
        "triggered": bool(first.get("triggered", False)),
        "entry_filled": bool(first.get("entry_filled", False)),
        "pnl": first.get("pnl", "") if policy == BASELINE else "",
        "holdout_read": False,
        "external_btc_data_used": False,
        "orders_placed": False,
    }


def simulate_policies(
    *, snapshots: Sequence[Snapshot], close_time, winning_side: str,
    ticker: str, segment: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    context = find_native_entry(snapshots, close_time)
    first = simulate_policy(
        snapshots=snapshots,
        close_time=close_time,
        winning_side=winning_side,
        ticker=ticker,
        segment=segment,
        policy="protected_50pct_max",
        kind="fraction",
        value=TARGET_FRACTION,
        entry_context=context,
    )
    rows = [
        _base_row(first=first, ticker=ticker, segment=segment, policy=policy)
        for policy, _label in POLICIES
    ]
    if first["status"] != "completed":
        return rows, first
    if first["exit_reason"] != "protected_profit_target":
        raise PrincipalRunnerError(f"{ticker}: baseline did not complete protected target")

    baseline = rows[0]
    baseline.update({
        "entry_execution_time": first["entry_execution_time"],
        "cash_deployed": first["cash_deployed"],
        "contracts": first["contracts"],
        "full_exit_execution_time": first["exit_execution_time"],
        "full_exit_pnl": first["pnl"],
        "profitable": first["profitable"],
        "full_capital_loss": first["full_capital_loss"],
        "runner_contracts": "0",
        "principal_recovered": True,
    })

    exit_time = parse_time(str(first["exit_execution_time"]))
    exit_index = first_index_at_or_after(snapshots, 0, exit_time)
    if exit_index is None or snapshots[exit_index].observed_at != exit_time:
        raise PrincipalRunnerError(f"{ticker}: exact protected exit snapshot missing")
    quantity = Decimal(str(first["contracts"]))
    outflow = Decimal(str(first["cash_deployed"]))
    side = str(first["side"])
    partial = minimum_principal_recovery_sale(
        snapshots[exit_index].book.bid_levels(side), quantity, outflow
    )
    runner_quantity = quantity - partial.quantity
    if runner_quantity <= 0:
        raise PrincipalRunnerError(f"{ticker}: no runner remains after principal recovery")
    locked_profit = partial.sell_inflow - outflow
    if locked_profit < 0:
        raise PrincipalRunnerError(f"{ticker}: principal was not recovered")

    common = {
        "entry_execution_time": first["entry_execution_time"],
        "cash_deployed": first["cash_deployed"],
        "contracts": first["contracts"],
        "full_exit_execution_time": first["exit_execution_time"],
        "full_exit_pnl": first["pnl"],
        "principal_sale_contracts": _decimal_text(partial.quantity),
        "principal_sale_gross": _decimal_text(partial.gross),
        "principal_sale_fee": _decimal_text(partial.fee),
        "principal_sale_inflow": _decimal_text(partial.sell_inflow),
        "principal_recovered": partial.sell_inflow >= outflow,
        "locked_profit_after_principal_sale": _decimal_text(locked_profit),
        "runner_contracts": _decimal_text(runner_quantity),
        "runner_fraction_of_position": _decimal_text(runner_quantity / quantity),
    }

    settlement_gross = runner_quantity if side == winning_side else Decimal("0")
    settlement_total_pnl = locked_profit + settlement_gross
    settlement = rows[2]
    settlement.update({
        **common,
        "runner_exit_reason": "settlement",
        "runner_exit_execution_time": close_time.isoformat(),
        "runner_exit_gross": _decimal_text(settlement_gross),
        "runner_exit_fee": "0",
        "runner_exit_inflow": _decimal_text(settlement_gross),
        "pnl": _decimal_text(settlement_total_pnl),
        "incremental_pnl_vs_full_exit": _decimal_text(
            settlement_total_pnl - Decimal(str(first["pnl"]))
        ),
        "profitable": settlement_total_pnl > 0,
        "full_capital_loss": False,
        "runner_won": side == winning_side,
    })

    preclose = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
    runner_execution, runner_time = _find_preclose_exit(
        snapshots=snapshots,
        start_index=exit_index + 1,
        start_time=preclose,
        close_time=close_time,
        side=side,
        quantity=runner_quantity,
    )
    if runner_execution is None:
        runner_inflow = settlement_gross
        runner_gross = settlement_gross
        runner_fee = Decimal("0")
        runner_time = close_time
        runner_reason = "settlement_after_preclose_liquidity_failure"
    else:
        runner_inflow = runner_execution.sell_inflow
        runner_gross = runner_execution.gross
        runner_fee = runner_execution.fee
        runner_reason = "preclose_runner_cash_exit"
    preclose_total_pnl = locked_profit + runner_inflow
    preclose_row = rows[1]
    preclose_row.update({
        **common,
        "runner_exit_reason": runner_reason,
        "runner_exit_execution_time": runner_time.isoformat(),
        "runner_exit_gross": _decimal_text(runner_gross),
        "runner_exit_fee": _decimal_text(runner_fee),
        "runner_exit_inflow": _decimal_text(runner_inflow),
        "pnl": _decimal_text(preclose_total_pnl),
        "incremental_pnl_vs_full_exit": _decimal_text(
            preclose_total_pnl - Decimal(str(first["pnl"]))
        ),
        "profitable": preclose_total_pnl > 0,
        "full_capital_loss": False,
        "runner_won": side == winning_side,
    })
    return rows, first


def verify_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    for ticker in {str(row["ticker"]) for row in rows}:
        selected = [row for row in rows if str(row["ticker"]) == ticker]
        if len(selected) != len(POLICIES):
            raise PrincipalRunnerError(f"{ticker}: policy row count mismatch")
        baseline = next(row for row in selected if row["policy"] == BASELINE)
        for row in selected:
            if row["status"] != "completed":
                if row.get("pnl", "") not in {"", baseline.get("pnl", "")}:
                    raise PrincipalRunnerError(f"{ticker}: no-trade P&L mismatch")
                continue
            if not bool(row.get("principal_recovered", False)):
                raise PrincipalRunnerError(f"{ticker}: policy left principal exposed")
            if Decimal(str(row["pnl"])) < 0:
                raise PrincipalRunnerError(f"{ticker}: recovered-principal policy lost cash")


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        source = list(rows) if segment == "all_96" else [
            row for row in rows
            if row["diagnostic_segment"]
            == ("earlier_64" if segment.startswith("earlier") else "later_32")
        ]
        baseline = {
            str(row["ticker"]): float(row["pnl"] or 0.0)
            for row in source if row["policy"] == BASELINE
        }
        for policy, label in POLICIES:
            selected = [row for row in source if row["policy"] == policy]
            completed = [row for row in selected if row["status"] == "completed"]
            pnl_market = [float(row["pnl"] or 0.0) for row in selected]
            pnl_filled = [float(row["pnl"]) for row in completed]
            estimate, low, high = _bootstrap(pnl_market)
            differences = [
                float(row["pnl"] or 0.0) - baseline[str(row["ticker"])]
                for row in selected
            ]
            diff, diff_low, diff_high = _bootstrap(differences)
            runner_rows = [row for row in completed if policy != BASELINE]
            output.append({
                "segment": segment,
                "policy": policy,
                "display_policy": label,
                "eligible_markets": len(selected),
                "filled_markets": len(completed),
                "mean_pnl_per_eligible_market": estimate,
                "bootstrap_ci_low_per_eligible_market": low,
                "bootstrap_ci_high_per_eligible_market": high,
                "mean_incremental_pnl_vs_full_exit": diff,
                "paired_difference_ci_low": diff_low,
                "paired_difference_ci_high": diff_high,
                "mean_pnl_per_filled_entry": _mean(pnl_filled),
                "profitable_rate": _mean([bool(row["profitable"]) for row in completed]),
                "principal_recovery_rate": _mean([
                    bool(row["principal_recovered"]) for row in completed
                ]),
                "mean_runner_fraction": _mean([
                    float(row["runner_fraction_of_position"]) for row in runner_rows
                ]),
                "runner_won_rate": _mean([
                    bool(row["runner_won"]) for row in runner_rows
                ]),
                "full_capital_loss_rate": _mean([
                    bool(row["full_capital_loss"]) for row in completed
                ]),
                "pnl_05_quantile": _quantile(pnl_filled, 0.05),
                "worst_pnl": min(pnl_filled) if pnl_filled else math.nan,
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
    if int(baseline["eligible_markets"]) != EXPECTED_ELIGIBLE_MARKETS:
        raise PrincipalRunnerError("eligible market count mismatch")
    if int(baseline["filled_markets"]) != EXPECTED_NATIVE_ENTRIES:
        raise PrincipalRunnerError("expected 57 native entries")
    if abs(float(baseline["mean_incremental_pnl_vs_full_exit"])) > 1e-12:
        raise PrincipalRunnerError("baseline paired difference is not zero")


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    rows = [row for row in summary if row["segment"] == "all_96"]
    lines = [
        "# KXBTC15M H3 principal-recovery runner diagnostic",
        "",
        "**Matched adaptive development test; protected entry/exit frozen; holdout sealed.**",
        "",
        "At the exact protected-50% full-exit execution snapshot, runner policies sell the "
        "minimum whole contracts whose net proceeds recover the entire initial cash outflow "
        "after the partial-sale fee. Only the remaining contracts continue as a runner. The "
        "baseline sells the full position at that same snapshot.",
        "",
        "| Policy | Filled | Mean / market | 95% CI | Increment vs full exit | Paired 95% CI | Mean / fill | Profitable | Principal recovered | Mean runner share | Runner won | Full loss | 5% tail | Worst |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['display_policy']} | {row['filled_markets']} | "
            f"{_money(row['mean_pnl_per_eligible_market'])} | "
            f"{_money(row['bootstrap_ci_low_per_eligible_market'])} to "
            f"{_money(row['bootstrap_ci_high_per_eligible_market'])} | "
            f"{_money(row['mean_incremental_pnl_vs_full_exit'])} | "
            f"{_money(row['paired_difference_ci_low'])} to "
            f"{_money(row['paired_difference_ci_high'])} | "
            f"{_money(row['mean_pnl_per_filled_entry'])} | "
            f"{_percent(row['profitable_rate'])} | "
            f"{_percent(row['principal_recovery_rate'])} | "
            f"{_percent(row['mean_runner_fraction'])} | "
            f"{_percent(row['runner_won_rate'])} | "
            f"{_percent(row['full_capital_loss_rate'])} | "
            f"{_money(row['pnl_05_quantile'])} | {_money(row['worst_pnl'])} |"
        )
    lines.extend([
        "",
        "The preclose runner attempts a one-second-delayed full cash exit beginning ten seconds "
        "before close; settlement is used only if archived depth cannot liquidate the runner. "
        "The settlement runner holds only the residual contracts. Neither runner can lose the "
        "recovered initial cash in this counterfactual.",
        "",
        "Mean P&L per eligible market counts no-trades as $0. The paired increment versus the "
        "full protected cash exit is primary. This is adaptive development evidence, not an "
        "unbiased return estimate or guarantee. No external BTC data, authentication, order, "
        "or holdout observation is used.",
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
        default=Path("analysis/kxbtc15m_h3_principal_runner"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows = []
    with TemporaryDirectory(prefix="kxbtc15m_principal_runner_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise PrincipalRunnerError("expected 96 eligible markets")
        if set(outcomes) != {market.ticker for market in eligible}:
            raise PrincipalRunnerError("development outcome ticker mismatch")
        for number, market in enumerate(eligible, start=1):
            _legacy, snapshots = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            segment = "earlier_64" if market.index <= 64 else "later_32"
            market_rows, first = simulate_policies(
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
    verify_rows(rows)
    summary = summarize(rows)
    verify_summary(summary)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_h3_principal_runner_scenarios.csv", rows)
    write_csv(args.output_dir / "kxbtc15m_h3_principal_runner_summary.csv", summary)
    report_path = args.output_dir / "KXBTC15M_H3_PRINCIPAL_RUNNER.md"
    report_path.write_text(markdown_report(summary), encoding="utf-8")
    print("KXBTC15M H3 principal-recovery runner diagnostic: PASS")
    print("Eligible development markets: 96")
    print("Causal-native entries: 57")
    print("Principal recovery required: 100% after partial-sale fee")
    print("Protected 50% native baseline reproduced: True")
    print("Holdout read: False")
    print("Orders placed: False")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (
        AuditError,
        PrincipalRunnerError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise SystemExit(f"KXBTC15M H3 principal-runner error: {exc}") from exc
