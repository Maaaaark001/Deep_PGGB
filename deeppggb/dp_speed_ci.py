"""60 s stereo 44.1->88.2 speed: interleaved rounds, median and 95% bootstrap CI.

Why interleaved: this machine (i5-7500T, 35 W) loses up to 30% of its clock after a
few minutes of full load.  Running one engine five times in a row and then the next
turns that drift into a ranking artefact -- the engine measured last looks slow.  So
every timed round runs all eight engines once, in the same order, and an engine's
spread across rounds carries the drift instead of its position in the file.

Protocol: one untimed warm-up pass (allocator / page cache / plan creation), then
ROUNDS timed rounds.  Speed = input seconds / wall seconds.
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import engines as E
from srctool import config  # noqa: F401

SRC, DST, SEC = 44100, 88200, 60.0
N = int(SRC * SEC)
ROUNDS = int(os.environ.get("DP_CI_ROUNDS", "7"))
ENGINES = ("dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy")

k1 = (np.arange(N, dtype=np.int64) * 997) % SRC
k2 = (np.arange(N, dtype=np.int64) * 4999) % SRC
X = np.stack([0.5 * np.sin(2 * np.pi * k1 / SRC), 0.5 * np.sin(2 * np.pi * k2 / SRC)], axis=1)
RNG = np.random.default_rng(20261124)


def ci(vals, n=5000):
    v = np.asarray(vals, float)
    med = float(np.median(v))
    sims = np.array([np.median(RNG.choice(v, len(v), replace=True)) for _ in range(n)])
    return med, float(np.percentile(sims, 2.5)), float(np.percentile(sims, 97.5))


def once(eng):
    t0 = time.perf_counter()
    E.resample(X, SRC, DST, eng)
    return time.perf_counter() - t0


def main():
    out = {"seconds": SEC, "runs": ROUNDS, "order": "interleaved", "engine": {}}
    live = []
    for eng in ENGINES:                      # warm-up, untimed
        try:
            once(eng)
            live.append(eng)
        except Exception as exc:  # noqa: BLE001
            out["engine"][eng] = {"error": str(exc)}
            print("%-6s FAILED %s" % (eng, str(exc)[:80]), flush=True)

    times = {eng: [] for eng in live}
    for r in range(ROUNDS):
        for eng in live:
            times[eng].append(once(eng))
        print("round %d/%d done" % (r + 1, ROUNDS), flush=True)

    # Drift index: per round, the geometric mean of each engine's speed divided by its
    # own median.  A flat series means the machine held its clock for the whole run;
    # a rising series means it was still throttled when the run started.
    drift = []
    for r in range(ROUNDS):
        rel = []
        for eng in live:
            xs = [SEC / t for t in times[eng]]
            rel.append(xs[r] / float(np.median(xs)))
        drift.append(round(float(np.exp(np.mean(np.log(rel)))), 3))
    print("drift per round: %s" % drift, flush=True)
    out["drift_index"] = drift

    for eng in live:
        ts = times[eng]
        xs = [SEC / t for t in ts]
        med, lo, hi = ci(xs)
        out["engine"][eng] = {"speed_x": med, "ci95": [lo, hi],
                              "times": ts, "runs_x": xs}
        print("%-6s %7.1f [%.1f, %.1f]  spread %5.1f%%"
              % (eng, med, lo, hi, 100.0 * (max(xs) - min(xs)) / med), flush=True)

    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "work", "speed_ci_882.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("WROTE", p)


if __name__ == "__main__":
    main()
