import sys, time
sys.path.insert(0, ".")
from hpm.arb import measure, advisor
rows = []
for p in (40, 48, 56, 64, 72, 80, 96):
    t0 = time.time()
    try:
        r = measure.measure("hpm/experiments/_eng16.wav", 88200, [1000], bits=p,
                            fmt="wav", skip_s=0.8, tail_s=0.8)
        rows.append((p, r["null_cert_db"], time.time() - t0, ""))
        print("p=%3d  cert %9.2f  %.1f s" % (p, r["null_cert_db"], time.time() - t0), flush=True)
    except Exception as e:
        rows.append((p, None, time.time() - t0, str(e)[:60]))
        print("p=%3d  FAILED: %s" % (p, str(e)[:80]), flush=True)
print("predicted length bill at 1.4M: %.1f dB = %.0f bit" % (
    -advisor.budget(400, 1411200)["log2n_db"] - advisor.budget(400, 1411200)["log2n2_db"],
    (-advisor.budget(400, 1411200)["log2n_db"] - advisor.budget(400, 1411200)["log2n2_db"]) / 6.02))
