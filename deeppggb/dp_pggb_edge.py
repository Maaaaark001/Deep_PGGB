"""dp_pggb_edge.py - what does PGGB actually do at the file boundary?

Earlier I inferred "PGGB does a 0.6 ms zero-order hold at the head" from the
first 24 output samples of its impulse response, and wrote that up as its
boundary treatment. That was an over-claim: 24 samples is what you can *see*
in a step response, not proof of how long the preprocessing runs.

This measures it directly. Run a signal through PGGB, then compute the null
against the analytic reference in windows at increasing distance from each
edge. If PGGB tapers, the near-edge windows are dirty and the interior is
clean; the distance at which it becomes clean is the taper length.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src_bench"))
import pggb_run


def make_signal(src, secs=4.0, ntones=40, seed=11, fmax=18000.0, amp=0.5):
    n = int(src * secs)
    rng = np.random.default_rng(seed)
    f = rng.uniform(200.0, fmax, ntones)
    ph = rng.uniform(0.0, 2 * np.pi, ntones)
    a = rng.uniform(0.5, 1.0, ntones)
    a *= amp / a.sum()
    t = np.arange(n) / float(src)
    x = sum(ai * np.sin(2 * np.pi * fi * t + pi) for ai, fi, pi in zip(a, f, ph))
    return x, (f, ph, a)


def analytic(params, nout, fo):
    f, ph, a = params
    t = np.arange(nout) / float(fo)
    return sum(ai * np.sin(2 * np.pi * fi * t + pi) for ai, fi, pi in zip(a, f, ph))


def window_null(y, ref, start, length):
    sy = y[start:start + length]
    sr = ref[start:start + length]
    if len(sr) < length:
        return None
    g = float(np.dot(sy, sr) / max(np.dot(sr, sr), 1e-300))
    e = sy - g * sr
    return 20 * np.log10(np.sqrt((e ** 2).mean()) /
                         np.sqrt(((g * sr) ** 2).mean()) + 1e-300)


def main():
    src, dst = 44100, 176400
    x, params = make_signal(src)
    y2, log = pggb_run.run(x, src, um=4, bits=64, workers=2)
    y = np.asarray(y2[:, 0], dtype=np.float64)
    ref = analytic(params, len(y), dst)
    print("in %d out %d expect %d" % (len(x), len(y), int(round(len(x) * dst / src))))
    print()
    print("window position            null dB")
    print("-" * 42)
    win = int(dst * 0.05)          # 50 ms windows
    for ms in (0, 10, 20, 50, 100, 200, 400, 800, 1600):
        off = int(dst * ms / 1000.0)
        v = window_null(y, ref, off, win)
        print("head +%-6d ms          %8.1f" % (ms, v if v is not None else float("nan")))
    print()
    for ms in (0, 10, 20, 50, 100, 200, 400, 800, 1600):
        off = int(dst * ms / 1000.0)
        v = window_null(y, ref, len(y) - win - off, win)
        print("tail -%-6d ms          %8.1f" % (ms, v if v is not None else float("nan")))


if __name__ == "__main__":
    main()
