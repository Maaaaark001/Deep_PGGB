"""Where the 30.5 dB of the guard plateau comes from."""
import sys

sys.path.insert(0, ".")
import math
from flint import arb, arb_mat, ctx

FS, F, BITS = 8000, 1000, 240


def run(N, guard, p_stim):
    ctx.prec = p_stim
    tp = 2 * arb.pi()
    x = [arb("0.5") * ((tp * arb((F * i) % FS) / arb(FS)).sin()) for i in range(N)]
    ctx.prec = BITS + guard
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
    return a, b, r2, x2


for N in (1024, 4096):
    for ps in (120, 240):
        a, b, r2, x2 = run(N, 384, ps)
        lr2, lx2 = float(r2.mid().log()), float(x2.mid().log())
        rad_r2 = float(r2.rad().log()) if r2.rad() > 0 else -1e9
        print("N=%4d p_stim=%3d  log r2 %10.2f  log rad(r2) %10.2f  log x2 %8.2f  "
              "rad/val %.2e  -> %.2f dB"
              % (N, ps, lr2, rad_r2, lx2, math.exp(rad_r2 - lr2),
                 10 * (rad_r2 - lr2) / math.log(10)))
        print("      a = %.6f +- %.2e   b = %.6f +- %.2e"
              % (float(a.mid()), float(a.rad()), float(b.mid()), float(b.rad())))
