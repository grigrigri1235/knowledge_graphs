import json,glob,collections
R="output/eval_v3/B2/B2_20261023T155537Z_c842d895"
spec=json.load(open("/tmp/claude-1000/-home-azureuser-code-projects/dbfe7ffd-ee14-4b6f-ab52-d79bdd15e981/scratchpad/spec1.json"))
EP={}
for a in ["tgr_tracker_v3","tgr_frozen"]:
    for f in sorted(glob.glob(f"{R}/{a}/episodes_shard*.jsonl")):
        for l in open(f):
            o=json.loads(l); EP[(a,o["env"],o["task_index"],o["trial"])]=o
def blocks(o):
    res=[]
    for x in o["attempts"]:
        if not (x["blocked"] or x.get("cap_override")): continue
        g=x["guard"]; logic=" ".join(r.get("logic","") for r in g.get("violated_rules",[]))
        ff=[]
        for fn,fv in g.get("judge",{}).items():
            if fn in logic:
                fd=(g.get("v3") or {}).get("facts",{}).get(fn,{})
                ff.append(f"{fn}={fv.get('value')}({fv.get('source')}{','+fd['first_question'] if fd.get('first_question') else ''})")
        res.append(f"step{x['exec_step']}.{x['attempt']} {x['action']}{' CAP' if x.get('cap_override') else ''} R{[r['rule_id'] for r in g.get('violated_rules',[])]} unk={g.get('unknown_predicates')} :: "+"; ".join(ff))
    return res
for name,items in spec.items():
    print("=====",name)
    for a,env,ti,tr,full in items:
        o=EP[(a,env,ti,tr)]
        print(f" {a} t{tr} r={o['reward']} steps={o['n_exec_steps']} done={o['done']}")
        for b in blocks(o): print("    ",b)
