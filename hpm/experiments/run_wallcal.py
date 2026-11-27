"""Wall-clock calibration of the streaming analyser.

The cost model in advisor.wall_seconds() is affine in precision: a fixed term
per sample (decoding, the phasor) plus a term proportional to the working
precision (the ball arithmetic).  This script measures both formats at six
precisions and fits the line, so the two constants come from data rather than
from a single pair of points.
"""
import json, sys, time
sys.path.insert(0, '.')
from hpm.arb import measure

SEC = 4.0
BITS = (100, 200, 300, 400, 600, 800)
rows = []
for fmt, path in (('f128', 'hpm/experiments/_eng16.f128'),
                  ('f64', 'hpm/experiments/_eng16.f64')):
    for bits in BITS:
        t0 = time.time()
        r = measure.measure(path, 88200, [1000], bits=bits, fmt=fmt,
                            skip_s=0.8, tail_s=0.8, total_s=SEC)
        dt = time.time() - t0
        us = dt / (2 * r['N']) * 1e6
        rows.append(dict(fmt=fmt, bits=bits, N=r['N'], seconds=dt, us_per_sample=us,
                         cert=r['null_cert_db']))
        print('%-5s bits=%3d  N=%d  %6.2f s  %6.2f us/sample/pass  cert %.1f'
              % (fmt, bits, r['N'], dt, us, r['null_cert_db']), flush=True)

for fmt in ('f128', 'f64'):
    sel = [r for r in rows if r['fmt'] == fmt]
    n = len(sel)
    sx = sum(r['bits'] for r in sel)
    sy = sum(r['us_per_sample'] for r in sel)
    sxx = sum(r['bits'] ** 2 for r in sel)
    sxy = sum(r['bits'] * r['us_per_sample'] for r in sel)
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    inter = (sy - slope * sx) / n
    print('%-5s  us/sample = %.3f + %.4f * bits   (ns fixed %.0f, ns/bit %.2f)'
          % (fmt, inter, slope, inter * 1000, slope * 1000), flush=True)

json.dump(rows, open('hpm/experiments/results_wallcal.json', 'w'), indent=1)
print('wrote results_wallcal.json')
