# -*- coding: utf-8 -*-
"""最终口径：16 s 激励 + 5 窗中位数 / 每台引擎用各自最高质量档。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

BEST = {"dpggb": {"prec": "long"}}
keys = ["dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"]
print("%-7s %8s %8s %8s %8s %8s %8s" % ("engine", "spur", "image", "alias", "ccif", "smpte", "multi"))
for k in keys:
    o = dict(E.default_opts(k))
    o.update(BEST.get(k, {}))
    m = Q.measure_engine(k, o, seconds=16.0, do_speed=False, do_passband=False)
    print("%-7s %8.1f %8.1f %8s %8.1f %8.1f %8.1f" %
          (k, m.spur_dbc, m.image_dbc, ("n/a" if m.alias_na else "%8.1f" % m.alias_dbc),
           m.imd_dbc, m.imd_smpte_dbc, m.mt_dbc))
