"""Precision advisor: given a target certificate, how many bits and how long?

Two fitted laws, both on measurements with the exact-integer-phase basis and
zero guard bits.  The estimator is the full 2K x 2K weighted normal-equation
solve in Arb, so every number below is an *enclosure*, not a point estimate.

Certificate law (26 points, p = 60..960 bit, N = 1k..1.27M, f = 1 kHz):

    null = 6.0199 p - 4.4941 L - 0.0583 L^2 - 10.44   [dB],  L = log2(N)
    (max |residual| 1.84 dB, rms 0.71 dB)

Ruler law (same shape, 3.0 dB above the reading at every point):

    coef = 6.0199 p - 4.4580 L - 0.0593 L^2 - 13.76   [dB]

Read the coefficients, they are the physics:

* **6.0199 dB/bit** - the arithmetic ceiling 6.0206 dB/bit, recovered to 0.01%.
  One bit of working precision buys one bit of certificate; nothing else does.
* **-4.49 L - 0.058 L^2 dB** - the record length is not free: the residual is a
  sum of N squares whose ball grows like sqrt(N) while the signal energy grows
  like N, which alone would cost 3 dB per doubling.  The coefficient radii also
  grow (the Gram matrix accumulates N roundings), and the quadratic term says the
  penalty per doubling itself grows: 5.9 dB at N = 1k, 7.2 dB at N = 65k,
  8.2 dB at N = 1.3M.  A linear fit over the whole range leaves 2.4 dB of
  residual; the quadratic leaves 1.8 dB.
* **-0.184 dB per decade of f** - almost nothing, once the basis is evaluated
  from the exact integer phase.  With cos(w*i) the same coefficient is -2.1, i.e.
  a 15 dB penalty at 4 kHz; that penalty is an argument-reduction artifact of the
  estimator, not a property of the measurement.

The laws are calibrated on synthetic stimuli whose own accuracy is ~6.02*bits
below full scale.  On a *measured* file the law is an extrapolation; the
residuals above are the honest uncertainty, and the engine check at N = 1.41M
(p = 94) came out 3.1 dB below the law.  Use MARGIN_DB.

Validity was checked outside the fit range (experiments/run_law_ext.py):

    p = 960 / 1920 / 3840 at N = 1.27M   +1.85 / +2.52 / +6.79 dB
    N = 2.82M / 5.64M at p = 240, 480   +4.38 / +2.45 / +5.39 / +3.46 dB

So the law is *conservative* everywhere it was tested (the certificate beats
the prediction) and the residual grows with precision, reaching 6.8 dB at
3840 bit.  That growth is the reason MARGIN_DB exists and the reason the
advisor should be read as a planning tool, not as a bound.

Inverting gives the advisor:

    p = (T + 4.4941 L + 0.0583 L^2 + 10.44 + 0.184 (log10 f - 3)) / 6.0199
"""
from __future__ import annotations

import math

DB_PER_BIT = 6.0199
B_LOG2N = 4.4941
B_LOG2N2 = 0.0583
C = 10.44
B_LOG10F = 0.184

RULER_B_LOG2N = 4.4580
RULER_B_LOG2N2 = 0.0593
RULER_C = 13.76

MARGIN_DB = 3.5   # law is optimistic by up to ~3 dB near the calibrated edge


def _L(N):
    return math.log2(N)


def _freq_term(f):
    return B_LOG10F * (math.log10(f) - 3.0)


def bits_for(target_db, N, f, fs=None, K=1):
    """Working precision needed to certify `target_db` on N samples of f Hz."""
    L = _L(N)
    b = (target_db + B_LOG2N * L + B_LOG2N2 * L * L + C + _freq_term(f)) / DB_PER_BIT
    if K > 1:
        b += math.log2(K)
    return int(math.ceil(b))


def certifiable_db(bits, N, f, K=1):
    """Inverse of bits_for: the certificate a given precision can reach."""
    b = bits
    if K > 1:
        b -= math.log2(K)
    L = _L(N)
    return DB_PER_BIT * b - B_LOG2N * L - B_LOG2N2 * L * L - C - _freq_term(f)


