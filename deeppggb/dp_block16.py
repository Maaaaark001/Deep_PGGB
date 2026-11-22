# -*- coding: utf-8 -*-
"""块 16 s：16 s 文件即整块（无接缝）。指标 + 60 s 速度。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

for prec in ("double", "long"):
    m = Q.measure_engine("dpggb", {"block": 16.0, "prec": prec}, seconds=16.0,
                         do_speed=False, do_passband=False)
    print("dpggb %-6s block16  spur %8.1f image %8.1f alias %8.1f ccif %8.1f smpte %8.1f multi %8.1f" %
          (prec, m.spur_dbc, m.image_dbc, m.alias_dbc, m.imd_dbc, m.imd_smpte_dbc, m.mt_dbc))

x = np.repeat(Q._tone(1000.0, 44100, 60.0), 2, axis=1)
def t(key, o, sec, reps=2):
    best = None
    for _ in range(reps):
        t0 = time.perf_counter(); E.resample(x, 44100, 176400, key, o)
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return sec / best
print()
print("60 s 立体声 44.1->176.4: r8b %5.0fx  pggb %5.0fx" % (t("r8b", E.default_opts("r8b"), 60.0),
                                                           t("pggb", E.default_opts("pggb"), 60.0)))
for block in (8.0, 16.0):
    for prec in ("double", "long"):
        print("   dpggb %-6s block %-4.0f -> %5.0fx" %
              (prec, block, t("dpggb", {"block": block, "prec": prec}, 60.0)))
