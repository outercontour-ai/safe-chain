"""Exact concentrated-liquidity simulator for sizing hard-edge arbs.
Liquidity map initialised at a block from tickBitmap/ticks (archive calls), then kept current by replaying
Mint/Burn logs; swaps are simulated tick-by-tick (Uniswap V3 / Pancake V3 / Aerodrome-Velodrome Slipstream)."""
import math, json, bisect
from collections import Counter
from chain import *
from eth_abi import decode
from engine import decode_swap, TOPIC_UNIV3, TOPIC_PCSV3, Q96, report

TOPIC_MINT = "0x" + Web3.keccak(text="Mint(address,address,int24,int24,uint128,uint256,uint256)").hex()
TOPIC_BURN = "0x" + Web3.keccak(text="Burn(address,int24,int24,uint128,uint256,uint256)").hex()

def sqrt_at_tick(t): return 1.0001 ** (t/2)

class V3Sim:
    def __init__(self, chain, pool, ts, fee, init_block, words=3, pct=0.05):
        self.chain, self.pool, self.ts, self.f = chain, pool, ts, fee
        self.net = {}         # tick -> liquidityNet
        self.sqrtP = None; self.L = None; self.tick = None
        self.init_block = init_block
        slot0 = call(chain, pool, "slot0()", block=init_block)
        sp = int(slot0[2:66], 16); tick = int(slot0[66:130], 16); tick = tick - 2**256 if tick >= 2**255 else tick
        # slot0 layouts differ across forks but sqrtPriceX96 and tick are always the first two words
        self.sqrtP = sp/Q96; self.tick = tick
        self.L = call(chain, pool, "liquidity()", out=("uint128",), block=init_block)[0]
        # scan only ticks within +-pct of the current price (arb moves are small); fetch ticks() in parallel
        from concurrent.futures import ThreadPoolExecutor
        R = int(math.log(1 + pct) / math.log(1.0001))
        lo_c = (tick - R) // ts; hi_c = (tick + R) // ts
        self.scan_lo = lo_c * ts; self.scan_hi = hi_c * ts
        cand = []
        for w in range(lo_c >> 8, (hi_c >> 8) + 1):
            bm = call(chain, pool, "tickBitmap(int16)", (w,), ("int16",), out=("uint256",), block=init_block)[0]
            if not bm: continue
            for bit in range(256):
                if bm >> bit & 1:
                    c = (w << 8) + bit
                    if lo_c <= c <= hi_c: cand.append(c * ts)
        def fetch(t):
            r = call(chain, pool, "ticks(int24)", (t,), ("int24",), block=init_block)
            gross, net = decode(["uint128","int128"], bytes.fromhex(r[2:66+64]))
            return t, net
        with ThreadPoolExecutor(6) as ex:
            for t, net in ex.map(fetch, cand): self.net[t] = net
        self.n_init_ticks = len(self.net)
    def unapply_log(self, l):
        """Reverse a Mint/Burn (used to roll the liquidity map back from an init-at-head snapshot)."""
        t0 = l["topics"][0]; data = bytes.fromhex(l["data"][2:])
        if t0 == TOPIC_MINT:
            lo = int(l["topics"][2], 16); hi = int(l["topics"][3], 16)
            lo = lo - 2**256 if lo >= 2**255 else lo; hi = hi - 2**256 if hi >= 2**255 else hi
            _, amt, _, _ = decode(["address","uint128","uint256","uint256"], data)
            self.net[lo] = self.net.get(lo, 0) - amt; self.net[hi] = self.net.get(hi, 0) + amt
        elif t0 == TOPIC_BURN:
            lo = int(l["topics"][2], 16); hi = int(l["topics"][3], 16)
            lo = lo - 2**256 if lo >= 2**255 else lo; hi = hi - 2**256 if hi >= 2**255 else hi
            amt, _, _ = decode(["uint128","uint256","uint256"], data)
            self.net[lo] = self.net.get(lo, 0) + amt; self.net[hi] = self.net.get(hi, 0) - amt
    def apply_log(self, l):
        t0 = l["topics"][0]; data = bytes.fromhex(l["data"][2:])
        if t0 == TOPIC_MINT:
            lo = int(l["topics"][2], 16); hi = int(l["topics"][3], 16)
            lo = lo - 2**256 if lo >= 2**255 else lo; hi = hi - 2**256 if hi >= 2**255 else hi
            _, amt, _, _ = decode(["address","uint128","uint256","uint256"], data)
            self.net[lo] = self.net.get(lo, 0) + amt; self.net[hi] = self.net.get(hi, 0) - amt
        elif t0 == TOPIC_BURN:
            lo = int(l["topics"][2], 16); hi = int(l["topics"][3], 16)
            lo = lo - 2**256 if lo >= 2**255 else lo; hi = hi - 2**256 if hi >= 2**255 else hi
            amt, _, _ = decode(["uint128","uint256","uint256"], data)
            self.net[lo] = self.net.get(lo, 0) - amt; self.net[hi] = self.net.get(hi, 0) + amt
        elif t0 in (TOPIC_UNIV3, TOPIC_PCSV3):
            e = decode_swap(l); self.sqrtP = e["sqrtP"]/Q96; self.L = e["L"]; self.tick = e["tick"]
    def _next_tick(self, zeroForOne):
        keys = sorted(k for k, v in self.net.items() if v != 0)
        if zeroForOne:
            i = bisect.bisect_right(keys, self.tick) - 1   # largest initialised tick <= current tick
            return keys[i] if i >= 0 else None
        i = bisect.bisect_right(keys, self.tick)            # smallest initialised tick > current tick
        return keys[i] if i < len(keys) else None
    def swap_to(self, target_sqrt):
        """Simulate swapping until sqrt price hits target. Returns (amount_in_incl_fee, amount_out, ran_dry, crossings)."""
        s, L, tick = self.sqrtP, self.L, self.tick
        net = dict(self.net)
        zeroForOne = target_sqrt < s
        a_in = a_out = 0.0; crossings = 0; dry = False
        for _ in range(500):
            if (zeroForOne and s <= target_sqrt) or (not zeroForOne and s >= target_sqrt): break
            keys = sorted(k for k, v in net.items() if v != 0)
            if zeroForOne:
                i = bisect.bisect_right(keys, tick) - 1
                # the tick at 'tick' itself is the lower bound of the current range only if price is above it
                nt = keys[i] if i >= 0 else None
                if nt is not None and sqrt_at_tick(nt) >= s: nt = keys[i-1] if i-1 >= 0 else None
                s_next = sqrt_at_tick(nt) if nt is not None else 0.0
                s_step = max(s_next, target_sqrt)
                if L > 0:
                    a_in += L*(1/s_step - 1/s)/(1-self.f); a_out += L*(s - s_step)
                elif s_step > target_sqrt: dry = True
                s = s_step
                if s == s_next and nt is not None:
                    L -= net[nt]; tick = nt - 1; crossings += 1
                elif s_next == 0.0 and s > target_sqrt: dry = True; break
            else:
                i = bisect.bisect_right(keys, tick)
                nt = keys[i] if i < len(keys) else None
                s_next = sqrt_at_tick(nt) if nt is not None else float("inf")
                s_step = min(s_next, target_sqrt)
                if L > 0:
                    a_in += L*(s_step - s)/(1-self.f); a_out += L*(1/s - 1/s_step)
                elif s_step < target_sqrt: dry = True
                s = s_step
                if s == s_next and nt is not None:
                    L += net[nt]; tick = nt; crossings += 1
                elif s_next == float("inf") and s < target_sqrt: dry = True; break
            if L <= 0 and ((zeroForOne and s > target_sqrt) or (not zeroForOne and s < target_sqrt)):
                # no liquidity in this range: jump to the next initialised tick
                if (zeroForOne and (nt is None)) or ((not zeroForOne) and (nt is None)): dry = True; break
        return a_in, a_out, dry, crossings

