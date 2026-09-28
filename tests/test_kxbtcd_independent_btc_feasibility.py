from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from src.kxbtcd_independent_btc_feasibility import (
    FROZEN_AUDIT_DESIGN_FINGERPRINT,
    KxbtcdIndependentBtcFeasibilityError,
    ReferenceObservation,
    audit_design_fingerprint,
    has_five_minute_causal_lookback,
    materialize_kxbtcd_snapshot,
    parse_coinbase_book,
    parse_kraken_pretrade,
    summarize_rows,
    validate_audit_design,
)


@dataclass(frozen=True)
class RawRef:
    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class Response:
    payload: dict
    raw_record: RawRef
    request_started_at_utc: str
    request_started_monotonic_ns: int
    received_at_utc: str
    received_monotonic_ns: int


def response(payload: dict, *, source: str, request_id: str, utc: str, mono: int) -> Response:
    return Response(
        payload=payload,
        raw_record=RawRef(source, f"{source}_session", request_id),
        request_started_at_utc=utc,
        request_started_monotonic_ns=mono - 1_000_000,
        received_at_utc=utc,
        received_monotonic_ns=mono,
    )


def coinbase(*, utc: str = "2026-08-16T00:30:00.000000Z", mono: int = 1_000_000_000) -> ReferenceObservation:
    return parse_coinbase_book(
        response(
            {
                "sequence": 123,
                "bids": [["100000", "1", 1]],
                "asks": [["100020", "1", 1]],
                "time": "2026-08-16T00:29:59.800000Z",
            },
            source="coinbase_exchange_rest_19b",
            request_id="cb1",
            utc=utc,
            mono=mono,
        )
    )


def kraken(*, utc: str = "2026-08-16T00:30:00.200000Z", mono: int = 1_200_000_000) -> ReferenceObservation:
    return parse_kraken_pretrade(
        response(
            {
                "error": [],
                "result": {
                    "bids": [
                        {
                            "price": "100010",
                            "qty": "0.5",
                            "publication_ts": "2026-08-16T00:29:59.900000Z",
                        }
                    ],
                    "asks": [
                        {
                            "price": "100030",
                            "qty": "0.4",
                            "publication_ts": "2026-08-16T00:29:59.950000Z",
                        }
                    ],
                },
            },
            source="kraken_spot_rest_19b",
            request_id="kr1",
            utc=utc,
            mono=mono,
        )
    )


def kalshi_response(*, mono: int = 1_500_000_000, include_result: bool = True) -> Response:
    market = {
        "event_ticker": "KXBTCD-26AUG1600",
        "ticker": "KXBTCD-26AUG1600-T100000",
        "close_time": "2026-08-16T01:00:00Z",
        "strike_type": "greater",
        "floor_strike": 100000,
        "yes_bid_dollars": "0.48",
        "yes_ask_dollars": "0.52",
    }
    if include_result:
        # The raw transport may contain downstream-looking fields. The 19B
        # materializer must never inspect or copy them into the feasibility row.
        market["result"] = "yes"
    return response(
        {"markets": [market], "cursor": ""},
        source="kalshi_public_rest",
        request_id="k1",
        utc="2026-08-16T00:30:00.500000Z",
        mono=mono,
    )


def test_audit_design_fingerprint_is_frozen() -> None:
    validate_audit_design()
    assert audit_design_fingerprint() == FROZEN_AUDIT_DESIGN_FINGERPRINT
    assert FROZEN_AUDIT_DESIGN_FINGERPRINT == (
        "41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be"
    )


def test_coinbase_book_parser_uses_level1_midpoint_and_source_time() -> None:
    obs = coinbase()
    assert obs.source_family == "coinbase"
    assert obs.price == Decimal("100010")
    assert obs.source_event_time_utc == "2026-08-16T00:29:59.800000Z"
    assert obs.raw_observation_ref.startswith("raw:coinbase_exchange_rest_19b:")


def test_kraken_parser_uses_midpoint_and_latest_best_level_publication_time() -> None:
    obs = kraken()
    assert obs.source_family == "kraken"
    assert obs.price == Decimal("100020")
    assert obs.source_event_time_utc == "2026-08-16T00:29:59.950000Z"


def test_materialized_row_is_protocol_valid_and_ignores_raw_result() -> None:
    cb = coinbase()
    kr = kraken()
    batch = materialize_kxbtcd_snapshot(
        kalshi_response(),
        coinbase_observation=cb,
        kraken_observation=kr,
        coinbase_history=[cb],
        kraken_history=[kr],
    )
    assert len(batch.rows) == 1
    assert not batch.exclusions
    row = batch.rows[0]
    assert row["q_market"] == "0.5"
    assert row["spread"] == "0.04"
    assert row["strike_dollars"] == "100000"
    assert row["coinbase_observation_available"] is True
    assert row["kraken_observation_available"] is True
    assert Decimal(row["coinbase_age_seconds"]) == Decimal("0.5")
    assert Decimal(row["kraken_age_seconds"]) == Decimal("0.3")
    assert row["cross_source_price_disagreement_bps"] is not None
    assert "result" not in row
    assert "outcome" not in row
    assert "label" not in row


