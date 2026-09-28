from decimal import Decimal
from types import SimpleNamespace

from src.kxbtcd_candidate_e_dashboard_shadow_projection import project_shadow_ledger_events
from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    PRICE_QUANTUM,
    BookLevel,
    BookState,
    account_synthetic_fill,
)
from src.kxbtcd_candidate_e_live_shadow_micro_simulator import (
    FROZEN_ATM_FIVE,
    FROZEN_ATM_ONE,
    MAXIMUM_FILLED_ENTRIES_PER_EVENT,
    NS_PER_MINUTE,
    SIMULATED_ENTRY_BUDGET_DOLLARS,
    LiveShadowMicroState,
    _hypothetical_resting_exit_limit,
    advance_live_shadow_micro,
    advance_live_shadow_micro_for_scenario,
)
from src.kxbtcd_candidate_e_live_shadow_snapshot import build_live_shadow_snapshot
from src.kxbtcd_candidate_e_live_shadow_snapshot_reader import parse_live_shadow_snapshot
from src.kxbtcd_candidate_e_prospective_live_collector import CoinbaseMinuteClose, EventLadder, LadderMarket
from src.kxbtcd_candidate_e_shadow_v2_scenarios import SHADOW_V2_SCENARIOS
from src.kxbtcd_candidate_e_shadow_v2_selection import ShadowV2Selection
from src.kxbtcd_candidate_e_v2_rest_candle_readiness import V2BoundRestCandle


def snapshot(*, sequence, bid, generated_utc="2026-09-09T00:59:00Z"):
    ladder = EventLadder("KXBTCD-TEST", "2026-09-09T01:30:00Z", 1788917400000, (
        LadderMarket("KXBTCD-TEST", "T1", Decimal("99900"), 0, 1, None),
    ))
    candle = V2BoundRestCandle("shadow-run", CoinbaseMinuteClose(
        1788915480, 1788915540, Decimal("100000"), sequence,
        "2026-09-09T00:59:01Z"))
    books = {"T1": BookState(sequence, (BookLevel(Decimal(bid), Decimal("1")),),
                              (BookLevel(Decimal("0.50"), Decimal("1")),))}
    return parse_live_shadow_snapshot(build_live_shadow_snapshot(
        run_id="shadow-run", snapshot_sequence=sequence,
        generated_utc=generated_utc,
        generated_monotonic_ns=sequence,
        event_ladder=ladder, candle=candle, books=books))


def wide_snapshot(*, sequence, btc_spot):
    strikes = tuple(Decimal("99600") + Decimal("100") * index for index in range(9))
    ladder = EventLadder("KXBTCD-WIDE", "2026-09-09T01:30:00Z", 1788917400000, tuple(
        LadderMarket("KXBTCD-WIDE", f"T{index}", strike, index, len(strikes), None)
        for index, strike in enumerate(strikes)
    ))
    candle = V2BoundRestCandle("shadow-run", CoinbaseMinuteClose(
        1788915480, 1788915540, Decimal(btc_spot), sequence, "2026-09-09T00:59:01Z"))
    books = {
        f"T{index}": BookState(sequence, (BookLevel(Decimal("0.40"), Decimal("10")),),
                                 (BookLevel(Decimal("0.50"), Decimal("10")),))
        for index in range(len(strikes))
    }
    return parse_live_shadow_snapshot(build_live_shadow_snapshot(
        run_id="shadow-run", snapshot_sequence=sequence,
        generated_utc=f"2026-09-09T00:59:{sequence:02d}Z",
        generated_monotonic_ns=sequence, event_ladder=ladder, candle=candle, books=books,
    ))


def test_atm_five_challenger_freezes_the_initial_nearest_five(monkeypatch):
    candidate = ShadowV2Selection("T4", "YES", Decimal("0.00"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *_: candidate,
    )
    first = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(), snapshot=wide_snapshot(sequence=1, btc_spot="100000"),
        first_event_sequence=1, scenario=SHADOW_V2_SCENARIOS[0], market_universe=FROZEN_ATM_FIVE,
    )
    assert first.state.market_universe == FROZEN_ATM_FIVE
    assert first.state.frozen_atm_event_ticker == "KXBTCD-WIDE"
    assert first.state.frozen_atm_market_tickers == ("T2", "T3", "T4", "T5", "T6")

    later = advance_live_shadow_micro_for_scenario(
        prior=first.state, snapshot=wide_snapshot(sequence=2, btc_spot="100300"),
        first_event_sequence=first.events[-1]["event_sequence"] + 1,
        scenario=SHADOW_V2_SCENARIOS[0], market_universe=FROZEN_ATM_FIVE,
    )
    assert later.state.frozen_atm_market_tickers == ("T2", "T3", "T4", "T5", "T6")


