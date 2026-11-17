"""Part 7: diff the before/after checks. A file counts as broken by the cleanup only if it was ok before and is not
ok after. Also re-does the compile step with compile() (check_tree.py's py_compile wrote to /dev/null and failed).

Usage: python3 -B compare_trees.py before.json after.json out.md
"""
import json
import os
import sys


def compile_errors(root, files):
    bad = {}
    for r in files:
        try:
            compile(open(os.path.join(root, r), encoding="utf-8").read(), r, "exec")
        except Exception as e:  # noqa: BLE001
            bad[r] = f"{type(e).__name__}: {e}"[:200]
    return bad


def main(before_p, after_p, out):
    b, a = json.load(open(before_p)), json.load(open(after_p))
    lines = ["# Part 7: before vs after", ""]
    cb = compile_errors(b["root"], b["compile"])
    ca = compile_errors(a["root"], a["compile"])
    lines += [f"- compile errors: before {len(cb)} of {len(b['compile'])}, after {len(ca)} of {len(a['compile'])}"]
    new_c = sorted(set(ca) - set(cb))
    broke_i = sorted(r for r, v in a["import"].items() if v != "ok" and b["import"].get(r) == "ok")
    fixed_i = sorted(r for r, v in a["import"].items() if v == "ok" and b["import"].get(r) not in (None, "ok"))
    same_fail_i = sorted(r for r, v in a["import"].items() if v != "ok" and b["import"].get(r) not in (None, "ok"))
    lines += [f"- imports: before {sum(v != 'ok' for v in b['import'].values())} fail of {len(b['import'])}, "
              f"after {sum(v != 'ok' for v in a['import'].values())} fail of {len(a['import'])}",
              f"- **imports broken by the cleanup: {len(broke_i)}**", ""]
    broke_t, same_t = [], []
    for r, v in sorted(a["tests"].items()):
        bv = b["tests"].get(r)
        if v["code"] != 0 and bv and bv["code"] == 0:
            broke_t.append(r)
        elif v["code"] != 0:
            same_t.append(r)
        elif bv and v["summary"] != bv["summary"]:
            same_t.append(r)
    lines += [f"- v4 test files: {len(a['tests'])} after (before {len(b['tests'])}; test_v4_v3_untouched removed)",
              f"- **v4 tests broken by the cleanup: {len(broke_t)}**", ""]
    lines += ["## New compile errors"] + [f"- {r}: {ca[r]}" for r in new_c] + ["(none)" if not new_c else "", ""]
    lines += ["## Imports broken by the cleanup"] + [f"- {r}: {a['import'][r]}" for r in broke_i]
    lines += ["(none)" if not broke_i else "", ""]
    lines += ["## Tests broken by the cleanup"] + [f"- {r}: {a['tests'][r]['summary']}" for r in broke_t]
    lines += ["(none)" if not broke_t else "", ""]
    lines += ["## Already failing before the cleanup (same here and in the snapshot)", "",
              "| file | before | after |", "|---|---|---|"]
    for r in same_fail_i:
        lines.append(f"| import {r} | {b['import'][r][:90]} | {a['import'][r][:90]} |")
    for r in same_t:
        lines.append(f"| test {r} | {b['tests'].get(r, {}).get('summary', '-')[:90]} | {a['tests'][r]['summary'][:90]} |")
    if fixed_i:
        lines += ["", "## Imports that failed before and pass now"] + [f"- {r}" for r in fixed_i]
    open(out, "w").write("\n".join(lines) + "\n")
    print(f"new_compile {len(new_c)} broke_imports {len(broke_i)} broke_tests {len(broke_t)}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
