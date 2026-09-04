"""Fees vs LVR vs emissions for CL pools, from cached swap logs.
LVR increment for liquidity L when sqrt price moves s0->s1 (arb marks the LP's forced trade at the new price):
 L*(s1-s0)^2/s0 in token1 raw units. Fees: fee * |amount1| per swap. Both use the pool's in-range L from the event."""
import json, glob, sys
from collections import defaultdict
from chain import *
from engine import decode_swap, Q96
ETH = 2450.0
POOLS = {"base AeroCL WETH/USDC ts100": ("base","0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59",18,6,True),
         "base UniV3 WETH/USDC 0.05%":  ("base","0xd0b53d9277642d899df5c87a3966a349a798f224",18,6,True),
         "base PancakeV3 WETH/USDC 0.01%":("base","0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38",18,6,True),
         "op VeloCL WETH/USDC ts100":   ("op","0x478946bcd4a5a22b316470f5486fafb928c0ba25",6,18,False),
         "arb UniV3 WETH/USDC 0.05%":   ("arb","0xc6962004f452be9203591991d15f6b388e09e8d0",18,6,True)}
for name,(ch,pool,d0,d1,weth_is_0) in POOLS.items():
    ev=[]
    files = glob.glob(f"cache/{ch}_swaponly_{pool}*/*.json") or glob.glob(f"cache/{ch}_swaps_{pool}/*.json")
    for f in files: ev += [e for e in map(decode_swap, json.load(open(f))) if e]
    ev.sort(key=lambda e:(e["block"],e["idx"]))
    if not ev: print(name,"no data"); continue
    fee=call(ch,pool,"fee()",out=("uint24",))[0]/1e6
    days=(ev[-1]["block"]-ev[0]["block"])*CHAINS[ch]["block_time"]/86400
    usd1 = 1.0 if d1==6 else ETH   # token1 USD (USDC or WETH)
    fees=0.0; vol=0.0
    for e in ev:
        v=abs(e["a1"])/10**d1*usd1; vol+=v; fees+=v*fee
    # LVR on block-level price path (last swap of each block), with in-range L from the event
    last={}
    for e in ev: last[e["block"]]=e
    blocks=sorted(last); lvr=0.0
    for i in range(1,len(blocks)):
        p0=last[blocks[i-1]]; p1=last[blocks[i]]
        s0=p0["sqrtP"]/Q96; s1=p1["sqrtP"]/Q96; L=p0["L"]
        lvr += L*(s1-s0)**2/s0/10**d1*usd1
    # TVL from balances
    t0=call(ch,pool,"token0()",out=("address",))[0]; t1=call(ch,pool,"token1()",out=("address",))[0]
    b0=call(ch,t0,"balanceOf(address)",(pool,),("address",),out=("uint256",))[0]/10**d0; b1=call(ch,t1,"balanceOf(address)",(pool,),("address",),out=("uint256",))[0]/10**d1
    tvl = b0*(ETH if d0==18 else 1) + b1*(ETH if d1==18 else 1)
    print(f"{name}: {days:.1f}d volume=${vol/days:,.0f}/day fees=${fees/days:,.0f}/day LVR=${lvr/days:,.0f}/day fees/LVR={fees/lvr:.2f} TVL=${tvl:,.0f} | fee APR={fees/days*365/tvl*100:.0f}% LVR APR={lvr/days*365/tvl*100:.0f}% net(fees-LVR)={(fees-lvr)/days*365/tvl*100:.0f}%")
    sys.stdout.flush()
