"""Weekly gauge emissions (AERO / VELO) for CL pools via Voter.gauges(pool) -> gauge NotifyReward events, priced via a DEX pool."""
import sys, json
from chain import *
from eth_abi import decode
T_NOTIFY = "0x" + Web3.keccak(text="NotifyReward(address,uint256)").hex()
CFG = {"base": dict(voter="0x16613524e02ad97eDfeF371bC883F2F5d6C480A5", token="0x940181a94A35A4569E4529A3CDfB74e38FD98631", usdc="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", v2f="0x420DD381b31aEf6683db6B902084cB0FFECe40Da",
                    pools={"AeroCL WETH/USDC ts100":"0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59"}),
       "op":   dict(voter="0x41C914ee0c7E1A5edCD0295623e6dC557B5aBf3C", token="0x9560e827aF36c94D2Ac33a39bCE1Fe78631088Db", usdc="0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", v2f="0xF1046053aa5682b4F9a81b5481394DA16BE5FF5a",
                    pools={"VeloCL WETH/USDC ts100":"0x478946bcd4a5a22b316470f5486fafb928c0ba25"})}
for ch, c in CFG.items():
    # token price via v2 volatile pool token/USDC reserves
    p = call(ch, c["v2f"], "getPool(address,address,bool)", (c["token"], c["usdc"], False), ("address","address","bool"), out=("address",))
    price = None
    if p and int(p[0],16):
        r = call(ch, p[0], "getReserves()", out=("uint256","uint256","uint256")); t0 = call(ch, p[0], "token0()", out=("address",))[0].lower()
        tok_res, usd_res = (r[0]/1e18, r[1]/1e6) if t0 == c["token"].lower() else (r[1]/1e18, r[0]/1e6)
        price = usd_res/tok_res
    print(f"== {ch}: emission token price ≈ ${price:.4f}" if price else f"== {ch}: price n/a")
    h = head(ch); fb = h - int(35*86400/CHAINS[ch]["block_time"])
    for name, pool in c["pools"].items():
        g = call(ch, c["voter"], "gauges(address)", (pool,), ("address",), out=("address",))
        if not g or not int(g[0],16): print(name, "no gauge"); continue
        logs = get_logs(ch, g[0], fb, h, topics=[T_NOTIFY], cache_key=f"gauge_{g[0].lower()}")
        weekly = [(int(l["blockNumber"],16), decode(["uint256"], bytes.fromhex(l["data"][2:]))[0]/1e18) for l in logs]
        tot = sum(a for _, a in weekly)
        print(f"{name}: gauge {g[0]} | {len(weekly)} NotifyReward in 35d | total {tot:,.0f} tokens = ${tot*price:,.0f} -> ${tot*price/35:,.0f}/day")
        for b, a in weekly[-6:]: print(f"   block {b}: {a:,.0f} tokens (${a*price:,.0f})")
        sys.stdout.flush()