def test_atm_one_challenger_freezes_only_the_initial_nearest_strike(monkeypatch):
    candidate = ShadowV2Selection("T4", "YES", Decimal("0.00"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *_: candidate,
    )
    first = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(), snapshot=wide_snapshot(sequence=1, btc_spot="100000"),
        first_event_sequence=1, scenario=SHADOW_V2_SCENARIOS[0], market_universe=FROZEN_ATM_ONE,
    )
    assert first.state.market_universe == FROZEN_ATM_ONE
    assert first.state.frozen_atm_market_tickers == ("T4",)

    later = advance_live_shadow_micro_for_scenario(
        prior=first.state, snapshot=wide_snapshot(sequence=2, btc_spot="100300"),
        first_event_sequence=first.events[-1]["event_sequence"] + 1,
        scenario=SHADOW_V2_SCENARIOS[0], market_universe=FROZEN_ATM_ONE,
    )
    assert later.state.frozen_atm_market_tickers == ("T4",)


def test_shadow_simulator_records_actual_v2_decision_and_explicitly_hypothetical_book_walk(monkeypatch):
    candidate = ShadowV2Selection(
        market_ticker="T1", side="YES", net_edge_per_contract=Decimal("0.02"),
        signal=SimpleNamespace(decision_limit_price=Decimal("0.50")),
    )
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate",
        lambda _: candidate,
    )
    first = advance_live_shadow_micro(
        prior=LiveShadowMicroState.new(), snapshot=snapshot(sequence=2, bid="0.40"),
        first_event_sequence=1,
    )
    assert first.state.remaining_quantity == Decimal("1")
    assert first.state.entry_cost <= SIMULATED_ENTRY_BUDGET_DOLLARS
    assert [event["event_type"] for event in first.events] == ["shadow_decision", "shadow_simulated_fill"]
    assert first.events[0]["observed_best_ask_probability"] == "0.50"
    assert first.events[0]["decision_limit_price"] == "0.50"
    assert all(event["scenario_id"] == "edge_002" for event in first.events)
    assert all(event["execution_timing_basis"] == "OBSERVED_SHADOW_PATH" for event in first.events)
    second = advance_live_shadow_micro(
        prior=first.state, snapshot=snapshot(sequence=3, bid="0.70"),
        first_event_sequence=3,
    )
    assert second.state.remaining_quantity == 0
    assert second.events[0]["action"] == "SIMULATED_BACKEND_FULL_EXIT"
    assert second.events[0]["observed_best_bid_probability"] == "0.70"
    assert second.events[0]["visible_full_exit_net_proceeds"]
    assert second.events[0]["required_total_net_proceeds"]
    projected = project_shadow_ledger_events((*first.events, *second.events))
    assert projected.trades[0].simulated_flat is True
    assert projected.trades[0].simulated_net_pnl is not None


def test_shadow_simulator_does_not_claim_unproven_resting_exit_fill(monkeypatch):
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr("src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate", lambda _: candidate)
    first = advance_live_shadow_micro(
        prior=LiveShadowMicroState.new(), snapshot=snapshot(sequence=2, bid="0.40"),
        first_event_sequence=1,
    )
    second = advance_live_shadow_micro(
        prior=first.state, snapshot=snapshot(sequence=3, bid="0.40"),
        first_event_sequence=3,
    )
    # The first post-entry evaluation legitimately initializes peak_favorable_price
    # (None -> the observed price) even on a no-fill cycle, since peak tracking must
    # observe the market regardless of fill status -- that is not an unproven fill.
    # A THIRD identical-price cycle is the real idempotence check: once the peak is
    # already set, repeated no-fill evaluations must not drift any further.
    third = advance_live_shadow_micro(
        prior=second.state, snapshot=snapshot(sequence=4, bid="0.40"),
        first_event_sequence=4,
    )
    assert second.state.peak_favorable_price == Decimal("0.40")
    assert third.state == second.state
    assert second.events[0]["reason"] == "VISIBLE_FULL_EXIT_MISSES_RETAINED_TARGET"
    assert second.events[0]["observed_best_bid_probability"] == "0.40"
    assert second.events[0]["hypothetical_resting_exit_limit_probability"] is not None
    assert Decimal(second.events[0]["hypothetical_resting_exit_limit_probability"]) > Decimal("0.40")
    assert second.events[0]["visible_full_exit_net_proceeds"]
    assert second.events[0]["required_total_net_proceeds"]


