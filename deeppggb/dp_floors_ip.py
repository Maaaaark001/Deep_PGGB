# -*- coding: utf-8 -*-
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality, engines

# (1) floors: synthesise directly at 88.2 kHz, never resample
f1, f2 = quality.IMD_CCIF
xi = quality._two_tone(f1, f2, 88200, 4.0, 0.25, 0.25)
seg = xi[88200*3//2: 88200*3//2+88200, 0]
print("CCIF  floor (no resample): %8.1f dBc" % quality._worst_product(seg, 88200, (2*f1-f2, 2*f2-f1, f2-f1, f1+f2), (f1,f2))[0])
f1s, f2s = quality.IMD_SMPTE
xs = quality._two_tone(f1s, f2s, 88200, 4.0, 0.40, 0.10)
seg = xs[88200*3//2: 88200*3//2+88200, 0]
print("SMPTE floor (no resample): %8.1f dBc" % quality._worst_product(seg, 88200, [f2s+i*f1s for i in (-2,-1,1,2)], f2s)[0])
xm, mt_f = quality._multitone(88200, 4.0)
seg = xm[88200*3//2: 88200*3//2+88200, 0]
print("multi floor (no resample): %8.1f dBc" % quality._tone_residual(seg, 88200, mt_f)[0])

# (2) matched ratio 44.1 -> 88.2 for both
def run(key, x, src, dst):
    return np.asarray(engines.resample(x, src, dst, key)[:, 0], dtype=np.float64)

for key in ("dpggb", "pggb"):
    src, dst = 44100, 88200
    x = quality._tone(1000.0, src, 4.0)
    y = run(key, x, src, dst); seg = y[(len(y)-dst)//2:][:dst]
    spur = quality._worst_spur(seg, dst, 1000.0)
    x2 = quality._tone(19000.0, src, 4.0)
    y2 = run(key, x2, src, dst); s2 = y2[(len(y2)-dst)//2:][:dst]
    img = 20*np.log10(max(quality._line_level(s2, dst, 44100-19000.0),1e-20)/max(quality._line_level(s2, dst, 19000.0),1e-20))
    xm2, mtf = quality._multitone(src, 4.0)
    y3 = run(key, xm2, src, dst); s3 = y3[(len(y3)-dst)//2:][:dst]
    mt = quality._tone_residual(s3, dst, mtf)[0]
    print("%-6s 44.1->88.2  spur %8.1f  image %8.1f  mt %8.1f" % (key, spur[0], img, mt))
