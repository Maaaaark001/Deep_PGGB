# -*- coding: utf-8 -*-
"""修正口径后重跑八引擎基准（含 PGGB），结果写入 cache/bench.json 与 work/paper_data.json。"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality as Q, engines as E, config

keys = ["dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"]
print("%-8s %9s %9s %9s %9s %9s %8s %7s" %
      ("engine", "spur", "image", "alias", "ccif", "multi", "pb21.5k", "x"))
out = []
for k in keys:
    t0 = time.perf_counter()
    m = Q.measure_engine(k, E.default_opts(k))
    dt = time.perf_counter() - t0
    out.append(m)
    print("%-8s %9.1f %9.1f %9s %9.1f %9.1f %8.2f %7.0f" %
          (k, m.spur_dbc, m.image_dbc,
           ("n/a" if m.alias_na else "%9.1f" % m.alias_dbc),
           m.imd_dbc, m.mt_dbc, m.passband_21500, m.speed_x))
    if not m.ok:
        print("   ERROR:", m.error)
Q.save_bench(out, {"note": "corrected metrics: residual spur / band-energy image / two-tone alias"})
print()
for v in Q.verdict_src(out):
    print("[%s] %s — %s" % (v["level"], v["title"], v["text"][:120]))
