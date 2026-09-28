from decimal import Decimal
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_coinbase_ws_minute_builder import (
    CoinbaseMinuteBuilder,
)
from src.kxbtcd_candidate_e_prospective_live_collector import (
    EventLadder,
    KalshiBookCache,
)
from src.kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import (
    LadderMarket,
)
from src.kxbtcd_candidate_e_restart_gate_state_machine import (
    CohortStatus,
    GateStatus,
    resolve_restart_state,
)
from src.kxbtcd_candidate_e_restart_source_readiness import (
    KALSHI_WS_MAX_PONG_AGE_NS,
    build_current_source_gate_snapshot,
    evaluate_coinbase_readiness,
    evaluate_kalshi_readiness,
    evaluate_kalshi_transport_liveness,
    parse_chronyc_tracking,
    resolve_boot_identity,
)


SESSION = "runtime-session-b4"
SYNTH_BOOT = "12345678-1234-5678-1234-567812345678"
COINBASE_CONNECTION_GENERATION = 1
KALSHI_CONNECTION_GENERATION = 1


def ready_transport(
    *,
    generation=KALSHI_CONNECTION_GENERATION,
    connected=True,
    last_pong_monotonic_ns=1_000_000_000,
    now_monotonic_ns=2_000_000_000,
    runtime_session_id=SESSION,
):
    return evaluate_kalshi_transport_liveness(
        runtime_session_id=runtime_session_id,
        connection_generation=generation,
        connected=connected,
        last_pong_monotonic_ns=last_pong_monotonic_ns,
        now_monotonic_ns=now_monotonic_ns,
    )


def test_validation_boot_id_requires_explicit_injection():
    result = resolve_boot_identity(
        validation_mode=True,
        injected_synthetic_boot_id=None,
        platform_system="Windows",
    )
    assert result.status == GateStatus.BLOCKED


def test_validation_boot_id_accepts_explicit_synthetic_uuid():
    result = resolve_boot_identity(
        validation_mode=True,
        injected_synthetic_boot_id=SYNTH_BOOT,
        platform_system="Windows",
    )
    assert result.status == GateStatus.PASS
    assert result.validation_only is True


def test_production_forbids_synthetic_boot_id():
    result = resolve_boot_identity(
        validation_mode=False,
        injected_synthetic_boot_id=SYNTH_BOOT,
        platform_system="Linux",
    )
    assert result.status == GateStatus.FATAL


def test_production_non_linux_boot_id_blocks():
    result = resolve_boot_identity(
        validation_mode=False,
        platform_system="Windows",
    )
    assert result.status == GateStatus.BLOCKED


def test_linux_boot_id_file_passes(tmp_path):
    p = tmp_path / "boot_id"
    p.write_text(SYNTH_BOOT + "\n", encoding="utf-8")
    result = resolve_boot_identity(
        validation_mode=False,
        platform_system="Linux",
        production_boot_id_path=p,
    )
    assert result.status == GateStatus.PASS
    assert result.validation_only is False


def test_linux_missing_boot_id_blocks(tmp_path):
    result = resolve_boot_identity(
        validation_mode=False,
        platform_system="Linux",
        production_boot_id_path=tmp_path / "missing",
    )
    assert result.status == GateStatus.BLOCKED


def chrony(system_time_line, leap="Normal"):
    return (
        "Reference ID    : 01020304 (test)\n"
        "Stratum         : 3\n"
        f"System time     : {system_time_line}\n"
        f"Leap status     : {leap}\n"
    )


def test_chrony_250ms_exactly_passes():
    result = parse_chronyc_tracking(
        chrony("0.250000000 seconds fast of NTP time")
    )
    assert result.status == GateStatus.PASS
    assert result.absolute_system_time_offset_ms == pytest.approx(250.0)


def test_chrony_negative_direction_is_absolute_for_gate():
    result = parse_chronyc_tracking(
        chrony("0.250000000 seconds slow of NTP time")
    )
    assert result.status == GateStatus.PASS
    assert result.signed_system_time_offset_ms == pytest.approx(-250.0)


def test_chrony_over_250ms_blocks():
    result = parse_chronyc_tracking(
        chrony("0.250001000 seconds fast of NTP time")
    )
    assert result.status == GateStatus.BLOCKED


def test_chrony_not_synchronised_blocks():
    result = parse_chronyc_tracking(
        chrony(
            "0.000001000 seconds slow of NTP time",
            leap="Not synchronised",
        )
    )
    assert result.status == GateStatus.BLOCKED
    assert result.reason == "CHRONY_NOT_SYNCHRONIZED"


