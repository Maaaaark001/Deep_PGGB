# -*- coding: utf-8 -*-
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

def run(x, src, um):
    y, _ = pggb_run.run(np.stack([x[:, 0], x[:, 0]], axis=1), src, um,
                        precision=64, bits=64, gain=0.0)
    y = y[:, :1]
    return y * (np.abs(x).max() / np.abs(y).max())

for f in (1000.0, 10000.0, 20000.0, 21500.0, 22000.0):
    x = tone(f, 44100, 4.0)
    y = run(x, 44100, 2)
    seg = y[88200*3//2: 88200*3//2 + 88200, 0]
    lvl = quality._line_level(seg, 88200, f)
    print("n_in=%d n_out=%d (expect %d)  f=%7.0f  gain=%+.4f dB"
          % (len(x), len(y), 2*len(x), f, 20*np.log10(max(lvl,1e-20)/0.5)))
