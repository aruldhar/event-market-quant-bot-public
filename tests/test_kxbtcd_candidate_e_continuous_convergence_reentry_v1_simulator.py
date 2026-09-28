from decimal import Decimal
from src.kxbtcd_candidate_e_continuous_btc_materialization import ContinuousBtcRow,EVENT_CLOSE_UTC,required_minutes,scan_bounds_ms
from src.kxbtcd_candidate_e_continuous_convergence_reentry_v1_simulator import ttc_bucket,domain_label,exact_original_anchor,decision_clock
from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import BookLevel,BookState,VerifiedSegmentTimeline,VerifiedTickerTimeline
def test_ttc_buckets():
    assert ttc_bucket(55*60000)=='55_to_45';assert ttc_bucket(45*60000)=='45_to_30';assert ttc_bucket(30*60000)=='30_to_20';assert ttc_bucket(2*60000)=='5_to_2'
def test_domain_labels():
    assert exact_original_anchor(45*60000);assert domain_label(45*60000)==('exact_original_anchor',False);assert domain_label(20*60000)[1] is True
def test_clock_ignores_deep_only_change():
    e='KXBTCD-26JUL1013';lo,hi=scan_bounds_ms(e)
    s0=BookState(lo,(BookLevel(Decimal('0.40'),Decimal('10.00')),BookLevel(Decimal('0.39'),Decimal('10.00'))),(BookLevel(Decimal('0.42'),Decimal('10.00')),BookLevel(Decimal('0.43'),Decimal('10.00'))))
    s1=BookState(lo+1000,(BookLevel(Decimal('0.40'),Decimal('10.00')),BookLevel(Decimal('0.38'),Decimal('10.00'))),s0.yes_asks)
    s2=BookState(lo+2000,s1.yes_bids,(BookLevel(Decimal('0.42'),Decimal('9.00')),BookLevel(Decimal('0.43'),Decimal('10.00'))))
    tl=VerifiedTickerTimeline('SYNTH',(VerifiedSegmentTimeline(0,lo,hi,(s0,s1,s2)),))
    btc=tuple(ContinuousBtcRow(r.event_ticker,r.event_close_time_utc,r.minute_start_utc,r.minute_end_utc,Decimal('100000')) for r in required_minutes())
    c=decision_clock(event_ticker=e,structural_timelines={'SYNTH':tl},btc_rows=btc);assert lo+1000 not in c;assert lo+2000 in c
