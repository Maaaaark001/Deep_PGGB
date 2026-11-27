"""Certified (ball-arithmetic) measurement of audio files.

Two streaming passes: the first accumulates the normal equations for K tones of
known frequency, the second evaluates the residual energy and the level of every
intermodulation product.  Nothing is held in memory, so cost is O(N) per pass
and file length is free.

Every number returned is an enclosure.  `null_cert_db` is a *lower* bound on the
null depth of the data: a statement about the file, not about the estimator's
luck.  Two diagnostic channels say whether the reading is limited by the data or
by the ruler:

    coefficient channel  |dm| <= rad(a) + rad(b)            (free, from the solve)
    frequency channel    |dm/dw| <= i*A  =>  Lipschitz bound (free, closed form)

The coefficient channel is deliberately the triangle inequality: it adds the two
radii, so it over-states the true model error by sqrt(2) in amplitude, i.e. exactly
3.01 dB in power.  Measured, the certificate sits 3.0 dB above this bound at every
(p, N) - the gap is the looseness of the bound, not a property of the data.
Quadrature (rad(a)^2 + rad(b)^2)/2 reproduces the certificate to 0.05 dB, but it is
not a bound: the radii are not independent random variables.  The reported
null_cert_db comes from the residual enclosure r2 and is rigorous; this channel is
the diagnostic that says which stage owns the floor.

The model carries a constant (DC) column, fitted together with the tones.  Without
it a biased segment hides its offset in the residual: a 24-bit sine whose 12 s
segment sits 5.9e-8 below zero reads 134.3 dB instead of 140.7 dB, because 77% of
the residual energy is that one number.  DC is part of the model, not the null.
"""
from __future__ import annotations

import math
import os
import struct

from flint import arb, arb_mat, ctx

from . import f128

SIZES = {"f128": 16, "f64": 8}


def setbits(bits):
    ctx.prec = bits


def omega(f, fs, bits=400):
    """2*pi*f/fs evaluated at the working precision, not at the caller's."""
    old = ctx.prec
    ctx.prec = bits
    w = 2 * arb.pi() * arb(f) / arb(fs)
    ctx.prec = old
    return w


def _exact_ok(f, fs):
    """The exact-integer-phase basis needs f and fs to be whole numbers."""
    return float(f).is_integer() and float(fs).is_integer()


def unit_omega(fs):
    """2*pi/fs at the current precision, computed once per file."""
    return 2 * arb.pi() / arb(int(fs))


def phasor(f, fs, i, exact, unit=None):
    """cos/sin of the phase at sample i.

    With `exact` the phase is reduced as an integer (2*pi*((f*i) mod fs)/fs), so
    the argument never exceeds 2*pi and the ball stays at ~16 eps for every i.
    Without it the argument grows like i*w and the ball grows with it, which is
    the argument-reduction loss measured in hpm/experiments/run_phasebasis.py.

    `unit` is 2*pi/fs precomputed at the working precision; passing a float here
    would cap the phase at 53 bits and seed a floor.
    """
    if exact:
        if not (float(f).is_integer() and float(fs).is_integer()):
            # int() would silently truncate 1000.5 Hz to 1000 Hz, i.e. measure a
            # different stimulus than the one that was declared.
            raise ValueError("exact phase needs integer f and fs; use exact=False")
        t = (unit if unit is not None else unit_omega(fs)) * ((int(f) * i) % int(fs))
    else:
        t = 2 * arb.pi() * arb(f) / arb(fs) * i
    return t.cos(), t.sin()


