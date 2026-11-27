"""Validate the quadratic advisor (hpm/arb/advisor.py) end to end.

For a set of targets it asks the advisor for a precision, measures at exactly
that precision, and reports the margin.  The last two points are engine-scale
(N = 262144 and 1.27M), where the quadratic term matters most.
"""
import json, sys, time
sys.path.insert(0, ".")
from flint import arb, ctx
from hpm.arb import advisor, mcore

FS = 8000
rows = []
CASES = [(200, 4096, 1000), (500, 4096, 1000), (1000, 4096, 1000),
         (1000, 1024, 100), (1000, 16384, 3990), (2000, 4096, 1000),
         (3000, 65536, 1000), (440, 262144, 1000), (440, 1270080, 1000)]
for T, N, f in CASES:
    p = advisor.bits_for(T, N, f)
    x = mcore.tone(f, FS, N, "0.5", p + 400)
    cs = mcore.basis_exact(f, FS, N, p)
    w = mcore.omega(f, FS, p + 400)
    t0 = time.time()
    c, r2, x2, _ = mcore.ls_known(x, [w], None, p, cs=[cs])
    dt = time.time() - t0
    nul = mcore.null_upper_db(r2, x2)
    rul = advisor.ruler_db(p, N)
    rows.append(dict(T=T, N=N, f=f, bits=p, measured=nul, margin=nul - T,
                     ruler=rul, ruler_gap=rul - nul, wall_s=dt,
                     wall_pred=advisor.wall_seconds(p, N)))
    print("T=%5d N=%8d f=%5d -> p=%3d  measured=%9.2f  margin=%+6.2f  ruler=%9.1f (gap %6.1f)  wall %5.1f s (pred %5.1f)" %
          (T, N, f, p, nul, nul - T, rul, rul - nul, dt, rows[-1]["wall_pred"]), flush=True)
json.dump(rows, open("hpm/experiments/results_validate2.json", "w"), indent=1)
print("max |margin| = %.2f dB, mean %+.2f" % (max(abs(r["margin"]) for r in rows), sum(r["margin"] for r in rows) / len(rows)))
