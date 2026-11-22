"""Locate the block-mode error for awkward rate pairs (diagnostic).

Ground truth: taper + exact FFT resampling over the whole file, done in numpy.
The engine in whole-file mode should reproduce it to ~-250 dB; in block mode any
excess is a seam bug.
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


def ideal(x, src, dst, fade_ms=20.0):
    g = np.gcd(src, dst); L, M = dst // g, src // g
    n = len(x)
    xs = x.copy()
    t = max(1, int(fade_ms * 0.001 * src)); t = min(t, n // 20 if n >= 20 else n // 2)
    i = np.arange(t) / (t - 1)
    w = i * i * i * (i * (i * 6 - 15) + 10)
    xs[:t] *= w; xs[n - 1 - np.arange(t)] *= w
    P = int(np.ceil(n / M)) * M
    buf = np.zeros(P); buf[:n] = xs
    S = np.fft.rfft(buf)
    Q = P // M * L
    keep = min(len(S), Q // 2 + 1)
    out = np.zeros(Q // 2 + 1, complex)
    out[:keep] = S[:keep]
    # numpy's irfft already divides by Q; FFTW's c2r does not (the engine divides
    # by P), so scale by Q/P to land on the same convention.
    return np.fft.irfft(out, Q) * (Q / P)


def db(a, b, ref_rms=0.3536):
    n = min(len(a), len(b))
    return 20 * np.log10(max(np.sqrt(np.mean((a[:n] - b[:n]) ** 2)), 1e-300) / ref_rms)


for src, dst in [(44100, 56448), (44100, 50001), (44100, 48000), (44100, 96000)]:
    n = int(src * 2)
    x = 0.5 * np.sin(2 * np.pi * 997.0 * np.arange(n) / src)
    ref = ideal(x, src, dst)
    lo = int(0.3 * dst); hi = min(len(ref), len(ref)) - int(0.3 * dst)
    for blk in (0.0, 1.0, 0.5):
        y = run(x, src, dst, ch=1, block=blk)
        print(f"{src}->{dst} block={blk}: null={db(y[lo:hi], ref[lo:hi]):7.1f} dB "
              f"rms_y={np.sqrt(np.mean(y[lo:hi]**2)):.4f} rms_ref={np.sqrt(np.mean(ref[lo:hi]**2)):.4f}")
        seg = int(0.25 * dst)
        ph = []
        for s in range(lo, hi - seg, seg):
            Y = np.fft.rfft(y[s:s + seg]); R = np.fft.rfft(ref[s:s + seg])
            k = int(round(997.0 * seg / dst))
            ph.append(np.degrees(np.angle(Y[k] / R[k])) if abs(R[k]) > 1e-9 else 0.0)
        print("   phase err per 0.25 s slice (deg):", np.round(np.array(ph), 2)[:12])
    print()
