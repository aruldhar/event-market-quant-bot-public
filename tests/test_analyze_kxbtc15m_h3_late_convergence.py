from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_late_convergence import (
    favored_quote,
    probability_band,
    remaining_time_band,
    simulate_h3_entry,
    summarize_core,
)
from audit_kxbtc15m_raw_depth import ParsedBook


def book(yes_bid: str, no_bid: str, quantity: str = "10000") -> ParsedBook:
    return ParsedBook(
        ((Decimal(yes_bid), Decimal(quantity)),),
        ((Decimal(no_bid), Decimal(quantity)),),
    )


def snapshots(values):
    start = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    return start, [
        Snapshot(start + timedelta(seconds=second), str(second), book(yes, no))
        for second, yes, no in values
    ]


def test_favored_quote_uses_midpoint_and_returns_executable_ask():
    side, mid, ask = favored_quote(book(".75", ".15"))
    assert side == "YES"
    assert mid == Decimal(".80")
    assert ask == Decimal(".85")


def test_favored_quote_rejects_midpoint_tie():
    assert favored_quote(book(".40", ".40")) is None


def test_probability_bands_have_stable_boundaries():
    assert probability_band(.7999) == "03_70_80c"
    assert probability_band(.80) == "04_80_90c"
    assert probability_band(.95) == "06_95_98c"
    assert probability_band(.98) == "07_98_100c"


def test_remaining_time_bands_have_stable_boundaries():
    assert remaining_time_band(121) == "03_120_180s"
    assert remaining_time_band(120) == "04_90_120s"
    assert remaining_time_band(60) == "06_30_60s"
    assert remaining_time_band(30) == "07_0_30s"


def test_target_exit_observes_one_second_execution_latency():
    start, values = snapshots([
        (0, ".75", ".15"),
        (1, ".75", ".15"),
        (2, ".90", ".05"),
        (3, ".91", ".04"),
    ])
    rows = simulate_h3_entry(
        snapshots=values,
        decision_index=0,
        close_time=start + timedelta(seconds=100),
        winning_side="YES",
    )
    target = next(row for row in rows if row["exit_policy"] == "target_or_settlement")
    assert target["exit_reason"] == "profit_target"
    assert target["exit_time"] == (start + timedelta(seconds=3)).isoformat()
    assert target["target_achieved_after_latency"] is True


def test_hold_policy_uses_finalized_outcome_not_future_entry_feature():
    start, values = snapshots([
        (0, ".75", ".15"),
        (1, ".75", ".15"),
    ])
    rows = simulate_h3_entry(
        snapshots=values,
        decision_index=0,
        close_time=start + timedelta(seconds=100),
        winning_side="NO",
    )
    hold = next(row for row in rows if row["exit_policy"] == "hold_to_settlement")
    assert hold["favored_side_won"] is False
    assert hold["pnl"] < 0
    assert hold["exit_reason"] == "settlement"


def test_preclose_policy_forces_executable_sale():
    start, values = snapshots([
        (0, ".75", ".15"),
        (1, ".75", ".15"),
        (90, ".70", ".20"),
        (91, ".70", ".20"),
    ])
    rows = simulate_h3_entry(
        snapshots=values,
        decision_index=0,
        close_time=start + timedelta(seconds=100),
        winning_side="YES",
    )
    forced = next(row for row in rows if row["exit_policy"] == "target_or_preclose_10s")
    assert forced["exit_reason"] == "preclose_time_exit"
    assert forced["exit_time"] == (start + timedelta(seconds=91)).isoformat()


def test_core_summary_keeps_chronological_segments_separate():
    base = {
        "status": "completed",
        "seconds_remaining": 100,
        "decision_favored_midpoint": .85,
        "pnl": 1.0,
        "profitable": True,
        "favored_side_won": True,
        "target_achieved_after_latency": True,
        "exit_reason": "profit_target",
        "total_fees": 1.0,
    }
    rows = []
    for policy in ("hold_to_settlement", "target_or_settlement", "target_or_preclose_10s"):
        rows.append({**base, "ticker": "A", "diagnostic_segment": "earlier_64", "exit_policy": policy})
        rows.append({**base, "ticker": "B", "diagnostic_segment": "later_32", "exit_policy": policy})
    summary = summarize_core(rows)
    assert len(summary) == 9
    later = [row for row in summary if row["segment"] == "later_32_diagnostic"]
    assert all(row["markets"] == 1 for row in later)
