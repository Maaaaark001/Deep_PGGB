# -*- coding: utf-8 -*-
"""Build work/paper/blocks.json for the Deep_PGGB manuscript (part 1)."""
import os
import struct

B = []


def h1(x): B.append({"t": "h1", "x": x})
def sub(x): B.append({"t": "subtitle", "x": x})
def h2(x): B.append({"t": "h2", "x": x})
def h3(x): B.append({"t": "h3", "x": x})
def p(x): B.append({"t": "body", "x": x})
def cap(x): B.append({"t": "caption", "x": x})
def ref(x): B.append({"t": "ref", "x": x})
def eq(x, n): B.append({"t": "eq", "x": x, "n": n})
def pb(): B.append({"t": "pb"})


def tbl(rows, c, widths=None, header=1, **kw):
    d = {"t": "table", "rows": rows, "cap": c, "widths": widths, "header": header}
    d.update(kw)
    B.append(d)


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def fig(src, c):
    path = os.path.join(ROOT, src)
    with open(path, "rb") as f:
        head = f.read(33)
    w0, h0 = struct.unpack(">II", head[16:24])
    w = min(580, int(round(w0 * 96.0 / 300.0)))
    h = int(round(w * h0 / float(w0)))
    B.append({"t": "fig", "src": src, "w": w, "h": h, "cap": c})


# ------------------------------------------------------------------ 题名
B.append({"t": "title", "x": "任意有理倍率的分块频域重采样方法"})
sub("——误差分解、流式扩展与八引擎对照")
B.append({"t": "author", "x": "Maaaaark"})
B.append({"t": "affil", "x": "（独立研究者，深圳 518000）"})
B.append({"t": "corr", "x": "通信作者：Maaaaark，E-mail：maaaaark@163.com"})
B.append({"t": "date", "x": "收稿日期：2026-11-24"})

h1("摘要")
p("采样率转换在 24 bit 音频链中的指标通常止于 −144 dBFS，但在测量、母带与多次级联等场景中，算法误差会累积，需要在更低的量级上给出可复现的结论。本文研究分块频域重采样在任意有理倍率下的误差构成，并建立一套以 −307 dBc 为地板、灵敏度到 −310 dBc 的测量协议。")
p("方法把倍率 L/M 映射到同一张频域网格：取输入点数 P=M·s、输出点数 Q=L·s，s 为仅含 2、3、5 因子的光滑数，使 Q/P 精确等于 L/M，重采样退化为频域补零；块步进与上下文取 M 的整数倍，使相邻块的输出网格保持整相位；文件边界采用 20 ms 五次 smootherstep 渐变窗（C5 为窗名）。误差被分解为网格相位、块接缝、边界窗旁瓣与浮点舍入四项，并分别给出控制量与实测值。")
p("九种倍率的零差（输出与增益精修参考的残差比，定义见 §4.2）为 300.9–303.8 dB，含素数分母的 44.1→50.001 kHz 为 300.9 dB；五次 smootherstep 窗把升采样方向的零差从余弦窗的 207.9 dB 提高到 302.6 dB。流式实现把同一频域核置于 FIFO 之后，稳态零差 296–303 dB，长度漂移为零，代价是至少一个核心区加上下文的算法时延。在统一协议下对照八台引擎，只有 Deep_PGGB 与 PGGB 触及 float64 地板，其余六台的杂散高出地板 23–221 dB；因此在 −300 dBc 量级上，前两者之间 0.6 dB 的差异不构成排序。")
p("本文的结论是：当精度进入浮点地板，可复现的误差分解与测量协议比继续压低单个数字更有价值；流式扩展则把这一精度带入准实时与分块流水线，其代价可以显式量化。真实素材给出这条结论的边界：2 分钟立体声音乐上，以该引擎 120 s 整段输出为参考，带 800 ms 上下文的引擎内 16 s 分块零差为 175.2 dB，比 24 bit 理论信噪比高 29 dB；无上下文的独立分段拼接只有 30.2 dB，另外七台引擎的独立拼接为 41.3–91.6 dB。八声道逐通道零差为 303.9–305.8 dB，通道间无泄漏。")
B.append({"t": "meta", "x": "关键词：采样率转换；频域补零；误差分解；零差测量；流式处理；窗函数"})
B.append({"t": "meta", "x": "PACS：43.60"})
B.append({"t": "en_title", "x": "A Block-Wise Frequency-Domain Sample-Rate Conversion Method for Arbitrary Rational Ratios"})
B.append({"t": "en_sub", "x": "—Error Decomposition, Streaming Extension, and an Eight-Engine Comparison"})
B.append({"t": "en_author", "x": "Maaaaark"})
B.append({"t": "en_affil", "x": "(Independent Researcher, Shenzhen 518000, China)   Corresponding author: maaaaark@163.com"})
B.append({"t": "en_body", "x": "Sample-rate conversion (SRC) for 24-bit audio is usually specified down to −144 dBFS, yet measurement, mastering, and cascaded processing call for reproducible behaviour at much lower error levels. This paper studies block-wise frequency-domain resampling at arbitrary rational ratios and establishes a measurement protocol with a −307 dBc floor and −310 dBc sensitivity. The ratio L/M is mapped onto one spectral grid by choosing P=M·s and Q=L·s with s a 5-smooth integer, so that Q/P=L/M exactly and resampling reduces to spectral zero-padding. Block hops and contexts are constrained to integer multiples of M, which keeps the output grid phase-aligned across blocks; a 20 ms fifth-order smootherstep window handles file boundaries. The error is decomposed into grid phase, block seam, boundary-window sidelobe, and floating-point rounding. Nine ratios reach null depths of 300.9–303.8 dB; the smootherstep window raises the 40-tone null depth from 207.9 to 302.6 dB. A FIFO streaming extension holds 296–303 dB with zero length drift, at the cost of algorithmic latency. Under one protocol, eight engines are compared; only Deep_PGGB and PGGB reach the float64 floor, and their 0.6 dB difference lies below repeatability. On 16 s blocks of real music, measured against each engine's own 120 s whole-file output, the engine-internal block with 800 ms context reaches 175.2 dB, 84–134 dB above independent segment splicing by the other seven engines (41.3–91.6 dB); splicing Deep_PGGB itself gives only 30.2 dB. The contribution is the decomposition and the protocol, not a new interpolation kernel."})
B.append({"t": "en_kw", "x": "**Keywords:** sample rate conversion; frequency-domain zero-padding; error decomposition; null-depth measurement; streaming; window functions"})

