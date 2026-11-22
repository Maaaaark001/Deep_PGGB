"""dp_final_verify.py - full regression after the speed work.

Covers: accuracy across ratios, stereo, short files, min-phase, and the
block/worker defaults that are about to become the shipped values.
"""
import os
import subprocess
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")


def run(x, src, dst, block=1.0, workers=0, phase="linear", context=100, fade=20):
    td = tempfile.mkdtemp()
    fi, fo = os.path.join(td, "i.f64"), os.path.join(td, "o.f64")
    x2 = x if x.ndim == 2 else x[:, None]
    x2.astype("<f8").tofile(fi)
    r = subprocess.run([EXE, str(src), str(dst), fi, fo, "--ch", str(x2.shape[1]),
                        "--block", str(block), "--fade", str(fade), "--context", str(context),
                        "--taper", "smooth", "--prec", "double", "--phase", phase,
                        "--threads", "0", "--workers", str(workers)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return np.fromfile(fo, "<f8").reshape(-1, x2.shape[1])


def tones(src, secs=4.0, ntones=40, seed=11):
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
    print("1) accuracy across ratios (block 1 s, workers auto)")
    for src, dst in ((44100, 176400), (44100, 48000), (48000, 44100),
                     (44100, 96000), (96000, 44100), (44100, 88200)):
        x, p = tones(src)
        ref = analytic(p, int(round(len(x) * dst / src)), dst)
        print("   %6d -> %6d  %8.1f dB" % (src, dst, null_db(run(x, src, dst)[:, 0], ref)))

    print()
    print("2) stereo: both channels independent and correct")
    xl, p = tones(44100)
    xr = 0.4 * xl
    y = run(np.stack([xl, xr], axis=1), 44100, 176400)
    ref = analytic(p, len(y), 176400)
    print("   L %8.1f dB   R %8.1f dB" % (null_db(y[:, 0], ref), null_db(y[:, 1], 0.4 * ref)))

    print()
    print("3) short file (0.3 s) still safe")
    xs, ps = tones(44100, 0.3)
    print("   %8.1f dB" % null_db(run(xs, 44100, 176400)[:, 0],
                                  analytic(ps, int(round(len(xs) * 4)), 176400)))

    print()
    print("4) minimum phase runs and is stable")
    x, p = tones(44100)
    y = run(x, 44100, 176400, phase="min")
    print("   frames %d, finite %s, peak %.3f" %
          (len(y), np.isfinite(y).all(), np.abs(y).max()))


if __name__ == "__main__":
    main()
