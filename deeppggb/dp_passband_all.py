# -*- coding: utf-8 -*-
"""通带（passband）系统扫描：八引擎 × 九频点 × 上行/下行两个方向。

口径：4 s 单音、居中 1 s 窗、读该频率的单根谱线相对输入幅度 0.5 的增益（dB）。
上行 44.1→88.2（×2，八台都能跑，包括只做整数倍率的 PGGB）；
下行 96→44.1（PGGB 无降采样路径，记 n/a）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import engines as E  # noqa: E402
from srctool.quality import _gain_at  # noqa: E402

FREQS = [1000.0, 10000.0, 18000.0, 20000.0, 21000.0, 21500.0, 21900.0, 22000.0, 22049.0]
UP_SRC, UP_DST = 44100, 88200
DN_SRC, DN_DST = 96000, 44100
ORDER = ["dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"]

res = {"freqs": FREQS, "up": {}, "down": {}}
print("=== 上行 44.1->88.2（增益 dB）")
head = "%-6s" % "eng" + "".join("%8.0f" % f for f in FREQS)
print(head)
for eng in ORDER:
    try:
        row = [_gain_at(eng, E.default_opts(eng), UP_SRC, UP_DST, f) for f in FREQS]
        res["up"][eng] = [round(v, 2) for v in row]
        print("%-6s" % eng + "".join("%8.2f" % v for v in row), flush=True)
    except Exception as exc:  # noqa: BLE001
        res["up"][eng] = None
        print("%-6s FAILED %s" % (eng, str(exc)[:60]), flush=True)

print("=== 下行 96->44.1（增益 dB）")
print(head)
for eng in ORDER:
    try:
        row = [_gain_at(eng, E.default_opts(eng), DN_SRC, DN_DST, f) for f in FREQS]
        res["down"][eng] = [round(v, 2) for v in row]
        print("%-6s" % eng + "".join("%8.2f" % v for v in row), flush=True)
    except Exception as exc:  # noqa: BLE001
        res["down"][eng] = None
        print("%-6s n/a (%s)" % (eng, str(exc)[:40]), flush=True)

p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work", "passband_all.json")
json.dump(res, open(p, "w", encoding="utf-8"), indent=1)
print("WROTE", p)
