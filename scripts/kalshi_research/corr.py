# Strike-ladder structural arbitrage screen. Live snapshot, fee-aware.
# See docs/KALSHI_STRUCTURAL_ARBITRAGE_SCREEN.md
#
# Structure is read from strike_type, NOT inferred from which strike fields are populated:
# for 'greater'/'less' markets floor_strike == cap_strike, and treating that as a bucket
# manufactured an 85c phantom arbitrage. Only 'between' is a real bucket.
# A ladder is priced only if the partition VERIFIES: cap_less == floor_first,
# floor_greater == cap_last, and every internal gap <= its bucket width.
import json,urllib.request,time,math
from collections import defaultdict
K='https://api.elections.kalshi.com/trade-api/v2/'
SKIP={'Sports','Entertainment','Mentions','Elections','Politics'}
def kget(u):
    for _ in range(3):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'r/1.0'}),timeout=40).read())
        except Exception: time.sleep(1.0)
    return None
def C(m,k):
    try: return float(m.get(k))*100.0
    except Exception: return None
def FP(m,k):
    try: return float(m.get(k))
    except Exception: return 0.0
def S(m,k):
    v=m.get(k)
    return None if v is None else float(v)
d=kget(K+'series?limit=1000') or {}
SER=[s for s in (d.get('series') or []) if (s.get('category') or '?') not in SKIP]
print('target series: %d'%len(SER),flush=True)
MK=[]
for i,s in enumerate(SER):
    st=s.get('ticker')
    if not st: continue
    cur=None
    for _ in range(4):
        r=kget(K+'markets?series_ticker=%s&status=open&limit=1000'%st+(('&cursor='+cur) if cur else ''))
        ms=(r or {}).get('markets') or []
        for m in ms:
            MK.append({'tk':m.get('ticker'),'ser':st,'cat':s.get('category'),
                'sty':m.get('strike_type'),'fl':S(m,'floor_strike'),'cp':S(m,'cap_strike'),
                'yb':C(m,'yes_bid_dollars'),'ya':C(m,'yes_ask_dollars'),
                'bsz':FP(m,'yes_bid_size_fp'),'asz':FP(m,'yes_ask_size_fp'),
                'oi':FP(m,'open_interest_fp'),'v':FP(m,'volume_fp'),
                'liq':FP(m,'liquidity_dollars')})
        cur=(r or {}).get('cursor')
        if not cur or not ms: break
    time.sleep(0.22)
    if i%600==0: print('  ...%d/%d, %d mkts'%(i,len(SER),len(MK)),flush=True)
print('open markets: %d'%len(MK),flush=True)
json.dump(MK,open('/data/corr_snap.json','w'))
cs=defaultdict(int)
for m in MK: cs[m['sty']]+=1
print('strike_type census: %s'%', '.join('%s=%d'%x for x in sorted(cs.items(),key=lambda x:-x[1])))
print('markets with oi>0: %d   with liquidity>0: %d'%(sum(1 for m in MK if m['oi']>0),sum(1 for m in MK if m['liq']>0)))
UP={'greater','greater_or_equal'}; DN={'less','less_or_equal'}
SUB=defaultdict(list)
for m in MK:
    t=m['tk'] or ''
    # group by ticker minus its final strike token, NOT by event_ticker: MLB player props
    # share an event but are different subjects and must never be paired as nested strikes.
    SUB['-'.join(t.split('-')[:-1]) if '-' in t else t].append(m)
N=100
def fee(p): return math.ceil(7.0*N*p*(1.0-p))/float(N)
def buy_yes(m): return None if (m['ya'] is None or m['ya']>=100 or m['asz']<=0) else m['ya']+fee(m['ya']/100.0)
def buy_no(m):
    if m['yb'] is None or m['yb']<=0 or m['bsz']<=0: return None
    q=100.0-m['yb']; return q+fee(q/100.0)
