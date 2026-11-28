# work/ · 产出物索引

这里只放**产出物**（论文、图、基准数据、报告），代码在 `deeppggb/`、`srctool/`、`hpm/`。
按分支对应关系：

| 路径 | 分支 | 内容 |
|---|---|---|
| `paper/` | A | 论文源（`build_paper_*.py` 的分段文件）、`Deep_PGGB_paper.docx/.pdf`、`blocks.json` |
| `figures/` | A | 论文图（`dp_figures.py` / `dp_fig_sinad.py` 生成） |
| `paper_data.json`、`sinad_profile.json`、`passband_all.json`、`engine_music_8ch.json`、`stream_engines.json` | A | 论文口径的基准数据 |
| `shots/` | B | 工具箱界面截图 |
| `bench_opt/` 等临时目录 | B | 引擎对比的中间数据 |
| `paper_hpm/` | C | 旧稿《可证失真测量》的源与产物（`paper_a.md`/`paper_b.md`、`build_paper.py`/`embed.py`/`pdfshot.py`、`certified_measurement_paper.docx/.pdf`）。**已被 `paper_cert/` 取代**，仅作历史留存；其 `embed.py` 产出的 docx 在 Word 中打不开（DrawingML 命名空间缺声明），不要复用 |
| `paper_cert/` | C | 新稿《可证零差》的源（`paper_a.md` 标题+§1–4、`paper_b.md` §5–11+附录）、`build_paper.py`（python-docx 直出，图用 `add_picture`）、`_wordcheck.py`（Word COM 开档 + 导 PDF）、`_raster.py`（pymupdf 光栅化）、`certified_null_paper.docx/.pdf`（25 页、6 图、14 表、15 式、16 篇文献）、`figures/`（6 图，由 `hpm/experiments/fig_paper2.py` 生成） |
| `float128_report.univer` | C | 已被 Univer 进程占用，暂时留在原地；正文副本在 `hpm/reports/float128/` |

> 分支 C 的新报告直接写在 `hpm/reports/`，不再进 `work/`。
