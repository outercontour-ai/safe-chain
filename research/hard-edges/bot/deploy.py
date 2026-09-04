"""Deploy TwoPoolArb on Base. Usage: PRIVATE_KEY=0x... python3 deploy.py [rpc]"""
import os, sys, json, time
from web3 import Web3
rpc = sys.argv[1] if len(sys.argv) > 1 else "https://mainnet.base.org"
w3 = Web3(Web3.HTTPProvider(rpc)); art = json.load(open(os.path.join(os.path.dirname(__file__), "TwoPoolArb.json")))
key = os.environ["PRIVATE_KEY"]; acct = w3.eth.account.from_key(key)
print("deployer", acct.address, "balance", w3.from_wei(w3.eth.get_balance(acct.address), "ether"), "ETH")
C = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
tx = C.constructor().build_transaction({"from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address), "chainId": w3.eth.chain_id,
      "maxFeePerGas": w3.eth.gas_price*2, "maxPriorityFeePerGas": w3.to_wei(0.001, "gwei")})
tx["gas"] = int(w3.eth.estimate_gas(tx)*1.2)
signed = acct.sign_transaction(tx); h = w3.eth.send_raw_transaction(signed.raw_transaction)
print("sent", h.hex()); rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=180)
print("deployed at", rcpt.contractAddress, "gas used", rcpt.gasUsed, "status", rcpt.status)
