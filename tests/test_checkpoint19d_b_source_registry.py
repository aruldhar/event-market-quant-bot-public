from __future__ import annotations

from src.source_registry import load_source_registry

EXPECTED_19D_B_SOURCES = {
    "coinbase.exchange.public_rest.product_book.btc_usd.v1",
    "coinbase.exchange.public_rest.product_candles.btc_usd.1m.v1",
    "kraken.spot.public_rest.pretrade.btc_usd.v1",
    "kraken.spot.public_rest.posttrade.btc_usd.v1",
}


def test_checkpoint19d_b_sources_are_registered_and_active() -> None:
    registry = load_source_registry("configs/source_registry.json")
    sources = {source["source_id"]: source for source in registry["sources"]}
    assert EXPECTED_19D_B_SOURCES.issubset(sources)
    for source_id in EXPECTED_19D_B_SOURCES:
        source = sources[source_id]
        assert source["authentication"]["mode"] == "none"
        assert source["collection_state"] == "active"
        assert source["validation_state"] == "validated"
        assert source["settlement_role"] == "none"
        assert source["quality_policy_id"] == "read_only_source_quality.v1"

    generic_policy = next(
        p for p in registry["quality_policies"]
        if p["policy_id"] == "read_only_source_quality.v1"
    )
    assert EXPECTED_19D_B_SOURCES.issubset(set(generic_policy["scope_source_ids"]))
