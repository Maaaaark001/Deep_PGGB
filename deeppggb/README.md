# 分支 A · Deep_PGGB 引擎与论文

> 本项目三分支之一。总览见根目录 [README.md](../README.md)，分支 C 见 [hpm/README.md](../hpm/README.md)。

## 是什么

**Deep_PGGB** 是一个任意有理倍率的分块频域采样率转换引擎：16 s 块、800 ms 上下文、
20 ms 块边渐变（12 阶 smootherstep）、200 Hz 滚降、FFTW 复数变换、块级并行。
它把"砖墙滤波 + 分块 + 渐变"三件事的取舍写成了可测的参数，并用论文的口径（16 s 整数相位激励、
泄漏免疫残差、带能量镜像、双音混叠、7 轮交错速度）与八台引擎对照。

## 代码入口

| 路径 | 作用 |
|---|---|
| `src/dpggb_core.cpp` | 引擎核心：分块、渐变、FFTW、plan/buffer 复用、量化 |
| `src/dpggb.h` | C API：`resample`、`resample_channel`、`resample_channel_q`（binary128） |
| `src/quad_fft.h` | 四精度混合基 FFT（FFTW 没有 quad 变换时使用） |
| `src/dpggb_q_cli.cpp` + `build_quad.sh` | `dpggb128.exe`：f128 文件前端（`-DDPGGB_QUAD`，默认不编） |
| `deeppggb.py` / `deeppggb_stream.py` | Python 绑定与流式 API |
| `dp_paper_metrics.py` / `dp_sinad.py` / `dp_speed_ci.py` | 论文口径的测量脚本 |
| `build_paper_*.py` → `merge.sh` → `build.sh` → `build_docx.py` | 论文管线（`work/paper/`） |
| `dp_quad_probe.cpp` | 四精度测量探针（分支 C 的第一把尺子，暂放此处） |

## 构建

```bash
cd deeppggb && bash build.sh        # dpggb.dll + dpggb.exe（依赖 third_party 里的 FFTW）
bash build_quad.sh                  # 可选：dpggb128.exe + dp_quad_probe.exe（需 libquadmath）
```

## 当前状态

- 论文：25 页、10 图、6 表，`work/paper/Deep_PGGB_paper.docx` / `.pdf`。
- 精度：double 零差 ≈ 307 dB（float64 表示极限）；binary128 版本 **665.5 dB**，距 binary128 格式地板
  689.6 dB 只差 24 dB，且已贴住四精度变换链自身的算术上限 666 dB。
- 速度：60 s 立体声 44.1→88.2 约 180–200×（同会话交错口径）。

## 渐变阶数是精度旋钮（2026-11-28）

四精度路径的零差曾被默认参数压在 440.2 dB，远低于 binary128 格式地板 689.6 dB。原因不是 FFT 舍入、
不是分析器，也不是最小相位滤波器（`cfg.phase` 默认 `PHASE_LINEAR`，那段代码根本不执行），
而是变换前后两个乘法窗的**阶数**：窗的旁瓣与信号卷积后落进输出带内，把读数按住。

16 s、1 kHz、44.1→88.2、binary128、两个渐变都保持 20 ms 时，只改阶数：

| 阶数 | 5 | 6 | 7 | 8 | 10 | 12 |
|---|---:|---:|---:|---:|---:|---:|
| 零差 (dB) | 440.2 | 451.2 | 516.5 | 528.4 | 601.7 | **665.3** |

把两个渐变都拉长到 600 ms 但用 6 阶只有 657.5 dB——**阶数比长度划算**（长度按 dB/ms 线性买，
阶数按旁瓣衰减指数买）。长度又不能为零：文件渐变取 0 时塌到 139.5 dB。因此
`Cfg::taper_shape` 的默认值从 `TAPER_SMOOTH5` 改为 `TAPER_SMOOTH12`，长度不变，
四精度读数 +225 dB 且机时不变。

天花板是 666 dB，即四精度变换链自身的算术上限（同尺寸 r2c→c2r 往返 666.04 dB，
r2c@705600 → c2r@1411200 的真实块路径 665.26 dB），所以 665.5 dB 已经贴住它。
剩下的 24 dB 来自高频：19 kHz 单音只有 449.7 dB，因为块渐变的调制边带离输出奈奎斯特只有 3 kHz，
加长渐变（100/200/400 ms 都读 453.26 dB）救不了。float64 路径同受益：19 kHz 从 293.3 升到 306.5 dB。

```bash
# 复现：quad 路径，默认参数（阶数已改为 12）
cd deeppggb && ./dp_quad_probe.exe null 2 16 1000 16 0 20 12 800 44100 88200 0.05
# 对照：5 阶（旧默认）
DPQ_FADE=20 ./dp_quad_probe.exe null 2 16 1000 16 0 20 5 800 44100 88200 0.05
# 算术上限：同尺寸往返 / 真实块路径
./dp_quad_probe.exe rt 16 44100
./dp_quad_probe.exe rt2 705600 1411200 44100
```

## 约定

- 改分段文件后必须跑 `merge.sh`，只跑 `build.sh` 等于什么都没改。
- 测量口径以根 `AGENTS.md` §D6 为准；跨会话速度差 ±20%，只能同会话交错比较。
- `dp_paper_data.py` 没有 main guard，import 会重跑基准并覆盖 `work/paper_data.json`。
