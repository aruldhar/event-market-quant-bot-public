from src.historical_feasibility_schema import (
    CATEGORY_SUMMARY_FIELDS,
    EVENT_FIELDS,
    MARKET_FIELDS,
    OBSERVATION_FIELDS,
    TARGET_CATEGORIES,
    WINDOW_FIELDS,
    validate_schema_contract,
)


def test_schema_is_outcome_blind_and_has_exact_time_to_close():
    validate_schema_contract()
    for fields in (EVENT_FIELDS, MARKET_FIELDS, WINDOW_FIELDS, OBSERVATION_FIELDS, CATEGORY_SUMMARY_FIELDS):
        assert "result" not in fields
    assert "time_to_close_seconds" in OBSERVATION_FIELDS
    assert "time_band" in OBSERVATION_FIELDS
    assert TARGET_CATEGORIES == (
        "Sports",
        "Crypto",
        "Climate and Weather",
        "Commodities",
    )
