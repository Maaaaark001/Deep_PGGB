"""Window as a weight vs window as a transform.

Two estimators on the same non-coherent data (1000.5 Hz in 8000 Hz, N = 4096):

  weighted LS   minimise sum_i w_i (x_i - model_i)^2 over the full (2K+1) normal
                equations, model = a cos + b sin + DC.  The window is a weight.
  single bin    A = 2 sum w x cos / sum w, B = 2 sum w x sin / sum w (one bin,
                rectangular normalisation), subtract that sinusoid, measure what
                is left.  The window is a transform; its sidelobes are the floor.

Both are swept over working precision.  If leakage were physics the weighted LS
would inherit it and neither would move with bits.

The single-bin path must use exact=False: 1000.5 Hz is not an integer, so the
integer-phase shortcut would truncate it to 1000 Hz and measure a different
stimulus.  The measured floor is compared with the closed form

    null_sb = -20 log10 | L(2 w0) |,   L = sum_n w[n] exp(-i 2 w0 n) / sum_n w[n]

which is the fraction of the tone that the window transform leaves in the
residual bin.  It is exact for a pure tone and does not move with precision.
"""
import json, sys
sys.path.insert(0, '.')
from flint import arb, ctx
from hpm.arb import measure, mcore

FS, F, N = 8000, 1000.5, 4096
BITS = [60, 90, 120, 180, 240, 360, 480]
WINS = ['rect', 'hann', 'hamming', 'blackman', 'blackmanharris', 'flattop', 'nuttall']


def single_bin_null(x, f, fs, win, bits):
    """Classical windowed single-bin projection, then the residual."""
    ctx.prec = bits
    unit = measure.unit_omega(fs)
    a = arb(0)
    b = arb(0)
    sw = arb(0)
    for i in range(N):
        wi = arb(1) if win is None else win[i]
        c, sn = measure.phasor(f, fs, i, False, unit)
        a += wi * arb(x[i]) * c
        b += wi * arb(x[i]) * sn
        sw += wi
    a = 2 * a / sw
    b = 2 * b / sw
    r2 = arb(0)
    x2 = arb(0)
    for i in range(N):
        wi = arb(1) if win is None else win[i]
        c, sn = measure.phasor(f, fs, i, False, unit)
        d = arb(x[i]) - (a * c + b * sn)
        r2 += wi * d * d
        x2 += wi * arb(x[i]) * arb(x[i])
    return mcore.null_upper_db(r2, x2)


def leak_closed_form(win, f, fs):
    """-20 log10 |L(2 w0)| with L the window transform at twice the tone frequency.

    L is the coefficient the single-bin normalisation assigns to the tone's own
    image, so |L| is the fraction of the tone left in the residual; the residual
    is then A^2 |L|^2 / 2 and the signal A^2 / 2, hence the floor.
    """
    ctx.prec = 1200
    unit = measure.unit_omega(fs)
    re = arb(0)
    im = arb(0)
    sw = arb(0)
    for i in range(N):
        wi = arb(1) if win is None else win[i]
        c, sn = measure.phasor(f, fs, i, False, unit)
        re += wi * (c * c - sn * sn)
        im += wi * (-2 * c * sn)
        sw += wi
    mag = ((re / sw) ** 2 + (im / sw) ** 2).sqrt()
    return float(-20 * mag.log() / arb(10).log())


rows = []
x = mcore.tone(F, FS, N, '0.5', 1200)
print('non-coherent %.1f Hz in %d Hz, N=%d' % (F, FS, N), flush=True)
for name in WINS:
    win = measure.make_window(name, N, 1200)
    for bits in BITS:
        cs = mcore.basis_exact(F, FS, N, bits)
        c, r2, x2, _ = mcore.ls_known(x, [mcore.omega(F, FS, bits)], win, bits, cs=[cs])
        wls = mcore.null_upper_db(r2, x2)
        sb = single_bin_null(x, F, FS, win, bits)
        leak = leak_closed_form(win, F, FS)
        rows.append(dict(window=name, bits=bits, wls_db=wls, single_bin_db=sb,
                         leak_closed_db=leak))
        print('%-15s p=%4d  weighted LS %9.2f   single bin %9.2f   closed form %9.2f'
              % (name, bits, wls, sb, leak), flush=True)

json.dump(rows, open('hpm/experiments/results_window.json', 'w'), indent=1)
print('wrote results_window.json')