"""音频质量度量：电平、响度(LUFS)、真峰值、有效位深、带宽、频谱、削波、立体声场。

所有函数只依赖 numpy / scipy / soxr，不引入新依赖。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

import numpy as np

EPS = 1e-20


# --------------------------------------------------------------------------
# 基础电平
# --------------------------------------------------------------------------
def db(x: float | np.ndarray, floor: float = -200.0) -> float | np.ndarray:
    """幅度比 -> dB，带下限，避免 log(0)。"""
    with np.errstate(divide="ignore", invalid="ignore"):
        v = 20.0 * np.log10(np.maximum(np.abs(x), EPS))
    return np.maximum(v, floor) if not np.isscalar(v) else float(max(v, floor))


# 长音频一律分块处理：424 秒立体声是 1870 万帧 × 2 声道 = 300 MB，
# 任何 np.abs(y) / y ** 2 这类整段临时数组都会瞬间再吃掉几百 MB；
# 而早期的"花式索引取重叠块"写法（z[idx]）更是把内存放大到 8 GB 级别。
_CHUNK_ROWS = 1 << 20          # 每块 100 万帧（8 MB/声道）
_BITDEPTH_SAMPLES = 2_000_000  # 量化残差抽样上限（再多也不会更准）


def _iter_chunks(y: np.ndarray, chunk: int = _CHUNK_ROWS):
    """按帧切块遍历，块内统一 float64 且至少二维 (frames, channels)。"""
    n = int(y.shape[0])
    for s in range(0, n, chunk):
        blk = np.asarray(y[s:s + chunk], dtype=np.float64)
        if blk.ndim == 1:
            blk = blk[:, None]
        if blk.shape[0]:
            yield s, blk


def peak_dbfs(y: np.ndarray) -> float:
    if y.size == 0:
        return -200.0
    pk = 0.0
    for _, blk in _iter_chunks(y):
        pk = max(pk, float(np.max(np.abs(blk))))
    return float(db(pk))


def rms_dbfs(y: np.ndarray) -> float:
    if y.size == 0:
        return -200.0
    acc = 0.0
    cnt = 0
    for _, blk in _iter_chunks(y):
        acc += float(np.sum(np.square(blk)))
        cnt += int(blk.size)
    return float(db(math.sqrt(acc / max(cnt, 1)) + EPS))


def crest_factor_db(y: np.ndarray) -> float:
    r = rms_dbfs(y)
    return float(peak_dbfs(y) - r) if r > -199 else 0.0


def dc_offset(y: np.ndarray) -> float:
    if y.size == 0:
        return 0.0
    acc = 0.0
    cnt = 0
    for _, blk in _iter_chunks(y):
        acc += float(np.sum(blk))
        cnt += int(blk.size)
    return acc / max(cnt, 1)


def dc_dbfs(y: np.ndarray) -> float:
    return float(db(abs(dc_offset(y))))


def clip_stats(y: np.ndarray, threshold: float = 0.999) -> dict:
    """统计达到/超过满刻度的样本数与最长连续段。"""
    if y.size == 0:
        return {"samples": 0, "ratio": 0.0, "longest_run": 0, "count": 0}
    n = int(y.shape[0])
    # hot 每帧只占 1 字节（424 秒 = 18 MB），比整段 abs() 便宜一个数量级
    hot = np.zeros(n, dtype=bool)
    for s, blk in _iter_chunks(y):
        hot[s:s + blk.shape[0]] = (np.abs(blk) >= threshold).any(axis=1)
    cnt = int(hot.sum())
    longest = 0
    if cnt:
        # 只在有热点时做差分扫描，避免长文件全量循环
        d = np.diff(np.concatenate(([0], hot.view(np.int8), [0])))
        starts = np.flatnonzero(d == 1)
        ends = np.flatnonzero(d == -1)
        if starts.size:
            longest = int(np.max(ends - starts))
    return {"samples": cnt, "ratio": cnt / float(n), "longest_run": longest,
            "count": cnt}


# --------------------------------------------------------------------------
# 真峰值（4x 过采样）
# --------------------------------------------------------------------------
def true_peak_dbtp(y: np.ndarray, rate: int, oversample: int = 4,
                   chunk: int = 1 << 18) -> float:
    """ITU-R BS.1770 建议的 4 倍过采样真峰值。

    整段一次性上采样在长音频上是灾难：424 秒立体声 4 倍过采样 = 1.2 GB 的
    float64。这里改用 soxr 的流式重采样器，只保留一块输出并累计峰值。
    """
    if y.size == 0:
        return -200.0
    if rate * oversample > 384000 * 4 or y.shape[0] < 8:
        return peak_dbfs(y)
    nch = int(y.shape[1]) if y.ndim > 1 else 1
    try:
        import soxr

        st = soxr.ResampleStream(rate, rate * oversample, nch,
                                 dtype="float64", quality="HQ")
        pk = 0.0
        for _, blk in _iter_chunks(y, chunk):
            out = st.resample_chunk(blk, last=False)
            if out.size:
                pk = max(pk, float(np.abs(out).max()))
        tail = st.resample_chunk(np.zeros((0, nch)), last=True)
        if tail.size:
            pk = max(pk, float(np.abs(tail).max()))
        return float(db(pk))
    except Exception:
        try:
            import soxr

            up = soxr.resample(np.asarray(y, dtype=np.float64), rate,
                               rate * oversample, quality="HQ")
            return peak_dbfs(up)
        except Exception:
            return peak_dbfs(y)


# --------------------------------------------------------------------------
# LUFS (ITU-R BS.1770-4 / EBU R128)
# --------------------------------------------------------------------------
def _k_coeffs(rate: int):
    """BS.1770-4 的 K 计权系数：一级高架 + 一级高通，按采样率重算。"""
    # 48 kHz 参考系数（BS.1770-4 表 1/2），其它采样率按双线性变换重算
    f0, G, Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    K = math.tan(math.pi * f0 / rate)
    Vh = 10.0 ** (G / 20.0)
    Vb = Vh ** 0.4996667741545416
    a0 = 1.0 + K / Q + K * K
    b1 = np.array([(Vh + Vb * K / Q + K * K) / a0, 2.0 * (K * K - Vh) / a0,
                   (Vh - Vb * K / Q + K * K) / a0])
    a1 = np.array([1.0, 2.0 * (K * K - 1.0) / a0, (1.0 - K / Q + K * K) / a0])

    f0, Q = 38.13547087602444, 0.5003270373238773
    K = math.tan(math.pi * f0 / rate)
    b2 = np.array([1.0, -2.0, 1.0])
    a2 = np.array([1.0, 2.0 * (K * K - 1.0) / (1.0 + K / Q + K * K),
                   (1.0 - K / Q + K * K) / (1.0 + K / Q + K * K)])
    return b1, a1, b2, a2


def _k_weight_iter(y: np.ndarray, rate: int, chunk: int = _CHUNK_ROWS):
    """分块 K 计权，逐块产出 (起始帧, 数据)；滤波状态跨块传递，结果与整段一致。"""
    import scipy.signal as sig

    b1, a1, b2, a2 = _k_coeffs(rate)
    nch = int(y.shape[1]) if y.ndim > 1 else 1
    zi1 = np.zeros((max(len(a1), len(b1)) - 1, nch))
    zi2 = np.zeros((max(len(a2), len(b2)) - 1, nch))
    for s, blk in _iter_chunks(y, chunk):
        blk = blk.reshape(-1, nch)
        blk, zi1 = sig.lfilter(b1, a1, blk, axis=0, zi=zi1)
        blk, zi2 = sig.lfilter(b2, a2, blk, axis=0, zi=zi2)
        yield s, blk


def _k_weight(y: np.ndarray, rate: int) -> np.ndarray:
    """K 计权（整段返回，仅短素材使用）。"""
    x = np.asarray(y, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    out = np.empty(x.shape, dtype=np.float64)
    for s, blk in _k_weight_iter(x, rate):
        out[s:s + blk.shape[0]] = blk
    return out


def _squared_cumsum(y: np.ndarray, rate: int,
                    chunk: int = _CHUNK_ROWS) -> np.ndarray:
    """K 计权 → 逐帧平方 → 累积和，返回 (n+1, nch)。

    峰值内存只有一份 n×nch 的累积和，不物化整段 K 计权信号。
    """
    n = int(y.shape[0])
    nch = int(y.shape[1]) if y.ndim > 1 else 1
    csum = np.empty((n + 1, nch), dtype=np.float64)
    csum[0] = 0.0
    for s, blk in _k_weight_iter(y, rate, chunk):
        blk = blk.reshape(-1, nch)
        seg = csum[s + 1:s + 1 + blk.shape[0]]
        np.cumsum(blk * blk, axis=0, out=seg)
        seg += csum[s]
    return csum


def _block_ms(csum: np.ndarray, w: np.ndarray, block: int, hop: int) -> np.ndarray:
    """由前缀和求每个重叠块的加权均方 —— 两个前缀和相减，零拷贝。"""
    n = csum.shape[0] - 1
    if n < block:
        return np.zeros(0)
    nb = 1 + (n - block) // hop
    starts = np.arange(nb) * hop
    seg = csum[starts + block] - csum[starts]
    return (seg @ w) / float(block)


def _channel_weights(nch: int) -> np.ndarray:
    """BS.1770 声道权重：L/R/C=1.0，环绕=1.41，LFE=0。"""
    if nch == 1:
        return np.array([1.0])
    if nch == 2:
        return np.array([1.0, 1.0])
    w = np.ones(nch)
    if nch >= 6:
        w[3] = 1.41
        w[4] = 1.41
        w[5] = 0.0
    return w


def loudness(y: np.ndarray, rate: int) -> dict:
    """返回 integrated / short-term max / loudness range 与 true peak。"""
    empty = {"integrated": -70.0, "short_term_max": -70.0, "lra": 0.0,
             "momentary_max": -70.0}
    if y.size == 0 or rate <= 0:
        return empty
    nch = y.shape[1]
    if nch > 6:  # 超 5.1 时退化为逐声道 1.0 权重
        w = np.ones(nch)
    else:
        w = _channel_weights(nch)
    block = int(0.4 * rate)          # 400 ms 门限块
    hop = int(0.1 * rate)            # 75% 重叠
    if block < 8 or y.shape[0] < block:
        z = _k_weight(y, rate)
        ms = float(np.sum(np.mean(z ** 2, axis=0) * w))
        l = -0.691 + 10 * math.log10(max(ms, EPS))
        return {"integrated": max(l, -70.0), "short_term_max": max(l, -70.0),
                "lra": 0.0, "momentary_max": max(l, -70.0)}
    csum = _squared_cumsum(y, rate)
    ms = _block_ms(csum, w, block, hop)                     # (n,)
    lk = -0.691 + 10 * np.log10(np.maximum(ms, EPS))

    # 绝对门限 -70 LUFS
    g1 = ms[lk > -70.0]
    if g1.size == 0:
        return empty
    rel = -0.691 + 10 * math.log10(max(float(np.mean(g1)), EPS)) - 10.0
    g2 = ms[(lk > -70.0) & (lk > rel)]
    integrated = -0.691 + 10 * math.log10(max(float(np.mean(g2 if g2.size else g1)), EPS))

    # 短时（3 s）与瞬时（400 ms）
    st_block = int(3.0 * rate)
    if y.shape[0] >= st_block:
        sms = _block_ms(csum, w, st_block, hop)
        st = -0.691 + 10 * np.log10(np.maximum(sms, EPS))
        short_term_max = float(np.max(st))
        st_g = st[st > -70.0]
        lra = float(np.percentile(st_g, 95) - np.percentile(st_g, 10)) if st_g.size > 2 else 0.0
    else:
        short_term_max = float(np.max(lk))
        lra = 0.0
    return {"integrated": float(integrated), "short_term_max": short_term_max,
            "lra": float(max(lra, 0.0)), "momentary_max": float(np.max(lk))}


# --------------------------------------------------------------------------
# 有效位深 / 带宽 / 噪声底
# --------------------------------------------------------------------------
def effective_bit_depth(y: np.ndarray, max_bits: int = 32) -> dict:
    """用"最小量化台阶"估计有效位深。

    对每个候选位深 b，把样本量化到 b bit 后计算残差；
    残差首次低于 -140 dBFS 的 b 即为有效位深（量化噪声淹没在真实噪声之下时会被高估，
    因此同时返回 measured 值供参考）。
    """
    if y.size == 0:
        return {"bits": 0, "residual_db": -200.0}
    peak = 0.0
    for _, blk in _iter_chunks(y):
        peak = max(peak, float(np.max(np.abs(blk))))
    if peak < 1e-9:
        return {"bits": 0, "residual_db": -200.0}
    # 量化残差只需要一个代表性样本集：整段 3700 万样本 × 最多 28 轮迭代
    # 会白烧几十秒，而量化台阶在任意 200 万样本上都一样清楚。
    flat = np.asarray(y, dtype=np.float64).reshape(-1)
    stride = max(1, flat.size // _BITDEPTH_SAMPLES)
    x = flat[::stride] / peak          # 归一化到满刻度
    best = max_bits
    best_res = -200.0
    for b in range(4, max_bits + 1):
        step = 2.0 ** (1 - b)
        res = float(np.sqrt(np.mean((x - np.round(x / step) * step) ** 2)))
        res_db = float(db(res + EPS))
        if res_db < -138.0:
            best = b
            best_res = res_db
            break
    return {"bits": best, "residual_db": best_res, "peak_normalized": True}


def noise_floor_db(y: np.ndarray, rate: int) -> float:
    """用最安静的 5% 帧估计本底噪声。"""
    if y.size == 0:
        return -200.0
    flen = max(256, int(0.02 * rate))
    n = y.shape[0] // flen
    if n < 4:
        return rms_dbfs(y)
    # 逐块按帧对齐计算帧能量，避免 reshape 整段（424 秒会再复制 300 MB）
    per_chunk = max(1, _CHUNK_ROWS // flen)
    energies = []
    for s in range(0, n * flen, per_chunk * flen):
        blk = np.asarray(y[s:s + per_chunk * flen], dtype=np.float64)
        if blk.ndim == 1:
            blk = blk[:, None]
        m = blk.shape[0] // flen
        if m <= 0:
            break
        fr = blk[: m * flen].reshape(m, flen, -1)
        energies.append(np.mean(fr ** 2, axis=(1, 2)))
    if not energies:
        return rms_dbfs(y)
    r = np.sqrt(np.concatenate(energies))
    r.sort()
    k = max(1, r.size // 20)
    return float(db(float(np.mean(r[:k])) + EPS))


def bandwidth_hz(y: np.ndarray, rate: int, drop_db: float = 60.0,
                 seg_seconds: float = 2.0) -> dict:
    """估计实际信号带宽：平均功率谱相对峰值下降 drop_db 的最高频率。"""
    if y.size == 0 or rate <= 0:
        return {"hz": 0.0, "ratio": 0.0}
    seg = min(y.shape[0], int(seg_seconds * rate))
    start = max(0, (y.shape[0] - seg) // 2)
    x = np.asarray(y[start:start + seg, 0], dtype=np.float64)
    if x.size < 64:
        return {"hz": 0.0, "ratio": 0.0}
    win = np.hanning(x.size)
    spec = np.abs(np.fft.rfft(x * win)) ** 2
    freqs = np.fft.rfftfreq(x.size, 1.0 / rate)
    # 按 1/24 倍频程平滑
    dbp = 10 * np.log10(np.maximum(spec, EPS))
    peak = float(np.max(dbp))
    thr = peak - drop_db
    above = np.flatnonzero(dbp > thr)
    if above.size == 0:
        return {"hz": 0.0, "ratio": 0.0}
    hz = float(freqs[above[-1]])
    return {"hz": hz, "ratio": hz / (rate / 2.0), "threshold_db": -drop_db}


# --------------------------------------------------------------------------
# 频谱 / 频谱图
# --------------------------------------------------------------------------
def spectrum(y: np.ndarray, rate: int, fft_size: int = 8192,
             seg_seconds: float = 3.0) -> dict:
    """Welch 平均功率谱，返回对数频率轴与 dB 值（供 ECharts 使用）。"""
    if y.size == 0 or rate <= 0:
        return {"freq": [], "db": [], "fmax": 0}
    seg = min(y.shape[0], int(seg_seconds * rate))
    start = max(0, (y.shape[0] - seg) // 2)
    x = np.asarray(y[start:start + seg], dtype=np.float64)
    n = 1 << max(10, int(math.log2(max(64, min(fft_size, x.shape[0])))))
    hop = n // 2
    if x.shape[0] < n:
        x = np.pad(x, ((0, n - x.shape[0]), (0, 0)))
    win = np.hanning(n)[:, None]
    cnt = max(1, (x.shape[0] - n) // hop + 1)
    acc = np.zeros(n // 2 + 1)
    for i in range(cnt):
        blk = x[i * hop:i * hop + n]
        if blk.shape[0] < n:
            break
        acc += np.mean(np.abs(np.fft.rfft(blk * win, axis=0)) ** 2, axis=1)
    acc /= max(cnt, 1)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    dbv = 10 * np.log10(np.maximum(acc, EPS))
    # 峰值归一到 0 dB
    dbv = dbv - float(np.max(dbv))
    # 对数降采样到 ~600 点，保证前端流畅
    target = 600
    if freqs.size > target:
        edges = np.unique(np.round(np.logspace(0, math.log10(freqs.size - 1),
                                               target + 1)).astype(int))
        edges = np.clip(edges, 0, freqs.size - 1)
        f2, d2 = [], []
        for a, b in zip(edges[:-1], edges[1:]):
            if b <= a:
                continue
            f2.append(float(freqs[(a + b) // 2]))
            d2.append(float(np.max(dbv[a:b])))
        freqs, dbv = np.array(f2), np.array(d2)
    return {"freq": [round(float(v), 1) for v in freqs],
            "db": [round(float(v), 2) for v in dbv],
            "fmax": float(rate / 2.0)}


def spectrogram(y: np.ndarray, rate: int, n_fft: int = 1024, frames: int = 260,
                fmax: float | None = None) -> dict:
    """返回 ECharts heatmap 需要的 [x, y, value] 三元组。"""
    if y.size == 0 or rate <= 0:
        return {"data": [], "tmax": 0, "fmax": 0}
    # 只读第一声道，但绝不复制整段：长音频里 y[:, 0] 就是 150 MB 的副本，
    # 而我们真正需要的只是 260 个 1024 点窗。
    total = int(y.shape[0])
    n_fft = 1 << max(8, int(math.log2(max(64, min(n_fft, total)))))
    hop = max(1, (total - n_fft) // max(1, frames))
    if hop < 1 or total < n_fft:
        return {"data": [], "tmax": 0, "fmax": 0}
    win = np.hanning(n_fft)
    nbins = n_fft // 2 + 1
    fmax = fmax or rate / 2.0
    kmax = int(nbins * fmax / (rate / 2.0))
    kmax = max(8, min(nbins, kmax))
    step = max(1, kmax // 96)
    ys = list(range(0, kmax, step))
    xs = list(range(0, frames))
    rows = []
    vmax = -200.0
    mat = np.empty((frames, len(ys)))
    for i in xs:
        blk = np.asarray(y[i * hop:i * hop + n_fft, 0], dtype=np.float64)
        if blk.shape[0] < n_fft:
            break
        m = np.abs(np.fft.rfft(blk * win))[:kmax]
        v = 20 * np.log10(np.maximum(m, EPS))
        mat[i] = v[ys]
        vmax = max(vmax, float(v[ys].max()))
    mat = np.maximum(mat - vmax, -90.0)
    for i in xs:
        for j, k in enumerate(ys):
            rows.append([i, j, round(float(mat[i, j]), 1)])
    return {"data": rows, "tmax": frames,
            "fmax": round(kmax * (rate / 2.0) / nbins, 1),
            "nyquist": rate / 2.0}


# --------------------------------------------------------------------------
# 立体声场
# --------------------------------------------------------------------------
def stereo_stats(y: np.ndarray) -> dict:
    if y.ndim < 2 or y.shape[1] < 2:
        return {"available": False}
    # 分块累加五个矩，避免为 424 秒素材各复制两份 150 MB 的声道
    n = 0
    s_l = s_r = 0.0
    q_l = q_r = q_m = q_s = 0.0
    for _, blk in _iter_chunks(y):
        if blk.shape[1] < 2:
            return {"available": False}
        l = blk[:, 0]
        r = blk[:, 1]
        n += l.size
        s_l += float(np.sum(l))
        s_r += float(np.sum(r))
        q_l += float(np.sum(l * l))
        q_r += float(np.sum(r * r))
        mid = (l + r) * 0.5
        side = (l - r) * 0.5
        q_m += float(np.sum(mid * mid))
        q_s += float(np.sum(side * side))
    if n < 2:
        return {"available": False}
    m_l, m_r = s_l / n, s_r / n
    v_l = max(q_l / n - m_l * m_l, 0.0)
    v_r = max(q_r / n - m_r * m_r, 0.0)
    sl, sr = math.sqrt(v_l), math.sqrt(v_r)
    # 相关系数由协方差推得，需要单独累加 l*r
    cov = 0.0
    for _, blk in _iter_chunks(y):
        cov += float(np.sum(blk[:, 0] * blk[:, 1]))
    cov = cov / n - m_l * m_r
    corr = float(cov / (sl * sr)) if sl > 1e-12 and sr > 1e-12 else 1.0
    corr = max(-1.0, min(1.0, corr))
    return {
        "available": True,
        "correlation": round(corr, 4),
        "lr_balance_db": round(float(db(sl + EPS) - db(sr + EPS)), 2),
        "side_mid_db": round(float(db(math.sqrt(q_s / n) + EPS)
                                   - db(math.sqrt(q_m / n) + EPS)), 2),
        "mono_compat": round(corr, 4),
    }


# --------------------------------------------------------------------------
# 汇总
# --------------------------------------------------------------------------
@dataclass
class AudioReport:
    """一份完整的音频体检报告。"""

    rate: int = 0
    channels: int = 0
    frames: int = 0
    duration: float = 0.0
    peak_dbfs: float = -200.0
    true_peak_dbtp: float = -200.0
    rms_dbfs: float = -200.0
    crest_db: float = 0.0
    lufs: dict = field(default_factory=dict)
    dc_dbfs: float = -200.0
    noise_floor_dbfs: float = -200.0
    effective_bits: int = 0
    bit_residual_db: float = -200.0
    bandwidth: dict = field(default_factory=dict)
    clipping: dict = field(default_factory=dict)
    stereo: dict = field(default_factory=dict)
    spectrum: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def analyze(y: np.ndarray, rate: int, *, with_spectrum: bool = True,
            with_true_peak: bool = True) -> AudioReport:
    rep = AudioReport(rate=int(rate), channels=int(y.shape[1]) if y.ndim > 1 else 1,
                      frames=int(y.shape[0]))
    if y.size == 0:
        return rep
    rep.duration = rep.frames / float(rate) if rate else 0.0
    rep.peak_dbfs = round(peak_dbfs(y), 2)
    rep.true_peak_dbtp = round(true_peak_dbtp(y, rate) if with_true_peak else rep.peak_dbfs, 2)
    rep.rms_dbfs = round(rms_dbfs(y), 2)
    rep.crest_db = round(crest_factor_db(y), 2)
    rep.lufs = {k: round(v, 2) for k, v in loudness(y, rate).items()}
    rep.dc_dbfs = round(dc_dbfs(y), 2)
    rep.noise_floor_dbfs = round(noise_floor_db(y, rate), 2)
    eb = effective_bit_depth(y)
    rep.effective_bits = int(eb["bits"])
    rep.bit_residual_db = round(float(eb["residual_db"]), 2)
    bw = bandwidth_hz(y, rate)
    rep.bandwidth = {"hz": round(bw["hz"], 1), "ratio": round(bw["ratio"], 4)}
    rep.clipping = clip_stats(y)
    rep.stereo = stereo_stats(y)
    if with_spectrum:
        rep.spectrum = spectrum(y, rate)
    return rep


def diff_metrics(a: np.ndarray, b: np.ndarray, rate: int) -> dict:
    """两个等长信号的差异：用于 null test（相对参考的偏差）。"""
    n = min(a.shape[0], b.shape[0])
    if n == 0:
        return {"ok": False}
    x = np.asarray(a[:n], dtype=np.float64)
    y = np.asarray(b[:n], dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if y.ndim == 1:
        y = y[:, None]
    if x.shape[1] != y.shape[1]:
        c = min(x.shape[1], y.shape[1])
        x, y = x[:, :c], y[:, :c]
    d = x - y
    ref = float(np.sqrt(np.mean(x ** 2)))
    err = float(np.sqrt(np.mean(d ** 2)))
    return {
        "ok": True,
        "frames": n,
        "ref_rms_dbfs": round(float(db(ref + EPS)), 2),
        "err_rms_dbfs": round(float(db(err + EPS)), 2),
        "null_depth_db": round(float(db(ref + EPS) - db(err + EPS)), 2),
        "max_abs_err": round(float(np.max(np.abs(d))) if d.size else 0.0, 8),
        "correlation": round(float(np.corrcoef(x.ravel(), y.ravel())[0, 1]), 6)
        if x.size > 1 and np.std(x) > 0 and np.std(y) > 0 else 1.0,
        "rate": rate,
    }
