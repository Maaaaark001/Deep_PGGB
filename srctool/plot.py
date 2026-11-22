"""ECharts 图表构建：把 metrics/quality 的输出翻译成 option dict。

为什么用 ECharts 而不是 matplotlib/Pillow：
  * 交互（缩放、hover 读数、图例开关）是分析工具的核心体验，静态图给不了；
  * 与 UI 共用同一套 CSS 变量配色，深/浅主题切换零成本；
  * 不引入新依赖 —— NiceGUI 自带 ECharts。

约定：所有函数只做纯数据变换，不碰 UI，便于单测与复用。
"""
from __future__ import annotations

import math

# 配色：与 ui/theme.py 的 CSS 变量保持一致（theme 从这里 import，避免循环依赖）
PALETTE = {
    "signal": "#0F7B74",      # 主信号色（深青）
    "signal_dim": "#7FB8B3",
    "ref": "#8A6A2F",         # 参考曲线（赭石）
    "warn": "#B4761A",
    "bad": "#A33A2E",
    "ok": "#2F7D4F",
    "ink": "#1B201E",
    "muted": "#5C6660",
    "grid": "#C6CCC4",
    "panel": "#F7F8F5",
}

FONT_NUM = "Consolas, 'Cascadia Mono', monospace"
FONT_UI = "Bahnschrift, 'Segoe UI', 'Microsoft YaHei', sans-serif"


def _base(title: str = "", *, dark: bool = False) -> dict:
    ink = "#E6EAE4" if dark else PALETTE["ink"]
    muted = "#9AA5A0" if dark else PALETTE["muted"]
    grid = "#2C3438" if dark else PALETTE["grid"]
    return {
        "backgroundColor": "transparent",
        "animationDuration": 320,
        "textStyle": {"fontFamily": FONT_UI, "color": ink, "fontSize": 11},
        "title": ({"text": title, "left": 0, "top": 0,
                   "textStyle": {"fontSize": 12, "fontWeight": "normal", "color": muted}}
                  if title else {}),
        "grid": {"left": 52, "right": 18, "top": 34 if title else 18, "bottom": 34},
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": "#1B201E" if not dark else "#0E1214",
            "borderWidth": 0,
            "textStyle": {"color": "#F2F4F0", "fontSize": 11, "fontFamily": FONT_NUM},
        },
        "_axis": {"ink": ink, "muted": muted, "grid": grid},
    }


def _apply_axes(opt: dict, *, xname: str = "", yname: str = "") -> dict:
    a = opt.pop("_axis")
    axis_common = {
        "axisLine": {"lineStyle": {"color": a["grid"]}},
        "axisTick": {"show": False},
        "axisLabel": {"color": a["muted"], "fontSize": 10, "fontFamily": FONT_NUM},
        "splitLine": {"lineStyle": {"color": a["grid"], "opacity": 0.45}},
        "nameTextStyle": {"color": a["muted"], "fontSize": 10},
    }
    # 用 update 合并而不是 dict(..., **x)：调用方自带的 xAxis 里可能已经有 name，
    # 直接展开会抛 "dict() got multiple values for keyword argument 'name'"。
    x = {**axis_common, "name": xname, "nameLocation": "middle", "nameGap": 24}
    x.update(opt.get("xAxis") or {})
    opt["xAxis"] = x
    y = {**axis_common, "name": yname, "nameLocation": "middle", "nameGap": 42}
    y.update(opt.get("yAxis") or {})
    opt["yAxis"] = y
    if opt.get("title") is None:
        opt.pop("title", None)
    return opt


# --------------------------------------------------------------------------
# 频谱
# --------------------------------------------------------------------------
def spectrum_option(curves: list[dict], labels: list[str] | None = None,
                    *, title: str = "", dark: bool = False,
                    fmin: float = 20.0, floor_db: float = -140.0) -> dict:
    """多条频谱叠加（典型用法：输入 vs 输出，直接看出高频被削掉多少）。"""
    labels = labels or [f"曲线 {i + 1}" for i in range(len(curves))]
    colors = [PALETTE["ref"], PALETTE["signal"], PALETTE["warn"], PALETTE["bad"]]
    opt = _base(title, dark=dark)
    series = []
    for i, c in enumerate(curves):
        freq, db = c.get("freq") or [], c.get("db") or []
        pts = [[float(f), max(float(d), floor_db)] for f, d in zip(freq, db) if f >= fmin]
        series.append({
            "name": labels[i] if i < len(labels) else f"曲线 {i + 1}",
            "type": "line",
            "showSymbol": False,
            "smooth": False,
            "sampling": "lttb",
            "lineStyle": {"width": 1.4, "color": colors[i % len(colors)],
                          "type": "solid" if i == 0 else "dashed", "opacity": 1 if i == 0 else .95},
            "itemStyle": {"color": colors[i % len(colors)]},
            "areaStyle": None,
            "data": pts,
        })
    opt["xAxis"] = {"type": "log", "min": fmin, "max": max(
        [c.get("fmax", 24000) for c in curves] or [24000])}
    opt["yAxis"] = {"type": "value", "min": floor_db, "max": 6}
    opt["series"] = series
    opt["legend"] = {"right": 0, "top": 0, "textStyle": {"color": opt["_axis"]["muted"],
                                                         "fontSize": 10}}
    opt["tooltip"]["valueFormatter"] = None
    return _apply_axes(opt, xname="Hz", yname="dB")


