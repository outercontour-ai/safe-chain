"""PoolSim exact_in/exact_out vs Uniswap QuoterV2; bot sizing vs TwoPoolArb execution (eth_call state override)."""
import json, requests, sys
sys.argv=["x"]; import bot
from web3 import Web3
from eth_abi import encode, decode
from bot import PoolSim, best_cycle, POOLS, rpc
blk=int(rpc("eth_blockNumber",[]),16)
pools={n:PoolSim(n,a) for n,a in POOLS.items()}
for p in pools.values(): p.init_state(blk)
QUOTER="0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a"; WETH="0x4200000000000000000000000000000000000006"; USDC="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
sel_in=Web3.keccak(text="quoteExactInputSingle((address,address,uint256,uint24,uint160))")[:4].hex()
sel_out=Web3.keccak(text="quoteExactOutputSingle((address,address,uint256,uint24,uint160))")[:4].hex()
uni=pools["uni"]
for amt in (10**16, 10**18, 10**19):
    ain,aout,_=uni.exact_in(True, amt)
    r=rpc("eth_call",[{"to":QUOTER,"data":"0x"+sel_in+encode(["(address,address,uint256,uint24,uint160)"],[(WETH,USDC,amt,500,0)]).hex()},hex(blk)])
    q=decode(["uint256","uint160","uint32","uint256"],bytes.fromhex(r[2:]))[0]
    print(f"exact_in  {amt/1e18:g} WETH: sim out {aout:.0f} quoter {q} rel.err {abs(aout-q)/q:.2e}")
for amt in (10**16, 10**18):
    bin_,bout,_=uni.exact_out(False, amt)
    r=rpc("eth_call",[{"to":QUOTER,"data":"0x"+sel_out+encode(["(address,address,uint256,uint24,uint160)"],[(USDC,WETH,amt,500,0)]).hex()},hex(blk)])
    q=decode(["uint256","uint160","uint32","uint256"],bytes.fromhex(r[2:]))[0]
    print(f"exact_out {amt/1e18:g} WETH: sim in {bin_:.0f} quoter {q} rel.err {abs(bin_-q)/q:.2e}")
art=json.load(open("TwoPoolArb.json")); FAKE="0x00000000000000000000000000000000000A4b17"; OWNER="0x000000000000000000000000000000000000dEaD"
slot=Web3.keccak(encode(["address","uint256"],[FAKE,3])).hex()
override={FAKE:{"code":art["deployedBytecode"],"stateDiff":{"0x"+"0"*64:"0x"+OWNER[2:].lower().rjust(64,"0")}}, WETH:{"stateDiff":{"0x"+slot:"0x"+hex(10**18)[2:].rjust(64,"0")}}}
eth=uni.sqrtP**2*1e12; b=best_cycle(pools, eth)
print("best cycle now:", None if not b else {k:(round(v,6) if isinstance(v,float) else v) for k,v in b.items() if k in ("sell","buy","z","usd")})
for (an,bn,z,x) in (("aero","uni",False,30*10**6),("uni","pcs",True,10**16),("pcs","aero",False,50*10**6)):
    A,B=pools[an],pools[bn]
    ain,aout,sA=A.exact_in(z,x); bin_,bout,sB=B.exact_out(not z,x); pred=aout-bin_
    params=(Web3.to_checksum_address(A.addr),Web3.to_checksum_address(B.addr),z,x,0,0,0,-10**18)
    data="0x"+bot.SEL_EXEC+encode([bot.PARAMS_T],[params]).hex()
    r=requests.post("https://mainnet.base.org",json={"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"from":OWNER,"to":FAKE,"data":data,"gas":hex(2_000_000)},hex(blk),override]},timeout=60).json()
    real=decode(["int256"],bytes.fromhex(r["result"][2:]))[0] if "result" in r else str(r.get("error"))[:100]
    unit = "USDC" if z else "WETH"
    print(f"{an}->{bn} z={z} x={x}: simulator profit {pred:.0f} raw {unit}, contract {real} raw {unit}" + (f", rel.diff {abs(pred-real)/max(1,abs(real)):.2e}" if isinstance(real,int) else ""))
