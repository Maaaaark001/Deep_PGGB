# -*- coding: utf-8 -*-
"""镜像带能量：参考应该取输出里基频的实际电平（PGGB 归一化到 0.99，固定 0.5 会偏 6 dB）。"""
import os, sys
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

print("%-18s %10s %10s %10s" % ("config", "tone lvl", "img@0.5ref", "img@tone"))
for key, o, name in (("dpggb", None, "dpggb ctx400"),
                     ("dpggb", {"context": 800.0}, "dpggb ctx800"),
                     ("dpggb", {"prec": "long"}, "dpggb long"),
                     ("pggb", None, "pggb")):
    x = Q._tone(1000.0, 44100, 4.0)
    s = center(E.resample(x, 44100, 88200, key, o), 88200)
    lvl = Q._line_level(s, 88200, 1000.0)
    print("%-18s %10.4f %10.1f %10.1f" %
          (name, lvl, img_band(s, 88200, 42600.0, 44100.0, 0.5),
           img_band(s, 88200, 42600.0, 44100.0, lvl)))
print()
s = center(Q._tone(1000.0, 88200, 4.0), 88200)
lvl = Q._line_level(s, 88200, 1000.0)
print("%-18s %10.4f %10.1f %10.1f" % ("analytic floor", lvl,
      img_band(s, 88200, 42600.0, 44100.0, 0.5), img_band(s, 88200, 42600.0, 44100.0, lvl)))
