"""七台 SRC 引擎：参数元数据 + 统一的 resample() 接口。

每个引擎都暴露它底层的全部旋钮，参数元数据（PARAMS）同时供 UI 渲染和帮助文本使用。
统一约定：
    resample(y, src_rate, dst_rate, opts) -> np.ndarray (frames, channels), float64
    y 是交错存储的 float64 (frames, channels)；返回长度已按 round(n*dst/src) 对齐。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import config

# --------------------------------------------------------------------------
# 参数元数据
# --------------------------------------------------------------------------
@dataclass
class Param:
    key: str
    label: str
    kind: str                  # bool | int | float | select
    default: Any
    desc: str
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[tuple[Any, str]] = field(default_factory=list)
    unit: str = ""
    advanced: bool = False
    depends: str | None = None   # 仅当另一个参数取某值时生效

    def to_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "kind": self.kind,
            "default": self.default, "desc": self.desc, "min": self.min,
            "max": self.max, "step": self.step, "unit": self.unit,
            "options": [{"value": v, "label": l} for v, l in self.options],
            "advanced": self.advanced, "depends": self.depends,
        }


@dataclass
class EngineSpec:
    key: str
    label: str
    tagline: str
    description: str
    license: str
    speed: str
    fidelity: str
    bandwidth: str
    params: list[Param]
    available: bool = True
    reason: str = ""
    # 只作为基准对照出现的引擎：它不能完成一般转换（PGGB 只能整数倍上采样），
    # 所以不出现在转换页的下拉里，但仍参与基准测量与图表。
    bench_only: bool = False
    # 只能做整数倍率：测量口径要相应改成 44.1→88.2，且降采样类指标（混叠）测不了。
    integer_only: bool = False

    def to_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "tagline": self.tagline,
            "description": self.description, "license": self.license,
            "speed": self.speed, "fidelity": self.fidelity,
            "bandwidth": self.bandwidth, "available": self.available,
            "reason": self.reason, "bench_only": self.bench_only,
            "integer_only": self.integer_only,
            "params": [p.to_dict() for p in self.params],
        }


PHASE = [
    ("linear", "线性相位（默认）—— 波形对称，无相位失真，但有预振铃与延迟"),
    ("min", "最小相位 —— 无预振铃、延迟低，瞬态更\"紧\"，但相位非线性"),
]

# --------------------------------------------------------------------------
# 1) r8brain-free
# --------------------------------------------------------------------------
R8B_PARAMS = [
    Param("quality", "精度档", "select", "full",
          "r8brain 内部的滤波器精度档。16bit 用 136 dB 阻带、24bit 用 180 dB、full 用 206.91 dB。"
          "除非你在做 16bit 母带，否则一律用 full —— 差别只体现在噪声底，速度差异很小。",
          options=[("16", "16 bit 级（136 dB）"), ("24", "24 bit 级（180 dB）"),
                   ("full", "full / 浮点级（207 dB）")]),
    Param("transband", "过渡带宽度", "float", 2.0,
          "低通滤波器的过渡带，占 Nyquist 的百分比。**这是 r8brain 最重要的旋钮**："
          "数值越小 → 通带越宽（高频保得越多）、滤波器越长越慢；"
          "数值越大 → 通带变窄（高频提前滚降）、速度变快。"
          "2.0 是默认值，22.05 kHz 上限时通带能到 21.5 kHz；"
          "批量转码想提速可用 5–10（通带缩到约 21 kHz / 20.5 kHz）。",
          min=0.5, max=45.0, step=0.5, unit="% Nyquist"),
    Param("atten", "阻带衰减", "float", 206.91,
          "低通滤波器的阻带抑制深度（dB）。它只决定\"噪声底有多低\"，不影响通带宽度，"
          "与 transband **相互独立**。经验公式 6.02×位数+40：16bit→136、24bit→180、"
          "32bit 浮点→207。超过 200 dB 后已低于双精度浮点的实际噪声底，再高没有意义。",
          min=60.0, max=250.0, step=0.01, unit="dB"),
    Param("phase", "相位响应", "select", "linear",
          "线性相位保证所有频率延迟一致（波形不变形），代价是预振铃（pre-ringing）与较高延迟；"
          "最小相位把能量集中在因果侧，听感上瞬态更干脆，适合母带与鼓组素材。",
          options=PHASE),
]

# --------------------------------------------------------------------------
# 2) sox_ng rate
# --------------------------------------------------------------------------
SOXNG_PRESETS = [
    ("q", "quick   — 最快，质量最低"),
    ("l", "low     — 低质量"),
    ("m", "medium  — 中等"),
    ("g", "good    — 良好"),
    ("h", "high    — SoX 的默认值（实测仅 −142 dB，不建议）"),
    ("e", "extreme — sox_ng 新增，150 dB"),
    ("v", "very high — 经典推荐值，实测 −191 dB"),
    ("u", "ultra   — sox_ng 新增，200 dB，实测 −199 dB"),
]

SOXNG_PARAMS = [
    Param("preset", "预设档", "select", "v",
          "SoX/sox_ng 的 rate 质量档，本质是\"滤波器长度 + 通带 + 阻带\"的打包预设。"
          "**经典陷阱：默认的 -h 只有 −142 dB 杂散**，换成 -v 立刻好 48 dB，速度几乎不变。"
          "sox_ng 又新增了 -e（150 dB）与 -u（200 dB）。",
          options=SOXNG_PRESETS),
    Param("steep", "陡峭滤波（-s）", "bool", True,
          "把通带边缘推到 Nyquist 的 99%。**这是 SoX 里最划算的一个开关**："
          "21.5 kHz 处的增益从 −32 dB 变成 0 dB，抑制比还略高，速度只慢约 10%。"
          "实测 -v -s 是 SoX 的\"免费午餐\"。", advanced=False),
    Param("bandwidth", "通带百分比（-b）", "float", None,
          "手动指定通带边缘占 Nyquist 的百分比（74–99.7）。留空则跟随预设/陡峭开关。"
          "收窄它只能杀掉已知的带外信号，对杂散几乎没有改善 —— 不建议乱调。",
          min=74.0, max=99.7, step=0.1, unit="% Nyquist", advanced=True),
    Param("rejection", "阻带抑制（-R）", "float", None,
          "手动指定阻带抑制深度（90–200 dB）。这是 SoX 里\"诚实的质量旋钮\"："
          "实测 -R 120 会掉 50 dB 杂散，但换来明显更快的速度。留空跟随预设。",
          min=90.0, max=200.0, step=1.0, unit="dB", advanced=True),
    Param("phase", "相位响应", "select", "linear",
          "-M 最小相位 / -I 中间相位 / -L 线性相位。默认线性。",
          options=[("linear", "线性相位（-L，默认）"),
                   ("intermediate", "中间相位（-I）"),
                   ("min", "最小相位（-M）")]),
    Param("phase_percent", "相位混合度（-p）", "int", 50,
          "SoX rate 的相位响应百分比：0 = 最小相位（无预振铃、瞬态紧），"
          "50 = 中间相位，100 = 线性相位（波形对称）。"
          "它与 -M/-I/-L 是同一件事的连续版本，二者取其一即可；"
          "母带常用 100，鼓组/打击乐可用 0–25 让瞬态更硬。",
          min=0, max=100, step=5, unit="%", advanced=True),
]

# --------------------------------------------------------------------------
# 3) SSRC (Shibatch)
# --------------------------------------------------------------------------
SSRC_PARAMS = [
    Param("profile", "质量档", "select", "insane",
          "SSRC 的 FFT 长度 + 保护带 + 默认衰减的组合。档位越高，滤波器越长、速度越慢。"
          "insane 用 2^18 点 FFT，通带平到 22.02 kHz —— **本工具箱里唯一真正保住全部 22.05 kHz 带宽的实现**。",
          options=[("lightning", "lightning — 2^8，最快"),
                   ("fast", "fast — 2^10"),
                   ("short", "short — 2^12"),
                   ("standard", "standard — 2^14 / 145 dB"),
                   ("high", "high — 2^16 / 170 dB"),
                   ("insane", "insane — 2^18 / 200 dB（默认）")]),
    Param("att", "阻带衰减", "float", None,
          "覆盖档位自带的衰减值（dB）。与 profile 独立：profile 决定 FFT 长度与带宽，"
          "att 决定噪声底。留空则用档位默认值。",
          min=60.0, max=250.0, step=1.0, unit="dB"),
    Param("phase", "相位响应", "select", "linear",
          "--minPhase 使用最小相位滤波器（延迟更低，瞬态更紧）。默认线性相位。",
          options=PHASE),
    Param("compensate_delay", "补偿滤波器延迟", "bool", True,
          "SSRC 会在输出前后各垫一段与滤波器等长的静音（insane 档多达 43565 样本 ≈ 0.9 秒）。"
          "开启后本工具会用冲激探针测出延迟并从输出头部裁掉，使结果与输入时间对齐。"
          "只有在研究原始输出时才需要关闭。"),
    Param("dither", "输出抖动", "select", "98",
          "SSRC 在写 WAV 时的抖动类型。98 = 三角分布噪声整形（推荐）；0 = ATH 曲线噪声整形"
          "（更贴合人耳等响曲线，但只适合 16bit 输出）。本工具默认用 float32 中转，此项目前不生效。",
          options=[("98", "三角分布（98）"), ("0", "ATH 噪声整形（0）"),
                   ("none", "不加抖动")], advanced=True),
]

# --------------------------------------------------------------------------
# 4) libsoxr
# --------------------------------------------------------------------------
SOXR_PARAMS = [
    Param("quality", "质量预设", "select", "VHQ",
          "libsoxr 只提供预设，没有过渡带/截止频率的细调（C API 有，Python 绑定没暴露）。"
          "VHQ 是最高档，实测 −188 dB 杂散、977× 实时 —— 比 SoX -v 快 5.5 倍而质量只差 2 dB。",
          options=[("QQ", "QQ — 最快（≈ 1400×）"), ("LQ", "LQ — 低"),
                   ("MQ", "MQ — 中（实测 −119 dB）"), ("HQ", "HQ — 高（实测 −141 dB）"),
                   ("VHQ", "VHQ — 极高（实测 −188 dB，推荐）")]),
    Param("precision", "内部精度", "select", "float64",
          "libsoxr 的样本格式。float64 用双精度中间量，噪声底更低；float32 更快但会引入 −150 dB 级舍入。",
          options=[("float64", "float64（默认）"), ("float32", "float32（更快）")], advanced=True),
]

# --------------------------------------------------------------------------
# 5) ffmpeg aresample
# --------------------------------------------------------------------------
SWR_PARAMS = [
    Param("resampler", "重采样内核", "select", "soxr",
          "**ffmpeg 默认的 swr 内核在母带级完全不可用**：实测镜像只有 −11 dB（上采样时在 "
          "44.1−f 处留一个 −11 dB 的鬼影），混叠 −20 dB。必须切到 soxr。",
          options=[("soxr", "soxr（推荐，−189 dB）"), ("swr", "swr（ffmpeg 原生，可细调）")]),
    Param("precision", "soxr 精度", "int", 28,
          "soxr 内核的精度（bits），20–33。28 是 ffmpeg 的推荐值，再高收益极小。",
          min=16, max=33, step=1, unit="bit", depends="soxr"),
    Param("cheby", "切比雪夫优化", "bool", True,
          "soxr 的 cheby=1 使用切比雪夫逼近（等波纹），过渡带更陡。默认开启。",
          depends="soxr"),
    Param("filter_size", "滤波器长度", "int", 256,
          "**swr 内核的过渡带旋钮**（taps）。32 是默认值（滚降极缓），256 才勉强可用（−152 dB），"
          "但即使 256 也打不过 soxr。仅在需要 cutoff/phase_shift 行为时才用 swr。",
          min=16, max=1024, step=16, unit="taps", depends="swr"),
    Param("cutoff", "截止频率比", "float", 0.97,
          "swr 内核的截止频率，占输出 Nyquist 的比例（0.8–1.0）。1.0 = 不过滤（会混叠）。",
          min=0.80, max=1.0, step=0.01, depends="swr"),
    Param("phase_shift", "相位偏移", "int", 10,
          "swr 内核的滤波器相位偏移（0–30）。0 = 线性相位，越大越接近最小相位。",
          min=0, max=30, step=1, depends="swr", advanced=True),
]

# --------------------------------------------------------------------------
# 6) scipy resample_poly
# --------------------------------------------------------------------------
SCIPY_PARAMS = [
    Param("window", "窗函数", "select", "kaiser",
          "重采样低通滤波器的窗函数。kaiser 可控旁瓣、blackman 旁瓣最低但主瓣宽、"
          "hann/hamming 折中、boxcar 等于矩形窗（最差）。",
          options=[("kaiser", "Kaiser（β=5.0，推荐）"), ("blackman", "Blackman"),
                   ("hamming", "Hamming"), ("hann", "Hann"), ("boxcar", "Boxcar（矩形）")]),
    Param("beta", "Kaiser β", "float", 5.0,
          "仅 kaiser 窗生效。β 越大旁瓣越低（抑制更好）但主瓣越宽（过渡带越缓）。"
          "5.0 对应约 −60 dB；8.0 约 −90 dB。",
          min=0.0, max=20.0, step=0.5, depends="kaiser"),
    Param("half_len", "滤波器半长", "int", 32,
          "滤波器长度 = 2×half_len×max(up,down)+1。越大越精确、越慢。"
          "SciPy 默认 10，本工具默认 32 以改善其糟糕的镜像抑制。",
          min=2, max=256, step=2, unit="taps"),
]

# --------------------------------------------------------------------------
# 7) Deep_PGGB —— 本项目自研的理想砖墙 FFT 引擎
# --------------------------------------------------------------------------
DPGGB_PARAMS = [
    Param("block", "分块长度", "float", 16.0,
          "每块处理的音频秒数。**它同时是速度、内存和接缝质量的旋钮**。"
          "块长不小于文件长度时整首一次变换，接缝数为零，指标最好；"
          "60 秒立体声 44.1→176.4 实测：8 秒块 73×、**16 秒块 81×**、"
          "4 秒块约 65×（r8brain-free 同条件 57×）—— 大块把上下文开销摊薄，"
          "收益超过了并行度下降的损失。"
          "注意接缝：4 秒块时块接缝会让 SMPTE 边带读数从 −335 掉到 −325 dBc，"
          "16 秒块下 16 秒以内的文件根本不产生接缝。填 0 表示整首一次算。",
          min=0.0, max=600.0, step=0.5, unit="秒"),
    Param("workers", "并行块数", "int", 0,
          "同时处理多少个分块。0 = 自动取 CPU 线程数。**这是本引擎真正的并行加速旋钮**："
          "每个块互相独立（各读固定的输入窗、写固定的输出段），所以可以完全并行、"
          "输出与单线程**逐位相同**。实测 60 秒素材 0.5 秒块：1 线程 345×、4 线程 459×。"
          "注意它和下面的「FFT 线程数」不是一回事——那个是单次变换内部并行，"
          "在单块场景下基本没用。",
          min=0, max=64, step=1, advanced=True),
    Param("mem", "内存上限", "float", 1024.0,
          "单块允许占用的内存（MB）。分块长度会被自动压缩到这个上限以内，"
          "所以长文件不会因为块设得太大而爆内存。",
          min=128.0, max=16384.0, step=64.0, unit="MB", advanced=True),
    Param("fade", "首尾渐变", "float", 20.0,
          "文件头尾的淡入淡出长度（ms）。**这是本引擎精度能到 −218 dB 的关键**："
          "文件边界是一个阶跃，理想低通会把它摊成 1/d 的尾巴污染整首歌。"
          "实测不加渐变只有 −108 dB，**20 ms 就到 −218 dB 并且完全饱和**"
          "（50/100/200 ms 一个数字都不变），所以默认 20 ms，只损失 20 ms 音频。"
          "**注意：用恒定值/零阶保持去延拓边界完全无效**——那只是让值连续、"
          "导数仍不连续，实测与不处理一样是 −109 dB。必须让曲线在两端平滑归零。",
          min=0.0, max=1000.0, step=1.0, unit="ms"),
    Param("edgefade", "首尾渐变覆盖（高精度）", "float", 0.0,
          "只覆盖文件首尾的渐变长度，0 = 用上面的值。**这是高频端的精度旋钮**："
          "默认 20 ms 时 19 kHz 的零差只有 449.7 dB、21 kHz 只有 310.7 dB，因为渐变的"
          "调制边带离输出奈奎斯特只剩 3 kHz、落回了带内。经验律 **T ≈ 650000/(0.5·fs − f)**"
          "毫秒（上限 900）：15 kHz 要 92、18 kHz 160、19 kHz 213、21 kHz 619。实测 19 kHz"
          "在 20/60/120/240/480 ms 下读 450.8/582.1/654.8/665.7/**666.1** dB，按律逐点取时"
          "全频段回到 665 dB 以上。**代价是真的在改信号**：头尾各有几百毫秒被淡入淡出，"
          "音乐上可听，所以默认关着。短文件会被 5% 上限压住（1 s 文件最多 50 ms）；"
          "对 float64 路径无益（它早贴自己的地板）。块边缘渐变会自动跟随，不用另外调。",
          min=0.0, max=1000.0, step=1.0, unit="ms", advanced=True),
    Param("context", "分块上下文", "float", 800.0,
          "每个分块两侧额外携带的上下文长度（ms），转换后丢弃、只保留中段。"
          "**它一口气决定三件事**：分块接缝的干净程度、奈奎斯特附近的抗混叠、"
          "以及升采样镜像频带（88.2 kHz 输出的 42.6–44.1 kHz）能压多低。"
          "实测 22.05 kHz 抑制 400 ms −195 dB → 800 ms −211 dB；"
          "镜像频带 400 ms −314.8 dBc → 800 ms −322.1 dBc（地板 −320 dBc）。"
          "代价是速度：44.1→88.2、60 秒立体声，400 ms 约 160×、800 ms 约 126×。"
          "它和「首尾渐变」是两回事 —— 渐变只负责杀掉文件边界那一步。",
          min=10.0, max=2000.0, step=10.0, unit="ms", advanced=True),
    Param("rolloff", "滚降宽度", "float", 200.0,
          "奈奎斯特以下的过渡带宽度（Hz）。**0 是纯砖墙，也就是 PGGB 的做法**，"
          "通带全平但奈奎斯特处对非整周期信号无能为力（实测 22.05 kHz 只有 −9 dB）。"
          "留出过渡带后阻带立刻变干净：100 Hz → −98 dB、200 Hz → −118 dB、"
          "400 Hz → −138 dB。代价是通带上限下移：200 Hz 时 21.5 kHz 仍是 0.00 dB、"
          "21.9 kHz −2.7 dB。默认 200 Hz 在两个轴上同时优于 sox_ng。",
          min=0.0, max=4000.0, step=10.0, unit="Hz"),
    Param("rollorder", "滚降阶数", "int", 2,
          "过渡带窗形的指数。窗形是 [0.5(1+cos)] 的 N 次幂：阶数越高，截止点处衰减越快，"
          "但通带边缘下移越多。实测（200 Hz 宽）1 阶 −87 dB、2 阶 −118 dB、3 阶 −125 dB、"
          "4 阶 −127 dB；而 21.9 kHz 的通带代价分别是 −1.3 / −2.6 / −4.0 / −5.3 dB。"
          "**2 阶是拐点**：再往上多花的通带换不来成比例的抑制。",
          min=1, max=8, step=1, advanced=True),
    Param("btaper", "块边缘渐变", "float", 20.0,
          "每个分块两端施加的渐变长度（ms），与「分块上下文」独立。"
          "渐变本身是幅度调制，会在载波两侧产生间隔 1/T 的边带；T 太长，边带就落进"
          "过渡带、贴到奈奎斯特的音上。实测 22.05 kHz 处：1 ms −135 dB、10 ms −158 dB、"
          "20 ms −161 dB、50 ms −156 dB。**20 ms 最好**，既杀掉块边阶跃，又不把边带推得太远。",
          min=1.0, max=500.0, step=1.0, unit="ms", advanced=True),
    Param("mptaps", "最小相位滤波器长度", "float", 50.0,
          "仅最小相位模式生效。因果 FIR 的抽头数 = 4×该值（ms）。"
          "越长过渡带越陡、奈奎斯特附近越准：实测 20 ms 时 21 kHz 只有 −77 dB，"
          "50 ms 提升到 −116 dB，再往上收益递减（100 ms 反而略差）。",
          min=10.0, max=500.0, step=10.0, unit="ms", advanced=True),
    Param("taper", "渐变形状", "select", "smooth12",
          "淡入淡出的窗形，**它是精度的旋钮，不是装饰**。渐变是一个乘法器，"
          "把信号频谱与窗自身的变换做卷积：离奈奎斯特越近的音，其旁瓣越容易落回带内。"
          "窗形取 smootherstep 的通用阶：w(t)=t^(N+1)·Σ C(N+k,k)·C(2N+1,N−k)·(−t)^k。"
          "**实测（16 s、1 kHz、44.1→88.2、四精度、长度不变 20 ms）**：5 阶 440.2 dB、"
          "6 阶 451.2、7 阶 516.5、8 阶 528.4、10 阶 601.7、**12 阶 665.3** dB —— 12 阶把读数"
          "抬了 225 dB，机时不变。再往上没有收益：16 阶在长渐变下反而掉到 651.6（u→0.5 处"
          "多项式大数相消）。float64 路径同受益（19 kHz 293.3 → 306.5 dB，贴住自己的地板）。"
          "C5 是 2026-11-28 之前的默认，只适合对照。",
          options=[("smooth12", "smooth12（C12 smootherstep，推荐）"),
                   ("smooth10", "smooth10（C10）"),
                   ("smooth8", "smooth8（C8）"),
                   ("smooth7", "smooth7（C7）"),
                   ("smooth6", "smooth6（C6）"),
                   ("smooth5", "smooth5（C5，2026-11-28 之前的默认）"),
                   ("smooth4", "smooth4（C4）"),
                   ("smooth2", "smooth2（C2，旧默认）"),
                   ("cos", "cos（升余弦，C1）"),
                   ("blackman", "blackman（最低旁瓣）"),
                   ("none", "none（不渐变，仅用于诊断）")]),
    Param("prec", "计算精度", "select", "double",
          "FFT 的内部精度。double 用 64 位浮点，long 用 80 位扩展精度（x87）。"
          "**实测两者输出差 −308 dB，对 PCM 完全没有区别**，long 只慢约 2 倍。"
          "只有在做 32-bit 以上、或把结果继续喂给高增益算法时才需要考虑。",
          options=[("double", "double（64 位，推荐）"), ("long", "long double（80 位）")]),
    Param("phase", "相位响应", "select", "linear",
          "linear 是零相位失真的砖墙，代价是预振铃（pre-ringing）；"
          "min 用倒谱法设计因果 FIR，**彻底消除预振铃**（实测预振铃从 −38 dB 降到 −139 dB），"
          "但因为是因果滤波器，必须在奈奎斯特下方留 10% 的过渡带，"
          "所以 22 kHz 附近会略微提前滚降。母带追求瞬态用 min，追求测量指标用 linear。",
          options=[("linear", "线性相位（砖墙，默认）"),
                   ("min", "最小相位（无预振铃）")]),
    Param("threads", "FFT 线程数", "int", 0,
          "FFTW 使用的线程数。0 表示由 FFTW 自己决定（通常等于物理核数）。"
          "多文件并行处理时建议设为 1–2，避免线程超额订阅。",
          min=0, max=64, step=1, advanced=True),
]

# --------------------------------------------------------------------------
# 引擎表
# --------------------------------------------------------------------------
def _has_soxr() -> bool:
    try:
        import soxr  # noqa: F401

        return True
    except Exception:
        return False


def _has_scipy() -> bool:
    try:
        import scipy.signal  # noqa: F401

        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# 8) PGGB（原版，仅作基准对照）
# --------------------------------------------------------------------------
# 内核 pggb_256_it.exe 的第 2 个位置参数 um 是**整数倍率**：um=2/3/4 得到 2×/3×/4×，
# 而 um=1.5、um=0.5、um=48000 全被静默当成 1（原样返回，实测输出长度 == 输入长度）。
# 所以它能做的转换只有"整数倍上采样"，44.1→48 这类非整数倍率根本做不到 ——
# 这正是 Deep_PGGB 要解决的问题，也是把 PGGB 摆进基准的意义。
PGGB_PARAMS = [
    Param("precision", "内核精度", "select", "64",
          "PGGB 的内核位宽。64 是双精度浮点，是它能达到 −300 dB 级零差的前提；"
          "32 会掉到单精度，数字完全不同。基准里固定用 64，否则对比的是精度而不是算法。",
          options=[("32", "32 bit"), ("64", "64 bit（推荐，基准口径）")]),
    Param("corner", "过渡带拐点 Hz", "int", 22050,
          "抗混叠低通的拐点频率。22050 表示一直通到 44.1 kHz 的奈奎斯特，即最陡的砖墙；"
          "调低会加宽过渡带、降低混叠但损失高频。基准里用 22050 与 Deep_PGGB 的砖墙口径对齐。",
          min=18000, max=22050, step=10, unit="Hz"),
    Param("gain", "附加增益 dB", "float", 0.0,
          "PGGB 会把输出**峰值归一化到 0.99 满刻度**，所以幅度不保持（输入 0.5 幅度的正弦，"
          "输出峰值 0.99，等于 +5.93 dB）。这个参数在归一化**之后**再叠加一个增益，"
          "用它把幅度还原回输入电平，基准测量的比值才有意义。",
          min=-40.0, max=40.0, step=0.1, unit="dB"),
]

ENGINES: dict[str, EngineSpec] = {}


def _reg(spec: EngineSpec) -> None:
    ENGINES[spec.key] = spec


_reg(EngineSpec(
    "r8b", "r8brain-free",
    "绝对保真冠军 · MIT",
    "Voxengo 的 r8brain 免费版。先用 2× 过采样，再用 8–30 抽头多项式插值 sinc 做分数延迟，"
    "多级分解整因数。实测杂散 −211 dB、镜像 −239 dB、混叠 −254 dB，通带只损 0.27 dB，"
    "速度 284× 实时。**本工具箱默认引擎。**",
    "MIT（库）", "284× 实时", "−211 dBc 杂散", "21.5 kHz @ −0.27 dB",
    R8B_PARAMS, available=config.R8B is not None,
    reason="" if config.R8B else "未找到 r8b.exe",
))

_reg(EngineSpec(
    "soxng", "sox_ng rate",
    "格式之王 · 全旋钮",
    "SoX 的活跃硬分叉 14.9。除了重采样，它还是本工具的解码/编码/抖动后端。"
    "rate 效果提供 8 档预设 + 通带/阻带/相位/精度的完整控制，实测 -u 达 −199 dB。",
    "GPL-2", "140–180× 实时", "−199 dBc 杂散（-u）", "21.8 kHz @ 0 dB（-s）",
    SOXNG_PARAMS, available=config.SOXNG is not None,
    reason="" if config.SOXNG else "未找到 sox_ng.exe",
))

_reg(EngineSpec(
    "ssrc", "SSRC / Shibatch",
    "唯一保住 22.05 kHz 全带宽",
    "Shibatch 的 Sample Rate Converter 2.4。FFT 两级滤波（多相 FIR + FFT 快速卷积），"
    "SleefDFT + AVX-512。insane 档用 2^18 点 FFT，通带平到 22.02 kHz 后 20 Hz 内垂直掉到 −242 dB。"
    "代价是速度只有 14× 实时。",
    "Boost-1.0", "13–100× 实时", "−163 dBc（受 float32 链路限制）", "22.02 kHz @ 0 dB",
    SSRC_PARAMS, available=config.SSRC is not None,
    reason="" if config.SSRC else "未找到 ssrc.exe",
))

_reg(EngineSpec(
    "soxr", "libsoxr",
    "速度之王 · 实时首选",
    "Rob Sykes 的 libsoxr 1.1，与 SoX rate 同源算法，但用了更快的 FFT 与多相滤波器实现。"
    "实测 VHQ 977× 实时、−188 dB 杂散，延迟约 20 ms。只有 5 档预设，没有细调旋钮。",
    "LGPL-2.1", "977× 实时", "−188 dBc 杂散", "21.5 kHz @ −32 dB",
    SOXR_PARAMS, available=_has_soxr(),
))

_reg(EngineSpec(
    "swr", "FFmpeg aresample",
    "流水线里必须显式指定",
    "FFmpeg 的 aresample 滤镜。**默认的 swr 内核在母带级不可用（镜像 −11 dB）**，"
    "但切到 soxr 内核后立刻变成 −189 dB。适合已经在 ffmpeg 流水线里的场景，"
    "并且 swr 内核提供了 cutoff / phase_shift / filter_size 这几个别处没有的旋钮。",
    "LGPL/GPL", "206× 实时（含进程开销）", "−189 dBc（soxr 内核）", "21.5 kHz @ −32 dB",
    SWR_PARAMS, available=config.FFMPEG is not None,
    reason="" if config.FFMPEG else "未找到 ffmpeg",
))

_reg(EngineSpec(
    "dpggb", "Deep_PGGB",
    "理想砖墙 · 任意倍率 · 本项目自研",
    "本工具箱自研的 FFT 重采样器。与 PGGB 一样用整段 FFT 做理想砖墙低通（零宽度过渡带），"
    "实测与理想解的偏差 **−218.6 dB**，与 PGGB 持平；但 PGGB 只能做整数倍（44.1→176.4），"
    "**Deep_PGGB 支持任意有理倍率**（44.1→48、96→44.1、44.1→88.2 都能做，实测均优于 −217 dB）。"
    "另有最小相位模式、long double 精度、PCM 噪声整形与 DSD 输出。",
    "本项目自研（FFTW GPL / 代码 MIT）", "30–70× 实时", "−218.6 dB（与理想解偏差）",
    "22.049 kHz @ −0.01 dB", DPGGB_PARAMS,
    available=config.DPGGB is not None,
    reason="" if config.DPGGB else "未找到 dpggb.exe（应位于 deeppggb/ 或 skill 的 deeppggb/bin/）",
))

_reg(EngineSpec(
    "pggb", "PGGB（原版）",
    "精度参照系 · 仅整数倍 · 仅作对照",
    "PGGB-IT! 的内核 pggb_256_it.exe，本项目的精度参照系。它把整段信号补零到 2 的幂次做一次 FFT，"
    "在频域做零宽过渡带的砖墙低通，再用 64 bit 内核逆变换 —— 与 Deep_PGGB 是同一类算法，"
    "因此两者的零差（302.0 与 302.5 dB）可以直接对比，差距在测量噪声以内。"
    "**它只能做整数倍上采样**：内核的倍率参数是整数，喂 1.5 / 0.5 / 48000 全被静默当成 1（原样返回），"
    "所以 44.1→48、96→44.1 这类它根本做不到。这正是 Deep_PGGB 存在的理由。"
    "本工具只把它当**基准对照**，不出现在转换引擎里。",
    "商业软件（免费 Lite 档）", "24× 实时", "−323 dBc 杂散（×2 上采样）",
    "22 kHz @ −0.64 dB", PGGB_PARAMS,
    available=config.PGGB is not None, bench_only=True, integer_only=True,
    reason="" if config.PGGB else "未找到 pggb_256_it.exe（应位于 PGGB-IT! 安装目录）",
))

_reg(EngineSpec(
    "scipy", "SciPy resample_poly",
    "草稿级 · 仅作对照",
    "scipy.signal.resample_poly，纯 Python 可调的多相重采样。实测镜像 −9 dB、混叠 −11 dB，"
    "与 FFmpeg 默认内核同级 —— **只适合草稿和教学对照，不要用于交付**。"
    "但它的窗函数与滤波器长度完全可调，是理解 SRC 原理的好教具。",
    "BSD", "585× 实时", "−66 dBc 杂散", "22 kHz @ −4 dB",
    SCIPY_PARAMS, available=_has_scipy(),
))


# --------------------------------------------------------------------------
# 默认参数
# --------------------------------------------------------------------------
def default_opts(key: str) -> dict:
    spec = ENGINES[key]
    opts = {p.key: p.default for p in spec.params}
    # swr 引擎的默认内核取决于这台机器的 ffmpeg 有没有 libsoxr。
    # essentials 构建没有，硬套 soxr 会让第一次转换就报 -22。
    if key == "swr" and not ffmpeg_caps().get("soxr"):
        opts["resampler"] = "swr"
    return opts


def _tmpdir() -> Path:
    config.ensure_dirs()
    return Path(tempfile.mkdtemp(prefix="src_", dir=str(config.WORK)))


def _run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError("引擎失败: " + " ".join(cmd[:3]) + "\n" + (r.stderr or "")[-800:])
    return r.stderr or ""


# --------------------------------------------------------------------------
# 各引擎实现
# --------------------------------------------------------------------------
def _resample_r8b(y: np.ndarray, src: int, dst: int, o: dict) -> np.ndarray:
    nch = y.shape[1]
    td = _tmpdir()
    try:
        fi, fo = td / "in.f64", td / "out.f64"
        np.ascontiguousarray(y, dtype="<f8").tofile(fi)
        q = {"16": "0", "24": "1", "full": "2"}[str(o.get("quality", "full"))]
        cmd = [str(config.R8B), str(src), str(dst), str(fi), str(fo), q,
               f"{float(o.get('transband', 2.0)):.4f}",
               f"{float(o.get('atten', 206.91)):.4f}",
               "1" if o.get("phase") == "min" else "0", str(nch)]
        _run(cmd)
        out = np.fromfile(fo, dtype="<f8")
        return out.reshape(-1, nch)
    finally:
        shutil.rmtree(td, ignore_errors=True)


def _resample_soxng(y: np.ndarray, src: int, dst: int, o: dict) -> np.ndarray:
    nch = y.shape[1]
    td = _tmpdir()
    try:
        fi, fo = td / "in.f64", td / "out.f64"
        np.ascontiguousarray(y, dtype="<f8").tofile(fi)
        eff = ["rate", "-" + str(o.get("preset", "v"))]
        if o.get("steep", True):
            eff.append("-s")
        if o.get("bandwidth") is not None:
            eff += ["-b", f"{float(o['bandwidth']):.2f}"]
        if o.get("rejection") is not None:
            eff += ["-R", f"{float(o['rejection']):.1f}"]
        ph = o.get("phase", "linear")
        if ph == "min":
            eff.append("-M")
        elif ph == "intermediate":
            eff.append("-I")
        elif o.get("phase_percent") is not None and int(o["phase_percent"]) != 50:
            eff += ["-p", str(int(o["phase_percent"]))]
        cmd = [str(config.SOXNG), "-q", "-t", "raw", "-r", str(src),
               "-e", "floating-point", "-b", "64", "-c", str(nch), str(fi),
               "-t", "raw", "-r", str(dst), "-e", "floating-point", "-b", "64",
               "-c", str(nch), str(fo)] + eff + [str(dst)]
        _run(cmd)
        return np.fromfile(fo, dtype="<f8").reshape(-1, nch)
    finally:
        shutil.rmtree(td, ignore_errors=True)


def _write_f32_wav(path: Path, y: np.ndarray, rate: int) -> None:
    import scipy.io.wavfile as wf

    wf.write(str(path), int(rate), np.ascontiguousarray(y, dtype="<f4"))


def _read_f32_wav(path: Path) -> tuple[np.ndarray, int]:
    import scipy.io.wavfile as wf

    rate, data = wf.read(str(path))
    if data.dtype != np.float32:
        data = data.astype("<f4")
    arr = np.asarray(data, dtype="<f8")
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr, int(rate)


# SSRC 会在输出前后各垫一段与滤波器等长的延迟（insane 档可达 43565 样本）。
# 不补偿的话，输出相对输入有 0.9 秒的时间偏移，做零差测试/对齐会得到毫无意义的结论。
# 这里用一次冲激探针测出延迟，按 (profile, att, phase, src, dst) 缓存。
_SSRC_LATENCY: dict[tuple, int] = {}
_SSRC_LOCK = threading.Lock()


def _ssrc_args(dst: int, o: dict) -> list[str]:
    cmd = [str(config.SSRC), "--rate", str(dst),
           "--profile", str(o.get("profile", "insane")), "--bits", "-32"]
    dith = str(o.get("dither", "98"))
    if dith != "none":
        cmd += ["--dither", dith]
    if o.get("att") is not None:
        cmd += ["--att", f"{float(o['att']):.1f}"]
    if o.get("phase") == "min":
        cmd.append("--minPhase")
    return cmd


def _ssrc_run(y: np.ndarray, src: int, dst: int, o: dict) -> tuple[np.ndarray, int]:
    nch = y.shape[1]
    td = _tmpdir()
    try:
        fi, fo = td / "in.wav", td / "out.wav"
        _write_f32_wav(fi, y, src)
        _run(_ssrc_args(dst, o) + [str(fi), str(fo)])
        out, rate = _read_f32_wav(fo)
        if rate != dst:
            raise RuntimeError(f"SSRC 返回 {rate} Hz，期望 {dst} Hz")
        if out.shape[1] != nch:
            raise RuntimeError(f"SSRC 返回 {out.shape[1]} 声道，期望 {nch}")
        return out, rate
    finally:
        shutil.rmtree(td, ignore_errors=True)


def _ssrc_latency(src: int, dst: int, o: dict) -> int:
    """用单点冲激测出 SSRC 的滤波器延迟（输出样本数）。"""
    key = (str(o.get("profile", "insane")), str(o.get("att")),
           str(o.get("phase", "linear")), int(src), int(dst))
    with _SSRC_LOCK:
        if key in _SSRC_LATENCY:
            return _SSRC_LATENCY[key]
    n = max(int(src * 0.5), 4096)
    probe = np.zeros((n, 1))
    probe[n // 4, 0] = 0.9
    out, _ = _ssrc_run(probe, src, dst, o)
    expected = int(round((n // 4) * dst / float(src)))
    peak = int(np.argmax(np.abs(out[:, 0])))
    delay = max(0, peak - expected)
    with _SSRC_LOCK:
        _SSRC_LATENCY[key] = delay
    return delay


def _resample_ssrc(y: np.ndarray, src: int, dst: int, o: dict) -> np.ndarray:
    out, _ = _ssrc_run(y, src, dst, o)
    if o.get("compensate_delay", True):
        delay = _ssrc_latency(src, dst, o)
        if delay and out.shape[0] > delay:
            out = out[delay:]
    return out


def _resample_soxr(y: np.ndarray, src: int, dst: int, o: dict) -> np.ndarray:
    import soxr

    q = str(o.get("quality", "VHQ"))
    dtype = np.float32 if str(o.get("precision")) == "float32" else np.float64
    out = soxr.resample(np.ascontiguousarray(y, dtype=dtype), src, dst, quality=q)
    return np.asarray(out, dtype=np.float64).reshape(-1, y.shape[1])


_FFMPEG_CAPS: dict = {}


def ffmpeg_caps() -> dict:
    """探测当前 ffmpeg 是否编进了 libsoxr。

    PGGB-IT! 自带的是 essentials 构建，没有 --enable-libsoxr；选 resampler=soxr 时
    ffmpeg 只吐一句 'Requested resampling engine is unavailable'，在 UI 里表现为一个
    语焉不详的 -22。探测一次缓存起来，就能给出可执行的提示。
    """
    if _FFMPEG_CAPS:
        return _FFMPEG_CAPS
    caps = {"soxr": False, "path": str(config.FFMPEG) if config.FFMPEG else None}
    if config.FFMPEG is not None:
        try:
            probe = subprocess.run(
                [str(config.FFMPEG), "-v", "error", "-nostdin", "-f", "lavfi",
                 "-i", "anullsrc=r=44100:cl=mono", "-t", "0.05",
                 "-af", "aresample=48000:resampler=soxr", "-f", "null", "-"],
                capture_output=True, text=True, timeout=20)
            txt = (probe.stderr or "") + (probe.stdout or "")
            caps["soxr"] = probe.returncode == 0 and "unavailable" not in txt
        except Exception as exc:
            caps["error"] = str(exc)
    _FFMPEG_CAPS.update(caps)
    return caps

def _resample_swr(y: np.ndarray, src: int, dst: int, o: dict) -> np.ndarray:
    nch = y.shape[1]
    kernel = str(o.get("resampler", "soxr"))
    if kernel == "soxr" and not ffmpeg_caps()["soxr"]:
        raise RuntimeError(
            "当前 ffmpeg 没有编入 libsoxr，无法使用 resampler=soxr："
            f"{config.FFMPEG}。这是 essentials 构建的典型症状（PGGB-IT! 自带的那份就是）。"
            "换成完整 GPL 构建（含 --enable-libsoxr），或把 resampler 参数改为 swr。"
        )
    af = f"aresample={dst}"
    if kernel == "soxr":
        af += f":resampler=soxr:precision={int(o.get('precision', 28))}"
        if o.get("cheby", True):
            af += ":cheby=1"
    else:
        af += ":resampler=swr"
        if o.get("filter_size") is not None:
            af += f":filter_size={int(o['filter_size'])}"
        if o.get("cutoff") is not None:
            af += f":cutoff={float(o['cutoff']):.4f}"
        if o.get("phase_shift") is not None:
            af += f":phase_shift={int(o['phase_shift'])}"
    cmd = [str(config.FFMPEG), "-v", "error", "-nostdin",
           "-f", "f64le", "-ar", str(src), "-ac", str(nch), "-i", "-",
           "-af", af, "-f", "f64le", "-ac", str(nch), "-"]
    r = subprocess.run(cmd, input=np.ascontiguousarray(y, dtype="<f8").tobytes(),
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg aresample 失败: " +
                           r.stderr.decode("utf-8", "replace")[-600:])
    out = np.frombuffer(r.stdout, dtype="<f8")
    n = out.size // nch
    return out[: n * nch].reshape(n, nch)


_DPGGB_LIB = None
_DPGGB_LOCK = threading.Lock()


def _dpggb_lib():
    """Load dpggb.dll once. Returns None when the DLL is unavailable."""
    global _DPGGB_LIB
    if _DPGGB_LIB is not None:
        return _DPGGB_LIB or None
    with _DPGGB_LOCK:
        if _DPGGB_LIB is not None:
            return _DPGGB_LIB or None
        dll = config.DPGGB_DLL
        if dll is None:
            _DPGGB_LIB = False
            return None
        try:
            import ctypes

            # The DLL sits beside its FFTW DLLs, so that folder has to be on the
            # loader search path before the import.
            os.add_dll_directory(str(dll.parent))
            lib = ctypes.CDLL(str(dll))
            lib.dpggb_resample.restype = ctypes.c_int
            lib.dpggb_resample.argtypes = [
                ctypes.POINTER(ctypes.c_double), ctypes.c_longlong, ctypes.c_int,
                ctypes.c_double, ctypes.c_double, ctypes.c_char_p,
                ctypes.POINTER(ctypes.POINTER(ctypes.c_double)),
                ctypes.POINTER(ctypes.c_longlong)]
            lib.dpggb_free.argtypes = [ctypes.POINTER(ctypes.c_double)]
            lib.dpggb_free.restype = None
            _DPGGB_LIB = lib
            return lib
        except Exception:
            _DPGGB_LIB = False
            return None


def _resample_dpggb(y: np.ndarray, src: int, dst: int, o: dict) -> np.ndarray:
    """Deep_PGGB：自研理想砖墙 FFT 引擎。

    优先在进程内调用 dpggb.dll（无数据拷贝）；DLL 缺失时退回 dpggb.exe 子进程。
    """
    import ctypes

    y = np.ascontiguousarray(y, dtype=np.float64)
    nch = y.shape[1]
    opts = ",".join([
        "block=%g" % float(o.get("block", 4.0)),
        "workers=%d" % int(o.get("workers", 0)),
        "mem=%g" % float(o.get("mem", 1024.0)),
        "fade=%g" % float(o.get("fade", 20.0)),
        "context=%g" % float(o.get("context", 800.0)),
        "mptaps=%g" % float(o.get("mptaps", 50.0)),
        "rolloff=%g" % float(o.get("rolloff", 200.0)),
        "rollorder=%d" % int(o.get("rollorder", 2)),
        "btaper=%g" % float(o.get("btaper", 20.0)),
        "edgefade=%g" % float(o.get("edgefade", 0.0)),
        "taper=%s" % str(o.get("taper", "smooth12")),
        "prec=%s" % str(o.get("prec", "double")),
        "phase=%s" % str(o.get("phase", "linear")),
        "threads=%d" % int(o.get("threads", 0)),
    ]).encode()

    lib = _dpggb_lib()
    if lib is not None:
        ptr = ctypes.POINTER(ctypes.c_double)()
        nout = ctypes.c_longlong()
        rc = lib.dpggb_resample(
            y.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.c_longlong(y.shape[0]), ctypes.c_int(nch),
            ctypes.c_double(float(src)), ctypes.c_double(float(dst)), opts,
            ctypes.byref(ptr), ctypes.byref(nout))
        if rc != 0:
            raise RuntimeError("dpggb.dll 返回错误码 %d" % rc)
        try:
            buf = np.ctypeslib.as_array(ptr, shape=(nout.value * nch,)).copy()
        finally:
            lib.dpggb_free(ptr)
        return buf.reshape(nout.value, nch)

    exe = config.DPGGB
    if exe is None:
        raise RuntimeError("未找到 dpggb.exe 或 dpggb.dll")
    y = np.ascontiguousarray(y, dtype="<f8")
    nch = y.shape[1]
    # 走管道而不是临时文件：180 秒立体声的 float64 中间件是 135 MB，
    # 写盘+读盘的时间比重采样本身还长（实测端到端 246× vs 仅转换 300×）。
    cmd = [str(exe), str(src), str(dst), "-", "-",
           "--ch", str(nch),
           "--block", str(float(o.get("block", 4.0))),
           "--workers", str(int(o.get("workers", 0))),
           "--mem", str(float(o.get("mem", 1024.0))),
           "--fade", str(float(o.get("fade", 20.0))),
           "--context", str(float(o.get("context", 800.0))),
           "--mptaps", str(float(o.get("mptaps", 50.0))),
           "--rolloff", str(float(o.get("rolloff", 200.0))),
           "--rollorder", str(int(o.get("rollorder", 2))),
           "--btaper", str(float(o.get("btaper", 20.0))),
           "--taper", str(o.get("taper", "smooth12")),
           "--prec", str(o.get("prec", "double")),
           "--phase", str(o.get("phase", "linear")),
           "--threads", str(int(o.get("threads", 0)))]
    r = subprocess.run(cmd, input=y.tobytes(), capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("dpggb 失败: " + r.stderr.decode("utf-8", "replace").strip()[-600:])
    out = np.frombuffer(r.stdout, dtype="<f8")
    n = out.size // nch
    return out[: n * nch].reshape(n, nch)


def _resample_scipy(y: np.ndarray, src: int, dst: int, o: dict) -> np.ndarray:
    import scipy.signal as sig

    g = np.gcd(int(src), int(dst))
    up, down = int(dst) // g, int(src) // g
    win = str(o.get("window", "kaiser"))
    # resample_poly 把 window 直接交给 firwin，因此 (name, param) 元组形式才带得动 β
    window: Any = ("kaiser", float(o.get("beta", 5.0))) if win == "kaiser" else win
    out = sig.resample_poly(np.asarray(y, dtype=np.float64), up, down, axis=0,
                            window=window)
    return np.asarray(out, dtype=np.float64).reshape(-1, y.shape[1])


def _resample_pggb(y: np.ndarray, src: int, dst: int, o: dict) -> np.ndarray:
    """原版 PGGB：只支持整数倍上采样，幅度按峰值归一化后由调用方还原。

    内核的第二个位置参数是**整数**倍率 um。非整数（1.5 / 0.5 / 48000）会被静默
    当成 1 原样返回 —— 不报错，只是什么都不做，这是它最容易骗过测试的地方，
    所以这里显式拒绝，而不是让它"成功"返回一段没有重采样的数据。
    """
    if dst % src != 0:
        raise RuntimeError(
            "PGGB 只能做整数倍上采样（%d → %d 不是整数倍）。它只作基准对照，"
            "请改用 Deep_PGGB 等支持任意有理倍率的引擎。" % (src, dst))
    um = int(dst // src)
    td = _tmpdir()
    try:
        nch = y.shape[1]
        # PGGB 内核是双声道的；单声道复制一份再取回，多声道逐对处理。
        outs = []
        for c0 in range(0, nch, 2):
            c1 = min(c0 + 1, nch - 1)
            pair = np.stack([y[:, c0], y[:, c1]], axis=1).astype("<f8")
            left = td / ("L%d.raw" % c0)
            right = td / ("R%d.raw" % c0)
            pair[:, 0].tofile(left)
            pair[:, 1].tofile(right)
            n = pair.shape[0]
            args = [str(int(src)), str(um), "64", "2", str(td / "log.txt"), "0", "0",
                    str(int(o.get("precision", 64))), str(int(o.get("corner", 22050))),
                    "%.4f" % float(o.get("gain", 0.0)), "0", "0", "0", "None",
                    str(n), str(left), str(right), str(left), str(right), "Lite", "1",
                    "1", "0", "0", "0", "None", "None", "0", "0", "0", "0", "0", "0", "0", "0"]
            _run([str(config.PGGB)] + args)
            a = np.fromfile(left, dtype="<f8")
            b = np.fromfile(right, dtype="<f8")
            if a.size == 0:
                raise RuntimeError("PGGB 未产生输出")
            m = min(a.size, b.size)
            outs.append(np.stack([a[:m], b[:m]], axis=1))
        out = outs[0] if len(outs) == 1 else np.concatenate(outs, axis=1)
        # PGGB 把峰值归一化到 0.99：输入 0.5 幅度的正弦出去就是 0.99。
        # 不还原的话，所有"相对基频"的比值仍成立，但通带增益会读出 +5.93 dB 的假象。
        peak_in = float(np.max(np.abs(y))) if y.size else 0.0
        peak_out = float(np.max(np.abs(out))) if out.size else 0.0
        if peak_out > 0 and peak_in > 0:
            out = out * (peak_in / peak_out)
        return out[:, :nch]
    finally:
        shutil.rmtree(td, ignore_errors=True)


IMPL: dict[str, Callable[[np.ndarray, int, int, dict], np.ndarray]] = {
    "r8b": _resample_r8b,
    "soxng": _resample_soxng,
    "ssrc": _resample_ssrc,
    "soxr": _resample_soxr,
    "swr": _resample_swr,
    "dpggb": _resample_dpggb,
    "pggb": _resample_pggb,
    "scipy": _resample_scipy,
}


def resample(y: np.ndarray, src: int, dst: int, engine: str = "r8b",
             opts: dict | None = None, *, align: bool = True) -> np.ndarray:
    """统一入口。自动把输出长度对齐到 round(n*dst/src)，去掉引擎的填充差异。"""
    if src == dst:
        return np.asarray(y, dtype=np.float64)
    spec = ENGINES.get(engine)
    if spec is None:
        raise ValueError(f"未知引擎: {engine}")
    if not spec.available:
        raise RuntimeError(f"引擎 {spec.label} 不可用：{spec.reason}")
    o = default_opts(engine)
    if opts:
        o.update({k: v for k, v in opts.items() if v is not None})
    out = IMPL[engine](y, int(src), int(dst), o)
    if align:
        want = int(round(y.shape[0] * float(dst) / float(src)))
        if out.shape[0] > want:
            out = out[:want]
        elif out.shape[0] < want:
            pad = np.zeros((want - out.shape[0], out.shape[1]))
            out = np.vstack([out, pad])
    return np.asarray(out, dtype=np.float64)


def available_engines() -> list[str]:
    return [k for k, v in ENGINES.items() if v.available]
