# -*- coding: utf-8 -*-
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import engines, quality

def tone(f, fs, sec, amp=0.5):
    n = int(round(fs * sec))
    k = (np.arange(n) * int(round(f))) % fs
    return (amp * np.sin(2 * np.pi * k / fs)).reshape(-1, 1)

print("available:", engines.ENGINES["pggb"].available)
for src, dst in ((44100, 88200), (44100, 176400), (48000, 96000), (44100, 48000)):
    x = tone(1000.0, src, 1.0)
    try:
        y = engines.resample(x, src, dst, "pggb")
        seg = y[dst//2: dst//2 + dst, 0] if y.shape[0] >= dst else y[:, 0]
        print("%6d -> %6d : n=%7d peak=%.4f" % (src, dst, y.shape[0], np.abs(y).max()))
    except Exception as exc:
        print("%6d -> %6d : %s" % (src, dst, str(exc)[:100]))

# passband after undo
for f in (1000.0, 20000.0, 22000.0):
    x = tone(f, 44100, 4.0)
    y = engines.resample(x, 44100, 88200, "pggb")
    seg = y[88200*3//2: 88200*3//2+88200, 0]
    print("passband %7.0f -> %+.4f dB" % (f, 20*np.log10(max(quality._line_level(seg, 88200, f),1e-20)/0.5)))
