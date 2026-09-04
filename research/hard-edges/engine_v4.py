"""Stage 2 of the 'bot blind spots' test: gap persistence between a Uniswap V4 pool (hooked) and a clean V3/CL venue
of the same pair on Base. No sizing (V4 tick map lives in PoolManager storage); windows = |gap| beyond fee_X+fee_Y."""
import sys, json, bisect
from collections import Counter
from chain import *
from eth_abi import decode
from engine import decode_swap, Q96
PM = "0x498581fF718922c3f8e6A244956aF099B2652b2b"
WETH = "0x4200000000000000000000000000000000000006"; ZERO = "0x"+"0"*40
T_SWAP4 = "0x" + Web3.keccak(text="Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)").hex()

def v4_events(pool_id, fb, h):
    logs = get_logs("base", PM, fb, h, topics=[T_SWAP4, pool_id], cache_key=f"v4pool_{pool_id[2:14]}")
    ev = []
    for l in logs:
        a0, a1, sp, L, tick, fee = decode(["int128","int128","uint160","uint128","int24","uint24"], bytes.fromhex(l["data"][2:]))
        ev.append(dict(block=int(l["blockNumber"],16), idx=int(l["logIndex"],16), tx=l["transactionHash"], sender="0x"+l["topics"][2][-40:], a0=a0, a1=a1, sqrtP=sp, L=L, tick=tick, fee=fee))
    return sorted(ev, key=lambda e:(e["block"], e["idx"]))

def decimals(t): 
    if t == ZERO: return 18
    r = call("base", t, "decimals()", out=("uint8",)); return r[0] if r else 18

def run(cand, days, gas_usd=0.03, verbose=True):
    h = head("base"); fb = h - int(days*86400/2)
    c0, c1 = cand["c0"], cand["c1"]; d0, d1 = decimals(c0), decimals(c1)
    x = v4_events(cand["poolId"], fb, h)
    if len(x) < 20: return None
    # clean venue: first V3/CL venue in the list
    venue = next((v for v in cand["venues"] if v[0] in ("UniV3","AeroCL")), None)
    if venue is None: return None
    vkind, vparam, vaddr = venue
    vt0 = call("base", vaddr, "token0()", out=("address",))[0].lower()
    vfee = call("base", vaddr, "fee()", out=("uint24",))[0]/1e6
    ylogs = get_logs("base", vaddr, fb, h, cache_key=f"swaps_{vaddr.lower()}")
    y = sorted([e for e in map(decode_swap, ylogs) if e], key=lambda e:(e["block"], e["idx"]))
    if len(y) < 20: return None
    c0w = WETH if c0 == ZERO else c0
    invert = (vt0 != c0w.lower())     # venue token0 differs from V4 currency0 -> invert venue price
    scale = 10**(d0-d1)
    yb = [e["block"] for e in y]
    def yprice(b):
        i = bisect.bisect_right(yb, b) - 1
        if i < 0: return None
        p = (y[i]["sqrtP"]/Q96)**2
        p = (1/p) if invert else p
        return p*scale
    # merged timeline: X events + Y events (Y moves can open a window too) + hourly checkpoints
    pts = [(e["block"], e["idx"], "x", e) for e in x] + [(e["block"], e["idx"], "y", e) for e in y]
    pts.sort(key=lambda t:(t[0], t[1]))
    state = None; cur = None; windows = []; last_fee = None
    for b, idx, kind, e in pts:
        if kind == "x": state = e; last_fee = e["fee"]/1e6
        if state is None: continue
        A = yprice(b)
        if A is None: continue
        P = (state["sqrtP"]/Q96)**2*scale
        gap = P/A - 1
        band = last_fee + vfee
        opp = abs(gap) > band
        if opp and cur is None:
            cur = dict(open_block=b, opened_by=kind, gap_open=gap, gap_max=gap, band=band)
        elif opp and cur is not None:
            if abs(gap) > abs(cur["gap_max"]): cur["gap_max"] = gap
        elif (not opp) and cur is not None:
            cur.update(close_block=b, blocks_open=b-cur["open_block"], closed_by=kind, closer=e["sender"] if kind=="x" else e["sender"], closer_tx=e["tx"])
            windows.append(cur); cur = None
    if cur is not None: cur.update(close_block=None, blocks_open=h-cur["open_block"], closed_by=None, closer=None, closer_tx=None); windows.append(cur)
    res = dict(poolId=cand["poolId"], hooks=cand["hooks"], c0=c0, c1=c1, venue=venue, v4_fee_last=last_fee, venue_fee=vfee, days=days, n_x=len(x), n_y=len(y), windows=windows)
    if verbose:
        w = windows; closed = [q for q in w if q["close_block"] is not None]
        durs = sorted(q["blocks_open"] for q in w); qf = lambda p: durs[min(len(durs)-1, int(p*len(durs)))] if durs else None
        same = sum(1 for q in closed if q["blocks_open"] == 0)
        gaps = sorted(abs(q["gap_max"]) for q in w)
        print(f"V4 {cand['poolId'][:12]} hooks={cand['hooks'][:10]} fee={last_fee} vs {vkind} {vparam} fee={vfee} | swaps x={len(x)} y={len(y)} | windows={len(w)} ({len(w)/days:.1f}/d) same-block={same} p50={qf(.5)} p90={qf(.9)} max={durs[-1] if durs else None} | |gap|max p50={gaps[len(gaps)//2]*1e4 if gaps else 0:.0f}bp p90={gaps[int(.9*len(gaps))]*1e4 if gaps else 0:.0f}bp | closers={Counter(q['closer'] for q in closed).most_common(2)}")
    return res

if __name__ == "__main__":
    days = float(sys.argv[1]) if len(sys.argv) > 1 else 7
    cands = json.load(open("quirk_candidates_base.json"))
    out = []
    for c in cands:
        try:
            r = run(c, days)
            if r: out.append(r)
        except Exception as ex: print("ERR", c["poolId"][:12], str(ex)[:120])
        sys.stdout.flush()
        json.dump(out, open("res_quirk_base.json", "w"))
