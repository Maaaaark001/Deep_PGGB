"""Branch C roadmap steps 1, 2, 3, 5 in Arb ball arithmetic.

Step 1  floor law at arbitrary precision, with certificates (Arb instead of mpmath)
Step 2  two-tone IMD through a known cubic DUT, every product certified
Step 3  non-coherent + unknown frequency: LP init + Gauss-Newton, no coherent sampling
Step 5  DPSS at arbitrary precision, and window-aware LS
"""
import sys, time, json, math
sys.path.insert(0, ".")
from flint import arb, ctx
from mpmath import mp, mpf
from hpm.arb import mcore


def step1():
    FS, F, N = 8000, 1000, 4096
    rows = []
    for bits in (60, 120, 240, 480, 960, 1920, 3840):
        t0 = time.time()
        x = mcore.tone(F, FS, N, "0.5", bits + 60)
        w = mcore.omega(F, FS, bits + 60)
        c, r2, x2, _ = mcore.ls_known(x, [w], None, bits)
        dt = time.time() - t0
        dbv = mcore.null_upper_db(r2, x2)
        rows.append(dict(bits=bits, ceiling_db=6.017 * bits, null_db=dbv,
                         gap_db=6.017 * bits - dbv, wall_s=dt))
        print(f"[1] bits={bits:5d} null={dbv:12.2f} dB  gap={6.017*bits-dbv:6.1f}  {dt:6.2f} s")
    return rows


def bench_mpmath(dps, N=4096, fs=8000, f=1000):
    mp.dps = dps + 10
    x = [mpf(0.5) * mp.sin(2 * mp.pi * ((f * i) % fs) / fs) for i in range(N)]
    mp.dps = dps
    w = 2 * mp.pi * f / fs
    cc = ss = cs = 0
    for i in range(N):
        c, s = mp.cos(w * i), mp.sin(w * i)
        cc += c * c; ss += s * s; cs += c * s
    bc = sum(x[i] * mp.cos(w * i) for i in range(N))
    bs = sum(x[i] * mp.sin(w * i) for i in range(N))
    det = cc * ss - cs * cs
    a = (bc * ss - bs * cs) / det
    b = (bs * cc - bc * cs) / det
    r2 = mpf(0)
    for i in range(N):
        r = x[i] - a * mp.cos(w * i) - b * mp.sin(w * i)
        r2 += r * r
    x2 = sum(v * v for v in x)
    return float(-10 * mp.log10(r2 / x2))


def step1b_conditioning():
    rows = []
    for N in (512, 1024, 2048, 4096, 8192):
        x = mcore.tone(1000, 8000, N, "0.5", 400)
        w = mcore.omega(1000, 8000, 400)
        c, r2, x2, _ = mcore.ls_known(x, [w], None, 240)
        rows.append(dict(kind="N", value=N, gap_db=6.017 * 240 - mcore.null_upper_db(r2, x2)))
    for f in (500, 1000, 2000, 3000, 3999):
        x = mcore.tone(f, 8000, 4096, "0.5", 400)
        w = mcore.omega(f, 8000, 400)
        c, r2, x2, _ = mcore.ls_known(x, [w], None, 240)
        rows.append(dict(kind="f", value=f, gap_db=6.017 * 240 - mcore.null_upper_db(r2, x2)))
    return rows


def step2_imd(bits=400):
    FS, N = 44100, 22050
    F1, F2 = 19000, 20000
    old = ctx.prec
    ctx.prec = bits + 80
    try:
        A = arb("0.25")
        w1, w2 = mcore.omega(F1, FS, bits + 60), mcore.omega(F2, FS, bits + 60)
        cs1 = mcore.basis(w1, N, bits)
        cs2 = mcore.basis(w2, N, bits)
        x = [A * (cs1[i][0] + cs2[i][0]) for i in range(N)]
        prod = {2 * F1 - F2: "2f1-f2", 2 * F2 - F1: "2f2-f1", F2 - F1: "f2-f1",
                (3 * F1) % FS: "3f1(alias)", (2 * F1 + F2) % FS: "2f1+f2(alias)",
                (2 * F2 + F1) % FS: "2f2+f1(alias)", (3 * F2) % FS: "3f2(alias)"}
        out = []
        for a3 in ("1e-3", "1e-6", "1e-9", "1e-12", "1e-15"):
            t0 = time.time()
            a3v = arb(a3)
            y = [x[i] + a3v * x[i] ** 3 for i in range(N)]
            c, r2, x2, _ = mcore.ls_known(y, [w1, w2], None, bits, cs=[cs1, cs2])
            rr = []
            for i in range(N):
                mi = c[0] * cs1[i][0] + c[1] * cs1[i][1] + c[2] * cs2[i][0] + c[3] * cs2[i][1]
                rr.append(y[i] - mi)
            sol = {}
            for fp, name in prod.items():
                wp = mcore.omega(fp, FS, bits)
                csp = mcore.basis(wp, N, bits)
                cp, r2p, x2p, _ = mcore.ls_known(rr, [wp], None, bits, cs=[csp])
                # squaring a zero-midpoint ball returns nan in python-flint, so take
                # a certified magnitude bound instead of the ball square
                amp = (arb(cp[0].abs_upper()) ** 2 + arb(cp[1].abs_upper()) ** 2).sqrt()
                sol[name] = float(20 * (amp.log() - A.log()) / arb(10).log())
            row = dict(a3=a3, total_db=mcore.null_upper_db(r2, x2),
                       theory_imd3_db=float(20 * math.log10(0.75 * float(a3v) * (0.25 ** 3) / 0.25)),
                       products_dbc=sol, wall_s=time.time() - t0)
            out.append(row)
            print(f"[2] a3={a3:>6s} total={row['total_db']:9.2f} dB  2f1-f2={sol['2f1-f2']:9.2f} dBc "
                  f"(theory {row['theory_imd3_db']:.2f})  {row['wall_s']:.1f} s")
        return out
    finally:
        ctx.prec = old


