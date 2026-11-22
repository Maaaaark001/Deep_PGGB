# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality, engines

for key in list(engines.ENGINES):
    spec = engines.ENGINES[key]
    if not spec.available:
        print("%-6s unavailable: %s" % (key, spec.reason))
        continue
    m = quality.measure_engine(key)
    if not m.ok:
        print("%-6s ERR %s" % (key, m.error[:90]))
        continue
    print("%-6s spur %8.1f | img %8.1f | alias %9s | imd %8.1f | smpte %8.1f | mt %8.1f | pb215 %+6.2f | pb220 %+7.2f | %5.0fx"
          % (key, m.spur_dbc, m.image_dbc,
             "n/a" if m.alias_na else "%.1f" % m.alias_dbc,
             m.imd_dbc, m.imd_smpte_dbc, m.mt_dbc,
             m.passband_21500, m.passband_22000, m.speed_x))
