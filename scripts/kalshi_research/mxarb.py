# Multi-outcome arbitrage screen over mutually_exclusive events.
# See docs/KALSHI_STRUCTURAL_ARBITRAGE_SCREEN.md
#
# mutually_exclusive means AT MOST one YES, not exactly one. So:
#   sell-all / sell-pair need only EXCLUSIVITY  -> sound, arb iff sum(bid) - fees > 100
#   buy-all needs EXHAUSTIVENESS, which the flag does NOT give -> reported as UNVERIFIED
# /events?with_nested_markets=true returns markets inline and exhausts in ~72 pages.
import json,urllib.request,time,math,statistics
from collections import defaultdict
K='https://api.elections.kalshi.com/trade-api/v2/'
def kget(u):
    for _ in range(4):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'r/1.0'}),timeout=60).read())
        except Exception: time.sleep(1.2)
    return None
def C(m,k):
    try: return float(m.get(k))*100.0
    except Exception: return None
def FP(m,k):
    try: return float(m.get(k))
    except Exception: return 0.0
EV=[];cur=None;pg=0
while pg<3000:
    d=kget(K+'events?status=open&with_nested_markets=true&limit=200'+(('&cursor='+cur) if cur else ''))
    es=(d or {}).get('events') or []
    for e in es:
        ms=[]
        for m in (e.get('markets') or []):
            ms.append({'tk':m.get('ticker'),'sub':(m.get('yes_sub_title') or m.get('subtitle') or ''),
                'yb':C(m,'yes_bid_dollars'),'ya':C(m,'yes_ask_dollars'),
                'bsz':FP(m,'yes_bid_size_fp'),'asz':FP(m,'yes_ask_size_fp'),
                'oi':FP(m,'open_interest_fp')})
        EV.append({'ev':e.get('event_ticker'),'cat':e.get('category') or '?','mx':e.get('mutually_exclusive'),
                   'ser':e.get('series_ticker') or '','ti':(e.get('title') or '')[:70],'ms':ms})
    pg+=1
    cur=(d or {}).get('cursor')
    if not cur or not es: break
    if pg%50==0: print('  ...%d pages, %d events'%(pg,len(EV)),flush=True)
    time.sleep(0.20)
print('pages=%d  events=%d  cursor_exhausted=%s'%(pg,len(EV),not cur),flush=True)
json.dump(EV,open('/data/mx_snap.json','w'))
MX=[e for e in EV if e['mx'] and len(e['ms'])>=2]
print('mutually_exclusive events with >=2 markets: %d  (of %d total)'%(len(MX),len(EV)))
cc=defaultdict(int)
for e in MX: cc[e['cat']]+=1
print('by category: %s'%', '.join('%s=%d'%x for x in sorted(cc.items(),key=lambda x:-x[1])))
N=100
def fee(p): return math.ceil(7.0*N*p*(1.0-p))/float(N)
H=[];SB=[];CN=defaultdict(int)
for e in MX:
    ms=e['ms']
    sell=[m for m in ms if m['yb'] is not None and m['yb']>0 and m['bsz']>0]
    sb=sum(m['yb'] for m in ms if m['yb'] is not None)
    sa=sum(m['ya'] for m in ms if m['ya'] is not None)
    if len(sell)==len(ms) and len(ms)>=2:
        CN['fully_quoted']+=1
        SB.append((sb,sa,e['ev'],len(ms),e['ti']))
    if len(sell)>=2:
        CN['sellall_tested']+=1
        f=sum(fee((100.0-m['yb'])/100.0) for m in sell)
        edge=sum(m['yb'] for m in sell)-100.0-f
        if edge>0:
            sz=min(m['bsz'] for m in sell)
            H.append((edge,'SELLALL%d'%len(sell),e['ev'],sz,edge*sz/100.0,min(m['oi'] for m in sell),
                      'sum_bid=%.0f over %d legs | %s'%(sum(m['yb'] for m in sell),len(sell),e['ti'])))
    for i in range(len(sell)):
        for j in range(i+1,len(sell)):
            A,B=sell[i],sell[j]
            CN['pairs']+=1
            edge=A['yb']+B['yb']-100.0-fee((100.0-A['yb'])/100.0)-fee((100.0-B['yb'])/100.0)
            if edge>0:
                sz=min(A['bsz'],B['bsz'])
                H.append((edge,'SELL2',e['ev'],sz,edge*sz/100.0,min(A['oi'],B['oi']),
                          'sell %s @%.0f + sell %s @%.0f'%(A['sub'][:20],A['yb'],B['sub'][:20],B['yb'])))
    buy=[m for m in ms if m['ya'] is not None and m['ya']<100 and m['asz']>0]
    if len(buy)==len(ms) and len(ms)>=2:
        c=sum(m['ya']+fee(m['ya']/100.0) for m in buy)
        if c<100.0:
            CN['buyall_candidate']+=1
            sz=min(m['asz'] for m in buy)
            H.append((100.0-c,'BUY?%d'%len(buy),e['ev'],sz,(100.0-c)*sz/100.0,min(m['oi'] for m in buy),
                      'UNVERIFIED-EXHAUSTIVE sum_ask=%.0f | %s'%(sum(m['ya'] for m in buy),e['ti'])))
print('COUNTS: '+'  '.join('%s=%d'%x for x in sorted(CN.items())))
H.sort(key=lambda x:-x[4])
print('')
print('=== VIOLATIONS net of fees, by DOLLARS AVAILABLE ===')
if not H: print('  NONE')
for h in H[:30]:
    print('  %+7.2fc size %-8.0f = $%-9.2f oi>=%-7.0f %-11s %-24s %s'%(h[0],h[3],h[4],h[5],h[1],h[2][:24],h[6][:70]))
print('')
print('total=%d  dollars=$%.2f'%(len(H),sum(h[4] for h in H)))
print('')
print('=== NEAR MISSES: highest sum_bid on fully-quoted mx events (need >100) ===')
SB.sort(key=lambda x:-x[0])
for sb,sa,ev,n,ti in SB[:20]:
    print('  sum_bid %6.1f  sum_ask %6.1f  legs %2d  %-26s %s'%(sb,sa,n,ev[:26],ti[:44]))
if SB:
    v=[x[0] for x in SB]
    print('  fully-quoted mx events: %d   sum_bid median %.1f  p90 %.1f  max %.1f'%(
        len(v),statistics.median(v),sorted(v)[int(0.9*len(v))],max(v)))
    w=[x[1]-x[0] for x in SB]
    print('  ask-bid spread across the whole partition: median %.1f  min %.1f'%(statistics.median(w),min(w)))
