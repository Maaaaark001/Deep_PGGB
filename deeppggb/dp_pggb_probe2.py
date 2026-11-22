# -*- coding: utf-8 -*-
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src_bench"))
import pggb_run

def tone(f, fs, sec, amp):
    n = int(round(fs * sec))
    k = (np.arange(n) * int(round(f))) % fs
    return amp * np.sin(2 * np.pi * k / fs)

for amp in (0.5, 0.25, 0.1, 0.01):
    x = tone(1000.0, 44100, 1.0, amp)
    y, _ = pggb_run.run(np.stack([x, x], axis=1), 44100, 2, precision=64, bits=64)
    seg = y[88200//2: 88200//2+88200, 0]
    print("amp=%.3f  in_peak=%.4f  out_peak=%.6f  gain=%.4f dB" % (
        amp, np.abs(x).max(), np.abs(y).max(), 20*np.log10(np.abs(y).max()/np.abs(x).max())))

# 88.2 -> 44.1 downsample by 2?
for fs, um, tag in ((88200, 1, "88200 um=1"), (176400, 1, "176400 um=1")):
    x = tone(1000.0, fs, 0.5, 0.5)
    y, _ = pggb_run.run(np.stack([x, x], axis=1), fs, um, precision=64, bits=64)
    print("%-14s n_in=%6d n_out=%6d" % (tag, len(x), y.shape[0]))
