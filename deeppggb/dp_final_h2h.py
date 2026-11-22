"""dp_final_h2h.py - the honest scorecard: Deep_PGGB vs PGGB vs r8brain."""
import sys, time
import numpy as np
sys.path.insert(0, r"C:\Users\Administrator\Documents\Python_Code\src")
sys.path.insert(0, r"C:\Users\Administrator\Documents\Python_Code\src\src_bench")
from srctool import engines
import pggb_run

FS = 44100
N = FS*4
rng = np.random.default_rng(5)
freqs = np.sort(rng.choice(np.arange(200, 18001), 40, replace=False)).astype(np.int64)
phs = rng.uniform(0, 2*np.pi, 40); amps = rng.uniform(0.05, 0.5, 40); amps = amps/amps.sum()*1.6

def build(fs, n):
    idx = np.arange(n, dtype=np.int64); y = np.zeros(n)
    for f, p, a in zip(freqs, phs, amps):
        y += a*np.sin(2*np.pi*(((f*idx) % fs)/float(fs)) + p)
    return y

x = build(FS, N); ref = build(176400, int(round(N*4)))

def null_db(y, skip=0.1):
    m = min(len(y), len(ref)); e = int(skip*m)
    a = y[e:m-e].astype(np.float64); b = ref[e:m-e]
    g = float(np.dot(a,b)/np.dot(b,b)); a = a/g
    d = a-b
    return 20*np.log10(np.sqrt(np.mean(b*b))/max(np.sqrt(np.mean(d*d)),1e-300))

print("=== 1. accuracy, 44.1 -> 176.4, band-limited content ===")
print("  Deep_PGGB  %7.1f dB" % null_db(np.asarray(engines.resample(x.reshape(-1,1), FS, 176400, "dpggb")[:,0])))
yp, _ = pggb_run.run(np.stack([x,x],axis=1), FS, 4, precision=64, bits=64, corner=22050)
print("  PGGB       %7.1f dB" % null_db(yp[:,0]))
print("  r8brain    %7.1f dB" % null_db(np.asarray(engines.resample(x.reshape(-1,1), FS, 176400, "r8b", {"transition":1.0})[:,0])))

print()
print("=== 2. can it do 44.1 -> 48 (non-integer)? ===")
try:
    yp2, out = pggb_run.run(np.stack([x,x],axis=1), FS, 48000, precision=64, bits=64, corner=22050)
    print("  PGGB: um=48000 -> output %d samples (expected 192000)." % len(yp2))
except Exception as e:
    print("  PGGB failed:", str(e)[:120])
y2 = engines.resample(x.reshape(-1,1), FS, 48000, "dpggb")
print("  Deep_PGGB: %d samples  OK" % len(y2))

print()
print("=== 3. speed, 30 s stereo 44.1 -> 176.4 ===")
x30 = np.random.default_rng(2).normal(0,0.1,(FS*30,2))
t0=time.time(); engines.resample(x30, FS, 176400, "dpggb"); d=time.time()-t0
print("  Deep_PGGB  %6.2f s = %5.0fx" % (d, 30.0/d))
t0=time.time(); pggb_run.run(x30, FS, 4, precision=64, bits=64, corner=22050, timeout=1800); d=time.time()-t0
print("  PGGB       %6.2f s = %5.0fx" % (d, 30.0/d))
