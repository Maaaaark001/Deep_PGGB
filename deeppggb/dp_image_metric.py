# -*- coding: utf-8 -*-
"""镜像指标在两种倍率、三种上下文下的行为：单 bin / 窄带 / 宽带，谁稳定？"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

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
    return 10 * np.log10(max(e, 1e-300) / max(ref ** 2 / 2.0, 1e-300))

def probe(key, o, dst):
    x = Q._tone(1000.0, 44100, 4.0)
    s = center(E.resample(x, 44100, dst, key, o), dst)
    lvl = Q._line_level(s, dst, 1000.0)
    nyq = dst / 2.0
    imgf = 44100.0 - 1000.0
    bin_ = 20 * np.log10(max(Q._line_level(s, dst, imgf), Q.EPS) / max(lvl, Q.EPS))
    return (bin_,
            band_db(s, dst, imgf + 100.0, nyq, lvl),
            band_db(s, dst, imgf - 500.0, nyq, lvl),
            band_db(s, dst, 22050.0, nyq, lvl))

print("%-26s %8s %9s %9s %9s" % ("config", "bin", "band+100", "band-500", "from22k"))
for dst in (88200, 96000):
    for ctx in (400.0, 800.0, 1600.0):
        a, b, c, d = probe("dpggb", {"context": ctx}, dst)
        print("%-26s %8.1f %9.1f %9.1f %9.1f" % ("dpggb %d ctx%.0f" % (dst, ctx), a, b, c, d))
    # floor
    s = center(Q._tone(1000.0, dst, 4.0), dst)
    lvl = Q._line_level(s, dst, 1000.0)
    imgf = 43100.0
    print("%-26s %8.1f %9.1f %9.1f %9.1f" %
          ("analytic floor", 20*np.log10(max(Q._line_level(s, dst, imgf), Q.EPS)/lvl),
           band_db(s, dst, imgf+100, dst/2.0, lvl), band_db(s, dst, imgf-500, dst/2.0, lvl),
           band_db(s, dst, 22050.0, dst/2.0, lvl)))
if True:
    a, b, c, d = probe("pggb", None, 88200)
    print("%-26s %8.1f %9.1f %9.1f %9.1f" % ("pggb 88200", a, b, c, d))
