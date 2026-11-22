# -*- coding: utf-8 -*-
"""指标随激励长度的变化：4 s 是不是把边界渐变的代价放大了？"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

print("%-6s %6s %9s %9s %9s %9s %9s" % ("engine", "sec", "spur", "image", "ccif", "smpte", "multi"))
for sec in (4.0, 8.0, 16.0, 30.0):
    for key, o in (("dpggb", None), ("pggb", None)):
        m = Q.measure_engine(key, o, seconds=sec, do_speed=False, do_passband=False)
        print("%-6s %6.0f %9.1f %9.1f %9.1f %9.1f %9.1f" %
              (key, sec, m.spur_dbc, m.image_dbc, m.imd_dbc, m.imd_smpte_dbc, m.mt_dbc))
    print()
