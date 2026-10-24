"""Tiny-question audit, step 1: read B2 + B3 lines, attribute blocks to questions, match answers to conversations.
Read-only on the runs. Writes one JSON to output/logs/v3_tqa_data.json. No project imports, no network."""
import collections, glob, json, os, re, unicodedata

BASE = "/home/azureuser/code_projects/predicate_correctness"
RUNS = {"B2": BASE + "/output/eval_v3/B2/B2_20261023T155537Z_c842d895",
        "B3": BASE + "/output/eval_v3/B3/B3_20261023T190740Z_9bf882c0"}
ARMS = ["tgr_tracker_v3", "tgr_frozen", "direct_facts_v3"]


def key(t):
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "", t)


rt = {d: {r["id"]: r for r in json.load(open(f"{BASE}/output/eval_v3/rule_table_{d}.json"))["rules"]}
      for d in ("retail", "airline")}
facts_doc = {d: json.load(open(f"{BASE}/state_tracker/v3/facts_v3_{d}.json"))["facts"] for d in ("retail", "airline")}
part_q = {d: {f: {pid: p.get("question") for pid, p in e["parts"].items()} for f, e in facts_doc[d].items()}
          for d in facts_doc}

eps = {}          # (run, arm, conv) -> ep
for run, R in RUNS.items():
    for arm in ARMS:
        for p in sorted(glob.glob(f"{R}/{arm}/episodes_shard*of4.jsonl")):
            for line in open(p):
                d = json.loads(line)
                cid = f"{d['env']}/{d['task_index']}/t{d['trial']}"
                eps[(run, arm, cid)] = d


def group(run, d):
    return run if run == "B3" else f"B2-{d['task_group']}"


def call_sig(name, kw):
    return name + json.dumps(kw, sort_keys=True)


out_blocks, conv_info, asks = [], {}, collections.defaultdict(collections.Counter)
for (run, arm, cid), d in eps.items():
    if arm != "tgr_tracker_v3":
        continue
    dom = d["env"]
    g = group(run, d)
    executed_sigs = []
    for a in d["attempts"]:
        if not a["blocked"]:
            executed_sigs.append((a["exec_step"], call_sig(a["action"], a.get("kwargs") or {})))
    gold = [call_sig(x["name"], x.get("kwargs") or {}) for x in ((d.get("reward_info") or {}).get("actions") or [])]
    conv_asks = collections.Counter()
    blocks = []
    for a in d["attempts"]:
        gd = a["guard"]
        v3 = gd.get("v3") or {}
        qs = (v3.get("questions") or {}).get("asked") or {}
        conv_asks.update(qs)
        if not a["blocked"]:
            continue
        facts = v3.get("facts") or {}
        judge = gd.get("judge") or {}
        causes = []
        for vr in gd.get("violated_rules") or []:
            rid = str(vr["rule_id"])
            rule = rt[dom].get(rid)
            if rule is None:
                causes.append({"rule": rid, "fact": None, "tag": "rule_not_tabled"})
                continue
            for f, bvs in rule["blocking_values"].items():
                val = (judge.get(f) or {}).get("value", (facts.get(f) or {}).get("value"))
                if val not in bvs and val is not None:
                    continue
                fr = facts.get(f) or {}
                src = fr.get("source") or (judge.get(f) or {}).get("source")
                tag = None
                if src in ("question", "blocking_value", "lazy_skip"):
                    qparts = []
                    for pid, p in (fr.get("parts") or {}).items():
                        q = part_q[dom].get(f, {}).get(pid)
                        if q and (p.get("value") is False or p.get("how") == "problem" or (p.get("value") is True and fr.get("value") is True and bvs == [True])):
                            qparts.append(f"{q} {'unclear' if p.get('how') == 'problem' else ('yes' if p.get('value') else 'no')}")
                    if src == "lazy_skip":
                        tag = "lazy_skip"
                    elif qparts:
                        tag = "+".join(sorted(set(qparts)))
                    elif fr.get("problems"):
                        tag = "blocking_value:" + ",".join(map(str, fr.get("problems")))
                    else:
                        tag = f"code-part ({fr.get('first_question')})"
                else:
                    tag = "code"
                causes.append({"rule": rid, "fact": f, "src": src, "tag": tag,
                               "first_q": fr.get("first_question"),
                               "parts": {pid: [p.get("value"), p.get("how")] for pid, p in (fr.get("parts") or {}).items()},
                               "problems": fr.get("problems")})
        sig = call_sig(a["action"], a.get("kwargs") or {})
        later = any(s == sig and st >= a["exec_step"] for st, s in executed_sigs)
        blocks.append({"step": a["exec_step"], "attempt": a["attempt"], "action": a["action"], "kwargs": a.get("kwargs"),
                       "causes": causes, "ran_later": later, "is_gold": sig in gold,
                       "feedback": (a.get("feedback") or "")[:1500], "agent_text": (a.get("agent_text") or "")[:600]})
    for b in blocks:
        out_blocks.append(dict(b, run=run, group=g, conv=cid, dom=dom, reward=d["reward"]))
    for k, v in conv_asks.items():
        asks[g][k] += v
    conv_info[f"{run}|{cid}"] = {"group": g, "reward": d["reward"], "n_blocks": d["n_blocks"],
                                 "n_steps": d["n_exec_steps"], "asks": dict(conv_asks),
                                 "last_action": d["attempts"][-1]["action"] if d["attempts"] else None,
                                 "transferred": any(a["action"] == "transfer_to_human_agents" and not a["blocked"] for a in d["attempts"]),
                                 "frozen_reward": (eps.get((run, "tgr_frozen", cid)) or {}).get("reward"),
                                 "frozen_task_mean": None}
