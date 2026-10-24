"""Markdown table: method-file hash vs eval v2 records (read only). Run from predicate_correctness/."""
import datetime, json, os, sys
sys.path.insert(0, os.getcwd())
from state_tracker.v3 import frozen as F
e = F.read_manifest()
sums = {}
for line in open("from_shieldagent/SHA256SUMS", encoding="utf-8"):
    if line.strip():
        h, rel = line.rstrip("\n").split("  ", 1)
        sums["from_shieldagent/" + rel] = h
rb = json.load(open("output/eval_v2/checks/ref/ref_guards_build.json"))
rec = {}  # rel -> list of (where, hash)
def add(rel, where, h):
    rec.setdefault(rel, []).append((where, h))
for rel in e:
    if rel in sums and F.group_of(rel) in ("method", "splits"):
        add(rel, "SHA256SUMS", sums[rel])
for k, v in rb["runner_files_sha256"].items():
    add("from_shieldagent/" + k, "ref_guards_build.json runner_files_sha256", v["sha256"])
for k, v in rb["frozen_inputs"]["FROZEN_SHA256_in_guard_tgr_tracker_py"].items():
    add(k, "guard/tgr_tracker.py FROZEN_SHA256 (as in ref_guards_build.json)", v)
for k, v in rb["frozen_inputs"]["rules"].items():
    add(k, "ref_guards_build.json frozen_inputs.rules", v["sha256"])
add("guard/tgr_tracker.py", "ref_guards_build.json frozen_inputs.guard_tgr_tracker_py", rb["frozen_inputs"]["guard_tgr_tracker_py"]["sha256"])
add("from_shieldagent/rules/airline/rule_set.json", "ref_guards_build.json domains.airline.rule_set_sha256", rb["domains"]["airline"]["rule_set_sha256"])
add("from_shieldagent/rules/retail/rule_set.json", "ref_guards_build.json domains.retail.rule_set_sha256", rb["domains"]["retail"]["rule_set_sha256"])
add("from_shieldagent/runner/method_tgr/prompts/judge.md", "ref_guards_build.json judge_call.judge_template_sha256", rb["judge_call"]["judge_template_sha256"])
# run files: guard info frozen_sha256 / rule_set_sha256 / rule set manifest
import glob
runs = sorted(glob.glob("output/eval_v2/**/run_*.json", recursive=True) + glob.glob("output/online/p10_*/*/*/run_*.json"))
def walk(x, path, out):
    if isinstance(x, dict):
        for k, v in x.items(): walk(v, path + [str(k)], out)
    elif isinstance(x, list):
        for i, v in enumerate(x): walk(v, path + [str(i)], out)
    elif isinstance(x, str) and len(x) == 64:
        out.append((path, x))
runrec = {}
for r in runs:
    out = []
    walk(json.load(open(r)), [], out)
    for path, h in out:
        key = None
        if "frozen_sha256" in path:
            key = path[-1]
        elif path[-1] == "rule_set_sha256":
            # domain from the record
            dom = "airline" if "/airline/" in r else ("retail" if "/retail/" in r else None)
            env_guess = None
            key = ("rule_set", tuple(path))
        if key:
            runrec.setdefault(key if isinstance(key, str) else "rule_set_sha256", []).append((r, h))
for k, lst in runrec.items():
    if k != "rule_set_sha256":
        for r, h in lst:
            add(k, "run files guard_info.frozen_sha256", h)
# rule_set_sha256 in run files: match by value to airline/retail
for r, h in runrec.get("rule_set_sha256", []):
    if h == e["from_shieldagent/rules/airline/rule_set.json"]:
        add("from_shieldagent/rules/airline/rule_set.json", "run files rule_set_sha256", h)
    elif h == e["from_shieldagent/rules/retail/rule_set.json"]:
        add("from_shieldagent/rules/retail/rule_set.json", "run files rule_set_sha256", h)
    else:
        print("UNMATCHED rule_set_sha256", r, h)
add("from_shieldagent/rules/airline/rule_set.json", "guard/run_online.py FROZEN_RULES_SHA256", None)
src = open("guard/run_online.py").read()
import re
m = re.search(r"FROZEN_RULES_SHA256\s*=\s*\{(.*?)\}", src, re.S)
rec["from_shieldagent/rules/airline/rule_set.json"].pop()
for dom, h in re.findall(r'"(airline|retail)":\s*"([0-9a-f]{64})"', m.group(1)):
    add(f"from_shieldagent/rules/{dom}/rule_set.json", "guard/run_online.py FROZEN_RULES_SHA256", h)
for dom, h in re.findall(r'"(airline|retail)":\s*"([0-9a-f]{64})"', re.search(r"FROZEN_SHA256 = \{(.*?)\}", open("state_tracker/replay.py").read(), re.S).group(1)):
    add(f"state_tracker/lookups_{dom}.json", "state_tracker/replay.py FROZEN_SHA256", h)
print("| file | our sha256 (first 16) | recorded in (count of records) | equal |")
print("|---|---|---|---|")
n_eq = n_diff = n_none = 0
for rel in sorted(r for r in e if F.group_of(r) in ("method", "splits")):
    lst = rec.get(rel, [])
    if not lst:
        n_none += 1
        mt = datetime.datetime.utcfromtimestamp(os.path.getmtime(rel)).strftime("%Y-%m-%d %H:%M")
        print(f"| `{rel}` | `{e[rel][:16]}` | no record (file modified {mt} UTC) | no record |")
        continue
    where = {}
    alleq = True
    for w, h in lst:
        where[w] = where.get(w, 0) + 1
        alleq &= (h == e[rel])
    n_eq += alleq
    n_diff += (not alleq)
    ws = "; ".join(f"{w} ({n})" for w, n in where.items())
    print(f"| `{rel}` | `{e[rel][:16]}` | {ws} | {'yes' if alleq else 'NO'} |")
print(f"equal {n_eq}, differ {n_diff}, no record {n_none}")
