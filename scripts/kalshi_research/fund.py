# Cross-venue perpetual funding logger. Five-minute polls to /data/funding.jsonl.
# See docs/CROSS_VENUE_PERP_FUNDING_SURVEY.md
#
# Binance returns HTTP 451 from us-east-1 and is deliberately absent.
# Kraken's fundingRate unit was NOT verified, so raw plus both candidate
# normalisations are stored rather than a guess.
# Kalshi perps are probed every cycle: as of 2026-09-28 the series resolve but
# every markets/events endpoint returns empty.
import json,urllib.request,urllib.error,time,traceback
OUT='/data/funding.jsonl'
def get(u,body=None,to=20):
    h={'User-Agent':'r/1.0'}; d=None
    if body: d=body.encode(); h['Content-Type']='application/json'
    r=urllib.request.urlopen(urllib.request.Request(u,data=d,headers=h),timeout=to)
    return json.loads(r.read().decode('utf-8','replace'))
def F(x):
    try: return float(x)
    except Exception: return None
def okx(rows,ts):
    for inst,asset in (('BTC-USDT-SWAP','BTC'),('ETH-USDT-SWAP','ETH')):
        try:
            d=(get('https://www.okx.com/api/v5/public/funding-rate?instId='+inst).get('data') or [{}])[0]
            t=(get('https://www.okx.com/api/v5/market/ticker?instId='+inst).get('data') or [{}])[0]
            fr=F(d.get('fundingRate'))
            rows.append({'ts':ts,'venue':'okx','asset':asset,'interval_h':8,
                'funding_raw':fr,'ann_pct':None if fr is None else fr*3*365*100,
                'premium':F(d.get('premium')),'interest':F(d.get('interestRate')),
                'sett_funding':F(d.get('settFundingRate')),
                'fmax':F(d.get('maxFundingRate')),'fmin':F(d.get('minFundingRate')),
                'bid':F(t.get('bidPx')),'ask':F(t.get('askPx')),
                'bsz':F(t.get('bidSz')),'asz':F(t.get('askSz')),'last':F(t.get('last'))})
        except Exception as e: rows.append({'ts':ts,'venue':'okx','asset':asset,'err':str(e)[:90]})
def hyper(rows,ts):
    try:
        a=get('https://api.hyperliquid.xyz/info',body='{"type":"metaAndAssetCtxs"}')
        uni=a[0]['universe']; ctx=a[1]
        for i,m in enumerate(uni):
            if m.get('name') in ('BTC','ETH') and i<len(ctx):
                c=ctx[i]; fr=F(c.get('funding'))
                rows.append({'ts':ts,'venue':'hyperliquid','asset':m['name'],'interval_h':1,
                    'funding_raw':fr,'ann_pct':None if fr is None else fr*24*365*100,
                    'premium':F(c.get('premium')),'interest':None,
                    'mark':F(c.get('markPx')),'oracle':F(c.get('oraclePx')),'mid':F(c.get('midPx')),
                    'oi':F(c.get('openInterest')),'ntl_vlm':F(c.get('dayNtlVlm')),
                    'impact':c.get('impactPxs')})
    except Exception as e: rows.append({'ts':ts,'venue':'hyperliquid','err':str(e)[:90]})
def kraken(rows,ts):
    try:
        for x in get('https://futures.kraken.com/derivatives/api/v3/tickers').get('tickers') or []:
            if x.get('symbol') in ('PF_XBTUSD','PF_ETHUSD'):
                ix=F(x.get('indexPrice')); fr=F(x.get('fundingRate'))
                rel=None if (ix in (None,0) or fr is None) else fr/ix
                rows.append({'ts':ts,'venue':'kraken','asset':'BTC' if 'XBT' in x['symbol'] else 'ETH',
                    'interval_h':None,'funding_raw':fr,'funding_rel':rel,
                    'ann_pct_if_hourly':None if rel is None else rel*24*365*100,
                    'ann_pct_if_8h':None if rel is None else rel*3*365*100,
                    'pred_raw':F(x.get('fundingRatePrediction')),
                    'mark':F(x.get('markPrice')),'index':ix,
                    'bid':F(x.get('bid')),'ask':F(x.get('ask')),
                    'bsz':F(x.get('bidSize')),'asz':F(x.get('askSize')),
                    'oi':F(x.get('openInterest'))})
    except Exception as e: rows.append({'ts':ts,'venue':'kraken','err':str(e)[:90]})
def kalshi(rows,ts):
    K='https://api.elections.kalshi.com/trade-api/v2/'
    for t in ('KXBTCPERP','KXETHPERP'):
        try:
            d=get(K+'markets?series_ticker=%s&status=open&limit=5'%t)
            ms=d.get('markets') or []
            rows.append({'ts':ts,'venue':'kalshi','asset':t,'n_markets':len(ms),
                         'sample':ms[0] if ms else None})
        except Exception as e: rows.append({'ts':ts,'venue':'kalshi','asset':t,'err':str(e)[:90]})
n=0
while True:
    ts=time.strftime('%Y-%m-%dT%H:%M:%S',time.gmtime())
    rows=[]
    okx(rows,ts); hyper(rows,ts); kraken(rows,ts); kalshi(rows,ts)
    with open(OUT,'a') as f:
        for r in rows: f.write(json.dumps(r)+'\n')
    n+=1
    ok=[r for r in rows if 'err' not in r]
    def g(v,a):
        for r in ok:
            if r.get('venue')==v and r.get('asset')==a: return r.get('ann_pct') or r.get('ann_pct_if_hourly')
        return None
    hb,ob=g('hyperliquid','BTC'),g('okx','BTC')
    print('%s poll=%d rows=%d  BTC ann%%: hyper=%s okx=%s  diff=%s  kalshi_mkts=%s'%(
        ts,n,len(rows),
        'na' if hb is None else '%+.2f'%hb,'na' if ob is None else '%+.2f'%ob,
        'na' if (hb is None or ob is None) else '%+.2f'%(hb-ob),
        [r.get('n_markets') for r in rows if r.get('venue')=='kalshi']),flush=True)
    time.sleep(300)