def multitone(path, fs, freqs, bits=400, fmt="f128", skip_s=0.0, tail_s=0.0,
              total_s=None, order=3, block=1 << 15, fit_dc=True, window=None,
              fmin=20.0):
    """Certified multitone measurement: every product up to `order`.

    `measure` answers for a hand-written list of frequencies; this asks the
    question a multitone test actually asks - what is *everything else* in the
    file, product by product.  The products are enumerated by intermod_products
    (integer combinations up to `order`, aliased), the K input tones are fitted
    jointly, and each product is then projected out of the residual.

    The null certificate is the same residual enclosure as measure(), so it is
    still a statement about the file.  `products_db` holds one entry per
    product, in dBc relative to the *first* fitted tone amplitude (amp0, the
    one at freqs[0]); the product amplitudes themselves come from the 2x2
    normal equations of that product's own bin.  Passing the largest tone first
    is the convention that does not flatter the result when the tones differ.
    """
    prods = intermod_products(freqs, fs, order=order, fmin=fmin,
                               skip=tuple(freqs))
    pf = [f for f, _ in prods]
    r = measure(path, fs, freqs, bits=bits, fmt=fmt, skip_s=skip_s,
                tail_s=tail_s, total_s=total_s, products=pf, block=block,
                fit_dc=fit_dc, window=window)
    labels = {repr(f): lab for f, lab in prods}
    r['product_labels'] = {repr(f): labels.get(repr(f), '') for f in pf}
    r['product_freqs'] = pf
    r['order'] = order
    return r


def intermod_products(freqs, fs, order=3, fmin=20.0, fmax=None, skip=()):
    """Every intermodulation product of the given tones up to `order`, aliased.

    A product is an integer combination sum_k m_k f_k with sum_k |m_k| <= order
    (order 3 is the usual two-tone set: 2f1-f2, 2f2-f1, 3f1, 2f1+f2, ...).  Each
    is folded into [0, fs/2] the way a sampled system actually shows it, so a
    product at 41 kHz in a 44.1 kHz file appears at 3.1 kHz and is reported
    there - measuring the un-aliased frequency would read noise.

    Returns [(frequency, label)] sorted by frequency, deduplicated to 1e-9 Hz,
    with the input tones and anything in `skip` removed.
    """
    from itertools import product as _prod
    fs = float(fs)
    base = [float(f) for f in freqs]
    K = len(base)
    nyq = fs / 2.0
    fmax = nyq if fmax is None else float(fmax)
    drop = set(round(float(f), 9) for f in list(base) + list(skip))
    out = {}
    for ms in _prod(range(-order, order + 1), repeat=K):
        tot = sum(abs(m) for m in ms)
        if tot < 2 or tot > order:
            continue
        if all(m == 0 for m in ms):
            continue
        f = sum(m * b for m, b in zip(ms, base))
        f = abs(f) % fs
        if f > nyq:
            f = fs - f
        key = round(f, 9)
        if key < fmin or key > fmax or key in drop:
            continue
        label = ''.join(('%+d' % m if m else '') + 'f%d' % (k + 1)
                        for k, m in enumerate(ms) if m)
        if key in out and len(out[key]) <= len(label):
            continue
        out[key] = label
    return sorted(out.items())


WINDOWS = ("rect", "hann", "hamming", "blackman", "blackmanharris",
           "flattop", "nuttall")


def make_window(name, N, bits=None):
    """A window of length N as a list of Arb balls, evaluated at `bits`.

    The window is a *weight*, not a model term: it enters the normal equations
    and the energy sums, so the estimator minimises a weighted residual and the
    reported null is a weighted energy ratio.  That is what makes it neutral -
    the same data measured through different weights gives the same floor.  A
    window applied to the *transform* instead is a convolution, and its
    sidelobes are the floor; that difference is the whole point of
    experiments/run_window.py.

    Closed forms only, so cost is O(N) trig evaluations and any record length
    works.  DPSS is not here: its eigenvector costs O(N^2) and it is used at
    N <= 1024 in run_window.py, where it is passed in as an array.
    """
    if name in (None, "rect", "none"):
        return None
    if not isinstance(name, str):
        return list(name)
    name = name.lower()
    if name not in WINDOWS:
        raise ValueError(f"unknown window {name!r}; known: {WINDOWS}")
    old = ctx.prec
    ctx.prec = bits if bits else old
    try:
        two_pi = 2 * arb.pi()
        out = []
        for i in range(N):
            t = two_pi * arb(i) / arb(N - 1) if N > 1 else arb(0)
            c1, c2, c3 = t.cos(), (2 * t).cos(), (3 * t).cos()
            if name == "hann":
                v = arb("0.5") - arb("0.5") * c1
            elif name == "hamming":
                v = arb("0.54") - arb("0.46") * c1
            elif name == "blackman":
                v = arb("0.42") - arb("0.5") * c1 + arb("0.08") * c2
            elif name == "blackmanharris":
                v = (arb("0.35875") - arb("0.48829") * c1
                     + arb("0.14128") * c2 - arb("0.01168") * c3)
            elif name == "nuttall":
                v = (arb("0.355768") - arb("0.487396") * c1
                     + arb("0.144232") * c2 - arb("0.012604") * c3)
            else:  # flattop (SciPy coefficients)
                v = (arb("0.21557895") - arb("0.41663158") * c1
                     + arb("0.277263158") * c2 - arb("0.083578947") * c3
                     + arb("0.006947368") * (4 * t).cos())
            out.append(v)
        return out
    finally:
        ctx.prec = old


