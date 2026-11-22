# -*- coding: utf-8 -*-
"""修正口径后的八引擎表：宽排除带杂散 / 带能量镜像 / 双音混叠。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

def spur_wide(s, rate, fund, half_hz=50.0):
    n = s.shape[0]
    spec = np.abs(np.fft.rfft(s)) * 2.0 / n
    f = np.fft.rfftfreq(n, 1.0 / rate)
    k = int(round(fund * n / rate))
    half = max(3, int(round(half_hz * n / rate)))
    keep = np.ones(spec.shape[0], bool)
    keep[max(0, k - half): k + half + 1] = False
    keep[:4] = False
    keep &= (f >= 20) & (f <= 20000)
    idx = np.flatnonzero(keep)
    j = idx[int(np.argmax(spec[idx]))]
    ref = max(Q._line_level(s, rate, fund), Q.EPS)
    return 20 * np.log10(max(spec[j], Q.EPS) / ref), float(f[j])

def image_band(s, rate, fund, lo, hi):
    n = s.shape[0]
    spec = np.abs(np.fft.rfft(s)) ** 2
    f = np.fft.rfftfreq(n, 1.0 / rate)
    m = (f >= lo) & (f <= hi)
    e = float(np.sum(spec[m])) * 2.0 / (n * n)
    ref = max(Q._line_level(s, rate, fund), Q.EPS)
    return 10 * np.log10(max(e, 1e-300) / (ref ** 2 / 2))

UP_SRC, UP_DST = 44100, 88200
DN_SRC, DN_DST = 96000, 44100
FOLD = 14100.0

print("%-8s %9s %9s %9s %9s" % ("engine", "spur", "image", "alias", "multi"))
for key in ("dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"):
    spec = E.ENGINES.get(key)
    o = E.default_opts(key)
    int_only = bool(getattr(spec, "integer_only", False))
    try:
        x = Q._tone(1000.0, UP_SRC, 4.0)
        s = center(E.resample(x, UP_SRC, UP_DST, key, o), UP_DST)
        sp, _ = spur_wide(s, UP_DST, 1000.0)
        im = image_band(s, UP_DST, 1000.0, 22050.0, 44100.0)

        if int_only:
            al = float("nan")
        else:
            xa = Q._tone(1000.0, DN_SRC, 4.0, 0.5) + Q._tone(30000.0, DN_SRC, 4.0, 0.5)
            sa = center(E.resample(xa, DN_SRC, DN_DST, key, o), DN_DST)
            refa = max(Q._line_level(sa, DN_DST, 1000.0), Q.EPS)
            al = 20 * np.log10(max(Q._line_level(sa, DN_DST, FOLD), Q.EPS) / refa)

        xm, mtf = Q._multitone(UP_SRC, 4.0)
        sm = center(E.resample(xm, UP_SRC, UP_DST, key, o), UP_DST)
        mt = Q._tone_residual(sm, UP_DST, mtf)[0]
        print("%-8s %9.1f %9.1f %9s %9.1f" %
              (key, sp, im, ("n/a" if int_only else "%9.1f" % al), mt))
    except Exception as e:
        print("%-8s ERR %s" % (key, str(e)[:60]))

print()
print("== 地板（解析合成，不重采样）==")
s = center(Q._tone(1000.0, UP_DST, 4.0), UP_DST)
print("   spur  %8.1f" % spur_wide(s, UP_DST, 1000.0)[0])
print("   image %8.1f" % image_band(s, UP_DST, 1000.0, 22050.0, 44100.0))
sa = center(Q._tone(1000.0, DN_DST, 4.0, 0.5) + Q._tone(FOLD, DN_DST, 4.0, 0.5), DN_DST)
refa = max(Q._line_level(sa, DN_DST, 1000.0), Q.EPS)
print("   alias %8.1f" % (20 * np.log10(max(Q._line_level(sa, DN_DST, FOLD), Q.EPS) / refa)))
xm, mtf = Q._multitone(UP_DST, 4.0)
print("   multi %8.1f" % Q._tone_residual(center(xm, UP_DST), UP_DST, mtf)[0])
