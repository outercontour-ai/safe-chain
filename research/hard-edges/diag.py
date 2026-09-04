"""Gap distribution at swap events for cached pools (no sizing)."""
import json, glob, sys
from engine import decode_swap, Q96
from anchor import SSRAnchor, RAY
from chain import *
def load(chain, pool):
    logs=[]
    for f in glob.glob(f"cache/{chain}_swaps_{pool.lower()}/*.json"): logs+=json.load(open(f))
    return sorted([e for e in map(decode_swap, logs) if e], key=lambda e:(e["block"],e["idx"]))
def pct(xs, p): xs=sorted(xs); return xs[min(len(xs)-1,int(p*len(xs)))] if xs else None
a=SSRAnchor("base",days=120); clock=None
for label,pool,d0,d1,anchor in [("Pancake USDS/USDC 0.01%","0x81057171115672ac7d08bbebb04481e19aa0bfeb",18,6,lambda b:1.0),
                                ("AeroCL USDS/USDC ts1","0xa441378a1cb4df371535296e539a1e0def6924e4",18,6,lambda b:1.0),
                                ("UniV3 USDS/USDC 0.05%","0x3b42964f167702bd2ce18e7703fe3bd328aff93c",18,6,lambda b:1.0),
                                ("UniV3 sUSDS/USDC 1%","0x4c9f68e780523feb4c9bb1aad2e5cc3b6476892b",18,6,None),
                                ("AeroCL WETH/superOETHb ts1","0x6446021f4e396da3df4235c62537431372195d38",18,18,lambda b:1.0)]:
    ev=load("base",pool)
    if not ev: print(label,"no events"); continue
    if anchor is None:
        clock=clock or BlockClock("base",ev[0]["block"],ev[-1]["block"])
        anchor=lambda b: a.rate(b,clock.ts(b))/RAY
    gaps=[]; Ls=[]
    for e in ev:
        s=e["sqrtP"]/Q96; P=s*s*10**(d0-d1); gaps.append(P/anchor(e["block"])-1); Ls.append(e["L"])
    ab=[abs(g) for g in gaps]
    fee=call("base",pool,"fee()",out=("uint24",))[0]/1e6
    print(f"{label}: n={len(ev)} fee={fee*1e4:.1f}bp |gap| bp: p50={pct(ab,.5)*1e4:.2f} p90={pct(ab,.9)*1e4:.2f} p99={pct(ab,.99)*1e4:.2f} max={max(ab)*1e4:.2f}  share |gap|>fee: {sum(1 for g in ab if g>fee)/len(ab):.3f}  signed p10={pct(gaps,.1)*1e4:.2f} p90={pct(gaps,.9)*1e4:.2f}  L p50={pct(Ls,.5):.3e}")
    # how many blocks pass with |gap|>fee (post-event state persists until next event)
    over=0; tot=0
    for i in range(len(ev)-1):
        dt=ev[i+1]["block"]-ev[i]["block"]; tot+=dt
        if ab[i]>fee: over+=dt
    print(f"   blocks with |gap|>fee (state held until next swap): {over}/{tot} = {over/max(1,tot):.3f}")
