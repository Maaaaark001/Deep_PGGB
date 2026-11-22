# -*- coding: utf-8 -*-
"""速度矩阵：块长 x 上下文，对照 r8brain（同条件 30 s 立体声 44.1->176.4）。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

x = np.repeat(Q._tone(1000.0, 44100, 30.0), 2, axis=1)
print("%-22s %8s %8s %8s" % ("config", "run1", "run2", "best"))
def timeit(key, o):
    best = None
    runs = []
    for _ in range(2):
        t0 = time.perf_counter()
        E.resample(x, 44100, 176400, key, o)
        dt = time.perf_counter() - t0
        runs.append(30.0 / dt)
        best = dt if best is None else min(best, dt)
    return runs, 30.0 / best

for key, name in (("r8b", "r8brain-free"), ("pggb", "PGGB")):
    r, b = timeit(key, E.default_opts(key))
    print("%-22s %8.0f %8.0f %8.0f" % (name, *r, b))
print()
for block in (4.0, 8.0, 16.0, 30.0):
    for ctx in (400.0, 600.0, 800.0):
        o = {"block": block, "context": ctx}
        r, b = timeit("dpggb", o)
        print("%-22s %8.0f %8.0f %8.0f" % ("dpggb b%.0f c%.0f" % (block, ctx), *r, b))
