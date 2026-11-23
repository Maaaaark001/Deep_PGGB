"""Eight-channel check for Deep_PGGB: per-channel null, crosstalk, throughput, streaming."""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from srctool import engines


def null_db(y, ref, skip=0.1, iters=3):
    m = min(len(y), len(ref))
    e = int(skip * m)
    a = np.asarray(y[e:m - e], dtype=np.float64)
    b = np.asarray(ref[e:m - e], dtype=np.float64)
    g = float(np.dot(a, b) / max(np.dot(b, b), 1e-300))
    bb = float(np.dot(b, b))
    for _ in range(iters):
        d = a - g * b
        g += float(np.dot(d, b) / max(bb, 1e-300))
    d = a - g * b
    return 20 * np.log10(max(float(np.sqrt(np.mean(b * b))), 1e-300) /
                         max(float(np.sqrt(np.mean(d * d))), 1e-300))

SR, DST, CH = 44100, 88200, 8
FREQS = [997, 3001, 5003, 7001, 9001, 11003, 13001, 15001]
AMP = 0.10
OUT = os.path.join(ROOT, "work", "multichannel.json")


def tones(dur, freqs):
    n = int(round(SR * dur))
    idx = np.arange(n, dtype=np.int64)
    y = np.empty((n, len(freqs)), dtype=np.float64)
    for j, f in enumerate(freqs):
        k = (int(f) * idx) % SR
        y[:, j] = AMP * np.sin(2.0 * np.pi * k / SR + 0.13 * j)
    return y


def reference(n, freqs):
    m = np.arange(n, dtype=np.int64)
    r = np.empty((n, len(freqs)), dtype=np.float64)
    for j, f in enumerate(freqs):
        k = (int(f) * m) % DST
        r[:, j] = AMP * np.sin(2.0 * np.pi * k / DST + 0.13 * j)
    return r


def run(y, block=16.0):
    t0 = time.perf_counter()
    out = engines.resample(y, SR, DST, "dpggb", {"block": block})
    wall = time.perf_counter() - t0
    return out, wall


def main():
    res = {"channels": CH, "src": SR, "dst": DST, "freqs": FREQS, "amp": AMP}

    y16 = tones(16.0, FREQS)
    out16, wall16 = run(y16, 16.0)
    ref16 = reference(out16.shape[0], FREQS)
    nulls = [null_db(out16[:, j], ref16[:, j], skip=0.1, iters=3) for j in range(CH)]
    res["offline_16s"] = {
        "wall_s": wall16,
        "frames": int(out16.shape[0]),
        "null_db": nulls,
        "min_db": float(min(nulls)),
        "mean_db": float(np.mean(nulls)),
        "length_drift": int(out16.shape[0] - round(y16.shape[0] * DST / SR)),
    }

    # crosstalk: excite only channel 0, other channels must stay at zero
    yx = np.zeros_like(y16)
    yx[:, 0] = y16[:, 0]
    outx, _ = run(yx, 16.0)
    leak = float(np.max(np.abs(outx[:, 1:]))) / max(float(np.max(np.abs(outx[:, 0]))), 1e-300)
    res["crosstalk"] = {
        "leak_abs": float(np.max(np.abs(outx[:, 1:]))),
        "leak_rel_db": (20.0 * np.log10(leak) if leak > 0 else None),
    }

    # 60 s throughput, block 16 s, best of two
    y60 = tones(60.0, FREQS)
    times = []
    for _ in range(2):
        out60, wall = run(y60, 16.0)
        times.append(wall)
    best = min(times)
    res["offline_60s"] = {
        "wall_s": best,
        "x_realtime": 60.0 / best,
        "frames": int(out60.shape[0]),
        "length_drift": int(out60.shape[0] - round(y60.shape[0] * DST / SR)),
    }

    # streaming: 60 s throughput and 16 s match against offline
    from deeppggb_stream import NativeStreamResampler

    def stream_run(y, chunk=1024):
        st = NativeStreamResampler(SR, DST, channels=CH, core_sec=1.0)
        t0 = time.perf_counter()
        pieces = []
        first = None
        for i in range(0, y.shape[0], chunk):
            o = st.push(y[i:i + chunk])
            if o.shape[0] and first is None:
                first = (i + chunk) / float(SR)
            pieces.append(o)
        pieces.append(st.flush())
        wall = time.perf_counter() - t0
        return np.vstack([p for p in pieces if p.shape[0]]), wall, first

    ys = tones(16.0, FREQS)
    outs, wall_s16, first16 = stream_run(ys)
    n = min(outs.shape[0], out16.shape[0])
    snull = [null_db(outs[:n, j], ref16[:n, j], skip=0.1, iters=3) for j in range(CH)]
    res["stream_16s"] = {
        "wall_s": wall_s16,
        "frames": int(outs.shape[0]),
        "first_out_s": first16,
        "null_db": snull,
        "min_db": float(min(snull)),
        "length_drift": int(outs.shape[0] - round(ys.shape[0] * DST / SR)),
    }

    y60s = tones(60.0, FREQS)
    out60s, wall60s, first60 = stream_run(y60s)
    res["stream_60s"] = {
        "wall_s": wall60s,
        "x_realtime": 60.0 / wall60s,
        "frames": int(out60s.shape[0]),
        "first_out_s": first60,
        "length_drift": int(out60s.shape[0] - round(y60s.shape[0] * DST / SR)),
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
