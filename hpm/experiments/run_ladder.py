import sys, json
sys.path.insert(0, ".")
from hpm.arb import measure

FS = 88200
rows = []
for name, fmt in (("_eng16.f128", "f128"), ("_eng16.f64", "f64"),
                  ("_eng16.wav", "wav"), ("_eng16_pcm24.wav", "wav"),
                  ("_eng16_pcm16.wav", "wav")):
    r = measure.measure("hpm/experiments/" + name, FS, [1000], bits=120, fmt=fmt,
                        skip_s=0.8, tail_s=0.8)
    rows.append(dict(name=name, fmt=fmt, cert=r["null_cert_db"], mid=r["null_mid_db"],
                     rms=r["rms_residual"], dc=r["dc"], amp=r["amp"][0]))
    print("%-20s %-5s null>=%9.3f  rms %.3e  dc %+.3e  amp %.12f" %
          (name, fmt, r["null_cert_db"], r["rms_residual"], r["dc"], r["amp"][0]), flush=True)
json.dump(rows, open("hpm/experiments/results_ladder.json", "w"), indent=1)
