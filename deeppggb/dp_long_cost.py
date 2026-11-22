# -*- coding: utf-8 -*-
"""long double 的代价，以及 sox_ng 全零输出是不是普遍现象。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

print("== prec double vs long：60 s 立体声 44.1->96 ==")
x = Q._tone(1000.0, 44100, 60.0)
x = np.repeat(x, 2, axis=1)
for prec in ("double", "long"):
    best = None
    for _ in range(2):
        t0 = time.perf_counter()
        E.resample(x, 44100, 96000, "dpggb", {"prec": prec})
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    print("   prec=%-7s %.2f s  %.0fx" % (prec, best, 60.0 / best))

print("== sox_ng 全零输出是否普遍 ==")
for src, dst, f in ((96000, 44100, 30000.0), (96000, 44100, 35000.0),
                    (96000, 48000, 30000.0), (192000, 44100, 60000.0)):
    xx = Q._tone(f, src, 4.0)
    y = E.resample(xx, src, dst, "soxng", E.default_opts("soxng"))
    seg = np.asarray(y[:, 0], dtype=np.float64)
    st = (seg.shape[0] - dst) // 2
    seg = seg[st:st + dst]
    print("   %d->%d @%6.0f Hz  zeros %6d/%d  peak %.3e" %
          (src, dst, f, int(np.sum(seg == 0.0)), seg.shape[0], float(np.max(np.abs(seg)))))

print("== dpggb 同条件 ==")
for src, dst, f in ((96000, 44100, 30000.0), (96000, 44100, 35000.0)):
    xx = Q._tone(f, src, 4.0)
    y = E.resample(xx, src, dst, "dpggb", None)
    seg = np.asarray(y[:, 0], dtype=np.float64)
    st = (seg.shape[0] - dst) // 2
    seg = seg[st:st + dst]
    print("   %d->%d @%6.0f Hz  zeros %6d/%d  peak %.3e" %
          (src, dst, f, int(np.sum(seg == 0.0)), seg.shape[0], float(np.max(np.abs(seg)))))
