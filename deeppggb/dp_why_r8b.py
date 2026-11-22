# -*- coding: utf-8 -*-
"""为什么 UI 基准里 r8brain 看起来比 Deep_PGGB 快：把口径与并行度拆开测。

UI 的速度列 = measure_engine 内部口径：10 s 单声道 44.1->88.2，两次取优。
论文的速度列 = 60 s 立体声 44.1->176.4，两次取优。
这个脚本把两种口径、以及 dpggb 的块长/线程数都测一遍，
并换算成 ns/输出样本（消除了"谁做的事多"的混淆）。
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import engines as E


def tone(rate, seconds, nch=1):
    n = int(rate * seconds)
    k = (np.arange(n, dtype=np.int64) * 997) % rate
    x = 0.5 * np.sin(2 * np.pi * k / rate)
    return np.stack([x] * nch, axis=1)  # 始终 2-D：(frames, ch)，单声道也要有列


def bench(engine, opts, src, dst, seconds, nch, reps=3):
    x = tone(src, seconds, nch)
    best = None
    for _ in range(reps):
        t0 = time.perf_counter()
        y = E.resample(x, src, dst, engine, opts)
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    n_out = y.shape[0] * (y.shape[1] if y.ndim > 1 else 1)
    return best, seconds / best, best / n_out * 1e9


CASES = [
    ("UI 口径: 10 s 单声道 44.1->88.2", 44100, 88200, 10.0, 1),
    ("论文口径: 60 s 立体声 44.1->176.4", 44100, 176400, 60.0, 2),
]
VARIANTS = [
    ("r8b", {"quality": "full", "transband": 2.0, "atten": 206.91}, "r8b 2% TB / 207 dB"),
    ("r8b", {"quality": "full", "transband": 10.0, "atten": 206.91}, "r8b 10% TB（更宽的过渡带）"),
    ("r8b", {"quality": "16", "transband": 2.0, "atten": 136.0}, "r8b 16bit 档 / 136 dB"),
    ("dpggb", {"block": 16.0, "context": 800.0}, "dpggb 块 16 s（默认）"),
    ("dpggb", {"block": 1.0, "context": 800.0}, "dpggb 块 1 s"),
    ("dpggb", {"block": 16.0, "context": 800.0, "workers": 1}, "dpggb 块 16 s / 单线程"),
    ("dpggb", {"block": 16.0, "context": 800.0, "prec": "long"}, "dpggb long double"),
]

for label, src, dst, sec, nch in CASES:
    print()
    print("=" * 96)
    print(label, " (输出样本数 %d)" % (int(sec * dst) * nch))
    print("%-38s %10s %10s %12s" % ("配置", "耗时 ms", "倍速 x", "ns/输出样本"))
    print("-" * 96)
    for eng, opts, name in VARIANTS:
        try:
            dt, sp, per = bench(eng, opts, src, dst, sec, nch)
            print("%-38s %10.1f %10.1f %12.2f" % (name, dt * 1e3, sp, per))
        except Exception as exc:  # noqa: BLE001
            print("%-38s %10s  %s" % (name, "ERR", str(exc)[:40]))
