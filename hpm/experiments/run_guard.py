"""Does the 20 log10(N) term survive guard bits?

Two knobs: (a) how the basis is evaluated (cos(w*i) vs exact integer phase),
(b) how many guard bits the solve and the residual evaluation get.  If the
N-term is accumulation noise it should vanish once the guard exceeds log2(N).
"""
import sys, json, math
sys.path.insert(0, ".")
from flint import arb, arb_mat, ctx

FS, F = 8000, 1000


def run(N, guard, route, bits=240):
    eps = 2.0 ** -bits
    ctx.prec = bits + 120
    tp = 2 * arb.pi()
    x = [arb("0.5") * ((tp * arb((F * i) % FS) / arb(FS)).sin()) for i in range(N)]
    w = 2 * arb.pi() * arb(F) / arb(FS)
    ctx.prec = bits + guard
    if route == "phase":
        cs = [((tp * arb((F * i) % FS) / arb(FS)).cos(),
               (tp * arb((F * i) % FS) / arb(FS)).sin()) for i in range(N)]
    else:
        cs = [((w * i).cos(), (w * i).sin()) for i in range(N)]
    cc = ss = sg = bc = bs = arb(0)
    for i in range(N):
        c, s = cs[i]
        cc += c * c; ss += s * s; sg += c * s
        bc += c * x[i]; bs += s * x[i]
    sol = list(arb_mat([[cc, sg], [sg, ss]]).solve(arb_mat([[bc], [bs]])))
    a, b = sol
    r2 = arb(0); x2 = arb(0)
    for i in range(N):
        c, s = cs[i]
        d = x[i] - (a * c + b * s)
        r2 += d * d; x2 += x[i] * x[i]
    ctx.prec = bits
    nul = float(-10 * (r2.abs_upper().log() - x2.abs_lower().log()) / arb(10).log())
    return 6.0206 * bits - nul


rows = []
for route in ("phase", "w*i"):
    for N in (1024, 4096, 16384):
        line = []
        for guard in (0, 16, 32, 64, 128, 256):
            g = run(N, guard, route)
            line.append(round(g, 2))
            rows.append(dict(route=route, N=N, guard=guard, gap_db=g))
        print("%-6s N=%6d  gaps for guard 0/16/32/64/128/256: %s" % (route, N, line))
json.dump(rows, open("hpm/experiments/results_guard.json", "w"), indent=1)
