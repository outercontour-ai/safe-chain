"""Per-day table over res_day_*.json: opportunities, wins and $ at 2-flashblock latency, closer concentration."""
import json, glob
from collections import Counter
def pos(b, fb): return (b, fb)
rows = []
for f in sorted(glob.glob("res_day_*.json")):
    if "backtest" in f: continue
    d = json.load(open(f)); b_end = int(f.split("_")[-1].split(".")[0])
    for th in ("1.0", "3.0"):
        ws = [w for w in d[th] if "close_block" in w]
        won = []
        for w in ws:
            our = (w["open_block"], w["open_fb"] + 2) if w["open_fb"] + 2 <= 10 else (w["open_block"] + 1, w["open_fb"] + 2 - 11)
            if our < (w["close_block"], w["close_fb"]): won.append(w)
        top3 = sum(sorted((w["net"] for w in won), reverse=True)[:3])
        rows.append((b_end, th, len(ws), sum(w["net"] for w in ws), len(won), sum(w["net"] for w in won), top3, Counter(w["closer"][:8] for w in ws).most_common(2)))
print("| день (конец, блок) | порог | окон | net на открытии | выиграно (задержка 2) | $ выиграно | топ-3 окна | закрывающие |")
print("|---|---|---|---|---|---|---|---|")
for b, th, n, tot, nw, w_usd, top3, cl in rows:
    print(f"| {b} | ${th} | {n} | ${tot:,.0f} | {nw} | ${w_usd:,.0f} | ${top3:,.0f} | {cl} |")
by_th = {}
for b, th, n, tot, nw, w_usd, top3, cl in rows: by_th.setdefault(th, []).append(w_usd)
for th, v in by_th.items(): print(f"threshold ${th}: days {len(v)}, mean ${sum(v)/len(v):,.0f}/day, min ${min(v):,.0f}, max ${max(v):,.0f}")
