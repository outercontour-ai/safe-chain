"""Flashblock-driven variant of bot.py: reacts inside the 2-second block instead of after it.

Event source: the public Base flashblocks stream (wss://mainnet.flashblocks.base.org/ws) publishes a 200 ms sub-block
with raw transactions. The stream carries no receipts, so on every frame that contains user transactions we fetch the
logs of the *pending* block for our pools (one coalesced eth_getLogs('pending') on the flashblocks-aware RPC), apply the
ones we have not seen, re-solve the two-pool cycle and, if it clears the threshold, send immediately: the transaction
lands in a later flashblock of the same block, ahead of block-level bots. Sealed blocks are reconciled afterwards.
Pool state (price, liquidity, tick map) lives in memory; the only per-frame RPC is the pending-logs fetch.
"""
import os, sys, json, time, asyncio, threading, traceback
import websockets, brotli, requests
import bot
from bot import Bot, rpc, log, POOLS, MIN_PROFIT_USD, MAX_GAS_GWEI, GAS_UNITS, PRIORITY_GWEI, L1_FEE_USD, best_cycle

FB_WS = os.environ.get("FB_WS", "wss://mainnet.flashblocks.base.org/ws")
PRECONF = os.environ.get("RPC_PRECONF", "https://mainnet-preconf.base.org")
_sess = requests.Session()

def pending_logs():
    j = _sess.post(PRECONF, json={"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs",
                                  "params": [{"address": list(POOLS.values()), "fromBlock": "pending", "toBlock": "pending"}]}, timeout=5).json()
    return j.get("result") or []

class FlashBot(Bot):
    def __init__(self):
        super().__init__()
        self.seen = set()           # (txhash, logIndex) already applied
        self.cur_block = self.head  # pending block number we are tracking
        self.gas_price = int(rpc("eth_gasPrice", []), 16) / 1e9
        self.last_gas_t = time.time()
        self.lock = threading.Lock()
        self.n_frames = 0; self.n_polls = 0
    def apply_logs(self, logs):
        n = 0
        for l in sorted(logs, key=lambda l: (int(l["blockNumber"], 16), int(l["logIndex"], 16))):
            key = (l["transactionHash"], int(l["logIndex"], 16))
            if key in self.seen: continue
            p = self.addr_to.get(l["address"].lower())
            if p: p.apply(l); n += 1
            self.seen.add(key)
        return n
    def reconcile(self, a, b):
        try:
            sealed = rpc("eth_getLogs", [{"address": list(POOLS.values()), "fromBlock": hex(a), "toBlock": hex(b)}])
        except Exception as e:
            print("reconcile error:", str(e)[:80], flush=True); return
        with self.lock: self.apply_logs(sealed)
    def on_frame(self, block, index, n_txs, t_arrival):
        """called per flashblock; fetch pending logs (coalesced by the caller) and evaluate"""
        with self.lock:
            if block > self.cur_block:
                # new block started: reconcile the previous (now sealed) block off the hot path
                prev_from, prev_to = self.cur_block, block - 1
                threading.Thread(target=self.reconcile, args=(prev_from, prev_to), daemon=True).start()
                if len(self.seen) > 50000: self.seen = set()
                self.cur_block = block; self.head = block - 1; self.n_blocks += 1
                if self.n_blocks % 150 == 0:
                    for p in self.pools.values(): p.refresh_fee()
            if n_txs == 0: return
            t0 = time.time()
            try: logs = pending_logs()
            except Exception as e: print("pending logs error:", str(e)[:80], flush=True); return
            self.n_polls += 1
            applied = self.apply_logs(logs)
            if self.n_polls % 300 == 0:
                print(f"heartbeat: block {block} fb {index} | frames {self.n_frames} polls {self.n_polls} | pending logs {len(logs)} new {applied} | poll {1000*(time.time()-t0):.0f}ms lag {1000*(time.time()-t_arrival):.0f}ms | ETH {self.eth_usd():.0f}", flush=True)
            if applied == 0: return
            if time.time() - self.last_gas_t > 10:
                try: self.gas_price = int(rpc("eth_gasPrice", []), 16) / 1e9; self.last_gas_t = time.time()
                except Exception: pass
            eth = self.eth_usd(); b = best_cycle(self.pools, eth)
            gas_usd = GAS_UNITS * (self.gas_price + PRIORITY_GWEI) * 1e-9 * eth + L1_FEE_USD
            dt = time.time() - t0; lag = time.time() - t_arrival
            if b and b["usd"] - gas_usd > 0:
                print(f"blk {block} fb {index} | +{dt*1000:.0f}ms (lag {lag*1000:.0f}ms) | {b['sell']}->{b['buy']} sell {'WETH' if b['z'] else 'USDC'} x={b['x']/10**(18 if b['z'] else 6):.4f} gross ${b['usd']:.2f} gas ${gas_usd:.3f} net ${b['usd']-gas_usd:.2f}", flush=True)
                log(event="opportunity", block=block, flashblock=index, lag_ms=lag*1000, **{k: v for k, v in b.items() if k in ("sell","buy","z","x","usd","profit","out_sell","in_buy","sA","sB")}, gas_usd=gas_usd, eth=eth)
                if b["usd"] - gas_usd >= MIN_PROFIT_USD and self.gas_price <= MAX_GAS_GWEI and time.time() > self.pending_until:
                    self.try_execute(b, block, self.gas_price)
            elif self.n_polls % 200 == 0:
                print(f"blk {block} fb {index} | {applied} new logs, +{dt*1000:.0f}ms | no edge (best gross ${b['usd']:.3f})" if b else f"blk {block} fb {index} | no candidate", flush=True)

def feed(fbot):
    inflight = {"busy": False}
    def worker(block, index, n_txs, t):
        try: fbot.on_frame(block, index, n_txs, t)
        except Exception: traceback.print_exc()
        finally: inflight["busy"] = False
    async def run():
        while True:
            try:
                async with websockets.connect(FB_WS, open_timeout=15, max_size=2**24) as ws:
                    print("flashblocks stream connected", flush=True)
                    while True:
                        m = await asyncio.wait_for(ws.recv(), 15); t = time.time()
                        j = json.loads(brotli.decompress(m))
                        block = j["metadata"]["block_number"]; index = j["index"]; n_txs = len(j["diff"]["transactions"])
                        fbot.n_frames += 1
                        if inflight["busy"]: continue          # coalesce: the next poll will see this frame's logs too
                        inflight["busy"] = True
                        threading.Thread(target=worker, args=(block, index, n_txs, t), daemon=True).start()
            except Exception as e:
                print("stream error, reconnecting:", str(e)[:80], flush=True); await asyncio.sleep(1)
    asyncio.run(run())

if __name__ == "__main__":
    fbot = FlashBot()
    feed(fbot)