# ------------------------------------------------------------------ 1
h1("1  引言")
p("采样率转换（sample rate conversion, SRC）是数字音频处理链中的基本操作。理想重采样定义为带限插值[4]：把离散序列视为连续带限信号的样本，在目标时刻重新取值。任何实现都只能逼近这一理想，逼近方式决定了算法的误差结构、通带与计算代价。")
p("工程实现主要有两条路线。多相有限脉冲响应（FIR）把插值核分解为 L 个相位，每个输出只访问其中一个相位，计算量与滤波器长度成正比、与倍率无关[1–3]，因而适合实时系统；sox_ng[12]、libsoxr[13]、r8brain[14] 与 SSRC[15] 均属此类，差异在滤波器设计（Kaiser 窗、等波纹、最小二乘）以及过渡带与阻带之间的取舍。频域方法把整段信号变换到频域，补零或截断后反变换[4,5]；PGGB[16] 与本文的 Deep_PGGB 采用后者，scipy.signal.resample_poly 虽以多相 FIR 实现，接口与用途相近[7]。")
p("频域方法有一个可精确陈述的性质。若输入点数 P 与输出点数 Q 满足 Q/P=L/M，且 P、Q 可用同一组频点表示，则重采样不需要插值核：输出频谱就是输入频谱的补零或截断。该性质在周期信号上是严格的（命题 1），对有限长信号则受块边界与文件边界调制；这两类边界正是工程实现中误差的主要来源。")
p("已有对照多止于 −180 dBc 量级。InfiniteWave 的公开比较[17]以扫频、单音、通带与过渡带为激励，覆盖了模拟与数字域的主要商用实现；厂商文档通常给出阻带衰减与通带纹波。当被测误差低到 −300 dBc，测量系统本身的相位累积、增益估计与窗泄漏会先于被测对象失效，公开数据中缺少可复现的协议与地板声明。本文因此把测量方法作为与算法并列的研究对象。")
p("本文把这条误差链作为组织全文的线索：理想带限插值给出目标，频域网格决定映射是否精确，分块接缝决定块与块能否拼接，文件边界决定有限长信号的两端，浮点舍入则给出测量下限（表 1）。四者处在同一条链上，前一环的残余会改变后一环的落点。")
p("沿这条链，本文首先把倍率映射写成 P=M·s、Q=L·s，使任意有理倍率的频域映射精确成立，并把块步进与上下文约束为 M 的整数倍，以保持相邻块的输出网格整相位。边界上，本文指出决定升采样精度上限的是渐变窗的平滑阶数而非长度，并给出 20 ms 五次 smootherstep 窗的组合；这对应降采样已达 302 dB、升采样却停在 233 dB 的现象。把同一内核放进 FIFO 之后，离线结果扩展到连续流：稳态输出与离线整文件在 float64 内一致，长度不漂移，头部差异在 20 ms 处降到 −78 dB。测量方面，本文给出一套可复现到 −310 dBc 的协议，并在同一协议下对照八台引擎，区分“贴地板”与“地板以上”两种读数。")
p("以下各节沿这条链展开：第 2 节给出相关工作、问题定义与误差分解，第 3 节描述实现，第 4 节定义测量，第 5 节报告结果，第 6 节讨论适用边界与局限，第 7 节总结；附录 A 列出复现所需的软硬件环境与命令。")

