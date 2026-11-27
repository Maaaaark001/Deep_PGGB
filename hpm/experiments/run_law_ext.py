"""Push the certificate law past the range it was fitted on.

Two directions, because the quadratic term says the two are not independent:

  precision  p = 960, 1920, 3840 bit at N = 1.27 M   (the fit stopped at 960)
  length     N = 2.8 M, 5.6 M at p = 240, 480        (the fit stopped at 1.27 M)

Synthetic data throughout (exact integer phase, so the stimulus is not the limit),
and every point records the ruler next to the certificate: a point is only
admissible if the certificate stays 20 dB below the ruler.
"""
import json, sys, time
sys.path.insert(0, '.')
from flint import arb, ctx
from hpm.arb import measure, mcore, advisor

FS = 8000
F = 1000
rows = []


def point(p, N, f=F, fs=FS):
    t0 = time.time()
    x = mcore.tone(f, fs, N, '0.5', p + 300)
    cs = mcore.basis_exact(f, fs, N, p)
    w = mcore.omega(f, fs, p + 300)
    c, r2, x2, _ = mcore.ls_known(x, [w], None, p, cs=[cs])
    cert = mcore.null_upper_db(r2, x2)
    ruler = advisor.ruler_db(p, N)
    dt = time.time() - t0
    pred = advisor.certifiable_db(p, N, f)
    rec = dict(p=p, N=N, f=f, cert_db=cert, ruler_db=ruler, law_db=pred,
               resid_db=cert - pred, wall_s=dt)
    rows.append(rec)
    print('p=%5d N=%9d  cert %9.2f  law %9.2f  resid %+7.2f  ruler %9.1f  %.1f s'
          % (p, N, cert, pred, cert - pred, ruler, dt), flush=True)
    return rec


print('--- precision direction', flush=True)
for p in (960, 1920, 3840):
    point(p, 1_270_080)

print('--- length direction', flush=True)
for N in (2_822_400, 5_644_800):
    for p in (240, 480):
        point(p, N)

json.dump(rows, open('hpm/experiments/results_law_ext.json', 'w'), indent=1)
print('wrote results_law_ext.json')