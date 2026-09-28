from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_micro_probe_market_terms import (
    MicroProbeMarketTermsError,
    validate_micro_probe_market_terms,
)


def payload(**overrides):
    return {
        "market_ticker": "KXBTCD-EXAMPLE-T100000",
        "observed_utc": "2026-09-08T00:00:00Z",
        "market_response_sha256": "a" * 64,
        "fractional_trading_enabled": True,
        "quantity_increment_contracts": "0.01",
        "price_grid_evidence_id": "market-price-ranges-v1",
        "fee_schedule_id": "reviewed-fee-schedule-v1",
        "fee_schedule_response_sha256": "b" * 64,
        "fee_schedule_effective_utc": "2026-09-08T00:00:00Z",
        **overrides,
    }


def test_market_terms_requires_exact_reviewable_terms_evidence():
    receipt = validate_micro_probe_market_terms(payload())
    assert receipt.quantity_increment_contracts == Decimal("0.01")
    assert receipt.fractional_trading_enabled is True


@pytest.mark.parametrize("overrides, message", [
    ({"fractional_trading_enabled": False}, "fractional"),
    ({"quantity_increment_contracts": "0.02"}, "0.01"),
    ({"fee_schedule_response_sha256": "not-a-hash"}, "hash"),
])
def test_market_terms_fails_closed_on_unproven_quantity_or_fee_evidence(overrides, message):
    with pytest.raises(MicroProbeMarketTermsError, match=message):
        validate_micro_probe_market_terms(payload(**overrides))
