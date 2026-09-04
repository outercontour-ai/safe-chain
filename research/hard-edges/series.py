"""Price series of a CL pool from its Swap logs, usable as an anchor for another pool on the same chain."""
import bisect
from chain import *
from engine import decode_swap, Q96
class SeriesAnchor:
    def __init__(self, chain, pool, from_block, to_block, d0, d1, invert=False):
        logs = get_logs(chain, pool, from_block, to_block, cache_key=f"swaps_{pool.lower()}")
        ev = sorted([e for e in map(decode_swap, logs) if e], key=lambda e:(e["block"], e["idx"]))
        scale = 10**(d0-d1)
        self.blocks = [e["block"] for e in ev]
        self.prices = [((e["sqrtP"]/Q96)**2*scale) for e in ev]
        if invert: self.prices = [1/p for p in self.prices]
        self.n = len(ev)
    def price(self, block):
        i = bisect.bisect_right(self.blocks, block) - 1
        return self.prices[i] if i >= 0 else None
