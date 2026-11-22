# -*- coding: utf-8 -*-
"""Real spectral data for figure 2.

Two panels, both from the actual engine, no synthetic model:

  a) output spectrum of a 1 kHz, 0.5 FS tone, 44.1 -> 88.2 kHz, after the
     20 ms head/tail fades are trimmed.  The remaining span is an exact
     integer number of cycles, so a rectangular window has no leakage and
     the residual really is the engine's numerical floor.
  b) sensitivity calibration: a probe tone is added at -220 ... -310 dBc and
     the analyser reads it back.  This is the evidence that the -300 dBc
     readings in the paper are resolved, not extrapolated.

Output: work/spectrum_data.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
import importlib.util as _ilu  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = _ilu.spec_from_file_location("dpmod", os.path.join(HERE, "deeppggb.py"))
_dp = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_dp)
dp = _dp

OUT = os.path.join(os.path.dirname(HERE), "work", "spectrum_data.json")
SRC, DST = 44100, 88200
SECS = 4.0
TRIM_MS = 100.0
F0 = 1000.0


def phase_tone(freq, n, rate):
    """Integer-phase tone: (f*n) mod rate keeps the phase exact."""
    idx = (np.arange(n, dtype=np.int64) * int(round(freq))) % int(rate)
    return np.sin(2.0 * np.pi * idx / rate)


def analyse(y, rate, f0):
    """Trim fade zones, take a rectangular-window FFT, return dBc array."""
    a = int(rate * TRIM_MS / 1000.0)
    y = np.asarray(y[: y.shape[0] - a], dtype=np.float64)
    y = y[a:]
    n = y.shape[0]
    spec = np.abs(np.fft.rfft(y))
    freq = np.fft.rfftfreq(n, 1.0 / rate)
    k = int(round(f0 * n / rate))
    carrier = spec[k]
    dbc = 20.0 * np.log10(spec / carrier + 1e-300)
    return freq, dbc, carrier, k, n


def peak_hold(freq, dbc, buckets=2600):
    """Max-hold per horizontal bucket: a display, not a decimation."""
    edges = np.linspace(0, freq[-1], buckets + 1)
    idx = np.clip(np.searchsorted(edges, freq) - 1, 0, buckets - 1)
    out_f = np.zeros(buckets)
    out_d = np.full(buckets, -400.0)
    for b in range(buckets):
        sel = idx == b
        if not np.any(sel):
            continue
        j = np.argmax(dbc[sel])
        out_f[b] = freq[sel][j]
        out_d[b] = dbc[sel][j]
    keep = out_d > -399.0
    return out_f[keep], out_d[keep]


def main():
    n = int(SRC * SECS)
    x = 0.5 * phase_tone(F0, n, SRC)
    y = dp.resample(x, SRC, DST, block=0.0)[:, 0]
    freq, dbc, carrier, k, nn = analyse(y, DST, F0)
    floor_band = np.ones_like(dbc, dtype=bool)
    floor_band[max(0, k - 2): k + 3] = False
    floor_band[0] = False
    floor = 20.0 * np.log10(np.sqrt(np.sum(10.0 ** (dbc[floor_band] / 10.0))) + 1e-300)
    pf, pd = peak_hold(freq, dbc)
    # strongest discrete lines outside the carrier
    cand = np.where(floor_band & (dbc > floor + 3.0))[0]
    cand = cand[np.argsort(dbc[cand])[::-1][:8]]
    spurs = [{"freq_hz": float(freq[i]), "db": float(dbc[i])} for i in cand]

    # sensitivity sweep
    sens = []
    for level in (-220, -230, -240, -250, -260, -270, -280, -290, -300, -310):
        amp = 0.5 * 10.0 ** (level / 20.0)
        xs = 0.5 * phase_tone(F0, n, SRC) + amp * phase_tone(3000.0, n, SRC)
        ys = dp.resample(xs, SRC, DST, block=0.0)[:, 0]
        fs, ds, c, kk, _ = analyse(ys, DST, F0)
        k3 = int(round(3000.0 * nn / DST))
        sens.append({"injected_dbc": level,
                     "measured_dbc": round(float(ds[k3]), 1)})

    out = {
        "src": SRC, "dst": DST, "secs": SECS, "trim_ms": TRIM_MS,
        "carrier_hz": F0, "gain_interior": round(float(carrier / (0.5 * nn / 2)), 6),
        "floor_db": round(float(floor), 1),
        "freq_khz": [float(v / 1000.0) for v in pf],
        "mag_db": [round(float(v), 1) for v in pd],
        "spurs": spurs,
        "sensitivity": sens,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("floor %.1f dBc, gain %.6f, points %d" % (floor, out["gain_interior"], len(pf)))
    print("spurs", spurs[:4])
    print("sensitivity", sens)


if __name__ == "__main__":
    main()
