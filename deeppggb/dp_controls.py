# -*- coding: utf-8 -*-
"""两个判别实验：
A) 单音杂散是不是被"窗泄漏"污染？扫排除宽度。
B) sox_ng 的混叠读数是不是 0/0？加通带参考音后重测。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

print("== A. 单音杂散 vs 排除宽度（44.1->88.2, 1 kHz, 4 s, 1 s 窗）==")
print("%-16s %8s %8s %8s %8s %8s" % ("config", "±3", "±10", "±50", "±200", "worst Hz"))
SRC, DST = 44100, 88200
for key, opts in (("dpggb", None), ("dpggb", {"prec": "long"}), ("pggb", None)):
    x = Q._tone(1000.0, SRC, 4.0)
    s = center(E.resample(x, SRC, DST, key, opts), DST)
    n = s.shape[0]
    spec = np.abs(np.fft.rfft(s)) * 2.0 / n
    freqs = np.fft.rfftfreq(n, 1.0 / DST)
    k = int(round(1000.0 * n / DST))
    ref = max(Q._line_level(s, DST, 1000.0), Q.EPS)
    row = []
    hz = 0.0
    for half in (3, 10, 50, 200):
        keep = np.ones(spec.shape[0], bool)
        keep[max(0, k - half): k + half + 1] = False
        keep[:4] = False
        keep &= (freqs >= 20) & (freqs <= 20000)
        idx = np.flatnonzero(keep)
        j = idx[int(np.argmax(spec[idx]))]
        row.append(20 * np.log10(max(spec[j], Q.EPS) / ref))
        hz = freqs[j]
    print("%-16s %8.1f %8.1f %8.1f %8.1f %8.0f" %
          ("%s %s" % (key, "long" if opts else "dflt"), *row, hz))

print()
print("== B. 混叠：只有通带音 / 只有阻带音 / 双音（96->44.1，折到 14.1 kHz）==")
SRC, DST = 96000, 44100
FOLD = 14100.0
def alias_of(x, key):
    s = center(E.resample(x, SRC, DST, key, E.default_opts(key)), DST)
    ref = max(Q._line_level(s, DST, 1000.0), Q.EPS)
    return 20 * np.log10(max(Q._line_level(s, DST, FOLD), Q.EPS) / ref), int(np.sum(s == 0))

x_ref = Q._tone(1000.0, SRC, 4.0, 0.5)
x_agg = Q._tone(30000.0, SRC, 4.0, 0.5)
x_both = x_ref + x_agg
print("%-8s %14s %14s %14s" % ("engine", "ref only", "aggr only", "both"))
for key in ("soxng", "dpggb", "r8b", "soxr"):
    a, z1 = alias_of(x_ref, key)
    b, z2 = alias_of(x_agg, key)
    c, z3 = alias_of(x_both, key)
    print("%-8s %10.1f dBc %10.1f dBc %10.1f dBc  (zeros %d/%d/%d)" %
          (key, a, b, c, z1, z2, z3))
