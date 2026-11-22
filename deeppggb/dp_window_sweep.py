# -*- coding: utf-8 -*-
"""单窗测量是否正好压在块接缝上？扫窗位置看 SMPTE 的分布。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

D = 88200
def windows(n, k=5):
    w = D
    return [int((i + 0.5) * (n - w) / k) + 0 for i in range(k)]

def smpte_at(seg):
    f2s = Q.IMD_SMPTE[1]
    prods = [f2s + i * 60 for i in (-2, -1, 1, 2)]
    return Q._worst_product(seg, D, prods, f2s)[0]

sec = 16.0
xs = Q._two_tone(*Q.IMD_SMPTE, 44100, sec, 0.40, 0.10)
for key, o in (("dpggb", {"block": 4.0}), ("dpggb", {"block": 8.0}),
               ("dpggb", {"block": 16.0}), ("pggb", None)):
    y = np.asarray(E.resample(xs, 44100, D, key, o)[:, 0], dtype=np.float64)
    vals = [smpte_at(y[st:st + D]) for st in windows(y.shape[0])]
    vals_sorted = sorted(vals)
    med = vals_sorted[len(vals) // 2]
    print("%-18s median %8.1f  all %s" %
          ("%s b%s" % (key, o["block"] if o else "whole"), med,
           " ".join("%.0f" % v for v in vals)))
