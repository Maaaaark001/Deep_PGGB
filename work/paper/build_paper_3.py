
h2("4.4  吞吐量")
p("图 5a 是块长与 worker 数的网格。0.5 s 块、2 workers 达到 148.3×，16 s 块、自动线程为 117.7×，"
  "30 s 块降到 107.0×。--threads 让 FFTW 在单次变换内并行，实测完全无效；有效的并行粒度是块。"
  "双 worker 已经接近上限，继续增加到 4 或 8 个 worker 的收益被内存带宽抵消。")
p("图 5b 是八台引擎在统一口径下的吞吐量。Deep_PGGB 117.7×，r8brain 89.9×，sox_ng 90.5×，"
  "FFmpeg 130.2×，SciPy 138.2×，libsoxr 584.8×，PGGB 30.0×，SSRC 24.4×。"
  "Deep_PGGB 比 r8brain 快 1.31 倍，比 PGGB 快 3.92 倍。libsoxr 的 584.8× 与本节的精度结论并不矛盾："
  "它用 −196.7 dBc 的最差指标换速度。")
fig("work/figures/png/fig5_speed.png",
    "图 5  吞吐量。(a) 60 s 立体声 44.1→88.2 kHz 下，吞吐量随块长与 worker 数的变化；"
    "(b) 八台引擎在同一口径下的吞吐量，对数横轴。误差量级为同机三次运行的 ±10%，跨会话 ±20%；"
    "图中只把 1.3 倍以上的差异当作排序。")

h2("4.5  参数机理")
p("图 6a 是渐变窗阶数与 22.05 kHz 泄漏的关系。C1 到 C6 的泄漏单调下降，零差在 C5 饱和；"
  "C6 的 21 dB 额外泄漏抑制没有转化为零差，因为后者已经贴到 float64 地板。"
  "这解释了此前一个长期存在的困惑：为什么降采样方向早已达到 302 dB，升采样方向却停在 233 dB。"
  "限制不在滤波器长度，也不在块长，而在渐变窗的旁瓣落点。")
p("图 6b 是上下文与块边缘渐变对混叠的影响。上下文从 50 ms 加到 800 ms，22.05 kHz 的抑制从 −137.4 升到 −211.2 dBc；"
  "块边缘渐变在 5–20 ms 之间只差约 1 dB，50 ms 略差，因为更长的边缘渐变把块内有效区压得更短。"
  "接缝本身在 100 ms 上下文时已经饱和（305.8 dB），此后的上下文长度只改善混叠，两者是独立的问题。")
p("分块与整块处理的一致性用零差直接检验：块长 0.25、0.5、1、2 s 时，分块输出相对整块输出的零差都是 305.6 dB；"
  "块长不小于文件长度时，两条路径退化为同一条，比较结果为逐位相同。")
fig("work/figures/png/fig6_params.png",
    "图 6  参数机理。(a) 渐变窗连续性阶数与 22.05 kHz 泄漏；底部标注为 40 音零差。"
    "(b) 块上下文与块边缘渐变对 22.05 kHz 混叠抑制的影响；四条曲线对应 5、10、20、50 ms 的块边缘渐变。")

h2("4.6  流式一致性")
p("图 7a 是流式输出逐 0.5 s 窗相对离线整文件的零差。第 0 窗为 17.6 dB，第 1 窗 104.5 dB，"
  "第 2 窗起 296.3–302.5 dB；第 0、1 窗的偏差来自头部约定，不是稳态误差。"
  "4 s 双声道测试的输出长度为 352800 帧，与 4.0×88200 精确相等，没有累积漂移。")
p("图 7b 是头部偏差随偏移的变化。0 ms 处偏差为 −1.7 dB（几乎完全不同），20 ms 处 −78.1 dB，"
  "40 ms 处 −84.2 dB，80 ms 后 −90 dB 以下。20 ms 正好是渐变窗长度；超过它之后，流式与离线只差 float64 舍入。"
  "稳态内部零差为 296–303 dB，与离线路径同量级。")
p("流式路径的代价是算法时延：在拿到右上下文之前不能输出核心，因此端到端时延至少是核心长度加一个上下文；core 1.0 s 加 800 ms 上下文时实测 1.80 s（§4.7）。"
  "对实时监听，这个时延偏大；把 core 与 context 一起压到 100 ms 量级，时延可降到约 0.2 s，代价是 22.05 kHz 的混叠抑制从 −211.2 降到 −161.2 dBc。"
  "这是设计上可以显式选择的折中，而不是实现限制。")
fig("work/figures/png/fig7_streaming.png",
    "图 7  流式输出与离线整文件处理的一致性。(a) 逐 0.5 s 窗的零差；第 2 窗起进入 296–303 dB 的稳态。"
    "(b) 头部偏差随偏移的变化；20 ms 为渐变窗长度，偏差来自头部约定，不是稳态误差。")