def test_dynamic_stop_loss_exits_only_when_current_full_book_is_still_below_stop(monkeypatch):
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *_: candidate,
    )
    first = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(), snapshot=snapshot(sequence=2, bid="0.40"),
        first_event_sequence=1, scenario=SHADOW_V2_SCENARIOS[2],
        stop_loss_fraction=Decimal("0.20"),
    )
    # The full book now values the position below 80% of its actual entry outlay.
    second = advance_live_shadow_micro_for_scenario(
        prior=first.state, snapshot=snapshot(sequence=3, bid="0.40"),
        first_event_sequence=3, scenario=SHADOW_V2_SCENARIOS[2],
        stop_loss_fraction=Decimal("0.20"),
    )
    assert second.events[0]["action"] == "SIMULATED_STOP_LOSS_FULL_EXIT"
    assert second.events[0]["stop_loss_fraction"] == "0.20"
    assert second.state.remaining_quantity == 0


def _monotonic_snapshot(*, sequence, bid_price, bid_quantity, generated_monotonic_ns):
    """A snapshot whose monotonic clock is controllable independent of the
    sequence number, so a hold-duration cap can be aged past its threshold
    without producing an out-of-range ``generated_utc`` seconds field."""
    ladder = EventLadder("KXBTCD-TEST", "2026-09-09T01:30:00Z", 1788917400000, (
        LadderMarket("KXBTCD-TEST", "T1", Decimal("99900"), 0, 1, None),
    ))
    candle = V2BoundRestCandle("shadow-run", CoinbaseMinuteClose(
        1788915480, 1788915540, Decimal("100000"), sequence, "2026-09-09T00:59:01Z"))
    books = {"T1": BookState(sequence, (BookLevel(Decimal(bid_price), Decimal(bid_quantity)),),
                              (BookLevel(Decimal("0.50"), Decimal("1")),))}
    return parse_live_shadow_snapshot(build_live_shadow_snapshot(
        run_id="shadow-run", snapshot_sequence=sequence, generated_utc="2026-09-09T00:59:00Z",
        generated_monotonic_ns=generated_monotonic_ns,
        event_ladder=ladder, candle=candle, books=books))


def test_duration_cap_accepts_a_partial_fill_and_scales_cost_basis_proportionally(monkeypatch):
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *_: candidate,
    )
    entered = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(),
        snapshot=_monotonic_snapshot(
            sequence=1, bid_price="0.40", bid_quantity="1", generated_monotonic_ns=0,
        ),
        first_event_sequence=1, scenario=SHADOW_V2_SCENARIOS[2],
        duration_cap_minutes=Decimal("15"),
    )
    assert entered.state.remaining_quantity == Decimal("1")
    entry_cost = entered.state.entry_cost
    required = entered.state.required_total_net_proceeds

    # Past the 15-minute cap, with only half a contract of visible sell depth,
    # the cap accepts the partial fill instead of holding out for full depth.
    triggered = advance_live_shadow_micro_for_scenario(
        prior=entered.state,
        snapshot=_monotonic_snapshot(
            sequence=2, bid_price="0.40", bid_quantity="0.5",
            generated_monotonic_ns=16 * NS_PER_MINUTE,
        ),
        first_event_sequence=entered.events[-1]["event_sequence"] + 1,
        scenario=SHADOW_V2_SCENARIOS[2], duration_cap_minutes=Decimal("15"),
    )
    assert triggered.events[0]["action"] == "SIMULATED_DURATION_CAP_PARTIAL_EXIT"
    assert triggered.state.remaining_quantity == Decimal("0.5")
    assert triggered.state.entry_cost == entry_cost / 2
    assert triggered.state.required_total_net_proceeds == required / 2
    assert triggered.state.duration_cap_minutes == Decimal("15")
    assert not any(event["event_type"] == "shadow_position_closed" for event in triggered.events)


