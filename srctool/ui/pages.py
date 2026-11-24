"""页面组装：工作台 / 引擎基准 / 音频体检 / 参数百科 / 任务。

设计取舍：
  * 每个页面 = 一个函数，内部用 @ui.refreshable 管局部重绘，避免整页闪烁。
  * 耗时操作一律走 jobs.JobManager（后台线程），UI 只轮询进度 ——
    NiceGUI 的事件循环不能被 30 秒的重采样卡住。
  * 所有数字都来自 metrics/quality，页面本身不做任何音频计算。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from nicegui import app, events, ui

from .. import codecs, config, engines, jobs as jobsmod, metrics, pipeline, plans, plot, presets, probe, quality
from .. import __version__
from . import components as C
from . import theme

NAV = [
    ("/", "转换台", "tune"),
    ("/engines", "引擎基准", "graphic_eq"),
    ("/analyze", "音频体检", "monitor_heart"),
    ("/glossary", "参数百科", "menu_book"),
    ("/jobs", "任务", "list_alt"),
]


# --------------------------------------------------------------------------
# 外壳
# --------------------------------------------------------------------------
def _rail(active: str) -> None:
    with ui.element("div").classes("ss-rail"):
        with ui.element("div").classes("ss-rail-head"):
            with ui.element("div").style("display:flex;align-items:baseline;gap:2px"):
                ui.html('<div class="ss-brand">SONAR<span>SRC</span></div>')
            ui.label("采样率转换工作台").classes("ss-sub").style("margin-top:6px")
            ui.label("v" + __version__).classes("ss-sub").style("margin-top:2px;opacity:.6")
        with ui.element("div").classes("ss-nav"):
            for i, (route, label, icon) in enumerate(NAV):
                cls = "ss-nav-item" + (" active" if route == active else "")
                with ui.element("div").classes(cls).on("click", lambda r=route: ui.navigate.to(r)):
                    ui.label(f"{i + 1:02d}").classes("ss-nav-idx")
                    ui.icon(icon)
                    ui.label(label).classes("ss-nav-label")
        with ui.element("div").style("flex:1 1 auto"):
            pass
        with ui.element("div").classes("ss-rail-foot")                 .style("padding:10px 16px;border-top:1px solid var(--line-soft)"):
            env = config.env_report()
            keys = ("ffmpeg", "sox_ng", "r8brain", "ssrc", "deeppggb")
            ok = sum(1 for k in keys if env.get(k))
            ui.label(f"引擎就绪 {ok}/{len(keys)}").classes("ss-note")
            ui.label(f"ffmpeg {'✓' if env.get('ffmpeg') else '✗'}  "
                     f"sox_ng {'✓' if env.get('sox_ng') else '✗'}  "
                     f"dpggb {'✓' if env.get('deeppggb') else '✗'}").classes("ss-note") \
                .style("font-family:var(--font-num);font-size:10px;opacity:.75")
            C.theme_toggle()


def _shell(active: str):
    """返回内容容器；调用方在 with 里写页面主体。"""
    with ui.element("div").classes("ss-shell"):
        _rail(active)
        main = ui.element("div").classes("ss-main")
    with main:
        return ui.element("div").classes("ss-page")


def _page_header(title: str, desc: str, extra: str = "") -> None:
    with ui.element("div").style("margin-bottom:20px"):
        with ui.element("div").classes("row items-baseline").style("gap:12px;width:100%"):
            ui.label(title).classes("ss-h1")
            if extra:
                C.chip(extra)
        ui.label(desc).classes("ss-body").style("margin-top:5px;max-width:820px")


# --------------------------------------------------------------------------
# 通用：文件选择
# --------------------------------------------------------------------------
UPLOAD_DIR = config.WORK / "uploads"


def _fmt_duration(sec: float) -> str:
    if not sec:
        return "—"
    m, s = divmod(float(sec), 60.0)
    return f"{int(m)}:{s:05.2f}" if m else f"{s:.2f} s"


def file_picker(state: dict, *, key: str = "path", on_change=None) -> ui.element:
    """上传 / 整页拖拽 / 手输路径三条路都落到同一个 state[key]，并回调 on_change。"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    holder = ui.element("div").style("width:100%")
    guard = {"busy": False}

    with holder:
        with ui.element("div").classes("row items-center").style("gap:10px;width:100%;flex-wrap:nowrap"):
            path_in = ui.input(placeholder="把文件拖到页面任意位置，或粘贴绝对路径…",
                               value=state.get(key, "")).props("dense outlined clearable")
            path_in.classes("ss-num").style("flex:1 1 auto;min-width:0")

            def _commit(p: str) -> None:
                """唯一落点：写 state → 同步输入框 → 回调。

                guard 用来挡住"程序写 value 又触发 on_value_change"的回路，
                否则拖拽一次会分析两遍。
                """
                p = (p or "").strip()
                state[key] = p
                guard["busy"] = True
                try:
                    if (path_in.value or "") != p:
                        path_in.value = p
                finally:
                    guard["busy"] = False
                if on_change:
                    on_change(p)

            def _path_changed(e) -> None:
                # 手动输入/粘贴路径也必须进入 state，否则点"开始转换"会报没选文件
                if guard["busy"]:
                    return
                _commit(e.value or "")

            path_in.on_value_change(_path_changed)

            async def _upload(e: events.UploadEventArguments) -> None:
                safe = Path(e.file.name).name
                dest = UPLOAD_DIR / f"{int(time.time())}_{safe}"
                await e.file.save(dest)
                _commit(str(dest))
                ui.notify(f"已载入 {safe}", position="bottom-left")

            ui.upload(on_upload=_upload, auto_upload=True, multiple=False,
                      max_file_size=4 * 1024**3, label="上传") \
                .props("flat dense color=transparent accept=audio/*,.wav,.flac,.mp3,.aif,.aiff,.caf,.m4a,.ogg,.opus,.wv,.tta,.dsf,.dff,.ape,.w64,.au,.webm") \
                .classes("ss-uploader") \
                .style("max-width:112px;flex:0 0 auto")

        # Quasar 的 q-uploader 只接受拖到它自己的标题栏上，拖到页面别处毫无反应。
        # 这里给整页加兜底：DROP_JS 监听 window 的 drag* 事件，POST 到 /api/upload，
        # 再用 emitEvent('ssdrop', path) 把结果送回下面这个 handler。
        ui.add_body_html(theme.DROP_JS)

        def _dropped(e) -> None:
            p = str(getattr(e, "args", "") or "").strip()
            if p:
                _commit(p)
                ui.notify(f"已载入 {Path(p).name}", position="bottom-left")

        ui.on("ssdrop", _dropped)
        ui.on("ssdrop-error", lambda e: ui.notify(f"上传失败：{e.args}", type="negative"))
    return holder


