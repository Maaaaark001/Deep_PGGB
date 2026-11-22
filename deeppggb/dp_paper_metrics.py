# -*- coding: utf-8 -*-
"""论文用的最终指标集（修正口径）。输出 work/paper_metrics.json。"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from srctool import quality as Q, engines as E

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "work", "paper_metrics.json")

def center(y, n):
    s = np.asarray(y[:, 0], dtype=np.float64)
    st = (s.shape[0] - n) // 2
    return s[st:st + n]

D = {}

# ---------- 1. 八引擎 ----------
keys = ["dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"]
rows = {}
for k in keys:
    o = E.default_opts(k)
    m = Q.measure_engine(k, o, do_speed=False)
    # 速度：10 秒立体声 44.1->88.2（所有引擎都能做的倍率）
    xs = np.repeat(Q._tone(1000.0, 44100, 10.0), 2, axis=1)
    best = None
    for _ in range(2):
        t0 = time.perf_counter()
        E.resample(xs, 44100, 88200, k, o)
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    rows[k] = dict(label=m.label, spur=m.spur_dbc, image=m.image_dbc,
                   alias=(None if m.alias_na else m.alias_dbc),
                   ccif=m.imd_dbc, smpte=m.imd_smpte_dbc, multi=m.mt_dbc,
                   pb215=m.passband_21500, pb220=m.passband_22000,
                   speed=round(10.0 / best, 1), ok=m.ok, error=m.error)
    print("%-7s %8.1f %8.1f %8s %8.1f %8.1f %8.1f %6.0f" %
          (k, m.spur_dbc, m.image_dbc, ("n/a" if m.alias_na else "%8.1f" % m.alias_dbc),
           m.imd_dbc, m.imd_smpte_dbc, m.mt_dbc, rows[k]["speed"]))
D["engines"] = rows
D["engines_ratio"] = "上行指标统一 44.1→88.2（×2）；混叠 96→44.1；速度 10 s 立体声 44.1→88.2"

# ---------- 2. 地板 ----------
fl = {}
s = center(Q._tone(1000.0, 88200, 4.0), 88200)
fl["spur"] = Q._tone_residual(s, 88200, [1000.0])[0]
lvl = Q._line_level(s, 88200, 1000.0)
fl["image"] = Q._band_level_db(s, 88200, 43100.0, 44100.0, lvl)
xi = center(Q._two_tone(*Q.IMD_CCIF, 88200, 4.0, 0.25, 0.25), 88200)
fl["ccif"] = Q._worst_product(xi, 88200, (2*19000-20000, 2*20000-19000, 1000, 39000), Q.IMD_CCIF)[0]
xs2 = center(Q._two_tone(*Q.IMD_SMPTE, 88200, 4.0, 0.40, 0.10), 88200)
f2s = Q.IMD_SMPTE[1]
fl["smpte"] = Q._worst_product(xs2, 88200, [f2s + i*60 for i in (-2,-1,1,2)], f2s)[0]
xm, mtf = Q._multitone(88200, 4.0)
fl["multi"] = Q._tone_residual(center(xm, 88200), 88200, mtf)[0]
sa = center(Q._tone(1000.0, 44100, 4.0, 0.5) + Q._tone(14100.0, 44100, 4.0, 0.5), 44100)
ra = max(Q._line_level(sa, 44100, 1000.0), Q.EPS)
fl["alias_ref"] = 20 * np.log10(max(Q._line_level(sa, 44100, 14100.0), Q.EPS) / ra)
print("floors:", json.dumps({k: round(v, 1) for k, v in fl.items()}))
D["floors"] = {k: round(float(v), 1) for k, v in fl.items()}

# ---------- 3. sox_ng 全零语义 ----------
sx = {}
for f in (22050.0, 23000.0, 25000.0, 30000.0, 35000.0):
    seg = center(E.resample(Q._tone(f, 96000, 4.0), 96000, 44100, "soxng", E.default_opts("soxng")), 44100)
    sx["pure_%.0f" % f] = dict(zeros=int(np.sum(seg == 0)), n=int(seg.shape[0]),
                               peak=float(np.max(np.abs(seg))))
print("soxng pure-stopband:", json.dumps(sx))
D["soxng_zero"] = sx

# 三态：只有通带音 / 只有阻带音 / 双音
three = {}
for k in ("soxng", "dpggb", "r8b", "soxr"):
    o = E.default_opts(k)
    res = {}
    for name, x in (("ref_only", Q._tone(1000.0, 96000, 4.0, 0.5)),
                    ("aggr_only", Q._tone(30000.0, 96000, 4.0, 0.5)),
                    ("both", Q._tone(1000.0, 96000, 4.0, 0.5) + Q._tone(30000.0, 96000, 4.0, 0.5))):
        seg = center(E.resample(x, 96000, 44100, k, o), 44100)
        ref = max(Q._line_level(seg, 44100, 1000.0), Q.EPS)
        res[name] = round(float(20*np.log10(max(Q._line_level(seg, 44100, 14100.0), Q.EPS)/ref)), 1)
        res[name + "_zeros"] = int(np.sum(seg == 0))
    three[k] = res
print("alias three-state:", json.dumps(three))
D["alias_three_state"] = three

# ---------- 4. 杂散排除宽度 ----------
excl = {}
for name, k, o in (("dpggb", "dpggb", None), ("dpggb_long", "dpggb", {"prec": "long"}), ("pggb", "pggb", None)):
    s = center(E.resample(Q._tone(1000.0, 44100, 4.0), 44100, 88200, k, o), 88200)
    n = s.shape[0]
    spec = np.abs(np.fft.rfft(s)) * 2.0 / n
    freqs = np.fft.rfftfreq(n, 1.0 / 88200)
    kk = int(round(1000.0 * n / 88200))
    ref = max(Q._line_level(s, 88200, 1000.0), Q.EPS)
    row = {}
    for half in (3, 10, 50, 200):
        keep = np.ones(spec.shape[0], bool)
        keep[max(0, kk-half): kk+half+1] = False
        keep[:4] = False
        keep &= (freqs >= 20) & (freqs <= 20000)
        idx = np.flatnonzero(keep)
        j = idx[int(np.argmax(spec[idx]))]
        row["pm%d" % half] = [round(float(20*np.log10(max(spec[j], Q.EPS)/ref)), 1), round(float(freqs[j]), 1)]
    excl[name] = row
print("exclusion:", json.dumps(excl))
D["spur_exclusion"] = excl

# ---------- 5. context 扫描 ----------
ctx = {}
for c in (200.0, 400.0, 600.0, 800.0, 1200.0):
    m = Q.measure_engine("dpggb", {"context": c}, do_speed=False)
    x60 = np.repeat(Q._tone(1000.0, 44100, 60.0), 2, axis=1)
    best = None
    for _ in range(2):
        t0 = time.perf_counter()
        E.resample(x60, 44100, 88200, "dpggb", {"context": c})
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    ctx["%.0f" % c] = dict(image=round(m.image_dbc, 1), spur=round(m.spur_dbc, 1),
                           speed=round(60.0/best, 1))
    print("ctx %4.0f  image %7.1f  spur %7.1f  %5.0fx" % (c, m.image_dbc, m.spur_dbc, 60.0/best))
D["context_sweep"] = ctx

# ---------- 6. PGGB 速度对照 ----------
x30 = np.repeat(Q._tone(1000.0, 44100, 30.0), 2, axis=1)
pair = {}
for k in ("dpggb", "pggb"):
    best = None
    for _ in range(2):
        t0 = time.perf_counter()
        E.resample(x30, 44100, 176400, k, E.default_opts(k))
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    pair[k] = round(30.0/best, 1)
print("30 s stereo 44.1->176.4:", pair)
D["speed_pair"] = pair

json.dump(D, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", OUT)
