"""Cross-engine benchmark on real stereo music and 8-channel synthetic tones."""
import json, os, sys, time
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from srctool import engines

SR, DST = 44100, 88200
TRACK = os.path.join(ROOT, "music", "Pixabay.mp3")
OUT = os.path.join(ROOT, "work", "engine_music_8ch.json")
ENG = ["dpggb", "pggb", "r8b", "soxng", "soxr", "swr", "ssrc", "scipy"]
CH = 8
FREQS = [997, 3001, 5003, 7001, 9001, 11003, 13001, 15001]
AMP = 0.10
RNG = np.random.default_rng(12345)


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


def boot_ci(vals, n=5000):
    vals = np.asarray(vals, dtype=float)
    med = float(np.median(vals))
    if len(vals) <= 1:
        return med, med, med
    sims = np.array([np.median(RNG.choice(vals, len(vals), replace=True)) for _ in range(n)])
    return med, float(np.percentile(sims, 2.5)), float(np.percentile(sims, 97.5))


def summary(vals):
    med, lo, hi = boot_ci(vals)
    return {"median": med, "ci95": [lo, hi], "runs": [float(v) for v in vals], "n": len(vals)}


def tones(dur, freqs, sr=SR):
    n = int(round(sr * dur))
    idx = np.arange(n, dtype=np.int64)
    y = np.empty((n, len(freqs)), dtype=np.float64)
    for j, f in enumerate(freqs):
        k = (int(f) * idx) % sr
        y[:, j] = AMP * np.sin(2.0 * np.pi * k / sr + 0.13 * j)
    return y


def reference(n, freqs, sr=DST):
    m = np.arange(n, dtype=np.int64)
    r = np.empty((n, len(freqs)), dtype=np.float64)
    for j, f in enumerate(freqs):
        k = (int(f) * m) % sr
        r[:, j] = AMP * np.sin(2.0 * np.pi * k / sr + 0.13 * j)
    return r


def timed(fn, n):
    ts = []
    out = None
    for _ in range(n):
        t0 = time.perf_counter()
        out = fn()
        ts.append(time.perf_counter() - t0)
    return out, ts


def chunked(y, key, block_s, nch):
    parts, ts = [], []
    step = int(round(block_s * SR))
    for i in range(0, y.shape[0], step):
        x = y[i:i + step]
        t0 = time.perf_counter()
        o = engines.resample(x, SR, DST, key)
        ts.append(time.perf_counter() - t0)
        parts.append(o)
    return np.vstack(parts), float(sum(ts))


def quality(out, ref):
    n = min(len(out), len(ref))
    vals = [null_db(out[:n, c], ref[:n, c]) for c in range(out.shape[1])]
    return {"per_channel": vals, "min": float(min(vals)), "mean": float(np.mean(vals))}


def main():
    y, sr = sf.read(TRACK, dtype="float64", always_2d=True)
    assert sr == SR and y.shape[1] == 2
    y = np.ascontiguousarray(y[: int(SR * 120.0)])
    y *= 0.99 / float(np.max(np.abs(y)))
    res = {"source": "music/Pixabay.mp3", "seconds": 120.0, "src": SR, "dst": DST,
           "channels": 2, "engines": {}}

    for key in ENG:
        print("music", key, flush=True)
        rec = {}
        try:
            full_opts = {"block": 130.0} if key == "dpggb" else None
            full, tf = timed(lambda: engines.resample(y, SR, DST, key, full_opts), 5)
            rec["full_s"] = summary(tf)
            rec["full_speed_x"] = 120.0 / float(np.median(tf))
            rec["full_speed_ci_x"] = [120.0 / rec["full_s"]["ci95"][1],
                                      120.0 / rec["full_s"]["ci95"][0]]
            rec["full_frames"] = int(full.shape[0])
        except Exception as exc:
            rec["error_full"] = str(exc)
            res["engines"][key] = rec
            continue

        try:
            ch, tc = timed(lambda: chunked(y, key, 16.0, 2)[0], 5)
            rec["chunk16_s"] = summary(tc)
            rec["chunk16_speed_x"] = 120.0 / float(np.median(tc))
            rec["chunk16_speed_ci_x"] = [120.0 / rec["chunk16_s"]["ci95"][1],
                                         120.0 / rec["chunk16_s"]["ci95"][0]]
            rec["chunk16_frames"] = int(ch.shape[0])
            rec["chunk16_null"] = quality(ch, full)
        except Exception as exc:
            rec["error_chunk"] = str(exc)

        if key == "dpggb":
            try:
                nat, tn = timed(lambda: engines.resample(y, SR, DST, key, {"block": 16.0}), 5)
                rec["native16_s"] = summary(tn)
                rec["native16_speed_x"] = 120.0 / float(np.median(tn))
                rec["native16_speed_ci_x"] = [120.0 / rec["native16_s"]["ci95"][1],
                                              120.0 / rec["native16_s"]["ci95"][0]]
                rec["native16_frames"] = int(nat.shape[0])
                rec["native16_null"] = quality(nat, full)
            except Exception as exc:
                rec["error_native"] = str(exc)
        res["engines"][key] = rec

    # 8-channel synthetic: absolute null against analytic reference and 60 s throughput
    y16 = tones(16.0, FREQS)
    ref16 = reference(int(round(16.0 * DST)), FREQS)
    y60 = tones(60.0, FREQS)
    res["eight_channel"] = {"channels": CH, "freqs": FREQS, "amp": AMP,
                            "src": SR, "dst": DST, "engines": {}}
    for key in ENG:
        print("8ch", key, flush=True)
        rec = {}
        try:
            out16, t16 = timed(lambda: engines.resample(y16, SR, DST, key), 3)
            rec["quality16_s"] = summary(t16)
            rec["quality16_frames"] = int(out16.shape[0])
            rec["null16"] = quality(out16, ref16[:out16.shape[0]])
        except Exception as exc:
            rec["error_quality"] = str(exc)
        try:
            out60, t60 = timed(lambda: engines.resample(y60, SR, DST, key), 3)
            rec["speed60_s"] = summary(t60)
            rec["speed60_x"] = 60.0 / float(np.median(t60))
            rec["speed60_ci_x"] = [60.0 / rec["speed60_s"]["ci95"][1],
                                    60.0 / rec["speed60_s"]["ci95"][0]]
            rec["speed60_frames"] = int(out60.shape[0])
        except Exception as exc:
            rec["error_speed"] = str(exc)
        res["eight_channel"]["engines"][key] = rec

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
