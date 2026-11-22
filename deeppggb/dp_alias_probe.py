# -*- coding: utf-8 -*-
"""sox_ng 的 -394 dBc 混叠到底是真的还是"清零"？同条件解剖。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

SRC, DST = 96000, 44100
x = Q._tone(30000.0, SRC, 4.0)
print("输入峰值 %.6f" % float(np.max(np.abs(x))))
for key in ("soxng", "dpggb", "pggb", "r8b", "soxr", "swr", "ssrc", "scipy"):
    spec = E.ENGINES.get(key)
    if spec is not None and getattr(spec, "integer_only", False):
        print("  %-6s  integer-only, skipped" % key); continue
    try:
        y = E.resample(x, SRC, DST, key, E.default_opts(key))
    except Exception as e:
        print("  %-6s  ERR %s" % (key, str(e)[:60])); continue
    seg = np.asarray(y[:, 0], dtype=np.float64)
    st = (seg.shape[0] - 44100) // 2
    seg = seg[st:st + 44100]
    zeros = int(np.sum(seg == 0.0))
    peak = float(np.max(np.abs(seg)))
    rms = float(np.sqrt(np.mean(seg ** 2)))
    fold = abs(30000.0 - round(30000.0 / 44100.0) * 44100.0)
    lvl = Q._line_level(seg, 44100, fold)
    db = 20 * np.log10(max(lvl, Q.EPS) / 0.5)
    print("  %-6s zeros %6d/%d  peak %.3e  rms %.3e  fold %8.1f dBc" %
          (key, zeros, seg.shape[0], peak, rms, db))
