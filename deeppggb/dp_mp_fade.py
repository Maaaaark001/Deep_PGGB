"""dp_mp_fade.py - minimum-phase passband vs fade length, measured correctly.

The earlier version divided by the spectrum bin at 1 kHz, but the test signal
only contained a tone at f, so that bin was pure noise and every result came
out as a positive number. Measure against the input amplitude instead.
"""
import os
import subprocess
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")
SRC, DST = 44100, 176400


def run(x, fade, phase="linear"):
    td = tempfile.mkdtemp()
    fi, fo = os.path.join(td, "i.f64"), os.path.join(td, "o.f64")
    np.asarray(x, dtype="<f8").tofile(fi)
    r = subprocess.run([EXE, str(SRC), str(DST), fi, fo, "--ch", "1",
                        "--block", "30", "--fade", str(fade), "--taper", "smooth",
                        "--prec", "double", "--phase", phase, "--threads", "0"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return np.fromfile(fo, "<f8")


def tone_gain_db(freq, fade, phase):
    """Gain at freq, relative to the 0.5 input amplitude, on the steady interior."""
    n = int(SRC * 4)
    t = np.arange(n) / float(SRC)
    x = 0.5 * np.sin(2 * np.pi * freq * t)
    y = run(x, fade, phase)
    m = int(DST * 1.0)
    seg = y[len(y) // 2: len(y) // 2 + m]
    w = np.hanning(len(seg))
    spec = np.abs(np.fft.rfft(seg * w)) * 2.0 / w.sum()
    fr = np.fft.rfftfreq(len(seg), 1.0 / DST)
    i = int(np.argmin(np.abs(fr - freq)))
    return 20 * np.log10(spec[i] / 0.5 + 1e-300)


def main():
    print("minimum-phase passband vs fade (FIR taps = 4 x fade)")
    print("%-8s %8s %10s %10s %10s" % ("fade", "taps", "21 kHz", "21.5 kHz", "22 kHz"))
    print("-" * 50)
    for ms in (10, 20, 50, 100):
        taps = 4 * int(0.001 * ms * SRC)
        vals = [tone_gain_db(f, ms, "min") for f in (21000.0, 21500.0, 22000.0)]
        print("%-8s %8d " % ("%g ms" % ms, taps) + " ".join("%10.2f" % v for v in vals))
    print()
    print("linear-phase reference (fade 20 ms):")
    print("%-18s " % "linear" + " ".join(
        "%10.2f" % tone_gain_db(f, 20, "linear") for f in (21000.0, 21500.0, 22000.0)))


if __name__ == "__main__":
    main()