def _info_tiles(info: dict) -> None:
    with C.row(10):
        C.tile("采样率", f"{info.get('sample_rate', 0) / 1000:.1f}", "kHz")
        C.tile("声道", info.get("channels", "—"))
        C.tile("位深", info.get("bit_depth") or "—", "bit")
        C.tile("时长", _fmt_duration(info.get("duration", 0)))
        C.tile("编码", (info.get("codec") or "—").upper())
        C.tile("容器", (info.get("container") or "—").upper())


def _report_tiles(rep: dict) -> None:
    lufs = rep.get("lufs") or {}
    bw = rep.get("bandwidth") or {}
    with C.row(10):
        C.tile("峰值", f"{rep.get('peak_dbfs', -200):.2f}", "dBFS")
        C.tile("真峰值", f"{rep.get('true_peak_dbtp', -200):.2f}", "dBTP",
               level="bad" if rep.get("true_peak_dbtp", -200) > -1 else "")
        C.tile("响度", f"{lufs.get('integrated', -200):.1f}", "LUFS")
        C.tile("动态范围", f"{lufs.get('lra', 0):.1f}", "LU")
        C.tile("波峰因数", f"{rep.get('crest_db', 0):.1f}", "dB")
        C.tile("有效位深", rep.get("effective_bits", "—"), "bit",
               level="warn" if (rep.get("effective_bits") or 0) < 16 else "")
        C.tile("带宽", f"{bw.get('hz', 0) / 1000:.2f}", "kHz")
        C.tile("静段电平", f"{rep.get('noise_floor_dbfs', -200):.1f}", "dBFS")


