import json, sys
sys.path.insert(0, ".")
from hpm.arb import measure
rows = []
for p in (92, 96, 100, 104, 110, 120, 140, 160, 200, 240, 320, 400):
    r = measure.measure("hpm/experiments/_eng16.f128", 88200, [1000], bits=p,
                        fmt="f128", skip_s=0.8, tail_s=0.8)
    rows.append(dict(bits=p, cert=r["null_cert_db"], mid=r["null_mid_db"], ruler=r["ruler_db"]))
    print("p=%3d cert=%9.3f mid=%9.3f ruler=%8.1f" % (p, r["null_cert_db"], r["null_mid_db"], r["ruler_db"]), flush=True)
json.dump(rows, open("hpm/experiments/results_saturation.json", "w"), indent=1)
