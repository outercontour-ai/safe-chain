"""Implied effective fee of a V4 pool from its own Swap events (hooks may charge outside the event's fee field):
for in-range swaps, fee-free input for the observed sqrtP move is L*(1/s1-1/s0) (zeroForOne) or L*(s1-s0); fee = 1 - that/amount_in."""
import json, sys
from engine import Q96
def implied_fees(ev):
    fees = []; prev = None
    for e in ev:
        if prev is not None and prev["L"] > 0 and abs(e["L"] - prev["L"]) <= prev["L"]*0.02:   # (almost) same liquidity -> stayed in range
            s0 = prev["sqrtP"]/Q96; s1 = e["sqrtP"]/Q96
            # V4 BalanceDelta is from the swapper's view: negative = paid into the pool
            if e["a0"] < 0 and s1 < s0:      # token0 in
                free = prev["L"]*(1/s1 - 1/s0); fees.append(1 - free/(-e["a0"]))
            elif e["a1"] < 0 and s1 > s0:    # token1 in
                free = prev["L"]*(s1 - s0); fees.append(1 - free/(-e["a1"]))
        prev = e
    fees = sorted(f for f in fees if -0.01 < f < 0.5)
    return (fees[len(fees)//2] if fees else None, len(fees))
if __name__ == "__main__":
    from engine_v4 import v4_events
    from chain import head
    cands = json.load(open("quirk_candidates_base.json"))
    h = head("base"); fb = h - int(7*86400/2)
    for c in cands[:3]:
        ev = v4_events(c["poolId"], fb, h)
        med, n = implied_fees(ev)
        print(c["poolId"][:12], "hook", c["hooks"][:10], "event fee", ev[-1]["fee"] if ev else None, "implied median fee", None if med is None else f"{med*1e4:.0f}bp", "from", n, "in-range swaps")
