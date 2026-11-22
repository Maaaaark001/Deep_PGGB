"""dp_app_check.py - confirm Deep_PGGB is wired into the toolbox UI."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srctool import engines

spec = engines.ENGINES.get("dpggb")
assert spec is not None, "engine not registered"
print("label       :", spec.label)
print("tagline     :", spec.tagline)
print("available   :", spec.available)
print("fidelity    :", spec.fidelity)
print("bandwidth   :", spec.bandwidth)
print("params      :", len(spec.params))
for p in spec.params:
    print("  %-8s %-6s default=%s" % (p.key, p.kind, p.default))

d = spec.to_dict()
assert len(d["params"]) == len(spec.params)
print("serialises  : ok")

# every registered engine must still resolve defaults
for k in engines.ENGINES:
    o = engines.default_opts(k)
    assert o, k
print("default_opts: ok for", len(engines.ENGINES), "engines")
