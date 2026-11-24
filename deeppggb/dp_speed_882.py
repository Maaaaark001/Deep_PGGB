# -*- coding: utf-8 -*-
"""统一速度口径：60 s 立体声 44.1->88.2（与保真度同一倍率）。

交错测量：这台 i5-7500T（35 W）连续满载几分钟就会掉 20-30% 主频，按"一个块长跑完
再跑下一个"的顺序测量，表里最后一行（30 s 块）量到的其实是降频后的机器。所以每轮
把所有单元各跑一次（顺序固定、先打乱一次并固定种子），单元的成绩取多轮最好值，
漂移落进单元自身的离散度而不是它的位置。

输出 work/speed_882.json：engine = 八引擎最低耗时（best of ROUNDS），
grid = dpggb 块长 × worker 矩阵（best of ROUNDS）。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

from srctool import engines as E

SRC, DST, SEC = 44100, 88200, 60.0
ROUNDS = 3
ENGINES = ("dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy")
BLOCKS = (0.5, 1.0, 2.0, 4.0, 30.0)
WORKERS = (1, 2, 4, 8)

n = int(SRC * SEC)
k1 = (np.arange(n, dtype=np.int64) * 997) % SRC
k2 = (np.arange(n, dtype=np.int64) * 4999) % SRC
X = np.stack([0.5 * np.sin(2 * np.pi * k1 / SRC), 0.5 * np.sin(2 * np.pi * k2 / SRC)], axis=1)


def grid_opts(blk, wk):
    return {"block": blk, "context": 800.0, "workers": wk}


def timed(eng, opts):
    t0 = time.perf_counter()
    E.resample(X, SRC, DST, eng, opts)
    return SEC / (time.perf_counter() - t0)


def main():
    out = {"engine": {}, "grid": {}, "rounds": ROUNDS, "order": "interleaved"}

    cells = [("eng", e) for e in ENGINES]
    cells += [("grid", (b, w)) for b in BLOCKS for w in WORKERS]
    rng = np.random.default_rng(20261124)
    order = [cells[i] for i in rng.permutation(len(cells))]

    best = {}
    for kind, key in cells:                       # 预热：建 plan、暖页缓存
        try:
            if kind == "eng":
                timed(key, E.default_opts(key))
            else:
                timed("dpggb", grid_opts(*key))
        except Exception as exc:  # noqa: BLE001
            best[(kind, key)] = ("error", str(exc))

    for r in range(ROUNDS):
        for kind, key in order:
            if isinstance(best.get((kind, key)), tuple):
                continue
            try:
                x = timed(key, E.default_opts(key)) if kind == "eng" else timed("dpggb", grid_opts(*key))
            except Exception as exc:  # noqa: BLE001
                best[(kind, key)] = ("error", str(exc))
                continue
            prev = best.get((kind, key))
            best[(kind, key)] = x if prev is None else max(prev, x)
        print("round %d/%d done" % (r + 1, ROUNDS), flush=True)

    for eng in ENGINES:
        v = best.get(("eng", eng))
        if isinstance(v, tuple):
            out["engine"][eng] = None
            print("%-6s FAILED %s" % (eng, v[1][:60]), flush=True)
        else:
            out["engine"][eng] = round(v, 1)
            print("%-6s %7.1fx" % (eng, v), flush=True)

    for blk in BLOCKS:
        row = {}
        for wk in WORKERS:
            v = best.get(("grid", (blk, wk)))
            row[wk] = None if isinstance(v, tuple) else round(v, 1)
        out["grid"][str(blk)] = row
        print("block %-5s %s" % (blk, row), flush=True)

    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "work", "speed_882.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("WROTE", p)


if __name__ == "__main__":
    main()
