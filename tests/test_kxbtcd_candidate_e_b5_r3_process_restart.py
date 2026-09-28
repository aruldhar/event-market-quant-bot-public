from decimal import Decimal

from src.kxbtcd_candidate_e_b5_r2_live_reconnect import (
    ReconnectGenerationController,
)
from src.kxbtcd_candidate_e_b5_r3_process_restart import (
    CANONICAL_PROSPECTIVE_DB_CREATED,
    COHORT_ARMED,
    NETWORK_ENABLED,
    ORDERS_SUBMITTED,
    PRODUCTION_WRITES,
    SIGNALS_COMPUTED,
    OfflineProcessRestartOrchestrator,
    StrategyRestartState,
    evaluate_strategy_reconciliation,
)
from src.kxbtcd_candidate_e_prospective_live_collector import (
    EventLadder,
)
from src.kxbtcd_candidate_e_restart_durable_state_store import (
    RestartDurableStateStore,
)
from src.kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from src.kxbtcd_candidate_e_restart_reconciliation import (
    RestartSessionRawJournal,
    build_validation_arm_manifest,
    commit_validation_decision,
    install_validation_cohort_identity,
    write_validation_arm_manifest_once,
)
from src.kxbtcd_candidate_e_restart_source_readiness import (
    BootIdentityEvidence,
    ChronyTrackingEvidence,
    CoinbaseReadinessEvidence,
    KalshiReadinessEvidence,
    KalshiTransportLivenessEvidence,
    evaluate_coinbase_readiness,
    evaluate_kalshi_readiness,
)
from src.kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import (
    LadderMarket,
)


COMMIT = "0123456789abcdef0123456789abcdef01234567"
BOOT_1 = "11111111-1111-1111-1111-111111111111"
BOOT_2 = "22222222-2222-2222-2222-222222222222"


def make_store(tmp_path):
    return RestartDurableStateStore(
        tmp_path / "state.sqlite3",
        validation_mode=True,
    )


def install_validation_identity(tmp_path, store):
    first = store.start_session(
        boot_id=BOOT_1,
        git_commit=COMMIT,
        started_utc="2026-09-04T08:00:00Z",
        started_monotonic_ns=1000,
        session_id="session-1",
    )
    manifest = build_validation_arm_manifest(
        cohort_id="validation-cohort",
        arm_time_utc="2026-09-04T08:00:00Z",
        arm_git_commit=COMMIT,
    )
    path = tmp_path / "arm.json"
    write_validation_arm_manifest_once(path, manifest)
    install_validation_cohort_identity(
        store=store,
        manifest_path=path,
        armed_by_session_id=first,
    )
    return first, path


def start_second(store, *, utc="2026-09-04T08:01:00Z", ns=10):
    return OfflineProcessRestartOrchestrator.start_new_process(
        store=store,
        boot_id=BOOT_2,
        git_commit=COMMIT,
        started_utc=utc,
        started_monotonic_ns=ns,
        session_id="session-2",
    )


def pass_boot():
    return BootIdentityEvidence(
        status=GateStatus.PASS,
        boot_id=BOOT_2,
        source="synthetic_validation",
        validation_only=True,
        reason="PASS",
    )


def pass_clock():
    return ChronyTrackingEvidence(
        status=GateStatus.PASS,
        signed_system_time_offset_ms=0.0,
        absolute_system_time_offset_ms=0.0,
        leap_status="Normal",
        reason="PASS",
    )


def pass_coinbase():
    return CoinbaseReadinessEvidence(
        status=GateStatus.PASS,
        reason="PASS",
        target_minute_start_s=1788508800,
        target_minute_end_s=1788508860,
        builder_status="AVAILABLE",
        close_trade_id=123,
        connection_generation=1,
    )


def blocked_coinbase():
    return CoinbaseReadinessEvidence(
        status=GateStatus.BLOCKED,
        reason="COINBASE_WEBSOCKET_NOT_CONNECTED",
        target_minute_start_s=1788508800,
        target_minute_end_s=1788508860,
        builder_status="DISCONNECTED",
        close_trade_id=None,
        connection_generation=1,
    )


def pass_kalshi():
    return KalshiReadinessEvidence(
        status=GateStatus.PASS,
        reason="PASS",
        event_ticker="KXBTCD-26SEP0405",
        expected_tickers=("KXBTCD-26SEP0405-T80000",),
        generation=0,
        last_seq=2,
        subscription_sid=7,
        connection_generation=1,
        transport_reason="PASS",
    )


