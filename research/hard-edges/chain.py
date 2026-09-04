"""Shared RPC helpers: multi-endpoint failover, chunked getLogs with cache, historical eth_call."""
import json, os, time, random, requests
from web3 import Web3
from eth_abi import encode, decode

CHAINS = {
 "base":     dict(rpcs=["https://mainnet.base.org","https://base.drpc.org"], block_time=2.0, logs_chunk=10_000),
 "op":       dict(rpcs=["https://mainnet.optimism.io","https://optimism.drpc.org"], block_time=2.0, logs_chunk=10_000),
 "unichain": dict(rpcs=["https://unichain.drpc.org"], block_time=1.0, logs_chunk=10_000),
 "arb":      dict(rpcs=["https://arb1.arbitrum.io/rpc","https://arbitrum.drpc.org"], block_time=0.25, logs_chunk=10_000),
 "eth":      dict(rpcs=["https://ethereum-rpc.publicnode.com","https://eth.drpc.org"], block_time=12.0, logs_chunk=10_000),
}
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
os.makedirs(CACHE, exist_ok=True)
_sess = requests.Session()

class RpcError(Exception): pass
class Reverted(RpcError): pass

def rpc(chain, method, params, timeout=60, tries=6):
    urls = CHAINS[chain]["rpcs"]
    last = None
    for i in range(tries):
        u = urls[i % len(urls)]
        try:
            r = _sess.post(u, json={"jsonrpc":"2.0","id":1,"method":method,"params":params}, timeout=timeout)
            j = r.json()
            if "result" in j: return j["result"]
            last = j.get("error")
            msg = str(last)
            if "revert" in msg or (isinstance(last, dict) and last.get("code") == 3):
                raise Reverted(msg)
            # non-retryable: range/result-size errors -> raise so caller can split
            if any(k in msg for k in ("exceeds", "too large", "limited to", "Block range", "more than")):
                raise RpcError(msg)
        except Reverted: raise
        except RpcError: raise
        except Exception as e:
            last = str(e)[:200]
        time.sleep(min(8, 0.5 * 2**i) + random.random()*0.3)
    raise RpcError(f"{chain} {method} failed: {last}")

def sel(sig): return Web3.keccak(text=sig)[:4].hex()

def call(chain, to, sig, args=(), types=(), block="latest", out=None):
    data = "0x"+sel(sig) + (encode(list(types), list(args)).hex() if types else "")
    blk = block if isinstance(block, str) else hex(block)
    try:
        res = rpc(chain, "eth_call", [{"to": to, "data": data}, blk])
    except Reverted:
        return None
    if out is None: return res
    if res is None or res == "0x": return None
    return decode(list(out), bytes.fromhex(res[2:]))

def head(chain): return int(rpc(chain, "eth_blockNumber", []), 16)

def block_ts(chain, n): return int(rpc(chain, "eth_getBlockByNumber", [hex(n), False])["timestamp"], 16)

def _fetch_range(chain, address, a, b, topics):
    """getLogs for [a,b], splitting on size errors."""
    params = {"address": address, "fromBlock": hex(a), "toBlock": hex(b)}
    if topics: params["topics"] = topics
    try:
        return rpc(chain, "eth_getLogs", [params])
    except RpcError as e:
        if b - a < 20: raise
        m = (a + b) // 2
        return _fetch_range(chain, address, a, m, topics) + _fetch_range(chain, address, m+1, b, topics)

def get_logs(chain, address, from_block, to_block, topics=None, cache_key=None, workers=6):
    """Chunk-aligned cached getLogs (chunks fully inside the range are cached on disk), fetched in parallel."""
    import hashlib
    from concurrent.futures import ThreadPoolExecutor
    key = (cache_key or address.lower()) + ("" if not topics else "_" + hashlib.md5(json.dumps(topics).encode()).hexdigest()[:8])
    d = os.path.join(CACHE, f"{chain}_{key}"); os.makedirs(d, exist_ok=True)
    chunk = CHAINS[chain]["logs_chunk"]
    starts = list(range(from_block - from_block % chunk, to_block + 1, chunk))
    def fetch(s):
        e = s + chunk - 1
        path = os.path.join(d, f"{s}.json")
        if os.path.exists(path):
            try: return json.load(open(path))
            except Exception: pass
        logs = _fetch_range(chain, address, max(s, 1), min(e, to_block), topics)
        if e <= to_block:
            tmp = path + ".tmp"; json.dump(logs, open(tmp, "w")); os.replace(tmp, path)
        return logs
    with ThreadPoolExecutor(workers) as ex:
        parts = list(ex.map(fetch, starts))
    return [l for part in parts for l in part if from_block <= int(l["blockNumber"], 16) <= to_block]

class BlockClock:
    """block -> timestamp. OP-stack chains have a fixed block time; Arbitrum is interpolated from samples."""
    def __init__(self, chain, lo, hi):
        self.chain = chain
        bt = CHAINS[chain]["block_time"]
        n = 2 if bt >= 1.0 else max(2, int((hi - lo) / 200_000) + 2)
        self.samples = []
        for i in range(n):
            b = lo + (hi - lo) * i // (n - 1)
            self.samples.append((b, block_ts(chain, b)))
        if bt >= 1.0:
            (b0, t0), (b1, t1) = self.samples[0], self.samples[-1]
            est = (t1 - t0) / max(1, b1 - b0)
            assert abs(est - bt) < 0.05, f"{chain}: block time {est} != {bt}"
    def ts(self, b):
        import bisect
        bs = [s[0] for s in self.samples]
        i = min(max(bisect.bisect_right(bs, b) - 1, 0), len(self.samples) - 2)
        (b0, t0), (b1, t1) = self.samples[i], self.samples[i+1]
        return int(t0 + (t1 - t0) * (b - b0) / max(1, b1 - b0))

def h2i(x, signed=False, bits=256):
    v = int(x, 16)
    if signed and v >= 2**(bits-1): v -= 2**bits
    return v
