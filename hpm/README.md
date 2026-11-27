# 分支 C · 高精度 / 任意精度音频测量（HPM）

> 本目录是研究分支 C 的实现与文档。分支 A（算法与论文）在 `deeppggb/`，分支 B（SRC 工具箱）在
> `srctool/` + `app.py`，三者的总览见根目录 `README.md`。

## 这个分支在问什么

音频测量的「地板」到底由什么决定？行业最好的模拟分析仪（Audio Precision APx555）残余 THD+N 是
−120 dB；deep_pggb 的 double 引擎能读到 −307 dBc；128 位版本读到 −665 dB。这三个数量级之间，
**是算术精度在起作用，还是分析窗在起作用，还是被测设备本身？**

分支 C 的答案是把地板拆成一条**五级级联**（激励定义 / 输入表示 / 引擎算术 / 输出表示 / 分析器），
逐级测量，并把分析器做成一把**会自报家门**的尺子：每次测量同时给出可证下界、它自己的地板、
以及这次读数属于文件还是属于尺子。

## 当前结论（2026-11-28）

1. **精度律 6.02 dB/bit 成立到 23032 dB**。Arb 球算术 + 完整正规方程：60/240/960/3840 bit →
   276.8/1360.5/5695.3/23032.2 dB（`experiments/run_arb.py`，证书值，不是估计值）。
   同精度下比 mpmath 快 15–20 倍。
2. **可证地板有结构**（二次律，26 点，max 残差 1.84 dB）：

       null = 6.0199·p − 4.4941·L − 0.0583·L² − 10.44 dB，  L = log2 N

   N 每翻倍掉 5.7 dB（N=1k）到 6.9 dB（N=1.4M）—— **长文件要多买精度**，这不是速度问题。
   尺子律同形恒高 3.0 dB。
3. **经典「频谱泄漏」是估计器的假象**。同一段非相干数据（1000.5 Hz，4096 点）：单 bin 投影恒在
   71.9 dB，加多少位都不动；解完整的 2×2 正规方程，地板与相干情形逐位相同。
   **相干采样不是必要条件。**
4. **窗当权重是中性的，当变换是灾难性的**（`run_window.py`，1000.5 Hz 非相干、N=4096）：
   七种窗加权最小二乘在 60/240/480 bit 下都读 286→2815 dB（相差 < 2 dB）；同一批窗的单 bin
   投影恒在 **7.0–32.8 dB**，加多少位都不动。**泄漏属于估计器，不属于数据。**
   DPSS 泄漏上界表见 `python -m hpm.arb.dpss_table`。
5. **未知频率也能带证书**：LP 初值 + 高斯牛顿，600 bit 下证书 ≥3404 dB，频率相对不确定度 1e−174。
   代价是牛顿每步把球半径放大约 17–35 倍（证书每步 −25…−30 dB）。
6. **多音可整表证书**（`run_multitone.py`）：四音 1001/6997/13003/18997 Hz、幅度不等，过已知三次
   非线性，a₃=1e−3/1e−5/1e−7 时 58 个三阶产物**逐项**与复数展开的解析值吻合到 0.00 dB；
   电平按 a₃ 精确每十倍降 20 dB。**排序（-2f1+f2 三个排列、3f1 一个排列）是电平差 9.54 dB 的
   来源**——把排列折叠掉的计数会把三次谐波算错 6.02 dB，看起来像测量缺陷。
   纯三次非线性不产生偶次产物；双音 f₂−f₁ 读 −702.75 dBc 是量化噪声，不是失真。
7. **五级级联在 665.5 dB 处被验证**：binary128 的 deep_pggb 引擎跑 16 s/44.1→88.2，Arb 分析器
   给出 665.522 dB，与 C++ quad 分析器一致，尺子 2279.7 dB。140 bit 起饱和。
   **这个数不是格式的上限**：同一 binary128 格式装合成激励能读 689.45 dB，24 dB 的缺口属于引擎。
8. **缺口已经定位并修掉**：不是 FFT 舍入、不是分析器、不是最小相位滤波器，而是变换前后两个乘法窗的
   **阶数**。默认 5 阶时窗的旁瓣落进输出带内，把读数按在 440.2 dB；改成 12 阶（长度仍是 20 ms）
   就升到 665.3 dB，**+225 dB，机时不变**。天花板 666 dB 是四精度变换链自己的算术上限
   （r2c→c2r 往返 666.04 dB）。剩下的 24 dB 来自高频：19 kHz 只有 449.7 dB。
9. **同一个信号，读数由存法决定**：引擎输出存成 binary128 665.522 / float64 328.091 /
   float32 153.822 / PCM24 140.662 / PCM16 92.701 dB。注意最高一级仍是引擎的地板而不是格式的地板；
   把理想激励直接舍入成五种格式才是格式阶梯（689.45/328.27/153.70/140.20/92.07，跨度 597.4 dB）。
10. **模型必须含直流**。漏掉 DC 列会让一段有偏置的量化信号少读 6.3 dB（PCM24 读成 134.332 而非
   140.662）。任何「残差 = 数据 − 模型」的证书，模型漏一项就等于给被测对象减分。
11. **墙钟不是正比于精度**：`µs/样本/遍 = 6.34 + 0.0131·bits`（f128 输入）。94 bit 时 69% 的时间
    花在与精度无关的解码与三角函数上。

## 怎么用（命令行）