# ------------------------------------------------------------------ 2
h1("2  相关工作与问题定义")
h2("2.1  时域多相结构")
p("多相结构将插值核 h[n] 按输出相位分解，第 p 个输出只与 h 的第 p 个相位做卷积，因此每输出样本的乘法数与滤波器长度 K 成正比，与 L 无关[1–3]。其设计问题归结为在给定过渡带宽 Δf 与阻带衰减 A_{s} 下最小化 K；Kaiser 窗的经典估计为 K≈(A_{s}−8)/(2.285·2πΔf)[8]。这一族方法的精度上限由系数字长与舍入决定，双精度实现通常在 −180 至 −250 dBc 量级；优点是无块边界、时延可控、可逐样本流式。")
p("r8brain 与 libsoxr 在通带末端采用不同的滚降策略，sox_ng 暴露 transition bandwidth 与 phase response 等参数，SSRC 以高衰减长核换取阻带抑制。这些差异在 −180 dBc 以上可分辨；在本文关注的 −300 dBc 量级，误差不再由滤波器设计单独决定。")
h2("2.2  频域补零与周期 sinc 插值")
p("频域补零重采样是经典方法[4,5]。对长度 P 的序列做 DFT，在频谱中部补零到 Q，再反变换并乘以 1/P 归一化，等价于以周期 sinc 为核的带限插值。Fraser[5] 系统讨论了该方法的插值精度与实现陷阱，指出误差主要来自频谱截断、补零位置与归一化，而非 FFT 本身。")
p("频域重采样此后仍有进展。Bi 与 Mitra 系统整理了整数与分数倍率的 DFT 域搬移及其误差与复杂度[19]；Välimäki 与 Bilbao 的 Giant FFT 对整段音频做一次大变换，在频域插零或截断，再一次逆变换合成[20]。Brückl 与 Schönle 随后把 Giant FFT 与理想 sinc 插值逐项对照，解析了时域混叠并给出误差界[21]；Salmi 与 Välimäki 则用频域 Dolph–Chebyshev 双窗压低奈奎斯特振铃[22]。这些工作与本文共享频域补零这一内核，差别在分块与边界：Giant FFT 没有块接缝，但需要 O(N) 内存，不能流式；本文用块加上下文换取任意长文件与流式 FIFO，代价是要单独处理接缝与文件边界。本文不主张首次提出频域重采样，也不重复 Giant FFT 的误差分析；本文主张的是四类误差的分解、接缝的整相位条件，以及在 float64 地板上可复现的测量协议。")
h2("2.3  既有对照的覆盖范围")
p("公开的 SRC 对照以可听域指标为主：通带纹波、阻带衰减、混叠、群时延与听感。这些指标的分辨率通常在 −120 至 −180 dBc，足以区分消费级与专业级实现，但不足以区分“数值精确”与“误差 −250 dBc”的实现。当比较进入 float64 地板，首先需要声明分析地板、激励长度、窗函数与聚合方式；否则引擎之间的排序会随协议改变。第 4 节给出这样一套协议。")
h2("2.4  问题定义与误差分解")
p("设源序列 x[n] 的采样率为 f_{s}，目标为 f_{s}′，比值 f_{s}′/f_{s}=L/M 为既约分数。重采样算子 R 把 x 映射为 y[m]=x_c(m·M/L)，其中 x_c 为 x 的带限插值。理想算子不可实现；实际实现给出 ỹ=y+e。本文把 e 分解为四项：")
eq("e = e_{grid} + e_{seam} + e_{boundary} + e_{round}", 1)
p("e_{grid} 来自频域网格与输出采样时刻的相位失配；e_{seam} 来自分块引入的周期延拓；e_{boundary} 来自文件首尾的硬切与渐变窗；e_{round} 来自有限精度算术。表 1 给出各项的机制、控制量与实测水平。四项并不独立：边界窗改变信号的频谱，从而改变接缝误差的落点；舍入误差则构成其余三项的测量下限。")
tbl([
    ["误差项", "机制", "控制量", "实测"],
    ["网格相位 e_{grid}", "块步进不是 M 的整数倍，输出网格偏移分数样本并逐块累积", "C_{in}=M·c", "对齐后无可见接缝（>305 dB）"],
    ["块接缝 e_{seam}", "块边周期延拓与上下文截断", "上下文 800 ms", "305.7 dB（分块对整段）"],
    ["文件边界 e_{boundary}", "渐变窗旁瓣落在源奈奎斯特", "C5 窗，20 ms", "302.6 dB（40 音）"],
    ["浮点舍入 e_{round}", "float64 FFT 与累加", "精度档", "≈302 dB"],
], "表 1  误差项分解。表中数值为该项单独作用时的零差深度；四项的合成结果即 §5.1 的总零差。",
   widths=[118, 250, 100, 130])
