"""Real stereo music check: block-wise vs single-block Deep_PGGB on a 2-minute track."""
import json
import os
import sys
import time

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from srctool import engines

SR, DST = 44100, 88200
TRACK = os.path.join(ROOT, "music", "Pixabay.mp3")
OUT = os.path.join(ROOT, "work", "music_check.json")
SECONDS = 120.0


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


def run(y, block):
    t0 = time.perf_counter()
    out = engines.resample(y, SR, DST, "dpggb", {"block": block})
    return out, time.perf_counter() - t0


def main():
    y, sr = sf.read(TRACK, dtype="float64", always_2d=True)
    assert sr == SR and y.shape[1] == 2, (sr, y.shape)
    y = np.ascontiguousarray(y[: int(SR * SECONDS)])
    raw_peak = float(np.max(np.abs(y)))
    y *= 0.99 / raw_peak
    res = {
        "track": "music/Pixabay.mp3",
        "source": "Pixabay royalty-free",
        "seconds": SECONDS,
        "src": SR,
        "dst": DST,
        "channels": 2,
        "input_frames": int(y.shape[0]),
        "input_peak_raw": raw_peak,
        "input_peak": float(np.max(np.abs(y))),
        "input_dc": float(np.mean(y, axis=0).tolist()[0]),
    }

    ref, t_ref = run(y, 130.0)
    res["single_block"] = {
        "wall_s": t_ref,
        "frames": int(ref.shape[0]),
        "length_drift": int(ref.shape[0] - round(y.shape[0] * DST / SR)),
        "peak": float(np.max(np.abs(ref))),
        "dc": [float(v) for v in np.mean(ref, axis=0)],
    }

    rows = []
    for block in (1.0, 4.0, 16.0):
        out, wall = run(y, block)
        nulls = [null_db(out[:, c], ref[:, c], skip=0.1, iters=3) for c in range(2)]
        rows.append({
            "block_s": block,
            "wall_s": wall,
            "null_db": nulls,
            "min_db": float(min(nulls)),
            "mean_db": float(np.mean(nulls)),
            "length_drift": int(out.shape[0] - ref.shape[0]),
        })
        del out
    res["blocks"] = rows

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
