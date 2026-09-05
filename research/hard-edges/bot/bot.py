"""Live next-block arbitrage detector/executor for Base (public RPC only, no own node).

Watches three WETH/USDC concentrated-liquidity pools, keeps their state (sqrt price, liquidity, tick map) from
block logs, and every block solves the exact two-pool cycle (sell X on pool A, buy X back on pool B) with a
tick-by-tick simulator. When the best cycle clears gas + threshold it verifies the bundle with eth_call against
the deployed TwoPoolArb contract and sends it. Without PRIVATE_KEY/EXECUTOR it runs in dry-run mode and only logs.

Usage:  python3 bot.py                  (dry run)
        EXECUTOR=0x... PRIVATE_KEY=0x... python3 bot.py
Env:    RPC_HTTP (comma list), RPC_WS, MIN_PROFIT_USD (default 3), PRIORITY_GWEI (0.02), MAX_GAS_GWEI (0.05), LOG (bot.log.jsonl)
"""
import os, sys, json, time, math, bisect, asyncio, threading, traceback
import requests
from web3 import Web3
from eth_abi import encode, decode

RPCS = [u for u in os.environ.get("RPC_HTTP", "https://mainnet.base.org,https://base-rpc.publicnode.com,https://base.drpc.org").split(",") if u]
WS_URL = os.environ.get("RPC_WS", "wss://base-rpc.publicnode.com")
MIN_PROFIT_USD = float(os.environ.get("MIN_PROFIT_USD", "3"))
PRIORITY_GWEI = float(os.environ.get("PRIORITY_GWEI", "0.02"))
MAX_GAS_GWEI = float(os.environ.get("MAX_GAS_GWEI", "0.05"))
LOG = os.environ.get("LOG", "bot.log.jsonl")
PRECHECK = os.environ.get("PRECHECK", "1") == "1"   # eth_call before sending; 0 = trust the contract's early revert (faster)
EXECUTOR = os.environ.get("EXECUTOR"); KEY = os.environ.get("PRIVATE_KEY")
GAS_UNITS = 340_000; L1_FEE_USD = 0.004
Q96 = 2**96
POOLS = {  # all three: token0 = WETH (18), token1 = USDC (6)
    "uni":  "0xd0b53d9277642d899df5c87a3966a349a798f224",
    "aero": "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59",
    "pcs":  "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38",
}
D0, D1 = 18, 6
T_SWAP  = "0x" + Web3.keccak(text="Swap(address,address,int256,int256,uint160,uint128,int24)").hex()
T_SWAP_PCS = "0x" + Web3.keccak(text="Swap(address,address,int256,int256,uint160,uint128,int24,uint128,uint128)").hex()
T_MINT  = "0x" + Web3.keccak(text="Mint(address,address,int24,int24,uint128,uint256,uint256)").hex()
T_BURN  = "0x" + Web3.keccak(text="Burn(address,int24,int24,uint128,uint256,uint256)").hex()
SEL_EXEC = Web3.keccak(text="execute((address,address,bool,uint256,uint256,uint160,uint160,int256))")[:4].hex()
PARAMS_T = "(address,address,bool,uint256,uint256,uint160,uint160,int256)"

_sess = requests.Session()
def rpc(method, params, timeout=20):
    last = None
    for i in range(8):
        u = RPCS[i % len(RPCS)]
        try:
            j = _sess.post(u, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=timeout).json()
            if "result" in j: return j["result"]
            last = j.get("error")
            if isinstance(last, dict) and (last.get("code") == 3 or "revert" in str(last)): raise RuntimeError(str(last))
        except RuntimeError: raise
        except Exception as e: last = str(e)[:120]
        time.sleep(3.0 if "rate limit" in str(last).lower() else 0.2)
    raise RuntimeError(f"rpc {method} failed: {last}")
