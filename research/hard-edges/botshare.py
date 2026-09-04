"""Competition density from swap logs: share of swaps where sender==recipient (direct pool callers, i.e. bots),
top senders, and same-block opposite-direction follow-ups (backruns)."""
import json, glob, sys
from collections import Counter
from engine import decode_swap
chain=sys.argv[1]; pools=json.loads(sys.argv[2])
for name,pool in pools.items():
    logs=[]
    for f in glob.glob(f"cache/{chain}_swaps_{pool.lower()}/*.json"): logs+=json.load(open(f))
    ev=sorted([e for e in map(decode_swap,logs) if e], key=lambda e:(e["block"],e["idx"]))
    if not ev: print(name,"no data"); continue
    n=len(ev); direct=sum(1 for e in ev if e["sender"]==e["recipient"])
    senders=Counter(e["sender"] for e in ev); recips=Counter(e["recipient"] for e in ev)
    # backrun: next swap in same block with opposite sign of amount0
    backruns=0; blocks_with_multi=0; per_block=Counter(e["block"] for e in ev)
    for i in range(n-1):
        if ev[i+1]["block"]==ev[i]["block"] and (ev[i+1]["a0"]>0)!=(ev[i]["a0"]>0): backruns+=1
    blocks=len(per_block); span=ev[-1]["block"]-ev[0]["block"]+1
    top=senders.most_common(4)
    print(f"{chain} {name}: swaps={n} blocks_with_swaps={blocks}/{span} ({blocks/span:.2f}) direct(sender==recipient)={direct/n:.2f} backrun_pairs={backruns/n:.2f} distinct_senders={len(senders)}")
    for a,c in top: print(f"    {a} {c/n:.2f} recips={len({e['recipient'] for e in ev if e['sender']==a})}")
