# -*- coding: utf-8 -*-
"""块长默认 8 s 的全面复核：4 s 激励的指标 + 三个倍率的速度。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

print("== 指标（4 s 激励，块 8 s => 整块处理）==")
for name, key, o in (("dpggb b8", "dpggb", {"block": 8.0}),
                     ("dpggb b8 long", "dpggb", {"block": 8.0, "prec": "long"}),
                     ("pggb", "pggb", None)):
    m = Q.measure_engine(key, o, do_speed=False, do_passband=False)
    print("%-14s spur %8.1f image %8.1f ccif %8.1f smpte %8.1f multi %8.1f" %
          (name, m.spur_dbc, m.image_dbc, m.imd_dbc, m.imd_smpte_dbc, m.mt_dbc))

print()
print("== 速度（30 s 立体声）==")
x = np.repeat(Q._tone(1000.0, 44100, 30.0), 2, axis=1)
def timeit(key, o, src=44100, dst=176400, sec=30.0):
    best = None
    for _ in range(3):
        t0 = time.perf_counter()
        E.resample(x, src, dst, key, o)
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return sec / best
for src, dst in ((44100, 176400), (44100, 96000), (44100, 88200), (96000, 44100)):
    d = timeit("dpggb", {"block": 8.0}, src, dst)
    r = timeit("r8b", E.default_opts("r8b"), src, dst) if src != 96000 or dst != 44100 else None
    print("   %6d -> %6d   dpggb %5.0fx   r8b %5s" % (src, dst, d, ("%.0fx" % r) if r else "n/a"))