# ==========================================================================
# 1. 转换台
# ==========================================================================
@ui.page("/")
def page_workbench() -> None:
    ui.add_head_html(theme.head_html())
    ui.page_title(config.APP_TITLE)

    state: dict = {
        "path": "",
        "dst_rate": 48000,
        "fmt": "flac",
        "bits": 24,
        "engine": "r8b",
        "opts": engines.default_opts("r8b"),
        "gain_db": None,
        "normalize_dbfs": None,
        "dither": True,
        "noise_shape": True,
        "dither_filter": "shibata",
        "fmt_opts": {p["key"]: p["default"] for p in codecs.FORMATS["flac"].params},
        "analyze": True,
        "null_test": True,
        "result": None,
        "job": None,
    }

    page = _shell("/")
    with page:
        _page_header("转换台", "载入任意格式音频 → 选择引擎与全部底层参数 → 输出并同时得到"
                               "输入质量、输出质量、SRC 保真度三份结论。",
                     extra="七引擎全参数")

        # ---------------- 输入 ----------------
        with C.card("输入源", subtitle="支持 wav/flac/aiff/caf/mp3/ogg/opus/m4a/alac/wv/tta/dsf/ape…",
                    accent="brass"):
            info_holder = ui.element("div").style("width:100%")

            def _show_info(path: str) -> None:
                info_holder.clear()
                if not path:
                    return
                with info_holder:
                    info = pipeline.quick_probe(path)
                    if not info.get("ok"):
                        ui.label("无法解析：" + str(info.get("error"))[:200]).classes("ss-verdict bad")
                        return
                    with C.row(12):
                        with ui.element("div").style("flex:1 1 560px;min-width:0"):
                            _info_tiles(info)
                        with ui.element("div").style("flex:0 0 auto"):
                            if info.get("lossless") is False:
                                C.chip("有损源", "bad")
                            else:
                                C.chip("无损源", "ok")
                            if info.get("dsd"):
                                C.chip("DSD", "brass")

            file_picker(state, on_change=_show_info)
            _show_info(state["path"])

        # ---------------- 目标 + 引擎 ----------------
        dither_ctl: list = []      # 抖动相关控件，切到有损格式时统一禁用（在下方填充）
        with C.row(14):
            with ui.element("div").style("flex:1 1 420px;min-width:0"):
                with C.card("目标", accent="sig"):
                    rate_in = ui.select(
                        {r: f"{r} Hz  ({r / 1000:g} kHz)" for r in config.TARGET_RATES},
                        value=state["dst_rate"], label="目标采样率", with_input=True,
                        new_value_mode="add-unique",
                    ).props("dense outlined").classes("full-width")
                    rate_in.on_value_change(
                        lambda e: state.__setitem__("dst_rate", int(e.value or 0)))

                    with ui.element("div").classes("row").style("gap:10px;width:100%;margin-top:10px"):
                        fmt_in = ui.select(
                            dict(codecs.format_choices()), value=state["fmt"],
                            label="输出格式").props("dense outlined").classes("col")
                        fmt_in.on_value_change(lambda e: _on_fmt(e.value))

                        bits_in = ui.select(config.STANDARD_BITS, value=state["bits"],
                                            label="位深").props("dense outlined").classes("col")

                    def _on_fmt(v: str) -> None:
                        state["fmt"] = v
                        spec = codecs.FORMATS.get(v)
                        if spec and state["bits"] not in spec.bits:
                            state["bits"] = spec.default_bits
                            bits_in.value = spec.default_bits
                        lossy = bool(spec and not spec.lossless)
                        if lossy:
                            ui.notify("有损格式：位深设置不生效，抖动也会被忽略",
                                      position="bottom-left", type="warning")
                        # 有损编码器内部自己做量化，抖动/噪声整形接不上，直接禁用避免误解
                        for ctl in dither_ctl:
                            ctl.set_enabled(not lossy)
                            if lossy and hasattr(ctl, "value"):
                                try:
                                    ctl.value = False
                                except Exception:  # noqa: BLE001
                                    pass
                        # 换格式时把该格式的专属参数重置成它自己的默认值，
                        # 否则会把上一个容器的参数（如 FLAC 的压缩等级）带到 MP3 上
                        state["fmt_opts"] = ({p["key"]: p["default"] for p in spec.params}
                                             if spec else {})
                        fmt_box.refresh()

                    bits_in.on_value_change(
                        lambda e: state.__setitem__("bits", int(e.value or 24)))

                    # 容器专属参数（码率/压缩等级/立体声模式/DSD 倍率…）
                    @ui.refreshable
                    def fmt_box() -> None:
                        spec = codecs.FORMATS.get(state["fmt"])
                        if not spec or not spec.params:
                            return
                        ui.element("div").style("height:6px")
                        C.rich(spec.note, "ss-note", style="margin:8px 0 2px 0")

                        def _set_fmt(key: str, val) -> None:
                            if val is None:
                                state["fmt_opts"].pop(key, None)
                            else:
                                state["fmt_opts"][key] = val

                        for p in spec.params:
                            C.param_row(p, state["fmt_opts"].get(p["key"], p["default"]),
                                        _set_fmt)

                    fmt_box()

            # align-self:flex-start —— 否则 .row 的 items-stretch 会把引擎卡
            # 拉到与"目标"卡同高（目标卡有容器参数，通常更高），下面空出一大片
            with ui.element("div").style("flex:1 1 420px;min-width:0;align-self:flex-start"):
                with C.card("引擎", accent="sig"):
                    # 只列能真正完成转换的引擎：PGGB 这类"仅整数倍上采样"的对照引擎
                    # 放进来，用户选中后 44.1→48 必然报错，等于给了一个假选项。
                    eng_in = ui.select(
                        {k: f"{v.label}" for k, v in engines.ENGINES.items()
                         if not v.bench_only},
                        value=state["engine"], label="重采样引擎").props("dense outlined") \
                        .classes("full-width")
                    eng_note = ui.html("").classes("ss-note").style("margin-top:8px")

                    def _on_engine(v: str) -> None:
                        state["engine"] = v
                        state["opts"] = engines.default_opts(v)
                        spec = engines.ENGINES.get(v)
                        eng_note.set_content(
                            (spec.tagline + "　速度 " + spec.speed + "　保真 " + spec.fidelity)
                            if spec else "")
                        params_box.refresh()

                    eng_in.on_value_change(lambda e: _on_engine(e.value))
                    _spec0 = engines.ENGINES.get(state["engine"])
                    if _spec0:
                        eng_note.set_content(_spec0.tagline + "　速度 " + _spec0.speed
                                             + "　保真 " + _spec0.fidelity)

        # ---------------- 预设 ----------------
        with C.card("预设", subtitle="每个预设都能被下面的旋钮还原 —— 不是黑盒"):
            with ui.element("div").classes("row").style("gap:8px;flex-wrap:wrap;width:100%"):
                for p in presets.PRESETS:
                    def _apply(_e=None, _p=p):
                        state["engine"] = _p.engine
                        state["opts"] = dict(_p.engine_opts)
                        state["fmt"] = _p.fmt
                        state["bits"] = _p.bits
                        state["dither"] = _p.dither
                        state["noise_shape"] = _p.noise_shape
                        state["dither_filter"] = _p.dither_filter
                        eng_in.value = _p.engine
                        _on_engine(_p.engine)
                        state["opts"] = dict(_p.engine_opts)
                        fmt_in.value = _p.fmt
                        bits_in.value = _p.bits
                        note.set_content(_p.note)
                        params_box.refresh()

                    with ui.element("div").classes("ss-chip").style("cursor:pointer;padding:4px 10px") \
                            .on("click", _apply).tooltip(p.group):
                        ui.label(p.label)
            note = ui.html("").classes("ss-note").style("margin-top:10px;max-width:900px;line-height:1.7")

        # ---------------- 引擎参数 ----------------
        @ui.refreshable
        def params_box() -> None:
            spec = engines.ENGINES.get(state["engine"])
            if not spec:
                return
            with C.card("引擎参数", subtitle=spec.label + " · " + spec.speed + " 实时"):
                C.rich(spec.description, "ss-body")
                ui.element("div").style("height:10px")

                def _set(key: str, val) -> None:
                    if val is None:
                        state["opts"].pop(key, None)
                    else:
                        state["opts"][key] = val

                for p in spec.params:
                    C.param_row(p.to_dict(), state["opts"].get(p.key, p.default), _set)

        params_box()
        _on_engine(state["engine"])

        # ---------------- 处理选项 ----------------
        with C.card("处理与输出选项"):
            with ui.element("div").style("display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px"):
                gain = ui.number(label="增益 (dB)", value=state["gain_db"], step=0.1,
                                 format="%.2f").props("dense outlined clearable")
                gain.on_value_change(lambda e: state.__setitem__("gain_db", e.value))

                norm = ui.number(label="归一化到峰值 (dBFS)", value=state["normalize_dbfs"],
                                 min=-60, max=0, step=0.1).props("dense outlined clearable")
                norm.on_value_change(lambda e: state.__setitem__("normalize_dbfs", e.value))

                dith = ui.switch("抖动（dither）", value=state["dither"]).props("dense")
                dith.on_value_change(lambda e: state.__setitem__("dither", e.value))

                ns = ui.switch("噪声整形", value=state["noise_shape"]).props("dense")
                ns.on_value_change(lambda e: state.__setitem__("noise_shape", e.value))

                # 供 _on_fmt 在切换到有损格式时统一禁用（见上方闭包）
                dither_ctl.extend([dith, ns])

                dfil = ui.select({"shibata": "shibata（44.1/48 经典）",
                                  "lipshitz": "lipshitz（44.1 优化）",
                                  "f-weighted": "f-weighted（温和）",
                                  "modified-e-weighted": "modified-e-weighted",
                                  "improved-e-weighted": "improved-e-weighted",
                                  "gesemann": "gesemann（24bit）",
                                  "none": "不整形"},
                                 value=state["dither_filter"], label="整形曲线").props("dense outlined")
                dfil.on_value_change(lambda e: state.__setitem__("dither_filter", e.value))

                nullsw = ui.switch("零差测试（与 r8brain 参考对比）", value=state["null_test"]).props("dense")
                nullsw.on_value_change(lambda e: state.__setitem__("null_test", e.value))

        # ---------------- 执行 ----------------
        with C.card("执行"):
            prog = ui.linear_progress(value=0, show_value=False).props("rounded=false") \
                .style("height:3px;margin-bottom:10px")
            status_holder = ui.element("div").style("width:100%")

            with ui.element("div").classes("row items-center").style("gap:12px;width:100%"):
                run_btn = ui.button("开始转换", icon="play_arrow").classes("ss-btn-primary")
                out_label = ui.label("").classes("ss-note ss-num")

            result_holder = ui.element("div").style("width:100%;margin-top:4px")

            def _render_result(res: dict) -> None:
                result_holder.clear()
                with result_holder:
                    if not res.get("ok"):
                        with C.card("转换失败", accent="bad"):
                            ui.label(res.get("error") or "未知错误").classes("ss-verdict bad")
                        return
                    with C.card("结果", accent="ok"):
                        with C.row(10):
                            C.tile("输出采样率", f"{res['dst_rate'] / 1000:.1f}", "kHz")
                            C.tile("帧数", f"{res['frames_out']:,}")
                            C.tile("耗时", f"{res['elapsed']:.2f}", "s")
                            C.tile("速度", f"{res['speed_x']:.0f}", "× 实时")
                            C.tile("引擎", res.get("engine_label", ""))
                        p = res.get("output_path", "")
                        if p:
                            name = Path(p).name
                            with ui.element("div").classes("row").style("gap:8px;margin-top:12px"):
                                ui.label(p).classes("ss-note ss-num").style("flex:1 1 auto")
                                ui.button("下载", icon="download",
                                          on_click=lambda: ui.navigate.to("/files/" + name)) \
                                    .props("flat dense").classes("ss-btn-ghost")

                    for w in res.get("warnings") or []:
                        with C.card("", accent="bad"):
                            ui.label(w).classes("ss-verdict-x")

                    # 结论
                    for title, items in (("SRC 质量结论", res.get("src_verdicts") or []),
                                         ("输入音频结论", res.get("input_verdicts") or []),
                                         ("输出音频结论", res.get("output_verdicts") or [])):
                        if not items:
                            continue
                        with C.card(title):
                            with C.col(8):
                                for v in items:
                                    C.verdict(v)

                    # 绝对保真度（当前引擎已是参考本身时）
                    sm = res.get("src_measure") or {}
                    if sm.get("ok"):
                        with C.card("SRC 绝对保真度", accent="sig",
                                    subtitle="当前引擎的参数已是最严格参考，改测合成音指标"):
                            with C.row(10):
                                C.tile("杂散", f"{sm.get('spur_dbc', 0):.1f}", "dBc")
                                C.tile("镜像", f"{sm.get('image_dbc', 0):.1f}", "dBc")
                                C.tile("混叠", f"{sm.get('alias_dbc', 0):.1f}", "dBc")
                                C.tile("互调", f"{sm.get('imd_dbc', 0):.1f}", "dBc",
                                       hint="19k+20k 双音，CCIF")
                                C.tile("多音", f"{sm.get('mt_dbc', 0):.1f}", "dBc",
                                       hint="24 音 100 Hz–18 kHz")
                                C.tile("SINAD", f"{sm.get('sinad_dbc', -300):.1f}", "dBc",
                                       hint="基频 / 全部残余（谐波+杂散+镜像+噪声）")
                                C.tile("SFDR", f"{sm.get('sfdr_dbc', -300):.1f}", "dBc",
                                       hint="最坏一根谱线，除直流与基频 ±1 bin")
                                C.tile("ENOB", f"{sm.get('enob_bits', 0):.1f}", "bit",
                                       hint="按 SINAD 折算到满刻度正弦，双精度上限约 52 bit")
                                C.tile("21.5 kHz", f"{sm.get('passband_21500', 0):+.2f}", "dB")
                                C.tile("速度", f"{sm.get('speed_x', 0):.0f}", "×")

                    # 零差
                    null = res.get("null") or {}
                    if null.get("ok"):
                        with C.card("零差测试", accent="brass",
                                    subtitle=f"参考 = r8brain full / 250 dB"):
                            v = null.get("verdict") or {}
                            with C.row(10):
                                C.tile("可闻带深度", f"{null.get('null_depth_audible_db', 0):.1f}",
                                       "dB", hint="判级依据：20 kHz 以下")
                                C.tile("全带深度", f"{null.get('null_depth_db', 0):.1f}", "dB",
                                       hint="含超声区")
                                C.tile("可闻误差", f"{null.get('audible_err_dbfs', -200):.1f}",
                                       "dBFS")
                                C.tile("对齐滞后", f"{null.get('lag_ms', 0):.3f}", "ms")
                            if v:
                                ui.label(v.get("text", "")).classes("ss-verdict-x") \
                                    .style("margin-top:10px")
                            C.chart(plot.band_option(null, dark=True), height=220)

                    # 频谱对比
                    ir = res.get("input_report") or {}
                    orr = res.get("output_report") or {}
                    if ir.get("spectrum") and orr.get("spectrum"):
                        with C.card("频谱对比", subtitle="输入 vs 输出（峰值归一，对数频率轴）"):
                            C.chart(plot.spectrum_option(
                                [ir["spectrum"], orr["spectrum"]], ["输入", "输出"],
                                dark=True), height=280)

                    if orr.get("spectrum"):
                        sg = res.get("output_spectrogram")
                        if sg:
                            with C.card("输出频谱图", subtitle="时间 × 频率 × 能量"):
                                C.chart(plot.spectrogram_option(
                                    sg, duration=res.get("duration", 0), dark=True), height=260)

            def _run() -> None:
                path = state.get("path", "").strip()
                if not path or not Path(path).is_file():
                    ui.notify("请先选择一个存在的音频文件", type="negative")
                    return
                spec = codecs.FORMATS.get(state["fmt"])
                if spec is None:
                    ui.notify("输出格式无效", type="negative")
                    return
                dst = int(state["dst_rate"] or 0)
                out_name = codecs.output_name(path, spec, dst, "srctool")
                out_path = config.WORK / out_name
                req = pipeline.ConvertRequest(
                    input_path=path,
                    output_path=str(out_path),
                    fmt=state["fmt"],
                    bits=int(state["bits"]),
                    dst_rate=dst,
                    engine=state["engine"],
                    engine_opts=dict(state["opts"]),
                    gain_db=state["gain_db"],
                    normalize_dbfs=state["normalize_dbfs"],
                    dither=bool(state["dither"]),
                    dither_filter=state["dither_filter"],
                    noise_shape=bool(state["noise_shape"]),
                    format_params=dict(state.get("fmt_opts") or {}),
                    analyze=True,
                    null_test=bool(state["null_test"]),
                )
                out_label.set_text("→ " + out_name)
                run_btn.disable()

                job = jobsmod.JOBS.submit("convert", Path(path).name,
                                          lambda j: pipeline.convert(req, jobsmod.progress_reporter(j)))
                state["job"] = job.id
                result_holder.clear()
                status_holder.clear()
                with status_holder:
                    dot = ui.element("div").classes("ss-status")

                def _poll() -> None:
                    j = jobsmod.JOBS.get(job.id)
                    if j is None:
                        timer.cancel()
                        run_btn.enable()
                        return
                    prog.value = j.progress
                    dot.clear()
                    with dot:
                        ui.element("span").classes(
                            "ss-dot " + ("run" if j.status in ("running", "queued") else
                                         "done" if j.status == "done" else "err"))
                        ui.label(f"{j.progress * 100:5.1f}%  {j.message or j.status}")
                    if j.status in ("done", "error", "cancelled"):
                        timer.cancel()
                        run_btn.enable()
                        if j.status == "done":
                            res = j.result.to_dict() if hasattr(j.result, "to_dict") else (j.result or {})
                            # 频谱图需要单独算（不进 ConvertResult，避免分析时浪费）
                            try:
                                from ..codecs import decode as _dec
                                au = _dec(res["output_path"])
                                res["output_spectrogram"] = metrics.spectrogram(
                                    au.data, au.rate, n_fft=1024, frames=240)
                                au.close()
                            except Exception:  # noqa: BLE001
                                pass
                            state["result"] = res
                            _render_result(res)
                            ui.notify("转换完成", type="positive", position="bottom-left")
                        else:
                            _render_result({"ok": False, "error": j.error or "任务被取消"})

                timer = ui.timer(0.3, _poll)

            run_btn.on_click(_run)


