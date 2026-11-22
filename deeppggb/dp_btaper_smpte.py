# -*- coding: utf-8 -*-
"""SMPTE 的边带是不是块边缘渐变的调制边带？扫 btaper 与 context。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality as Q

print("%-20s %9s %9s %9s" % ("config", "smpte", "ccif", "spur"))
for bt in (2.0, 5.0, 10.0, 20.0, 50.0):
    for ctx in (400.0, 800.0):
        m = Q.measure_engine("dpggb", {"btaper": bt, "context": ctx}, seconds=16.0,
                             do_speed=False, do_passband=False)
        print("%-20s %9.1f %9.1f %9.1f" % ("bt%.0f ctx%.0f" % (bt, ctx),
                                           m.imd_smpte_dbc, m.imd_dbc, m.spur_dbc))
print()
print("参考：单块（block 16）smpte -335.0 / ccif -332.9；PGGB smpte -336.2 / ccif -333.4")
