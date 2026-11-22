"""dp_fade_coupling.py - is the fade length load-bearing for anything but the edge?

Two couplings I need to check before picking a default:

1. The fade length doubles as the block context length (T = fade). A shorter
   context means less room for the block's spectral surgery to settle, so the
   seam between blocks could get worse. Test: compare --block 0.5 against
   --block 30 (whole file); the difference is pure seam error.

2. The minimum-phase FIR is ntap = 4 * fade. A shorter fade means a shorter
   FIR, hence a wider transition band, hence worse min-phase accuracy near
   Nyquist. Test: min-phase passband at 21 / 21.5 / 22 kHz vs fade length.
"""
import os
import subprocess
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")
SRC, DST = 44100, 176400


def run(x, fade, block=30.0, phase="linear"):
    td = tempfile.mkdtemp()
    fi, fo = os.path.join(td, "i.f64"), os.path.join(td, "o.f64")
    np.asarray(x, dtype="<f8").tofile(fi)
    cmd = [EXE, str(SRC), str(DST), fi, fo, "--ch", "1", "--block", str(block),
           "--fade", str(fade), "--taper", "smooth", "--prec", "double",
           "--phase", phase, "--threads", "0"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return np.fromfile(fo, "<f8")


def tones(secs=4.0, ntones=40, seed=11):
    n = int(SRC * secs)
    rng = np.random.default_rng(seed)
    f = rng.uniform(200.0, 18000.0, ntones)
    ph = rng.uniform(0.0, 2 * np.pi, ntones)
    a = rng.uniform(0.5, 1.0, ntones)
    a *= 0.5 / a.sum()
    t = np.arange(n) / float(SRC)
    return sum(ai * np.sin(2 * np.pi * fi * t + pi)
               for ai, fi, pi in zip(a, f, ph))


def null_db(y, ref, frac=0.1):
    n = min(len(y), len(ref))
    a0, b0 = int(n * frac), int(n * (1 - frac))
    sy, sr = y[a0:b0], ref[a0:b0]
    g = float(np.dot(sy, sr) / max(np.dot(sr, sr), 1e-300))
    e = sy - g * sr
    return 20 * np.log10(np.sqrt((e ** 2).mean()) /
                         np.sqrt(((g * sr) ** 2).mean()) + 1e-300)


def gain_at(y, freq):
    """single-tone gain, measured on the steady interior"""
    n = int(DST * 2)
    seg = y[len(y) // 2: len(y) // 2 + n]
    w = np.hanning(len(seg))
    spec = np.abs(np.fft.rfft(seg * w))
    fr = np.fft.rfftfreq(len(seg), 1.0 / DST)
    i = int(np.argmin(np.abs(fr - freq)))
    return 20 * np.log10(spec[i] / spec[int(np.argmin(np.abs(fr - 1000.0)))] + 1e-300)


def main():
    x = tones()
    print("1) block seam error vs fade length (block 0.5 s vs block 30 s)")
    print("   %-8s %12s" % ("fade", "seam null"))
    for ms in (5, 10, 20, 50, 100):
        a = run(x, ms, block=0.5)
        b = run(x, ms, block=30.0)
        print("   %-8s %10.1f dB" % ("%g ms" % ms, null_db(a, b)))

    print()
    print("2) minimum-phase passband vs fade length (FIR is 4 x fade taps)")
    print("   %-8s %10s %10s %10s" % ("fade", "21 kHz", "21.5 kHz", "22 kHz"))
    for ms in (10, 20, 50, 100):
        # sweep a single tone at each frequency
        row = []
        for f in (21000.0, 21500.0, 22000.0):
            n = int(SRC * 4)
            t = np.arange(n) / float(SRC)
            x1 = 0.5 * np.sin(2 * np.pi * f * t)
            y = run(x1, ms, phase="min")
            row.append(gain_at(y, f))
        print("   %-8s " % ("%g ms" % ms) + " ".join("%10.2f" % v for v in row))


if __name__ == "__main__":
    main()
