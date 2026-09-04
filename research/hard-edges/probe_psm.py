import requests, json
from web3 import Web3
def rpc(u,m,p):
    return requests.post(u,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=30).json().get("result")
sel=lambda s: Web3.keccak(text=s)[:4].hex()
rpcs={"base":"https://mainnet.base.org","arb":"https://arb1.arbitrum.io/rpc","op":"https://mainnet.optimism.io","unichain":"https://unichain.drpc.org"}
cands=["0x1601843c5E9bC251A3272907010AFa41Fa18347E","0x2B05F8e1cACC6974fD79A673a341Fe1f58d27266","0xe0F9978b907853F354d79188A3dEfbD41978af62","0x7b42Ed932f26509465F7cE3FAF76FfCe1275312f"]
for chain,u in rpcs.items():
    for a in cands:
        code=rpc(u,"eth_getCode",[a,"latest"])
        if code and code!="0x":
            row=[chain,a]
            for fn in ["usdc()","usds()","susds()","rateProvider()","pocket()"]:
                r=rpc(u,"eth_call",[{"to":a,"data":sel(fn)},"latest"])
                row.append(fn+"="+("0x"+r[-40:] if r and len(r)>=42 else str(r)))
            print(" ".join(row))