def test_duration_cap_partial_then_full_exit_accumulates_correct_realized_pnl(monkeypatch):
    """A partial exit does not close the position, so the read model must
    keep accumulating across it rather than settling prematurely -- and it
    enforces this itself: shadow_position_closed may only land once the
    read model's own running quantity is exactly flat. A later exit that
    clears the remainder must still land as one coherent, negative,
    flat trade."""
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *_: candidate,
    )
    entered = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(),
        snapshot=_monotonic_snapshot(
            sequence=1, bid_price="0.40", bid_quantity="1", generated_monotonic_ns=0,
        ),
        first_event_sequence=1, scenario=SHADOW_V2_SCENARIOS[2],
        duration_cap_minutes=Decimal("15"),
    )
    partial = advance_live_shadow_micro_for_scenario(
        prior=entered.state,
        snapshot=_monotonic_snapshot(
            sequence=2, bid_price="0.40", bid_quantity="0.5",
            generated_monotonic_ns=16 * NS_PER_MINUTE,
        ),
        first_event_sequence=entered.events[-1]["event_sequence"] + 1,
        scenario=SHADOW_V2_SCENARIOS[2], duration_cap_minutes=Decimal("15"),
    )
    assert partial.state.remaining_quantity == Decimal("0.5")
    # Full depth is available for the remainder, and the cap is still past
    # threshold, so the rest closes out on the next evaluation.
    closed = advance_live_shadow_micro_for_scenario(
        prior=partial.state,
        snapshot=_monotonic_snapshot(
            sequence=3, bid_price="0.40", bid_quantity="1",
            generated_monotonic_ns=17 * NS_PER_MINUTE,
        ),
        first_event_sequence=partial.events[-1]["event_sequence"] + 1,
        scenario=SHADOW_V2_SCENARIOS[2], duration_cap_minutes=Decimal("15"),
    )
    assert closed.state.remaining_quantity == 0
    projected = project_shadow_ledger_events((*entered.events, *partial.events, *closed.events))
    assert len(projected.trades) == 1
    assert projected.trades[0].simulated_flat is True
    assert projected.trades[0].simulated_net_pnl < 0


def test_duration_cap_forces_a_full_exit_below_target_once_past_the_cap(monkeypatch):
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *_: candidate,
    )
    entered = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(),
        snapshot=_monotonic_snapshot(
            sequence=1, bid_price="0.40", bid_quantity="1", generated_monotonic_ns=0,
        ),
        first_event_sequence=1, scenario=SHADOW_V2_SCENARIOS[2],
        duration_cap_minutes=Decimal("15"),
    )
    # Full sell depth is available, but the book never recovers above the
    # entry price -- an ordinary exit would keep holding forever. Past the
    # cap, the position is forced out anyway, booking the real loss.
    triggered = advance_live_shadow_micro_for_scenario(
        prior=entered.state,
        snapshot=_monotonic_snapshot(
            sequence=2, bid_price="0.40", bid_quantity="1",
            generated_monotonic_ns=16 * NS_PER_MINUTE,
        ),
        first_event_sequence=entered.events[-1]["event_sequence"] + 1,
        scenario=SHADOW_V2_SCENARIOS[2], duration_cap_minutes=Decimal("15"),
    )
    assert triggered.events[0]["action"] == "SIMULATED_DURATION_CAP_FULL_EXIT"
    assert triggered.state.remaining_quantity == 0
    projected = project_shadow_ledger_events((*entered.events, *triggered.events))
    assert projected.trades[0].simulated_flat is True
    assert projected.trades[0].simulated_net_pnl < 0


def test_trailing_lock_gives_back_half_of_peak_gain_then_forces_an_exit(monkeypatch):
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *_: candidate,
    )
    entered = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(), snapshot=snapshot(sequence=1, bid="0.40"),
        first_event_sequence=1, scenario=SHADOW_V2_SCENARIOS[2],
        profit_target_multiplier=Decimal("2.00"),
        trailing_activation_margin=Decimal("0.02"),
    )
    assert entered.state.remaining_quantity == Decimal("1")

    # The book rises well past the 0.02 activation margin (entry ~0.5175) but
    # stays short of the 2.00x retained profit target (~0.5575 required), so
    # only the trailing lock -- never the ordinary profit-target check --
    # can explain a later forced exit.
    risen = advance_live_shadow_micro_for_scenario(
        prior=entered.state, snapshot=snapshot(sequence=2, bid="0.55"),
        first_event_sequence=entered.events[-1]["event_sequence"] + 1,
        scenario=SHADOW_V2_SCENARIOS[2], profit_target_multiplier=Decimal("2.00"),
        trailing_activation_margin=Decimal("0.02"),
    )
    assert risen.state.remaining_quantity == Decimal("1")  # armed, not yet exited
    assert risen.state.peak_favorable_price == Decimal("0.55")

    # The book gives back more than half of that peak gain over entry --
    # well past the 0.01625 give-back tolerance -- so the lock fires.
    given_back = advance_live_shadow_micro_for_scenario(
        prior=risen.state, snapshot=snapshot(sequence=3, bid="0.40"),
        first_event_sequence=risen.events[-1]["event_sequence"] + 1,
        scenario=SHADOW_V2_SCENARIOS[2], profit_target_multiplier=Decimal("2.00"),
        trailing_activation_margin=Decimal("0.02"),
    )
    assert given_back.events[0]["action"] == "SIMULATED_TRAILING_LOCK_FULL_EXIT"
    assert given_back.state.remaining_quantity == 0


