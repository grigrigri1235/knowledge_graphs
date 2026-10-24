import re, hashlib, os, sys, collections
ov = "/home/azureuser/code_projects/docs/planning/tracker_v3/overview.md"
pc = "/home/azureuser/code_projects/predicate_correctness"
base = "/home/azureuser/code_projects"
rows = []
for i, line in enumerate(open(ov), 1):
    m = re.match(r"^\| ([^`|]*)`([^`]+)`[^|]*\| `([0-9a-f]{64})`", line)
    if m: rows.append((i, m.group(1), m.group(2), m.group(3), line.strip()[:160]))
def path_of(p):
    for b in (pc, base):
        f = os.path.join(b, p)
        if os.path.isfile(f): return f
    return None
byp = collections.defaultdict(list)
for r in rows: byp[r[2]].append(r)
print("rows", len(rows), "files", len(byp))
for p, rs in byp.items():
    f = path_of(p)
    cur = hashlib.sha256(open(f, "rb").read()).hexdigest() if f else None
    match = [r[0] for r in rs if r[3] == cur]
    last = rs[-1][0]
    status = "OK" if match and match[-1] == last else ("MISSING" if cur is None else ("OLDER-ROW-MATCH" if match else "NO-ROW-MATCH"))
    print(f"{status}\t{p}\trows={[r[0] for r in rs]}\tmatching_row={match}\tcur={cur}")
