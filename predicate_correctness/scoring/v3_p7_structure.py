"""Tracker v3, part 7: the development-data run of the text-structure code (pass marks P7.1-P7.6).

docs/planning/tracker_v3/p7.md, step 4. Development data only (side "dev" of output/eval_v3/split.json); a hold-out
conversation is skipped before anything of it is read. $0: no LLM call, no network.

What it does, per development conversation (fork/offline_v3.py iter_conversations):
  - P7.1 the view: the view of the whole executed history, rebuilt into messages, equals the history (an
    independent walk over the messages here); every check's prefix view holds exactly the messages before it; no
    text is cut (characters counted);
  - every structure part of p7's overlay (output/eval_v3/p7_parts/exprs_<domain>.json), evaluated ALONE with the v3
    evaluator on the check's state (state.walk) and view, at every check whose tool is in one of the fact's rules;
  - P7.2 identity: retail: every check where the identity fact is true: τ-bench's own find_user_id_* on the
    database copy with the call's values returns the task's user (task file); airline: `me` (a typed user id) exists
    (get_user_details on the copy, no Error) and equals the task's user; the "obtained" user ids too (reported);
  - P7.3 disclosure: a RAW scan, separate from the info classes: every string field of every user, order and
    payment record of the database (and the records changed in the conversation) vs the reply's tokens; a value
    counts when it is held by at most RAW_MAX_USERS users, is not catalog data, and no user message holds it. Replies
    before login that the disclosure fact lets through by code (part a false, part b false) must hold none;
  - P7.4 another user: the owner of every call's object, from the database (own code here), vs `me`; part a of
    request_is_for_another_user (p6's expression when its overlay exists, else a reference written here) must be
    true for every call on another user's object; replies after login: the raw scan for other users' values;
  - P7.6 blocks added: the structure value (other parts unknown) takes the blocking value where the judge's saved
    value allowed. Identity and disclosure: each must have an objective reason. The other facts: each labelled with
    τ-bench's tool label (output/eval_v3/tool_labels.jsonl) and the task's expected actions;
  - screens on development data (recall on the judge's true values and on executed send_certificate calls);
  - the p4 follow-up: the too-strict reminder and listing checks of output/eval_v3/p4_wrong.jsonl.
Report: output/eval_v3/p7_structure.md; details: output/logs/v3_p7_run_details.json.

    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 python3 -B -m scoring.v3_p7_structure [--limit N] \
        > output/logs/v3_p7_<nn>_run.log 2>&1
    python3 -B -m scoring.v3_p7_structure --screens <set folder>      (the blind screen sets; reads no data set)
"""
from __future__ import annotations

import argparse
import ast
import collections
import glob
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

from state_tracker import paths                                    # noqa: E402
from state_tracker import state as S                               # noqa: E402
from state_tracker.v3 import facts_format_v3 as F                  # noqa: E402
from state_tracker.v3 import message_view as MV                    # noqa: E402

EVAL_V3 = os.path.join(paths.OUTPUT_DIR, "eval_v3")
REPORT = os.path.join(EVAL_V3, "p7_structure.md")
DETAILS = os.path.join(paths.LOGS_DIR, "v3_p7_run_details.json")
RAW_MAX_USERS = 20
VENV_TAU = os.path.expanduser("~/venvs/tau-bench/lib/python3.12/site-packages/tau_bench")
TASK_FILES = {"retail/test": ("envs/retail/tasks_test.py", "TASKS_TEST"),
              "retail/train": ("envs/retail/tasks_train.py", "TASKS_TRAIN"),
              "airline/test": ("envs/airline/tasks_test.py", "TASKS")}
IDENTITY_FACTS = ("email_identity_provided_by_user", "name_and_zip_identity_provided_by_user")
DISCLOSURE = "user_specific_information_disclosed"
CORE = IDENTITY_FACTS + (DISCLOSURE,)
# p5's literal wording for the listing candidates (the order id itself), run beside the overlay for the report
LITERAL = {
    "consequential_action_details_listed": {"a": "len(listing_candidates(call_key_ids())) > 0"},
    "user_confirmed_cancellation_order_and_reason": {"a": "len(confirm_pairs(call_key_ids())) > 0"},
    "user_confirmed_return_order_items_and_method": {"a": "len(confirm_pairs(call_key_ids())) > 0"},
    "user_explicitly_confirmed_pending_action": {"a": "len(confirm_pairs(call_key_ids())) > 0"},
    "user_chose_pending_payment_method": {
        "b": "len(payment_confirm_pairs(args['payment_method_id'], db('order', args['order_id'])['user_id'], "
             "call_key_ids())) > 0"},
    "user_chose_price_difference_payment_method": {
        "b": "len(payment_confirm_pairs(args['payment_method_id'], db('order', args['order_id'])['user_id'], "
             "call_key_ids())) > 0"},
}
REMINDER_RULES = {"retail:53": "agent_reminded_user_to_include_all_items_for_modification",
                  "retail:61": "agent_reminded_user_to_include_all_items_for_exchange"}
LISTED_RULES = {"retail:30", "retail:32", "retail:34", "retail:36", "retail:38", "retail:40", "retail:42"}
REMINDER_WORDS = re.compile(r"\b(?:all (?:the )?items?|every item|each item|any other|anything else|only item|"
                            r"only (?:one|these|this)|other items?|everything|complete list|full list|make sure|"
                            r"double-check|double check|include|included|including|is that all|are these all|"
                            r"is this all|all of them|nothing else|any more|anymore|additional)\b")


# ----------------------------------------------------------------------------------------------- inputs

def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _lit(node: ast.AST) -> Any:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("Task", "Action"):
        return {kw.arg: _lit(kw.value) for kw in node.keywords}
    if isinstance(node, ast.List):
        return [_lit(x) for x in node.elts]
    if isinstance(node, ast.Dict):
        return {_lit(k): _lit(v) for k, v in zip(node.keys, node.values)}
    return ast.literal_eval(node)


def load_tasks() -> Dict[str, List[dict]]:
    """τ-bench's task files (read with ast; tau_bench is not imported)."""
    out = {}
    for key, (rel, var) in TASK_FILES.items():
        path = os.path.join(VENV_TAU, rel)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        for st in tree.body:
            if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == var for t in st.targets):
                out[key] = _lit(st.value)
    return out


def task_of(tasks: Dict[str, List[dict]], conv: Any) -> dict:
    key = f"{conv.domain}/train" if conv.split == "tau_train" else f"{conv.domain}/test"
    return tasks[key][conv.task_id]


