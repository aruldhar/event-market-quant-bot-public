from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.kxbtcd_independent_btc_source_policy import (
    EXPECTED_POLICY_FINGERPRINT,
    KxbtcdIndependentBtcSourcePolicyError,
    causal_lookback_eligible,
    disagreement_bps,
    evaluate_live_source_state,
    load_and_validate_policy,
    tier_ready,
)


def test_frozen_policy_loads_and_has_expected_fingerprint() -> None:
    policy = load_and_validate_policy()
    assert policy["policy_fingerprint"] == EXPECTED_POLICY_FINGERPRINT
    assert policy["evidence_boundary"]["outcomes_used_to_select_policy"] is False
    assert policy["evidence_boundary"]["candidate_e_fitting_authorized"] is False
    assert policy["evidence_boundary"]["execution_authorized"] is False


def test_live_source_state_passes_inside_all_frozen_gates() -> None:
    decision = evaluate_live_source_state(
        coinbase_best_bid=62999.0,
        coinbase_best_ask=63001.0,
        kraken_best_bid=62998.5,
        kraken_best_ask=63001.5,
        coinbase_local_first_seen_age_seconds=2.0,
        kraken_local_first_seen_age_seconds=2.0,
        coinbase_source_event_age_seconds=4.0,
        kraken_best_bid_publication_age_seconds=30.0,
        kraken_best_ask_publication_age_seconds=40.0,
        cross_source_receive_skew_seconds=0.2,
        local_clock_offset_seconds=-0.17,
    )
    assert decision.eligible is True
    assert decision.primary_price == pytest.approx(63000.0)
    assert decision.exclusion_reasons == ()


def test_kraken_uses_older_side_for_conservative_freshness() -> None:
    decision = evaluate_live_source_state(
        coinbase_best_bid=62999.0,
        coinbase_best_ask=63001.0,
        kraken_best_bid=62999.0,
        kraken_best_ask=63001.0,
        coinbase_local_first_seen_age_seconds=1.0,
        kraken_local_first_seen_age_seconds=1.0,
        coinbase_source_event_age_seconds=2.0,
        kraken_best_bid_publication_age_seconds=3.0,
        kraken_best_ask_publication_age_seconds=61.0,
        cross_source_receive_skew_seconds=0.1,
        local_clock_offset_seconds=0.0,
    )
    assert decision.eligible is False
    assert "kraken_conservative_bbo_stale" in decision.exclusion_reasons


def test_disagreement_gate_is_strictly_frozen_at_five_bps() -> None:
    # 63000 versus 63040 is about 6.35 bp.
    decision = evaluate_live_source_state(
        coinbase_best_bid=62999.0,
        coinbase_best_ask=63001.0,
        kraken_best_bid=63039.0,
        kraken_best_ask=63041.0,
        coinbase_local_first_seen_age_seconds=1.0,
        kraken_local_first_seen_age_seconds=1.0,
        coinbase_source_event_age_seconds=2.0,
        kraken_best_bid_publication_age_seconds=10.0,
        kraken_best_ask_publication_age_seconds=10.0,
        cross_source_receive_skew_seconds=0.1,
        local_clock_offset_seconds=0.0,
    )
    assert decision.eligible is False
    assert "cross_source_disagreement_exceeded" in decision.exclusion_reasons


def test_lookback_is_causal_and_bounded() -> None:
    target = datetime(2026, 8, 17, 6, 0, 0, tzinfo=timezone.utc)
    assert causal_lookback_eligible(
        target_time_utc=target,
        observation_time_utc=datetime(2026, 8, 17, 5, 59, 56, tzinfo=timezone.utc),
    )
    assert not causal_lookback_eligible(
        target_time_utc=target,
        observation_time_utc=datetime(2026, 8, 17, 5, 59, 54, tzinfo=timezone.utc),
    )
    assert not causal_lookback_eligible(
        target_time_utc=target,
        observation_time_utc=datetime(2026, 8, 17, 6, 0, 1, tzinfo=timezone.utc),
    )


def test_e1_tier_requires_full_calendar_and_source_coverage() -> None:
    ready, reasons = tier_ready(
        "E1",
        eligible_event_count=168,
        distinct_utc_dates=7,
        chronological_span_hours=168,
        utc_hour_of_day_bins=range(24),
        tier_source_eligible_state_rate=0.95,
        per_event_source_eligible_state_fractions=[1.0] * 168,
    )
    assert ready is True
    assert reasons == ()

    ready, reasons = tier_ready(
        "E1",
        eligible_event_count=168,
        distinct_utc_dates=7,
        chronological_span_hours=168,
        utc_hour_of_day_bins=range(23),
        tier_source_eligible_state_rate=0.95,
        per_event_source_eligible_state_fractions=[1.0] * 168,
    )
    assert ready is False
    assert "incomplete_utc_hour_of_day_coverage" in reasons


def test_e3_requires_336_events_and_14_dates() -> None:
    ready, reasons = tier_ready(
        "E3",
        eligible_event_count=335,
        distinct_utc_dates=14,
        chronological_span_hours=336,
        utc_hour_of_day_bins=range(24),
        tier_source_eligible_state_rate=1.0,
        per_event_source_eligible_state_fractions=[1.0] * 335,
    )
    assert ready is False
    assert "insufficient_eligible_events" in reasons


def test_invalid_bbo_fails_closed() -> None:
    with pytest.raises(KxbtcdIndependentBtcSourcePolicyError):
        # direct primitive is validated separately
        from src.kxbtcd_independent_btc_source_policy import midpoint
        midpoint(101.0, 100.0)
