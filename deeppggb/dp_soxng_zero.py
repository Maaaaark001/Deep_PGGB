# -*- coding: utf-8 -*-
"""sox_ng 的"全零输出"是深度阻带还是引擎直接清零？三个判别实验。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

print("== A. 只有阻带音 vs 阻带音+通带音 ==")
for f in (30000.0, 25000.0, 23000.0, 22050.0):
    x = Q._tone(f, 96000, 4.0)
    seg = center(E.resample(x, 96000, 44100, "soxng", E.default_opts("soxng")), 44100)
    print("   only %6.0f Hz : zeros %6d  peak %.3e" % (f, int(np.sum(seg == 0)), float(np.max(np.abs(seg)))))

x = Q._tone(30000.0, 96000, 4.0) + Q._tone(1000.0, 96000, 4.0) * 0.5
seg = center(E.resample(x, 96000, 44100, "soxng", E.default_opts("soxng")), 44100)
spec = np.abs(np.fft.rfft(seg)) * 2 / seg.shape[0]
freqs = np.fft.rfftfreq(seg.shape[0], 1 / 44100)
k1 = int(round(1000 * seg.shape[0] / 44100)); kf = int(round(14100 * seg.shape[0] / 44100))
print("   mix: zeros %6d  peak %.3e  1k %.1f dBFS  fold14.1k %.1f dBFS" %
      (int(np.sum(seg == 0)), float(np.max(np.abs(seg))),
       20*np.log10(max(spec[k1], Q.EPS)*2/seg.shape[0]),
       20*np.log10(max(spec[kf], Q.EPS)*2/seg.shape[0])))

print("== B. 输出是不是被量化/截断 ==")
x = Q._tone(1000.0, 96000, 2.0)
seg = center(E.resample(x, 96000, 44100, "soxng", E.default_opts("soxng")), 44100)
print("   passband tone: min |nonzero| = %.3e, peak %.3f, unique vals %d" %
      (float(np.min(np.abs(seg[seg != 0]))), float(np.max(np.abs(seg))), len(np.unique(seg))))

print("== C. 22.05 kHz（真·过渡带）三引擎 ==")
for f in (22050.0, 22100.0, 22500.0, 24000.0):
    x = Q._tone(f, 96000, 4.0)
    row = []
    for key in ("soxng", "dpggb"):
        seg = center(E.resample(x, 96000, 44100, key, E.default_opts(key)), 44100)
        fold = abs(f - round(f / 44100.0) * 44100.0)
        db = 20*np.log10(max(Q._line_level(seg, 44100, fold), Q.EPS) / 0.5)
        row.append("%s %7.1f dB (peak %.2e)" % (key, db, float(np.max(np.abs(seg)))))
    print("   %6.0f Hz : %s" % (f, " | ".join(row)))
