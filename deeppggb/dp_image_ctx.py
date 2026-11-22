# -*- coding: utf-8 -*-
"""镜像项对 context / precision 的依赖，重复两次确认可复现。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

SRC, DST = 44100, 88200
def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

def image(opts):
    x = Q._tone(1000.0, SRC, 4.0)
    s = center(E.resample(x, SRC, DST, "dpggb", opts), DST)
    ref = max(Q._line_level(s, DST, 1000.0), Q.EPS)
    return 20 * np.log10(max(Q._line_level(s, DST, SRC - 1000.0), Q.EPS) / ref)

print("%-28s %8s %8s" % ("config", "run1", "run2"))
for ctx in (400.0, 800.0, 1600.0, 3200.0):
    for prec in ("double", "long"):
        a = image({"context": ctx, "prec": prec})
        b = image({"context": ctx, "prec": prec})
        print("%-28s %8.1f %8.1f" % ("%s ctx=%.0f" % (prec, ctx), a, b))
