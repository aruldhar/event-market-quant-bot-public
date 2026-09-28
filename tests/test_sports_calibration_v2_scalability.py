from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.historical_feasibility import HistoricalCutoff, HistoricalFeasibilityRows
from src.sports_calibration_v2_scalability import (
    SportsV2ScalabilityError,
    build_sports_v2_scalability_summary,
    validate_sports_v2_requested_event_count,
)


def make_rows(*, event_count: int = 100, dominant_series_count: int = 1):
    events = []
    markets = []
    observations = []
    for i in range(event_count):
        event_ticker = f"E{i:03d}"
        series = "DOM" if i < dominant_series_count else f"S{i:03d}"
        ticker = f"M{i:03d}"
        events.append({
            "category": "Sports",
            "event_ticker": event_ticker,
            "series_ticker": series,
        })
        markets.append({
            "category": "Sports",
            "event_ticker": event_ticker,
            "ticker": ticker,
        })
        observations.append({
            "category": "Sports",
            "event_ticker": event_ticker,
            "ticker": ticker,
            "valid_quote_observation": "true",
        })

    sports_summary = {
        "category": "Sports",
        "event_any_quote_coverage": "0.900000",
        "market_any_quote_coverage": "0.900000",
        "early_event_coverage": "0.800000",
        "middle_event_coverage": "0.800000",
        "late_event_coverage": "0.800000",
        "max_event_observation_share": "0.010000",
        "top_decile_event_observation_share": "0.100000",
    }
    other_summaries = [
        {"category": category}
        for category in ("Crypto", "Climate and Weather", "Commodities")
    ]
    cutoff = HistoricalCutoff(
        market_settled_ts=datetime(2026, 6, 1, tzinfo=timezone.utc),
        trades_created_ts=datetime(2026, 6, 1, tzinfo=timezone.utc),
        orders_updated_ts=datetime(2026, 6, 1, tzinfo=timezone.utc),
        market_positions_last_updated_ts=None,
    )
    return HistoricalFeasibilityRows(
        events=tuple(events),
        markets=tuple(markets),
        windows=(),
        observations=tuple(observations),
        category_summary=(sports_summary, *other_summaries),
        cutoff=cutoff,
        cutoff_raw_source="source",
        cutoff_raw_session_id="session",
        cutoff_raw_request_id="request",
        event_pages_scanned=1,
        cross_tier_observation_count=0,
        cross_tier_market_count=0,
        cross_tier_recovery_fetch_count=0,
        unclassifiable_event_count=0,
        target_events_per_category=event_count,
        max_markets_per_event=2,
    )


def test_100_event_scalability_sample_passes_when_quote_and_series_gates_pass():
    summary = build_sports_v2_scalability_summary(
        make_rows(event_count=100, dominant_series_count=20)
    )
    assert summary["sample_target_met"] is True
    assert summary["quote_gates_met"] is True
    assert summary["series_concentration_warning"] is False
    assert summary["series_concentration_block"] is False
    assert summary["scalability_gate_pass"] is True
    assert summary["status"] == "scalability_gate_pass"
    assert summary["dominant_series_event_share"] == "0.200000"
    assert summary["outcomes_materialized"] is False


def test_series_above_25_percent_warns_but_does_not_block():
    summary = build_sports_v2_scalability_summary(
        make_rows(event_count=100, dominant_series_count=30)
    )
    assert summary["series_concentration_warning"] is True
    assert summary["series_concentration_block"] is False
    assert summary["scalability_gate_pass"] is True
    assert summary["status"] == "scalability_gate_pass_with_series_warning"


def test_series_above_50_percent_blocks_general_sports_scalability():
    summary = build_sports_v2_scalability_summary(
        make_rows(event_count=100, dominant_series_count=51)
    )
    assert summary["series_concentration_warning"] is True
    assert summary["series_concentration_block"] is True
    assert summary["scalability_gate_pass"] is False
    assert summary["status"] == "series_concentration_blocked"


def test_below_100_events_cannot_pass_even_with_good_quote_coverage():
    summary = build_sports_v2_scalability_summary(
        make_rows(event_count=99, dominant_series_count=1)
    )
    assert summary["sample_target_met"] is False
    assert summary["scalability_gate_pass"] is False
    assert summary["status"] == "insufficient_event_sample"


def test_outcome_field_is_rejected_from_scalability_input():
    rows = make_rows()
    altered_events = list(rows.events)
    altered_events[0] = dict(altered_events[0], result="yes")
    altered = HistoricalFeasibilityRows(**{**rows.__dict__, "events": tuple(altered_events)})
    with pytest.raises(SportsV2ScalabilityError, match="forbidden outcome"):
        build_sports_v2_scalability_summary(altered)


def test_dedicated_scalability_request_cannot_lower_100_event_gate():
    assert validate_sports_v2_requested_event_count(100) == 100
    assert validate_sports_v2_requested_event_count(125) == 125
    with pytest.raises(ValueError, match="cannot be below 100"):
        validate_sports_v2_requested_event_count(99)