def sel(sig): return Web3.keccak(text=sig)[:4].hex()
def call(to, sig, args=(), types=(), out=None, block="latest"):
    data = "0x" + sel(sig) + (encode(list(types), list(args)).hex() if types else "")
    r = rpc("eth_call", [{"to": to, "data": data}, block])
    return decode(list(out), bytes.fromhex(r[2:])) if out else r
def s2(v): return v - 2**256 if v >= 2**255 else v
def log(**kw):
    kw["t"] = time.time()
    with open(LOG, "a") as f: f.write(json.dumps(kw) + "\n")

class PoolSim:
    """Tick-level simulator kept in sync with the chain by block logs. Prices as float sqrt(raw price)."""
    def __init__(self, name, addr):
        self.name, self.addr = name, addr.lower()
        self.refresh_fee()
        self.ts = call(self.addr, "tickSpacing()", out=("int24",))[0]
        self.net = {}; self._keys = None
        self.init_block = None
    def refresh_fee(self): self.fee = call(self.addr, "fee()", out=("uint24",))[0] / 1e6
    def init_state(self, block):
        blk = hex(block)
        slot0 = call(self.addr, "slot0()", block=blk)
        self.sqrtP = int(slot0[2:66], 16) / Q96; self.tick = s2(int(slot0[66:130], 16))
        self.L = call(self.addr, "liquidity()", out=("uint128",), block=blk)[0]
        R = int(math.log(1.01) / math.log(1.0001)); lo_c = (self.tick - R) // self.ts; hi_c = (self.tick + R) // self.ts   # +-1%: arbs move prices by bps; Mint/Burn replay keeps it fresh
        self.s_lo = 1.0001 ** (lo_c * self.ts / 2); self.s_hi = 1.0001 ** ((hi_c + 1) * self.ts / 2)   # known-liquidity window (sqrt prices)
        self.net = {}
        cand = []
        for w in range(lo_c >> 8, (hi_c >> 8) + 1):
            bm = call(self.addr, "tickBitmap(int16)", (w,), ("int16",), out=("uint256",), block=blk)[0]
            if not bm: continue
            for bit in range(256):
                if bm >> bit & 1:
                    c = (w << 8) + bit
                    if lo_c <= c <= hi_c: cand.append(c * self.ts)
        from concurrent.futures import ThreadPoolExecutor
        def fetch(t):
            r = call(self.addr, "ticks(int24)", (t,), ("int24",), block=blk)
            return t, decode(["uint128", "int128"], bytes.fromhex(r[2:130]))[1]
        with ThreadPoolExecutor(3) as ex:
            for t, netl in ex.map(fetch, cand): self.net[t] = netl
        print(f"  {self.name}: tick map {len(cand)} ticks within +-1% at block {block}", flush=True)
        self._keys = None; self.init_block = block
    def keys(self):
        if self._keys is None: self._keys = sorted(k for k, v in self.net.items() if v)
        return self._keys
    def apply(self, l):
        t0 = l["topics"][0]; data = bytes.fromhex(l["data"][2:])
        if t0 in (T_SWAP, T_SWAP_PCS):
            if t0 == T_SWAP: _, _, sp, L, tick = decode(["int256","int256","uint160","uint128","int24"], data)
            else: _, _, sp, L, tick, _, _ = decode(["int256","int256","uint160","uint128","int24","uint128","uint128"], data)
            self.sqrtP = sp / Q96; self.L = L; self.tick = tick
        elif t0 in (T_MINT, T_BURN):
            lo = s2(int(l["topics"][2], 16)); hi = s2(int(l["topics"][3], 16))
            amt = decode(["address","uint128","uint256","uint256"], data)[1] if t0 == T_MINT else decode(["uint128","uint256","uint256"], data)[0]
            sgn = 1 if t0 == T_MINT else -1
            self.net[lo] = self.net.get(lo, 0) + sgn * amt; self.net[hi] = self.net.get(hi, 0) - sgn * amt; self._keys = None
    def _walk(self, zeroForOne, amount, exact_in):
        """Generic tick walk. Returns (amount_in, amount_out, end_sqrtP), or None when the request cannot be served
        inside the known-liquidity window (never extrapolate: an unknown tick map looks like free liquidity)."""
        s, L, tick = self.sqrtP, self.L, self.tick; keys = self.keys(); f = self.fee
        a_in = a_out = 0.0; remaining = float(amount)
        for _ in range(200):
            if remaining <= 0: break
            if s <= self.s_lo or s >= self.s_hi: return None
            if zeroForOne:
                i = bisect.bisect_right(keys, tick) - 1
                nt = keys[i] if i >= 0 else None
                if nt is not None and 1.0001 ** (nt / 2) >= s: nt = keys[i - 1] if i - 1 >= 0 else None
                s_next = 1.0001 ** (nt / 2) if nt is not None else s * 0.5
            else:
                i = bisect.bisect_right(keys, tick)
                nt = keys[i] if i < len(keys) else None
                s_next = 1.0001 ** (nt / 2) if nt is not None else s * 2.0
            if L <= 0:
                if nt is None: return None
                s = s_next; L += (-self.net[nt] if zeroForOne else self.net[nt]); tick = nt - 1 if zeroForOne else nt; continue
            # max amounts to reach s_next within this range
            if zeroForOne:
                dx_full = L * (1 / s_next - 1 / s); dy_full = L * (s - s_next)
                cap_in, cap_out = dx_full / (1 - f), dy_full
            else:
                dy_full = L * (s_next - s); dx_full = L * (1 / s - 1 / s_next)
                cap_in, cap_out = dy_full / (1 - f), dx_full
            need = remaining
            if (exact_in and need >= cap_in) or ((not exact_in) and need >= cap_out):
                a_in += cap_in; a_out += cap_out; remaining -= (cap_in if exact_in else cap_out); s = s_next
                if nt is None: return None
                L += (-self.net[nt] if zeroForOne else self.net[nt]); tick = nt - 1 if zeroForOne else nt
            else:
                if exact_in:
                    net_in = need * (1 - f)
                    if zeroForOne: s_new = 1 / (1 / s + net_in / L); out = L * (s - s_new)
                    else: s_new = s + net_in / L; out = L * (1 / s - 1 / s_new)
                    a_in += need; a_out += out
                else:
                    if zeroForOne: s_new = s - need / L; inn = L * (1 / s_new - 1 / s) / (1 - f)
                    else: s_new = 1 / (1 / s - need / L); inn = L * (s_new - s) / (1 - f)
                    a_in += inn; a_out += need
                s = s_new; remaining = 0
        if remaining > 0 or s <= self.s_lo or s >= self.s_hi: return None
        return a_in, a_out, s
    def exact_in(self, zeroForOne, amount): return self._walk(zeroForOne, amount, True)
    def exact_out(self, zeroForOne, amount): return self._walk(zeroForOne, amount, False)

