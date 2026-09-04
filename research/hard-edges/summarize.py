"""Compact comparison table over res_*.json results."""
import json, glob, sys
rows=[]
for f in sorted(glob.glob("res_*.json")):
    for r in json.load(open(f)):
        w=r["windows"]; closed=[x for x in w if x.get("close_block") is not None]
        durs=sorted(x["blocks_open"] for x in w)
        q=lambda p: durs[min(len(durs)-1,int(p*len(durs)))] if durs else None
        rows.append(dict(file=f, label=r["label"], chain=r["chain"], days=r["days"], swaps=r["n_swaps"], windows=len(w),
            per_day=round(len(w)/r["days"],2), same_block=sum(1 for x in closed if x["blocks_open"]==0), p50=q(.5), p90=q(.9),
            usd_open=round(sum(x["profit_open"] for x in w),1), usd_max=round(sum(x["profit_max"] for x in w),1),
            by_anchor=sum(1 for x in closed if x.get("closer_in_anchor_tx")), val=(r.get("validation") or {}).get("med_in_err")))
import pandas as pd
pd.set_option("display.width",250); pd.set_option("display.max_colwidth",70)
df=pd.DataFrame(rows); print(df.drop(columns=["file"]).to_string(index=False))
