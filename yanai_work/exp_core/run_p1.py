"""ShieldAgent P1 rebuild with a model profile: the FROZEN repro_pipeline (tag repro-p1-v1) run unchanged, with
  - the rule-building model from the profile (exp_core.models.activate(profile, "rulebuild"); model in cache keys);
  - the Domain-Basic-filtered policy as input (exp_core/policy_filter.py output; the filter is applied here if the
    filtered file does not exist yet, with the headings given on the command line);
  - output under output/tgr/aspm_runs/<profile>/<domain>/<run_id>/ (never aspm_repro/, never output/repro/);
  - the embedding cache at output/tgr/_embcache/ (seeded once by copying the gpt-5-nano cache, which is only read).
After the frozen CLI finishes, the label it hard-codes ("model": "gpt-5-nano" in aspm.json meta and the manifest)
is corrected and a "tgr" block (profile, models, filter metadata) is added to manifest.json (decision M5).
Resumable: re-running replays every finished LLM call from the cache.

  python -m exp_core.run_p1 --profile luna-dev --domain airline --policy policy_docs/airline_wiki.txt \
         --drop-heading "Domain Basic" --run-id v1
Final line: "[tgr-p1] <profile>/<domain>/<run_id> DONE".
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
EMB_CACHE = os.path.join("output", "tgr", "_embcache", "embeddings.sqlite")


def _redirect_embedding_cache():
    import repro_core.embed as embed
    orig = embed.config
    src = os.path.join(ROOT, orig().get("cache_path", "output/repro/_embcache/embeddings.sqlite"))
    dst = os.path.join(ROOT, EMB_CACHE)
    if not os.path.exists(dst) and os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst + ".tmp")
        os.replace(dst + ".tmp", dst)
    embed.config = lambda: dict(orig(), cache_path=EMB_CACHE)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--policy", required=True, help="original policy document")
    ap.add_argument("--drop-heading", action="append", default=[])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args(argv)
    from exp_core import models, policy_filter
    import repro_pipeline.run as p1run          # loaded before activate so its structured_llm name is re-pointed
    act = models.activate(a.profile, "rulebuild")
    _redirect_embedding_cache()
    policy = a.policy
    filt = None
    if a.drop_heading:
        policy = os.path.join(ROOT, "output", "tgr", "policy_input", os.path.basename(a.policy).replace(".txt", ".rulebuild.txt"))
        os.makedirs(os.path.dirname(policy), exist_ok=True)
        if not os.path.exists(policy):
            policy_filter.main(["--policy", a.policy, "--out", policy] + sum([["--drop-heading", h] for h in a.drop_heading], []))
        filt = json.load(open(policy + ".filter.json"))
        if filt["drop_headings"] != a.drop_heading or filt["input"][1] != policy_filter.sha256(open(a.policy, encoding="utf-8").read()):
            raise SystemExit(f"{policy} was made from a different input or heading list; remove it to rebuild")
        policy = os.path.relpath(policy, ROOT)
    out_root = os.path.join(ROOT, "output", "tgr", "aspm_runs", a.profile)
    print(f"[tgr-p1] {a.profile}/{a.domain}/{a.run_id} start: model {act['structured_model']}, policy {policy}", flush=True)
    t0 = time.time()
    out = p1run.main(["--policy", policy, "--domain", a.domain, "--run-id", a.run_id, "--out", out_root,
                      "--workers", str(a.workers)])
    model = act["structured_model"]
    ap_path, man_path = os.path.join(out, "aspm.json"), os.path.join(out, "manifest.json")
    aspm = json.load(open(ap_path))
    if isinstance(aspm.get("meta"), dict):
        aspm["meta"]["model"] = model
        p1run.dump(ap_path, aspm)
    man = json.load(open(man_path))
    man["tgr"] = {"profile": a.profile, "rulebuild_model": model, "roles": act["roles"],
                  "label_fix": "frozen repro_pipeline/run.py writes meta.model='gpt-5-nano'; corrected here (decision M5)",
                  "original_policy": a.policy, "filter": filt, "embedding_cache": EMB_CACHE,
                  "wall_seconds": round(time.time() - t0, 1)}
    p1run.dump(man_path, man)
    print(f"[tgr-p1] {a.profile}/{a.domain}/{a.run_id} DONE: {out}", flush=True)


if __name__ == "__main__":
    main()
