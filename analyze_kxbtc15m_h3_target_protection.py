#!/usr/bin/env python3
"""Compare protected and unprotected H3 percentage-target execution.

The 52 H3 first-trigger entries, entry latency, archived full depth, $100
budget, fees, and outcomes remain frozen.  For each 25%, 50%, and 75% share of
maximum net settlement profit, the diagnostic compares:

* unprotected: a qualifying observation sends a sale that executes one second
  later at the available full-depth price, even if the target disappeared;
* protected: after the same delay, the full sale executes only if its net P&L
  still meets the target; otherwise the signal is rejected and monitoring
  continues.

Both modes are tested with preclose-sale and settlement fallbacks.  This is a
development-only execution-mechanics diagnostic.  The holdout remains sealed.
"""

from __future__ import annotations

import argparse
import csv
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
    SimulationError,
    Snapshot,
    first_index_at_or_after,
    load_outcomes,
    load_snapshots,
    sell_quantity,
    validate_fee_inputs,
    write_csv,
)
from analyze_kxbtc15m_h3_exit_policies import (
    EXPECTED_PRIMARY_TRIGGERS,
    PERCENTAGE_TARGETS,
    PRECLOSE_EXIT_SECONDS,
    ExitPolicyError,
    _find_preclose_exit,
    _row,
    load_primary_triggers,
    percentage_target,
    simulate_exit_policies,
)
from audit_kxbtc15m_raw_depth import (
    AuditError,
    assess_market,
    market_close_utc,
    parse_time,
    safe_extract_zip,
    select_development_manifests,
)


FALLBACKS = ("preclose", "settlement")
PROTECTION_MODES = ("unprotected", "protected")
EXPECTED_PRIOR_SCENARIOS = EXPECTED_PRIMARY_TRIGGERS * 12


def policy_name(mode: str, fraction: Decimal, fallback: str) -> str:
    if mode not in PROTECTION_MODES:
        raise ExitPolicyError(f"invalid protection mode: {mode}")
    if fallback not in FALLBACKS:
        raise ExitPolicyError(f"invalid fallback: {fallback}")
    return f"{mode}_target_{int(fraction * 100)}pct_max_or_{fallback}"


def policy_names() -> tuple[str, ...]:
    return tuple(
        policy_name(mode, fraction, fallback)
        for mode in PROTECTION_MODES
        for fraction in PERCENTAGE_TARGETS
        for fallback in FALLBACKS
    )


def prior_policy_name(fraction: Decimal, fallback: str) -> str:
    return f"target_{int(fraction * 100)}pct_max_or_{fallback}"


def parse_bool(value: Any) -> bool:
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    raise ExitPolicyError(f"invalid boolean value: {value!r}")


def load_prior_scenarios(path: Path) -> list[dict[str, str]]:
    required = {
        "ticker", "exit_policy", "pnl", "exit_reason", "holdout_read",
        "external_btc_data_used",
    }
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = required - fields
        if missing:
            raise ExitPolicyError(f"prior scenario CSV missing fields: {sorted(missing)}")
        rows = list(reader)
    if len(rows) != EXPECTED_PRIOR_SCENARIOS:
        raise ExitPolicyError(
            f"expected {EXPECTED_PRIOR_SCENARIOS} prior scenario rows; found {len(rows)}"
        )
    if any(parse_bool(row["holdout_read"]) for row in rows):
        raise ExitPolicyError("prior scenario input reports a holdout read")
    if any(parse_bool(row["external_btc_data_used"]) for row in rows):
        raise ExitPolicyError("prior scenario input reports external BTC data")
    return rows


