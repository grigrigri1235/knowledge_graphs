import json,glob,collections
R="output/eval_v3/B2/B2_20261023T155537Z_c842d895"
# spot check K1 answers on retail 92 phrases, K2 detail lines for airline 8 booking
for f in sorted(glob.glob(f"{R}/questions/answers_shard*.jsonl")):
    for l in open(f):
        q=json.loads(l)
        inp=json.dumps(q["input"]).lower()
        if q["qid"]=="K1" and ("all four items" in inp) and ("9375" in inp or "proceed" in inp):
            print("K1-92",f[-16:],q["status"],"| reply:",q["input"].get("reply","")[:160])
        if q["qid"]=="K2" and "book a new reservation" in inp and "hat023" in inp:
            d=q["input"]["details"]
            print("K2-air8",q["status"],"| lines:", [x[:110] for x in d.split("\n") if x.startswith("- ")][:12])
            break