# frozen task means
for ck, ci in conv_info.items():
    run, cid = ck.split("|")
    env, ti, _ = cid.split("/")
    rs = [eps[(run, "tgr_frozen", f"{env}/{ti}/t{t}")]["reward"] for t in range(3) if (run, "tgr_frozen", f"{env}/{ti}/t{t}") in eps]
    vs = [eps[(run, "tgr_tracker_v3", f"{env}/{ti}/t{t}")]["reward"] for t in range(3) if (run, "tgr_tracker_v3", f"{env}/{ti}/t{t}") in eps]
    ci["frozen_task_mean"] = sum(rs) / len(rs) if rs else None
    ci["v3_task_mean"] = sum(vs) / len(vs) if vs else None

# ---- answers: match each record to arm/conversation by its message inputs
msg_index = collections.defaultdict(set)
for (run, arm, cid), d in eps.items():
    if arm not in ("tgr_tracker_v3", "direct_facts_v3"):
        continue
    texts = [m.get("content") for m in d["messages"] if m.get("role") in ("user", "assistant")]
    texts += [a.get("agent_text") for a in d["attempts"]] + [(a.get("kwargs") or {}).get("content") for a in d["attempts"]]
    for t in texts:
        k = key(t)
        if len(k) >= 1:
            msg_index[(run, k)].add((arm, cid))
answers = []
unmatched = collections.Counter()
for run, R in RUNS.items():
    for p in sorted(glob.glob(f"{R}/questions/answers_shard*of4.jsonl")):
        for line in open(p):
            if not line.strip():
                continue
            r = json.loads(line)
            inp = r.get("input") or {}
            cands = None
            for name, v in inp.items():
                if name in ("details", "action", "tools", "trip", "items_action"):
                    continue
                vals = v if isinstance(v, list) else [v]
                for t in vals:
                    s = msg_index.get((run, key(t)), set())
                    if s:
                        cands = s if cands is None else (cands & s or cands)
            arms = sorted({a for a, _ in (cands or set())})
            convs = sorted({c for a, c in (cands or set()) if a == "tgr_tracker_v3"})
            if not cands:
                unmatched[(run, r["qid"])] += 1
            answers.append({"run": run, "qid": r["qid"], "status": r.get("status"), "answer": r.get("answer"),
                            "quote": r.get("quote"), "arms": arms, "v3_convs": convs, "key": r["key"],
                            "input": inp})
json.dump({"blocks": out_blocks, "conv_info": conv_info, "asks": {g: dict(c) for g, c in asks.items()},
           "answers": answers, "unmatched": {f"{a}|{b}": n for (a, b), n in unmatched.items()}},
          open(BASE + "/output/logs/v3_tqa_data.json", "w"), indent=0, default=str)
print("blocks", len(out_blocks), "convs", len(conv_info), "answers", len(answers), "unmatched", sum(unmatched.values()))
print("unmatched by q", dict(unmatched))
