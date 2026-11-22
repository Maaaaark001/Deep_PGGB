import sys, time
from pathlib import Path
sys.path.insert(0, str(Path("..").resolve()))
import numpy as np
from srctool import engines

x = np.sin(2 * np.pi * 997 * np.arange(44100 * 2) / 44100.0)[:, None] * 0.5
cases = [
    (44100, 48000, {}),
    (44100, 96000, {}),
    (96000, 44100, {}),
    (44100, 88200, {}),
    (48000, 44100, {}),
    (44100, 48000, {"phase": "min"}),
    (44100, 48000, {"prec": "long"}),
    (44100, 48000, {"taper": "blackman", "fade": 50.0}),
    (44100, 48000, {"block": 0.5}),
]
for src, dst, extra in cases:
    o = engines.default_opts("dpggb"); o.update(extra)
    xs = x if src == 44100 else np.sin(2 * np.pi * 997 * np.arange(src * 2) / src)[:, None] * 0.5
    t0 = time.perf_counter()
    y = engines.resample(xs, src, dst, "dpggb", o)
    dt = time.perf_counter() - t0
    exp = round(xs.shape[0] * dst / src)
    print("%6d->%6d %-28s len %7d (exp %7d) %5.2fs %5.0fx" % (
        src, dst, str(extra), y.shape[0], exp, dt, 2.0 / dt))
