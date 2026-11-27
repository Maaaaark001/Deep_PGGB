"""The certificate law, measured at zero guard bits with the exact-phase basis.

null = a*p - b*log2(N) - c - cf(f), with p the working precision.  a should be
6.02 dB/bit (the arithmetic ceiling); b should be 6.02 dB per doubling (the
residual energy grows with the coefficient radii, which grow with N); c and cf
are the constants the advisor has to carry.
"""
import sys, json, math
sys.path.insert(0, ".")
from flint import arb, ctx
from hpm.arb import mcore

FS = 8000
rows = []
for p in (120, 180, 240, 300):
    for N in (1024, 4096, 16384):
        for f in (100, 1000, 3990):
            x = mcore.tone(f, FS, N, "0.5", p + 400)
            cs = mcore.basis_exact(f, FS, N, p)
            w = mcore.omega(f, FS, p + 400)
            c, r2, x2, _ = mcore.ls_known(x, [w], None, p, cs=[cs])
            nul = mcore.null_upper_db(r2, x2)
            rows.append(dict(p=p, N=N, f=f, null_db=nul))
            print("p=%4d N=%6d f=%5d null=%9.2f  a=%.4f  resid=%7.2f" %
                  (p, N, f, nul, nul / p, nul - 6.0206 * p + 20 * math.log10(N)))

# least squares: null = a*p + b*log2(N) + c*log10(f) + d
A = [[r["p"], math.log2(r["N"]), math.log10(r["f"]), 1.0] for r in rows]
y = [r["null_db"] for r in rows]
n = 4
M = [[sum(A[k][i] * A[k][j] for k in range(len(A))) for j in range(n)] for i in range(n)]
b = [sum(A[k][i] * y[k] for k in range(len(A))) for i in range(n)]
Mm = [row[:] + [b[i]] for i, row in enumerate(M)]
for i in range(n):
    pv = max(range(i, n), key=lambda r_: abs(Mm[r_][i]))
    Mm[i], Mm[pv] = Mm[pv], Mm[i]
    for r_ in range(i + 1, n):
        fac = Mm[r_][i] / Mm[i][i]
        for c_ in range(i, n + 1):
            Mm[r_][c_] -= fac * Mm[i][c_]
sol = [0.0] * n
for i in range(n - 1, -1, -1):
    sol[i] = (Mm[i][n] - sum(Mm[i][j] * sol[j] for j in range(i + 1, n))) / Mm[i][i]
resid = [y[k] - sum(A[k][i] * sol[i] for i in range(n)) for k in range(len(y))]
print("FIT null = %.4f*p %+.3f*log2N %+.3f*log10f %+.2f   max|resid| %.1f dB, rms %.1f dB" %
      (sol[0], sol[1], sol[2], sol[3], max(abs(v) for v in resid),
       (sum(v * v for v in resid) / len(resid)) ** 0.5))
json.dump(dict(rows=rows, fit=dict(a_p=sol[0], b_log2N=sol[1], c_log10f=sol[2], d=sol[3],
                                   max_resid=max(abs(v) for v in resid))),
          open("hpm/experiments/results_law.json", "w"), indent=1)
