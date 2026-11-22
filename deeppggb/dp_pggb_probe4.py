# -*- coding: utf-8 -*-
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src_bench"))
import pggb_run

def tone(f, fs, sec, amp=0.5):
    n = int(round(fs * sec))
    k = (np.arange(n) * int(round(f))) % fs
    return amp * np.sin(2 * np.pi * k / fs)

x = tone(1000.0, 44100, 0.5)
for g in (0.0, -5.9334, -6.0, -11.954, 6.0):
    try:
        y, _ = pggb_run.run(np.stack([x, x], axis=1), 44100, 2, precision=64, bits=64, gain=g)
        print("gain=%-9s out_peak=%.6f  -> implied gain %.4f dB" % (g, np.abs(y).max(),
              20*np.log10(np.abs(y).max()/0.5)))
    except Exception as exc:
        print("gain=%-9s FAILED %s" % (g, str(exc)[:120]))

# does it normalize by peak, or by something else? try a signal with known peak 0.2 but quiet RMS
x2 = tone(1000.0, 44100, 0.5, amp=0.2)
y2, _ = pggb_run.run(np.stack([x2, x2], axis=1), 44100, 2, precision=64, bits=64)
print("amp 0.2 -> peak %.6f" % np.abs(y2).max())
