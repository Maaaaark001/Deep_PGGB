
# ------------------------------------------------------------------ 6
h1("6  讨论")
h2("6.1  与 PGGB 的关系")
p("Deep_PGGB 与 PGGB 属于同一类算法：频域、砖墙、float64、分块。两者的零差在 0.6 dB 内一致，说明它们都碰到了同一块地板。差别在能力边界：在本工具箱的调用方式下，PGGB 只接受整数倍率，请求 44.1→48 kHz 时会输出 176400 个样本而不是 192000，且不报错；它没有降采样路径，输出峰值归一化到 0.99。这些差异属于适用场景，不构成精度高下；表 5 把能力列在一起，避免把“多一项能力”误读成“高一分”。")
tbl([
    ["能力", "Deep_PGGB", "PGGB"],
    ["任意有理倍率", "支持（如 160/147、2381/2100）", "仅整数倍率"],
    ["降采样", "支持", "无路径"],
    ["分块处理", "支持，块长 0.25–30 s", "支持"],
    ["流式 FIFO", "支持", "未提供"],
    ["输出电平", "保持输入幅度", "归一化至峰值 0.99"],
    ["44.1→88.2 速度", "180×", "43.2×"],
    ["最高零差", "303.8 dB", "302.0 dB"],
], "表 5  能力对照，不是排名。PGGB 的整数倍率限制会把 44.1→48 kHz 静默输出为 4 倍样本（176400 而非 192000）；其峰值归一化也会使固定分母的镜像读数偏高 6 dB。",
   widths=[150, 210, 170])
p("本文不把 180× 对 43.2× 的速度差当作算法优越性的证据。两者的实现语言、FFT 后端与并行策略都不同，可比的是同一协议下的量级。反过来，Deep_PGGB 的 22.049 kHz 通带保持也不是无条件的——它只在升采样方向成立，降采样方向用 200 Hz 滚降换混叠，两者必须一起读。")

h2("6.2  何时 300 dB 有意义")
p("24 bit PCM 的理论信噪比约为 146 dB，32 bit 浮点的有效动态范围约为 150 dB[10]；−300 dBc 比可听域低 150 dB 以上，对播放与母带处理没有直接意义。它的价值在三个场景。数值正确性：当算法在 float64 下达到舍入地板，说明误差来自浮点而非算法结构，后续优化不会以精度为代价。测量工具：测试信号生成、器件建模与级联验证中，重采样器本身不应成为误差源，−300 dBc 为这些应用留出 150 dB 的余量。跨引擎比较：只有地板足够低，才能把 r8brain 的 −284 dBc 与 sox_ng 的 −187 dBc 区分为算法差异，而非测量噪声。")
p("因此，本文不主张“零差越高越好”。在 24 bit 交付链中，−180 dBc 的引擎已经足够；本文主张的是，当研究或验证需要更低的地板时，应当同时报告协议、地板与灵敏度，而不是只报一个数字。")

h2("6.3  测量即结论的一部分")
p("在 −300 dBc 量级，测量协议是结果的一部分。四类口径会带来系统性偏差：把泄漏裙边当杂散、把除以零当抑制、把闭式增益当无偏估计、把全文件增益当全局增益。它们的共同点是把误差推向“看起来合理”的方向，并抬高错误的引擎。可复现的做法是把地板、灵敏度、激励长度与聚合方式一起报告。")
p("同样的谨慎适用于跨引擎比较。表 3 中 r8brain 的杂散比 Deep_PGGB 高 20 dB，但它的 CCIF 为 −334.5 dBc，与地板齐平；sox_ng 的 CCIF 只有 −202.3 dBc，却在 21.9 kHz 保留了 −15.9 dB 的通带。一台引擎的“好坏”取决于用它做什么，单一排序会把这种结构抹平。")

h2("6.4  局限")
p("降采样方向默认让出 200 Hz 通带，这是为混叠抑制付的价；可以用更窄的滚降换回带宽，但混叠会上升。源奈奎斯特 100 Hz 以内的零差崩塌（21.9 kHz 为 136.2 dB，22 kHz 为 58.5 dB）由文件边界决定，任何渐变窗都无法消除，PGGB 同量级；这不是算法缺陷。商业工具（Weiss Saracon、iZotope RX、HQPlayer）没有可驱动的内核，本文无法把它们纳入对照。")
p("流式路径的算法时延至少为核心区加一个上下文，实时监听需要更短的上下文，代价是混叠抑制下降。除 §5.7 的一段 2 分钟 Pixabay 立体声音乐外，其余激励为合成正弦与正弦和；未做听感测试，因为真实音乐上的分块-整段零差已低至 175 dB（相对该引擎自己的整段输出），远低于听感测试的分辨率。§5.7 的八声道只测了单流离线与单流引擎内路径，多流并发、真实多声道素材与房间格式仍未覆盖。速度数据来自单机、三次取优，跨平台结论需要重新测量。")

