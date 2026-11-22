# -*- coding: utf-8 -*-
"""最终表：16 s 激励、5 窗中位数、块 8 s；dpggb 给出 double 与 long 两行。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

ROWS = [("dpggb", "Deep_PGGB (double)", {"block": 8.0}),
        ("dpggb", "Deep_PGGB (long)", {"block": 8.0, "prec": "long"}),
        ("pggb", "PGGB", None),
        ("r8b", "r8brain-free", None),
        ("soxng", "sox_ng rate", None),
        ("swr", "FFmpeg aresample", None),
        ("soxr", "libsoxr", None),
        ("ssrc", "SSRC / Shibatch", None),
        ("scipy", "SciPy resample_poly", None)]

print("%-22s %8s %8s %8s %8s %8s %8s" % ("engine", "spur", "image", "alias", "ccif", "smpte", "multi"))
for key, label, extra in ROWS:
    o = dict(E.default_opts(key))
    if extra:
        o.update(extra)
    m = Q.measure_engine(key, o, seconds=16.0, do_speed=False, do_passband=False)
    print("%-22s %8.1f %8.1f %8s %8.1f %8.1f %8.1f" %
          (label, m.spur_dbc, m.image_dbc, ("n/a" if m.alias_na else "%8.1f" % m.alias_dbc),
           m.imd_dbc, m.imd_smpte_dbc, m.mt_dbc))
