from __future__ import annotations

from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_strategy_replay_v1 import (
    PRIMARY_EVENT_COUNT,
    PRIMARY_NET_EDGE,
    PRIMARY_ROW_COUNT,
    UNTOUCHED_RESERVE_EVENT_COUNT,
    StrategyReplayPredeclarationError,
    h1_state_id,
    side_fair_probability,
    signal_executable_price,
    signal_net_edge,
    stressed_probability,
    validate_strategy_predeclaration,
)


def test_strategy_predeclaration_validates() -> None:
    document = validate_strategy_predeclaration()
    assert document["strategy_id"] == "kxbtcd_candidate_e_strategy_replay_v1"
    assert document["candidate_id"] == "kxbtcd_btc_distance_offset_logistic.v1"


def test_primary_scope_arithmetic_and_reserve_boundary() -> None:
    assert PRIMARY_EVENT_COUNT == 4070
    assert PRIMARY_ROW_COUNT == 118862
    assert UNTOUCHED_RESERVE_EVENT_COUNT == 4676
    assert PRIMARY_NET_EDGE == 0.04


def test_h1_state_id_matches_frozen_h1_constructor() -> None:
    assert h1_state_id("E", "M", 55, "q30") == "E|M|TTC55|q30"


def test_yes_and_no_executable_prices_are_complements_of_book_sides() -> None:
    assert signal_executable_price(side="YES", yes_bid=0.41, yes_ask=0.43) == pytest.approx(0.43)
    assert signal_executable_price(side="NO", yes_bid=0.41, yes_ask=0.43) == pytest.approx(0.59)


def test_side_fair_probabilities() -> None:
    assert side_fair_probability(side="YES", candidate_probability=0.64) == pytest.approx(0.64)
    assert side_fair_probability(side="NO", candidate_probability=0.64) == pytest.approx(0.36)


def test_signal_net_edge_charges_fee_per_contract() -> None:
    edge = signal_net_edge(
        side_fair_probability_value=0.64,
        executable_price=0.57,
        fee_total_dollars=0.10,
        planned_contracts=10,
    )
    assert edge == pytest.approx(0.06)


def test_uncertainty_stress_shrinks_candidate_toward_market() -> None:
    assert stressed_probability(q_market=0.50, candidate_probability=0.70) == pytest.approx(0.65)
    assert stressed_probability(q_market=0.60, candidate_probability=0.40) == pytest.approx(0.45)


def test_crossed_quote_fails_closed() -> None:
    with pytest.raises(StrategyReplayPredeclarationError):
        signal_executable_price(side="YES", yes_bid=0.60, yes_ask=0.50)


def test_module_contains_no_network_or_execution_surface() -> None:
    text = Path("src/kxbtcd_candidate_e_strategy_replay_v1.py").read_text(encoding="utf-8").lower()
    forbidden = (
        "import requests",
        "import websockets",
        "create_order",
        "cancel_order",
        "/portfolio/",
        "paper broker",
    )
    for token in forbidden:
        assert token not in text
