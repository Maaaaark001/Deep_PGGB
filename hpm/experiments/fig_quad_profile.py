# -*- coding: utf-8 -*-
"""Figures for the binary128 distortion profile (hpm/reports).

Same conventions as fig_paper2.py: every panel is declared at the width it lands
at (158 mm), drawn at draw_scale = 2, no panel titles, Arial axis labels.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from nature_style import (panel, apply_style, landed_report, clean_axes,
                          panel_letter)

R = Path("hpm/experiments")
OUT = Path("hpm/reports/figs")
OUT.mkdir(parents=True, exist_ok=True)
SCALE = 2.0

MEAS = "#3d6d9e"
ANALYTIC = "#c0392b"
BASE = "#333333"
LIGHT = "#dcdcdc"
GREY = "#6f6f6f"
GREEN = "#2e8b6f"
ORANGE = "#d08a2c"

D = json.loads((R / "results_quad_profile.json").read_text(encoding="utf-8"))


def new_fig(h_mm, body=9.5):
    p = panel(placed_mm=158, height_mm=h_mm, draw_scale=SCALE, body_pt=body)
    apply_style(p)
    return plt.figure(figsize=p.figsize), p


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


def profile():
    fig, p = new_fig(132)
    gs = fig.add_gridspec(2, 2, wspace=0.52, hspace=0.50,
                          left=0.115, right=0.905, top=0.955, bottom=0.095)

    # ---------------------------------------------------------- (a) frequency
    ax = fig.add_subplot(gs[0, 0])
    rows = D["freq_sweep"]
    f = np.array([r["f"] for r in rows], dtype=float)
    st = np.array([r["settled"] for r in rows])
    wo = np.array([r["worst"] for r in rows])
    ax.plot(f, st, "o-", color=MEAS, ms=fs(3.0), lw=1.1, mfc="white", mew=0.9,
            label="settled")
    ax.plot(f, wo, "s--", color=ANALYTIC, ms=fs(2.4), lw=0.9, mfc="none",
            label="worst 1 s")
    ax.set_xscale("log")
    ax.set_xlabel("Tone frequency (Hz)")
    ax.set_ylabel("Null depth (dB)")
    ax.set_xlim(15, 30000)
    ax.set_ylim(280, 726)
    ax.set_xticks([20, 100, 1000, 10000])
    ax.set_xticklabels(["20", "100", "1k", "10k"])
    ax.axhspan(660, 672, color="#eef2f6", zorder=0)
    ax.text(17, 690, "engine floor", fontsize=fs(6.2), color=GREY,
            va="center", ha="left")
    ax2 = ax.twinx()
    ax2.plot(f, [r["enob"] for r in rows], ":", color=GREEN, lw=1.2)
    ax2.set_ylabel("ENOB (bit)", color=GREEN, labelpad=1.5)
    ax2.tick_params(axis="y", colors=GREEN, labelsize=fs(6.8), pad=1.5)
    ax2.set_ylim(40, 126)
    ax2.spines["right"].set_color(GREEN)
    ax2.spines["top"].set_visible(False)
    ax.legend(frameon=False, fontsize=fs(6.4), loc="lower left",
              handlelength=1.5, borderaxespad=0.15, title="null depth",
              title_fontsize=fs(6.4))
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "a", x=-0.28, y=1.04)

    # ------------------------------------------------------- (b) level and rate
    ax = fig.add_subplot(gs[0, 1])
    labels, vals, cols = [], [], []
    for r in D["level_sweep"]:
        labels.append("%+.0f dBFS" % r["amp_db"])
        vals.append(r["settled"])
        cols.append(ORANGE)
    for r in D["rates"]:
        labels.append(r["pair"].replace(" -> ", "\u2192"))
        vals.append(r["settled"])
        cols.append(MEAS)
    # a gap between the two groups so the eye reads them as separate sweeps
    y = np.array([10, 9, 8, 7, 6, 4.2, 3.2, 2.2, 1.2, 0.2, -0.8])
    ax.barh(y, np.array(vals) - 640, left=640, height=0.66, color=cols,
            edgecolor="white", linewidth=0.4)
    for yy, v in zip(y, vals):
        ax.text(640.4, yy, "%.1f" % v, va="center", fontsize=fs(6.3),
                color="white")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=fs(6.5))
    # Colour the tick labels rather than annotating the groups: the two sweeps
    # then read apart without a label landing on top of a bar.
    for tick, c in zip(ax.get_yticklabels(), cols):
        tick.set_color(c)
    ax.set_ylim(-1.6, 11.6)
    ax.set_xlim(640, 672)
    ax.set_xlabel("Settled null depth (dB)")
    ax.axvline(665.5, color=BASE, lw=0.7, ls=":", zorder=0)
    clean_axes(ax, grid_axis="x")
    panel_letter(ax, "b", x=-0.30, y=1.04)

    # ------------------------------------------- (c) where the products land
    ax = fig.add_subplot(gs[1, 0])
    ax.plot(f, st, "-", color=LIGHT, lw=2.4, zorder=1)
    hx, hy, ix, iy, mx, my = [], [], [], [], [], []
    for r in D["harmonics_images"]:
        if r["prec"] != 2:
            continue
        hx += [r["f"] * 2, r["f"] * 3]
        hy += [r["h2"], r["h3"]]
        ix += [44100 - r["f"], 44100 + r["f"]]
        iy += [r["img_lo"], r["img_hi"]]
    for r in D["imd"]:
        for pr in r["prod"]:
            mx.append(abs(pr["f"]) or 1.0)
            my.append(pr["db"])
    ax.plot(hx, hy, "o", color=ANALYTIC, ms=fs(3.2), label="harmonic", zorder=3)
    ax.plot(ix, iy, "s", color=GREEN, ms=fs(2.8), label="image", zorder=3)
    ax.plot(mx, my, "^", color=ORANGE, ms=fs(3.2), label="IMD product", zorder=3)
    f64 = [r for r in D["harmonics_images"] if r["prec"] == 0][0]
    ax.plot([2000, 3000, 43100, 45100],
            [f64["h2"], f64["h3"], f64["img_lo"], f64["img_hi"]],
            "x", color=GREY, ms=fs(3.4), mew=1.1, label="float64 engine",
            zorder=3)
    ax.set_xscale("log")
    ax.set_xlim(180, 90000)
    ax.set_ylim(-840, -320)
    ax.set_xlabel("Product frequency (Hz)")
    ax.set_ylabel("Product level (dB re 0.5 FS)")
    ax.set_xticks([200, 1000, 10000, 44000])
    ax.set_xticklabels(["200", "1k", "10k", "44k"])
    ax.legend(frameon=False, fontsize=fs(6.3), loc="lower left", ncol=2,
              handlelength=1.2, borderaxespad=0.2, columnspacing=0.9,
              handletextpad=0.4)
    ax.text(0.985, 0.46, "grey line: single-tone floor", transform=ax.transAxes,
            fontsize=fs(6.2), color=GREY, ha="right", va="center")
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "c", x=-0.28, y=1.04)

    # ------------------------------------------------------- (d) multitone
    ax = fig.add_subplot(gs[1, 1])
    ax.plot(f, st, "-", color=LIGHT, lw=2.4, zorder=1)
    mt = D["multitone"]
    top = np.array([r["top"] for r in mt], dtype=float)
    nv = np.array([r["null"] for r in mt])
    nt = np.array([r["ntone"] for r in mt])
    sc = ax.scatter(top, nv, c=nt, cmap="viridis", s=fs(18), zorder=3,
                    edgecolor="white", linewidth=0.5, vmin=1, vmax=40)
    cb = fig.colorbar(sc, ax=ax, pad=0.03, fraction=0.05)
    cb.set_label("tone count", fontsize=fs(6.5), labelpad=2)
    cb.set_ticks([1, 4, 8, 16, 40])
    cb.ax.set_yticklabels(["1", "4", "8", "16", "40"])
    cb.ax.tick_params(labelsize=fs(6.2), pad=1.5)
    cb.outline.set_linewidth(0.4)
    ax.set_xscale("log")
    ax.set_xlim(150, 30000)
    ax.set_ylim(400, 700)
    ax.set_xlabel("Highest tone in the multitone (Hz)")
    ax.set_ylabel("Multitone null depth (dB)")
    ax.set_xticks([200, 1000, 10000])
    ax.set_xticklabels(["200", "1k", "10k"])
    ax.text(0.03, 0.055, "grey line: single-tone floor", transform=ax.transAxes,
            fontsize=fs(6.2), color=GREY, va="bottom")
    clean_axes(ax, grid_axis="y")
    panel_letter(ax, "d", x=-0.28, y=1.04)

    finish(fig, p, "fig_quad_profile")


if __name__ == "__main__":
    profile()
