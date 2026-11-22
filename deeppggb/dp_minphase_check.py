"""dp_minphase_check.py - minimum phase cannot null against a linear-phase
reference (different phase by design). Verify it by magnitude and causality."""
import numpy as np
from dp_test import run

src, dst = 44100, 176400
secs = 4.0
n = int(src * secs)
t = np.arange(n) / float(src)

# 1) magnitude response must match the linear-phase path in the passband
print("freq    linear_dB   minphase_dB");
for f in (1000.0, 10000.0, 18000.0, 20000.0):
    x = 0.5 * np.sin(2 * np.pi * f * t)
    lv = []
    for ph in (0, 1):
        y, _ = run(x, src, dst, phase=ph)
        c = len(y) // 2
        seg = y[c:c + dst]
        m = np.abs(np.fft.rfft(seg)) * 2 / len(seg)
        k = int(round(f * len(seg) / dst))
        lv.append(20 * np.log10(m[max(0, k - 3):k + 4].max() + 1e-30))
    print("%7.0f  %8.2f  %10.2f" % (f, lv[0] - lv[0], lv[1] - lv[0]))

# 2) causality: an impulse must not produce energy before it arrives
x = np.zeros(n)
x[n // 2] = 0.5
for ph, name in ((0, "linear"), (1, "minphase")):
    y, _ = run(x, src, dst, phase=ph)
    c = len(y) // 2
    pre = np.abs(y[c - 4000:c - 100]).max()
    post = np.abs(y[c:c + 4000]).max()
    print("%-9s pre-ring %.3e  post %.3e  ratio %.1f dB" % (
          name, pre, post, 20 * np.log10(pre / (post + 1e-30) + 1e-30)))
