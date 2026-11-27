"""Certified audio measurement on Arb balls.

A result is an enclosure, so "null >= 1165 dB" is a statement about the data,
not about the estimator's luck.
"""
import math
from flint import arb, arb_mat, ctx


def setbits(bits):
    ctx.prec = bits


def tone(f, fs, N, amp="0.5", bits=400):
    """Exact integer-phase sinusoid: the phase argument uses (f*n mod fs)."""
    old = ctx.prec
    ctx.prec = bits
    a = arb(amp)
    two_pi = 2 * arb.pi()
    out = [a * (two_pi * arb((f * i) % fs) / arb(fs)).sin() for i in range(N)]
    ctx.prec = old
    return out


def omega(f, fs, bits=400):
    """2*pi*f/fs evaluated at the working precision (not at the caller's)."""
    old = ctx.prec
    ctx.prec = bits
    w = 2 * arb.pi() * arb(f) / arb(fs)
    ctx.prec = old
    return w


def basis_exact(f, fs, N, bits=400):
    """[(cos, sin)] from the *integer* phase 2*pi*((f*i) mod fs)/fs.

    cos(w*i) loses accuracy like i*w*eps because the argument reduction happens
    after the multiplication; reducing (f*i) mod fs in exact integers first keeps
    the radius at ~16 eps for every i.  Measured gain at 240 bit: 12.8 dB at
    1 kHz, 20.7 dB at 4 kHz, 1.9 dB at 100 Hz (N=4096).
    """
    old = ctx.prec
    ctx.prec = bits
    tp = 2 * arb.pi()
    out = [((tp * arb((f * i) % fs) / arb(fs)).cos(),
            (tp * arb((f * i) % fs) / arb(fs)).sin()) for i in range(N)]
    ctx.prec = old
    return out


def basis(omega, N, bits=400):
    """[(cos(w i), sin(w i))] for i < N, evaluated once and reused."""
    old = ctx.prec
    ctx.prec = bits
    out = []
    for i in range(N):
        t = omega * i
        out.append((t.cos(), t.sin()))
    ctx.prec = old
    return out


def ls_known(x, omegas, window=None, bits=400, cs=None):
    """Weighted LS for K tones of *known* angular frequency.

    Returns (coeffs, r2, x2, cs) with r2 = sum w r^2 and x2 = sum w x^2.
    """
    old = ctx.prec
    ctx.prec = bits
    K = len(omegas)
    N = len(x)
    m = 2 * K
    if cs is None:
        cs = [basis(w, N, bits) for w in omegas]
    G = [[arb(0) for _ in range(m)] for _ in range(m)]
    b = [arb(0) for _ in range(m)]
    for i in range(N):
        wi = arb(1) if window is None else window[i]
        vals = [(cs[k][i][0], cs[k][i][1]) for k in range(K)]
        xi = arb(x[i])
        for p in range(K):
            cp, sp = vals[p]
            for q in range(p, K):
                cq, sq = vals[q]
                G[2 * p][2 * q] += wi * cp * cq
                G[2 * p][2 * q + 1] += wi * cp * sq
                G[2 * p + 1][2 * q] += wi * sp * cq
                G[2 * p + 1][2 * q + 1] += wi * sp * sq
            b[2 * p] += wi * cp * xi
            b[2 * p + 1] += wi * sp * xi
    for p in range(m):
        for q in range(p):
            G[p][q] = G[q][p]
    sol = list(arb_mat(G).solve(arb_mat([[v] for v in b])))
    coeffs = list(sol)
    r2 = arb(0)
    x2 = arb(0)
    for i in range(N):
        wi = arb(1) if window is None else window[i]
        s = arb(0)
        for k in range(K):
            c, sn = cs[k][i]
            s += coeffs[2 * k] * c + coeffs[2 * k + 1] * sn
        xi = arb(x[i])
        d = xi - s
        r2 += wi * d * d
        x2 += wi * xi * xi
    ctx.prec = old
    return coeffs, r2, x2, cs


def null_upper_db(r2, x2):
    """Certified lower bound on null depth, from the upper bound on r2."""
    hi = r2.abs_upper()
    lo = x2.abs_lower()
    if hi == 0:
        return float("inf")
    if lo <= 0:
        return None
    return float(-10.0 * (hi.log() - lo.log()) / arb(10).log())


def null_mid_db(r2, x2):
    m = r2.mid()
    if m < 0:
        m = -m
    if m == 0:
        return float("inf")
    return float(-10.0 * (m.log() - x2.mid().log()) / arb(10).log())


def newton(x, omegas0, bits=400, iters=6, window=None):
    """Gauss-Newton on (a_k, b_k, w_k) for K tones of unknown frequency."""
    old = ctx.prec
    ctx.prec = bits
    K = len(omegas0)
    omegas = [arb(w) for w in omegas0]
    coeffs, r2, x2, cs = ls_known(x, omegas, window, bits)
    a = [coeffs[2 * k] for k in range(K)]
    b = [coeffs[2 * k + 1] for k in range(K)]
    N = len(x)
    hist = []
    for _ in range(iters):
        npar = 3 * K
        JtJ = [[arb(0) for _ in range(npar)] for _ in range(npar)]
        Jtr = [arb(0) for _ in range(npar)]
        for i in range(N):
            wi = arb(1) if window is None else window[i]
            cols = []
            for k in range(K):
                c, s = cs[k][i]
                cols.append(c)
                cols.append(s)
                cols.append(-a[k] * arb(i) * s + b[k] * arb(i) * c)
            xi = arb(x[i])
            mi = arb(0)
            for k in range(K):
                c, s = cs[k][i]
                mi += a[k] * c + b[k] * s
            ri = xi - mi
            for p in range(npar):
                Jtr[p] += wi * cols[p] * ri
                for q in range(p, npar):
                    JtJ[p][q] += wi * cols[p] * cols[q]
        for p in range(npar):
            for q in range(p):
                JtJ[p][q] = JtJ[q][p]
        delta = list(arb_mat(JtJ).solve(arb_mat([[v] for v in Jtr])))
        for k in range(K):
            a[k] += delta[3 * k]
            b[k] += delta[3 * k + 1]
            omegas[k] += delta[3 * k + 2]
        cs = [basis(omegas[k], N, bits) for k in range(K)]
        # residual for reporting
        r2 = arb(0)
        x2 = arb(0)
        for i in range(N):
            wi = arb(1) if window is None else window[i]
            mi = arb(0)
            for k in range(K):
                c, s = cs[k][i]
                mi += a[k] * c + b[k] * s
            xi = arb(x[i])
            d = xi - mi
            r2 += wi * d * d
            x2 += wi * xi * xi
        hist.append((null_upper_db(r2, x2), float(omegas[0])))
    ctx.prec = old
    return a, b, omegas, r2, x2, hist