def find_protected_target_exit(
    *,
    snapshots: Sequence[Snapshot],
    start_index: int,
    stop_time: datetime,
    side: str,
    quantity: Decimal,
    outflow: Decimal,
    target: Decimal,
) -> tuple[Any | None, datetime | None, int, int]:
    """Return the first delayed full fill that still satisfies the target.

    A target observation that no longer satisfies the target after one-second
    latency is rejected rather than sold at an unrestricted lower price.
    Monitoring resumes after that delayed observation.
    """

    signal_count = 0
    rejected_count = 0
    index = start_index
    while index < len(snapshots):
        observed = snapshots[index]
        if observed.observed_at >= stop_time:
            break
        hypothetical = sell_quantity(observed.book.bid_levels(side), quantity)
        if hypothetical.quantity != quantity or hypothetical.sell_inflow - outflow < target:
            index += 1
            continue
        signal_count += 1
        delayed_index = first_index_at_or_after(
            snapshots,
            index + 1,
            observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if delayed_index is None or snapshots[delayed_index].observed_at >= stop_time:
            rejected_count += 1
            break
        executed = sell_quantity(snapshots[delayed_index].book.bid_levels(side), quantity)
        if executed.quantity == quantity and executed.sell_inflow - outflow >= target:
            return executed, snapshots[delayed_index].observed_at, signal_count, rejected_count
        rejected_count += 1
        index = delayed_index + 1
    return None, None, signal_count, rejected_count


def _with_protection_fields(
    row: dict[str, Any], *, mode: str, signals: int | str, rejected: int | str
) -> dict[str, Any]:
    row.update({
        "target_protection_mode": mode,
        "target_signal_count": signals,
        "target_rejected_after_latency_count": rejected,
    })
    return row


def simulate_matched_policies(
    *,
    snapshots: Sequence[Snapshot],
    decision_index: int,
    close_time: datetime,
    winning_side: str,
    trigger: Mapping[str, Any],
) -> list[dict[str, Any]]:
    prior_rows = simulate_exit_policies(
        snapshots=snapshots,
        decision_index=decision_index,
        close_time=close_time,
        winning_side=winning_side,
        trigger=trigger,
    )
    source_by_policy = {row["exit_policy"]: row for row in prior_rows}
    hold = source_by_policy["hold_to_settlement"]
    output: list[dict[str, Any]] = []

    for fraction in PERCENTAGE_TARGETS:
        for fallback in FALLBACKS:
            source = dict(source_by_policy[prior_policy_name(fraction, fallback)])
            source["exit_policy"] = policy_name("unprotected", fraction, fallback)
            output.append(_with_protection_fields(
                source, mode="unprotected", signals="", rejected=""
            ))

    side = str(hold["side"])
    quantity = Decimal(str(hold["contracts"]))
    outflow = Decimal(str(hold["cash_deployed"]))
    entry_fee = Decimal(str(hold["entry_fee"]))
    maximum_profit = Decimal(str(hold["maximum_settlement_profit"]))
    settlement_pnl = Decimal(str(hold["settlement_counterfactual_pnl"]))
    settlement_gross = Decimal(str(hold["exit_gross"]))
    entry_time = parse_time(str(hold["entry_execution_time"]))
    entry_index = first_index_at_or_after(snapshots, decision_index + 1, entry_time)
    if entry_index is None or snapshots[entry_index].observed_at != entry_time:
        raise ExitPolicyError(f"{trigger['ticker']}: exact entry snapshot not found")
    base_fields = (
        "ticker", "diagnostic_segment", "decision_time", "seconds_remaining",
        "side", "favored_side_won", "decision_favored_midpoint",
        "decision_favored_ask", "entry_execution_time", "entry_best_ask",
        "entry_average_price", "max_budget",
    )
    base = {field: hold[field] for field in base_fields}
    preclose_time = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)

    for fraction in PERCENTAGE_TARGETS:
        target_amount = percentage_target(maximum_profit, fraction)
        for fallback in FALLBACKS:
            stop_time = preclose_time if fallback == "preclose" else close_time
            execution, exit_time, signals, rejected = find_protected_target_exit(
                snapshots=snapshots,
                start_index=entry_index + 1,
                stop_time=stop_time,
                side=side,
                quantity=quantity,
                outflow=outflow,
                target=target_amount,
            )
            name = policy_name("protected", fraction, fallback)
            if execution is not None:
                row = _row(
                    base=base, policy=name, exit_reason="protected_profit_target",
                    exit_time=exit_time, exit_gross=execution.gross,
                    exit_fee=execution.fee, entry_fee=entry_fee,
                    pnl=execution.sell_inflow - outflow, quantity=quantity,
                    outflow=outflow, maximum_settlement_profit=maximum_profit,
                    settlement_pnl=settlement_pnl, target_amount=target_amount,
                    target_fraction=fraction, target_hit=True,
                    target_signal_seen=signals > 0,
                    missed_target_signals=rejected,
                    conditional_action="protected_sell",
                )
                output.append(_with_protection_fields(
                    row, mode="protected", signals=signals, rejected=rejected
                ))
                continue

            if fallback == "settlement":
                row = _row(
                    base=base, policy=name,
                    exit_reason="settlement_after_no_protected_target",
                    exit_time=close_time, exit_gross=settlement_gross,
                    exit_fee=Decimal("0"), entry_fee=entry_fee,
                    pnl=settlement_pnl, quantity=quantity, outflow=outflow,
                    maximum_settlement_profit=maximum_profit,
                    settlement_pnl=settlement_pnl, target_amount=target_amount,
                    target_fraction=fraction, target_hit=False,
                    target_signal_seen=signals > 0,
                    missed_target_signals=rejected,
                    conditional_action="hold",
                )
                output.append(_with_protection_fields(
                    row, mode="protected", signals=signals, rejected=rejected
                ))
                continue

            forced, forced_time = _find_preclose_exit(
                snapshots=snapshots,
                start_index=entry_index + 1,
                start_time=preclose_time,
                close_time=close_time,
                side=side,
                quantity=quantity,
            )
            if forced is None:
                row = _row(
                    base=base, policy=name,
                    exit_reason="settlement_after_preclose_liquidity_failure",
                    exit_time=close_time, exit_gross=settlement_gross,
                    exit_fee=Decimal("0"), entry_fee=entry_fee,
                    pnl=settlement_pnl, quantity=quantity, outflow=outflow,
                    maximum_settlement_profit=maximum_profit,
                    settlement_pnl=settlement_pnl, target_amount=target_amount,
                    target_fraction=fraction, target_hit=False,
                    target_signal_seen=signals > 0,
                    missed_target_signals=rejected,
                    conditional_action="hold_liquidity_failure",
                )
            else:
                row = _row(
                    base=base, policy=name, exit_reason="preclose_time_exit",
                    exit_time=forced_time, exit_gross=forced.gross,
                    exit_fee=forced.fee, entry_fee=entry_fee,
                    pnl=forced.sell_inflow - outflow, quantity=quantity,
                    outflow=outflow, maximum_settlement_profit=maximum_profit,
                    settlement_pnl=settlement_pnl, target_amount=target_amount,
                    target_fraction=fraction, target_hit=False,
                    target_signal_seen=signals > 0,
                    missed_target_signals=rejected,
                    conditional_action="sell",
                )
            output.append(_with_protection_fields(
                row, mode="protected", signals=signals, rejected=rejected
            ))

    if {row["exit_policy"] for row in output} != set(policy_names()):
        raise ExitPolicyError("internal protected/unprotected policy set mismatch")
    return output


