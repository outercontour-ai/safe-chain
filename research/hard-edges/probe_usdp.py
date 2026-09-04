from chain import *
CFG={"base":dict(usdp="0xB79DD08EA68A908A97220C76d19A6aA9cBDE4376",ex="0x7cb1B38591021309C64f451859d79312d8Ca2789",usdc="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",usdbc="0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
                 v2f="0x420DD381b31aEf6683db6B902084cB0FFECe40Da",clf="0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"),
     "op":dict(usdp="0x73cb180bf0521828d8849bc8CF2B920918e23032",ex="0xe80772Eaf6e2E18B651F160Bc9158b2A5caFCA65",usdc="0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",usdce="0x7F5c764cBc14f9669B88837ca1490cCa17c31607",
               v2f="0xF1046053aa5682b4F9a81b5481394DA16BE5FF5a",clf="0x548118C7E0B865C2CfA94D15EC86B666468ac758")}
for ch,c in CFG.items():
    print("==",ch)
    for fn in ("buyFee()","buyFeeDenominator()","redeemFee()","redeemFeeDenominator()","paused()","usdc()","usdPlus()","totalSupply()"):
        try:
            out=("bool",) if fn=="paused()" else ("address",) if fn in("usdc()","usdPlus()") else ("uint256",)
            r=call(ch,c["ex"],fn,out=out); print("  exchange",fn,r)
        except Exception as e: print("  exchange",fn,"ERR",str(e)[:60])
    print("  USD+ totalSupply", call(ch,c["usdp"],"totalSupply()",out=("uint256",))[0]/1e6, "decimals",call(ch,c["usdp"],"decimals()",out=("uint8",)))
    def bal(t,w,d=6):
        r=call(ch,t,"balanceOf(address)",(w,),("address",),out=("uint256",)); return round(r[0]/10**d,0) if r else None
    quotes=[(k,v) for k,v in c.items() if k in ("usdc","usdbc","usdce")]
    for qn,q in quotes:
        for st in (True,False):
            p=call(ch,c["v2f"],"getPool(address,address,bool)",(q,c["usdp"],st),("address","address","bool"),out=("address",))
            if p and int(p[0],16): print("  V2",qn,"/USD+ stable",st,p[0],"bal",{qn:bal(q,p[0]),"USD+":bal(c["usdp"],p[0])})
        for ts in (1,10,50,100,200):
            p=call(ch,c["clf"],"getPool(address,address,int24)",(q,c["usdp"],ts),("address","address","int24"),out=("address",))
            if p and int(p[0],16): print("  CL",qn,"/USD+ ts",ts,p[0],"fee",call(ch,p[0],"fee()",out=("uint24",)),"bal",{qn:bal(q,p[0]),"USD+":bal(c["usdp"],p[0])})
