# -*- coding: utf-8 -*-
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality, engines

def spur_of(key, src, dst, opts=None, fund=1000.0):
    x = quality._tone(fund, src, 4.0)
    y = np.asarray(engines.resample(x, src, dst, key, opts)[:, 0], dtype=np.float64)
    seg = y[(len(y)-dst)//2:][:dst]
    return quality._worst_spur(seg, dst, fund)

for blk in (0.25, 1.0, 4.0, 16.0):
    print("dpggb 44.1->48 block=%-5s : %8.1f @ %6.0f" % (blk, *spur_of("dpggb", 44100, 48000, {"block": blk})))
for dst in (88200, 96000, 176400):
    print("dpggb 44.1->%-6d        : %8.1f @ %6.0f" % (dst, *spur_of("dpggb", 44100, dst)))
print("pggb  44.1->176400       : %8.1f @ %6.0f" % spur_of("pggb", 44100, 176400))
print("pggb  44.1->88200        : %8.1f @ %6.0f" % spur_of("pggb", 44100, 88200))
# tone bin energy share of the residual
x = quality._tone(1000.0, 44100, 4.0)
y = np.asarray(engines.resample(x, 44100, 48000, "dpggb")[:, 0], dtype=np.float64)
seg = y[(len(y)-48000)//2:][:48000]
n = seg.shape[0]; spec = np.abs(np.fft.rfft(seg))*2/n
k = 1000; keep = np.ones(spec.shape[0], bool); keep[max(0,k-3):k+4]=False; keep[:4]=False
print("dpggb residual: total %.3e, at 2 kHz %.3e (%.1f%%)" % (
    np.sqrt((spec[keep]**2).sum()), spec[2000], 100*(spec[2000]**2)/(spec[keep]**2).sum()))
