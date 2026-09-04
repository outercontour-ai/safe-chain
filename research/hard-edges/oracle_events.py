"""Pull all logs emitted by SSRAuthOracle on each chain to reconstruct the anchor over time."""
from chain import *
import sys
ORACLE = {"base":"0x65d946e533748A998B1f0E430803e39A6388f7a1","op":"0x6E53585449142A5E6D5fC918AE6BEa341dC81C68","unichain":"0x1566BFA55D95686a823751298533D42651183988","arb":"0xEE2816c1E1eed14d444552654Ed3027abC033A36"}
DAYS = int(sys.argv[1]) if len(sys.argv)>1 else 90
for ch, o in ORACLE.items():
    try:
        h = head(ch); span = int(DAYS*86400/CHAINS[ch]["block_time"])
        logs = get_logs(ch, o, max(1,h-span), h, cache_key=f"ssroracle_{DAYS}d")
        topics = {}
        for l in logs: topics.setdefault(l["topics"][0], []).append(l)
        print(ch, "logs:", len(logs), {t[:10]:len(v) for t,v in topics.items()})
        for l in logs[-3:]:
            print("   blk", int(l["blockNumber"],16), "topic", l["topics"][0][:10], "data", l["data"][:200])
    except Exception as e: print(ch, "ERR", str(e)[:200])
    sys.stdout.flush()
