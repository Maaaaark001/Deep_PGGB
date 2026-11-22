import sys, numpy as np
sys.path.insert(0, r"C:\Users\Administrator\Documents\Python_Code\src\deeppggb")
import deeppggb

FS = 96000
N = FS * 4

def tone(f, fs, n, amp=0.5):
    idx = np.arange(n, dtype=np.int64)
    k = (np.int64(int(round(f))) * idx) % fs
    return amp * np.sin(2.0 * np.pi * k / fs)

def gain_db(f, src, dst, opts):
    x = tone(f, src, int(src * 4)).astype(np.float64)
    y = deeppggb.resample(x, src, dst, **opts)
    m = slice(int(dst * 1.0), int(dst * 3.0))
    seg = np.asarray(y).reshape(-1)[m]
    n = len(seg)
    idx = np.arange(n, dtype=np.int64)
    k = (np.int64(int(round(f))) * idx) % dst
    b = np.sin(2.0 * np.pi * k / dst)
    a = seg
    g = (a @ b) / (b @ b)
    for _ in range(3):
        d = a - g * b
        g += (d @ b) / (b @ b)
    return 20 * np.log10(abs(g) / 0.5)

print("down 96->44.1, rolloff 200 order2 (default)")
for f in (1000, 10000, 18000, 20000, 21000, 21500, 21850, 21900, 21950, 22000, 22040):
    print(f"  {f:7.1f} Hz  {gain_db(f, 96000, 44100, dict(taper='smooth5', block=4.0, context=400.0, btaper=20.0, rolloff=200.0, rollorder=2)):+.4f} dB")
print("down 96->44.1, rolloff 0")
for f in (21900, 21950, 22000, 22040):
    print(f"  {f:7.1f} Hz  {gain_db(f, 96000, 44100, dict(taper='smooth5', block=4.0, context=400.0, btaper=20.0, rolloff=0.0)):+.4f} dB")
print("up 44.1->96")
for f in (21500, 21900, 22000, 22049):
    print(f"  {f:7.1f} Hz  {gain_db(f, 44100, 96000, dict(taper='smooth5', block=4.0, context=400.0, btaper=20.0)):+.4f} dB")