h2("4.7  流式吞吐与时延")
p("图 8 把有增量接口的四台引擎放进同一流式口径：60 s 立体声 44.1→88.2 kHz，按 256、1024、4096 帧分块喂入；"
  "吞吐量按输入秒数除以墙钟秒数，时延定义为第一帧输出之前已经消耗的输入时长。"
  "r8brain、SSRC、SciPy 与 PGGB 在本工具箱中没有增量接口（r8brain 的 C++ 类可按块调用，但本工具箱只绑定了 CLI），不进入这一比较。")
p("Deep_PGGB 在 core 1.0 s、1024 帧块下为 54.2×，时延 1.80 s；core 0.5 s 为 33.9×/1.30 s，core 2.0 s 为 74.8×/2.80 s。"
  "块长从 256 增到 4096 帧只把 core 1.0 s 从 51.1× 抬到 54.8×：FIFO、游标与窗口拼接已经下沉到 C++ 的 dpggb_stream_* 接口，"
  "Python 每块只做一次 ABI 调用，前端不再按块长放大。")
p("作为对照，同样窗口几何的 Python 外挂补丁（每个窗口重新调用 dpggb.exe）只有 9.6×/13.5×/18.4×；"
  "原生实现去掉每窗口的进程启动、临时文件往返和重复 FFT plan 建设，提升 3.5–4.1×。")
p("原生流式吞吐达到离线 117.7× 的 46%（core 1.0 s）到 64%（core 2.0 s）。剩余差距来自算法结构：每个窗口长 core 加两侧 context，"
  "却只产出 core；core 1.0 s 时重叠 2.6×，窗口之间又有数据依赖，离线路径的块并行在流式里不存在。"
  "core 2.0 s 用更大时延换到 74.8×，适合文件转码与准实时流水线；硬实时监听需要把 core 与 context 同时压小，"
  "代价是 §4.6 已经量化的混叠抑制下降。流式支持不是免费的第四个维度，而是把同一套频域核放到另一个工作点上。")
fig("work/figures/png/fig8_stream_bench.png",
    "图 8  流式吞吐量与时延。(a) 吞吐量随分块大小的变化；Deep_PGGB 取 core 1.0 s，其余引擎取各自默认档。"
    "(b) 1024 帧块下首帧时延与吞吐量的关系；虚线为 Deep_PGGB 的离线吞吐 117.7×，离线路径没有首帧时延，故只画参考线。"
    "r8brain、SSRC、SciPy、PGGB 无增量接口，未参与比较。")

# ------------------------------------------------------------------ 5
h1("5  讨论")
h2("5.1  与 PGGB 的关系")
p("Deep_PGGB 与 PGGB 属于同一类算法：频域、砖墙、float64、分块。两者的零差在 0.6 dB 内一致，"
  "说明它们都碰到了同一块地板。差别在能力边界：PGGB 只接受整数倍率，向它请求 44.1→48 kHz 时"
  "输出 176400 个样本而不是 192000，且不报错；它没有降采样路径，输出峰值归一化到 0.99。"
  "Deep_PGGB 支持任意有理倍率、双向转换、流式 FIFO 与可调的块参数。这些差异不是精度上的胜负，"
  "而是适用场景的不同。表 3 把能力列在一起，避免把“多一项能力”误读成“高一分”。")
tbl([
    ["能力", "Deep_PGGB", "PGGB"],
    ["任意有理倍率", "支持（如 160/147、2381/2100）", "仅整数倍率"],
    ["降采样", "支持", "无路径"],
    ["分块处理", "支持，块长 0.25–30 s", "支持"],
    ["流式 FIFO", "支持", "未提供"],
    ["输出电平", "保持输入幅度", "归一化至峰值 0.99"],
    ["44.1→88.2 速度", "117.7×", "30.0×"],
    ["最高零差", "303.8 dB", "302.0 dB"],
], "表 3  能力对照，不是排名。PGGB 的整数倍率限制会把 44.1→48 kHz 静默输出为 4 倍样本（176400 而非 192000）；"
   "其峰值归一化也会使固定分母的镜像读数偏高 6 dB。",
   widths=[150, 210, 170])
p("本文不把 117.7× 对 30.0× 的速度差当作算法优越性的证据。两者的实现语言、FFT 后端与并行策略都不同；"
  "可比的是同一协议下的量级。反过来，Deep_PGGB 的 22.049 kHz 通带保持也不是无条件的：它只在升采样方向成立，"
  "降采样方向用 200 Hz 滚降换混叠，两者必须一起读。")

h2("5.2  测量即结论的一部分")
p("在 −300 dBc 量级，测量协议是结果的一部分。本文的三次误判都来自口径：把泄漏裙边当杂散、把除以零当抑制、"
  "把闭式增益当无偏估计。每一次误判都朝着“看起来合理”的方向，而且都抬高了错误的引擎。"
  "可复现的做法是把地板、灵敏度、激励长度与聚合方式一起报告，而不是只报一个最好看的数字。")