def event():
    return EventLadder(
        event_ticker="KXBTCD-26SEP0405",
        close_time_utc="2026-09-04T09:00:00Z",
        close_timestamp_ms=1788512400000,
        markets=(
            LadderMarket(
                event_ticker="KXBTCD-26SEP0405",
                market_ticker="KXBTCD-26SEP0405-T79999.99",
                strike=Decimal("80000"),
                strike_rank_zero_based=0,
                event_market_count=1,
                historical_structural_role=None,
            ),
        ),
    )


def test_safety_constants_remain_zero_read_only():
    assert NETWORK_ENABLED is False
    assert CANONICAL_PROSPECTIVE_DB_CREATED is False
    assert COHORT_ARMED is False
    assert SIGNALS_COMPUTED == 0
    assert ORDERS_SUBMITTED == 0
    assert PRODUCTION_WRITES == 0


def test_clean_restart_classifies_prior_and_allows_durability_pass(tmp_path):
    with make_store(tmp_path) as store:
        _, manifest = install_validation_identity(tmp_path, store)
        store.clean_shutdown(
            "session-1",
            ended_utc="2026-09-04T08:00:30Z",
            ended_monotonic_ns=2000,
        )
        restart = start_second(store, ns=5)
        startup = restart.reconcile_startup(
            manifest_path=manifest,
            current_git_commit=COMMIT,
            evaluated_utc="2026-09-04T08:01:01Z",
            raw_segments={},
        )
        assert startup.durability.status == GateStatus.PASS
        assert startup.durability.prior_shutdown_status == "CLEAN"
        assert startup.durability.pending_after == 0
        assert startup.strategy.status == GateStatus.PASS
        assert restart.gate.state == "STARTUP_DISABLED"


def test_unclean_restart_marks_prior_and_process_gap(tmp_path):
    with make_store(tmp_path) as store:
        _, manifest = install_validation_identity(tmp_path, store)
        restart = start_second(store, ns=3)
        startup = restart.reconcile_startup(
            manifest_path=manifest,
            current_git_commit=COMMIT,
            evaluated_utc="2026-09-04T08:01:01Z",
            raw_segments={},
        )
        assert startup.durability.status == GateStatus.PASS
        assert startup.durability.prior_shutdown_status == "UNCLEAN_DETECTED"
        assert store.session("session-1")["shutdown_status"] == "UNCLEAN_DETECTED"
        gaps = store.observation_gaps()
        assert any(
            g["reason"] == "UNCLEAN_PRIOR_SESSION"
            and g["canonical_backfill_allowed"] == 0
            for g in gaps
        )


def test_pending_complete_raw_becomes_verified_before_durability_pass(tmp_path):
    raw = tmp_path / "raw.jsonl"
    with make_store(tmp_path) as store:
        _, manifest = install_validation_identity(tmp_path, store)
        with RestartSessionRawJournal(
            raw,
            runtime_session_id="session-1",
            raw_segment_id="segment-1",
        ) as journal:
            ref = journal.append(
                source="coinbase_exchange_ws",
                transport="wss",
                raw_text='{"type":"match"}',
                received_monotonic_ns=1500,
                received_utc="2026-09-04T08:00:10Z",
            )
        decision_id = commit_validation_decision(
            store=store,
            session_id="session-1",
            session_decision_seq=1,
            decision_utc="2026-09-04T08:00:20Z",
            decision_monotonic_ns=1600,
            event_ticker="KXBTCD-TEST",
            raw_refs=[ref],
            source_id="coinbase_exchange_ws",
            raw_segment_id="segment-1",
            last_raw_record_index=1,
        )
        restart = start_second(store)
        startup = restart.reconcile_startup(
            manifest_path=manifest,
            current_git_commit=COMMIT,
            evaluated_utc="2026-09-04T08:01:01Z",
            raw_segments={
                ("session-1", "segment-1"): raw,
            },
        )
        status = store.connection.execute(
            """
            SELECT integrity_status
            FROM decision_records
            WHERE decision_record_id=?
            """,
            (decision_id,),
        ).fetchone()[0]
        assert status == "VERIFIED"
        assert startup.durability.pending_before == 1
        assert startup.durability.verified == 1
        assert startup.durability.pending_after == 0
        assert startup.durability.status == GateStatus.PASS


