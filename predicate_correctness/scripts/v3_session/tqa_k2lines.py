"""Heuristic: which K2 detail line is missing from the listing, for every K2 no / quote_failed answer of the v3 arm."""
import collections, json, re
BASE = "/home/azureuser/code_projects/predicate_correctness"
D = json.load(open(BASE + "/output/logs/v3_tqa_data.json"))
import glob
RECS = {}
for f in glob.glob(BASE + "/output/eval_v3/B[23]/B*/questions/answers_shard*of4.jsonl"):
    for line in open(f):
        if line.strip():
            r = json.loads(line); RECS[r["key"]] = r
def details_of(a):
    pu = RECS.get(a["key"], {}).get("prompt_user", "")
    m = re.search(r"The action and its details:(.*?)\nQuestion:", pu, re.S)
    return m.group(1) if m else ""
WORDS = {"0": "zero|no", "1": "one", "2": "two", "3": "three", "4": "four"}


def has(t, s):
    return s.lower() in t


def check(line, L):
    """(kind, present?)"""
    m = re.match(r"- order: #?(W\d+)", line)
    if m:
        return "order id", has(L, m.group(1))
    m = re.match(r"- reservation: (\w+)", line)
    if m:
        return "reservation id", has(L, m.group(1))
    m = re.match(r"- new item for (.+?) \[item (\d+)\]: item (\d+) — .*each option that changes: (.*)$", line)
    if m:
        prod, old, new, opts = m.groups()
        named = has(L, prod) or has(L, old) or any(w in L for w in prod.lower().split() if len(w) > 3)
        vals = [o.split("→")[-1].strip().lower() for o in opts.split(";")]
        newok = has(L, new) or all(v in L for v in vals)
        return "new item", named and newok
    m = re.match(r"- returned item: (.+?) \[item (\d+)\]", line)
    if m:
        prod, iid = m.groups()
        return "returned item", has(L, prod) or has(L, iid) or any(w in L for w in prod.lower().split() if len(w) > 3)
    m = re.match(r"- (payment method|refund method|new payment method)[^:]*: credit card .*ending in (\d{4})", line)
    if m:
        return "card last four", has(L, m.group(2))
    m = re.match(r"- (payment method|refund method|new payment method)[^:]*: gift card \((\w+)\)", line)
    if m:
        return "gift card", "gift card" in L or has(L, m.group(2))
    if re.match(r"- (payment method|refund method|new payment method)[^:]*: PayPal", line):
        return "paypal", "paypal" in L
    m = re.match(r"- (?:new address|new default address): (.+?) — ", line)
    if m:
        fields = [f.strip().lower() for f in m.group(1).split(",")]
        miss = [f for f in fields if f not in L]
        return ("address (only country missing)" if miss == ["usa"] else "address"), not miss
    m = re.match(r"- reason: (.+?) — ", line)
    if m:
        return "cancel reason", has(L, m.group(1))
    m = re.match(r"- flight: (HAT\d+) on", line)
    if m:
        return "flight", has(L, m.group(1))
    m = re.match(r"- cabin: (\w[\w ]*?) — ", line)
    if m:
        return "cabin", has(L, m.group(1).replace("_", " "))
    m = re.match(r"- passenger: (.+?), date of birth (\d{4})-", line)
    if m:
        return "passenger dob", has(L, m.group(1)) and m.group(2) in L
    m = re.match(r"- checked bags: (\d+) in total, (\d+) paid", line)
    if m:
        return "bags (total + paid)", ("paid" in L or "free" in L or "allowance" in L or "no charge" in L)
    if line.startswith("- travel insurance"):
        return "insurance", "insurance" in L
    if "certificate" in line:
        return "certificate", "certificate" in L
    return "other", True


per_kind = collections.Counter()
miss_kind = collections.Counter()
n_missing = collections.Counter()
ex = collections.defaultdict(list)
status = collections.Counter()
for a in D["answers"]:
    if a["qid"] != "K2" or "tgr_tracker_v3" not in a["arms"] or a["status"] == "yes":
        continue
    status[a["status"]] += 1
    L = a["input"].get("listing") or ""
    L = L.lower().replace("**", "")
    det = details_of(a)
    lines = [x.strip() for x in det.split("\n") if x.strip().startswith("- ")]
    miss = []
    for ln in lines:
        k, ok = check(ln, L)
        per_kind[k] += 1
        if not ok:
            miss_kind[k] += 1
            miss.append(k)
    n_missing[(a["status"], len(miss))] += 1
    if not miss and len(ex[a["status"]]) < 4:
        ex[a["status"]].append((a["v3_convs"][:1], L[:300]))
# id digits instead of last four
iddig = 0
for a in D["answers"]:
    if a["qid"] != "K2" or "tgr_tracker_v3" not in a["arms"] or a["status"] == "yes":
        continue
    det = details_of(a)
    L = (a["input"].get("listing") or "").lower()
    m = re.search(r"ending in (\d{4})", det)
    if m and m.group(1) not in L and re.search(r"(ending|card)[^0-9]{0,15}\d{5,7}|ending in \d{4}", L):
        iddig += 1
print("K2 non-yes answers (v3 arm, unique):", dict(status))
print("lines checked per kind:", dict(per_kind))
print("lines missing per kind:", dict(miss_kind))
print("missing count per answer:", sorted(n_missing.items()))
print("card line missing while the listing names some other card digits:", iddig)
for s, xs in ex.items():
    print("EXAMPLES no line missing,", s)
    for x in xs:
        print("  ", x)
# per run split of K2 no
byrun = collections.Counter((a["run"], a["status"]) for a in D["answers"] if a["qid"] == "K2" and "tgr_tracker_v3" in a["arms"])
print("K2 status by run:", dict(byrun))
byrun1 = collections.Counter((a["run"], a["status"]) for a in D["answers"] if a["qid"] == "K1" and "tgr_tracker_v3" in a["arms"])
print("K1 status by run:", dict(byrun1))
# K1 no where reply names card digits that differ from the action's last four
k1 = 0; k1n = 0
for a in D["answers"]:
    if a["qid"] != "K1" or "tgr_tracker_v3" not in a["arms"] or a["status"] == "yes":
        continue
    k1n += 1
    act = a["input"].get("action") or ""
    r = a["input"].get("reply") or ""
    m = re.search(r"ending in (\d{4}) \(credit_card_(\d+)\)", act)
    if m:
        last4, idd = m.groups()
        digs = re.findall(r"\d{4,7}", r)
        if any(d != last4 and d in idd for d in digs):
            k1 += 1
print("K1 non-yes:", k1n, "of which the reply names card id digits (not the last four):", k1)
