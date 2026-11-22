# -*- coding: utf-8 -*-
"""Dense passband edge sweep for figure 4.

Non-uniform grid: coarse through the flat region, 7 Hz near Nyquist, so the
brick wall and the gentle FIR roll-offs are both resolved.  Gain is read from
a 1 s centre window of a 4 s integer-phase tone, relative to the 0.5 FS input.

Output: work/passband_dense.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from srctool import engines as E  # noqa: E402
from srctool.quality import _gain_at  # noqa: E402

UP_SRC, UP_DST = 44100, 88200
DN_SRC, DN_DST = 96000, 44100
ORDER = ["dpggb", "pggb", "r8b", "soxng", "swr", "soxr", "ssrc", "scipy"]

FREQS = []
FREQS += [19500, 20000, 20500, 21000, 21500]
FREQS += list(range(21600, 21901, 100))
FREQS += [21925, 21950, 21975, 22000]
FREQS += list(range(22007, 22050, 7))

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "work", "passband_dense.json")


def main():
    res = {"freqs": FREQS, "up": {}, "down": {}, "up_src": UP_SRC, "up_dst": UP_DST,
           "down_src": DN_SRC, "down_dst": DN_DST}
    for eng in ORDER:
        if not E.ENGINES[eng].available:
            res["up"][eng] = None
            res["down"][eng] = None
            continue
        row = []
        for f in FREQS:
            row.append(round(_gain_at(eng, E.default_opts(eng), UP_SRC, UP_DST, f), 2))
        res["up"][eng] = row
        print("up", eng, row[-6:], flush=True)
    for eng in ORDER:
        if eng == "pggb" or not E.ENGINES[eng].available:
            res["down"][eng] = None
            continue
        row = []
        for f in FREQS:
            row.append(round(_gain_at(eng, E.default_opts(eng), DN_SRC, DN_DST, f), 2))
        res["down"][eng] = row
        print("down", eng, row[-6:], flush=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
