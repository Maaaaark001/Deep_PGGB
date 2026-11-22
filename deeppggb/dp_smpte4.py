# -*- coding: utf-8 -*-
"""4 s 激励下 7k±60 的来源：渐变？文件长度？还是 60 Hz 真的在调制？"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

D = 88200
def prod(seg):
    f2s = Q.IMD_SMPTE[1]
    return Q._worst_product(seg, D, [f2s + i * 60 for i in (-2, -1, 1, 2)], f2s)[0]

def run(x, key, o, sec):
    y = np.asarray(E.resample(x, 44100, D, key, o)[:, 0], dtype=np.float64)
    st = (y.shape[0] - D) // 2
    return prod(y[st:st + D])

for sec in (4.0, 8.0, 16.0):
    xs = Q._two_tone(*Q.IMD_SMPTE, 44100, sec, 0.40, 0.10)
    row = ["%-8.0fs" % sec]
    for name, o in (("f20", {"block": 8.0}), ("f0", {"block": 8.0, "fade": 0.0}),
                    ("f100", {"block": 8.0, "fade": 100.0}), ("f0b4", {"block": 4.0, "fade": 0.0})):
        row.append("%s %7.1f" % (name, run(xs, "dpggb", o, sec)))
    row.append("pggb %7.1f" % run(xs, "pggb", None, sec))
    print("  ".join(row))

print()
print("== 只有 7 kHz（4 s）==")
x = Q._tone(7000.0, 44100, 4.0, 0.10)
print("  dpggb %7.1f   pggb %7.1f" % (run(x, "dpggb", {"block": 8.0}, 4.0), run(x, "pggb", None, 4.0)))
