"""dp_taper_shape.py - why does a constant extension fail but a fade work?

Hypothesis: what matters at a file boundary is not continuity of the value
(C0) but how many derivatives are continuous. A step is C-1 and its spectrum
falls as 1/f. A raised cosine is C1 and falls as 1/f^3. Smootherstep is C2
and falls faster still. Constant extension only reaches C0, so it should buy
nothing - which is what the first sweep showed.

If the hypothesis holds, at equal length a C2 taper must beat a C1 taper,
and the gap should be largest when the taper is short.
"""
import os
import subprocess
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")
SRC, DST = 44100, 176400


def run(x, fade, taper):
    td = tempfile.mkdtemp()
    fi, fo = os.path.join(td, "i.f64"), os.path.join(td, "o.f64")
    np.asarray(x, dtype="<f8").tofile(fi)
    cmd = [EXE, str(SRC), str(DST), fi, fo, "--ch", "1", "--block", "30",
           "--fade", str(fade), "--taper", taper, "--prec", "double",
           "--phase", "linear", "--threads", "0"]
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
    x = sum(ai * np.sin(2 * np.pi * fi * t + pi) for ai, fi, pi in zip(a, f, ph))
    return x, (f, ph, a)


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


def main():
    x, p = tones()
    ref = analytic(p, int(round(len(x) * DST / SRC)))
    print("null dB by taper shape (4 s, 200 Hz - 18 kHz)")
    print()
    print("%-10s %10s %10s %10s %10s" % ("taper", "2 ms", "5 ms", "10 ms", "20 ms"))
    print("-" * 54)
    for taper in ("cos", "smooth", "blackman"):
        vals = []
        for ms in (2, 5, 10, 20):
            vals.append(null_db(run(x, ms, taper), ref))
        print("%-10s " % taper + " ".join("%10.1f" % v for v in vals))
    print()
    print("none (no taper)          %10.1f" % null_db(run(x, 0, "none"), ref))


if __name__ == "__main__":
    main()
