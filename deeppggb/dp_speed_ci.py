"""60 s stereo 44.1->88.2 speed with 5 repeats, median and 95% bootstrap CI."""
import json, os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import engines as E
from srctool import config  # noqa: F401

SRC, DST, SEC = 44100, 88200, 60.0
N = int(SRC * SEC)
k1 = (np.arange(N, dtype=np.int64) * 997) % SRC
k2 = (np.arange(N, dtype=np.int64) * 4999) % SRC
X = np.stack([0.5 * np.sin(2 * np.pi * k1 / SRC), 0.5 * np.sin(2 * np.pi * k2 / SRC)], axis=1)
RNG = np.random.default_rng(20261124)


def ci(vals, n=5000):
    v = np.asarray(vals, float)
    med = float(np.median(v))
    sims = np.array([np.median(RNG.choice(v, len(v), replace=True)) for _ in range(n)])
    return med, float(np.percentile(sims, 2.5)), float(np.percentile(sims, 97.5))


def main():
    out = {"seconds": SEC, "runs": 5, "engine": {}}
    for eng in ("dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"):
        ts = []
        try:
            for _ in range(5):
                t0 = time.perf_counter()
                E.resample(X, SRC, DST, eng)
                ts.append(time.perf_counter() - t0)
            med, lo, hi = ci([SEC / t for t in ts])
            out["engine"][eng] = {"speed_x": med, "ci95": [lo, hi],
                                  "times": ts, "runs_x": [SEC / t for t in ts]}
            print("%-6s %7.1f [%.1f, %.1f]" % (eng, med, lo, hi), flush=True)
        except Exception as exc:  # noqa: BLE001
            out["engine"][eng] = {"error": str(exc)}
            print("%-6s FAILED %s" % (eng, str(exc)[:80]), flush=True)
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work", "speed_ci_882.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("WROTE", p)


if __name__ == "__main__":
    main()
