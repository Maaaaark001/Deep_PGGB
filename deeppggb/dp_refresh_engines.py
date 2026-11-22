# -*- coding: utf-8 -*-
"""把 work/bench_repeat.json（16 s 激励 + 5 窗中位数，3 遍一致）写回 paper_data.json 的
engines 段，并把 60 s 立体声的速度写进 pggb 段，供 dp_figures 使用。"""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pd_path = os.path.join(ROOT, "work", "paper_data.json")
br_path = os.path.join(ROOT, "work", "bench_repeat.json")
data = json.load(open(pd_path, encoding="utf-8"))
br = json.load(open(br_path, encoding="utf-8"))
LABEL = {"dpggb": "Deep_PGGB", "pggb": "PGGB", "r8b": "r8brain-free", "soxng": "sox_ng rate",
         "swr": "FFmpeg aresample", "soxr": "libsoxr", "ssrc": "SSRC / Shibatch",
         "scipy": "SciPy resample_poly"}
rows = []
for k, lab in LABEL.items():
    c = br[k]
    def med(f):
        d = c.get(f)
        return None if not d else round(d["med"], 1)
    rows.append({
        "engine": k, "label": lab,
        "spur_dbc": med("spur_dbc"), "image_dbc": med("image_dbc"),
        "alias_dbc": None if c.get("alias_na") else med("alias_dbc"),
        "alias_na": bool(c.get("alias_na")),
        "imd_dbc": med("imd_dbc"), "imd_smpte_dbc": med("imd_smpte_dbc"),
        "mt_dbc": med("mt_dbc"),
        "speed_x": c.get("speed"),
    })
data["engines"] = rows
data["pggb"]["speed_x_60s_stereo"] = br["pggb"]["speed"]
data["pggb"]["dpggb_speed_x_60s_stereo"] = br["dpggb"]["speed"]
data["pggb"]["r8b_speed_x_60s_stereo"] = br["r8b"]["speed"]
data["protocol"] = {"excitation_s": 16.0, "windows": 5, "aggregate": "median",
                    "upsampling": "44.1->88.2", "alias": "96->44.1 two-tone",
                    "speed": "60 s stereo 44.1->176.4, best of 2"}
with open(pd_path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=1)
print("engines refreshed:", len(rows))
for r in rows:
    print("%-8s %7s %7s %7s %7s %7s %7s %6s" % (r["engine"], r["spur_dbc"], r["image_dbc"],
          r["alias_dbc"], r["imd_dbc"], r["imd_smpte_dbc"], r["mt_dbc"], r["speed_x"]))
