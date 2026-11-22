"""Validate the native C++ streaming backend against the Python FIFO and offline path.

Checks:
  1. Native push/flush length equals the offline length (no drift).
  2. Native output is bit-identical to the Python StreamResampler on the same chunks.
  3. Interior native-vs-offline null is >100 dB (the head-fade convention is the
     only intentional difference).
  4. latency_sec() is core + context.
"""
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import importlib.util as ilu

here = os.path.dirname(os.path.abspath(__file__))
def load(name, path):
    s = ilu.spec_from_file_location(name, path)
    m = ilu.module_from_spec(s); s.loader.exec_module(m); return m
st = load("st", os.path.join(here, "deeppggb_stream.py"))
deep = load("deep", os.path.join(here, "deeppggb.py"))
st.DEFAULTS = deep.DEFAULTS
st.resample = deep.resample

SR, DST, CH = 44100, 88200, 2
N = SR * 4
rng = np.random.default_rng(11); t = np.arange(N) / SR
x = np.zeros((N, CH))
for ch in range(CH):
    for f, a in ((997.0, 0.4), (4001.0, 0.25), (12007.0, 0.15), (18001.0, 0.1)):
        x[:, ch] += a * np.sin(2*np.pi*f*t + rng.uniform(0, 2*np.pi))
x *= 0.5 / np.abs(x).max()
x = np.ascontiguousarray(x)

def run(r):
    chunks = []
    for i in range(0, N, int(0.37*SR)):
        o = r.push(x[i:i+int(0.37*SR)])
        if o.shape[0]: chunks.append(o)
    o = r.flush()
    if o.shape[0]: chunks.append(o)
    return np.vstack(chunks)

py = run(st.StreamResampler(SR, DST, CH, core_sec=1.0, block=0.0))
nat_r = st.NativeStreamResampler(SR, DST, CH, core_sec=1.0, block=0.0)
lat = nat_r.latency_sec()
nat = run(nat_r); nat_r.close()
off = deep.resample(x, SR, DST, block=0.0)

assert nat.shape == py.shape == off.shape, (nat.shape, py.shape, off.shape)
assert np.array_equal(nat, py), "native and Python FIFO differ"
head = int(0.2*DST)
d = nat[head:] - off[head:]
ref = np.sqrt(np.mean(off[head:]**2))
null = 20*np.log10(ref/np.sqrt(np.mean(d**2)))
print("length", nat.shape, "native-vs-python bit-exact", np.array_equal(nat, py))
print("native-vs-offline interior null %.1f dB, max err %.3e" % (null, np.abs(d).max()))
print("latency %.3f s" % lat)
assert null > 100.0, null
assert abs(lat - 1.8) < 0.02, lat
print("NATIVE STREAM TEST PASS")