def test_chrony_missing_system_time_blocks():
    result = parse_chronyc_tracking(
        "Leap status     : Normal\n"
    )
    assert result.status == GateStatus.BLOCKED


def ws_last_match(
    *,
    trade_id=100,
    sequence=1000,
    time="2026-09-04T06:30:10Z",
    price="80000",
):
    return {
        "type": "last_match",
        "product_id": "BTC-USD",
        "trade_id": trade_id,
        "sequence": sequence,
        "time": time,
        "price": price,
        "size": "0.001",
        "side": "buy",
    }


def ws_match(
    *,
    trade_id,
    sequence,
    time,
    price,
):
    return {
        "type": "match",
        "product_id": "BTC-USD",
        "trade_id": trade_id,
        "sequence": sequence,
        "time": time,
        "price": price,
        "size": "0.001",
        "side": "buy",
    }


def heartbeat(
    *,
    trade_id,
    sequence,
    time,
):
    return {
        "type": "heartbeat",
        "product_id": "BTC-USD",
        "last_trade_id": trade_id,
        "sequence": sequence,
        "time": time,
    }


def ready_builder():
    builder = CoinbaseMinuteBuilder()
    builder.apply_ws(
        ws_last_match(),
        received_monotonic_ns=100,
    )
    builder.apply_ws(
        ws_match(
            trade_id=101,
            sequence=1001,
            time="2026-09-04T06:30:50Z",
            price="80010",
        ),
        received_monotonic_ns=200,
    )
    builder.apply_ws(
        heartbeat(
            trade_id=101,
            sequence=1002,
            time="2026-09-04T06:31:01Z",
        ),
        received_monotonic_ns=1_000_000_000,
    )
    return builder


def test_coinbase_exact_current_completed_minute_passes():
    evidence = evaluate_coinbase_readiness(
        builder=ready_builder(),
        runtime_session_id=SESSION,
        builder_runtime_session_id=SESSION,
        current_connection_generation=COINBASE_CONNECTION_GENERATION,
        builder_connection_generation=COINBASE_CONNECTION_GENERATION,
        decision_epoch_s=(
            1788503465  # 2026-09-04T06:31:05Z
        ),
        now_monotonic_ns=2_000_000_000,
    )
    assert evidence.status == GateStatus.PASS
    assert evidence.builder_status == "AVAILABLE"
    assert evidence.close_trade_id == 101


