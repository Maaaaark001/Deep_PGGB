"""The precision advisor's law, measured in the inverse direction.

For a target certificate T we bisect the working precision and record the first
p that certifies T.  Measured with the exact-integer-phase basis, which is what
the library now uses.  Fit:  p = T/6.0206 + log2(N) + b*log10(f) + c.
"""
import sys, json, math, time
sys.path.insert(0, ".")
from flint import arb, ctx
from hpm.arb import mcore

FS = 8000


def cert_at(bits, N, f):
    x = mcore.tone(f, FS, N, "0.5", bits + 400)
    cs = mcore.basis_exact(f, FS, N, bits)
    w = mcore.omega(f, FS, bits + 400)
    c, r2, x2, _ = mcore.ls_known(x, [w], None, bits, cs=[cs])
    return mcore.null_upper_db(r2, x2)


def bits_for(target, N, f, lo=32, hi=20000, tol=2):
    while hi - lo > tol:
        mid = (lo + hi) // 2
        if cert_at(mid, N, f) >= target:
            hi = mid
        else:
            lo = mid
    return hi


rows = []
for N in (1024, 4096, 16384):
    for f in (100, 500, 1000, 2000, 3990):
        p = bits_for(1000.0, N, f)
        rows.append(dict(N=N, f=f, T=1000.0, bits=p))
        print("N=%6d f=%5d -> %5d bits" % (N, f, p))

A = [[math.log2(r["N"]), math.log10(r["f"]), 1.0] for r in rows]
y = [float(r["bits"]) for r in rows]
M = [[sum(A[k][i] * A[k][j] for k in range(len(A))) for j in range(3)] for i in range(3)]
b = [sum(A[k][i] * y[k] for k in range(len(A))) for i in range(3)]
Mm = [row[:] + [b[i]] for i, row in enumerate(M)]
for i in range(3):
    p_ = max(range(i, 3), key=lambda r_: abs(Mm[r_][i]))
    Mm[i], Mm[p_] = Mm[p_], Mm[i]
    for r_ in range(i + 1, 3):
        fac = Mm[r_][i] / Mm[i][i]
        for c_ in range(i, 4):
            Mm[r_][c_] -= fac * Mm[i][c_]
sol = [0.0] * 3
for i in (2, 1, 0):
    sol[i] = (Mm[i][3] - sum(Mm[i][j] * sol[j] for j in range(i + 1, 3))) / Mm[i][i]
resid = [y[k] - sum(A[k][i] * sol[i] for i in range(3)) for k in range(len(y))]
print("FIT bits = %.3f*log2(N) + %.3f*log10(f) + %.3f  max resid %.2f bit" %
      (sol[0], sol[1], sol[2], max(abs(v) for v in resid)))

json.dump(dict(rows=rows, fit=dict(a_log2N=sol[0], b_log10f=sol[1], c=sol[2],
                                   max_resid_bits=max(abs(v) for v in resid))),
          open("hpm/experiments/results_advisor.json", "w"), indent=1)
