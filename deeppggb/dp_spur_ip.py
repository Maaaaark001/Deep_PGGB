# -*- coding: utf-8 -*-
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality, engines

def tone_ip(f, fs, sec, amp=0.5):
    n = int(round(fs * sec))
    k = (np.arange(n, dtype=np.int64) * int(round(f))) % int(fs)
    return (amp * np.sin(2 * np.pi * k / float(fs))).reshape(-1, 1)

for key in ("dpggb", "pggb", "r8b", "soxng", "soxr", "swr", "ssrc", "scipy"):
    spec = engines.ENGINES.get(key)
    if spec is None or not spec.available:
        continue
    src, dst = (44100, 88200) if spec.integer_only else (44100, 48000)
    x = tone_ip(1000.0, src, 4.0)
    try:
        y = engines.resample(x, src, dst, key)
        seg = np.asarray(y[:, 0], dtype=np.float64)
        st = (seg.shape[0] - dst) // 2
        seg = seg[st: st + dst]
        spur, hz = quality._worst_spur(seg, dst, 1000.0)
        print("%-6s %6d->%6d  spur %8.1f dBc @ %7.0f Hz" % (key, src, dst, spur, hz))
    except Exception as exc:
        print("%-6s FAILED %s" % (key, str(exc)[:80]))
