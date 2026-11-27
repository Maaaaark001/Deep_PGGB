"""certify -- command-line certified audio measurement.

    certify null  out.f128 --fs 88200 --f 1000 [--skip 0.8 --tail 0.8]
    certify imd   out.f128 --fs 44100 --f1 19000 --f2 20000 [--bits 400]
    certify tone  out.wav  --fs 44100 --f 1000        (wav/flac via soundfile)
    certify predict --db 440 --N 1411200 --f 1000     (precision advisor)

Every measurement prints an *enclosure*, never a point estimate:
    null >= 440.211 dB   (certified)
and, next to it, the ruler's own floor:
    ruler  = min(coefficient 1350 dB, frequency 1366 dB)
If the reading is within ~20 dB of the ruler, the tool says so and refuses to
present the number as a property of the file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hpm.arb import advisor, measure


def _fmt(x, nd=3):
    return "inf" if x == float("inf") else f"{x:.{nd}f}"


def cmd_null(a):
    if a.auto:
        print(f"file      {a.file}  (auto sweep from {a.bits} bit, step 6)")
        r, hist = measure.measure_auto(a.file, a.fs, [a.f], fmt=a.fmt,
                                       bits_start=a.bits, skip_s=a.skip,
                                       tail_s=a.tail, products=a.product or (),
                                       fit_dc=a.dc, window=a.window)
        r["sweep"] = hist
    else:
        r = measure.measure(a.file, a.fs, [a.f], bits=a.bits, fmt=a.fmt,
                            skip_s=a.skip, tail_s=a.tail, products=a.product or (),
                            fit_dc=a.dc, window=a.window)
    print(f"file      {a.file}  ({r['fmt']}, {r['N']} samples analysed, {r['bits']} bit)")
    print(f"tone      {a.f} Hz, amplitude {r['amp'][0]:.12f}")
    print(f"null      >= {_fmt(r['null_cert_db'], 3)} dB   (certified; midpoint {_fmt(r['null_mid_db'], 3)})")
    print(f"residual  rms {r['rms_residual']:.3e}"
          + (f"   (DC {r['dc']:+.3e} fitted)" if r["fit_dc"] else "   (DC left in the residual)"))
    print(f"ruler     min(coefficient {_fmt(r['ruler_coef_db'], 1)}, "
          f"frequency {_fmt(r['ruler_freq_db'], 1)}) = {_fmt(r['ruler_db'], 1)} dB")
    regime = ("ruler-limited (raise --bits)" if r["null_cert_db"] > r["ruler_db"] - 20
              else "file-limited (the number is a property of the data)")
    print(f"regime    {regime}; certificate is {_fmt(r['ruler_db'] - r['null_cert_db'], 1)} dB below the ruler")
    for k, v in r["products_db"].items():
        print(f"product   {k:>12s}  {v:9.2f} dBc")
    if a.json:
        print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_imd(a):
    products = [2 * a.f1 - a.f2, 2 * a.f2 - a.f1, a.f2 - a.f1,
                (3 * a.f1) % a.fs, (2 * a.f1 + a.f2) % a.fs,
                (2 * a.f2 + a.f1) % a.fs, (3 * a.f2) % a.fs]
    r = measure.measure(a.file, a.fs, [a.f1, a.f2], bits=a.bits, fmt=a.fmt,
                        skip_s=a.skip, tail_s=a.tail, products=products,
                        fit_dc=a.dc, window=a.window)
    print(f"file      {a.file}  ({r['N']} samples, {r['bits']} bit)")
    print(f"tones     {a.f1} Hz @ {r['amp'][0]:.9f}, {a.f2} Hz @ {r['amp'][1]:.9f}")
    print(f"null      >= {_fmt(r['null_cert_db'], 3)} dB   (certified)")
    print(f"ruler     {_fmt(r['ruler_db'], 1)} dB")
    for k, v in r["products_db"].items():
        print(f"  {float(k):>9.1f} Hz  {v:10.2f} dBc")
    if a.json:
        print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_multi(a):
    r = measure.multitone(a.file, a.fs, a.f, bits=a.bits, fmt=a.fmt,
                          skip_s=a.skip, tail_s=a.tail, order=a.order,
                          fit_dc=a.dc, window=a.window)
    print(f"file      {a.file}  ({r['N']} samples, {r['bits']} bit, order {r['order']})")
    print("tones     " + ", ".join(f"{f} Hz @ {v:.9f}" for f, v in zip(a.f, r['amp'])))
    print(f"null      >= {_fmt(r['null_cert_db'], 3)} dB   (certified)")
    print(f"ruler     {_fmt(r['ruler_db'], 1)} dB")
    rows = [(float(k), r['product_labels'].get(k, ''), v)
            for k, v in r['products_db'].items()]
    rows.sort(key=lambda t: -t[2])         # loudest first: that is the worst
    worst = rows[0][2] if rows else 0.0
    shown = [t for t in rows if t[2] >= worst - a.top_db]
    for f, lab, v in shown:
        print(f"  {f:>9.1f} Hz  {lab:<12s} {v:10.2f} dBc")
    print(f"products  {len(rows)} enumerated, {len(shown)} within {a.top_db:.0f} dB of the loudest")
    if a.json:
        print(json.dumps(r, indent=1, default=str))
    return 0


def cmd_predict(a):
    adv = advisor.advise(a.db, a.bits, int(a.N), a.f, K=a.k)
    print(f"target    {adv['target_db']:.1f} dB on N={adv['N']} at {adv['f']:.0f} Hz, K={adv['K']}")
    print(f"bits      {adv['bits']}")
    print(f"wall      ~{adv['wall_s']:.1f} s")
    print(f"ceiling   {adv['ceiling_gap_db']:+.1f} dB vs the 6.02 dB/bit ideal")
    print(f"ruler     {adv['ruler_db']:.1f} dB (certificate must stay 20 dB below it)")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="certify", description="certified audio measurement")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, tone=True):
        sp.add_argument("file", nargs="?" if not tone else None)
        sp.add_argument("--fs", type=float, required=True, help="sample rate of the file")
        sp.add_argument("--bits", type=int, default=400, help="working precision (default 400)")
        sp.add_argument("--fmt", default=None, choices=["f128", "f64", "wav"],
                        help="sample format (default: infer from the extension)")
        sp.add_argument("--skip", type=float, default=0.0, help="seconds to skip at the start")
        sp.add_argument("--tail", type=float, default=0.0, help="seconds to skip at the end")
        sp.add_argument("--json", action="store_true")
        sp.add_argument("--window", default=None,
                        help="weighting window: " + ", ".join(measure.WINDOWS))

    n = sub.add_parser("null", help="certified null of a single tone")
    common(n)
    n.add_argument("--f", type=float, required=True)
    n.add_argument("--product", type=float, nargs="*", help="extra frequencies to read as dBc")
    n.add_argument("--auto", action="store_true",
                   help="sweep the precision upward until the certificate saturates")
    n.add_argument("--no-dc", dest="dc", action="store_false",
                   help="leave the constant term in the residual instead of fitting it")
    n.set_defaults(func=cmd_null)

    i = sub.add_parser("imd", help="certified two-tone IMD")
    common(i)
    i.add_argument("--f1", type=float, required=True)
    i.add_argument("--f2", type=float, required=True)
    i.add_argument("--no-dc", dest="dc", action="store_false",
                   help="leave the constant term in the residual instead of fitting it")
    i.set_defaults(func=cmd_imd)

    m = sub.add_parser("multitone", help="certified multitone: every product up to order")
    common(m)
    m.add_argument("--f", type=float, nargs="+", required=True, help="tone frequencies")
    m.add_argument("--order", type=int, default=3)
    m.add_argument("--top-db", type=float, default=40.0,
                   help="show products within this many dB of the worst one")
    m.add_argument("--no-dc", dest="dc", action="store_false")
    m.set_defaults(func=cmd_multi)

    q = sub.add_parser("predict", help="precision advisor")
    q.add_argument("--db", type=float, default=None)
    q.add_argument("--bits", type=int, default=None)
    q.add_argument("--N", type=float, default=1_411_200)
    q.add_argument("--f", type=float, default=1000.0)
    q.add_argument("-k", type=int, default=1)
    q.set_defaults(func=cmd_predict)

    a = p.parse_args(argv)
    if getattr(a, "fmt", "x") is None:
        ext = os.path.splitext(a.file)[1].lower().lstrip(".")
        a.fmt = {"f128": "f128", "f64": "f64", "wav": "wav", "flac": "wav"}.get(ext, "f128")
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
