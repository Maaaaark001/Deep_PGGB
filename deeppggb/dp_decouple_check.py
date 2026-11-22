"""dp_decouple_check.py - verify the fade/context/min-phase split actually works.

Goal: 20 ms fade (kills the boundary step) + 100 ms context (clean block seams)
+ 50 ms min-phase FIR (sharp transition), all independent.
"""
import os
import subprocess
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")
SRC, DST = 44100, 176400


def run(x, fade=20, context=100, block=30.0, phase="linear", mptaps=50):
    td = tempfile.mkdtemp()
    fi, fo = os.path.join(td, "i.f64"), os.path.join(td, "o.f64")
    np.asarray(x, dtype="<f8").tofile(fi)
    cmd = [EXE, str(SRC), str(DST), fi, fo, "--ch", "1", "--block", str(block),
           "--fade", str(fade), "--context", str(context), "--mptaps", str(mptaps),
           "--taper", "smooth", "--prec", "double", "--phase", phase, "--threads", "0"]
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
               for ai, fi, pi in zip(a, f, ph)), (f, ph, a)


def analytic(p, nout):
    f, ph, a = p
    t = np.arange(nout) / float(DST)
    return sum(ai * np.sin(2 * np.pi * fi * t + pi) for ai, fi, pi in zip(a, f, ph))


def null_db(y, ref, frac=0.1):
    n = min(len(y), len(ref))
    a0, b0 = int(n * frac), int(n * (1 - frac))
    sy, sr = y[a0:b0], ref[a0:b0]
    g = float(np.dot(sy, sr) / max(np.dot(sr, sr), 1e-300))
    e = sy - g * sr
    return 20 * np.log10(np.sqrt((e ** 2).mean()) /
                         np.sqrt(((g * sr) ** 2).mean()) + 1e-300)


def tone_gain_db(freq, **kw):
    n = int(SRC * 4)
    t = np.arange(n) / float(SRC)
    y = run(0.5 * np.sin(2 * np.pi * freq * t), **kw)
    m = int(DST * 1.0)
    seg = y[len(y) // 2: len(y) // 2 + m]
    w = np.hanning(len(seg))
    spec = np.abs(np.fft.rfft(seg * w)) * 2.0 / w.sum()
    fr = np.fft.rfftfreq(len(seg), 1.0 / DST)
    return 20 * np.log10(spec[int(np.argmin(np.abs(fr - freq)))] / 0.5 + 1e-300)


def main():
    x, p = tones()
    ref = analytic(p, int(round(len(x) * DST / SRC)))

    print("1) accuracy with fade=20 ms (the whole point of the change)")
    for ctx in (50, 100, 200):
        y = run(x, fade=20, context=ctx, block=30.0)
        print("   context %3d ms -> null %8.1f dB" % (ctx, null_db(y, ref)))

    print()
    print("2) block seam error (block 0.5 s vs whole file), fade=20 ms")
    for ctx in (20, 50, 100):
        a = run(x, fade=20, context=ctx, block=0.5)
        b = run(x, fade=20, context=ctx, block=30.0)
        print("   context %3d ms -> seam %8.1f dB" % (ctx, null_db(a, b)))

    print()
    print("3) minimum-phase passband, fade=20 ms, varying mptaps")
    print("   %-10s %10s %10s %10s" % ("mptaps", "21 kHz", "21.5 kHz", "22 kHz"))
    for mt in (20, 50, 100):
        vals = [tone_gain_db(f, fade=20, mptaps=mt, phase="min")
                for f in (21000.0, 21500.0, 22000.0)]
        print("   %-10s " % ("%g ms" % mt) + " ".join("%10.2f" % v for v in vals))

    print()
    print("4) short file (0.5 s) still safe with fade=20 ms")
    xs, ps = tones(0.5)
    refs = analytic(ps, int(round(len(xs) * DST / SRC)))
    print("   null %8.1f dB" % null_db(run(xs, fade=20), refs))


if __name__ == "__main__":
    main()
