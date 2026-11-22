# -*- coding: utf-8 -*-
"""八引擎基准的重复性：同一协议跑 3 遍，逐格取中位数并报告极差。
协议：16 s 激励、5 个 1 s 窗中位数、44.1->88.2 上行 + 96->44.1 双音混叠、
速度列 60 s 立体声 44.1->176.4（两次取优）。"""
import os, sys, json, time, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality as Q, engines as E

KEYS = ["dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"]
REPEATS = 3
FIELDS = ["spur_dbc", "image_dbc", "alias_dbc", "imd_dbc", "imd_smpte_dbc", "mt_dbc"]

runs = {k: [] for k in KEYS}
for rep in range(REPEATS):
    for k in KEYS:
        m = Q.measure_engine(k, E.default_opts(k), seconds=16.0, do_speed=False)
        runs[k].append({f: getattr(m, f) for f in FIELDS} | {"ok": m.ok, "na": getattr(m, "alias_na", False)})
    print("repeat %d done" % (rep + 1), flush=True)

table = {}
for k in KEYS:
    cells = {}
    for f in FIELDS:
        vals = [r[f] for r in runs[k] if r["ok"] and r[f] is not None]
        if not vals:
            cells[f] = None
            continue
        cells[f] = {"med": statistics.median(vals), "min": min(vals), "max": max(vals),
                    "spread": max(vals) - min(vals)}
    cells["alias_na"] = runs[k][0]["na"]
    table[k] = cells

# speed on its own: 60 s stereo 44.1->176.4, best of 2, not part of the repeat
import numpy as np
from srctool import engines as E2
_src, _dst, _sec = 44100, 176400, 60.0
_n = int(_src * _sec)
_x = np.stack([0.5 * np.sin(2 * np.pi * 997.0 * np.arange(_n) / _src),
               0.5 * np.sin(2 * np.pi * 4999.0 * np.arange(_n) / _src)], axis=1)
for k in KEYS:
    try:
        opts = E.default_opts(k)
        best = None
        for _ in range(2):
            t0 = time.perf_counter()
            E2.resample(_x, _src, _dst, k, opts)
            dt = time.perf_counter() - t0
            best = dt if best is None else min(best, dt)
        table[k]["speed"] = round(_sec / best, 1)
    except Exception as exc:  # noqa: BLE001
        table[k]["speed"] = None
        print("speed failed", k, exc)

print()
hdr = "%-8s %18s %18s %10s %18s %18s %18s %8s" % ("engine", "spur", "image", "alias", "ccif", "smpte", "multi", "x")
print(hdr)
for k in KEYS:
    c = table[k]
    def cell(f):
        d = c.get(f)
        if not d:
            return "%18s" % ("n/a" if c.get("alias_na") and f == "alias_dbc" else "-")
        return "%8.1f±%4.1f(%4.1f)" % (d["med"], d["spread"] / 2, d["spread"])
    print("%-8s %s %s %s %s %s %s %s" % (k, cell("spur_dbc"), cell("image_dbc"), cell("alias_dbc"),
                                         cell("imd_dbc"), cell("imd_smpte_dbc"), cell("mt_dbc"),
                                         ("%7.0f" % c["speed"]) if c.get("speed") else "   -"))

out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work", "bench_repeat.json")
with open(out, "w", encoding="utf-8") as fh:
    json.dump(table, fh, ensure_ascii=False, indent=1)
print("WROTE", out)
