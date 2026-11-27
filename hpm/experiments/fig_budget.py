"""Four panels for the certified-measurement tooling report."""
import json, sys
sys.path.insert(0, ".")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from hpm.arb import advisor

plt.rcParams.update({"font.size": 8, "axes.linewidth": 0.7,
                     "font.family": "DejaVu Sans", "axes.unicode_minus": False})
C1, C2, C3, C4 = "#1f4e79", "#c0504d", "#4f81bd", "#9bbb59"

fig, ax = plt.subplots(2, 2, figsize=(7.0, 5.2), dpi=200)

# (a) certificate vs bits at four record lengths, with the law
a = ax[0][0]
rr = json.load(open("hpm/experiments/results_ruler.json"))
pts = [r for r in rr if "p" in r]
# plot the GAP below 6.02 dB/bit: the four lengths are invisible on an absolute axis
for N, col, mk in ((1024, C1, "o"), (4096, C2, "s"), (16384, C3, "^"), (65536, C4, "d")):
    sel = [r for r in pts if r["N"] == N]
    a.plot([r["p"] for r in sel], [6.0206 * r["p"] - r["null_db"] for r in sel], mk, ms=3.2,
           color=col, label=f"N = {N:,}")
    xs = np.linspace(50, 1000, 50)
    a.plot(xs, [6.0206 * x - advisor.certifiable_db(x, N, 1000) for x in xs], "-", lw=0.8,
           color=col, alpha=0.6)
a.set_xlabel("working precision (bit)")
a.set_ylabel("gap below 6.0206 dB/bit (dB)")
a.set_title("(a) what one bit does not buy: the length term", loc="left", fontsize=8)
a.set_ylim(0, 135)
a.legend(frameon=False, fontsize=6.5, loc="upper left", ncol=2)
a.grid(alpha=0.25, lw=0.4)

# (b) representation ladder
b = ax[0][1]
lad = {r["name"]: r["cert"] for r in json.load(open("hpm/experiments/results_ladder.json"))}
ladder = [("binary128", lad["_eng16.f128"], C1), ("float64", lad["_eng16.f64"], C2),
          ("float32 (WAV)", lad["_eng16.wav"], C3), ("PCM 24", lad["_eng16_pcm24.wav"], C4),
          ("PCM 16", lad["_eng16_pcm16.wav"], "#8064a2")]
ys = np.arange(len(ladder))[::-1]
for y, (name, v, col) in zip(ys, ladder):
    b.barh(y, v, height=0.55, color=col, alpha=0.85)
    b.text(v + 6, y, f"{v:.1f}", va="center", fontsize=6.5)
b.set_yticks(ys)
b.set_yticklabels([n for n, _, _ in ladder], fontsize=7)
b.set_xlim(0, 520)
b.set_xlabel("certified null of the same 1 kHz tone (dB)")
b.set_title("(b) the same signal, five representations", loc="left", fontsize=8)
b.grid(axis="x", alpha=0.25, lw=0.4)

# (c) advisor validation: ask for a target, measure at the advised precision
c = ax[1][0]
v2 = json.load(open("hpm/experiments/results_validate2.json"))
T = np.array([r["T"] for r in v2])
M = np.array([r["measured"] for r in v2])
lo, hi = 0, 3300
c.plot([lo, hi], [lo, hi], "-", lw=0.8, color="0.55", label="measured = target")
c.plot(T, M, "o", ms=4.2, color=C1, zorder=3, label="advisor + measurement")
for t, m in zip(T, M):
    if t >= 900:
        c.annotate(f"{m - t:+.1f} dB", (t, m), textcoords="offset points", xytext=(-30, 6),
                   fontsize=6, color="0.3")
c.text(0.97, 0.06, "9 cases, every one within +1.6 to +4.8 dB",
       transform=c.transAxes, fontsize=6.2, color="0.3", va="bottom", ha="right")
c.set_xlim(lo, hi); c.set_ylim(lo, hi)
c.set_xticks([0, 1000, 2000, 3000]); c.set_yticks([0, 1000, 2000, 3000])
c.set_xlabel("target certificate (dB)")
c.set_ylabel("measured certificate (dB)")
c.set_title("(c) ask for a target, get it", loc="left", fontsize=8)
c.legend(frameon=False, fontsize=5.8, loc="upper left")
c.grid(alpha=0.25, lw=0.4)

# (d) the length bill: what the record costs, at fixed precision
d = ax[1][1]
Ns = [1024, 4096, 16384, 65536, 262144, 1411200]
x = np.arange(len(Ns))
bn = [-advisor.budget(400, N)["log2n_db"] for N in Ns]
bq = [-advisor.budget(400, N)["log2n2_db"] for N in Ns]
bc = [-advisor.budget(400, N)["constant_db"] for N in Ns]
d.bar(x, bn, color=C2, label="20 log$_{10}$N term", width=0.62)
d.bar(x, bq, bottom=bn, color=C3, label="length$^2$ term", width=0.62)
d.bar(x, bc, bottom=np.array(bn) + bq, color=C4, label="constant", width=0.62)
for i, N in enumerate(Ns):
    tot = bn[i] + bq[i] + bc[i]
    d.text(i, tot + 3, f"{tot:.0f}", ha="center", fontsize=6)
    d.text(i, tot + 14, f"{tot / (6.0206 * 400) * 100:.1f}%", ha="center", fontsize=5.2, color="0.35")
d.set_xticks(x)
d.set_xticklabels(["1k", "4k", "16k", "65k", "262k", "1.4M"], fontsize=6.5)
d.set_xlabel("record length N (samples)")
d.set_ylabel("dB below the 6.02 dB/bit ceiling")
d.set_ylim(0, 175)
d.set_title("(d) the length bill at 400 bit", loc="left", fontsize=8)
d.legend(frameon=False, fontsize=5.8, loc="upper left", bbox_to_anchor=(0.0, 1.0))
d.grid(axis="y", alpha=0.25, lw=0.4)

fig.tight_layout(pad=0.6)
fig.savefig("hpm/reports/figs/budget_1_5.png", bbox_inches="tight", pad_inches=0.12)
print("wrote hpm/reports/figs/budget_1_5.png")
