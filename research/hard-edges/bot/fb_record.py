"""Record the public Base flashblocks stream: for every flashblock store (block, index, arrival time, tx hashes).
Output: fb_record.jsonl. Used to measure, per swap, in which 200 ms sub-block it landed."""
import asyncio, json, time, sys, websockets, brotli
from web3 import Web3
OUT = sys.argv[1] if len(sys.argv) > 1 else "fb_record.jsonl"
DURATION = float(sys.argv[2]) if len(sys.argv) > 2 else 4500
async def main():
    t_end = time.time() + DURATION; n = 0
    with open(OUT, "a") as f:
        while time.time() < t_end:
            try:
                async with websockets.connect("wss://mainnet.flashblocks.base.org/ws", open_timeout=15, max_size=2**24) as ws:
                    while time.time() < t_end:
                        m = await asyncio.wait_for(ws.recv(), 15); t = time.time()
                        j = json.loads(brotli.decompress(m))
                        hashes = [Web3.keccak(hexstr=tx).hex() for tx in j["diff"]["transactions"]]
                        rec = {"t": t, "block": j["metadata"]["block_number"], "index": j["index"], "txs": hashes}
                        if j["index"] == 0 and j.get("base"): rec["timestamp"] = int(j["base"]["timestamp"], 16) if isinstance(j["base"]["timestamp"], str) else j["base"]["timestamp"]
                        f.write(json.dumps(rec) + "\n"); f.flush(); n += 1
            except Exception as e:
                print("reconnect:", str(e)[:80], flush=True); await asyncio.sleep(1)
    print("recorded", n, "flashblocks", flush=True)
asyncio.run(main())
