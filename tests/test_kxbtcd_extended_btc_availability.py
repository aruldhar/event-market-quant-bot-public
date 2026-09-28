
from decimal import Decimal

from src.kxbtcd_extended_btc_availability import (
    COINBASE_SOURCE_ID,
    DURATION_SECONDS,
    EXTERNAL_INTERVAL_SECONDS,
    FROZEN_AUDIT_DESIGN_FINGERPRINT,
    KALSHI_INTERVAL_SECONDS,
    KRAKEN_SOURCE_ID,
    ReferenceObservation,
    audit_design_definition,
    audit_design_fingerprint,
    external_cycle_row,
    five_minute_lookback_gap_seconds,
    public_error_is_raw_persistence_failure,
    validate_audit_design,
)


def _obs(family: str, source_id: str, mono: int, price: str):
    return ReferenceObservation(
        source_family=family,
        source_id=source_id,
        instrument_id="BTC-USD" if family == "coinbase" else "BTC/USD",
        source_event_time_utc="2026-08-16T01:00:00Z",
        price=Decimal(price),
        raw_observation_ref=f"raw:{family}:session:req",
        local_receive_utc="2026-08-16T01:00:00Z",
        local_receive_monotonic_ns=mono,
    )


def test_design_fingerprint_is_frozen():
    validate_audit_design()
    assert audit_design_fingerprint() == FROZEN_AUDIT_DESIGN_FINGERPRINT


def test_design_is_24h_15s_5m_and_not_overrideable():
    design = audit_design_definition()["collection"]
    assert (
        DURATION_SECONDS,
        EXTERNAL_INTERVAL_SECONDS,
        KALSHI_INTERVAL_SECONDS,
    ) == (86400, 15.0, 300.0)
    assert design["command_line_cadence_or_duration_override"] is False


def test_model_outcome_execution_remain_disabled():
    design = audit_design_definition()
    assert design["candidate_e_formula_frozen"] is False
    assert design["candidate_e_fitting_authorized"] is False
    assert design["outcome_access_authorized"] is False
    assert design["execution_authorized"] is False
    assert design["subsecond_lead_lag_authorized"] is False


def test_thresholds_and_cohort_sizes_remain_unfrozen():
    unfrozen = set(audit_design_definition()["not_frozen_by_19c"])
    assert "source_staleness_threshold" in unfrozen
    assert "cross_source_disagreement_threshold" in unfrozen
    assert "Candidate_E_formula" in unfrozen
    assert "E1_E2_E3_event_counts" in unfrozen


def test_external_cycle_disagreement_is_not_model_output():
    cb = _obs("coinbase", COINBASE_SOURCE_ID, 1_000_000_000, "100000")
    kr = _obs("kraken", KRAKEN_SOURCE_ID, 1_100_000_000, "100010")
    row = external_cycle_row(
        cycle_index=0,
        cycle_completed_utc="2026-08-16T01:00:01Z",
        coinbase=cb,
        kraken=kr,
    )
    assert row["coinbase_available"] is True
    assert row["kraken_available"] is True
    assert float(row["cross_source_price_disagreement_bps"]) > 0
    assert row["external_receive_skew_ms"] == 100.0
    assert "prediction" not in row
    assert "outcome" not in row


def test_external_cycle_handles_one_source_missing():
    cb = _obs("coinbase", COINBASE_SOURCE_ID, 1_000_000_000, "100000")
    row = external_cycle_row(
        cycle_index=3,
        cycle_completed_utc="2026-08-16T01:00:01Z",
        coinbase=cb,
        kraken=None,
    )
    assert row["coinbase_available"] is True
    assert row["kraken_available"] is False
    assert row["cross_source_price_disagreement_bps"] is None


def test_five_minute_gap_uses_latest_past_observation():
    history = [
        _obs("coinbase", COINBASE_SOURCE_ID, 1_000_000_000, "100000"),
        _obs("coinbase", COINBASE_SOURCE_ID, 11_000_000_000, "100001"),
    ]
    assert (
        five_minute_lookback_gap_seconds(
            history, as_of_monotonic_ns=316_000_000_000
        )
        == 5.0
    )


def test_five_minute_gap_none_without_old_enough_observation():
    history = [
        _obs("coinbase", COINBASE_SOURCE_ID, 20_000_000_000, "100000")
    ]
    assert (
        five_minute_lookback_gap_seconds(
            history, as_of_monotonic_ns=310_000_000_000
        )
        is None
    )


def test_source_ids_remain_provisional_not_e1():
    assert "provisional_19c" in COINBASE_SOURCE_ID
    assert "provisional_19c" in KRAKEN_SOURCE_ID
    assert (
        "not_E1_frozen"
        in audit_design_definition()["sources"]["coinbase"]["status"]
    )


def test_raw_persistence_failure_classifier_fails_closed():
    assert public_error_is_raw_persistence_failure(
        RuntimeError("GET failed and raw persistence also failed")
    )
    assert public_error_is_raw_persistence_failure(
        RuntimeError("response arrived but raw persistence failed")
    )
    assert not public_error_is_raw_persistence_failure(
        RuntimeError("HTTP 503")
    )


def test_parent_19b_evidence_is_bound():
    design = audit_design_definition()
    assert design["parent_19b_audit_design_fingerprint"] == "41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be"
    assert design["parent_19b_pilot_run_id"] == "collect_kxbtcd_independent_btc_feasibility_20260816T003652267319Z_b123b960"