def test_trailing_lock_peak_ratchets_up_and_give_back_floor_tracks_the_true_peak(monkeypatch):
    """The lock must not latch onto the FIRST price that cleared the
    activation margin: as the book keeps making new highs, the tracked peak
    -- and the protected floor computed from it -- must keep rising with it.
    A pullback that would NOT have triggered against the (wrong, frozen)
    first-arm peak must still trigger once the true, higher peak is used."""
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *_: candidate,
    )
    entered = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(), snapshot=snapshot(sequence=1, bid="0.40"),
        first_event_sequence=1, scenario=SHADOW_V2_SCENARIOS[2],
        profit_target_multiplier=Decimal("2.00"),
        trailing_activation_margin=Decimal("0.02"),
    )

    # First arm: just past the 0.02 margin (entry ~0.5175), well short of the
    # 2.00x target (~0.5575 required), so no ordinary exit fires here.
    first_rise = advance_live_shadow_micro_for_scenario(
        prior=entered.state, snapshot=snapshot(sequence=2, bid="0.54"),
        first_event_sequence=entered.events[-1]["event_sequence"] + 1,
        scenario=SHADOW_V2_SCENARIOS[2], profit_target_multiplier=Decimal("2.00"),
        trailing_activation_margin=Decimal("0.02"),
    )
    assert first_rise.state.remaining_quantity == Decimal("1")
    assert first_rise.state.peak_favorable_price == Decimal("0.54")

    # A new, higher high -- still short of the target. If the peak wrongly
    # froze at 0.54, this assertion catches it directly.
    second_rise = advance_live_shadow_micro_for_scenario(
        prior=first_rise.state, snapshot=snapshot(sequence=3, bid="0.57"),
        first_event_sequence=first_rise.events[-1]["event_sequence"] + 1,
        scenario=SHADOW_V2_SCENARIOS[2], profit_target_multiplier=Decimal("2.00"),
        trailing_activation_margin=Decimal("0.02"),
    )
    assert second_rise.state.remaining_quantity == Decimal("1")
    assert second_rise.state.peak_favorable_price == Decimal("0.57")

    # Pull back to 0.535: below the true peak's give-back floor
    # (0.57 - (0.57-0.5175)*0.5 = 0.54375, so 0.535 triggers) but ABOVE what
    # the floor would have been off the stale first-arm peak
    # (0.54 - (0.54-0.5175)*0.5 = 0.52875, so 0.535 would NOT have
    # triggered there). Only a correctly ratcheted peak explains a trigger.
    given_back = advance_live_shadow_micro_for_scenario(
        prior=second_rise.state, snapshot=snapshot(sequence=4, bid="0.535"),
        first_event_sequence=second_rise.events[-1]["event_sequence"] + 1,
        scenario=SHADOW_V2_SCENARIOS[2], profit_target_multiplier=Decimal("2.00"),
        trailing_activation_margin=Decimal("0.02"),
    )
    assert given_back.events[0]["action"] == "SIMULATED_TRAILING_LOCK_FULL_EXIT"
    assert given_back.state.remaining_quantity == 0


def test_trailing_lock_does_not_trigger_a_position_that_climbs_straight_to_target(monkeypatch):
    """A position that jumps directly to a price meeting its profit target,
    without ever having a lower peak to give back from, must exit via the
    ordinary profit-target path -- never the trailing lock -- proving the
    lock cannot cut off a legitimate winner that never pulled back."""
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *_: candidate,
    )
    entered = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(), snapshot=snapshot(sequence=1, bid="0.40"),
        first_event_sequence=1, scenario=SHADOW_V2_SCENARIOS[2],
        profit_target_multiplier=Decimal("1.00"),
        trailing_activation_margin=Decimal("0.02"),
    )
    climbed = advance_live_shadow_micro_for_scenario(
        prior=entered.state, snapshot=snapshot(sequence=2, bid="0.70"),
        first_event_sequence=entered.events[-1]["event_sequence"] + 1,
        scenario=SHADOW_V2_SCENARIOS[2], profit_target_multiplier=Decimal("1.00"),
        trailing_activation_margin=Decimal("0.02"),
    )
    assert climbed.events[0]["action"] == "SIMULATED_BACKEND_FULL_EXIT"
    assert climbed.state.remaining_quantity == 0


