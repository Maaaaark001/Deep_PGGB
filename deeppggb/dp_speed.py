"""dp_speed.py - where does the time actually go, and what actually makes it faster?

Questions:
  1. does --threads help, and how far? (machine has 4 cores, default is 0 = 1 thread)
  2. does the FFTW plan flag matter? (currently FFTW_ESTIMATE)
  3. is the block loop serial, and would running blocks in parallel help?
"""
import os
import subprocess
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")
SRC, DST = 44100, 48000


def timed(x, threads=0, block=30.0, prec="double"):
    td = tempfile.mkdtemp()
    fi, fo = os.path.join(td, "i.f64"), os.path.join(td, "o.f64")
    np.asarray(x, dtype="<f8").tofile(fi)
    cmd = [EXE, str(SRC), str(DST), fi, fo, "--ch", "1", "--block", str(block),
           "--fade", "20", "--context", "100", "--taper", "smooth",
           "--prec", prec, "--phase", "linear", "--threads", str(threads)]
    t0 = time.perf_counter()
    r = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-400:])
    return dt


def main():
    n = int(SRC * 10)
    t = np.arange(n) / float(SRC)
    x = 0.5 * np.sin(2 * np.pi * 1000 * t)
    print("10 s mono, 44.1 -> 48 kHz")
    print("%-10s %10s %10s" % ("threads", "seconds", "x realtime"))
    for th in (0, 1, 2, 4):
        d = timed(x, threads=th)
        print("%-10d %10.3f %10.1f" % (th, d, 10.0 / d))

    print()
    print("block length effect (threads=4)")
    for blk in (0.5, 2.0, 5.0, 10.0, 30.0, 0.0):
        d = timed(x, threads=4, block=blk)
        print("   block %5.1f s -> %6.3f s  (%5.1fx)" % (blk, d, 10.0 / d))

    print()
    print("precision (threads=4, block 30)")
    for pr in ("double", "long"):
        d = timed(x, threads=4, block=30.0, prec=pr)
        print("   %-8s -> %6.3f s  (%5.1fx)" % (pr, d, 10.0 / d))


if __name__ == "__main__":
    main()
