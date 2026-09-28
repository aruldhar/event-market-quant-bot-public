import pytest

from src.kxbtcd_candidate_e_soak_source_lifecycle import (
    KalshiHourlySuccessorUnavailable,
    RECONNECT_BACKOFF_SECONDS,
    ReconnectBackoff,
    SoakSourceLifecycleError,
    classify_event_rollover,
    choose_current_event_ladder,
    reconnect_delay_seconds,
)


def test_frozen_backoff_sequence_and_cap():
    observed = [
        reconnect_delay_seconds(i)
        for i in range(1, 9)
    ]

    assert observed == [
        1, 2, 4, 8, 15, 15, 15, 15
    ]

    assert RECONNECT_BACKOFF_SECONDS == (
        1, 2, 4, 8, 15
    )


def test_failure_schedules_retry_from_monotonic_time():
    backoff = ReconnectBackoff()

    decision = backoff.record_failure(
        observed_monotonic_ns=10_000_000_000
    )

    assert decision.consecutive_failures == 1
    assert decision.delay_seconds == 1
    assert (
        decision.retry_not_before_monotonic_ns
        == 11_000_000_000
    )

    assert not backoff.retry_allowed(
        now_monotonic_ns=10_999_999_999
    )

    assert backoff.retry_allowed(
        now_monotonic_ns=11_000_000_000
    )


def test_socket_open_alone_does_not_reset_backoff():
    backoff = ReconnectBackoff()

    backoff.record_failure(
        observed_monotonic_ns=1
    )

    # There intentionally is no "connection_opened" reset.
    second = backoff.record_failure(
        observed_monotonic_ns=2_000_000_000
    )

    assert second.consecutive_failures == 2
    assert second.delay_seconds == 2


def test_readiness_pass_resets_backoff():
    backoff = ReconnectBackoff()

    backoff.record_failure(
        observed_monotonic_ns=1
    )
    backoff.record_failure(
        observed_monotonic_ns=2_000_000_000
    )

    backoff.readiness_passed()

    next_failure = backoff.record_failure(
        observed_monotonic_ns=10_000_000_000
    )

    assert next_failure.consecutive_failures == 1
    assert next_failure.delay_seconds == 1


def test_intentional_rollover_allows_immediate_attempt_without_fake_pass():
    backoff = ReconnectBackoff()

    backoff.record_failure(
        observed_monotonic_ns=10_000_000_000
    )

    assert not backoff.retry_allowed(
        now_monotonic_ns=10_500_000_000
    )

    backoff.intentional_rollover()

    assert backoff.retry_allowed(
        now_monotonic_ns=10_500_000_000
    )

    # Rollover did not fabricate source-health success.
    next_failure = backoff.record_failure(
        observed_monotonic_ns=10_500_000_000
    )

    assert next_failure.consecutive_failures == 2
    assert next_failure.delay_seconds == 2


def test_event_close_requires_rollover():
    decision = classify_event_rollover(
        current_event_ticker="KXBTCD-OLD",
        current_event_close_timestamp_ms=1000,
        now_timestamp_ms=1000,
    )

    assert decision.rollover_required
    assert decision.reason == "SELECTED_EVENT_CLOSED"


def test_rediscovery_change_requires_rollover_before_close():
    decision = classify_event_rollover(
        current_event_ticker="KXBTCD-A",
        current_event_close_timestamp_ms=5000,
        now_timestamp_ms=1000,
        rediscovered_current_event_ticker="KXBTCD-B",
    )

    assert decision.rollover_required
    assert (
        decision.reason
        == "SELECTED_EVENT_NO_LONGER_CURRENT"
    )


def test_same_rediscovered_event_does_not_roll():
    decision = classify_event_rollover(
        current_event_ticker="KXBTCD-A",
        current_event_close_timestamp_ms=5000,
        now_timestamp_ms=1000,
        rediscovered_current_event_ticker="KXBTCD-A",
    )

    assert not decision.rollover_required
    assert (
        decision.reason
        == "CURRENT_EVENT_STILL_VALID"
    )


def test_no_rediscovery_and_not_closed_does_not_roll():
    decision = classify_event_rollover(
        current_event_ticker="KXBTCD-A",
        current_event_close_timestamp_ms=5000,
        now_timestamp_ms=1000,
    )

    assert not decision.rollover_required


@pytest.mark.parametrize(
    "value",
    [0, -1, True, 1.5],
)
def test_invalid_failure_count_rejected(value):
    with pytest.raises(
        SoakSourceLifecycleError
    ):
        reconnect_delay_seconds(value)



class FakeEvent:
    def __init__(self, ticker, close_ms):
        self.event_ticker = ticker
        self.close_timestamp_ms = close_ms


def test_current_event_selector_chooses_earliest_future_event():
    events = (
        FakeEvent("KXBTCD-LATER", 9000),
        FakeEvent("KXBTCD-NEXT", 5000),
        FakeEvent("KXBTCD-OLD", 1000),
    )

    selected = choose_current_event_ladder(
        events,
        now_timestamp_ms=2000,
    )

    assert selected.event_ticker == "KXBTCD-NEXT"


def test_current_event_selector_is_stable_under_input_order():
    a = FakeEvent("KXBTCD-A", 5000)
    b = FakeEvent("KXBTCD-B", 7000)

    first = choose_current_event_ladder(
        (a, b),
        now_timestamp_ms=1000,
    )

    second = choose_current_event_ladder(
        (b, a),
        now_timestamp_ms=1000,
    )

    assert first.event_ticker == "KXBTCD-A"
    assert second.event_ticker == "KXBTCD-A"


def test_current_event_selector_uses_ticker_only_as_deterministic_tiebreak():
    a = FakeEvent("KXBTCD-B", 5000)
    b = FakeEvent("KXBTCD-A", 5000)

    selected = choose_current_event_ladder(
        (a, b),
        now_timestamp_ms=1000,
    )

    assert selected.event_ticker == "KXBTCD-A"


def test_current_event_selector_rejects_when_none_future():
    with pytest.raises(
        SoakSourceLifecycleError,
        match="no active/future",
    ):
        choose_current_event_ladder(
            (
                FakeEvent("KXBTCD-A", 1000),
                FakeEvent("KXBTCD-B", 2000),
            ),
            now_timestamp_ms=2000,
        )


def test_current_event_selector_waits_for_a_near_term_hourly_successor():
    with pytest.raises(KalshiHourlySuccessorUnavailable, match="near-term hourly"):
        choose_current_event_ladder(
            (FakeEvent("KXBTCD-TOMORROW", 100 * 60 * 1000),),
            now_timestamp_ms=0,
        )


def test_current_event_selector_does_not_require_strategy_fields():
    # FakeEvent intentionally has no probability, TTC-entry-window,
    # market-price, liquidity, edge, or settlement attributes.
    selected = choose_current_event_ladder(
        (
            FakeEvent("KXBTCD-A", 3000),
            FakeEvent("KXBTCD-B", 4000),
        ),
        now_timestamp_ms=1000,
    )

    assert selected.event_ticker == "KXBTCD-A"
