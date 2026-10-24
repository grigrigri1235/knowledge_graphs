import json,glob
R="output/eval_v3/B2/B2_20261023T155537Z_c842d895"
n=0
for f in sorted(glob.glob(f"{R}/questions/answers_shard*.jsonl")):
    for l in open(f):
        q=json.loads(l)
        inp=json.dumps(q["input"]).lower()
        if q["qid"]=="K2" and "book_reservation" in inp and "hat023" in inp:
            print(q["status"]); print(q["input"]["details"][:2200]); print("LISTING:",q["input"]["listing"][:1500]); n+=1
            if n>=1: raise SystemExit