def load_overlay(domain: str, by: str) -> Optional[dict]:
    path = os.path.join(EVAL_V3, f"{by}_parts", f"exprs_{domain}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fact_actions(domain: str) -> Dict[str, set]:
    with open(os.path.join(EVAL_V3, f"rule_table_{domain}.json"), encoding="utf-8") as f:
        t = json.load(f)
    out: Dict[str, set] = collections.defaultdict(set)
    for r in t["rules"]:
        for fct in r["facts"]:
            out[fct].update(r["actions"])
    return out


def load_labels() -> Dict[str, dict]:
    out = {}
    with open(os.path.join(EVAL_V3, "tool_labels.jsonl"), encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            out[d["ckey"]] = d
    return out


# ----------------------------------------------------------------------------------------------- small context

class Ctx:
    """A minimal helper context (for calling message_view helpers directly)."""

    def __init__(self, state: Any, view: Any, args: dict):
        self.state, self.view, self.args = state, view, args
        self.domain = getattr(state, "domain", None)
        self.notes: List[Any] = []

    def need_view(self):
        return self.view

    def arg(self, key):
        if key not in self.args:
            raise F.MissingArgument(key)
        return self.args[key]

    def note(self, x):
        self.notes.append(x)


def part_entry(entry: dict, pid: str, expr: str) -> dict:
    """A fact entry with only one part (so a part is evaluated on its own)."""
    e = dict(entry)
    e["parts"] = {pid: dict(entry["parts"][pid], expr=expr)}
    e["combine"] = pid
    return e


# ----------------------------------------------------------------------------------------------- P7.1

def expected_entries(history: List[dict]) -> List[tuple]:
    """The view's entries as this check expects them, from the messages (own walk, not message_view)."""
    out, calls = [], {}
    for m in history:
        role = m.get("role")
        if role == "system":
            continue
        if role == "user":
            out.append(("user", m.get("content") or ""))
        elif role == "assistant":
            tcs = m.get("tool_calls") or []
            if not tcs:
                out.append(("agent", m.get("content") or ""))
            for tc in tcs:
                fn = tc.get("function") or {}
                a = fn.get("arguments")
                calls[tc.get("id")] = (fn.get("name"), a if isinstance(a, dict) else json.loads(a or "{}"))
        elif role == "tool":
            name, a = calls.pop(m.get("tool_call_id"), (m.get("name"), {}))
            out.append(("tool", name, a, m.get("content") or ""))
        else:
            out.append(("?", role))
    return out


def view_entries(view: Any) -> List[tuple]:
    return [(e.role, e.tool, e.args, e.text) if e.role == "tool" else (e.role, e.text) for e in view.entries]


# ----------------------------------------------------------------------------------------------- raw scan (P7.3)

def _rnorm(text: Any) -> str:
    """The raw scan's own normalization: accents removed, lower case, '*' and backticks removed, spaces collapsed."""
    t = unicodedata.normalize("NFKD", text if isinstance(text, str) else json.dumps(text))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("’", "'").replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", t).strip()


def _rhas(text: str, v: str) -> bool:
    """v as a whole token of the text (a decimal number such as 3356.49 is one token)."""
    if v not in text:
        return False
    return re.search(r"(?<![a-z0-9_])(?<!\d[.,])" + re.escape(v) + r"(?![a-z0-9_]|[.,]\d)", text) is not None


_RDATE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
                    r"[a-z]*\.? \d{1,2}(?:st|nd|rd|th)?,? \d{4}|\d{1,2}(?:st|nd|rd|th)? (?:jan|feb|mar|apr|may|jun|"
                    r"jul|aug|sep|oct|nov|dec)[a-z]*,? \d{4}")


def _strings(x: Any, out: List[str]) -> None:
    if isinstance(x, str):
        out.append(x)
    elif isinstance(x, dict):
        for k, v in x.items():
            if isinstance(k, str) and k.startswith(("#W", "credit_card_", "gift_card_", "paypal_", "certificate_")):
                out.append(k)
            _strings(v, out)
    elif isinstance(x, list):
        for v in x:
            _strings(v, out)


class RawScan:
    """Every string field of every user, order and payment record (airline: user, reservation, payment) ->
    the users that hold it. Catalog strings (products, variants, flights, airports) are left out."""

    def __init__(self, domain: str, db: dict):
        self.domain = domain
        self.owner: Dict[str, set] = collections.defaultdict(set)
        catalog: List[str] = []
        _strings(db.get("products", {}), catalog)
        _strings(db.get("flights", {}), catalog)
        self.catalog = {_rnorm(s) for s in catalog}
        if domain == "airline":
            for code, city in MV._airports(None).items():
                self.catalog |= {_rnorm(code), _rnorm(city)}
        for uid, u in db.get("users", {}).items():
            self.add_record(uid, u)
            self.owner[_rnorm(uid)].add(uid)
        for o in db.get("orders", {}).values():
            self.add_record(o.get("user_id"), o)
        for r in db.get("reservations", {}).values():
            self.add_record(r.get("user_id"), r)

    def add_record(self, uid: Any, rec: Any) -> None:
        add_record(self.owner, uid, rec)

    def hits(self, reply: str, typed: List[str], extra: Optional[Dict[str, set]] = None) -> List[dict]:
        t = _rnorm(reply)
        t = _RDATE.sub(" <date> ", t)
        keys = set(self.owner) | set(extra or {})
        out = []
        for v in keys:
            if v not in t:
                continue
            users = self.owner.get(v, set()) | (extra or {}).get(v, set())
            if len(users) > RAW_MAX_USERS or v in self.catalog or not _rhas(t, v):
                continue
            forms = [v, v.lstrip("#")] if v.startswith("#w") else [v]
            if any(_rhas(u, f) for u in typed for f in forms):
                continue
            out.append({"value_len": len(v), "users": set(users), "n_users": len(users), "value": v})
        return out


def add_record(extra: Dict[str, set], uid: Any, rec: Any) -> None:
    """Every string of a record, held by uid. A payment id also holds its number and the number's last four digits
    (users name a gift card that way)."""
    vals: List[str] = []
    _strings(rec, vals)
    for s in vals:
        v = _rnorm(s)
        if len(v) >= 3 and isinstance(uid, str):
            extra.setdefault(v, set()).add(uid)
            m = re.fullmatch(r"(?:gift_card|credit_card|paypal|certificate)_(\d+)", v)
            if m:
                extra.setdefault(m.group(1), set()).add(uid)
                extra.setdefault(m.group(1)[-4:], set()).add(uid)


# ----------------------------------------------------------------------------------------------- owners (P7.4)

def call_owner(domain: str, tool: str, args: dict, db: dict) -> Tuple[Optional[str], str]:
    """(the user who owns the call's object, from the database; how). None when the call has no user object."""
    if domain == "retail":
        if tool in ("get_user_details", "modify_user_address"):
            return args.get("user_id"), "user_id argument"
        if tool in MV.RETAIL_ORDER_TOOLS:
            o = db["orders"].get(args.get("order_id")) if isinstance(args.get("order_id"), str) else None
            return (o["user_id"] if o else None), "order owner"
        if tool in MV.FIND_TOOLS:
            out = S.run_tool(domain, db, tool, dict(args))
            return (None if S.is_failure(out) else out), "find tool output"
        return None, "no user object"
    if tool in ("get_user_details", "book_reservation", "send_certificate"):
        return args.get("user_id"), "user_id argument"
    if tool in MV.AIRLINE_RES_TOOLS:
        r = db["reservations"].get(args.get("reservation_id")) if isinstance(args.get("reservation_id"), str) else None
        return (r["user_id"] if r else None), "reservation owner"
    return None, "no user object"


REF_PART_A = ("reference (p7, for the check only; p6 owns part a): me is set, and the call's object is not me's: "
              "user_id argument, order owner, or the user the find tool returns")


# ----------------------------------------------------------------------------------------------- main run

def run(limit: Optional[int], datasets: Optional[List[str]] = None) -> dict:
    from fork import offline_v3 as O
    t0 = time.time()
    tasks = load_tasks()
    labels = load_labels()
    facts = {d: F.load_facts(d)["facts"] for d in paths.DOMAINS}
    ov = {d: load_overlay(d, "p7")["exprs"] for d in paths.DOMAINS}
    p6 = {d: (load_overlay(d, "p6") or {}).get("exprs", {}) for d in paths.DOMAINS}
    acts = {d: fact_actions(d) for d in paths.DOMAINS}
    trees = {d: {f: F.parse_combine(e["combine"]) for f, e in facts[d].items()} for d in paths.DOMAINS}
    p4 = {}
    with open(os.path.join(EVAL_V3, "p4_wrong.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if d["class"] == "too_strict":
                p4[d["ckey"]] = d
    raw_base = {d: RawScan(d, MV._initial_db(d)) for d in paths.DOMAINS}

    C = collections.Counter()
    part_vals = collections.Counter()               # (domain, fact, part, value/problem)
    problems = collections.Counter()
    judge_cmp = collections.Counter()               # (fact, mine, judge)
    added: List[dict] = []
    literal_added = collections.Counter()
    ident: List[dict] = []
    airline_me = collections.Counter()
    airline_me_bad: List[dict] = []
    obtained_bad: List[dict] = []
    disc_rows: List[dict] = []
    owner_rows: List[dict] = []
    other_reply_rows: List[dict] = []
    screen_recall = collections.Counter()
    screen_miss: List[dict] = []
    p4_rows: List[dict] = []
    view_fail: List[str] = []
    n_conv = 0

    for conv in O.iter_conversations(datasets):
        if conv.side != O.DEV:
            C["hold-out conversations skipped (not read)"] += 1
            continue
        if limit is not None and n_conv >= limit:
            break
        n_conv += 1
        dom = conv.domain
        ex = conv.ep["executed"]
        task = task_of(tasks, conv)
        full = MV.build_view(ex, domain=dom)
        # ---- P7.1 (whole conversation)
        C["P7.1 conversations"] += 1
        ok_conv = view_entries(full) == expected_entries(ex)
        for pr in full.problems:
            C["P7.1 notes: " + re.sub(r"message \d+: ", "", pr)] += 1
        chars_hist = sum(len(m.get("content") or "") for m in ex if m.get("role") != "system"
                         and not (m.get("role") == "assistant" and m.get("tool_calls")))
        chars_view = sum(len(e.text) for e in full.entries)
        ok_conv = ok_conv and chars_hist == chars_view
        if ok_conv:
            C["P7.1 conversations equal"] += 1
        else:
            view_fail.append(conv.conv_key)
        checks = list(conv.checks())
        by_prefix: Dict[int, list] = collections.defaultdict(list)
        for chk in checks:
            by_prefix[chk.attempt["executed_prefix_len"]].append(chk)
        raw = raw_base[dom]
        raw_extra: Dict[str, set] = {}
        raw_extra_done = 0
        typed_cache: Dict[int, List[str]] = {}
        me_seen = set()
        for n, st in S.walk(ex, dom, sorted(by_prefix)):
            for chk in by_prefix[n]:
                C["checks"] += 1
                tool, args = O.call_of(chk.msg)
                st.pending = S.normalize_action({"tool": tool, "args": args})
                view = full.prefix(n, {"tool": tool, "args": args}, st)
                # P7.1 per check
                exp_n = expected_entries(chk.history)
                if view_entries(view) != exp_n:
                    C["P7.1 check prefix differs"] += 1
                else:
                    C["P7.1 check prefixes equal"] += 1
                if chk.history_len() > 24000:
                    C["checks whose history is over 24,000 characters (the judge's view was cut; the view is not)"] += 1
                ctx = Ctx(st, view, args)
                who = MV.me(ctx)
                saved = None
                try:
                    saved = chk.saved_judge()
                except Exception as e:                             # noqa: BLE001
                    problems[f"saved_judge: {type(e).__name__}"] += 1
                vals: Dict[str, Dict[str, Any]] = {}
                for fct, parts in ov[dom].items():
                    if tool not in acts[dom].get(fct, ()):
                        continue
                    entry = facts[dom][fct]
                    pv = {}
                    for pid, spec in parts.items():
                        try:
                            r = F.evaluate(part_entry(entry, pid, spec["expr"]), st, args, view=view, name=fct)
                        except Exception as e:                     # noqa: BLE001
                            problems[f"{fct}.{pid}: {type(e).__name__}: {str(e)[:80]}"] += 1
                            pv[pid] = None
                            continue
                        if r["problems"]:
                            k = r["problems"][0]["kind"]
                            problems[f"{fct}.{pid}: problem {k}"] += 1
                            pv[pid] = "problem:" + k
                        else:
                            pv[pid] = r["value"]
                        part_vals[(dom, fct, pid, str(pv[pid]))] += 1
                    vals[fct] = pv
                    if dom == "retail" and fct in LITERAL:
                        lv = dict(pv)
                        for pid, expr in LITERAL[fct].items():
                            try:
                                rl = F.evaluate(part_entry(entry, pid, expr), st, args, view=view, name=fct)
                                lv[pid] = rl["value"] if not rl["problems"] else "problem"
                            except Exception as e:                 # noqa: BLE001
                                lv[pid] = f"error {type(e).__name__}"
                        lk = {p: v for p, v in lv.items() if isinstance(v, bool)}
                        lforced = F.combine_value(trees[dom][fct], lk)
                        jl = (saved or {}).get(fct, {}).get("value") if saved is not None else "n/a"
                        if lforced == entry["blocking_value"] and jl is (not entry["blocking_value"]):
                            literal_added[fct] += 1
                    known = {p: v for p, v in pv.items() if isinstance(v, bool)}
                    forced = F.combine_value(trees[dom][fct], known)
                    if any(isinstance(v, str) for v in pv.values()):
                        forced = entry["blocking_value"]          # a problem: the fact takes its blocking value
                    jv = (saved or {}).get(fct, {}).get("value") if saved is not None else "n/a"
                    if fct in (saved or {}):
                        judge_cmp[(fct, str(forced), str(jv))] += 1
                    if forced == entry["blocking_value"] and jv is (not entry["blocking_value"]):
                        lab = labels.get(chk.ckey) or {}
                        exp = [a for a in task.get("actions", []) if a.get("name") == tool
                               and json.dumps(a.get("kwargs"), sort_keys=True) == json.dumps(args, sort_keys=True)]
                        added.append({"ckey": chk.ckey, "fact": fct, "tool": tool, "parts": pv,
                                      "tool_label": {"accepted": lab.get("accepted"), "check": lab.get("check")}
                                      if lab else None,
                                      "expected_action": bool(exp), "blocked_saved": chk.blocked,
                                      "cap": chk.cap_override, "dataset": chk.dataset})
                # ---- P7.2 identity
                if dom == "retail" and tool in MV.FIND_TOOLS:
                    fct = IDENTITY_FACTS[0] if tool == "find_user_id_by_email" else IDENTITY_FACTS[1]
                    v = vals.get(fct, {}).get("a")
                    out = S.run_tool(dom, st.db, tool, dict(args))
                    ident.append({"ckey": chk.ckey, "fact": fct, "mine": v, "judge": (saved or {}).get(fct, {})
                                  .get("value") if saved else None, "tool_output": out,
                                  "task_user": task.get("user_id"), "gives_task_user": out == task.get("user_id")})
                if dom == "airline" and who is not None and (conv.conv_key, who) not in me_seen:
                    me_seen.add((conv.conv_key, who))
                    out = S.run_tool(dom, st.db, "get_user_details", {"user_id": who})
                    k = ("exists" if not S.is_failure(out) else "error") + ("/task user" if who == task.get("user_id")
                                                                           else "/other user")
                    airline_me[k] += 1
                    if k != "exists/task user":
                        airline_me_bad.append({"conv": conv.conv_key, "me": who, "task_user": task.get("user_id"),
                                               "result": k})
                if dom == "airline":
                    for fct, pid, uid in (("booking_required_information_established", "a", args.get("user_id")),
                                          ("modification_user_and_reservation_ids_established", "b", None),
                                          ("cancellation_context_established", "b", None),
                                          ("cancelled_flight_certificate_send_conditions_met", "a", args.get("user_id")),
                                          ("delayed_flight_certificate_send_conditions_met", "a", args.get("user_id"))):
                        if vals.get(fct, {}).get(pid) is not True:
                            continue
                        if uid is None:
                            res = st.db["reservations"].get(args.get("reservation_id"))
                            uid = res["user_id"] if res else None
                        C[f"airline obtained id true ({fct}.{pid})"] += 1
                        if uid != task.get("user_id"):
                            obtained_bad.append({"ckey": chk.ckey, "fact": fct, "id": uid,
                                                 "task_user": task.get("user_id")})
                # ---- P7.3 / P7.6 disclosure (retail replies before login)
                logged_in = bool(st.events_where(tool=list(MV.FIND_TOOLS), ok=True))
                if dom == "retail" and tool == "respond":
                    if n not in typed_cache:
                        typed_cache[n] = [_rnorm(e.text) for e in view.entries if e.role == "user"]
                    if raw_extra_done < len(st.events):
                        for ev in st.events[raw_extra_done:]:
                            if ev["ok"] and ev.get("changes_db"):
                                oid = ev["args"].get("order_id")
                                o = st.db["orders"].get(oid) if isinstance(oid, str) else None
                                if o:
                                    add_record(raw_extra, o["user_id"], o)
                                uid = ev["args"].get("user_id")
                                if isinstance(uid, str) and uid in st.db["users"]:
                                    add_record(raw_extra, uid, st.db["users"][uid])
                        raw_extra_done = len(st.events)
                    hits = raw.hits(args.get("content") or "", typed_cache[n], raw_extra)
                    pv = vals.get(DISCLOSURE, {})
                    if not logged_in:
                        code = ("block (a true)" if pv.get("a") is True else
                                "allow by code (a false, b false)" if pv.get("a") is False and pv.get("b") is False
                                else "K14 decides (a false, b true)" if pv.get("a") is False else "problem")
                        jv = (saved or {}).get(DISCLOSURE, {}).get("value") if saved else None
                        disc_rows.append({"ckey": chk.ckey, "code": code, "raw_hits": len(hits), "judge": jv,
                                          "hit_values": [h["value"] for h in hits][:5], "cap": chk.cap_override,
                                          "hit_users": [sorted(h["users"])[:3] for h in hits][:5]})
                    elif who is not None:
                        others = [h for h in hits if who not in h["users"]]
                        pa = vals.get("response_performs_task_for_another_user", {}).get("a")
                        if others or pa is True:
                            other_reply_rows.append({"ckey": chk.ckey, "raw_other_hits": len(others),
                                                     "part_a": pa, "values": [h["value"] for h in others][:5]})
                # ---- P7.4 another user (calls)
                if dom == "retail" or tool != "respond":
                    owner, how = call_owner(dom, tool, args, st.db) if tool != "respond" else (None, "reply")
                    if owner is not None:
                        rel = ("no me yet" if who is None else "me" if owner == who else "another user")
                        pa_p6 = None
                        if dom == "retail" and rel == "another user":
                            spec = (p6[dom].get("request_is_for_another_user") or {}).get("a")
                            if spec:
                                try:
                                    rr = F.evaluate(part_entry(facts[dom]["request_is_for_another_user"], "a",
                                                               spec["expr"]), st, args, view=view)
                                    pa_p6 = rr["value"] if not rr["problems"] else "problem"
                                except Exception as e:             # noqa: BLE001
                                    pa_p6 = f"error {type(e).__name__}"
                        owner_rows.append({"ckey": chk.ckey, "domain": dom, "tool": tool, "relation": rel,
                                           "how": how, "p6_part_a": pa_p6,
                                           "ref_part_a": rel == "another user", "blocked_saved": chk.blocked})
                # ---- screens on development data (the judge's true values; offers before send_certificate)
                if saved:
                    for fct, scr, scope in (
                            ("pending_response_offers_any_compensation_certificate", "offer", "reply"),
                            ("insured_cancellation_condition_met", "health", "user"),
                            ("user_complained_about_relevant_flight_situation", "complaint", "user"),
                            ("user_explicitly_requested_compensation", "compensation_request", "user"),
                            ("request_is_for_another_user", "other_person", "user"),
                            ("response_performs_task_for_another_user", "other_person", "reply_or_user")):
                        if (saved.get(fct) or {}).get("value") is True:
                            hit = False
                            if scope in ("reply", "reply_or_user") and tool == "respond":
                                hit = MV.screen_text(scr, args.get("content") or "")
                            if not hit and scope in ("user", "reply_or_user"):
                                hit = bool(MV.screened_user_messages(ctx, scr))
                            screen_recall[(fct, scr, hit)] += 1
                            if not hit:
                                screen_miss.append({"ckey": chk.ckey, "fact": fct, "screen": scr})
                if dom == "airline" and tool == "send_certificate":
                    prev = [r for r in MV.agent_messages(ctx)][:1]
                    hit = bool(prev) and MV.screen_text("offer", view.text(prev[0]))
                    screen_recall[("agent text before an executed-or-tried send_certificate", "offer", hit)] += 1
                    if not hit:
                        screen_miss.append({"ckey": chk.ckey, "fact": "text before send_certificate",
                                            "screen": "offer", "text": view.text(prev[0])[:200] if prev else None})
                # ---- the p4 follow-up
                if chk.ckey in p4:
                    d = p4[chk.ckey]
                    row = {"ckey": chk.ckey, "rules": d["rules"], "tool": tool}
                    for rule, fct in REMINDER_RULES.items():
                        if rule in d["rules"]:
                            cands = MV.reminder_candidates(ctx, args.get("order_id"))
                            worded = [c for c in cands if REMINDER_WORDS.search(view.norm(c))]
                            row[fct] = {"part_a": vals.get(fct, {}).get("a"), "candidates": len(cands),
                                        "reminder_wording": len(worded),
                                        "example": view.text(worded[0])[:300] if worded else
                                        (view.text(cands[0])[:300] if cands else None)}
                    if set(d["rules"]) & LISTED_RULES:
                        fct = "consequential_action_details_listed"
                        cands = MV.listing_candidates(ctx, MV.call_key_ids(ctx))
                        items = [x for x in (args.get("item_ids") or []) + (args.get("new_item_ids") or [])]
                        with_items = [c for c in cands if any(MV.text_has_value(view.norm(c), i) for i in items)
                                      or any(MV.has_form(view.norm(c), f) for i in items
                                             for f in MV.shown_forms(ctx, i)[1:2])]
                        row[fct] = {"part_a": vals.get(fct, {}).get("a"), "candidates": len(cands),
                                    "candidates_naming_items": len(with_items),
                                    "example": view.text(cands[0])[:300] if cands else None}
                    p4_rows.append(row)
        if n_conv % 200 == 0:
            print(f"{n_conv} conversations, {C['checks']} checks, {time.time() - t0:.0f} s", flush=True)
    return {"C": C, "part_vals": part_vals, "problems": problems, "judge_cmp": judge_cmp, "added": added,
            "ident": ident, "airline_me": airline_me, "airline_me_bad": airline_me_bad, "obtained_bad": obtained_bad,
            "disc_rows": disc_rows, "owner_rows": owner_rows, "other_reply_rows": other_reply_rows,
            "screen_recall": screen_recall, "screen_miss": screen_miss, "p4_rows": p4_rows, "view_fail": view_fail,
            "n_conv": n_conv, "seconds": time.time() - t0, "literal_added": literal_added, "p6_overlay": {d: bool(p6[d]) for d in p6}}


# ----------------------------------------------------------------------------------------------- the screens

SCREEN_OF = {"K4": "other_person", "K5": "other_person", "K6": "health", "K8": "cancel", "K9": "delay",
             "K10": "compensation_request", "K12": "offer", "K16": "cancel"}
NO_SCREEN = {"K3": "every agent text after the order id first appears (reminder_candidates)",
             "K7": "every user message (user_messages)", "K11": "every user message (user_messages)",
             "K13": "the newest two user messages (retail) / every user message (airline)",
             "K14": "the pending reply (no screen)"}


def screen_sets(folder: str) -> dict:
    """Run the screens (message_view.SCREENS and SCREENS_RAW, through screen_text) on a constructed set
    <folder>/<K>.jsonl. A positive must hit (0 misses is the pass mark P7.5); a negative that hits costs one
    question. Topics without a screen ask every candidate message, so they cannot miss. K15 has no screen: its code
    part is the airport naming (a table code or city), reported here."""
    out = {}
    airports = MV._airports(None)
    for path in sorted(glob.glob(os.path.join(folder, "K*.jsonl")), key=lambda p: int(re.sub(r"\D", "", os.path.basename(p)))):
        k = os.path.splitext(os.path.basename(path))[0]
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        res = {"path": os.path.relpath(path, paths.PC_DIR), "sha256": sha256(path),
               "pos": sum(r["label"] == "pos" for r in rows), "neg": sum(r["label"] == "neg" for r in rows)}
        if k in MV.REMOVED_BY_SET3:
            res.update(screen=f"removed after set 3 ({MV.REMOVED_BY_SET3[k]}): asked on every candidate",
                       misses=[], neg_hits=res["neg"])
        elif k in SCREEN_OF:
            name = SCREEN_OF[k]
            hit = {r["id"]: MV.screen_text(name, r["text"]) for r in rows}
            res.update(screen=name, misses=[{"id": r["id"], "text": r["text"], "note": r.get("note")}
                                            for r in rows if r["label"] == "pos" and not hit[r["id"]]],
                       neg_hits=sum(1 for r in rows if r["label"] == "neg" and hit[r["id"]]))
        elif k == "K15":
            def names_airport(t: str) -> bool:
                pl, nt = MV.plain(t), MV.normalize(t)
                return any(MV._form_re(c, case=True).search(pl) or MV.has_form(nt, MV.normalize(city))
                           for c, city in airports.items())
            hit = {r["id"]: names_airport(r["text"]) for r in rows}
            res.update(screen="airport naming (code part, not a screen)",
                       misses=[{"id": r["id"], "text": r["text"]} for r in rows if r["label"] == "pos"
                               and not hit[r["id"]]],
                       neg_hits=sum(1 for r in rows if r["label"] == "neg" and hit[r["id"]]))
        else:
            res.update(screen="none: " + NO_SCREEN.get(k, "every candidate"), misses=[], neg_hits=res["neg"])
        out[k] = res
    return out


def write_screen_report(res: dict, folder: str) -> str:
    lines = [f"Screens on {os.path.relpath(folder, paths.PC_DIR)} (message_view.py sha256 "
             f"{sha256(MV.__file__)})", "", "| K | screen | pos | misses | neg | neg that hit (cost) |",
             "|---|---|---|---|---|---|"]
    for k, r in res.items():
        lines.append(f"| {k} | {r['screen']} | {r['pos']} | {len(r['misses'])} | {r['neg']} | {r['neg_hits']} |")
    for k, r in res.items():
        for m in r["misses"]:
            lines.append(f"- MISS {k} {m['id']}: {m['text'][:200]!r}")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------------------------- report

def main(argv: Optional[List[str]] = None) -> int:
    from state_tracker.v3.frozen import check_manifest
    check_manifest()
    ap = argparse.ArgumentParser(prog="python3 -B -m scoring.v3_p7_structure")
    ap.add_argument("--limit", type=int, default=None, help="only the first N development conversations")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--datasets", default=None, help="comma-separated data set names (default: all)")
    ap.add_argument("--screens", default=None, help="run only the screens on this constructed set folder")
    ap.add_argument("--from-details", action="store_true", help="write the report from the saved details file")
    a = ap.parse_args(argv)
    if a.from_details:
        write_report(load_details())
        return 0
    if a.screens:
        res = screen_sets(a.screens)
        print(write_screen_report(res, a.screens))
        out = os.path.join(paths.LOGS_DIR, "v3_p7_screens_" + os.path.basename(os.path.normpath(a.screens)) + ".json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, sort_keys=True)
            f.write("\n")
        return 0
    res = run(a.limit, a.datasets.split(",") if a.datasets else None)
    save_details(res)
    if not a.no_report:
        write_report(res)
    return 0


def _jsonable(x: Any) -> Any:
    if isinstance(x, collections.Counter):
        return [[list(k) if isinstance(k, tuple) else k, v] for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))]
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


COUNTERS = ("C", "part_vals", "problems", "judge_cmp", "airline_me", "screen_recall", "literal_added")


def load_details() -> dict:
    """The saved details, with the counters rebuilt (tuple keys from lists)."""
    with open(DETAILS, encoding="utf-8") as f:
        d = json.load(f)
    for k in COUNTERS:
        d[k] = collections.Counter({(tuple(x) if isinstance(x, list) else x): v for x, v in d.get(k) or []})
    return d


def save_details(res: dict) -> None:
    with open(DETAILS, "w", encoding="utf-8") as f:
        json.dump(_jsonable(res), f, indent=1, sort_keys=True, default=str)
        f.write("\n")


OWN_FILES = ("state_tracker/v3/message_view.py", "state_tracker/v3/info_classes.py",
             "output/eval_v3/p7_parts/exprs_retail.json", "output/eval_v3/p7_parts/exprs_airline.json",
             "output/eval_v3/p7_api.md", "tests/test_v3_message_view.py", "tests/test_v3_structure_facts.py",
             "scoring/v3_p7_structure.py")
SCREEN_SETS = ("set1", "set2", "set3")


DEFINITION_NOTES = [
    "1. **P7.2 wording.** \"Returns the task's user, 100 %\" cannot hold when the user's own typed email or name + zip "
    "matches nobody (tasks 54, 67, 107: `Error: user not found`). The identity fact is right there (the user did type "
    "the values) and no login happens. Proposed reading: never another user (0 here).",
    "2. **Listing candidates** (`consequential_action_details_listed`, the three confirmations): p5 says \"agent "
    "messages that name the call's key id (the order id)\". The agent's real listing often names the items, the "
    "payment or the address but not the order id again. The overlay uses `call_details()` (key ids, item ids, product "
    "names, the payment's shown forms, the reason, the new address). The literal reading's extra blocks are counted "
    "above.",
    "3. **Payment chosen, retail part b:** no key-id condition (as the airline part c), and the method may be named in "
    "L **or in the user's reply r** (\"yes, refund it to PayPal\"). Payment naming is negation-aware (\"not the "
    "Mastercard\" does not name the Mastercard); a balance (\"the $280 gift card\") or \"my card\" names a method "
    "when only one fits. The airline part b uses the same negation check as retail (not in its text; it is stricter).",
    "4. **Strict no:** \"No other items\", \"no more\", \"no, that's all\", \"nothing else\", \"no problem\" are "
    "not a no (they answer \"anything else?\"). A strict no makes a structure block, so it stays narrow; K1 decides "
    "the rest.",
    "5. **Names typed inside a user id** (\"my name is daiki_johnson_9523\") count as typed (letters-only values "
    "use '_' as a separator).",
    "6. **Disclosure token filter:** amounts (balances, prices) count only when a worked user-data tool output showed "
    "them (amounts repeat across many records); a value that is also catalog data (item id, price) counts only when a "
    "user-data output showed it and no catalog output did; a 4-digit number inside a date is a year. Every value a "
    "user-data output showed belongs to that output's user (so the user's own data is never another user's).",
    "7. **`me`** is registered with source `event` (p6's database part a of `request_is_for_another_user` needs it). "
    "Airline `me` = the first user id the user typed that exists in the database.",
    "8. **Reminder candidates** start where the order id first appears; a general reminder given before the order "
    "is named is not a candidate (1 + 1 added blocks above).",
    "9. **K4 at the first login** is always asked (p5 flag 2: no code key there).",
    "10. **The offer facts** (blocking value true) have no code key for \"no offer\": only the wide `offer` screen; "
    "its cost is that most replies with a `$` amount or 'sorry' ask K12.",
    "11. **Screens (P7.5):** blind set 1 had misses (K5 3, K6 4, K8 3, K9 9, K10 3, K16 6); the lists were widened; "
    "blind set 2 then had misses (K6 1, K9 3, K10 4); the lists were widened again. Blind set 3, run once unchanged, "
    "missed K5 2, K8 3, K9 1, K16 1: by the pre-registered rule those four topics lost their screens (asked on every "
    "candidate message); K4, K6, K10 and K12 keep theirs.",
    "12. **K15** has no word screen: its code part names airports by an upper-case code or the table's city; "
    "'NY', 'LA', 'San Fran', 'the Big Apple', 'Hawaii' are not found (the listing path d/e with K1 covers them).",
]


def _tbl(rows: List[List[Any]], head: List[str]) -> List[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return out


def write_report(res: dict) -> None:
    C = res["C"]
    L: List[str] = []
    L += ["# Tracker v3 part 7: text structure on the development data", "",
          f"Written by `scoring/v3_p7_structure.py` on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. "
          f"$0: no LLM call, no network. Development data only: {res['n_conv']:,} conversations, "
          f"{C['checks']:,} checks; {C['hold-out conversations skipped (not read)']} hold-out conversations skipped "
          f"before reading. Run time {res['seconds']:.0f} s (one process). Details: `output/logs/v3_p7_run_details.json`.",
          "", "Each structure part (p7's overlay) is evaluated **on its own** by the v3 evaluator, on the check's "
          "state and view. A fact's *structure value* is its `combine` with the other parts (p6, p8) unknown: it is "
          "the blocking value only when the structure parts alone force it.", ""]
    # P7.1
    eq, n = C["P7.1 conversations equal"], C["P7.1 conversations"]
    L += ["## P7.1 the view", "",
          f"- Whole conversations: the view rebuilt into messages equals the executed history (independent walk, "
          f"same characters): **{eq:,} / {n:,}**.",
          f"- Every check's prefix view equals the messages before it: **{C['P7.1 check prefixes equal']:,} / "
          f"{C['checks']:,}** (differs: {C['P7.1 check prefix differs']}).",
          f"- Checks whose history is over 24,000 characters (the judge's view was cut there; the view is not): "
          f"{C['checks whose history is over 24,000 characters (the judge' + chr(39) + 's view was cut; the view is not)']:,}."]
    for k, v in sorted(C.items()):
        if k.startswith("P7.1 notes: "):
            L.append(f"- Note ({v}): {k[12:]} (the text is not shown to the user; τ-bench sends only the call).")
    L.append("")
    # P7.2
    ident = res["ident"]
    true_rows = [i for i in ident if i["mine"] is True]
    tu = sum(1 for i in true_rows if i["gives_task_user"])
    nf = [i for i in true_rows if not i["gives_task_user"] and str(i["tool_output"]).startswith("Error")]
    other = [i for i in true_rows if not i["gives_task_user"] and not str(i["tool_output"]).startswith("Error")]
    L += ["## P7.2 identity", "",
          f"- Retail: identity fact true at {len(true_rows):,} login checks. τ-bench's own find_user_id_* on the "
          f"database copy with the call's values returns **the task's user in {tu:,}**, **another user in "
          f"{len(other)}**, and `Error: user not found` in {len(nf)}: the user typed values that match nobody "
          f"(tasks {sorted({i['ckey'].split('|')[1].split('/')[1] for i in nf})}; no login happens, so no wrong "
          f"identity). The pass mark's literal \"returns the task's user, 100 %\" is therefore "
          f"{'met' if not nf and not other else 'not met as worded'}: see the definition problems.",
          f"- Airline: `me` (the first user id the user typed that exists in the database), per conversation: "
          + ", ".join(f"{k} {v}" for k, v in sorted(res["airline_me"].items())) + ". `get_user_details` on the copy "
          f"gives no Error for every `me` (the id must exist to become `me`).",
          f"- Airline obtained ids (the user's words or a worked tool output) behind a true part: "
          + ", ".join(f"{k.split('(')[1][:-1]} {v}" for k, v in sorted(C.items()) if k.startswith("airline obtained"))
          + f"; not the task's user: **{len(res['obtained_bad'])}**.", ""]
    # P7.3
    disc = res["disc_rows"]
    cnt = collections.Counter((r["code"], r["raw_hits"] > 0) for r in disc)
    allow_hit = [r for r in disc if r["code"].startswith("allow") and r["raw_hits"]]
    L += ["## P7.3 disclosure (replies before login)", "",
          f"Raw scan (separate code, not the info classes): every string field of every user, order and payment "
          f"record (plus the records changed in the conversation), held by at most {RAW_MAX_USERS} users and not "
          f"catalog data, against the reply's tokens; values a user message holds are left out.", ""]
    L += _tbl([[k[0], "yes" if k[1] else "no", v] for k, v in sorted(cnt.items())],
              ["structure value", "raw scan finds a database value the user did not type", "replies"])
    L += ["", f"- Replies let through by code (part a false, part b false) that hold such a value: **{len(allow_hit)}**."]
    L += [f"  - {r['ckey']}: {r['hit_values']}" for r in allow_hit[:10]]
    L.append("")
    # P7.4
    own = collections.Counter((r["domain"], r["relation"]) for r in res["owner_rows"])
    bad_calls = [r for r in res["owner_rows"] if r["relation"] == "another user" and not r["ref_part_a"]]
    L += ["## P7.4 another user", "",
          "Owner of every call's object from the database (own code here): " + ", ".join(
              f"{d} {rel} {v:,}" for (d, rel), v in sorted(own.items())) + ".",
          f"- Calls on another user's object: {sum(v for (d, rel), v in own.items() if rel == 'another user')}; let "
          f"through: **{len(bad_calls)}**. Part a of `request_is_for_another_user` is p6's; p6's overlay present at "
          f"the run: {res['p6_overlay']}. A call before the first login has no `me` (part a is false then; the login "
          f"rules block those calls).", ]
    orr = res["other_reply_rows"]
    oc = collections.Counter((r["part_a"], r["raw_other_hits"] > 0) for r in orr)
    L += [f"- Replies after login (retail): raw scan finds a value held only by other users / part a of "
          f"`response_performs_task_for_another_user`: " + ", ".join(
              f"raw {'yes' if k[1] else 'no'} & part a {k[0]}: {v}" for k, v in sorted(oc.items(), key=str)) + ".",
          "  Values of the raw hits where part a is false: " + ", ".join(
              f"{v} {n}" for v, n in collections.Counter(x for r in orr if not r['part_a'] for x in r['values'])
              .most_common(15)) + ".", ""]
    # P7.6
    added = res["added"]
    disc_by = {r["ckey"]: r for r in disc}
    ident_by = {i["ckey"]: i for i in ident}
    L += ["## P7.6 blocks added (structure value = blocking value, judge's saved value = allowing value)", ""]
    rows = []
    for fct in IDENTITY_FACTS:
        xs = [a for a in added if a["fact"] == fct]
        with_reason = [a for a in xs if not ident_by.get(a["ckey"], {}).get("gives_task_user", True)]
        rows.append([fct, len(xs), len(with_reason), len(xs) - len(with_reason),
                     "τ-bench's tool on the copy does not give the task's user"])
    xs = [a for a in added if a["fact"] == DISCLOSURE]
    pre = [a for a in xs if a["ckey"] in disc_by]
    with_reason = [a for a in pre if disc_by[a["ckey"]]["raw_hits"] > 0]
    rows.append([DISCLOSURE + " (before login)", len(pre), len(with_reason), len(pre) - len(with_reason),
                 "the raw scan finds a database value the user did not type"])
    L += _tbl(rows, ["core fact", "added", "with an objective reason", "without", "reason"])
    L += ["", f"- Disclosure after login (rule 3 holds then, so no decision changes): {len(xs) - len(pre)} more.",
          "- Without a reason: " + (", ".join(a["ckey"] for a in added if a["fact"] in IDENTITY_FACTS and
                                               ident_by.get(a["ckey"], {}).get("gives_task_user", True)) or "none")]
    jc = res["judge_cmp"]
    L += ["", "Count against the judge (structure value vs the judge's saved value; None = not decided by structure "
          "alone, or the judge said unknown):", ""]
    L += _tbl([[f, m, j, v] for (f, m, j), v in sorted(jc.items()) if f in CORE],
              ["fact", "structure", "judge", "checks"])
    L += ["", "### The other structure facts: added blocks, labelled (not a pass mark)", ""]
    by = collections.defaultdict(list)
    for a in added:
        if a["fact"] not in CORE:
            by[a["fact"]].append(a)
    rows = []
    for fct, xs in sorted(by.items()):
        acc = sum(1 for a in xs if (a["tool_label"] or {}).get("accepted") is True)
        ref = sum(1 for a in xs if (a["tool_label"] or {}).get("accepted") is False)
        exp = sum(1 for a in xs if a["expected_action"])
        rows.append([fct, len(xs), acc, ref, len(xs) - acc - ref, exp,
                     sum(1 for a in xs if a["blocked_saved"])])
    L += _tbl(rows, ["fact", "added", "tool accepts", "tool refuses", "no label (reply / read)",
                     "equals an expected action", "the saved guard blocked it too"])
    lit = res.get("literal_added") or {}
    L += ["", "p5's literal candidates (the agent message must name the order id itself; payment pairs with the order "
          "id) would add: " + (", ".join(f"{k} {v}" for k, v in sorted(lit.items())) or "none") +
          " (the overlay uses `call_details()`: the listing may name the items, the payment or the address "
          "instead of the order id; and the payment may be named in the user's reply).", ""]
    # screens
    L += ["## P7.5 screens", "", "Development data: the screen holds on every check where the judge said true:", ""]
    L += _tbl([[k[0], k[1], k[2], v] for k, v in sorted(res["screen_recall"].items(), key=str)],
              ["fact", "screen", "hit", "checks"])
    L += [f"", f"Misses on development data: {len(res['screen_miss'])}.", ""]
    for name in SCREEN_SETS:
        folder = os.path.join(EVAL_V3, "p7_screen_sets", name)
        if os.path.isdir(folder):
            L += ["```", write_screen_report(screen_sets(folder), folder).rstrip(), "```", ""]
    before = os.path.join(paths.LOGS_DIR, "v3_p7_screens_set3_before_rule.json")
    if os.path.isfile(before):
        with open(before, encoding="utf-8") as f:
            s3 = json.load(f)
        L += ["### Set 3 (the pre-registered last run, 2026-10-23 06:40 UTC)", "",
              "Blind set 3 (`output/eval_v3/p7_screen_sets/set3/`) was run once with the lists unchanged "
              "(message_view.py sha256 `50882d986d72e20a221274ac492f1b6a11ac0e6cb0019592ff3bf38b012ceffa`). Rule "
              "(preregistration change log, 06:20): a topic with any miss loses its word screen; its tiny question is "
              "then asked on every candidate message, so no miss remains (P7.5 by construction; the cost goes into "
              "p8's dry run).", ""]
        L += _tbl([[k, r["screen"], r["pos"], len(r["misses"]), r["neg"], r["neg_hits"],
                    "removed" if k in MV.REMOVED_BY_SET3 else ("kept" if k in SCREEN_OF else "no screen")]
                   for k, r in s3.items()],
                  ["K", "screen", "pos", "misses", "neg", "neg that hit", "after the rule"])
        L += [""] + [f"- MISS {k} {m['id']}: {m['text'][:200]!r}" for k, r in s3.items() for m in r["misses"]]
        L += ["", "Screens removed: " + ", ".join(f"{k} ({v})" for k, v in MV.REMOVED_BY_SET3.items()) +
              ". Kept: K4 (other_person, catalog reads), K6 (health), K10 (compensation_request), K12 (offer). "
              "In code: the screens `cancel`, `delay` and `complaint` always hit, and `other_person_screen()` always "
              "holds. The development-data numbers above were run after the rule.", ""]
    # p4
    L += ["## The p4 follow-up (too-strict checks of output/eval_v3/p4_wrong.jsonl)", ""]
    for rule, fct in REMINDER_RULES.items():
        rr = [r[fct] for r in res["p4_rows"] if fct in r]
        L += [f"- `{fct}` ({rule}): {len(rr)} too-strict checks; structure part a true (a reminder candidate exists) "
              f"in {sum(1 for x in rr if x['part_a'] is True)}; a candidate with reminder wording (report-only word "
              f"list, never a value) in {sum(1 for x in rr if x['reminder_wording'])}; K3 still needed in "
              f"{sum(1 for x in rr if x['part_a'] is True)} (a screen never sets a value; code alone never makes "
              f"the reminder true); part a false (no agent text after the order id, so the block stays): "
              f"{sum(1 for x in rr if x['part_a'] is False)}."]
        for x in [x for x in rr if x["reminder_wording"]][:3]:
            L.append(f"  - example: {x['example'][:220]!r}")
    rr = [r["consequential_action_details_listed"] for r in res["p4_rows"]
          if "consequential_action_details_listed" in r]
    L += [f"- `consequential_action_details_listed`: {len(rr)} too-strict checks; part a true in "
          f"{sum(1 for x in rr if x['part_a'] is True)}; a candidate also names the call's items (id or product name) "
          f"in {sum(1 for x in rr if x['candidates_naming_items'])}; K2 decides the rest."]
    for x in rr[:2]:
        if x["example"]:
            L.append(f"  - example: {x['example'][:220]!r}")
    L.append("")
    # part values
    L += ["## Part values (development data, each part on its own)", ""]
    pv = collections.defaultdict(dict)
    for (d, f, p_, v), n_ in res["part_vals"].items():
        pv[(d, f, p_)][v] = n_
    L += _tbl([[d, f, p_, v.get("True", 0), v.get("False", 0),
                sum(n_ for k, n_ in v.items() if k not in ("True", "False"))] for (d, f, p_), v in sorted(pv.items())],
              ["domain", "fact", "part", "true", "false", "problem (blocking value, counted)"])
    L += ["", "Problems: " + (", ".join(f"{k} {v}" for k, v in sorted(res["problems"].items())) or "none"), ""]
    L += ["## Definition problems and reading choices (for the main chat)", ""]
    L += DEFINITION_NOTES
    L += ["", "## Files", ""]
    L += _tbl([[f, sha256(os.path.join(paths.PC_DIR, f))] for f in OWN_FILES], ["file", "sha256"])
    L += ["", "Rerun: `PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 python3 -B -m scoring.v3_p7_structure > "
          "output/logs/v3_p7_<nn>_run.log 2>&1`; screens only: `... --screens output/eval_v3/p7_screen_sets/set1`.", ""]
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
