from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    BALANCE_QUANTUM,
    LATENCY_MS,
    PLANNED_QUANTITY,
    BookLevel,
    BookState,
    SignalCandidate,
    VerifiedSegmentTimeline,
    VerifiedTickerTimeline,
    account_synthetic_fill,
    best_yes_quote,
    build_signal_candidates,
    candidate_e_probability,
    select_event_signal,
    select_structural_markets,
    side_purchase_asks,
    side_sale_bids,
    simulate_entry,
    simulate_ioc,
    simulate_liquidation_branch,
    simulate_scenario,
)


D = Decimal


def state(ts, bids, asks):
    return BookState(
        timestamp_ms=ts,
        yes_bids=tuple(BookLevel(D(p), D(q)) for p, q in bids),
        yes_asks=tuple(BookLevel(D(p), D(q)) for p, q in asks),
    )


def timeline(ticker, start, end, states):
    return VerifiedTickerTimeline(
        ticker=ticker,
        segments=(
            VerifiedSegmentTimeline(
                segment_index=0,
                start_timestamp_ms=start,
                end_timestamp_ms=end,
                states=tuple(states),
            ),
        ),
    )


def signal(
    *,
    side="YES",
    decision=1000,
    limit="0.4000",
    fair="0.6000",
    edge="0.1800",
):
    return SignalCandidate(
        event_ticker="E1",
        market_ticker="M1",
        structural_role="q50",
        ttc_target_minutes=55,
        decision_timestamp_ms=decision,
        side=side,
        candidate_probability=D("0.6000") if side == "YES" else D("0.4000"),
        side_fair_probability=D(fair),
        q_market=D("0.5000"),
        decision_yes_bid=D("0.3900"),
        decision_yes_ask=D("0.4000"),
        decision_limit_price=D(limit),
        signal_entry_fee=D("0.0200"),
        net_edge_per_contract=D(edge),
    )


def test_single_fill_direct_member_accounting_identity():
    fill = account_synthetic_fill(action="BUY", price="0.5000", quantity="1.00")
    assert fill.trade_fee == D("0.017500")
    assert fill.rounding_fee == D("0.000000")
    assert fill.rebate == D("0.0000")
    assert fill.net_fee == D("0.017500")
    assert fill.net_cash_change == D("-0.517500")
    assert fill.net_cash_change == fill.gross_revenue - fill.net_fee


def test_multifill_accumulator_rebates_in_centi_cent_units():
    first = account_synthetic_fill(action="BUY", price="0.3333", quantity="0.25")
    second = account_synthetic_fill(
        action="BUY", price="0.4444", quantity="0.25",
        accumulator_before=first.accumulator_after,
    )
    assert first.rounding_fee == D("0.000086")
    assert first.accumulator_after == D("0.000086")
    assert second.rebate == BALANCE_QUANTUM
    assert second.accumulator_after == D("0.000065")
    assert second.net_cash_change == D("-0.1154")
    assert second.net_fee >= 0


def test_ioc_walks_visible_levels_and_reports_partial_fill():
    levels = (
        BookLevel(D("0.4000"), D("0.40")),
        BookLevel(D("0.4100"), D("0.30")),
        BookLevel(D("0.4200"), D("1.00")),
    )
    result = simulate_ioc(
        action="BUY", levels=levels, limit_price="0.4100", requested_quantity="1.00"
    )
    assert result.status == "PARTIAL"
    assert result.filled_quantity == D("0.70")
    assert result.unfilled_quantity == D("0.30")
    assert [fill.price for fill in result.fills] == [D("0.4000"), D("0.4100")]


def test_yes_no_book_normalization_is_complementary():
    s = state(
        1000,
        bids=[("0.6000", "2.00"), ("0.5900", "3.00")],
        asks=[("0.6100", "4.00"), ("0.6200", "5.00")],
    )
    assert side_purchase_asks(s, "NO")[0] == BookLevel(D("0.4000"), D("2.00"))
    assert side_sale_bids(s, "NO")[0] == BookLevel(D("0.3900"), D("4.00"))


def test_structural_market_selection_reuses_frozen_half_up_ranks():
    markets = [(f"M{i}", str(100 + i)) for i in range(10)]
    selected = select_structural_markets(markets)
    assert [item.structural_role for item in selected] == ["q10", "q30", "q50", "q70", "q90"]
    assert [item.strike_rank_zero_based for item in selected] == [1, 3, 5, 6, 8]


def test_candidate_probability_nests_market_at_zero_distance():
    p = candidate_e_probability(q_market="0.42", btc_spot="100", strike="100")
    assert abs(p - D("0.42")) < D("0.00000000000001")


