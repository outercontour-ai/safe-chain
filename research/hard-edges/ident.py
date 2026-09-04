from chain import *
def name(ch,a):
    try:
        r=call(ch,a,"symbol()"); 
        if r and len(r)>=130: return decode(["string"],bytes.fromhex(r[2:]))[0]
        if r and len(r)==66: return bytes.fromhex(r[2:]).rstrip(b"\0").decode(errors="replace")
    except Exception as e: return "?"
    return "?"
for a in []:
    t0=call("base",a,"token0()",out=("address",)); t1=call("base",a,"token1()",out=("address",))
    ts=call("base",a,"tickSpacing()",out=("int24",)); fee=call("base",a,"fee()",out=("uint24",))
    print(a, "symbol",name("base",a), "token0",t0 and (t0[0],name("base",t0[0])), "token1",t1 and (t1[0],name("base",t1[0])), "ts",ts, "fee",fee)
# USD+ (Overnight) on Base: exchange contract and fees
USDP="0xB79DD08EA68A908A97220C76d19A6aA9cBDE4A74"
ex=call("base",USDP,"exchange()",out=("address",)); print("USD+ exchange()",ex)
if ex:
    for fn in ("buyFee()","buyFeeDenominator()","redeemFee()","redeemFeeDenominator()","paused()"):
        try: print("  ",fn,call("base",ex[0],fn,out=("uint256",)))
        except Exception as e: print("  ",fn,"ERR",str(e)[:60])
# superOETHb on Base
SO="0xDBFeFD2e8460a6Ee4955A68582F85708BAEA60A3"; WETH="0x4200000000000000000000000000000000000006"; AEROCL="0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"
for ts in (1,10,50,100,200):
    p=call("base",AEROCL,"getPool(address,address,int24)",(WETH,SO,ts),("address","address","int24"),out=("address",))
    if p and int(p[0],16): print("AeroCL WETH/superOETHb ts",ts,p[0], "fee",call("base",p[0],"fee()",out=("uint24",)))
v=call("base",SO,"vaultAddress()",out=("address",)); print("superOETHb vault", v)
# Pools for USD+/USDC on Aerodrome (v2 stable and CL)
USDC="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"; AEROV2="0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
for st in (True,False):
    p=call("base",AEROV2,"getPool(address,address,bool)",(USDC,USDP,st),("address","address","bool"),out=("address",))
    if p and int(p[0],16): print("AeroV2 USDC/USD+ stable",st,p[0])
for ts in (1,10,50,100):
    p=call("base",AEROCL,"getPool(address,address,int24)",(USDC,USDP,ts),("address","address","int24"),out=("address",))
    if p and int(p[0],16): print("AeroCL USDC/USD+ ts",ts,p[0],"fee",call("base",p[0],"fee()",out=("uint24",)))
