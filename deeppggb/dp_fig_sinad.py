"""dp_fig_sinad.py - Figure 10: single-tone SINAD / SFDR / ENOB.

Reads work/sinad_profile.json (written by deeppggb/dp_sinad.py) and draws to the
Nature spec through the skill's nature_style module: drawn at 180 mm, landed 9-10 pt.

    python deeppggb/dp_fig_sinad.py
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(os.path.expanduser("~"), ".dsh", "skills",
                     "nature-figure-production", "assets")
sys.path.insert(0, SKILL)

import nature_style as ns  # noqa: E402

DATA = json.load(open(os.path.join(ROOT, "work", "sinad_profile.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "work", "figures")
ns.set_outdir(OUT)

C_DEEP = "#0B75B3"
C_PGGB = "#E64B35"
C_REF = "#808080"
C_ALT = "#00A087"
C_WARN = "#F0A202"

NAME = {"dpggb": "Deep_PGGB", "pggb": "PGGB", "r8b": "r8brain", "soxng": "sox_ng",
        "swr": "FFmpeg", "soxr": "libsoxr", "ssrc": "SSRC", "scipy": "SciPy"}
COLOR = {"dpggb": C_DEEP, "pggb": C_PGGB}
FLOOR = 306.0          # double-precision output floor for a 0.5 FS tone at 88.2 kHz


def enob(sinad_db):
    return (sinad_db + 4.26) / 6.02      # +6.02 dB for the 0.5 FS test tone, minus 1.76


ORDER = None


def _dumbbell(ax, R, f_lo, f_hi, label_lo, label_hi, xlabel="SINAD (dB)"):
    global ORDER
    order = ORDER or sorted(R, key=lambda k: R[k]["settled"]["sinad_db"])
    ys = np.arange(len(order))
    for y, k in zip(ys, order):
        lo = f_lo(R[k])
        hi = f_hi(R[k])
        col = COLOR.get(k, C_ALT)
        ax.plot([lo, hi], [y, y], color=col, lw=1.0, alpha=0.5, solid_capstyle="butt")
        ax.plot([lo], [y], marker="o", ms=3.4, mfc="white", mec=col, mew=0.9, ls="none")
        ax.plot([hi], [y], marker="o", ms=3.4, color=col, ls="none")
    ax.axvline(FLOOR, color=C_REF, lw=0.6, ls=(0, (3, 2)))
    ax.set_yticks(ys)
    ax.set_yticklabels([NAME[k] for k in order])
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.set_xlim(60, 330)
    ax.set_xticks([100, 150, 200, 250, 300])
    ax.set_xlabel(xlabel, labelpad=2)
    ax.grid(axis="x", ls="--", lw=0.4, alpha=0.30)
    ax.tick_params(axis="y", length=0)
    ax.plot([], [], marker="o", ms=3.4, mfc="white", mec=C_REF, mew=0.9, ls="none",
            label=label_lo)
    ax.plot([], [], marker="o", ms=3.4, color=C_REF, ls="none", label=label_hi)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.30),
              ncol=2, handlelength=0.7, labelspacing=0.18, columnspacing=0.9,
              borderaxespad=0.0, handletextpad=0.4)
    return order


def fig_sinad():
    p = ns.panel(placed_mm=180, aspect=0.46)
    ns.apply_style(p)
    fig = plt.figure(figsize=p.figsize)
    gs = fig.add_gridspec(2, 3, height_ratios=[0.80, 1.20],
                          left=0.080, right=0.988, top=0.940, bottom=0.235,
                          hspace=0.66, wspace=0.52)
    R = {r["engine"]: r for r in DATA["rows"]}
    global ORDER
    ORDER = sorted(R, key=lambda k: R[k]["settled"]["sinad_db"])

    # ---- (a) SINAD of successive 1 s windows -----------------------------
    ax = fig.add_subplot(gs[0, :])
    for eng, col in (("dpggb", C_DEEP), ("pggb", C_PGGB)):
        prof = R[eng]["profile"]
        ax.plot([r[0] for r in prof], [r[1] for r in prof], color=col, lw=1.1,
                label=NAME[eng])
    for a, b in ((0.0, 1.0), (14.0, 15.2)):
        ax.axvspan(a, b, color=C_WARN, alpha=0.10, lw=0)
    ax.axhline(FLOOR, color=C_REF, lw=0.6, ls=(0, (3, 2)))
    ax.set_xlim(0, 15.2)
    ax.set_ylim(150, 325)
    ax.set_xlabel("Window position (s)")
    ax.set_ylabel("SINAD (dB)")
    ax.set_xticks([0, 4, 8, 12])
    ax.set_yticks([150, 200, 250, 300])
    ax.text(4.6, FLOOR - 14, "float64 floor", color=C_REF, fontsize=8.0,
            ha="left", va="top")
    ax.legend(frameon=False, loc="center left", bbox_to_anchor=(0.055, 0.26),
              handlelength=1.4, labelspacing=0.25)
    ax.text(0.008, 1.02, "a", transform=ax.transAxes, fontweight="bold",
            va="bottom", ha="left")

    # ---- (b) settled interior vs worst second ---------------------------
    ax = fig.add_subplot(gs[1, 0])
    _dumbbell(ax, R, lambda r: r["worst"]["sinad_db"],
              lambda r: r["settled"]["sinad_db"], "worst second", "settled")
    ax.text(0.012, 1.02, "b", transform=ax.transAxes, fontweight="bold",
            va="bottom", ha="left")

    # ---- (c) SFDR -------------------------------------------------------
    ax = fig.add_subplot(gs[1, 1])
    _dumbbell(ax, R, lambda r: min(r["settled"]["sfdr_db"], r["settled"]["sinad_db"]),
              lambda r: r["settled"]["sfdr_db"], "SINAD", "SFDR", xlabel="Level (dB)")
    ax.text(0.012, 1.02, "c", transform=ax.transAxes, fontweight="bold",
            va="bottom", ha="left")

    # ---- (d) full band vs in band ---------------------------------------
    ax = fig.add_subplot(gs[1, 2])
    _dumbbell(ax, R, lambda r: r["settled"]["sinad_db"],
              lambda r: r["settled"]["sinad_inband_db"], "full band", "in band")
    ax.text(0.012, 1.02, "d", transform=ax.transAxes, fontweight="bold",
            va="bottom", ha="left")

    ns.landed_report(fig, p)
    ns.save_all("fig10_sinad", fig)
    return fig


if __name__ == "__main__":
    fig_sinad()