# ==========================================================================
# 2. 引擎基准
# ==========================================================================
@ui.page("/engines")
def page_engines() -> None:
    ui.add_head_html(theme.head_html())
    ui.page_title("引擎基准 · " + config.APP_NAME)

    state: dict = {"measurements": [], "running": False}

    page = _shell("/engines")
    with page:
        _page_header("引擎基准",
                     "用合成正弦对八台引擎做可复现的保真度测量：44.1→48 kHz 测杂散、"
                     "44.1→96 kHz 测镜像、96→44.1 kHz 测混叠，再测 21.5/22 kHz 通带、"
                     "双音/多音互调与实时倍速。激励用整数相位，参考信号的自身误差在 −320 dBc 以下。",
                     extra="合成音测量")

        with C.card("被测引擎", subtitle="勾选后一起测；每台用各自的默认参数"):
            chosen: dict[str, bool] = {k: True for k in engines.ENGINES}
            with ui.element("div").style(
                    "display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px"):
                for k, spec in engines.ENGINES.items():
                    sw = ui.switch(spec.label, value=True).props("dense")
                    sw.on_value_change(lambda e, _k=k: chosen.__setitem__(_k, e.value))
                    with sw:
                        ui.label(spec.tagline).classes("ss-note")
                        if spec.integer_only:
                            ui.label("只测整数倍率（44.1→88.2），无降采样项").classes("ss-note") \
                                .style("color:var(--warn)")

        table_holder = ui.element("div").style("width:100%")
        chart_holder = ui.element("div").style("width:100%")
        verdict_holder = ui.element("div").style("width:100%")
        prog = ui.linear_progress(value=0, show_value=False).style("height:3px;margin:8px 0")
        status_holder = ui.element("div").style("width:100%")

        def _render(ms: list) -> None:
            rows = []
            for m in ms:
                if not m.ok:
                    rows.append({"engine": m.label, "spur": "—", "image": "—", "alias": "—",
                                 "imd": "—", "mt": "—", "sinad": "—", "sfdr": "—",
                                 "enob": "—", "pb215": "—", "pb220": "—", "speed": "—",
                                 "note": m.error or ""})
                    continue
                rows.append({
                    "engine": m.label,
                    # 整数倍率引擎没有降采样项：写 n/a，不要写 −300 的哨兵值冒充好成绩
                    "spur": f"{m.spur_dbc:.1f}",
                    "image": f"{m.image_dbc:.1f}",
                    "alias": "n/a" if m.alias_na else f"{m.alias_dbc:.1f}",
                    "imd": f"{m.imd_dbc:.1f}",
                    "mt": f"{m.mt_dbc:.1f}",
                    "sinad": f"{m.sinad_dbc:.1f}",
                    "sfdr": f"{m.sfdr_dbc:.1f}",
                    "enob": f"{m.enob_bits:.1f}",
                    "pb215": f"{m.passband_21500:+.2f}",
                    "pb220": f"{m.passband_22000:+.2f}",
                    "speed": f"{m.speed_x:.0f}×",
                    "note": "",
                })
            table_holder.clear()
            with table_holder:
                with C.card("测量结果", subtitle="dBc 越小（越负）越好；通带 +0.00 dB 表示全通"):
                    # 口径不同的引擎混在一张表里必须写清：PGGB 只能做整数倍上采样，
                    # 它的杂散/镜像/互调全部是在 44.1→88.2 下测的，与其余引擎的
                    # 44.1→48 / 44.1→96 不是同一个倍率，逐格比较前要看这一行。
                    if any(getattr(m, "integer_only", False) or
                           (getattr(m, "ratio_label", "") or "").startswith("44.1→88.2")
                           for m in ms):
                        C.rich("PGGB 一行为 44.1→88.2（×2 整数倍）口径，其余引擎为 "
                               "44.1→48 / 44.1→96 / 96→44.1；它的混叠项 n/a 是因为内核"
                               "只能整数倍上采样，做不了降采样。", "ss-note",
                               style="margin-bottom:8px")
                    ui.table(
                        columns=[
                            {"name": "engine", "label": "引擎", "field": "engine",
                             "align": "left", "style": "font-family:var(--font-ui)"},
                            {"name": "spur", "label": "杂散 dBc", "field": "spur", "align": "right"},
                            {"name": "image", "label": "镜像 dBc", "field": "image", "align": "right"},
                            {"name": "alias", "label": "混叠 dBc", "field": "alias", "align": "right"},
                            {"name": "imd", "label": "互调 dBc", "field": "imd", "align": "right"},
                            {"name": "mt", "label": "多音 dBc", "field": "mt", "align": "right"},
                            {"name": "sinad", "label": "SINAD dBc", "field": "sinad", "align": "right"},
                            {"name": "sfdr", "label": "SFDR dBc", "field": "sfdr", "align": "right"},
                            {"name": "enob", "label": "ENOB bit", "field": "enob", "align": "right"},
                            {"name": "pb215", "label": "21.5k dB", "field": "pb215", "align": "right"},
                            {"name": "pb220", "label": "22k dB", "field": "pb220", "align": "right"},
                            {"name": "speed", "label": "速度", "field": "speed", "align": "right"},
                        ],
                        rows=rows, row_key="engine", pagination=0,
                    ).props("flat dense separator=horizontal").classes("full-width")

            chart_holder.clear()
            with chart_holder:
                with C.card("保真度对比"):
                    C.chart(plot.fidelity_option(ms, dark=True), height=260)
                with C.card("互调失真（线性度）",
                            subtitle="单音只看有没有多余谱线，双音/多音才看会不会长出新的音"):
                    C.chart(plot.imd_option(ms, dark=True), height=260)
                with C.card("速度 × 保真",
                            subtitle="右下角最好：越快（越右）越干净（越下）；虚线是 −180 dBc"):
                    C.chart(plot.speed_fidelity_option(ms, dark=True), height=260)

            verdict_holder.clear()
            with verdict_holder:
                with C.card("结论", accent="sig"):
                    with C.col(8):
                        for v in quality.verdict_src(ms):
                            C.verdict(v)

        def _run() -> None:
            keys = [k for k, on in chosen.items() if on]
            if not keys:
                ui.notify("至少选一台引擎", type="warning")
                return
            run_btn.disable()
            job = jobsmod.JOBS.submit(
                "bench", "引擎基准",
                lambda j: quality.compare_engines(
                    keys, progress=lambda i, n, k: setattr(j, "progress", i / max(1, n))))

            def _poll() -> None:
                j = jobsmod.JOBS.get(job.id)
                if j is None:
                    timer.cancel()
                    run_btn.enable()
                    return
                prog.value = j.progress
                status_holder.clear()
                with status_holder:
                    ui.label(f"测量中… {j.progress * 100:.0f}%").classes("ss-note ss-num")
                if j.status in ("done", "error", "cancelled"):
                    timer.cancel()
                    run_btn.enable()
                    status_holder.clear()
                    if j.status == "done":
                        state["measurements"] = j.result
                        _render(j.result)
                        ui.notify("测量完成", type="positive", position="bottom-left")
                    else:
                        ui.notify("测量失败：" + str(j.error)[:200], type="negative")

            timer = ui.timer(0.4, _poll)

        with ui.element("div").classes("row").style("gap:10px;margin:14px 0"):
            run_btn = ui.button("开始测量", icon="science").classes("ss-btn-primary")
            run_btn.on_click(_run)
            def _load_last(silent: bool = False) -> None:
                items, meta = quality.load_bench()
                if not items:
                    if not silent:
                        ui.notify("还没有测过 —— 先点一次开始测量", type="warning",
                                  position="bottom-left")
                    return
                state["measurements"] = items
                _render(items)
                if not silent:
                    ui.notify("已载入 " + meta.get("saved_at", "上次结果"), type="info",
                              position="bottom-left")

            ui.button("载入上次结果", icon="history",
                      on_click=lambda: _load_last()).props("flat").classes("ss-btn-ghost")

        # 引擎说明书
        with C.card("引擎档案"):
            for k, spec in engines.ENGINES.items():
                with ui.expansion(f"{spec.label} — {spec.tagline}").classes("full-width"):
                    ui.label(spec.description).classes("ss-body")
                    with ui.element("div").style("margin-top:8px"):
                        C.kv("许可", spec.license)
                        C.kv("速度", spec.speed)
                        C.kv("保真", spec.fidelity)
                        C.kv("带宽", spec.bandwidth)

        # 进页面就把上次的测量结果铺出来 —— 空白页对"上次测过什么"毫无提示
        _load_last(silent=True)


