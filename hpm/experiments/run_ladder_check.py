"""The four chains of the floor cascade, on the representation ladder.

Fig. 1a of the manuscript used to plot "predicted floor" as 6.0206*bits, which is
the arithmetic ceiling of the *analyser*, not the ceiling of the stage that is
supposed to bound the reading.  For a chain whose output is float64 the binding
stage is the output representation, whose floor is 328.1 dB regardless of how
many bits the analyser carries.  Plotting the analyser ceiling there made every
gap look like an engine defect.

Here the ladder is measured properly: take the engine binary128 output, store it
five ways, and run the same 120-bit ruler on each.  The reading then equals the
format floor by construction, which is the whole point - the ruler does not
participate.
"""
import json
import sys

sys.path.insert(0, ".")
from hpm.arb import advisor

LAD = json.load(open("hpm/experiments/results_ladder.json"))

FMT = [
    ("binary128", 113, 440.211),
    ("float64", 53, 328.091),
    ("float32", 24, 153.822),
    ("PCM 24", 24, 140.662),
    ("PCM 16", 16, 92.701),
]


def ceiling(sig_bits):
    """Representation floor of a p-bit format, 0.5 full-scale sine.

    Quantisation step 2^-p of full scale, signal power 1/8, noise power q^2/12:
    null = 10 log10( (1/8) / (2^-2p / 12) ) = 6.0206 p + 10.79 dB.
    """
    return 6.0206 * sig_bits + 10.79

print("%-10s %8s %10s %10s %8s" % ("format", "sig bits", "measured", "formula", "diff"))
for lab, sb, meas in FMT:
    print("%-10s %8d %10.3f %10.3f %8.2f"
          % (lab, sb, meas, ceiling(sb), meas - ceiling(sb)))

print()
print("engine law check at N = 1411200, p = 94:")
c94 = advisor.certifiable_db(94, 1411200, 1000)
print("  certifiable_db(94) = %.2f dB" % c94)
print("  measured           = 440.211 dB")
print("  difference         = %+.2f dB" % (440.211 - c94))
print()
r94 = advisor.ruler_db(94, 1411200)
print("ruler at p = 94, N = 1411200: %.2f dB (headroom over the reading %.2f dB)"
      % (r94, r94 - 440.211))
print()
print("analyser ceiling at 400 bit: %.2f dB" % (6.0206 * 400))
print("certificate at 400 bit, N = 1411200: %.2f dB"
      % advisor.certifiable_db(400, 1411200, 1000))
