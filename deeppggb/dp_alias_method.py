# -*- coding: utf-8 -*-
"""混叠测量的正确口径：通带参考音 + 阻带侵略音，产物相对参考音。

现有 measure_engine 只放一个阻带音，于是"混叠抑制"变成 0/0 —— sox_ng 的输出
是逐位精确的 0，读数直接落到 EPS=1e-20 上，给出 −394 dBc 的假成绩。
标准做法（AES17 / InfiniteWave）是通带音在场时测折叠产物。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

SRC, DST, SEC = 96000, 44100, 4.0
REF_F, AGG_F = 1000.0, 30000.0        # 30 kHz 折到 44100-30000 = 14100
FOLD = abs(AGG_F - round(AGG_F / DST) * DST)

def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

x = Q._tone(REF_F, SRC, SEC, 0.5) + Q._tone(AGG_F, SRC, SEC, 0.5)
print("ref %.0f Hz @0.5 + aggressor %.0f Hz @0.5  -> fold %.0f Hz" % (REF_F, AGG_F, FOLD))
print("%-6s %10s %10s %10s" % ("engine", "alias dBc", "alias dBFS", "zeros"))
for key in ("soxng", "dpggb", "r8b", "soxr", "swr", "ssrc", "scipy"):
    try:
        y = E.resample(x, SRC, DST, key, E.default_opts(key))
    except Exception as e:
        print("%-6s ERR %s" % (key, str(e)[:50])); continue
    seg = center(y, DST)
    ref = max(Q._line_level(seg, DST, REF_F), Q.EPS)
    fold = Q._line_level(seg, DST, FOLD)
    print("%-6s %10.1f %10.1f %10d" %
          (key, 20*np.log10(max(fold, Q.EPS)/ref), 20*np.log10(max(fold, Q.EPS)), int(np.sum(seg == 0))))

print()
print("== 分析地板：把同一对音直接合成在 44.1 kHz 上（不重采样）==")
xs = Q._tone(REF_F, DST, SEC, 0.5) + Q._tone(FOLD, DST, SEC, 0.5)
seg = center(xs, DST)
ref = max(Q._line_level(seg, DST, REF_F), Q.EPS)
print("   floor: %8.1f dBc" % (20*np.log10(max(Q._line_level(seg, DST, FOLD), Q.EPS)/ref)))

print()
print("== 只有侵略音（现口径）vs 双音（新口径）==")
xa = Q._tone(AGG_F, SRC, SEC, 0.5)
for key in ("soxng", "dpggb", "r8b"):
    seg = center(E.resample(xa, SRC, DST, key, E.default_opts(key)), DST)
    old = 20*np.log10(max(Q._line_level(seg, DST, FOLD), Q.EPS)/0.5)
    seg2 = center(E.resample(x, SRC, DST, key, E.default_opts(key)), DST)
    ref2 = max(Q._line_level(seg2, DST, REF_F), Q.EPS)
    new = 20*np.log10(max(Q._line_level(seg2, DST, FOLD), Q.EPS)/ref2)
    print("   %-6s 单音 %8.1f dBc   双音 %8.1f dBc   差 %+6.1f dB" % (key, old, new, new-old))
