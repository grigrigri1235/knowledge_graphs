"""Collect E1-E6 for one automatic run into a JSON (inputs to docs/step2b_auto/report.md).

python -m eval.collect <domain> <run_dir> <out.json> [--labels L.json] [--proxy P.json] [--mapping M.json]
"""
from __future__ import annotations

import argparse
import json

from eval.e1_clauses import e1
from eval.e2_rules import score
from eval.e3_e6 import e3_e5, e4, e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("run_dir")
    ap.add_argument("out")
    ap.add_argument("--labels")
    ap.add_argument("--proxy")
    ap.add_argument("--mapping")
    a = ap.parse_args()
    res = {"domain": a.domain, "run": a.run_dir, "E1": e1(a.domain, a.run_dir), "E6": e6(a.run_dir)}
    if a.labels:
        res["E2"] = score(a.domain, a.run_dir, a.labels, a.proxy)
        res["E4"] = e4(a.domain, a.run_dir, a.labels)
    elif a.proxy:
        res["E2_proxy_only"] = score(a.domain, a.run_dir, a.proxy)
    if a.mapping:
        res["E3_E5"] = e3_e5(a.domain, a.run_dir, a.mapping)
    json.dump(res, open(a.out, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({k: (v if k in ("domain", "run") else "...") for k, v in res.items()}))


if __name__ == "__main__":
    main()
