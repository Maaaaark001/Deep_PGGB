# -*- coding: utf-8 -*-
"""Figures for the certified-floor manuscript (work/paper_cert).

Every panel is declared at the width it will occupy on the page (158 mm inside
a 451 pt text block) and drawn at draw_scale = 2, so type, rules and markers all
scale together and the landed size is unchanged.  No panel carries a title: the
caption is the title.  Axis labels are English so that Arial can render them at
the landed size without a CJK fallback.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from hpm.arb import advisor
from nature_style import (panel, apply_style, landed_report, clean_axes,
                          panel_letter, ACADEMIC)

R = Path("hpm/experiments")
OUT = Path("work/paper_cert/figures")
OUT.mkdir(parents=True, exist_ok=True)
SCALE = 2.0

MEAS = "#3d6d9e"        # measured
ANALYTIC = "#c0392b"    # closed form / analytic reference
BASE = "#333333"        # baselines, ceilings
LIGHT = "#dcdcdc"
GREY = "#6f6f6f"

WIN_COLOR = {
    "rect": "#333333", "hann": "#3d6d9e", "hamming": "#c0392b",
    "blackman": "#2e8b6f", "blackmanharris": "#8a6bb0",
    "flattop": "#d08a2c", "nuttall": "#5c8d89",
}
WIN_MARK = {"rect": "o", "hann": "s", "hamming": "^", "blackman": "D",
            "blackmanharris": "v", "flattop": "P", "nuttall": "X"}


def load(name):
    return json.loads((R / name).read_text(encoding="utf-8"))


def new_fig(h_mm, body=9.5):
    p = panel(placed_mm=158, height_mm=h_mm, draw_scale=SCALE, body_pt=body)
    apply_style(p)
    fig = plt.figure(figsize=p.figsize)
    return fig, p


def finish(fig, p, name):
    fig.canvas.draw()
    rows, bad = landed_report(fig, p, verbose=False)
    if bad:
        print("  !! %d text objects out of spec on %s" % (bad, name))
        for lp, dp, cnt, s, st in rows:
            if st == "FAIL":
                print("     %.2f pt landed: %r" % (lp, s))
    fig.savefig(OUT / (name + ".png"), dpi=300, bbox_inches="tight",
                pad_inches=0.02, facecolor="white")
    fig.savefig(OUT / (name + ".pdf"), bbox_inches="tight", pad_inches=0.02,
                facecolor="white")
    plt.close(fig)
    print("wrote", name)


def fs(pt):
    return pt * SCALE


# ------------------------------------------------------------------ figure 1
def fig1():
    fig, p = new_fig(76)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.06], wspace=0.42,
                          left=0.20, right=0.985, top=0.93, bottom=0.155)

    # (a) a reading is bounded by the lowest stage of its chain
    ax = fig.add_subplot(gs[0, 0])
    # The stage ceiling of a chain is the format the output lives in; the reading
    # is what the ruler gets.  Only the last chain sits on its ceiling.
    chains = [("float64 engine", 328.3, 307.16),
              ("80-bit engine", 394.6, 372.90),
              ("binary128 engine", 689.6, 665.52),
              ("binary128 stimulus", 689.6, 689.45)]
    y = np.arange(len(chains))[::-1]
    for yy, (nm, ceil, read) in zip(y, chains):
        ax.barh(yy, ceil, height=0.44, color=LIGHT, edgecolor="#9a9a9a",
                linewidth=0.5, zorder=1)
        ax.barh(yy, read, height=0.44, color=MEAS, zorder=2)
        ax.text(ceil + 12, yy, "%.1f" % read, va="center", fontsize=fs(7.0),
                color="#2b2b2b")
    ax.set_yticks(y)
    ax.set_yticklabels([c[0] for c in chains], fontsize=fs(7.0))
    ax.set_xlim(0, 790)
    ax.set_xlabel("Null depth of a 1 kHz tone (dB)")
    clean_axes(ax, grid_axis="x")
    panel_letter(ax, "a", x=-0.36, y=1.05)
    ax.text(0.02, 1.055, "reading  |  format ceiling", transform=ax.transAxes,
            fontsize=fs(6.8), color=GREY, va="bottom")

    # (b) the decision rule on one real file
    ax = fig.add_subplot(gs[0, 1])
    sat = sorted(load("results_saturation.json"), key=lambda r: r["bits"])
    b = [r["bits"] for r in sat]
    ax.fill_between([b[0] - 1, b[-1] + 1], -1e9, 1e9, where=[True, False],
                    color="none")
    ax.axvspan(b[0] - 2, 140, color="#f2e6e0", zorder=0)
    ax.plot(b, [r["cert"] for r in sat], "o-", color=MEAS, ms=fs(3.4), lw=1.1,
            mfc="white", mew=0.9, zorder=4, label="certificate")
    ax.plot(b, [r["mid"] for r in sat], "s--", color=BASE, ms=fs(2.8), lw=0.9,
            zorder=3, label="midpoint")
    ax.plot(b, [r["ruler"] for r in sat], "^-", color=ANALYTIC, ms=fs(3.4),
            lw=1.0, label="analyser floor")
    ax.axhline(665.522, color=MEAS, lw=0.7, ls=":", zorder=1)
    ax.text(210, 672.0, "engine floor 665.5 dB", fontsize=fs(6.6), color=MEAS)

    ax.set_xlabel("Working precision (bit)")
    ax.set_ylabel("Null depth (dB)")
    ax.set_xlim(b[0] - 2, b[-1] + 4)
    ax.set_ylim(420, 760)
    ax.legend(frameon=False, fontsize=fs(6.8), loc="lower right",
              handlelength=1.6, borderaxespad=0.2)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "b", x=-0.20, y=1.05)
    finish(fig, p, "fig1_cascade")


# ------------------------------------------------------------------ figure 2
def fig2():
    fig, p = new_fig(118)
    gs = fig.add_gridspec(2, 2, wspace=0.34, hspace=0.46,
                          left=0.095, right=0.985, top=0.955, bottom=0.085)
    rr = [r for r in load("results_ruler.json") if "p" in r]

    ax = fig.add_subplot(gs[0, 0])
    cols = ["#3d6d9e", "#2e8b6f", "#d08a2c", "#8a6bb0"]
    marks = ["o", "s", "^", "D"]
    for (N, col, mk) in zip((1024, 4096, 16384, 65536), cols, marks):
        sel = sorted([r for r in rr if r["N"] == N], key=lambda r: r["p"])
        ax.plot([r["p"] for r in sel], [r["null_db"] for r in sel], mk,
                ms=fs(3.2), color=col, label="N = %s" % format(N, ","))
        xs = np.linspace(55, 1000, 60)
        ax.plot(xs, [advisor.certifiable_db(x, N, 1000) for x in xs], "-",
                lw=0.8, color=col, alpha=0.5)
    xs = np.linspace(55, 1000, 60)
    ax.plot(xs, 6.0206 * xs, "--", lw=1.0, color=BASE)
    ax.text(150, 6.0206 * 640, "6.0206 dB/bit", fontsize=fs(6.9), color=BASE,
            rotation=33, rotation_mode="anchor")
    ax.set_xlabel("Working precision (bit)")
    ax.set_ylabel("Certified null (dB)")
    ax.legend(frameon=False, fontsize=fs(6.9), loc="lower right",
              handlelength=1.2, borderaxespad=0.3, ncol=1)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "a", x=-0.20, y=1.05)

    ax = fig.add_subplot(gs[0, 1])
    Ns = [1024, 4096, 16384, 65536, 262144, 1411200]
    x = np.arange(len(Ns))
    bn = np.array([-advisor.budget(400, N)["log2n_db"] for N in Ns])
    bq = np.array([-advisor.budget(400, N)["log2n2_db"] for N in Ns])
    bc = np.array([-advisor.budget(400, N)["constant_db"] for N in Ns])
    ax.bar(x, bn, color="#3d6d9e", width=0.62, label=r"4.49 $\log_2 N$")
    ax.bar(x, bq, bottom=bn, color="#2e8b6f", width=0.62, label=r"0.058 $(\log_2 N)^2$")
    ax.bar(x, bc, bottom=bn + bq, color="#d08a2c", width=0.62, label="constant")
    for i in range(len(Ns)):
        ax.text(i, bn[i] + bq[i] + bc[i] + 4, "%.0f" % (bn[i] + bq[i] + bc[i]),
                ha="center", fontsize=fs(6.8))
    ax.set_xticks(x)
    ax.set_xticklabels(["1k", "4k", "16k", "65k", "262k", "1.4M"])
    ax.set_xlabel("Record length N (samples)")
    ax.set_ylabel("dB below the 2408 dB ceiling")
    ax.set_ylim(0, 185)
    ax.legend(frameon=False, fontsize=fs(6.9), loc="upper left",
              handlelength=1.1, borderaxespad=0.2)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "b", x=-0.20, y=1.05)

    ax = fig.add_subplot(gs[1, 0])
    Ng = np.array([1024, 4096, 16384, 65536, 262144, 1411200])
    lp = np.array([advisor.loss_per_doubling(int(n)) for n in Ng])
    ax.plot(Ng, lp, "o-", color=ANALYTIC, ms=fs(3.4), lw=1.1)
    for n, v in zip(Ng, lp):
        ax.annotate("%.2f" % v, (n, v), textcoords="offset points",
                    xytext=(0, 7), ha="center", fontsize=fs(6.7), color=GREY)
    ax.set_xscale("log", base=2)
    ax.set_xticks([1024, 16384, 262144, 1411200])
    ax.set_xticklabels(["1k", "16k", "262k", "1.4M"])
    ax.set_ylim(5.4, 7.35)
    ax.set_xlabel("Record length N (samples)")
    ax.set_ylabel("Loss per doubling (dB)")
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "c", x=-0.20, y=1.05)

    ax = fig.add_subplot(gs[1, 1])
    ext = load("results_law_ext.json")
    bcol = {240: "#3d6d9e", 480: "#2e8b6f", 960: "#d08a2c",
            1920: "#8a6bb0", 3840: "#5c8d89"}
    for bits, col in bcol.items():
        sel = [r for r in ext if r["p"] == bits]
        if not sel:
            continue
        ax.plot([np.log2(r["N"]) for r in sel], [r["resid_db"] for r in sel],
                "o", ms=fs(4.0), color=col, label="%d bit" % bits)
    ax.axhline(0, color=BASE, lw=0.8, ls="--")
    ax.set_xlabel(r"Record length $\log_2 N$")
    ax.set_ylabel("Measured minus law (dB)")
    ax.set_ylim(-1, 8.6)
    ax.set_xlim(19.4, 23.4)
    ax.legend(frameon=False, fontsize=fs(6.8), ncol=2, loc="upper left",
              handlelength=0.9, borderaxespad=0.2, columnspacing=1.0)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "d", x=-0.20, y=1.05)
    finish(fig, p, "fig2_law")


# ------------------------------------------------------------------ figure 3
def fig3():
    fig, p = new_fig(78)
    gs = fig.add_gridspec(1, 3, wspace=0.44, left=0.085, right=0.985,
                          top=0.92, bottom=0.20)

    win = load("results_window.json")
    names = ["rect", "hann", "hamming", "blackman", "blackmanharris",
             "flattop", "nuttall"]

    ax = fig.add_subplot(gs[0, 0])
    for nm in names:
        sel = sorted([r for r in win if r["window"] == nm], key=lambda r: r["bits"])
        ax.semilogy([r["bits"] for r in sel], [r["wls_db"] for r in sel],
                    WIN_MARK[nm], ms=fs(2.6), color=WIN_COLOR[nm], lw=0,
                    label=nm)
    ax.set_xlabel("Working precision (bit)")
    ax.set_ylabel("Certified null (dB)")
    ax.set_ylim(2e2, 1e4)
    ax.legend(frameon=False, fontsize=fs(6.3), ncol=2, loc="lower right",
              handlelength=0.8, borderaxespad=0.2, columnspacing=0.7,
              labelspacing=0.3)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "a", x=-0.28, y=1.06)

    ax = fig.add_subplot(gs[0, 1])
    xs = [r["leak_closed_db"] for r in win]
    ys = [r["single_bin_db"] for r in win]
    for r in win:
        if r["bits"] != 480:
            continue
        ax.plot(r["leak_closed_db"], r["single_bin_db"], WIN_MARK[r["window"]],
                ms=fs(5.0), color=WIN_COLOR[r["window"]], lw=0,
                label=r["window"])
    lim = (60, 230)
    ax.plot(lim, lim, "--", lw=0.9, color=BASE, zorder=0)
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel(r"Closed form $-20\log_{10}|L(2\omega_0)|$ (dB)")
    ax.set_ylabel("Measured single-bin floor (dB)")
    ax.legend(frameon=False, fontsize=fs(6.0), loc="upper left",
              handlelength=0.8, borderaxespad=0.2, labelspacing=0.25,
              columnspacing=0.8, ncol=2)
    clean_axes(ax, box=True, grid_axis=None)
    panel_letter(ax, "b", x=-0.30, y=1.06)

    ax = fig.add_subplot(gs[0, 2])
    dp = load("results_dpss.json")
    for N, col, mk in ((128, "#3d6d9e", "o"), (256, "#2e8b6f", "s"),
                       (512, "#d08a2c", "^")):
        sel = sorted([r for r in dp if r["N"] == N], key=lambda r: r["NW"])
        ax.plot([r["NW"] for r in sel], [r["leak_db"] for r in sel], mk + "-",
                ms=fs(3.0), lw=0.9, color=col, label="N = %d" % N)
    ax.set_xlabel(r"Time--bandwidth product $NW$")
    ax.set_ylabel("DPSS leakage bound (dB)")
    ax.legend(frameon=False, fontsize=fs(6.4), loc="lower left",
              handlelength=1.2, borderaxespad=0.3)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "c", x=-0.30, y=1.06)
    finish(fig, p, "fig3_window")


# ------------------------------------------------------------------ figure 4
def fig4():
    fig, p = new_fig(76)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.12], wspace=0.34,
                          left=0.085, right=0.985, top=0.92, bottom=0.20)

    mt = load("results_multitone.json")
    ax = fig.add_subplot(gs[0, 0])
    xs, ys, cols = [], [], []
    for row, col in zip(mt, ["#3d6d9e", "#2e8b6f", "#c0392b"]):
        for r in row["rows"]:
            xs.append(r["pred_db"])
            ys.append(r["meas_db"])
            cols.append(col)
    ax.plot([-215, -85], [-215, -85], "--", lw=0.9, color=BASE, zorder=0)
    for c in ["#3d6d9e", "#2e8b6f", "#c0392b"]:
        sel = [(x, y) for x, y, cc in zip(xs, ys, cols) if cc == c]
        ax.plot([s[0] for s in sel], [s[1] for s in sel], "o", ms=fs(2.6),
                color=c, lw=0, label=r"$a_3$ = %s" % {"#3d6d9e": r"$10^{-3}$",
                                                      "#2e8b6f": r"$10^{-5}$",
                                                      "#c0392b": r"$10^{-7}$"}[c])
    ax.set_xlim(-215, -85)
    ax.set_ylim(-215, -85)
    ax.set_xlabel("Analytic level (dBc)")
    ax.set_ylabel("Measured level (dBc)")
    ax.legend(frameon=False, fontsize=fs(6.6), loc="upper left",
              handlelength=0.8, borderaxespad=0.3, labelspacing=0.3)
    clean_axes(ax, box=True, grid_axis=None)
    panel_letter(ax, "a", x=-0.24, y=1.06)

    ax = fig.add_subplot(gs[0, 1])
    rows = [r for r in mt if abs(r["a3"] - 1e-7) < 1e-12][0]["rows"]
    f = [r["f"] for r in rows]
    lv = [r["meas_db"] for r in rows]
    ax.vlines(f, -232, lv, color="#9fb6c9", lw=0.8, zorder=1)
    ax.plot(f, lv, "o", ms=fs(2.6), color=MEAS, zorder=2)
    ax.axhline(-172.96, color=ANALYTIC, lw=0.8, ls="--", zorder=1)
    ax.text(4100, -172.2, "strongest product, 172.96 dBc", fontsize=fs(6.5),
            color=ANALYTIC)
    ax.axhline(-162.58, color=GREY, lw=0.7, ls=":", zorder=1)
    ax.text(4100, -161.4, "sum of all 58 products, 162.58 dBc",
            fontsize=fs(6.5), color=GREY)
    ax.set_xlim(4000, 22000)
    ax.set_ylim(-232, -160)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Third-order product level (dBc)")
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "b", x=-0.20, y=1.06)
    finish(fig, p, "fig5_multitone")


# ------------------------------------------------------------------ figure 6
def fig6():
    fig, p = new_fig(78)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.0, 1.0, 1.0], wspace=0.46,
                          left=0.105, right=0.985, top=0.92, bottom=0.20)

    # One ideal 1001 Hz sine, generated at 1200 bit and rounded five ways.  The
    # bars are each format's own quantisation floor; the dots are what the ruler
    # reads.  They coincide to 0.11 dB, so the ladder measures the formats.
    lad = load("results_ladder2.json")
    ax = fig.add_subplot(gs[0, 0])
    y = np.arange(len(lad))[::-1]
    vals = [r["cert_db"] for r in lad]
    fl = [r["floor_db"] for r in lad]
    ax.barh(y, fl, height=0.58, color=LIGHT, edgecolor="#9a9a9a", linewidth=0.5,
            zorder=1)
    ax.plot(vals, y, "o", ms=fs(3.4), color=MEAS, zorder=3)
    for yy, v in zip(y, vals):
        ax.text(v + 14, yy, "%.1f" % v, va="center", fontsize=fs(6.6))
    ax.set_yticks(y)
    ax.set_yticklabels([r["name"] for r in lad], fontsize=fs(6.9))
    ax.set_xlim(0, 790)
    ax.set_xlabel("Certified null (dB)")
    clean_axes(ax, grid_axis="x")
    ax.text(0.03, 1.045, "format floor  |  reading", transform=ax.transAxes,
            fontsize=fs(6.4), color=GREY, va="bottom")
    panel_letter(ax, "a", x=-0.34, y=1.10)

    ax = fig.add_subplot(gs[0, 1])
    wc = load("results_wallcal.json")
    for fmt, col, mk in (("f128", "#c0392b", "o"), ("f64", "#3d6d9e", "s")):
        sel = sorted([r for r in wc if r["fmt"] == fmt], key=lambda r: r["bits"])
        b = np.array([r["bits"] for r in sel], float)
        u = np.array([r["us_per_sample"] for r in sel], float)
        A = np.vstack([np.ones_like(b), b]).T
        c0, c1 = np.linalg.lstsq(A, u, rcond=None)[0]
        ax.plot(b, u, mk, ms=fs(3.2), color=col, lw=0,
                label="%s: %.2f + %.4f p" % ("binary128" if fmt == "f128" else "float64", c0, c1))
        xx = np.linspace(80, 820, 20)
        ax.plot(xx, c0 + c1 * xx, "-", lw=0.9, color=col)
        print("  wall fit %s: %.3f + %.5f*bits us/sample/pass" % (fmt, c0, c1))
    ax.set_xlabel("Working precision (bit)")
    ax.set_ylabel(r"Cost ($\mu$s sample$^{-1}$ pass$^{-1}$)")
    ax.legend(frameon=False, fontsize=fs(6.2), loc="upper left",
              handlelength=1.0, borderaxespad=0.3, labelspacing=0.3)
    ax.set_ylim(0, 21)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "b", x=-0.30, y=1.06)

    ax = fig.add_subplot(gs[0, 2])
    v2 = load("results_validate2.json")
    xs = [r["wall_pred"] for r in v2]
    ys = [r["wall_s"] for r in v2]
    ax.plot([0.005, 3], [0.005, 3], "--", lw=0.9, color=BASE, zorder=0)
    ax.plot(xs, ys, "o", ms=fs(3.6), color=MEAS)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(0.008, 3)
    ax.set_ylim(0.008, 3)
    ax.set_xlabel("Predicted time (s)")
    ax.set_ylabel("Measured time (s)")
    clean_axes(ax, box=True, grid_axis=None)
    panel_letter(ax, "c", x=-0.30, y=1.06)
    finish(fig, p, "fig6_engine")


# ------------------------------------------------------------------ figure 5
def fig5():
    """Two ceilings: the estimator's (length-dependent) and the file's (not)."""
    fig, p = new_fig(76)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.18, 1.0], wspace=0.34,
                          left=0.085, right=0.985, top=0.92, bottom=0.20)

    G = load("results_guard2.json")
    P_STIM = [120, 240, 360, 480]
    PCOL = {120: "#333333", 240: "#3d6d9e", 360: "#2e8b6f", 480: "#d08a2c"}
    PMK = {120: "o", 240: "s", 360: "^", 480: "D"}
    NFIX = 4096

    ax = fig.add_subplot(gs[0, 0])
    for ps in P_STIM:
        sel = sorted([r for r in G if r["N"] == NFIX and r["p_stim"] == ps],
                     key=lambda r: r["p_eff"])
        ax.plot([r["p_eff"] for r in sel], [r["null_db"] for r in sel],
                PMK[ps] + "-", ms=fs(3.0), lw=0.9, color=PCOL[ps],
                label=r"$p_{\rm stim}$ = %d" % ps)
        cap = 6.0199 * ps - 30.5
        ax.plot([240, 660], [cap, cap], ":", lw=0.9, color=PCOL[ps], alpha=0.85)
    xx = np.linspace(240, 660, 40)
    ax.plot(xx, [advisor.certifiable_db(x, NFIX, 1000) for x in xx], "--",
            lw=1.1, color=BASE, label="estimator law")
    ax.set_xlabel(r"Effective precision $p_{\rm eff}=p+$ guard (bit)")
    ax.set_ylabel("Certified null (dB)")
    ax.set_xlim(230, 660)
    ax.set_ylim(600, 3050)
    ax.legend(frameon=False, fontsize=fs(6.4), loc="upper left",
              handlelength=1.5, borderaxespad=0.3, labelspacing=0.3)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "a", x=-0.21, y=1.06)

    ax = fig.add_subplot(gs[0, 1])
    ps_all = sorted({r["p_stim"] for r in G})
    # the two record lengths land on the same plateau, so they are drawn with a
    # small horizontal offset and that coincidence is the point of the panel
    for N, mk, col, off in ((1024, "o", "#3d6d9e", -3.2), (4096, "s", "#c0392b", 3.2)):
        xs, ys = [], []
        for ps in ps_all:
            sel = sorted([r for r in G if r["N"] == N and r["p_stim"] == ps],
                         key=lambda r: r["guard"])
            if not sel:
                continue
            last = sel[-1]
            # only take a point that has actually stopped moving
            if len(sel) > 1 and abs(last["null_db"] - sel[-2]["null_db"]) > 0.5:
                continue
            xs.append(ps + off)
            ys.append(last["null_db"])
        ax.plot(xs, ys, mk, ms=fs(4.0), color=col, lw=0, zorder=3,
                label="N = %s" % format(N, ","))
    px = np.linspace(100, 500, 20)
    ax.plot(px, 6.0199 * px - 30.5, "-", lw=1.0, color=BASE,
            label=r"$6.02\,p_{\rm stim}-30.5$")
    ax.set_xlabel(r"Stimulus precision $p_{\rm stim}$ (bit)")
    ax.set_ylabel("Plateau of the certificate (dB)")
    ax.set_xlim(95, 505)
    ax.legend(frameon=False, fontsize=fs(6.5), loc="upper left",
              handlelength=1.2, borderaxespad=0.3, labelspacing=0.35)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "b", x=-0.24, y=1.06)
    finish(fig, p, "fig4_guard")


if __name__ == "__main__":
    fig1()
    fig2()
    fig3()
    fig4()
    fig5()
    fig6()
