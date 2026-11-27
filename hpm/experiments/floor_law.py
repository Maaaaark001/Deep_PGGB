"""Arbitrary-precision measurement floors: what actually sets the floor.

All experiments use exact integer-phase sinusoids and solve the measurement
problem at a chosen decimal precision, so every floor reported here is either
arithmetic (scales with digits) or an artefact of the estimator (does not).
"""
import contextlib, json, math, time
from mpmath import mp, mpf, cos, sin, sqrt, log10, acos, matrix, lu_solve, iv

@contextlib.contextmanager
def ivdps(d):
    old = iv.dps
    iv.dps = d
    try:
        yield
    finally:
        iv.dps = old

def tone(f, fs, n, dps, amp=mpf("0.5"), phase=mpf(0)):
    with mp.workdps(dps + 10):
        w = 2 * mp.pi * mpf(f) / mpf(fs)
        return [amp * sin(w * i + phase) for i in range(n)], w

def ls2(x, w0, win=None, dps=50):
    """Solve the full 2x2 normal equations for a*cos + b*sin at omega=w0."""
    with mp.workdps(dps):
        n = len(x)
        cc = ss = cs = xc = xs = 0
        for i in range(n):
            wi = 1 if win is None else win[i]
            c = cos(w0 * i); s = sin(w0 * i)
            cc += wi * c * c; ss += wi * s * s; cs += wi * c * s
            xc += wi * c * x[i]; xs += wi * s * x[i]
        G = matrix([[cc, cs], [cs, ss]])
        b = matrix([xc, xs])
        ab = lu_solve(G, b)
        r2 = x2 = 0
        for i in range(n):
            wi = 1 if win is None else win[i]
            m = ab[0] * cos(w0 * i) + ab[1] * sin(w0 * i)
            d = x[i] - m
            r2 += wi * d * d
            x2 += wi * x[i] * x[i]
        return 10 * log10(x2 / r2), ab

def dft1(x, w0, dps=50):
    """The classic single-bin estimate: project on cos and sin independently."""
    with mp.workdps(dps):
        n = len(x)
        cc = ss = xc = xs = 0
        for i in range(n):
            c = cos(w0 * i); s = sin(w0 * i)
            cc += c * c; ss += s * s
            xc += c * x[i]; xs += s * x[i]
        a = xc / cc; b = xs / ss
        r2 = x2 = 0
        for i in range(n):
            d = x[i] - (a * cos(w0 * i) + b * sin(w0 * i))
            r2 += d * d; x2 += x[i] * x[i]
        return 10 * log10(x2 / r2)

def main():
    fs, N = 8000, 4096
    out = {}

    # 1. floor vs precision, coherent tone, full 2x2 solve
    rows = []
    for dps in (20, 40, 60, 80, 120):
        x, w0 = tone(1000, fs, N, dps)
        t0 = time.perf_counter()
        nd, _ = ls2(x, w0, None, dps)
        dt = time.perf_counter() - t0
        rows.append({"dps": dps, "bits": round(dps * 3.3219, 1), "null_db": round(float(nd), 1), "wall_s": round(dt, 3)})
    out["coherent_ls2"] = rows

    # 2. same, non-coherent (1000.5 Hz), full solve
    rows = []
    for dps in (20, 60, 120):
        x, w0 = tone(1000.5, fs, N, dps)
        nd, _ = ls2(x, w0, None, dps)
        rows.append({"dps": dps, "bits": round(dps * 3.3219, 1), "null_db": round(float(nd), 1)})
    out["noncoherent_ls2"] = rows

    # 3. the classic single-bin shortcut on the same non-coherent data
    rows = []
    for dps in (20, 60, 120):
        x, w0 = tone(1000.5, fs, N, dps)
        rows.append({"dps": dps, "null_db": round(float(dft1(x, w0, dps)), 1)})
    out["noncoherent_dft1"] = rows

    # 4. unknown frequency: three-sample linear prediction then 2x2 solve
    for dps in (40, 120):
        x, w0 = tone(1000.5, fs, N, dps)
        with mp.workdps(dps):
            w_hat = acos((x[N // 2] + x[N // 2 + 2]) / (2 * x[N // 2 + 1]))
            nd, _ = ls2(x, w_hat, None, dps)
            err = abs(w_hat - w0) / w0
        out["lp_recovered_" + str(dps)] = {"null_db": round(float(nd), 1), "freq_rel_err": float(err)}

    # 5. windowed (Hann) full solve on non-coherent data
    for dps in (60,):
        x, w0 = tone(1000.5, fs, N, dps)
        with mp.workdps(dps):
            win = [mpf("0.5") * (1 - cos(2 * mp.pi * i / (N - 1))) for i in range(N)]
        nd, _ = ls2(x, w0, win, dps)
        out["hann_ls2_" + str(dps)] = {"null_db": round(float(nd), 1)}

    # 6. certified bound with interval arithmetic (small N)
    N2 = 512
    x, w0 = tone(1000.5, fs, N2, 60)
    with mp.workdps(70), ivdps(60):
        xi = [iv.mpf(v) for v in x]
        cc = ss = cs = xc = xs = 0
        for i in range(N2):
            c = iv.cos(w0 * i); s = iv.sin(w0 * i)
            cc += c * c; ss += s * s; cs += c * s
            xc += c * xi[i]; xs += s * xi[i]
        det = cc * ss - cs * cs
        a = (xc * ss - xs * cs) / det
        b = (cc * xs - cs * xc) / det
        r2 = x2 = 0
        for i in range(N2):
            d = xi[i] - (a * iv.cos(w0 * i) + b * iv.sin(w0 * i))
            r2 += d * d; x2 += xi[i] * xi[i]
        # r2 is a rigorous enclosure that straddles zero, so the honest
        # statement is a certified UPPER bound on the residual energy:
        # null >= -10 log10( hi(r2) / lo(x2) ).
        bound = -10 * math.log10(float(r2.b) / float(x2.a))
        out["certified_iv"] = {"N": N2, "r2_lo": float(r2.a), "r2_hi": float(r2.b),
                               "x2_lo": float(x2.a), "certified_null_min_db": round(bound, 1)}

    print(json.dumps(out, indent=1))

main()