# ==========================================================================
# 3. 音频体检
# ==========================================================================
@ui.page("/analyze")
def page_analyze() -> None:
    ui.add_head_html(theme.head_html())
    ui.page_title("音频体检 · " + config.APP_NAME)

    state: dict = {"path": ""}
    page = _shell("/analyze")
    with page:
        _page_header("音频体检",
                     "对一个文件做完整测量：电平、响度、真峰值、有效位深、带宽、直流、削波、"
                     "立体声场，以及频谱与频谱图。",
                     extra="BS.1770-4")

        with C.card("文件", accent="brass"):
            _holder_box: dict = {}

            def _render(payload: dict) -> None:
                holder = _holder_box.get("el")
                if holder is None:
                    return
                info = payload["info"]
                plan = payload["plan"]
                holder.clear()
                with holder:
                    _info_tiles(info)
                    with C.card("分析范围", accent="brass"):
                        with C.row(10):
                            C.tile("模式", {"full": "全长", "sample": "抽样",
                                            "truncated": "截断"}.get(plan["mode"], plan["mode"]))
                            C.tile("参与分析", _fmt_duration(plan["seconds"]))
                            C.tile("文件总长", _fmt_duration(plan["total_seconds"]))
                        C.rich(plan["note"], "ss-note", style="margin-top:8px")
                    with C.card("电平与响度", accent="sig"):
                        _report_tiles(payload["report"])
                    with C.card("结论"):
                        with C.col(8):
                            for v in payload["verdicts"]:
                                C.verdict(v)
                    if payload.get("spectrum"):
                        with C.card("频谱"):
                            C.chart(payload["spectrum"], height=300)
                    if payload.get("spectrogram"):
                        with C.card("频谱图", subtitle="时间 × 频率 × 能量（0 到 −90 dB）"):
                            C.chart(payload["spectrogram"], height=300)
                    if payload.get("waveform"):
                        with C.card("波形包络"):
                            C.chart(payload["waveform"], height=180)

            def _analyze(path: str) -> None:
                info_holder = _holder_box.get("el")
                if info_holder is None:
                    return
                info_holder.clear()
                if not path or not Path(path).is_file():
                    return
                with info_holder:
                    with ui.row().classes("items-center").style("gap:10px"):
                        ui.spinner(size="sm")
                        ui.label("解码并分析…").classes("ss-note")

                def _work(j) -> dict:
                    j.message = "探测…"
                    j.progress = 0.05
                    info = probe.probe(path)
                    j.message = "解码…"
                    j.progress = 0.15
                    au = codecs.decode(path)
                    # 大文件走 memmap：y 是磁盘映射的视图，au.close() 之后它就成了
                    # 悬空指针（Windows 上直接 access violation，不是异常）。
                    # 所以所有用到 y 的计算都必须留在 with 里面。
                    try:
                        rate, nch = au.rate, au.channels
                        plan = plans.plan_analysis(au.duration, rate, nch)
                        y = plans.extract(au.data, rate, plan)
                        j.message = f"测量（{plan.mode}）…"
                        j.progress = 0.4
                        rep = metrics.analyze(y, rate)
                        j.message = "频谱…"
                        j.progress = 0.75
                        payload = {
                            "info": info.to_dict(),
                            "plan": plan.to_dict(),
                            "report": rep.to_dict(),
                            "verdicts": quality.verdict_audio(rep, info),
                            "spectrum": plot.spectrum_option([rep.spectrum], ["信号"], dark=True)
                            if rep.spectrum else {},
                            "waveform": plot.waveform_option(y, rate),
                        }
                        sg = metrics.spectrogram(y, rate, n_fft=1024, frames=260)
                        if sg.get("data"):
                            payload["spectrogram"] = plot.spectrogram_option(
                                sg, duration=plan.seconds, dark=True)
                    finally:
                        au.close()
                    j.progress = 0.95
                    return payload

                job = jobsmod.JOBS.submit("analyze", Path(path).name, _work)
                state["job"] = job.id

                def _poll() -> None:
                    j = jobsmod.JOBS.get(job.id)
                    if j is None:
                        timer.cancel()
                        return
                    if j.status in ("done", "error", "cancelled"):
                        timer.cancel()
                        if j.status == "done" and isinstance(j.result, dict):
                            _render(j.result)
                        else:
                            info_holder.clear()
                            with info_holder:
                                with C.card("", accent="bad"):
                                    ui.label(f"分析失败：{j.error or '已取消'}") \
                                        .classes("ss-verdict-x")

                timer = ui.timer(0.25, _poll)

            # 顺序很重要：先建文件选择器，再建结果容器，否则结果会出现在选择器上方
            file_picker(state, on_change=_analyze)
            _holder_box["el"] = ui.element("div").style("width:100%;margin-top:12px")
            _analyze(state["path"])


