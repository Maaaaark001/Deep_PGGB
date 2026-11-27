"""Validate the advisor and measure the Newton certificate decay.

(1) Advisor: for a grid of (target, N, f) predict the bits, then measure the
    certificate actually reached at that precision.  A prediction is useful only
    if the measured certificate is at or above the target.
(2) Wall-clock calibration for advisor.wall_seconds.
(3) Newton: the certificate after each Gauss-Newton step, with the exact-phase
    basis, to see whether the radius growth is still 35x per step.
"""
import sys, json, math, time
sys.path.insert(0, ".")
from flint import arb, arb_mat, ctx
from hpm.arb import advisor, mcore

FS = 8000
out = {}


def measure_at(bits, N, f, T=None):
    t0 = time.time()
    x = mcore.tone(f, FS, N, "0.5", bits + 400)
    cs = mcore.basis_exact(f, FS, N, bits)
    w = mcore.omega(f, FS, bits + 400)
    c, r2, x2, _ = mcore.ls_known(x, [w], None, bits, cs=[cs])
    nul = mcore.null_upper_db(r2, x2)
    return nul, time.time() - t0


print("--- advisor validation ---")
rows = []
for T, N, f in [(200, 4096, 1000), (500, 4096, 1000), (1000, 4096, 1000),
                (1000, 1024, 100), (1000, 16384, 3990), (2000, 4096, 1000),
                (3000, 65536, 1000), (440, 1411200, 1000)]:
    p = advisor.bits_for(T, N, f)
    nul, dt = measure_at(p, N, f)
    rows.append(dict(T=T, N=N, f=f, bits=p, measured=nul, margin=nul - T, wall_s=dt))
    print("  T=%5d N=%7d f=%5d -> %4d bit -> measured %9.1f dB (margin %+8.1f, %.1f s)" %
          (T, N, f, p, nul, nul - T, dt))
out["advisor_validation"] = rows

print("--- wall-clock calibration (bits=240, K=1, N=4096) ---")
xs = []
for N in (4096, 16384, 65536):
    x = mcore.tone(1000, FS, N, "0.5", 640)
    cs = mcore.basis_exact(1000, FS, N, 240)
    w = mcore.omega(1000, FS, 640)
    t0 = time.time()
    mcore.ls_known(x, [w], None, 240, cs=[cs])
    dt = time.time() - t0
    xs.append(dict(N=N, wall_s=dt, ns_per_sample_per_bit=dt / (N * 240) * 1e9))
    print("  N=%6d  %.2f s  -> %.3f ns per sample per bit" % (N, dt, dt / (N * 240) * 1e9))
out["wall_calibration"] = xs

print("--- Newton certificate decay (exact-phase basis) ---")
BITS = 600
N = 4096
fm, fsm = 1000500, FS * 1000
ctx.prec = BITS + 200
xu = mcore.tone(fm, fsm, N, "0.5", BITS + 150)
true_w = mcore.omega(fm, fsm, BITS + 150)
w0 = ((xu[0] + xu[2]) / (2 * xu[1])).acos()
ctx.prec = BITS
om = [arb(w0)]
cs = [mcore.basis(om[0], N, BITS)]
c, r2, x2, _ = mcore.ls_known(xu, [om[0]], None, BITS, cs=cs)
aa = [c[0]]
bb = [c[1]]
hist = [dict(step=0, null_db=mcore.null_upper_db(r2, x2), w_rad=float(om[0].rad()),
             w_err=float((om[0] - true_w).abs_upper()))]
print("  step 0 (LP): null >= %8.1f dB  w_err %.2e" % (hist[0]["null_db"], hist[0]["w_err"]))
for it in range(6):
    JtJ = [[arb(0) for _ in range(3)] for _ in range(3)]
    Jtr = [arb(0) for _ in range(3)]
    for i in range(N):
        cc, ss = cs[0][i]
        cols = [cc, ss, -aa[0] * arb(i) * ss + bb[0] * arb(i) * cc]
        mi = aa[0] * cc + bb[0] * ss
        ri = xu[i] - mi
        for p_ in range(3):
            Jtr[p_] += cols[p_] * ri
            for q_ in range(p_, 3):
                JtJ[p_][q_] += cols[p_] * cols[q_]
    for p_ in range(3):
        for q_ in range(p_):
            JtJ[p_][q_] = JtJ[q_][p_]
    try:
        delta = list(arb_mat(JtJ).solve(arb_mat([[v] for v in Jtr])))
    except ZeroDivisionError:
        print("  step %d: singular" % (it + 1))
        break
    aa[0] += delta[0]
    bb[0] += delta[1]
    om[0] += delta[2]
    cs = [mcore.basis(om[0], N, BITS)]
    rr = arb(0); xx = arb(0)
    for i in range(N):
        cc, ss = cs[0][i]
        d = xu[i] - (aa[0] * cc + bb[0] * ss)
        rr += d * d; xx += xu[i] * xu[i]
    h = dict(step=it + 1, null_db=mcore.null_upper_db(rr, xx), w_rad=float(om[0].rad()),
             w_err=float((om[0] - true_w).abs_upper()))
    hist.append(h)
    print("  step %d: null >= %8.1f dB  w_rad %.3e  w_err %.3e" % (h["step"], h["null_db"], h["w_rad"], h["w_err"]))
out["newton_decay"] = hist

json.dump(out, open("hpm/experiments/results_validate.json", "w"), indent=1)
print("wrote results_validate.json")
