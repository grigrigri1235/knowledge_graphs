import json, sys
S = sys.argv[1]
m = json.load(open(f"{S}/metrics.json"))
r = json.load(open(f"{S}/recompute.json"))
print("recompute comparisons keys:", sorted(r["comparisons"]))
print("metrics secondary keys:", sorted(m.get("secondary") or {}), "reported keys:", sorted(m.get("reported") or {}))
SETS = ("all", "val", "train")
pairs = []
# arm success
for ts in SETS:
    for arm, v in r["arm_success"][ts].items():
        if arm == "n_tasks":
            continue
        pairs.append((f"arm_success.{arm}.{ts}", m["arm_success"][arm][ts]["rate"], v))
    pairs.append((f"n_tasks.main.{ts}", m["main_claim"][ts]["n_tasks"], r["arm_success"][ts]["n_tasks"]))
# comparisons
cmap = {}
for k, rec in r["comparisons"].items():
    arms = rec.get("arms", "")
    if k.startswith("main"):
        cmap[k] = m["main_claim"]
    elif k.startswith("S1"):
        cmap[k] = m["secondary"]["S1"]
    elif k.startswith("S2"):
        cmap[k] = m["secondary"]["S2"]
    elif "none" in arms or "none" in k:
        cmap[k] = m["reported"].get("tgr_tracker_v3_vs_none")
    else:
        print("UNMAPPED comparison", k, arms)
for k, mrec in cmap.items():
    for ts in SETS:
        rr = r["comparisons"][k].get(ts)
        if rr is None or mrec is None:
            print("missing", k, ts)
            continue
        pairs.append((f"{k}.{ts}.point", mrec[ts]["diff"], rr["point"]))
        pairs.append((f"{k}.{ts}.n_tasks", mrec[ts]["n_tasks"], rr["n_tasks"]))
        if "rate_a" in mrec[ts] and "rate_a" in rr:
            pairs.append((f"{k}.{ts}.rate_a", mrec[ts]["rate_a"], rr["rate_a"]))
bad = 0
maxd = 0.0
exact = 0
for name, a, b in pairs:
    d = abs(a - b)
    maxd = max(maxd, d)
    exact += a == b
    if d > 1e-12:
        bad += 1
        print("MISMATCH", name)
print(f"checked {len(pairs)} values; bit-identical {exact}; max abs diff {maxd:.3e}; over 1e-12: {bad}")
