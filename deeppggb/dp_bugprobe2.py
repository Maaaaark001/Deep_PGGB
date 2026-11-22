"""Quantify two suspected Deep_PGGB defects with a null test.

A. Seam phase error: compare block-wise output against the whole-file output for
   rate pairs whose block advance is not an integer number of output samples.
B. Grid-ratio error: when the block grid is forced up to 4*T (P < 4T), P stops
   being a multiple of M, so Q/P != L/M and the audio is transposed.
"""
import os, subprocess, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")


def run(x, src, dst, **opts):
    td = tempfile.mkdtemp()
    fi = os.path.join(td, "i.f64"); fo = os.path.join(td, "o.f64")
    x.astype("<f8").tofile(fi)
    cmd = [EXE, str(src), str(dst), fi, fo]
    for k, v in opts.items():
        cmd += ["--" + k, str(v)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return np.fromfile(fo, "<f8")


def tone(f, rate, sec, ph=0.0):
    t = np.arange(int(rate * sec)) / rate
    return 0.5 * np.sin(2 * np.pi * f * t + ph)


def db(a, b):
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    return 20 * np.log10(max(np.sqrt(np.mean((a - b) ** 2)), 1e-300) / 0.3536)


print("=== A. block-wise vs whole-file (seam error) ===")
print(f"{'rate pair':>18} {'L/M':>12} {'kept*L/M':>12} {'seam dB':>9}")
for src, dst in [(44100, 48000), (44100, 96000), (96000, 44100), (44100, 88200),
                 (44100, 176400), (44100, 50001), (44100, 56448), (48000, 44100),
                 (22050, 48000), (44100, 32000)]:
    g = np.gcd(src, dst); L, M = dst // g, src // g
    x = tone(997.0, src, 4.0)
    a = run(x, src, dst, ch=1, block=1.0)
    b = run(x, src, dst, ch=1, block=0)
    n = min(len(a), len(b))
    # skip 0.5 s at both ends: the block path and the whole-file path both fade,
    # but the whole-file path has no seams, so any interior difference is a seam.
    lo = int(0.5 * dst); hi = n - int(0.5 * dst)
    seam = db(a[lo:hi], b[lo:hi])
    # theoretical block advance in output samples
    P = 0
    print(f"{src}->{dst:<7} {L:>6}/{M:<5} {'-':>12} {seam:>9.1f}")

print()
print("=== B. forced 4T grid (block shorter than 4*context) ===")
print(f"{'rate pair':>18} {'block':>6} {'len':>9} {'want':>9} {'peak Hz':>9} {'cents':>7}")
for src, dst in [(44100, 56448), (44100, 50001), (44100, 48000), (44100, 96000)]:
    for blk in (1.0, 0.25, 0.1):
        x = tone(1000.0, src, 2.0)
        y = run(x, src, dst, ch=1, block=blk, context=100.0)
        want = int(round(len(x) * dst / src))
        n = len(y)
        w = np.hanning(n)
        s = np.abs(np.fft.rfft(y * w))
        k = int(np.argmax(s[1:])) + 1
        f = k * dst / n
        cents = 1200 * np.log2(max(f, 1e-9) / 1000.0)
        print(f"{src}->{dst:<7} {blk:>6} {n:>9} {want:>9} {f:>9.2f} {cents:>+7.1f}")
