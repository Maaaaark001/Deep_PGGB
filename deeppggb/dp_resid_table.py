# -*- coding: utf-8 -*-
"""把"杂散"改成泄漏免疫的口径：扣掉基频 bin 后的残余能量（等价于最小二乘拟合基频）。
对比它与宽排除带口径的一致性，并给出八引擎全表。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

def spur_resid(s, rate, fund, half_bins=3):
    return Q._tone_residual(s, rate, [fund], half_bins=half_bins)

print("== 残差口径 vs 宽排除口径 ==")
print("%-16s %10s %10s" % ("config", "resid ±3", "resid ±20"))
UP_SRC, UP_DST = 44100, 88200
for key, o, name in (("dpggb", None, "dpggb dflt"),
                     ("dpggb", {"prec": "long"}, "dpggb long"),
                     ("dpggb", {"context": 800.0}, "dpggb ctx800"),
                     ("pggb", None, "pggb")):
    x = Q._tone(1000.0, UP_SRC, 4.0)
    s = center(E.resample(x, UP_SRC, UP_DST, key, o), UP_DST)
    a = spur_resid(s, UP_DST, 1000.0, 3)[0]
    b = spur_resid(s, UP_DST, 1000.0, 20)[0]
    print("%-16s %10.1f %10.1f" % (name, a, b))

print()
print("== 地板 ==")
s = center(Q._tone(1000.0, UP_DST, 4.0), UP_DST)
print("   analytic 88.2k: %8.1f" % spur_resid(s, UP_DST, 1000.0, 3)[0])

print()
print("== 八引擎全表（resid 杂散 / 单 bin 镜像 / 双音混叠 / 多音）==")
DN_SRC, DN_DST, FOLD = 96000, 44100, 14100.0
print("%-8s %9s %9s %9s %9s %6s" % ("engine", "spur", "image", "alias", "multi", "x"))
import time
for key in ("dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"):
    spec = E.ENGINES.get(key); o = E.default_opts(key)
    int_only = bool(getattr(spec, "integer_only", False))
    try:
        x = Q._tone(1000.0, UP_SRC, 4.0)
        s = center(E.resample(x, UP_SRC, UP_DST, key, o), UP_DST)
        sp = spur_resid(s, UP_DST, 1000.0, 3)[0]
        ref = max(Q._line_level(s, UP_DST, 1000.0), Q.EPS)
        im = 20*np.log10(max(Q._line_level(s, UP_DST, 43100.0), Q.EPS)/ref)
        if int_only:
            al = "n/a"
        else:
            xa = Q._tone(1000.0, DN_SRC, 4.0, 0.5) + Q._tone(30000.0, DN_SRC, 4.0, 0.5)
            sa = center(E.resample(xa, DN_SRC, DN_DST, key, o), DN_DST)
            r2 = max(Q._line_level(sa, DN_DST, 1000.0), Q.EPS)
            al = "%9.1f" % (20*np.log10(max(Q._line_level(sa, DN_DST, FOLD), Q.EPS)/r2))
        xm, mtf = Q._multitone(UP_SRC, 4.0)
        sm = center(E.resample(xm, UP_SRC, UP_DST, key, o), UP_DST)
        mt = Q._tone_residual(sm, UP_DST, mtf)[0]
        # speed on 10 s
        xs = np.repeat(Q._tone(1000.0, 44100, 10.0), 2, axis=1)
        best = None
        for _ in range(2):
            t0 = time.perf_counter(); E.resample(xs, 44100, 88200, key, o)
            dt = time.perf_counter()-t0; best = dt if best is None else min(best, dt)
        print("%-8s %9.1f %9.1f %9s %9.1f %6.0f" % (key, sp, im, al, mt, 10.0/best))
    except Exception as e:
        print("%-8s ERR %s" % (key, str(e)[:60]))
