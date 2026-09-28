from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_early_persistence import (
    BASELINE,
    HISTORICAL_CONTROL,
    EarlyPersistenceError,
    _policy_name,
    find_persistent_entry,
    selection_table,
    simulate_market_policies,
    summarize,
)
from audit_kxbtc15m_raw_depth import ParsedBook


UTC = timezone.utc
OPEN = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
CLOSE = OPEN + timedelta(seconds=900)
TICKER = "KXBTC15M-26AUG131515-15"


def book(yes_bid: str, yes_ask: str) -> ParsedBook:
    return ParsedBook(
        yes_levels=((Decimal(yes_bid), Decimal("1000")),),
        no_levels=((Decimal("1") - Decimal(yes_ask), Decimal("1000")),),
    )


def snapshot(elapsed: float, yes_bid: str, yes_ask: str) -> Snapshot:
    return Snapshot(
        observed_at=OPEN + timedelta(seconds=elapsed),
        request_id=str(elapsed),
        book=book(yes_bid, yes_ask),
    )


def test_zero_seconds_triggers_immediately_then_uses_one_second_fill():
    snapshots = [
        snapshot(450.0, "0.90", "0.92"),
        snapshot(451.1, "0.90", "0.92"),
    ]
    context, diagnostics = find_persistent_entry(
        snapshots, close_time=CLOSE, threshold_seconds=0
    )
    assert context is not None
    assert context[0] == 0
    assert context[1] == 1
    assert diagnostics["confirmation_observations"] == 1
    assert diagnostics["confirmation_elapsed_seconds"] == "0.000000"


def test_one_second_requires_uninterrupted_same_side_native_observations():
    snapshots = [
        snapshot(450.0, "0.90", "0.92"),
        snapshot(450.5, "0.90", "0.92"),
        snapshot(451.1, "0.90", "0.92"),
        snapshot(452.2, "0.90", "0.92"),
    ]
    context, diagnostics = find_persistent_entry(
        snapshots, close_time=CLOSE, threshold_seconds=1
    )
    assert context is not None
    assert context[0] == 2
    assert context[1] == 3
    assert diagnostics["confirmation_observations"] == 3
    assert diagnostics["confirmation_elapsed_seconds"] == "1.100000"


def test_out_of_band_response_resets_elapsed_confirmation():
    snapshots = [
        snapshot(450.0, "0.90", "0.92"),
        snapshot(450.7, "0.98", "0.99"),
        snapshot(451.0, "0.90", "0.92"),
        snapshot(452.1, "0.90", "0.92"),
        snapshot(453.2, "0.90", "0.92"),
    ]
    context, diagnostics = find_persistent_entry(
        snapshots, close_time=CLOSE, threshold_seconds=1
    )
    assert context is not None
    assert context[0] == 3
    assert context[1] == 4
    assert diagnostics["episode_resets"] == 1
    assert diagnostics["episodes_armed"] == 2


def test_favored_side_change_resets_and_arms_new_qualifying_side():
    snapshots = [
        snapshot(450.0, "0.90", "0.92"),
        snapshot(450.7, "0.08", "0.10"),
        snapshot(451.8, "0.08", "0.10"),
        snapshot(452.9, "0.08", "0.10"),
    ]
    context, diagnostics = find_persistent_entry(
        snapshots, close_time=CLOSE, threshold_seconds=1
    )
    assert context is not None
    assert context[0] == 2
    assert context[1] == 3
    assert context[2] == "NO"
    assert diagnostics["episode_resets"] == 1


def test_fill_must_execute_strictly_before_five_minute_boundary():
    snapshots = [
        snapshot(598.5, "0.90", "0.92"),
        snapshot(600.0, "0.90", "0.92"),
    ]
    context, diagnostics = find_persistent_entry(
        snapshots, close_time=CLOSE, threshold_seconds=0
    )
    assert context is None
    assert diagnostics["entry_rejected_after_cutoff"] is True


def test_historical_control_allows_fill_to_cross_five_minute_boundary():
    snapshots = [
        snapshot(598.5, "0.90", "0.92"),
        snapshot(600.0, "0.90", "0.92"),
    ]
    context, diagnostics = find_persistent_entry(
        snapshots,
        close_time=CLOSE,
        threshold_seconds=0,
        require_fill_before_boundary=False,
    )
    assert context is not None
    assert context[0] == 0
    assert context[1] == 1
    assert diagnostics["entry_crossed_5m_boundary"] is True
    assert diagnostics["strict_fill_before_5m"] is False


def test_undeclared_threshold_fails_closed():
    with pytest.raises(EarlyPersistenceError):
        find_persistent_entry([], close_time=CLOSE, threshold_seconds=3)