p("命题 1 设 x[n] 为周期 P 的序列，X[k] 为其 DFT；令 P=M·s、Q=L·s，定义 Y[k]=X[k]（0≤k≤min(P,Q)/2），其余频点按共轭对称置零，y[m]=(1/P)Σ_{k=0}^{Q−1}Y[k]e^{j2πkm/Q}。若 x 在 min(P,Q)/2 以上无谱线，则 y[m]=x_c(mM/L)，其中 x_c 为 x 的周期带限插值。")
p("证明：x 的 DTFT 是位于 f=k·f_{s}/P 的线谱，系数为 X[k]/P。补零或截断不改变保留下来的系数，只把频率轴加密到 1/(Q·T_{s}′)；反变换在同一条谱线上取值，故 y 与 x_c 在输出时刻 mM/L 上相等。由三角多项式的唯一性，等式对所有 m 成立。证毕。")
p("命题 1 说明，频域补零的精度上限由“块是否可视为周期信号”决定，而非由插值核长度决定。分块把每个块当作周期序列，块边因此出现周期延拓误差；文件首尾的硬切则通过渐变窗把阶跃摊成旁瓣。以下两节分别处理这两类边界。")

h2("2.5  术语与记号")
p("“整段处理”指一次调用处理完整文件；“分块处理”把输入切成固定长度的块。块中真正输出的部分称为“核心区”，两侧额外读入、只用于吸收滤波器瞬态而不输出的样本称为“上下文”。如果分块在引擎内部完成、相邻块保留上下文，本文称为“引擎内分块”；如果在外部把输入切成互不重叠的独立文件、逐块调用引擎后直接首尾拼接，称为“独立分段拼接”。前者块间连续，后者在接缝处会出现相位与幅值跳变。")
p("“整相位”指相邻块核心区的输出采样时刻落在同一输出网格的整数点上，不出现分数样本偏移。“光滑数”指只含 2、3、5 三个素因子的整数，记 s=2^{a}3^{b}5^{c}；取光滑数是为了让 P=M·s 与 Q=L·s 都能用混合基 FFT 处理。“砖墙”指频域上的理想矩形截断：通带内增益为 1，阻带内为 0，过渡带宽度为零。“滚降”是降采样时在通带末端主动引入的过渡带，用少量带宽换取更低的混叠。")
p("“零差”（null depth）是转换输出与增益精修参考之间的残差比，定义见式 (5)；“分析地板”是测量链自身在 float64 下的残余，本文约 302 dB；“贴地板”指被测读数与分析地板相差不到重复性，只能说明“低于测量分辨率”，不能用于排序。“实时倍速”指每秒墙钟时间处理的输入音频秒数，记作 ×。其余符号在首次出现处定义。")

