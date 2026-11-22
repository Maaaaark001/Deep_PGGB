"""dp_boundary2.py - does the short fade hold up for low frequency and DC?

The first sweep used 40 tones spread over 200 Hz - 18 kHz. That is the easy
case: every tone completes many cycles inside a 20 ms fade. Two harder cases:
  * low frequency  - 20 Hz needs 50 ms just for one cycle, so a short fade
                     is a much bigger relative disturbance
  * DC offset      - a constant term makes the file end on a level, not at 0
"""
import os
import subprocess
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")


def run(x, src, dst, fade, taper="smooth"):
    td = tempfile.mkdtemp()
    fi, fo = os.path.join(td, "i.f64"), os.path.join(td, "o.f64")
    np.asarray(x, dtype="<f8").tofile(fi)
    cmd = [EXE, str(src), str(dst), fi, fo, "--ch", "1", "--block", "30",
           "--fade", str(fade), "--taper", taper, "--prec", "double",
           "--phase", "linear", "--threads", "0"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return np.fromfile(fo, "<f8")


def tones(src, secs, freqs, seed=5, amp=0.5):
    n = int(src * secs)
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0.0, 2 * np.pi, len(freqs))
    a = np.full(len(freqs), amp / len(freqs))
    t = np.arange(n) / float(src)
    x = sum(ai * np.sin(2 * np.pi * fi * t + pi) for ai, fi, pi in zip(a, freqs, ph))
    return x, (freqs, ph, a)


def analytic(params, nout, fo):
    f, ph, a = params
    t = np.arange(nout) / float(fo)
    return sum(ai * np.sin(2 * np.pi * fi * t + pi) for ai, fi, pi in zip(a, f, ph))


def null_db(y, ref, frac=0.1, lag_search=2):
    n = min(len(y), len(ref))
    best = None
    for lag in range(-lag_search, lag_search + 1):
        if lag >= 0:
            yy, rr = y[lag:n], ref[0:n - lag]
        else:
            yy, rr = y[0:n + lag], ref[-lag:n]
        m = len(rr)
        a0, b0 = int(m * frac), int(m * (1 - frac))
        sy, sr = yy[a0:b0], rr[a0:b0]
        g = float(np.dot(sy, sr) / max(np.dot(sr, sr), 1e-300))
        e = sy - g * sr
        v = 20 * np.log10(np.sqrt((e ** 2).mean()) /
                          np.sqrt(((g * sr) ** 2).mean()) + 1e-300)
        if best is None or v < best:
            best = v
    return best


def sweep(name, x, params, src=44100, dst=176400, fades=(0, 2, 5, 10, 20, 50, 100)):
    ref = analytic(params, int(round(len(x) * dst / src)), dst)
    out = []
    for ms in fades:
        y = run(x, src, dst, ms)
        out.append((ms, null_db(y, ref)))
    print("%-22s " % name + "  ".join("%gms:%.1f" % (m, v) for m, v in out))


def main():
    print("null dB vs fade length (interior 10-90%, 4 s signal)")
    print()
    sweep("20-500 Hz (low)", *tones(44100, 4.0, [20, 40, 80, 160, 320, 500]))
    sweep("20-2000 Hz", *tones(44100, 4.0, [20, 60, 200, 700, 2000]))
    sweep("200 Hz - 18 kHz", *tones(44100, 4.0,
                                    [200, 800, 3000, 9000, 15000, 18000]))
    sweep("1 kHz only", *tones(44100, 4.0, [1000]))
    sweep("20 Hz only", *tones(44100, 4.0, [20]))

    print()
    print("DC offset case (tone + 0.1 DC):")
    x, p = tones(44100, 4.0, [1000])
    x = x + 0.1
    ref = analytic(p, int(round(len(x) * 176400 / 44100)), 176400) + 0.1
    for ms in (0, 5, 20, 50, 100):
        y = run(x, 44100, 176400, ms)
        print("  fade %5g ms -> null %.1f dB" % (ms, null_db(y, ref)))

    print()
    print("Does it depend on file length? (200 Hz - 18 kHz)")
    for secs in (1.0, 2.0, 8.0):
        sweep("%.0f s" % secs, *tones(44100, secs,
                                     [200, 800, 3000, 9000, 15000, 18000]))


if __name__ == "__main__":
    main()
