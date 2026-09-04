"""Discover V3-style pools (getPool) for hard-edge token pairs on Base/OP/Unichain/Arbitrum."""
import requests, itertools, sys
from web3 import Web3
from eth_abi import encode
def rpc(u,m,p):
    r=requests.post(u,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=30).json()
    return r.get("result")
def call(u,to,sig,args=(),types=()):
    data=Web3.keccak(text=sig)[:4].hex()+ (encode(list(types),list(args)).hex() if types else "")
    return rpc(u,"eth_call",[{"to":to,"data":data},"latest"])
def addr(r): return "0x"+r[-40:] if r and len(r)>=42 else None
CH={
 "base":dict(rpc="https://mainnet.base.org",
   tokens={"USDC":"0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913","USDS":"0x820C137fa70C8691f0e44Dc420a5e53c168921Dc","sUSDS":"0x5875eEE11Cf8398102FdAd704C9E96607675467a","USDbC":"0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA"},
   v3={"UniV3":("0x33128a8fC17869897dcE68Ed026d694621f6FDfD",[100,500,3000,10000]),
       "PancakeV3":("0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",[100,500,2500,10000]),
       "SushiV3":("0xc35DADB65012eC5796536bD9864eD8773aBc74C4",[100,500,3000,10000])},
   cl={"AeroCL":("0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A",[1,10,50,100,200,2000])},
   v2={"AeroV2":("0x420DD381b31aEf6683db6B902084cB0FFECe40Da",[True,False])}),
 "op":dict(rpc="https://mainnet.optimism.io",
   tokens={"USDC":"0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85","USDS":"0x4F13a96EC5C4Cf34e442b46Bbd98a0791F20edC3","sUSDS":"0xb5B2dc7fd34C249F4be7fB1fCea07950784229e0"},
   v3={"UniV3":("0x1F98431c8aD98523631AE4a59f267346ea31F984",[100,500,3000,10000])},
   cl={"VeloCL":("0x548118C7E0B865C2CfA94D15EC86B666468ac758",[1,10,50,100,200,2000])},
   v2={"VeloV2":("0xF1046053aa5682b4F9a81b5481394DA16BE5FF5a",[True,False])}),
 "unichain":dict(rpc="https://unichain.drpc.org",
   tokens={"USDC":"0x078D782b760474a361dDA0AF3839290b0EF57AD6","USDS":"0x7E10036Acc4B56d4dFCa3b77810356CE52313F9C","sUSDS":"0xA06b10Db9F390990364A3984C04FaDf1c13691b5"},
   v3={"UniV3":("0x1F98400000000000000000000000000000000003",[100,500,3000,10000])},
   cl={}, v2={}),
 "arb":dict(rpc="https://arb1.arbitrum.io/rpc",
   tokens={"USDC":"0xaf88d065e77c8cC2239327C5EDb3A432268e5831","USDS":"0x6491c05A82219b8D1479057361ff1654749b876b","sUSDS":"0xdDb46999F8891663a8F2828d25298f70416d7610"},
   v3={"UniV3":("0x1F98431c8aD98523631AE4a59f267346ea31F984",[100,500,3000,10000]),
       "PancakeV3":("0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",[100,500,2500,10000]),
       "SushiV3":("0x1af415a1EbA07a4986a52B6f2e7dE7003D82231e",[100,500,3000,10000])},
   cl={}, v2={}),
}
ZERO="0x"+"0"*40
for chain,c in CH.items():
    u=c["rpc"]; toks=c["tokens"]
    for (n1,t1),(n2,t2) in itertools.combinations(toks.items(),2):
        for dex,(fac,fees) in c["v3"].items():
            for f in fees:
                p=addr(call(u,fac,"getPool(address,address,uint24)",(t1,t2,f),("address","address","uint24")))
                if p and p!=ZERO: print(chain,dex,n1,n2,"fee",f,p)
        for dex,(fac,tss) in c["cl"].items():
            for ts in tss:
                p=addr(call(u,fac,"getPool(address,address,int24)",(t1,t2,ts),("address","address","int24")))
                if p and p!=ZERO: print(chain,dex,n1,n2,"ts",ts,p)
        for dex,(fac,stables) in c["v2"].items():
            for st in stables:
                p=addr(call(u,fac,"getPool(address,address,bool)",(t1,t2,st),("address","address","bool")))
                if p and p!=ZERO: print(chain,dex,n1,n2,"stable",st,p)
        sys.stdout.flush()
