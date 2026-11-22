# -*- coding: utf-8 -*-
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality

for key in ("dpggb", "pggb"):
    m = quality.measure_engine(key)
    print("%-6s ok=%s ratio=%s" % (key, m.ok, m.ratio_label))
    if not m.ok:
        print("   ERR", m.error)
        continue
    print("   spur %8.1f @%7.0f | image %8.1f @%7.0f | alias %s | imd %8.1f | smpte %8.1f | mt %8.1f"
          % (m.spur_dbc, m.spur_hz, m.image_dbc, m.image_hz,
             "n/a" if m.alias_na else "%8.1f" % m.alias_dbc,
             m.imd_dbc, m.imd_smpte_dbc, m.mt_dbc))
    print("   pb215 %+.2f pb220 %+.2f speed %.0fx" % (m.passband_21500, m.passband_22000, m.speed_x))
