"""Certificate loss budget: where does 6.02*bits go?

Splits the gap between the ideal 6.02 dB/bit and the achieved certificate into
  (a) a size term      20 log10(N)          (normal-equation accumulation)
  (b) a frequency term Gram-matrix conditioning near Nyquist
  (c) a constant       ~11.4 dB             (energy halving + accumulation factor)
and measures the Newton certificate decay separately, because that is the one
term that is a property of the *estimator* rather than of the data.
"""
import sys, json, time, math
sys.path.insert(0, ".")
from flint import arb, ctx
from hpm.arb import mcore

FS = 8000
OUT = {}


def gram_cond(w, N, bits):
    """Condition number of the 2x2 Gram matrix of [cos w i, sin w i]."""
    old = ctx.prec
    ctx.prec = bits
    cc = ss = cs = arb(0)
    for i in range(N):
        c, s = (w * i).cos(), (w * i).sin()
        cc += c * c
        ss += s * s
        cs += c * s
    tr = cc + ss
    disc = ((cc - ss) ** 2 + 4 * cs * cs).sqrt()
    lo = tr - disc
    cond = float((tr + disc) / lo) if lo.mid() > 0 else float("inf")
    ctx.prec = old
    return cond


def run(bits, N, f, fs=FS):
    x = mcore.tone(f, fs, N, "0.5", bits + 60)
    w = mcore.omega(f, fs, bits + 60)
    c, r2, x2, _ = mcore.ls_known(x, [w], None, bits)
    nul = mcore.null_upper_db(r2, x2)
    return nul, 6.017 * bits - nul, max(v.rad() for v in c)


def part_a():
    rows = []
    for bits in (60, 120, 240, 480, 960, 1920, 3840):
        t0 = time.time()
        nul, gap, crad = run(bits, 4096, 1000)
        rows.append(dict(bits=bits, null_db=nul, gap_db=gap, coeff_rad=crad, wall_s=time.time() - t0))
        print("[A] bits=%5d gap=%6.2f dB  coeff_rad=%.2e" % (bits, gap, crad))
    return rows


def part_b():
    rows = []
    for N in (256, 512, 1024, 2048, 4096, 8192, 16384):
        nul, gap, crad = run(240, N, 1000)
        rows.append(dict(N=N, gap_db=gap, gap_minus_20logN=gap - 20 * math.log10(N),
                         coeff_over_eps=crad / (2.0 ** -240), wall_s=0))
        print("[B] N=%6d gap=%6.2f  gap-20logN=%6.2f  coeff/eps=%.3e" %
              (N, gap, gap - 20 * math.log10(N), crad / 2.0 ** -240))
    return rows


def part_c():
    rows = []
    for f in (100, 250, 500, 1000, 2000, 3000, 3500, 3800, 3900, 3950, 3990):
        nul, gap, _ = run(240, 4096, f)
        cond = gram_cond(mcore.omega(f, FS, 300), 4096, 300)
        rows.append(dict(f=f, f_over_fs=f / FS, gap_db=gap, cond=cond,
                         log10cond=math.log10(cond) if cond > 0 else None))
        print("[C] f=%5d (%.4f fs) gap=%6.2f dB  cond=%.3e" % (f, f / FS, gap, cond))
    return rows


def part_d():
    """Does the frequency term follow the Gram condition number?"""
    rows = []
    for f in (1000, 2000, 3000, 3500, 3800, 3900, 3950, 3990):
        nul, gap, _ = run(240, 4096, f)
        cond = gram_cond(mcore.omega(f, FS, 300), 4096, 300)
        rows.append(dict(f=f, gap_db=gap, cond=cond,
                         gap_minus_10logcond=gap - 10 * math.log10(cond)))
        print("[D] f=%5d gap=%6.2f  gap-10log10(cond)=%6.2f" % (f, gap, gap - 10 * math.log10(cond)))
    return rows


def part_e():
    """Newton: certificate decay per iteration (a property of the estimator)."""
    bits = 600
    fmilli, fs_milli, N = 1000500, FS * 1000, 4096
    x = mcore.tone(fmilli, fs_milli, N, "0.5", bits + 60)
    true_w = mcore.omega(fmilli, fs_milli, bits + 60)
    w0 = ((x[0] + x[2]) / (2 * x[1])).acos()
    a, b, omegas, r2, x2, hist = mcore.newton(x, [w0], bits, iters=7)
    rows = [dict(iter=0, null_db=mcore.null_upper_db(r2, x2),
                 w_rad=float((w0 - true_w).abs_upper()), kind="LP init")]
    # rerun capturing per-iteration radii
    old = ctx.prec
    ctx.prec = bits
    K = 1
    aa, bb = a, b
    om = [arb(w0)]
    for it in range(7):
        cs = [mcore.basis(om[0], N, bits)]
        npar = 3
        JtJ = [[arb(0) for _ in range(npar)] for _ in range(npar)]
        Jtr = [arb(0) for _ in range(npar)]
        for i in range(N):
            c, s = cs[0][i]
            cols = [c, s, -aa[0] * arb(i) * s + bb[0] * arb(i) * c]
            mi = aa[0] * c + bb[0] * s
            ri = x[i] - mi
            for p in range(npar):
                Jtr[p] += cols[p] * ri
                for q in range(p, npar):
                    JtJ[p][q] += cols[p] * cols[q]
        for p in range(npar):
            for q in range(p):
                JtJ[p][q] = JtJ[q][p]
        from flint import arb_mat
        delta = list(arb_mat(JtJ).solve(arb_mat([[v] for v in Jtr])))
        aa[0] += delta[0]
        bb[0] += delta[1]
        om[0] += delta[2]
        cs = [mcore.basis(om[0], N, bits)]
        rr = arb(0)
        xx = arb(0)
        for i in range(N):
            c, s = cs[0][i]
            d = x[i] - (aa[0] * c + bb[0] * s)
            rr += d * d
            xx += x[i] * x[i]
        rows.append(dict(iter=it + 1, null_db=mcore.null_upper_db(rr, xx),
                         w_rad=float(om[0].rad()), w_err=float((om[0] - true_w).abs_upper()),
                         kind="newton"))
        print("[E] iter %d  null>=%8.1f dB  w_rad=%.2e  w_err=%.2e" %
              (it + 1, rows[-1]["null_db"], rows[-1]["w_rad"], rows[-1]["w_err"]))
    ctx.prec = old
    return rows


if __name__ == "__main__":
    OUT["a_bits"] = part_a()
    OUT["b_size"] = part_b()
    OUT["c_frequency"] = part_c()
    OUT["d_conditioning"] = part_d()
    OUT["e_newton"] = part_e()
    with open("hpm/experiments/results_budget.json", "w") as fh:
        json.dump(OUT, fh, indent=1)
    print("wrote hpm/experiments/results_budget.json")
