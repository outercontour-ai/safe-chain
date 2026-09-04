"""Stage 3: size the arb on the clean V3 twin (exact tick-map sim) against the hooked V4 pool's price as anchor,
charging the V4 effective (hook) fee per direction. V4 side assumed infinitely deep => upper bound on $."""
import json, sys, bisect
from chain import *
from engine import Q96, report
from engine_v3 import run
from engine_v4 import v4_events, decimals
WETH = "0x4200000000000000000000000000000000000006"; USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"; ZERO = "0x"+"0"*40
ETH_USD = 3500.0
days = float(sys.argv[1]) if len(sys.argv) > 1 else 7
only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
cands = json.load(open("quirk_candidates_base.json"))
h = head("base"); fb = h - int(days*86400/2)
out = []
for c in cands:
    if only and not any(c["poolId"].startswith(o) for o in only): continue
    if c.get("eff_fee") is None or c["eff_fee"] > 0.05: print("skip", c["poolId"][:12], "eff_fee", c.get("eff_fee")); continue
    twin = next((v for v in c["venues"] if v[0] == "UniV3"), None)
    if not twin: continue
    taddr = twin[2]
    t0 = call("base", taddr, "token0()", out=("address",))[0].lower(); t1 = call("base", taddr, "token1()", out=("address",))[0].lower()
    d0 = decimals(t0); d1 = decimals(t1)
    c0w = (WETH if c["c0"] == ZERO else c["c0"]).lower(); c1w = c["c1"].lower()
    invert = (t0 != c0w)
    x = v4_events(c["poolId"], fb, h)
    if len(x) < 20: continue
    xb = [e["block"] for e in x]
    dv0 = decimals(c["c0"]); dv1 = decimals(c["c1"])
    def v4price(b):   # twin orientation, human units (token1 per token0)
        i = bisect.bisect_right(xb, b) - 1
        if i < 0: return None
        p = (x[i]["sqrtP"]/Q96)**2 * 10**(dv0-dv1)   # V4 currency1 per currency0, human
        return (1/p) if invert else p
    f4 = c["eff_fee"]
    res = []
    for allow, adj in (("1to0", 1/(1-f4)), ("0to1", (1-f4))):
        r = run("base", taddr, days, lambda b, t, adj=adj: (None if v4price(b) is None else v4price(b)*adj), d0, d1, token1_usd=1.0, allow=(allow,),
                gas_usd=0.0, min_profit_usd=0.0, label=f"twin {twin[0]} {twin[1]} vs V4 {c['poolId'][:12]} {allow}", to_block=h, words=2, validate=False, verbose=False)
        res.append(r)
    w = sorted(res[0]["windows"] + res[1]["windows"], key=lambda q: q["open_block"])
    # USD conversion of token1 profit + gas
    for q in w:
        if t1 == USDC: usd = 1.0
        elif t1 == WETH: usd = ETH_USD
        elif t0 == WETH: usd = ETH_USD / q["P"]          # token1 is the memecoin: 1 token1 = 1/P WETH
        else: usd = None
        q["profit_open_usd"] = (q["profit_open"]*usd - 0.03) if usd else None
        q["profit_max_usd"] = (q["profit_max"]*usd - 0.03) if usd else None
    w2 = [q for q in w if q["profit_open_usd"] is not None and q["profit_open_usd"] > 0.5]
    closed = [q for q in w2 if q["close_block"] is not None]
    durs = sorted(q["blocks_open"] for q in w2); qf = lambda p: durs[min(len(durs)-1, int(p*len(durs)))] if durs else None
    same = sum(1 for q in closed if q["blocks_open"] == 0)
    from collections import Counter
    print(f"V4 {c['poolId'][:12]} hook={c['hooks'][:10]} eff_fee={f4*1e4:.0f}bp | twin {twin[0]} fee={twin[1]} | windows>$0.5: {len(w2)} ({len(w2)/days:.1f}/d) same-block={same} p50={qf(.5)} p90={qf(.9)} max={durs[-1] if durs else None} | $/day open={sum(q['profit_open_usd'] for q in w2)/days:.0f} max={sum(q['profit_max_usd'] for q in w2)/days:.0f} | median $ open={sorted(q['profit_open_usd'] for q in w2)[len(w2)//2] if w2 else 0:.2f} | closers={Counter(q['closer_sender'] for q in closed).most_common(2)}")
    sys.stdout.flush()
    out.append(dict(poolId=c["poolId"], hooks=c["hooks"], eff_fee=f4, twin=twin, days=days, windows=w2))
    json.dump(out, open("res_quirk_sized_base.json", "w"))
