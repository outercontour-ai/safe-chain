"""Backtest for Velodrome/Aerodrome v2 *stable* pools (x^3*y + x*y^3 = k) against a hard anchor.
Pool state from Sync(reserve0, reserve1) events; marginal price and optimal size solved numerically."""
import math, json, sys
from collections import Counter
from chain import *
from eth_abi import decode

TOPIC_SYNC = "0x" + Web3.keccak(text="Sync(uint256,uint256)").hex()
TOPIC_SWAP = "0x" + Web3.keccak(text="Swap(address,address,uint256,uint256,uint256,uint256)").hex()

def _k(x, y):  # in 1e18-normalised units
    a = x*y/1e18; b = (x*x/1e18 + y*y/1e18); return a*b/1e18
def _f(x0, y): return x0*(y*y/1e18*y/1e18)/1e18 + (x0*x0/1e18*x0/1e18)*y/1e18
def _d(x0, y): return 3*x0*(y*y/1e18)/1e18 + (x0*x0/1e18*x0/1e18)
def _get_y(x0, xy, y):
    for _ in range(255):
        k = _f(x0, y)
        if k < xy:
            dy = (xy - k)*1e18/_d(x0, y)
            if dy == 0: return y
            y += dy
        else:
            dy = (k - xy)*1e18/_d(x0, y)
            if dy == 0: return y
            y -= dy
        if abs(dy) < 1: return y
    return y
def amount_out(amount_in, in0, r0, r1, d0, d1, fee):
    """Velodrome v2 stable getAmountOut (float approximation of the integer math)."""
    amount_in = amount_in*(1-fee)
    _r0 = r0*1e18/10**d0; _r1 = r1*1e18/10**d1
    ra, rb = (_r0, _r1) if in0 else (_r1, _r0)
    ain = amount_in*1e18/(10**d0 if in0 else 10**d1)
    xy = _k(_r0, _r1)
    y = rb - _get_y(ain + ra, xy, rb)
    return y*(10**d1 if in0 else 10**d0)/1e18
def marginal_price(r0, r1, d0, d1):
    """token1 per token0 (human units) at zero size, from the stable invariant."""
    eps = r0*1e-6
    out = amount_out(eps, True, r0, r1, d0, d1, 0.0)
    return (out/10**d1)/(eps/10**d0)

def best_size(r0, r1, d0, d1, fee, A, allow):
    """Maximise profit over amount_in for: sell0 (token0 in, token1 out, convert token1->token0 at A) or
    buy0 (token1 in, token0 out, convert token0->token1 at A). Golden-section on log-size. Returns (dir, profit_token1_human, amount_in_human)."""
    best = None
    def prof(dirn, amt):
        if dirn == "sell0":
            out = amount_out(amt*10**d0, True, r0, r1, d0, d1, fee)/10**d1
            return out - amt*A
        else:
            out = amount_out(amt*10**d1, False, r0, r1, d0, d1, fee)/10**d0
            return out*A - amt
    for dirn, cap in (("sell0", r1/10**d1/A*0.999), ("buy0", r0/10**d0*A*0.999)):
        if ("1to0" if dirn=="sell0" else "0to1") not in allow: continue
        lo, hi = 1.0, max(2.0, cap)
        # golden section on concave profit(amount)
        gr = (math.sqrt(5)-1)/2
        a, b = lo, hi
        c = b - gr*(b-a); d = a + gr*(b-a)
        for _ in range(60):
            if prof(dirn, c) > prof(dirn, d): b = d
            else: a = c
            c = b - gr*(b-a); d = a + gr*(b-a)
        amt = (a+b)/2; p = prof(dirn, amt)
        if p > 0 and (best is None or p > best[1]): best = (dirn, p, amt)
    return best

