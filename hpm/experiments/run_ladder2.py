"""The representation ladder, measured on an ideal stimulus.

results_ladder.json stores the *engine's* binary128 output five ways, so its top
rung is the engine's floor, not binary128's: the engine saturates at 440.211 dB
while binary128 itself can hold 689.6 dB.  That mixes two ceilings in one column.

Here the stimulus is generated at 1200 bit - far above every storage format -
and then rounded five ways.  Each rung is now the format and nothing else, so
the reading should equal the format's own quantisation floor.
"""
import json
import os
import sys

sys.path.insert(0, ".")
import numpy as np
import soundfile as sf
from flint import ctx

from hpm.arb import f128, measure, mcore

FS = 8000
N = 65536
# 1001 Hz, not 1000: at 1000/8000 the record visits only 8 distinct phases, so
# the quantisation error is 8 fixed numbers and its rms is a property of where
# those 8 values happen to fall, not of the format.  1001 is coprime with 8000,
# so the period is the whole record and the error is averaged properly.
F = 1001
P_STIM = 1200          # the stimulus, ~500 dB above the best storage format
BITS = 600             # the ruler: 3514 dB at this N, far above every rung
OUT = "hpm/experiments/_lad2"
os.makedirs(OUT, exist_ok=True)


def floor_fp(p, amp=0.5, n=20000):
    """Quantisation floor of a p-bit *floating point* format.

    The step is relative, so it must be averaged over the sinusoid's excursion
    rather than taken at full scale; a uniform-quantiser formula is off by
    13 dB for float32 and float64.
    """
    th = (np.arange(n) + 0.5) / n * np.pi / 2
    x = amp * np.sin(th)
    _, e = np.frexp(x)
    ulp = np.ldexp(1.0, e - p)
    return 10 * np.log10(amp ** 2 / 2 / (np.mean(ulp ** 2) / 12))


def floor_pcm(bits, amp=0.5):
    """Signed p-bit PCM: step 2^-(bits-1) of full scale, mid-tread."""
    q = 2.0 ** -(bits - 1)
    return 10 * np.log10(amp ** 2 / 2 / (q * q / 12))


def main():
    print("generating %d samples of %g Hz at %d bit" % (N, F, P_STIM), flush=True)
    x = mcore.tone(F, FS, N, "0.5", P_STIM)

    raw = b"".join(f128.encode(v) for v in x)
    open(os.path.join(OUT, "lad2.f128"), "wb").write(raw)

    old = ctx.prec
    ctx.prec = 200
    try:
        a = np.array([float(v) for v in x], dtype=np.float64)
    finally:
        ctx.prec = old
    a.tofile(os.path.join(OUT, "lad2.f64"))
    sf.write(os.path.join(OUT, "lad2_f32.wav"), a.astype(np.float32), FS,
             subtype="FLOAT")
    sf.write(os.path.join(OUT, "lad2_pcm24.wav"), a, FS, subtype="PCM_24")
    sf.write(os.path.join(OUT, "lad2_pcm16.wav"), a, FS, subtype="PCM_16")

    rungs = [
        ("binary128", "lad2.f128", "f128", 113, floor_fp(113)),
        ("float64", "lad2.f64", "f64", 53, floor_fp(53)),
        ("float32", "lad2_f32.wav", "wav", 24, floor_fp(24)),
        ("PCM 24", "lad2_pcm24.wav", "wav", 24, floor_pcm(24)),
        ("PCM 16", "lad2_pcm16.wav", "wav", 16, floor_pcm(16)),
    ]
    rows = []
    print("%-10s %9s %9s %8s" % ("format", "measured", "floor", "diff"), flush=True)
    for lab, fn, fmt, sig, pred in rungs:
        r = measure.measure(os.path.join(OUT, fn), FS, [F], bits=BITS, fmt=fmt)
        cert = r["null_cert_db"]
        rows.append(dict(name=lab, file=fn, fmt=fmt, sig_bits=sig, cert_db=cert,
                         mid_db=r["null_mid_db"], floor_db=float(pred),
                         diff_db=cert - float(pred), rms=r["rms_residual"],
                         amp=r["amp"][0], dc=r["dc"]))
        print("%-10s %9.3f %9.3f %+8.2f" % (lab, cert, pred, cert - pred), flush=True)

    print()
    print("ruler at %d bit, N=%d: %.1f dB" % (BITS, N, 6.0199 * BITS - 4.4941 * np.log2(N)
                                              - 0.0583 * np.log2(N) ** 2 - 10.44))
    print("total spread %.1f dB" % (rows[0]["cert_db"] - rows[-1]["cert_db"]))
    json.dump(rows, open("hpm/experiments/results_ladder2.json", "w"), indent=1)
    print("wrote results_ladder2.json")


if __name__ == "__main__":
    main()