def test_missing_raw_becomes_gap_and_fresh_recovery_remains_allowed(tmp_path):
    raw = tmp_path / "raw.jsonl"
    with make_store(tmp_path) as store:
        _, manifest = install_validation_identity(tmp_path, store)
        with RestartSessionRawJournal(
            raw,
            runtime_session_id="session-1",
            raw_segment_id="segment-1",
        ) as journal:
            ref = journal.append(
                source="kalshi_production_ws",
                transport="wss",
                raw_text="snapshot",
                received_monotonic_ns=1500,
                received_utc="2026-09-04T08:00:10Z",
            )
        decision_id = commit_validation_decision(
            store=store,
            session_id="session-1",
            session_decision_seq=1,
            decision_utc="2026-09-04T08:00:20Z",
            decision_monotonic_ns=1600,
            event_ticker="KXBTCD-TEST",
            raw_refs=[ref],
            source_id="kalshi_production_ws",
            raw_segment_id="segment-1",
            last_raw_record_index=1,
        )
        restart = start_second(store)
        startup = restart.reconcile_startup(
            manifest_path=manifest,
            current_git_commit=COMMIT,
            evaluated_utc="2026-09-04T08:01:01Z",
            raw_segments={},
        )
        status = store.connection.execute(
            """
            SELECT integrity_status
            FROM decision_records
            WHERE decision_record_id=?
            """,
            (decision_id,),
        ).fetchone()[0]
        assert status == "RAW_EVIDENCE_GAP"
        assert startup.durability.raw_evidence_gaps == 1
        assert startup.durability.pending_after == 0
        assert startup.durability.status == GateStatus.PASS
        assert any(
            g["reason"] == "MISSING_OR_DAMAGED_RAW_REFERENCE"
            and g["canonical_backfill_allowed"] == 0
            for g in store.observation_gaps()
        )


