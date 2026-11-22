"""dp_fade_default.py - confirm the new 50 ms default costs nothing.

Two questions:
  1. does 50 ms still reach the same null depth as 100 ms on long material?
  2. on short files, where does 20 ms start to fall short?
"""
import os
import subprocess
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")


def run(x, src, dst, fade):
    td = tempfile.mkdtemp()
    fi, fo = os.path.join(td, "i.f64"), os.path.join(td, "o.f64")
    np.asarray(x, dtype="<f8").tofile(fi)
    r = subprocess.run([EXE, str(src), str(dst), fi, fo, "--ch", "1",
                        "--block", "30", "--fade", str(fade), "--taper", "smooth",
                        "--prec", "double", "--phase", "linear", "--threads", "0"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return np.fromfile(fo, "<f8")


def tones(src, secs, ntones=40, seed=11):
    n = int(src * secs)
    rng = np.random.default_rng(seed)
    f = rng.uniform(200.0, 18000.0, ntones)
    ph = rng.uniform(0.0, 2 * np.pi, ntones)
    a = rng.uniform(0.5, 1.0, ntones)
    a *= 0.5 / a.sum()
    t = np.arange(n) / float(src)
    return sum(ai * np.sin(2 * np.pi * fi * t + pi)
               for ai, fi, pi in zip(a, f, ph)), (f, ph, a)


def analytic(p, nout, dst):
    f, ph, a = p
    t = np.arange(nout) / float(dst)
    return sum(ai * np.sin(2 * np.pi * fi * t + pi) for ai, fi, pi in zip(a, f, ph))


def null_db(y, ref, frac=0.1):
    n = min(len(y), len(ref))
    a0, b0 = int(n * frac), int(n * (1 - frac))
    sy, sr = y[a0:b0], ref[a0:b0]
    g = float(np.dot(sy, sr) / max(np.dot(sr, sr), 1e-300))
    e = sy - g * sr
    return 20 * np.log10(np.sqrt((e ** 2).mean()) /
                         np.sqrt(((g * sr) ** 2).mean()) + 1e-300)


def main():
    print("1) long material (10 s), 50 ms default, several ratios")
    for src, dst in ((44100, 176400), (44100, 48000), (48000, 44100),
                     (44100, 96000), (96000, 44100)):
        x, p = tones(src, 10.0)
        ref = analytic(p, int(round(len(x) * dst / src)), dst)
        print("   %6d -> %6d   %8.1f dB" % (src, dst, null_db(run(x, src, dst, 50), ref)))

    print()
    print("2) short files: where does 20 ms start to lose?")
    print("   %-8s %10s %10s %10s" % ("length", "20 ms", "50 ms", "100 ms"))
    for secs in (0.5, 1.0, 2.0, 4.0):
        x, p = tones(44100, secs)
        ref = analytic(p, int(round(len(x) * 4)), 176400)
        vals = [null_db(run(x, 44100, 176400, ms), ref) for ms in (20, 50, 100)]
        print("   %-8s " % ("%.1f s" % secs) + " ".join("%10.1f" % v for v in vals))


if __name__ == "__main__":
    main()
