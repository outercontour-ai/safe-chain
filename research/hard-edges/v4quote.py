"""Effective round-trip fee of hooked V4 pools via the Uniswap V4 Quoter (hook fees included)."""
import json, sys
from chain import *
from eth_abi import encode, decode
QUOTER = "0x0d5e0F971ED27FBfF6c2837bf31316121532048D"   # Uniswap V4 Quoter, Base
SEL = Web3.keccak(text="quoteExactInputSingle(((address,address,uint24,int24,address),bool,uint128,bytes))")[:4].hex()
def quote(key, zeroForOne, amount):
    data = "0x"+SEL+encode(["((address,address,uint24,int24,address),bool,uint128,bytes)"], [(key, zeroForOne, amount, b"")]).hex()
    r = rpc("base", "eth_call", [{"to": QUOTER, "data": data}, "latest"])
    return decode(["uint256","uint256"], bytes.fromhex(r[2:]))[0]
def eff_fee(c):
    key = (c["c0"], c["c1"], c["fee"], c["ts"], c["hooks"])
    d0 = 18 if c["c0"] == "0x"+"0"*40 else call("base", c["c0"], "decimals()", out=("uint8",))[0]
    a = 10**(d0-3)   # 0.001 of token0
    out1 = quote(key, True, a); back = quote(key, False, out1)
    rt = back / a
    return 1 - rt**0.5, out1, back
cands = json.load(open("quirk_candidates_base.json"))
for c in cands:
    try:
        f, o1, b = eff_fee(c)
        c["eff_fee"] = f
        print(f"{c['poolId'][:12]} hook={c['hooks'][:10]} keyfee={c['fee']} ts={c['ts']} eff one-way fee ≈ {f*1e4:.0f}bp")
    except Exception as e:
        c["eff_fee"] = None; print(c["poolId"][:12], "quote failed:", str(e)[:100])
json.dump(cands, open("quirk_candidates_base.json", "w"))
