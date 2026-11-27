import sys, json, math, time
sys.path.insert(0, ".")
from flint import arb, ctx
from hpm.arb import mcore

FS = 8000

def one(bits, N, f):
    x = mcore.tone(f, FS, N, "0.5", bits + 60)
    w = mcore.omega(f, FS, bits + 60)
    c, r2, x2, _ = mcore.ls_known(x, [w], None, bits)
    nul = mcore.null_upper_db(r2, x2)
    return dict(bits=bits, N=N, f=f, null_db=nul, gap_db=6.0206 * bits - nul,
                r2_mid=float(r2.mid()), r2_rad=float(r2.rad()),
                x2=float(x2.mid()), coeff_rad=float(max(v.rad() for v in c)))

rows = []
for N in (1024, 4096, 16384):
    for f in (100, 250, 500, 1000, 2000, 3000, 3990):
        r = one(240, N, f)
        rows.append(r)
        print("N=%6d f=%5d gap=%7.2f  r2mid=%.2e r2rad=%.2e  mid_limited=%s" %
              (N, f, r["gap_db"], r["r2_mid"], r["r2_rad"],
               abs(r["r2_mid"]) > r["r2_rad"]))

# least squares fit gap = a*log10(N) + b*log10(f) + c
import itertools
A = [[math.log10(r["N"]), math.log10(r["f"]), 1.0] for r in rows]
y = [r["gap_db"] for r in rows]
# normal equations 3x3
M = [[sum(A[k][i]*A[k][j] for k in range(len(A))) for j in range(3)] for i in range(3)]
b = [sum(A[k][i]*y[k] for k in range(len(A))) for i in range(3)]
# solve by hand (Gauss)
import copy
Mm = [row[:] + [b[i]] for i, row in enumerate(M)]
for i in range(3):
    p = max(range(i,3), key=lambda r_: abs(Mm[r_][i]))
    Mm[i], Mm[p] = Mm[p], Mm[i]
    for r_ in range(i+1,3):
        fac = Mm[r_][i]/Mm[i][i]
        for c_ in range(i,4):
            Mm[r_][c_] -= fac*Mm[i][c_]
sol = [0]*3
for i in (2,1,0):
    sol[i] = (Mm[i][3] - sum(Mm[i][j]*sol[j] for j in range(i+1,3)))/Mm[i][i]
print("FIT gap = %.3f*log10(N) + %.3f*log10(f) + %.3f" % tuple(sol))
resid = [y[k] - sum(A[k][i]*sol[i] for i in range(3)) for k in range(len(y))]
print("max resid %.2f dB, rms %.2f dB" % (max(abs(v) for v in resid), (sum(v*v for v in resid)/len(resid))**0.5))
json.dump(dict(rows=rows, fit=dict(a_logN=sol[0], b_logf=sol[1], c=sol[2],
          max_resid=max(abs(v) for v in resid))),
          open("hpm/experiments/results_gaplaw.json", "w"), indent=1)
