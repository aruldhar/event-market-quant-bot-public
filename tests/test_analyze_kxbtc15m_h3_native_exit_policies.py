from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_frequency import simulate_market as simulate_frequency_market
from analyze_kxbtc15m_h3_native_exit_policies import (
    BASELINE_POLICY,
    POLICIES,
    find_native_entry,
    simulate_policy,
    summarize,
    verify_baseline_reproduction,
)
from audit_kxbtc15m_raw_depth import ParsedBook


UTC = timezone.utc
OPEN = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
CLOSE = OPEN + timedelta(seconds=900)
TICKER = "KXBTC15M-26AUG131515-15"


def book(yes_bid: str, yes_ask: str, quantity: str = "1000") -> ParsedBook:
    return ParsedBook(
        yes_levels=((Decimal(yes_bid), Decimal(quantity)),),
        no_levels=((Decimal("1") - Decimal(yes_ask), Decimal(quantity)),),
    )


def snapshot(
    elapsed: float, yes_bid: str = "0.91", yes_ask: str = "0.93",
    quantity: str = "1000",
) -> Snapshot:
    return Snapshot(
        observed_at=OPEN + timedelta(seconds=elapsed),
        request_id=str(elapsed),
        book=book(yes_bid, yes_ask, quantity),
    )


def test_native_entry_uses_first_eligible_causal_response_and_one_second_delay():
    snapshots = [
        snapshot(599.9, "0.85", "0.87"),
        snapshot(600.2, "0.85", "0.87"),
        snapshot(601.0, "0.90", "0.92"),
        snapshot(601.9, "0.91", "0.93"),
        snapshot(602.1, "0.92", "0.94"),
    ]
    context = find_native_entry(snapshots, CLOSE)
    assert context is not None
    decision_index, entry_index, side, midpoint, _ask, _entry = context
    assert decision_index == 2
    assert entry_index == 4
    assert side == "YES"
    assert midpoint == Decimal("0.91")


def test_no_native_entry_outside_frozen_window():
    snapshots = [
        snapshot(599.9, "0.90", "0.92"),
        snapshot(660.0, "0.90", "0.92"),
        snapshot(661.1, "0.90", "0.92"),
    ]
    assert find_native_entry(snapshots, CLOSE) is None


def test_lower_target_exits_earlier_while_all_use_same_entry():
    snapshots = [
        snapshot(600.0, "0.90", "0.92"),
        snapshot(601.1, "0.90", "0.92"),
        snapshot(602.0, "0.93", "0.94"),
        snapshot(603.1, "0.93", "0.94"),
        snapshot(604.0, "0.96", "0.97"),
        snapshot(605.1, "0.96", "0.97"),
    ]
    context = find_native_entry(snapshots, CLOSE)
    rows = {}
    for policy, _label, kind, value in POLICIES[:4]:
        rows[policy] = simulate_policy(
            snapshots=snapshots,
            close_time=CLOSE,
            winning_side="YES",
            ticker=TICKER,
            segment="earlier_64",
            policy=policy,
            kind=kind,
            value=value,
            entry_context=context,
        )
    assert rows["protected_25pct_max"]["entry_execution_time"] == rows[BASELINE_POLICY]["entry_execution_time"]
    assert rows["protected_25pct_max"]["exit_execution_time"] <= rows[BASELINE_POLICY]["exit_execution_time"]
    assert all(row["status"] == "completed" for row in rows.values())


def test_protected_50_percent_exactly_reproduces_frequency_scenario():
    snapshots = [
        snapshot(600.0, "0.90", "0.92"),
        snapshot(601.1, "0.90", "0.92"),
        snapshot(602.0, "0.96", "0.97"),
        snapshot(603.1, "0.96", "0.97"),
    ]
    context = find_native_entry(snapshots, CLOSE)
    baseline = simulate_policy(
        snapshots=snapshots,
        close_time=CLOSE,
        winning_side="YES",
        ticker=TICKER,
        segment="earlier_64",
        policy=BASELINE_POLICY,
        kind="fraction",
        value=Decimal("0.50"),
        entry_context=context,
    )
    frequency = simulate_frequency_market(
        snapshots=snapshots,
        close_time=CLOSE,
        winning_side="YES",
        ticker=TICKER,
        frequency="native",
        entry_mode="unprotected",
        clock_basis="causal_response_receipt",
        diagnostic_segment="earlier_64",
    )
    verify_baseline_reproduction(baseline, frequency)


def test_summary_counts_no_trigger_as_zero_and_pairs_by_market():
    rows = []
    for ticker, filled in ((TICKER, True), ("KXBTC15M-26AUG131530-30", False)):
        for policy, _label, _kind, _value in POLICIES:
            row = {
                "ticker": ticker,
                "diagnostic_segment": "earlier_64",
                "exit_policy": policy,
                "status": "completed" if filled else "no_trigger",
                "triggered": filled,
                "pnl": "4" if filled and policy == BASELINE_POLICY else (
                    "2" if filled else ""
                ),
            }
            if filled:
                row.update({
                    "profitable": True,
                    "target_filled": policy != "hold_to_settlement",
                    "fallback_used": False,
                    "exit_reason": "settlement" if policy == "hold_to_settlement" else "protected_profit_target",
                    "favored_side_won": True,
                    "full_capital_loss": False,
                    "exposure_seconds": "20",
                })
            rows.append(row)
    result = summarize(rows)
    baseline = next(
        row for row in result
        if row["segment"] == "all_96" and row["exit_policy"] == BASELINE_POLICY
    )
    fixed = next(
        row for row in result
        if row["segment"] == "all_96" and row["exit_policy"] == "protected_fixed_1usd"
    )
    assert baseline["mean_pnl_per_eligible_market"] == 2
    assert fixed["mean_pnl_per_eligible_market"] == 1
    assert fixed["mean_paired_difference_vs_protected_50pct"] == -1
