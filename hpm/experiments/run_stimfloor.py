"""What does a p-bit stimulus actually cost, in dB?

The plateau of the guard experiment sits at 6.0199*p_stim - 30.5 dB, which is
about 39 dB below the naive "one ulp of a 0.5-amplitude p-bit value" estimate.
Before writing that constant into the manuscript we measure where the 39 dB
goes: generate the sine at p_stim, fit it at p_stim+400 with the exact-phase
basis, and report the residual rms in units of 2^-p_stim.
"""
import sys

sys.path.insert(0, ".")
import math
from flint import arb, ctx

from hpm.arb import mcore

FS, F = 8000, 1000


def residual_rms(p_stim, N=1024, extra=400):
    ctx.prec = p_stim
    tp = 2 * arb.pi()
    x = [arb("0.5") * ((tp * arb((F * i) % FS) / arb(FS)).sin()) for i in range(N)]
    ctx.prec = p_stim + extra
    cs = mcore.basis_exact(F, FS, N, p_stim + extra)
    w = mcore.omega(F, FS, p_stim + extra)
    c, r2, x2, _ = mcore.ls_known(x, [w], None, p_stim + extra, cs=[cs])
    ctx.prec = p_stim + extra
    rms = float((r2 / arb(N)).abs_upper().sqrt())
    return rms, float(x2)


print("%6s %12s %12s %10s %10s" % ("p_stim", "rms", "rms/2^-p", "dB", "null dB"))
for p in (60, 120, 240, 360, 480):
    rms, x2 = residual_rms(p)
    unit = 2.0 ** -p
    db = 10 * math.log10(0.125 / (rms ** 2))
    print("%6d %12.4e %12.3e %10.2f %10.2f"
          % (p, rms, rms / unit, 20 * math.log10(rms / unit), db))
