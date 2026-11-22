# -*- coding: utf-8 -*-
"""给两个新口径定地板：
A) 混叠 = 通带参考音 + 阻带侵略音，测折叠 bin 相对参考音；
B) 镜像 = 22.05-44.1 kHz 频带总能量相对音能量（不是单 bin）。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

def band_energy_db(s, rate, lo, hi, ref):
    n = s.shape[0]
    spec = np.abs(np.fft.rfft(s)) ** 2
    f = np.fft.rfftfreq(n, 1.0 / rate)
    m = (f >= lo) & (f <= hi)
    e = float(np.sum(spec[m])) * 2.0 / (n * n)
    return 10 * np.log10(max(e, 1e-300) / (ref ** 2 / 2))

print("== A. 混叠口径：地板 = 只有 1 kHz 时 14.1 kHz bin 的裙边 ==")
SRC, DST = 96000, 44100
for f_ref in (1000.0,):
    x = Q._tone(f_ref, DST, 4.0, 0.5)
    s = center(x, DST)
    ref = max(Q._line_level(s, DST, f_ref), Q.EPS)
    print("   analytic 44.1k, 1 kHz only -> 14.1k bin %8.1f dBc" %
          (20*np.log10(max(Q._line_level(s, DST, 14100.0), Q.EPS)/ref)))

print()
print("== B. 镜像口径：地板 = 解析 88.2k 单音在 22.05-44.1k 的带能量 ==")
DST2 = 88200
x = Q._tone(1000.0, DST2, 4.0, 0.5)
s = center(x, DST2)
ref = 0.5
print("   analytic 88.2k 1 kHz -> image band %8.1f dBc" % band_energy_db(s, DST2, 22050.0, 44100.0, ref))
for key, o in (("dpggb", None), ("dpggb", {"prec": "long"}), ("pggb", None)):
    x = Q._tone(1000.0, 44100, 4.0, 0.5)
    s = center(E.resample(x, 44100, DST2, key, o), DST2)
    print("   %-6s %-5s -> image band %8.1f dBc" % (key, "long" if o else "dflt",
                                                    band_energy_db(s, DST2, 22050.0, 44100.0, ref)))

print()
print("== C. 新混叠口径下八引擎（96->44.1，1 kHz@0.5 + 30 kHz@0.5）==")
x = Q._tone(1000.0, SRC, 4.0, 0.5) + Q._tone(30000.0, SRC, 4.0, 0.5)
for key in ("dpggb", "r8b", "soxng", "soxr", "swr", "ssrc", "scipy"):
    s = center(E.resample(x, SRC, DST, key, E.default_opts(key)), DST)
    ref = max(Q._line_level(s, DST, 1000.0), Q.EPS)
    a = 20*np.log10(max(Q._line_level(s, DST, 14100.0), Q.EPS)/ref)
    print("   %-6s %8.1f dBc" % (key, a))
