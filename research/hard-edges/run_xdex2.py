"""Cross-DEX closure speed, v2: pool X sized exactly against pool Y's marginal price WITH Y's fee charged.
sell0 on X (token0 in) needs token1->token0 on Y at P_Y/(1-fY); buy0 on X needs token0->token1 on Y at P_Y*(1-fY).
Y is treated as infinitely deep at its marginal price, so window *existence* is exact, profit is an upper bound."""
import sys, json
from chain import *
from series import SeriesAnchor
from engine_v3 import run
chain = sys.argv[1]; days = float(sys.argv[2]); pools = json.loads(sys.argv[3])
CFG = {"base": dict(d0=18, d1=6, gas=0.03), "op": dict(d0=6, d1=18, gas=0.02), "arb": dict(d0=18, d1=6, gas=0.05)}
c = CFG[chain]; h = head(chain); span = int(days*86400/CHAINS[chain]["block_time"]); fb = h - span
names = list(pools); out = []
series = {n: SeriesAnchor(chain, pools[n], fb, h, c["d0"], c["d1"]) for n in names}
fees = {n: call(chain, pools[n], "fee()", out=("uint24",))[0]/1e6 for n in names}
for n in names: print(n, "swaps:", series[n].n, "fee", fees[n])
pairs = [(names[i], names[j]) for i in range(len(names)) for j in range(len(names)) if i != j]
for X, Y in pairs:
    sy, fy = series[Y], fees[Y]
    res = []
    for allow, adj in (("1to0", 1/(1-fy)), ("0to1", (1-fy))):
        r = run(chain, pools[X], days, lambda b, t, sy=sy, adj=adj: (None if sy.price(b) is None else sy.price(b)*adj), c["d0"], c["d1"],
                token1_usd=1.0 if c["d1"]==6 else 3500.0, allow=(allow,), gas_usd=c["gas"], min_profit_usd=0.5,
                label=f"{chain} X={X} vs Y={Y} dir={allow}", to_block=h, words=2, validate=False, verbose=False, init_at_head=(chain=="arb"))
        res.append(r)
    # merge the two one-directional runs into one report
    w = sorted(res[0]["windows"] + res[1]["windows"], key=lambda x: x["open_block"])
    m = dict(res[0]); m["windows"] = w; m["n_windows"] = len(w); m["label"] = f"{chain} X={X} (fee {fees[X]*1e4:.0f}bp) vs Y={Y} (fee {fy*1e4:.0f}bp charged)"
    from engine import report; report(m)
    out.append(m); sys.stdout.flush()
json.dump(out, open(f"res_xdex2_{chain}.json", "w"))
