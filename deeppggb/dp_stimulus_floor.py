# -*- coding: utf-8 -*-
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import quality

# The spur floor: analyse a PERFECT 1 kHz tone at 88.2 kHz, no resampling at all.
n = 88200 * 4
t = np.arange(n) / 88200.0
perfect = (0.5 * np.sin(2 * np.pi * 1000.0 * t))
seg = perfect[88200*3//2: 88200*3//2 + 88200]
print("naive-phase tone, no resampling : spur %8.1f dBc @ %7.0f Hz" % quality._worst_spur(seg, 88200, 1000.0))

k = (np.arange(n, dtype=np.int64) * 1000) % 88200
exact = 0.5 * np.sin(2 * np.pi * k / 88200.0)
seg2 = exact[88200*3//2: 88200*3//2 + 88200]
print("integer-phase tone, no resampling: spur %8.1f dBc @ %7.0f Hz" % quality._worst_spur(seg2, 88200, 1000.0))
