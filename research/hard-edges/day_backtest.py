"""Replay one day through the live bot's own code (PoolSim + best_cycle): at every swap in any of the three pools,
decide whether the bot would fire (net profit >= threshold after gas), and whether it would have won given a reaction
latency of L flashblocks and the position of the swap that actually closed the opportunity.
Flashblock of a tx = calibrated function of its index in the block (FB_START measured on the live stream)."""
import sys, os, json, glob, time
from collections import Counter, defaultdict
sys.path.insert(0, "/home/user/safe-chain/research/hard-edges/bot")
import bot
from bot import PoolSim, best_cycle, POOLS, D0, D1, GAS_UNITS, L1_FEE_USD
from chain import get_logs, head, CHAINS
from engine import decode_swap, TOPIC_UNIV3, TOPIC_PCSV3
FB_START = [0, 1, 55, 70, 89, 108, 124, 139, 154, 169, 184]
def fb_of(i):
    k = 0
    for j, st in enumerate(FB_START):
        if i >= st: k = j
    return k + max(0, (i - FB_START[-1]) // 15) if i >= FB_START[-1] else k
b_end = int(sys.argv[1]) if len(sys.argv) > 1 else 50878997
b_start = b_end - 43200
THRESHOLDS = [1.0, 3.0]; LATENCIES = [1, 2, 3, 4]
GAS_PRICE_GWEI = 0.01
t0 = time.time()
logs = []
for n, a in POOLS.items():
    ls = get_logs("base", a, b_start, b_end, cache_key=f"swaps_{a.lower()}")
    logs += ls; print(n, "logs", len(ls), flush=True)
logs.sort(key=lambda l: (int(l["blockNumber"], 16), int(l["logIndex"], 16)))
pools = {n: PoolSim(n, a) for n, a in POOLS.items()}
for p in pools.values(): p.init_state(b_start - 1)
print("init done in %.0fs" % (time.time() - t0), flush=True)
addr_to = {p.addr: p for p in pools.values()}
# state machine: an 'opportunity' opens at the first swap after which best net >= threshold (per threshold),
# and closes at the first swap after which it is below. Record opener/closer (block, txIndex).
cur = {th: None for th in THRESHOLDS}
opps = {th: [] for th in THRESHOLDS}
n_swaps = 0; n_eval = 0
n_resync = 0
for l in logs:
    p = addr_to.get(l["address"].lower()); p.apply(l)
    if l["topics"][0] not in (TOPIC_UNIV3, TOPIC_PCSV3): continue
    n_swaps += 1
    if not (p.s_lo < p.sqrtP < p.s_hi):
        p.init_state(int(l["blockNumber"], 16)); n_resync += 1     # price left the known window: resync like the live bot
    blk = int(l["blockNumber"], 16); ti = int(l["transactionIndex"], 16); txh = l["transactionHash"]
    eth = pools["uni"].sqrtP ** 2 * 10 ** (D0 - D1)
    b = best_cycle(pools, eth); n_eval += 1
    gas_usd = GAS_UNITS * (GAS_PRICE_GWEI + 0.02) * 1e-9 * eth + L1_FEE_USD
    net = (b["usd"] - gas_usd) if b else -1
    for th in THRESHOLDS:
        c = cur[th]
        if net >= th and c is None:
            cur[th] = dict(open_block=blk, open_ti=ti, open_tx=txh, open_fb=fb_of(ti), net=net, gross=b["usd"], pair=f"{b['sell']}->{b['buy']}", z=b["z"], x=b["x"], sender=("0x"+l["topics"][1][-40:]))
        elif net >= th and c is not None:
            c["net_max"] = max(c.get("net_max", c["net"]), net)
        elif net < th and c is not None:
            c.update(close_block=blk, close_ti=ti, close_fb=fb_of(ti), closer=("0x"+l["topics"][1][-40:]), close_tx=txh)
            opps[th].append(c); cur[th] = None
print(f"day {b_start}-{b_end}: swaps {n_swaps}, evaluated {n_eval}, tick-map resyncs {n_resync} in {time.time()-t0:.0f}s", flush=True)
for th in THRESHOLDS:
    ws = [w for w in opps[th] if "close_block" in w]
    print(f"\n== threshold ${th}: opportunities {len(ws)} | gross at open sum ${sum(w['gross'] for w in ws):,.0f} | net at open sum ${sum(w['net'] for w in ws):,.0f}")
    clos = Counter(w["closer"][:10] for w in ws); print("   closers:", clos.most_common(4))
    for L in LATENCIES:
        won = []; lost = []
        for w in ws:
            our = (w["open_block"], w["open_fb"] + L) if w["open_fb"] + L <= 10 else (w["open_block"] + 1, w["open_fb"] + L - 11)
            their = (w["close_block"], w["close_fb"])
            (won if our < their else lost).append(w)
        gas_lost = len(lost) * 0.006
        print(f"   latency {L} flashblock(s): won {len(won)}/{len(ws)} -> net ${sum(w['net'] for w in won):,.0f}/day, lost {len(lost)} reverts ≈ -${gas_lost:.1f}; median won ${sorted(w['net'] for w in won)[len(won)//2] if won else 0:.2f}")
json.dump({str(th): opps[th] for th in THRESHOLDS}, open(f"res_day_{b_end}.json", "w"))
