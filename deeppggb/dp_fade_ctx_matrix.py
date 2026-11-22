# -*- coding: utf-8 -*-
"""双精度下，fade / context / taper 对 spur 与 image 的影响，找能同时压过 PGGB 的组合。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

SRC, DST = 44100, 88200
def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

def metrics(o):
    x = Q._tone(1000.0, SRC, 4.0)
    s = center(E.resample(x, SRC, DST, "dpggb", o), DST)
    sp = Q._worst_spur(s, DST, 1000.0)[0]
    ref = max(Q._line_level(s, DST, 1000.0), Q.EPS)
    im = 20*np.log10(max(Q._line_level(s, DST, SRC - 1000.0), Q.EPS)/ref)
    resid = Q._tone_residual(s, DST, [1000.0])[0]
    return sp, im, resid

x60 = np.repeat(Q._tone(1000.0, 44100, 30.0), 2, axis=1)
def speed(o):
    best = None
    for _ in range(2):
        t0 = time.perf_counter(); E.resample(x60, 44100, 88200, "dpggb", o)
        dt = time.perf_counter()-t0; best = dt if best is None else min(best, dt)
    return 30.0/best

print("PGGB target: spur -323.1  image -335.6  resid -306.1   (floor: -323.4 / -321.0 / -307.1)")
print("%-26s %8s %8s %8s %6s" % ("config", "spur", "image", "resid", "x"))
for fade in (20.0, 50.0, 100.0, 200.0):
    for ctx in (400.0, 800.0):
        o = {"fade": fade, "context": ctx}
        sp, im, rs = metrics(o)
        print("%-26s %8.1f %8.1f %8.1f %6.0f" % ("fade%.0f ctx%.0f" % (fade, ctx), sp, im, rs, speed(o)))
for taper in ("smooth6", "smooth4"):
    o = {"fade": 100.0, "context": 800.0, "taper": taper}
    sp, im, rs = metrics(o)
    print("%-26s %8.1f %8.1f %8.1f %6.0f" % ("fade100 ctx800 " + taper, sp, im, rs, speed(o)))
