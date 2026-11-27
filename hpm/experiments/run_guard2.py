"""Guard bits and stimulus precision: who owns the ceiling?

The earlier experiment (run_guard.py) reported "gap" = 6.0206*bits - null, i.e.
it compared the certificate against the *nominal* working precision and ignored
the guard bits themselves.  Read that way, every guard bit looks like a 6 dB
regression, and the certificate ends up hundreds of dB above the midpoint.  That
reading is wrong: the guard bits are part of the arithmetic, so the honest
abscissa is p_eff = bits + guard.

Two ceilings then show up, and they are separable:

  arithmetic   null = 6.0199 p_eff - 4.4941 L - 0.0583 L^2 - 10.44      (the law)
  stimulus     null = 6.0199 p_stim - 5.1                                (the cap)

The certificate follows the law until p_eff passes p_stim, then plateaus.  The
plateau is the stimulus's own representation floor, the same kind of number as
the format ladder (binary128 / float64 / PCM24) - a property of the file, not of
the estimator.  So guard bits are not useless; they are the knob that moves the
estimator out of the way so that the file's floor can be seen.
"""
import json
import sys

sys.path.insert(0, ".")
from flint import arb, arb_mat, ctx

FS, F, BITS = 8000, 1000, 240
N_LIST = [1024, 4096]
P_STIM = [120, 240, 360, 480, 720]
GUARDS = [0, 16, 32, 64, 128, 192, 256, 384]


def run(N, guard, p_stim, bits=BITS):
    """Build the stimulus at p_stim, solve and evaluate the residual at bits+guard."""
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
    return float(-10 * (r2.abs_upper().log() - x2.abs_lower().log()) / arb(10).log())


rows = []
for N in N_LIST:
    for p_stim in P_STIM:
        for g in GUARDS:
            if p_stim > 480 and g > 192 and N == 4096:
                continue
            v = run(N, g, p_stim)
            rows.append(dict(N=N, bits=BITS, guard=g, p_stim=p_stim,
                             p_eff=BITS + g, null_db=v))
            print("N=%5d p_stim=%3d guard=%3d p_eff=%3d  null %9.2f  "
                  "(%.2f bit of p_eff, %.2f bit of p_stim)"
                  % (N, p_stim, g, BITS + g, v, v / 6.0206,
                     (v + 5.1) / 6.0199), flush=True)

json.dump(rows, open("hpm/experiments/results_guard2.json", "w"), indent=1)
print("wrote results_guard2.json", len(rows), "rows")
