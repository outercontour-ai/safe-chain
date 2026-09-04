from chain import *
pools = {
 "base": [("UniV3 USDC/USDS 0.01%","0x73f754af377cb7b377ff25aa659f023de46f79d3"),("UniV3 USDC/USDS 0.05%","0x3b42964f167702bd2ce18e7703fe3bd328aff93c"),
          ("PancakeV3 USDC/USDS 0.01%","0x81057171115672ac7d08bbebb04481e19aa0bfeb"),("AeroCL USDC/USDS ts1","0xa441378a1cb4df371535296e539a1e0def6924e4"),
          ("UniV3 USDC/sUSDS 0.3%","0x7dd2f626865e71b099f80bab3ca25a7918c5e0dd"),("UniV3 USDC/sUSDS 1%","0x4c9f68e780523feb4c9bb1aad2e5cc3b6476892b"),
          ("AeroV2 USDC/sUSDS vol","0x65218026a90e823e0645252e7c2d6725e3716502")],
 "op":   [("UniV3 USDC/sUSDS 1%","0xee9be05d7396d80ec0900c07726ad6ccaf977e47")],
}
TOK = {"base":{"USDC":"0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913","USDS":"0x820C137fa70C8691f0e44Dc420a5e53c168921Dc","sUSDS":"0x5875eEE11Cf8398102FdAd704C9E96607675467a"},
       "op":{"USDC":"0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85","USDS":"0x4F13a96EC5C4Cf34e442b46Bbd98a0791F20edC3","sUSDS":"0xb5B2dc7fd34C249F4be7fB1fCea07950784229e0"},
       "unichain":{"USDC":"0x078D782b760474a361dDA0AF3839290b0EF57AD6","USDS":"0x7E10036Acc4B56d4dFCa3b77810356CE52313F9C","sUSDS":"0xA06b10Db9F390990364A3984C04FaDf1c13691b5"},
       "arb":{"USDC":"0xaf88d065e77c8cC2239327C5EDb3A432268e5831","USDS":"0x6491c05A82219b8D1479057361ff1654749b876b","sUSDS":"0xdDb46999F8891663a8F2828d25298f70416d7610"}}
DEC = {"USDC":6,"USDS":18,"sUSDS":18}
PSM = {"base":"0x1601843c5E9bC251A3272907010AFa41Fa18347E","op":"0xe0F9978b907853F354d79188A3dEfbD41978af62","unichain":"0x7b42Ed932f26509465F7cE3FAF76FfCe1275312f","arb":"0x2B05F8e1cACC6974fD79A673a341Fe1f58d27266"}
ORACLE = {"base":"0x65d946e533748A998B1f0E430803e39A6388f7a1","op":"0x6E53585449142A5E6D5fC918AE6BEa341dC81C68","unichain":"0x1566BFA55D95686a823751298533D42651183988","arb":"0xEE2816c1E1eed14d444552654Ed3027abC033A36"}
def bal(chain, tok, who):
    r = call(chain, TOK[chain][tok], "balanceOf(address)", (who,), ("address",), out=("uint256",))
    return r[0]/10**DEC[tok] if r else None
print("== PSM3 reserves (capacity of the hard edge) ==")
for ch in PSM:
    try:
        pocket = call(ch, PSM[ch], "pocket()", out=("address",))[0]
        row = {t: bal(ch, t, pocket if t=="USDC" else PSM[ch]) for t in ("USDC","USDS","sUSDS")}
        rate = call(ch, ORACLE[ch], "getConversionRate()", out=("uint256",))[0]/1e27
        row["sUSDS_rate"]=round(rate,6)
        print(ch, {k:(round(v,0) if isinstance(v,float) and k!="sUSDS_rate" else v) for k,v in row.items()})
    except Exception as e: print(ch, "ERR", str(e)[:120])
print("== pool balances ==")
for ch, lst in pools.items():
    for name, p in lst:
        try:
            t0 = call(ch, p, "token0()", out=("address",))[0]
            fee = call(ch, p, "fee()", out=("uint24",))
            names = {v.lower():k for k,v in TOK[ch].items()}
            b = {t: bal(ch, t, p) for t in ("USDC","USDS","sUSDS")}
            print(ch, name, p, "token0=",names.get(t0.lower(),t0), "fee=",fee[0] if fee else None, {k:round(v,2) for k,v in b.items() if v})
        except Exception as e: print(ch, name, "ERR", str(e)[:100])