H=[];CN=defaultdict(int)
for key,ms in SUB.items():
    up=sorted([m for m in ms if m['sty'] in UP and m['fl'] is not None],key=lambda m:m['fl'])
    dn=sorted([m for m in ms if m['sty'] in DN and m['cp'] is not None],key=lambda m:m['cp'])
    bt=sorted([m for m in ms if m['sty']=='between' and m['fl'] is not None and m['cp'] is not None],key=lambda m:m['fl'])
    if len(set(m['fl'] for m in up))<len(up): up=[]     # tied strikes = not a real ladder
    if len(set(m['cp'] for m in dn))<len(dn): dn=[]
    if up: CN['grp_up']+=1
    if dn: CN['grp_dn']+=1
    if bt: CN['grp_bt']+=1
    for A,B,tag in [(up[i],up[j],'UP') for i in range(len(up)) for j in range(i+1,len(up))]+ \
                   [(dn[j],dn[i],'DN') for i in range(len(dn)) for j in range(i+1,len(dn))]:
        cy=buy_yes(A); cn=buy_no(B)
        if cy is None or cn is None: continue
        CN['pairs_nested']+=1
        e=100.0-cy-cn
        if e>0:
            sz=min(A['asz'],B['bsz'])
            H.append((e,'NESTED-'+tag,key,sz,e*sz/100.0,min(A['oi'],B['oi']),
                'buy YES %s @%.0f + buy NO %s @%.0f'%(A['tk'].split('-')[-1],A['ya'],B['tk'].split('-')[-1],100-B['yb'])))
    if len(bt)>=2 and len(dn)==1 and len(up)==1:
        ok=(dn[0]['cp']==bt[0]['fl']) and (up[0]['fl']==bt[-1]['cp'])
        for i in range(len(bt)-1):
            w=bt[i]['cp']-bt[i]['fl']; g=bt[i+1]['fl']-bt[i]['cp']
            if not (g>0 and g<=max(w,1e-9)): ok=False
        CN['partition_checked']+=1
        if not ok: CN['partition_incomplete']+=1
        else:
            CN['partition_ok']+=1
            full=[dn[0]]+bt+[up[0]]
            cy=[buy_yes(m) for m in full]
            if all(x is not None for x in cy):
                CN['ladder_priced']+=1
                e=100.0-sum(cy)
                if e>0:
                    sz=min(m['asz'] for m in full)
                    H.append((e,'LADBUY%d'%len(full),key,sz,e*sz/100.0,min(m['oi'] for m in full),
                        'buy all %d, sum_ask=%.0f'%(len(full),sum(m['ya'] for m in full))))
                cnl=[buy_no(m) for m in full]
                if all(x is not None for x in cnl):
                    e2=(len(full)-1)*100.0-sum(cnl)
                    if e2>0:
                        sz=min(m['bsz'] for m in full)
                        H.append((e2,'LADSELL%d'%len(full),key,sz,e2*sz/100.0,min(m['oi'] for m in full),
                            'sell all %d, sum_bid=%.0f'%(len(full),sum(m['yb'] for m in full))))
            for i in range(len(full)):
                for j in range(i+1,len(full)):
                    A,B=full[i],full[j]
                    ca,cb=buy_no(A),buy_no(B)
                    if ca is None or cb is None: continue
                    CN['pairs_excl']+=1
                    e=100.0-ca-cb
                    if e>0:
                        sz=min(A['bsz'],B['bsz'])
                        H.append((e,'EXCL2',key,sz,e*sz/100.0,min(A['oi'],B['oi']),
                            'sell %s @%.0f + sell %s @%.0f'%(A['tk'].split('-')[-1],A['yb'],B['tk'].split('-')[-1],B['yb'])))
print('')
print('COUNTS: '+'  '.join('%s=%d'%x for x in sorted(CN.items())))
H.sort(key=lambda x:-x[4])      # rank by DOLLARS available, not cents per contract
print('')
print('=== VIOLATIONS net of fees, sorted by DOLLARS AVAILABLE ===')
if not H: print('  NONE')
for h in H[:30]:
    print('  %+7.2fc  size %-9.0f = $%-9.2f oi>=%-8.0f %-12s %-26s %s'%(h[0],h[3],h[4],h[5],h[1],h[2][:26],h[6]))
print('')
print('total=%d   with oi>0 both legs=%d   total dollars=$%.2f'%(len(H),sum(1 for h in H if h[5]>0),sum(h[4] for h in H)))
