# -*- coding: utf-8 -*-
"""同条件（44.1 -> 88.2, x2）下 Deep_PGGB 与 PGGB 的逐项对照。

论文 6.3(6) 声称两者在 44.1->88.2 上不可区分，这个脚本就是那个断言的证据。
必须两边都用同一套激励（整数相位）、同一个居中分析窗。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

SRC, DST = 44100, 88200
SEC = 4.0

def seg_center(y, n):
    y = np.asarray(y[:, 0], dtype=np.float64)
    if y.shape[0] < n:
        raise RuntimeError("out too short %d < %d" % (y.shape[0], n))
    st = (y.shape[0] - n) // 2
    return y[st:st + n]

rows = {}
for key in ("dpggb", "pggb"):
    o = E.default_opts(key)
    r = {}
    x = Q._tone(1000.0, SRC, SEC)
    s = seg_center(E.resample(x, SRC, DST, key, o), DST)
    r["spur"], r["spur_hz"] = Q._worst_spur(s, DST, 1000.0)

    s = seg_center(E.resample(x, SRC, DST, key, o), DST)
    ref = max(Q._line_level(s, DST, 1000.0), Q.EPS)
    r["image"] = 20 * np.log10(max(Q._line_level(s, DST, SRC - 1000.0), Q.EPS) / ref)

    xi = Q._two_tone(*Q.IMD_CCIF, SRC, SEC, 0.25, 0.25)
    s = seg_center(E.resample(xi, SRC, DST, key, o), DST)
    prods = (2*Q.IMD_CCIF[0]-Q.IMD_CCIF[1], 2*Q.IMD_CCIF[1]-Q.IMD_CCIF[0],
             Q.IMD_CCIF[1]-Q.IMD_CCIF[0], sum(Q.IMD_CCIF))
    r["ccif"], _ = Q._worst_product(s, DST, prods, Q.IMD_CCIF)

    xm, mtf = Q._multitone(SRC, SEC)
    s = seg_center(E.resample(xm, SRC, DST, key, o), DST)
    r["mt"], _ = Q._tone_residual(s, DST, mtf)
    rows[key] = r

print("%-6s %9s %9s %9s %9s" % ("engine", "spur", "image", "CCIF", "multi"))
for k, r in rows.items():
    print("%-6s %9.1f %9.1f %9.1f %9.1f" % (k, r["spur"], r["image"], r["ccif"], r["mt"]))
d = {k: rows["dpggb"][k] - rows["pggb"][k] for k in rows["dpggb"]}
print("delta  " + " ".join("%+.1f" % d[k] for k in ("spur", "image", "ccif", "mt")))
