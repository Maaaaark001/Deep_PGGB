import numpy as np


def taper(x, t):
    n = len(x); xs = x.copy()
    i = np.arange(t) / (t - 1)
    w = i ** 3 * (i * (i * 6 - 15) + 10)
    xs[:t] *= w
    xs[n - 1 - np.arange(t)] *= w
    return xs


def convert(xs, P, L, M):
    buf = np.zeros(P); buf[:min(len(xs), P)] = xs[:P]
    S = np.fft.rfft(buf)
    Q = (P // M) * L
    keep = min(len(S), Q // 2 + 1)
    out = np.zeros(Q // 2 + 1, complex)
    out[:keep] = S[:keep]
    return np.fft.irfft(out, Q) * (Q / P)


def resid(y, dst, f0, skip=0.5):
    lo = int(skip * dst); hi = len(y) - int(skip * dst)
    if hi <= lo:
        return float("nan")
    y = y[lo:hi]
    t = np.arange(len(y)) / dst
    Mx = np.column_stack([np.cos(2 * np.pi * f0 * t), np.sin(2 * np.pi * f0 * t)])
    c, *_ = np.linalg.lstsq(Mx, y, rcond=None)
    r = y - Mx @ c
    return 20 * np.log10(max(np.sqrt(np.mean(r ** 2)), 1e-300) / 0.3536)


n = 132300
t = np.arange(n) / 44100
print("44100->56448, P=220500 (Q=282240), vary taper and tone")
for ms in (0.0, 5.0, 20.0):
    for f0 in (997.0, 1000.0, 5000.0):
        x = 0.5 * np.sin(2 * np.pi * f0 * t)
        xx = taper(x, max(1, int(ms * 44.1))) if ms > 0 else x
        print(f"  taper {ms:5.1f} ms f0={f0:7.1f} -> {resid(convert(xx, 220500, 32, 25), 56448, f0):7.1f} dB")
print()
print("same P, but pad the input with zeros to fill P exactly")
x = 0.5 * np.sin(2 * np.pi * 997.0 * t)
for P in (132300, 135000, 220500, 264600, 441000):
    xx = taper(x, 882)
    y = convert(xx, P, 32, 25)
    print(f"  P={P:>7} -> {resid(y, 56448, 997.0):7.1f} dB")