# ==========================================================================
# 4. 参数百科
# ==========================================================================
@ui.page("/glossary")
def page_glossary() -> None:
    ui.add_head_html(theme.head_html())
    ui.page_title("参数百科 · " + config.APP_NAME)

    page = _shell("/glossary")
    with page:
        _page_header("参数百科",
                     "每个指标是什么意思、每个旋钮在动什么、调它要付出什么代价。"
                     "这里的内容和界面上参数旁的说明来自同一份数据。",
                     extra=f"{len(presets.GLOSSARY)} 个概念")

        with ui.tabs().props("dense align=left") as tabs:
            t1 = ui.tab("指标")
            t2 = ui.tab("引擎参数")
            t3 = ui.tab("预设")

        with ui.tab_panels(tabs, value=t1).classes("full-width").style("background:transparent"):
            with ui.tab_panel(t1).style("padding:16px 0"):
                for term in presets.GLOSSARY:
                    with ui.element("div").classes("ss-term"):
                        with ui.element("div").classes("ss-term-t"):
                            ui.label(term.title)
                            ui.label(term.short).classes("ss-note").style("font-weight:400")
                            if term.typical:
                                ui.label(term.typical).classes("ss-term-s")
                        C.rich(term.long, "ss-body", style="margin-top:6px;max-width:980px")
                        if term.unit:
                            C.chip(term.unit)

            with ui.tab_panel(t2).style("padding:16px 0"):
                for k, spec in engines.ENGINES.items():
                    with C.card(spec.label, subtitle=spec.tagline):
                        C.rich(spec.description, "ss-body", style="margin-bottom:10px")
                        for p in spec.params:
                            d = p.to_dict()
                            with ui.element("div").classes("ss-param"):
                                with ui.element("div").classes("ss-param-l"):
                                    ui.label(d["label"])
                                    C.chip(d["key"])
                                    if d["default"] is not None:
                                        C.chip(f"默认 {d['default']}", "brass")
                                    if d.get("min") is not None:
                                        C.chip(f"{d['min']} – {d['max']} {d.get('unit', '')}")
                                C.rich(d["desc"], "ss-param-d")

            with ui.tab_panel(t3).style("padding:16px 0"):
                for p in presets.PRESETS:
                    with C.card(p.label, subtitle=p.group, accent="brass"):
                        C.rich(p.note, "ss-body")
                        with ui.element("div").classes("row").style("gap:8px;margin-top:10px"):
                            C.chip(p.engine, "patina")
                            C.chip(p.fmt)
                            C.chip(f"{p.bits} bit")
                            for kk, vv in p.engine_opts.items():
                                C.chip(f"{kk}={vv}")


