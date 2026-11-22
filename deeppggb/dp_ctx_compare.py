# -*- coding: utf-8 -*-
"""context 400 vs 800：是否值得用 15% 速度换 8-20 dB 镜像？全指标对照。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

def img_band(s, rate, lo, hi, ref):
    n = s.shape[0]
    spec = np.abs(np.fft.rfft(s)) ** 2
    f = np.fft.rfftfreq(n, 1.0 / rate)
    m = (f >= lo) & (f <= hi)
    e = float(np.sum(spec[m])) * 2.0 / (n * n)
    return 10 * np.log10(max(e, 1e-300) / max(ref**2/2.0, 1e-300))

def full(key, o):
    r = {}
    x = Q._tone(1000.0, 44100, 4.0)
    s = center(E.resample(x, 44100, 88200, key, o), 88200)
    r["spur"] = Q._tone_residual(s, 88200, [1000.0])[0]
    lvl = Q._line_level(s, 88200, 1000.0)
    r["img_hi"] = img_band(s, 88200, 42600.0, 44100.0, lvl)
    r["img_all"] = img_band(s, 88200, 22050.0, 44100.0, lvl)

    xa = Q._tone(1000.0, 96000, 4.0, 0.5) + Q._tone(30000.0, 96000, 4.0, 0.5)
    sa = center(E.resample(xa, 96000, 44100, key, o), 44100)
    ra = max(Q._line_level(sa, 44100, 1000.0), Q.EPS)
    r["alias"] = 20*np.log10(max(Q._line_level(sa, 44100, 14100.0), Q.EPS)/ra) if key != "pggb" else float("nan")

    xi = Q._two_tone(*Q.IMD_CCIF, 44100, 4.0, 0.25, 0.25)
    si = center(E.resample(xi, 44100, 88200, key, o), 88200)
    r["ccif"] = Q._worst_product(si, 88200, (2*19000-20000, 2*20000-19000, 1000, 39000), Q.IMD_CCIF)[0]

    xm, mtf = Q._multitone(44100, 4.0)
    sm = center(E.resample(xm, 44100, 88200, key, o), 88200)
    r["multi"] = Q._tone_residual(sm, 88200, mtf)[0]

    x60 = np.repeat(Q._tone(1000.0, 44100, 30.0), 2, axis=1)
    best = None
    for _ in range(2):
        t0 = time.perf_counter(); E.resample(x60, 44100, 88200, key, o)
        dt = time.perf_counter()-t0; best = dt if best is None else min(best, dt)
    r["x"] = 30.0/best
    return r

print("%-20s %8s %8s %8s %8s %8s %8s %6s" %
      ("config", "spur", "img-hi", "img-all", "alias", "ccif", "multi", "x"))
for name, key, o in (("dpggb ctx400 (now)", "dpggb", None),
                     ("dpggb ctx800", "dpggb", {"context": 800.0}),
                     ("dpggb ctx1200", "dpggb", {"context": 1200.0}),
                     ("pggb", "pggb", None)):
    r = full(key, o)
    print("%-20s %8.1f %8.1f %8.1f %8s %8.1f %8.1f %6.0f" %
          (name, r["spur"], r["img_hi"], r["img_all"],
           ("n/a" if r["alias"] != r["alias"] else "%8.1f" % r["alias"]),
           r["ccif"], r["multi"], r["x"]))
print()
s = center(Q._tone(1000.0, 88200, 4.0), 88200)
lvl = Q._line_level(s, 88200, 1000.0)
print("floor (analytic 88.2k): img-hi %8.1f  img-all %8.1f" %
      (img_band(s, 88200, 42600.0, 44100.0, lvl), img_band(s, 88200, 22050.0, 44100.0, lvl)))
