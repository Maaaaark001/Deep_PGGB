"""Multitone: every third-order product, measured with a certificate.

Four tones at 1001 / 6997 / 13003 / 18997 Hz - deliberately not harmonics of each
other and not commensurate with 48 kHz - pass through a known cubic y = x + a3 x^3.

Two things are tested, and they are different:

1. **Identity.** A cubic is odd, so it generates only odd-order products.  The
   enumerator must put 2f_i - f_j, f_i + f_j - f_k and 3f_i on the right
   frequencies after aliasing.  An enumerator that is off by one index produces a
   table that still looks plausible.
2. **Level.** Every product has a closed-form amplitude, so every row has a
   predicted value to compare against.  Equal tone amplitudes would make many
   products coincide at one level and hide an error, so the amplitudes here are
   0.20 / 0.15 / 0.10 / 0.05.
"""
import cmath, json, math, sys
from itertools import product as _prod
sys.path.insert(0, '.')
from flint import arb, ctx
from hpm.arb import f128, measure, mcore

FS, N = 48000, 48000
FREQS = [1001, 6997, 13003, 18997]
AMPS = [0.20, 0.15, 0.10, 0.05]
A3S = [1e-3, 1e-5, 1e-7]


def predicted(a3, freqs, amps, order=3, phase=-math.pi / 2.0):
    """Exact third-order coefficient at each aliased frequency.

    x(t) = sum_k A_k cos(w_k t) = sum_k (A_k/2)(e^{j w_k t} + e^{-j w_k t}), so
    x^3 is a sum over *signed ordered* triples of a complex term

        C(f) = a3 * sum_{triples summing to f} prod (A_k / 2)   at frequency f.

    x^3 is real, so C(-f) = conj(C(f)) and the two spectral lines at +f and -f
    add in phase: the physical amplitude of the cosine at f > 0 is 2|C(f)|.

    Both facts are load-bearing and both are easy to lose.  Dropping the sign
    makes 2f1 - f2 unreachable (it needs f2 - 2f1 < 0) and the product reads
    -inf; dropping the factor 2 puts every product 6.02 dB low.  The textbook
    levels fall out: 2f1 - f2 gets three orderings and reads 3/4 a3 A1^2 A2,
    while 3f1 gets one and reads 1/4 a3 A1^3.
    """
    fs = float(FS)
    nyq = fs / 2
    K = len(freqs)
    acc = {}
    for trip in _prod(range(K), repeat=order):
        for signs in _prod((1, -1), repeat=order):
            f = sum(s * freqs[k] for s, k in zip(signs, trip))
            if f <= 0:
                continue                  # +f and -f are one physical line
            # the phasor matters: the tones are sines, and two aliases of the
            # same bin can cancel.  Summing magnitudes instead of complex
            # amplitudes reads 9.5 dB high on exactly those bins.
            c = complex(a3, 0.0)
            for s, k in zip(signs, trip):
                c *= (amps[k] / 2.0) * cmath.exp(1j * s * phase)
            g = f % fs
            if g > nyq:
                g = fs - g
                c = complex(c.real, -c.imag)   # folding conjugates the phasor
            key = round(g, 6)
            acc[key] = acc.get(key, 0j) + c
    return {k: 2.0 * abs(v) for k, v in acc.items()}


def build(path, a3):
    ctx.prec = 400
    acc = [arb(0)] * N
    for f, a in zip(FREQS, AMPS):
        t = mcore.tone(f, FS, N, repr(a), 400)
        acc = [p + q for p, q in zip(acc, t)]
    out = bytearray()
    for v in acc:
        out += f128.encode(v + arb(a3) * v * v * v)
    open(path, 'wb').write(bytes(out))


rows = []
for a3 in A3S:
    path = 'hpm/experiments/_multi_%g.f128' % a3
    build(path, a3)
    r = measure.multitone(path, FS, FREQS, bits=300, fmt='f128', order=3)
    pred = predicted(a3, FREQS, AMPS)
    amin = r['amp'][0]        # measure() reports dBc against the first tone
    lab = r['product_labels']
    rec = dict(a3=a3, null_db=r['null_cert_db'], ruler_db=r['ruler_db'], rows=[])
    print('a3=%.0e  null %7.2f dB  ruler %7.1f dB  %d products'
          % (a3, r['null_cert_db'], r['ruler_db'], len(r['products_db'])), flush=True)
    for k, v in r['products_db'].items():
        f = float(k)
        p = pred.get(round(f, 6), 0.0)
        pdb = 20 * math.log10(p / amin) if p > 0 else float('-inf')
        rec['rows'].append(dict(f=f, label=lab.get(k, ''), meas_db=v, pred_db=pdb))
    rec['rows'].sort(key=lambda t: -t['meas_db'])
    for t in rec['rows'][:8]:
        d = t['meas_db'] - t['pred_db']
        print('    %9.1f Hz  %-16s meas %8.2f   pred %8.2f   d %+6.2f'
              % (t['f'], t['label'], t['meas_db'], t['pred_db'], d), flush=True)
    rows.append(rec)

json.dump(rows, open('hpm/experiments/results_multitone.json', 'w'), indent=1)
print('wrote results_multitone.json')