def probe_length(path, fmt="f128"):
    if fmt == "wav":
        import soundfile as sf
        return int(sf.info(path).frames)
    size = SIZES[fmt]
    n = os.path.getsize(path)
    if n % size:
        raise ValueError(f"file length {n} is not a multiple of {size} bytes")
    return n // size


def _wav_samples(path):
    import soundfile as sf
    data, fs = sf.read(path, dtype="float64", always_2d=True)
    return [float(v) for v in data[:, 0]], fs


def blocks(path, fmt, offset, count, block=1 << 15):
    """Yield consecutive lists of samples starting at sample `offset`."""
    if fmt == "wav":
        vals, _ = _wav_samples(path)
        seg = vals[offset:offset + count]
        for i in range(0, len(seg), block):
            yield seg[i:i + block]
        return
    size = SIZES[fmt]
    with open(path, "rb") as fh:
        fh.seek(offset * size)
        left = count
        while left > 0:
            n = min(block, left)
            raw = fh.read(n * size)
            if len(raw) != n * size:
                raise ValueError("short read: file holds fewer samples than requested")
            if fmt == "f128":
                yield [f128.to_arb(raw[i:i + 16]) for i in range(0, len(raw), 16)]
            else:
                yield list(struct.unpack("<" + str(n) + "d", raw))
            left -= n


def lipschitz_null_db(N, amp, dw):
    """Rigorous lower bound on the null when the angular frequency is only known
    to within `dw` (an Arb ball or a float; Arb is required for tiny dw, since
    dw^2 underflows a float below ~1e-154).

    |dm_i/dw| = |i(-a sin + b cos)| <= i*amp, so a frequency error dw moves the
    model by at most i*amp*dw at sample i.  Summing i^2 over the segment bounds
    the residual energy; dividing by the signal energy N*amp^2/2 gives

        null >= -10 log10( 2 * dw^2 * N(N+1)(2N+1)/6 / N )

    which is O(1) to evaluate and needs no ball arithmetic at all.  Measured
    against a deliberately perturbed model it is tight to 9.0 dB.
    """
    old = ctx.prec
    ctx.prec = max(old, 200)
    try:
        s = arb(N) * arb(N + 1) * arb(2 * N + 1) / 6
        d = dw if isinstance(dw, arb) else arb(dw)
        r2b = (d * d) * (arb(amp) * arb(amp)) * s
        x2b = arb(N) * arb(amp) * arb(amp) / 2
        return _db_ratio(r2b, x2b)
    finally:
        ctx.prec = old


def _db_ratio(r2, x2):
    """10*log10(r2/x2) as a float, computed with Arb logs (float underflows)."""
    hi = r2 if isinstance(r2, arb) else arb(r2)
    lo = x2 if isinstance(x2, arb) else arb(x2)
    if hi.abs_upper() == 0:
        return float("-inf")
    return float(10 * (hi.abs_upper().log() - lo.abs_lower().log()) / arb(10).log())


