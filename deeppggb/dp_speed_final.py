# -*- coding: utf-8 -*-
"""论文与 UI 共用的速度口径：60 s 立体声 44.1->176.4，best of 3，单进程顺序跑。"""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import engines as E

SRC, DST, SEC = 44100, 96000, 60.0
n = int(SRC * SEC)
k1 = (np.arange(n, dtype=np.int64) * 997) % SRC
k2 = (np.arange(n, dtype=np.int64) * 4999) % SRC
X = np.stack([0.5 * np.sin(2 * np.pi * k1 / SRC), 0.5 * np.sin(2 * np.pi * k2 / SRC)], axis=1)

out = {}
for eng in ("dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"):
    opts = E.default_opts(eng)
    times = []
    try:
        for _ in range(3):
            t0 = time.perf_counter()
            E.resample(X, SRC, DST, eng, opts)
            times.append(time.perf_counter() - t0)
    except Exception as exc:  # noqa: BLE001
        out[eng] = {"error": str(exc)[:80]}
        print("%-6s FAILED %s" % (eng, str(exc)[:60]), flush=True)
        continue
    best = min(times)
    out[eng] = {"best_s": round(best, 3), "x": round(SEC / best, 1),
                "all_x": [round(SEC / t, 1) for t in times]}
    print("%-6s best %6.2fs  %6.1fx   runs %s" % (eng, best, SEC / best, out[eng]["all_x"]), flush=True)

p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work", "speed_final_96k.json")
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("WROTE", p)
