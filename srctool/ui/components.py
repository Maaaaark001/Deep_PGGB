"""可复用 UI 组件。

全部是薄封装：只负责"长成什么样"，不持有业务状态。
页面逻辑在 pages.py，样式令牌在 theme.py。
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable

from nicegui import ui

from . import theme


# --------------------------------------------------------------------------
# 容器
# --------------------------------------------------------------------------
@contextmanager
def card(title: str = "", *, subtitle: str = "", accent: str = "",
         cls: str = "", flat: bool = False):
    """一张仪器面板。accent: '' | 'sig' | 'bad' | 'ok'（左侧色条语义）。"""
    classes = "ss-card"
    if flat:
        classes += " flat"
    if accent:
        classes += " ss-accent " + accent
    with ui.element("div").classes(classes + (" " + cls if cls else "")):
        if title:
            with ui.element("div").classes("ss-card-h"):
                ui.label(title).classes("ss-card-t")
                if subtitle:
                    ui.label(subtitle).classes("ss-note")
        yield


@contextmanager
def row(gap: int = 10, cls: str = ""):
    with ui.element("div").classes("row items-stretch").style(
            "gap:%dpx;flex-wrap:wrap;width:100%%;%s" % (gap, cls)):
        yield


@contextmanager
def col(gap: int = 10, cls: str = ""):
    with ui.element("div").classes("column").style("gap:%dpx;width:100%%;%s" % (gap, cls)):
        yield


# --------------------------------------------------------------------------
# 数据块
# --------------------------------------------------------------------------
def tile(label: str, value: Any, unit: str = "", *, level: str = "",
         hint: str = "") -> ui.element:
    """一个读数块：小标签 + 大数字（等宽）+ 单位。"""
    el = ui.element("div").classes("ss-tile" + (" " + level if level else ""))
    with el:
        ui.label(label).classes("ss-tile-l")
        with ui.element("div").classes("ss-tile-v"):
            ui.label(str(value))
            if unit:
                ui.html("<small>%s</small>" % unit)
    if hint:
        with el:
            ui.label(hint).classes("ss-note").style("margin-top:4px")
    return el


def verdict(v: dict) -> None:
    """结论卡：level / title / text / metric。"""
    level = v.get("level", "info")
    with ui.element("div").classes("ss-verdict " + level):
        with ui.element("div").classes("ss-verdict-t"):
            ui.label(v.get("title", ""))
            if v.get("metric"):
                ui.label(v["metric"]).classes("ss-verdict-m")
        ui.label(v.get("text", "")).classes("ss-verdict-x")


def chip(text: str, tone: str = "") -> ui.element:
    el = ui.element("span").classes("ss-chip" + (" " + tone if tone else ""))
    with el:
        ui.label(text)
    return el


def kv(k: str, v: str, *, mono: bool = True) -> None:
    with ui.element("div").classes("row items-baseline").style("gap:8px;width:100%"):
        ui.label(k).classes("ss-note").style("flex:0 0 96px")
        ui.label(str(v)).classes("ss-num" if mono else "ss-body").style("flex:1 1 auto")


def section(title: str, note: str = "") -> None:
    with ui.element("div").style("margin-bottom:6px"):
        ui.label(title).classes("ss-h2")
        if note:
            ui.label(note).classes("ss-note")


def rich(text: str, cls: str = "ss-body", style: str = "") -> None:
    """把数据里的 **粗体** 与 `代码` 变成真正的强调，而不是显示星号。

    这些字符串来自 engines/presets 的说明文本，作者习惯用 markdown 强调，
    但 ui.label 不解析 markdown，直接显示会露出 ** 号。
    """
    import html as _html
    import re as _re

    safe = _html.escape(str(text))
    safe = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
    safe = _re.sub(r"`([^`]+?)`", r"<code>\1</code>", safe)
    el = ui.html('<div class="%s">%s</div>' % (cls, safe))
    if style:
        el.style(style)
    return el


def empty(text: str) -> None:
    ui.label(text).classes("ss-empty")


def rule() -> None:
    ui.element("div").classes("ss-rule")


# --------------------------------------------------------------------------
# 参数控件
# --------------------------------------------------------------------------
def param_control(p: dict, value: Any, on_change: Callable[[str, Any], None],
                  *, compact: bool = True) -> ui.element:
    """按 Param 元数据渲染一个控件，并把变更回调出去。

    kind: bool -> 开关；int/float -> 数字框；select -> 下拉。
    default 为 None 的数值参数表示"跟随档位默认"，额外给一个开关。
    """
    key = p["key"]
    kind = p["kind"]
    ctl_cls = "ss-param-ctl"

    if kind == "bool":
        sw = ui.switch(p["label"], value=bool(value))
        sw.classes("ss-param-l")
        sw.on_value_change(lambda e: on_change(key, bool(e.value)))
        return sw

    if kind == "select":
        # 引擎参数用 [{"value","label"}]，容器参数（codecs._p）用 [(value, label)] 元组，
        # 这里统一成 NiceGUI 需要的 {value: label} 字典。
        raw = p.get("options") or []
        opts = {(o["value"] if isinstance(o, dict) else o[0]):
                (o["label"] if isinstance(o, dict) else o[1]) for o in raw}
        sel = ui.select(opts, value=value, label=p["label"], with_input=False)
        sel.classes(ctl_cls).props("dense outlined options-dense")
        sel.on_value_change(lambda e: on_change(key, e.value))
        return sel

    # 数值
    optional = p.get("default") is None
    holder = ui.element("div").style("width:100%")
    with holder:
        if optional:
            with ui.element("div").classes("row items-center").style("gap:8px;width:100%"):
                auto = ui.switch("跟随档位", value=(value is None)).props("dense")
                num = ui.number(label=p["label"], value=(value if value is not None
                                                          else p.get("min", 0)),
                                min=p.get("min"), max=p.get("max"),
                                step=p.get("step") or 1,
                                format="%.4g" if kind == "float" else "%d")
                num.classes(ctl_cls).props("dense outlined")
                num.set_enabled(value is not None)

                def _auto(e, _n=num, _k=key):
                    _n.set_enabled(not e.value)
                    on_change(_k, None if e.value else _n.value)

                def _num(e, _a=auto, _k=key):
                    if not _a.value:
                        on_change(_k, e.value)

                auto.on_value_change(_auto)
                num.on_value_change(_num)
        else:
            num = ui.number(label=p["label"], value=value, min=p.get("min"),
                            max=p.get("max"), step=p.get("step") or 1,
                            format="%.4g" if kind == "float" else "%d")
            num.classes(ctl_cls + " full-width").props("dense outlined")
            num.on_value_change(lambda e: on_change(key, e.value))
    return holder


def param_row(p: dict, value: Any, on_change: Callable[[str, Any], None]) -> None:
    """一行参数：左边标签+说明，右边控件。说明文字始终可见（需求要求参数可解释）。"""
    with ui.element("div").classes("ss-param"):
        with ui.element("div").classes("row items-start").style("gap:14px;width:100%"):
            with ui.element("div").style("flex:1 1 220px;min-width:0"):
                with ui.element("div").classes("ss-param-l"):
                    ui.label(p["label"])
                    if p.get("advanced"):
                        chip("高级")
                    if p.get("unit"):
                        ui.label(p["unit"]).classes("ss-note")
                ui.label(p["desc"]).classes("ss-param-d")
            with ui.element("div").style("flex:0 0 190px;max-width:190px"):
                param_control(p, value, on_change)


# --------------------------------------------------------------------------
# 图表容器
# --------------------------------------------------------------------------
def chart(options: dict, *, height: int = 240) -> ui.element | None:
    if not options:
        return None
    with ui.element("div").classes("ss-chart").style("width:100%"):
        e = ui.echart(options).style("height:%dpx;width:100%%" % height)
    return e


def theme_toggle() -> None:
    """侧栏底部的明暗切换：图标 + 文字，比一个孤零零的圆形按钮好认。"""
    dark = ui.dark_mode(value=theme.dark_enabled())
    btn = ui.button("深色", icon="contrast").props("flat dense no-caps") \
        .classes("ss-theme-btn").style("margin-top:8px")
    btn.tooltip("切换深色 / 浅色")

    def _flip() -> None:
        dark.toggle()
        btn.set_text("浅色" if dark.value else "深色")

    btn.on_click(_flip)


def status_dot(state: str, text: str) -> ui.element:
    el = ui.element("div").classes("ss-status")
    with el:
        ui.element("span").classes("ss-dot " + state)
        ui.label(text)
    return el