def measure_auto(path, fs, freqs, fmt="f128", bits_start=60, bits_step=6,
                 max_bits=1200, sat_db=3.0, skip_s=0.0, tail_s=0.0,
                 total_s=None, products=(), block=1 << 15, verbose=True,
                 fit_dc=True, window=None):
    """Sweep the precision upward until the certificate stops moving.

    The advisor answers "how many bits for target T", but on a real file T is
    what you are trying to find.  This inverts the question: raise the precision
    and watch the certificate.  While the estimator is the limit the certificate
    gains ~6 dB per bit; once the enclosure has closed on the file's own
    residual it stops, and the plateau is the answer.

    Returns (best, history).  `best` is the measurement at the plateau;
    `history` is the list of (bits, cert, mid) triples.
    """
    hist = []
    p = bits_start
    prev = None
    best = None
    while p <= max_bits:
        r = measure(path, fs, freqs, bits=p, fmt=fmt, skip_s=skip_s,
                    tail_s=tail_s, total_s=total_s, products=products, block=block,
                    fit_dc=fit_dc, window=window)
        hist.append(dict(bits=p, cert_db=r["null_cert_db"], mid_db=r["null_mid_db"]))
        if verbose:
            print("  p=%4d  cert %10.3f  mid %10.3f  gap %8.3f" %
                  (p, r["null_cert_db"], r["null_mid_db"],
                   r["null_mid_db"] - r["null_cert_db"]), flush=True)
        best = r
        if prev is not None:
            gain = r["null_cert_db"] - prev["null_cert_db"]
            if gain < sat_db:
                if verbose:
                    print("  saturated: %+.2f dB for %d more bits (< %.1f)" %
                          (gain, bits_step, sat_db))
                break
        prev = r
        p += bits_step
    return best, hist


