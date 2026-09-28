from decimal import Decimal

from src.kxbtcd_candidate_e_coinbase_rest_seed import (
    BoundCoinbaseRestCandleSeed,
    bind_rest_candle_seed,
    evaluate_coinbase_with_rest_seed,
)
from src.kxbtcd_candidate_e_prospective_live_collector import (
    CoinbaseMinuteClose,
)
from src.kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from src.kxbtcd_candidate_e_restart_source_readiness import (
    CoinbaseReadinessEvidence,
)


# Exact UTC-minute boundary required by the frozen 60-second
# Coinbase REST-candle seed contract.
TARGET = 1_725_550_920

assert TARGET % 60 == 0


def minute():
    return CoinbaseMinuteClose(
        minute_start_s=TARGET,
        minute_end_s=TARGET + 60,
        close_price=Decimal("110123.45"),
        available_monotonic_ns=10_000,
        raw_received_utc="2026-09-04T15:10:01Z",
    )


def blocked(
    builder_status="NO_TRADES_IN_MINUTE",
):
    return CoinbaseReadinessEvidence(
        status=GateStatus.BLOCKED,
        reason=f"COINBASE_{builder_status}",
        target_minute_start_s=TARGET,
        target_minute_end_s=TARGET + 60,
        builder_status=builder_status,
        close_trade_id=None,
        connection_generation=3,
    )


def seed():
    return bind_rest_candle_seed(
        runtime_session_id="runtime-a",
        connection_generation=3,
        minute=minute(),
    )


def test_exact_current_generation_seed_can_satisfy_no_trades_block():
    result = evaluate_coinbase_with_rest_seed(
        base_evidence=blocked(),
        seed=seed(),
        runtime_session_id="runtime-a",
        current_connection_generation=3,
        now_monotonic_ns=20_000,
    )

    assert result.status == GateStatus.PASS
    assert result.reason == "PASS"
    assert result.builder_status == "REST_CANDLE_SEED"
    assert result.close_trade_id is None


def test_rest_seed_does_not_override_recovery_required():
    result = evaluate_coinbase_with_rest_seed(
        base_evidence=blocked(
            "RECOVERY_REQUIRED"
        ),
        seed=seed(),
        runtime_session_id="runtime-a",
        current_connection_generation=3,
        now_monotonic_ns=20_000,
    )

    assert result.status == GateStatus.BLOCKED
    assert result.builder_status == "RECOVERY_REQUIRED"


def test_rest_seed_does_not_override_stale_heartbeat():
    result = evaluate_coinbase_with_rest_seed(
        base_evidence=blocked(
            "HEARTBEAT_STALE"
        ),
        seed=seed(),
        runtime_session_id="runtime-a",
        current_connection_generation=3,
        now_monotonic_ns=20_000,
    )

    assert result.status == GateStatus.BLOCKED


def test_prior_generation_seed_cannot_restore_current_readiness():
    result = evaluate_coinbase_with_rest_seed(
        base_evidence=blocked(),
        seed=seed(),
        runtime_session_id="runtime-a",
        current_connection_generation=4,
        now_monotonic_ns=20_000,
    )

    assert result.status == GateStatus.BLOCKED


def test_prior_runtime_seed_cannot_restore_current_readiness():
    result = evaluate_coinbase_with_rest_seed(
        base_evidence=blocked(),
        seed=seed(),
        runtime_session_id="runtime-b",
        current_connection_generation=3,
        now_monotonic_ns=20_000,
    )

    assert result.status == GateStatus.BLOCKED


def test_wrong_minute_seed_cannot_restore_readiness():
    wrong = BoundCoinbaseRestCandleSeed(
        runtime_session_id="runtime-a",
        connection_generation=3,
        minute=CoinbaseMinuteClose(
            minute_start_s=TARGET - 60,
            minute_end_s=TARGET,
            close_price=Decimal("110000"),
            available_monotonic_ns=10_000,
            raw_received_utc="2026-09-04T15:09:01Z",
        ),
    )

    result = evaluate_coinbase_with_rest_seed(
        base_evidence=blocked(),
        seed=wrong,
        runtime_session_id="runtime-a",
        current_connection_generation=3,
        now_monotonic_ns=20_000,
    )

    assert result.status == GateStatus.BLOCKED


def test_native_builder_pass_always_wins_over_seed():
    native = CoinbaseReadinessEvidence(
        status=GateStatus.PASS,
        reason="PASS",
        target_minute_start_s=TARGET,
        target_minute_end_s=TARGET + 60,
        builder_status="AVAILABLE",
        close_trade_id=999,
        connection_generation=3,
    )

    result = evaluate_coinbase_with_rest_seed(
        base_evidence=native,
        seed=seed(),
        runtime_session_id="runtime-a",
        current_connection_generation=3,
        now_monotonic_ns=20_000,
    )

    assert result is native
    assert result.close_trade_id == 999


def test_future_monotonic_seed_is_fatal():
    future = bind_rest_candle_seed(
        runtime_session_id="runtime-a",
        connection_generation=3,
        minute=CoinbaseMinuteClose(
            minute_start_s=TARGET,
            minute_end_s=TARGET + 60,
            close_price=Decimal("110123"),
            available_monotonic_ns=30_000,
            raw_received_utc="2026-09-04T15:10:01Z",
        ),
    )

    result = evaluate_coinbase_with_rest_seed(
        base_evidence=blocked(),
        seed=future,
        runtime_session_id="runtime-a",
        current_connection_generation=3,
        now_monotonic_ns=20_000,
    )

    assert result.status == GateStatus.FATAL
