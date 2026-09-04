"""'Sell the gap' test: a one-tick LP position parked on the hard anchor (price 1.0 for DAI/USDC vs LitePSM).
Replays real swaps with the tick map; for each swap computes the token1 volume that passed through the anchor tick,
the pool fees generated inside that tick, and the share a position of size V would have captured (L_me/(L_tick+L_me)).
Inventory risk is capped by the anchor: whatever side you end up holding converts 1:1 at the PSM."""
import sys, math, json, bisect
from chain import *
from engine import decode_swap, Q96
from engine_v3 import V3Sim, TOPIC_UNIV3, TOPIC_PCSV3
chain, pool, days = "eth", "0x5777d92f208679DB4b9778590Fa3CAB3aC9e2168", 45
d0, d1 = 18, 6                      # DAI / USDC
anchor_raw = 10**(d1-d0)            # 1.0 human = 1e-12 raw (USDC per DAI)
sizes_usd = [50_000, 200_000, 1_000_000]
h = head(chain); fb = h - int(days*86400/CHAINS[chain]["block_time"])
fee = call(chain, pool, "fee()", out=("uint24",))[0]/1e6; ts = call(chain, pool, "tickSpacing()", out=("int24",))[0]
logs = sorted(get_logs(chain, pool, fb, h, cache_key=f"swaps_{pool.lower()}"), key=lambda l:(int(l["blockNumber"],16), int(l["logIndex"],16)))
sim = V3Sim(chain, pool, ts, fee, fb-1, words=2)
ta = math.floor(math.log(anchor_raw)/math.log(1.0001)); ta -= ta % ts          # anchor tick (range [ta, ta+ts))
sa, sb = 1.0001**(ta/2), 1.0001**((ta+ts)/2)
print(f"pool fee={fee*1e4:.0f}bp ts={ts} anchor tick={ta} range price {sa*sa*1e12:.5f}-{sb*sb*1e12:.5f}")
def L_at(sim, t):
    """pool liquidity active inside tick range starting at t, derived from current L and the net map"""
    L = sim.L; cur = sim.tick
    if t > cur:
        for k in sorted(k for k in sim.net if cur < k <= t): L += sim.net[k]
    elif t < cur:
        for k in sorted((k for k in sim.net if t < k <= cur), reverse=True): L -= sim.net[k]
    return max(L, 0)
vol_tick = 0.0; fees_tick = 0.0; n_cross = 0; n_touch = 0; n_swaps = 0
my_fees = {v: 0.0 for v in sizes_usd}; share_samples = {v: [] for v in sizes_usd}
in_tick_time = 0; last_block = None; blocks_in = 0
prev = None
for l in logs:
    t0 = l["topics"][0]
    if t0 in (TOPIC_UNIV3, TOPIC_PCSV3) and sim.sqrtP is not None:
        e = decode_swap(l); n_swaps += 1
        s0, s1 = sim.sqrtP, e["sqrtP"]/Q96
        lo, hi = min(s0, s1), max(s0, s1)
        a, b = max(lo, sa), min(hi, sb)
        if b > a:
            La = L_at(sim, ta)
            dy = La*(b - a)                       # token1 (USDC raw) moved inside the anchor tick
            vol = dy/10**d1; vol_tick += vol; fees_tick += vol*fee; n_touch += 1
            if lo <= sa and hi >= sb: n_cross += 1
            for v in sizes_usd:
                L_me = (v*10**d1) / (sb - sa)     # one-tick position fully in token1 terms: V = L*(sb-sa)
                sh = L_me/(La + L_me); my_fees[v] += vol*fee*sh; share_samples[v].append(sh)
    sim.apply_log(l)
    if t0 in (TOPIC_UNIV3, TOPIC_PCSV3):
        b_ = int(l["blockNumber"],16)
        if last_block is not None and sa <= sim.sqrtP < sb: blocks_in += b_ - last_block
        last_block = b_
print(f"{days}d: swaps={n_swaps} touching anchor tick={n_touch} full crossings={n_cross} | volume through tick=${vol_tick:,.0f} (${vol_tick/days:,.0f}/day) pool fees in tick=${fees_tick:,.0f} (${fees_tick/days:.1f}/day)")
print(f"share of time price inside the anchor tick: {blocks_in/(h-fb):.2f}")
for v in sizes_usd:
    sh = sorted(share_samples[v]); med = sh[len(sh)//2] if sh else 0
    print(f"position ${v:,}: fee share median={med:.2f}  fees=${my_fees[v]:,.0f} (${my_fees[v]/days:.2f}/day)  APR={my_fees[v]/days*365/v*100:.1f}%")
