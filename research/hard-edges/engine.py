"""Hard-edge vs AMM backtest engine.
Reconstructs a concentrated-liquidity pool's marginal price from Swap logs, compares it with an anchor
(a hard conversion rate), sizes the within-range arbitrage, and measures how long opportunities stay open
and who closes them (joined with the anchor contract's own event logs by tx hash)."""
import math, json, sys, os, bisect
from collections import Counter, defaultdict
from chain import *
from eth_abi import decode

TOPIC_UNIV3 = "0x" + Web3.keccak(text="Swap(address,address,int256,int256,uint160,uint128,int24)").hex()
TOPIC_PCSV3 = "0x" + Web3.keccak(text="Swap(address,address,int256,int256,uint160,uint128,int24,uint128,uint128)").hex()
Q96 = 2**96

def decode_swap(l):
    t0 = l["topics"][0]
    data = bytes.fromhex(l["data"][2:])
    if t0 == TOPIC_UNIV3: a0,a1,sp,L,tick = decode(["int256","int256","uint160","uint128","int24"], data)
    elif t0 == TOPIC_PCSV3: a0,a1,sp,L,tick,_,_ = decode(["int256","int256","uint160","uint128","int24","uint128","uint128"], data)
    else: return None
    return dict(block=int(l["blockNumber"],16), idx=int(l["logIndex"],16), tx=l["transactionHash"],
                sender="0x"+l["topics"][1][-40:], recipient="0x"+l["topics"][2][-40:], a0=a0, a1=a1, sqrtP=sp, L=L, tick=tick)

