from datetime import datetime, timedelta, timezone

import pytest

from analyze_kxbtc15m_lead_lag import (
    EVENT_OFFSETS,
    GridPoint,
    LAGS,
    direction_agreement,
    lag_pairs,
    pearson,
    select_events,
    time_phase,
)


UTC = timezone.utc
BASE = datetime(2026, 8, 13, tzinfo=UTC)


def test_extended_ranges_are_frozen_and_include_prior_window():
    assert LAGS == tuple(range(-10, 16))
    assert EVENT_OFFSETS == tuple(range(-10, 16))
    assert set(range(-5, 6)).issubset(LAGS)


def point(second, book_change, chart_change, *, remaining=None):
    remaining = 300 - second if remaining is None else remaining
    return GridPoint(
        ticker="KXBTC15M-TEST",
        market_index=1,
        diagnostic_segment="earlier_64",
        observed_at=BASE + timedelta(seconds=second),
        seconds_remaining=remaining,
        time_phase=time_phase(remaining),
        book_observed_at=BASE + timedelta(seconds=second, milliseconds=-200),
        book_age_seconds=0.2,
        yes_bid=0.5,
        chart_value=100.0,
        chart_delta_from_target=0.0,
        book_change_cents=book_change,
        chart_change_usd=chart_change,
    )


def test_phase_boundaries_are_explicit():
    assert time_phase(300) == "05_240_300s"
    assert time_phase(240) == "04_180_240s"
    assert time_phase(180) == "03_120_180s"
    assert time_phase(120) == "02_60_120s"
    assert time_phase(60) == "01_final_0_60s"
    assert time_phase(0) == "01_final_0_60s"


def test_positive_lag_means_orderbook_leads_chart():
    points = [point(i, float(i), float(max(0, i - 2))) for i in range(12)]
    pairs = lag_pairs(points, "all_final_5m", 2)
    assert pairs[0] == (0.0, 0.0)
    assert pairs[-1] == (9.0, 9.0)
    assert pearson(pairs) == pytest.approx(1.0)


def test_negative_lag_means_chart_leads_orderbook():
    points = [point(i, float(i), float(i + 1)) for i in range(12)]
    pairs = lag_pairs(points, "all_final_5m", -1)
    assert pairs[0] == (1.0, 1.0)
    assert pairs[-1] == (11.0, 11.0)
    assert pearson(pairs) == pytest.approx(1.0)


def test_lag_pair_does_not_cross_time_phase_boundary():
    points = [
        point(0, 1.0, 1.0, remaining=241),
        point(1, 1.0, 1.0, remaining=240),
    ]
    assert lag_pairs(points, "05_240_300s", 1) == []


def test_direction_agreement_excludes_zero_changes():
    assert direction_agreement([(1, 2), (-1, -2), (0, 2), (1, 0)]) == 1.0
    assert direction_agreement([(1, -2), (-1, -2)]) == 0.5


def test_large_jump_events_use_five_second_cooldown():
    points = [point(i, 3.0 if i in {1, 2, 6, 7} else 0.0, 0.0) for i in range(9)]
    events = select_events(points, 2.0)
    assert [event.observed_at for event in events] == [
        BASE + timedelta(seconds=1),
        BASE + timedelta(seconds=6),
    ]