def _thin_sell_snapshot(*, sequence, bid_price, bid_quantity):
    """A snapshot whose sell-side depth is controllable independent of the
    shared ``snapshot`` helper's fixed quantity, so a stop-loss dip can be
    observed without enough visible depth to actually complete the exit."""
    ladder = EventLadder("KXBTCD-TEST", "2026-09-09T01:30:00Z", 1788917400000, (
        LadderMarket("KXBTCD-TEST", "T1", Decimal("99900"), 0, 1, None),
    ))
    candle = V2BoundRestCandle("shadow-run", CoinbaseMinuteClose(
        1788915480, 1788915540, Decimal("100000"), sequence, "2026-09-09T00:59:01Z"))
    books = {"T1": BookState(sequence, (BookLevel(Decimal(bid_price), Decimal(bid_quantity)),),
                              (BookLevel(Decimal("0.50"), Decimal("1")),))}
    return parse_live_shadow_snapshot(build_live_shadow_snapshot(
        run_id="shadow-run", snapshot_sequence=sequence, generated_utc="2026-09-09T00:59:00Z",
        generated_monotonic_ns=sequence, event_ladder=ladder, candle=candle, books=books))


def test_dynamic_stop_loss_does_not_force_exit_at_a_now_stale_dip(monkeypatch):
    """A stop condition observed while exit depth is incomplete must not be
    remembered: the position must be re-evaluated fresh, purely against the
    current book, once full depth returns."""
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *_: candidate,
    )
    entered = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(), snapshot=snapshot(sequence=2, bid="0.40"),
        first_event_sequence=1, scenario=SHADOW_V2_SCENARIOS[2],
        stop_loss_fraction=Decimal("0.20"),
    )
    assert entered.state.remaining_quantity == 1

    # The book dips well below the stop threshold, but only 0.5 of a contract
    # of depth is visible -- the full 1-contract exit cannot complete.
    thin_dip = advance_live_shadow_micro_for_scenario(
        prior=entered.state, snapshot=_thin_sell_snapshot(sequence=3, bid_price="0.20", bid_quantity="0.5"),
        first_event_sequence=3, scenario=SHADOW_V2_SCENARIOS[2],
        stop_loss_fraction=Decimal("0.20"),
    )
    assert thin_dip.events[0]["reason"] == "FULL_VISIBLE_EXIT_DEPTH_UNAVAILABLE"
    assert thin_dip.state.remaining_quantity == 1

    # Full depth returns and price has recovered above the stop threshold
    # (though still below the retained profit target). This must stay open:
    # the earlier dip must not have latched a pending forced exit.
    recovered = advance_live_shadow_micro_for_scenario(
        prior=thin_dip.state, snapshot=_thin_sell_snapshot(sequence=4, bid_price="0.45", bid_quantity="1"),
        first_event_sequence=4, scenario=SHADOW_V2_SCENARIOS[2],
        stop_loss_fraction=Decimal("0.20"),
    )
    assert recovered.events[0]["reason"] == "VISIBLE_FULL_EXIT_MISSES_RETAINED_TARGET"
    assert recovered.state.remaining_quantity == 1


def test_profit_target_multiplier_scales_the_selected_net_edge(monkeypatch):
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *_: candidate,
    )
    step = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(), snapshot=snapshot(sequence=2, bid="0.40"),
        first_event_sequence=1, scenario=SHADOW_V2_SCENARIOS[2],
        profit_target_multiplier=Decimal("1.50"),
    )
    assert step.state.profit_target_multiplier == Decimal("1.50")
    assert step.state.required_total_net_proceeds == (
        step.state.entry_cost + Decimal("0.03") * step.state.remaining_quantity
    )


def test_hypothetical_resting_exit_reference_is_the_lowest_fee_aware_limit():
    required = Decimal("0.5200")
    quantity = Decimal("1.00")
    limit = _hypothetical_resting_exit_limit(required, quantity)
    assert limit is not None
    assert account_synthetic_fill(
        action="SELL", price=limit, quantity=quantity,
    ).net_cash_change >= required
    assert account_synthetic_fill(
        action="SELL", price=limit - PRICE_QUANTUM, quantity=quantity,
    ).net_cash_change < required


