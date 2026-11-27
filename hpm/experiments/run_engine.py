"""Step 4: binary128 Deep_PGGB as the device under test, Arb as the analyser.

dp_quad_probe.exe "dump" writes the engine's binary128 output; every binary128
value is a dyadic rational, so Arb holds it exactly and the certified least
squares null measures the engine, not the analyser.
"""
import sys, time, subprocess, json
sys.path.insert(0, ".")
from flint import arb, ctx, arb_mat
from hpm.arb import f128, mcore

FS_IN, FS_OUT, F, SECS = 44100, 88200, 1000, 16
BITS = 400
OUT = "hpm/experiments/engine_out.f128"


def dump():
    t0 = time.time()
    p = subprocess.run(["deeppggb/dp_quad_probe.exe", "dump", str(SECS), str(F),
                        str(FS_IN), str(FS_OUT), "16", OUT], capture_output=True, text=True)
    print(f"[4] probe dump rc={p.returncode} {time.time()-t0:.1f} s :: {p.stdout.strip()[:200]}",
          flush=True)
    if p.returncode:
        print(p.stderr[-400:], flush=True)


def chunks(path, chunk=8192):
    with open(path, "rb") as f:
        while True:
            blk = f.read(16 * chunk)
            if not blk:
                break
            yield [f128.to_arb(blk[i:i + 16]) for i in range(0, len(blk), 16)]


def measure(path, w, bits, skip_s=0.8, fs=FS_OUT):
    lo = int(skip_s * fs)
    import os
    hi_idx = os.path.getsize(path) // 16 - lo   # the block taper sits at both ends
    old = ctx.prec
    ctx.prec = bits
    t0 = time.time()
    G = [[arb(0), arb(0)], [arb(0), arb(0)]]
    b = [arb(0), arb(0)]
    idx = 0
    for blk in chunks(path):
        for xi in blk:
            if lo <= idx < hi_idx:
                t = w * idx
                c, s = t.cos(), t.sin()
                G[0][0] += c * c; G[0][1] += c * s; G[1][1] += s * s
                b[0] += c * xi; b[1] += s * xi
            idx += 1
    G[1][0] = G[0][1]
    a, bb = list(arb_mat(G).solve(arb_mat([[v] for v in b])))
    print(f"[4] pass1 {idx} samples in {time.time()-t0:.1f} s  a={float(a):.3e} b={float(bb):.6f}",
          flush=True)
    t0 = time.time()
    r2 = arb(0); x2 = arb(0)
    idx = 0
    for blk in chunks(path):
        for xi in blk:
            if lo <= idx < hi_idx:
                t = w * idx
                d = xi - (a * t.cos() + bb * t.sin())
                r2 += d * d
                x2 += xi * xi
            idx += 1
    ctx.prec = old
    print(f"[4] pass2 {time.time()-t0:.1f} s", flush=True)
    return dict(n=idx, null_db=mcore.null_upper_db(r2, x2),
                null_mid_db=mcore.null_mid_db(r2, x2),
                rms_residual=float((r2.mid() / idx).sqrt()) if r2.mid() > 0 else None,
                amp=float((a ** 2 + bb ** 2).sqrt()))


if __name__ == "__main__":
    t0 = time.time()
    dump()
    w = mcore.omega(F, FS_OUT, BITS + 60)
    res = measure(OUT, w, BITS)
    res["wall_s"] = time.time() - t0
    print(json.dumps(res, indent=1), flush=True)
    with open("hpm/experiments/results_engine.json", "w") as f:
        json.dump(res, f, indent=1)
