# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality
ms, meta = quality.load_bench()
print("cached:", len(ms), meta.get("saved_at"))
for v in quality.verdict_src(ms):
    print("[%s] %s | %s" % (v["level"], v["title"], v["metric"]))