# ------------------------------------------------------------------ 3
h1("3  方法")
h2("3.1  精确有理映射")
p("取光滑数 s=2^{a}·3^{b}·5^{c}，令 P=M·s、Q=L·s。于是 Q/P=L/M 精确成立，且 P、Q 均可由混合基 FFT 处理[6]。输入第 k 个频点对应 f=k·f_{s}/P，输出第 k 个频点对应 f=k·f_{s}′/Q=k·f_{s}/(M·s)，二者是同一张网格。频域重采样因此退化为补零或截断：")
eq("Y[k] = X[k]，0 ≤ k ≤ min(P, Q)/2", 2)
p("其余频点置零，并按共轭对称恢复负频率；反变换后乘以 1/P，通带增益归一。降采样时 Q<P，高于 Q/2 的频点被丢弃；升采样时 Q>P，新频点置零。整个过程没有插值核与过渡带设计，阻带抑制由频域截断的锐度决定。")
p("光滑数的选择只影响效率。若 P、Q 含大素数因子，混合基 FFT 退化为 任意长度 FFT（Bluestein 算法）[6]，成本上升；把 s 取为 2、3、5 的乘积，可在几乎不增加点数的前提下保持 O(N log N)。44.1→48 kHz 的 L/M=160/147，P=147s、Q=160s；44.1→50.001 kHz 的 L/M=2381/2100，P=2100s、Q=2381s，2381 为素数。后者的零差仍达到 300.9 dB，说明精度不依赖倍率的算术形式，而依赖 P、Q 是否落在同一网格上。")
p("输出幅度在内部区间严格等于输入幅度。若在整段文件上估计增益，4 s 测试会读到 0.4975 而非 0.5000；该读数来自首尾各 20 ms 的渐变：它占 1% 时长、平均窗值为 0.5，并非全局增益误差（§4.2）。")

h2("3.2  分块、上下文与重叠保留")
p("分块采用重叠保留[18]。第 b 块取输入区间 [b·C_{in}−C_{ctx}, (b+1)·C_{in}+C_{ctx})，变换后只保留与核心区对应的输出，再把各块的核心区按序拼接。核心区与上下文均取 M 的整数倍：C_{in}=M·c，C_{out}=L·c。")
p("命题 2 若 C_{in} 是 M 的整数倍，则相邻块的输出网格相位连续。证明：第 b 块的起始输入样本为 b·C_{in}，对应输出时刻 b·C_{in}·L/M=b·L·c，为整数；因此各块核心区在输出网格上首尾相接，不产生分数样本偏移。证毕。")
p("若步进不是 M 的整数倍，Q/P 在全局仍成立，但块内网格相对整段偏移一个分数样本；该偏移随块序号累积，在接缝处表现为周期性的相位台阶。实测中这类接缝会把 SMPTE 边带抬高约 10 dB。")
p("上下文长度决定块边周期延拓误差的衰减。对升采样，它要装下砖墙滤波器的时域尾巴；对降采样，它要装下抗混叠滤波器的尾巴。实测 800 ms 把镜像项从 −315.6 dBc 提高到 −319.0 dBc；继续加长收益递减，而内存与单次变换长度线性增长。接缝本身在 100 ms 上下文时已饱和（305.8 dB），此后的上下文只改善混叠（§5.5）。")
p("块长同时影响速度与接缝：块越短，可并行的块越多，但接缝周期也越短。0.5 s 块在 8 个工作线程下达到 187×，16 s 块（默认）约 180×；但小块会在 SMPTE 边带上留下痕迹。默认取 16 s，是速度与接缝之间的折中。图 1a 给出离线路径的信号流。")

