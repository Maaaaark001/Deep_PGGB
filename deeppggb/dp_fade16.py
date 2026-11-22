# -*- coding: utf-8 -*-
"""16 s 激励下 fade / context 的全指标矩阵：SMPTE 的 20 dB 到底是渐变边带还是引擎失真？"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality as Q

print("%-18s %9s %9s %9s %9s %9s" % ("config", "spur", "image", "ccif", "smpte", "multi"))
for fade in (20.0, 50.0, 100.0, 200.0):
    for ctx in (400.0, 800.0):
        m = Q.measure_engine("dpggb", {"fade": fade, "context": ctx}, seconds=16.0,
                             do_speed=False, do_passband=False)
        print("%-18s %9.1f %9.1f %9.1f %9.1f %9.1f" %
              ("fade%.0f ctx%.0f" % (fade, ctx), m.spur_dbc, m.image_dbc,
               m.imd_dbc, m.imd_smpte_dbc, m.mt_dbc))
m = Q.measure_engine("dpggb", {"fade": 0.0, "context": 800.0}, seconds=16.0,
                     do_speed=False, do_passband=False)
print("%-18s %9.1f %9.1f %9.1f %9.1f %9.1f" %
      ("fade0 ctx800", m.spur_dbc, m.image_dbc, m.imd_dbc, m.imd_smpte_dbc, m.mt_dbc))
m = Q.measure_engine("pggb", None, seconds=16.0, do_speed=False, do_passband=False)
print("%-18s %9.1f %9.1f %9.1f %9.1f %9.1f" %
      ("pggb", m.spur_dbc, m.image_dbc, m.imd_dbc, m.imd_smpte_dbc, m.mt_dbc))
