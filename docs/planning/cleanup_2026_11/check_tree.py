"""Part 7 of the cleanup: compile, import and v4-test check of one predicate_correctness tree.

Usage: python3 -B check_tree.py <predicate_correctness dir> <out.json>
Run once on the snapshot (before) and once on the cleaned tree (after); compare_trees.py diffs them.
No network, no LLM call. Each import and test runs in its own process with a timeout.
"""
import concurrent.futures as cf
import json
import os
import py_compile
import subprocess
import sys

PKGS = ("guard", "scoring", "state_tracker", "fork", "scripts", "tests")


def last_line(s):
    lines = [x for x in s.strip().splitlines() if x.strip()]
    return lines[-1][:300] if lines else ""


def run(cmd, cwd, timeout):
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return "timeout", ""


def main(root, out):
    root = os.path.abspath(root)
    pys = []
    for d, _, fs in os.walk(root):
        for f in fs:
            if f.endswith(".py"):
                pys.append(os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/"))
    pys.sort()

    compiled = {}
    for r in pys:
        try:
            py_compile.compile(os.path.join(root, r), doraise=True, cfile=os.devnull)
            compiled[r] = "ok"
        except Exception as e:  # noqa: BLE001 - report any compile error
            compiled[r] = "error: " + last_line(str(e))

    mods = [r for r in pys if r.split("/")[0] in PKGS]
    names = {r: r[:-3].replace("/", ".").removesuffix(".__init__") for r in mods}

    def imp(r):
        code, txt = run([sys.executable, "-B", "-c", f"import {names[r]}"], root, 120)
        return r, "ok" if code == 0 else f"fail ({code}): {last_line(txt)}"

    tests = [r for r in mods if r.startswith("tests/test_v4_")]

    def test(r):
        code, txt = run([sys.executable, "-B", "-m", "unittest", names[r]], root, 900)
        return r, {"code": code, "summary": last_line(txt)}

    with cf.ThreadPoolExecutor(8) as ex:
        imports = dict(ex.map(imp, mods))
        results = dict(ex.map(test, tests))

    json.dump({"root": root, "compile": compiled, "import": imports, "tests": results}, open(out, "w"), indent=1)
    print(f"py {len(pys)} compile_err {sum(v != 'ok' for v in compiled.values())} "
          f"import_fail {sum(v != 'ok' for v in imports.values())} "
          f"tests {len(results)} tests_not_ok {sum(v['code'] != 0 for v in results.values())}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
