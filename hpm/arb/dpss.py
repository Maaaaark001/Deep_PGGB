"""Discrete prolate spheroidal sequences (Slepian) at arbitrary precision.

The order-0 DPSS maximises the energy inside |f| < W.  Its concentration
lambda0 = v^T K v / v^T v with K_nm = sin(2 pi W (n-m)) / (pi (n-m)) is the
in-band fraction, so 1 - lambda0 is the window's own leakage floor.  Because a
Rayleigh quotient of a symmetric matrix never exceeds the top eigenvalue,
RQ(v) <= lambda0 rigorously, hence 10 log10(1 - RQ) is a certified *upper*
bound on the leakage.
"""
from flint import arb, ctx


def _diag_off(N, W, bits):
    old = ctx.prec
    ctx.prec = bits
    c = (2 * arb.pi() * arb(W)).cos()
    diag = [((arb(N - 1 - 2 * n) / 2) ** 2) * c for n in range(N)]
    off = [arb(n) * arb(N - n) / 2 for n in range(1, N)]
    ctx.prec = old
    return diag, off


def _count_below(diag, off, lam):
    d = diag[0] - lam
    if not (d < 0 or d > 0):
        raise ArithmeticError("pivot straddles zero; raise precision")
    cnt = 1 if d < 0 else 0
    for i in range(1, len(diag)):
        d = diag[i] - lam - off[i - 1] ** 2 / d
        if not (d < 0 or d > 0):
            raise ArithmeticError("pivot straddles zero; raise precision")
        if d < 0:
            cnt += 1
    return cnt


def top_eigenvalue(N, W, bits=200, iters=300):
    """Rigorous enclosure of the largest eigenvalue of the Slepian tridiagonal."""
    old = ctx.prec
    ctx.prec = bits
    diag, off = _diag_off(N, W, bits)
    lo, hi = arb(0), arb(4 * (N / 2) ** 2)
    for _ in range(iters):
        mid = (lo + hi) / 2
        try:
            n = _count_below(diag, off, mid)
        except ArithmeticError:          # mid is inside the eigenvalue's own ball
            break
        if n == N:
            hi = mid
        else:
            lo = mid
    ctx.prec = old
    return lo, hi


def _thomas(diag, off, lam, rhs):
    n = len(diag)
    cp = [arb(0)] * n
    dp = [arb(0)] * n
    cp[0] = diag[0] - lam
    dp[0] = rhs[0]
    for i in range(1, n):
        cp[i] = diag[i] - lam - off[i - 1] ** 2 / cp[i - 1]
        dp[i] = rhs[i] - off[i - 1] * dp[i - 1] / cp[i - 1]
    x = [arb(0)] * n
    x[-1] = dp[-1] / cp[-1]
    for i in range(n - 2, -1, -1):
        x[i] = (dp[i] - off[i] * x[i + 1]) / cp[i]
    return x


def _kernel_RQ(v, W, bits):
    """v^T K v / v^T v with K_nm = sin(2 pi W (n-m)) / (pi (n-m)); certified ball."""
    old = ctx.prec
    ctx.prec = bits
    N = len(v)
    two_pi_W = 2 * arb.pi() * arb(W)
    num = arb(0)
    den = arb(0)
    for n in range(N):
        for m in range(N):
            d = n - m
            k = 2 * arb(W) if d == 0 else (two_pi_W * arb(d)).sin() / (arb.pi() * arb(d))
            num += v[n] * v[m] * k
        den += v[n] * v[n]
    ctx.prec = old
    return num / den


def dpss0(N, W, bits=200, sweeps=8):
    """Order-0 DPSS (peak-normalised) plus a certified enclosure of its concentration."""
    old = ctx.prec
    ctx.prec = bits
    diag, off = _diag_off(N, W, bits)
    lo, hi = top_eigenvalue(N, W, bits)
    # shift strictly outside the eigenvalue, otherwise the Thomas solve is singular
    lam = hi + (hi - lo) + abs(hi) * arb(10) ** -30
    v = [arb(1) / arb(i + 1) for i in range(N)]
    for k in range(sweeps):
        w = _thomas(diag, off, lam, v)
        nrm = sum((t * t for t in w), arb(0)).sqrt()
        v = [t / nrm for t in w]
    lam0 = _kernel_RQ(v, W, bits)
    peak = max(abs(t) for t in v)
    v = [t / peak for t in v]
    ctx.prec = old
    return v, lam0


def leakage_upper_db(lam0):
    """Certified upper bound on the out-of-band fraction, in dB."""
    return float(10.0 * ((arb(1) - lam0).log() / arb(10).log()))


def concentration(N, W, bits=None, target_leak_db=-400.0):
    """lambda0 with enough working precision that 1 - lambda0 keeps its digits.

    `1 - lambda0` is a difference of two numbers that both approach 1, so it
    loses log10(1/leak) digits outright: at 160 bits a NW=6 window returns a ball
    for lambda0 that straddles 1 and the leakage reads nan.  Raise the precision
    until the ball for 1 - lambda0 is strictly positive.
    """
    from flint import ctx
    b = bits or 160
    old = ctx.prec
    try:
        for _ in range(8):
            v, lam0 = dpss0(N, W, b)
            ctx.prec = b
            rest = arb(1) - lam0
            ctx.prec = old
            if rest.mid() > rest.rad() and rest.mid() > 0:
                return lam0, rest, b
            b = int(b * 1.8) + 60
        raise ArithmeticError("could not resolve 1 - lambda0; raise precision")
    finally:
        ctx.prec = old
