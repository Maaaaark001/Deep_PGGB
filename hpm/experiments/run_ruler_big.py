"""Extend the ruler law to engine-scale N (1.27e6 samples).

The law fitted on N <= 65536 predicts 440.7 dB at p=94, N=1.27e6; the measured
value is 433.2 dB, so the log2(N) coefficient must be slightly larger out there.
"""
import sys, json, math
sys.path.insert(0, ".")
from flint import arb, ctx
from hpm.arb import mcore, measure

FS, F = 88200, 1000
rows = []
for N in (262144, 1270080):
    for p in (96, 120, 240):
        x = mcore.tone(F, FS, N, "0.5", p + 400)
        cs = mcore.basis_exact(F, FS, N, p)
        w = mcore.omega(F, FS, p + 400)
        c, r2, x2, _ = mcore.ls_known(x, [w], None, p, cs=[cs])
        rad = c[0].rad() + c[1].rad()
        coef = -measure._db_ratio(arb(N) * rad * rad, x2)
        nul = mcore.null_upper_db(r2, x2)
        rows.append(dict(p=p, N=N, coef_db=coef, null_db=nul,
                         law_coef=6.0198 * p - 5.9488 * math.log2(N) - 4.59))
        print("p=%4d N=%8d coef=%9.2f (law %9.2f, delta %+6.2f)  null=%9.2f" %
              (p, N, coef, rows[-1]["law_coef"], coef - rows[-1]["law_coef"], nul), flush=True)
json.dump(rows, open("hpm/experiments/results_ruler_big.json", "w"), indent=1)
print("wrote results_ruler_big.json")
