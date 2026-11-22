"""dp_paper_data.py - collect every number the paper needs into one JSON.

Two measurement traps this script is built to avoid:

1. REFERENCE PHASE. A naive reference sin(2*pi*f*n/fs) accumulates float phase
   error: at 18 kHz over 4 s the argument reaches 4.5e5 rad and a 1e-16 relative
   error becomes 4.5e-11 rad of absolute phase, i.e. -217 dB. That is the same
   order as the engine's own error, so the reference would be measuring itself.
   Fix: for an integer-Hz tone, (f*n) mod fs is exact integer arithmetic, so the
   reference carries no accumulated phase error at all.

2. REFERENCE FREQUENCY. Resampling changes the sample rate, NOT the frequency.
   The analytic reference at the destination rate is the same set of tones
   evaluated at the destination rate. Scaling the frequencies by the ratio (an
   earlier bug in this file) makes the reference a different signal and the null
   test then reports 0 dB - which looks like "perfect" and is actually garbage.
   The sanity asserts after section 1 exist to make that failure loud.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

ROOT = r"C:\Users\Administrator\Documents\Python_Code\src"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src_bench"))
from srctool import engines, config  # noqa: E402

OUT = {}
FS = 44100


def exact_tone(f, fs, n, ph=0.0, amp=0.5):
    idx = np.arange(n, dtype=np.int64)
    k = (int(round(f)) * idx) % fs
    return amp * np.sin(2 * np.pi * (k / float(fs)) + ph)


def tones(freqs, phs, amps, fs, n):
    idx = np.arange(n, dtype=np.int64)
    y = np.zeros(n)
    for f, p, a in zip(freqs, phs, amps):
        k = (int(round(f)) * idx) % fs
        y += a * np.sin(2 * np.pi * (k / float(fs)) + p)
    return y


def null_db(y, ref, skip=0.1, iters=3):
    """Null depth in dB, with the gain fitted by damped Gauss-Newton.

    The closed-form least-squares gain g = <a,b>/<b,b> is only accurate to a few
    ulp, and its error is NOT second order: a residual of 1e-15 * |g b| shows up
    as a -289 dB floor whenever |g| differs from 1. PGGB normalises to full
    scale (g = 1.11), so a single dot-product gain made PGGB look 13 dB worse
    than it is -- 288.8 dB instead of 302.0 dB, which is the difference between
    "measurably worse than Deep_PGGB" and "indistinguishable". Refining the gain
    removes the artifact; it is a property of the estimator, not of the engine.
    """
    m = min(len(y), len(ref))
    e = int(skip * m)
    a = np.asarray(y[e:m - e], dtype=np.float64)
    b = np.asarray(ref[e:m - e], dtype=np.float64)
    g = float(np.dot(a, b) / max(np.dot(b, b), 1e-300))
    bb = float(np.dot(b, b))
    for _ in range(iters):
        d = a - g * b
        g += float(np.dot(d, b) / max(bb, 1e-300))
    d = a - g * b
    return 20 * np.log10(max(float(np.sqrt(np.mean(b * b))), 1e-300) /
                         max(float(np.sqrt(np.mean(d * d))), 1e-300))


def res(x, src, dst, opts=None, eng="dpggb"):
    return np.asarray(engines.resample(x.reshape(-1, 1), src, dst, eng, opts)[:, 0],
                      dtype=np.float64)


# ---------------------------------------------------------------- stimulus
rng = np.random.default_rng(5)
FREQS = np.sort(rng.choice(np.arange(200, 18001), 40, replace=False)).astype(np.int64)
PHS = rng.uniform(0, 2 * np.pi, 40)
AMPS = rng.uniform(0.05, 0.5, 40)
AMPS = AMPS / AMPS.sum() * 1.6
N4 = FS * 4
X4 = tones(FREQS, PHS, AMPS, FS, N4)

# ---------------------------------------------------- 1. accuracy vs ratio
rows = []
for src, dst in [(44100, 48000), (44100, 88200), (44100, 96000), (44100, 176400),
                 (48000, 44100), (96000, 44100), (44100, 50001), (44100, 56448),
                 (96000, 192000)]:
    x = X4 if src == FS else tones(FREQS, PHS, AMPS, src, src * 4)
    n_out = int(round(len(x) * dst / src))
    ref = tones(FREQS, PHS, AMPS, dst, n_out)
    y = res(x, src, dst)
    rows.append({"src": src, "dst": dst, "ratio": round(dst / src, 6),
                 "null_db": round(null_db(y, ref), 1)})
    print("ratio %6d -> %6d  %7.1f dB" % (src, dst, rows[-1]["null_db"]), flush=True)
OUT["accuracy"] = rows
# sanity: a correct reference must give >200 dB; 0 dB means the reference is wrong
for r in rows:
    assert r["null_db"] > 150.0, ("reference looks wrong", r)
print("sanity: every ratio above 150 dB (reference is exact)", flush=True)


# ------------------------------- 1b. taper window order vs upsampling accuracy
# The fade window is a multiplier: it convolves the signal spectrum with its own
# transform. A tone 4 kHz below Nyquist then puts its window sidelobes exactly on
# the source Nyquist line, where the analytic reference is zero. The sidelobe
# level is a property of the window alone, so this sweep isolates it.
def smootherstep_generic(t, order):
    """w(t) = t^(N+1) * sum_k C(N+k,k) C(2N+1,N-k) (-t)^k, mirrored at t>0.5."""
    from math import comb
    n = order
    out = np.zeros_like(t)
    lo = t <= 0.5
    for mask, u in ((lo, t[lo]), (~lo, 1.0 - t[~lo])):
        s = np.zeros_like(u)
        for k in range(n + 1):
            s += comb(n + k, k) * comb(2 * n + 1, n - k) * (-u) ** k
        w = u ** (n + 1) * s
        out[mask] = w if mask is lo else 1.0 - w
    return out


def window_leak_db(order, tone=15000.0, ms=20.0, fs=44100, probe=22050.0, n=88200):
    """Leakage a fade window alone produces at the Nyquist probe frequency."""
    x = exact_tone(tone, fs, n)
    T = int(round(ms * 1e-3 * fs))
    w = smootherstep_generic(np.linspace(0.0, 1.0, T), order)
    x = x.copy()
    x[:T] *= w
    x[-T:] *= w[::-1]
    spec = np.abs(np.fft.rfft(x)) * 2.0 / n
    k = int(round(probe * n / fs))
    return 20 * np.log10(max(float(np.max(spec[k - 1:k + 2])), 1e-30) / 0.5)


def taper_null(shape, f=15000.0):
    x = exact_tone(f, FS, N4)
    y = res(x, FS, 176400, {"taper": shape})
    ref = exact_tone(f, 176400, int(round(N4 * 4)))
    return null_db(y, ref)


taper_rows = []
for shape, order, label in (("cos", 1, "cos (C1)"), ("smooth2", 2, "smooth2 (C2)"),
                            ("smooth4", 4, "smooth4 (C4)"), ("smooth5", 5, "smooth5 (C5)"),
                            ("smooth6", 6, "smooth6 (C6)")):
    ym = res(X4, FS, 176400, {"taper": shape})
    refm = tones(FREQS, PHS, AMPS, 176400, int(round(N4 * 4)))
    taper_rows.append({"shape": shape, "order": order, "label": label,
                       "leak_22050_db": round(window_leak_db(order), 1),
                       "null_15k_db": round(taper_null(shape), 1),
                       "null_40tone_db": round(null_db(ym, refm), 1)})
    print("taper %-9s leak %7.1f  null15k %7.1f  null40t %7.1f"
          % (shape, taper_rows[-1]["leak_22050_db"], taper_rows[-1]["null_15k_db"],
             taper_rows[-1]["null_40tone_db"]), flush=True)
OUT["taper_order"] = taper_rows

# ------------------------- 1c. null depth vs tone frequency, C2 vs C5
freq_rows = []
for f in (1000, 5000, 10000, 15000, 18000, 19000, 20000, 21000, 21500, 21900, 21950, 22000):
    row = {"hz": f}
    for shape in ("smooth2", "smooth5"):
        x = exact_tone(f, FS, N4)
        y = res(x, FS, 176400, {"taper": shape})
        ref = exact_tone(f, 176400, int(round(N4 * 4)))
        row["null_" + shape] = round(null_db(y, ref), 1)
    freq_rows.append(row)
    print("freq %7d  C2 %7.1f  C5 %7.1f"
          % (f, row["null_smooth2"], row["null_smooth5"]), flush=True)
OUT["freq_sweep"] = freq_rows

# ---------------------------------- 1d. short files (the taper is clamped to 5%)
len_rows = []
for secs in (0.1, 0.2, 0.5, 1.0, 2.0, 4.0):
    n = int(round(FS * secs))
    x = exact_tone(15000.0, FS, n)
    y = res(x, FS, 176400, {"taper": "smooth5"})
    ref = exact_tone(15000.0, 176400, int(round(n * 4)))
    len_rows.append({"seconds": secs, "null_db": round(null_db(y, ref), 1)})
    print("length %4.2f s -> %7.1f dB" % (secs, len_rows[-1]["null_db"]), flush=True)
OUT["file_length"] = len_rows

# ------------------------------------------- 2. block-length invariance
base = res(X4, FS, 48000, {"block": 0.0})
inv = []
for blk in (0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 30.0):
    y = res(X4, FS, 48000, {"block": blk})
    inv.append({"block_s": blk, "null_vs_whole_db": round(null_db(y, base), 1)})
    print("block %5.2f s -> %7.1f dB vs whole" % (blk, inv[-1]["null_vs_whole_db"]), flush=True)
OUT["block_invariance"] = inv

# ---------------------------------------------------------- 3. speed
x60 = np.random.default_rng(2).normal(0, 0.1, (FS * 60, 2))
sp = []
for blk in (0.5, 1.0, 2.0, 4.0, 30.0):
    for wk in (1, 2, 4, 8):
        t0 = time.perf_counter()
        engines.resample(x60, FS, 96000, "dpggb", {"block": blk, "workers": wk})
        dt = time.perf_counter() - t0
        sp.append({"block_s": blk, "workers": wk, "speed_x": round(60.0 / dt, 1)})
        print("speed block %5.2f workers %d -> %6.1fx" % (blk, wk, sp[-1]["speed_x"]), flush=True)
OUT["speed"] = sp

# --------------------------------------------- 4. rolloff / alias sweep
n8 = int(96000 * 8)
t8 = np.arange(n8) / 96000.0
REF_RMS = 0.5 / np.sqrt(2.0)


def alias_db(f, roll, order=2, block=1.0, ctx=400, bt=20):
    x = (0.5 * np.sin(2 * np.pi * f * t8)).astype("<f8")
    td = tempfile.mkdtemp()
    fi, fo = os.path.join(td, "i.f64"), os.path.join(td, "o.f64")
    x.tofile(fi)
    subprocess.run([str(config.DPGGB), "96000", "44100", fi, fo, "--ch", "1",
                    "--block", str(block), "--context", str(ctx), "--btaper", str(bt),
                    "--rolloff", str(roll), "--rollorder", str(order)],
                   check=True, capture_output=True)
    y = np.fromfile(fo, "<f8")
    seg = y[len(y) // 4: 3 * len(y) // 4]
    return 20 * np.log10(max(float(np.sqrt(np.mean(seg * seg))), 1e-30) / REF_RMS)


roll_rows = []
for roll in (0, 50, 100, 200, 400, 800):
    for order in (1, 2, 3, 4):
        if roll == 0 and order > 1:
            continue
        roll_rows.append({
            "rolloff_hz": roll, "order": order,
            "alias_22050": round(alias_db(22050.37, roll, order), 1),
            "alias_22100": round(alias_db(22100.37, roll, order), 1),
            "alias_22500": round(alias_db(22500.37, roll, order), 1),
        })
        print("rolloff %4d order %d -> %s" % (roll, order, roll_rows[-1]), flush=True)
OUT["rolloff"] = roll_rows

# ------------------------------------- 4b. context / block-taper sweep
ctx_rows = []
xb = np.fft.rfft(rng.normal(0, 1, n8))
fr = np.fft.rfftfreq(n8, 1.0 / 96000)
xb[fr > 18000.0] = 0.0
band = np.fft.irfft(xb, n8)
band = band / np.max(np.abs(band)) * 0.4
whole = res(band, 96000, 44100, {"block": 0.0, "rolloff": 200})
for ctx in (50, 100, 200, 400, 800):
    for bt in (5, 10, 20, 50):
        y = res(band, 96000, 44100, {"block": 1.0, "context": ctx, "btaper": bt,
                                     "rolloff": 200})
        ctx_rows.append({"context_ms": ctx, "btaper_ms": bt,
                         "join_db": round(null_db(y, whole, skip=0.02), 1),
                         "alias_22050": round(alias_db(22050.37, 200, 2, 1.0, ctx, bt), 1)})
        print("ctx %4d bt %3d -> join %7.1f alias %7.1f"
              % (ctx, bt, ctx_rows[-1]["join_db"], ctx_rows[-1]["alias_22050"]), flush=True)
OUT["context"] = ctx_rows

# ------------------------------------------------- 5. passband (upsampling)
pb = []
for f in (1000.0, 10000.0, 18000.0, 20000.0, 21000.0, 21500.0, 21900.0, 22000.0, 22049.0):
    x = exact_tone(f, FS, N4)
    y = res(x, FS, 96000)
    seg = y[len(y) // 2: len(y) // 2 + 96000]
    spec = np.abs(np.fft.rfft(seg)) * 2.0 / len(seg)
    k = int(round(f * len(seg) / 96000))
    amp = float(np.max(spec[max(0, k - 1):k + 2]))
    pb.append({"hz": f, "gain_db": round(20 * np.log10(max(amp, 1e-30) / 0.5), 3)})
    print("passband %7.0f Hz -> %+.3f dB" % (f, pb[-1]["gain_db"]), flush=True)
OUT["passband"] = pb

# ------------------------- 6. minimum phase: pre-ringing before a hard onset
# A tone that switches on at t0 is the cleanest probe: a linear-phase filter MUST
# ring before t0 because it is non-causal; a minimum-phase one must not.
def onset_signal(f=1000.0, t0=1.0, total=2.0, fs=FS):
    n = int(fs * total)
    x = np.zeros(n)
    i0 = int(fs * t0)
    idx = np.arange(n - i0, dtype=np.int64)
    x[i0:] = 0.5 * np.sin(2 * np.pi * ((int(f) * idx) % fs) / fs)
    return x


def pre_ring_dbfs(phase, win_ms=2.0):
    x = onset_signal()
    y = res(x, FS, 96000, {"phase": phase})
    i0 = int(round(1.0 * 96000))
    win = y[max(0, i0 - int(win_ms / 1000.0 * 96000)): i0]
    return 20 * np.log10(max(float(np.sqrt(np.mean(win ** 2))), 1e-30))


mp = {}
for ph in ("linear", "min"):
    mp[ph] = round(pre_ring_dbfs(ph), 1)
    print("phase %-6s pre-ringing %7.1f dBFS" % (ph, mp[ph]), flush=True)
assert mp["min"] < mp["linear"] - 20, ("min-phase should kill pre-ringing", mp)
OUT["minphase"] = mp

# --------------------------------- 7. seven-engine single tone + IMD metrics
from srctool import quality  # noqa: E402
eng_rows = []
for key in ("dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"):
    if not engines.ENGINES[key].available:
        print("engine %-8s unavailable, skipped" % key, flush=True)
        continue
    m = quality.measure_engine(key, engines.default_opts(key), seconds=4.0)
    eng_rows.append({k: getattr(m, k) for k in
                     ("engine", "label", "spur_dbc", "image_dbc", "alias_dbc",
                      "imd_dbc", "imd_smpte_dbc", "mt_dbc", "passband_21500",
                      "passband_22000", "speed_x", "alias_na", "ratio_label")})
    print("engine %-8s spur %7.1f imd %7.1f mt %7.1f speed %5.0fx [%s]"
          % (key, m.spur_dbc, m.imd_dbc, m.mt_dbc, m.speed_x, m.ratio_label), flush=True)
OUT["engines"] = eng_rows

# ------------------------------------------------- 8. PGGB head-to-head
try:
    import pggb_run
    # Diagnostic: X4 must still be the signal built at the top. A stale copy, a
    # mutated buffer or a wrong reference length all show up as a null depth in
    # the 280-290 dB range instead of ~302, which is easy to mistake for a real
    # engine difference.
    print("  X4 rms %.9f  len %d" % (float(np.sqrt(np.mean(X4 * X4))), len(X4)),
          flush=True)
    yp, _ = pggb_run.run(np.stack([X4, X4], axis=1), FS, 4, precision=64, bits=64,
                         corner=22050)
    ref = tones(FREQS, PHS, AMPS, 176400, int(round(N4 * 4)))
    print("  yp len %d  rms %.9f  ref len %d" % (len(yp), float(np.sqrt(np.mean(yp[:, 0] ** 2))), len(ref)),
          flush=True)
    OUT["pggb"] = {"null_db": round(null_db(yp[:, 0], ref), 1)}
    x30 = np.random.default_rng(2).normal(0, 0.1, (FS * 30, 2))
    t0 = time.perf_counter()
    pggb_run.run(x30, FS, 4, precision=64, bits=64, corner=22050, timeout=1800)
    OUT["pggb"]["speed_x_30s_stereo"] = round(30.0 / (time.perf_counter() - t0), 1)
    t0 = time.perf_counter()
    engines.resample(x30, FS, 176400, "dpggb")
    OUT["pggb"]["dpggb_speed_x_30s_stereo"] = round(30.0 / (time.perf_counter() - t0), 1)
    yp2, _ = pggb_run.run(np.stack([X4, X4], axis=1), FS, 48000, precision=64, bits=64,
                          corner=22050)
    OUT["pggb"]["arbitrary_ratio_out_samples"] = int(len(yp2))
    OUT["pggb"]["arbitrary_ratio_expected"] = int(round(N4 * 48000 / 44100))
    print("PGGB:", OUT["pggb"], flush=True)
except Exception as exc:  # noqa: BLE001
    OUT["pggb"] = {"error": str(exc)[:300]}
    print("PGGB failed:", OUT["pggb"], flush=True)

os.makedirs(os.path.join(ROOT, "work"), exist_ok=True)
with open(os.path.join(ROOT, "work", "paper_data.json"), "w", encoding="utf-8") as fh:
    json.dump(OUT, fh, ensure_ascii=False, indent=1)
print("WROTE work/paper_data.json")
