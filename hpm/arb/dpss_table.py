"""DPSS leakage bounds as data.

The table answers one question without any arithmetic: for a record of N samples,
which time-half-bandwidth NW keeps the window's own leakage below a target?  The
numbers are certified upper bounds (Rayleigh quotient of the Slepian kernel never
exceeds the top eigenvalue), so they are safe to quote.

Regenerate with `python hpm/experiments/run_dpss_table.py`; precision is raised
adaptively because 1 - lambda0 cancels digits (at 160 bit, NW >= 6 returns nan).
"""
from __future__ import annotations

import json
import os

_TABLE = None


def _load():
    global _TABLE
    if _TABLE is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "experiments", "results_dpss.json")
        with open(path) as fh:
            _TABLE = json.load(fh)
    return _TABLE


def table():
    return _load()


def nw_for(leak_db, N=None):
    """Smallest NW whose certified leakage bound is at or below `leak_db`.

    Returns (N, NW, leak_db) or None.  Interpolating N is deliberately not
    supported: lambda0 depends on N only through the boundary, and the table
    shows the dependence is below 0.05 dB over 128..1024.
    """
    rows = [r for r in _load() if r["leak_db"] is not None and r["leak_db"] <= leak_db]
    if N is not None:
        exact = [r for r in rows if r["N"] == N]
        if exact:
            rows = exact
    if not rows:
        return None
    r = min(rows, key=lambda r: r["NW"])
    return r["N"], r["NW"], r["leak_db"]


def report():
    rows = _load()
    ns = sorted({r["N"] for r in rows})
    nws = sorted({r["NW"] for r in rows})
    head = "N\\NW  " + "".join("%9.1f" % n for n in nws)
    print(head)
    for N in ns:
        cells = []
        for nw in nws:
            hit = [r for r in rows if r["N"] == N and r["NW"] == nw]
            cells.append("%9.1f" % hit[0]["leak_db"] if hit and hit[0]["leak_db"] is not None else "        -")
        print("%5d  " % N + "".join(cells))


if __name__ == "__main__":
    report()
