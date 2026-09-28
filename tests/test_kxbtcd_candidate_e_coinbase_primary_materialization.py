from __future__ import annotations

from copy import deepcopy

from src.kxbtcd_candidate_e_coinbase_primary_materialization import (
    FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
    RAW_QUEUE_CONSUMPTION_LIMIT,
    assign_cohorts,
    build_coinbase_primary_candidate_row,
    evaluate_historical_coinbase_state,
    validate_coinbase_primary_amendment,
)


def _event(index: int, *, eligible: bool = True):
    return {
        "schema_version": "kxbtcd_candidate_e_coinbase_primary_event_materialization.v1",
        "contract_fingerprint": "cc3e3326455fce2abbf7e39bdb8858d0d4cea67415ea90ece091259780de9145",
        "source_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "event_ticker": f"KXBTCD-SYN-{index:04d}",
        "event_close_time_utc": f"2025-01-{1 + (index // 24) % 28:02d}T{index % 24:02d}:00:00Z",
        "queue_index_zero_based": index,
        "eligible_event": eligible,
        "eligible_anchor_count": 6 if eligible else 3,
        "common_row_count": 30 if eligible else 0,
        "exclusion_reasons": [] if eligible else ["fewer_than_four_eligible_anchors"],
        "source_chunk_run_id": f"run-{index//50:03d}",
    }


def test_amendment_fingerprint_is_frozen():
    assert validate_coinbase_primary_amendment(verify_parent=False) == FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT


def test_coinbase_state_does_not_require_kraken():
    good = evaluate_historical_coinbase_state(
        coinbase_current_price=100000,
        coinbase_lookback_price=99900,
    )
    assert good.eligible
    assert good.exclusion_reasons == ()


def test_coinbase_state_fails_closed_on_missing_required_price():
    missing_now = evaluate_historical_coinbase_state(
        coinbase_current_price=None,
        coinbase_lookback_price=99900,
    )
    assert not missing_now.eligible
    assert "missing_coinbase_current" in missing_now.exclusion_reasons


def test_candidate_row_uses_coinbase_features_and_blanks_kraken_diagnostics():
    row = build_coinbase_primary_candidate_row(
        event_ticker="KXBTCD-TEST",
        event_close_time_utc="2025-01-01T01:00:00Z",
        queue_index_zero_based=0,
        structural_role="q50",
        market_ticker="KXBTCD-TEST-T100000",
        strike_dollars="100000",
        ttc_target_minutes=55,
        decision_target="2025-01-01T00:05:00Z",
        kalshi_anchor={
            "yes_bid": "0.4",
            "yes_ask": "0.6",
            "midpoint": "0.5",
            "spread": "0.2",
            "selected_end_period_ts": 1735689900,
            "staleness_seconds": 0,
        },
        coinbase_current_minute_start_utc="2025-01-01T00:04:00Z",
        coinbase_current_price="100100",
        coinbase_lookback_minute_start_utc="2024-12-31T23:59:00Z",
        coinbase_lookback_price="100000",
        raw_observation_refs=["raw:coinbase:x:1", "raw:kalshi:y:2"],
    )
    assert row["source_amendment_fingerprint"] == FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT
    assert row["coinbase_current_price"] == "100100"
    assert row["kraken_current_price"] == ""
    assert row["kraken_lookback_price"] == ""
    assert row["current_disagreement_bps"] == ""
    assert row["lookback_disagreement_bps"] == ""
    assert float(row["d_BTC"]) > 0
    assert float(row["r_5m"]) > 0


def test_cohort_targets_remain_1500_750_750():
    events = [_event(i) for i in range(3000)]
    cohort, exclusions, summary = assign_cohorts(events)
    assert not exclusions
    assert summary["eligible_counts"] == {"H1": 1500, "H2": 750, "H3": 750}
    assert len(cohort) == 3000
    assert all(row["source_amendment_fingerprint"] == FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT for row in cohort)


def test_same_identity_rematerialization_does_not_change_queue_cap():
    assert RAW_QUEUE_CONSUMPTION_LIMIT == 4431
