"""dp_smoke.py - Deep_PGGB smoke test. Every check prints PASS or FAIL."""
import os
import sys
import time
import numpy as np

import deeppggb as dp
from dp_test import run, make_signal, analytic, interior_null

FAILS = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + ("  " + detail if detail else ""))
    if not ok:
        FAILS.append(name)


def main():
    check("binary present", dp.available())

    # 1. quality at the reference ratio
    src, dst = 44100, 176400
    x, params = make_signal(src)
    y, log = run(x, src, dst)
    ref = analytic(params, len(y), dst)
    q = interior_null(y, ref)
    check("44.1->176.4 accuracy < -215 dB", q < -215, "%.1f dB" % q)
    check("output length exact", len(y) == int(round(len(x) * dst / src)))

    # 2. arbitrary ratios (PGGB cannot do these at all)
    for s, d in ((44100, 48000), (48000, 44100), (44100, 96000), (96000, 44100), (44100, 88200)):
        xx, pp = make_signal(s, secs=2.0)
        yy, _ = run(xx, s, d)
        rr = analytic(pp, len(yy), d)
        qq = interior_null(yy, rr)
        check("%d->%d accuracy < -210 dB" % (s, d), qq < -210, "%.1f dB" % qq)

    # 3. block independence: same result whether one block or many
    y1, _ = run(x, src, dst, block=0.5)
    y2, _ = run(x, src, dst, block=30.0)
    d = 20 * np.log10(np.sqrt(((y1 - y2) ** 2).mean()) / np.sqrt((y2 ** 2).mean()) + 1e-300)
    check("block size does not change output", d < -200, "%.1f dB difference" % d)

    # 4. precision modes agree
    yd, _ = run(x, src, dst, prec=0)
    yl, _ = run(x, src, dst, prec=1)
    d = 20 * np.log10(np.sqrt(((yd - yl) ** 2).mean()) / np.sqrt((yd ** 2).mean()) + 1e-300)
    check("double vs long double agree", d < -190, "%.1f dB difference" % d)

    # 5. minimum phase: no pre-ringing, same magnitude
    imp = np.zeros(src * 2)
    imp[src] = 0.5
    yl2, _ = run(imp, src, dst, phase=0)
    ym2, _ = run(imp, src, dst, phase=1)
    c = len(yl2) // 2
    pre_l = np.abs(yl2[c - 4000:c - 100]).max()
    pre_m = np.abs(ym2[c - 4000:c - 100]).max()
    check("min-phase removes pre-ringing", pre_m < pre_l * 1e-3,
          "%.1e vs %.1e" % (pre_m, pre_l))

    # 6. PCM quantisation lands at the expected depth
    # One LSB is 3.05e-5 (16-bit) and 1.19e-7 (24-bit); a correctly dithered
    # quantiser lands at roughly 0.3 LSB RMS.
    for bits, floor in ((16, 1.5e-5), (24, 6e-8)):
        qq, _ = run(x, src, dst, mode="pcm", bits=bits)
        nb = bits // 8
        a = qq.reshape(-1, nb).astype(np.int64)
        v = np.zeros(a.shape[0], dtype=np.int64)
        for b in range(nb):
            v |= a[:, b] << (8 * b)
        half = 1 << (bits - 1)
        v = np.where(v >= half, v - (1 << bits), v).astype(float) / half
        err = np.sqrt(((v - y) ** 2).mean())
        check("pcm%d error near floor" % bits, err < floor, "%.2e" % err)

    # 7. DSD stream is balanced and not stuck
    ds, _ = run(x, src, dst, mode="dsd", dsd=64)
    bits_arr = np.unpackbits(ds)
    ones = bits_arr.mean()
    check("dsd ones fraction near 0.5", 0.35 < ones < 0.65, "%.3f" % ones)
    flips = np.count_nonzero(np.diff(bits_arr))
    check("dsd toggles constantly", flips > bits_arr.size * 0.1,
          "%d flips of %d" % (flips, bits_arr.size))

    # 8. noise shaping pushes noise out of band
    f = np.fft.rfftfreq(len(y), 1 / dst)
    lo = (f >= 20) & (f <= 5000)
    # Noise shaping pushes error toward the OUTPUT Nyquist (88.2 kHz), so the
    # rise must be measured up there, not inside the audio band.
    hi = (f >= 60000) & (f <= 88000)
    def errs(ns):
        qq, _ = run(x, src, dst, mode="pcm", bits=16, ns=ns)
        a = qq.reshape(-1, 2).astype(np.int64)
        v = (a[:, 0] | (a[:, 1] << 8)).astype(np.int64)
        v = np.where(v >= 32768, v - 65536, v).astype(float) / 32768.0
        E = np.abs(np.fft.rfft(v - y)) ** 2
        return (10 * np.log10(E[lo].mean() + 1e-30), 10 * np.log10(E[hi].mean() + 1e-30))
    e0 = errs(0)
    e4 = errs(4)
    check("shaping lowers in-band noise", e4[0] < e0[0] - 20,
          "%.1f -> %.1f dB" % (e0[0], e4[0]))
    check("shaping raises out-of-band noise", e4[1] > e0[1] + 10,
          "%.1f -> %.1f dB" % (e0[1], e4[1]))

    # 9. determinism
    ya, _ = run(x, src, dst)
    yb, _ = run(x, src, dst)
    check("bit-identical across runs", np.array_equal(ya, yb))

    # 10. file round trip
    os.makedirs("work", exist_ok=True)
    st = np.stack([0.4 * np.sin(2 * np.pi * 440 * np.arange(src * 2) / src),
                   0.3 * np.sin(2 * np.pi * 3000 * np.arange(src * 2) / src)], 1)
    dp.encode(st, src, "work/smoke.flac", 24)
    rep = dp.convert("work/smoke.flac", "work/smoke_out.wav", 48000, bits=24)
    check("file conversion length", rep["out_frames"] == int(round(rep["in_frames"] * 48000 / src)),
          "%d -> %d" % (rep["in_frames"], rep["out_frames"]))

    print()
    print("%d checks, %d failed" % (16, len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())