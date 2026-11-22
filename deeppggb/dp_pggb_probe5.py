# -*- coding: utf-8 -*-
"""Does gain compensation recover PGGB's spur measurement? And what does um=2 give?"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src_bench"))
import pggb_run
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality

def tone(f, fs, sec, amp=0.5):
    n = int(round(fs * sec))
    k = (np.arange(n) * int(round(f))) % fs
    return (amp * np.sin(2 * np.pi * k / fs)).reshape(-1, 1)

def pggb_resample(x, src, dst, um, gain_db):
    y, _ = pggb_run.run(np.stack([x[:, 0], x[:, 0]], axis=1), src, um,
                        precision=64, bits=64, gain=gain_db)
    return y[:, :1]

# PGGB normalises peak to 0.99; peak gain for a 0.5 tone is 0.99/0.5 = +5.9334 dB.
# gain arg is applied AFTER normalisation, so pass -5.9334 to restore amplitude.
G = -20*np.log10(0.99/0.5)
print("gain arg =", G)

for (src, um, dst, tag) in ((44100, 2, 88200, "44.1->88.2"), (44100, 4, 176400, "44.1->176.4")):
    x = tone(1000.0, src, 4.0)
    y = pggb_resample(x, src, dst, um, G)
    seg = np.asarray(y[:, 0])[dst*3//2: dst*3//2 + dst]
    spur, hz = quality._worst_spur(seg, dst, 1000.0)
    print("%-14s spur=%8.1f dBc @ %8.0f Hz  peak=%.5f" % (tag, spur, hz, np.abs(y).max()))
