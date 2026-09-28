#!/usr/bin/env python3
"""Audit H3 monitoring frequency on the frozen 96-market development set.

The strategy, window, entry band, latency, sizing, fees, protected exit, and
preclose fallback are fixed.  Only the decision-monitoring schedule changes.
Matched causal rows use raw HTTP response receipt time.  A separately labelled
legacy 5-second row uses the derived CSV loop-observation time solely to
reproduce the accepted historical baseline; it is never used as the causal
comparator.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import (
    EXPECTED_ELIGIBLE_MARKETS,
    LATENCY_SECONDS,
    MAX_BUDGET,
    SimulationError,
    Snapshot,
    buy_with_budget,
    first_index_at_or_after,
    load_outcomes,
    sell_quantity,
    validate_fee_inputs,
    write_csv,
)
from analyze_kxbtc15m_h3_exit_policies import (
    PRECLOSE_EXIT_SECONDS,
    _find_preclose_exit,
    percentage_target,
)
from analyze_kxbtc15m_h3_late_convergence import favored_quote
from analyze_kxbtc15m_h3_target_protection import find_protected_target_exit
from audit_kxbtc15m_raw_depth import (
    AuditError,
    DevelopmentMarket,
    ParsedBook,
    assess_market,
    market_close_utc,
    one_or_more_descriptors,
    parse_book,
    parse_time,
    quote_matches,
    resolve_raw_path,
    safe_extract_zip,
    select_development_manifests,
    sha256_path,
)


WINDOW_START_SECONDS = 300
WINDOW_END_SECONDS = 240
LOW = Decimal("0.90")
HIGH_EXCLUSIVE = Decimal("0.98")
MAX_ANCHOR_LAG_SECONDS = 2.0
TARGET_FRACTION = Decimal("0.50")
FREQUENCIES = ("native", "1s", "2s", "5s")
ENTRY_MODES = ("unprotected", "state_protected")
EXPECTED_LEGACY_TRIGGERS = 52
EXPECTED_LEGACY_MEAN_PNL = 3.7284038461538462


class FrequencyError(SimulationError):
    """Raised when a frequency-audit input or invariant fails."""


@dataclass(frozen=True)
class MonitoringPoint:
    anchor: datetime
    snapshot_index: int
    anchor_lag_seconds: float


def _mean(values: Sequence[float]) -> float:
    return statistics.mean(values) if values else math.nan


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def _bootstrap(values: Sequence[float]) -> tuple[float, float, float]:
    if not values:
        return math.nan, math.nan, math.nan
    estimate = statistics.mean(values)
    if len(values) < 2:
        return estimate, math.nan, math.nan
    rng = random.Random(20260813)
    samples = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(2_000)]
    samples.sort()
    return estimate, samples[49], samples[1949]


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _average_price(execution: Any) -> Decimal:
    if execution.quantity <= 0:
        raise FrequencyError("cannot average a zero-quantity execution")
    return execution.gross / execution.quantity


def _raw_snapshot_sets(
    market: DevelopmentMarket, repository_root: Path
) -> tuple[list[Snapshot], list[Snapshot]]:
    """Return (CSV loop-time legacy, response-receipt causal) snapshots."""

    descriptors = one_or_more_descriptors(market.manifest, "raw_api_archive")
    rows_by_id = {row["raw_request_id"]: row for row in market.rows}
    csv_ids = [row["raw_request_id"] for row in market.rows]
    records: list[tuple[datetime, datetime, int, str, ParsedBook]] = []
    seen: set[str] = set()
    books_by_id: dict[str, ParsedBook] = {}
    for descriptor in descriptors:
        raw_path = resolve_raw_path(repository_root, descriptor)
        if not raw_path.is_file() or sha256_path(raw_path) != descriptor.get("sha256"):
            raise FrequencyError(f"{market.ticker}: raw archive integrity failure")
        count = 0
        with raw_path.open(encoding="utf-8-sig") as handle:
            for line in handle:
                record = json.loads(line)
                request = record.get("request")
                timing = record.get("timing")
                if not isinstance(request, dict) or not isinstance(timing, dict):
                    raise FrequencyError(f"{market.ticker}: raw record lacks request/timing")
                request_id = str(request.get("request_id", ""))
                if not request_id or request_id in seen:
                    raise FrequencyError(f"{market.ticker}: duplicate/empty request ID")
                row = rows_by_id.get(request_id)
                if row is None:
                    raise FrequencyError(f"{market.ticker}: raw request absent from CSV")
                book = parse_book(record, market.ticker)
                if not quote_matches(row, book):
                    raise FrequencyError(f"{market.ticker}: raw/derived quote mismatch")
                started = parse_time(str(request["started_at_utc"]))
                received = parse_time(str(timing["received_at_utc"]))
                if received < started:
                    raise FrequencyError(f"{market.ticker}: response precedes request")
                monotonic = request.get("started_monotonic_ns")
                if not isinstance(monotonic, int):
                    raise FrequencyError(f"{market.ticker}: invalid monotonic timestamp")
                records.append((started, received, monotonic, request_id, book))
                seen.add(request_id)
                books_by_id[request_id] = book
                count += 1
        if count != int(descriptor.get("record_count", -1)):
            raise FrequencyError(f"{market.ticker}: raw record-count mismatch")

    by_start = sorted(records, key=lambda item: (item[0], item[2], item[3]))
    if [item[3] for item in by_start] != csv_ids:
        raise FrequencyError(f"{market.ticker}: raw/derived sequence mismatch")
    legacy = [
        Snapshot(
            parse_time(row["observed_at_utc"]),
            row["raw_request_id"],
            books_by_id[row["raw_request_id"]],
        )
        for row in market.rows
    ]
    causal_records = sorted(records, key=lambda item: (item[1], item[2], item[3]))
    causal = [Snapshot(received, request_id, book) for _started, received, _mono, request_id, book in causal_records]
    if len({snapshot.request_id for snapshot in causal}) != len(causal):
        raise FrequencyError(f"{market.ticker}: causal request IDs are not unique")
    return legacy, causal


def monitoring_points(
    snapshots: Sequence[Snapshot], close_time: datetime, frequency: str
) -> list[MonitoringPoint]:
    start = close_time - timedelta(seconds=WINDOW_START_SECONDS)
    stop = close_time - timedelta(seconds=WINDOW_END_SECONDS)
    if frequency == "native":
        return [
            MonitoringPoint(snapshot.observed_at, index, 0.0)
            for index, snapshot in enumerate(snapshots)
            if start <= snapshot.observed_at < stop
        ]
    if frequency not in {"1s", "2s", "5s"}:
        raise FrequencyError(f"unknown monitoring frequency: {frequency}")
    step = int(frequency[:-1])
    output: list[MonitoringPoint] = []
    prior_index: int | None = None
    for offset in range(0, WINDOW_START_SECONDS - WINDOW_END_SECONDS, step):
        anchor = start + timedelta(seconds=offset)
        index = first_index_at_or_after(snapshots, 0, anchor)
        if index is None:
            continue
        lag = (snapshots[index].observed_at - anchor).total_seconds()
        if lag < 0 or lag > MAX_ANCHOR_LAG_SECONDS or index == prior_index:
            continue
        output.append(MonitoringPoint(anchor, index, lag))
        prior_index = index
    return output


def _origin(
    previous_quote: tuple[str, Decimal, Decimal] | None,
    current_quote: tuple[str, Decimal, Decimal],
) -> str:
    side, midpoint, _ask = current_quote
    if previous_quote is None:
        return "initial_state"
    previous_side, previous_midpoint, _previous_ask = previous_quote
    if previous_side != side:
        return "side_changed_into_band"
    if previous_midpoint >= HIGH_EXCLUSIVE:
        return "above_98_to_band"
    if previous_midpoint < LOW:
        return "below_90_to_band"
    if LOW <= previous_midpoint < HIGH_EXCLUSIVE:
        return "already_in_band"
    return "unclassified"


def _base_row(
    *, ticker: str, scenario: str, clock_basis: str, frequency: str,
    entry_mode: str, diagnostic_segment: str
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "diagnostic_segment": diagnostic_segment,
        "scenario": scenario,
        "clock_basis": clock_basis,
        "monitoring_frequency": frequency,
        "entry_protection_mode": entry_mode,
        "status": "no_trigger",
        "triggered": False,
        "entry_filled": False,
        "pnl": "",
        "holdout_read": False,
        "external_btc_data_used": False,
        "orders_placed": False,
    }


def simulate_market(
    *, snapshots: Sequence[Snapshot], close_time: datetime, winning_side: str,
    ticker: str, frequency: str, entry_mode: str, clock_basis: str,
    diagnostic_segment: str
) -> dict[str, Any]:
    scenario = f"{clock_basis}_{frequency}_{entry_mode}"
    row = _base_row(
        ticker=ticker, scenario=scenario, clock_basis=clock_basis,
        frequency=frequency, entry_mode=entry_mode,
        diagnostic_segment=diagnostic_segment,
    )
    points = monitoring_points(snapshots, close_time, frequency)
    prior_quote: tuple[str, Decimal, Decimal] | None = None
    rejected = 0
    trigger_count = 0

    for point in points:
        quote = favored_quote(snapshots[point.snapshot_index].book)
        if quote is None:
            prior_quote = None
            continue
        side, midpoint, ask = quote
        qualifies = LOW <= midpoint < HIGH_EXCLUSIVE
        origin = _origin(prior_quote, quote) if qualifies else ""
        prior_quote = quote
        if not qualifies:
            continue
        trigger_count += 1
        decision = snapshots[point.snapshot_index]
        entry_index = first_index_at_or_after(
            snapshots,
            point.snapshot_index + 1,
            decision.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if entry_index is None or snapshots[entry_index].observed_at >= close_time:
            if entry_mode == "state_protected":
                rejected += 1
                break
            row.update({
                "status": "entry_latency_unavailable", "triggered": True,
                "decision_time": decision.observed_at.isoformat(),
                "signal_origin": origin,
            })
            return row
        entry_snapshot = snapshots[entry_index]
        delayed_quote = favored_quote(entry_snapshot.book)
        if entry_mode == "state_protected" and (
            delayed_quote is None
            or delayed_quote[0] != side
            or not (LOW <= delayed_quote[1] < HIGH_EXCLUSIVE)
        ):
            rejected += 1
            continue
        entry = buy_with_budget(entry_snapshot.book.ask_levels(side), MAX_BUDGET)
        if entry.quantity <= 0:
            if entry_mode == "state_protected":
                rejected += 1
                continue
            row.update({"status": "entry_unfilled", "triggered": True})
            return row
        maximum_profit = entry.quantity - entry.buy_outflow
        if maximum_profit <= 0:
            if entry_mode == "state_protected":
                rejected += 1
                continue
            row.update({"status": "nonpositive_maximum_profit", "triggered": True})
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

        delayed_midpoint = "" if delayed_quote is None else _decimal_text(delayed_quote[1])
        row.update({
            "status": "completed",
            "triggered": True,
            "entry_filled": True,
            "monitoring_points": len(points),
            "entry_signal_count": trigger_count,
            "entry_rejected_after_latency_count": rejected,
            "anchor_time": point.anchor.isoformat(),
            "anchor_lag_seconds": f"{point.anchor_lag_seconds:.6f}",
            "decision_time": decision.observed_at.isoformat(),
            "seconds_remaining": f"{(close_time - decision.observed_at).total_seconds():.6f}",
            "side": side,
            "favored_side_won": side == winning_side,
            "signal_origin": origin,
            "decision_favored_midpoint": _decimal_text(midpoint),
            "decision_favored_ask": _decimal_text(ask),
            "entry_execution_time": entry_snapshot.observed_at.isoformat(),
            "realized_entry_delay_seconds": f"{(entry_snapshot.observed_at - decision.observed_at).total_seconds():.6f}",
            "delayed_favored_midpoint": delayed_midpoint,
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

    if trigger_count:
        row.update({
            "status": "all_entry_signals_rejected",
            "triggered": True,
            "entry_signal_count": trigger_count,
            "entry_rejected_after_latency_count": rejected,
            "monitoring_points": len(points),
        })
    else:
        row["monitoring_points"] = len(points)
    return row


def _scenario_order() -> list[tuple[str, str, str]]:
    output = [("legacy_csv_loop_time", "5s", "unprotected")]
    output.extend(
        ("causal_response_receipt", frequency, mode)
        for frequency in FREQUENCIES
        for mode in ENTRY_MODES
    )
    return output


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    scenarios = [f"{clock}_{frequency}_{mode}" for clock, frequency, mode in _scenario_order()]
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        segment_rows = list(rows) if segment == "all_96" else [
            row for row in rows
            if row["diagnostic_segment"] == ("earlier_64" if segment.startswith("earlier") else "later_32")
        ]
        by_scenario_market = {
            (str(row["scenario"]), str(row["ticker"])): float(row["pnl"] or 0.0)
            for row in segment_rows
        }
        for scenario in scenarios:
            selected = [row for row in segment_rows if row["scenario"] == scenario]
            completed = [row for row in selected if row["status"] == "completed"]
            pnl_entered = [float(row["pnl"]) for row in completed]
            pnl_market = [float(row["pnl"] or 0.0) for row in selected]
            mean_market, ci_low, ci_high = _bootstrap(pnl_market)
            sample = selected[0] if selected else {}
            clock = str(sample.get("clock_basis", ""))
            frequency = str(sample.get("monitoring_frequency", ""))
            mode = str(sample.get("entry_protection_mode", ""))
            baseline = f"causal_response_receipt_5s_{mode}"
            paired = math.nan
            if clock == "causal_response_receipt" and selected:
                paired = statistics.mean(
                    float(row["pnl"] or 0.0) - by_scenario_market[(baseline, str(row["ticker"]))]
                    for row in selected
                )
            output.append({
                "segment": segment,
                "scenario": scenario,
                "clock_basis": clock,
                "monitoring_frequency": frequency,
                "entry_protection_mode": mode,
                "eligible_markets": len(selected),
                "triggered_markets": sum(bool(row["triggered"]) for row in selected),
                "entry_filled_markets": len(completed),
                "no_trigger_markets": sum(row["status"] == "no_trigger" for row in selected),
                "all_entry_signals_rejected_markets": sum(row["status"] == "all_entry_signals_rejected" for row in selected),
                "trigger_rate_per_market": _mean([bool(row["triggered"]) for row in selected]),
                "entry_fill_rate_given_trigger": (
                    len(completed) / sum(bool(row["triggered"]) for row in selected)
                    if any(bool(row["triggered"]) for row in selected) else math.nan
                ),
                "mean_pnl_per_eligible_market": mean_market,
                "bootstrap_ci_low_per_eligible_market": ci_low,
                "bootstrap_ci_high_per_eligible_market": ci_high,
                "mean_pnl_per_filled_entry": _mean(pnl_entered),
                "mean_paired_difference_vs_causal_5s_per_market": paired,
                "profitable_rate_per_filled_entry": _mean([bool(row["profitable"]) for row in completed]),
                "protected_target_fill_rate": _mean([bool(row["target_filled"]) for row in completed]),
                "fallback_rate": _mean([bool(row["fallback_used"]) for row in completed]),
                "full_capital_loss_rate": _mean([bool(row["full_capital_loss"]) for row in completed]),
                "mean_entry_rejections_per_market": _mean([
                    float(row.get("entry_rejected_after_latency_count") or 0) for row in selected
                ]),
                "mean_realized_entry_delay_seconds": _mean([
                    float(row["realized_entry_delay_seconds"]) for row in completed
                ]),
                "mean_decision_midpoint": _mean([
                    float(row["decision_favored_midpoint"]) for row in completed
                ]),
                "mean_entry_average_price": _mean([
                    float(row["entry_average_price"]) for row in completed
                ]),
                "pnl_05_quantile_per_filled_entry": _quantile(pnl_entered, 0.05),
                "worst_pnl_per_filled_entry": min(pnl_entered) if pnl_entered else math.nan,
                "holdout_read": False,
                "external_btc_data_used": False,
                "orders_placed": False,
            })
    return output


def verify_legacy_reproduction(summary: Sequence[Mapping[str, Any]]) -> None:
    row = next(
        item for item in summary
        if item["segment"] == "all_96"
        and item["scenario"] == "legacy_csv_loop_time_5s_unprotected"
    )
    if int(row["entry_filled_markets"]) != EXPECTED_LEGACY_TRIGGERS:
        raise FrequencyError(
            f"legacy reproduction expected 52 entries; found {row['entry_filled_markets']}"
        )
    if abs(float(row["mean_pnl_per_filled_entry"]) - EXPECTED_LEGACY_MEAN_PNL) > 1e-9:
        raise FrequencyError(
            "legacy reproduction mean P&L mismatch: "
            f"{row['mean_pnl_per_filled_entry']}"
        )


def _money(value: Any) -> str:
    number = float(value)
    return "n/a" if math.isnan(number) else f"${number:.2f}"


def _percent(value: Any) -> str:
    number = float(value)
    return "n/a" if math.isnan(number) else f"{number:.1%}"


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    rows = [row for row in summary if row["segment"] == "all_96"]
    lines = [
        "# KXBTC15M H3 monitoring-frequency diagnostic",
        "",
        "**Matched development execution diagnostic; rule frozen; holdout sealed.**",
        "",
        "The causal rows differ only in how often the frozen H3 entry condition is checked. "
        "All use raw HTTP response receipt time, a one-second entry delay, archived full depth, "
        "a $100 maximum budget, conservative fees, the protected 50%-of-maximum profit target, "
        "and a ten-second preclose fallback. Native means every archived response (approximately "
        "0.5 seconds, with actual jitter).",
        "",
        "State-protected entry requires the same favored side and 90%-to-below-98% midpoint band "
        "to remain valid after latency; rejected signals resume monitoring. Unprotected entry is "
        "the frozen behavior. The legacy row uses derived CSV loop timestamps only to reproduce the "
        "accepted prior baseline and is not a causal frequency comparator.",
        "",
        "| Clock | Frequency | Entry mode | Trigger | Filled | Mean / market | vs causal 5s | Mean / fill | Profitable | Target fill | Full loss | 5% tail | Worst |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['clock_basis']} | {row['monitoring_frequency']} | {row['entry_protection_mode']} | "
            f"{_percent(row['trigger_rate_per_market'])} | {row['entry_filled_markets']} | "
            f"{_money(row['mean_pnl_per_eligible_market'])} | "
            f"{_money(row['mean_paired_difference_vs_causal_5s_per_market'])} | "
            f"{_money(row['mean_pnl_per_filled_entry'])} | "
            f"{_percent(row['profitable_rate_per_filled_entry'])} | "
            f"{_percent(row['protected_target_fill_rate'])} | "
            f"{_percent(row['full_capital_loss_rate'])} | "
            f"{_money(row['pnl_05_quantile_per_filled_entry'])} | "
            f"{_money(row['worst_pnl_per_filled_entry'])} |"
        )
    lines.extend([
        "",
        "Mean P&L per eligible market assigns $0 to no-trade markets and is the primary matched "
        "frequency comparison. Mean per filled entry is conditional and can improve merely by "
        "changing which markets trigger. Earlier/later diagnostic rows and signal origins are "
        "retained in the CSVs.",
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
        "--output-dir", type=Path,
        default=Path("analysis/kxbtc15m_h3_frequency"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_frequency_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise FrequencyError(f"expected 96 eligible markets; found {len(eligible)}")
        if set(outcomes) != {market.ticker for market in eligible}:
            raise FrequencyError("outcome ticker set does not equal development market set")

        for number, market in enumerate(eligible, start=1):
            legacy, causal = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            segment = "earlier_64" if market.index <= 64 else "later_32"
            for clock, frequency, mode in _scenario_order():
                snapshots = legacy if clock == "legacy_csv_loop_time" else causal
                rows.append(simulate_market(
                    snapshots=snapshots,
                    close_time=close,
                    winning_side=outcomes[market.ticker],
                    ticker=market.ticker,
                    frequency=frequency,
                    entry_mode=mode,
                    clock_basis=clock,
                    diagnostic_segment=segment,
                ))
            print(f"[{number:02d}/96] {market.ticker}")

    summary = summarize(rows)
    verify_legacy_reproduction(summary)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = args.output_dir / "kxbtc15m_h3_frequency_scenarios.csv"
    summary_path = args.output_dir / "kxbtc15m_h3_frequency_summary.csv"
    report_path = args.output_dir / "KXBTC15M_H3_FREQUENCY.md"
    write_csv(scenario_path, rows)
    write_csv(summary_path, summary)
    report_path.write_text(markdown_report(summary), encoding="utf-8")

    print("KXBTC15M H3 monitoring-frequency diagnostic: PASS")
    print("Eligible development markets: 96")
    print("Causal frequencies: native, 1s, 2s, 5s")
    print("Entry modes: unprotected, state_protected")
    print("Legacy 5s baseline reproduced: True")
    print("Clock basis for matched comparisons: raw response receipt")
    print("Holdout read: False")
    print("Orders placed: False")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, FrequencyError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"KXBTC15M H3 frequency error: {exc}") from exc
