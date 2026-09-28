import copy

import pytest

import src.kxbtcd_successor_research_protocol as protocol


def _good_row():
    return {
        "schema_version": protocol.FEASIBILITY_ROW_SCHEMA_VERSION,
        "protocol_fingerprint": protocol.FROZEN_PROTOCOL_FINGERPRINT,
        "state_id": "state-1",
        "event_ticker": "KXBTCD-EVENT",
        "market_ticker": "KXBTCD-MARKET",
        "as_of_utc": "2026-08-16T00:00:00Z",
        "time_to_close_seconds": "1800",
        "strike_dollars": "118000",
        "q_market": "0.55",
        "spread": "0.02",
        "kalshi_raw_observation_refs": ["kalshi-1"],
        "coinbase_observation_available": True,
        "coinbase_source_id": "coinbase.public_ws.btcusd.v1",
        "coinbase_source_event_time_utc": "2026-08-15T23:59:59Z",
        "coinbase_price": "118010",
        "coinbase_age_seconds": "1",
        "coinbase_raw_observation_refs": ["cb-1"],
        "kraken_observation_available": True,
        "kraken_source_id": "kraken.public_ws.btcusd.v1",
        "kraken_source_event_time_utc": "2026-08-15T23:59:58Z",
        "kraken_price": "118020",
        "kraken_age_seconds": "2",
        "kraken_raw_observation_refs": ["kr-1"],
        "cross_source_price_disagreement_bps": "0.8473",
        "five_minute_lookback_available_coinbase": True,
        "five_minute_lookback_available_kraken": True,
        "structurally_usable_for_design": True,
        "exclusion_reasons": [],
    }


def _good_spec():
    return {
        "schema_version": protocol.SUCCESSOR_PREDECLARATION_SCHEMA_VERSION,
        "protocol_fingerprint": protocol.FROZEN_PROTOCOL_FINGERPRINT,
        "model_id": "candidate-e-placeholder",
        "benchmark": protocol.RAW_BENCHMARK_ID,
        "uses_checkpoint17_terminal": False,
        "uses_exposed_E0_for_advancement": False,
        "subsecond_lead_lag": False,
        "execution_authorized": False,
        "features": [
            {
                "name": "independent_btc_level",
                "source_family": "coinbase",
                "independent_of_kalshi_probability": True,
            },
            {
                "name": "market_logit",
                "source_family": "kalshi",
                "independent_of_kalshi_probability": False,
            },
        ],
    }


def test_protocol_fingerprint_is_frozen():
    protocol.validate_protocol()
    assert protocol.protocol_fingerprint() == protocol.FROZEN_PROTOCOL_FINGERPRINT


def test_checkpoint19a_remains_no_fit_no_outcome_no_execution():
    assert protocol.CANDIDATE_E_FORMULA_FROZEN is False
    assert protocol.CANDIDATE_E_FITTING_AUTHORIZED is False
    assert protocol.OUTCOME_ACCESS_AUTHORIZED is False
    assert protocol.EXECUTION_AUTHORIZED is False


def test_outcome_exposed_evidence_cannot_be_upgraded():
    with pytest.raises(protocol.KxbtcdSuccessorProtocolError, match="cannot be upgraded"):
        protocol.validate_evidence_transition(
            from_tier="E1_successor_design",
            to_tier="E3_prospective_test",
            source_outcomes_used=True,
        )


def test_successor_requires_independent_btc_state():
    spec = _good_spec()
    protocol.validate_successor_predeclaration(spec)
    spec["features"] = [
        {
            "name": "market_logit",
            "source_family": "kalshi",
            "independent_of_kalshi_probability": False,
        }
    ]
    with pytest.raises(protocol.KxbtcdSuccessorProtocolError, match="independent BTC-state"):
        protocol.validate_successor_predeclaration(spec)


def test_checkpoint17_terminal_use_is_rejected():
    spec = _good_spec()
    spec["uses_checkpoint17_terminal"] = True
    with pytest.raises(protocol.KxbtcdSuccessorProtocolError, match="Checkpoint-17"):
        protocol.validate_successor_predeclaration(spec)


def test_subsecond_lead_lag_is_rejected():
    spec = _good_spec()
    spec["subsecond_lead_lag"] = True
    with pytest.raises(protocol.KxbtcdSuccessorProtocolError, match="sub-second"):
        protocol.validate_successor_predeclaration(spec)


def test_good_feasibility_row_passes():
    protocol.validate_feasibility_row(_good_row())


def test_future_reference_observation_fails_closed():
    row = _good_row()
    row["coinbase_source_event_time_utc"] = "2026-08-16T00:00:01Z"
    with pytest.raises(protocol.KxbtcdSuccessorProtocolError, match="future"):
        protocol.validate_feasibility_row(row)


def test_missing_source_requires_null_source_values():
    row = _good_row()
    row["kraken_observation_available"] = False
    row["kraken_source_id"] = None
    row["kraken_source_event_time_utc"] = None
    row["kraken_price"] = None
    row["kraken_age_seconds"] = None
    row["kraken_raw_observation_refs"] = []
    row["five_minute_lookback_available_kraken"] = False
    row["cross_source_price_disagreement_bps"] = None
    protocol.validate_feasibility_row(row)


def test_unusable_row_requires_reason():
    row = _good_row()
    row["structurally_usable_for_design"] = False
    with pytest.raises(protocol.KxbtcdSuccessorProtocolError, match="at least one exclusion"):
        protocol.validate_feasibility_row(row)


def test_outcome_field_is_rejected_as_extra_field():
    row = _good_row()
    row["outcome"] = 1
    with pytest.raises(protocol.KxbtcdSuccessorProtocolError):
        protocol.validate_feasibility_row(row)