# ==========================================================================
# 5. 任务
# ==========================================================================
@ui.page("/jobs")
def page_jobs() -> None:
    ui.add_head_html(theme.head_html())
    ui.page_title("任务 · " + config.APP_NAME)

    page = _shell("/jobs")
    with page:
        _page_header("任务", "后台线程里的转换与测量。关掉页面不会中断，重新打开仍在。")
        holder = ui.element("div").style("width:100%")

        def _render() -> None:
            items = jobsmod.JOBS.list()
            holder.clear()
            with holder:
                if not items:
                    C.empty("暂无任务。回到转换台提交一个转换，或去引擎基准跑一次测量。")
                    return
                rows = [{
                    "id": j.id, "title": j.title, "kind": j.kind, "status": j.status,
                    "progress": f"{j.progress * 100:.0f}%",
                    "elapsed": f"{j.elapsed:.1f}s",
                    "msg": (j.error or j.message or "")[:80],
                } for j in items]
                with C.card("任务列表"):
                    ui.table(columns=[
                        {"name": "id", "label": "ID", "field": "id", "align": "left"},
                        {"name": "kind", "label": "类型", "field": "kind", "align": "left"},
                        {"name": "title", "label": "标题", "field": "title", "align": "left"},
                        {"name": "status", "label": "状态", "field": "status", "align": "left"},
                        {"name": "progress", "label": "进度", "field": "progress", "align": "right"},
                        {"name": "elapsed", "label": "耗时", "field": "elapsed", "align": "right"},
                        {"name": "msg", "label": "信息", "field": "msg", "align": "left"},
                    ], rows=rows, row_key="id", pagination=0) \
                        .props("flat dense separator=horizontal").classes("full-width")

        _render()
        ui.timer(1.0, _render)
