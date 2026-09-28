#!/usr/bin/env python3
"""Explore bounded causal stop-loss candidates on all opened H3 evidence.

This is an adaptive development diagnostic, not a new holdout evaluation.  It
replays the frozen H3 baseline on the original 96-market development partition
and the permanently opened 26-market partition, verifies the opened baseline
market by market, and then applies a small prespecified surface of causal,
depth-aware full-position risk exits.  It selects no H3 v2 policy and performs
no hybrid search.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import (
    EXPECTED_ELIGIBLE_MARKETS,
    LATENCY_SECONDS,
    Snapshot,
    first_index_at_or_after,
    load_outcomes,
    sell_quantity,
    validate_fee_inputs,
    write_csv,
)
from analyze_kxbtc15m_h3_exit_policies import PRECLOSE_EXIT_SECONDS
from analyze_kxbtc15m_h3_frequency import (
    TARGET_FRACTION,
    _decimal_text,
    _raw_snapshot_sets,
    simulate_market as simulate_frequency_market,
)
from analyze_kxbtc15m_h3_native_exit_policies import (
    BASELINE_POLICY,
    EXPECTED_NATIVE_ENTRIES,
    find_native_entry,
    simulate_policy,
    verify_baseline_reproduction,
)
from analyze_kxbtc15m_h3_native_path_stops import progressive_liquidation
from analyze_kxbtc15m_h3_time_windows import _bootstrap, _mean, _money, _percent, _quantile
from audit_kxbtc15m_raw_depth import (
    AuditError,
    DevelopmentMarket,
    assess_market,
    market_close_utc,
    parse_time,
    safe_extract_zip,
    select_development_manifests,
)
EXPECTED_HOLDOUT_MARKETS = 26
HOLDOUT_FIRST_TICKER = "KXBTC15M-26AUG121445-45"
HOLDOUT_LAST_TICKER = "KXBTC15M-26AUG122100-00"
EXPECTED_TOTAL_MARKETS = EXPECTED_ELIGIBLE_MARKETS + EXPECTED_HOLDOUT_MARKETS
EXPECTED_HOLDOUT_ENTRIES = 14
EXPECTED_TOTAL_ENTRIES = EXPECTED_NATIVE_ENTRIES + EXPECTED_HOLDOUT_ENTRIES
EXPECTED_HOLDOUT_TOTAL_PNL = -46.55
FULL_LOSS_FRACTION = Decimal("0.90")
MATERIAL_LOSER_SAVINGS = 25.0
MAX_WINNER_COST_SHARE = 0.50


class StopCandidateError(RuntimeError):
    """Raised when an opened-sample diagnostic invariant fails closed."""


def _required(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if result is None or str(result) == "":
        raise StopCandidateError(f"required field {field!r} is missing")
    return str(result)


def select_opened_manifests(root: Path) -> list[dict[str, Any]]:
    """Select the exact already-opened 26-market chronological partition."""

    manifests: list[dict[str, Any]] = []
    for path in root.rglob("record_orderbook_*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        ticker = document.get("arguments", {}).get("ticker")
        if ticker and document.get("status") == "completed":
            manifests.append(document)
    manifests.sort(key=lambda item: parse_time(_required(item, "started_at_utc")))
    selected: list[dict[str, Any]] = []
    active = False
    for manifest in manifests:
        ticker = _required(manifest.get("arguments", {}), "ticker")
        if ticker == HOLDOUT_FIRST_TICKER:
            active = True
        if active:
            selected.append(manifest)
        if ticker == HOLDOUT_LAST_TICKER:
            break
    if len(selected) != EXPECTED_HOLDOUT_MARKETS:
        raise StopCandidateError(
            f"expected {EXPECTED_HOLDOUT_MARKETS} opened manifests; found {len(selected)}"
        )
    tickers = [_required(item["arguments"], "ticker") for item in selected]
    if tickers[0] != HOLDOUT_FIRST_TICKER or tickers[-1] != HOLDOUT_LAST_TICKER:
        raise StopCandidateError("opened partition boundary ticker changed")
    if len(set(tickers)) != len(tickers):
        raise StopCandidateError("opened partition contains a duplicate ticker")
    return selected


@dataclass(frozen=True)
class CandidatePolicy:
    key: str
    label: str
    family: str
    threshold: Decimal | None = None
    persistence_seconds: float = 0.0
    time_seconds_remaining: float | None = None
    stress_multiple: Decimal | None = None


@dataclass
class SignalState:
    breach_started_at: datetime | None = None
    hysteresis_armed_at: datetime | None = None


POLICIES: tuple[CandidatePolicy, ...] = (
    CandidatePolicy("baseline_no_stop", "Baseline: 10s fallback", "baseline"),
    CandidatePolicy("fixed_2", "Fixed stop -$2", "fixed", Decimal("2")),
    CandidatePolicy("fixed_5", "Fixed stop -$5", "fixed", Decimal("5")),
    CandidatePolicy("fixed_10", "Fixed stop -$10", "fixed", Decimal("10")),
    CandidatePolicy("fixed_15", "Fixed stop -$15", "fixed", Decimal("15")),
    CandidatePolicy("fixed_20", "Fixed stop -$20", "fixed", Decimal("20")),
    CandidatePolicy("fallback_90s", "No-target cash exit at 90s", "time", time_seconds_remaining=90),
    CandidatePolicy("fallback_60s", "No-target cash exit at 60s", "time", time_seconds_remaining=60),
    CandidatePolicy("fallback_30s", "No-target cash exit at 30s", "time", time_seconds_remaining=30),
    CandidatePolicy(
        "persistent_15_5s", "Persistent -$15 for 5s", "persistent",
        Decimal("15"), persistence_seconds=5,
    ),
    CandidatePolicy(
        "persistent_20_5s", "Persistent -$20 for 5s", "persistent",
        Decimal("20"), persistence_seconds=5,
    ),
    CandidatePolicy(
        "hysteresis_10_20_5", "Arm -$10; stop -$20; reset above -$5", "hysteresis"
    ),
    CandidatePolicy(
        "late_loss_ladder", "90s: -$10; 60s: below $0", "late_loss"
    ),
    CandidatePolicy("lost_full_depth", "Exit on lost full depth", "lost_depth"),
    CandidatePolicy(
        "depth_buffer_125", "-$10 plus <125% depth buffer", "depth_buffer",
        Decimal("10"), stress_multiple=Decimal("1.25"),
    ),
    CandidatePolicy(
        "depth_buffer_150", "-$10 plus <150% depth buffer", "depth_buffer",
        Decimal("10"), stress_multiple=Decimal("1.50"),
    ),
)


def _policy(key: str) -> CandidatePolicy:
    try:
        return next(policy for policy in POLICIES if policy.key == key)
    except StopIteration as exc:
        raise StopCandidateError(f"unknown stop policy: {key}") from exc


def _whole_contracts(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_CEILING)


def candidate_signal(
    *,
    policy: CandidatePolicy,
    state: SignalState,
    observed_at: datetime,
    seconds_remaining: float,
    full_depth: bool,
    executable_pnl: Decimal | None,
    stress_coverage: Decimal | None,
) -> tuple[bool, str]:
    """Advance causal signal state and return (signal, reason)."""

    if policy.family == "baseline":
        return False, ""
    if policy.family == "fixed":
        signal = (
            full_depth and executable_pnl is not None and policy.threshold is not None
            and executable_pnl <= -policy.threshold
        )
        return signal, "fixed_loss_threshold" if signal else ""
    if policy.family == "time":
        assert policy.time_seconds_remaining is not None
        signal = seconds_remaining <= policy.time_seconds_remaining
        return signal, "no_target_time_exit" if signal else ""
    if policy.family == "persistent":
        assert policy.threshold is not None
        breached = (
            full_depth and executable_pnl is not None
            and executable_pnl <= -policy.threshold
        )
        if breached:
            if state.breach_started_at is None:
                state.breach_started_at = observed_at
            elapsed = (observed_at - state.breach_started_at).total_seconds()
            if elapsed >= policy.persistence_seconds:
                return True, "persistent_loss_threshold"
        elif full_depth:
            state.breach_started_at = None
        elif state.breach_started_at is not None:
            elapsed = (observed_at - state.breach_started_at).total_seconds()
            if elapsed >= policy.persistence_seconds:
                return True, "persistent_breach_with_depth_loss"
        return False, ""
    if policy.family == "hysteresis":
        if not full_depth:
            return (
                state.hysteresis_armed_at is not None,
                "armed_deterioration_with_depth_loss"
                if state.hysteresis_armed_at is not None else "",
            )
        assert executable_pnl is not None
        if executable_pnl > Decimal("-5"):
            state.hysteresis_armed_at = None
            return False, ""
        previously_armed = state.hysteresis_armed_at is not None
        if executable_pnl <= Decimal("-10") and not previously_armed:
            state.hysteresis_armed_at = observed_at
        if previously_armed and executable_pnl <= Decimal("-20"):
            return True, "confirmed_deterioration"
        return False, ""
    if policy.family == "late_loss":
        if seconds_remaining <= 60:
            signal = not full_depth or (
                executable_pnl is not None and executable_pnl < 0
            )
            return signal, "late_nonrecovery_60s" if signal else ""
        if seconds_remaining <= 90:
            signal = (
                full_depth and executable_pnl is not None
                and executable_pnl <= Decimal("-10")
            )
            return signal, "late_deep_loss_90s" if signal else ""
        return False, ""
    if policy.family == "lost_depth":
        return (not full_depth, "lost_full_position_depth" if not full_depth else "")
    if policy.family == "depth_buffer":
        if not full_depth:
            return True, "lost_full_position_depth"
        signal = (
            executable_pnl is not None and policy.threshold is not None
            and executable_pnl <= -policy.threshold
            and stress_coverage is not None and policy.stress_multiple is not None
            and stress_coverage < policy.stress_multiple
        )
        return signal, "thin_depth_after_loss" if signal else ""
    raise StopCandidateError(f"unsupported policy family: {policy.family}")


def _base_candidate_fields(policy: CandidatePolicy) -> dict[str, Any]:
    return {
        "candidate_policy": policy.key,
        "candidate_display_policy": policy.label,
        "candidate_family": policy.family,
        "candidate_stop_signal": False,
        "candidate_signal_reason": "",
        "candidate_signal_time": "",
        "candidate_signal_seconds_remaining": "",
        "candidate_signal_executable_pnl": "",
        "candidate_signal_liquidatable_fraction": "",
        "candidate_signal_stress_coverage": "",
        "candidate_progressive_attempts": 0,
        "candidate_progressive_fill_events": 0,
        "candidate_quantity_sold": "0",
        "candidate_remaining_at_settlement": "0",
        "candidate_fully_liquidated": False,
        "candidate_settlement_residual": False,
    }


def simulate_candidate_overlay(
    *,
    snapshots: Sequence[Snapshot],
    close_time: datetime,
    winning_side: str,
    baseline: Mapping[str, Any],
    entry_context: tuple[int, int, str, Decimal, Decimal, Any],
    policy: CandidatePolicy,
) -> dict[str, Any]:
    """Interleave the protected target with one causal full-position risk exit."""

    row = dict(baseline)
    row.update(_base_candidate_fields(policy))
    if policy.family == "baseline":
        return row

    _decision_index, entry_index, side, _midpoint, _ask, entry = entry_context
    target = (entry.quantity - entry.buy_outflow) * TARGET_FRACTION
    preclose = close_time - timedelta(seconds=PRECLOSE_EXIT_SECONDS)
    state = SignalState()
    index = entry_index + 1
    target_signals = 0
    target_rejections = 0

    while index < len(snapshots):
        observed = snapshots[index]
        if observed.observed_at >= preclose:
            break
        attempted = sell_quantity(observed.book.bid_levels(side), entry.quantity)
        full = attempted.quantity == entry.quantity
        observed_pnl = attempted.sell_inflow - entry.buy_outflow if full else None

        # The frozen protected target always wins at a shared observation.
        if full and observed_pnl is not None and observed_pnl >= target:
            target_signals += 1
            delayed_index = first_index_at_or_after(
                snapshots,
                index + 1,
                observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
            )
            if delayed_index is None or snapshots[delayed_index].observed_at >= preclose:
                break
            executed = sell_quantity(
                snapshots[delayed_index].book.bid_levels(side), entry.quantity
            )
            if (
                executed.quantity == entry.quantity
                and executed.sell_inflow - entry.buy_outflow >= target
            ):
                return row
            target_rejections += 1
            index = delayed_index + 1
            continue

        stress_coverage: Decimal | None = None
        if policy.stress_multiple is not None:
            stress_quantity = _whole_contracts(entry.quantity * policy.stress_multiple)
            stressed = sell_quantity(observed.book.bid_levels(side), stress_quantity)
            stress_coverage = stressed.quantity / entry.quantity

        signal, reason = candidate_signal(
            policy=policy,
            state=state,
            observed_at=observed.observed_at,
            seconds_remaining=(close_time - observed.observed_at).total_seconds(),
            full_depth=full,
            executable_pnl=observed_pnl,
            stress_coverage=stress_coverage,
        )
        if not signal:
            index += 1
            continue

        result = progressive_liquidation(
            snapshots=snapshots,
            signal_index=index,
            close_time=close_time,
            side=side,
            quantity=entry.quantity,
            outflow=entry.buy_outflow,
            winning_side=winning_side,
        )
        exit_time = result.last_execution_time or close_time
        if result.settled_residual:
            exit_time = close_time
        row.update({
            "candidate_stop_signal": True,
            "candidate_signal_reason": reason,
            "candidate_signal_time": observed.observed_at.isoformat(),
            "candidate_signal_seconds_remaining": (
                close_time - observed.observed_at
            ).total_seconds(),
            "candidate_signal_executable_pnl": (
                "" if observed_pnl is None else _decimal_text(observed_pnl)
            ),
            "candidate_signal_liquidatable_fraction": float(
                attempted.quantity / entry.quantity
            ),
            "candidate_signal_stress_coverage": (
                "" if stress_coverage is None else float(stress_coverage)
            ),
            "target_filled": False,
            "target_signal_count": target_signals,
            "target_rejected_after_latency_count": target_rejections,
            "fallback_used": False,
            "exit_reason": (
                "candidate_progressive_exit_with_settlement_residual"
                if result.settled_residual else "candidate_progressive_exit"
            ),
            "exit_execution_time": exit_time.isoformat(),
            "exit_gross": _decimal_text(result.gross),
            "exit_fee": _decimal_text(result.fee),
            "exit_average_price": _decimal_text(result.gross / entry.quantity),
            "pnl": _decimal_text(result.pnl),
            "profitable": result.pnl > 0,
            "full_capital_loss": result.pnl <= -FULL_LOSS_FRACTION * entry.buy_outflow,
            "candidate_progressive_attempts": result.attempts,
            "candidate_progressive_fill_events": result.fill_events,
            "candidate_quantity_sold": _decimal_text(result.quantity_sold),
            "candidate_remaining_at_settlement": _decimal_text(result.remaining_quantity),
            "candidate_fully_liquidated": result.remaining_quantity == 0,
            "candidate_settlement_residual": result.settled_residual,
            "exposure_seconds": (
                f"{(exit_time - snapshots[entry_index].observed_at).total_seconds():.6f}"
            ),
        })
        return row
    return row


def load_opened_holdout_outcomes(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != EXPECTED_HOLDOUT_MARKETS:
        raise StopCandidateError(
            f"expected {EXPECTED_HOLDOUT_MARKETS} opened outcomes; found {len(rows)}"
        )
    output: dict[str, str] = {}
    for row in rows:
        ticker = str(row.get("ticker", ""))
        side = str(row.get("winning_side", row.get("result", ""))).upper()
        if not ticker or side not in {"YES", "NO"} or ticker in output:
            raise StopCandidateError("opened outcome file has an invalid or duplicate row")
        output[ticker] = side
    return output


def load_opened_baseline(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != EXPECTED_HOLDOUT_MARKETS:
        raise StopCandidateError(
            f"expected {EXPECTED_HOLDOUT_MARKETS} opened baseline rows; found {len(rows)}"
        )
    output = {str(row.get("ticker", "")): row for row in rows}
    if len(output) != len(rows) or "" in output:
        raise StopCandidateError("opened baseline file has an invalid or duplicate ticker")
    return output


def _normalize_csv_value(field: str, value: Any) -> str:
    text = "" if value is None else str(value)
    if field == "pnl" and text:
        return _decimal_text(Decimal(text))
    if field in {"triggered", "entry_filled"}:
        return text.lower()
    return text


def verify_opened_baseline_row(
    reproduced: Mapping[str, Any], frozen: Mapping[str, Any]
) -> None:
    fields = (
        "status", "triggered", "entry_filled", "decision_time",
        "entry_execution_time", "exit_reason", "exit_execution_time", "pnl",
    )
    mismatches = [
        field for field in fields
        if _normalize_csv_value(field, reproduced.get(field))
        != _normalize_csv_value(field, frozen.get(field))
    ]
    if mismatches:
        raise StopCandidateError(
            f"{reproduced.get('ticker')}: opened baseline reproduction mismatch: {mismatches}"
        )


def _group_rows(
    rows: Sequence[Mapping[str, Any]], group: str
) -> list[Mapping[str, Any]]:
    if group == "combined_122":
        return list(rows)
    if group == "development_96":
        return [row for row in rows if row["evidence_partition"] == "development_96"]
    if group == "opened_26":
        return [row for row in rows if row["evidence_partition"] == "opened_26"]
    if group == "earlier_64_diagnostic":
        return [row for row in rows if row["diagnostic_segment"] == "earlier_64"]
    if group == "later_32_diagnostic":
        return [row for row in rows if row["diagnostic_segment"] == "later_32"]
    raise StopCandidateError(f"unknown summary group: {group}")


def summarize_candidates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for group in (
        "development_96", "opened_26", "combined_122",
        "earlier_64_diagnostic", "later_32_diagnostic",
    ):
        source = _group_rows(rows, group)
        baseline = {
            str(row["ticker"]): float(row["pnl"] or 0.0)
            for row in source if row["candidate_policy"] == "baseline_no_stop"
        }
        baseline_winners = {ticker for ticker, pnl in baseline.items() if pnl > 0}
        baseline_losers = {ticker for ticker, pnl in baseline.items() if pnl < 0}
        for policy in POLICIES:
            selected = [row for row in source if row["candidate_policy"] == policy.key]
            completed = [row for row in selected if row["status"] == "completed"]
            pnl_market = [float(row["pnl"] or 0.0) for row in selected]
            pnl_filled = [float(row["pnl"]) for row in completed]
            differences = [
                float(row["pnl"] or 0.0) - baseline[str(row["ticker"])]
                for row in selected
            ]
            loser_rows = [row for row in completed if row["ticker"] in baseline_losers]
            winner_rows = [row for row in completed if row["ticker"] in baseline_winners]
            loser_savings = sum(
                float(row["pnl"]) - baseline[str(row["ticker"])] for row in loser_rows
            )
            winner_net = sum(
                float(row["pnl"]) - baseline[str(row["ticker"])] for row in winner_rows
            )
            winner_cost = sum(
                max(0.0, baseline[str(row["ticker"])] - float(row["pnl"]))
                for row in winner_rows
            )
            stopped = [row for row in completed if bool(row["candidate_stop_signal"])]
            mean_market, ci_low, ci_high = _bootstrap(pnl_market)
            diff_mean, diff_low, diff_high = _bootstrap(differences)
            fully_liquidated = all(
                bool(row["candidate_fully_liquidated"]) for row in stopped
            ) if stopped else False
            full_losses = sum(bool(row["full_capital_loss"]) for row in completed)
            stopped_losers = sum(
                bool(row["candidate_stop_signal"]) for row in loser_rows
            )
            cost_share = winner_cost / loser_savings if loser_savings > 0 else math.inf
            strong = (
                group == "combined_122"
                and policy.family != "baseline"
                and stopped_losers >= 1
                and loser_savings >= MATERIAL_LOSER_SAVINGS
                and sum(differences) > 0
                and cost_share <= MAX_WINNER_COST_SHARE
                and full_losses == 0
                and fully_liquidated
            )
            output.append({
                "group": group,
                "candidate_policy": policy.key,
                "display_policy": policy.label,
                "candidate_family": policy.family,
                "eligible_markets": len(selected),
                "entry_filled_markets": len(completed),
                "baseline_winning_entries": len(baseline_winners),
                "baseline_losing_entries": len(baseline_losers),
                "stop_signals": len(stopped),
                "stopped_baseline_winners": sum(
                    bool(row["candidate_stop_signal"]) for row in winner_rows
                ),
                "stopped_baseline_losers": stopped_losers,
                "total_pnl": sum(pnl_market),
                "mean_pnl_per_eligible_market": mean_market,
                "bootstrap_ci_low_per_eligible_market": ci_low,
                "bootstrap_ci_high_per_eligible_market": ci_high,
                "total_paired_difference_vs_baseline": sum(differences),
                "mean_paired_difference_vs_baseline": diff_mean,
                "paired_difference_ci_low": diff_low,
                "paired_difference_ci_high": diff_high,
                "mean_pnl_per_filled_entry": _mean(pnl_filled),
                "profitable_rate_per_filled_entry": _mean(
                    [bool(row["profitable"]) for row in completed]
                ),
                "loser_savings_vs_baseline": loser_savings,
                "winner_net_impact_vs_baseline": winner_net,
                "winner_gross_opportunity_cost": winner_cost,
                "winner_cost_share_of_loser_savings": cost_share,
                "all_signaled_positions_fully_liquidated": fully_liquidated,
                "settlement_residuals": sum(
                    bool(row["candidate_settlement_residual"]) for row in stopped
                ),
                "full_capital_losses": full_losses,
                "pnl_05_quantile_per_filled_entry": _quantile(pnl_filled, 0.05),
                "worst_pnl_per_filled_entry": min(pnl_filled) if pnl_filled else math.nan,
                "strong_standalone_screen": strong,
                "adaptive_development_only": True,
                "external_btc_data_used": False,
                "authentication_used": False,
                "orders_placed": 0,
            })
    return output


def verify_results(
    rows: Sequence[Mapping[str, Any]], summaries: Sequence[Mapping[str, Any]]
) -> None:
    expected = EXPECTED_TOTAL_MARKETS * len(POLICIES)
    if len(rows) != expected:
        raise StopCandidateError(f"expected {expected} scenario rows; found {len(rows)}")
    lookup = {(row["group"], row["candidate_policy"]): row for row in summaries}
    development = lookup[("development_96", "baseline_no_stop")]
    opened = lookup[("opened_26", "baseline_no_stop")]
    combined = lookup[("combined_122", "baseline_no_stop")]
    if int(development["entry_filled_markets"]) != EXPECTED_NATIVE_ENTRIES:
        raise StopCandidateError("development baseline did not reproduce 57 entries")
    if abs(float(development["mean_pnl_per_eligible_market"]) - 2.32) > 0.01:
        raise StopCandidateError("development baseline mean no longer reproduces H3")
    if int(development["full_capital_losses"]) != 0:
        raise StopCandidateError("development baseline unexpectedly contains a full loss")
    if int(opened["entry_filled_markets"]) != EXPECTED_HOLDOUT_ENTRIES:
        raise StopCandidateError("opened baseline did not reproduce 14 entries")
    if abs(float(opened["total_pnl"]) - EXPECTED_HOLDOUT_TOTAL_PNL) > 0.02:
        raise StopCandidateError("opened baseline total P&L no longer reproduces -$46.55")
    if int(opened["full_capital_losses"]) != 1:
        raise StopCandidateError("opened baseline did not reproduce one full loss")
    if int(combined["entry_filled_markets"]) != EXPECTED_TOTAL_ENTRIES:
        raise StopCandidateError("combined baseline did not reproduce 71 entries")


def _optional_money(value: Any) -> str:
    """Format a diagnostic amount whose absence is represented by an empty cell."""

    if value is None or str(value) == "":
        return "n/a"
    return _money(value)


def markdown_report(
    rows: Sequence[Mapping[str, Any]], summaries: Sequence[Mapping[str, Any]]
) -> str:
    combined = [row for row in summaries if row["group"] == "combined_122"]
    opened_lookup = {
        row["candidate_policy"]: row for row in summaries if row["group"] == "opened_26"
    }
    development_lookup = {
        row["candidate_policy"]: row
        for row in summaries if row["group"] == "development_96"
    }
    baseline_loss_tickers = {
        str(row["ticker"])
        for row in rows
        if row["candidate_policy"] == "baseline_no_stop"
        and row["status"] == "completed" and float(row["pnl"]) < 0
    }
    loser_rows = [
        row for row in rows
        if row["candidate_policy"] != "baseline_no_stop"
        and row["ticker"] in baseline_loss_tickers
    ]
    strong = [row for row in combined if bool(row["strong_standalone_screen"])]
    lines = [
        "# KXBTC15M H3 opened-evidence stop-candidate diagnostic",
        "",
        "**Adaptive hypothesis-generation test; all 122 markets are development evidence.**",
        "",
        "The frozen causal-native H3 entry and protected 50%-of-maximum target are reproduced "
        "on the original 96 markets and the permanently opened 26 markets before any overlay "
        "is evaluated. Candidate exits use only causally received native responses, archived "
        "full depth, fees, one-second latency, and progressive liquidation. No candidate is a "
        "validated H3 v2 rule.",
        "",
        "## Standalone policy surface",
        "",
        "| Policy | Stops | Winners stopped | Loser stopped | Dev-96 delta | Opened-26 P&L | Opened delta | Combined P&L | Combined delta | Loser saved | Winner cost | Full losses | Fully liquidated | Strong screen |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in combined:
        dev = development_lookup[str(row["candidate_policy"])]
        opened = opened_lookup[str(row["candidate_policy"])]
        lines.append(
            f"| {row['display_policy']} | {row['stop_signals']} | "
            f"{row['stopped_baseline_winners']} | {row['stopped_baseline_losers']} | "
            f"{_money(dev['total_paired_difference_vs_baseline'])} | "
            f"{_money(opened['total_pnl'])} | "
            f"{_money(opened['total_paired_difference_vs_baseline'])} | "
            f"{_money(row['total_pnl'])} | "
            f"{_money(row['total_paired_difference_vs_baseline'])} | "
            f"{_money(row['loser_savings_vs_baseline'])} | "
            f"{_money(row['winner_gross_opportunity_cost'])} | "
            f"{row['full_capital_losses']} | "
            f"{row['all_signaled_positions_fully_liquidated']} | "
            f"{row['strong_standalone_screen']} |"
        )
    lines.extend([
        "",
        "Winner cost is the gross profit sacrificed across baseline-winning entries; loser "
        "savings is the change on baseline-losing entries. No-trade markets remain $0.",
        "",
        "## Known-loss execution",
        "",
        "| Policy | Signaled | Reason | Signal sec left | Signal executable P&L | Result P&L | Saved vs baseline | Fully liquidated | Residual settlement |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ])
    baseline_loss = next(
        row for row in rows
        if row["candidate_policy"] == "baseline_no_stop"
        and row["ticker"] in baseline_loss_tickers
    )
    for row in loser_rows:
        lines.append(
            f"| {row['candidate_display_policy']} | {row['candidate_stop_signal']} | "
            f"{row['candidate_signal_reason'] or 'n/a'} | "
            f"{row['candidate_signal_seconds_remaining'] or 'n/a'} | "
            f"{_optional_money(row['candidate_signal_executable_pnl'])} | "
            f"{_money(row['pnl'])} | "
            f"{_money(float(row['pnl']) - float(baseline_loss['pnl']))} | "
            f"{row['candidate_fully_liquidated']} | "
            f"{row['candidate_settlement_residual']} |"
        )
    lines.extend([
        "",
        "## Evidence screen",
        "",
        "A standalone candidate is marked strong only if it stops the known loser, saves at "
        f"least {_money(MATERIAL_LOSER_SAVINGS)}, improves combined total P&L, limits gross "
        f"winner opportunity cost to at most {_percent(MAX_WINNER_COST_SHARE)} of loser savings, "
        "creates zero full-capital losses, and fully liquidates every signaled position.",
        "",
        "Strong standalone candidates: "
        + (", ".join(f"`{row['candidate_policy']}`" for row in strong) if strong else "none"),
        "",
        "This screen is intentionally permissive enough to decide whether fresh collection is "
        "worthwhile; it is not a selection or validation gate. If two simple families remain "
        "strong across nearby settings, one causal hybrid may be defined afterward with explicit "
        "signal priority and tested on these opened data only as a final development candidate. "
        "Any chosen H3 v2 policy still requires a newly collected chronological confirmation "
        "sample. No external BTC data, authentication, or orders are used.",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_zip", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--development-outcomes-csv", type=Path, required=True)
    parser.add_argument("--opened-holdout-outcomes-csv", type=Path, required=True)
    parser.add_argument("--opened-holdout-scenarios-csv", type=Path, required=True)
    parser.add_argument("--series-csv", type=Path, required=True)
    parser.add_argument("--fee-changes-csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("analysis/kxbtc15m_h3_stop_candidates"),
    )
    return parser.parse_args()


def _market_partition(
    markets: Sequence[DevelopmentMarket], partition: str
) -> list[tuple[DevelopmentMarket, str, str]]:
    output: list[tuple[DevelopmentMarket, str, str]] = []
    for market in markets:
        if partition == "development_96":
            segment = "earlier_64" if market.index <= 64 else "later_32"
        else:
            segment = "opened_26"
        output.append((market, partition, segment))
    return output


def main() -> None:
    args = parse_args()
    development_outcomes = load_outcomes(args.development_outcomes_csv)
    opened_outcomes = load_opened_holdout_outcomes(args.opened_holdout_outcomes_csv)
    opened_baseline = load_opened_baseline(args.opened_holdout_scenarios_csv)
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    scenario_rows: list[dict[str, Any]] = []

    with TemporaryDirectory(prefix="kxbtc15m_h3_stop_candidates_") as temporary:
        audit_root = Path(temporary)
        safe_extract_zip(args.audit_zip, audit_root)
        dev_manifests = select_development_manifests(audit_root)
        dev_all = [
            assess_market(index, manifest, audit_root)
            for index, manifest in enumerate(dev_manifests, start=1)
        ]
        dev_markets = [market for market in dev_all if market.eligible]
        if len(dev_markets) != EXPECTED_ELIGIBLE_MARKETS:
            raise StopCandidateError(
                f"expected {EXPECTED_ELIGIBLE_MARKETS} eligible development markets; "
                f"found {len(dev_markets)}"
            )
        holdout_manifests = select_opened_manifests(audit_root)
        holdout_markets = [
            assess_market(index, manifest, audit_root)
            for index, manifest in enumerate(holdout_manifests, start=101)
        ]
        if len(holdout_markets) != EXPECTED_HOLDOUT_MARKETS or any(
            not market.eligible for market in holdout_markets
        ):
            raise StopCandidateError("opened 26-market partition failed its frozen quality gate")
        if set(development_outcomes) != {market.ticker for market in dev_markets}:
            raise StopCandidateError("development outcomes do not match eligible markets")
        if set(opened_outcomes) != {market.ticker for market in holdout_markets}:
            raise StopCandidateError("opened outcomes do not match the opened partition")
        if set(opened_baseline) != {market.ticker for market in holdout_markets}:
            raise StopCandidateError("opened baseline rows do not match the opened partition")

        work = (
            _market_partition(dev_markets, "development_96")
            + _market_partition(holdout_markets, "opened_26")
        )
        for number, (market, partition, segment) in enumerate(work, start=1):
            outcomes = development_outcomes if partition == "development_96" else opened_outcomes
            _legacy, snapshots = _raw_snapshot_sets(market, args.repo_root)
            close = market_close_utc(market.ticker)
            context = find_native_entry(snapshots, close)
            baseline = simulate_policy(
                snapshots=snapshots,
                close_time=close,
                winning_side=outcomes[market.ticker],
                ticker=market.ticker,
                segment=segment,
                policy=BASELINE_POLICY,
                kind="fraction",
                value=TARGET_FRACTION,
                entry_context=context,
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
            verify_baseline_reproduction(baseline, frequency)
            if partition == "opened_26":
                verify_opened_baseline_row(baseline, opened_baseline[market.ticker])
            baseline.update({
                "market_index": market.index,
                "evidence_partition": partition,
                "diagnostic_segment": segment,
                "baseline_pnl": baseline["pnl"],
                "adaptive_development_only": True,
                "external_btc_data_used": False,
                "authentication_used": False,
                "orders_placed": 0,
            })
            for policy in POLICIES:
                if baseline["status"] != "completed":
                    row = dict(baseline)
                    row.update(_base_candidate_fields(policy))
                else:
                    if context is None:
                        raise StopCandidateError(
                            f"{market.ticker}: completed baseline lacks entry context"
                        )
                    row = simulate_candidate_overlay(
                        snapshots=snapshots,
                        close_time=close,
                        winning_side=outcomes[market.ticker],
                        baseline=baseline,
                        entry_context=context,
                        policy=policy,
                    )
                row.update({
                    "market_index": market.index,
                    "evidence_partition": partition,
                    "diagnostic_segment": segment,
                    "baseline_pnl": baseline["pnl"],
                    "pnl_difference_vs_baseline": (
                        float(row["pnl"] or 0.0) - float(baseline["pnl"] or 0.0)
                    ),
                    "adaptive_development_only": True,
                    "external_btc_data_used": False,
                    "authentication_used": False,
                    "orders_placed": 0,
                })
                scenario_rows.append(row)
            print(f"[{number:03d}/{len(work)}] {market.ticker}")

    # Preserve the expensive market-by-policy replay before summary formatting.
    # This also leaves an auditable checkpoint if a later reporting invariant fails.
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = args.output_dir / "kxbtc15m_h3_stop_candidate_scenarios.csv"
    write_csv(scenario_path, scenario_rows)

    summaries = summarize_candidates(scenario_rows)
    verify_results(scenario_rows, summaries)
    strong = [
        row for row in summaries
        if row["group"] == "combined_122" and bool(row["strong_standalone_screen"])
    ]
    screen_rows = [
        row for row in summaries
        if row["group"] == "combined_122" and row["candidate_family"] != "baseline"
    ]
    summary_path = args.output_dir / "kxbtc15m_h3_stop_candidate_summary.csv"
    strong_path = args.output_dir / "kxbtc15m_h3_stop_candidate_strong_screen.csv"
    report_path = args.output_dir / "KXBTC15M_H3_STOP_CANDIDATES.md"
    write_csv(summary_path, summaries)
    write_csv(strong_path, screen_rows)
    report_path.write_text(markdown_report(scenario_rows, summaries), encoding="utf-8")

    print("KXBTC15M H3 opened-evidence stop-candidate diagnostic: PASS")
    print(f"Eligible markets: {EXPECTED_TOTAL_MARKETS}")
    print(f"Baseline entries: {EXPECTED_TOTAL_ENTRIES}")
    print(f"Standalone policies: {len(POLICIES)}")
    print(f"Strong standalone screens: {len(strong)}")
    print("Hybrid selected: no")
    print("Fresh validation performed: no")
    print("Authentication used: no")
    print("Orders placed: 0")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, StopCandidateError, OSError, ValueError) as exc:
        raise SystemExit(f"KXBTC15M H3 stop-candidate error: {exc}") from exc
