from decimal import Decimal
import pytest
from src.kxbtcd_candidate_e_continuous_btc_materialization import *
def rows():return tuple(ContinuousBtcRow(r.event_ticker,r.event_close_time_utc,r.minute_start_utc,r.minute_end_utc,Decimal('100000')+i) for i,r in enumerate(required_minutes()))
def test_required_count():
    assert len(required_minutes())==216
    assert all(len(v)==54 for v in required_minutes_by_event().values())
def test_boundaries_use_exact_preceding_minute():
    for e in EVENT_CLOSE_UTC:
        lo,hi=scan_bounds_ms(e);assert required_minute_for_decision(e,lo).minute_end_ms==lo;assert required_minute_for_decision(e,hi).minute_end_ms==hi
def test_piecewise_causal():
    idx=materialization_index(rows());e='KXBTCD-26JUL1013';lo,_=scan_bounds_ms(e)
    assert btc_row_for_decision(idx,event_ticker=e,decision_timestamp_ms=lo)==btc_row_for_decision(idx,event_ticker=e,decision_timestamp_ms=lo+59999)
    assert btc_row_for_decision(idx,event_ticker=e,decision_timestamp_ms=lo+60000)!=btc_row_for_decision(idx,event_ticker=e,decision_timestamp_ms=lo+59999)
def test_missing_row_fails():
    with pytest.raises(ContinuousBtcMaterializationError):validate_rows(rows()[:-1])