def run(chain, pool, days, anchor, d0, d1, token1_usd=1.0, allow=("0to1","1to0"), anchor_contract=None,
        gas_usd=0.03, min_profit_usd=0.05, checkpoint_blocks=None, label="", to_block=None, verbose=True):
    h = to_block or head(chain); span = int(days*86400/CHAINS[chain]["block_time"]); fb = max(1, h-span)
    fee = call(chain, pool, "fee()") if False else None
    # fee via factory getFee(pool, stable)
    fac = call(chain, pool, "factory()", out=("address",))[0]
    fee_bps = call(chain, fac, "getFee(address,bool)", (pool, True), ("address","bool"), out=("uint256",))[0]; f = fee_bps/1e4
    clock = BlockClock(chain, fb, h)
    logs = get_logs(chain, pool, fb, h, cache_key=f"v2logs_{pool.lower()}")
    ev = []
    last_swap = {}
    for l in sorted(logs, key=lambda l:(int(l["blockNumber"],16), int(l["logIndex"],16))):
        t = l["topics"][0]
        if t == TOPIC_SWAP:
            last_swap = dict(tx=l["transactionHash"], sender="0x"+l["topics"][1][-40:], recipient="0x"+l["topics"][2][-40:])
        elif t == TOPIC_SYNC:
            r0, r1 = decode(["uint256","uint256"], bytes.fromhex(l["data"][2:]))
            ev.append(dict(block=int(l["blockNumber"],16), idx=int(l["logIndex"],16), r0=r0, r1=r1, tx=l["transactionHash"],
                           sender=last_swap.get("sender") if last_swap.get("tx")==l["transactionHash"] else None,
                           recipient=last_swap.get("recipient") if last_swap.get("tx")==l["transactionHash"] else None))
    anchor_txs = {}
    if anchor_contract:
        for l in get_logs(chain, anchor_contract, fb, h, cache_key=f"anchorlogs_{anchor_contract.lower()}"):
            anchor_txs[l["transactionHash"]] = l
    if checkpoint_blocks is None: checkpoint_blocks = int(3600/CHAINS[chain]["block_time"])
    points = [(e["block"], e["idx"], e) for e in ev] + [(b, 10**9, None) for b in range(fb, h, checkpoint_blocks)]
    points.sort(key=lambda x:(x[0], x[1]))
    state = None; windows = []; cur = None; n_ev = 0
    for b, idx, e in points:
        if e is not None: state = e; n_ev += 1
        if state is None or state["r0"] == 0 or state["r1"] == 0: continue
        A = anchor(b, clock.ts(b))
        P = marginal_price(state["r0"], state["r1"], d0, d1)
        r = best_size(state["r0"], state["r1"], d0, d1, f, A, set(allow))
        gap = P/A - 1
        m = dict(gap=gap, P=P, A=A, dir=r[0] if r else None, profit=(r[1]*token1_usd - gas_usd) if r else 0.0, amt=r[2] if r else 0)
        opp = m["profit"] > min_profit_usd
        if opp and cur is None:
            cur = dict(open_block=b, open_by_event=e is not None, dir=m["dir"], gap_open=gap, profit_open=m["profit"], profit_max=m["profit"], capped=False, amt_open=m["amt"], A=A, P=P)
        elif opp: cur["profit_max"] = max(cur["profit_max"], m["profit"])
        elif cur is not None:
            cur.update(close_block=b, blocks_open=b-cur["open_block"], closer_tx=e["tx"] if e else None, closer_sender=e["sender"] if e else None,
                       closer_recipient=e["recipient"] if e else None, closer_in_anchor_tx=(e["tx"] in anchor_txs) if e else None, gap_close=gap)
            windows.append(cur); cur = None
    if cur is not None:
        cur.update(close_block=None, blocks_open=h-cur["open_block"], closer_tx=None, closer_sender=None, closer_recipient=None, closer_in_anchor_tx=None); windows.append(cur)
    res = dict(label=label, chain=chain, pool=pool, fee=fee_bps*100, tickSpacing=0, from_block=fb, to_block=h, days=days, n_swaps=n_ev, n_windows=len(windows), n_anchor_txs=len(anchor_txs), windows=windows)
    if verbose:
        from engine import report; report(res)
    return res
