# -*- coding: utf-8 -*-
"""−320.2 dBc 到底来自渐变乘法还是 FFT？三组对照。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

SRC, DST, SEC = 44100, 88200, 4.0
print("EPS =", Q.EPS)

def worst(y, fund=1000.0):
    seg = np.asarray(y[:, 0], dtype=np.float64)
    st = (seg.shape[0] - DST) // 2
    return Q._worst_spur(seg[st:st + DST], DST, fund)

# 1) 引擎内部渐变（默认）
x = Q._tone(1000.0, SRC, SEC)
print("A engine fade=20      %8.1f @ %8.0f" % worst(E.resample(x, SRC, DST, "dpggb", None)))

# 2) 调用方预先渐变，引擎 fade=0 —— 若残差消失，说明是引擎内部那次乘法
def smoother5(t, n=5):
    # 与引擎同形的 C5 窗（镜像求值）
    from math import comb
    def w(u):
        s = 0.0
        for k in range(n + 1):
            s += comb(n + k, k) * comb(2 * n + 1, n - k) * ((-u) ** k)
        return u ** (n + 1) * s
    return np.where(t > 0.5, 1.0 - w(1.0 - t), w(t))

n = x.shape[0]
T = int(round(0.020 * SRC))
t = np.arange(T) / T
w = smoother5(t)
xp = x.copy()
xp[:T, 0] *= w
xp[-T:, 0] *= w[::-1]
print("B caller fade, engine0 %8.1f @ %8.0f" %
      worst(E.resample(xp, SRC, DST, "dpggb", {"fade": 0.0})))
print("C caller fade, engine20%8.1f @ %8.0f" %
      worst(E.resample(xp, SRC, DST, "dpggb", None)))

# 3) 完全不过引擎：直接拿 88.2k 的解析信号，看纯分析地板
x88 = Q._tone(1000.0, DST, SEC)
print("D analytic 88.2k      %8.1f @ %8.0f" % worst(x88))

# 4) long double
print("E long double         %8.1f @ %8.0f" %
      worst(E.resample(x, SRC, DST, "dpggb", {"prec": "long"})))
