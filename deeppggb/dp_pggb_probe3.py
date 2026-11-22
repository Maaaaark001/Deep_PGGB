# -*- coding: utf-8 -*-
"""What does the second positional arg of pggb_256_it.exe actually mean?"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src_bench"))
import pggb_run

def tone(f, fs, sec, amp=0.5):
    n = int(round(fs * sec))
    k = (np.arange(n) * int(round(f))) % fs
    return amp * np.sin(2 * np.pi * k / fs)

def probe(fs, um, sec=0.25):
    x = tone(1000.0, fs, sec)
    try:
        y, out = pggb_run.run(np.stack([x, x], axis=1), fs, um, precision=64, bits=64)
        eff = y.shape[0] / float(len(x))
        print("fs=%6d um=%-18s n_in=%6d n_out=%7d  eff=%.6f" % (fs, um, len(x), y.shape[0], eff))
    except Exception as exc:
        print("fs=%6d um=%-18s FAILED %s" % (fs, um, str(exc)[:120]))

for um in (2, 3, 4, 0.5, 0.25, 1.5, 48000/44100.0, "1.08843537414966", 88200/44100.0*0.5):
    probe(44100, um)
print("---- 96k")
for um in (1, 2, 0.5, 48000/96000.0):
    probe(96000, um)
print("---- 48k")
for um in (1, 2, 0.5):
    probe(48000, um)
