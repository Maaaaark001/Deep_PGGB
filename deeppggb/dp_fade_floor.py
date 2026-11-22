# -*- coding: utf-8 -*-
"""用"去掉地板"后的口径重扫 fade / context：20 ms 是否仍然饱和？"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

SRC, DST = 44100, 88200
def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

def band_db(s, rate, lo, hi, ref):
    n = s.shape[0]
    spec = np.abs(np.fft.rfft(s)) ** 2
    f = np.fft.rfftfreq(n, 1.0 / rate)
    m = (f >= lo) & (f <= hi)
    e = float(np.sum(spec[m])) * 2.0 / (n * n)
    return 10 * np.log10(max(e, 1e-300) / (ref ** 2 / 2))

x60 = np.repeat(Q._tone(1000.0, 44100, 30.0), 2, axis=1)
def speed(o):
    best = None
    for _ in range(2):
        t0 = time.perf_counter(); E.resample(x60, 44100, 88200, "dpggb", o)
        dt = time.perf_counter()-t0; best = dt if best is None else min(best, dt)
    return 30.0/best

print("floors: spur(resid) -307.1   image(band) -311.0   single-bin image floor -321.0")
print("%-22s %9s %9s %9s %6s" % ("config", "resid", "img-band", "img-bin", "x"))
for fade in (10.0, 20.0, 50.0, 100.0, 200.0):
    for ctx in (400.0, 800.0):
        o = {"fade": fade, "context": ctx}
        x = Q._tone(1000.0, SRC, 4.0)
        s = center(E.resample(x, SRC, DST, "dpggb", o), DST)
        rs = Q._tone_residual(s, DST, [1000.0])[0]
        ib = band_db(s, DST, 22050.0, 44100.0, 0.5)
        ref = max(Q._line_level(s, DST, 1000.0), Q.EPS)
        bin_ = 20*np.log10(max(Q._line_level(s, DST, 43100.0), Q.EPS)/ref)
        print("%-22s %9.1f %9.1f %9.1f %6.0f" % ("fade%.0f ctx%.0f" % (fade, ctx), rs, ib, bin_, speed(o)))
