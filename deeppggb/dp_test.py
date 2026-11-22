"""dp_test.py - Deep_PGGB correctness harness.

Reference = analytic evaluation of the same tone sum on the output grid.
Every tone is below 18 kHz, so a perfect resampler must reproduce that sum
exactly; any residual is engine error. Interior window (10-90%) excludes
start-up transients, isolating steady-state accuracy."""
import os
import subprocess
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")


def run(x, src, dst, ch=1, block=30.0, fade=100.0, prec=0, phase=0, threads=0,
        mode="raw", bits=24, ns=0, dsd=64, dsd_order=5):
    td = tempfile.mkdtemp()
    fi, fo = os.path.join(td, "i.f64"), os.path.join(td, "o.f64")
    np.asarray(x, dtype="<f8").tofile(fi)
    cmd = [EXE, str(src), str(dst), fi, fo, "--ch", str(ch), "--block", str(block),
           "--fade", str(fade), "--prec", "long" if prec else "double",
           "--phase", "min" if phase else "linear", "--threads", str(threads),
           "--mode", mode, "--bits", str(bits), "--ns", str(ns),
           "--dsd", str(dsd), "--dsd-order", str(dsd_order)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-900:])
    if mode == "raw":
        return np.fromfile(fo, "<f8"), r.stderr
    return np.fromfile(fo, np.uint8), r.stderr


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


def interior_null(y, ref, frac=0.1):
    n = min(len(y), len(ref))
    a, b = int(n * frac), int(n * (1 - frac))
    yy, rr = y[a:b], ref[a:b]
    g = float(np.dot(yy, rr) / np.dot(rr, rr))
    e = yy - g * rr
    return 20 * np.log10(np.sqrt((e ** 2).mean()) / np.sqrt(((g * rr) ** 2).mean()) + 1e-300)


def main():
    src, dst = 44100, 176400
    x, params = make_signal(src)
    y, log = run(x, src, dst)
    ref = analytic(params, len(y), dst)
    print("len in %d out %d expect %d" % (len(x), len(y), len(ref)))
    print("null (interior) %.1f dB" % interior_null(y, ref))
    print("peak in %.4f out %.4f" % (np.abs(x).max(), np.abs(y).max()))
    print(log.strip())


if __name__ == "__main__":
    main()
