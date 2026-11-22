# -*- coding: utf-8 -*-
"""Publication figures for the Deep_PGGB manuscript.

All data panels read work/*.json produced by the measurement scripts; no
synthetic curve is drawn.  Panels carry no titles -- the caption is the title.
Figure width is 159 mm so that the 602 px placement in the A4 manuscript lands
at 1:1.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import numpy as np  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from nature_style import (apply_style, panel, save_all, set_outdir, clean_axes,  # noqa: E402
                          panel_letter, landed_report, ACADEMIC, GREY)

FIGDIR = os.path.join(ROOT, "work", "figures")
set_outdir(FIGDIR)
W = 159.0

# semantic engine colours, fixed for the whole paper
C = {
    "dpggb": "#E64B35",
    "pggb": "#3C5488",
    "r8b": "#4DBBD5",
    "soxng": "#00A087",
    "swr": "#F39B7F",
    "soxr": "#8491B4",
    "ssrc": "#8C6D31",
    "scipy": "#B09C85",
}
LBL = {
    "dpggb": "Deep_PGGB", "pggb": "PGGB", "r8b": "r8brain-free",
    "soxng": "sox_ng rate", "swr": "FFmpeg aresample", "soxr": "libsoxr",
    "ssrc": "SSRC", "scipy": "SciPy resample_poly",
}
INK = "#222222"
MUTED = "#666666"


def load(name):
    with open(os.path.join(ROOT, "work", name), encoding="utf-8") as f:
        return json.load(f)


def _box(ax, x, y, w, h, text, fc="#dfe9f3", ec="#9db4cc", fs=8.4):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=1.2",
                                linewidth=0.7, edgecolor=ec, facecolor=fc, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=INK, zorder=3, linespacing=1.25)


def _arrow(ax, p0, p1, dashed=False):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=8,
                                 linewidth=0.8, color="#4d4d4d", zorder=1,
                                 linestyle=(0, (3, 2)) if dashed else "solid",
                                 shrinkA=1.5, shrinkB=1.5))


# ---------------------------------------------------------------------------
# fig1: offline block pipeline (a) and streaming FIFO (b)
# ---------------------------------------------------------------------------
def fig1_architecture():
    p = panel(placed_mm=W, height_mm=122)
    apply_style(p)
    fig = plt.figure(figsize=p.figsize)
    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.12], hspace=0.10)
    a = fig.add_subplot(gs[0])
    b = fig.add_subplot(gs[1])
    for ax in (a, b):
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        ax.axis("off")

    # ---- (a) offline pipeline
    y, h, w = 58, 20, 14.0
    xs = [1.5, 18.0, 34.5, 51.0, 67.5, 84.0]
    labels = ["Input", "Block framing\n+ context", "rFFT\n(P bins)",
              "Zero-pad to Q\n+ roll-off", "irFFT", "Overlap-add\n→ output"]
    for x, t in zip(xs, labels):
        _box(a, x, y, w, h, t)
    for x in xs[:-1]:
        _arrow(a, (x + w + 0.4, y + h / 2), (x + w + 3.0, y + h / 2))

    _box(a, 22, 16, 58, 24,
         "Kernel controls\n"
         "C5 boundary taper   ·   passband roll-off ($Q<P$)\n"
         "minimum-phase FIR (optional)",
         fc="#f6e8d5", ec="#d8bd97", fs=8.2)
    _arrow(a, (58, 40.5), (58, 57.5), dashed=True)
    a.text(1.5, 47, "16 s blocks · 800 ms context", fontsize=7.8,
           color=MUTED, va="center")
    panel_letter(a, "a", x=0.0, y=0.99)

    # ---- (b) streaming front end
    yb, hb, wb = 78, 16, 14.0
    xb = [1.5, 17.0, 32.5, 48.0, 63.5, 79.0]
    bl = ["push\nN frames", "FIFO", "window\nL|core|R", "same\nkernel",
          "emit\ncore", "cursor\n+= core"]
    for x, t in zip(xb, bl):
        _box(b, x, yb, wb, hb, t, fc="#dfe9f3", ec="#9db4cc", fs=8.0)
    for x in xb[:-1]:
        _arrow(b, (x + wb + 0.4, yb + hb / 2), (x + wb + 3.0, yb + hb / 2))

    # window geometry: three successive windows, core advances
    x0, core, ctx = 7.0, 26.0, 8.0
    for k, yy in enumerate((58, 44, 30)):
        xx = x0 + k * core
        b.add_patch(plt.Rectangle((xx, yy), ctx, 7, facecolor="#dbe7f3",
                                  edgecolor="#9db4cc", lw=0.5, zorder=2))
        b.add_patch(plt.Rectangle((xx + ctx, yy), core, 7, facecolor="#8fb8de",
                                  edgecolor="#5f86ad", lw=0.5, zorder=2))
        b.add_patch(plt.Rectangle((xx + ctx + core, yy), ctx, 7, facecolor="#dbe7f3",
                                  edgecolor="#9db4cc", lw=0.5, zorder=2))
        b.text(xx - 1.2, yy + 3.5, "k" if k == 0 else "k+%d" % k,
               ha="right", va="center", fontsize=7.6, color=MUTED)
    b.annotate("", xy=(x0 + 3 * core + ctx, 25), xytext=(x0 + 3 * core + ctx, 67),
               arrowprops=dict(arrowstyle="-|>", lw=0.7, color=MUTED,
                               linestyle=(0, (2, 2))))
    b.text(x0 + 3 * core + ctx + 1, 71, "cursor", fontsize=7.4, color=MUTED)
    b.text(x0 + ctx / 2, 61.5, "ctx", ha="center", va="center", fontsize=6.8, color="#33506e")
    b.text(x0 + ctx + core / 2, 61.5, "core", ha="center", va="center", fontsize=6.8, color="white")
    b.text(x0 + ctx + core + ctx / 2, 61.5, "ctx", ha="center", va="center", fontsize=6.8, color="#33506e")
    b.text(7, 20, "only the core is written out; the context is recomputed on the next push",
           fontsize=7.4, color=MUTED, va="center")
    panel_letter(b, "b", x=0.0, y=0.99)

    landed_report(fig, p, verbose=False)
    save_all("fig1_architecture", fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# fig2: measured spectrum and analyser sensitivity
# ---------------------------------------------------------------------------
def fig2_spectral():
    d = load("spectrum_data.json")
    p = panel(placed_mm=W, height_mm=78)
    apply_style(p)
    fig, (a, b) = plt.subplots(1, 2, figsize=p.figsize,
                               gridspec_kw={"wspace": 0.30, "width_ratios": [1.45, 1]})

    a.plot(d["freq_khz"], d["mag_db"], lw=0.55, color=C["pggb"], zorder=3)
    a.set_xlim(0, 44.1)
    a.set_ylim(-340, 6)
    a.set_xlabel("Frequency (kHz)")
    a.set_ylabel("Level (dBc)")
    a.axhline(d["floor_db"], color="#8a8a8a", ls="--", lw=0.7, zorder=1)
    a.text(43.6, d["floor_db"] + 6, "residual floor %.1f dBc" % d["floor_db"],
           ha="right", fontsize=7.4, color=MUTED)
    a.annotate("1 kHz carrier", xy=(1.0, 0.0), xytext=(8.0, -55),
               fontsize=7.8, color=INK,
               arrowprops=dict(arrowstyle="-", lw=0.6, color=MUTED))
    a.text(6.0, -115, "44.1 → 88.2 kHz\n4 s · rectangular window", fontsize=7.4,
           color=MUTED, va="center")

    xs = [s["injected_dbc"] for s in d["sensitivity"]]
    ys = [s["measured_dbc"] for s in d["sensitivity"]]
    b.plot([-315, -215], [-315, -215], ls="--", lw=0.7, color="#8a8a8a")
    b.plot(xs, ys, "o", ms=4.2, color=C["dpggb"], mec="white", mew=0.5, zorder=3)
    b.set_xlim(-316, -214)
    b.set_ylim(-316, -214)
    b.set_aspect("equal")
    b.set_xticks([-300, -280, -260, -240, -220])
    b.set_yticks([-300, -280, -260, -240, -220])
    b.set_xlabel("Injected probe (dBc)")
    b.set_ylabel("Measured level (dBc)")
    b.text(-304, -230, "1:1", fontsize=7.6, color=MUTED, rotation=45)
    b.annotate("−310 dBc probe\nreads −308.8 dBc", xy=(-310, -308.8), xytext=(-288, -303),
               fontsize=7.2, color=INK,
               arrowprops=dict(arrowstyle="-", lw=0.6, color=MUTED))

    panel_letter(a, "a", x=-0.11)
    panel_letter(b, "b", x=-0.20)
    landed_report(fig, p, verbose=False)
    save_all("fig2_spectral", fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# fig3: eight-engine matrix and the accuracy / throughput plane
# ---------------------------------------------------------------------------
def fig3_engines():
    d = load("paper_data.json")
    eng = d["engines"]
    order = ["dpggb", "pggb", "r8b", "swr", "soxr", "soxng", "ssrc", "scipy"]
    rows = {e["engine"]: e for e in eng}
    metrics = [("spur_dbc", "Spurious", "#E64B35", "o"),
               ("image_dbc", "Image", "#4DBBD5", "s"),
               ("alias_dbc", "Alias", "#00A087", "^"),
               ("imd_dbc", "CCIF IMD", "#3C5488", "D"),
               ("imd_smpte_dbc", "SMPTE IMD", "#F39B7F", "v"),
               ("mt_dbc", "Multi-tone", "#8491B4", "P")]
    floors = {"spur_dbc": -307.1, "image_dbc": -320.2, "alias_dbc": -352.0,
              "imd_dbc": -334.4, "imd_smpte_dbc": -334.7, "mt_dbc": -295.2}

    p = panel(placed_mm=W, height_mm=98)
    apply_style(p)
    fig = plt.figure(figsize=p.figsize)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.0], wspace=0.30,
                          top=0.90, bottom=0.24, left=0.20, right=0.985)
    a = fig.add_subplot(gs[0])
    b = fig.add_subplot(gs[1])

    y = np.arange(len(order))
    a.axhspan(-0.45, 0.45, color="#fbe6e1", zorder=0)
    for i, key in enumerate(order):
        e = rows[key]
        for field, _lab, col, mk in metrics:
            v = e[field]
            if v is None:
                a.scatter(-373, i, marker="x", s=22, color="#9a9a9a", lw=0.8, zorder=3)
                continue
            a.scatter(v, i, marker=mk, s=24, facecolor=col, edgecolor="white",
                      linewidth=0.35, zorder=3)
    a.text(-370, 1.28, "n/a", fontsize=6.8, color="#7a7a7a", va="center")
    a.set_yticks(y)
    a.set_yticklabels([LBL[k] for k in order], fontsize=8.2)
    a.set_ylim(len(order) - 0.5, -0.5)
    a.set_xlim(-382, -40)
    a.set_xticks([-350, -300, -250, -200, -150, -100, -50])
    a.set_xlabel("Distortion product (dBc)")
    a.grid(axis="x", ls="--", lw=0.4, alpha=0.3)
    a.set_axisbelow(True)
    clean_axes(a, grid_axis=None)
    a.grid(axis="x", ls="--", lw=0.4, alpha=0.3)

    vals = []
    for k in order:
        e = rows[k]
        worst = max(e[f] for f, *_ in metrics if e[f] is not None)
        vals.append((e["speed_x"], worst, k))
    for sp, wo, k in vals:
        if k == "dpggb":
            b.scatter(sp, wo, s=72, marker="*", color=C["dpggb"], edgecolor="white",
                      linewidth=0.4, zorder=4)
        elif k == "pggb":
            b.scatter(sp, wo, s=34, marker="s", color=C["pggb"], edgecolor="white",
                      linewidth=0.4, zorder=3)
        else:
            b.scatter(sp, wo, s=30, marker="o", color="#9aa6b2", edgecolor="white",
                      linewidth=0.4, zorder=3)
    b.set_xscale("log")
    b.set_xlim(18, 900)
    b.set_xticks([20, 50, 100, 200, 500])
    b.set_xticklabels(["20", "50", "100", "200", "500"])
    b.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    b.set_ylim(-312, -48)
    b.set_xlabel("Throughput (× realtime)")
    b.set_ylabel("Worst metric (dBc)")
    b.axhline(floors["mt_dbc"], color="#8a8a8a", ls=":", lw=0.7)
    b.text(20, floors["mt_dbc"] - 6, "multi-tone floor", fontsize=7.0, color=MUTED, ha="left", va="top")
    offs = {"dpggb": (1.02, 7), "pggb": (1.12, 7), "r8b": (1.07, 4),
            "soxng": (1.07, 7), "swr": (0.55, -14), "soxr": (0.90, -12),
            "ssrc": (1.08, 4), "scipy": (1.06, 4)}
    for sp, wo, k in vals:
        dx, dy = offs[k]
        b.annotate(LBL[k], xy=(sp, wo), xytext=(sp * dx, wo + dy),
                   fontsize=6.9, color=INK, va="center")
    clean_axes(b)

    handles = [Line2D([], [], marker=mk, ls="", markersize=4, markerfacecolor=col,
                      markeredgecolor="white", markeredgewidth=0.35, label=lab)
               for _f, lab, col, mk in metrics]
    a.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.17),
             ncol=3, frameon=False, fontsize=6.8, handletextpad=0.3,
             columnspacing=1.0, labelspacing=0.35, borderaxespad=0.0)
    panel_letter(a, "a", x=-0.02, y=1.06)
    panel_letter(b, "b", x=-0.02, y=1.06)
    landed_report(fig, p, verbose=False)
    save_all("fig3_engines", fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# fig4: passband edge, dense sweep, both directions
# ---------------------------------------------------------------------------
def fig4_passband():
    d = load("passband_dense.json")
    f = np.array(d["freqs"]) / 1000.0
    order = ["dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"]
    p = panel(placed_mm=W, height_mm=90)
    apply_style(p)
    fig, (a, b) = plt.subplots(1, 2, figsize=p.figsize,
                               gridspec_kw={"wspace": 0.20}, sharey=True)
    cb = {"dpggb": "#D55E00", "pggb": "#0072B2", "r8b": "#009E73",
          "soxng": "#E69F00", "swr": "#56B4E9", "soxr": "#CC79A7",
          "ssrc": "#8C6D31", "scipy": "#9A9A9A"}
    dash = {"dpggb": "-", "pggb": (0, (6, 2)), "r8b": (0, (2, 1.6)),
            "soxng": (0, (5, 1.5, 1, 1.5)), "swr": (0, (1, 1.3)),
            "soxr": (0, (8, 2, 2, 2)), "ssrc": (0, (4, 1, 1, 1, 1, 1)),
            "scipy": (0, (7, 1.5))}
    for ax, key in ((a, "up"), (b, "down")):
        for k in order:
            row = d[key].get(k)
            if row is None:
                continue
            ax.plot(f, row, color=cb[k], ls=dash[k],
                    lw=2.2 if k == "dpggb" else 1.25,
                    label=LBL[k], zorder=4 if k == "dpggb" else 3)
        ax.axvline(22.05, color="#8a8a8a", ls=":", lw=0.7)
        ax.set_xlim(19.4, 22.06)
        ax.set_xticks([20, 21, 22])
        ax.set_xlabel("Frequency (kHz)")
    a.set_ylim(-232, 4)
    a.set_yticks([0, -50, -100, -150, -200])
    a.set_ylabel("Gain (dB)")
    a.legend(loc="lower left", fontsize=6.6, frameon=False, labelspacing=0.25,
             handlelength=1.5, borderaxespad=0.3)
    a.text(19.55, -8, "44.1 → 88.2 kHz", fontsize=7.6, color=INK)
    b.text(19.55, -8, "96 → 44.1 kHz", fontsize=7.6, color=INK)
    panel_letter(a, "a", x=-0.14)
    panel_letter(b, "b", x=-0.10)
    clean_axes(a); clean_axes(b)
    landed_report(fig, p, verbose=False)
    save_all("fig4_passband", fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# fig5: throughput -- block/worker grid and engine ranking
# ---------------------------------------------------------------------------
def fig5_speed():
    d = load("paper_data.json")
    p = panel(placed_mm=W, height_mm=84)
    apply_style(p)
    fig, (a, b) = plt.subplots(1, 2, figsize=p.figsize,
                               gridspec_kw={"wspace": 0.34, "width_ratios": [1.0, 1.05]})
    blocks = sorted({r["block_s"] for r in d["speed"]})
    cols = {1: "#B0B7C3", 2: "#7FA6C9", 4: "#3C5488", 8: "#E64B35"}
    for wk in (1, 2, 4, 8):
        ys = []
        for bs in blocks:
            hit = [r["speed_x"] for r in d["speed"]
                   if r["block_s"] == bs and r["workers"] == wk]
            ys.append(hit[0] if hit else np.nan)
        a.plot(blocks, ys, "o-", color=cols[wk], lw=1.0, ms=3.6,
               label="%d worker%s" % (wk, "s" if wk > 1 else ""))
    a.set_xscale("log")
    a.set_xticks([0.5, 1, 2, 4, 30])
    a.set_xticklabels(["0.5", "1", "2", "4", "30"])
    a.set_xlabel("Block length (s)")
    a.set_ylabel("Throughput (× realtime)")
    a.set_ylim(60, 160)
    a.legend(fontsize=6.2, loc="lower left", bbox_to_anchor=(0.0, 1.0),
             frameon=False, ncol=2, columnspacing=0.9, handlelength=1.2,
             borderaxespad=0.0, labelspacing=0.3)

    eng = {e["engine"]: e for e in d["engines"]}
    order = ["ssrc", "pggb", "r8b", "soxng", "dpggb", "swr", "scipy", "soxr"]
    ypos = np.arange(len(order))[::-1]
    vals = [eng[k]["speed_x"] for k in order]
    colors = [C["dpggb"] if k == "dpggb" else (C["pggb"] if k == "pggb" else "#9aa6b2")
              for k in order]
    b.barh(ypos, vals, color=colors, height=0.62, edgecolor="white", lw=0.4)
    for yp, v in zip(ypos, vals):
        b.text(v * 1.06, yp, "%.0f×" % v, va="center", fontsize=7.0, color=INK)
    b.set_yticks(ypos)
    b.set_yticklabels([LBL[k] for k in order])
    b.set_xscale("log")
    b.set_xlim(15, 1000)
    b.set_xticks([20, 50, 100, 200, 500, 1000])
    b.set_xticklabels(["20", "50", "100", "200", "500", "1000"])
    b.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    b.set_xlabel("Throughput (× realtime)")
    b.set_ylim(-0.7, len(order) - 0.3)
    clean_axes(a); clean_axes(b)
    panel_letter(a, "a", x=-0.24, y=1.16)
    panel_letter(b, "b", x=-0.20)
    landed_report(fig, p, verbose=False)
    save_all("fig5_speed", fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# fig6: mechanism -- taper continuity and context length
# ---------------------------------------------------------------------------
def fig6_params():
    d = load("paper_data.json")
    p = panel(placed_mm=W, height_mm=78)
    apply_style(p)
    fig, (a, b) = plt.subplots(1, 2, figsize=p.figsize, gridspec_kw={"wspace": 0.30})

    t = d["taper_order"]
    o = [r["order"] for r in t]
    leak = [r["leak_22050_db"] for r in t]
    null = [r["null_40tone_db"] for r in t]
    a.plot(o, leak, "o-", color=C["pggb"], lw=1.1, ms=4)
    a.set_ylim(-390, -200)
    a.set_yticks([-200, -250, -300, -350])
    a.set_xticks(o)
    a.set_xlabel("Taper continuity order")
    a.set_ylabel("Leakage at 22.05 kHz (dBc)")
    a.annotate("C5 used", xy=(5, -355.7), xytext=(3.2, -330),
               fontsize=7.4, color=INK,
               arrowprops=dict(arrowstyle="-", lw=0.6, color=MUTED))
    a.text(1, -382, "null depth: %d dB at C1, %d dB at C5" % (round(null[0]), round(null[-1])),
           fontsize=7.0, color=MUTED, va="bottom")

    ctxs = sorted({r["context_ms"] for r in d["context"]})
    for bt, col, mk in ((5, "#B0B7C3", "o"), (10, "#7FA6C9", "s"),
                        (20, C["dpggb"], "D"), (50, "#3C5488", "^")):
        ys = [next(r["alias_22050"] for r in d["context"]
                   if r["context_ms"] == cm and r["btaper_ms"] == bt) for cm in ctxs]
        b.plot(ctxs, ys, mk + "-", color=col, lw=1.0, ms=3.6, label="%d ms" % bt)
    b.set_xscale("log")
    b.set_xticks([50, 100, 200, 400, 800])
    b.set_xticklabels(["50", "100", "200", "400", "800"])
    b.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    b.set_xlabel("Context (ms)")
    b.set_ylabel("Alias at 22.05 kHz (dBc)")
    b.set_ylim(-225, -105)
    b.legend(title="block taper", fontsize=6.6, title_fontsize=6.6,
             loc="upper right", frameon=False, ncol=2, columnspacing=0.9,
             handlelength=1.3, labelspacing=0.3, borderaxespad=0.3)
    clean_axes(a); clean_axes(b)
    panel_letter(a, "a", x=-0.26, y=1.0)
    panel_letter(b, "b", x=-0.17)
    landed_report(fig, p, verbose=False)
    save_all("fig6_params", fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# fig7: streaming -- steady state and the head convention
# ---------------------------------------------------------------------------
def fig7_streaming():
    d = load("stream_data.json")
    cores = d["cores"]
    head = d["head"]
    p = panel(placed_mm=W, height_mm=78)
    apply_style(p)
    fig, (a, b) = plt.subplots(1, 2, figsize=p.figsize, gridspec_kw={"wspace": 0.28})

    ks = [c["k"] for c in cores]
    nd = [c["null_db"] for c in cores]
    a.bar(ks, nd, color=[C["dpggb"] if k < 2 else "#9aa6b2" for k in ks],
          width=0.62, edgecolor="white", lw=0.4)
    a.set_xlabel("Window index (0.5 s)")
    a.set_ylabel("Null depth vs offline (dB)")
    a.set_ylim(0, 330)
    a.set_xticks(ks)
    a.axhline(300, color="#8a8a8a", ls="--", lw=0.7)
    a.text(7.3, 306, "steady state ≈300 dB", fontsize=7.2, color=MUTED, ha="right")
    a.annotate("head convention", xy=(1.0, 108), xytext=(0.15, 155),
               fontsize=7.2, color=INK,
               arrowprops=dict(arrowstyle="-", lw=0.6, color=MUTED))

    ms = [h["ms"] for h in head]
    er = [h["err_db"] for h in head]
    b.plot(ms, er, "-", color=C["dpggb"], lw=1.2)
    b.axvline(20, color="#8a8a8a", ls=":", lw=0.8)
    b.set_xlim(0, 125)
    b.set_ylim(-100, 3)
    b.set_xlabel("Offset from stream head (ms)")
    b.set_ylabel("Error vs offline (dB)")
    b.text(21.5, -12, "20 ms taper", fontsize=7.2, color=MUTED)
    b.annotate("−84 dB at 40 ms", xy=(40, -84), xytext=(52, -58),
               fontsize=7.2, color=INK,
               arrowprops=dict(arrowstyle="-", lw=0.6, color=MUTED))
    clean_axes(a); clean_axes(b)
    panel_letter(a, "a", x=-0.16)
    panel_letter(b, "b", x=-0.16)
    landed_report(fig, p, verbose=False)
    save_all("fig7_streaming", fig)
    plt.close(fig)




# ---------------------------------------------------------------------------
# fig8: streaming throughput and latency across engines
# ---------------------------------------------------------------------------
def fig8_stream_bench():
    d = load("stream_engines.json")
    rows = d["rows"]
    p = panel(placed_mm=W, height_mm=92)
    apply_style(p)
    fig, (a, b) = plt.subplots(1, 2, figsize=p.figsize,
                               gridspec_kw={"wspace": 0.30})

    chunks = d["meta"]["chunks"]
    series = [
        ("dpggb", 1.0, "Deep_PGGB 1.0 s", C["dpggb"], "-", "o"),
        ("soxr", None, "libsoxr", C["soxr"], (0, (5, 1.5)), "s"),
        ("ffmpeg", None, "FFmpeg", C["swr"], (0, (2, 1.4)), "^"),
        ("sox_ng", None, "sox_ng", C["soxng"], (0, (1, 1.2)), "D"),
    ]
    for eng, core, lab, col, ls, mk in series:
        xs, ys = [], []
        for ch in chunks:
            hit = [r for r in rows if r["engine"] == eng and r["chunk"] == ch
                   and (core is None or r["core_s"] == core)]
            if hit:
                xs.append(ch)
                ys.append(hit[0]["throughput_x"])
        a.plot(xs, ys, ls=ls, marker=mk, ms=3.4, lw=1.3, color=col, label=lab)
    a.set_xscale("log", base=2)
    a.set_xticks(chunks)
    a.set_xticklabels([str(c) for c in chunks])
    a.minorticks_off()
    a.set_xlabel("Chunk size (frames)")
    a.set_ylabel("Throughput (× realtime)")
    a.set_yscale("log")
    a.set_yticks([5, 10, 20, 50, 100, 200, 500, 1000])
    a.set_yticklabels(["5", "10", "20", "50", "100", "200", "500", "1000"])
    a.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    a.set_ylim(4, 1500)
    a.legend(fontsize=6.4, loc="lower left", bbox_to_anchor=(0.0, 1.0),
             ncol=2, frameon=False, columnspacing=0.9, handlelength=1.5,
             borderaxespad=0.0, labelspacing=0.3)

    pts = []
    for core, lab, dx, dy, ha, va in ((0.5, "0.5 s", 6, -3, "left", "top"),
                                      (1.0, "1.0 s", -6, 5, "right", "bottom"),
                                      (2.0, "2.0 s", 6, 5, "left", "bottom")):
        hit = [r for r in rows if r["engine"] == "dpggb"
               and r["core_s"] == core and r["chunk"] == 1024][0]
        pts.append((hit["throughput_x"], hit["latency_s"], lab, C["dpggb"], "*", 7.0,
                    dx, dy, ha, va))
    for eng, lab, col, mk in (("soxr", "libsoxr", C["soxr"], "s"),
                              ("ffmpeg", "FFmpeg", C["swr"], "^"),
                              ("sox_ng", "sox_ng", C["soxng"], "D")):
        hit = [r for r in rows if r["engine"] == eng and r["chunk"] == 1024][0]
        if eng == "sox_ng":
            dx, dy, ha, va = -6, 4, "right", "bottom"
        elif eng == "ffmpeg":
            dx, dy, ha, va = 6, -4, "left", "top"
        else:
            dx, dy, ha, va = -6, 5, "right", "bottom"
        pts.append((hit["throughput_x"], hit["latency_s"], lab, col, mk, 4.0,
                    dx, dy, ha, va))
    for x, y, lab, col, mk, ms, dx, dy, ha, va in pts:
        b.plot([x], [y], ls="none", marker=mk, ms=ms, color=col,
               mec="white", mew=0.4, zorder=4)
        b.annotate(lab, xy=(x, y), xytext=(dx, dy), textcoords="offset points",
                   fontsize=6.6, color=INK, ha=ha, va=va)
    off = d["meta"]["offline_speed_x"].get("dpggb")
    if off:
        b.axvline(off, color="#8a8a8a", ls=":", lw=0.8)
        b.text(off * 1.03, 6.0, "offline\n%.1f×" % off, fontsize=6.2,
               color=MUTED, ha="left", va="top")
    b.set_xscale("log")
    b.set_xlim(4, 1000)
    b.set_xticks([5, 10, 20, 50, 100, 200, 1000])
    b.set_xticklabels(["5", "10", "20", "50", "100", "200", "1000"])
    b.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    b.set_yscale("log")
    b.set_ylim(0.012, 12)
    b.set_yticks([0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5])
    b.set_yticklabels(["0.02", "0.05", "0.1", "0.2", "0.5", "1", "2", "5"])
    b.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    b.set_xlabel("Throughput (× realtime)")
    b.set_ylabel("Latency to first output (s)")

    clean_axes(a); clean_axes(b)
    panel_letter(a, "a", x=-0.18, y=1.16)
    panel_letter(b, "b", x=-0.16, y=1.02)
    landed_report(fig, p, verbose=False)
    save_all("fig8_stream_bench", fig)
    plt.close(fig)


if __name__ == "__main__":
    fig1_architecture()
    fig2_spectral()
    fig3_engines()
    fig4_passband()
    fig5_speed()
    fig6_params()
    fig7_streaming()
    fig8_stream_bench()
    print("ALL FIGURES DONE")

