"""Probe suspected Deep_PGGB defects.

1. Grid ratio: P must stay a multiple of M. When the block grid is enlarged to
   fit the context (P < 4T), P is set to 4T directly, which is not a multiple of
   M for rate pairs whose gcd is not a multiple of 5. Q = (P/M)*L then uses a
   *different* ratio than L/M, so the audio is transposed.
2. Block seams: output index arithmetic uses llround/floor independently per
   block, so for the same rate pairs a block can leave a one-sample gap (zero)
   or overwrite one sample of its neighbour.
"""
import os, sys, subprocess, tempfile
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
    y = np.fromfile(fo, "<f8")
    return y


def peak_freq(y, rate):
    n = len(y)
    w = np.hanning(n)
    s = np.abs(np.fft.rfft(y * w))
    k = int(np.argmax(s[1:])) + 1
    return k * rate / n


def tone(f, rate, sec):
    t = np.arange(int(rate * sec)) / rate
    return 0.5 * np.sin(2 * np.pi * f * t)


print("=== 1. rate-ratio integrity (1 kHz tone must stay 1 kHz) ===")
pairs = [(44100, 48000), (48000, 44100), (44100, 96000), (96000, 44100),
         (44100, 176400), (44100, 88200), (22050, 48000), (8000, 44100),
         (44100, 50001), (44100, 56448), (11025, 48000), (44100, 2822400)]
for src, dst in pairs:
    x = tone(1000.0, src, 2.0)
    try:
        y = run(x, src, dst, ch=1)
    except Exception as e:
        print(f"{src}->{dst}: FAILED {e}")
        continue
    f = peak_freq(y, dst)
    want = int(round(len(x) * dst / src))
    # exact expected frequency for an ideal converter
    print(f"{src:>7}->{dst:<7} len={len(y):>8} want={want:>8} peak={f:9.2f} Hz "
          f"err={f-1000.0:+8.2f} Hz ({20*np.log10(max(abs(f-1000),1e-9)/1000):+6.1f} rel)")

print()
print("=== 2. seam integrity: exact-zero / step artefacts at block joins ===")
for src, dst in [(44100, 48000), (44100, 96000), (96000, 44100), (44100, 50001),
                 (44100, 56448), (48000, 44100)]:
    x = tone(997.0, src, 6.0)
    y = run(x, src, dst, ch=1, block=1.0, context=100.0)
    # a gap leaves an exact zero; count them away from the faded ends
    body = y[int(0.2 * dst):-int(0.2 * dst)]
    zeros = int(np.sum(body == 0.0))
    d = np.abs(np.diff(body))
    med = np.median(d)
    spikes = int(np.sum(d > 20 * med))
    print(f"{src}->{dst}: exact zeros={zeros:>5}  diff spikes(>20x median)={spikes:>5}  "
          f"max|diff|={d.max():.3e} median={med:.3e}")
