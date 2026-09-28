from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_delta_risk import (
    ChartPoint,
    ChartSeries,
    DeltaRiskError,
    RISK_POLICIES,
    RiskPolicy,
    find_protected_or_risk_exit,
    latest_chart_point,
    policy_names,
    risk_signal,
    side_aligned_delta,
    verify_baseline_reproduction,
)
from audit_kxbtc15m_raw_depth import ParsedBook


UTC = timezone.utc
BASE = datetime(2026, 8, 13, tzinfo=UTC)


def chart(values):
    points = tuple(
        ChartPoint(BASE + timedelta(seconds=index), Decimal(value))
        for index, value in enumerate(values)
    )
    return ChartSeries(
        target=Decimal("100"),
        timestamps=tuple(point.observed_at for point in points),
        points=points,
    )


def snapshot(second, yes_bid, no_bid="0.02", quantity="1000"):
    return Snapshot(
        observed_at=BASE + timedelta(seconds=second, microseconds=500000),
        request_id=str(second),
        book=ParsedBook(
            yes_levels=((Decimal(yes_bid), Decimal(quantity)),),
            no_levels=((Decimal(no_bid), Decimal(quantity)),),
        ),
    )


def policy(name):
    return next(item for item in RISK_POLICIES if item.name == name)


def test_grid_is_small_predeclared_and_unique():
    assert len(RISK_POLICIES) == 8
    assert len(set(policy_names())) == 8
    assert "baseline_no_risk_overlay" in policy_names()
    assert "delta_5usd_or_loss_10pct" in policy_names()


def test_side_aligned_delta_is_positive_on_purchased_side():
    assert side_aligned_delta(
        side="YES", value=Decimal("105"), target=Decimal("100")
    ) == Decimal("5")
    assert side_aligned_delta(
        side="NO", value=Decimal("95"), target=Decimal("100")
    ) == Decimal("5")


def test_latest_chart_point_never_looks_forward():
    series = chart(["99", "100", "101"])
    point, age = latest_chart_point(
        series, BASE + timedelta(seconds=1, microseconds=400000)
    )
    assert point.value == Decimal("100")
    assert age == pytest.approx(0.4)


def test_stale_chart_point_fails_closed():
    with pytest.raises(DeltaRiskError, match="stale"):
        latest_chart_point(chart(["99"]), BASE + timedelta(seconds=2))


def test_delta_and_loss_modes_use_executable_net_pnl():
    assert risk_signal(
        policy("delta_buffer_5usd"), aligned_delta=Decimal("5"),
        executable_pnl=Decimal("2"), outflow=Decimal("100"),
    )
    assert risk_signal(
        policy("loss_stop_10pct"), aligned_delta=Decimal("50"),
        executable_pnl=Decimal("-10"), outflow=Decimal("100"),
    )
    assert not risk_signal(
        policy("loss_stop_10pct"), aligned_delta=Decimal("50"),
        executable_pnl=None, outflow=Decimal("100"),
    )


def test_combined_or_and_are_distinct():
    assert risk_signal(
        policy("delta_5usd_or_loss_10pct"), aligned_delta=Decimal("4"),
        executable_pnl=Decimal("0"), outflow=Decimal("100"),
    )
    assert not risk_signal(
        policy("delta_5usd_and_loss_5pct"), aligned_delta=Decimal("4"),
        executable_pnl=Decimal("0"), outflow=Decimal("100"),
    )
    assert risk_signal(
        policy("delta_5usd_and_loss_5pct"), aligned_delta=Decimal("4"),
        executable_pnl=Decimal("-5"), outflow=Decimal("100"),
    )


def test_risk_signal_waits_full_latency_before_sale():
    selection = find_protected_or_risk_exit(
        snapshots=[snapshot(0, "0.90"), snapshot(1, "0.80")],
        chart=chart(["99", "99"]),
        start_index=0,
        stop_time=BASE + timedelta(seconds=10),
        side="YES",
        quantity=Decimal("100"),
        outflow=Decimal("95"),
        target_amount=Decimal("4"),
        exit_latency_seconds=1.0,
        policy=policy("delta_cross_0usd"),
    )
    assert selection.reason == "risk_overlay_exit"
    assert selection.signal_time == BASE + timedelta(microseconds=500000)
    assert selection.exit_time == BASE + timedelta(seconds=1, microseconds=500000)
    assert selection.execution is not None
    assert selection.execution.sell_inflow - Decimal("95") < 0


def test_protected_target_has_priority_over_risk_signal():
    selection = find_protected_or_risk_exit(
        snapshots=[snapshot(0, "0.99"), snapshot(1, "0.99")],
        chart=chart(["99", "99"]),
        start_index=0,
        stop_time=BASE + timedelta(seconds=10),
        side="YES",
        quantity=Decimal("100"),
        outflow=Decimal("95"),
        target_amount=Decimal("1"),
        exit_latency_seconds=1.0,
        policy=policy("delta_cross_0usd"),
    )
    assert selection.reason == "protected_profit_target"
    assert selection.risk_signals == 0


def test_partial_risk_exit_is_rejected_and_monitoring_continues():
    selection = find_protected_or_risk_exit(
        snapshots=[
            snapshot(0, "0.80"),
            snapshot(1, "0.80", quantity="50"),
            snapshot(2, "0.80"),
            snapshot(3, "0.80"),
        ],
        chart=chart(["99", "99", "99", "99"]),
        start_index=0,
        stop_time=BASE + timedelta(seconds=10),
        side="YES",
        quantity=Decimal("100"),
        outflow=Decimal("95"),
        target_amount=Decimal("10"),
        exit_latency_seconds=1.0,
        policy=policy("delta_cross_0usd"),
    )
    assert selection.reason == "risk_overlay_exit"
    assert selection.risk_liquidity_failures == 1
    assert selection.exit_time == BASE + timedelta(seconds=3, microseconds=500000)


def test_baseline_reproduction_detects_economic_drift():
    prior = {("A", "combined_1s"): 1.25}
    rows = [{
        "ticker": "A", "scenario": "combined_1s",
        "risk_policy": "baseline_no_risk_overlay", "pnl": 1.24,
    }]
    with pytest.raises(DeltaRiskError, match="reproduction failed"):
        verify_baseline_reproduction(prior, rows)