# --------------------------------------------------------------------------
# 频谱图（热力图）
# --------------------------------------------------------------------------
def spectrogram_option(sg: dict, *, duration: float = 0.0,
                       title: str = "", dark: bool = False) -> dict:
    data = sg.get("data") or []
    if not data:
        return {}
    ncol = max(int(p[0]) for p in data) + 1
    nrow = max(int(p[1]) for p in data) + 1
    fmax = float(sg.get("fmax") or 0.0) or 1.0
    dur = duration or float(ncol)
    xs = [f"{dur * i / max(1, ncol - 1):.2f}" for i in range(ncol)]
    ys = [f"{fmax * j / max(1, nrow - 1) / 1000:.1f}" for j in range(nrow)]
    opt = _base(title, dark=dark)
    opt["grid"] = {"left": 52, "right": 74, "top": 34 if title else 18, "bottom": 34}
    opt["tooltip"] = {"trigger": "item", "backgroundColor": "#1B201E", "borderWidth": 0,
                      "textStyle": {"color": "#F2F4F0", "fontSize": 11, "fontFamily": FONT_NUM},
                      "formatter": "{b}"}
    opt["xAxis"] = {"type": "category", "data": xs, "splitArea": {"show": False}}
    opt["yAxis"] = {"type": "category", "data": ys}
    opt["visualMap"] = {
        "min": -90, "max": 0, "calculable": False, "orient": "vertical",
        "right": 0, "top": "center", "itemHeight": 120, "itemWidth": 10,
        "textStyle": {"color": opt["_axis"]["muted"], "fontSize": 9, "fontFamily": FONT_NUM},
        "inRange": {"color": ["#10161A", "#0F3D45", "#0F7B74", "#8FBF6A", "#E8C547", "#F2F4F0"]},
    }
    opt["series"] = [{
        "type": "heatmap", "data": data, "progressive": 4000,
        "emphasis": {"itemStyle": {"borderWidth": 0}},
        "itemStyle": {"borderWidth": 0},
    }]
    opt["xAxis"] = dict(opt["xAxis"], name="时间 (s)", nameLocation="middle", nameGap=24,
                        nameTextStyle={"color": opt["_axis"]["muted"], "fontSize": 10})
    opt["yAxis"] = dict(opt["yAxis"], name="kHz", nameLocation="middle", nameGap=42,
                        nameTextStyle={"color": opt["_axis"]["muted"], "fontSize": 10})
    a = opt.pop("_axis")
    for ax in ("xAxis", "yAxis"):
        opt[ax].update({
            "axisLine": {"lineStyle": {"color": a["grid"]}},
            "axisTick": {"show": False},
            "axisLabel": {"color": a["muted"], "fontSize": 9, "fontFamily": FONT_NUM},
            "splitLine": {"show": False},
        })
    return opt


# --------------------------------------------------------------------------
# 零差测试：频带差异柱状图
# --------------------------------------------------------------------------
def band_option(null: dict, *, title: str = "", dark: bool = False) -> dict:
    bands = null.get("bands") or []
    if not bands:
        return {}
    labels = [f"{b['lo'] / 1000:.0f}–{b['hi'] / 1000:.0f}k" for b in bands]
    vals = [round(float(b["diff_db"]), 1) for b in bands]
    hot = null.get("hot_band") or {}
    opt = _base(title, dark=dark)
    opt["grid"] = {"left": 52, "right": 18, "top": 34 if title else 18, "bottom": 34}
    opt["tooltip"] = {"trigger": "axis", "backgroundColor": "#1B201E", "borderWidth": 0,
                      "textStyle": {"color": "#F2F4F0", "fontSize": 11, "fontFamily": FONT_NUM},
                      "valueFormatter": None}
    opt["xAxis"] = {"type": "category", "data": labels}
    opt["yAxis"] = {"type": "value", "min": -120, "max": 0}
    colors = []
    for b in bands:
        is_hot = hot and abs(float(b["lo"]) - float(hot.get("lo", -1))) < 1e-6
        colors.append(PALETTE["bad"] if is_hot else PALETTE["signal"])
    opt["series"] = [{
        "type": "bar", "data": [{"value": v, "itemStyle": {"color": c}}
                                for v, c in zip(vals, colors)],
        "barMaxWidth": 34,
        "label": {"show": True, "position": "inside", "color": "#F7F8F5", "fontSize": 9,
                  "fontFamily": FONT_NUM, "formatter": "{c}"},
    }]
    opt["xAxis"] = {"type": "category", "data": labels}
    return _apply_axes(opt, xname="频带 (Hz)", yname="差异 (dBFS)")


