# -*- coding: utf-8 -*-
"""统一速度口径：60 s 立体声 44.1->88.2（与保真度同一倍率），best of 3。
同时给出 dpggb 的块长×线程网格（表 7）。"""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import engines as E

SRC, DST, SEC = 44100, 88200, 60.0
n = int(SRC * SEC)
k1 = (np.arange(n, dtype=np.int64) * 997) % SRC
k2 = (np.arange(n, dtype=np.int64) * 4999) % SRC
X = np.stack([0.5 * np.sin(2 * np.pi * k1 / SRC), 0.5 * np.sin(2 * np.pi * k2 / SRC)], axis=1)


def run(eng, opts, reps=3):
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        E.resample(X, SRC, DST, eng, opts)
        ts.append(time.perf_counter() - t0)
    return min(ts), ts


out = {"engine": {}, "grid": {}}
print("--- 八引擎 60 s 立体声 44.1->88.2 ---")
for eng in ("dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"):
    try:
        best, ts = run(eng, E.default_opts(eng))
        out["engine"][eng] = round(SEC / best, 1)
        print("%-6s %7.1fx  (runs %s)" % (eng, SEC / best, [round(SEC / t, 1) for t in ts]), flush=True)
    except Exception as exc:  # noqa: BLE001
        out["engine"][eng] = None
        print("%-6s FAILED %s" % (eng, str(exc)[:60]), flush=True)

print("--- dpggb 块长 x 线程（表 7）---")
for blk in (0.5, 1.0, 2.0, 4.0, 30.0):
    row = {}
    for wk in (1, 2, 4, 8):
        best, _ = run("dpggb", {"block": blk, "context": 800.0, "workers": wk}, reps=2)
        row[wk] = round(SEC / best, 1)
    out["grid"][str(blk)] = row
    print("block %-5s %s" % (blk, row), flush=True)

p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work", "speed_882.json")
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("WROTE", p)
