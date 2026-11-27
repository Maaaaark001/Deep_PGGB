"""Regenerate the measurement fixtures the tooling report runs on.

    python hpm/experiments/make_fixtures.py [--out DIR] [--check]

Fixtures (all under hpm/experiments/ by default):

    _eng16.f128       16 s, 1 kHz, 0.5 FS through the binary128 engine
    _eng16.f64        the same samples rounded to float64
    _eng16.wav        the same samples as float32 WAV
    _eng16_pcm24.wav  the same samples as PCM24
    _eng16_pcm16.wav  the same samples as PCM16
    _syn24.wav        1 kHz sine synthesised directly into PCM24 (no engine)
    _imd.f128         19k+20k two-tone through a known cubic, a3 = 1e-9

The first one needs deeppggb/dp_quad_probe.exe (bash deeppggb/build_quad.sh).
Everything else is derived from it, so the whole ladder moves together.
"""
import argparse, hashlib, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import soundfile as sf

from hpm.arb import f128, mcore

FS_ENG = 88200
FS_IMD = 44100


def _hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def engine_dump(out, secs=16, f=1000, fs_in=44100, fs_out=88200, block=16):
    """binary128 output of the quad engine: 16 bytes per sample, native LE."""
    exe = os.path.join('deeppggb', 'dp_quad_probe.exe')
    if not os.path.exists(exe):
        raise SystemExit('missing %s; run: bash deeppggb/build_quad.sh' % exe)
    path = os.path.join(out, '_eng16.f128')
    subprocess.run([exe, 'dump', str(secs), str(f), str(fs_in), str(fs_out),
                    str(block), path], check=True)
    return path


def f128_to_float64(path):
    """Decode binary128 exactly, then round once to float64."""
    from flint import ctx
    raw = open(path, 'rb').read()
    old = ctx.prec
    ctx.prec = 200
    try:
        vals = [f128.value_of(raw[i:i + 16]) for i in range(0, len(raw), 16)]
    finally:
        ctx.prec = old
    return np.array([float(v) for v in vals], dtype=np.float64)


def build(out):
    os.makedirs(out, exist_ok=True)
    p128 = engine_dump(out)
    a = f128_to_float64(p128)

    a.tofile(os.path.join(out, '_eng16.f64'))
    sf.write(os.path.join(out, '_eng16.wav'), a, FS_ENG, subtype='FLOAT')
    sf.write(os.path.join(out, '_eng16_pcm24.wav'), a, FS_ENG, subtype='PCM_24')
    sf.write(os.path.join(out, '_eng16_pcm16.wav'), a, FS_ENG, subtype='PCM_16')

    n = 1270080
    i = np.arange(n)
    x = 0.5 * np.sin(2 * np.pi * ((1000 * i) % FS_ENG) / FS_ENG)
    sf.write(os.path.join(out, '_syn24.wav'), x, FS_ENG, subtype='PCM_24')

    from flint import arb, ctx
    ctx.prec = 400
    n = 22050
    x1 = mcore.tone(19000, FS_IMD, n, '0.25', 400)
    x2 = mcore.tone(20000, FS_IMD, n, '0.25', 400)
    buf = bytearray()
    for i in range(n):
        v = x1[i] + x2[i]
        # arb(float) is exact, so this is the binary64 value of 1e-9; arb('1e-9')
        # would be the decimal at working precision and shift every mantissa.
        buf += f128.encode(v + arb(1e-9) * v * v * v)
    open(os.path.join(out, '_imd.f128'), 'wb').write(bytes(buf))
    return out


NAMES = ['_eng16.f128', '_eng16.f64', '_eng16.wav', '_eng16_pcm24.wav',
         '_eng16_pcm16.wav', '_syn24.wav', '_imd.f128']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join('hpm', 'experiments'))
    ap.add_argument('--check', action='store_true',
                    help='regenerate into a temp dir and compare sha256 with --out')
    a = ap.parse_args()
    if a.check:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            build(td)
            bad = 0
            for n in NAMES:
                p1, p2 = os.path.join(a.out, n), os.path.join(td, n)
                if n.endswith('.wav'):
                    # libsndfile stamps a PEak chunk with the write time, so
                    # the bytes differ while the audio is identical.
                    x, _ = sf.read(p1, dtype='float64')
                    y, _ = sf.read(p2, dtype='float64')
                    same = x.shape == y.shape and np.array_equal(x, y)
                    h1 = 'audio identical' if same else 'audio DIFFERS'
                else:
                    same = _hash(p1) == _hash(p2)
                    h1 = _hash(p1)[:16]
                ok = 'ok  ' if same else 'DIFF'
                if not same:
                    bad += 1
                print('%s %-18s %s' % (ok, n, h1))
            return 1 if bad else 0
    build(a.out)
    for n in NAMES:
        p = os.path.join(a.out, n)
        print('%-18s %10d bytes  %s' % (n, os.path.getsize(p), _hash(p)[:16]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())