def measure(path, fs, freqs, bits=400, fmt="f128", skip_s=0.0, tail_s=0.0,
            total_s=None, products=(), block=1 << 15, fit_dc=True,
            window=None):
    """Certified analysis of K tones plus optional IMD products.

    Returns a dict; `null_cert_db` is the certified lower bound on the null.
    With `fit_dc` the constant term joins the model (see the module docstring).
    `window` is a name from WINDOWS or an explicit array; it weights the
    estimator and the energy sums, so the reading stays a property of the file.
    """
    total = probe_length(path, fmt)
    if total_s is not None:
        total = min(total, int(round(total_s * fs)))
    skip_n = int(round(skip_s * fs))
    tail_n = int(round(tail_s * fs))
    N = total - skip_n - tail_n
    if N <= 1:
        raise ValueError("analysis segment is empty")

    old = ctx.prec
    ctx.prec = bits
    try:
        ws = [omega(f, fs, bits) for f in freqs]
        ex = [_exact_ok(f, fs) for f in freqs]
        unit = unit_omega(fs)
        win = make_window(window, N, bits)
        w2 = arb(0)
        K = len(ws)
        m = 2 * K + (1 if fit_dc else 0)
        G = [[arb(0) for _ in range(m)] for _ in range(m)]
        b = [arb(0) for _ in range(m)]
        sc = [arb(0) for _ in range(K)]
        ss = [arb(0) for _ in range(K)]
        x2 = arb(0)
        i = 0
        for blk in blocks(path, fmt, skip_n, N, block):
            for xv in blk:
                wi = arb(1) if win is None else win[i]
                cs = [phasor(freqs[k], fs, i, ex[k], unit) for k in range(K)]
                xi = arb(xv)
                for p in range(K):
                    cp, sp = cs[p]
                    for q in range(p, K):
                        cq, sq = cs[q]
                        G[2 * p][2 * q] += wi * cp * cq
                        G[2 * p][2 * q + 1] += wi * cp * sq
                        G[2 * p + 1][2 * q] += wi * sp * cq
                        G[2 * p + 1][2 * q + 1] += wi * sp * sq
                    b[2 * p] += wi * cp * xi
                    b[2 * p + 1] += wi * sp * xi
                    sc[p] += wi * cp
                    ss[p] += wi * sp
                x2 += wi * xi * xi
                w2 += wi
                if fit_dc:
                    b[2 * K] += wi * xi
                i += 1
        for p in range(m):
            for q in range(p):
                G[p][q] = G[q][p]
        if fit_dc:
            for p in range(K):
                G[2 * p][2 * K] = sc[p]
                G[2 * p + 1][2 * K] = ss[p]
                G[2 * K][2 * p] = sc[p]
                G[2 * K][2 * p + 1] = ss[p]
            G[2 * K][2 * K] = w2
        try:
            sol = list(arb_mat(G).solve(arb_mat([[v] for v in b])))
        except ZeroDivisionError:
            raise ValueError(
                f"the normal equations are singular at {bits} bit: the Gram matrix "
                f"cannot be resolved above the data's own dynamic range.  Raise --bits "
                f"(rule of thumb: 6.02*bits must exceed the signal's dynamic range by "
                f"~20*log10(N)).") from None
        a = [sol[2 * k] for k in range(K)]
        bb = [sol[2 * k + 1] for k in range(K)]
        dc = sol[2 * K] if fit_dc else arb(0)

        wprod = [omega(f, fs, bits) for f in products]
        exp_ = [_exact_ok(f, fs) for f in products]
        GP = [[[arb(0), arb(0)], [arb(0), arb(0)]] for _ in wprod]
        BP = [[arb(0), arb(0)] for _ in wprod]
        r2 = arb(0)
        i = 0
        for blk in blocks(path, fmt, skip_n, N, block):
            for xv in blk:
                wi = arb(1) if win is None else win[i]
                model = dc
                for k in range(K):
                    c, s = phasor(freqs[k], fs, i, ex[k], unit)
                    model += a[k] * c + bb[k] * s
                d = arb(xv) - model
                r2 += wi * d * d
                for j, w in enumerate(wprod):
                    c, s = phasor(products[j], fs, i, exp_[j], unit)
                    GP[j][0][0] += wi * c * c
                    GP[j][0][1] += wi * c * s
                    GP[j][1][0] += wi * c * s
                    GP[j][1][1] += wi * s * s
                    BP[j][0] += wi * c * d
                    BP[j][1] += wi * s * d
                i += 1

        amps = []
        for k in range(K):
            amps.append((arb(a[k].abs_upper()) ** 2 + arb(bb[k].abs_upper()) ** 2).sqrt())
        amp0 = amps[0]
        prod_db = {}
        for j, f in enumerate(products):
            M = arb_mat([[GP[j][0][0], GP[j][0][1]], [GP[j][1][0], GP[j][1][1]]])
            v = list(M.solve(arb_mat([[BP[j][0]], [BP[j][1]]])))
            amp = (arb(v[0].abs_upper()) ** 2 + arb(v[1].abs_upper()) ** 2).sqrt()
            prod_db[repr(f)] = float(20 * (amp.log() - amp0.log()) / arb(10).log())

        # --- the two ruler channels, both free and rigorous ---
        rad_model = sum((a[k].rad() + bb[k].rad()) for k in range(K)) + dc.rad()
        coef_db = -_db_ratio(arb(N) * rad_model * rad_model, x2)
        dw = max(w.rad() for w in ws)
        freq_db = -lipschitz_null_db(N, float(amp0.abs_upper()), float(dw))

        out = dict(path=path, fmt=fmt, fs=fs, freqs=list(freqs), N=N,
                   bits=bits, skip_n=skip_n,
                   amp=[float(v.abs_upper()) for v in amps],
                   amp_ball=[str(v) for v in amps],
                   coeffs=[(float(a[k].mid()), float(bb[k].mid())) for k in range(K)],
                   coeff_rad=[float(a[k].rad() + bb[k].rad()) for k in range(K)],
                   dc=float(dc.mid()), dc_rad=float(dc.rad()), fit_dc=fit_dc,
                   x2=float(x2.abs_lower()),
                   r2_mid=float(r2.mid()),
                   rms_residual=float((r2.mid() / arb(N)).sqrt()),
                   null_cert_db=float(-_db_ratio(r2, x2)),
                   null_mid_db=float(-_db_ratio(arb(r2.mid()), x2)),
                   ruler_coef_db=coef_db,
                   ruler_freq_db=freq_db,
                   ruler_db=min(coef_db, freq_db),
                   dw=float(dw),
                   products_db=prod_db)
        return out
    finally:
        ctx.prec = old
