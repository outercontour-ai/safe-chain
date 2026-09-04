"""Stage 1 of the 'bot blind spots' test: enumerate Uniswap V4 pools WITH hooks on Base whose token pair also has a
clean V3/Aerodrome venue, plus V4 pool activity, over the last N days."""
import sys, json
from collections import Counter, defaultdict
from chain import *
from eth_abi import decode
PM = "0x498581fF718922c3f8e6A244956aF099B2652b2b"       # Uniswap V4 PoolManager, Base
UNIV3 = "0x33128a8fC17869897dcE68Ed026d694621f6FDfD"; AEROCL = "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"; AEROV2 = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
T_INIT = "0x" + Web3.keccak(text="Initialize(bytes32,address,address,uint24,int24,address,uint160,int24)").hex()
T_SWAP = "0x" + Web3.keccak(text="Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)").hex()
DAYS = float(sys.argv[1]) if len(sys.argv) > 1 else 30
h = head("base"); fb = h - int(DAYS*86400/2)
inits = get_logs("base", PM, fb, h, topics=[T_INIT], cache_key="v4_init")
swaps = get_logs("base", PM, fb, h, topics=[T_SWAP], cache_key="v4_swap")
print("V4 pools initialised:", len(inits), "swaps:", len(swaps)); sys.stdout.flush()
nswaps = Counter(l["topics"][1] for l in swaps)
pools = {}
for l in inits:
    pid = l["topics"][1]; c0 = "0x"+l["topics"][2][-40:]; c1 = "0x"+l["topics"][3][-40:]
    fee, ts, hooks, sp, tick = decode(["uint24","int24","address","uint160","int24"], bytes.fromhex(l["data"][2:]))
    pools[pid] = dict(c0=c0, c1=c1, fee=fee, ts=ts, hooks=hooks, block=int(l["blockNumber"],16), n=nswaps.get(pid, 0))
hooked = {k:v for k,v in pools.items() if int(v["hooks"],16) != 0}
print("with hooks:", len(hooked), " hooked pools with >=200 swaps:", sum(1 for v in hooked.values() if v["n"]>=200))
hookcnt = Counter(v["hooks"] for v in hooked.values()); print("top hook contracts:", hookcnt.most_common(6))
# for the most active hooked pools, look for a clean venue of the same pair
ZERO = "0x"+"0"*40
def clean_venues(a, b):
    out = []
    if a == ZERO: a = "0x4200000000000000000000000000000000000006"   # native ETH -> WETH
    for f in (100, 500, 3000, 10000):
        p = call("base", UNIV3, "getPool(address,address,uint24)", (a, b, f), ("address","address","uint24"), out=("address",))
        if p and int(p[0],16): out.append(("UniV3", f, p[0]))
    for ts in (1, 10, 50, 100, 200, 2000):
        p = call("base", AEROCL, "getPool(address,address,int24)", (a, b, ts), ("address","address","int24"), out=("address",))
        if p and int(p[0],16): out.append(("AeroCL", ts, p[0]))
    for st in (True, False):
        p = call("base", AEROV2, "getPool(address,address,bool)", (a, b, st), ("address","address","bool"), out=("address",))
        if p and int(p[0],16): out.append(("AeroV2", st, p[0]))
    return out
cands = []
for pid, v in sorted(hooked.items(), key=lambda kv: -kv[1]["n"])[:60]:
    venues = clean_venues(v["c0"], v["c1"])
    if venues:
        cands.append(dict(poolId=pid, **v, venues=venues))
        print(f"hooked pool {pid[:12]} swaps={v['n']} fee={v['fee']} hooks={v['hooks'][:10]} c0={v['c0'][:10]} c1={v['c1'][:10]} clean venues={[(a,b,c[:10]) for a,b,c in venues]}")
        sys.stdout.flush()
json.dump(cands, open("quirk_candidates_base.json", "w"))
print("candidates with a clean venue:", len(cands))