def best_cycle(pools, eth_usd):
    """For every ordered pair and direction: sell X of tokenIn on A (exact in), buy X back on B (exact out).
    Returns the best dict or None. Profit in tokenOut; converted to USD."""
    best = None
    names = list(pools)
    for a in names:
        for b in names:
            if a == b: continue
            A, B = pools[a], pools[b]
            for z in (True, False):        # z: sell token0 (WETH) on A
                def profit(x):
                    ra = A.exact_in(z, x); rb = B.exact_out(not z, x)   # buy back x of tokenIn on B
                    if ra is None or rb is None: return -1e300, 0, 0, 0, 0
                    ain, aout, sA = ra; bin_, bout, sB = rb
                    return aout - bin_, aout, bin_, sA, sB
                # quick reject: marginal prices with fees
                pA = A.sqrtP ** 2; pB = B.sqrtP ** 2
                if z and not (pA * (1 - A.fee) > pB / (1 - B.fee)): continue
                if (not z) and not (pB * (1 - B.fee) > pA / (1 - A.fee)): continue
                lo, hi = (1e14, 5e20) if z else (1e5, 5e11)   # 1e-4..500 WETH  /  0.1..500k USDC
                gr = (math.sqrt(5) - 1) / 2
                c, d = hi - gr * (hi - lo), lo + gr * (hi - lo)
                for _ in range(45):
                    if profit(c)[0] > profit(d)[0]: hi = d
                    else: lo = c
                    c, d = hi - gr * (hi - lo), lo + gr * (hi - lo)
                x = (lo + hi) / 2; p, aout, bin_, sA, sB = profit(x)
                if p <= -1e299: continue
                usd = p / 10 ** (D1 if z else D0) * (1.0 if z else eth_usd)
                if best is None or usd > best["usd"]:
                    best = dict(sell=a, buy=b, z=z, x=x, profit=p, usd=usd, out_sell=aout, in_buy=bin_, sA=sA, sB=sB)
    return best

