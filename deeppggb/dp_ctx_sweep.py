# -*- coding: utf-8 -*-
"""context 扫描：镜像带能量、混叠、速度。找与 PGGB 齐平的最小代价。"""
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

x60 = np.repeat(Q._tone(1000.0, 44100, 60.0), 2, axis=1)

def speed(key, o):
    best = None
    for _ in range(2):
        t0 = time.perf_counter()
        E.resample(x60, 44100, 88200, key, o)
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return 60.0 / best

print("%-12s %9s %9s %9s %8s" % ("context", "img-hi", "img-all", "alias", "speed"))
for ctx in (400.0, 600.0, 800.0, 1000.0):
    o = {"context": ctx}
    x = Q._tone(1000.0, 44100, 4.0)
    s = center(E.resample(x, 44100, 88200, "dpggb", o), 88200)
    lvl = Q._line_level(s, 88200, 1000.0)
    hi = img_band(s, 88200, 42600.0, 44100.0, lvl)
    al = img_band(s, 88200, 22050.0, 44100.0, lvl)
    xa = Q._tone(1000.0, 96000, 4.0, 0.5) + Q._tone(30000.0, 96000, 4.0, 0.5)
    sa = center(E.resample(xa, 96000, 44100, "dpggb", o), 44100)
    ra = max(Q._line_level(sa, 44100, 1000.0), Q.EPS)
    alias = 20 * np.log10(max(Q._line_level(sa, 44100, 14100.0), Q.EPS) / ra)
    print("%-12.0f %9.1f %9.1f %9.1f %8.0f" % (ctx, hi, al, alias, speed("dpggb", o)))

x = Q._tone(1000.0, 44100, 4.0)
s = center(E.resample(x, 44100, 88200, "pggb", None), 88200)
lvl = Q._line_level(s, 88200, 1000.0)
print("%-12s %9.1f %9.1f %9s %8.0f" %
      ("pggb", img_band(s, 88200, 42600.0, 44100.0, lvl),
       img_band(s, 88200, 22050.0, 44100.0, lvl), "n/a", speed("pggb", None)))
