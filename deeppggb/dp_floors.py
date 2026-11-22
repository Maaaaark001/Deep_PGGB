# -*- coding: utf-8 -*-
"""每一项指标的"分析地板"到底在哪？直接合成在目标采样率上，不重采样。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q

DST, SEC = 88200, 4.0

def center(s, n):
    s = np.asarray(s, dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

x = center(Q._tone(1000.0, DST, SEC)[:, 0], DST)
# 杂散地板必须与 measure_engine 同口径（_tone_residual，−307.1），不是 _worst_spur（−323.4）。
print("spur   (analytic 88.2k) %8.1f" % Q._tone_residual(x, DST, [1000.0])[0])
print("       single-bin ref      %8.1f @ %8.0f" % Q._worst_spur(x, DST, 1000.0))
ref = Q._line_level(x, DST, 1000.0)
print("image  @43.1k            %8.1f" %
      (20*np.log10(max(Q._line_level(x, DST, 43100.0), Q.EPS)/ref)))

xi = center(Q._two_tone(*Q.IMD_CCIF, DST, SEC, 0.25, 0.25)[:, 0], DST)
prods = (2*19000-20000, 2*20000-19000, 1000, 39000)
print("CCIF   (analytic 88.2k) %8.1f @ %8.0f" % Q._worst_product(xi, DST, prods, Q.IMD_CCIF))

xm, mtf = Q._multitone(DST, SEC)
xm = center(xm[:, 0], DST)
print("multi  (analytic 88.2k) %8.1f" % Q._tone_residual(xm, DST, mtf)[0])

# 同一批信号用 float128（long double）算 FFT 作为对照地板
print()
print("== 用 longdouble FFT 重算同一批信号（更低的舍入）==")
def worst_spur_ld(s, rate, fund):
    n = s.shape[0]
    spec = np.abs(np.fft.rfft(s.astype(np.longdouble))) * 2.0 / n
    freqs = np.fft.rfftfreq(n, 1.0/rate)
    k = int(round(fund*n/rate))
    keep = np.ones(spec.shape[0], bool); keep[max(0,k-3):k+4] = False; keep[:4] = False
    keep &= (freqs >= 20) & (freqs <= 20000)
    idx = np.flatnonzero(keep)
    j = idx[int(np.argmax(spec[idx]))]
    return float(20*np.log10(float(spec[j])/float(spec[k]))), float(freqs[j])

print("spur   ld-fft            %8.1f @ %8.0f" % worst_spur_ld(x, DST, 1000.0))