def size_exact(sim, A_raw, allow):
    best = None
    f = sim.f
    if "1to0" in allow:
        s1 = math.sqrt(A_raw/(1-f))
        if s1 < sim.sqrtP:
            a_in, a_out, dry, cr = sim.swap_to(s1)
            prof = a_out - a_in*A_raw
            best = ("sell0", prof, a_in, dry, cr)
    if "0to1" in allow:
        s1 = math.sqrt(A_raw*(1-f))
        if s1 > sim.sqrtP:
            a_in, a_out, dry, cr = sim.swap_to(s1)
            prof = a_out*A_raw - a_in
            c = ("buy0", prof, a_in, dry, cr)
            if best is None or c[1] > best[1]: best = c
    return best

def run(chain, pool, days, anchor, d0, d1, token1_usd=1.0, allow=("0to1","1to0"), anchor_contract=None,
        gas_usd=0.03, min_profit_usd=0.05, checkpoint_blocks=None, label="", to_block=None, verbose=True, words=3, validate=True, init_at_head=False):
    h = to_block or head(chain); span = int(days*86400/CHAINS[chain]["block_time"]); fb = max(1, h-span)
    fee = call(chain, pool, "fee()", out=("uint24",))[0]; f = fee/1e6
    ts = call(chain, pool, "tickSpacing()", out=("int24",))[0]
    clock = BlockClock(chain, fb, h)
    logs = sorted(get_logs(chain, pool, fb, h, cache_key=f"swaps_{pool.lower()}"), key=lambda l:(int(l["blockNumber"],16), int(l["logIndex"],16)))
    if init_at_head:
        # no archive needed: snapshot the tick map at h, then roll Mint/Burn back to fb-1; price state comes from the first Swap
        sim = V3Sim(chain, pool, ts, f, h, words=words)
        for l in reversed(logs): sim.unapply_log(l)
        sim.sqrtP = None; sim.L = None; sim.tick = None
    else:
        sim = V3Sim(chain, pool, ts, f, fb - 1, words=words)
    scale = 10**(d0-d1)
    anchor_txs = {}
    if anchor_contract:
        for l in get_logs(chain, anchor_contract, fb, h, cache_key=f"anchorlogs_{anchor_contract.lower()}"):
            anchor_txs[l["transactionHash"]] = l
    if checkpoint_blocks is None: checkpoint_blocks = int(3600/CHAINS[chain]["block_time"])
    # validation: replay real swaps from pre-state and compare amounts
    val_err = []
    points = [(int(l["blockNumber"],16), int(l["logIndex"],16), l) for l in logs] + [(b, 10**9, None) for b in range(fb, h, checkpoint_blocks)]
    points.sort(key=lambda x:(x[0], x[1]))
    windows = []; cur = None; n_sw = 0; last_e = None
    for b, idx, l in points:
        e = None
        if l is not None:
            if l["topics"][0] in (TOPIC_UNIV3, TOPIC_PCSV3):
                e = decode_swap(l); n_sw += 1
                if validate and sim.L and len(val_err) < 400 and sim.sqrtP:
                    tgt = e["sqrtP"]/Q96
                    if tgt != sim.sqrtP:
                        a_in, a_out, dry, cr = sim.swap_to(tgt)
                        real_in = e["a0"] if e["a0"] > 0 else e["a1"]; real_out = -(e["a1"] if e["a0"] > 0 else e["a0"])
                        if real_in > 0 and not dry: val_err.append((abs(a_in-real_in)/real_in, abs(a_out-real_out)/max(1,real_out), cr))
            sim.apply_log(l)
            if e is None: continue
            last_e = e
        if sim.sqrtP is None or last_e is None: continue
        A = anchor(b, clock.ts(b)); A_raw = A/scale
        P = sim.sqrtP**2*scale; gap = P/A - 1
        r = size_exact(sim, A_raw, set(allow))
        m = dict(gap=gap, P=P, A=A, dir=r[0] if r else None, profit=(r[1]/10**d1*token1_usd - gas_usd) if r else 0.0, amt=r[2] if r else 0, dry=r[3] if r else False)
        opp = m["profit"] > min_profit_usd
        if opp and cur is None:
            cur = dict(open_block=b, open_by_event=e is not None, dir=m["dir"], gap_open=gap, profit_open=m["profit"], profit_max=m["profit"], capped=m["dry"], amt_open=m["amt"], A=A, P=P)
        elif opp: cur["profit_max"] = max(cur["profit_max"], m["profit"])
        elif cur is not None:
            cur.update(close_block=b, blocks_open=b-cur["open_block"], closer_tx=e["tx"] if e else None, closer_sender=e["sender"] if e else None,
                       closer_recipient=e["recipient"] if e else None, closer_in_anchor_tx=(e["tx"] in anchor_txs) if e else None, gap_close=gap)
            windows.append(cur); cur = None
    if cur is not None:
        cur.update(close_block=None, blocks_open=h-cur["open_block"], closer_tx=None, closer_sender=None, closer_recipient=None, closer_in_anchor_tx=None); windows.append(cur)
    res = dict(label=label, chain=chain, pool=pool, fee=fee, tickSpacing=ts, from_block=fb, to_block=h, days=days, n_swaps=n_sw, n_windows=len(windows),
               n_anchor_txs=len(anchor_txs), windows=windows, init_ticks=sim.n_init_ticks,
               validation=dict(n=len(val_err), med_in_err=sorted(x[0] for x in val_err)[len(val_err)//2] if val_err else None, p90_in_err=sorted(x[0] for x in val_err)[int(.9*len(val_err))] if val_err else None, max_in_err=max((x[0] for x in val_err), default=None)))
    if verbose:
        print(f"[sim] init ticks={sim.n_init_ticks} validation(replayed swaps): {res['validation']}")
        report(res)
    return res
