# -*- coding: utf-8 -*-
"""把 spur 与 image 同时推过 PGGB 的最小代价组合。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

SRC, DST, SEC = 44100, 88200, 4.0

def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

def metrics(opts):
    x = Q._tone(1000.0, SRC, SEC)
    s = center(E.resample(x, SRC, DST, "dpggb", opts), DST)
    spur = Q._worst_spur(s, DST, 1000.0)[0]
    ref = max(Q._line_level(s, DST, 1000.0), Q.EPS)
    img = 20 * np.log10(max(Q._line_level(s, DST, SRC - 1000.0), Q.EPS) / ref)
    return spur, img

x60 = np.repeat(Q._tone(1000.0, 44100, 60.0), 2, axis=1)
def speed(opts):
    best = None
    for _ in range(2):
        t0 = time.perf_counter()
        E.resample(x60, 44100, 88200, "dpggb", opts)
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return 60.0 / best

print("target: PGGB spur -323.1  image -335.6")
print("%-30s %8s %8s %8s" % ("config", "spur", "image", "speed"))
cases = [("double ctx400 fade20 (now)", {}),
         ("double ctx800 fade20", {"context": 800.0}),
         ("double ctx800 fade100", {"context": 800.0, "fade": 100.0}),
         ("long   ctx400 fade20", {"prec": "long"}),
         ("long   ctx800 fade20", {"prec": "long", "context": 800.0}),
         ("long   ctx800 fade100", {"prec": "long", "context": 800.0, "fade": 100.0}),
         ("long   ctx1600 fade20", {"prec": "long", "context": 1600.0})]
for name, o in cases:
    sp, im = metrics(o)
    print("%-30s %8.1f %8.1f %8.0f" % (name, sp, im, speed(o)))
