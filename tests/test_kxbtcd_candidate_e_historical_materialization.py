from __future__ import annotations

from copy import deepcopy

import pytest

from collect_kxbtcd_candidate_e_historical_materialization_chunk import (
    CANONICAL_ROOT,
    SMOKE_ROOT,
    _chunk_output_paths,
)

from src.kxbtcd_candidate_e_historical_materialization import (
    FROZEN_CONTRACT_FINGERPRINT,
    RAW_QUEUE_CONSUMPTION_LIMIT,
    CandidateEHistoricalMaterializationError,
    anchor_is_eligible,
    assign_cohorts,
    balanced_block_ids,
    build_common_candidate_row,
    evaluate_historical_btc_pair,
    event_is_eligible,
    project_historical_market_metadata,
    validate_contract,
)


def _event(index: int, *, eligible: bool = True) -> dict[str, object]:
    return {
        "event_ticker": f"KXBTCD-SYN-{index:04d}",
        "event_close_time_utc": f"2025-01-{1 + (index // 24) % 28:02d}T{index % 24:02d}:00:00Z",
        "queue_index_zero_based": index,
        "eligible_event": eligible,
        "eligible_anchor_count": 6 if eligible else 3,
        "common_row_count": 30 if eligible else 0,
        "exclusion_reasons": [] if eligible else ["fewer_than_four_eligible_anchors"],
        "source_chunk_run_id": f"run-{index//50:03d}",
    }


def test_contract_fingerprint_is_frozen():
    assert validate_contract(verify_parents=False) == FROZEN_CONTRACT_FINGERPRINT


def test_source_outcome_values_cannot_change_metadata_projection():
    base = {
        "event_ticker": "KXBTCD-TEST",
        "ticker": "KXBTCD-TEST-T100000",
        "rules_primary": "same",
        "rules_secondary": "same",
        "close_time": "2025-01-01T01:00:00Z",
        "strike_type": "greater",
        "floor_strike": 100000,
        "functional_strike": None,
    }
    yes = {**base, "result": "yes", "settlement_value_dollars": "1.0000"}
    no = {**base, "result": "no", "settlement_value_dollars": "0.0000"}
    assert project_historical_market_metadata(yes) == project_historical_market_metadata(no)


def test_current_and_lookback_cross_source_gates_are_both_required():
    good = evaluate_historical_btc_pair(
        coinbase_current_price=100000,
        kraken_current_price=100001,
        coinbase_lookback_price=99900,
        kraken_lookback_price=99901,
    )
    assert good.eligible

    bad_lookback = evaluate_historical_btc_pair(
        coinbase_current_price=100000,
        kraken_current_price=100001,
        coinbase_lookback_price=99900,
        kraken_lookback_price=100100,
    )
    assert not bad_lookback.eligible
    assert "lookback_cross_source_disagreement_above_5bp" in bad_lookback.exclusion_reasons


def test_anchor_and_event_gate_is_at_least_one_row_and_four_of_six():
    assert anchor_is_eligible(btc_pair_eligible=True, valid_common_row_count=1)
    assert not anchor_is_eligible(btc_pair_eligible=True, valid_common_row_count=0)
    assert not anchor_is_eligible(btc_pair_eligible=False, valid_common_row_count=5)
    assert event_is_eligible([True, True, True, True, False, False]) == (True, 4)
    assert event_is_eligible([True, True, True, False, False, False]) == (False, 3)


def test_balanced_blocks_differ_by_at_most_one():
    ids = balanced_block_ids(1500, 7)
    counts = [ids.count(f"B{i}") for i in range(7)]
    assert max(counts) - min(counts) <= 1
    assert sum(counts) == 1500


def test_cohort_assignment_exact_1500_750_750():
    events = [_event(i) for i in range(3000)]
    cohort, exclusions, summary = assign_cohorts(events)
    assert not exclusions
    assert summary["eligible_counts"] == {"H1": 1500, "H2": 750, "H3": 750}
    assert len(cohort) == 3000
    assert cohort[0]["stage"] == "H1"
    assert cohort[1499]["stage"] == "H1"
    assert cohort[1500]["stage"] == "H2"
    assert cohort[2249]["stage"] == "H2"
    assert cohort[2250]["stage"] == "H3"


def test_ineligible_events_extend_queue_without_filling_stage():
    events = []
    for i in range(3010):
        events.append(_event(i, eligible=i not in set(range(0, 10))))
    cohort, exclusions, summary = assign_cohorts(events)
    assert len(exclusions) == 10
    assert summary["eligible_counts"] == {"H1": 1500, "H2": 750, "H3": 750}
    assert summary["queue_events_consumed"] == 3010


def test_protected_tail_fails_closed_before_4432nd_queue_event():
    events = [_event(i, eligible=False) for i in range(RAW_QUEUE_CONSUMPTION_LIMIT + 1)]
    with pytest.raises(CandidateEHistoricalMaterializationError, match="protected"):
        assign_cohorts(events, require_complete=False)


def test_common_row_has_no_outcome_and_preserves_raw_q():
    row = build_common_candidate_row(
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
        kraken_current_price="100101",
        current_disagreement_bps=0.1,
        coinbase_lookback_minute_start_utc="2024-12-31T23:59:00Z",
        coinbase_lookback_price="100000",
        kraken_lookback_price="100001",
        lookback_disagreement_bps=0.1,
        raw_observation_refs=["raw:a:b:c"],
    )
    assert row["q_market"] == "0.5"
    assert "result" not in row
    assert row["stage"] == ""
    assert row["event_row_weight"] == ""

def test_smoke_output_path_does_not_repeat_long_run_id_directory():
    run_id = (
        "collect_kxbtcd_candidate_e_historical_materialization_chunk_"
        "20260817T082331633916Z_9b282d18"
    )

    event_path, anchor_path, row_path = _chunk_output_paths(
        smoke=True,
        run_id=run_id,
    )

    assert event_path.parent == SMOKE_ROOT
    assert anchor_path.parent == SMOKE_ROOT
    assert row_path.parent == SMOKE_ROOT
    assert event_path.name == f"{run_id}_events.csv"
    assert anchor_path.name == f"{run_id}_anchors.csv"
    assert row_path.name == f"{run_id}_rows.csv"
    assert event_path.parent != SMOKE_ROOT / run_id

    canonical_event, _, _ = _chunk_output_paths(
        smoke=False,
        run_id=run_id,
    )
    assert canonical_event.parent == CANONICAL_ROOT