# ------------------------------------------------------------------ 7
h1("7  结论")
p("本文把分块频域重采样在任意有理倍率下的误差收敛到四个可分别处理的环节：频域网格、块接缝、文件边界与浮点舍入。前两个由 P=M·s、Q=L·s 与 M 的整数倍步进解决，第三个由 20 ms 五次 smootherstep 窗解决，第四个构成测量地板。四者合起来把九种倍率的零差推到 300.9–303.8 dB，与 PGGB 的 302.0 dB 处于同一地板。")
p("流式 FIFO 把这个结果从离线整文件扩展到连续流：稳态零差 296–303 dB，长度零漂移，唯一差异是前 20 ms 的头部约定。八引擎对照表明，其余六台的杂散都明显高于地板（r8brain 高 23 dB，其余高 100 dB 以上）；Deep_PGGB 与 PGGB 的差异则落在测量重复性以内。把同一批输出折算成 SINAD、SFDR 与 ENOB，这个分层更清楚：20 kHz 以内六台引擎落在 307–311 dB（51.8–52.4 bit），即双精度的有效位数上限；它们的差距全部来自 22.05–44.1 kHz 的镜像区，sox_ng 与 SSRC 是唯一的例外，带内就只有 187.7 dB 与 153.3 dB。")
p("真实素材与多声道给出这条结论的边界。2 分钟立体声音乐上，引擎内 16 s 分块相对 120 s 整段输出的零差为 175.2 dB；它比合成单音低 130 dB，但仍比 24 bit 的 146 dB 指标高 29 dB。八声道逐通道零差为 303.9–305.8 dB，通道间逐位无泄漏；60 s 离线吞吐 41.4×，引擎内流式 7.6×/1.8 s，说明通道扩展同样有代价。")
p("需要明确本文的边界。本文不提出新的插值核；其贡献在于把已知的频域补零方法在任意有理倍率下组织成可分解、可测量、可流式化的形式，并给出该形式在 float64 地板上的行为。当精度进入 −300 dBc，继续压低单个数字的收益有限；更有价值的是把测量协议、地板与灵敏度一起固定下来，使不同引擎的差异可以被复现地讨论。")
p("后续工作包括把上下文与核心区同时压到 100 ms 以支持硬实时、在真实音乐素材与多声道链路上验证，以及把该协议用于 DAC、ADC 与插件链的级联测量。")

p("**数据与代码可用性**：测量脚本、原始读数（work/*.json）与图表生成脚本可向通讯作者（maaaaark@163.com）索取；复现环境与命令见附录 A。")
p("**利益冲突**：作者声明不存在利益冲突。")

# ------------------------------------------------------------------ 附录
h1("附录 A  复现环境与数据")
p("实验环境：Intel Core i5-7500T（4 核 4 线程，12 GB），Windows 10 22H2（19045），Python 3.13.16，NumPy 2.5.1，SciPy 1.18.1，FFTW 3.3（双精度），MSYS2 UCRT64 g++ 16.2.0，编译选项 -O3 -std=c++20。")
p("测量脚本：deeppggb/dp_bench_all.py（失真）、dp_speed_882.py 与 dp_speed_ci.py（速度）、dp_passband_dense.py（通带）、dp_stream_data.py 与 dp_stream_bench.py（流式）、dp_spectrum_data.py（频谱）；原始读数写入 work/*.json。")
p("成图：work/figures/gen_figures_new.py 读 work/*.json 生成 PNG、PDF 与 SVG。排版：build_paper_1/2/3.py → merge.sh → build_docx.py → embed_figures.py → qa_docx.py。")

