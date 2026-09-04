import json, sys
from engine import run
from anchor import SSRAnchor, RAY
PSM="0x1601843c5E9bC251A3272907010AFa41Fa18347E"
out=[]
one=lambda b,t: 1.0
# USDS(token0,18)/USDC(token1,6) pools vs PSM3 1:1
for label,pool in [("Base PancakeV3 USDS/USDC 0.01%","0x81057171115672ac7d08bbebb04481e19aa0bfeb"),
                   ("Base AeroCL USDS/USDC ts1","0xa441378a1cb4df371535296e539a1e0def6924e4"),
                   ("Base UniV3 USDS/USDC 0.05%","0x3b42964f167702bd2ce18e7703fe3bd328aff93c")]:
    r=run("base",pool,60,one,18,6,token1_usd=1.0,anchor_contract=PSM,gas_usd=0.03,label=label); out.append(r); sys.stdout.flush()
# sUSDS(token0)/USDC(token1) UniV3 1% vs SSR rate
a=SSRAnchor("base",days=120)
r=run("base","0x4c9f68e780523feb4c9bb1aad2e5cc3b6476892b",60,lambda b,t: a.rate(b,t)/RAY,18,6,token1_usd=1.0,anchor_contract=PSM,gas_usd=0.03,label="Base UniV3 sUSDS/USDC 1%"); out.append(r)
json.dump(out,open("res_base_sky.json","w"))
