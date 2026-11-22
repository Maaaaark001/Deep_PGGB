"""dp_block_acc.py - is a small block actually free?

dp_speed.py showed block 0.5 s runs at 191x while block 30 s runs at 125x.
Before making 0.5 the default I need to know whether accuracy survives.
"""
import os
import subprocess
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")
SRC, DST = 44100, 176400


def run(x, block):
    td = tempfile.mkdtemp()
    fi, fo = os.path.join(td, "i.f64"), os.path.join(td, "o.f64")
    np.asarray(x, dtype="<f8").tofile(fi)
    r = subprocess.run([EXE, str(SRC), str(DST), fi, fo, "--ch", "1", "--block", str(block),
                        "--fade", "20", "--context", "100", "--taper", "smooth",
                        "--prec", "double", "--phase", "linear", "--threads", "1"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
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


def main():
    x, p = tones()
    ref = analytic(p, int(round(len(x) * DST / SRC)))
    print("accuracy vs block size (4 s, 200 Hz - 18 kHz, context 100 ms)")
    for blk in (0.25, 0.5, 1.0, 2.0, 5.0, 30.0, 0.0):
        y = run(x, blk)
        print("   block %6.2f s -> null %8.1f dB" % (blk, null_db(y, ref)))


if __name__ == "__main__":
    main()
