# -*- coding: utf-8 -*-
"""单音 SINAD / SFDR / ENOB —— 高精度残差法。

为什么不能直接用 rfft 的 bin 能量：
    输出是 float64，一个满刻度 0.5 的正弦量化步长就是 2^-53·0.5 ≈ −320 dBc。
    用 np.fft 求谱时，基函数本身只有 1e-16 的相对精度、多项式求和又只有 sqrt(N)·eps，
    所以"扣掉基频 bin 后剩下的能量"这种教科书做法，地板在 −290…−307 dBc
    （见 srctool/quality.py:_tone_residual 的注释）。被测引擎正好就在这一带，
    读数会被尺子而不是被引擎决定。

这里改成"残差法 + 精确整数相位 + 双倍长舍入求和"：
    1. 基函数用整数相位 θ_n = 2π·((k·n) mod N)/N，k = f·N/fs 为整数 —— 相位无累积误差；
    2. 投影用 math.sumprod（内部双倍长累加），幅度 a、b 的求和误差降到 ~1e-19；
    3. 最小二乘减掉 c + a·cosθ + b·sinθ，再对残差重新投影一次（迭代精化），
       把"模型自身在 float64 里舍入"的那一层也扣掉；
    4. 残差功率 = Σr²/N（Parseval，等价于全带噪声+失真功率）。
    本机实测地板：把一条 50 位有效数字算出来、再舍入成 float64 的正弦喂进来，
    读数为 −320.4 dB（就是 2^-53 的量化本身）。所以 −300 dB 附近的读数是可信的，
    但它同时也说明：低于 −320 dB 的数字没有意义。

定义（与 IEEE Std 1241 / ADC 术语一致，但显式写出本文口径）：
    SINAD = 10·log10( P_signal / P_noise+distortion )，噪声+失真 = 残差的全带功率，
            P_signal = (a² + b²)/2，直流分量先作为 c 拟合掉、不计入噪声。
    SFDR  = 20·log10( A_signal / A_worst_spur )，A_worst_spur 是除掉直流与基频
            （±1 bin）后最大的单根谱线；窗长是整数周期，矩形窗无泄漏，bin 幅度即真实幅度。
    ENOB  = (SINAD_FS − 1.76) / 6.02，SINAD_FS 是把测试音折算到满刻度正弦（峰值 1.0）后的值；
            测试音幅度 0.5 时 SINAD_FS = SINAD + 6.02 dB。
    THD   = 各次谐波（2f…奈奎斯特）功率和 / 信号功率。
    SNR   = (P_noise+distortion − P_harmonics) / P_signal。
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

INBAND_HZ = 20000.0  # 带内 SINAD 的带宽上限
FS_AMP = 1.0          # 满刻度正弦峰值
FS_SINAD_OFFSET = 20.0 * math.log10(FS_AMP)   # 与测试音幅度无关的常数项，写在公式里

_BASIS_CACHE = {}


def basis(rate: int, freq: float, n: int):
    """整数相位基函数：返回 (k, cos 数组, sin 数组)。"""
    key = (rate, freq, n)
    if key in _BASIS_CACHE:
        return _BASIS_CACHE[key]
    kk = freq * n / rate
    k = int(round(kk))
    if abs(kk - k) > 1e-9:
        raise ValueError("窗长必须是 f/fs 的整数周期：k = %.6f" % kk)
    m = (np.arange(n, dtype=np.int64) * k) % n
    # 基函数必须比被测残差准一个数量级以上：float64 直接算 2π·m/n 会在 6e-16 rad
    # 量级上带进参数误差，把地板压到 -313 dB（正好等于被测引擎的量级）。
    # 所以用 60 位有效数字算好、再舍入成 float64，并缓存到磁盘。
    cache = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "work", "cache_basis_%d_%d.npz" % (n, k))
    if os.path.exists(cache):
        z = np.load(cache)
        c, s = z["c"], z["s"]
    else:
        import mpmath as mp
        mp.mp.dps = 60
        two_pi = 2 * mp.pi
        nn = mp.mpf(n)
        cc = np.empty(n, dtype=np.float64)
        ss = np.empty(n, dtype=np.float64)
        for i in range(n):
            th = two_pi * int(m[i]) / nn
            cc[i] = float(mp.cos(th))
            ss[i] = float(mp.sin(th))
        c, s = cc, ss
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        np.savez_compressed(cache, c=c, s=s)
    _BASIS_CACHE[key] = (k, c, s)
    return k, c, s


def _project(x: np.ndarray, c: np.ndarray, s: np.ndarray) -> tuple:
    n = x.size
    a = 2.0 * math.sumprod(x, c) / n
    b = 2.0 * math.sumprod(x, s) / n
    d = math.fsum(x) / n
    return d, a, b


def analyze(seg: np.ndarray, rate: int, freq: float, *, harmonics: int = 20,
            refine: int = 2, exclude_bins: int = 1) -> dict:
    """分析一个整数周期的窗，返回 SINAD/SFDR/ENOB/THD/SNR（dB）。"""
    x = np.asarray(seg, dtype=np.float64)
    n = x.size
    k, c, s = basis(rate, freq, n)

    d, a, b = _project(x, c, s)
    model = d + a * c + b * s
    r = x - model
    for _ in range(int(refine)):
        dd, da, db = _project(r, c, s)
        d += dd
        a += da
        b += db
        r = r - (dd + da * c + db * s)

    p_sig = 0.5 * (a * a + b * b)
    p_res = math.sumprod(r, r) / n
    p_res = max(p_res, 1e-300)

    spec = np.abs(np.fft.rfft(r)) * (2.0 / n)
    # 20 kHz 以内的残余功率（排除 22.05–44.1 kHz 的镜像区）：用来区分"带内底噪"
    # 与"镜像/杂散泄漏"，两者的物理来源完全不同。
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    inband = freqs <= INBAND_HZ
    p_in = float(math.fsum((spec[inband] ** 2).tolist()) / 2.0)
    keep = np.ones(spec.size, bool)
    keep[:3] = False                                   # 直流
    keep[max(0, k - exclude_bins): k + exclude_bins + 1] = False
    harm = []
    for h in range(2, harmonics + 2):
        hk = h * k
        if hk >= spec.size - 1:
            break
        harm.append(hk)
    mask_h = np.zeros(spec.size, bool)
    for hk in harm:
        mask_h[max(0, hk - 1): hk + 2] = True
    idx = np.flatnonzero(keep)
    j = idx[int(np.argmax(spec[idx]))] if idx.size else 0
    a_spur = float(spec[j]) if idx.size else 0.0
    p_harm = float(np.sum(spec[mask_h] ** 2) / 2.0)
    p_spur_rest = max(p_res - p_harm, 1e-300)

    amp_in = math.sqrt(2.0 * p_sig)
    sinad = 10.0 * math.log10(p_sig / p_res)
    sinad_fs = sinad + 20.0 * math.log10(FS_AMP / max(amp_in, 1e-300))
    return {
        "n": n,
        "bin": k,
        "amp": amp_in,
        "sinad_db": sinad,
        "sinad_fs_db": sinad_fs,
        "sinad_inband_db": 10.0 * math.log10(p_sig / max(p_in, 1e-300)),
        "sfdr_db": 20.0 * math.log10(max(amp_in, 1e-300) / max(a_spur, 1e-300)),
        "spur_hz": float(j) * rate / n,
        "enob_bits": (sinad_fs - 1.76) / 6.02,
        "enob_inband_bits": (10.0 * math.log10(p_sig / max(p_in, 1e-300))
                             + 20.0 * math.log10(FS_AMP / max(amp_in, 1e-300)) - 1.76) / 6.02,
        "thd_db": 10.0 * math.log10(max(p_harm, 1e-300) / p_sig),
        "snr_db": 10.0 * math.log10(p_spur_rest / p_sig),
    }


def ideal_tone(rate: int, freq: float, n: int, amp: float = 0.5, dps: int = 50) -> np.ndarray:
    """用 mpmath 按 50 位有效数字合成正弦，再舍入成 float64 —— 用来量尺子本身。"""
    import mpmath as mp
    mp.mp.dps = dps
    k = int(round(freq * n / rate))
    out = np.empty(n, dtype=np.float64)
    tw = 2 * mp.pi * k / n
    for i in range(n):
        out[i] = float(mp.mpf(amp) * mp.sin(tw * i))
    return out


def windows(y: np.ndarray, rate: int, count: int = 5) -> list:
    s = np.asarray(y[:, 0] if y.ndim > 1 else y, dtype=np.float64)
    n = s.size
    w = rate
    if n < 2 * w:
        raise RuntimeError("输出过短")
    # 首尾各让出 5%：输入的 20 ms 渐变会在输出首尾留下宽带成分，落进窗里会把
    # SINAD 从 305 dB 打到 20 dB —— 那是渐变，不是引擎。
    margin = int(0.05 * n)
    out = []
    for i in range(count):
        st = margin + int(round(i * (n - 2 * margin - w) / float(count - 1)))
        out.append(s[st: st + w])
    return out


def median(values):
    v = sorted(values)
    m = len(v) // 2
    return v[m] if len(v) % 2 else 0.5 * (v[m - 1] + v[m])


def measure_engine(engine: str, opts=None, *, src: int = 44100, dst: int = 88200,
                   freq: float = 1000.0, seconds: float = 16.0, count: int = 5) -> dict:
    from srctool import engines as E, quality as Q
    x = Q._tone(freq, src, seconds, 0.5)
    y = E.resample(x, src, dst, engine, opts if opts is not None else E.default_opts(engine))
    ws = windows(y, dst, count)
    rows = [analyze(w, dst, freq) for w in ws]
    return {
        "engine": engine,
        "sinad_db": median([r["sinad_db"] for r in rows]),
        "sinad_inband_db": median([r["sinad_inband_db"] for r in rows]),
        "sinad_fs_db": median([r["sinad_fs_db"] for r in rows]),
        "sfdr_db": median([r["sfdr_db"] for r in rows]),
        "enob_bits": median([r["enob_bits"] for r in rows]),
        "enob_inband_bits": median([r["enob_inband_bits"] for r in rows]),
        "thd_db": median([r["thd_db"] for r in rows]),
        "snr_db": median([r["snr_db"] for r in rows]),
        "spur_hz": rows[int(np.argmin([r["sfdr_db"] for r in rows]))]["spur_hz"],
        "worst": rows[int(np.argmin([r["sinad_db"] for r in rows]))]["sinad_db"],
        "windows": len(rows),
    }


def _validate(rate: int = 88200, freq: float = 1000.0, n: int = 88200) -> None:
    print("== 1. 尺子地板：50 位有效数字的正弦 → float64")
    y0 = ideal_tone(rate, freq, n, 0.5)
    r0 = analyze(y0, rate, freq)
    print("   SINAD %.2f dB  SFDR %.2f dB  ENOB %.2f bit" %
          (r0["sinad_db"], r0["sfdr_db"], r0["enob_bits"]))

    print("== 2. 合成已知失真：解析值 vs 读数")
    k, c, s = basis(rate, freq, n)
    for spur_db in (-60.0, -100.0, -140.0):
        a1 = 0.5
        a2 = a1 * 10 ** (spur_db / 20.0)
        y = a1 * s + a2 * np.sin(2 * np.pi * (3 * k % n) * np.arange(n) / n)
        r = analyze(y, rate, freq)
        want = 10 * math.log10((a1 * a1 / 2) / (a2 * a2 / 2))
        print("   spur %7.1f dB -> SINAD 读数 %7.2f / 解析 %7.2f | SFDR %7.2f (want %7.2f)" %
              (spur_db, r["sinad_db"], want, r["sfdr_db"], -spur_db))

    print("== 3. 与论文现用 float64 谱残差法交叉对照 (-100 dB 量级，两种方法都够用)")
    from srctool import quality as Q
    a2 = 0.5 * 10 ** (-100.0 / 20.0)
    y = 0.5 * s + a2 * np.sin(2 * np.pi * (3 * k % n) * np.arange(n) / n)
    old, _lvl = Q._tone_residual(y, rate, [freq])
    new = analyze(y, rate, freq)["sinad_db"]
    print("   _tone_residual %8.2f dBc | 新法 SINAD %8.2f dB | 差 %.2f dB" %
          (old, new, abs(abs(old) - new)))

    print("== 4. 灵敏度：注入 a3*x^3（x 幅度 0.5）")
    for a3 in (1e-3, 1e-4, 1e-5, 1e-6):
        y = 0.5 * s + a3 * (0.5 * s) ** 3
        r = analyze(y, rate, freq)
        print("   a3=%8.0e -> SINAD %8.2f dB  ENOB %6.2f bit  SFDR %8.2f dB" %
              (a3, r["sinad_db"], r["enob_bits"], r["sfdr_db"]))

    print("== 5. 解析自检：SFDR/ENOB 公式")
    print("   ENOB(302 dB SINAD_FS) = %.2f bit" % ((302.0 - 1.76) / 6.02))


def profile(y: np.ndarray, rate: int, freq: float, *, step: float = 0.25,
            margin: float = 0.05, win: float = 1.0) -> list:
    """用 1 s 窗铺满整个输出（每 step 秒取一个），返回逐窗读数。

    首尾各让出 margin：输入的 20 ms 渐变落进窗里会把 SINAD 从 305 dB 打到 20 dB，
    那是激励的边界，不是引擎的。窗长取整数个周期，矩形窗无泄漏。
    """
    s = np.asarray(y[:, 0] if y.ndim > 1 else y, dtype=np.float64)
    n = s.size
    w = int(round(win * rate))
    m = int(round(margin * n))
    out = []
    st = m
    while st + w <= n - m:
        r = analyze(s[st:st + w], rate, freq)
        r["t"] = st / float(rate)
        out.append(r)
        st += int(round(step * rate))
    return out


def _median_row(rows: list) -> dict:
    def med(k):
        return median([r[k] for r in rows])
    return {
        "sinad_db": med("sinad_db"),
        "sinad_inband_db": med("sinad_inband_db"),
        "sinad_fs_db": med("sinad_fs_db"),
        "sfdr_db": med("sfdr_db"),
        "enob_bits": med("enob_bits"),
        "enob_inband_bits": med("enob_inband_bits"),
        "amp": med("amp"),
        "windows": len(rows),
    }


def measure_engine_full(engine: str, opts=None, *, src: int = 44100, dst: int = 88200,
                        freq: float = 1000.0, seconds: float = 16.0,
                        step: float = 0.25, settled_from: float = 2.0,
                        settled_to: float = 13.0) -> dict:
    """整段测量：在"平稳区"取中位数，在全部窗里取最差一秒。

    两件事必须分开报：平稳区回答"引擎在稳定状态下能做到多少"（这时每台都贴
    float64 地板，差异不可复现）；最差一秒回答"交付的文件里有没有一秒被
    边界效应污染"。后者才区分得开分块处理的引擎。
    """
    from srctool import engines as E, quality as Q
    x = Q._tone(freq, src, seconds, 0.5)
    y = E.resample(x, src, dst, engine, opts if opts is not None else E.default_opts(engine))
    prof = profile(y, dst, freq, step=step)
    settled = [r for r in prof if settled_from <= r["t"] <= settled_to]
    worst = min(prof, key=lambda r: r["sinad_db"])
    row = {"engine": engine, "settled": _median_row(settled),
           "worst": {k: worst[k] for k in
                     ("t", "sinad_db", "sinad_inband_db", "sinad_fs_db", "sfdr_db",
                      "enob_bits", "enob_inband_bits", "amp", "spur_hz")},
           "profile": [[round(r["t"], 3), round(r["sinad_db"], 2),
                        round(r["sinad_inband_db"], 2)] for r in prof]}
    row["settled"]["engine"] = engine
    return row


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        _validate()
        sys.exit(0)
    keys = [a for a in sys.argv[1:] if not a.startswith("-")] or \
        ["dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"]
    rows = []
    print("%-7s %9s %9s %9s | %7s %8s %7s" %
          ("engine", "SINAD", "<20k", "SFDR", "worst@t", "worst", "ENOBw"))
    for key in keys:
        m = measure_engine_full(key)
        rows.append(m)
        st, wo = m["settled"], m["worst"]
        print("%-7s %9.1f %9.1f %9.1f | %7.2f %8.1f %7.2f" %
              (key, st["sinad_db"], st["sinad_inband_db"], st["sfdr_db"],
               wo["t"], wo["sinad_db"], wo["enob_bits"]))
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "work", "sinad_profile.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"protocol": "16 s, 1 kHz, amp 0.5, 44.1→88.2; 1 s windows every 0.25 s "
                               "tiling the whole output (20 ms fades excluded); settled = "
                               "median over t in [2, 13] s; worst = min over all windows",
                   "rows": rows}, f, ensure_ascii=False, indent=1)
    print("WROTE", out)