def ruler_db(bits, N):
    """The estimator's own floor at this precision.

    Above it the reading is the file's property; below it the reading is the
    ruler's, and the tool should say so instead of printing a number.
    """
    L = _L(N)
    return DB_PER_BIT * bits - RULER_B_LOG2N * L - RULER_B_LOG2N2 * L * L - RULER_C


def loss_per_doubling(N, f=1000.0):
    """How many dB of certificate a doubling of the record costs at this N."""
    L = _L(N)
    return B_LOG2N + B_LOG2N2 * (2 * L + 1)


def wall_seconds(bits, N, K=1, passes=2, ns_fixed=6341.0, ns_per_bit=13.12):
    """Wall clock for the streaming measurement, as an affine law in bits.

    The cost per sample is NOT proportional to the precision.  Each sample pays a
    fixed price (decode + phasor: two trig calls) plus a per-bit price (the ball
    accumulations).  Calibrated on 211680 samples, K=1, two passes: 8.34 / 10.42 /
    12.60 us per sample per pass at 100 / 200 / 400 bit (f128 input) and 4.99 /
    7.32 / 9.10 us (f64 input).  A straight line through those fits

        us/sample/pass = 6.341 + 0.0131 * bits   (f128 input)

    so a 94-bit run on 1.27 M samples costs ~2*1.27e6*(6341+13.12*94)e-9 = 19 s,
    not the 4 s a purely proportional model would promise.  A proportional model
    is wrong by 3x at the low-precision end, which is exactly the end users ask
    about.  Input format shifts the constant by ~1.4x (f64 is cheaper to decode).
    """
    per_sample = (4.0 * K + 4.0 * K * K) / 8.0
    per_ns = ns_fixed + ns_per_bit * bits
    return passes * N * per_sample * per_ns * 1e-9


def budget(bits, N, f=1000.0, K=1):
    """Where the 6.02 dB/bit goes, in dB, for one measurement.

    Total available: 6.0206*bits (the arithmetic ceiling).  The estimator spends
    it on the record length (the Gram matrix accumulates N roundings), on the
    frequency term, and on a constant; what is left is the certificate.  Each
    line is separately measurable, which is what makes this a budget rather
    than a fit.
    """
    L = _L(N)
    ceiling = 6.0206 * bits
    return dict(ceiling_db=ceiling,
                log2n_db=-B_LOG2N * L,
                log2n2_db=-B_LOG2N2 * L * L,
                freq_db=-_freq_term(f),
                constant_db=-C,
                certificate_db=certifiable_db(bits, N, f, K=K),
                ruler_db=ruler_db(bits, N))


def advise(target_db=None, bits=None, N=None, f=1000.0, K=1, margin=MARGIN_DB):
    """The two-number answer: bits to buy, seconds to spend, and the ruler."""
    if bits is None:
        bits = bits_for(target_db + margin, N, f, K=K)
    if target_db is None:
        target_db = certifiable_db(bits, N, f, K=K)
    return dict(target_db=target_db, bits=bits, N=N, f=f, K=K,
                wall_s=wall_seconds(bits, N, K=K),
                ruler_db=ruler_db(bits, N),
                ceiling_gap_db=target_db - DB_PER_BIT * bits,
                loss_per_doubling_db=loss_per_doubling(N, f),
                margin_db=margin)


if __name__ == "__main__":
    import sys
    T = float(sys.argv[1]) if len(sys.argv) > 1 else 440.0
    N = int(float(sys.argv[2])) if len(sys.argv) > 2 else 1411200
    f = float(sys.argv[3]) if len(sys.argv) > 3 else 1000.0
    a = advise(T, None, N, f)
    print("target %.1f dB on N=%d at %.1f Hz -> %d bits, ~%.1f s" %
          (a["target_db"], a["N"], a["f"], a["bits"], a["wall_s"]))
    print("ruler at that precision: %.1f dB (headroom %.1f dB)" % (a["ruler_db"], a["ruler_db"] - a["target_db"]))
