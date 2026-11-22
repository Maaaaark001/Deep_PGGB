# -*- coding: utf-8 -*-
"""用最终口径（带 43.1k->44.1k、参考=实测基频）复核 context 是否值得设 800。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q

def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

print("%-18s %9s %9s %9s" % ("config", "spur", "image", "ccif"))
for ctx in (200.0, 400.0, 600.0, 800.0, 1200.0):
    o = {"context": ctx}
    m = Q.measure_engine("dpggb", o, do_speed=False)
    print("%-18s %9.1f %9.1f %9.1f" % ("ctx%.0f" % ctx, m.spur_dbc, m.image_dbc, m.imd_dbc))
m = Q.measure_engine("pggb", None, do_speed=False)
print("%-18s %9.1f %9.1f %9.1f" % ("pggb", m.spur_dbc, m.image_dbc, m.imd_dbc))
# floor for image band, same band definition
s = center(Q._tone(1000.0, 88200, 4.0), 88200)
lvl = Q._line_level(s, 88200, 1000.0)
print("image floor (analytic 88.2k): %.1f" % Q._band_level_db(s, 88200, 43100.0, 44100.0, lvl))
