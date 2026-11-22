# -*- coding: utf-8 -*-
"""taper 阶数 C5 vs C6 vs C4：四个指标 + 零差，4 s 与 16 s。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

def prod(seg, rate=88200):
    f2s = Q.IMD_SMPTE[1]
    return Q._worst_product(seg, rate, [f2s + i * 60 for i in (-2, -1, 1, 2)], f2s)[0]

def run(x, key, o, sec):
    y = np.asarray(E.resample(x, 44100, 88200, key, o)[:, 0], dtype=np.float64)
    st = (y.shape[0] - 88200) // 2
    return prod(y[st:st + 88200])

print("%-22s %8s %8s" % ("config", "smpte4s", "smpte16s"))
xs4 = Q._two_tone(*Q.IMD_SMPTE, 44100, 4.0, 0.40, 0.10)
xs16 = Q._two_tone(*Q.IMD_SMPTE, 44100, 16.0, 0.40, 0.10)
for name, o in (("C5 (now)", {"block": 8.0}),
                ("C6", {"block": 8.0, "taper": "smooth6"}),
                ("C4", {"block": 8.0, "taper": "smooth4"}),
                ("C6 long", {"block": 8.0, "taper": "smooth6", "prec": "long"})):
    print("%-22s %8.1f %8.1f" % (name, run(xs4, "dpggb", o, 4.0), run(xs16, "dpggb", o, 16.0)))
print("%-22s %8.1f %8.1f" % ("pggb", run(xs4, "pggb", None, 4.0), run(xs16, "pggb", None, 16.0)))

print()
print("%-22s %8s %8s %8s %8s" % ("config", "spur", "image", "ccif", "multi"))
for name, o in (("C5 (now)", {"block": 8.0}), ("C6", {"block": 8.0, "taper": "smooth6"})):
    m = Q.measure_engine("dpggb", o, do_speed=False, do_passband=False)
    print("%-22s %8.1f %8.1f %8.1f %8.1f" % (name, m.spur_dbc, m.image_dbc,
                                              m.imd_dbc, m.mt_dbc))
m = Q.measure_engine("pggb", None, do_speed=False, do_passband=False)
print("%-22s %8.1f %8.1f %8.1f %8.1f" % ("pggb", m.spur_dbc, m.image_dbc, m.imd_dbc, m.mt_dbc))
