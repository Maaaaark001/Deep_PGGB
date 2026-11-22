"""dp_exact_verify.py - is 301 dB real? Cross-check three ways.

1. A single pure tone, exact reference, several frequencies.
2. Long double mode: if float64-limited, long double should go further.
3. A round trip 44.1 -> 176.4 -> 44.1 against the ORIGINAL samples (not analytic).
   A round trip must be exact if the filter is a true ideal brick wall, and it
   shares no code path with the analytic reference.
"""
import sys
import numpy as np
sys.path.insert(0, r"C:\Users\Administrator\Documents\Python_Code\src")
from srctool import engines

def exact_tone(f, fs, n, ph=0.0, amp=0.5):
    idx = np.arange(n, dtype=np.int64)
    k = (int(f)*idx) % fs
    return amp*np.sin(2*np.pi*(k/float(fs)) + ph)

def null_db(y, ref, skip=0.1):
    m = min(len(y), len(ref))
    e = int(skip*m)
    y = y[e:m-e]; ref = ref[e:m-e]
    d = y-ref
    return 20*np.log10(np.sqrt(np.mean(ref*ref))/max(np.sqrt(np.mean(d*d)), 1e-300))

print("1. single tone, exact reference, 44.1 -> 176.4, 4 s")
for f in (997, 5000, 15000, 17999):
    n = 44100*4
    x = exact_tone(f, 44100, n).reshape(-1,1)
    y = np.asarray(engines.resample(x, 44100, 176400, "dpggb")[:,0], dtype=np.float64)
    ref = exact_tone(f, 176400, int(round(n*4)))
    print("   %6d Hz : %7.1f dB" % (f, null_db(y, ref)))

print()
print("2. precision: double vs long, 40-tone analytic reference")
rng = np.random.default_rng(5)
freqs = np.sort(rng.choice(np.arange(200,18001),40,replace=False)).astype(np.int64)
phs = rng.uniform(0,2*np.pi,40); amps = rng.uniform(0.05,0.5,40); amps = amps/amps.sum()*1.6
def build(fs, n):
    idx = np.arange(n, dtype=np.int64); y = np.zeros(n)
    for f,p,a in zip(freqs,phs,amps):
        y += a*np.sin(2*np.pi*(((f*idx)%fs)/float(fs)) + p)
    return y
n = 44100*4
x = build(44100, n).reshape(-1,1)
ref = build(176400, int(round(n*4)))
for prec in ("double","long"):
    y = np.asarray(engines.resample(x, 44100, 176400, "dpggb", {"prec": prec})[:,0], dtype=np.float64)
    print("   prec %-6s : %7.1f dB" % (prec, null_db(y, ref)))

print()
print("3. round trip 44.1 -> 176.4 -> 44.1 vs the ORIGINAL samples")
for f in (997, 15000):
    n = 44100*4
    x0 = exact_tone(f, 44100, n)
    up = np.asarray(engines.resample(x0.reshape(-1,1), 44100, 176400, "dpggb")[:,0], dtype=np.float64)
    back = np.asarray(engines.resample(up.reshape(-1,1), 176400, 44100, "dpggb")[:,0], dtype=np.float64)
    print("   %6d Hz : %7.1f dB (n=%d -> %d)" % (f, null_db(back, x0), len(x0), len(back)))
