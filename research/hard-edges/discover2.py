"""Pool discovery on Arbitrum/Unichain for USDC/USDS/sUSDS with failover RPC + Camelot (Algebra) factory."""
from chain import *
import itertools, sys
T = {"unichain":{"USDC":"0x078D782b760474a361dDA0AF3839290b0EF57AD6","USDS":"0x7E10036Acc4B56d4dFCa3b77810356CE52313F9C","sUSDS":"0xA06b10Db9F390990364A3984C04FaDf1c13691b5","USDT0":"0x9151434b16b9763660705744891fA906F660EcC5","WETH":"0x4200000000000000000000000000000000000006"},
     "arb":{"USDC":"0xaf88d065e77c8cC2239327C5EDb3A432268e5831","USDS":"0x6491c05A82219b8D1479057361ff1654749b876b","sUSDS":"0xdDb46999F8891663a8F2828d25298f70416d7610","USDT":"0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9","USDCe":"0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8","WETH":"0x82aF49447D8a07e3bd95BD0d56f35241523fBaFf"}}
V3 = {"unichain":{"UniV3":("0x1F98400000000000000000000000000000000003",[100,500,3000,10000])},
      "arb":{"UniV3":("0x1F98431c8aD98523631AE4a59f267346ea31F984",[100,500,3000,10000]),"PancakeV3":("0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",[100,500,2500,10000]),"SushiV3":("0x1af415a1EbA07a4986a52B6f2e7dE7003D82231e",[100,500,3000,10000])}}
ALG = {"arb":{"CamelotV3":"0x1a3c9B1d2F0529D97f2afC5136Cc23e58f1FD35B"}}
def bal(ch, tok, who, dec):
    r = call(ch, tok, "balanceOf(address)", (who,), ("address",), out=("uint256",)); return r[0]/10**dec if r else None
DEC={"USDC":6,"USDT":6,"USDCe":6,"USDT0":6,"USDS":18,"sUSDS":18,"WETH":18}
for ch in T:
    toks=T[ch]
    for (n1,t1),(n2,t2) in itertools.combinations(toks.items(),2):
        if n1 not in ("USDS","sUSDS") and n2 not in ("USDS","sUSDS"): continue
        found=[]
        for dex,(fac,fees) in V3.get(ch,{}).items():
            for f in fees:
                p=call(ch,fac,"getPool(address,address,uint24)",(t1,t2,f),("address","address","uint24"),out=("address",))
                if p and int(p[0],16): found.append((dex,f,p[0]))
        for dex,fac in ALG.get(ch,{}).items():
            p=call(ch,fac,"poolByPair(address,address)",(t1,t2),("address","address"),out=("address",))
            if p and int(p[0],16): found.append((dex,"algebra",p[0]))
        for dex,f,p in found:
            print(ch,dex,n1,n2,f,p,"bal:",{n1:bal(ch,t1,p,DEC[n1]),n2:bal(ch,t2,p,DEC[n2])}); sys.stdout.flush()
print("done")
