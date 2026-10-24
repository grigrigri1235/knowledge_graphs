import collections, json, sys
BASE = "/home/azureuser/code_projects/predicate_correctness"
D = json.load(open(BASE + "/output/logs/v3_tqa_data.json"))
G = ["B2-val", "B2-train", "B3"]
K = [f"K{i}" for i in range(1, 17)]

print("## arms of answers", collections.Counter(tuple(a["arms"]) for a in D["answers"]))
# answers split, v3 arm only (record matched to a v3 conversation)
split = collections.defaultdict(collections.Counter)
for a in D["answers"]:
    if "tgr_tracker_v3" not in a["arms"]:
        continue
    gs = {D["conv_info"][f"{a['run']}|{c}"]["group"] for c in a["v3_convs"]}
    st = a["status"] if a["status"] in ("yes", "no") else ("unclear" if a["status"] == "unclear" else f"bad:{a['status']}")
    split[a["qid"]][st] += 1
    split[a["qid"]]["n"] += 1
asks = collections.Counter()
for g in G:
    asks.update(D["asks"].get(g, {}))
print("\n## per question: asks (all checks, B2+B3) | unique v3 answers split")
for k in K:
    print(k, "asks", asks[k], {g: D["asks"].get(g, {}).get(k, 0) for g in G}, dict(split[k]))

# blocks
def qtags(b):
    tags = set()
    for c in b["causes"]:
        t = c.get("tag") or ""
        for piece in t.split("+"):
            if piece.startswith("K"):
                tags.add(piece.split()[0])
    return tags

def codecause(b):
    return [c for c in b["causes"] if c.get("tag") in ("code", "rule_not_tabled") or str(c.get("tag", "")).startswith("blocking_value") or str(c.get("tag","")).startswith("code-part") or c.get("tag") == "lazy_skip"]

print("\n## block tags")
print(collections.Counter(tuple(sorted(c.get("tag") for c in b["causes"])) for b in D["blocks"]).most_common(60))
per = collections.defaultdict(lambda: collections.Counter())
convs_k = collections.defaultdict(set)
for b in D["blocks"]:
    ks = qtags(b)
    other = codecause(b)
    for k in ks:
        per[k][b["group"] + " blocks"] += 1
        per[k]["all blocks"] += 1
        if len(ks) == 1 and not other:
            per[k]["alone"] += 1
        convs_k[k].add((b["run"], b["conv"]))
    if not ks:
        per["(no K)"]["all blocks"] += 1
        per["(no K)"][b["group"] + " blocks"] += 1
print("\n## per K blocks")
for k in K + ["(no K)"]:
    if per[k]:
        cs = convs_k[k]
        fail = [c for c in cs if D["conv_info"][f"{c[0]}|{c[1]}"]["reward"] == 0]
        print(k, dict(per[k]), "convs", len(cs), "failed", len(fail))
# answer status per K per block (no vs unclear)
st = collections.defaultdict(collections.Counter)
for b in D["blocks"]:
    for c in b["causes"]:
        for piece in str(c.get("tag")).split("+"):
            if piece.startswith("K"):
                st[piece.split()[0]][piece.split()[1]] += 1
print("\n## per K cause answer kind", {k: dict(v) for k, v in st.items()})
print("\n## blocks by group", collections.Counter(b["group"] for b in D["blocks"]))
print("## non-K block tags", collections.Counter(c.get("tag") for b in D["blocks"] for c in b["causes"] if not str(c.get("tag")).startswith("K")))
print("## rule x tag", collections.Counter((b["dom"], c["rule"], c.get("tag")) for b in D["blocks"] for c in b["causes"]).most_common(40))

# lost candidates: v3 failed, frozen same conv passed
print("\n## lost candidates (v3 0, frozen same try 1)")
lost = collections.defaultdict(list)
for ck, ci in D["conv_info"].items():
    if ci["reward"] == 0 and ci["frozen_reward"] == 1:
        run, cid = ck.split("|")
        bl = [b for b in D["blocks"] if b["run"] == run and b["conv"] == cid]
        ks = collections.Counter()
        never = []
        for b in bl:
            for k in qtags(b):
                ks[k] += 1
            if not b["ran_later"]:
                never.append((b["step"], b["action"], sorted(qtags(b)), b["is_gold"]))
        lost[ci["group"]].append(cid)
        print(ci["group"], cid, "blocks", len(bl), dict(ks), "never-ran:", never, "transferred", ci["transferred"], "steps", ci["n_steps"], "fz task", round(ci["frozen_task_mean"], 2))
print({g: len(v) for g, v in lost.items()})
# also: v3 failed while frozen task mean >= 2/3 but frozen same try failed
print("\n## v3 0, frozen same try 0 but frozen task mean>=0.67, with K blocks")
for ck, ci in D["conv_info"].items():
    if ci["reward"] == 0 and ci["frozen_reward"] == 0 and (ci["frozen_task_mean"] or 0) >= 0.66:
        run, cid = ck.split("|")
        bl = [b for b in D["blocks"] if b["run"] == run and b["conv"] == cid]
        print(ci["group"], cid, [(b["step"], b["action"], sorted(qtags(b)), b["ran_later"], b["is_gold"]) for b in bl])
