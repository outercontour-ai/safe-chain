"""Historical proxy for flashblock timing: tx-index gap between the opening and the closing swap of same-block windows.
Flashblocks fill sequentially, so gap / TX_PER_FB ~ flashblocks of slack (27.7 txs per flashblock measured live)."""
import json, glob, sys, statistics
from collections import Counter
TX_PER_FB = 327000/11827
src = sys.argv[1] if len(sys.argv) > 1 else "res_xdex2_base_unipcs.json"
idx = {}
for d in glob.glob("cache/base_swaps_0x*") + glob.glob("cache/base_swaponly_0x*"):
    for f in glob.glob(d + "/*.json"):
        for l in json.load(open(f)): idx[l["transactionHash"]] = int(l["transactionIndex"], 16)
rows = json.load(open(src)); d = rows[0]["days"]
cat = Counter(); usd = Counter(); gaps = []; n_same = miss = 0; nb_usd = 0; nb = 0
for r in rows:
    for w in r["windows"]:
        if w.get("close_block") is None: continue
        if w["blocks_open"] >= 1: nb += 1; nb_usd += w["profit_open"]; continue
        n_same += 1; o, c = idx.get(w.get("open_tx")), idx.get(w.get("closer_tx"))
        if o is None or c is None: miss += 1; continue
        g = c - o; gaps.append(g)
        k = "same tx" if g == 0 else ("<1 flashblock" if g < TX_PER_FB else ("1-2 flashblocks" if g < 2*TX_PER_FB else ("2-5 flashblocks" if g < 5*TX_PER_FB else ">5 flashblocks")))
        cat[k] += 1; usd[k] += w["profit_open"]
tot = sum(cat.values())
print(f"{src}: same-block windows {n_same} (indexed {tot}, missing {miss}); next-block-or-later windows {nb} = ${nb_usd/d:,.0f}/day")
for k in ("same tx", "<1 flashblock", "1-2 flashblocks", "2-5 flashblocks", ">5 flashblocks"):
    print(f"   {k:16s} {cat[k]:5d} ({cat[k]/max(1,tot):4.0%})  ${usd[k]/d:7,.0f}/day at open")
reach = sum(cat[k] for k in ("2-5 flashblocks", ">5 flashblocks")); reach_usd = sum(usd[k] for k in ("2-5 flashblocks", ">5 flashblocks"))
print(f"reachable inside the block with >=2 flashblocks of slack: {reach} windows ({reach/max(1,tot):.0%}), ${reach_usd/d:,.0f}/day; block-level bot gets only the ${nb_usd/d:,.0f}/day next-block tier")
if gaps: print("tx-index gap: median", statistics.median(gaps), "p75", sorted(gaps)[int(.75*len(gaps))], "p90", sorted(gaps)[int(.9*len(gaps))])
