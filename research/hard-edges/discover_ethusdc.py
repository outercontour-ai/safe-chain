"""WETH/USDC pools on Base / Arbitrum / OP across DEXes (for cross-DEX closure-speed measurement)."""
from chain import *
C={"base":dict(WETH="0x4200000000000000000000000000000000000006",USDC="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
     v3={"UniV3":("0x33128a8fC17869897dcE68Ed026d694621f6FDfD",[100,500,3000]),"PancakeV3":("0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",[100,500,2500]),"SushiV3":("0xc35DADB65012eC5796536bD9864eD8773aBc74C4",[100,500,3000])},
     cl={"AeroCL":("0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A",[1,10,50,100,200])}),
   "arb":dict(WETH="0x82aF49447D8a07e3bd95BD0d56f35241523fBaFf",USDC="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
     v3={"UniV3":("0x1F98431c8aD98523631AE4a59f267346ea31F984",[100,500,3000]),"PancakeV3":("0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",[100,500,2500]),"SushiV3":("0x1af415a1EbA07a4986a52B6f2e7dE7003D82231e",[100,500,3000])}, cl={}),
   "op":dict(WETH="0x4200000000000000000000000000000000000006",USDC="0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
     v3={"UniV3":("0x1F98431c8aD98523631AE4a59f267346ea31F984",[100,500,3000])},
     cl={"VeloCL":("0x548118C7E0B865C2CfA94D15EC86B666468ac758",[1,10,50,100,200])})}
for ch,c in C.items():
    def bal(t,w,d): r=call(ch,t,"balanceOf(address)",(w,),("address",),out=("uint256",)); return round(r[0]/10**d,1) if r else None
    for dex,(fac,fees) in c["v3"].items():
        for f in fees:
            p=call(ch,fac,"getPool(address,address,uint24)",(c["WETH"],c["USDC"],f),("address","address","uint24"),out=("address",))
            if p and int(p[0],16):
                w=bal(c["WETH"],p[0],18); u=bal(c["USDC"],p[0],6)
                if (u or 0)>50000: print(ch,dex,"fee",f,p[0],"WETH",w,"USDC",u,"token0",call(ch,p[0],"token0()",out=("address",))[0][:10])
    for dex,(fac,tss) in c["cl"].items():
        for t in tss:
            p=call(ch,fac,"getPool(address,address,int24)",(c["WETH"],c["USDC"],t),("address","address","int24"),out=("address",))
            if p and int(p[0],16):
                w=bal(c["WETH"],p[0],18); u=bal(c["USDC"],p[0],6)
                if (u or 0)>50000: print(ch,dex,"ts",t,p[0],"fee",call(ch,p[0],"fee()",out=("uint24",))[0],"WETH",w,"USDC",u,"token0",call(ch,p[0],"token0()",out=("address",))[0][:10])
print("done")