```bash
# 这个文件的可证零差是多少？不知道精度该给多少就加 --auto
python -m hpm.arb.certify null out.f128 --fs 88200 --f 1000 --skip 0.8 --tail 0.8 --auto

# 双音互调，一次读七个产物频率
python -m hpm.arb.certify imd out.f128 --fs 44100 --f1 19000 --f2 20000

# 想要 440 dB，要多少位、多少秒？
python -m hpm.arb.certify predict --db 440 --N 1270080 --f 1000

# 想要 −120 dB 泄漏，DPSS 的 NW 取多少？
python -m hpm.arb.dpss_table
```

每次 `null` 都会打印四行：读数（可证下界 + 中点）、残差 rms、尺子的地板、以及 `regime` ——
`file-limited`（这个数属于文件）还是 `ruler-limited`（加 `--bits` 再读）。

## 目录

```
hpm/
├─ README.md                 本文件
├─ arb/                      球算术测量库（python-flint 0.9.0 的 Arb 绑定）
│  ├─ f128.py                binary128 编解码（IEEE 字节序，精确、无舍入）
│  ├─ mcore.py               单音/多音最小二乘、证书、高斯牛顿、精确整数相位基
│  ├─ dpss.py                DPSS：Sturm 二分 + 逆迭代 + 核 Rayleigh 商（泄漏上界）
│  ├─ measure.py             流式证书测量（f128/f64/wav）、DC 列、饱和扫描、Lipschitz 界
│  ├─ advisor.py             二次精度律、反解、损耗预算、仿射墙钟模型
│  ├─ certify.py             命令行：null / imd / predict
│  └─ dpss_table.py          N×NW 泄漏上界网格与 nw_for()
├─ experiments/              实验脚本（run_*.py）与结果（results_*.json）
│  ├─ floor_law.py           第一版（mpmath）：标度律、泄漏是估计器假象
│  ├─ make_fixtures.py       生成/校验全部夹具（--check 重造并逐样本比对）
│  ├─ run_window.py          窗当权重 vs 当变换 → results_window.json
│  ├─ run_multitone.py       四音三阶产物整表 → results_multitone.json
│  ├─ run_law_ext.py         律在 3840 bit / 5.6M 上的外推验证 → results_law_ext.json
│  ├─ run_arb.py             路线图 1/2/3/5，写 results_arb.json
│  ├─ run_engine.py          路线图 4：引擎 dump → Arb 证书，写 results_engine.json
│  ├─ run_law.py             二次证书律拟合 → results_law.json
│  ├─ run_ruler.py           尺子律 → results_ruler.json（run_ruler_big.py 到大 N）
│  ├─ run_advisor_law.py     反解律（bits_for 的标定）→ results_advisor.json
│  ├─ run_validate.py        顾问验证 + 墙钟标定 → results_validate2.json
│  ├─ run_ladder.py          表示阶梯（五种存法）→ results_ladder.json
│  ├─ run_saturation.py      饱和扫描 → results_saturation.json
│  ├─ run_minsolve.py        求解精度下限（Gram 奇异在哪）
│  ├─ run_wallcal.py         墙钟标定（仿射模型的两个常数）
│  ├─ run_guard.py / run_phasebasis.py / run_lipschitz.py / run_gaplaw.py / run_budget.py
│  ├─ fig_roadmap.py         出图 reports/figs/roadmap_1_5.png
│  └─ fig_budget.py          出图 reports/figs/budget_1_5.png
└─ reports/
   ├─ 2026-11-25-arbitrary-precision-audio-measurement.md   综述 + 理论 + 实验 + 创新点
   ├─ 2026-11-26-certified-measurement-roadmap.md           路线图 1–5 交付报告
   ├─ 2026-11-26-certified-measurement-tooling.md           工具链与精度律（本轮）
   ├─ figs/roadmap_1_5.png, figs/budget_1_5.png
   └─ float128/                                             分支 C 的第一份报告
      ├─ Deep_PGGB_float128_report.md/.docx/.pdf
      ├─ float128_report.univer
      ├─ md2docx.py / pdfshot.py
      └─ raw_measure.log
```

## 论文

当前稿是 `work/paper_cert/certified_null_paper.docx` / `.pdf`（23 页、6 图、13 表、14 式、16 篇文献），
题名《可证零差：任意精度音频测量的地板归属与精度预算》。源是 `work/paper_cert/paper_a.md`（标题与 §1–4）
和 `paper_b.md`（§5–11 与附录），图由 `hpm/experiments/fig_paper2.py` 生成，构建链是
`build_paper.py`（python-docx 直出，`add_picture` 内联图）→ `_wordcheck.py`（Word COM 开档验证 + 导 PDF）
→ `_raster.py`（pymupdf 逐页光栅化目视）。旧稿 `work/paper_hpm/` 保留作历史，其 `embed.py` 写出的
DrawingML 缺命名空间声明，Word 打不开，不要复用。

## 下一步

1. 投稿前还差三件：跨实现的残差散布（目前每个读数来自一次 realization）、把 3 dB 的三角不等式
   缺口换成真正的上界、以及把保护位平台的 −30.5 dB 在 360/480 bit 上单独拆一遍（现在只有
   120/240 两点）。
2. 引擎那 249 dB 的缺口尚未定位到内核：需要算术、算法窗、块边界三部分的对照实验。
3. 真实音乐与非平稳内容的块间误差不能从合成单音外推，缺一段音乐口径的对照。