def test_combined_policy_uses_early_entry_else_baseline_without_second_cycle():
    early_path = [
        snapshot(450.0, "0.90", "0.92"),
        snapshot(451.1, "0.90", "0.92"),
        snapshot(455.0, "0.98", "0.99"),
        snapshot(456.1, "0.98", "0.99"),
        snapshot(600.0, "0.90", "0.92"),
        snapshot(601.1, "0.90", "0.92"),
    ]
    rows, _baseline, _immediate = simulate_market_policies(
        snapshots=early_path,
        close_time=CLOSE,
        winning_side="YES",
        ticker=TICKER,
        segment="earlier_64",
    )
    combined = next(
        row for row in rows if row["policy"] == _policy_name(0, True)
    )
    assert combined["entry_source"] == "early_5_7_5m"
    assert combined["maximum_cycles"] == 1

    baseline_only_path = [
        snapshot(600.0, "0.90", "0.92"),
        snapshot(601.1, "0.90", "0.92"),
        snapshot(605.0, "0.98", "0.99"),
        snapshot(606.1, "0.98", "0.99"),
    ]
    rows, _baseline, _immediate = simulate_market_policies(
        snapshots=baseline_only_path,
        close_time=CLOSE,
        winning_side="YES",
        ticker=TICKER,
        segment="earlier_64",
    )
    combined = next(
        row for row in rows if row["policy"] == _policy_name(0, True)
    )
    assert combined["entry_source"] == "fallback_4_5m"
    assert combined["maximum_cycles"] == 1


def _summary_rows(differences):
    rows = []
    for segment, diff in differences.items():
        for threshold in (0, 1, 2, 5):
            rows.append({
                "segment": segment,
                "policy": _policy_name(threshold, True),
                "full_loss_count": 0,
                "mean_paired_difference_vs_baseline": diff[threshold],
            })
    return rows


def test_selection_gate_chooses_shortest_threshold_passing_every_gate():
    summary = _summary_rows({
        "all_96": {0: -1, 1: 0.2, 2: 0.5, 5: 0.4},
        "earlier_64_diagnostic": {0: -1, 1: 0.1, 2: 0.3, 5: 0.2},
        "later_32_diagnostic": {0: -1, 1: 0.05, 2: 0.2, 5: 0.2},
    })
    result = selection_table(summary)
    selected = [row for row in result if row["selected_shortest_passing_threshold"]]
    assert len(selected) == 1
    assert selected[0]["persistence_threshold_seconds"] == 1


def test_selection_gate_rejects_full_loss_even_with_positive_means():
    summary = _summary_rows({
        "all_96": {0: -1, 1: 0.2, 2: 0.5, 5: 0.4},
        "earlier_64_diagnostic": {0: -1, 1: 0.1, 2: 0.3, 5: 0.2},
        "later_32_diagnostic": {0: -1, 1: 0.05, 2: 0.2, 5: 0.2},
    })
    next(
        row for row in summary
        if row["segment"] == "all_96" and row["policy"] == _policy_name(1, True)
    )["full_loss_count"] = 1
    result = selection_table(summary)
    selected = [row for row in result if row["selected_shortest_passing_threshold"]]
    assert selected[0]["persistence_threshold_seconds"] == 2


def test_summary_counts_no_trade_as_zero_and_combined_fallback_entry():
    rows = []
    policies = [BASELINE, HISTORICAL_CONTROL] + [
        _policy_name(threshold, combined)
        for combined in (False, True)
        for threshold in (0, 1, 2, 5)
    ]
    for ticker, pnl in ((TICKER, "4"), ("KXBTC15M-26AUG131530-30", "")):
        for policy in policies:
            completed = bool(pnl)
            rows.append({
                "ticker": ticker,
                "diagnostic_segment": "earlier_64",
                "policy": policy,
                "variant": "baseline" if policy == BASELINE else (
                    "historical_control" if policy == HISTORICAL_CONTROL else
                    "early_else_baseline" if policy.endswith("early_else_baseline")
                    else "early_only"
                ),
                "persistence_threshold_seconds": "" if policy == BASELINE else 0,
                "entry_source": (
                    "baseline_4_5m" if policy == BASELINE and completed else
                    "historical_early_5_7_5m" if policy == HISTORICAL_CONTROL and completed else
                    "fallback_4_5m" if policy.endswith("early_else_baseline") and completed else
                    "early_5_7_5m" if completed else "none"
                ),
                "status": "completed" if completed else "no_trigger",
                "pnl": pnl,
                "profitable": completed,
                "target_filled": completed,
                "favored_side_won": completed,
                "full_capital_loss": False,
                "seconds_remaining": "299" if completed else "",
                "persistent_signal_seen": completed,
            })
    result = summarize(rows)
    baseline = next(
        row for row in result
        if row["segment"] == "all_96" and row["policy"] == BASELINE
    )
    combined = next(
        row for row in result
        if row["segment"] == "all_96"
        and row["policy"] == _policy_name(0, True)
    )
    assert baseline["mean_pnl_per_eligible_market"] == 2
    assert combined["mean_pnl_per_eligible_market"] == 2
    assert combined["fallback_entries"] == 1
