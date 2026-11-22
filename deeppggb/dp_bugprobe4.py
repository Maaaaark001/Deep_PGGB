"""Reference-free check: does the engine's output actually contain a clean tone?

Fits amplitude/phase/frequency to the interior and reports the residual, then
fits each 0.1 s slice independently. A correct converter gives a residual near
the numerical floor and a constant phase across slices.
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


def fit(y, dst, f0):
    """Least-squares fit of A*cos + B*sin at f0 -> (amp, phase, residual dB)."""
    t = np.arange(len(y)) / dst
    M = np.column_stack([np.cos(2 * np.pi * f0 * t), np.sin(2 * np.pi * f0 * t)])
    coef, *_ = np.linalg.lstsq(M, y, rcond=None)
    amp = np.hypot(*coef)
    ph = np.degrees(np.arctan2(-coef[1], coef[0]))
    res = y - M @ coef
    return amp, ph, 20 * np.log10(max(np.sqrt(np.mean(res ** 2)), 1e-300) / 0.3536)


for src, dst in [(44100, 56448), (44100, 50001), (44100, 48000), (44100, 96000),
                 (48000, 44100), (44100, 88200), (96000, 44100), (44100, 32000)]:
    n = int(src * 3)
    x = 0.5 * np.sin(2 * np.pi * 997.0 * np.arange(n) / src)
    for blk in (0.0, 1.0):
        y = run(x, src, dst, ch=1, block=blk)
        lo = int(0.5 * dst); hi = len(y) - int(0.5 * dst)
        amp, ph, res = fit(y[lo:hi], dst, 997.0)
        seg = int(0.1 * dst)
        amps, phs = [], []
        for s in range(lo, hi - seg, seg):
            a, p, _ = fit(y[s:s + seg], dst, 997.0)
            amps.append(a); phs.append(p)
        amps = np.array(amps); phs = np.unwrap(np.radians(np.array(phs)))
        print(f"{src}->{dst:<7} block={blk}: amp={amp:.4f} res={res:7.1f} dB  "
              f"slice amp {amps.min():.3f}..{amps.max():.3f}  "
              f"phase drift {np.degrees(phs.max()-phs.min()):6.1f} deg")
    print()
