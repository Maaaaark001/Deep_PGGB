# -*- coding: utf-8 -*-
"""Main figures for the certified-measurement paper.

Every panel is declared at the width it will occupy on the page (180 mm,
double column) and rendered at draw_scale = 2 for comfortable preview; type,
rules and markers all scale together, so the landed size is unchanged.
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
                          panel_letter, save_all, set_outdir, ACADEMIC,
                          COLOR_SIM, COLOR_REAL, COLOR_BASELINE)

R = Path("hpm/experiments")
OUT = Path("work/paper_hpm/figures")
OUT.mkdir(parents=True, exist_ok=True)
SCALE = 2.0
C = ACADEMIC                      # #E64B35, #4DBBD5, #00A087, #3C5488, #F39B7F, #8491B4
GREY = "#555555"


def load(name):
    return json.loads((R / name).read_text(encoding="utf-8"))


def leg(ax, items, **kw):
    """Draw a legend with large markers and thin handles so it stays legible at 1x."""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    hs = []
    for it in items:
        kind, col, lab = it[0], it[1], it[2]
        mk = it[3] if len(it) > 3 else "o"
        if kind == "line":
            hs.append(Line2D([], [], color=col, marker=mk, ms=2*5.2, lw=1.6,
                             label=lab))
        else:
            hs.append(Patch(facecolor=col, edgecolor="none", label=lab))
    ax.legend(handles=hs, frameon=False, **kw)


def new_fig(height_mm):
    p = panel(placed_mm=158, height_mm=height_mm * 158 / 180.0, draw_scale=SCALE,
              body_pt=9.5)
    apply_style(p)
    fig = plt.figure(figsize=p.figsize)
    return fig, p


def finish(fig, p, name):
    fig.canvas.draw()
    landed_report(fig, p, verbose=False)
    fig.savefig(OUT / (name + ".png"), dpi=300, bbox_inches="tight", pad_inches=0.02)
    fig.savefig(OUT / (name + ".pdf"), bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print("wrote", name)


# ---------------------------------------------------------------- figure 1
def fig1():
    fig, p = new_fig(88)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.05], wspace=0.32,
                          left=0.085, right=0.985, top=0.90, bottom=0.15)

    # (a) reading = min(stage ceiling)
    ax = fig.add_subplot(gs[0, 0])
    chains = [("float64", 328.1, 307.16), ("80-bit I/O", 394.6, 372.90),
              ("binary128", 440.2, 440.21), ("quad ruler", 686.4, 686.39)]
    y = np.arange(len(chains))[::-1]
    for yy, (nm, ceil, read) in zip(y, chains):
        ax.barh(yy, ceil, height=0.46, color="#dcdcdc", edgecolor="#9a9a9a",
                linewidth=0.5, zorder=1)
        ax.barh(yy, read, height=0.46, color=COLOR_REAL, zorder=2)
        ax.text(max(ceil, read) + 10, yy, f"{read:.1f} / {ceil:.0f}", va="center",
                fontsize=2*7.2, color="#333333")
    ax.set_yticks(y)
    ax.set_yticklabels([c[0] for c in chains])
    ax.set_xlim(0, 790)
    ax.set_xlabel("null of a 1 kHz tone (dB)")
    ax.set_title("reading = the lowest stage", loc="left")
    clean_axes(ax, grid_axis="x")
    panel_letter(ax, "a")

    # (b) the estimator, not the data, sets the leakage floor
    ax = fig.add_subplot(gs[0, 1])
    fl = load("results_arb.json") if (R / "results_arb.json").exists() else {}
    bits = np.array([60, 120, 240, 480, 960, 1920, 3840])
    coh = np.array([276.78, 638.02, 1360.50, 2805.44, 5695.33, 11475.10, 23032.15])
    ax.semilogy(bits, coh, "o-", color=COLOR_REAL, ms=2*3.4, lw=1.1,
                label="full normal equations")
    ax.semilogy(bits, np.full_like(bits, 71.9, dtype=float), "s--", color=C[0],
                ms=2*3.2, lw=1.0, label="single-bin projection")
    ax.axhline(1164.2, color=COLOR_SIM, lw=0.8, ls=":", zorder=1)
    ax.text(70, 1500, "windowed fit, coherent", fontsize=2*7.2, color=COLOR_SIM)
    ax.set_xscale("log", base=2)
    ax.set_xticks([60, 240, 960, 3840])
    ax.set_xticklabels(["60", "240", "960", "3840"])
    ax.set_xlabel("working precision (bit)")
    ax.set_ylabel("null of 1000.5 Hz in 8 kHz (dB)")
    ax.set_ylim(30, 1e5)
    ax.set_title("same non-coherent data, two estimators", loc="left")
    leg(ax, [("line", COLOR_REAL, "full normal equations", "o"),
             ("line", C[0], "single-bin projection", "s")],
        loc="upper left", fontsize=2*7.6)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "b")
    finish(fig, p, "fig1_cascade")


# ---------------------------------------------------------------- figure 2
def fig2():
    fig, p = new_fig(150)
    gs = fig.add_gridspec(2, 2, wspace=0.30, hspace=0.42,
                          left=0.085, right=0.985, top=0.94, bottom=0.09)

    rr = [r for r in load("results_ruler.json") if "p" in r]

    # (a) certificate vs precision, four lengths, plus the law
    ax = fig.add_subplot(gs[0, 0])
    for N, col, mk in ((1024, C[3], "o"), (4096, C[1], "s"),
                       (16384, C[2], "^"), (65536, C[4], "d")):
        sel = [r for r in rr if r["N"] == N]
        ax.plot([r["p"] for r in sel], [r["null_db"] for r in sel], mk, ms=2*3.2,
                color=col, label=f"N = {N:,}")
        xs = np.linspace(55, 1000, 60)
        ax.plot(xs, [advisor.certifiable_db(x, N, 1000) for x in xs], "-", lw=0.8,
                color=col, alpha=0.55)
    xs = np.linspace(55, 1000, 60)
    ax.plot(xs, 6.0206 * xs, "-", lw=1.0, color=COLOR_BASELINE, ls="--")
    ax.text(120, 6.0206 * 700, "6.0206 dB/bit", fontsize=2*7.2, color=COLOR_BASELINE,
            rotation=34, rotation_mode="anchor")
    ax.set_xlabel("working precision (bit)")
    ax.set_ylabel("certified null (dB)")
    ax.set_title("certificate tracks the arithmetic ceiling", loc="left")
    leg(ax, [("line", C[3], "N = 1,024", "o"), ("line", C[1], "N = 4,096", "s"),
             ("line", C[2], "N = 16,384", "^"), ("line", C[4], "N = 65,536", "d")],
        fontsize=2*7.4, loc="lower right")
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "a")

    # (b) the length bill at fixed precision
    ax = fig.add_subplot(gs[0, 1])
    Ns = [1024, 4096, 16384, 65536, 262144, 1411200]
    x = np.arange(len(Ns))
    bn = np.array([-advisor.budget(400, N)["log2n_db"] for N in Ns])
    bq = np.array([-advisor.budget(400, N)["log2n2_db"] for N in Ns])
    bc = np.array([-advisor.budget(400, N)["constant_db"] for N in Ns])
    ax.bar(x, bn, color=C[1], width=0.62, label="20 log$_{10}$N")
    ax.bar(x, bq, bottom=bn, color=C[2], width=0.62, label="length$^2$")
    ax.bar(x, bc, bottom=bn + bq, color=C[4], width=0.62, label="constant")
    for i in range(len(Ns)):
        tot = bn[i] + bq[i] + bc[i]
        ax.text(i, tot + 4, f"{tot:.0f}", ha="center", fontsize=2*7.2)
    ax.set_xticks(x)
    ax.set_xticklabels(["1k", "4k", "16k", "65k", "262k", "1.4M"])
    ax.set_xlabel("record length N (samples)")
    ax.set_ylabel("dB lost below the ceiling")
    ax.set_ylim(0, 185)
    ax.set_title("at 400 bit, a long record costs 127 dB", loc="left")
    leg(ax, [("patch", C[1], "20 log$_{10}$N"), ("patch", C[2], "length$^2$"),
             ("patch", C[4], "constant")], fontsize=2*7.4, loc="upper left", ncol=1)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "b")

    # (c) loss per doubling rises with N
    ax = fig.add_subplot(gs[1, 0])
    Ng = np.array([1024, 4096, 16384, 65536, 262144, 1411200])
    lp = np.array([advisor.loss_per_doubling(int(n)) for n in Ng])
    ax.plot(Ng, lp, "o-", color=C[0], ms=2*3.6, lw=1.1)
    for n, v in zip(Ng, lp):
        ax.annotate(f"{v:.2f}", (n, v), textcoords="offset points", xytext=(0, 7),
                    ha="center", fontsize=2*7.0, color=GREY)
    ax.set_xscale("log", base=2)
    ax.set_xticks([1024, 16384, 262144, 1411200])
    ax.set_xticklabels(["1k", "16k", "262k", "1.4M"])
    ax.set_ylim(5.4, 7.3)
    ax.set_xlabel("record length N (samples)")
    ax.set_ylabel("loss per doubling (dB)")
    ax.set_title("the price of length is itself growing", loc="left")
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "c")

    # (d) extrapolation: the law stays conservative
    ax = fig.add_subplot(gs[1, 1])
    ext = load("results_law_ext.json")
    bcol = {240: C[3], 480: C[1], 960: C[2], 1920: C[4], 3840: "#8064a2"}
    for p, col in bcol.items():
        sel = [r for r in ext if r["p"] == p]
        if not sel:
            continue
        ax.plot([np.log2(r["N"]) for r in sel], [r["resid_db"] for r in sel], "o",
                ms=2*4.2, color=col, label=f"{p} bit")
    ax.axhline(0, color=COLOR_BASELINE, lw=0.8, ls="--")
    ax.set_xlabel("record length log$_{2}$N")
    ax.set_ylabel("measured − law (dB)")
    ax.set_ylim(-1, 8.5)
    ax.set_xlim(19, 23.5)
    ax.set_title("every extrapolation is conservative", loc="left")
    leg(ax, [("line", bcol[k], f"{k} bit", "o") for k in (240, 480, 960, 1920, 3840)],
        fontsize=2*7.2, loc="upper left", ncol=2, columnspacing=0.8, labelspacing=0.3)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "d")
    finish(fig, p, "fig2_law")


# ---------------------------------------------------------------- figure 3
def fig3():
    fig, p = new_fig(80)
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1], wspace=0.36,
                          left=0.075, right=0.985, top=0.90, bottom=0.17)

    win = load("results_window.json")
    names = ["rect", "hann", "hamming", "blackman", "blackmanharris", "flattop", "nuttall"]
    cols = [C[3], C[1], C[2], C[4], C[0], "#8064a2", "#7f7f7f"]

    # (a) window as weight: neutral
    ax = fig.add_subplot(gs[0, 0])
    for nm, col in zip(names, cols):
        sel = sorted([r for r in win if r["window"] == nm], key=lambda r: r["bits"])
        ax.semilogy([r["bits"] for r in sel], [r["wls_db"] for r in sel], "o-",
                    ms=2*3.8, lw=1.1, color=col, label=nm)
    ax.set_xlabel("working precision (bit)")
    ax.set_ylabel("certified null (dB)")
    ax.set_title("window as weight", loc="left")
    ax.text(0.04, 0.94, "seven windows overlap\nwithin 2 dB", transform=ax.transAxes,
            fontsize=2*7.0, color="#333333", va="top")
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "a", x=-0.22)

    # (b) window as transform: flat
    ax = fig.add_subplot(gs[0, 1])
    for nm, col in zip(names, cols):
        sel = sorted([r for r in win if r["window"] == nm], key=lambda r: r["bits"])
        ax.plot([r["bits"] for r in sel], [r["single_bin_db"] for r in sel], "o-",
                ms=2*3.8, lw=1.1, color=col)
    ax.set_xlabel("working precision (bit)")
    ax.set_ylabel("single-bin null (dB)")
    ax.set_ylim(0, 38)
    ax.set_title("window as transform", loc="left")
    ax.text(0.04, 0.72, "seven windows, 60→480 bit,\nno reading moves",
            transform=ax.transAxes, fontsize=2*6.8, color=GREY, va="top")
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "b", x=-0.22)

    # (c) DPSS leakage bound
    ax = fig.add_subplot(gs[0, 2])
    dp = load("results_dpss.json")
    for N, col, mk in ((128, C[3], "o"), (256, C[1], "s"), (512, C[2], "^"),
                       (1024, C[4], "d")):
        sel = sorted([r for r in dp if r["N"] == N], key=lambda r: r["NW"])
        ax.plot([r["NW"] for r in sel], [r["leak_db"] for r in sel], mk + "-",
                ms=2*4.2, lw=1.1, color=col, label=f"N = {N}")
    ax.set_xlabel("time–bandwidth product NW")
    ax.set_ylabel("leakage upper bound (dB)")
    ax.set_title("DPSS, certified", loc="left")
    leg(ax, [("line", C[3], "N = 128", "o"), ("line", C[1], "N = 256", "s"),
             ("line", C[2], "N = 512", "^"), ("line", C[4], "N = 1,024", "d")],
        fontsize=2*7.0, loc="lower left", ncol=1, handlelength=1.4,
        columnspacing=0.8, labelspacing=0.35)
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "c", x=-0.22)
    finish(fig, p, "fig3_window")


# ---------------------------------------------------------------- figure 4
def fig4():
    fig, p = new_fig(84)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.15], wspace=0.30,
                          left=0.085, right=0.985, top=0.90, bottom=0.16)

    mt = load("results_multitone.json")
    ax = fig.add_subplot(gs[0, 0])
    cols = {0.001: C[3], 1e-05: C[1], 1e-07: C[2]}
    for blk in mt:
        a3 = blk["a3"]
        rows = [r for r in blk["rows"] if np.isfinite(r["pred_db"])]
        pr = [r["pred_db"] for r in rows]
        ms = [r["meas_db"] for r in rows]
        ax.plot(pr, ms, "o", ms=2*4.2, color=cols.get(a3, GREY),
                label=f"$a_3$ = {a3:g}")
    lo, hi = -185, -80
    ax.plot([lo, hi], [lo, hi], "--", lw=0.9, color=COLOR_BASELINE)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("predicted product level (dBc)")
    ax.set_ylabel("measured product level (dBc)")
    ax.set_title("42 generated products, one model", loc="left")
    ax.text(0.96, 0.06, "16 even-order bins sit at the floor",
            transform=ax.transAxes, fontsize=2*7.0, color=GREY, ha="right")
    leg(ax, [("line", C[3], "$a_3$ = 0.001", "o"),
             ("line", C[1], "$a_3$ = 1e−5", "o"),
             ("line", C[2], "$a_3$ = 1e−7", "o")], fontsize=2*7.4, loc="upper left")
    clean_axes(ax, grid_axis="both")
    panel_letter(ax, "a")

    ax = fig.add_subplot(gs[0, 1])
    blk = [b for b in mt if abs(b["a3"] - 1e-07) < 1e-12][0]
    f = np.array([r["f"] for r in blk["rows"]])
    v = np.array([r["meas_db"] for r in blk["rows"]])
    order = np.argsort(f)
    f, v = f[order], v[order]
    ax.vlines(f, -230, v, color="#b0b0b0", lw=0.7)
    ax.plot(f, v, "o", ms=2*3.8, color=C[3])
    ax.axhline(blk["null_db"] * -1, color=COLOR_SIM, lw=0.8, ls=":")
    ax.text(2000, -blk["null_db"] + 5, "total distortion", fontsize=2*7.0,
            color=COLOR_SIM)
    ax.set_ylim(-235, -60)
    ax.set_xlabel("output frequency (Hz)")
    ax.set_ylabel("product level (dBc)")
    ax.set_title("$a_3$ = 1e−7, four tones", loc="left")
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "b")
    finish(fig, p, "fig4_multitone")


# ---------------------------------------------------------------- figure 5
def fig5():
    fig, p = new_fig(80)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.15, 1.05, 0.95], wspace=0.46,
                          left=0.135, right=0.985, top=0.86, bottom=0.17)

    # (a) representation ladder
    ax = fig.add_subplot(gs[0, 0])
    lad = {r["name"]: r["cert"] for r in load("results_ladder.json")}
    rows = [("binary128", lad["_eng16.f128"]), ("float64", lad["_eng16.f64"]),
            ("float32", lad["_eng16.wav"]), ("PCM 24", lad["_eng16_pcm24.wav"]),
            ("PCM 16", lad["_eng16_pcm16.wav"])]
    y = np.arange(len(rows))[::-1]
    for yy, (nm, v) in zip(y, rows):
        ax.barh(yy, v, height=0.55, color=COLOR_REAL, alpha=0.9)
        ax.text(v + 10, yy, f"{v:.1f}", va="center", fontsize=2*7.8, color="#222222")
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlim(0, 560)
    ax.set_xlabel("certified null (dB)")
    ax.set_title("same tone, five formats", loc="left")
    clean_axes(ax, grid_axis="x")
    panel_letter(ax, "a", x=-0.22)

    # (b) saturation sweep with the regime
    ax = fig.add_subplot(gs[0, 1])
    sat = load("results_saturation.json")
    b = [r["bits"] for r in sat]
    ax.plot(b, [r["mid"] for r in sat], "s--", ms=2*4.6, lw=1.0, color=COLOR_SIM,
            mfc="none", mew=1.2, label="midpoint")
    ax.plot(b, [r["cert"] for r in sat], "o-", ms=2*4.6, lw=1.4, color=COLOR_REAL,
            label="certificate")
    ax.plot(b, [r["ruler"] for r in sat], "^-", ms=2*3.8, lw=1.1, color=GREY,
            label="ruler")
    ax.set_xlabel("working precision (bit)")
    ax.set_ylabel("dB")
    ax.set_title("saturation of a real file", loc="left")
    ax.set_ylim(418, 610)
    ax.set_yticks([420, 460, 500, 540, 580])
    leg(ax, [("line", COLOR_REAL, "certificate", "o"),
             ("line", COLOR_SIM, "midpoint", "s"),
             ("line", GREY, "ruler", "^")], fontsize=2*7.4, loc="upper left")
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "b", x=-0.20)

    # (c) advisor validation
    ax = fig.add_subplot(gs[0, 2])
    v2 = load("results_validate2.json")
    T = np.array([r["T"] for r in v2])
    M = np.array([r["measured"] for r in v2])
    ax.plot([0, 3200], [0, 3200], "--", lw=0.9, color=COLOR_BASELINE)
    ax.plot(T, M, "o", ms=2*4.2, color=COLOR_REAL)
    ax.set_xlim(0, 3200)
    ax.set_ylim(0, 3200)
    ax.set_xticks([0, 1000, 2000, 3000])
    ax.set_yticks([0, 1000, 2000, 3000])
    ax.set_xlabel("target (dB)")
    ax.set_ylabel("measured (dB)")
    ax.set_title("advisor", loc="left")
    ax.text(0.95, 0.07, "all nine above target\nby +1.6 to +4.8 dB", transform=ax.transAxes,
            fontsize=2*7.2, ha="right", va="bottom", color="#333333")
    clean_axes(ax, grid_axis="both")
    panel_letter(ax, "c", x=-0.28)
    finish(fig, p, "fig5_ladder")


# ---------------------------------------------------------------- figure 6
def fig6():
    fig, p = new_fig(78)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.12, 1.0], wspace=0.34,
                          left=0.155, right=0.985, top=0.90, bottom=0.17)

    # (a) the analyser's wall clock is affine in precision, not proportional
    ax = fig.add_subplot(gs[0, 0])
    cal = load("results_wallcal.json")
    for fmt, col, mk, lab in (("f128", C[3], "o", "binary128 input"),
                              ("f64", C[1], "s", "float64 input")):
        sel = [r for r in cal if r["fmt"] == fmt]
        b = np.array([r["bits"] for r in sel], float)
        v = np.array([r["us_per_sample"] for r in sel])
        ax.plot(b, v, mk, ms=2*5.2, color=col, label=lab)
        sl, ic = np.polyfit(b, v, 1)
        xs = np.linspace(60, 860, 40)
        ax.plot(xs, ic + sl * xs, "-", lw=0.9, color=col, alpha=0.55)
    ax.text(230, 12.6, "6.34 + 0.0131·p", fontsize=2*7.2, color=C[3])
    ax.text(230, 4.0, "3.38 + 0.0133·p", fontsize=2*7.2, color=C[1])
    ax.set_xlabel("working precision (bit)")
    ax.set_ylabel("cost (µs per sample per pass)")
    ax.set_ylim(0, 19)
    ax.set_title("cost is affine in precision", loc="left")
    leg(ax, [("line", C[3], "binary128 input", "o"),
             ("line", C[1], "float64 input", "s")], fontsize=2*7.6, loc="upper left")
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "a", x=-0.26)

    # (b) what precision costs the device under test
    ax = fig.add_subplot(gs[0, 1])
    lab = ["float64", "80-bit I/O", "binary128"]
    thr = [201.19, 88.07, 2.43]
    nul = [307.16, 372.90, 440.21]
    y = np.arange(3)[::-1]
    ax.hlines(y, 1, thr, color="#b0b0b0", lw=0.9)
    ax.plot(thr, y, "o", ms=2*6.0, color=C[3])
    for yy, t, n in zip(y, thr, nul):
        ax.text(t * 1.22, yy + 0.10, f"{t:.1f}×", va="bottom", fontsize=2*7.6)
        ax.text(t * 1.22, yy - 0.10, f"{n:.0f} dB", va="top", fontsize=2*7.0, color=GREY)
    ax.set_xscale("log")
    ax.set_yticks(y)
    ax.set_yticklabels(lab, fontsize=2*7.6)
    ax.set_xlim(1, 2200)
    ax.set_ylim(-0.75, 2.6)
    ax.set_xlabel("throughput (× realtime)")
    ax.set_title("83× the time for 133 dB", loc="left")
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "b", x=-0.24)
    finish(fig, p, "fig6_cost")


if __name__ == "__main__":
    set_outdir(OUT)
    fig1(); fig2(); fig3(); fig4(); fig5(); fig6()
    print("figures in", OUT)
