"""Dump sampled blocked cases per question for reading. Usage: tqa_dump.py K2 40 [seed]"""
import collections, glob, json, random, re, sys, unicodedata
BASE = "/home/azureuser/code_projects/predicate_correctness"
RUNS = {"B2": BASE + "/output/eval_v3/B2/B2_20261023T155537Z_c842d895",
        "B3": BASE + "/output/eval_v3/B3/B3_20261023T190740Z_9bf882c0"}
Q, N = sys.argv[1], int(sys.argv[2])
SEED = int(sys.argv[3]) if len(sys.argv) > 3 else 7
ONLY = sys.argv[4].split(",") if len(sys.argv) > 4 else None   # explicit "run|conv" list


def key(t):
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "", t)


D = json.load(open(BASE + "/output/logs/v3_tqa_data.json"))
recs = {}
for run, R in RUNS.items():
    for p in glob.glob(f"{R}/questions/answers_shard*of4.jsonl"):
        for line in open(p):
            if line.strip():
                r = json.loads(line)
                recs[r["key"]] = r
eps = {}
for run, R in RUNS.items():
    for p in glob.glob(f"{R}/tgr_tracker_v3/episodes_shard*of4.jsonl"):
        for line in open(p):
            d = json.loads(line)
            eps[(run, f"{d['env']}/{d['task_index']}/t{d['trial']}")] = d


def has_q(b):
    return any(Q in str(c.get("tag")).replace("+", " ").split() for c in b["causes"])


blocks = [b for b in D["blocks"] if has_q(b)]
byconv = collections.OrderedDict()
for b in blocks:
    byconv.setdefault((b["run"], b["conv"]), []).append(b)
keys = list(byconv)
random.Random(SEED).shuffle(keys)
if ONLY:
    keys = [tuple(x.split("|")) for x in ONLY]
else:
    keys = keys[:N]
ans_by_conv = collections.defaultdict(list)
for a in D["answers"]:
    if a["qid"] == Q:
        for c in a["v3_convs"]:
            ans_by_conv[(a["run"], c)].append(a)


def short(t, n=900):
    t = str(t or "").replace("\n", " / ")
    return t if len(t) <= n else t[:n] + "…"


for k in keys:
    d = eps[k]
    ci = D["conv_info"][f"{k[0]}|{k[1]}"]
    bl = byconv[k]
    b = bl[0]
    print("=" * 100)
    print(f"CONV {k[0]} {ci['group']} {k[1]}  v3 reward {ci['reward']}  frozen same try {ci['frozen_reward']}  frozen task {ci['frozen_task_mean']:.2f}  steps {ci['n_steps']}  blocks with {Q}: {len(bl)}")
    print("  blocks:", [(x['step'], x['action'], [c.get('tag') for c in x['causes']], 'ran later' if x['ran_later'] else 'never ran', 'gold' if x['is_gold'] else '') for x in bl])
    att = next(a for a in d["attempts"] if a["blocked"] and a["exec_step"] == b["step"] and a["attempt"] == b["attempt"])
    hist = d["executed"][:att["executed_prefix_len"]]
    print(f"  FIRST BLOCK step {b['step']} {b['action']} {short(json.dumps(b['kwargs']), 400)}")
    print("  FEEDBACK:", short(att.get("feedback"), 700))
    # transcript tail: last 6 user/assistant text messages before the block
    texts = [(m["role"], m.get("content")) for m in hist if m.get("role") in ("user", "assistant") and m.get("content")]
    hk = {key(t): i for i, (_, t) in enumerate(texts)}
    print("  --- last messages before the block")
    for role, t in texts[-5:]:
        print(f"   [{role[0].upper()}] {short(t, 1100)}")
    # answers of this question about messages in the history
    cand = []
    for a in ans_by_conv.get(k, []):
        idx = []
        for name, v in a["input"].items():
            if name in ("details", "action", "tools", "trip", "items_action"):
                continue
            for t in (v if isinstance(v, list) else [v]):
                if key(t) in hk:
                    idx.append(hk[key(t)])
        if idx and max(idx) >= len(texts) - 6:
            cand.append((max(idx), a))
    cand.sort(key=lambda x: -x[0])
    print(f"  --- {Q} answers about recent messages (newest first, max 3)")
    for _, a in cand[:3]:
        r = recs.get(a["key"], {})
        pu = r.get("prompt_user", "")
        m = re.search(r"(The action and its details:|The action:|What the agent's tools can do:|The items:)(.*?)(\nQuestion:)", pu, re.S)
        detail = m.group(2).strip() if m else ""
        print(f"   ANSWER {a['status']} quote={short(a.get('quote'), 200)!r}")
        if detail and Q != "K13":
            print("   DETAILS:", short(detail, 1200))
        for name, v in a["input"].items():
            if name in ("details", "action", "tools", "trip", "items_action"):
                continue
            if name in ("reply", "message") or Q in ("K13", "K5", "K16"):
                print(f"   INPUT {name}:", short(v if isinstance(v, str) else " || ".join(v), 600))
    # what happened after: later attempts summary
    later = [(a["exec_step"], a["action"], "BLOCKED" if a["blocked"] else "ok") for a in d["attempts"] if a["exec_step"] > b["step"] and a["action"] != "respond"]
    print("  --- later tool calls:", later[:12])
    last_user = [m.get("content") for m in d["messages"] if m.get("role") == "user"][-1:]
    print("  --- last user msg:", short(last_user[0] if last_user else "", 300))