p("同样的谨慎适用于跨引擎比较[13]。表 2 中 r8brain 的杂散比 Deep_PGGB 高 20 dB，但它的 CCIF 为 −334.5 dBc，"
  "与地板齐平；sox_ng 的 CCIF 只有 −202.3 dBc，却在 21.9 kHz 保留了 −15.9 dB 的通带。"
  "一台引擎的“好坏”取决于用它做什么，单一排序会把这种结构抹平。")

h2("5.3  局限")
p("第一，降采样方向默认让出 200 Hz 通带，这是为混叠抑制付的价；可以用更窄的滚降换回带宽，但混叠会上升。"
  "第二，源奈奎斯特 100 Hz 以内的零差崩塌（21.9 kHz 为 136.2 dB，22 kHz 为 58.5 dB）由文件边界决定，"
  "任何渐变窗都无法消除，PGGB 同量级；这不是算法缺陷。第三，商业工具（Weiss Saracon、iZotope RX、HQPlayer）"
  "没有可驱动的内核，本文无法把它们纳入对照。第四，流式路径的算法时延至少为核心长度加一个上下文，"
  "对实时监听需要更短的上下文，代价是混叠抑制下降。")

# ------------------------------------------------------------------ 6
h1("6  结论")
p("本文把分块频域重采样在任意有理倍率下的误差来源收敛到三个可分别处理的因素：频域网格的对齐、块接缝的相位、"
  "文件边界的连续性阶数。前两个由 P=M·s、Q=L·s 与 M 的整数倍步进解决，第三个由 C5 渐变窗解决。"
  "三者合起来把九种倍率的零差推到 300.9–303.8 dB，与 PGGB 的 302.0 dB 处于同一地板。"
  "流式 FIFO 把这个结果从离线整文件扩展到连续流：稳态零差 296–303 dB，长度零漂移，"
  "唯一差异是前 20 ms 的头部约定。八引擎对照表明，其余六台的杂散都明显高于地板（r8brain 高 23 dB，其余高 100 dB 以上）；"
  "Deep_PGGB 与 PGGB 的差异则落在测量重复性以内。")
p("当精度进入 −300 dBc，继续压低单个数字的收益有限；更有价值的是把测量协议、地板与灵敏度一起固定下来，"
  "使不同引擎的差异可以被复现地讨论。本文的代码与数据随 SonarSRC 项目发布，测量脚本可以重跑。")

# ------------------------------------------------------------------ 参考
pb()
h1("参考文献")
ref("[1] Oetken G. A new approach for the design of digital interpolating filters. IEEE Trans. Acoust., Speech, Signal Process., 1979, 27(6): 637–643.")
ref("[2] Crochiere R E, Rabiner L R. Interpolation and decimation of digital signals—a tutorial review. Proc. IEEE, 1981, 69(3): 300–331.")
ref("[3] Virtanen P, Gommers R, Oliphant T E, et al. SciPy 1.0: fundamental algorithms for scientific computing in Python. Nature Methods, 2020, 17: 261–272.")
ref("[4] Smith J O, Gossett P. A flexible sampling-rate conversion method. Proc. ICASSP, 1984: 19.4.1–19.4.4.")
ref("[5] Frigo M, Johnson S G. The design and implementation of FFTW3. Proceedings of the IEEE, 2005, 93(2): 216–231.")
ref("[6] AES. AES17-2015: AES standard method for digital audio engineering—measurement of digital audio equipment. 2015.")
ref("[7] Zölzer U. DAFX: Digital Audio Effects. 2nd ed. Chichester: Wiley, 2011.")
ref("[8] sox_ng project. sox_ng: a maintained fork of SoX. https://codeberg.org/sox_ng/sox_ng, 2025.")
ref("[9] libsoxr. The SoX Resampler library. https://sourceforge.net/projects/soxr/, 2024.")
ref("[10] Avaneev A. r8brain-free-src. https://github.com/avaneev/r8brain-free-src, 2024.")
ref("[11] Shibata N. SSRC—a high-quality sampling rate converter. http://shibatch.sourceforge.net/, 2006.")
ref("[12] PGGB. Perfectly Gentle Great Bands. https://www.remastero.com/pggb.html, 2024.")
ref("[13] Infinite Wave. SRC comparisons. https://src.infinitewave.ca/, 2024.")
ref("[14] Oppenheim A V, Schafer R W. Discrete-Time Signal Processing. 3rd ed. Pearson, 2010.")
ref("[15] Harris F J. On the use of windows for harmonic analysis with the discrete Fourier transform. Proceedings of the IEEE, 1978, 66(1): 51–83.")

import json
_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blocks.json")
with open(_out, "w", encoding="utf-8", newline="\n") as f:
    json.dump(B, f, ensure_ascii=False, indent=1)
print(len(B), "blocks,", sum(len(b.get("x", "")) for b in B), "chars")
