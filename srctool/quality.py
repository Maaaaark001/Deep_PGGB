"""SRC 质量测量：用合成激励精确测出杂散 / 镜像 / 混叠 / 通带 / 速度，
并对任意真实转换做"相对参考"的零差测试。

方法论（来自本机 SRC 实测报告，可复现）：
  * 激励：0.5 幅度正弦，整数 Hz 频率，4 秒
  * 分析窗：取中间正好 1 秒（= fs_out 个样本）
  * 整数 Hz + 整秒窗 ⇒ 矩形窗 FFT 无泄漏，旁瓣不会伪装成杂散
  * 杂散 spur  ：20 Hz–20 kHz 内除基频外最强谱线（44.1→48）
  * 镜像 image ：fs_in − f 处的残留（44.1→96，上采样必测）
  * 混叠 alias ：|f − round(f/fs_out)·fs_out| 处的残留（96→44.1，下采样必测）
  * 通带      ：21.5 kHz 处相对 1 kHz 的增益
  * 互调 IMD  ：双音（CCIF 19k+20k、SMPTE 60 Hz+7 kHz）与 24 音多音的产物电平

为什么单音杂散不够：单音只回答"有没有多余的谱线"，互调回答"两个音同时在时会不会
长出新的音"。对线性系统两者都应为零，所以 IMD 实质上是**线性度**判据；含非线性环节
（插值、量化、块间幅度调制）的实现，IMD 会先于单音杂散暴露问题。
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, asdict, field

import numpy as np

from . import config, engines, metrics

EPS = 1e-20


# --------------------------------------------------------------------------
# 频谱工具
# --------------------------------------------------------------------------
def _phase_index(freq: float, rate: int, n: int) -> np.ndarray:
    """整数相位索引：k[n] = (f·n) mod fs，全部是整数运算。

    为什么不能用 t = n/fs 再算 sin(2πft)：4 秒 / 88.2 kHz 时 f·t 累积到 4e5 弧度，
    float64 的相对误差 1e-16 变成 4e-11 rad 的绝对相位误差，**这本身就是 −257 dBc
    的杂散**。也就是说朴素写法会让任何引擎的杂散测量都卡在 −257 dBc 上，
    把 Deep_PGGB（−320）和 r8brain（−211）之间的真实差距抹掉一大半。
    整数取模后相位是精确的，同样的信号读出来是 −323 dBc。
    """
    k = (np.arange(n, dtype=np.int64) * int(round(freq))) % int(rate)
    return k.astype(np.float64)


def _tone(freq: float, rate: int, seconds: float, amp: float = 0.5) -> np.ndarray:
    n = int(round(rate * seconds))
    return (amp * np.sin(2 * np.pi * _phase_index(freq, rate, n) / rate)).reshape(-1, 1)


def _line_level(seg: np.ndarray, rate: int, freq: float) -> float:
    """整秒窗、整数 Hz 条件下，freq 处的谱线幅度（相对满刻度 1.0）。"""
    n = seg.shape[0]
    spec = np.abs(np.fft.rfft(seg))
    k = int(round(freq * n / rate))
    if k < 0 or k >= spec.shape[0]:
        return 0.0
    lo, hi = max(0, k - 1), min(spec.shape[0], k + 2)
    return float(np.max(spec[lo:hi]) * 2.0 / n)


def _band_level_db(seg: np.ndarray, rate: int, lo: float, hi: float, ref: float) -> float:
    """[lo, hi] 频带内的总能量，相对参考音（幅度 ref 的正弦）的能量，dB。

    为什么镜像要用带能量而不是单根 bin：升采样的镜像产物不是一根干净的线，
    它是**镜像频带里的一整片**。只读一根 bin 会把"产物落在别处"误判成"没有产物"，
    而且那根 bin 上往往还叠着基频的窗泄漏裙边 —— 两个效应都不受控。
    """
    n = seg.shape[0]
    if n == 0:
        return -300.0
    spec = np.abs(np.fft.rfft(seg)) ** 2
    f = np.fft.rfftfreq(n, 1.0 / rate)
    m = (f >= lo) & (f <= hi)
    if not np.any(m):
        return -300.0
    e = float(np.sum(spec[m])) * 2.0 / (n * n)
    return float(10 * math.log10(max(e, 1e-300) / max(ref * ref / 2.0, 1e-300)))


def _worst_spur(seg: np.ndarray, rate: int, fund: float,
                f_lo: float = 20.0, f_hi: float = 20000.0) -> tuple[float, float]:
    """返回 (最差杂散 dBc, 该杂散所在频率)。基频附近 ±3 bin 与直流被排除。"""
    n = seg.shape[0]
    spec = np.abs(np.fft.rfft(seg)) * 2.0 / n
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    k = int(round(fund * n / rate))
    keep = np.ones(spec.shape[0], bool)
    keep[max(0, k - 3): k + 4] = False
    keep[:4] = False
    band = (freqs >= f_lo) & (freqs <= f_hi)
    idx = np.flatnonzero(keep & band)
    if idx.size == 0:
        return -300.0, 0.0
    j = idx[int(np.argmax(spec[idx]))]
    ref = max(_line_level(seg, rate, fund), EPS)
    return float(20 * math.log10(max(spec[j], EPS) / ref)), float(freqs[j])


def _gain_at(engine: str, opts: dict | None, src: int, dst: int, freq: float) -> float:
    """重采样后 freq 处相对源信号的增益（dB）。"""
    x = _tone(freq, src, 4.0)
    out = engines.resample(x, src, dst, engine, opts)
    seg = np.asarray(out[:, 0], dtype=np.float64)
    seg = seg[len(seg) // 2: len(seg) // 2 + dst]
    if seg.shape[0] < dst:
        return -300.0
    return float(20 * math.log10(max(_line_level(seg, dst, freq), EPS) / 0.5))


# --------------------------------------------------------------------------
# 互调失真（IMD）：双音与多音
# --------------------------------------------------------------------------
IMD_CCIF = (19000.0, 20000.0)    # CCIF/ITU-R 双音：贴过渡带，最苛刻
IMD_SMPTE = (60.0, 7000.0)       # SMPTE 双音：4:1 幅度，看 7 kHz 是否被 60 Hz 调制
    
# 速度口径（与论文表 6 完全一致）：60 秒立体声 44.1→88.2，测一次墙钟。
# 这个口径下 60 s / 块 16 s = 4 块 × 2 声道 = 8 个可并行块，上下文只占 6%，
# 论文里 dpggb 76× / r8brain 53× / PGGB 27×。
SPEED_SECONDS = 60.0
SPEED_SRC = 44100
SPEED_DST = 88200
MT_COUNT = 24                    # 多音个数
MT_LO, MT_HI = 100.0, 18000.0    # 多音覆盖的频段


def _two_tone(f1: float, f2: float, rate: int, seconds: float,
              a1: float, a2: float) -> np.ndarray:
    n = int(round(rate * seconds))
    ph1 = _phase_index(f1, rate, n) * (2 * np.pi / rate)
    ph2 = _phase_index(f2, rate, n) * (2 * np.pi / rate)
    return (a1 * np.sin(ph1) + a2 * np.sin(ph2)).reshape(-1, 1)


def _multitone(rate: int, seconds: float, *, count: int = MT_COUNT,
               lo: float = MT_LO, hi: float = MT_HI,
               peak: float = 0.9) -> tuple[np.ndarray, list]:
    """对数等间隔多音 + Schroeder 相位（压低峰均比）。

    频率取整到 Hz：整秒窗下每个音都精确落在 FFT bin 上，因此不需要窗函数，
    也就不存在"窗函数自己造出来的谱线"——这一点和单音测量是同一个前提。
    """
    n = int(round(rate * seconds))
    freqs = np.unique(np.round(np.geomspace(lo, hi, count)))
    k = len(freqs)
    phases = np.pi * np.arange(k) ** 2 / max(1, k)
    x = np.zeros(n)
    for f, ph in zip(freqs, phases):
        # 整数相位，理由同 _phase_index：朴素写法会自己造出 −225 dBc 的"残余"。
        x += np.sin(2 * np.pi * _phase_index(f, rate, n) / rate + ph)
    x *= peak / max(float(np.max(np.abs(x))), EPS)
    return x.reshape(-1, 1), [float(f) for f in freqs]


def _worst_product(seg: np.ndarray, rate: int, products, ref) -> tuple[float, float]:
    """互调产物中最差的一个（dBc）。

    ref 为单频时以它为 0 dBc；为 (f1, f2) 时取两音电平的几何平均——
    对等幅双音即等于单音电平，且当某个音被过渡带削掉时分子分母同步下降，
    不会把"把音滤掉了"误判成"互调很低"。
    """
    if isinstance(ref, tuple):
        r = math.sqrt(max(_line_level(seg, rate, float(ref[0])), EPS) *
                      max(_line_level(seg, rate, float(ref[1])), EPS))
    else:
        r = max(_line_level(seg, rate, float(ref)), EPS)
    r = max(r, EPS)
    best_db, best_f = -400.0, 0.0
    for f in products:
        db = float(20 * math.log10(max(_line_level(seg, rate, float(f)), EPS) / r))
        if db > best_db:
            best_db, best_f = db, float(f)
    return best_db, best_f


def _tone_residual(seg: np.ndarray, rate: int, freqs: list,
                   half_bins: int = 3) -> tuple[float, float]:
    """多音残余：去掉各音所在 bin（±half_bins）后剩下的能量，相对音的总能量（dB）。

    因为每个音精确落在 bin 上，bin 值本身就是该音的最小二乘复幅度，
    所以"扣掉这些 bin"等价于"对每个音做一次幅度/相位自由的最小二乘拟合并减掉"——
    结果对引擎的群延迟与通带下垂不敏感，只对**新长出来的频率成分**敏感。

    **这个指标有地板，而且地板由激励的相位精度决定。** 用整数相位合成（见
    _phase_index）后：单音 −307.1 dBc、24 音 −295.2 dBc、双音 CCIF −334.4 dBc。
    这些是"完全不做重采样、直接把同一组频率合成在目标采样率上"读出来的数，
    即 rfft 自身的舍入，不是引擎的失真。所以：
    * 读数贴在地板上（Deep_PGGB 的 −295.0）只能说明"低于测量能力"，不能说明"更干净"；
    * 只有明显高于地板的读数（r8brain −262.3、sox_ng −182.6、SciPy −65.0）才是真实失真。

    早期用 sin(2πft) 直接生成激励时，4 s / 88.2 kHz 的相位累积误差本身就是
    −257 dBc，把 109 dB 的真实差距压成 42 dB —— 见 _phase_index 的说明。
    """
    n = seg.shape[0]
    spec = np.fft.rfft(seg)
    keep = np.ones(spec.shape[0], bool)          # True = 判为残余
    for f in freqs:
        k = int(round(f * n / rate))
        keep[max(0, k - half_bins): min(spec.shape[0], k + half_bins + 1)] = False
    keep[:2] = False                             # 直流不算残余
    fit_spec = spec.copy()
    fit_spec[keep] = 0.0
    resid_spec = spec.copy()
    resid_spec[~keep] = 0.0
    fit = np.fft.irfft(fit_spec, n)
    resid = np.fft.irfft(resid_spec, n)
    ref = float(np.sqrt(np.mean(fit ** 2)))
    err = float(np.sqrt(np.mean(resid ** 2)))
    return float(20 * math.log10(max(err, EPS) / max(ref, EPS))), float(
        20 * math.log10(max(ref, EPS)))


# --------------------------------------------------------------------------
# 测量结果
# --------------------------------------------------------------------------
@dataclass
class SrcMeasurement:
    engine: str = ""
    label: str = ""
    spur_dbc: float = -300.0
    spur_hz: float = 0.0
    image_dbc: float = -300.0
    image_hz: float = 0.0
    alias_dbc: float = -300.0
    alias_hz: float = 0.0
    imd_dbc: float = -300.0          # CCIF 双音 19k+20k 的最差互调产物
    imd_hz: float = 0.0
    imd_smpte_dbc: float = -300.0    # SMPTE 双音 60 Hz+7 kHz 的最差边带
    mt_dbc: float = -300.0           # 24 音多音残余（相对音的总能量）
    sinad_dbc: float = -300.0        # 单音 SINAD：基频功率 / 残差全带功率
    sinad_inband_dbc: float = -300.0 # 同上，只算 20 Hz–20 kHz
    sfdr_dbc: float = -300.0         # 最坏一根谱线（除直流与基频 ±1 bin）
    enob_bits: float = 0.0           # (SINAD_FS − 1.76)/6.02，折算到满刻度正弦
    enob_inband_bits: float = 0.0
    passband_21500: float = -300.0
    passband_22000: float = -300.0
    speed_x: float = 0.0
    # 整数倍率引擎（PGGB）做不了降采样，混叠项无定义 —— 用这个标记把它排除出
    # "混叠最好/最差"的评比，否则 −300 的哨兵值会冒充"混叠抑制完美"。
    alias_na: bool = False
    ratio_label: str = ""            # 本次测量用的倍率口径，写进表格脚注
    elapsed: float = 0.0
    error: str | None = None
    ok: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def _segs(y: np.ndarray, rate: int, count: int = 5) -> list:
    """把输出切成 count 个 1 秒分析窗，均匀铺在文件内（互不重叠）。

    **为什么不是只取正中一个窗**：分块引擎在块接缝处有一个极小的不连续，接缝
    落在窗口里时读数会差 5–10 dB。单个居中窗只要恰好压在接缝上（块长与文件长度
    成整数倍时必然如此），测出来的就是"接缝"而不是"引擎"。取 5 个窗的中位数，
    让读数对窗口位置不敏感；最差窗仍然单独记录，不允许把它藏起来。
    """
    s = np.asarray(y[:, 0], dtype=np.float64)
    n = s.shape[0]
    if n < rate or count <= 1:
        if n < rate:
            raise RuntimeError("输出过短，无法取 1 秒分析窗")
        return [s[(n - rate) // 2: (n - rate) // 2 + rate]]
    w = rate
    out = []
    for i in range(count):
        st = int(round(i * (n - w) / float(count - 1)))
        out.append(s[st: st + w])
    return out


def _median(values: list) -> float:
    v = sorted(x for x in values if x is not None)
    if not v:
        return -300.0
    m = len(v) // 2
    return float(v[m] if len(v) % 2 else 0.5 * (v[m - 1] + v[m]))


def measure_engine(engine: str, opts: dict | None = None, *, fund: float = 1000.0,
                   seconds: float = 4.0, do_passband: bool = True,
                   do_speed: bool = True, do_imd: bool = True,
                   windows: int = 5) -> SrcMeasurement:
    """对单个引擎做一次完整的 SRC 保真度测量。

    两套口径，取决于引擎能不能做任意有理倍率：

    * 通用引擎：杂散 44.1→48、镜像 44.1→96、混叠 96→44.1、互调/多音 44.1→96。
    * 只能整数倍率的引擎（PGGB，`spec.integer_only`）：全部改到 **44.1→88.2**（×2），
      因为它的内核只接受整数倍率，喂 1.5 会被静默当成 1 原样返回 —— 那样测出来的
      是"没重采样"的数字，看起来完美，其实什么也没测。降采样类指标（混叠）
      它根本做不到，标 `alias_na` 并从评比里剔除，而不是留一个 −300 的哨兵冒充好成绩。
    """
    spec = engines.ENGINES.get(engine)
    m = SrcMeasurement(engine=engine, label=spec.label if spec else engine)
    int_only = bool(getattr(spec, "integer_only", False))
    # 分析用的目标采样率与倍率口径
    # **所有引擎的上行指标统一用 44.1→88.2（×2）**，包括能跑任意倍率的引擎。
    # 理由是可比较性：镜像、互调、多音、通带这四列全部落在同一条倍率、同一个分析
    # 地板上，PGGB 才能和其他七台同表比较。以前给通用引擎用 44.1→96、给 PGGB 用
    # 44.1→88.2，两列的"地板"本身差 2.7 dB，做出来的差距有一半是口径造成的。
    # 任意倍率的能力由论文的九倍率精度表单独证明，不靠这一列。
    up_src, up_dst = 44100, 88200
    hi_dst = 88200                                # 高频口径（镜像/互调/多音/通带）
    m.ratio_label = "上行 44.1→88.2（×2）/ 混叠 96→44.1"
    try:
        # --- 杂散 -------------------------------------------------------
        # 分析窗必须**居中**，不能从 mid 往后取：Deep_PGGB 这类引擎会在文件末尾做
        # 20 ms 淡出，淡出是幅度调制，会在基频两侧摊出 −26 dB 的裙边；
        # 从 mid 往后取的窗口会正好把这段淡出框进去，把 −247 dB 误测成 −27 dB。
        x = _tone(fund, up_src, seconds)
        y = engines.resample(x, up_src, up_dst, engine, opts)
        # 杂散用**泄漏免疫**口径：扣掉基频附近的 bin 后的残余能量，等价于对基频做
        # 幅度/相位自由的最小二乘拟合后的残差。用 ±3 bin 的单 bin 口径会把基频的
        # 窗泄漏裙边（±3 bin 外第一根）当成杂散：实测 Deep_PGGB 因此读 −320.2 dBc，
        # 放宽到 ±50 bin 就变成 −323.1，而 PGGB 一直是 −323.1 —— 差的 3 dB 全是泄漏。
        m.spur_dbc = _median([_tone_residual(g, up_dst, [fund])[0]
                              for g in _segs(y, up_dst, windows)])
        m.spur_hz = fund

        # --- 单音 SINAD / SFDR / ENOB ------------------------------------
        # 与杂散同源（同一段 1 kHz 输出、同一批分析窗），但读的是"全部残余"：
        # 分母是残差的全带功率（Parseval 等价），谐波、杂散、镜像与宽带噪声都进来。
        # 这几项不进论文的"五项地板"表，它们是 ADC 测试的口径，用来把同一批输出
        # 换算成 ENOB —— 双精度 53 位有效数字的上限约 52 bit。
        tq = [metrics.tone_sinad(g, up_dst, fund) for g in _segs(y, up_dst, windows)]
        m.sinad_dbc = _median([t["sinad_db"] for t in tq])
        m.sinad_inband_dbc = _median([t["sinad_inband_db"] for t in tq])
        m.sfdr_dbc = _median([t["sfdr_db"] for t in tq])
        m.enob_bits = _median([t["enob_bits"] for t in tq])
        m.enob_inband_bits = _median([t["enob_inband_bits"] for t in tq])

        # --- 镜像 -------------------------------------------------------
        y2 = engines.resample(x, up_src, hi_dst, engine, opts)
        # 镜像用**带能量**口径：产物是镜像频带里的一整片，不是一根线。参考取
        # 输出里基频的实测电平，而不是输入幅度 —— PGGB 会把峰值归一化到 0.99，
        # 用固定 0.5 当分母会让它凭空多出 6 dB。
        img_f = up_src - fund
        vals = []
        for g in _segs(y2, hi_dst, windows):
            img_ref = max(_line_level(g, hi_dst, fund), EPS)
            vals.append(_band_level_db(g, hi_dst, img_f, hi_dst / 2.0, img_ref))
        m.image_dbc = _median(vals)
        m.image_hz = img_f

        # --- 混叠（只有能降采样的引擎才测）------------------------------
        if int_only:
            m.alias_na = True
        else:
            # **必须**有通带参考音在场。只放一个阻带音时，分母是固定常数 0.5，
            # 而 sox_ng 对纯阻带输入返回逐位精确的全零（44100/44100 个 0.0），
            # 于是读数落到 EPS 上给出 −394 dBc —— 那是 0/0，不是抑制能力。
            # 加了参考音后 sox_ng 读 −221.0 dBc，从"最强"变成倒数第三。
            xh = _two_tone(fund, 30000.0, 96000, seconds, 0.5, 0.5)
            y = engines.resample(xh, 96000, 44100, engine, opts)
            # 30 kHz 对 44.1 kHz 折叠到 44100-30000 = 14100
            fold = abs(30000.0 - round(30000.0 / 44100.0) * 44100.0)
            vals = []
            for g in _segs(y, 44100, windows):
                ref = max(_line_level(g, 44100, fund), EPS)
                vals.append(float(20 * math.log10(
                    max(_line_level(g, 44100, fold), EPS) / ref)))
            m.alias_dbc = _median(vals)
            m.alias_hz = fold

        # --- 互调：CCIF 双音 19k + 20k ----------------------------------
        if do_imd:
            f1, f2 = IMD_CCIF
            xi = _two_tone(f1, f2, up_src, seconds, 0.25, 0.25)
            y = engines.resample(xi, up_src, hi_dst, engine, opts)
            # 二阶/三阶产物：2f1−f2、2f2−f1、f2−f1、f1+f2
            prods = (2 * f1 - f2, 2 * f2 - f1, f2 - f1, f1 + f2)
            got = [_worst_product(g, hi_dst, prods, (f1, f2))
                   for g in _segs(y, hi_dst, windows)]
            m.imd_dbc = _median([v[0] for v in got])
            m.imd_hz = got[0][1]

            # --- SMPTE 双音：60 Hz + 7 kHz，4:1 --------------------------
            f1s, f2s = IMD_SMPTE
            xs = _two_tone(f1s, f2s, up_src, seconds, 0.40, 0.10)
            y = engines.resample(xs, up_src, hi_dst, engine, opts)
            # 载波被低频音调制的边带：7k ± 60、7k ± 120
            prods = [f2s + i * f1s for i in (-2, -1, 1, 2)]
            m.imd_smpte_dbc = _median([_worst_product(g, hi_dst, prods, f2s)[0]
                                       for g in _segs(y, hi_dst, windows)])

            # --- 多音：24 个音，100 Hz – 18 kHz --------------------------
            xm, mt_f = _multitone(up_src, seconds)
            y = engines.resample(xm, up_src, hi_dst, engine, opts)
            m.mt_dbc = _median([_tone_residual(g, hi_dst, mt_f)[0]
                                for g in _segs(y, hi_dst, windows)])

        # --- 通带 -------------------------------------------------------
        if do_passband:
            m.passband_21500 = _gain_at(engine, opts, up_src, hi_dst, 21500.0)
            m.passband_22000 = _gain_at(engine, opts, up_src, hi_dst, 22000.0)

        # --- 速度 -------------------------------------------------------
        # 口径必须与论文表一致：60 s 立体声 44.1->88.2，跑一次。
        # 之前用 10 s 单声道 44.1->88.2，那会让"多相 FIR 引擎"看起来压倒性地快：
        # 10 s 文件在 block=16 s 下只有一块、并行度为 1，而多相 FIR 每样本成本恒定。
        # 实测同一台机器：10 s 单声道口径 r8brain 208× vs dpggb 108×，
        # 60 s 立体声口径 r8brain 53× vs dpggb 76× —— 排序直接翻转。
        if do_speed:
            xs = _two_tone(997.0, 4999.0, up_src, SPEED_SECONDS, 0.5, 0.5)
            t0 = time.perf_counter()
            engines.resample(xs, up_src, SPEED_DST, engine, opts)
            m.elapsed = time.perf_counter() - t0
            m.speed_x = round(SPEED_SECONDS / m.elapsed, 1) if m.elapsed > 0 else 0.0
    except Exception as exc:  # noqa: BLE001
        m.ok = False
        m.error = str(exc)[:400]
    return m


BENCH_CACHE = config.CACHE / "bench.json"


def save_bench(ms: list[SrcMeasurement], meta: dict | None = None) -> None:
    """把一次基准测量的结果落盘，下次打开页面可以直接看到上次的数字。"""
    try:
        config.ensure_dirs()
        payload = {
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "meta": meta or {},
            "items": [m.to_dict() for m in ms],
        }
        BENCH_CACHE.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    except Exception:
        pass


def load_bench() -> tuple[list[SrcMeasurement], dict]:
    """读回上次的基准结果；没有缓存就返回空列表。"""
    try:
        payload = json.loads(BENCH_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return [], {}
    items = []
    for raw in payload.get("items", []):
        try:
            items.append(SrcMeasurement(**raw))
        except Exception:
            continue
    meta = {"saved_at": payload.get("saved_at", "")}
    meta.update(payload.get("meta") or {})
    return items, meta


def compare_engines(engines_to_test: list[str], opts_by_engine: dict | None = None,
                    progress=None) -> list[SrcMeasurement]:
    out: list[SrcMeasurement] = []
    total = len(engines_to_test)
    for i, key in enumerate(engines_to_test):
        if progress:
            progress(i, total, key)
        opts = (opts_by_engine or {}).get(key)
        out.append(measure_engine(key, opts))
    if progress:
        progress(total, total, "")
    save_bench(out, {"engines": engines_to_test})
    return out


# --------------------------------------------------------------------------
# 真实文件的零差测试
# --------------------------------------------------------------------------
def _shift_frac(x: np.ndarray, tau: float) -> np.ndarray:
    """用 FFT 相位旋转把信号整体平移 tau 个样本。

    这是"亚样本对齐"的关键：SSRC 的群延迟是 2723.46 样本这样的非整数，
    只做整数对齐会残留一个恒定的相位斜坡，在零差测试里表现为 −24 dB 的假误差。
    """
    if abs(tau) < 1e-6:
        return x
    n = x.shape[0]
    pad = int(abs(tau)) + 64
    size = 1 << int(np.ceil(np.log2(n + 2 * pad)))
    freqs = np.fft.rfftfreq(size)
    out = np.empty_like(x)
    for c in range(x.shape[1]):
        # 把信号放在零填充缓冲区的正中，平移后仍从中间取回，避免循环卷绕
        buf = np.zeros(size)
        buf[pad:pad + n] = x[:, c]
        spec = np.fft.rfft(buf)
        y = np.fft.irfft(spec * np.exp(-2j * np.pi * freqs * tau), size)
        out[:, c] = y[pad:pad + n]
    return out


def _align(x: np.ndarray, y: np.ndarray, max_lag: int):
    """互相关对齐：先求整数滞后，再用抛物线插值求亚样本滞后并补偿。"""
    a = np.asarray(x[:, 0], dtype=np.float64)
    b = np.asarray(y[:, 0], dtype=np.float64)
    n = min(a.shape[0], b.shape[0])
    if n < 64:
        return x, y, 0.0
    seg = min(n, 1 << 16)
    a_s = a[:seg] - a[:seg].mean()
    b_s = b[:seg] - b[:seg].mean()
    size = 1 << int(np.ceil(np.log2(2 * seg)))
    cc = np.fft.irfft(np.fft.rfft(a_s, size) * np.conj(np.fft.rfft(b_s, size)), size)
    cc = np.concatenate([cc[-max_lag:], cc[: max_lag + 1]])
    lag = int(np.argmax(cc)) - max_lag

    if lag > 0:
        x2, y2s = x[lag:], y
    elif lag < 0:
        x2, y2s = x, y[-lag:]
    else:
        x2, y2s = x, y
    m = min(x2.shape[0], y2s.shape[0])
    x2, y2s = x2[:m], y2s[:m]

    # 亚样本滞后：抛物线插值只能给粗略值（且符号容易搞反），
    # 这里直接在 [−1, 1] 上做一次小规模搜索，用真实残差挑最优，稳妥且只要几十次 FFT。
    frac = 0.0
    if m > 4096:
        seg_len = min(m, int(0.5 * max(1, m)))
        lo = max(0, (m - seg_len) // 2)
        a_seg = x2[lo:lo + seg_len]
        # 两级搜索：粗扫 ±1 样本（步长 0.05），再在最优附近细扫（步长 0.002）。
        # 精度必须到 0.002 样本级别，否则 15 kHz 处残留的相位误差就有 −34 dB。
        best = None
        for cand in np.arange(-1.0, 1.0001, 0.05):
            shifted = _shift_frac(y2s[lo:lo + seg_len], cand)
            e = float(np.sum((a_seg - shifted) ** 2))
            if best is None or e < best[1]:
                best = (float(cand), e)
        coarse = best[0]
        for cand in np.arange(coarse - 0.06, coarse + 0.0601, 0.002):
            shifted = _shift_frac(y2s[lo:lo + seg_len], cand)
            e = float(np.sum((a_seg - shifted) ** 2))
            if e < best[1]:
                best = (float(cand), e)
        frac = best[0]
        if abs(frac) > 1e-3:
            y2s = _shift_frac(y2s, frac)
    return x2, y2s, lag + frac


def _band_split(d: np.ndarray, rate: int, edges: list) -> list:
    """把信号按频带分解，返回每个频带的 RMS 电平（dBFS）。"""
    x = np.asarray(d[:, 0], dtype=np.float64)
    n = x.shape[0]
    if n < 1024:
        return [-200.0] * (len(edges) - 1)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (freqs >= lo) & (freqs < hi)
        if not mask.any():
            out.append(-200.0)
            continue
        part = np.zeros_like(spec)
        part[mask] = spec[mask]
        e = float(np.sqrt(np.mean(np.fft.irfft(part, n) ** 2)))
        out.append(round(float(20 * math.log10(max(e, EPS))), 1))
    return out


def null_test(y: np.ndarray, src: int, dst: int, engine: str, opts: dict | None,
              reference_engine: str = "r8b",
              reference_opts: dict | None = None,
              max_seconds: float = 90.0) -> dict:
    """把被测引擎的输出与参考实现对比，并做时延对齐与频带分解。

    为什么必须对齐：不同引擎的滤波器群延迟不同（线性相位滤波器可达数百样本），
    不对齐时算出来的"差异"几乎全是时间偏移，毫无意义。

    为什么必须分频带：两个都正确的引擎，差异也一定集中在过渡带（近 Nyquist）。
    如果差异只在 16 kHz 以上，那是滤波器设计不同，不是失真；
    如果差异铺满整个可闻频段，那才是真正的问题。
    """
    ref_opts = reference_opts or {"transband": 1.0, "atten": 250.0, "quality": "full",
                                  "phase": "linear"}
    # 零差测试要跑两遍重采样（参考 + 被测），还要做亚样本对齐搜索。
    # 一小时素材上这会是几分钟，而 90 秒足够暴露任何滤波器差异 ——
    # 于是统一取中段 90 秒，并在结果里注明。
    n_src = int(y.shape[0])
    window = min(n_src, int(max_seconds * src)) if max_seconds else n_src
    if window < n_src:
        start = max(0, (n_src - window) // 2)
        y = np.asarray(y[start:start + window], dtype=np.float64)
    try:
        ref = engines.resample(y, src, dst, reference_engine, ref_opts)
        got = engines.resample(y, src, dst, engine, opts)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:400]}

    max_lag = int(0.25 * dst)
    a, b, lag = _align(ref, got, max_lag)
    n = min(a.shape[0], b.shape[0])
    a, b = a[:n], b[:n]

    # --- 增益 / 直流 诊断（P1）-----------------------------------------
    # 只报告，不改写零差深度。理由见论文 §4.3：闭式 LS 增益估计 g=<a,b>/<b,b>
    # 的误差不是二阶的，会把一对本来就完美的引擎（g≈1）的零差从 387 dB 压到
    # 297 dB——拟合注入的数值误差比它要去掉的尺度差还大。所以这里只算出 g/DC
    # 让"归一化不一致"变得可见，深度仍用未拟合的 a-b。
    if n > 4 and np.std(a) > 0:
        m_a = float(np.mean(a))
        m_b = float(np.mean(b))
        var_a = float(np.sum((a - m_a) ** 2))
        ls_gain = float(np.sum((a - m_a) * (b - m_b)) / var_a) if var_a > 0 else 1.0
        ls_dc = m_b - ls_gain * m_a
    else:
        ls_gain, ls_dc = 1.0, 0.0

    # 掐掉两端的边界区再比较。原因：Deep_PGGB 会在文件首尾各做 100 ms 渐变
    # （那是它精度能到 −218 dB 的前提），而 r8brain 不做。两段渐变本身
    # 就是幅度调制，会在差值里留下 −27 dB 的"假差异"，把真实的滤波器差异
    # 完全盖住。掐掉 100 ms 后，同一对引擎的零差从 26.9 dB 变成 41.9 dB，
    # 而可闻带（<20 kHz）的差异是 −203 dB —— 剩下的 41.9 dB 全部来自
    # 21–23 kHz 的过渡带设计不同（r8brain 1% 过渡带 vs 砖墙）。
    edge = int(0.1 * dst)
    if n > 4 * edge:
        a, b = a[edge: n - edge], b[edge: n - edge]
        n = a.shape[0]
    d = a - b

    ref_rms = float(np.sqrt(np.mean(a ** 2)))
    err_rms = float(np.sqrt(np.mean(d ** 2)))
    depth = float(20 * math.log10(max(ref_rms, EPS) / max(err_rms, EPS)))

    # 全带零差深度会被 20 kHz 以上的超声差异主导（那部分本来就听不见），
    # 所以另算一个"可闻带深度"：把差值信号 20 kHz 以上滤掉再求 RMS。
    # 判级用可闻带，全带值仍然报出来，方便排查滤波器设计差异。
    n_fft = d.shape[0]
    d_spec = np.fft.rfft(d, axis=0)
    d_freqs = np.fft.rfftfreq(n_fft, 1.0 / dst)
    d_spec[d_freqs >= min(20000.0, dst / 2.0)] = 0
    d_aud = np.fft.irfft(d_spec, n_fft, axis=0)[: d.shape[0]]
    aud_err = float(np.sqrt(np.mean(d_aud ** 2)))
    depth_audible = float(20 * math.log10(max(ref_rms, EPS) / max(aud_err, EPS)))

    nyq = dst / 2.0
    edges = sorted({round(e, 1) for e in
                    [0.0, 1000.0, 5000.0, 10000.0, 16000.0, 20000.0, nyq + 1]
                    if e <= nyq + 1})
    bands = _band_split(d, dst, edges)
    band_ref = _band_split(a, dst, edges)

    audible = [(edges[i], edges[i + 1], bands[i]) for i in range(len(bands))
               if edges[i + 1] <= min(20000.0, nyq)]
    hot = max(audible, key=lambda t: t[2]) if audible else (0.0, 0.0, -200.0)
    # 只有"最热的频带本身就在 16 kHz 以上"才算过渡带差异
    high_only = hot[0] >= 16000 and all(v <= -60 for i, v in enumerate(bands)
                                        if edges[i] < 16000)

    return {
        "ok": True, "frames": n,
        "lag_samples": round(lag, 3), "lag_ms": round(lag / dst * 1000.0, 3),
        "ref_rms_dbfs": round(float(20 * math.log10(max(ref_rms, EPS))), 2),
        "err_rms_dbfs": round(float(20 * math.log10(max(err_rms, EPS))), 2),
        "null_depth_db": round(depth, 2),
        "null_depth_audible_db": round(depth_audible, 2),
        "audible_err_dbfs": round(float(20 * math.log10(max(aud_err, EPS))), 2),
        "correlation": round(float(np.corrcoef(a.ravel(), b.ravel())[0, 1]), 6)
        if a.size > 1 and np.std(a) > 0 and np.std(b) > 0 else 1.0,
        "bands": [{"lo": edges[i], "hi": edges[i + 1], "diff_db": bands[i],
                   "ref_db": band_ref[i]} for i in range(len(bands))],
        "hot_band": {"lo": hot[0], "hi": hot[1], "db": hot[2]},
        "diff_concentrated_high": high_only,
        # 诊断字段：LS 拟合增益与直流偏移。偏离 1.0 / 0.0 较多说明两台引擎归一化
        # 不一致，需要人工判断是通带增益差还是整体尺度差；不影响 null_depth_db。
        "ls_gain": round(ls_gain, 6),
        "ls_dc": float("%.3e" % ls_dc),
        "seconds_tested": round(window / float(src), 2),
        "truncated": window < n_src,
        "engine": engine, "reference": reference_engine, "src": src, "dst": dst,
        "verdict": verdict_null(depth_audible, hot, high_only,
                                 full_depth=depth),
    }


def verdict_null(depth: float, hot: tuple = (0.0, 0.0, -200.0),
                 high_only: bool = False, full_depth: float | None = None) -> dict:
    """把零差深度 + 差异分布翻译成人话。

    关键洞察：两个**都正确**的引擎之间也一定有差异，因为滤波器形状不同。
    真正要判断的是"差异落在哪里"：
      * 只在过渡带（>16 kHz）→ 滤波器设计差异，可闻性极低
      * 铺满可闻频段       → 真的有问题
    """
    lo, hi, band_db = hot
    band_txt = f"差异能量主要集中在 {lo/1000:.0f}–{hi/1000:.0f} kHz（{band_db:.0f} dBFS）"
    if full_depth is not None and full_depth < depth - 6:
        band_txt += (f"；全带差值只有 {full_depth:.0f} dB，那部分在 20 kHz 以上的"
                     "超声区，人耳听不到")

    if depth >= 96:
        return {"level": "transparent", "label": "数学等价",
                "text": f"可闻带与参考实现的波形偏差 {depth:.0f} dB，已经低于 16bit 噪声底。"
                        "这属于数值误差级别，任何系统上都不可能听出区别。"}
    if high_only and depth >= 40:
        return {"level": "good", "label": "仅过渡带差异",
                "text": f"可闻带（20 kHz 以下）与参考实现的偏差 {depth:.0f} dB，{band_txt}——"
                        "这是不同滤波器设计在近 Nyquist 处的正常差异，不是失真。"
                        "20 kHz 以上人耳无法感知，可放心使用。"}
    if depth >= 72:
        return {"level": "excellent", "label": "听不出差别",
                "text": f"可闻带偏差 {depth:.0f} dB，接近 16bit 噪声底（−96 dB）。{band_txt}。"
                        "正常聆听条件下不可分辨。"}
    if depth >= 48:
        return {"level": "good", "label": "差异轻微",
                "text": f"可闻带偏差 {depth:.0f} dB，{band_txt}。属于滤波器形状差异，"
                        "安静段落里可能听出细微的高频差别，日常使用无碍。"}
    if depth >= 24:
        return {"level": "fair", "label": "差异可闻",
                "text": f"可闻带偏差 {depth:.0f} dB，{band_txt}。"
                        "已进入可闻范围，母带级工作应换用更接近参考的参数。"}
    return {"level": "poor", "label": "差异明显",
            "text": f"可闻带偏差仅 {depth:.0f} dB，{band_txt}。请检查参数："
                    "常见元凶是 swr 内核的 filter_size 太小，或 scipy 的 half_len 不足。"}


# --------------------------------------------------------------------------
# 音质结论（输入 / 输出）
# --------------------------------------------------------------------------
def verdict_audio(rep, media_info=None) -> list[dict]:
    """把 AudioReport 翻译成一组带等级的结论卡片。"""
    out: list[dict] = []

    def add(level: str, title: str, text: str, metric: str = "") -> None:
        out.append({"level": level, "title": title, "text": text, "metric": metric})

    # 峰值 / 削波
    if rep.clipping.get("samples", 0) > 0:
        add("bad", "检测到削波",
            f"有 {rep.clipping['samples']} 个样本达到满刻度（占比 "
            f"{rep.clipping['ratio']*100:.4f}%），最长连续 {rep.clipping['longest_run']} 个样本。"
            "削波是不可逆的失真，转换前应先降增益。",
            f"peak {rep.peak_dbfs:.2f} dBFS")
    elif rep.peak_dbfs > -0.1:
        add("warn", "峰值贴顶",
            f"峰值 {rep.peak_dbfs:.2f} dBFS，距离满刻度不足 0.1 dB。"
            "重采样会在峰值附近产生轻微过冲（overshoot），可能导致输出削波。建议留 −1 dB 余量。",
            f"peak {rep.peak_dbfs:.2f} dBFS")
    elif rep.peak_dbfs < -20:
        add("warn", "电平偏低",
            f"峰值只有 {rep.peak_dbfs:.2f} dBFS，浪费了约 {-rep.peak_dbfs - 1:.0f} dB 的动态范围。"
            "如果这是母带，建议归一化到 −1 dBFS。",
            f"peak {rep.peak_dbfs:.2f} dBFS")
    else:
        add("ok", "峰值正常",
            f"峰值 {rep.peak_dbfs:.2f} dBFS，真峰值 {rep.true_peak_dbtp:.2f} dBTP，"
            "留有合理的余量。", f"peak {rep.peak_dbfs:.2f} dBFS")

    # 真峰值 vs 采样峰值
    if rep.true_peak_dbtp - rep.peak_dbfs > 0.3:
        add("info", "采样间峰值过冲",
            f"真峰值 {rep.true_peak_dbtp:.2f} dBTP 比采样峰值 {rep.peak_dbfs:.2f} dBFS 高 "
            f"{rep.true_peak_dbtp - rep.peak_dbfs:.2f} dB。"
            "这说明存在采样点之间的过冲，DAC 重建时可能削波。",
            f"TP {rep.true_peak_dbtp:.2f} dBTP")

    # 有效位深
    bits = rep.effective_bits
    if media_info is not None and getattr(media_info, "bit_depth", None):
        declared = media_info.bit_depth
        if bits and bits < declared - 2:
            add("warn", "位深被浪费",
                f"文件声明 {declared} bit，但实际有效位深只有约 {bits} bit"
                f"（量化残差 {rep.bit_residual_db:.1f} dB）。"
                "这通常意味着它是由更低位的源升采样/转码而来 —— 高 bit 只是容器，没有真实信息。",
                f"{bits}/{declared} bit")
        else:
            add("ok", "位深使用充分",
                f"声明 {declared} bit，有效位深约 {bits} bit，容器没有明显浪费。",
                f"{bits}/{declared} bit")
    elif bits:
        add("info", "有效位深",
            f"有效位深约 {bits} bit（量化残差 {rep.bit_residual_db:.1f} dB）。",
            f"{bits} bit")

    # 带宽 vs 采样率
    bw = rep.bandwidth.get("hz", 0.0)
    nyq = rep.rate / 2.0
    if rep.rate and bw > 0:
        ratio = bw / nyq
        if ratio < 0.35 and rep.rate >= 44100:
            add("bad", "疑似升采样文件",
                f"采样率 {rep.rate} Hz（Nyquist {nyq/1000:.1f} kHz），但实际信号带宽只有 "
                f"{bw/1000:.1f} kHz（{ratio*100:.0f}%）。"
                "这几乎可以肯定是低采样率文件被升采样而来 —— 高频并不存在，"
                "升采样只增加了文件体积。",
                f"{bw/1000:.1f} kHz")
        elif ratio < 0.75 and rep.rate >= 44100:
            add("info", "带宽偏窄",
                f"信号带宽约 {bw/1000:.1f} kHz，占 Nyquist 的 {ratio*100:.0f}%。"
                "可能是原始录音本就如此（如老录音、电话带宽素材），也可能是编码损失。",
                f"{bw/1000:.1f} kHz")
        else:
            add("ok", "带宽饱满",
                f"信号带宽约 {bw/1000:.1f} kHz，占 Nyquist 的 {ratio*100:.0f}%，"
                "高频内容被完整保留。", f"{bw/1000:.1f} kHz")

    # 响度
    lufs = rep.lufs.get("integrated", -70)
    if lufs > -8:
        add("warn", "响度过高",
            f"整体响度 {lufs:.1f} LUFS，已经进入\"响度战争\"区间。"
            "流媒体平台（Spotify −14、Apple Music −16、YouTube −14）都会把它压回去，"
            "动态范围白白损失。", f"{lufs:.1f} LUFS")
    elif lufs > -70:
        add("info", "响度",
            f"整体响度 {lufs:.1f} LUFS，短时峰值 {rep.lufs.get('short_term_max', -70):.1f} LUFS，"
            f"响度范围 LRA {rep.lufs.get('lra', 0):.1f} LU。"
            "（流媒体参考：Spotify/YouTube −14 LUFS，Apple Music −16 LUFS）",
            f"{lufs:.1f} LUFS")

    # 直流
    if rep.dc_dbfs > -60:
        add("warn", "直流偏移",
            f"直流偏移 {rep.dc_dbfs:.1f} dBFS（线性值 {10**(rep.dc_dbfs/20):.5f}）。"
            "会浪费动态范围并可能在后续处理中产生咔哒声，建议加高通滤波。",
            f"DC {rep.dc_dbfs:.1f} dB")

    # 静段电平（最安静的 5% 帧）—— 注意：音乐素材里它不是"噪声底"，
    # 而是"最安静段落有多响"，用来判断压限程度与是否需要门限。
    quiet = rep.noise_floor_dbfs
    if quiet > -20:
        add("warn", "几乎没有静段",
            f"最安静的 5% 帧也有 {quiet:.1f} dBFS，整段素材始终处于高电平。"
            "这通常意味着重度压限（响度战争），动态余量已经所剩无几；"
            "如果这不是刻意的风格化处理，建议回退压缩量。",
            f"quiet {quiet:.1f} dBFS")
    elif quiet > -45:
        add("info", "静段电平偏高",
            f"最安静的 5% 帧约 {quiet:.1f} dBFS（相对满刻度）。"
            "对连续演奏的音乐属正常；但如果是含静音间隙的素材，说明存在底噪或房间声，"
            "交付前可考虑加门限。",
            f"quiet {quiet:.1f} dBFS")
    else:
        add("ok", "静段干净",
            f"最安静的 5% 帧约 {quiet:.1f} dBFS，与峰值相差 "
            f"{rep.peak_dbfs - quiet:.0f} dB，动态余量充裕，没有可闻底噪。",
            f"quiet {quiet:.1f} dBFS")

    # 立体声
    st = rep.stereo or {}
    if st.get("available"):
        corr = st.get("correlation", 1.0)
        if corr > 0.99:
            add("info", "近乎单声道",
                f"左右声道相关系数 {corr:.3f}，几乎是单声道内容。"
                "如果是刻意为之（如人声居中），可以降为单声道省一半体积。",
                f"ρ={corr:.3f}")
        elif corr < -0.5:
            add("bad", "相位反转",
                f"左右声道相关系数 {corr:.3f}（负值）。两声道存在反相，"
                "单声道下混时会互相抵消，务必检查接线或插件。",
                f"ρ={corr:.3f}")
        else:
            add("ok", "立体声场正常",
                f"左右声道相关系数 {corr:.3f}，左右平衡 {st.get('lr_balance_db', 0):+.2f} dB，"
                f"Side/Mid {st.get('side_mid_db', 0):+.1f} dB。",
                f"ρ={corr:.3f}")

    return out


def verdict_src(measurements: list[SrcMeasurement]) -> list[dict]:
    """把引擎测量结果翻译成排序结论。

    注意方向：杂散/镜像/混叠的数值是"负得越多越好"，所以**最优 = 最小值**，
    最差 = 最大值。早期版本在这里用反了，会把最差的引擎写成"最佳"。
    """
    out: list[dict] = []
    ok = [m for m in measurements if m.ok]
    if not ok:
        return [{"level": "bad", "title": "测量失败",
                 "text": "所有引擎都未能完成测量，请检查二进制是否可用。", "metric": ""}]

    best_spur = min(ok, key=lambda m: m.spur_dbc)
    worst_spur = max(ok, key=lambda m: m.spur_dbc)

    # SINAD / ENOB：同一批 1 kHz 输出的"总和"口径。与杂散分开报，是因为两者
    # 的分母不同 —— 杂散只扣基频附近的 bin，SINAD 把镜像与宽带噪声也算进去。
    # 带内列能把"镜像受限"与"带内失真"分开：前者换一个带宽读数就消失。
    best_sinad = max(ok, key=lambda m: m.sinad_dbc)
    if best_sinad.sinad_dbc > -300:
        out.append({
            "level": "ok",
            "title": "单音信纳比",
            "text": (f"{best_sinad.label} 的 SINAD 为 {best_sinad.sinad_dbc:.1f} dBc，"
                     f"等效 {best_sinad.enob_bits:.1f} bit；20 kHz 带内为 "
                     f"{best_sinad.sinad_inband_dbc:.1f} dBc（{best_sinad.enob_inband_bits:.1f} bit）。"
                     "带内与全带差得多，说明限制来自镜像区而不是带内失真。"),
            "metric": f"SINAD {best_sinad.sinad_dbc:.1f} dBc",
        })
    # 杂散用泄漏免疫口径（扣掉基频 bin 后的残余），地板约 −307 dBc：读数贴在
    # 地板上只能说明"低于测量能力"，不能拿来排名。文案必须把这层说清楚，
    # 否则 −304 与 −306 之间 2 dB 会被读者当成"引擎更干净"。
    spur_txt = (f"在 44.1→48 kHz、1 kHz 激励下，{best_spur.label} 的杂散残余为 "
                f"{best_spur.spur_dbc:.1f} dBc。"
                "这个数字扣掉了基频本身（含它的窗泄漏裙边），只统计新长出来的频率成分。")
    if best_spur.spur_dbc < -300:
        spur_txt += ("它已经贴住本测量的分析地板（−307 dBc），"
                     "与同样贴住地板的引擎之间**不可区分**。")
    if best_spur.spur_dbc < -180:
        spur_txt += "这个电平已经低于任何播放系统的动态范围，可以认为完全无杂散。"
    elif best_spur.spur_dbc < -120:
        spur_txt += "这个电平低于 24bit 噪声底（−144 dB），实际听不出来。"
    out.append({
        "level": "ok" if best_spur.spur_dbc < -120 else "info",
        "title": f"杂散最低：{best_spur.label}",
        "text": spur_txt, "metric": f"{best_spur.spur_dbc:.1f} dBc",
    })

    if worst_spur.spur_dbc > -120:
        out.append({
            "level": "warn", "title": f"杂散偏高：{worst_spur.label}",
            "text": f"{worst_spur.label} 的杂散为 {worst_spur.spur_dbc:.1f} dBc，"
                    "已经接近或超过 16bit 噪声底（−96 dB）。在安静段落里可能听出轻微的\"沙\"感。",
            "metric": f"{worst_spur.spur_dbc:.1f} dBc",
        })

    best_img = min(ok, key=lambda m: m.image_dbc)
    worst_img = max(ok, key=lambda m: m.image_dbc)
    if worst_img.image_dbc > -60:
        out.append({
            "level": "bad", "title": f"镜像严重：{worst_img.label}",
            "text": f"{worst_img.label} 在 {worst_img.image_hz:.0f} Hz 处留下 "
                    f"{worst_img.image_dbc:.1f} dBc 的镜像。上采样时镜像会变成可闻的\"鬼影\""
                    "（与原信号呈镜像关系），这是最容易听出来的 SRC 缺陷。请更换引擎或参数。",
            "metric": f"{worst_img.image_dbc:.1f} dBc",
        })
    else:
        out.append({
            "level": "ok", "title": f"镜像抑制最好：{best_img.label}",
            "text": f"上采样镜像最低为 {best_img.image_dbc:.1f} dBc（{best_img.label}），"
                    f"最差 {worst_img.image_dbc:.1f} dBc（{worst_img.label}）。"
                    "这里统计的是镜像频带（22.05 kHz 以上）的总能量，不是单根谱线 ——"
                    "产物是一整片，只读一根 bin 会漏掉它。镜像低于 −100 dB 后不可闻。",
            "metric": f"{best_img.image_dbc:.1f} dBc",
        })

    # 只做整数倍上采样的引擎（PGGB）没有降采样，混叠项无定义 —— 把它排除出评比，
    # 否则哨兵值 −300 会冒充"混叠抑制完美"，把真正做过降采样的引擎挤下去。
    aliased = [m for m in ok if not m.alias_na]
    best_alias = min(aliased or ok, key=lambda m: m.alias_dbc)
    worst_alias = max(aliased or ok, key=lambda m: m.alias_dbc)
    if worst_alias.alias_dbc > -60:
        out.append({
            "level": "bad", "title": f"混叠严重：{worst_alias.label}",
            "text": f"{worst_alias.label} 把 30 kHz 的内容折叠到了 {worst_alias.alias_hz:.0f} Hz，"
                    f"残留 {worst_alias.alias_dbc:.1f} dBc。下采样前必须做足够陡的低通，"
                    "否则带外能量会污染可闻频段，且**无法事后修复**。",
            "metric": f"{worst_alias.alias_dbc:.1f} dBc",
        })
    else:
        out.append({
            "level": "ok", "title": f"混叠抑制最好：{best_alias.label}",
            "text": f"下采样混叠最低为 {best_alias.alias_dbc:.1f} dBc（{best_alias.label}），"
                    f"最差 {worst_alias.alias_dbc:.1f} dBc（{worst_alias.label}）。"
                    "测法是**通带参考音（1 kHz）与阻带侵略音（30 kHz）同时在场**，"
                    "读折叠产物相对参考音的电平 —— 只放阻带音时，把阻带真的清零的引擎"
                    "会得到 0/0 的假满分（sox_ng 的旧读数 −394 dBc 就是这么来的）。",
            "metric": f"{best_alias.alias_dbc:.1f} dBc",
        })

    # --- 互调失真：线性度判据 -------------------------------------------
    # 与上面三项分开写，因为它的物理含义不同：杂散/镜像/混叠是"多出来什么"，
    # 互调是"两个音同时在时会不会长出第三个音"，只有非线性才会产生。
    imd = [m for m in ok if m.imd_dbc > -420]
    if imd:
        best_imd = min(imd, key=lambda m: m.imd_dbc)
        worst_imd = max(imd, key=lambda m: m.imd_dbc)
        if worst_imd.imd_dbc > -100:
            out.append({
                "level": "warn", "title": f"互调偏高：{worst_imd.label}",
                "text": f"19 kHz + 20 kHz 双音下，{worst_imd.label} 在 "
                        f"{worst_imd.imd_hz:.0f} Hz 处产生 {worst_imd.imd_dbc:.1f} dBc 的互调产物。"
                        "互调是**非线性**的直接证据，且产物落在可闻带内，比同电平的杂散更容易察觉。",
                "metric": f"{worst_imd.imd_dbc:.1f} dBc",
            })
        else:
            txt = (f"19 kHz + 20 kHz 双音下，{best_imd.label} 的最差互调产物为 "
                   f"{best_imd.imd_dbc:.1f} dBc（{best_imd.imd_hz:.0f} Hz），"
                   f"最差的 {worst_imd.label} 为 {worst_imd.imd_dbc:.1f} dBc。")
            # 说清楚"打平"意味着什么：这里存在一个由浮点运算本身决定的测量下限，
            # 到了下限就不是"引擎更好"，而是"这套测量已经分辨不出来"。
            if best_imd.imd_dbc < -320:
                txt += ("注意 −334 dBc 是本测量的数值下限：把同一对频率直接在目标采样率上合成、"
                        "**完全不重采样**再测，读数就是 −334.4 dBc（float64 正弦叠加与 rfft 的舍入）。"
                        "贴在下限上的引擎之间**不可区分**，不代表它们真的完全相同。")
            else:
                txt += "这个量级远低于任何可闻阈值。"
            out.append({
                "level": "ok", "title": f"互调最低：{best_imd.label}",
                "text": txt, "metric": f"{best_imd.imd_dbc:.1f} dBc",
            })

    mt = [m for m in ok if m.mt_dbc > -420]
    if mt:
        best_mt = min(mt, key=lambda m: m.mt_dbc)
        worst_mt = max(mt, key=lambda m: m.mt_dbc)
        if worst_mt.mt_dbc > -90:
            out.append({
                "level": "warn", "title": f"多音残余偏高：{worst_mt.label}",
                "text": f"{worst_mt.label} 在 24 音（100 Hz–18 kHz）激励下的残余为 "
                        f"{worst_mt.mt_dbc:.1f} dB。多音是最接近真实音乐的激励，"
                        "这个电平已经接近 16bit 噪声底。",
                "metric": f"{worst_mt.mt_dbc:.1f} dB",
            })
        else:
            out.append({
                "level": "ok", "title": f"多音残余最低：{best_mt.label}",
                "text": f"24 音激励下，{best_mt.label} 的残余为 {best_mt.mt_dbc:.1f} dB"
                        f"（相对音的总能量），最差的 {worst_mt.label} 为 {worst_mt.mt_dbc:.1f} dB。"
                        + ("　注意 −295 dBc 是测量下限：24 个音直接在目标采样率上合成、"
                           "完全不重采样，读数也是 −295.2 dBc。"
                           if best_mt.mt_dbc < -290 else ""),
                "metric": f"{best_mt.mt_dbc:.1f} dB",
            })

    fast = max(ok, key=lambda m: m.speed_x)
    slow = min(ok, key=lambda m: m.speed_x)
    out.append({
        "level": "info", "title": f"最快：{fast.label}",
        "text": f"{fast.label} 达到 {fast.speed_x:.0f}× 实时（60 秒立体声 44.1→88.2 kHz，"
                f"{fast.elapsed * 1000:.0f} ms）。最慢的 {slow.label} 为 {slow.speed_x:.0f}×。",
        "metric": f"{fast.speed_x:.0f}×",
    })

    pb = [m for m in ok if m.passband_21500 > -290]
    if pb:
        best_pb = max(pb, key=lambda m: m.passband_21500)
        if best_pb.passband_21500 > -1.0:
            out.append({
                "level": "ok", "title": f"通带最宽：{best_pb.label}",
                "text": f"{best_pb.label} 在 21.5 kHz 处只掉 {abs(best_pb.passband_21500):.2f} dB，"
                        "完整保留了 44.1 kHz 素材的高频。",
                "metric": f"{best_pb.passband_21500:.2f} dB @ 21.5k",
            })
        else:
            out.append({
                "level": "info", "title": f"通带最宽：{best_pb.label}",
                "text": f"{best_pb.label} 在 21.5 kHz 处为 {best_pb.passband_21500:.1f} dB，"
                        "其余引擎滚降更早。若素材含大量 20 kHz 以上内容（如高解析母带），"
                        "应优先选择通带更宽的引擎。",
                "metric": f"{best_pb.passband_21500:.1f} dB @ 21.5k",
            })
    return out
