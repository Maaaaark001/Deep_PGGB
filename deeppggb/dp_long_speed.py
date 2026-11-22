# -*- coding: utf-8 -*-
"""long 精度的速度代价：能不能仍然快过 r8brain？"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

x = np.repeat(Q._tone(1000.0, 44100, 30.0), 2, axis=1)
def t(key, o, reps=3):
    best = None
    for _ in range(reps):
        t0 = time.perf_counter(); E.resample(x, 44100, 176400, key, o)
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return 30.0 / best

print("r8brain %5.0fx   PGGB %5.0fx" % (t("r8b", E.default_opts("r8b")), t("pggb", E.default_opts("pggb"))))
for prec in ("double", "long"):
    for block in (4.0, 8.0, 16.0):
        for ctx in (600.0, 800.0):
            o = {"prec": prec, "block": block, "context": ctx}
            print("%-6s block %-4.0f ctx %-4.0f -> %5.0fx" % (prec, block, ctx, t("dpggb", o, 2)))