def verify_prior_reproduction(
    prior: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]
) -> None:
    expected: dict[tuple[str, str], float] = {}
    for row in prior:
        for fraction in PERCENTAGE_TARGETS:
            for fallback in FALLBACKS:
                old_name = prior_policy_name(fraction, fallback)
                if row["exit_policy"] == old_name:
                    expected[(str(row["ticker"]), policy_name("unprotected", fraction, fallback))] = float(row["pnl"])
    actual = {
        (str(row["ticker"]), str(row["exit_policy"])): float(row["pnl"])
        for row in rows if row["target_protection_mode"] == "unprotected"
    }
    if set(expected) != set(actual):
        raise ExitPolicyError("unprotected reproduction key set mismatch")
    mismatches = [key for key in expected if abs(expected[key] - actual[key]) > 1e-9]
    if mismatches:
        raise ExitPolicyError(
            f"unprotected reproduction failed for {len(mismatches)} row(s); first={mismatches[0]}"
        )


def _bootstrap(values: Sequence[float]) -> tuple[float, float, float]:
    if not values:
        return math.nan, math.nan, math.nan
    mean = statistics.mean(values)
    if len(values) < 2:
        return mean, math.nan, math.nan
    rng = random.Random(20260813)
    samples = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(2_000)]
    samples.sort()
    return mean, samples[49], samples[1949]


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key = {
        (str(row["ticker"]), str(row["exit_policy"])): float(row["pnl"])
        for row in rows
    }
    output: list[dict[str, Any]] = []
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        if segment == "all_96":
            source = list(rows)
        else:
            key = "earlier_64" if segment == "earlier_64_diagnostic" else "later_32"
            source = [row for row in rows if row["diagnostic_segment"] == key]
        for mode in PROTECTION_MODES:
            for fraction in PERCENTAGE_TARGETS:
                for fallback in FALLBACKS:
                    name = policy_name(mode, fraction, fallback)
                    selected = [row for row in source if row["exit_policy"] == name]
                    pnl = [float(row["pnl"]) for row in selected]
                    mean, low, high = _bootstrap(pnl)
                    matching_unprotected = policy_name("unprotected", fraction, fallback)
                    paired_difference = statistics.mean(
                        float(row["pnl"]) - by_key[(str(row["ticker"]), matching_unprotected)]
                        for row in selected
                    ) if selected else math.nan
                    output.append({
                        "segment": segment,
                        "target_protection_mode": mode,
                        "target_fraction_of_maximum": float(fraction),
                        "fallback": fallback,
                        "exit_policy": name,
                        "triggered_markets": len(selected),
                        "mean_pnl": mean,
                        "bootstrap_ci_low": low,
                        "bootstrap_ci_high": high,
                        "mean_paired_difference_vs_matching_unprotected": paired_difference,
                        "profitable_rate": statistics.mean(bool(row["profitable"]) for row in selected) if selected else math.nan,
                        "target_signal_rate": statistics.mean(bool(row["target_signal_seen"]) for row in selected) if selected else math.nan,
                        "protected_target_fill_rate": statistics.mean(bool(row["target_achieved_after_latency"]) for row in selected) if selected else math.nan,
                        "fallback_rate": statistics.mean(
                            str(row["exit_reason"])
                            not in {"profit_target", "protected_profit_target"}
                            for row in selected
                        ) if selected else math.nan,
                        "full_capital_loss_rate": statistics.mean(
                            float(row["pnl"]) <= -0.90 * float(row["cash_deployed"])
                            for row in selected
                        ) if selected else math.nan,
                        "mean_rejected_signals": statistics.mean(
                            float(row["target_rejected_after_latency_count"])
                            for row in selected
                        ) if mode == "protected" and selected else 0.0,
                        "pnl_05_quantile": _quantile(pnl, 0.05),
                        "worst_pnl": min(pnl) if pnl else math.nan,
                        "holdout_read": False,
                        "external_btc_data_used": False,
                    })
    return output


