from chain import *
import itertools
T={"USDC":"0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48","USDS":"0xdC035D45d973E3EC169d2276DDab16f1e407384F","sUSDS":"0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD","DAI":"0x6B175474E89094C44Da98b954EedeAC495271d0F","sDAI":"0x83F20F44975D03b1b09e64809B757c47f942BEeA","USDT":"0xdAC17F958D2ee523a2206206994597C13D831ec7"}
DEC={"USDC":6,"USDT":6,"USDS":18,"sUSDS":18,"DAI":18,"sDAI":18}
FAC="0x1F98431c8aD98523631AE4a59f267346ea31F984"
def bal(t,w,d):
    r=call("eth",t,"balanceOf(address)",(w,),("address",),out=("uint256",)); return round(r[0]/10**d) if r else None
for (n1,t1),(n2,t2) in itertools.combinations(T.items(),2):
    if not ({n1,n2} & {"USDS","sUSDS","sDAI"}): continue
    for f in (100,500,3000,10000):
        p=call("eth",FAC,"getPool(address,address,uint24)",(t1,t2,f),("address","address","uint24"),out=("address",))
        if p and int(p[0],16):
            b={n1:bal(t1,p[0],DEC[n1]),n2:bal(t2,p[0],DEC[n2])}
            if (b[n1] or 0)+(b[n2] or 0) > 1000: print("eth UniV3",n1,n2,f,p[0],b)
print("done")
