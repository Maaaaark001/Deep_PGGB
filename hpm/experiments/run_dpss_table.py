"""DPSS leakage-bound table: lambda0 and the certified leakage bound vs (N, NW).

The table replaces rule-of-thumb window choice: for a given record length and a
given tolerable leakage, it says which NW to use, and the bound is rigorous
(Rayleigh quotient of the Slepian kernel <= top eigenvalue).

Precision is raised adaptively: 1 - lambda0 cancels digits, so a fixed 160 bit
reads nan for NW >= 6.
"""
import sys, json, time
sys.path.insert(0, ".")
from flint import arb, ctx
from hpm.arb import dpss as D

rows = []
for N in (128, 256, 512, 1024):
    for NW in (2.0, 2.5, 3.0, 3.5, 4.0, 6.0, 8.0):
        if NW > N / 4:
            continue
        t0 = time.time()
        try:
            lam0, rest, used = D.concentration(N, NW / N)
            leak = float(10 * (rest.abs_upper().log() / arb(10).log()))
            lam_mid = float(lam0.mid())
        except ArithmeticError as e:
            lam_mid, leak, used = None, None, None
        rows.append(dict(N=N, NW=NW, lambda0=lam_mid, leak_db=leak, bits=used,
                         wall_s=time.time() - t0))
        print("N=%5d NW=%4.1f lambda0=%.15f leak<=%8.2f dB  (%d bit, %.1f s)" %
              (N, NW, lam_mid, leak, used or 0, rows[-1]["wall_s"]), flush=True)
json.dump(rows, open("hpm/experiments/results_dpss.json", "w"), indent=1)
print("wrote results_dpss.json")
