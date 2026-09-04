import json
from engine_v3 import run
PSM="0xf6e72Db5454dd049d0788e411b06CfAF16853042"
# DAI(token0,18)/USDC(token1,6) 0.01% vs LitePSM 1:1 (tin=tout=0). Mainnet gas ~ $1 per arb bundle at 1 gwei.
r=run("eth","0x5777d92f208679DB4b9778590Fa3CAB3aC9e2168",45,lambda b,t:1.0,18,6,anchor_contract=PSM,gas_usd=1.0,min_profit_usd=0.5,label="ETH mainnet UniV3 DAI/USDC 0.01% vs LitePSM",words=2)
json.dump([r],open("res_eth_psm.json","w"))
