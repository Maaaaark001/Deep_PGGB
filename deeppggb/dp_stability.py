# -*- coding: utf-8 -*-
"""在 −300 dBc 量级上，引擎之间的排序稳定吗？换一个"不该影响失真"的旋钮再看一次。"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

def m(key, o):
    r = Q.measure_engine(key, o, do_speed=False, do_passband=False)
    return dict(spur=r.spur_dbc, image=r.image_dbc, ccif=r.imd_dbc,
                smpte=r.imd_smpte_dbc, multi=r.mt_dbc)

print("%-26s %8s %8s %8s %8s %8s" % ("config", "spur", "image", "ccif", "smpte", "multi"))
out = {}
for name, key, o in (
        ("dpggb double block4", "dpggb", {"block": 4.0}),
        ("dpggb double block1", "dpggb", {"block": 1.0}),
        ("dpggb double block16", "dpggb", {"block": 16.0}),
        ("dpggb long", "dpggb", {"prec": "long"}),
        ("dpggb taper6", "dpggb", {"taper": "smooth6"}),
        ("pggb corner22050", "pggb", {"corner": 22050.0}),
        ("pggb corner21500", "pggb", {"corner": 21500.0}),
        ("pggb corner20000", "pggb", {"corner": 20000.0})):
    r = m(key, o)
    out[name] = r
    print("%-26s %8.1f %8.1f %8.1f %8.1f %8.1f" %
          (name, r["spur"], r["image"], r["ccif"], r["smpte"], r["multi"]))

json.dump(out, open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "work", "paper_stability.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
