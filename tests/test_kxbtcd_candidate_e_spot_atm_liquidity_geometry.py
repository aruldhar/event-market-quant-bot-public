from src.kxbtcd_candidate_e_spot_atm_liquidity_geometry import (
    ANALYSIS_ID,
    CHECKPOINT_ID,
    EXPECTED_CROSS_SECTION_COUNT,
    EXPECTED_EVENT_COUNT,
    EXPECTED_MINUTE_CROSS_SECTIONS_PER_EVENT,
    EXPECTED_TICKER_COUNT,
)

def test_21n_w_analysis_contract_constants():
    assert CHECKPOINT_ID == "21N-W"
    assert ANALYSIS_ID == "kxbtcd_candidate_e_spot_atm_liquidity_geometry.v1"
    assert EXPECTED_EVENT_COUNT == 4
    assert EXPECTED_MINUTE_CROSS_SECTIONS_PER_EVENT == 54
    assert EXPECTED_CROSS_SECTION_COUNT == 216
    assert EXPECTED_TICKER_COUNT == 623

def test_21n_w_is_geometry_only_by_contract():
    # The materializer imports no outcome reader and its public contract is
    # explicitly descriptive market-universe geometry only.
    from src import kxbtcd_candidate_e_spot_atm_liquidity_geometry as m
    assert "outcome" not in m.ANALYSIS_ID
