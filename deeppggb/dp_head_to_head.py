"""dp_head_to_head.py - Deep_PGGB vs PGGB vs r8brain, identical test, exact reference.

PGGB only does integer multiples, so the comparison is 44.1 -> 176.4 (um=4),
which is also PGGB's native use case.
"""
import sys
import numpy as np
sys.path.insert(0, r"C:\Users\Administrator\Documents\Python_Code\src")
sys.path.insert(0, r"C:\Users\Administrator\Documents\Python_Code\src\src_bench")
from srctool import engines
import pggb_run

FS, DST = 44100, 176400
N = FS*4
rng = np.random.default_rng(5)
freqs = np.sort(rng.choice(np.arange(200, 18001), 40, replace=False)).astype(np.int64)
phs = rng.uniform(0, 2*np.pi, 40)
amps = rng.uniform(0.05, 0.5, 40); amps = amps/amps.sum()*1.6

def build(fs, n):
    idx = np.arange(n, dtype=np.int64); y = np.zeros(n)
    for f, p, a in zip(freqs, phs, amps):
        y += a*np.sin(2*np.pi*(((f*idx) % fs)/float(fs)) + p)
    return y

x = build(FS, N)
ref = build(DST, int(round(N*DST/FS)))

def null_db(y, skip=0.1):
    m = min(len(y), len(ref)); e = int(skip*m)
    a = y[e:m-e]; b = ref[e:m-e]
    d = a-b
    return 20*np.log10(np.sqrt(np.mean(b*b))/max(np.sqrt(np.mean(d*d)), 1e-300))

print("44.1 -> 176.4, 4 s, 40 tones below 18 kHz, exact-integer-phase reference")
print()

y = np.asarray(engines.resample(x.reshape(-1,1), FS, DST, "dpggb")[:,0], dtype=np.float64)
print("  Deep_PGGB          : %7.1f dB" % null_db(y))

y = np.asarray(engines.resample(x.reshape(-1,1), FS, DST, "r8b", {"transition": 1.0})[:,0], dtype=np.float64)
print("  r8brain 1%%         : %7.1f dB" % null_db(y))

try:
    yp, _ = pggb_run.run(np.stack([x, x], axis=1), FS, 4, precision=64, bits=64, corner=22050)
    yp = yp[:, 0].astype(np.float64)
    print("  PGGB (64-bit)      : %7.1f dB" % null_db(yp))
except Exception as e:
    print("  PGGB failed:", str(e)[:200])