# ------------------------------------------------------------------ 参考
pb()
h1("参考文献")
ref("[1] Oetken G. A new approach for the design of digital interpolating filters. IEEE Trans. Acoust., Speech, Signal Process., 1979, 27(6): 637–643.")
ref("[2] Crochiere R E, Rabiner L R. Interpolation and decimation of digital signals—a tutorial review. Proc. IEEE, 1981, 69(3): 300–331.")
ref("[3] Smith J O, Gossett P. A flexible sampling-rate conversion method. Proc. ICASSP, 1984: 19.4.1–19.4.4.")
ref("[4] Oppenheim A V, Schafer R W. Discrete-Time Signal Processing. 3rd ed. Upper Saddle River: Pearson, 2010.")
ref("[5] Fraser D. Interpolation by the FFT revisited—an experimental investigation. IEEE Trans. Acoust., Speech, Signal Process., 1989, 37(5): 665–675.")
ref("[6] Frigo M, Johnson S G. The design and implementation of FFTW3. Proc. IEEE, 2005, 93(2): 216–231.")
ref("[7] Virtanen P, Gommers R, Oliphant T E, et al. SciPy 1.0: fundamental algorithms for scientific computing in Python. Nature Methods, 2020, 17: 261–272.")
ref("[8] Harris F J. On the use of windows for harmonic analysis with the discrete Fourier transform. Proc. IEEE, 1978, 66(1): 51–83.")
ref("[9] Nuttall A H. Some windows with very good sidelobe behavior. IEEE Trans. Acoust., Speech, Signal Process., 1981, 29(1): 84–91.")
ref("[10] Zölzer U. DAFX: Digital Audio Effects. 2nd ed. Chichester: Wiley, 2011.")
ref("[11] AES. AES17-2015: AES standard method for digital audio engineering—measurement of digital audio equipment. 2015.")
ref("[12] sox_ng project. sox_ng: a maintained fork of SoX. https://codeberg.org/sox_ng/sox_ng, 2025（访问日期：2026-11-24）.")
ref("[13] libsoxr. The SoX Resampler library. https://sourceforge.net/projects/soxr/, 2024（访问日期：2026-11-24）.")
ref("[14] Avaneev A. r8brain-free-src. https://github.com/avaneev/r8brain-free-src, 2024（访问日期：2026-11-24）.")
ref("[15] Shibata N. SSRC—a high-quality sampling rate converter. http://shibatch.sourceforge.net/, 2006（访问日期：2026-11-24）.")
ref("[16] PGGB. Perfectly Gentle Great Bands. https://www.remastero.com/pggb.html, 2024（访问日期：2026-11-24）.")
ref("[17] Infinite Wave. SRC comparisons. https://src.infinitewave.ca/, 2024（访问日期：2026-11-24）.")
ref("[18] Rabiner L R, Gold B. Theory and Application of Digital Signal Processing. Englewood Cliffs: Prentice-Hall, 1975.")
ref("[19] Bi G, Mitra S K. Sampling rate conversion in the frequency domain. IEEE Signal Process. Mag., 2011, 28(5): 140–144.")
ref("[20] Välimäki V, Bilbao S. Giant FFTs for sample-rate conversion. J. Audio Eng. Soc., 2023, 71(3): 88–99.")
ref("[21] Brückl S, Schönle M. Sample-rate conversion by the Giant FFT revisited—a theoretical and experimental investigation. J. Audio Eng. Soc., 2026. DOI: 10.17743/jaes.2026.0307.")
ref("[22] Salmi R, Välimäki V. Suppression of Nyquist ringing in FFT-based sample rate conversion. IEEE Signal Process. Lett., 2026. DOI: 10.1109/LSP.2026.3654546.")
ref("[23] Golub G H, Van Loan C F. Matrix Computations. 4th ed. Baltimore: Johns Hopkins University Press, 2013.")
ref("[24] IEC. IEC 60268-3:2018: Sound system equipment—Part 3: Amplifiers. Geneva: IEC, 2018.")
ref("[25] SMPTE. SMPTE RP 120:2000: Measurement of intermodulation distortion in audio systems. White Plains: SMPTE, 2000.")
ref("[26] IEEE. IEEE Std 1241-2010: IEEE standard for terminology and test methods for analog-to-digital converters. New York: IEEE, 2010.")

import json
import re

_refs = [b for b in B if b.get("t") == "ref"]
B[:] = [b for b in B if b.get("t") != "ref"]


def _nums(group):
    out = []
    for part in re.split(r"[,，、]", group):
        part = part.strip()
        m = re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", part)
        if m:
            out.extend(range(int(m.group(1)), int(m.group(2)) + 1))
        elif part.isdigit():
            out.append(int(part))
    return out


_order = []
for _b in B:
    for _m in re.finditer(r"\[([0-9][0-9\s,，、–-]*)\]", _b.get("x", "")):
        for _n in _nums(_m.group(1)):
            if _n not in _order:
                _order.append(_n)

_old_nums = sorted(int(re.match(r"\[(\d+)\]", b["x"]).group(1)) for b in _refs)
assert sorted(_order) == _old_nums, ("citations and refs differ", _order, _old_nums)
assert len(_order) == len(set(_order))

_map = {n: i + 1 for i, n in enumerate(_order)}


def _fix(m):
    ns = sorted({_map[n] for n in _nums(m.group(1))})
    parts = []
    i = 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        parts.append(str(ns[i]) if j == i else "%d–%d" % (ns[i], ns[j]))
        i = j + 1
    return "[" + ",".join(parts) + "]"


for _b in B:
    if "x" in _b:
        _b["x"] = re.sub(r"\[([0-9][0-9\s,，、–-]*)\]", _fix, _b["x"])

_by_old = {}
for _b in _refs:
    _m = re.match(r"\[(\d+)\]\s*(.*)", _b["x"], re.S)
    _by_old[int(_m.group(1))] = _m.group(2)
for _new in range(1, len(_refs) + 1):
    _old = _order[_new - 1]
    B.append({"t": "ref", "x": "[%d] %s" % (_new, _by_old[_old])})

_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blocks.json")
with open(_out, "w", encoding="utf-8", newline="\n") as f:
    json.dump(B, f, ensure_ascii=False, indent=1)
print(len(B), "blocks,", sum(len(b.get("x", "")) for b in B), "chars")
