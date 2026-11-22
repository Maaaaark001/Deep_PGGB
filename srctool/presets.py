"""预设与参数百科。

两块内容：
  PRESETS   —— "我想做什么" 的一键配置（引擎 + 参数 + 格式 + 抖动）
  GLOSSARY  —— 每个概念/参数的中文解释，UI 里作为悬浮说明与帮助抽屉的数据源

设计原则：预设只给出**有依据**的组合，每一条都在 note 里写清楚"为什么这样配"，
并且都必须能被 UI 里暴露的旋钮还原 —— 预设不是黑盒。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Preset:
    key: str
    label: str
    group: str
    note: str
    engine: str
    engine_opts: dict = field(default_factory=dict)
    fmt: str = "wav"
    bits: int = 24
    dither: bool = True
    noise_shape: bool = True
    dither_filter: str = "shibata"
    tag: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "group": self.group, "note": self.note,
            "engine": self.engine, "engine_opts": self.engine_opts, "fmt": self.fmt,
            "bits": self.bits, "dither": self.dither, "noise_shape": self.noise_shape,
            "dither_filter": self.dither_filter, "tag": self.tag,
        }


PRESETS: list[Preset] = [
    Preset(
        "master_r8b", "母带级 · 最高保真", "保真优先",
        "r8brain full 档 + 1% 过渡带 + 250 dB 阻带。实测杂散 −211 dBc、镜像 −288 dBc，"
        "是本机所有引擎里最干净的一条路径；代价是 240× 实时（仍然远快于播放）。"
        "1% 过渡带让通带一直平到 21.8 kHz，是唯一在 22 kHz 处还有 −120 dB 的实现之一。",
        "r8b", {"quality": "full", "transband": 1.0, "atten": 250.0, "phase": "linear"},
        fmt="wav", bits=24, tag="推荐",
    ),
    Preset(
        "master_r8b_16", "母带级 · 16bit 交付", "保真优先",
        "同上的重采样设置，但输出 16bit 并开启 shibata 噪声整形。"
        "重采样用 207 dB 的浮点精度，量化噪声交给最后一步的噪声整形 —— "
        "这是 CD 交付的标准做法：先高精度处理，最后一次量化。",
        "r8b", {"quality": "full", "transband": 1.0, "atten": 250.0, "phase": "linear"},
        fmt="wav", bits=16, dither=True, noise_shape=True, dither_filter="shibata",
    ),
    Preset(
        "dpggb_ideal", "理想砖墙 · Deep_PGGB", "保真优先",
        "本项目自研的 FFT 重采样器：整段 FFT 做近乎理想低通，"
        "与精确解析参考的零差 **302 dB**（float64 的分析地板），与 PGGB 不可区分。"
        "**支持任意有理倍率**（44.1→48、96→44.1 都行），这是 PGGB 做不到的。"
        "杂散 −306 dBc、混叠抑制 −348 dBc（都贴住各自的分析地板），"
        "通带到 21.5 kHz 全平，代价只是 21.9 kHz 起的一小段过渡带。"
        "文件首尾各牺牲 20 ms 做渐变（20 ms 即饱和）；上下文 800 ms 是为了把"
        "升采样的镜像频带压到地板，比 400 ms 慢约两成但仍有 PGGB 的 4 倍以上。",
        "dpggb", {"block": 16.0, "context": 800.0, "btaper": 20.0, "rolloff": 200.0,
                  "rollorder": 2, "fade": 20.0, "taper": "smooth5",
                  "prec": "double", "phase": "linear"},
        fmt="wav", bits=24, tag="推荐",
    ),
    Preset(
        "dpggb_min", "理想砖墙 · 无预振铃", "特殊用途",
        "同上的砖墙重采样，但换最小相位：预振铃从 −38 dB 降到 −139 dB，"
        "瞬态（鼓、拨弦）听起来更紧。代价是必须在奈奎斯特下方留过渡带，"
        "所以 22 kHz 附近会提前一点滚降 —— 用测量指标换听感。",
        "dpggb", {"block": 16.0, "context": 800.0, "btaper": 20.0, "rolloff": 200.0,
                  "rollorder": 2, "fade": 20.0, "taper": "smooth5",
                  "prec": "double", "phase": "min"},
        fmt="wav", bits=24,
    ),
    Preset(
        "fast_soxr", "快速批量 · libsoxr VHQ", "速度优先",
        "libsoxr VHQ 实测 966× 实时（r8brain 的 4 倍），杂散 −188 dBc —— 比 SoX -v 还高 3 dB。"
        "代价是通带只到 21.5 kHz（22 kHz 处已跌到 −138 dB），"
        "对 44.1→48 这类常见转换完全够用。批量转码首选。",
        "soxr", {"quality": "VHQ", "precision": "float64"}, fmt="flac", bits=24, tag="推荐",
    ),
    Preset(
        "ssrc_fullband", "全带宽 · SSRC insane", "保真优先",
        "SSRC insane 用 2^18 点 FFT，通带一直平到 22.02 kHz —— 本工具箱里唯一真正保住"
        "全部 22.05 kHz 带宽的实现。代价是仅 13.8× 实时，且原生输出前后各垫约 0.9 秒延迟"
        "（本工具已用冲激探针自动裁掉）。只在需要极致高频保真时使用。",
        "ssrc", {"profile": "insane", "compensate_delay": True}, fmt="wav", bits=24,
    ),
    Preset(
        "soxng_v", "均衡 · sox_ng -v -s", "通用",
        "sox_ng 的 very-high 档 + 陡峭滤波，实测 −196 dBc 杂散、108× 实时。"
        "注意 **SoX 的默认 -h 档只有 −142 dBc**，换成 -v 立刻好 48 dB 而速度几乎不变 —— "
        "这是 SoX 用户最容易踩的坑。",
        "soxng", {"preset": "v", "steep": True, "phase": "linear"}, fmt="flac", bits=24,
    ),
    Preset(
        "soxng_ultra", "极致 · sox_ng -u", "保真优先",
        "sox_ng 新增的 ultra 档，实测 −199 dBc，107× 实时 —— 比 r8brain 慢一倍，"
        "杂散高 12 dB。如果你已经在用 sox_ng 生态（Dither/Noise shaping 一体），这是个稳妥选择。",
        "soxng", {"preset": "u", "steep": True, "phase": "linear"}, fmt="wav", bits=24,
    ),
    Preset(
        "minphase", "瞬态优先 · 最小相位", "特殊用途",
        "最小相位滤波器没有预振铃（pre-ringing），鼓组、拨弦、电子鼓这类瞬态素材听起来更"
        "紧、更靠前。代价是相位非线性 —— 多轨并行处理时要注意轨道间的相位一致性。",
        "r8b", {"quality": "full", "transband": 2.0, "atten": 206.91, "phase": "min"},
        fmt="wav", bits=24,
    ),
    Preset(
        "speech_16k", "语音 · 16 kHz 单声道", "场景",
        "语音识别/会议录音的标准预处理：r8brain 转 16 kHz、下混单声道、输出 16bit FLAC。"
        "16 kHz 的 Nyquist 是 8 kHz，人声能量几乎全在 4 kHz 以下，"
        "用 2% 过渡带即可，不必上 1%（那是给 44.1/48 全带宽用的）。",
        "r8b", {"quality": "full", "transband": 2.0, "atten": 206.91, "phase": "linear"},
        fmt="flac", bits=16, dither=True, noise_shape=True, dither_filter="shibata",
    ),
    Preset(
        "lofi_8k", "低保真 · 8 kHz", "场景",
        "电话/复古音色。8 kHz 采样率意味着 4 kHz 以上全部消失。"
        "注意下采样必然产生混叠，这里用 r8brain 的高阻带把它压到 −200 dB 以下，"
        "得到的是干净的低保真，而不是脏的低保真。",
        "r8b", {"quality": "full", "transband": 5.0, "atten": 206.91, "phase": "linear"},
        fmt="wav", bits=16, dither=True, noise_shape=False,
    ),
    Preset(
        "dsd_convert", "DSD · 2.8 MHz", "特殊用途",
        "先高质量转成 352.8 kHz PCM，再用 sox_ng 的 SDM 调制器转 DSD64。"
        "DSD 无法再编辑，只适合归档与播放；转回 PCM 时必然引入噪声整形的高频噪声，"
        "需要额外低通。",
        "r8b", {"quality": "full", "transband": 1.0, "atten": 250.0, "phase": "linear"},
        fmt="dsf", bits=24, dither=False,
    ),
    Preset(
        "draft", "草稿 · 最快", "速度优先",
        "sox_ng quick 档，快到几乎无感，但质量只够试听。"
        "用来快速确认时长/内容是否正确，正式输出请换回上面的预设。",
        "soxng", {"preset": "q", "steep": False}, fmt="wav", bits=16, dither=False,
    ),
]


def preset_choices() -> list[tuple[str, str]]:
    return [(p.key, f"{p.label}") for p in PRESETS]


def get(key: str) -> Preset | None:
    for p in PRESETS:
        if p.key == key:
            return p
    return None


def groups() -> list[str]:
    seen: list[str] = []
    for p in PRESETS:
        if p.group not in seen:
            seen.append(p.group)
    return seen


# --------------------------------------------------------------------------
# 参数百科
# --------------------------------------------------------------------------
@dataclass
class Term:
    key: str
    title: str
    short: str
    long: str
    unit: str = ""
    typical: str = ""

    def to_dict(self) -> dict:
        return {"key": self.key, "title": self.title, "short": self.short,
                "long": self.long, "unit": self.unit, "typical": self.typical}


GLOSSARY: list[Term] = [
    Term("spur", "杂散（Spurious）", "重采样器在非谐波位置留下的离散谱线",
         "输入一个纯正弦，输出却多出一堆不该存在的谱线，这些就是杂散。"
         "它来自滤波器系数的量化误差、有限字长舍入、以及多相分解的相位不连续。"
         "杂散是**离散的单根谱线**，听感上是若有若无的\"哨音\"或\"金属味\"，"
         "而不是宽带噪声。−200 dBc 意味着杂散比基波低 200 dB，远在任何系统的动态范围之外；"
         "−76 dBc（如 scipy 默认参数）则已经贴在 16bit 噪声底上了。",
         "dBc", "优秀 < −180，可用 < −120，可疑 > −100"),
    Term("image", "镜像（Imaging）", "上采样时残留在原频率附近的\"鬼影\"",
         "上采样本质是插入零值再低通。如果低通不够陡，插值产生的镜像会残留在 "
         "fs_src − f 处。44.1→48 时，1 kHz 的镜像落在 43.1 kHz（超出 Nyquist 听不到），"
         "但 44.1→96 时镜像落在 43.1 kHz 仍然可闻 —— 所以本工具用 44.1→96 来测。"
         "**FFmpeg 默认 swr 内核的镜像只有 −11 dB，这是最容易听出来的 SRC 缺陷**。",
         "dBc", "优秀 < −150，可用 < −100，危险 > −40"),
    Term("alias", "混叠（Aliasing）", "下采样时带外能量折叠回可闻频段",
         "下采样前必须低通到新 Nyquist 以下。滤不干净，30 kHz 的内容就会折叠到 "
         "44.1 − 30 = 14.1 kHz 处，变成一段与音乐毫无关系的\"哨音\"。"
         "混叠**不可逆**：一旦折叠进来，任何后期处理都无法把它与真实信号分开。"
         "本工具用 96→44.1、30 kHz 激励来测这条路径。",
         "dBc", "优秀 < −150，可用 < −90，危险 > −40"),
    Term("passband", "通带 / 过渡带", "滤波器从\"全通\"滚降到\"全阻\"的那一段",
         "理想低通在 Nyquist 处垂直切断，实际滤波器必须有过渡带。过渡带越窄，"
         "高频保得越多，但滤波器越长、越慢、预振铃越明显。"
         "本工具报两个数：21.5 kHz 与 22.0 kHz 处的增益（相对 1 kHz）。"
         "−32 dB 意味着 21.5 kHz 已经被削掉 32 dB —— 这是 libsoxr/ffmpeg 默认的行为；"
         "0.00 dB 意味着一直平到 21.5 kHz（SSRC insane、sox_ng -s）。",
         "dB", "全带宽要求 21.5 kHz ≥ −0.5 dB"),
    Term("phase", "相位响应", "线性相位 vs 最小相位",
         "线性相位：所有频率延迟相同，波形不变形，但有对称的预振铃（pre-ringing），"
         "且延迟大。最小相位：能量集中在因果侧，无预振铃，瞬态更\"紧\"，但相位非线性。"
         "母带/古典用线性；鼓组/电子/影视音效用最小相位。"
         "注意：**相位选择不改变频响与失真指标**，它只改变时间域的振铃分布。",
         "", "母带 linear，打击乐 min"),
    Term("dither", "抖动（Dither）", "量化前加入微量噪声，把量化失真变成白噪声",
         "从浮点降到 16/24bit 时，不做抖动会产生与信号相关的量化失真（谐波），"
         "听感上是\"沙哑\"而非\"嘶嘶\"。加抖动后失真变成与信号无关的白噪声，"
         "听感上更干净，代价是噪声底抬高约 4.8 dB（三角分布）。"
         "**32bit 浮点输出不需要抖动**。本工具用 sox_ng 的 dither 实现。",
         "", "16bit 必开，24bit 建议开，32bit float 关闭"),
    Term("noise_shape", "噪声整形（Noise Shaping）", "把量化噪声推向人耳不敏感的频段",
         "抖动的噪声是均匀分布的，但人耳在 3–4 kHz 最敏感、在 15 kHz 以上几乎不敏感。"
         "噪声整形用一个反馈滤波器把量化误差的频谱\"推\"到高频，"
         "从而在不增加总噪声功率的前提下显著降低可闻噪声。"
         "shibata 是 44.1/48 kHz 的经典曲线，lipshitz 适合 44.1，f-weighted 更温和。",
         "", "16bit 交付建议开启"),
    Term("lufs", "LUFS / 响度", "按 BS.1770-4 K 计权后的节目响度",
         "LUFS 是带 K 计权（模拟人耳频率响应）与门限（−70 LUFS 绝对门限、"
         "相对门限 −10 LU）的 RMS。流媒体平台通常把目标定在 −14 LUFS（Spotify/YouTube）"
         "或 −16 LUFS（播客）。**转采样率不应改变 LUFS** —— 如果变了，说明重采样过程中"
         "产生了失真或电平变化。本工具会对比输入/输出的 LUFS 作为一致性检查。",
         "LUFS", "流媒体 −14，播客 −16，广播 −23"),
    Term("truepeak", "真峰值（True Peak）", "重建模拟波形后的实际峰值",
         "数字采样点之间可能藏着比任何采样点都高的峰。重采样后峰值过冲（overshoot）"
         "很常见 —— 一个 −0.1 dBFS 的母带经过 SRC 后可能超过 0 dBFS 而削波。"
         "本工具用 4 倍过采样测真峰值（BS.1770 要求至少 4×）。"
         "**如果输出真峰值 > −1 dBTP，说明转换过程可能削波，应降低输入增益**。",
         "dBTP", "交付建议 ≤ −1.0"),
    Term("bitdepth", "有效位深", "信号实际用到了多少 bit",
         "一个 24bit 文件如果内容是从 16bit 升上来的，有效位深仍然是 16bit（低 8 位全是 0）。"
         "本工具用残差法估计：对信号做高位截断，看剩余能量。"
         "如果 24bit 文件的有效位深只有 12bit，说明它被过度压缩或经过有损处理，"
         "再存成 24bit 只是浪费空间。",
         "bit", "24bit 素材应 ≥ 20"),
    Term("crest", "波峰因数（Crest Factor）", "峰值与 RMS 的差，反映动态",
         "峰值 − RMS。古典/原声通常 14–20 dB，流行 8–12 dB，重度压限 4–6 dB。"
         "转采样率不应改变它 —— 如果明显变了，多半是出现了削波或过冲。",
         "dB", "流行 8–12，古典 14–20"),
    Term("dc", "直流偏移（DC Offset）", "波形整体偏离零轴",
         "直流偏移会浪费动态范围、在编辑时产生咔嗒声、并让某些编码器效率下降。"
         "正常素材应低于 −60 dBFS。重采样本身不会引入直流，但如果输入有，输出也会有。",
         "dBFS", "应 < −60"),
    Term("speed", "实时倍速（× realtime）", "处理 1 秒音频所需时间的倒数",
         "10 秒单声道 44.1→48 kHz 素材的处理速度。数值越大越快。"
         "注意这是单线程、冷启动后的最优值；实际批量处理受磁盘 I/O 限制。",
         "×", "> 50× 即可认为是\"瞬间完成\""),
    Term("null", "零差测试（Null Test）", "把两个输出相减，听剩下什么",
         "把被测引擎的输出与参考实现（默认 r8brain full + 250 dB）对齐后相减。"
         "差值越小，两者越接近。**但零差深度不是\"质量分数\"**：两个都正确的引擎"
         "因为滤波器形状不同，也一定会有差异。关键是看差异落在哪个频带 —— "
         "只在 16 kHz 以上是正常的滤波器设计差异，铺满整个可闻频段才是真问题。"
         "本工具会对差值做频带分解并据此判定。",
         "dB", "> 72 dB 且集中在高频 = 良好"),
    Term("quiet", "静段电平", "最安静的 5% 帧有多响",
         "把一个文件切成 20 ms 的帧，取最安静的 5% 求平均 —— 它回答的不是"
         "\"噪声底是多少 dB\"，而是\"音乐停下来的时候，电平掉到多低\"。"
         "连续演奏的流行乐通常在 −25 到 −35 dBFS；有真实静音间隙的古典/原声可以低到 −60 以下；"
         "如果这个值高于 −20 dBFS，说明整段素材被压得很平（响度战争的典型特征），"
         "或者根本没有静音段。真正测量化噪声要看有效位深。",
         "dBFS", "流行 −25…−35，古典 < −50"),
    Term("bandwidth", "信号带宽", "内容实际占据的最高频率",
         "用平均功率谱相对峰值下降 60 dB 的最高频点来估计。"
         "CD 音源通常到 20–21 kHz；MP3 320 通常只到 19–20 kHz（编码器切掉的）；"
         "老磁带转录可能只到 15 kHz。这个值决定了\"有没有必要升采样率\"。",
         "Hz", "CD 20–21k，MP3 19–20k"),
    Term("brickwall", "砖墙滤波（Brick-wall）", "过渡带宽度为零的理想低通",
         "普通重采样器的过渡带是「斜」的：从 21 kHz 到 22.05 kHz 一路滚降，"
         "这一段里频率响应既不是 1 也不是 0，高频细节被逐渐磨掉。"
         "砖墙的做法是把整段音频做一次 FFT，直接**把 Nyquist 以上的频点清零**再逆变换 —— "
         "过渡带宽度严格为零，通带一直平到 22.049 kHz，代价是一次变换要吃掉整段内存。"
         "Deep_PGGB 与 PGGB 都是这个路子。用整数相位的精确参考测量时，"
         "两者对理想解的偏差都在 −300 dB 量级（早期 −218 dB 那个数字其实是"
         "参考信号自身的浮点相位误差，是测量下限而非引擎上限）。",
         "", "理想：22.049 kHz 处仍有 0 dB"),
    Term("taper", "首尾渐变（Taper）", "文件两端为什么要淡入淡出",
         "文件从第一个采样直接开始、到最后一个采样直接结束，这在数学上是一个**阶跃**。"
         "阶跃含有全频段能量，理想低通会把它摊成一条按 1/d 衰减的长尾巴，"
         "从文件头一直渗到文件尾 —— 这就是为什么朴素的 FFT 重采样只有 −108 dB。"
         "两端各加一段 smootherstep 渐变后，边界不再有阶跃，同一测量立刻从 −108 dB 跳到 −218 dB"
         "（同口径下的实测差值）。渐变形状比长度更值钱，而且**形状就是升采样精度的天花板**："
         "渐变是乘法器，它的旁瓣会落到源奈奎斯特（22.05 kHz）上，而参考信号在那里是零。"
         "实测 15 kHz 音 × 20 ms 窗在 22.05 kHz 的泄漏：C2 −271.8 dB、C4 −342.1、C5 −359.6、"
         "C6 −341.2、C1 升余弦 −235.3。所以默认用 C5：40 音升采样零差从 C2 的 233 dB 提到 302.5 dB。"
         "**这是 FFT 类重采样器最容易被忽略、又最影响结果的一步。**",
         "ms", "默认 20 ms，且夹紧到文件长度的 5%"),
    Term("imd", "互调失真（IMD）", "两个音同时在时会不会长出第三个音",
         "单音测试只回答\"有没有多余的谱线\"；互调测试同时送两个音（CCIF 用 19 kHz + 20 kHz，"
         "SMPTE 用 60 Hz + 7 kHz），再看 2f₁−f₂、2f₂−f₁、f₂−f₁ 这些**原本不存在**的频率上"
         "有没有能量。线性系统无论输入几个音都不会产生新频率，所以互调产物的电平就是"
         "**线性度的直接量度**——它比单音杂散更容易暴露插值、量化、块间幅度调制这类缺陷。"
         "本工具在 44.1→96 kHz 下测 CCIF 与 SMPTE 两组双音，取最差产物。",
         "dBc", "> −120 dBc 即远低于可闻阈值"),
    Term("multitone", "多音测试（Multitone）", "用 24 个音模拟真实音乐的频谱密度",
         "把 24 个对数等间隔（100 Hz–18 kHz）、相位按 Schroeder 公式铺开的正弦叠加，"
         "峰均比压到接近音乐信号。相比双音，它一次性激励整个频段，"
         "能抓住只在特定频率组合下出现的互调与寄生边带。"
         "判定用\"残余\"：每个音都精确落在整秒窗的 FFT bin 上，"
         "因此把各音所在 bin 扣掉后的剩余能量，就等于对每个音做幅度/相位自由的最小二乘"
         "拟合后剩下的部分——对群延迟与通带下垂不敏感，只对**新长出来的频率成分**敏感。",
         "dB", "> −90 dB 相对音的总能量"),
    Term("spectrogram", "频谱图", "时间 × 频率 × 能量的二维图",
         "横轴时间、纵轴频率、颜色表示能量。用来一眼看出：高频是不是被切了、"
         "有没有周期性噪声、瞬态是否被抹平、编码器有没有在 16 kHz 处硬切。",
         "", ""),
]


def glossary_index() -> dict:
    return {t.key: t.to_dict() for t in GLOSSARY}
