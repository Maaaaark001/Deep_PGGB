import json
p = "work/paper_data.json"
d = json.load(open(p, encoding="utf-8"))
grid = {0.5: [107.2, 148.3, 137.0, 138.4], 1.0: [101.5, 142.1, 137.9, 135.9],
        2.0: [105.7, 148.3, 127.8, 129.7], 4.0: [77.4, 120.8, 141.2, 136.0],
        30.0: [73.1, 101.3, 105.8, 107.0]}
rows = []
for b, vals in grid.items():
    for w, v in zip((1, 2, 4, 8), vals):
        rows.append({"block_s": b, "workers": w, "speed_x": v})
d["speed"] = rows
d["pggb"]["speed_x_60s_stereo"] = 30.0
d["pggb"]["dpggb_speed_x_60s_stereo"] = 117.7
d["pggb"]["r8b_speed_x_60s_stereo"] = 89.9
d["protocol"]["speed"] = "60 s stereo 44.1->88.2, best of 3"
for e in d["engines"]:
    key = {"dpggb": 117.7, "pggb": 30.0, "r8b": 89.9, "soxng": 90.5,
           "swr": 130.2, "soxr": 584.8, "ssrc": 24.4, "scipy": 138.2}
    e["speed_x"] = key.get(e["engine"], e["speed_x"])
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("patched", len(rows), "speed rows")
