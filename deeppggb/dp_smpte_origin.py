# -*- coding: utf-8 -*-
"""7 kHz ± 60/120 的边带从哪来：分块接缝？还是 60 Hz 与 7 kHz 的真互调？"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

def spectrum_peaks(s, rate, ref, lo, hi, k=6):
    n = s.shape[0]
    spec = np.abs(np.fft.rfft(s)) * 2.0 / n
    f = np.fft.rfftfreq(n, 1.0 / rate)
    band = (f >= lo) & (f <= hi)
    idx = np.flatnonzero(band)
    top = idx[np.argsort(spec[idx])[-k:]][::-1]
    return [(round(float(f[i]), 1), round(float(20*np.log10(max(spec[i], Q.EPS)/ref)), 1)) for i in top]

print("== 不同块长下的 SMPTE（16 s 激励）==")
for o in ({"block": 4.0}, {"block": 16.0}, {"block": 30.0}):
    m = Q.measure_engine("dpggb", o, seconds=16.0, do_speed=False, do_passband=False)
    print("   block %-5.0f smpte %8.1f  ccif %8.1f" % (o["block"], m.imd_smpte_dbc, m.imd_dbc))

print()
print("== 只有 7 kHz（无 60 Hz）时的边带 ==")
x = Q._tone(7000.0, 44100, 16.0, 0.10)
y = center(E.resample(x, 44100, 88200, "dpggb", None), 88200)
ref = Q._line_level(y, 88200, 7000.0)
print("   dpggb", spectrum_peaks(y, 88200, ref, 6800.0, 7200.0, 5))
y = center(E.resample(x, 44100, 88200, "pggb", None), 88200)
ref = Q._line_level(y, 88200, 7000.0)
print("   pggb  ", spectrum_peaks(y, 88200, ref, 6800.0, 7200.0, 5))

print()
print("== SMPTE 双音时的边带 ==")
xs = Q._two_tone(*Q.IMD_SMPTE, 44100, 16.0, 0.40, 0.10)
for k in ("dpggb", "pggb"):
    y = center(E.resample(xs, 44100, 88200, k, E.default_opts(k)), 88200)
    ref = Q._line_level(y, 88200, 7000.0)
    print("   %-5s %s" % (k, spectrum_peaks(y, 88200, ref, 6800.0, 7200.0, 6)))