def _money(value: float) -> str:
    return "n/a" if math.isnan(value) else f"${value:.2f}"


def _percent(value: float) -> str:
    return "n/a" if math.isnan(value) else f"{value:.1%}"


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    all_rows = [row for row in summary if row["segment"] == "all_96"]
    lines = [
        "# KXBTC15M H3 target-protection diagnostic",
        "",
        "**Matched execution-mechanics study; entries frozen; holdout sealed.**",
        "",
        "The unprotected rule sells one second after a target signal at whatever full-depth "
        "price remains. The protected rule sells only when the delayed full-position execution "
        "still meets the target after fees; otherwise it rejects the signal and continues "
        "monitoring. Both use the same 52 entries.",
        "",
        "| Mode | Target | Fallback | Mean P&L | Bootstrap 95% CI | vs unprotected | Profitable | Protected fill | Fallback used | Full loss | 5% tail | Worst |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in all_rows:
        lines.append(
            f"| {row['target_protection_mode']} | {float(row['target_fraction_of_maximum']):.0%} | "
            f"{row['fallback']} | {_money(float(row['mean_pnl']))} | "
            f"{_money(float(row['bootstrap_ci_low']))} to {_money(float(row['bootstrap_ci_high']))} | "
            f"{_money(float(row['mean_paired_difference_vs_matching_unprotected']))} | "
            f"{_percent(float(row['profitable_rate']))} | "
            f"{_percent(float(row['protected_target_fill_rate']))} | "
            f"{_percent(float(row['fallback_rate']))} | "
            f"{_percent(float(row['full_capital_loss_rate']))} | "
            f"{_money(float(row['pnl_05_quantile']))} | {_money(float(row['worst_pnl']))} |"
        )
    lines.extend([
        "",
        "## Chronological stability",
        "",
        "| Mode | Target | Fallback | Earlier mean | Later mean |",
        "|---|---:|---|---:|---:|",
    ])
    for mode in PROTECTION_MODES:
        for fraction in PERCENTAGE_TARGETS:
            for fallback in FALLBACKS:
                name = policy_name(mode, fraction, fallback)
                earlier = next(row for row in summary if row["segment"] == "earlier_64_diagnostic" and row["exit_policy"] == name)
                later = next(row for row in summary if row["segment"] == "later_32_diagnostic" and row["exit_policy"] == name)
                lines.append(
                    f"| {mode} | {float(fraction):.0%} | {fallback} | "
                    f"{_money(float(earlier['mean_pnl']))} | {_money(float(later['mean_pnl']))} |"
                )
    lines.extend([
        "",
        "The protected simulation is a full-position price-protection diagnostic, not evidence "
        "that a real passive order would receive queue priority or a fill. The sample has already "
        "been explored; keep the existing holdout sealed and validate any surviving policy on "
        "prospective or explicitly reserved data.",
    ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_zip", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--triggers-csv", type=Path, required=True)
    parser.add_argument("--prior-exit-scenarios-csv", type=Path, required=True)
    parser.add_argument("--outcomes-csv", type=Path, required=True)
    parser.add_argument("--series-csv", type=Path, required=True)
    parser.add_argument("--fee-changes-csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("analysis/kxbtc15m_h3_target_protection"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    triggers = load_primary_triggers(args.triggers_csv)
    prior = load_prior_scenarios(args.prior_exit_scenarios_csv)
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    trigger_by_ticker = {row["ticker"]: row for row in triggers}
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_h3_protection_") as temporary:
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
        triggered = [market for market in eligible if market.ticker in trigger_by_ticker]
        if len(triggered) != EXPECTED_PRIMARY_TRIGGERS:
            raise ExitPolicyError("eligible trigger-market set mismatch")

        for number, market in enumerate(triggered, start=1):
            trigger = trigger_by_ticker[market.ticker]
            snapshots = load_snapshots(market, args.repo_root)
            decision_time = parse_time(trigger["decision_time"])
            decision_index = first_index_at_or_after(snapshots, 0, decision_time)
            if decision_index is None or snapshots[decision_index].observed_at != decision_time:
                raise ExitPolicyError(f"{market.ticker}: exact trigger snapshot not found")
            rows.extend(simulate_matched_policies(
                snapshots=snapshots,
                decision_index=decision_index,
                close_time=market_close_utc(market.ticker),
                winning_side=outcomes[market.ticker],
                trigger=trigger,
            ))
            print(f"[{number:02d}/{EXPECTED_PRIMARY_TRIGGERS}] {market.ticker}")

    verify_prior_reproduction(prior, rows)
    summary = summarize(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_h3_target_protection_scenarios.csv", rows)
    write_csv(args.output_dir / "kxbtc15m_h3_target_protection_summary.csv", summary)
    report_path = args.output_dir / "KXBTC15M_H3_TARGET_PROTECTION.md"
    report_path.write_text(markdown_report(summary), encoding="utf-8")

    print("KXBTC15M H3 target-protection diagnostic: PASS")
    print(f"Frozen primary triggers: {EXPECTED_PRIMARY_TRIGGERS}")
    print(f"Matched policies: {len(policy_names())}")
    print(f"Scenario rows: {len(rows)}")
    print("Targets: 25%, 50%, 75% of actual maximum net settlement profit")
    print("Protection modes: unrestricted delayed sale; delayed target-protected full sale")
    print("Fallbacks: 10-second preclose sale; settlement")
    print("Prior unprotected reproduction: PASS")
    print("External BTC data used: no")
    print("Holdout read: False")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, ExitPolicyError, OSError, SimulationError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"H3 target-protection error: {exc}") from exc
