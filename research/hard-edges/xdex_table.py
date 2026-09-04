"""Markdown table from res_xdex2_*.json: closure speed per chain/pair."""
import json, glob
from chain import CHAINS
print("| Чейн | X (сайзится) | Y (якорь) | Окон/день | В том же блоке | p50 блоков (с) | p90 блоков (с) | $/день на открытии | $/день максимум |")
print("|---|---|---|---|---|---|---|---|---|")
for f in sorted(glob.glob("res_xdex2_*.json")):
    for r in json.load(open(f)):
        w=r["windows"]; ch=r["chain"]; bt=CHAINS[ch]["block_time"]; d=r["days"]
        closed=[x for x in w if x.get("close_block") is not None]
        durs=sorted(x["blocks_open"] for x in w)
        q=lambda p: durs[min(len(durs)-1,int(p*len(durs)))] if durs else 0
        lab=r["label"]; X=lab.split("X=")[1].split(" vs ")[0]; Y=lab.split("Y=")[1]
        same=sum(1 for x in closed if x["blocks_open"]==0)
        print(f"| {ch} | {X} | {Y} | {len(w)/d:.1f} | {same}/{len(closed)} | {q(.5)} ({q(.5)*bt:.1f}) | {q(.9)} ({q(.9)*bt:.1f}) | {sum(x['profit_open'] for x in w)/d:.0f} | {sum(x['profit_max'] for x in w)/d:.0f} |")
