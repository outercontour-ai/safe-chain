"""superOETHb discount: exact sizing of buy-superOETHb-and-redeem (10-min queue) at thresholds of net profit."""
import json
from engine_v3 import run
VAULT="0x98a0cbef61bd2d21435f433be4cd42b56b38cc93"
out=[]
for thr in (1.0, 20.0, 100.0):
    r=run("base","0x6446021f4e396da3df4235c62537431372195d38",90,lambda b,t:1.0,18,18,token1_usd=3500.0,allow=("1to0",),anchor_contract=VAULT,gas_usd=0.05,min_profit_usd=thr,label=f"Base superOETHb discount (exact sim), window when profit>${thr}",words=2,validate=(thr==1.0))
    out.append(r)
json.dump(out,open("res_base_soeth_exact.json","w"))
