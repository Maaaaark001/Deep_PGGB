"""dp_figures.py - paper figures for Deep_PGGB, built to the Nature spec.

Layout: one 180 mm double-column figure with four panels, plus one 88 mm
single-column figure. Every panel is drawn at its PLACED size, so the landed
type size is what the reader measures. Type is Arial at 9-10.5 pt landed.

    python deeppggb/dp_figures.py            # writes work/figures/{pdf,svg,png}
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = r"C:\Users\Administrator\Documents\Python_Code\src"
SKILL = os.path.join(os.path.expanduser("~"), ".dsh", "skills",
                     "nature-figure-production", "assets")
sys.path.insert(0, SKILL)
sys.path.insert(0, ROOT)

import nature_style as ns  # noqa: E402

DATA = json.load(open(os.path.join(ROOT, "work", "paper_data.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "work", "figures")
ns.set_outdir(OUT)

# --- semantic colour code, fixed for the whole paper ----------------------
C_DEEP = "#0B75B3"      # Deep_PGGB
C_PGGB = "#E64B35"      # PGGB (reference commercial engine)
C_REF = "#808080"       # analytic / ideal
C_ALT = "#00A087"       # other engines
C_WARN = "#F0A202"      # warning / transition band


def _eng(name):
    for r in DATA["engines"]:
        if r["engine"] == name:
            return r
    raise KeyError(name)


# =========================================================== Figure 1 (180 mm)
def figure_accuracy():
    p = ns.panel(placed_mm=180, aspect=0.62)
    ns.apply_style(p)
    fig, axes = plt.subplots(2, 2, figsize=p.figsize)
    fig.subplots_adjust(left=0.085, right=0.985, top=0.94, bottom=0.185,
                        wspace=0.32, hspace=0.46)

    # (a) null depth vs conversion ratio -----------------------------------
    ax = axes[0, 0]
    acc = DATA["accuracy"]
    labels = ["%g\N{RIGHTWARDS ARROW}%g" % (r["src"] / 1000.0, r["dst"] / 1000.0)
              for r in acc]
    vals = [r["null_db"] for r in acc]
    xs = np.arange(len(vals))
    up = [r["dst"] > r["src"] for r in acc]
    cols = [C_DEEP if u else C_ALT for u in up]
    # A DOT plot, not bars. Every value sits within 3 dB of 302, so the axis has
    # to be truncated; bars drawn from a non-zero baseline then encode a 3 dB
    # difference as a 20x height ratio, which is a lie about the data.
    ax.vlines(xs, 285, vals, color=cols, lw=0.9, zorder=3)
    ax.scatter(xs, vals, s=24, color=cols, edgecolor="white", linewidth=0.5,
               zorder=4)
    pg = DATA["pggb"]
    ax.axhline(pg["null_db"], color=C_PGGB, lw=0.8, ls="--", zorder=2)
    ax.text(-0.4, pg["null_db"] + 0.8, "PGGB", color=C_PGGB, fontsize=6.3,
            ha="left", va="bottom")
    ax.text(len(vals) - 0.45, 285.6, "axis truncated at 285 dB", color=C_REF,
            fontsize=6.0, ha="right", va="bottom")
    ax.set_xticks(xs)
    # Rotated labels already carry the units (kHz), so an x-axis title would
    # collide with them for no information.
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=6.3,
                       rotation_mode="anchor")
    ax.set_ylim(285, 312)
    ax.set_ylabel("Null depth vs. exact\nreference (dB)")
    ns.clean_axes(ax)
    ns.panel_letter(ax, "a")

    # (b) taper window order: the mechanism --------------------------------
    ax = axes[0, 1]
    t = DATA["taper_order"]
    ords = [r["order"] for r in t]
    leak = [-r["leak_22050_db"] for r in t]
    null15 = [r["null_15k_db"] for r in t]
    null40 = [r["null_40tone_db"] for r in t]
    ax.plot(ords, null40, "o-", color=C_DEEP, lw=1.2, ms=3.4,
            label="40-tone null depth")
    ax.plot(ords, null15, "s--", color=C_ALT, lw=1.0, ms=3.0,
            label="15 kHz null depth")
    # Leakage is reported as a SUPPRESSION (the negative of the level), so all
    # three curves are "higher is better" and can share one axis honestly.
    ax.plot(ords, leak, "^--", color=C_PGGB, lw=1.0, ms=3.0,
            label="taper leakage suppression")
    ax.axhline(DATA["pggb"]["null_db"], color=C_REF, lw=0.7, ls=":")
    ax.text(5.95, DATA["pggb"]["null_db"] + 2.4, "PGGB", color=C_REF,
            fontsize=6.5, ha="right")
    ax.set_xlabel("Taper polynomial order $N$")
    ax.set_ylabel("Rejection (dB)")
    ax.set_xticks(ords)
    ax.set_ylim(190, 400)
    ax.legend(frameon=False, loc="lower right", fontsize=6.3, handlelength=1.6,
              borderaxespad=0.3)
    ns.clean_axes(ax)
    ns.panel_letter(ax, "b")

    # (c) null depth vs tone frequency -------------------------------------
    ax = axes[1, 0]
    fr = DATA["freq_sweep"]
    hz = [r["hz"] / 1000.0 for r in fr]
    ax.semilogx(hz, [r["null_smooth2"] for r in fr], "o--", color=C_PGGB,
                lw=1.0, ms=2.8, label="C2 taper (old default)")
    ax.semilogx(hz, [r["null_smooth5"] for r in fr], "o-", color=C_DEEP,
                lw=1.2, ms=3.0, label="C5 taper (this work)")
    ax.axvline(22.05, color=C_WARN, lw=0.8, ls=":")
    ax.text(22.1, 268, "source\nNyquist", color=C_WARN, fontsize=6.3, va="top")
    ax.set_xlabel("Tone frequency (kHz)")
    ax.set_ylabel("Null depth (dB)")
    ax.set_xlim(0.9, 24)
    ax.set_ylim(40, 320)
    ax.legend(frameon=False, loc="lower left", fontsize=6.3, handlelength=1.6,
              borderaxespad=0.3)
    ns.clean_axes(ax)
    ns.panel_letter(ax, "c")

    # (d) rolloff: alias rejection vs transition width ---------------------
    ax = axes[1, 1]
    ro = DATA["rolloff"]
    widths = sorted({r["rolloff_hz"] for r in ro})
    for order, col, mk in ((1, C_ALT, "s"), (2, C_DEEP, "o"), (3, C_PGGB, "^")):
        xs2, ys2 = [], []
        for w in widths:
            for r in ro:
                if r["rolloff_hz"] == w and r["order"] == order:
                    xs2.append(max(w, 1.0))
                    ys2.append(-r["alias_22050"])
        ax.semilogx(xs2, ys2, mk + "-", color=col, lw=1.1, ms=3.0,
                    label="order %d" % order)
    ax.axhline(211, color=C_REF, lw=0.7, ls=":")
    ax.text(1.1, 202, "float64 floor", color=C_REF, fontsize=6.3)
    ax.set_xlabel("Transition width (Hz, 0 drawn at 1)")
    ax.set_ylabel("Rejection at 22.05 kHz (dB)")
    ax.set_ylim(0, 225)
    ax.legend(frameon=False, loc="lower right", fontsize=6.3, handlelength=1.6,
              borderaxespad=0.3)
    ns.clean_axes(ax)
    ns.panel_letter(ax, "d", x=-0.22)

    ns.landed_report(fig, p)
    paths = ns.save_all("fig1_accuracy", fig)
    plt.close(fig)
    return paths


# =========================================================== Figure 2 (88 mm)
def figure_engines():
    p = ns.panel(placed_mm=88, aspect=1.30)
    ns.apply_style(p)
    fig, axes = plt.subplots(2, 1, figsize=p.figsize, sharey=True)
    fig.subplots_adjust(left=0.30, right=0.965, top=0.955, bottom=0.175,
                        hspace=0.34)

    order = ["dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"]
    rows = [_eng(k) for k in order]
    # Engine labels are localised in the app ("PGGB（原版）"); the figure is
    # English, and Arial has no CJK glyphs, so pin the row names here.
    EN = {"pggb": "PGGB", "dpggb": "Deep_PGGB", "soxng": "sox_ng",
          "swr": "FFmpeg swr", "soxr": "libsoxr", "r8b": "r8brain",
          "ssrc": "SSRC", "scipy": "SciPy"}
    names = [EN.get(r["engine"], r["label"]) for r in rows]
    ys = np.arange(len(rows))
    h = 0.34

    panels = (
        (axes[0], [("spur_dbc", "single-tone spur", C_DEEP),
                   ("mt_dbc", "24-tone residual", C_ALT)],
         "Harmonic / multi-tone"),
        (axes[1], [("imd_dbc", "CCIF 19+20 kHz", C_DEEP),
                   ("imd_smpte_dbc", "SMPTE 60 Hz + 7 kHz", C_ALT)],
         "Intermodulation"),
    )
    # Both floors are what float64 produces with NO resampling at all: 24 summed
    # sinusoids analysed directly read -295.2 dBc, and the two-tone products read
    # -334.4 dBc. Drawing them keeps the panels from reading as "Deep_PGGB is
    # 109 dB cleaner than r8brain" when the top two rows are simply at the floor.
    # Label each floor vertically along its own line near the bottom row: a
    # horizontal label above the top row collides with the top bars, which now
    # end exactly at the floor.
    # No in-axes label: any placement collides with either the top bars (which
    # end at the floor) or the 300 dB tick. The caption states both values.
    axes[0].axvline(295.2, color=C_REF, lw=0.7, ls=":")
    axes[1].axvline(334.4, color=C_REF, lw=0.7, ls=":")

    for ax, series, head in panels:
        for i, (key, lab, col) in enumerate(series):
            vals = [-r[key] for r in rows]
            off = h / 2 if i == 0 else -h / 2
            ax.barh(ys + off, vals, height=h, color=col, edgecolor="none",
                    label=lab)
            for y, v in zip(ys + off, vals):
                ax.text(min(v, 396) + 4, y, "%.0f" % v, va="center",
                        fontsize=5.8, color="#333333")
        ax.set_yticks(ys)
        ax.set_yticklabels(names)
        # 0-400 dB: the top two rows now read -320 and -339 dBc, so a 300 dB
        # axis would clip them and the floor lines would fall outside.
        ax.set_xlim(0, 400)
        ax.set_ylabel(head, fontsize=6.6)
        # Legend above the axes: every bar grows to the right, so any in-axes
        # corner eventually collides with one.
        ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0.0, 1.005),
                  ncol=2, fontsize=6.0, handlelength=1.3, borderaxespad=0.0,
                  columnspacing=1.4)
        ns.clean_axes(ax, grid_axis="x")
        plt.setp(ax.get_yticklabels(), fontsize=6.4)
    axes[1].invert_yaxis()
    # Head-room above the first row for the floor labels; set after the inversion
    # so "top of the axes" means the first row.
    axes[1].set_ylim(7.6, -0.55)
    axes[1].set_xlabel("Rejection (dB, higher is cleaner)")
    # 295 / 334 dB are not engine properties: they are where float64 rounding of
    # the stimulus itself sits in this measurement.
    fig.text(0.5, 0.030, "dotted = float64 analysis floor (295 / 334 dBc), not an engine property",
             fontsize=5.6, color=C_REF, ha="center", va="bottom")

    ns.landed_report(fig, p)
    paths = ns.save_all("fig2_engines", fig)
    plt.close(fig)
    return paths




# =========================================================== Figure 3 (180 mm)
def figure_cost():
    p = ns.panel(placed_mm=180, aspect=0.34)
    ns.apply_style(p)
    fig, axes = plt.subplots(1, 3, figsize=p.figsize)
    fig.subplots_adjust(left=0.062, right=0.988, top=0.93, bottom=0.30,
                        wspace=0.34)

    # (a) throughput vs block length and worker count ----------------------
    ax = axes[0]
    sp = DATA["speed"]
    blocks = sorted({r["block_s"] for r in sp})
    marks = {1: ("o", "#89CAEA"), 2: ("s", "#4DBBD5"), 4: ("^", C_DEEP),
             8: ("D", "#012A61")}
    for w, (mk, col) in marks.items():
        xs3 = [b for b in blocks if any(r["block_s"] == b and r["workers"] == w
                                        for r in sp)]
        ys3 = [next(r["speed_x"] for r in sp
                    if r["block_s"] == b and r["workers"] == w) for b in xs3]
        ax.plot(xs3, ys3, mk + "-", color=col, lw=1.1, ms=3.0,
                label="%d worker%s" % (w, "" if w == 1 else "s"))
    ax.axhline(DATA["pggb"].get("speed_x_60s_stereo", DATA["pggb"]["speed_x_30s_stereo"]), color=C_PGGB, lw=0.8,
               ls="--")
    ax.text(29.0, DATA["pggb"].get("speed_x_60s_stereo", DATA["pggb"]["speed_x_30s_stereo"]) + 6, "PGGB", color=C_PGGB,
            fontsize=6.2, ha="right")
    ax.set_xscale("log")
    ax.set_xlabel("Block length (s)")
    ax.set_ylabel("Throughput (\u00d7 real time)")
    ax.set_ylim(0, 275)
    ax.legend(frameon=False, fontsize=6.0, handlelength=1.4, ncol=2,
              loc="upper center", borderaxespad=0.2, columnspacing=1.0)
    ns.clean_axes(ax)
    ns.panel_letter(ax, "a")

    # (b) block-length invariance -----------------------------------------
    ax = axes[1]
    inv = DATA["block_invariance"]
    xs4 = [r["block_s"] for r in inv]
    ys4 = [min(r["null_vs_whole_db"], 310.0) for r in inv]
    ax.semilogx(xs4, ys4, "o-", color=C_DEEP, lw=1.2, ms=3.2)
    # Values above 310 dB are exact equality (the difference is literally zero),
    # so the axis is capped and that cap is labelled rather than hidden.
    ax.axhline(310, color=C_REF, lw=0.7, ls=":")
    ax.text(0.27, 301.5, "bit-identical to\nthe whole-file result", color=C_REF,
            fontsize=6.0, va="top")
    ax.set_xlabel("Block length (s)")
    ax.set_ylabel("Null depth vs.\nwhole-file output (dB)")
    ax.set_ylim(295, 314)
    ns.clean_axes(ax)
    ns.panel_letter(ax, "b")

    # (c) null depth vs file length ---------------------------------------
    ax = axes[2]
    fl = DATA["file_length"]
    xs5 = [r["seconds"] for r in fl]
    ys5 = [r["null_db"] for r in fl]
    ax.semilogx(xs5, ys5, "o-", color=C_DEEP, lw=1.2, ms=3.2)
    # The taper is clamped to 5% of the file, so below 0.4 s it shortens with the
    # file: that is what the 0.1 s point measures, and the 20 ms marker has to be
    # inside the plotted range to be visible at all.
    ax.axvline(0.02, color=C_WARN, lw=0.8, ls=":")
    ax.text(0.022, 235, "20 ms taper", color=C_WARN, fontsize=6.0, va="bottom")
    ax.set_xlim(0.008, 8.0)
    ax.set_xlabel("File length (s)")
    ax.set_ylabel("Null depth (dB)")
    ax.set_ylim(200, 315)
    ns.clean_axes(ax)
    ns.panel_letter(ax, "c")

    ns.landed_report(fig, p)
    paths = ns.save_all("fig3_cost", fig)
    plt.close(fig)
    return paths


if __name__ == "__main__":
    for fn in (figure_accuracy, figure_engines, figure_cost):
        print("\n".join(fn()))
