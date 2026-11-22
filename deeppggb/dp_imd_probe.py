"""First look at two-tone intermodulation on the fixed engine."""
import os, subprocess, tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, "dpggb.exe")


def run(x, src, dst, **opts):
    td = tempfile.mkdtemp(); fi = os.path.join(td, "i.f64"); fo = os.path.join(td, "o.f64")
    x.astype("<f8").tofile(fi)
    cmd = [EXE, str(src), str(dst), fi, fo, "--ch", "1"]
    for k, v in opts.items(): cmd += ["--" + k, str(v)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr)
    return np.fromfile(fo, "<f8")


def line(seg, rate, f):
    n = len(seg); s = np.abs(np.fft.rfft(seg)); k = int(round(f * n / rate))
    return float(np.max(s[max(0,k-1):k+2]) * 2 / n)


for src, dst in [(44100, 96000), (44100, 48000), (96000, 44100), (44100, 176400)]:
    n = int(src * 4); t = np.arange(n) / src
    f1, f2 = 19000.0, 20000.0
    x = 0.25 * np.sin(2 * np.pi * f1 * t) + 0.25 * np.sin(2 * np.pi * f2 * t)
    y = run(x, src, dst)
    seg = y[len(y)//2: len(y)//2 + dst]
    ref = (line(seg, dst, f1) + line(seg, dst, f2)) / 2
    prods = {"f2-f1=1k": 1000.0, "2f1-f2=18k": 18000.0, "2f2-f1=21k": 21000.0,
             "f1+f2=39k": 39000.0, "2f1=38k": 38000.0, "2f2=40k": 40000.0}
    out = []
    for k, f in prods.items():
        if f >= dst / 2: continue
        out.append(f"{k}={20*np.log10(max(line(seg,dst,f),1e-20)/ref):7.1f}")
    print(f"{src}->{dst}: " + "  ".join(out))
