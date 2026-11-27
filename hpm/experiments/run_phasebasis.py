import sys, math, json
sys.path.insert(0, ".")
from flint import arb, arb_mat, ctx

FS = 8000

def basis_mul(w, N, bits):
    return [((w * i).cos(), (w * i).sin()) for i in range(N)]

def basis_exact(f, fs, N, bits):
    tp = 2 * arb.pi()
    return [((tp * arb((f * i) % fs) / arb(fs)).cos(),
             (tp * arb((f * i) % fs) / arb(fs)).sin()) for i in range(N)]

def solve(x, cs, N, bits):
    cc = ss = csg = bc = bs = arb(0)
    for i in range(N):
        c, s = cs[i]
        xi = x[i]
        cc += c * c; ss += s * s; csg += c * s
        bc += c * xi; bs += s * xi
    G = arb_mat([[cc, csg], [csg, ss]])
    sol = list(G.solve(arb_mat([[bc], [bs]])))
    a, b = sol
    r2 = arb(0); x2 = arb(0)
    for i in range(N):
        c, s = cs[i]
        d = x[i] - (a * c + b * s)
        r2 += d * d; x2 += x[i] * x[i]
    hi = r2.abs_upper(); lo = x2.abs_lower()
    return float(-10 * (hi.log() - lo.log()) / arb(10).log()), float(r2.rad()), float(max(a.rad(), b.rad()))

rows = []
for N in (1024, 4096):
    for f in (100, 500, 1000, 2000, 3000, 3990):
        bits = 240
        ctx.prec = bits + 60
        x = [arb("0.5") * ((2 * arb.pi() * arb((f * i) % FS) / arb(FS)).sin()) for i in range(N)]
        w = 2 * arb.pi() * arb(f) / arb(FS)
        ctx.prec = bits
        n_mul, r2rad_mul, crad_mul = solve(x, basis_mul(w, N, bits), N, bits)
        n_ex, r2rad_ex, crad_ex = solve(x, basis_exact(f, FS, N, bits), N, bits)
        rows.append(dict(N=N, f=f, mul=n_mul, exact=n_ex, gain=n_ex - n_mul,
                         r2rad_mul=r2rad_mul, r2rad_ex=r2rad_ex, crad_mul=crad_mul, crad_ex=crad_ex))
        print("N=%5d f=%4d  w*i basis %8.2f dB | exact-phase basis %8.2f dB | gain %6.2f dB" %
              (N, f, n_mul, n_ex, n_ex - n_mul))
json.dump(rows, open("hpm/experiments/results_phasebasis.json", "w"), indent=1)
