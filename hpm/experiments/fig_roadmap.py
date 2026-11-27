"""Figure for the branch C roadmap report (steps 1-5)."""
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.linewidth": 0.6,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.4,
    "legend.frameon": False, "figure.dpi": 200,
})
C = ["#2b6cb0", "#c05621", "#2f855a", "#6b46c1"]

with open("hpm/experiments/results_arb.json") as f:
    R = json.load(f)
eng = None
if os.path.exists("hpm/experiments/results_engine.json"):
    eng = json.load(open("hpm/experiments/results_engine.json"))

fig, ax = plt.subplots(2, 2, figsize=(7.1, 5.2))

# (a) precision law
a = ax[0][0]
rows = R["step1_precision_law"]
bits = np.array([r["bits"] for r in rows], float)
null = np.array([r["null_db"] for r in rows], float)
a.plot(bits, 6.017 * bits, "--", color="#94a3b8", lw=1.0, label="6.02 dB/bit ceiling")
a.plot(bits, null, "o-", color=C[0], ms=3.5, lw=1.2, label="certified floor (Arb)")
if eng:
    a.axhline(eng["null_db"], color=C[1], lw=1.0, ls=":")
    a.annotate("binary128 engine: %.0f dB" % eng["null_db"],
               xy=(1024, eng["null_db"]), xytext=(300, 9000), fontsize=6.8, color=C[1],
               arrowprops=dict(arrowstyle="-", lw=0.6, color=C[1]))
a.set_xscale("log", base=2)
a.set_xlabel("working precision (bits)")
a.set_ylabel("certified null (dB)")
a.legend(loc="upper left", fontsize=7)
a.set_title("(a) 6.02 dB per bit, up to 23 000 dB", fontsize=8, loc="left")

# (b) conditioning gap
b = ax[0][1]
cond = R["step1b_conditioning"]
Ns = [(r["value"], r["gap_db"]) for r in cond if r["kind"] == "N"]
b.plot([x for x, _ in Ns], [y for _, y in Ns], "s-", color=C[2], ms=3.5, lw=1.1,
       label="gap vs N (1 kHz, 240 bit)")
b.set_xlabel("analysis length N")
b.set_ylabel("gap below 6.02·bits (dB)")
b.text(0.04, 0.84, "gap = 20 log10(N) + 11.4 dB", transform=b.transAxes, fontsize=7,
       color="#4a5568")
b.text(0.04, 0.66, "frequency term, N = 4096:\n500 Hz 80.3 · 1 kHz 83.6 · 4 kHz 95.1 dB",
       transform=b.transAxes, fontsize=6.4, color=C[3])
b.set_title("(b) the floor also depends on N and f", fontsize=8, loc="left")
b.legend(loc="lower right", fontsize=7)

# (c) IMD products vs theory
c = ax[1][0]
rows = R["step2_imd"]
th = [r["theory_imd3_db"] for r in rows]
me = [r["products_dbc"]["2f1-f2"] for r in rows]
c.plot([-340, -60], [-340, -60], "--", color="#94a3b8", lw=1.0)
c.plot(th, me, "o", color=C[1], ms=4)
for r in rows:
    c.annotate(r["a3"], (r["theory_imd3_db"], r["products_dbc"]["2f1-f2"]),
               textcoords="offset points", xytext=(6, 3), fontsize=6, color="#4a5568")
c.set_xlabel("predicted 2f1-f2 level (dBc)")
c.set_ylabel("certified measurement (dBc)")
c.set_title("(c) two-tone IMD certified to -327 dBc", fontsize=8, loc="left")

# (d) DPSS leakage
d = ax[1][1]
rows = [r for r in R["step5_dpss"] if "NW" in r]
nw = [r["NW"] for r in rows]; lk = [r["leak_db"] for r in rows]
d.plot(nw, lk, "o-", color=C[3], ms=3.5, lw=1.2)
d.set_ylim(min(lk) - 6, max(lk) + 6)
for x, y in zip(nw, lk):
    d.annotate("%.0f" % y, (x, y), textcoords="offset points", xytext=(0, 5), fontsize=6)
d.set_xlabel("time-bandwidth product NW (N = 512)")
d.set_ylabel("certified leakage bound (dB)")
d.set_title("(d) DPSS floor at arbitrary precision", fontsize=8, loc="left")

fig.tight_layout(pad=0.6)
os.makedirs("hpm/reports/figs", exist_ok=True)
fig.savefig("hpm/reports/figs/roadmap_1_5.png", bbox_inches="tight")
print("wrote hpm/reports/figs/roadmap_1_5.png")
