"""Find where sUSDS/USDS actually trade: aggregate Transfer counterparties over recent blocks, then classify contracts."""
from chain import *
from collections import Counter
import sys
TOK = {"base":{"USDS":"0x820C137fa70C8691f0e44Dc420a5e53c168921Dc","sUSDS":"0x5875eEE11Cf8398102FdAd704C9E96607675467a"},
       "op":{"USDS":"0x4F13a96EC5C4Cf34e442b46Bbd98a0791F20edC3","sUSDS":"0xb5B2dc7fd34C249F4be7fB1fCea07950784229e0"},
       "unichain":{"USDS":"0x7E10036Acc4B56d4dFCa3b77810356CE52313F9C","sUSDS":"0xA06b10Db9F390990364A3984C04FaDf1c13691b5"},
       "arb":{"USDS":"0x6491c05A82219b8D1479057361ff1654749b876b","sUSDS":"0xdDb46999F8891663a8F2828d25298f70416d7610"}}
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
DAYS = float(sys.argv[1]) if len(sys.argv)>1 else 2
def classify(ch, a):
    code = rpc(ch, "eth_getCode", [a, "latest"])
    if not code or code == "0x": return "EOA"
    tags = []
    for sig, tag in (("token0()","v3/v2-pool"),("coins(uint256)","curve"),("tickSpacing()","cl"),("stable()","velo/aero-v2"),("getVault()","balancer-pool"),("readTokens()","pendle-market"),("asset()","erc4626"),("pocket()","psm3"),("MORPHO()","morpho-vault")):
        try:
            r = call(ch, a, sig, (0,) if "uint256" in sig else (), ("uint256",) if "uint256" in sig else ())
            if r and r != "0x": tags.append(tag)
        except Exception: pass
    return ",".join(tags) or "contract"
for ch, toks in TOK.items():
    h = head(ch); span = int(DAYS*86400/CHAINS[ch]["block_time"])
    for tname, t in toks.items():
        try:
            logs = get_logs(ch, t, h-span, h, topics=[TRANSFER], cache_key=f"xfer_{tname}_{DAYS}d")
        except Exception as e:
            print(ch, tname, "ERR", str(e)[:150]); continue
        cnt = Counter(); vol = Counter()
        for l in logs:
            frm = "0x"+l["topics"][1][-40:]; to = "0x"+l["topics"][2][-40:]; v = int(l["data"],16)/1e18
            for a in (frm, to): cnt[a]+=1; vol[a]+=v
        print(f"== {ch} {tname}: {len(logs)} transfers in {DAYS}d ==")
        for a, n in cnt.most_common(12):
            print(f"   {a} n={n} vol={vol[a]:,.0f} {classify(ch,a)}")
        sys.stdout.flush()
