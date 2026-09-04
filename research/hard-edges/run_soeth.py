import json, sys
from engine import run
VAULT="0x98a0cbef61bd2d21435f433be4cd42b56b38cc93"
# WETH(token0)/superOETHb(token1). Mint WETH->superOETHb 1:1 is atomic => anchor 0to1 only (captures superOETHb premium).
r=run("base","0x6446021f4e396da3df4235c62537431372195d38",90,lambda b,t:1.0,18,18,token1_usd=3500.0,allow=("0to1",),anchor_contract=VAULT,gas_usd=0.05,label="Base AeroCL WETH/superOETHb ts1 (mint side)")
json.dump([r],open("res_base_soeth.json","w"))
# also both sides, to see how often a discount (redeem side, 10-min queue) appears
r2=run("base","0x6446021f4e396da3df4235c62537431372195d38",90,lambda b,t:1.0,18,18,token1_usd=3500.0,allow=("0to1","1to0"),anchor_contract=VAULT,gas_usd=0.05,label="Base AeroCL WETH/superOETHb ts1 (both sides, redeem non-atomic)")
json.dump([r,r2],open("res_base_soeth.json","w"))
