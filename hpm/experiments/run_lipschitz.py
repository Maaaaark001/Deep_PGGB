"""Coherence-free certification: an endpoint plus a Lipschitz term.

Claim under test: a certificate does not require knowing the frequency exactly,
nor coherent sampling.  Two channels are compared on the same data:

  (a) endpoint only   - evaluate the model at the estimated omega and let the
                        ball for omega propagate through the basis.  This is what
                        ball arithmetic gives for free, and it is what Newton's
                        radius growth destroys (~35x per iteration).
  (b) endpoint + Lipschitz - |dm/dw| <= i*A bounds how far a frequency error dw
                        can move the model; the residual energy bound is
                        (A*dw)^2 * sum(i^2), closed form, no extra arithmetic.

Also measured: the *slack* of the Lipschitz bound, i.e. how conservative it is.
"""
import sys, json, math
sys.path.insert(0, ".")
from flint import arb, ctx
from hpm.arb import mcore, measure

FS, F, N = 8000, 1000, 4096
BITS = 400
rows = []

ctx.prec = BITS + 200
x = mcore.tone(F, FS, N, "0.5", BITS + 150)
w = mcore.omega(F, FS, BITS + 150)
amp = 0.5

print("--- (1) known frequency, deliberately perturbed ---")
for rel in ("1e-10", "1e-20", "1e-30", "1e-40", "1e-50", "1e-70", "1e-90"):
    wp = w * (arb(1) + arb(rel))
    # the basis must be built from the *perturbed* omega, otherwise the
    # perturbation never enters the model and the null cannot move
    cs = mcore.basis(wp, N, BITS)
    c, r2, x2, _ = mcore.ls_known(x, [wp], None, BITS, cs=[cs])
    nul = mcore.null_upper_db(r2, x2)
    dw = float((wp - w).abs_upper())
    bound = -measure.lipschitz_null_db(N, amp, dw)
    rows.append(dict(rel=rel, dw=dw, null_db=nul, lipschitz_db=bound, slack_db=nul - bound))
    print("  dw/w=%-6s  null >= %8.1f dB   lipschitz bound %8.1f dB   slack %+6.1f dB" %
          (rel, nul, bound, nul - bound))

print("--- (2) unknown frequency: Newton ball vs Lipschitz ---")
ctx.prec = 600
fm, fsm = 1000500, FS * 1000
xu = mcore.tone(fm, fsm, N, "0.5", 700)
true_w = mcore.omega(fm, fsm, 700)
w0 = ((xu[0] + xu[2]) / (2 * xu[1])).acos()
ctx.prec = 600
a, b, omegas, r2n, x2n, hist = mcore.newton(xu, [w0], 600, iters=5)
om = omegas[0]
endpoint = mcore.null_upper_db(r2n, x2n)
dw = float(om.rad())
ampn = abs(a[0].abs_upper()) + abs(b[0].abs_upper())
lips = -measure.lipschitz_null_db(N, float(ampn), om.rad())
print("  omega = %.20f  (radius %.3e, i.e. %.3e Hz)" %
      (float(om.mid()), dw, dw / (2 * math.pi) * FS))
print("  endpoint-only certificate   >= %8.1f dB" % endpoint)
print("  endpoint + Lipschitz        >= %8.1f dB" % lips)
print("  true offset of the midpoint %.3e rad" % float((om - true_w).abs_upper()))
rows.append(dict(case="newton", endpoint_db=endpoint, lipschitz_db=lips,
                 omega_radius=dw, omega_mid=float(om.mid())))

print("--- (3) non-coherent, known frequency (the 1241 claim) ---")
ctx.prec = 600
xn = mcore.tone(1000500, FS * 1000, N, "0.5", 700)
wn = mcore.omega(1000500, FS * 1000, 700)
csn = mcore.basis_exact(1000500, FS * 1000, N, 600)
c, r2c, x2c, _ = mcore.ls_known(xn, [wn], None, 600, cs=[csn])
nul = mcore.null_upper_db(r2c, x2c)
print("  1000.5 Hz in 8000 Hz (no coherent sampling, no window): null >= %.1f dB" % nul)
rows.append(dict(case="noncoherent", null_db=nul))

json.dump(rows, open("hpm/experiments/results_lipschitz.json", "w"), indent=1)
print("wrote results_lipschitz.json")