def test_signal_requires_full_quantity_at_best_decision_price_level():
    tl = timeline(
        "M1", 1000, 2000,
        [state(1000, bids=[("0.3900", "2.00")], asks=[("0.4000", "0.99")])],
    )
    candidates = build_signal_candidates(
        event_ticker="E1", market_ticker="M1", structural_role="q50",
        ttc_target_minutes=55, decision_timestamp_ms=1000,
        btc_spot="100", strike="100", timeline=tl,
    )
    # YES best ask lacks 1.00 depth; NO is still independently eligible from YES bid depth.
    assert [candidate.side for candidate in candidates] == ["NO"]


def test_first_qualifying_anchor_then_largest_edge_and_tie_break():
    base = signal()
    candidates = [
        base.__class__(**{**base.__dict__, "market_ticker": "Z", "side": "YES", "net_edge_per_contract": D("0.03")}),
        base.__class__(**{**base.__dict__, "market_ticker": "A", "side": "NO", "net_edge_per_contract": D("0.03")}),
        base.__class__(**{**base.__dict__, "market_ticker": "A", "side": "YES", "net_edge_per_contract": D("0.03")}),
        base.__class__(**{**base.__dict__, "market_ticker": "B", "ttc_target_minutes": 50, "net_edge_per_contract": D("0.50")}),
    ]
    selected = select_event_signal(candidates, threshold="0.02")
    assert selected is not None
    assert selected.ttc_target_minutes == 55
    assert selected.market_ticker == "A"
    assert selected.side == "YES"


def test_latency_interval_gap_is_source_unavailable_and_never_falls_through():
    tl = VerifiedTickerTimeline(
        ticker="M1",
        segments=(
            VerifiedSegmentTimeline(
                segment_index=0, start_timestamp_ms=1000, end_timestamp_ms=1200,
                states=(state(1000, bids=[("0.3900","2.00")], asks=[("0.4000","2.00")]),),
            ),
            VerifiedSegmentTimeline(
                segment_index=1, start_timestamp_ms=1500, end_timestamp_ms=3000,
                states=(state(1500, bids=[("0.3900","2.00")], asks=[("0.4000","2.00")]),),
            ),
        ),
    )
    attempt = simulate_entry(signal=signal(), timeline=tl, latency_ms=500)
    assert attempt.source_available is False
    assert attempt.ioc is None
    assert attempt.source_status == "SOURCE_UNAVAILABLE_DECISION_TO_ARRIVAL"


def test_entry_price_improvement_allowed_but_worsening_beyond_limit_misses():
    improving = timeline(
        "M1", 1000, 3000,
        [
            state(1000, bids=[("0.3900","2.00")], asks=[("0.4000","2.00")]),
            state(1500, bids=[("0.3900","2.00")], asks=[("0.3900","2.00")]),
        ],
    )
    attempt = simulate_entry(signal=signal(), timeline=improving, latency_ms=500)
    assert attempt.ioc is not None and attempt.ioc.status == "FULL"
    assert attempt.ioc.vwap == D("0.3900")

    worsening = timeline(
        "M1", 1000, 3000,
        [
            state(1000, bids=[("0.3900","2.00")], asks=[("0.4000","2.00")]),
            state(1500, bids=[("0.4000","2.00")], asks=[("0.4100","2.00")]),
        ],
    )
    attempt2 = simulate_entry(signal=signal(), timeline=worsening, latency_ms=500)
    assert attempt2.ioc is not None and attempt2.ioc.status == "MISSED"


def test_liquidation_trigger_requires_full_depth_and_net_fair_target():
    tl = timeline(
        "M1", 1000, 5000,
        [
            state(1000, bids=[("0.3900","2.00")], asks=[("0.4000","2.00")]),
            state(2000, bids=[("0.6100","0.50"), ("0.6000","0.40")], asks=[("0.6200","2.00")]),
            state(3000, bids=[("0.6200","1.00")], asks=[("0.6300","2.00")]),
        ],
    )
    entry = simulate_entry(signal=signal(fair="0.6000"), timeline=tl, latency_ms=0)
    branch = simulate_liquidation_branch(
        signal=signal(fair="0.6000"), entry=entry, timeline=tl, event_close_timestamp_ms=5000
    )
    assert branch is not None
    assert branch.trigger is not None
    assert branch.trigger.trigger_timestamp_ms == 3000


