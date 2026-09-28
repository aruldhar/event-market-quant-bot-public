#!/usr/bin/env python3
"""Development-only, depth-aware bounded KXBTC15M reversion simulation.

The simulation compares one, two, and three buy-in policies on the same fixed
maximum cash budget. It is scenario analysis, not a deployable portfolio or an
authorization to trade. The frozen 26-market holdout is never opened.
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
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable, Mapping, Sequence

from audit_kxbtc15m_raw_depth import (
    AuditError,
    DevelopmentMarket,
    HOLDOUT_FIRST_TICKER,
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


EXPECTED_ELIGIBLE_MARKETS = 96
MAX_BUDGET = Decimal("100.00")
DROP_STEP = Decimal("0.05")
NET_PROFIT_TARGET = Decimal("1.00")
LATENCY_SECONDS = 1.0
FORCED_EXIT_SECONDS_BEFORE_CLOSE = 120
FEE_BASE_RATE = Decimal("0.07")
FEE_TYPE = "quadratic"
FEE_MULTIPLIER = Decimal("1")
CENT = Decimal("0.01")
CENTICENT = Decimal("0.0001")


class SimulationError(RuntimeError):
    """Raised when frozen inputs or execution invariants fail."""


@dataclass(frozen=True)
class Snapshot:
    observed_at: datetime
    request_id: str
    book: ParsedBook


@dataclass(frozen=True)
class Fill:
    price: Decimal
    quantity: Decimal


@dataclass(frozen=True)
class Execution:
    fills: tuple[Fill, ...]
    quantity: Decimal
    gross: Decimal
    fee: Decimal

    @property
    def buy_outflow(self) -> Decimal:
        return self.gross + self.fee

    @property
    def sell_inflow(self) -> Decimal:
        return self.gross - self.fee


def ceil_to(value: Decimal, quantum: Decimal) -> Decimal:
    if value <= 0:
        return Decimal("0")
    return (value / quantum).to_integral_value(rounding=ROUND_CEILING) * quantum


def quadratic_fee(
    fills: Sequence[Fill], *, multiplier: Decimal = FEE_MULTIPLIER
) -> Decimal:
    """Conservative non-direct-member fee for one marketable order.

    Each price-level fill is first rounded up to $0.0001 as documented by the
    exchange. The order total is then rounded up to the account's $0.01 balance
    precision. This cannot understate the fee for the archived whole-cent book.
    """

    centicent_fees = [
        ceil_to(
            FEE_BASE_RATE
            * multiplier
            * fill.quantity
            * fill.price
            * (Decimal("1") - fill.price),
            CENTICENT,
        )
        for fill in fills
    ]
    return ceil_to(sum(centicent_fees, Decimal("0")), CENT)


def _whole_contract_capacity(quantity: Decimal) -> int:
    return int(quantity.to_integral_value(rounding=ROUND_FLOOR))


def buy_with_budget(
    ask_levels: Sequence[tuple[Decimal, Decimal]],
    budget: Decimal,
    *,
    multiplier: Decimal = FEE_MULTIPLIER,
) -> Execution:
    """Cross asks in price order without spending more than the tranche budget."""

    fills: list[Fill] = []
    for price, displayed_quantity in ask_levels:
        capacity = _whole_contract_capacity(displayed_quantity)
        if capacity <= 0:
            continue
        low, high = 0, capacity
        while low < high:
            middle = (low + high + 1) // 2
            candidate = fills + [Fill(price, Decimal(middle))]
            gross = sum((fill.price * fill.quantity for fill in candidate), Decimal("0"))
            if gross + quadratic_fee(candidate, multiplier=multiplier) <= budget:
                low = middle
            else:
                high = middle - 1
        if low:
            fills.append(Fill(price, Decimal(low)))
        candidate_fee = quadratic_fee(fills, multiplier=multiplier)
        candidate_gross = sum(
            (fill.price * fill.quantity for fill in fills), Decimal("0")
        )
        if candidate_gross + candidate_fee >= budget - CENT:
            break
    gross = sum((fill.price * fill.quantity for fill in fills), Decimal("0"))
    fee = quadratic_fee(fills, multiplier=multiplier)
    quantity = sum((fill.quantity for fill in fills), Decimal("0"))
    return Execution(tuple(fills), quantity, gross, fee)


def sell_quantity(
    bid_levels: Sequence[tuple[Decimal, Decimal]],
    quantity: Decimal,
    *,
    multiplier: Decimal = FEE_MULTIPLIER,
) -> Execution:
    """Cross bids best-first for up to the requested whole-contract quantity."""

    remaining = int(quantity)
    fills: list[Fill] = []
    for price, displayed_quantity in reversed(bid_levels):
        take = min(remaining, _whole_contract_capacity(displayed_quantity))
        if take > 0:
            fills.append(Fill(price, Decimal(take)))
            remaining -= take
        if remaining == 0:
            break
    gross = sum((fill.price * fill.quantity for fill in fills), Decimal("0"))
    fee = quadratic_fee(fills, multiplier=multiplier)
    filled = sum((fill.quantity for fill in fills), Decimal("0"))
    return Execution(tuple(fills), filled, gross, fee)


def first_index_at_or_after(
    snapshots: Sequence[Snapshot], start_index: int, target: datetime
) -> int | None:
    for index in range(start_index, len(snapshots)):
        if snapshots[index].observed_at >= target:
            return index
    return None


def best_ask(book: ParsedBook, side: str) -> Decimal | None:
    levels = book.ask_levels(side)
    return levels[0][0] if levels else None


def choose_lower_side(book: ParsedBook) -> str | None:
    yes, no = best_ask(book, "YES"), best_ask(book, "NO")
    if yes is None or no is None or yes == no:
        return None
    return "YES" if yes < no else "NO"


def simulate_policy(
    *,
    snapshots: Sequence[Snapshot],
    decision_index: int,
    close_time: datetime,
    winning_side: str,
    tranche_count: int,
    net_loss_stop: Decimal | None = None,
    loss_stop_grace_seconds: float = 0.0,
    loss_stop_confirmation_seconds: float = 0.0,
    additions_before_stop: bool = False,
) -> dict[str, Any]:
    if tranche_count not in {1, 2, 3}:
        raise SimulationError("tranche_count must be 1, 2, or 3")
    if net_loss_stop is not None and net_loss_stop <= 0:
        raise SimulationError("net_loss_stop must be positive when supplied")
    if loss_stop_grace_seconds < 0 or loss_stop_confirmation_seconds < 0:
        raise SimulationError("loss-stop grace and confirmation must be nonnegative")
    decision = snapshots[decision_index]
    side = choose_lower_side(decision.book)
    base = {
        "decision_time": decision.observed_at.isoformat(),
        "side": side or "",
        "tranche_count": tranche_count,
        "max_budget": float(MAX_BUDGET),
        "net_loss_stop": "" if net_loss_stop is None else float(net_loss_stop),
        "loss_stop_grace_seconds": loss_stop_grace_seconds,
        "loss_stop_confirmation_seconds": loss_stop_confirmation_seconds,
        "additions_before_stop": additions_before_stop,
    }
    if side is None:
        return {**base, "status": "entry_side_unavailable"}

    stop_time = close_time - timedelta(seconds=FORCED_EXIT_SECONDS_BEFORE_CLOSE)
    execution_index = first_index_at_or_after(
        snapshots,
        decision_index + 1,
        decision.observed_at + timedelta(seconds=LATENCY_SECONDS),
    )
    if execution_index is None or snapshots[execution_index].observed_at >= stop_time:
        return {**base, "status": "entry_missed_time_stop"}

    tranche_budget = MAX_BUDGET / Decimal(tranche_count)
    entry_snapshot = snapshots[execution_index]
    reference_ask = best_ask(entry_snapshot.book, side)
    if reference_ask is None:
        return {**base, "status": "entry_book_unavailable"}
    entry = buy_with_budget(entry_snapshot.book.ask_levels(side), tranche_budget)
    if entry.quantity <= 0:
        return {**base, "status": "entry_unfilled"}

    quantity = entry.quantity
    outflow = entry.buy_outflow
    total_fees = entry.fee
    tranches_filled = 1
    last_fill_time = entry_snapshot.observed_at
    cursor = execution_index + 1
    missed_profitable_exits = 0
    missed_loss_stops = 0
    additions_missed = 0
    exit_execution: Execution | None = None
    exit_reason = ""
    exit_time: datetime | None = None
    loss_breach_started_at: datetime | None = None

    while cursor < len(snapshots) and snapshots[cursor].observed_at < stop_time:
        observed = snapshots[cursor]
        liquidation = sell_quantity(observed.book.bid_levels(side), quantity)
        if (
            liquidation.quantity == quantity
            and liquidation.sell_inflow - outflow >= NET_PROFIT_TARGET
        ):
            delayed_index = first_index_at_or_after(
                snapshots,
                cursor + 1,
                observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
            )
            if delayed_index is not None:
                delayed = sell_quantity(
                    snapshots[delayed_index].book.bid_levels(side), quantity
                )
                if delayed.quantity == quantity:
                    exit_execution = delayed
                    exit_reason = "profit_target"
                    exit_time = snapshots[delayed_index].observed_at
                    break
            missed_profitable_exits += 1

        addition_filled = False
        if additions_before_stop and tranches_filled < tranche_count:
            trigger = reference_ask - DROP_STEP * Decimal(tranches_filled)
            observed_ask = best_ask(observed.book, side)
            if observed_ask is not None and observed_ask <= trigger:
                delayed_index = first_index_at_or_after(
                    snapshots,
                    cursor + 1,
                    observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
                )
                if delayed_index is not None:
                    delayed_snapshot = snapshots[delayed_index]
                    delayed_ask = best_ask(delayed_snapshot.book, side)
                    if delayed_ask is not None and delayed_ask <= trigger:
                        addition = buy_with_budget(
                            delayed_snapshot.book.ask_levels(side), tranche_budget
                        )
                        if addition.quantity > 0:
                            quantity += addition.quantity
                            outflow += addition.buy_outflow
                            total_fees += addition.fee
                            tranches_filled += 1
                            last_fill_time = delayed_snapshot.observed_at
                            loss_breach_started_at = None
                            cursor = delayed_index + 1
                            addition_filled = True
                if not addition_filled:
                    additions_missed += 1
            if addition_filled:
                continue

        stop_armed = (
            net_loss_stop is not None
            and (observed.observed_at - last_fill_time).total_seconds()
            >= loss_stop_grace_seconds
        )
        stop_breached = (
            stop_armed
            and liquidation.quantity == quantity
            and liquidation.sell_inflow - outflow <= -net_loss_stop
        )
        if stop_breached:
            if loss_breach_started_at is None:
                loss_breach_started_at = observed.observed_at
        else:
            loss_breach_started_at = None

        stop_confirmed = (
            loss_breach_started_at is not None
            and (observed.observed_at - loss_breach_started_at).total_seconds()
            >= loss_stop_confirmation_seconds
        )
        if stop_confirmed:
            delayed_index = first_index_at_or_after(
                snapshots,
                cursor + 1,
                observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
            )
            if delayed_index is not None:
                delayed = sell_quantity(
                    snapshots[delayed_index].book.bid_levels(side), quantity
                )
                if delayed.quantity == quantity:
                    exit_execution = delayed
                    exit_reason = "loss_stop"
                    exit_time = snapshots[delayed_index].observed_at
                    break
            missed_loss_stops += 1

        if not additions_before_stop and tranches_filled < tranche_count:
            trigger = reference_ask - DROP_STEP * Decimal(tranches_filled)
            observed_ask = best_ask(observed.book, side)
            if observed_ask is not None and observed_ask <= trigger:
                delayed_index = first_index_at_or_after(
                    snapshots,
                    cursor + 1,
                    observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
                )
                if delayed_index is not None:
                    delayed_snapshot = snapshots[delayed_index]
                    delayed_ask = best_ask(delayed_snapshot.book, side)
                    if delayed_ask is not None and delayed_ask <= trigger:
                        addition = buy_with_budget(
                            delayed_snapshot.book.ask_levels(side), tranche_budget
                        )
                        if addition.quantity > 0:
                            quantity += addition.quantity
                            outflow += addition.buy_outflow
                            total_fees += addition.fee
                            tranches_filled += 1
                            last_fill_time = delayed_snapshot.observed_at
                            loss_breach_started_at = None
                            cursor = delayed_index + 1
                            continue
                additions_missed += 1
        cursor += 1

    if exit_execution is None:
        stop_index = first_index_at_or_after(snapshots, cursor, stop_time)
        while stop_index is not None and snapshots[stop_index].observed_at < close_time:
            delayed_index = first_index_at_or_after(
                snapshots,
                stop_index + 1,
                snapshots[stop_index].observed_at + timedelta(seconds=LATENCY_SECONDS),
            )
            if delayed_index is None or snapshots[delayed_index].observed_at >= close_time:
                break
            attempted = sell_quantity(
                snapshots[delayed_index].book.bid_levels(side), quantity
            )
            if attempted.quantity == quantity:
                exit_execution = attempted
                exit_reason = "forced_time_stop"
                exit_time = snapshots[delayed_index].observed_at
                break
            stop_index = delayed_index + 1

    if exit_execution is None:
        settlement_inflow = quantity if side == winning_side else Decimal("0")
        pnl = settlement_inflow - outflow
        exit_reason = "settlement_after_liquidity_failure"
        exit_time_text = close_time.isoformat()
        exit_gross = settlement_inflow
        exit_fee = Decimal("0")
    else:
        pnl = exit_execution.sell_inflow - outflow
        total_fees += exit_execution.fee
        exit_time_text = exit_time.isoformat() if exit_time else ""
        exit_gross = exit_execution.gross
        exit_fee = exit_execution.fee

    return {
        **base,
        "status": "completed",
        "entry_execution_time": entry_snapshot.observed_at.isoformat(),
        "reference_ask": float(reference_ask),
        "tranches_filled": tranches_filled,
        "contracts": float(quantity),
        "cash_deployed": float(outflow),
        "budget_utilization": float(outflow / MAX_BUDGET),
        "entry_and_addition_fees": float(total_fees - exit_fee),
        "exit_time": exit_time_text,
        "exit_reason": exit_reason,
        "exit_gross": float(exit_gross),
        "exit_fee": float(exit_fee),
        "total_fees": float(total_fees),
        "pnl": float(pnl),
        "return_on_max_budget": float(pnl / MAX_BUDGET),
        "return_on_deployed": float(pnl / outflow),
        "profitable": pnl > 0,
        "target_achieved_after_latency": exit_reason == "profit_target" and pnl >= NET_PROFIT_TARGET,
        "missed_profitable_exits": missed_profitable_exits,
        "missed_loss_stops": missed_loss_stops,
        "loss_stop_executed": exit_reason == "loss_stop",
        "additions_missed_after_latency": additions_missed,
    }


def load_snapshots(market: DevelopmentMarket, repository_root: Path) -> list[Snapshot]:
    descriptors = one_or_more_descriptors(market.manifest, "raw_api_archive")
    csv_ids = [row["raw_request_id"] for row in market.rows]
    rows_by_id = {row["raw_request_id"]: row for row in market.rows}
    raw_records: list[tuple[datetime, int, str]] = []
    books: dict[str, ParsedBook] = {}
    for descriptor in descriptors:
        raw_path = resolve_raw_path(repository_root, descriptor)
        if not raw_path.is_file() or sha256_path(raw_path) != descriptor.get("sha256"):
            raise SimulationError(f"{market.ticker}: raw archive integrity failure")
        record_count = 0
        with raw_path.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                request_id = record["request"]["request_id"]
                if request_id in books:
                    raise SimulationError(f"{market.ticker}: duplicate raw request ID")
                book = parse_book(record, market.ticker)
                row = rows_by_id.get(request_id)
                if row is None or not quote_matches(row, book):
                    raise SimulationError(f"{market.ticker}: raw/derived quote mismatch")
                started_at = parse_time(record["request"]["started_at_utc"])
                monotonic_ns = record["request"]["started_monotonic_ns"]
                if not isinstance(monotonic_ns, int):
                    raise SimulationError(f"{market.ticker}: invalid monotonic timestamp")
                raw_records.append((started_at, monotonic_ns, request_id))
                books[request_id] = book
                record_count += 1
        if record_count != descriptor.get("record_count"):
            raise SimulationError(f"{market.ticker}: raw record-count mismatch")
    raw_records.sort(key=lambda item: (item[0], item[1], item[2]))
    raw_ids = [item[2] for item in raw_records]
    if raw_ids != csv_ids:
        raise SimulationError(f"{market.ticker}: raw/derived sequence mismatch")
    return [
        Snapshot(parse_time(row["observed_at_utc"]), row["raw_request_id"], books[row["raw_request_id"]])
        for row in market.rows
    ]


def load_outcomes(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != EXPECTED_ELIGIBLE_MARKETS:
        raise SimulationError(f"expected 96 development outcomes; found {len(rows)}")
    outcomes: dict[str, str] = {}
    for row in rows:
        ticker = row.get("ticker", "")
        if ticker >= HOLDOUT_FIRST_TICKER:
            raise SimulationError("holdout outcome entered development simulation")
        if row.get("status") != "finalized" or row.get("result") not in {"yes", "no"}:
            raise SimulationError(f"{ticker}: outcome is not finalized yes/no")
        if ticker in outcomes:
            raise SimulationError(f"duplicate outcome: {ticker}")
        outcomes[ticker] = row["result"].upper()
    return outcomes


def validate_fee_inputs(series_path: Path, changes_path: Path) -> Decimal:
    with series_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise SimulationError("expected exactly one series snapshot row")
    row = rows[0]
    if row.get("series_ticker") != "KXBTC15M" or row.get("fee_type") != FEE_TYPE:
        raise SimulationError("series fee type is not frozen quadratic KXBTC15M")
    try:
        multiplier = Decimal(row.get("fee_multiplier") or "")
    except InvalidOperation as exc:
        raise SimulationError("series fee multiplier is not numeric") from exc
    if multiplier != FEE_MULTIPLIER:
        raise SimulationError(f"expected fee multiplier 1; got {multiplier}")
    with changes_path.open(newline="", encoding="utf-8-sig") as handle:
        changes = list(csv.DictReader(handle))
    if changes:
        raise SimulationError(
            "historical fee-change rows require a separately interpreted effective schedule"
        )
    return multiplier


def phase_for_minute(minute: int) -> str:
    if minute < 5:
        return "01_first_0_5m"
    if minute < 10:
        return "02_middle_5_10m"
    return "03_late_10_13m"


def clustered_mean_ci(rows: Sequence[Mapping[str, Any]], key: str) -> tuple[float, float, float]:
    by_market: dict[str, list[float]] = {}
    for row in rows:
        by_market.setdefault(str(row["ticker"]), []).append(float(row[key]))
    market_means = [statistics.mean(values) for values in by_market.values()]
    estimate = statistics.mean(market_means) if market_means else math.nan
    if len(market_means) < 2:
        return estimate, math.nan, math.nan
    rng = random.Random(20260813)
    samples = [
        statistics.mean(rng.choices(market_means, k=len(market_means)))
        for _ in range(2000)
    ]
    samples.sort()
    return estimate, samples[49], samples[1949]


def summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for tranche_count in (1, 2, 3):
        for phase in ("01_first_0_5m", "02_middle_5_10m", "03_late_10_13m"):
            subset = [
                row for row in rows
                if row["tranche_count"] == tranche_count
                and row["time_phase"] == phase
                and row["status"] == "completed"
            ]
            mean_pnl, low, high = clustered_mean_ci(subset, "pnl")
            output.append({
                "tranche_count": tranche_count,
                "time_phase": phase,
                "completed_scenarios": len(subset),
                "markets": len({row["ticker"] for row in subset}),
                "mean_pnl_equal_market_weighted": mean_pnl,
                "mean_pnl_clustered_ci_low": low,
                "mean_pnl_clustered_ci_high": high,
                "median_pnl": statistics.median(float(row["pnl"]) for row in subset) if subset else math.nan,
                "profitable_rate": statistics.mean(bool(row["profitable"]) for row in subset) if subset else math.nan,
                "profit_target_rate": statistics.mean(bool(row["target_achieved_after_latency"]) for row in subset) if subset else math.nan,
                "settlement_fallback_rate": statistics.mean(row["exit_reason"] == "settlement_after_liquidity_failure" for row in subset) if subset else math.nan,
                "mean_budget_utilization": statistics.mean(float(row["budget_utilization"]) for row in subset) if subset else math.nan,
                "mean_total_fees": statistics.mean(float(row["total_fees"]) for row in subset) if subset else math.nan,
            })
    return output


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise SimulationError(f"refusing empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def markdown_report(summary: Sequence[Mapping[str, Any]], scenario_count: int) -> str:
    lines = [
        "# KXBTC15M bounded pooled-reversion simulation",
        "",
        "**Development-only scenario study; holdout sealed.**",
        "",
        f"Scenarios completed or explicitly skipped: {scenario_count:,}.",
        "",
        "Each row starts from one elapsed-minute anchor, chooses the lower executable side, "
        "uses a fixed $100 maximum budget, applies a one-second observation-to-fill delay, "
        "crosses archived full depth, charges conservative taker fees, targets $1 net profit, "
        "and begins forced liquidation with 120 seconds remaining.",
        "",
        "| Buy-ins | Time phase | Mean P&L / $100 | Clustered 95% CI | Profitable | Target hit | Settlement fallback |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['tranche_count']} | {row['time_phase']} | "
            f"${row['mean_pnl_equal_market_weighted']:.2f} | "
            f"${row['mean_pnl_clustered_ci_low']:.2f} to ${row['mean_pnl_clustered_ci_high']:.2f} | "
            f"{row['profitable_rate']:.1%} | {row['profit_target_rate']:.1%} | "
            f"{row['settlement_fallback_rate']:.1%} |"
        )
    lines.extend([
        "",
        "Rows overlap within markets and are not additive portfolio trades. Selection of one "
        "policy for a holdout test requires a separate freeze after reviewing this development report.",
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
        default=Path("analysis/kxbtc15m_bounded_simulation"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcomes = load_outcomes(args.outcomes_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    all_rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_bounded_") as temporary:
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

        for number, market in enumerate(eligible, start=1):
            snapshots = load_snapshots(market, args.repo_root)
            close = market_close_utc(market.ticker)
            open_time = close - timedelta(minutes=15)
            for minute in range(13):
                target = open_time + timedelta(minutes=minute)
                decision_index = first_index_at_or_after(snapshots, 0, target)
                if decision_index is None:
                    continue
                for tranches in (1, 2, 3):
                    result = simulate_policy(
                        snapshots=snapshots,
                        decision_index=decision_index,
                        close_time=close,
                        winning_side=outcomes[market.ticker],
                        tranche_count=tranches,
                    )
                    result.update({
                        "market_index": market.index,
                        "ticker": market.ticker,
                        "anchor_minute": minute,
                        "time_phase": phase_for_minute(minute),
                        "holdout_read": False,
                    })
                    all_rows.append(result)
            print(f"[{number:02d}/96] {market.ticker}")

    summary = summarize(all_rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = args.output_dir / "kxbtc15m_bounded_simulation_scenarios.csv"
    summary_path = args.output_dir / "kxbtc15m_bounded_simulation_summary.csv"
    report_path = args.output_dir / "KXBTC15M_BOUNDED_SIMULATION.md"
    write_csv(scenario_path, all_rows)
    write_csv(summary_path, summary)
    report_path.write_text(markdown_report(summary, len(all_rows)), encoding="utf-8")

    print("KXBTC15M bounded simulation: PASS")
    print(f"Eligible development markets: {len(eligible)}")
    print(f"Scenario rows: {len(all_rows)}")
    print("Maximum budget per scenario: $100.00")
    print("Compared buy-ins: 1, 2, 3")
    print("Drop step: $0.05")
    print("Net profit target: $1.00")
    print("Execution latency: 1.0 seconds")
    print("Forced-exit start: 120 seconds before close")
    print("Fee model: quadratic x 1; conservative taker/account rounding")
    print("Holdout read: False")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, OSError, SimulationError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Simulation error: {exc}") from exc
