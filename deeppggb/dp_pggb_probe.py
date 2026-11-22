# -*- coding: utf-8 -*-
"""Probe what the PGGB kernel actually accepts: integer factors only? downsampling?"""
import os, sys, traceback
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src_bench"))
import pggb_run

print("EXE:", pggb_run.PGGB_EXE, os.path.exists(pggb_run.PGGB_EXE))

def tone(f, fs, sec, amp=0.5):
    n = int(round(fs * sec))
    k = (np.arange(n) * int(round(f))) % fs
    return amp * np.sin(2 * np.pi * k / fs)

def probe(label, fs, um, sec=0.5):
    x = tone(1000.0, fs, sec)
    try:
        y, out = pggb_run.run(np.stack([x, x], axis=1), fs, um, precision=64, bits=64)
        print("%-28s fs=%6d um=%-4s -> %7d samples (expect %7d)  peak=%.4f"
              % (label, fs, um, y.shape[0], int(round(len(x) * um)), float(np.abs(y).max())))
        return y
    except Exception as exc:
        print("%-28s fs=%6d um=%-4s -> FAILED: %s" % (label, fs, um, str(exc)[:160]))
        return None

probe("upsample x2", 44100, 2)
probe("upsample x4", 44100, 4)
probe("upsample x1 (no-op?)", 44100, 1)
probe("downsample 96->48 (um=1)", 96000, 1)
probe("um=0.5 fractional", 44100, 0.5)
probe("um=48000 (non-integer ratio)", 44100, 48000)
