from __future__ import annotations

from src.source_registry import load_source_registry


def test_predexon_tick_source_is_registered_fail_closed() -> None:
    registry = load_source_registry("configs/source_registry.json")
    sources = {s["source_id"]: s for s in registry["sources"]}
    source = sources["predexon.kalshi.historical_orderbook_ticks.v1"]

    assert source["owner"] == "Predexon"
    assert source["transport"] == "https_rest"
    assert source["endpoint_identity"]["method"] == "GET"
    assert source["endpoint_identity"]["path_template"] == "/v2/data/ticks"
    assert source["authentication"]["mode"] == "api_key_header"
    assert source["market_scope"] == ["KXBTCD"]
    assert source["settlement_role"] == "none"
    assert source["collection_state"] == "active"
    assert source["validation_state"] == "validated"

    policy = next(
        p for p in registry["quality_policies"]
        if p["policy_id"] == "read_only_source_quality.v1"
    )
    assert source["source_id"] in policy["scope_source_ids"]
    assert policy["decision_use_default"] == "blocked"
