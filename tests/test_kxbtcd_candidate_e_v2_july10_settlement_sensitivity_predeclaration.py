from copy import deepcopy
from decimal import Decimal

import pytest

from src import kxbtcd_candidate_e_v2_july10_settlement_sensitivity_predeclaration as m


def test_installed_predeclaration_validates():
    out = m.validate_predeclaration(".")
    assert out["checkpoint_id"] == "21N-Y-E1"
    assert out["official_result_binding"]["robustness_classification_counts"] == {
        "INCONCLUSIVE": 15
    }


def test_observed_manifest_counts_and_outcome_blindness():
    payload = m.load_json(m.OBSERVED_MANIFEST_PATH)
    out = m.validate_observed_manifest(
        payload,
        expected_sha=m.canonical_json_sha(payload),
    )
    assert out["observed_filled_trade_count"] == 93
    assert out["scenario_class_counts"] == {
        "EXACT": 27,
        "CENSORED_SELECTION_REARM_ONLY": 27,
        "CENSORED_LIQUIDATION_ONLY": 3,
        "CENSORED_BOTH": 3,
    }
    assert out["safety"]["settlement_fields_read"] is False


def test_every_observed_trade_has_positive_fill_and_frozen_ticker():
    payload = m.load_json(m.OBSERVED_MANIFEST_PATH)
    tickers = set(payload["settlement_ticker_universe"])
    for row in payload["observed_filled_trades"]:
        assert Decimal(row["entry_filled_quantity"]) > 0
        assert Decimal(row["known_residual_settlement_quantity"]) >= 0
        assert row["market_ticker"] in tickers
        assert row["side"] in {"YES", "NO"}


def test_manifest_rejects_censorship_count_drift():
    payload = m.load_json(m.OBSERVED_MANIFEST_PATH)
    bad = deepcopy(payload)
    bad["scenario_class_counts"]["CENSORED_LIQUIDATION_ONLY"] = 4
    with pytest.raises(m.SensitivityPredeclarationError):
        m.validate_observed_manifest(bad)


def test_manifest_rejects_nonpositive_fill():
    payload = m.load_json(m.OBSERVED_MANIFEST_PATH)
    bad = deepcopy(payload)
    bad["observed_filled_trades"][0]["entry_filled_quantity"] = "0"
    with pytest.raises(m.SensitivityPredeclarationError):
        m.validate_observed_manifest(bad)


def test_policy_selection_and_official_override_are_forbidden():
    out = m.validate_predeclaration(".")
    assert out["interpretation"]["policy_ranking_or_selection_forbidden"] is True
    assert out["interpretation"]["cannot_override_official_inconclusive_result"] is True
    assert out["safety"]["new_outcomes_accessed_during_predeclaration"] is False
