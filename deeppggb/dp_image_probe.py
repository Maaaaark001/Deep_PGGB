# -*- coding: utf-8 -*-
"""44.1->88.2 的镜像（43.1 kHz）由什么决定？"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

SRC, DST, SEC = 44100, 88200, 4.0

def image(key, opts):
    x = Q._tone(1000.0, SRC, SEC)
    s = np.asarray(E.resample(x, SRC, DST, key, opts)[:, 0], dtype=np.float64)
    st = (s.shape[0] - DST) // 2
    s = s[st:st + DST]
    ref = max(Q._line_level(s, DST, 1000.0), Q.EPS)
    return 20 * np.log10(max(Q._line_level(s, DST, SRC - 1000.0), Q.EPS) / ref)

print("%-24s %8s" % ("config", "image"))
print("%-24s %8.1f" % ("pggb default", image("pggb", None)))
for name, o in (("dpggb default", None),
                ("dpggb long", {"prec": "long"}),
                ("dpggb fade=0", {"fade": 0.0}),
                ("dpggb fade=100", {"fade": 100.0}),
                ("dpggb ctx=800", {"context": 800.0}),
                ("dpggb block=16", {"block": 16.0}),
                ("dpggb long+fade=0", {"prec": "long", "fade": 0.0}),
                ("dpggb long+ctx800", {"prec": "long", "context": 800.0})):
    print("%-24s %8.1f" % (name, image("dpggb", o)))

print()
print("== 镜像频率附近扫一遍（看是单根线还是裙边）==")
x = Q._tone(1000.0, SRC, SEC)
s = np.asarray(E.resample(x, SRC, DST, "dpggb", {"prec": "long"})[:, 0], dtype=np.float64)
st = (s.shape[0] - DST) // 2
s = s[st:st + DST]
ref = Q._line_level(s, DST, 1000.0)
for f in (42000.0, 43000.0, 43100.0, 43200.0, 44000.0):
    print("   %6.0f Hz  %8.1f dBc" % (f, 20*np.log10(max(Q._line_level(s, DST, f), Q.EPS)/ref)))
