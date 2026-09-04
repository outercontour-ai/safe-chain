"""Flashblock-level persistence: which 200 ms sub-block did the opening swap and the closing swap of each window land in?
Uses fb_record.jsonl (tx hash -> block, flashblock index) and the exact engine over the recorded block range."""
import json, sys, bisect
from collections import Counter, defaultdict
from chain import *
from series import SeriesAnchor
from engine_v3 import run
REC = sys.argv[1] if len(sys.argv) > 1 else "/home/user/safe-chain/research/hard-edges/bot/fb_record.jsonl"
fb = {}; blocks = defaultdict(list); nfb = 0
for line in open(REC):
    r = json.loads(line); nfb += 1
    for h in r["txs"]: fb[h if h.startswith("0x") else "0x"+h] = (r["block"], r["index"], r["t"])
    blocks[r["block"]].append(r["index"])
bl = sorted(blocks); b0, b1 = bl[1], bl[-2]      # drop partial edge blocks
print(f"recorded {nfb} flashblocks over blocks {b0}-{b1} ({b1-b0+1} blocks), mean {nfb/len(bl):.1f} flashblocks/block, {len(fb)} txs")
POOLS = {"UniV3 0.05%":"0xd0b53d9277642d899df5c87a3966a349a798f224","AeroCL ts100":"0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59","PancakeV3 0.01%":"0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38"}
d0, d1 = 18, 6
series = {n: SeriesAnchor("base", a, b0, b1, d0, d1) for n, a in POOLS.items()}
fees = {n: call("base", a, "fee()", out=("uint24",))[0]/1e6 for n, a in POOLS.items()}
wins = []
names = list(POOLS)
for X in names:
    for Y in names:
        if X == Y: continue
        sy, fy = series[Y], fees[Y]
        for allow, adj in (("1to0", 1/(1-fy)), ("0to1", 1-fy)):
            r = run("base", POOLS[X], 0, lambda b, t, sy=sy, adj=adj: (None if sy.price(b) is None else sy.price(b)*adj), d0, d1,
                    allow=(allow,), gas_usd=0.03, min_profit_usd=0.5, label=f"{X} vs {Y} {allow}", from_block=b0, to_block=b1, words=2, validate=False, verbose=False, checkpoint_blocks=10**9)
            for w in r["windows"]: w["pair"] = f"{X} vs {Y}"; wins.append(w)
print(f"windows with profit > $0.5 in the recorded range: {len(wins)}  (per day equivalent: {len(wins)/((b1-b0+1)*2/86400):.0f})")
cat = Counter(); detail = []
for w in wins:
    o = fb.get(w.get("open_tx")); c = fb.get(w.get("closer_tx"))
    if w.get("close_block") is None: cat["still open"] += 1; continue
    if o is None or c is None: cat["unmapped"] += 1; continue
    if c[0] > o[0]: k = f"next block (+{c[0]-o[0]})"
    else:
        d = c[1] - o[1]; k = "same flashblock" if d == 0 else ("+1 flashblock" if d == 1 else "+2..9 flashblocks")
    cat[k] += 1; detail.append((k, w["profit_open"], w["pair"], o, c))
tot = sum(cat.values())
print("closure timing of windows (by flashblock of opener vs closer):")
for k, v in cat.most_common(): print(f"   {k:22s} {v:4d}  ({v/tot:.0%})  $ at open: {sum(x[1] for x in detail if x[0]==k):.0f}")
reach = [x for x in detail if x[0] in ("+2..9 flashblocks",) or x[0].startswith("next block")]
print(f"reachable by a flashblock-reactive bot (closer >= 2 flashblocks later or next block): {len(reach)} windows, ${sum(x[1] for x in reach):.0f} at open")
print(f"reachable by a block-level bot (next block only): {sum(1 for x in detail if x[0].startswith('next block'))} windows, ${sum(x[1] for x in detail if x[0].startswith('next block')):.0f}")
json.dump(dict(cat=cat, detail=[(k,p,pair,o,c) for k,p,pair,o,c in detail]), open("res_flashblocks.json","w"))
