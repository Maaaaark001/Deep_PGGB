# -*- coding: utf-8 -*-
"""大块 + FFTW 线程：能不能既有整块精度（无接缝）又有 r8brain 级速度？"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

x = np.repeat(Q._tone(1000.0, 44100, 30.0), 2, axis=1)
def timeit(key, o, reps=3):
    best = None
    for _ in range(reps):
        t0 = time.perf_counter()
        E.resample(x, 44100, 176400, key, o)
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return 30.0 / best

print("r8brain-free %6.0fx   PGGB %6.0fx" % (timeit("r8b", E.default_opts("r8b")),
                                             timeit("pggb", E.default_opts("pggb"))))
print()
for block in (4.0, 8.0, 16.0, 30.0):
    for th in (0, 2, 4, 8):
        o = {"block": block, "context": 800.0, "threads": th}
        print("block %-4.0f threads %-2d -> %6.0fx" % (block, th, timeit("dpggb", o)))