h2("3.3  边界、平滑阶数与 C5 窗")
p("把长度 N 的信号乘以窗 w(n)，其频谱是原频谱与 W(f) 的卷积。若 w 在端点不连续，W(f) 的旁瓣按 1/f 衰减；若低阶导数也不连续，衰减更慢、旁瓣更宽[8,9]。升采样时，源奈奎斯特（源采样率的一半）f_{s}/2 落在输出通带边缘，W(f) 在该处的残留不会被后续滤波去掉，因此直接决定零差上限。")
p("本文采用五次 smootherstep 窗（实现中记 C5，5 指多项式次数；窗在端点保持 C^{2} 连续）：")
eq("w(t) = S_{5}(min(t, 1−t))，S_{5}(u) = 6u^{5} − 15u^{4} + 10u^{3}", 3)
p("t>0.5 时取 1−w(1−t)，以避免大数相消。图 6a 与表 4 给出不同档位的泄漏与 40 音（40 个对数间隔等幅正弦）零差：C1 的余弦窗在 22.05 kHz 留下 −215.6 dBc，C2 改善到 −259.8 dBc，C4 到 −329.9 dBc，C5 到 −355.7 dBc；40 音零差相应从 207.9 dB 升到 302.6 dB。C6 把泄漏再压低 21 dB，但零差停在 302.6 dB，收益被 float64 地板吸收。图表沿用实现的窗名 C1–C6，数字指档位而非连续性阶数。")
p("渐变窗长度取 20 ms。更长的窗会削弱素材本身，更短的窗使旁瓣变宽；20 ms 在 44.1 kHz 下为 882 点，对 16 s 块占 0.55%。渐变窗只处理文件边界，不参与块接缝；块接缝由上下文与 M 对齐的步进解决，两者在实现中已经解耦。")

h2("3.4  流式扩展：FIFO 与滑窗")
p("流式实现把同一内核置于先进先出（FIFO）缓冲之后。FIFO、读指针（游标）与窗口拼接位于 C++ 引擎内，对外只暴露 dpggb_stream_create/push/flush/destroy 四个 C 入口。每次 push 把新样本追加到缓冲区；当缓冲区中至少有左上下文、一个核心区与右上下文时，取窗、变换、只输出核心区，然后游标前进一个核心区长度。")
p("把状态放进引擎层，使线程局部的 FFT plan 能跨窗口复用，也避免每个窗口重新进入进程或临时文件。同一窗口几何下，这一改动把流式吞吐提高 3.5–4.1 倍（§5.6）。窗口之间保留重叠，但重叠只用于计算，不参与输出。早期版本在相邻核心区之间做 交叉淡化（cross-fade），把两个不重叠的时间区混在一起，4 s 测试的长度漂移达到 66918 帧，零差跌到 −3.4 dB；去掉 交叉淡化（cross-fade） 后漂移归零。")
p("头部存在一个约定差异。第一个窗口没有左上下文，只能零填充；离线路径则在真实文件头做 20 ms 渐变。流式实现无法知道“这是文件头”，因此前 20 ms 的输出与离线不同。实测偏差在 20 ms 处降到 −78 dB，80 ms 后低于 −90 dB，之后进入稳态。把连续流的第一次 push 当作文件头，这是使用者的选择；算法本身不区分文件头与连续流。")

h2("3.5  复杂度与内存")
p("设单个块的输入为 P、输出为 Q，单块成本为 C_{blk}=O((P+Q)log(P+Q))；总成本与文件长度成线性，常数由 FFT 后端与精度档决定。多相 FIR 的单样本成本为 O(K)，总成本为 O(N_{src}·K)。当 K≫log N 时频域方法占优；当倍率接近 1 且滤波器很短时，多相方法更省。")
p("内存方面，离线路径需容纳一个块的输入、输出与 FFT 缓冲，约为 8(P+Q) 字节（双精度）；流式路径只需容纳一个窗口，即 core+2·ctx，与文件长度无关。FFTW 的单次变换内并行（--threads）在本实现中无效，有效的并行粒度是块：各块之间无数据依赖，可独立变换。流式路径没有这一并行度，因为窗口之间存在数据依赖；这是 §5.6 中流式吞吐低于离线的主要原因之一。")

fig("work/figures/png/fig1_architecture.png",
    "图 1  分块频域重采样的信号流。(a) 离线路径：输入按 16 s 分块，块两侧各取 800 ms 上下文，实序列 FFT（rFFT）后把 P 个频点补零到 Q 个，逆变换（irFFT）后只保留核心区并按序拼接；三个核参数分别控制边界渐变、通带滚降与最小相位重建。(b) 流式路径：FIFO 累积输入，按“左上下文|核心区|右上下文”取窗，复用同一内核，只输出核心区，游标按核心区长度推进；上下文在相邻窗之间重叠，不参与输出。")