# --------------------------------------------------------------------------
# 引擎基准：多指标横向对比
# --------------------------------------------------------------------------
def engine_compare_option(measurements: list, metric: str = "spur_dbc",
                          *, title: str = "", dark: bool = False) -> dict:
    """按某个指标对所有引擎横向对比。数值越接近 0（负得越少）越差。"""
    ok = [m for m in measurements if getattr(m, "ok", True)]
    if not ok:
        return {}
    key = metric
    ok = sorted(ok, key=lambda m: getattr(m, key), reverse=True)
    labels = [m.label for m in ok]
    vals = [round(float(getattr(m, key)), 1) for m in ok]
    opt = _base(title, dark=dark)
    opt["grid"] = {"left": 92, "right": 46, "top": 12, "bottom": 28}
    opt["tooltip"] = {"trigger": "axis", "backgroundColor": "#1B201E", "borderWidth": 0,
                      "textStyle": {"color": "#F2F4F0", "fontSize": 11, "fontFamily": FONT_NUM}}
    opt["xAxis"] = {"type": "value"}
    opt["yAxis"] = {"type": "category", "data": labels}
    best = vals[0] if vals else 0
    series_data = []
    for v in vals:
        series_data.append({"value": v,
                            "itemStyle": {"color": PALETTE["signal"] if v >= best - 3
                                          else PALETTE["signal_dim"]}})
    opt["series"] = [{
        "type": "bar", "data": series_data, "barMaxWidth": 16,
        "label": {"show": True, "position": "right", "color": opt["_axis"]["muted"],
                  "fontSize": 10, "fontFamily": FONT_NUM, "formatter": "{c}"},
    }]
    return _apply_axes(opt, yname="")


def speed_fidelity_option(measurements: list, *, title: str = "",
                          dark: bool = False) -> dict:
    """速度 × 保真 散点：**右下角最好**（又快又干净），左上角最差。

    方向容易搞反，这里说明白：x 是实时倍速，越大越快 → 越靠右越好；
    y 是杂散 dBc，越负越干净，而 dB 轴 0 在上、−250 在下 → **越靠下越好**。
    所以"理想区"是右下角，不是右上角（右上角是"快但脏"，典型如 SciPy / ffmpeg swr）。

    这张图回答的是"值不值得为几 dB 付 10 倍时间"——表格给不了这种直觉。
    """
    ok = [m for m in measurements if getattr(m, "ok", True) and m.speed_x > 0]
    if not ok:
        return {}
    opt = _base(title, dark=dark)
    # 左边距要够宽：纵轴名带方向提示（"杂散 dBc（越下越干净）"），
    # 62px 会把竖排文字压到画布外。
    opt["grid"] = {"left": 96, "right": 30, "top": 26 if title else 14, "bottom": 44}
    opt["tooltip"] = {"trigger": "item", "backgroundColor": "#1B201E", "borderWidth": 0,
                      "textStyle": {"color": "#F2F4F0", "fontSize": 11, "fontFamily": FONT_NUM}}
    # 轴名直接带上方向，省得读者猜：右=快，下=干净
    opt["xAxis"] = {"type": "log", "name": "实时倍速（越右越快）", "nameLocation": "middle",
                    "nameGap": 26, "nameTextStyle": {"color": opt["_axis"]["muted"],
                                                     "fontSize": 10}}
    opt["yAxis"] = {"type": "value", "name": "杂散 dBc（越下越干净）",
                    "nameLocation": "middle", "nameGap": 58,
                    "nameTextStyle": {"color": opt["_axis"]["muted"], "fontSize": 10}}
    pts = []
    for idx, m in enumerate(ok):
        # 标签左右交替：sox_ng 与 ffmpeg 的 (速度, 杂散) 几乎重合，统一放右侧必然叠字。
        # labelLayout 的 moveOverlap 在这版 ECharts 上对 scatter 不生效，于是按序号定边。
        pts.append({
            "name": m.label,
            "value": [round(float(m.speed_x), 1), round(float(m.spur_dbc), 1)],
            "symbolSize": 11,
            "itemStyle": {"color": PALETTE["signal"], "opacity": .9},
            "label": {"show": True, "position": "right" if idx % 2 == 0 else "left",
                      "distance": 7, "formatter": m.label,
                      "color": opt["_axis"]["muted"], "fontSize": 10,
                      "fontFamily": FONT_UI},
        })
    # 标签在右上方两点重合时会叠成一行（sox_ng rate 与 FFmpeg aresample 实测就撞了）。
    # shiftY 让 ECharts 自动把重叠的标签上下错开，比手工给每个点写偏移稳。
    opt["series"] = [{"type": "scatter", "data": pts,
                      "labelLayout": {"moveOverlap": "shiftY"},
                      "markLine": {"silent": True, "symbol": "none",
                                   "lineStyle": {"color": opt["_axis"]["grid"],
                                                 "type": "dashed", "width": 1},
                                   "label": {"show": False},
                                   "data": [{"yAxis": -180}]}}]
    # 右下角标一个"理想区"，光靠文案容易看反
    opt["graphic"] = [{
        "type": "text", "right": 46, "bottom": 52, "silent": True, "z": 3,
        "style": {"text": "理想区", "fill": opt["_axis"]["muted"], "fontSize": 10,
                  "fontFamily": FONT_UI, "opacity": .8},
    }]
    return _apply_axes(opt, xname="", yname="")