def test_actual_exit_uses_trigger_limit_and_partial_remainder_falls_to_settlement():
    tl = timeline(
        "M1", 1000, 5000,
        [
            state(1000, bids=[("0.3900","2.00")], asks=[("0.4000","2.00")]),
            state(2000, bids=[("0.6500","1.00")], asks=[("0.6600","2.00")]),
            # With 500ms latency, arrival book has only 0.40 at/above the trigger's 0.6500 limit.
            state(2500, bids=[("0.6500","0.40"), ("0.6400","5.00")], asks=[("0.6600","2.00")]),
        ],
    )
    sig = signal(fair="0.6000")
    entry = simulate_entry(signal=sig, timeline=tl, latency_ms=500)
    # Entry arrival is 1500, before the 2000 trigger.
    branch = simulate_liquidation_branch(
        signal=sig, entry=entry, timeline=tl, event_close_timestamp_ms=5000
    )
    assert branch is not None
    assert branch.status == "EXIT_PARTIAL_SETTLEMENT_FALLBACK"
    assert branch.exit_ioc is not None
    assert branch.exit_ioc.filled_quantity == D("0.40")
    assert branch.settlement_fallback_quantity == D("0.60")


def test_no_trigger_with_verified_path_to_close_holds():
    tl = timeline(
        "M1", 1000, 5000,
        [state(1000, bids=[("0.3900","2.00")], asks=[("0.4000","2.00")])],
    )
    sig = signal(fair="0.8000")
    entry = simulate_entry(signal=sig, timeline=tl, latency_ms=0)
    branch = simulate_liquidation_branch(
        signal=sig, entry=entry, timeline=tl, event_close_timestamp_ms=5000
    )
    assert branch is not None
    assert branch.status == "HOLD_TO_SETTLEMENT_NO_TRIGGER"
    assert branch.settlement_fallback_quantity == D("1.00")


def test_monitoring_gap_before_close_is_source_unavailable_not_assumed_hold():
    tl = timeline(
        "M1", 1000, 3000,
        [state(1000, bids=[("0.3900","2.00")], asks=[("0.4000","2.00")])],
    )
    sig = signal(fair="0.8000")
    entry = simulate_entry(signal=sig, timeline=tl, latency_ms=0)
    branch = simulate_liquidation_branch(
        signal=sig, entry=entry, timeline=tl, event_close_timestamp_ms=5000
    )
    assert branch is not None
    assert branch.status == "SOURCE_UNAVAILABLE_MONITORING_GAP"
    assert branch.source_available is False


def test_matched_hold_uses_identical_realized_entry_fill_quantity():
    tl = timeline(
        "M1", 1000, 5000,
        [
            state(1000, bids=[("0.3900","2.00")], asks=[("0.4000","2.00")]),
            state(1500, bids=[("0.3900","2.00")], asks=[("0.4000","0.40")]),
        ],
    )
    result = simulate_scenario(
        signal=signal(), timeline=tl, latency_ms=500, event_close_timestamp_ms=5000
    )
    assert result.entry.ioc is not None
    assert result.entry.ioc.filled_quantity == D("0.40")
    assert result.matched_hold_settlement_quantity == D("0.40")


def test_verified_replay_collapses_same_millisecond_transients_right_continuously():
    from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
        build_verified_ticker_timeline,
    )
    snapshots = [
        {
            "timestamp": 1000,
            "sequence": 1,
            "yes_bids": [{"price": "40", "size": "1.00"}],
            "yes_asks": [{"price": "60", "size": "1.00"}],
        },
        {
            "timestamp": 1001,
            "sequence": 2,
            "yes_bids": [{"price": "42", "size": "1.00"}],
            "yes_asks": [{"price": "60", "size": "1.00"}],
        },
    ]
    paid_rows = [
        {"timestamp": 1001, "sequence": 1, "side": "yes", "price_dollars": "0.4000", "delta_fp": "-1.00"},
        {"timestamp": 1001, "sequence": 2, "side": "yes", "price_dollars": "0.4100", "delta_fp": "1.00"},
        {"timestamp": 1001, "sequence": 3, "side": "yes", "price_dollars": "0.4100", "delta_fp": "-1.00"},
        {"timestamp": 1001, "sequence": 4, "side": "yes", "price_dollars": "0.4200", "delta_fp": "1.00"},
    ]
    replay = build_verified_ticker_timeline(ticker="M1", snapshots=snapshots, paid_rows=paid_rows)
    assert len(replay.segments) == 1
    segment = replay.segments[0]
    assert [item.timestamp_ms for item in segment.states] == [1000, 1001]
    assert segment.state_at(1001).yes_bids[0].price == D("0.42")
    assert all(
        all(level.price != D("0.41") for level in item.yes_bids)
        for item in segment.states
    )
