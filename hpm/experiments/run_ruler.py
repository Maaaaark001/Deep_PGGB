"""The ruler's own floor: how deep can the estimator see at precision p?

Two channels, both free and rigorous:

  coefficient  |dm| <= rad(a) + rad(b)  ->  -10log10(N * rad^2 / x2)
  frequency    |dm/dw| <= i*A           ->  -10log10(2*dw^2*sum(i^2)/N)

Both scale like 6.02*p minus a term that grows with N, so the *ruler* and the
*data* floor have the same shape.  That is why the advisor has to return two
numbers: the bits the target needs, and the bits at which the ruler stops being
able to certify it.
"""
import sys, json, math
sys.path.insert(0, ".")
from flint import arb, ctx
from hpm.arb import mcore, measure

FS, F = 8000, 1000
rows = []
for p in (60, 120, 240, 480, 960):
    for N in (1024, 4096, 16384, 65536):
        x = mcore.tone(F, FS, N, "0.5", p + 400)
        cs = mcore.basis_exact(F, FS, N, p)
        w = mcore.omega(F, FS, p + 400)
        c, r2, x2, _ = mcore.ls_known(x, [w], None, p, cs=[cs])
        rad = c[0].rad() + c[1].rad()
        coef = measure._db_ratio(arb(N) * rad * rad, x2)
        coef = -coef if coef != float("inf") else float("inf")
        freq = -measure.lipschitz_null_db(N, 0.5, w.rad())
        nul = mcore.null_upper_db(r2, x2)
        rows.append(dict(p=p, N=N, coef_db=coef, freq_db=freq, null_db=nul,
                         ruler_db=min(coef, freq),
                         rad_over_eps=float(rad) / 2.0 ** -p))
        print("p=%4d N=%6d coef=%9.1f freq=%9.1f null=%9.1f  null-coef=%+6.1f  rad/eps=%.1f" %
              (p, N, coef, freq, nul, nul - coef, float(rad) / 2.0 ** -p), flush=True)

# fit coef = a*p + b*log2(N) + c
data = list(rows)
for key in ("coef_db", "freq_db"):
    A = [[r["p"], math.log2(r["N"]), 1.0] for r in data]
    y = [r[key] for r in data]
    M = [[sum(A[k][i] * A[k][j] for k in range(len(A))) for j in range(3)] for i in range(3)]
    b = [sum(A[k][i] * y[k] for k in range(len(A))) for i in range(3)]
    Mm = [row[:] + [b[i]] for i, row in enumerate(M)]
    for i in range(3):
        pv = max(range(i, 3), key=lambda r_: abs(Mm[r_][i]))
        Mm[i], Mm[pv] = Mm[pv], Mm[i]
        for r_ in range(i + 1, 3):
            fac = Mm[r_][i] / Mm[i][i]
            for c_ in range(i, 4):
                Mm[r_][c_] -= fac * Mm[i][c_]
    sol = [0.0] * 3
    for i in (2, 1, 0):
        sol[i] = (Mm[i][3] - sum(Mm[i][j] * sol[j] for j in range(i + 1, 3))) / Mm[i][i]
    resid = [y[k] - sum(A[k][i] * sol[i] for i in range(3)) for k in range(len(y))]
    print("FIT %s = %.4f*p %+.4f*log2N %+.2f   max|resid| %.2f dB" %
          (key, sol[0], sol[1], sol[2], max(abs(v) for v in resid)), flush=True)
    rows_key = dict(a_p=sol[0], b_log2N=sol[1], c=sol[2], max_resid=max(abs(v) for v in resid))
    rows.append(dict(kind="fit_" + key, **rows_key))

json.dump(rows, open("hpm/experiments/results_ruler.json", "w"), indent=1)
print("wrote results_ruler.json")
