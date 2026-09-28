from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_frequency import monitoring_points, simulate_market, summarize
from audit_kxbtc15m_raw_depth import ParsedBook


UTC = timezone.utc
BASE = datetime(2026, 8, 13, 19, 10, tzinfo=UTC)
CLOSE = BASE + timedelta(seconds=300)


def book(yes_bid: str, yes_ask: str) -> ParsedBook:
    return ParsedBook(
        yes_levels=((Decimal(yes_bid), Decimal("1000")),),
        no_levels=((Decimal("1") - Decimal(yes_ask), Decimal("1000")),),
    )


def snapshot(seconds: float, yes_bid: str, yes_ask: str) -> Snapshot:
    return Snapshot(
        observed_at=BASE + timedelta(seconds=seconds),
        request_id=str(seconds),
        book=book(yes_bid, yes_ask),
    )


def simulate(snapshots, frequency="1s", mode="unprotected"):
    return simulate_market(
        snapshots=snapshots,
        close_time=CLOSE,
        winning_side="YES",
        ticker="KXBTC15M-26AUG131515-15",
        frequency=frequency,
        entry_mode=mode,
        clock_basis="causal_response_receipt",
        diagnostic_segment="earlier_64",
    )


def test_monitoring_schedule_counts_exact_window_anchors():
    snapshots = [snapshot(step / 2, "0.97", "0.98") for step in range(120)]
    assert len(monitoring_points(snapshots, CLOSE, "native")) == 120
    assert len(monitoring_points(snapshots, CLOSE, "1s")) == 60
    assert len(monitoring_points(snapshots, CLOSE, "2s")) == 30
    assert len(monitoring_points(snapshots, CLOSE, "5s")) == 12


def test_one_second_monitoring_catches_transient_that_five_seconds_misses():
    snapshots = [
        snapshot(0, "0.98", "0.99"),
        snapshot(1, "0.97", "0.98"),
        snapshot(2, "0.97", "0.98"),
        snapshot(3, "0.99", "1.00"),
        snapshot(4, "0.99", "1.00"),
        snapshot(5, "0.98", "0.99"),
    ]
    one_second = simulate(snapshots, "1s")
    five_second = simulate(snapshots, "5s")
    assert one_second["status"] == "completed"
    assert one_second["signal_origin"] == "above_98_to_band"
    assert five_second["status"] == "no_trigger"


def test_state_protection_rejects_stale_entry_then_resumes_monitoring():
    snapshots = [
        snapshot(0, "0.98", "0.99"),
        snapshot(1, "0.97", "0.98"),
        snapshot(2, "0.98", "0.99"),
        snapshot(3, "0.97", "0.98"),
        snapshot(4, "0.97", "0.98"),
        snapshot(5, "0.99", "1.00"),
        snapshot(6, "0.99", "1.00"),
    ]
    result = simulate(snapshots, "1s", "state_protected")
    assert result["status"] == "completed"
    assert result["decision_time"] == (BASE + timedelta(seconds=3)).isoformat()
    assert result["entry_execution_time"] == (BASE + timedelta(seconds=4)).isoformat()
    assert result["entry_rejected_after_latency_count"] == 1
    assert result["entry_signal_count"] == 2


def test_unprotected_entry_keeps_first_signal_despite_delayed_state_change():
    snapshots = [
        snapshot(0, "0.98", "0.99"),
        snapshot(1, "0.97", "0.98"),
        snapshot(2, "0.98", "0.99"),
        snapshot(3, "0.99", "1.00"),
        snapshot(4, "0.99", "1.00"),
    ]
    result = simulate(snapshots, "1s", "unprotected")
    assert result["status"] == "completed"
    assert result["decision_time"] == (BASE + timedelta(seconds=1)).isoformat()
    assert result["entry_execution_time"] == (BASE + timedelta(seconds=2)).isoformat()
    assert result["delayed_favored_midpoint"] == "0.985"


def test_summary_uses_zero_for_no_trade_market_in_primary_metric():
    completed = simulate([
        snapshot(0, "0.97", "0.98"),
        snapshot(1, "0.97", "0.98"),
        snapshot(2, "0.99", "1.00"),
        snapshot(3, "0.99", "1.00"),
    ], "5s")
    no_trade = dict(completed)
    no_trade.update({
        "ticker": "KXBTC15M-26AUG131530-30",
        "status": "no_trigger",
        "triggered": False,
        "entry_filled": False,
        "pnl": "",
    })
    rows = []
    # summarize expects every scenario for paired causal comparisons.
    for frequency in ("native", "1s", "2s", "5s"):
        for mode in ("unprotected", "state_protected"):
            scenario = f"causal_response_receipt_{frequency}_{mode}"
            for source in (completed, no_trade):
                row = dict(source)
                row.update({
                    "scenario": scenario,
                    "monitoring_frequency": frequency,
                    "entry_protection_mode": mode,
                    "clock_basis": "causal_response_receipt",
                })
                rows.append(row)
    for source in (completed, no_trade):
        row = dict(source)
        row.update({
            "scenario": "legacy_csv_loop_time_5s_unprotected",
            "monitoring_frequency": "5s",
            "entry_protection_mode": "unprotected",
            "clock_basis": "legacy_csv_loop_time",
        })
        rows.append(row)
    summary = summarize(rows)
    selected = next(
        row for row in summary
        if row["segment"] == "all_96"
        and row["scenario"] == "causal_response_receipt_5s_unprotected"
    )
    assert selected["mean_pnl_per_eligible_market"] == float(completed["pnl"]) / 2
    assert selected["mean_pnl_per_filled_entry"] == float(completed["pnl"])