def test_shadow_reentry_requires_a_later_v2_rearm_then_stops_after_second_exit(monkeypatch):
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate",
        lambda _: candidate,
    )
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._reentry_rearm_reason",
        lambda *_: "REFERENCE_EDGE_BELOW_THRESHOLD",
    )

    first_entry = advance_live_shadow_micro(
        prior=LiveShadowMicroState.new(), snapshot=snapshot(sequence=1, bid="0.40"),
        first_event_sequence=1,
    )
    first_exit = advance_live_shadow_micro(
        prior=first_entry.state, snapshot=snapshot(sequence=2, bid="0.70"),
        first_event_sequence=3,
    )
    assert first_exit.state.remaining_quantity == 0
    assert first_exit.state.filled_entry_count == 1
    assert first_exit.state.reentry_reference_market_ticker == "T1"

    rearmed = advance_live_shadow_micro(
        prior=first_exit.state, snapshot=snapshot(sequence=3, bid="0.40"),
        first_event_sequence=6,
    )
    assert rearmed.events[0]["action"] == "SIMULATED_REENTRY_REARMED"
    assert rearmed.events[0]["reentry_number"] == 2
    assert rearmed.events[0]["rearm_reason"] == "REFERENCE_EDGE_BELOW_THRESHOLD"

    same_snapshot = advance_live_shadow_micro(
        prior=rearmed.state, snapshot=snapshot(sequence=3, bid="0.40"),
        first_event_sequence=7,
    )
    assert same_snapshot.events == ()

    second_entry = advance_live_shadow_micro(
        prior=rearmed.state, snapshot=snapshot(sequence=4, bid="0.40"),
        first_event_sequence=7,
    )
    assert second_entry.events[0]["action"] == "SIMULATED_REENTRY_IOC"
    assert second_entry.events[0]["entry_number"] == 2
    assert second_entry.state.filled_entry_count == MAXIMUM_FILLED_ENTRIES_PER_EVENT

    second_exit = advance_live_shadow_micro(
        prior=second_entry.state, snapshot=snapshot(sequence=5, bid="0.70"),
        first_event_sequence=9,
    )
    assert second_exit.state.remaining_quantity == 0
    assert "KXBTCD-TEST" in second_exit.state.closed_event_tickers
    assert advance_live_shadow_micro(
        prior=second_exit.state, snapshot=snapshot(sequence=6, bid="0.40"),
        first_event_sequence=12,
    ).events == ()


def test_shadow_reentry_does_not_evaluate_after_the_live_entry_window_closes(monkeypatch):
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate",
        lambda _: candidate,
    )
    entry = advance_live_shadow_micro(
        prior=LiveShadowMicroState.new(), snapshot=snapshot(sequence=1, bid="0.40"),
        first_event_sequence=1,
    )
    exit_step = advance_live_shadow_micro(
        prior=entry.state, snapshot=snapshot(sequence=2, bid="0.70"),
        first_event_sequence=3,
    )
    late = advance_live_shadow_micro(
        prior=exit_step.state,
        snapshot=snapshot(sequence=3, bid="0.40", generated_utc="2026-09-09T01:22:00Z"),
        first_event_sequence=6,
    )
    assert late.state.reentry_reference_market_ticker == "T1"
    assert late.state.remaining_quantity == 0
    assert late.events == ()


def test_shadow_simulator_caps_a_deep_book_entry_at_one_hundred_dollars(monkeypatch):
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr("src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate", lambda _: candidate)
    state = snapshot(sequence=2, bid="0.40")
    rich = state.__class__(
        state.run_id, state.snapshot_sequence, state.generated_utc, state.generated_monotonic_ns,
        state.event_ladder, state.candle,
        {"T1": BookState(2, (BookLevel(Decimal("0.40"), Decimal("1000")),),
                         (BookLevel(Decimal("0.50"), Decimal("1000")),))},
    )
    step = advance_live_shadow_micro(
        prior=LiveShadowMicroState.new(), snapshot=rich, first_event_sequence=1,
    )
    assert step.state.entry_cost <= SIMULATED_ENTRY_BUDGET_DOLLARS
    assert step.state.entry_cost > Decimal("99")
    assert step.events[0]["simulated_entry_budget_dollars"] == "100.00"


def test_edge_scenarios_share_observed_snapshot_path_but_keep_distinct_ids(monkeypatch):
    candidate = ShadowV2Selection(
        "T1", "YES", Decimal("0.05"),
        SimpleNamespace(decision_limit_price=Decimal("0.50")),
    )
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda _state, _scenario: candidate,
    )
    common_snapshot = snapshot(sequence=2, bid="0.40")
    rows = []
    for scenario in SHADOW_V2_SCENARIOS:
        step = advance_live_shadow_micro_for_scenario(
            prior=LiveShadowMicroState.new(),
            snapshot=common_snapshot,
            first_event_sequence=1,
            scenario=scenario,
        )
        assert step.state.remaining_quantity == Decimal("1")
        assert step.events[0]["input_snapshot_sequence"] == 2
        assert step.events[0]["execution_timing_basis"] == "OBSERVED_SHADOW_PATH"
        rows.append(step.events[0]["scenario_id"])
    assert rows == [scenario.scenario_id for scenario in SHADOW_V2_SCENARIOS]


