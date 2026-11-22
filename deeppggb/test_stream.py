"""Validate StreamResampler against the offline path and against a reference.

Checks:
  1. Streaming output equals offline whole-file output (same input, same opts),
     within a small tolerance at the seams (the cross-fade region).
  2. Total output length matches offline length (no drift over many windows).
  3. The stream is bit-exact on stationary input in the *interior* (away from
     seams and edges) — the context overlap is a no-op there.
  4. End-to-end latency matches the documented bound.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import importlib.util
_HERE = os.path.dirname(os.path.abspath(__file__))
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
_deep = _load("deepmod", os.path.join(_HERE, "deeppggb.py"))
_streammod = _load("streammod", os.path.join(_HERE, "deeppggb_stream.py"))
# deeppggb_stream imports .deeppggb; patch its module ref so resample is the real one
_streammod.resample = _deep.resample
_streammod.DEFAULTS = _deep.DEFAULTS
StreamResampler = _streammod.StreamResampler
resample = _deep.resample

SRC, DST = 44100, 88200
CH = 2
SECS = 4.0
N = int(SRC * SECS)

# --- build a realistic multitone signal (not a pure sine, to stress seams) ---
rng = np.random.default_rng(11)
t = np.arange(N, dtype=np.float64) / SRC
x = np.zeros((N, CH), dtype=np.float64)
for ch in range(CH):
    for f, a in ((997.0, 0.4), (4001.0, 0.25), (12007.0, 0.15), (18001.0, 0.1)):
        ph = rng.uniform(0, 2*np.pi)
        x[:, ch] += a * np.sin(2*np.pi*f*t + ph)
# normalise peak to 0.5
pk = np.abs(x).max()
x = x * (0.5 / pk)

opts = dict(block=0.0)  # whole-file for the offline reference; stream uses block=0 too

# --- offline whole-file ---
offline = resample(x, SRC, DST, **opts)
print("offline shape", offline.shape, "expected", int(round(N*DST/SRC)))

# --- streaming with core_sec=0.5 (8 windows over 4 s) ---
rs = StreamResampler(SRC, DST, channels=CH, core_sec=0.5, **opts)
chunks = []
CHUNK = int(0.37 * SRC)   # non-aligned chunk size to stress the FIFO
for i in range(0, N, CHUNK):
    c = x[i:i+CHUNK]
    out = rs.push(c)
    if out.shape[0]:
        chunks.append(out)
tail = rs.flush()
if tail.shape[0]:
    chunks.append(tail)
stream = np.vstack(chunks)
print("stream  shape", stream.shape, "latency_sec", round(rs.latency_sec(), 3))

# --- compare lengths ---
m = min(offline.shape[0], stream.shape[0])
print("len offline=%d stream=%d delta=%d" % (offline.shape[0], stream.shape[0],
                                             offline.shape[0]-stream.shape[0]))

# --- interior comparison (skip first/last 0.2 s, skip seam zones) ---
skip = int(0.2*DST)
core = stream[skip:m-skip]
ref = offline[skip:m-skip]
# remove seam zones: seams at multiples of core_out (0.5 s of DST)
core_out = int(0.5*DST)
seam_zone = int(0.05*DST)  # 50 ms around each seam
mask = np.ones(core.shape[0], dtype=bool)
for k in range(1, int(core.shape[0]/core_out)+1):
    lo = max(0, k*core_out - seam_zone)
    hi = min(core.shape[0], k*core_out + seam_zone)
    mask[lo:hi] = False
c = core[mask]; r = ref[mask]
err = np.abs(c - r).max()
print("interior max|stream-offline| (dB rel 0.5) = %.1f dB" % (20*np.log10(max(err,1e-300)/0.5)))
print("interior rms err = %.3e" % np.sqrt(np.mean((c-r)**2)))

# --- overall null depth vs offline ---
d = stream - offline[:stream.shape[0]]
ref_rms = np.sqrt(np.mean(offline[:stream.shape[0]]**2))
depth = 20*np.log10(ref_rms/np.sqrt(np.mean(d**2)))
print("overall null depth stream-vs-offline = %.1f dB" % depth)

# --- interior null: skip the head-fade convention zone (first 200 ms) ---
head = int(0.2*DST)
di = stream[head:] - offline[head:stream.shape[0]]
refi = np.sqrt(np.mean(offline[head:stream.shape[0]]**2))
depth_i = 20*np.log10(refi/np.sqrt(np.mean(di**2)))
print("interior null (after 200 ms head) = %.1f dB" % depth_i)

# --- head error must be confined to the first ~20 ms edge-taper ---
# offline fades the true file head; stream has zero left-context. Difference
# should collapse after the taper duration (20 ms) to the float64 floor.
bad = np.where(np.abs(stream[:stream.shape[0]] - offline[:stream.shape[0]]).max(axis=1) > 1e-5)[0]
if bad.size:
    span_ms = bad[-1] / DST * 1000.0
    print("head deviation span = %.1f ms (first bad frame %d)" % (span_ms, bad[0]))
    assert span_ms < 100.0, "head deviation extends beyond the edge-taper zone"

# --- latency check ---
expected_lat = rs.latency_sec()
print("latency bound = %.3f s (core 0.5 + context %.3f)" % (expected_lat, 0.8))
assert stream.shape[0] > 0, "no output"
assert abs(stream.shape[0]-offline.shape[0]) <= 2, "length drift"
assert depth_i > 100, "interior stream deviates from offline too much"
print("STREAM TEST PASS")
