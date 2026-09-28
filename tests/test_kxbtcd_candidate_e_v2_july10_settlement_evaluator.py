from pathlib import Path

import pytest

from src import kxbtcd_candidate_e_v2_july10_settlement_evaluator as m


def contract_rows(classes):
    return {
        "scenario_classification": classes,
        "censored_path_accounting": {
            "pnl_lower_bound_dollars": "-2.0700",
            "pnl_upper_bound_dollars": "2",
        },
        "frozen_evidence": {
            "repaired_outcome_blind_path_sha256": "a",
            "competitive_censorship_refinement_sha256": "b",
        },
    }


def cls(event, threshold, latency, observation):
    return {
        "event_ticker": event,
        "threshold_dollars": threshold,
        "latency_ms": latency,
        "path_observation_class": observation,
        "selection_or_rearm_censored": observation == "CENSORED",
        "explicit_liquidation_censored": False,
    }


def trade(ticker, status, *, side="YES", entry_cash="-0.4", exit_cash="0.5"):
    liquidation = {
        "status": status,
        "settlement_fallback_quantity": (
            "1" if status == "EXIT_MISSED_SETTLEMENT_FALLBACK" else "0"
        ),
        "exit_ioc": None,
    }
    if status == "EXIT_FULL":
        liquidation["exit_ioc"] = {
            "status": "FULL",
            "net_cash_change_total": exit_cash,
        }
    return {
        "signal": {"market_ticker": ticker, "side": side},
        "entry": {
            "ioc": {
                "status": "FULL",
                "net_cash_change_total": entry_cash,
            }
        },
        "liquidation": liquidation,
    }


def policy_row(event, threshold, latency, trades):
    return {
        "event_ticker": event,
        "threshold_dollars": threshold,
        "latency_ms": latency,
        "policy_result": {"trades": trades},
    }


def settlement_record(ticker, result="yes", source_tier="live_recent"):
    source_path = (
        m.LIVE_MARKETS_PATH
        if source_tier == "live_recent"
        else m.HISTORICAL_MARKETS_PATH
    )
    return {
        "schema_version": "candidate_e_v2_exact_settlement_record.v1",
        "source_id": m.SOURCE_NAME,
        "source_tier": source_tier,
        "source_endpoint": m.market_source_endpoint(source_path, ticker),
        "market": {
            "ticker": ticker,
            "event_ticker": "E",
            "market_type": "binary",
            "status": "finalized",
            "result": result,
            "settlement_value_dollars": "1" if result == "yes" else "0",
            "settlement_ts": "2026-07-10T20:00:00Z",
            "is_provisional": False,
        },
        "raw_reference": {
            "source": m.SOURCE_NAME,
            "session_id": "s",
            "request_id": "r",
        },
        "request_started_at_utc": "2026-09-03T00:00:00Z",
        "received_at_utc": "2026-09-03T00:00:01Z",
    }


def normalize_kwargs(ticker="KX-A", source_tier="live_recent"):
    source_path = (
        m.LIVE_MARKETS_PATH
        if source_tier == "live_recent"
        else m.HISTORICAL_MARKETS_PATH
    )
    return {
        "expected_ticker": ticker,
        "source_tier": source_tier,
        "source_path": source_path,
        "raw_reference": {
            "source": m.SOURCE_NAME,
            "session_id": "s",
            "request_id": "r",
        },
        "request_started_at_utc": "2026-09-03T00:00:00Z",
        "received_at_utc": "2026-09-03T00:00:01Z",
    }


def test_fallback_tickers_respect_exact_vs_censored():
    c = contract_rows(
        [
            cls("E1", "0", 0, "EXACT"),
            cls("E2", "0", 0, "CENSORED"),
        ]
    )
    p = {
        "policy_results": [
            policy_row(
                "E1",
                "0",
                0,
                [trade("KX-A", "EXIT_MISSED_SETTLEMENT_FALLBACK")],
            ),
            policy_row(
                "E2",
                "0",
                0,
                [trade("KX-B", "EXIT_MISSED_SETTLEMENT_FALLBACK")],
            ),
        ]
    }
    out = m.fallback_tickers_by_class(c, p)
    assert out["exact_required"] == ("KX-A",)
    assert out["censored_fallback"] == ("KX-B",)
    assert out["overlap"] == ()


def test_exact_and_censored_overlap_is_reported_once():
    c = contract_rows(
        [
            cls("E1", "0", 0, "EXACT"),
            cls("E2", "0", 0, "CENSORED"),
        ]
    )
    p = {
        "policy_results": [
            policy_row(
                "E1",
                "0",
                0,
                [trade("KX-A", "EXIT_MISSED_SETTLEMENT_FALLBACK")],
            ),
            policy_row(
                "E2",
                "0",
                0,
                [trade("KX-A", "EXIT_MISSED_SETTLEMENT_FALLBACK")],
            ),
        ]
    }
    out = m.fallback_tickers_by_class(c, p)
    assert out["exact_required"] == ("KX-A",)
    assert out["censored_fallback"] == ("KX-A",)
    assert out["overlap"] == ("KX-A",)