def test_coinbase_wrong_runtime_session_blocks():
    evidence = evaluate_coinbase_readiness(
        builder=ready_builder(),
        runtime_session_id=SESSION,
        builder_runtime_session_id="old-session",
        current_connection_generation=COINBASE_CONNECTION_GENERATION,
        builder_connection_generation=COINBASE_CONNECTION_GENERATION,
        decision_epoch_s=1788503465,
        now_monotonic_ns=2_000_000_000,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert "CURRENT_RUNTIME_SESSION" in evidence.reason


def test_coinbase_stale_heartbeat_blocks():
    evidence = evaluate_coinbase_readiness(
        builder=ready_builder(),
        runtime_session_id=SESSION,
        builder_runtime_session_id=SESSION,
        current_connection_generation=COINBASE_CONNECTION_GENERATION,
        builder_connection_generation=COINBASE_CONNECTION_GENERATION,
        decision_epoch_s=1788503465,
        now_monotonic_ns=4_000_000_001,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.builder_status == "HEARTBEAT_STALE"


def test_coinbase_recovery_required_blocks():
    builder = ready_builder()
    builder.apply_ws(
        heartbeat(
            trade_id=105,
            sequence=1003,
            time="2026-09-04T06:31:02Z",
        ),
        received_monotonic_ns=1_100_000_000,
    )
    evidence = evaluate_coinbase_readiness(
        builder=builder,
        runtime_session_id=SESSION,
        builder_runtime_session_id=SESSION,
        current_connection_generation=COINBASE_CONNECTION_GENERATION,
        builder_connection_generation=COINBASE_CONNECTION_GENERATION,
        decision_epoch_s=1788503465,
        now_monotonic_ns=2_000_000_000,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.builder_status == "RECOVERY_REQUIRED"


def test_coinbase_no_trade_target_minute_blocks():
    builder = CoinbaseMinuteBuilder()
    builder.apply_ws(
        ws_last_match(
            trade_id=100,
            sequence=1000,
            time="2026-09-04T06:29:50Z",
        ),
        received_monotonic_ns=100,
    )
    builder.apply_ws(
        heartbeat(
            trade_id=100,
            sequence=1001,
            time="2026-09-04T06:31:01Z",
        ),
        received_monotonic_ns=1_000_000_000,
    )
    evidence = evaluate_coinbase_readiness(
        builder=builder,
        runtime_session_id=SESSION,
        builder_runtime_session_id=SESSION,
        current_connection_generation=COINBASE_CONNECTION_GENERATION,
        builder_connection_generation=COINBASE_CONNECTION_GENERATION,
        decision_epoch_s=1788503465,
        now_monotonic_ns=2_000_000_000,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.builder_status == "NO_TRADES_IN_MINUTE"


def event():
    return EventLadder(
        event_ticker="KXBTCD-26SEP0407",
        close_time_utc="2026-09-04T07:00:00Z",
        close_timestamp_ms=1788505200000,
        markets=(
            LadderMarket(
                event_ticker="KXBTCD-26SEP0407",
                market_ticker="KXBTCD-26SEP0407-T79999.99",
                strike=Decimal("80000"),
                strike_rank_zero_based=0,
                event_market_count=2,
                historical_structural_role=None,
            ),
            LadderMarket(
                event_ticker="KXBTCD-26SEP0407",
                market_ticker="KXBTCD-26SEP0407-T80999.99",
                strike=Decimal("81000"),
                strike_rank_zero_based=1,
                event_market_count=2,
                historical_structural_role=None,
            ),
        ),
    )


def snapshot(seq, ticker):
    return {
        "type": "orderbook_snapshot",
        "seq": seq,
        "msg": {
            "market_ticker": ticker,
            "yes_dollars_fp": [["0.50", "10"]],
            "no_dollars_fp": [["0.49", "10"]],
        },
    }


def ready_cache():
    e = event()
    tickers = tuple(m.market_ticker for m in e.markets)
    cache = KalshiBookCache(tickers)
    cache.apply_message({
        "type": "subscribed",
        "msg": {
            "channel": "orderbook_delta",
            "sid": 77,
        },
    })
    cache.apply_message(snapshot(1, tickers[0]))
    cache.apply_message(snapshot(2, tickers[1]))
    assert cache.all_ready()
    return cache


def test_kalshi_exact_current_ladder_passes():
    evidence = evaluate_kalshi_readiness(
        cache=ready_cache(),
        current_event=event(),
        runtime_session_id=SESSION,
        discovery_runtime_session_id=SESSION,
        cache_runtime_session_id=SESSION,
        cache_connection_generation=KALSHI_CONNECTION_GENERATION,
        transport_liveness=ready_transport(),
        now_ms=1788503465000,
    )
    assert evidence.status == GateStatus.PASS


def test_kalshi_old_session_cache_blocks():
    evidence = evaluate_kalshi_readiness(
        cache=ready_cache(),
        current_event=event(),
        runtime_session_id=SESSION,
        discovery_runtime_session_id=SESSION,
        cache_runtime_session_id="old-session",
        cache_connection_generation=KALSHI_CONNECTION_GENERATION,
        transport_liveness=ready_transport(),
        now_ms=1788503465000,
    )
    assert evidence.status == GateStatus.BLOCKED


def test_kalshi_missing_subscription_sid_blocks():
    cache = ready_cache()
    cache.subscription_sid = None
    evidence = evaluate_kalshi_readiness(
        cache=cache,
        current_event=event(),
        runtime_session_id=SESSION,
        discovery_runtime_session_id=SESSION,
        cache_runtime_session_id=SESSION,
        cache_connection_generation=KALSHI_CONNECTION_GENERATION,
        transport_liveness=ready_transport(),
        now_ms=1788503465000,
    )
    assert evidence.status == GateStatus.BLOCKED


def test_kalshi_sequence_gap_invalidates_all_and_blocks():
    cache = ready_cache()
    first = event().markets[0].market_ticker
    cache.apply_message({
        "type": "orderbook_delta",
        "seq": 4,  # gap: expected 3
        "msg": {
            "market_ticker": first,
            "side": "yes",
            "price_dollars": "0.50",
            "delta_fp": "1",
            "ts_ms": 1788503465000,
        },
    })
    assert cache.resync_required is True
    evidence = evaluate_kalshi_readiness(
        cache=cache,
        current_event=event(),
        runtime_session_id=SESSION,
        discovery_runtime_session_id=SESSION,
        cache_runtime_session_id=SESSION,
        cache_connection_generation=KALSHI_CONNECTION_GENERATION,
        transport_liveness=ready_transport(),
        now_ms=1788503465000,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "KALSHI_RESYNC_REQUIRED"


def test_kalshi_subscription_must_equal_current_ladder():
    e = event()
    cache = KalshiBookCache(
        (e.markets[0].market_ticker,)
    )
    evidence = evaluate_kalshi_readiness(
        cache=cache,
        current_event=e,
        runtime_session_id=SESSION,
        discovery_runtime_session_id=SESSION,
        cache_runtime_session_id=SESSION,
        cache_connection_generation=KALSHI_CONNECTION_GENERATION,
        transport_liveness=ready_transport(),
        now_ms=1788503465000,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert "EXACT_CURRENT_LADDER" in evidence.reason


def test_kalshi_expired_event_blocks():
    evidence = evaluate_kalshi_readiness(
        cache=ready_cache(),
        current_event=event(),
        runtime_session_id=SESSION,
        discovery_runtime_session_id=SESSION,
        cache_runtime_session_id=SESSION,
        cache_connection_generation=KALSHI_CONNECTION_GENERATION,
        transport_liveness=ready_transport(),
        now_ms=1788505200000,
    )
    assert evidence.status == GateStatus.BLOCKED



def test_kalshi_transport_missing_pong_blocks():
    evidence = evaluate_kalshi_transport_liveness(
        runtime_session_id=SESSION,
        connection_generation=KALSHI_CONNECTION_GENERATION,
        connected=True,
        last_pong_monotonic_ns=None,
        now_monotonic_ns=2_000_000_000,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "KALSHI_CURRENT_CONNECTION_PONG_NOT_PROVEN"


def test_kalshi_transport_disconnected_blocks():
    evidence = ready_transport(connected=False)
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "KALSHI_WEBSOCKET_NOT_CONNECTED"


def test_kalshi_transport_pong_age_boundary_passes():
    now_ns = KALSHI_WS_MAX_PONG_AGE_NS + 1_000_000_000
    evidence = ready_transport(
        last_pong_monotonic_ns=1_000_000_000,
        now_monotonic_ns=now_ns,
    )
    assert evidence.status == GateStatus.PASS
    assert evidence.pong_age_ns == KALSHI_WS_MAX_PONG_AGE_NS


def test_kalshi_transport_pong_over_frozen_window_blocks():
    now_ns = KALSHI_WS_MAX_PONG_AGE_NS + 1_000_000_001
    evidence = ready_transport(
        last_pong_monotonic_ns=1_000_000_000,
        now_monotonic_ns=now_ns,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "KALSHI_PONG_STALE"


def test_kalshi_transport_monotonic_regression_is_fatal():
    evidence = ready_transport(
        last_pong_monotonic_ns=2_000_000_001,
        now_monotonic_ns=2_000_000_000,
    )
    assert evidence.status == GateStatus.FATAL


def test_kalshi_old_connection_cache_blocks_even_same_process_session():
    evidence = evaluate_kalshi_readiness(
        cache=ready_cache(),
        current_event=event(),
        runtime_session_id=SESSION,
        discovery_runtime_session_id=SESSION,
        cache_runtime_session_id=SESSION,
        cache_connection_generation=1,
        transport_liveness=ready_transport(generation=2),
        now_ms=1788503465000,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == (
        "KALSHI_CACHE_NOT_FROM_CURRENT_CONNECTION_GENERATION"
    )


def test_kalshi_transport_pong_does_not_heal_sequence_gap():
    cache = ready_cache()
    first = event().markets[0].market_ticker
    cache.apply_message({
        "type": "orderbook_delta",
        "seq": 4,
        "msg": {
            "market_ticker": first,
            "side": "yes",
            "price_dollars": "0.50",
            "delta_fp": "1",
            "ts_ms": 1788503465000,
        },
    })
    assert cache.resync_required is True

    evidence = evaluate_kalshi_readiness(
        cache=cache,
        current_event=event(),
        runtime_session_id=SESSION,
        discovery_runtime_session_id=SESSION,
        cache_runtime_session_id=SESSION,
        cache_connection_generation=KALSHI_CONNECTION_GENERATION,
        transport_liveness=ready_transport(),
        now_ms=1788503465000,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "KALSHI_RESYNC_REQUIRED"


def test_coinbase_old_connection_builder_blocks_even_same_process_session():
    evidence = evaluate_coinbase_readiness(
        builder=ready_builder(),
        runtime_session_id=SESSION,
        builder_runtime_session_id=SESSION,
        current_connection_generation=2,
        builder_connection_generation=1,
        decision_epoch_s=1788503465,
        now_monotonic_ns=2_000_000_000,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == (
        "COINBASE_STATE_NOT_FROM_CURRENT_CONNECTION_GENERATION"
    )


def test_combined_current_sources_can_reach_ready():
    boot = resolve_boot_identity(
        validation_mode=True,
        injected_synthetic_boot_id=SYNTH_BOOT,
        platform_system="Windows",
    )
    clock = parse_chronyc_tracking(
        chrony("0.010000000 seconds fast of NTP time")
    )
    cb = evaluate_coinbase_readiness(
        builder=ready_builder(),
        runtime_session_id=SESSION,
        builder_runtime_session_id=SESSION,
        current_connection_generation=COINBASE_CONNECTION_GENERATION,
        builder_connection_generation=COINBASE_CONNECTION_GENERATION,
        decision_epoch_s=1788503465,
        now_monotonic_ns=2_000_000_000,
    )
    ka = evaluate_kalshi_readiness(
        cache=ready_cache(),
        current_event=event(),
        runtime_session_id=SESSION,
        discovery_runtime_session_id=SESSION,
        cache_runtime_session_id=SESSION,
        cache_connection_generation=KALSHI_CONNECTION_GENERATION,
        transport_liveness=ready_transport(),
        now_ms=1788503465000,
    )

    snap = build_current_source_gate_snapshot(
        frozen_identity_status=GateStatus.PASS,
        boot_identity=boot,
        cohort_status=CohortStatus.ACTIVE,
        durability_status=GateStatus.PASS,
        clock_evidence=clock,
        coinbase_evidence=cb,
        kalshi_evidence=ka,
        strategy_reconciliation_status=GateStatus.PASS,
    )
    assert resolve_restart_state(snap) == "READY_READ_ONLY"


def test_coinbase_block_maps_to_blocked_coinbase():
    boot = resolve_boot_identity(
        validation_mode=True,
        injected_synthetic_boot_id=SYNTH_BOOT,
        platform_system="Windows",
    )
    clock = parse_chronyc_tracking(
        chrony("0.010000000 seconds fast of NTP time")
    )
    cb = evaluate_coinbase_readiness(
        builder=ready_builder(),
        runtime_session_id=SESSION,
        builder_runtime_session_id="old",
        current_connection_generation=COINBASE_CONNECTION_GENERATION,
        builder_connection_generation=COINBASE_CONNECTION_GENERATION,
        decision_epoch_s=1788503465,
        now_monotonic_ns=2_000_000_000,
    )
    ka = evaluate_kalshi_readiness(
        cache=ready_cache(),
        current_event=event(),
        runtime_session_id=SESSION,
        discovery_runtime_session_id=SESSION,
        cache_runtime_session_id=SESSION,
        cache_connection_generation=KALSHI_CONNECTION_GENERATION,
        transport_liveness=ready_transport(),
        now_ms=1788503465000,
    )
    snap = build_current_source_gate_snapshot(
        frozen_identity_status=GateStatus.PASS,
        boot_identity=boot,
        cohort_status=CohortStatus.ACTIVE,
        durability_status=GateStatus.PASS,
        clock_evidence=clock,
        coinbase_evidence=cb,
        kalshi_evidence=ka,
        strategy_reconciliation_status=GateStatus.PASS,
    )
    assert resolve_restart_state(snap) == "BLOCKED_COINBASE"


def test_kalshi_block_maps_to_blocked_kalshi():
    boot = resolve_boot_identity(
        validation_mode=True,
        injected_synthetic_boot_id=SYNTH_BOOT,
        platform_system="Windows",
    )
    clock = parse_chronyc_tracking(
        chrony("0.010000000 seconds fast of NTP time")
    )
    cb = evaluate_coinbase_readiness(
        builder=ready_builder(),
        runtime_session_id=SESSION,
        builder_runtime_session_id=SESSION,
        current_connection_generation=COINBASE_CONNECTION_GENERATION,
        builder_connection_generation=COINBASE_CONNECTION_GENERATION,
        decision_epoch_s=1788503465,
        now_monotonic_ns=2_000_000_000,
    )
    cache = ready_cache()
    cache.subscription_sid = None
    ka = evaluate_kalshi_readiness(
        cache=cache,
        current_event=event(),
        runtime_session_id=SESSION,
        discovery_runtime_session_id=SESSION,
        cache_runtime_session_id=SESSION,
        cache_connection_generation=KALSHI_CONNECTION_GENERATION,
        transport_liveness=ready_transport(),
        now_ms=1788503465000,
    )
    snap = build_current_source_gate_snapshot(
        frozen_identity_status=GateStatus.PASS,
        boot_identity=boot,
        cohort_status=CohortStatus.ACTIVE,
        durability_status=GateStatus.PASS,
        clock_evidence=clock,
        coinbase_evidence=cb,
        kalshi_evidence=ka,
        strategy_reconciliation_status=GateStatus.PASS,
    )
    assert resolve_restart_state(snap) == "BLOCKED_KALSHI"
