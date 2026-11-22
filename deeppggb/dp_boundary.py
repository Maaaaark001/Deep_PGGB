"""dp_boundary.py - how much boundary treatment does a brick-wall resampler need?

The engine fades the file ends by 100 ms by default. That number was chosen
empirically (where the accuracy curve flattens), not derived, and it costs
0.1 s of audio at each end. This script measures the alternatives, including
ones that leave the audio completely untouched.

Strategies
  none      zero padding only (the honest "the file just ends" case)
  fade      multiply the first/last T of the audio by a window  (destroys T)
  constant  prepend/append K copies of the first/last sample   (destroys 0)
  hermite   prepend/append a cubic matching value and slope,
            decaying to zero over T, placed entirely in the padding (destroys 0)
"""
import os
import subprocess
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")


def run(x, src, dst, fade=0.0, taper="none"):
    td = tempfile.mkdtemp()
    fi, fo = os.path.join(td, "i.f64"), os.path.join(td, "o.f64")
    np.asarray(x, dtype="<f8").tofile(fi)
    cmd = [EXE, str(src), str(dst), fi, fo, "--ch", "1",
           "--block", "30", "--fade", str(fade), "--taper", taper,
           "--prec", "double", "--phase", "linear", "--threads", "0"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return np.fromfile(fo, "<f8")


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


def null_db(y, ref, frac=0.1, lag_search=2):
    """Interior null, minimised over a small integer lag (extension shifts the grid)."""
    n = min(len(y), len(ref))
    best = None
    for lag in range(-lag_search, lag_search + 1):
        if lag >= 0:
            yy, rr = y[lag:n], ref[0:n - lag]
        else:
            yy, rr = y[0:n + lag], ref[-lag:n]
        m = len(rr)
        a0, b0 = int(m * frac), int(m * (1 - frac))
        seg_y, seg_r = yy[a0:b0], rr[a0:b0]
        g = float(np.dot(seg_y, seg_r) / max(np.dot(seg_r, seg_r), 1e-300))
        e = seg_y - g * seg_r
        v = 20 * np.log10(np.sqrt((e ** 2).mean()) /
                          np.sqrt(((g * seg_r) ** 2).mean()) + 1e-300)
        if best is None or v < best:
            best = v
    return best


def const_extend(x, K):
    return np.concatenate([np.full(K, x[0]), x, np.full(K, x[-1])]), K


def hermite_extend(x, src, T_ms):
    """Cubic continuation matching value and slope, decaying to zero over T."""
    K = max(4, int(round(src * T_ms / 1000.0)))
    s = np.linspace(0.0, 1.0, K, endpoint=False)
    x0 = x[0]
    x1p = (x[1] - x[0]) * K
    head = (x1p - x0) * s ** 3 + (2 * x0 - x1p) * s ** 2
    xN = x[-1]
    xNp = (x[-1] - x[-2]) * K
    tail = ((xNp - xN) * s ** 3 + (2 * xN - xNp) * s ** 2)[::-1]
    return np.concatenate([head, x, tail]), K


def extract(y, K, n, src, dst):
    start = int(round(K * dst / float(src)))
    nout = int(round(n * dst / float(src)))
    if start + nout > len(y):
        y = np.concatenate([y, np.zeros(start + nout - len(y))])
    return y[start:start + nout]


def main():
    src, dst = 44100, 176400
    x, params = make_signal(src)
    n = len(x)
    ref = analytic(params, int(round(n * dst / src)), dst)
    print("signal: %d samples (%.2f s), x[0]=%.4f, x[-1]=%.4f, peak=%.3f"
          % (n, n / src, x[0], x[-1], np.abs(x).max()))
    print()
    print("%-10s %-14s %10s %10s" % ("strategy", "param", "null dB", "audio cut"))
    print("-" * 50)

    y = run(x, src, dst, fade=0.0, taper="none")
    print("%-10s %-14s %10.1f %10s" % ("none", "-", null_db(y, ref), "0 ms"))

    for ms in (0.5, 1, 2, 5, 10, 20, 50, 100, 200):
        y = run(x, src, dst, fade=ms, taper="smooth")
        print("%-10s %-14s %10.1f %10s"
              % ("fade", "smooth %g ms" % ms, null_db(y, ref), "%g ms" % ms))

    for K in (24, 128, 512, 2048, 4410):
        xe, Kk = const_extend(x, K)
        y = extract(run(xe, src, dst, fade=0.0, taper="none"), Kk, n, src, dst)
        print("%-10s %-14s %10.1f %10s"
              % ("constant", "K=%d" % K, null_db(y, ref), "0 ms"))

    for ms in (1, 5, 20, 100):
        xe, Kk = hermite_extend(x, src, ms)
        y = extract(run(xe, src, dst, fade=0.0, taper="none"), Kk, n, src, dst)
        print("%-10s %-14s %10.1f %10s"
              % ("hermite", "%g ms" % ms, null_db(y, ref), "0 ms"))


if __name__ == "__main__":
    main()