def test_exact_scenario_rejects_monitoring_gap_liquidation():
    c = contract_rows([cls("E1", "0", 0, "EXACT")])
    p = {
        "policy_results": [
            policy_row(
                "E1",
                "0",
                0,
                [trade("KX-A", "SOURCE_UNAVAILABLE_MONITORING_GAP")],
            )
        ]
    }
    with pytest.raises(m.SettlementEvaluationError):
        m.fallback_tickers_by_class(c, p)


def test_normalize_market_list_response_validates_live_finalized_binary():
    payload = {"markets": [settlement_record("KX-A")["market"]]}
    record = m.normalize_market_list_response(
        payload=payload,
        **normalize_kwargs("KX-A", "live_recent"),
    )
    assert record["source_tier"] == "live_recent"
    assert record["source_endpoint"] == "/markets?tickers=KX-A"
    assert record["market"]["result"] == "yes"
    assert record["market"]["settlement_value_dollars"] == "1"


def test_normalize_market_list_response_validates_historical_finalized_binary():
    payload = {
        "markets": [
            settlement_record("KX-A", source_tier="historical")["market"]
        ]
    }
    record = m.normalize_market_list_response(
        payload=payload,
        **normalize_kwargs("KX-A", "historical"),
    )
    assert record["source_tier"] == "historical"
    assert record["source_endpoint"] == "/historical/markets?tickers=KX-A"


def test_normalize_rejects_nonfinalized():
    payload = {"markets": [settlement_record("KX-A")["market"]]}
    payload["markets"][0]["status"] = "determined"
    with pytest.raises(Exception):
        m.normalize_market_list_response(
            payload=payload,
            **normalize_kwargs("KX-A", "live_recent"),
        )


def test_normalize_rejects_source_tier_path_mismatch():
    payload = {"markets": [settlement_record("KX-A")["market"]]}
    kwargs = normalize_kwargs("KX-A", "live_recent")
    kwargs["source_path"] = m.HISTORICAL_MARKETS_PATH
    with pytest.raises(m.SettlementEvaluationError):
        m.normalize_market_list_response(payload=payload, **kwargs)


def test_cache_validation_requires_raw_lineage_and_source_tier():
    bad = settlement_record("KX-A")
    bad["raw_reference"] = {}
    with pytest.raises(m.SettlementEvaluationError):
        m.validate_cached_settlement_record(bad, "KX-A")

    bad = settlement_record("KX-A")
    bad.pop("source_tier")
    with pytest.raises(m.SettlementEvaluationError):
        m.validate_cached_settlement_record(bad, "KX-A")


def test_partitioned_market_transport_uses_same_exact_filter():
    ticker = "KXBTCD-26JUL1014-T64099.99"
    assert m.LIVE_MARKETS_PATH == "/markets"
    assert m.HISTORICAL_MARKETS_PATH == "/historical/markets"
    assert m.market_filter_params(ticker) == {"tickers": ticker}
    assert m.market_source_endpoint(m.LIVE_MARKETS_PATH, ticker) == (
        "/markets?tickers=KXBTCD-26JUL1014-T64099.99"
    )
    assert m.market_source_endpoint(m.HISTORICAL_MARKETS_PATH, ticker) == (
        "/historical/markets?tickers=KXBTCD-26JUL1014-T64099.99"
    )


def test_exact_filtered_market_allows_zero_only_for_storage_tier_fallback():
    assert (
        m.exact_filtered_market(
            expected_ticker="KX-A",
            payload={"markets": []},
            allow_zero=True,
        )
        is None
    )

    with pytest.raises(m.SettlementEvaluationError):
        m.exact_filtered_market(
            expected_ticker="KX-A",
            payload={"markets": []},
            allow_zero=False,
        )


def test_exact_filtered_market_rejects_multiple_and_wrong_ticker():
    market = settlement_record("KX-A")["market"]
    with pytest.raises(m.SettlementEvaluationError):
        m.exact_filtered_market(
            expected_ticker="KX-A",
            payload={"markets": [market, market]},
            allow_zero=True,
        )

    wrong = settlement_record("KX-B")["market"]
    with pytest.raises(m.SettlementEvaluationError):
        m.exact_filtered_market(
            expected_ticker="KX-A",
            payload={"markets": [wrong]},
            allow_zero=True,
        )


def test_atomic_write_refuses_nonidentical_overwrite(tmp_path):
    path = tmp_path / "x.json"
    first = {"a": 1}
    second = {"a": 2}
    m.atomic_write_json(path, first)
    assert m.atomic_write_json(path, first) == m.sha256_file(path)
    with pytest.raises(m.SettlementEvaluationError):
        m.atomic_write_json(path, second)
