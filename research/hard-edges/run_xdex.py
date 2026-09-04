"""Cross-DEX closure speed: pool X vs pool Y (same pair, same chain). Windows = |gap| beyond fee_X+fee_Y with exact sizing on X."""
import sys, json
from chain import *
from series import SeriesAnchor
from engine_v3 import run
chain = sys.argv[1]; days = float(sys.argv[2])
CFG = {
 "base": dict(d0=18, d1=6, gas=0.03, pools={"UniV3 0.05%":"0xd0b53d9277642d899df5c87a3966a349a798f224","AeroCL ts100":"0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59","PancakeV3 0.01%":"0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38","UniV3 0.3%":"0x6c561b446416e1a00e8e93e221854d6ea4171372"}),
 "op":   dict(d0=6, d1=18, gas=0.02, pools={"UniV3 0.05%":"0x1fb3cf6e48f1e7b10213e7b6d87d4c073c7fdb7b","UniV3 0.3%":"0xc1738d90e2e26c35784a0d3e3d8a9f795074bca4"}),
 "arb":  dict(d0=18, d1=6, gas=0.05, pools={}),
}
if len(sys.argv) > 3: CFG[chain]["pools"].update(json.loads(sys.argv[3]))
c = CFG[chain]; h = head(chain); span = int(days*86400/CHAINS[chain]["block_time"]); fb = h - span
names = list(c["pools"]); out = []
series = {n: SeriesAnchor(chain, c["pools"][n], fb, h, c["d0"], c["d1"]) for n in names}
for n in names: print(n, "swaps:", series[n].n)
ref = names[0]
for n in names[1:]:
    # X = n (sized), anchor = ref price; then reverse
    for X, Y in ((n, ref), (ref, n)):
        fy = call(chain, c["pools"][Y], "fee()", out=("uint24",))[0]/1e6
        sy = series[Y]
        # treat Y as a hard edge at its marginal price, but charge Y's fee on the conversion
        anchor = lambda b, t, sy=sy, fy=fy: sy.price(b)
        r = run(chain, c["pools"][X], days, anchor, c["d0"], c["d1"], token1_usd=1.0 if c["d1"]==6 else 3500.0, gas_usd=c["gas"],
                min_profit_usd=0.5, label=f"{chain} {X} vs {Y} (Y fee {fy*1e4:.0f}bp not charged)", to_block=h, words=2, validate=(X==names[1]))
        out.append(r)
json.dump(out, open(f"res_xdex_{chain}.json","w"))
