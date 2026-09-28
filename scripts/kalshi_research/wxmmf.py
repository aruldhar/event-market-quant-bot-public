# Fetch the Kalshi weather market-making dataset: candles + full trade tapes.
# Writes /data/wxmm.json. ~30 min for ~3,360 markets.
# Docker: sudo docker run -d --name wxmm -v /var/lib/kalshi-research:/data \
#           python:3.12-slim python3 -u /data/wxmmf.py
import json,urllib.request,time,calendar
from collections import defaultdict
K='https://api.elections.kalshi.com/trade-api/v2/'
SER=['KXHIGHNY','KXHIGHTATL','KXHIGHLAX','KXHIGHTPHX','KXLOWTNYC','KXLOWTATL','KXLOWTLAX','KXLOWTPHX']
def kget(u):
    for _ in range(3):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'r/1.0'}),timeout=45).read())
        except Exception: time.sleep(0.9)
    return None
def ep(s):
    try: return calendar.timegm(time.strptime(s[:19],'%Y-%m-%dT%H:%M:%S'))
    except Exception: return None
def dc(d,k):
    try: return float(d.get(k))*100.0
    except Exception: return None
MKS=[]
for st in SER:
    cur=None;n=0
    for _ in range(6):
        r=kget(K+'markets?series_ticker=%s&status=settled&limit=1000'%st+(('&cursor='+cur) if cur else ''))
        ms=(r or {}).get('markets') or []
        for m in ms:
            if m.get('result') not in ('yes','no'): continue
            c=ep(m.get('close_time') or '')
            if c is None: continue
            MKS.append({'tk':m['ticker'],'ser':st,'ev':m.get('event_ticker'),'res':m['result'],
                'fl':None if m.get('floor_strike') is None else float(m['floor_strike']),
                'cp':None if m.get('cap_strike') is None else float(m['cap_strike']),'cl':c})
            n+=1
        cur=(r or {}).get('cursor')
        if not cur or not ms: break
        time.sleep(0.25)
    print('%-12s %d settled markets'%(st,n),flush=True)
print('total markets to pull: %d'%len(MKS),flush=True)
OUT=[];F=defaultdict(int)
for i,m in enumerate(MKS):
    if i%250==0: print('  ...%d/%d  kept=%d'%(i,len(MKS),len(OUT)),flush=True)
    r=kget(K+'series/%s/markets/%s/candlesticks?start_ts=%d&end_ts=%d&period_interval=60'%(m['ser'],m['tk'],m['cl']-42*3600,m['cl']))
    time.sleep(0.24)
    cs=(r or {}).get('candlesticks') or []
    if not cs: F['no_candles']+=1; continue
    cd=[]
    for x in cs:
        yb=x.get('yes_bid') or {}; ya=x.get('yes_ask') or {}
        b=dc(yb,'close_dollars'); a=dc(ya,'close_dollars')
        try: v=float(x.get('volume_fp'))
        except Exception: v=0.0
        cd.append([int(x['end_period_ts']),b,a,v])
    tr=[];cur=None;trunc=False
    for pg in range(8):
        r=kget(K+'markets/trades?ticker=%s&limit=1000'%m['tk']+(('&cursor='+cur) if cur else ''))
        ts=(r or {}).get('trades') or []
        for t in ts:
            e=ep(t.get('created_time') or '')
            try: p=float(t['yes_price_dollars'])*100.0
            except Exception: continue
            try: c=float(t['count_fp'])
            except Exception: c=0.0
            if e is None: continue
            tr.append([e,p,c,t.get('taker_book_side') or '',1 if t.get('is_block_trade') else 0])
        cur=(r or {}).get('cursor')
        if not cur or not ts: break
        if pg==7: trunc=True
        time.sleep(0.24)
    if trunc: F['truncated']+=1
    # /markets/trades returns NEWEST-FIRST. Sorting ascending here is mandatory --
    # see docs/KALSHI_API_SCHEMA_REFERENCE.md for the look-ahead this prevents.
    tr.sort()
    OUT.append({'tk':m['tk'],'ser':m['ser'],'ev':m['ev'],'res':m['res'],'fl':m['fl'],'cp':m['cp'],
                'cl':m['cl'],'c':cd,'t':tr,'trunc':trunc})
    F['kept']+=1
    F['trades']+=len(tr)
json.dump(OUT,open('/data/wxmm.json','w'))
print('')
print('FUNNEL: '+'  '.join('%s=%d'%x for x in sorted(F.items())))
print('CACHED %d markets, %d candles, %d trades -> /data/wxmm.json'%(
    len(OUT),sum(len(r['c']) for r in OUT),sum(len(r['t']) for r in OUT)))