def test_external_observation_received_after_kalshi_state_fails_closed() -> None:
    cb = coinbase(mono=2_000_000_000)
    kr = kraken()
    with pytest.raises(KxbtcdIndependentBtcFeasibilityError, match="received after"):
        materialize_kxbtcd_snapshot(
            kalshi_response(mono=1_500_000_000),
            coinbase_observation=cb,
            kraken_observation=kr,
            coinbase_history=[cb],
            kraken_history=[kr],
        )


def test_apparent_future_source_timestamp_becomes_unavailable_not_clamped() -> None:
    cb = ReferenceObservation(
        source_family="coinbase",
        source_id="coinbase.exchange.public_rest.product_book.btc_usd.provisional_19b",
        instrument_id="BTC-USD",
        source_event_time_utc="2026-08-16T00:30:01.000000Z",
        price=Decimal("100010"),
        raw_observation_ref="raw:coinbase:s:r",
        local_receive_utc="2026-08-16T00:30:00.100000Z",
        local_receive_monotonic_ns=1_000_000_000,
    )
    kr = kraken()
    row = materialize_kxbtcd_snapshot(
        kalshi_response(),
        coinbase_observation=cb,
        kraken_observation=kr,
        coinbase_history=[cb],
        kraken_history=[kr],
    ).rows[0]
    assert row["coinbase_observation_available"] is False
    assert row["coinbase_source_event_time_utc"] is None
    assert row["coinbase_price"] is None
    assert row["coinbase_age_seconds"] is None
    assert row["coinbase_raw_observation_refs"] == []
    assert row["kraken_observation_available"] is True


def test_five_minute_lookback_is_based_on_first_seen_monotonic_history() -> None:
    old = coinbase(mono=1_000_000_000)
    assert not has_five_minute_causal_lookback(
        [old], as_of_monotonic_ns=old.local_receive_monotonic_ns + 299_000_000_000
    )
    assert has_five_minute_causal_lookback(
        [old], as_of_monotonic_ns=old.local_receive_monotonic_ns + 300_000_000_000
    )


def test_cross_source_disagreement_matches_symmetric_midpoint_basis_points() -> None:
    cb = coinbase()
    kr = kraken()
    row = materialize_kxbtcd_snapshot(
        kalshi_response(),
        coinbase_observation=cb,
        kraken_observation=kr,
        coinbase_history=[cb],
        kraken_history=[kr],
    ).rows[0]
    expected = abs(cb.price - kr.price) / ((cb.price + kr.price) / 2) * Decimal("10000")
    assert Decimal(row["cross_source_price_disagreement_bps"]) == expected


def test_invalid_kalshi_quote_goes_to_structural_exclusion() -> None:
    response_obj = kalshi_response(include_result=False)
    response_obj.payload["markets"][0]["yes_bid_dollars"] = "0.70"
    response_obj.payload["markets"][0]["yes_ask_dollars"] = "0.60"
    cb = coinbase()
    kr = kraken()
    batch = materialize_kxbtcd_snapshot(
        response_obj,
        coinbase_observation=cb,
        kraken_observation=kr,
        coinbase_history=[cb],
        kraken_history=[kr],
    )
    assert not batch.rows
    assert len(batch.exclusions) == 1
    assert "valid probability quote" in batch.exclusions[0]["reason"]


def test_paginated_kxbtcd_snapshot_is_rejected() -> None:
    response_obj = kalshi_response()
    response_obj.payload["cursor"] = "more"
    with pytest.raises(KxbtcdIndependentBtcFeasibilityError, match="paginated"):
        materialize_kxbtcd_snapshot(
            response_obj,
            coinbase_observation=coinbase(),
            kraken_observation=kraken(),
            coinbase_history=[],
            kraken_history=[],
        )


def test_summary_remains_outcome_blind_and_no_fit_no_execution() -> None:
    cb = coinbase()
    kr = kraken()
    batch = materialize_kxbtcd_snapshot(
        kalshi_response(),
        coinbase_observation=cb,
        kraken_observation=kr,
        coinbase_history=[cb],
        kraken_history=[kr],
    )
    summary = summarize_rows(
        batch.rows,
        batch.exclusions,
        external_cycle_count=1,
        kalshi_snapshot_count=1,
        coinbase_attempt_count=1,
        coinbase_success_count=1,
        kraken_attempt_count=1,
        kraken_success_count=1,
        receive_skew_ms=[200.0],
    )
    assert summary["candidate_e_formula_frozen"] is False
    assert summary["candidate_e_fitting_performed"] is False
    assert summary["outcomes_accessed"] is False
    assert summary["checkpoint17_terminal_used"] is False
    assert summary["execution_performed"] is False
    assert summary["orders_placed"] == 0
    assert summary["thresholds_selected_from_outcomes"] is False
