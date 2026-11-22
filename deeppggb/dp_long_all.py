# -*- coding: utf-8 -*-
"""prec=long 是否把所有指标都推到地板？与 PGGB 同条件对照。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

SRC, DST, SEC = 44100, 88200, 4.0

def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

def run(key, opts):
    r = {}
    x = Q._tone(1000.0, SRC, SEC)
    seg = center(E.resample(x, SRC, DST, key, opts), DST)
    r["spur"] = Q._worst_spur(seg, DST, 1000.0)[0]
    ref = max(Q._line_level(seg, DST, 1000.0), Q.EPS)
    r["image"] = 20 * np.log10(max(Q._line_level(seg, DST, SRC - 1000.0), Q.EPS) / ref)
    xi = Q._two_tone(*Q.IMD_CCIF, SRC, SEC, 0.25, 0.25)
    seg = center(E.resample(xi, SRC, DST, key, opts), DST)
    prods = (2*19000-20000, 2*20000-19000, 1000, 39000)
    r["ccif"] = Q._worst_product(seg, DST, prods, Q.IMD_CCIF)[0]
    xm, mtf = Q._multitone(SRC, SEC)
    seg = center(E.resample(xm, SRC, DST, key, opts), DST)
    r["mt"] = Q._tone_residual(seg, DST, mtf)[0]
    return r

print("%-18s %8s %8s %8s %8s" % ("config", "spur", "image", "CCIF", "multi"))
for name, key, opts in (("dpggb double", "dpggb", None),
                        ("dpggb long", "dpggb", {"prec": "long"}),
                        ("pggb", "pggb", None)):
    r = run(key, opts)
    print("%-18s %8.1f %8.1f %8.1f %8.1f" % (name, r["spur"], r["image"], r["ccif"], r["mt"]))

print()
print("== 速度（60 s 立体声 44.1->88.2）==")
x = np.repeat(Q._tone(1000.0, 44100, 60.0), 2, axis=1)
for name, key, opts in (("dpggb double", "dpggb", None),
                        ("dpggb long", "dpggb", {"prec": "long"}),
                        ("pggb", "pggb", None)):
    best = None
    for _ in range(2):
        t0 = time.perf_counter()
        E.resample(x, 44100, 88200, key, opts)
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    print("   %-14s %.2f s  %.0fx" % (name, best, 60.0 / best))
