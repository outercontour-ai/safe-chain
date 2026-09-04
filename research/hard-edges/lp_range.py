"""Range-LP simulation on a CL pool from cached swaps: a position of $V on [p(1-w), p(1+w)], re-centred when the price
leaves the range (or weekly). Per block: fees share (unstaked) or emissions share (staked), LVR while in range.
Emissions accrue to active liquidity only (share = L_me / (L_active + L_me))."""
import sys, json, glob, math
from chain import *
from engine import decode_swap, Q96
ETH = 2450.0
chain = "base"; pool = sys.argv[3] if len(sys.argv) > 3 else "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"; d0, d1 = 18, 6
emis_usd_per_day = float(sys.argv[1]) if len(sys.argv) > 1 else 16850.0
days_arg = float(sys.argv[2]) if len(sys.argv) > 2 else None
V = 100_000.0
ev = []
files = glob.glob(f"cache/{chain}_swaponly_{pool}*/*.json") or glob.glob(f"cache/{chain}_swaps_{pool}/*.json")
for f in files:
    ev += [e for e in map(decode_swap, json.load(open(f))) if e]
ev.sort(key=lambda e: (e["block"], e["idx"]))
if days_arg: ev = [e for e in ev if e["block"] >= ev[-1]["block"] - int(days_arg*86400/2)]
fee = call(chain, pool, "fee()", out=("uint24",))[0]/1e6
bt = CHAINS[chain]["block_time"]; blocks_per_day = 86400/bt
days = (ev[-1]["block"] - ev[0]["block"])/blocks_per_day
scale = 10**(d0-d1)
print(f"{days:.1f} days, {len(ev)} swaps, fee {fee*1e4:.0f}bp, emissions ${emis_usd_per_day:,.0f}/day, position ${V:,.0f}")
for w in (0.0025, 0.005, 0.01, 0.02, 0.05, 0.10):
    def place(s):   # s = sqrt price raw; returns (L_me, sa, sb)
        p = s*s; pa, pb = p*(1-w), p*(1+w); sa, sb = math.sqrt(pa), math.sqrt(pb)
        Vraw = V*10**d1                         # capital in token1 raw (USDC)
        L = Vraw/((s - sa) + p*(1/s - 1/sb))
        return L, sa, sb
    s_prev = ev[0]["sqrtP"]/Q96; L_me, sa, sb = place(s_prev)
    fees = emis = lvr = rebal_cost = 0.0; n_rebal = 0; in_range_blocks = 0
    last_block = ev[0]["block"]; week_start = ev[0]["block"]
    for e in ev[1:]:
        s = e["sqrtP"]/Q96; L_pool = e["L"]
        # fees (unstaked case): share of the swap's token1 volume that happened inside my range
        lo, hi = min(s_prev, s), max(s_prev, s); a, b = max(lo, sa), min(hi, sb)
        if b > a and L_pool > 0:
            dy = L_pool*(b - a)                  # token1 raw moved inside my range (pool's own L)
            fees += dy/10**d1*fee*L_me/(L_pool + L_me)
        # LVR on my liquidity for the part of the move inside my range
        if b > a: lvr += L_me*(b - a)**2/a/10**d1
        # emissions per block while in range (accrue on block change)
        if e["block"] != last_block:
            db = e["block"] - last_block
            if sa <= s_prev < sb:
                in_range_blocks += db
                emis += emis_usd_per_day/blocks_per_day*db*L_me/(L_pool + L_me)
            last_block = e["block"]
        s_prev = s
        # re-centre when out of range or weekly
        if not (sa <= s < sb) or e["block"] - week_start > 7*blocks_per_day:
            # rebalancing cost: swap ~half the position back to balance at pool fee + 5bp impact
            rebal_cost += V*0.5*(fee + 0.0005); n_rebal += 1
            L_me, sa, sb = place(s); week_start = e["block"]
    apr = lambda x: x/days*365/V*100
    print(f"width ±{w*100:.2f}%: in-range {in_range_blocks/(ev[-1]['block']-ev[0]['block']):.2f} rebalances={n_rebal} | fees {apr(fees):.0f}% emissions {apr(emis):.0f}% LVR {apr(lvr):.0f}% rebal {apr(rebal_cost):.0f}% | net staked {apr(emis-lvr-rebal_cost):.0f}%  net unstaked {apr(fees-lvr-rebal_cost):.0f}%")