class Bot:
    def __init__(self):
        self.pools = {n: PoolSim(n, a) for n, a in POOLS.items()}
        self.addr_to = {p.addr: p for p in self.pools.values()}
        self.head = int(rpc("eth_blockNumber", []), 16)
        for p in self.pools.values(): p.init_state(self.head)
        self.acct = Web3().eth.account.from_key(KEY) if KEY else None
        self.nonce = int(rpc("eth_getTransactionCount", [self.acct.address, "pending"]), 16) if self.acct else None
        self.pending_until = 0; self.n_blocks = 0
        print(f"init at block {self.head}: " + ", ".join(f"{p.name} fee={p.fee*1e4:.0f}bp ticks={len(p.net)}" for p in self.pools.values()), flush=True)
        print("mode:", "LIVE" if (EXECUTOR and KEY) else "DRY-RUN", "| min profit $%.2f | priority %.3f gwei | gas cap %.3f gwei" % (MIN_PROFIT_USD, PRIORITY_GWEI, MAX_GAS_GWEI), flush=True)
    def eth_usd(self): return self.pools["uni"].sqrtP ** 2 * 10 ** (D0 - D1)
    def on_block(self, n):
        if n <= self.head: return
        t0 = time.time()
        logs = rpc("eth_getLogs", [{"address": list(POOLS.values()), "fromBlock": hex(self.head + 1), "toBlock": hex(n)}])
        for l in sorted(logs, key=lambda l: (int(l["blockNumber"], 16), int(l["logIndex"], 16))):
            p = self.addr_to.get(l["address"].lower())
            if p: p.apply(l)
        self.head = n; self.n_blocks += 1
        if self.n_blocks % 150 == 0:
            for p in self.pools.values(): p.refresh_fee()
        if self.n_blocks % 20000 == 0:
            for p in self.pools.values(): p.init_state(n)     # periodic resync of the tick map (~11h); takes a few minutes on public RPC
        eth = self.eth_usd(); b = best_cycle(self.pools, eth)
        gas_price = int(rpc("eth_gasPrice", []), 16) / 1e9
        gas_usd = GAS_UNITS * (gas_price + PRIORITY_GWEI) * 1e-9 * eth + L1_FEE_USD
        dt = time.time() - t0
        if b and b["usd"] - gas_usd > 0:
            print(f"blk {n} {dt*1000:.0f}ms | {b['sell']}->{b['buy']} sell {'WETH' if b['z'] else 'USDC'} x={b['x']/10**(D0 if b['z'] else D1):.4f} gross ${b['usd']:.2f} gas ${gas_usd:.3f} net ${b['usd']-gas_usd:.2f} | gas {gas_price:.4f} gwei", flush=True)
            log(event="opportunity", block=n, **{k: (v if not isinstance(v, float) or abs(v) < 1e300 else str(v)) for k, v in b.items()}, gas_usd=gas_usd, eth=eth)
            if b["usd"] - gas_usd >= MIN_PROFIT_USD and gas_price <= MAX_GAS_GWEI and time.time() > self.pending_until:
                self.try_execute(b, n, gas_price)
        elif self.n_blocks % 30 == 0:
            print(f"blk {n} {dt*1000:.0f}ms | no edge (best gross ${b['usd']:.3f}) | gas {gas_price:.4f} gwei | ETH {eth:.0f}" if b else f"blk {n} {dt*1000:.0f}ms | no candidate", flush=True)
    def try_execute(self, b, n, gas_price):
        A, B = self.pools[b["sell"]], self.pools[b["buy"]]
        x = int(b["x"]); min_out = int(b["out_sell"] * 0.999)
        lim_sell = int(b["sA"] * Q96 * (0.9995 if b["z"] else 1.0005)); lim_buy = int(b["sB"] * Q96 * (1.0005 if b["z"] else 0.9995))
        min_profit = int(b["profit"] * 0.5)
        params = (Web3.to_checksum_address(A.addr), Web3.to_checksum_address(B.addr), b["z"], x, min_out, lim_sell, lim_buy, min_profit)
        data = "0x" + SEL_EXEC + encode([PARAMS_T], [params]).hex()
        if not (EXECUTOR and self.acct):
            log(event="dry_run_would_send", block=n, params=[str(v) for v in params]); return
        sim_profit = None
        if PRECHECK:
            try:
                r = rpc("eth_call", [{"from": self.acct.address, "to": EXECUTOR, "data": data, "gas": hex(1_500_000)}, "latest"])
                sim_profit = decode(["int256"], bytes.fromhex(r[2:]))[0]
            except Exception as e:
                log(event="precheck_revert", block=n, err=str(e)[:200]); print("  precheck revert:", str(e)[:100], flush=True); return
        tx = {"to": EXECUTOR, "data": data, "gas": GAS_UNITS + 60_000, "chainId": 8453, "nonce": self.nonce, "value": 0,
              "maxFeePerGas": int((gas_price * 2 + PRIORITY_GWEI) * 1e9), "maxPriorityFeePerGas": int(PRIORITY_GWEI * 1e9), "type": 2}
        signed = self.acct.sign_transaction(tx)
        try:
            h = rpc("eth_sendRawTransaction", ["0x" + signed.raw_transaction.hex()])
            self.nonce += 1; self.pending_until = time.time() + 6
            print(f"  SENT {h} sim_profit={sim_profit}", flush=True); log(event="sent", block=n, tx=h, sim_profit=sim_profit, params=[str(v) for v in params])
            threading.Thread(target=self.watch_receipt, args=(h,), daemon=True).start()
        except Exception as e:
            log(event="send_error", block=n, err=str(e)[:200]); print("  send error:", str(e)[:120], flush=True)
            self.nonce = int(rpc("eth_getTransactionCount", [self.acct.address, "pending"]), 16)
    def watch_receipt(self, h):
        for _ in range(40):
            time.sleep(2)
            r = rpc("eth_getTransactionReceipt", [h])
            if r:
                st = int(r["status"], 16); gas = int(r["gasUsed"], 16)
                print(f"  receipt {h[:12]} status={st} gasUsed={gas}", flush=True); log(event="receipt", tx=h, status=st, gasUsed=gas); return

def feed_ws(bot):
    import websockets
    async def run():
        while True:
            try:
                async with websockets.connect(WS_URL, open_timeout=15, ping_interval=20) as ws:
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_subscribe", "params": ["newHeads"]}))
                    await ws.recv()
                    print("ws subscribed", WS_URL, flush=True)
                    while True:
                        m = json.loads(await asyncio.wait_for(ws.recv(), 30))
                        h = m.get("params", {}).get("result")
                        if h:
                            try: bot.on_block(int(h["number"], 16))
                            except Exception: traceback.print_exc()
            except Exception as e:
                print("ws error, falling back to polling for 60s:", str(e)[:80], flush=True)
                t_end = time.time() + 60
                while time.time() < t_end:
                    try: bot.on_block(int(rpc("eth_blockNumber", []), 16))
                    except Exception: traceback.print_exc()
                    time.sleep(0.4)
    asyncio.run(run())

if __name__ == "__main__":
    bot = Bot()
    feed_ws(bot)
