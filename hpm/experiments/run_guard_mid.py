"""Close the guard-plateau budget: enclosure conservatism plus stimulus rounding."""
import sys

sys.path.insert(0, ".")
import math
from flint import arb, arb_mat, ctx

from hpm.arb import mcore

FS, F, BITS = 8000, 1000, 240


def run(N, guard, p_stim, bits=BITS):
    ctx.prec = p_stim
    tp = 2 * arb.pi()
    x = [arb("0.5") * ((tp * arb((F * i) % FS) / arb(FS)).sin()) for i in range(N)]
    ctx.prec = bits + guard
    cs = [((tp * arb((F * i) % FS) / arb(FS)).cos(),
           (tp * arb((F * i) % FS) / arb(FS)).sin()) for i in range(N)]
    cc = ss = sg = bc = bs = arb(0)
    for i in range(N):
        c, s = cs[i]
        cc += c * c
        ss += s * s
        sg += c * s
        bc += c * x[i]
        bs += s * x[i]
    a, b = list(arb_mat([[cc, sg], [sg, ss]]).solve(arb_mat([[bc], [bs]])))
    r2 = arb(0)
    x2 = arb(0)
    for i in range(N):
        c, s = cs[i]
        d = x[i] - (a * c + b * s)
        r2 += d * d
        x2 += x[i] * x[i]
    ctx.prec = bits
    cert = float(-10 * (r2.abs_upper().log() - x2.abs_lower().log()) / arb(10).log())
    mid = mcore.null_mid_db(r2, x2)
    return cert, mid


print("%5s %5s %4s %10s %10s %8s" % ("N", "p_stim", "g", "cert", "mid", "mid-cert"))
for N in (1024, 4096):
    for ps in (120, 240, 480):
        g = 384 if not (ps == 480 and N == 4096) else 192
        c, m = run(N, g, ps)
        print("%5d %5d %4d %10.2f %10.2f %8.2f" % (N, ps, g, c, m, m - c))
