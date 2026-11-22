"""Replicate the C++ algorithm in numpy and isolate where the error comes from."""
import numpy as np


def taper(x, t):
    n = len(x); xs = x.copy()
    i = np.arange(t) / (t - 1)
    w = i ** 3 * (i * (i * 6 - 15) + 10)
    xs[:t] *= w
    xs[n - 1 - np.arange(t)] *= w
    return xs


def convert(xs, P, L, M):
    buf = np.zeros(P); buf[:len(xs)] = xs[:P]
    S = np.fft.rfft(buf)
    Q = (P // M) * L
    keep = min(len(S), Q // 2 + 1)
    out = np.zeros(Q // 2 + 1, complex)
    out[:keep] = S[:keep]
    return np.fft.irfft(out, Q) * (Q / P)


def resid(y, dst, f0, skip=0.5):
    lo = int(skip * dst); hi = len(y) - int(skip * dst)
    y = y[lo:hi]
    t = np.arange(len(y)) / dst
    Mx = np.column_stack([np.cos(2 * np.pi * f0 * t), np.sin(2 * np.pi * f0 * t)])
    c, *_ = np.linalg.lstsq(Mx, y, rcond=None)
    r = y - Mx @ c
    return 20 * np.log10(max(np.sqrt(np.mean(r ** 2)), 1e-300) / 0.3536)


n = 132300
t = np.arange(n) / 44100
x = 0.5 * np.sin(2 * np.pi * 997.0 * t)
xs = taper(x, 882)

print("44100 -> 56448 (L=32, M=25)")
for P in (132300, 135000, 141120, 220500):
    if P % 25:
        continue
    y = convert(xs, P, 32, 25)
    print(f"  P={P:>7} Q={P//25*32:>7} resid={resid(y, 56448, 997.0):7.1f} dB")

print("  no taper, P=135000:", f"{resid(convert(x, 135000, 32, 25), 56448, 997.0):7.1f} dB")
print("  taper 882, P=135000, f0 on bin (f=44100*3052/135000):")
f_bin = 44100 * 3052 / 135000
xb = 0.5 * np.sin(2 * np.pi * f_bin * t)
print(f"    f_bin={f_bin:.4f} Hz resid={resid(convert(taper(xb,882), 135000, 32, 25), 56448, f_bin):7.1f} dB")

print()
print("44100 -> 48000 (L=160, M=147)")
for P in (44100, 48000, 88200):
    if P % 147:
        continue
    y = convert(xs, P, 160, 147)
    print(f"  P={P:>7} Q={P//147*160:>7} resid={resid(y, 48000, 997.0):7.1f} dB")

print()
print("Is it the taper? sweep taper length, P=135000, 44100->56448")
for ms in (0.0, 5.0, 20.0, 50.0, 200.0):
    tt = int(ms * 44.1)
    xx = taper(x, max(1, tt)) if ms > 0 else x
    print(f"  taper {ms:6.1f} ms resid={resid(convert(xx, 135000, 32, 25), 56448, 997.0):7.1f} dB")

print()
print("Is it the tone? sweep f0 with 20 ms taper, P=135000, 44100->56448")
for f0 in (100.0, 997.0, 1000.0, 3000.0, 10000.0):
    xx = 0.5 * np.sin(2 * np.pi * f0 * t)
    print(f"  f0={f0:8.1f} Hz resid={resid(convert(taper(xx, 882), 135000, 32, 25), 56448, f0):7.1f} dB")
