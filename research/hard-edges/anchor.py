"""Anchor reconstruction for the Sky Savings Rate (sUSDS) from SSRAuthOracle SetSUSDSData events.
rate(t) = chi * ssr^(t - rho)  (RAY = 1e27), exactly as SSROracleBase.getConversionRate()."""
from chain import *
import bisect
ORACLE = {"base":"0x65d946e533748A998B1f0E430803e39A6388f7a1","op":"0x6E53585449142A5E6D5fC918AE6BEa341dC81C68","unichain":"0x1566BFA55D95686a823751298533D42651183988","arb":"0xEE2816c1E1eed14d444552654Ed3027abC033A36"}
RAY = 10**27
def rpow(x, n, base=RAY):
    # DSMath rpow (integer, round-half-up like MakerDAO)
    z = base if n % 2 == 0 else x
    half = base // 2
    while n > 1:
        n //= 2
        x = (x*x + half) // base
        if n % 2: z = (z*x + half) // base
    return z
class SSRAnchor:
    def __init__(self, chain, days=120):
        h = head(chain); span = int(days*86400/CHAINS[chain]["block_time"])
        logs = get_logs(chain, ORACLE[chain], max(1,h-span), h, cache_key=f"ssroracle_{days}d")
        self.updates = []  # (blockNumber, ssr, chi, rho)
        for l in logs:
            d = l["data"][2:]
            ssr, chi, rho = int(d[0:64],16), int(d[64:128],16), int(d[128:192],16)
            self.updates.append((int(l["blockNumber"],16), l["logIndex"] if isinstance(l["logIndex"],int) else int(l["logIndex"],16), ssr, chi, rho))
        self.updates.sort()
        self.blocks = [u[0] for u in self.updates]
        if not self.updates: raise RuntimeError("no oracle updates found; extend days")
    def data_at_block(self, block):
        i = bisect.bisect_right(self.blocks, block) - 1
        if i < 0: return None
        return self.updates[i]
    def rate(self, block, ts):
        """conversion rate (RAY) at block/timestamp, using the oracle data active at that block"""
        u = self.data_at_block(block)
        if u is None: return None
        _, _, ssr, chi, rho = u
        if ts <= rho: return chi
        return (rpow(ssr, ts - rho) * chi) // RAY
if __name__ == "__main__":
    import sys, time
    ch = sys.argv[1] if len(sys.argv)>1 else "base"
    a = SSRAnchor(ch)
    print(ch, "updates:", len(a.updates))
    for u in a.updates[-4:]: print("  blk",u[0],"ssr",u[2]/RAY,"chi",u[3]/RAY,"rho",u[4])
    h = head(ch); ts = block_ts(ch, h)
    mine = a.rate(h, ts); onchain = call(ch, ORACLE[ch], "getConversionRate()", out=("uint256",), block=h)[0]
    print("check at head", h, "reconstructed", mine, "onchain", onchain, "diff", mine-onchain)
    # historical checks
    for back in (1000, 200000, 1000000):
        b = h-back; ts = block_ts(ch, b)
        mine = a.rate(b, ts); onchain = call(ch, ORACLE[ch], "getConversionRate()", out=("uint256",), block=b)[0]
        print("check at", b, "reconstructed", mine, "onchain", onchain, "diff", mine-onchain)
