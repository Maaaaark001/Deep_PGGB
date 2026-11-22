# -*- coding: utf-8 -*-
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality, engines

def imd_of(key, opts=None, src=44100, dst=96000):
    f1, f2 = quality.IMD_CCIF
    xi = quality._two_tone(f1, f2, src, 4.0, 0.25, 0.25)
    y = np.asarray(engines.resample(xi, src, dst, key, opts)[:, 0], dtype=np.float64)
    seg = y[(len(y)-dst)//2:][:dst]
    return quality._worst_product(seg, dst, (2*f1-f2, 2*f2-f1, f2-f1, f1+f2), (f1, f2))[0]

def mt_of(key, opts=None, src=44100, dst=96000):
    xm, mtf = quality._multitone(src, 4.0)
    y = np.asarray(engines.resample(xm, src, dst, key, opts)[:, 0], dtype=np.float64)
    seg = y[(len(y)-dst)//2:][:dst]
    return quality._tone_residual(seg, dst, mtf)[0]

print("dpggb double  imd %8.1f  mt %8.1f" % (imd_of("dpggb"), mt_of("dpggb")))
print("dpggb long    imd %8.1f  mt %8.1f" % (imd_of("dpggb", {"prec": "long"}), mt_of("dpggb", {"prec": "long"})))
print("dpggb blk0.25 imd %8.1f  mt %8.1f" % (imd_of("dpggb", {"block": 0.25}), mt_of("dpggb", {"block": 0.25})))
print("dpggb blk16   imd %8.1f  mt %8.1f" % (imd_of("dpggb", {"block": 16.0}), mt_of("dpggb", {"block": 16.0})))
print("dpggb ->88.2  imd %8.1f  mt %8.1f" % (imd_of("dpggb", dst=88200), mt_of("dpggb", dst=88200)))
print("pggb  ->88.2  imd %8.1f  mt %8.1f" % (imd_of("pggb", dst=88200), mt_of("pggb", dst=88200)))