def test_shadow_simulator_quietly_skips_new_entries_outside_the_frozen_window():
    step = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(),
        snapshot=snapshot(
            sequence=1, bid="0.40", generated_utc="2026-09-09T01:29:00Z",
        ),
        first_event_sequence=1,
        scenario=SHADOW_V2_SCENARIOS[0],
    )
    assert step.state == LiveShadowMicroState.new()
    assert step.events == ()
    assert step.state.decision_diagnostics.snapshots_evaluated == 1
    assert step.state.decision_diagnostics.outside_entry_window == 1


def test_shadow_simulator_keeps_bounded_near_miss_diagnostics(monkeypatch):
    side = SimpleNamespace(side="YES", depth_qualifies=True, net_edge=Decimal("0.019"))
    evaluation = SimpleNamespace(status="EVALUABLE", sides=(side,))
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._evaluations",
        lambda _: (evaluation,),
    )
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *_: None,
    )
    step = advance_live_shadow_micro_for_scenario(
        prior=LiveShadowMicroState.new(), snapshot=snapshot(sequence=1, bid="0.40"),
        first_event_sequence=1, scenario=SHADOW_V2_SCENARIOS[2],
    )
    diagnostics = step.state.decision_diagnostics
    assert step.events == ()
    assert diagnostics.snapshots_evaluated == 1
    assert diagnostics.edge_below_threshold == 1
    assert diagnostics.max_yes_net_edge == Decimal("0.019")
    assert diagnostics.closest_net_edge_deficit == Decimal("0.001")


def test_shadow_simulator_allows_ten_minutes_but_not_later_entries(monkeypatch):
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr("src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate", lambda _: candidate)
    exact_ten_minutes = advance_live_shadow_micro(
        prior=LiveShadowMicroState.new(),
        snapshot=snapshot(sequence=1, bid="0.40", generated_utc="2026-09-09T01:20:00Z"),
        first_event_sequence=1,
    )
    later_than_ten_minutes = advance_live_shadow_micro(
        prior=LiveShadowMicroState.new(),
        snapshot=snapshot(sequence=2, bid="0.40", generated_utc="2026-09-09T01:20:01Z"),
        first_event_sequence=1,
    )
    assert exact_ten_minutes.state.remaining_quantity == Decimal("1")
    assert later_than_ten_minutes.state == LiveShadowMicroState.new()
    assert later_than_ten_minutes.events == ()


def test_new_event_can_enter_while_prior_event_awaits_official_settlement(monkeypatch):
    candidate = ShadowV2Selection("T1", "YES", Decimal("0.02"),
                                  SimpleNamespace(decision_limit_price=Decimal("0.50")))
    monkeypatch.setattr("src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate", lambda _: candidate)
    first = advance_live_shadow_micro(
        prior=LiveShadowMicroState.new(), snapshot=snapshot(sequence=1, bid="0.40"),
        first_event_sequence=1,
    )
    prior_snapshot = snapshot(sequence=2, bid="0.40", generated_utc="2026-09-09T02:20:00Z")
    next_event = prior_snapshot.__class__(
        prior_snapshot.run_id, prior_snapshot.snapshot_sequence, prior_snapshot.generated_utc,
        prior_snapshot.generated_monotonic_ns,
        EventLadder("KXBTCD-NEXT", "2026-09-09T02:30:00Z", 1788921000000, (
            LadderMarket("KXBTCD-NEXT", "T1", Decimal("99900"), 0, 1, None),
        )),
        prior_snapshot.candle, prior_snapshot.books,
    )
    second = advance_live_shadow_micro(
        prior=first.state, snapshot=next_event, first_event_sequence=3,
    )
    assert second.state.event_ticker == "KXBTCD-NEXT"
    assert second.state.remaining_quantity == Decimal("1")
    assert len(second.state.pending_settlements) == 1
    assert second.state.pending_settlements[0].event_ticker == "KXBTCD-TEST"
    assert second.events[0]["event_type"] == "shadow_position_awaiting_official_settlement"
    assert second.events[1]["action"] == "SIMULATED_ENTRY_IOC"
