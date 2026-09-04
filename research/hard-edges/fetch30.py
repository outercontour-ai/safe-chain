"""Swap-only (topic-filtered) 30-day fetch for the busiest Base pools; the Aerodrome pool emits ~20 JIT Mint/Burn/Collect per block, so unfiltered logs are 100x larger."""
from chain import *
from engine import TOPIC_UNIV3
h=head("base"); fb=h-int(30*86400/2)
for pool in ("0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59","0xd0b53d9277642d899df5c87a3966a349a798f224"):
    n=0
    # fetch in 1M-block slices to keep memory bounded; chunks are cached on disk anyway
    for a in range(fb, h, 200_000):
        logs=get_logs("base",pool,a,min(a+199_999,h),topics=[TOPIC_UNIV3],cache_key=f"swaponly_{pool}")
        n+=len(logs); print(pool[:10], a, len(logs), flush=True)
    print(pool, "swaps 30d:", n, flush=True)