def step3_unknown_frequency(bits=600):
    FS, N = 8000, 4096
    out = []
    cases = [("1000.5", None), ("1234.567", None), ("1999.37", None),
             ("1000.5", ("3f", -120))]
    for f_hz, harm in cases:
        fmilli = int(round(mpf(f_hz) * 1000))
        fs_milli = FS * 1000
        old = ctx.prec
        ctx.prec = bits + 80
        try:
            x = mcore.tone(fmilli, fs_milli, N, "0.5", bits + 60)
            if harm:                       # third harmonic at -120 dBc
                level = arb(10) ** arb(harm[1] / 20)
                xh = mcore.tone(3 * fmilli, fs_milli, N, "1", bits + 60)
                x = [x[i] + arb("0.5") * level * xh[i] for i in range(N)]
            true_w = mcore.omega(fmilli, fs_milli, bits + 60)
            x0, x1, x2s = x[0], x[1], x[2]
            w0 = ((x0 + x2s) / (2 * x1)).acos()
            a, b, omegas, r2, x2, hist = mcore.newton(x, [w0], bits, iters=5)
            f_hat = float(omegas[0].mid() / (2 * arb.pi()) * fs_milli / 1000)
            half = float(omegas[0].rad() / (2 * arb.pi()) * fs_milli / 1000) / 1000
            row = dict(f_hz=float(mpf(f_hz)), harmonic_db=harm[1] if harm else None,
                       null_db=mcore.null_upper_db(r2, x2),
                       null_mid_db=mcore.null_mid_db(r2, x2),
                       freq_rel_err=float((omegas[0] - true_w).abs_upper() / true_w),
                       lp_rel_err=float((w0 - true_w).abs_upper() / true_w),
                       f_hat_hz=f_hat, f_halfwidth_hz=half)
        finally:
            ctx.prec = old
        out.append(row)
        print(f"[3] f={f_hz:>8s} harm={harm[1] if harm else 0:4d} dBc  "
              f"null>={row['null_db']:8.1f} dB (mid {row['null_mid_db']:8.1f})  "
              f"w_err {row['freq_rel_err']:.1e} (LP {row['lp_rel_err']:.1e})")
    return out


def step5_dpss(bits=200):
    from hpm.arb import dpss as D
    FS, N = 8000, 512
    out = []
    for NW in (2.0, 2.5, 3.0, 4.0, 6.0):
        t0 = time.time()
        v, lam0 = D.dpss0(N, NW / N, bits)
        row = dict(N=N, NW=NW, lambda0=float(lam0), leak_db=D.leakage_upper_db(lam0),
                   wall_s=time.time() - t0)
        out.append(row)
        print(f"[5] N={N} NW={NW}: lambda0={float(lam0):.12f} leak<= {row['leak_db']:.1f} dB "
              f"({row['wall_s']:.1f} s)")
    v, lam0 = D.dpss0(N, 4.0 / N, bits)
    old = ctx.prec
    ctx.prec = bits + 80          # a 53-bit square of the window would seed a 1e-16 floor
    wgt = [arb(float(t)) ** 2 for t in v]
    ctx.prec = old
    x = mcore.tone(1000500, FS * 1000, N, "0.5", bits + 200)
    wtrue = mcore.omega(1000500, FS * 1000, bits + 200)
    c, r2, x2, _ = mcore.ls_known(x, [wtrue], None, bits)
    cw, r2w, x2w, _ = mcore.ls_known(x, [wtrue], wgt, bits)
    out.append(dict(case="no window", null_db=mcore.null_upper_db(r2, x2)))
    out.append(dict(case="DPSS NW=4 weighting", null_db=mcore.null_upper_db(r2w, x2w)))
    print(f"[5] non-coherent 1000.5 Hz: unwindowed {out[-2]['null_db']:.1f} dB, "
          f"DPSS-weighted {out[-1]['null_db']:.1f} dB")
    return out


if __name__ == "__main__":
    res = {}
    res["step1_precision_law"] = step1()
    res["step1_mpmath"] = [dict(dps=d, null_db=bench_mpmath(d)) for d in (60, 120)]
    res["step1b_conditioning"] = step1b_conditioning()
    res["step2_imd"] = step2_imd()
    res["step3_unknown_frequency"] = step3_unknown_frequency()
    res["step5_dpss"] = step5_dpss()
    with open("hpm/experiments/results_arb.json", "w") as f:
        json.dump(res, f, indent=1)
    print("wrote hpm/experiments/results_arb.json")