# --------------------------------------------------------------------------
# 波形包络
# --------------------------------------------------------------------------
def waveform_option(y, rate: int, *, points: int = 900, title: str = "",
                    dark: bool = False) -> dict:
    """抽取 min/max 包络画波形，长音频也不会拖慢前端。"""
    import numpy as np

    if y is None or len(y) == 0:
        return {}
    # 不要 y[:, 0]：那是整声道的一份副本（一小时立体声 = 600 MB），
    # 而画包络只需要 points 个 min/max 对。
    stereo = getattr(y, "ndim", 1) > 1
    n = int(len(y))
    step = max(1, n // max(1, points))
    xs, hi, lo = [], [], []
    for i in range(0, n - step + 1, step):
        blk = np.asarray(y[i:i + step, 0] if stereo else y[i:i + step], dtype=np.float64)
        if blk.size == 0:
            break
        xs.append(round(i / rate, 4))
        hi.append(round(float(blk.max()), 4))
        lo.append(round(float(blk.min()), 4))
    opt = _base(title, dark=dark)
    opt["grid"] = {"left": 52, "right": 18, "top": 18, "bottom": 34}
    opt["tooltip"] = {"trigger": "axis", "backgroundColor": "#1B201E", "borderWidth": 0,
                      "textStyle": {"color": "#F2F4F0", "fontSize": 11, "fontFamily": FONT_NUM}}
    opt["xAxis"] = {"type": "category", "data": xs, "boundaryGap": False}
    opt["yAxis"] = {"type": "value", "min": -1.05, "max": 1.05}
    opt["series"] = [
        {"type": "line", "data": hi, "showSymbol": False, "lineStyle": {"width": 0.8,
         "color": PALETTE["signal"]}, "silent": True},
        {"type": "line", "data": lo, "showSymbol": False, "lineStyle": {"width": 0.8,
         "color": PALETTE["signal"]}, "silent": True},
    ]
    return _apply_axes(opt, xname="秒", yname="幅度")


# --------------------------------------------------------------------------
# 杂散/镜像/混叠三合一（对数纵轴）
# --------------------------------------------------------------------------
def imd_option(measurements: list, *, title: str = "", dark: bool = False) -> dict:
    """互调失真专图：单音杂散 vs CCIF 双音 vs 24 音多音。

    分三组柱而不是一根柱，是因为三者的**测量条件**不同（单音/双音/多音），
    混在一根柱里读者会误以为可以逐项相减。它们只在"同一次重采样"下可比。
    """
    ok = [m for m in measurements if getattr(m, "ok", True)]
    if not ok:
        return {}
    opt = _base(title, dark=dark)
    # bottom 92 = 34 (legend) + 30 (rotated tick labels) + 28 (axis name); with the
    # old 46 the legend sat on top of the "引擎" label.
    opt["grid"] = {"left": 52, "right": 18, "top": 34, "bottom": 92}
    opt["tooltip"] = {"trigger": "axis", "backgroundColor": "#1B201E", "borderWidth": 0,
                      "textStyle": {"color": "#F2F4F0", "fontSize": 11, "fontFamily": FONT_NUM}}
    opt["legend"] = {"bottom": 2, "textStyle": {"color": opt["_axis"]["muted"], "fontSize": 10}}
    labels = [m.label for m in ok]
    # interval:0 forces every category label to render. ECharts hides alternate
    # labels by default when they would collide, which silently dropped half the
    # engine names from the chart.
    opt["xAxis"] = {"type": "category", "data": labels,
                    "axisLabel": {"interval": 0, "rotate": 30, "fontSize": 9}}
    vals = [float(getattr(m, k, -300.0)) for m in ok
            for k in ("spur_dbc", "imd_dbc", "mt_dbc")]
    # 阈值放到 −420：激励改成整数相位后，Deep_PGGB / PGGB 的真实读数已经在
    # −320…−365 dBc，用旧的 −290 会把它们整排滤掉，纵轴退回到 −120。
    lo = min([v for v in vals if v > -420] or [-120.0])
    opt["yAxis"] = {"type": "value", "min": math.floor((lo - 15) / 25) * 25, "max": 5}
    opt["series"] = [
        {"name": "单音杂散", "type": "bar", "barMaxWidth": 12,
         "itemStyle": {"color": PALETTE["signal"]},
         "data": [round(float(getattr(m, "spur_dbc", -300.0)), 1) for m in ok]},
        {"name": "双音互调 (19k+20k)", "type": "bar", "barMaxWidth": 12,
         "itemStyle": {"color": PALETTE["bad"]},
         "data": [round(float(getattr(m, "imd_dbc", -300.0)), 1) for m in ok]},
        {"name": "多音残余 (24 音)", "type": "bar", "barMaxWidth": 12,
         "itemStyle": {"color": PALETTE["ok"]},
         "data": [round(float(getattr(m, "mt_dbc", -300.0)), 1) for m in ok]},
    ]
    return _apply_axes(opt, xname="引擎", yname="dBc")


def fidelity_option(measurements: list, *, title: str = "", dark: bool = False) -> dict:
    ok = [m for m in measurements if getattr(m, "ok", True)]
    if not ok:
        return {}
    labels = [m.label for m in ok]
    opt = _base(title, dark=dark)
    opt["grid"] = {"left": 52, "right": 18, "top": 34, "bottom": 92}
    opt["tooltip"] = {"trigger": "axis", "backgroundColor": "#1B201E", "borderWidth": 0,
                      "textStyle": {"color": "#F2F4F0", "fontSize": 11, "fontFamily": FONT_NUM}}
    opt["legend"] = {"bottom": 2, "textStyle": {"color": opt["_axis"]["muted"], "fontSize": 10}}
    opt["xAxis"] = {"type": "category", "data": labels,
                    "axisLabel": {"interval": 0, "rotate": 30, "fontSize": 9}}
    # 纵轴按实际数据自适应：固定 −300 会把 −200 dB 的柱子压成一条线，看不出差别
    def _val(m, k):
        # 整数倍率引擎没有降采样，混叠项无定义：画成空柱而不是 −300 的长条，
        # 否则图上会出现一根"混叠抑制完美"的假柱子。
        if k == "alias_dbc" and getattr(m, "alias_na", False):
            return None
        v = float(getattr(m, k, -300.0))
        return v if v > -420 else None

    vals_all = [v for m in ok
                for k in ("spur_dbc", "image_dbc", "alias_dbc", "imd_dbc", "mt_dbc")
                for v in [_val(m, k)] if v is not None]
    lo = min(vals_all) if vals_all else -120.0
    opt["yAxis"] = {"type": "value", "min": math.floor((lo - 15) / 25) * 25, "max": 5}
    series = []
    # 单音三项（杂散/镜像/混叠）+ 互调两项（CCIF 双音、24 音多音）。
    # 互调单独用虚线边框标出：它衡量的是线性度，与前三项的物理含义不同。
    for key, name, color in (("spur_dbc", "杂散", PALETTE["signal"]),
                             ("image_dbc", "镜像", PALETTE["ref"]),
                             ("alias_dbc", "混叠", PALETTE["warn"]),
                             ("imd_dbc", "互调 IMD", PALETTE["bad"]),
                             ("mt_dbc", "多音残余", PALETTE["ok"])):
        series.append({"name": name, "type": "bar", "barMaxWidth": 12,
                       "itemStyle": {"color": color},
                       "data": [None if _val(m, key) is None else round(_val(m, key), 1)
                                for m in ok]})
    opt["series"] = series
    return _apply_axes(opt, xname="引擎", yname="dBc")