def test_strategy_reconciliation_blocks_any_inherited_actionable_state():
    evidence = evaluate_strategy_reconciliation(
        StrategyRestartState(
            prior_signal_reusable=True,
            current_signal_selection_restored=True,
        )
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "STRATEGY_STATE_NOT_NEUTRAL"
    assert "prior_signal_reusable" in evidence.restored_or_actionable_fields
    assert "current_signal_selection_restored" in evidence.restored_or_actionable_fields


def test_strategy_reconciliation_fatal_if_execution_not_disabled():
    evidence = evaluate_strategy_reconciliation(
        StrategyRestartState(execution_mode_disabled=False)
    )
    assert evidence.status == GateStatus.FATAL
    assert evidence.reason == "EXECUTION_MODE_NOT_DISABLED"


def test_old_process_coinbase_builder_rejected_by_new_runtime_session():
    old = ReconnectGenerationController("session-1")
    binding = old.open_coinbase(opened_monotonic_ns=100)
    evidence = evaluate_coinbase_readiness(
        builder=binding.builder,
        runtime_session_id="session-2",
        builder_runtime_session_id=binding.runtime_session_id,
        current_connection_generation=1,
        builder_connection_generation=binding.generation,
        decision_epoch_s=1788508865,
        now_monotonic_ns=200,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "COINBASE_STATE_NOT_FROM_CURRENT_RUNTIME_SESSION"


def test_old_process_kalshi_cache_rejected_by_new_runtime_session():
    old = ReconnectGenerationController("session-1")
    ticker = event().markets[0].market_ticker
    binding = old.open_kalshi(
        subscribed_tickers=(ticker,),
        opened_monotonic_ns=100,
    )
    transport = KalshiTransportLivenessEvidence(
        status=GateStatus.PASS,
        reason="PASS",
        runtime_session_id="session-1",
        connection_generation=1,
        last_pong_monotonic_ns=150,
        evaluated_monotonic_ns=200,
        pong_age_ns=50,
    )
    evidence = evaluate_kalshi_readiness(
        cache=binding.cache,
        current_event=event(),
        runtime_session_id="session-2",
        discovery_runtime_session_id="session-1",
        cache_runtime_session_id=binding.runtime_session_id,
        cache_connection_generation=binding.generation,
        transport_liveness=transport,
        now_ms=1788508865000,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "KALSHI_STATE_NOT_FROM_CURRENT_RUNTIME_SESSION"


def test_fresh_all_gate_evidence_reaches_ready_read_only(tmp_path):
    with make_store(tmp_path) as store:
        _, manifest = install_validation_identity(tmp_path, store)
        store.clean_shutdown(
            "session-1",
            ended_utc="2026-09-04T08:00:30Z",
            ended_monotonic_ns=2000,
        )
        restart = start_second(store, ns=5)
        startup = restart.reconcile_startup(
            manifest_path=manifest,
            current_git_commit=COMMIT,
            evaluated_utc="2026-09-04T08:01:01Z",
            raw_segments={},
        )
        state = restart.evaluate_current_readiness(
            startup=startup,
            boot_identity=pass_boot(),
            clock_evidence=pass_clock(),
            coinbase_evidence=pass_coinbase(),
            kalshi_evidence=pass_kalshi(),
            evaluated_utc="2026-09-04T08:01:02Z",
            evaluated_monotonic_ns=20,
        )
        assert state == "READY_READ_ONLY"
        assert restart.gate.readiness_generation == 1
        assert restart.gate.prior_signal_reusable is False


def test_post_ready_source_regression_blocks_and_records_gap(tmp_path):
    with make_store(tmp_path) as store:
        _, manifest = install_validation_identity(tmp_path, store)
        store.clean_shutdown(
            "session-1",
            ended_utc="2026-09-04T08:00:30Z",
            ended_monotonic_ns=2000,
        )
        restart = start_second(store, ns=5)
        startup = restart.reconcile_startup(
            manifest_path=manifest,
            current_git_commit=COMMIT,
            evaluated_utc="2026-09-04T08:01:01Z",
            raw_segments={},
        )
        assert restart.evaluate_current_readiness(
            startup=startup,
            boot_identity=pass_boot(),
            clock_evidence=pass_clock(),
            coinbase_evidence=pass_coinbase(),
            kalshi_evidence=pass_kalshi(),
            evaluated_utc="2026-09-04T08:01:02Z",
            evaluated_monotonic_ns=20,
        ) == "READY_READ_ONLY"

        state = restart.evaluate_current_readiness(
            startup=startup,
            boot_identity=pass_boot(),
            clock_evidence=pass_clock(),
            coinbase_evidence=blocked_coinbase(),
            kalshi_evidence=pass_kalshi(),
            evaluated_utc="2026-09-04T08:01:03Z",
            evaluated_monotonic_ns=21,
        )
        assert state == "BLOCKED_COINBASE"
        assert restart.gate.prior_signal_reusable is False
        assert any(
            g["reason"] == "READY_GATE_REGRESSION"
            and g["canonical_backfill_allowed"] == 0
            for g in store.observation_gaps()
        )


def test_restart_after_fixed_end_resolves_cohort_ended(tmp_path):
    with make_store(tmp_path) as store:
        _, manifest = install_validation_identity(tmp_path, store)
        store.clean_shutdown(
            "session-1",
            ended_utc="2026-09-04T08:00:30Z",
            ended_monotonic_ns=2000,
        )
        restart = start_second(
            store,
            utc="2026-09-12T08:00:01Z",
            ns=5,
        )
        startup = restart.reconcile_startup(
            manifest_path=manifest,
            current_git_commit=COMMIT,
            evaluated_utc="2026-09-12T08:00:01Z",
            raw_segments={},
        )
        state = restart.evaluate_current_readiness(
            startup=startup,
            boot_identity=pass_boot(),
            clock_evidence=pass_clock(),
            coinbase_evidence=pass_coinbase(),
            kalshi_evidence=pass_kalshi(),
            evaluated_utc="2026-09-12T08:00:02Z",
            evaluated_monotonic_ns=10,
        )
        assert state == "COHORT_ENDED"


def test_execution_mode_enabled_is_fatal_in_full_gate(tmp_path):
    with make_store(tmp_path) as store:
        _, manifest = install_validation_identity(tmp_path, store)
        store.clean_shutdown(
            "session-1",
            ended_utc="2026-09-04T08:00:30Z",
            ended_monotonic_ns=2000,
        )
        restart = start_second(store, ns=5)
        startup = restart.reconcile_startup(
            manifest_path=manifest,
            current_git_commit=COMMIT,
            evaluated_utc="2026-09-04T08:01:01Z",
            raw_segments={},
            strategy_state=StrategyRestartState(
                execution_mode_disabled=False
            ),
        )
        assert restart.evaluate_current_readiness(
            startup=startup,
            boot_identity=pass_boot(),
            clock_evidence=pass_clock(),
            coinbase_evidence=pass_coinbase(),
            kalshi_evidence=pass_kalshi(),
            evaluated_utc="2026-09-04T08:01:02Z",
            evaluated_monotonic_ns=20,
        ) == "FATAL"
