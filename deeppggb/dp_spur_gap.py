# -*- coding: utf-8 -*-
"""为什么 Deep_PGGB 的单音杂散比 PGGB 差 3 dB？同条件、重复、找谱线位置。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

SRC, DST = 44100, 88200

def run(key, opts=None, fund=1000.0):
    x = Q._tone(fund, SRC, 4.0)
    y = E.resample(x, SRC, DST, key, opts)
    seg = np.asarray(y[:, 0], dtype=np.float64)
    st = (seg.shape[0] - DST) // 2
    seg = seg[st:st + DST]
    return Q._worst_spur(seg, DST, fund), seg

print("== 同条件 44.1->88.2, 1 kHz ==")
for key in ("dpggb", "pggb"):
    for i in range(3):
        (db, hz), _ = run(key)
        print("  %-6s run%d  %8.1f dBc @ %8.1f Hz" % (key, i, db, hz))

print("== dpggb 旋钮 ==")
for name, o in (("default", None),
                ("taper=smooth6", {"taper": "smooth6"}),
                ("taper=smooth4", {"taper": "smooth4"}),
                ("ctx=800", {"context": 800.0}),
                ("fade=50", {"fade": 50.0}),
                ("block=16", {"block": 16.0}),
                ("long", {"prec": "long"})):
    (db, hz), _ = run("dpggb", o)
    print("  %-16s %8.1f dBc @ %8.1f Hz" % (name, db, hz))

print("== 频率依赖（dpggb / pggb）==")
for f in (100.0, 997.0, 5000.0, 10000.0, 15000.0, 18000.0):
    a, _ = run("dpggb", None, f)
    b, _ = run("pggb", None, f)
    print("  %6.0f Hz  dp %8.1f @%8.0f   pg %8.1f @%8.0f" % (f, a[0], a[1], b[0], b[1]))

print("== 残差谱 top bins（dpggb 1 kHz）==")
(db, hz), seg = run("dpggb")
spec = np.abs(np.fft.rfft(seg)) * 2.0 / seg.shape[0]
freqs = np.fft.rfftfreq(seg.shape[0], 1.0 / DST)
k = int(round(1000.0 * seg.shape[0] / DST))
mask = np.ones(spec.shape[0], bool); mask[max(0,k-3):k+4] = False; mask[:4] = False
mask &= (freqs >= 20) & (freqs <= 20000)
idx = np.argsort(spec[mask])[::-1][:8]
band = np.flatnonzero(mask)
ref = Q._line_level(seg, DST, 1000.0)
for j in idx:
    print("   %9.1f Hz  %8.1f dBc" % (freqs[band[j]], 20*np.log10(spec[band[j]]/ref)))
print("   ref level %.6f" % ref)