def size_within_range(s0, L, A_raw, f, tick, ts, allow):
    """Return (direction, profit_token1_raw, amount_in_raw, capped) for the best arb within the current tick range.
    s0: sqrt price (float, raw units), L: liquidity, A_raw: anchor price token1/token0 in raw units,
    f: fee fraction, tick/ts: current tick & spacing (range cap), allow: set of allowed anchor directions {'0to1','1to0'}."""
    lo_tick = (tick // ts) * ts; hi_tick = lo_tick + ts
    s_lo = 1.0001 ** (lo_tick/2); s_hi = 1.0001 ** (hi_tick/2)
    best = None
    if "1to0" in allow:  # sell token0 into pool (price too high): move s0 -> s1 = sqrt(A/(1-f)) (down)
        s1 = math.sqrt(A_raw/(1-f))
        if s1 < s0 and L > 0:
            capped = s1 < s_lo; s1c = max(s1, s_lo)
            dx_in = L*(1/s1c - 1/s0)/(1-f); dy_out = L*(s0 - s1c)
            prof = dy_out - dx_in*A_raw
            best = ("sell0", prof, dx_in, capped)
    if "0to1" in allow:  # buy token0 from pool (price too low): move s0 -> s1 = sqrt(A*(1-f)) (up)
        s1 = math.sqrt(A_raw*(1-f))
        if s1 > s0 and L > 0:
            capped = s1 > s_hi; s1c = min(s1, s_hi)
            dy_in = L*(s1c - s0)/(1-f); dx_out = L*(1/s0 - 1/s1c)
            prof = dx_out*A_raw - dy_in
            cand = ("buy0", prof, dy_in, capped)
            if best is None or cand[1] > best[1]: best = cand
    return best

def run(chain, pool, days, anchor, d0, d1, token1_usd=1.0, allow=("0to1","1to0"), anchor_contract=None,
        gas_usd=0.03, min_profit_usd=0.05, checkpoint_blocks=None, label="", to_block=None, verbose=True):
    """anchor: callable(block, ts) -> human price of token0 in token1 (e.g. 1.0 for USDS/USDC)."""
    h = to_block or head(chain); span = int(days*86400/CHAINS[chain]["block_time"]); fb = max(1, h-span)
    fee = call(chain, pool, "fee()", out=("uint24",))[0]; f = fee/1e6
    ts = call(chain, pool, "tickSpacing()", out=("int24",))[0]
    clock = BlockClock(chain, fb, h)
    logs = get_logs(chain, pool, fb, h, cache_key=f"swaps_{pool.lower()}")
    ev = sorted([e for e in map(decode_swap, logs) if e], key=lambda e:(e["block"], e["idx"]))
    scale = 10**(d0-d1)
    anchor_txs = {}
    if anchor_contract:
        for l in get_logs(chain, anchor_contract, fb, h, cache_key=f"anchorlogs_{anchor_contract.lower()}"):
            anchor_txs[l["transactionHash"]] = l
    if checkpoint_blocks is None: checkpoint_blocks = int(3600/CHAINS[chain]["block_time"])
    # merge real events with virtual checkpoints (anchor drift can open a window without a pool event)
    points = [(e["block"], e["idx"], e) for e in ev]
    for b in range(fb, h, checkpoint_blocks): points.append((b, 10**9, None))
    points.sort(key=lambda x:(x[0], x[1]))
    state = None; windows = []; cur = None
    def evaluate(b, e_state):
        if e_state is None: return None
        A = anchor(b, clock.ts(b)); A_raw = A/scale
        s0 = e_state["sqrtP"]/Q96
        P = (s0*s0)*scale
        r = size_within_range(s0, e_state["L"], A_raw, f, e_state["tick"], ts, set(allow))
        gap = P/A - 1
        if r is None: return dict(gap=gap, P=P, A=A, dir=None, profit=0.0, capped=False, amt=0)
        d, prof, amt, capped = r
        return dict(gap=gap, P=P, A=A, dir=d, profit=prof/10**d1*token1_usd - gas_usd, capped=capped, amt=amt)
    n_ev = 0
    for b, idx, e in points:
        if e is not None: state = e; n_ev += 1
        m = evaluate(b, state)
        if m is None: continue
        opp = m["profit"] > min_profit_usd
        if opp and cur is None:
            cur = dict(open_block=b, open_by_event=e is not None, dir=m["dir"], gap_open=m["gap"], profit_open=m["profit"], profit_max=m["profit"], capped=m["capped"], amt_open=m["amt"], A=m["A"], P=m["P"])
        elif opp and cur is not None:
            cur["profit_max"] = max(cur["profit_max"], m["profit"])
        elif (not opp) and cur is not None:
            cur.update(close_block=b, blocks_open=b-cur["open_block"], closer_tx=e["tx"] if e else None,
                       closer_sender=e["sender"] if e else None, closer_recipient=e["recipient"] if e else None,
                       closer_in_anchor_tx=(e["tx"] in anchor_txs) if e else None, gap_close=m["gap"])
            windows.append(cur); cur = None
    if cur is not None:
        cur.update(close_block=None, blocks_open=h-cur["open_block"], closer_tx=None, closer_sender=None, closer_recipient=None, closer_in_anchor_tx=None); windows.append(cur)
    res = dict(label=label, chain=chain, pool=pool, fee=fee, tickSpacing=ts, from_block=fb, to_block=h, days=days,
               n_swaps=n_ev, n_windows=len(windows), n_anchor_txs=len(anchor_txs), windows=windows)
    if verbose: report(res, ev)
    return res

def report(res, ev=None):
    w = res["windows"]
    print(f"\n=== {res['label']} | {res['chain']} {res['pool']} fee={res['fee']/1e4:.3f}% ts={res['tickSpacing']} | {res['days']}d blocks {res['from_block']}-{res['to_block']} ===")
    print(f"swaps={res['n_swaps']}  windows(opportunities)={res['n_windows']}  anchor-contract txs in range={res['n_anchor_txs']}")
    if not w: return
    closed = [x for x in w if x["close_block"] is not None]
    by_anchor = [x for x in closed if x["closer_in_anchor_tx"]]
    same_block = [x for x in closed if x["blocks_open"] == 0]
    durs = sorted(x["blocks_open"] for x in w)
    q = lambda p: durs[min(len(durs)-1, int(p*len(durs)))]
    print(f"profit at open: sum=${sum(x['profit_open'] for x in w):.2f} median=${sorted(x['profit_open'] for x in w)[len(w)//2]:.2f} max=${max(x['profit_open'] for x in w):.2f}   (within-range estimate, capped={sum(1 for x in w if x['capped'])})")
    print(f"blocks open: p50={q(.5)} p75={q(.75)} p90={q(.9)} max={durs[-1]}  | closed in same block: {len(same_block)}  | still open at end: {len(w)-len(closed)}")
    print(f"closed by tx that also touched the anchor contract: {len(by_anchor)}/{len(closed)}  profit_open captured by them: ${sum(x['profit_open'] for x in by_anchor):.2f}")
    print(f"opened by pool event: {sum(1 for x in w if x['open_by_event'])} / by anchor drift (checkpoint): {sum(1 for x in w if not x['open_by_event'])}")
    print("directions:", Counter(x["dir"] for x in w))
    c = Counter(x["closer_sender"] for x in closed); print("top closer senders:", c.most_common(5))
    c2 = Counter(x["closer_recipient"] for x in closed); print("top closer recipients:", c2.most_common(5))
    big = sorted(w, key=lambda x:-x["profit_open"])[:5]
    for x in big: print("  big:", {k:(round(v,4) if isinstance(v,float) else v) for k,v in x.items() if k in ("open_block","dir","gap_open","profit_open","profit_max","blocks_open","closer_in_anchor_tx","capped","closer_sender")})
