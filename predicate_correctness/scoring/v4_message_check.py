"""Tracker v4: the checks of the block messages. A COPY of scoring/v3_message_check.py (tracker v3, part 10); the diff
is the audit object (docs/planning/tracker_v4/code_change_map.md section 1.3, the v4_message_check.py row). $0: no LLM
call, no network.

What changes against v3:
  - the guard is guard/tgr_tracker_v4.py (TrackerTGRv4, built with meaning = saved_judge, messages = rule,
    require_freeze = False) and the builder is guard/feedback_v4.py; the fact definitions are the v4 fact files;
  - P10.1 also parses the v4 lines: the missing lines ("Not stated in your listing: the order id #W2806889.",
    "Not stated: the card. The call uses <id> (<brand>, last four <n>; ...).", "Your listing says '<words>' but
    ...") and the v4 advice (K1 go-ahead ask, payment ask, listing, clash, K3 reminder, K6 / K7 ask why, K13 / K16
    tools, K17 insurance). A value of a missing line must be a value of the call or of the own database records of
    the call's objects; a card's brand and last four must equal the own database; a quoted listing must be in an
    agent message; a named tool must be a real tool of the domain; the transfer line (predicate_table.md's "Do not
    transfer yet: the user's request (...) can be done with <tool>. ...") must quote a user message;
  - two new pass marks:
      P10.9  every block names a line the agent can fix in one turn: every advice line is a concrete one (a
             look-up, a call with the user's details, an exact sentence to ask, a clash with both values, the tools
             line, "not possible", user only, the user said no, change the call) and a listing line comes with at
             least one missing line; v3's generic "Do this step first, so that this becomes true: <fact>" and "Ask the
             user (the policy tells you to): <fact>" lines fail it (fixable_line_problems);
      P10.10 no expected value leaks: no missing line (or clash line) shows a value before login (own `me`), and the
             raw scan finds no value of another user in one (missing_leaks);
  - outputs: output/eval_v4/message_check_v4.md and output/logs/v4_message_check_details.json;
  - the data: only the 200 v3 development conversations (the p12a set: the first 50 of each of the 4 strong-agent
    development data sets, DEV_DATASETS / DEV_LIMIT), as scoring/v4_offline_eval.py; wider data is refused.
Everything else (P10.2-P10.8, the own database, the raw scan, the population) is v3's, unchanged. The
rest of this text is v3's.

The facts at each check come from p9's guard (guard/tgr_tracker_v3.py: facts = v3, meaning = saved_judge, the
offline stand-in; lazy, as p9 runs it) through the offline base (fork/offline_v3.py run_guard), with the saved judge
values of the check. A small subclass keeps, at each block, exactly what p9's _feedback passes to
guard/feedback_v3.py (tool, args, violated rules, the evaluator's results, the state, the view). Development data
only: the two hold-out data sets are never opened, and a Stage B try forked from a val conversation is skipped before
any check of it is read.

Population: every check whose saved decision is "block" (the saved blocks; the pass marks), and, with --all, every
development check (the v3 blocks at saved allows are then reported apart). At every v3 block the guard runs three
times, messages = frozen, rule and simple (p9's switch), and the checks below run on the rule message and on the
simple message (p9's simple text; guard/feedback_v3.py build_simple is also built and measured).

The checks (separate code here, not the builder's):
  P10.1 values: every line of the rule message is parsed; each value is checked against its source with code of this
        file: database lines by an own database (τ-bench's data loaded by its own loader, every executed call of the
        history replayed with τ-bench's own tool code, in order) and an own few-line reader; event lines by an own
        event log (the history's tool calls and outputs); argument lines by the call; fact lines by the guard's
        values; the policy line by the rule set; a quote by the user's message. A line that matches no pattern is a
        failure. Simple: its "name = value" lines against the guard's values;
  P10.2 steps: a look-up step: the tool and its argument are in τ-bench's tool schemas, and the call runs on a copy
        of the own database with no Error; a step with the user's details: tool and argument names equal the
        schema's (required parameters); message steps name no tool (counted);
  P10.3 "not possible": for the facts τ-bench's tool decides (p3: state_tracker/v3/tool_check.py), a fact of the
        message is "not possible" exactly when the tool refuses on it;
  P10.4 leaks: a raw scan, not the info classes: every string field of every user, order and reservation record
        (τ-bench's data, plus the records the conversation's calls touched, from the own database) against the
        message's tokens; a value held by at most RAW_MAX_USERS users, not catalog data, not typed by the user, not
        in the call's arguments and not in the policy is a hit. Before login (`me`, own few lines) a hit is a leak;
        after login a hit that `me` does not hold is another user's data;
  P10.5 no user_only fact offered as a step (the builder's plan, whose text equals the message): the fact of every
        step line has no user_only part (part who, else fact who) that is not true. Simple: TGR's "Not established
        yet (...): ..." lines for such a fact are counted too;
  P10.6 decisions: frozen, rule and simple give the same decision, margin, violated rules, mln record, unknown
        predicates and values (100 % equal);
  P10.7 fallbacks: the guard's message fallbacks, and the builder's own call on the same inputs (it must give the
        same text, no exception): 0;
  P10.8 closing: no "Do not repeat ..." when every violated rule has a flip set (rule table) whose facts can each
        be made true by agent / ask parts (own computation from the fact definitions and the guard's part values;
        a database or arguments part without its own who is none) and the user's latest message is not a strict no
        (message_view.is_strict_no);
  (9) length: characters of the frozen, rule and simple messages (reported only).
Also counted: the advice class and the closing per block; the judge's saved evidence and the rule set's predicate
descriptions in a rule message (0 expected).

Run from predicate_correctness/ (the venv Python, the hash seed fixed):
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v4_message_check \\
        [--all] [--limit N] > output/logs/v4_message_check_<nn>.log 2>&1
main() first calls state_tracker.v3.frozen.check_manifest(). Writes output/eval_v4/message_check_v4.md and
output/logs/v4_message_check_details.json. Imports no other scoring module and no gold code.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import os
import re
import statistics
import sys
import time
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from fork import offline_v3 as O                                          # noqa: E402  (sets up the runner path)
from state_tracker import paths                                           # noqa: E402
from state_tracker import state as S                                      # noqa: E402
from state_tracker import tau_copy                                        # noqa: E402

OUT_MD = os.path.join(paths.OUTPUT_DIR, "eval_v4", "message_check_v4.md")
OUT_JSON = os.path.join(paths.LOGS_DIR, "v4_message_check_details.json")
HOLDOUT_DATASETS = ("ours.p10_luna_val", "partner.luna_val")
# v4 purity (overview.md §3-4, build_brief.md rule 3): only the 200 v3 development conversations (the p12a set, as
# scoring/v4_offline_eval.py and scoring/v3_p12_offline.select_conversations("dev") use): the first 50 conversations
# of each of the 4 strong-agent development data sets. v3's wider default (every non-hold-out data set: the nano
# runs, all of each set, and stage_b, whose try files include forks of hold-out conversations) is refused.
DEV_DATASETS = ("stage_a.luna.tgr_frozen", "stage_a.luna.tgr_tracker", "ours.p10_luna_train", "partner.luna_train_v5")
DEV_LIMIT = 50
OWN_FILES = ("guard/feedback_v4.py", "tests/test_v4_feedback.py", "scoring/v4_message_check.py")
K_P109 = "P10.9 blocks that do not name a line the agent can fix in one turn"
K_P1010 = "P10.10 blocks with an expected value that leaks"
MODES = ("frozen", "rule", "simple")
RAW_MAX_USERS = 20
MAX_EXAMPLES = 25
COUNT: collections.Counter = collections.Counter()          # LLM / judge calls seen (0)
K_LOGIN = "P10.2 steps with the user's details"
K_P108 = "P10.8 'do not repeat' although a step can fix it"
K_JUDGE = "rule messages quoting the judge's saved evidence"
K_LENIENT = "closing 'call again' although no step can fix it (not a pass mark)"
K_TEXTDIFF = "P10.7 builder text differs from the guard's message"


def say(msg: str) -> None:
    print(msg, flush=True)


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def jtext(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


# ----------------------------------------------------------------------------------------------- safety
def install_safety() -> None:
    """TGR's own LLM judge and the runner's structured LLM call are refused (counted); the network is blocked."""
    from method_tgr import llm as tgr_llm                                 # runner copy
    from method_tgr import runtime as RT
    from state_tracker.v3 import questions as Q

    def judge(self, *a, **k):
        COUNT["TGR._judge (LLM judge) calls"] += 1
        raise AssertionError("TGR's LLM judge was called")

    def structured(*a, **k):
        COUNT["LLM calls"] += 1
        raise AssertionError("an LLM call was attempted")

    RT.TGR._judge = judge
    tgr_llm.structured = structured
    RT.llm.structured = structured
    Q.block_network()


# ----------------------------------------------------------------------------------------------- own database
_BASE: Dict[str, dict] = {}


def base_data(domain: str) -> dict:
    """τ-bench's data at the start of a conversation, by τ-bench's own loader (the copied data/__init__.py)."""
    if domain not in _BASE:
        _BASE[domain] = tau_copy.load_data_fresh(domain)
    return _BASE[domain]


class OwnDB:
    """τ-bench's data plus every executed call of the history, replayed in order with τ-bench's own tool code
    (Tool.invoke on the data, as Env.step does). Not state.py."""

    def __init__(self, domain: str, executed: List[dict]):
        self.domain, self.executed = domain, executed
        self.db: Optional[dict] = None
        self.i = 0
        self.calls: Dict[str, Tuple[str, dict]] = {}
        self.tools = tau_copy.tools(domain)

    def at(self, history: List[dict]) -> dict:
        n = len(history)
        if self.db is None or n < self.i or any(history[k] is not self.executed[k] for k in (0, n - 1) if k < n):
            self.db, self.i, self.calls = copy.deepcopy(base_data(self.domain)), 0, {}
        while self.i < n:
            m = self.executed[self.i]
            if m.get("role") == "assistant":
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    a = fn.get("arguments")
                    try:
                        a = a if isinstance(a, dict) else json.loads(a or "{}")
                    except ValueError:
                        a = None
                    self.calls[tc.get("id")] = (fn.get("name"), a)
            elif m.get("role") == "tool":
                name, a = self.calls.pop(m.get("tool_call_id"), (None, None))
                if name in self.tools and isinstance(a, dict):
                    try:
                        self.tools[name].invoke(data=self.db, **copy.deepcopy(a))
                    except Exception:  # noqa: BLE001 - τ-bench's Env turns it into an Error text
                        pass
            self.i += 1
        return self.db


TABLES = {"user": "users", "order": "orders", "reservation": "reservations", "product": "products",
          "flight": "flights"}
NESTED = {"payment_method": ("users", "payment_methods", "user_id"), "variant": ("products", "variants", "product_id")}
_MISSING = object()


def own_record(db: dict, kind: str, oid: str) -> Any:
    """The record of a kind and id in the own database (nested kinds with their parent's id added), or _MISSING."""
    if kind in TABLES:
        return db[TABLES[kind]].get(oid, _MISSING)
    if kind in NESTED:
        table, field, parent = NESTED[kind]
        for pid, p in db[table].items():
            sub = p.get(field) or {}
            if oid in sub:
                return dict(sub[oid], **{parent: pid})
    return _MISSING


def own_read(x: Any, path: List[Any]) -> Any:
    for k in path:
        if isinstance(x, dict) and k in x:
            x = x[k]
        elif isinstance(x, list) and isinstance(k, int) and 0 <= k < len(x):
            x = x[k]
        else:
            return _MISSING
    return x


_PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def parse_path(text: str) -> List[Any]:
    out: List[Any] = []
    for name, idx in _PATH_TOKEN.findall(text):
        out.append(int(idx) if idx else name)
    return out


# ----------------------------------------------------------------------------------------------- own event log, me
def failed(out: Any) -> bool:
    return not isinstance(out, str) or out.startswith("Error") or out.startswith("Unknown action")


def own_events(history: List[dict]) -> List[dict]:
    """The executed calls of the history with their outputs: {tool, args, ok, output}."""
    calls, out = {}, []
    for m in history:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                a = fn.get("arguments")
                try:
                    a = a if isinstance(a, dict) else json.loads(a or "{}")
                except ValueError:
                    a = {}
                calls[tc.get("id")] = (fn.get("name"), a)
        elif m.get("role") == "tool":
            name, a = calls.pop(m.get("tool_call_id"), (m.get("name"), {}))
            out.append({"tool": name, "args": a, "ok": not failed(m.get("content")), "output": m.get("content")})
    return out


def rnorm(text: Any) -> str:
    t = unicodedata.normalize("NFKD", text if isinstance(text, str) else json.dumps(text))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("’", "'").replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", t).strip()


_UID = re.compile(r"(?<![a-z0-9_])[a-z]+(?:_[a-z]+)*_\d{3,}(?![a-z0-9_])")


def own_me(domain: str, history: List[dict], db: dict) -> Optional[str]:
    """retail: the output of the first worked find_user_id_* call; airline: the first user id a user message holds
    that is a user of the database."""
    if domain == "retail":
        for e in own_events(history):
            if e["tool"] in ("find_user_id_by_email", "find_user_id_by_name_zip") and e["ok"] and e["output"].strip():
                return e["output"].strip()
        return None
    for m in history:
        if m.get("role") == "user":
            for uid in _UID.findall(rnorm(m.get("content") or "")):
                if uid in db["users"]:
                    return uid
    return None


def user_texts(history: List[dict]) -> List[str]:
    return [rnorm(m.get("content") or "") for m in history if m.get("role") == "user"]


# ----------------------------------------------------------------------------------------------- own raw scan
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


def _tokens(norm: str) -> List[str]:
    toks = []
    for t in re.split(r"[\s\"'(),;:!?\[\]{}<>]+", norm):
        t = t.strip(".-")
        if t:
            toks.append(t)
    return toks


def _grams(norm: str, n: int = 6) -> set:
    toks = _tokens(norm)
    out = set()
    for i in range(len(toks)):
        for k in range(1, n + 1):
            if i + k <= len(toks):
                out.add(" ".join(toks[i:i + k]))
    return out


def _value_forms(s: str) -> List[str]:
    v = " ".join(_tokens(rnorm(s)))
    forms = [v] if v else []
    m = re.fullmatch(r"(?:gift_card|credit_card|paypal|certificate)_(\d+)", v)
    if m:
        forms += [m.group(1), m.group(1)[-4:]]
    if v.startswith("#w"):
        forms.append(v[1:])
    return forms


class RawScan:
    """value (normalized) -> the users whose user / order / reservation records hold it; catalog values apart."""

    def __init__(self, domain: str):
        db = base_data(domain)
        self.owners: Dict[str, set] = collections.defaultdict(set)
        cat: List[str] = []
        _strings(db.get("products", {}), cat)
        _strings(db.get("flights", {}), cat)
        self.catalog = {f for s in cat for f in _value_forms(s)}
        for uid, u in db.get("users", {}).items():
            self.add(uid, u)
            self.owners[uid.lower()].add(uid)
        for o in db.get("orders", {}).values():
            self.add(o.get("user_id"), o)
        for r in db.get("reservations", {}).values():
            self.add(r.get("user_id"), r)
        pol: List[str] = [tau_copy.policy_text(domain)]
        rs = json.load(open(paths.rule_set_path(domain), encoding="utf-8"))
        pol += [s["text"] for s in rs.get("sentences") or []]
        self.policy = set()
        for t in pol:
            self.policy |= _grams(rnorm(t))

    def add(self, uid: Any, rec: Any, into: Optional[Dict[str, set]] = None) -> None:
        if not isinstance(uid, str):
            return
        vals: List[str] = []
        _strings(rec, vals)
        tgt = self.owners if into is None else into
        for s in vals:
            for f in _value_forms(s):
                if len(f) >= 3:
                    tgt.setdefault(f, set()).add(uid)

    def hits(self, text: str, typed: List[str], arg_strings: set, extra: Dict[str, set]) -> List[dict]:
        grams = _grams(rnorm(text))
        typed_grams = set()
        for t in typed:
            typed_grams |= _grams(t)
        out = []
        for g in grams:
            users = set(self.owners.get(g, set())) | set(extra.get(g, set()))
            if not users or len(users) > RAW_MAX_USERS or g in self.catalog or g in self.policy:
                continue
            if g in typed_grams or g in arg_strings or g.lstrip("#") in typed_grams:
                continue
            out.append({"value": g, "users": sorted(users)})
        return out


def arg_strings(args: Any) -> set:
    out: List[str] = []
    _strings(args, out)
    if isinstance(args, dict):
        for v in args.values():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.append(str(v))
    return {f for s in out for f in _value_forms(s)} | {g for s in out for g in _grams(rnorm(s))}


def touched_records(domain: str, history: List[dict], db: dict, scan: RawScan, args: dict) -> Dict[str, set]:
    """The records the conversation's calls touched (ids in their arguments and outputs), from the own database."""
    extra: Dict[str, set] = {}
    ids = set()
    for e in own_events(history):
        for k in ("order_id", "reservation_id", "user_id"):
            v = (e["args"] or {}).get(k)
            if isinstance(v, str):
                ids.add((k, v))
        if e["ok"] and isinstance(e["output"], str) and e["output"][:1] == "{":
            try:
                d = json.loads(e["output"])
            except ValueError:
                d = None
            if isinstance(d, dict):
                for k in ("order_id", "reservation_id", "user_id"):
                    if isinstance(d.get(k), str):
                        ids.add((k, d[k]))
    for k, v in ids:
        table = {"order_id": "orders", "reservation_id": "reservations", "user_id": "users"}[k]
        rec = db.get(table, {}).get(v)
        if rec is not None:
            scan.add(v if k == "user_id" else rec.get("user_id"), rec, extra)
    return extra


# ----------------------------------------------------------------------------------------------- the guard
_G = None


def guard_module():
    global _G
    if _G is None:
        from guard import tgr_tracker_v4 as G
        _G = G
    return _G


# v4: no pinned table. The v4 guard runs V3.check_frozen_v3() itself (the v3 files are frozen) and its own freeze
# check (require_freeze = False here: the message check runs before the freeze).
OVERRIDES: Dict[str, Dict[str, str]] = {}


def build_guard(domain: str) -> Any:
    """The v4 guard of a domain as the message check runs it: meaning = saved_judge (the offline stand-in), messages =
    rule, lazy (as the live guard), require_freeze = False."""
    G = guard_module()
    return G.build(domain, meaning="saved_judge", messages="rule", require_freeze=False)


def capture_class():
    G = guard_module()

    class Capture(G.TrackerTGRv4):
        """the v4 guard; _feedback also keeps the inputs its rule message gets."""

        def _feedback(self, step, a_text, violated, current, judged, meter, rec):
            text = super()._feedback(step, a_text, violated, current, judged, meter, rec)
            d = self._v3tls.data
            if d is None:
                d = self._message_data(step)
            self.captured = {"violated": copy.deepcopy(violated), "data": d, "text": text,
                             "message": dict(self._v3tls.message or {})}
            return text

    return Capture


class Walk:
    """The guard's offline state_source for one conversation (one state.Tracker fed along the executed messages; a
    history that is not a prefix gets build_state). The same reading as the guard's own build_state."""

    def __init__(self, conv: O.SavedConversation):
        self.executed, self.domain = conv.ep["executed"], conv.domain
        self.tr = S.Tracker(conv.domain)
        self.i = 0

    def __call__(self, history: List[dict], tool: str, args: Dict[str, Any]) -> Any:
        n = len(history)
        if not (self.i <= n <= len(self.executed) and all(history[k] is self.executed[k] for k in range(n))):
            COUNT["walk: build_state (not a prefix)"] += 1
            return S.build_state(history, {"tool": tool, "args": args}, domain=self.domain)
        while self.i < n:
            self.tr.feed_message(self.executed[self.i])
            self.i += 1
        if self.tr._open:
            COUNT["walk: build_state (open call)"] += 1
            return S.build_state(history, {"tool": tool, "args": args}, domain=self.domain)
        st = self.tr.state
        st.pending = S.normalize_action({"tool": tool, "args": args})
        return st


# ----------------------------------------------------------------------------------------------- parsing the message
R_FACT = re.compile(r"^- (?P<words>.+): (?P<shown>true|false|not established)$")
R_EVENT = re.compile(r"^(?P<tool>[a-z_]+) with (?P<key>[a-z_]+) (?P<val>.+): not done before this call$")
R_NOEVENT = re.compile(r"^a (?P<tools>[a-z_]+(?: or [a-z_]+)*) call that worked: none yet$")
R_HAS = re.compile(r"^(?P<kind>[a-z_]+) (?P<id>\S+): (?P<path>\S+) has (?P<key>.+): (?P<yn>yes|no)$")
R_GET = re.compile(r"^(?P<kind>[a-z_]+) (?P<id>\S+): (?P<path>\S+) = (?P<val>.+)$")
R_MISS = re.compile(r"^(?P<kind>[a-z_]+) (?P<id>\S+): not in the database$")
R_ARG = re.compile(r"^the call's (?P<key>[a-z_]+) = (?P<val>.+)$")
R_ARGN = re.compile(r"^the call's (?P<key>[a-z_]+): (?P<n>\d+) entries$")
R_ITEM = re.compile(r"^(?P<n>\d+)\. (?P<text>.+)$")
R_SUB = re.compile(r"^   (?P<l>[a-z])\) (?P<text>.+)$")
A_LOOKUP = re.compile(r"^Do this step first: look it up with (?P<tool>[a-z_]+) \((?P<key>[a-z_]+) (?P<val>.+)\)\. "
                      r"Then try again\.$")
A_LOGIN = re.compile(r"^Do this step first: call (?P<calls>.+) with details the user gives you; the call must work\. "
                     r"Then try again\.$")
A_CALL = re.compile(r"^(?P<tool>[a-z_]+) \((?P<args>[a-z_, ]*)\)$")
A_STEP = re.compile(r"^Do this step first, so that this becomes true: (?P<words>.+)\. Then try again\.$")
A_CHANGE = re.compile(r"^Change your (?:call|message) so that this is no longer true: (?P<words>.+)\.$")
A_ASK = re.compile(r"^(?:Ask|Do this step first, then ask) the user \(the policy tells you to\): (?P<words>.+)\. "
                   r"If the user says yes, try again\. If the user says no, do not do it\.$")
A_ASKNEG = re.compile(r"^Ask the user \(the policy tells you to\) about this, and change your (?:call|message) so that "
                      r"this is no longer true: (?P<words>.+)\.$")
A_ASKNO = re.compile(r"^The user said no \(\"(?P<quote>.*)\"\)\. Do not do it: (?P<words>.+)\.$")
A_SAIDNO = re.compile(r"^The user said no \(\"(?P<quote>.*)\"\)\.$")
A_NONE = re.compile(r"^Not possible with (?:these arguments|this message): (?P<words>.+) is "
                    r"(?P<shown>true|false|not established)\.$")
A_USERONLY = re.compile(r"^This depends only on what the user says \((?P<words>.+)\)\. Do not lead the user to say "
                        r"it\. Without it, this action is not allowed\.$")
SIMPLE_FACT = re.compile(r"^    (?P<name>[a-z_]+) = (?P<v>true|false|not established): ")
SIMPLE_TODO = re.compile(r"^- Not established yet \((?P<names>[a-z_, ]+)\): ")
# v4 lines
R_MISS_PAY = re.compile(r"^Not stated: the (?P<line>.+?)\. The call uses (?P<pid>(?:credit_card|gift_card|paypal|"
                        r"certificate)_\d+)(?: \((?P<inner>[^()]*)\))?(?P<amount>, \$[\d.,]+)?\.$")
R_MISS_LINE = re.compile(r"^Not stated in your listing: the (?P<rest>.+)\.$")
R_SAID = re.compile(r"^Your listing says '(?P<said>.*)' but the (?P<rest>.+)\.$")
R_SAID_HIDDEN = re.compile(r"^Your listing says '(?P<said>.*)', which does not match the (?P<line>.+) of this call\.$")
A_GO = re.compile(r"^Ask: 'Shall I go ahead with (?P<action>.+)\? Please reply yes or no\.'$")
A_PAYASK = re.compile(r"^Ask: '(?P<q>Which (?:gift card or credit card|payment method) .+\?)'$")
A_LISTING = re.compile(r"^List the (?:missing details above|details of this call \(every value it changes\)) in one "
                       r"message to the user, then ask for a yes\. Then try again\.$")
A_CLASH = re.compile(r"^The user named '(?P<said>.*)' but the call uses (?P<val>.+)\. Ask the user which one they "
                     r"want\.$")
A_CLASH_HIDDEN = re.compile(r"^A user message after your listing names another .+ than the call(?: \(.+\))?\. Ask the "
                            r"user which one they want\.$")
A_REMIND = re.compile(r"^Before this (?:exchange|change), ask the user: 'Are (?P<items>.+) all the items you want to "
                      r"(?:exchange|modify) in order (?P<oid>\S+)\? (?:An exchange|This) can be done only once\.'$")
A_WHY = re.compile(r"^Ask the user why they want to cancel reservation (?P<rid>\S+?)(?: \(change of plan, the airline "
                   r"cancelled the flight, or another reason\)\.|\. Do not suggest a reason\.)$")
# the transfer line, predicate_table.md's wording: "Do not transfer yet: the user's request ("<newest request>") can be
# done with <tool>. Do it, or deny it if the policy forbids it." (no tool found: "your tools")
A_TOOLS = re.compile(r"^Do not transfer yet: the user's request(?: \(\"(?P<quote>.*)\"\))? can be done with "
                     r"(?:(?P<tools>[a-z_]+(?:, [a-z_]+)*)|your tools)\. Do it, or deny it if the policy forbids it\.$")
A_INS = re.compile(r"^Ask: 'Would you like travel insurance for this booking\? Please reply yes or no\.' The call says "
                   r"insurance = (?P<v>.+)\.$")
# the line names of state_tracker/v4/listing_v4.py (line_specs_v4), written out here (not imported): longest first
LINE_NAMES = ("order id", "reservation id", "cancel reason", "flight", "cabin", "passenger", "checked bags",
              "paid bags", "travel insurance", "certificate amount", "new payment method",
              "payment method for the price difference", "refund method", "payment method", "item", "returned item",
              "street (line 1) of the new address", "line 2 of the new address", "city of the new address",
              "state of the new address", "zip of the new address", "card", "gift card", "PayPal", "certificate")
V4_ADVICE = (A_GO, A_PAYASK, A_LISTING, A_CLASH, A_CLASH_HIDDEN, A_REMIND, A_WHY, A_TOOLS, A_INS)
# P10.9: advice lines that name something the agent can do in one turn (a listing line also needs a missing line)
CONCRETE_TYPES = ("lookup", "user_args_call", "go_ahead", "ask_payment", "clash", "reminder", "ask_why",
                  "ask_why_insured", "tools", "insurance", "none", "user_only", "ask_no", "said_no", "change")


def fixable_line_problems(plan: dict, FB: Any) -> List[str]:
    """P10.9: why a block does not name a line the agent can fix in one turn (empty: it does). Every advice line must
    be a concrete one (CONCRETE_TYPES); a listing line needs at least one missing line of its fact; v3's generic
    "step" / "ask" lines (only the fact's words) fail."""
    out: List[str] = []
    lines = FB.advice_lines(plan["advice"])
    if not lines:
        out.append("no advice line")
    ev = {nm["fact"]: nm["evidence"] for nm in plan["not_met"]}
    for a in lines:
        t = a["type"]
        if t == "listing":
            if not any(e.get("type") == "missing" for e in ev.get(a["fact"]) or []):
                out.append(f"listing line without a missing line: {a['fact']}")
        elif t not in CONCRETE_TYPES:
            out.append(f"generic {t} line: {a['fact']}")
    return out


def missing_leaks(plan: dict, text: str, me: Optional[str], scan: Any, typed: List[str], argset: set,
                  extra: Dict[str, set], FB: Any) -> List[dict]:
    """P10.10: the missing lines and clash lines of a block that show a value before login (own `me`), or whose raw
    scan finds a value that `me` does not hold (another user's). Also a line of the plan that is not in the text."""
    out: List[dict] = []
    shown: List[str] = []
    for nm in plan["not_met"]:
        for e in nm["evidence"]:
            if e.get("type") == "missing" and (e.get("value") or e.get("of")):
                shown.append(e["text"])
    for a in FB.advice_lines(plan["advice"]):
        if a.get("type") == "clash" and a.get("value"):
            shown.append(a["text"])
    for t in shown:
        if t not in text:
            out.append({"why": "line of the plan not in the text", "line": t[:120]})
        if me is None:
            out.append({"why": "value before login", "line": t[:120]})
            continue
        bad = [h for h in scan.hits(t, typed, argset, extra) if me not in h["users"]]
        if bad:
            out.append({"why": "another user's value", "line": t[:120], "hits": [h["value"] for h in bad][:5]})
    return out


def call_records(domain: str, args: dict, db: dict, me: Optional[str]) -> List[Any]:
    """The own database records a missing line's value may come from: the call's order / reservation / user, `me`,
    the variants, products and flights the call names."""
    recs: List[Any] = [args]
    for k, kind in (("order_id", "order"), ("reservation_id", "reservation"), ("user_id", "user")):
        if isinstance(args.get(k), str):
            recs.append(own_record(db, kind, args[k]))
    if me:
        recs.append(own_record(db, "user", me))
    ids: List[str] = []
    _strings(args, ids)
    for i in ids:
        v = own_record(db, "variant", i) if "products" in db else _MISSING
        if v is not _MISSING:
            recs.append(v)
            recs.append(own_record(db, "product", v.get("product_id")))
        f = own_record(db, "flight", i) if "flights" in db else _MISSING
        if f is not _MISSING:
            recs.append(f)
    for fl in args.get("flights") or []:
        if isinstance(fl, dict) and isinstance(fl.get("flight_number"), str) and "flights" in db:
            recs.append(own_record(db, "flight", fl["flight_number"]))
    return [r for r in recs if r is not _MISSING]


def value_in_records(value: str, recs: List[Any]) -> bool:
    """Every piece of the value (split at ' (', ':', ';', ',', '→', ' or ', ' on ', ' in total') is a value of the
    records (normalized; a piece of 2+ characters inside a record string counts; a '$' amount must be a number of the
    records); filler words ('item', 'the new', 'last four', 'added', 'not added') are dropped."""
    strs: List[str] = []
    for r in recs:
        _strings(r, strs)

    def nums(x: Any) -> None:
        if isinstance(x, dict):
            for v in x.values():
                nums(v)
        elif isinstance(x, list):
            for v in x:
                nums(v)
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            strs.append(str(x))
            if float(x).is_integer():
                strs.append(str(int(x)))
    for r in recs:
        nums(r)
    norm = [rnorm(s) for s in strs]
    pieces = re.split(r" \(|\)|:|;|,|→| or | on | in total| paid| added", rnorm(value))
    for p in pieces:
        p = re.sub(r"^(?:the new |the |item |last four |also counts|')", "", p.strip()).strip(" .'$")
        p = re.sub(r"^(?:item |last four )", "", p).strip()
        if len(p) < 2 or p in ("not", "also counts", "ending in", "the user may call it"):
            continue
        if p.startswith("ending in "):
            continue
        if any(p == s or p in s or s.replace("_", " ") == p for s in norm):
            continue
        # an option piece ("color black"): each word is a value or a key of the records
        keys: List[str] = []
        for r in recs:
            _keys(r, keys)
        pool = norm + [rnorm(k) for k in keys]
        if not all(any(w == s or w in s for s in pool) for w in p.split() if len(w) >= 2):
            return False
    return True


def _keys(x: Any, out: List[str]) -> None:
    if isinstance(x, dict):
        for k, v in x.items():
            if isinstance(k, str):
                out.append(k)
            _keys(v, out)
    elif isinstance(x, list):
        for v in x:
            _keys(v, out)


def split_advice(text: str) -> List[str]:
    return text.split(" And: ")


def shown_of(res: dict) -> str:
    """How a fact's value must be shown: an unknown, a lazily skipped fact or an unclear answer is not
    established."""
    v = res.get("value")
    parts = res.get("parts") or {}
    no_part = (res.get("how") == "blocking_value" and bool(parts)
               and all((p or {}).get("how") not in ("value", "nonexistent", "problem") for p in parts.values()))
    if (v is None or res.get("how") in ("saved_unknown", "lazy_skip") or no_part
            or any(isinstance(p, dict) and p.get("kind") == "unclear" for p in res.get("problems") or [])):
        return "not established"
    return "true" if v else "false"


# ----------------------------------------------------------------------------------------------- own fixability
WHO_SOURCES_NONE = ("database", "arguments")


def part_who(entry: dict, part: dict) -> str:
    if part.get("who"):
        return part["who"]
    if part.get("source") in WHO_SOURCES_NONE:
        return "none"
    return entry.get("who") or "none"


def combine_eval(tree: Any, vals: Dict[str, bool]) -> bool:
    op = tree[0]
    if op == "ID":
        return bool(vals[tree[1]])
    if op == "NOT":
        return not combine_eval(tree[1], vals)
    xs = [combine_eval(t, vals) for t in tree[1]]
    return all(xs) if op == "AND" else any(xs)


def can_fix_fact(entry: dict, res: dict, current: bool, F: Any) -> Tuple[bool, bool]:
    """(some smallest part change made only of agent / ask parts turns the fact around; every smallest part change
    needs a user_only part)."""
    import itertools
    tree = F.parse_combine(entry["combine"])
    pids = list(entry["parts"])
    got = res.get("parts") or {}
    vals = {p: (got.get(p) or {}).get("value") for p in pids}
    vals = {p: (v if isinstance(v, bool) else current) for p, v in vals.items()}
    if combine_eval(tree, vals) is not current:
        vals = {p: current for p in pids}
    found: List[set] = []
    for k in range(1, len(pids) + 1):
        for sub in itertools.combinations(pids, k):
            s = set(sub)
            if any(f <= s for f in found):
                continue
            v = dict(vals)
            for p in sub:
                v[p] = not v[p]
            if combine_eval(tree, v) is (not current):
                found.append(s)
    whos = [{part_who(entry, entry["parts"][p]) for p in s} for s in found] or [
        {part_who(entry, entry["parts"][p]) for p in pids}]
    fix = any(w <= {"agent", "ask"} for w in whos)
    user_only = all("user_only" in w for w in whos)
    return fix, user_only


def own_closing_ok(domain: str, tool: str, violated: List[str], results: Dict[str, dict], table_rules: dict,
                   defs: dict, F: Any) -> bool:
    """Every violated rule has a flip set whose facts can each be made true by agent / ask parts."""
    for rid in violated:
        e = table_rules[rid]
        vals = {}
        for f in e["facts"]:
            v = results[f].get("value")
            if shown_of(results[f]) == "not established":
                v = bool(e["blocking_values"][f][0])
            vals[f] = bool(v)
        row = next(r for r in e["rows"] if r["action"] == tool and all(r["values"][f] == vals[f] for f in e["facts"]))
        ok = False
        for s in row["flip_sets"]:
            if all(can_fix_fact(defs[f], results[f], vals[f], F)[0] for f in s):
                ok = True
                break
        if not ok:
            return False
    return True


def user_only_not_given(entry: dict, res: dict) -> bool:
    """The fact has a user_only part (its own who, else the fact's) whose value is not true."""
    for pid, part in entry["parts"].items():
        if (part.get("who") or entry.get("who")) == "user_only":
            if ((res.get("parts") or {}).get(pid) or {}).get("value") is not True:
                return True
    return False


# ----------------------------------------------------------------------------------------------- one block
class Checker:
    def __init__(self) -> None:
        from guard import feedback_v4 as FB
        from state_tracker.v3 import facts_format_v3 as F
        from state_tracker.v3 import message_view as MV
        from state_tracker.v3 import tool_check as TC
        self.FB, self.F, self.MV, self.TC = FB, F, MV, TC
        self.rule_set = {d: json.load(open(paths.rule_set_path(d), encoding="utf-8")) for d in paths.DOMAINS}
        self.table = {d: json.load(open(F.rule_table_path(d), encoding="utf-8")) for d in paths.DOMAINS}
        self.table_rules = {d: {str(r["id"]): r for r in self.table[d]["rules"]} for d in paths.DOMAINS}
        self.defs = {d: FB.fact_definitions(d) for d in paths.DOMAINS}           # the v4 fact files
        self.schemas = {d: {t["function"]["name"]: t["function"] for t in tau_copy.tools_info(d)}
                        for d in paths.DOMAINS}
        self.write = {d: {n for n, s in S.tool_table()["domains"][d]["tools"].items() if s.get("changes_db")}
                      for d in paths.DOMAINS}
        self.scan = {d: RawScan(d) for d in paths.DOMAINS}
        self.sents = {d: {s["id"]: s["text"] for s in self.rule_set[d]["sentences"]} for d in paths.DOMAINS}
        self.rs_rules = {d: {str(r["id"]): r for r in self.rule_set[d]["rules"]} for d in paths.DOMAINS}
        self.descriptions = {d: [p["description"] for p in self.rule_set[d]["predicates"].values()
                                 if len(p.get("description") or "") >= 25] for d in paths.DOMAINS}
        self.line_names = LINE_NAMES

    # --- P10.1 (rule)
    def check_values(self, domain: str, tool: str, args: dict, viol: List[str], results: dict, text: str,
                     history: List[dict], db: dict) -> List[str]:
        fails: List[str] = []
        lines = text.split("\n")
        from method_tgr import feedback as TGR_FB
        kind = "respond" if tool == "respond" else "tool_call"
        if lines[0] != TGR_FB.actionable(kind, tool, [], None, {}, {}, {}).split("\n")[0]:
            fails.append("first line differs from TGR's")
        names = {f for rid in viol for f in self.table_rules[domain][rid]["facts"]}
        by_words = {self.FB.words(f): f for f in names}
        want_sents: List[str] = []
        for rid in viol:
            for sid in self.rs_rules[domain][rid].get("sentences") or []:
                if sid in self.sents[domain] and self.sents[domain][sid] not in want_sents:
                    want_sents.append(self.sents[domain][sid])
        events = own_events(history)
        users = [m.get("content") or "" for m in history if m.get("role") == "user"]
        section = "head"
        closings = {"Do not repeat the same call as it stands.", "Do not send the same message as it stands.",
                    f"When this is done, call {tool} again.", "When this is done, send your message again."}
        for i, ln in enumerate(lines[1:], 1):
            if ln.startswith("Policy: "):
                if ln != "Policy: " + " ".join(f"\"{s}\"" for s in want_sents):
                    fails.append("policy line is not the cited sentences")
                continue
            if ln == self.FB.NOT_MET:
                section = "not_met"
                continue
            if ln == self.FB.WHAT:
                section = "what"
                continue
            if i == len(lines) - 1:
                if ln not in closings:
                    fails.append(f"closing line not known: {ln[:80]}")
                continue
            if section == "not_met":
                m = R_FACT.match(ln)
                if m:
                    f = by_words.get(m.group("words"))
                    if f is None:
                        fails.append(f"fact line names no fact of the violated rules: {ln[:80]}")
                    elif m.group("shown") != shown_of(results[f]):
                        fails.append(f"fact value: {f} shown {m.group('shown')}, guard {shown_of(results[f])}")
                    continue
                if ln.startswith("  - "):
                    err = self.check_evidence(ln[4:], args, events, db, history=history, domain=domain)
                    if err:
                        fails.append(err)
                    continue
                fails.append(f"unparsed line: {ln[:80]}")
                continue
            if section == "what":
                m = R_ITEM.match(ln) or R_SUB.match(ln)
                if not m:
                    fails.append(f"unparsed advice line: {ln[:80]}")
                    continue
                t = m.group("text")
                if t == self.FB.ANY_ONE:
                    continue
                for a in split_advice(t):
                    err = self.check_advice_text(a, by_words, results, users, domain=domain, args=args)
                    if err:
                        fails.append(err)
                continue
            fails.append(f"unparsed line: {ln[:80]}")
        return fails

    def check_evidence(self, t: str, args: dict, events: List[dict], db: dict, history: Optional[List[dict]] = None,
                       domain: Optional[str] = None) -> Optional[str]:
        if t in (self.FB.HIDDEN_BEFORE_LOGIN, self.FB.HIDDEN_OTHER):
            return None
        if t.startswith(("Not stated", "Your listing says")):
            return self.check_missing_line(t, args, db, history or [], domain)
        m = R_EVENT.match(t)
        if m:
            val = json.loads(m.group("val"))
            done = any(e["ok"] and e["tool"] == m.group("tool") and isinstance(e["args"], dict)
                       and e["args"].get(m.group("key"), _MISSING) == val for e in events)
            return f"event line false: {t[:80]}" if done else None
        m = R_NOEVENT.match(t)
        if m:
            tools = m.group("tools").split(" or ")
            done = any(e["ok"] and e["tool"] in tools for e in events)
            return f"event line false: {t[:80]}" if done else None
        m = R_ARGN.match(t)
        if m:
            v = args.get(m.group("key"), _MISSING)
            ok = isinstance(v, list) and len(v) == int(m.group("n"))
            return None if ok else f"argument line false: {t[:80]}"
        m = R_ARG.match(t)
        if m:
            ok = m.group("key") in args and json.loads(m.group("val")) == args[m.group("key")]
            return None if ok else f"argument line false: {t[:80]}"
        m = R_MISS.match(t)
        if m:
            ok = own_record(db, m.group("kind"), m.group("id")) is _MISSING
            return None if ok else f"database line false: {t[:80]}"
        m = R_HAS.match(t)
        if m:
            rec = own_record(db, m.group("kind"), m.group("id"))
            cont = own_read(rec, parse_path(m.group("path"))) if m.group("path") != "record" else rec
            key = json.loads(m.group("key"))
            ok = isinstance(cont, dict) and ((key in cont) == (m.group("yn") == "yes"))
            return None if ok else f"database line false: {t[:80]}"
        m = R_GET.match(t)
        if m:
            rec = own_record(db, m.group("kind"), m.group("id"))
            v = own_read(rec, parse_path(m.group("path"))) if rec is not _MISSING else _MISSING
            ok = v is not _MISSING and json.loads(m.group("val")) == v
            return None if ok else f"database line false: {t[:80]}"
        return f"unparsed evidence line: {t[:80]}"

    def check_missing_line(self, t: str, args: dict, db: dict, history: List[dict], domain: Optional[str]
                           ) -> Optional[str]:
        """v4: a missing line against the call and the own database (module text)."""
        me = own_me(domain, history, db) if domain else None
        recs = call_records(domain or "", args, db, me)
        m = R_MISS_PAY.match(t)
        if m:
            pid = m.group("pid")
            if pid not in arg_strings(args):
                return f"missing line: the payment id is not the call's: {t[:80]}"
            rec = own_record(db, "payment_method", pid)
            inner = m.group("inner") or ""
            if rec is _MISSING:
                return None if not inner else f"missing line: details of a payment method not in the database: {t[:80]}"
            lf = re.search(r"last four (\d{4})", inner)
            if lf and str(rec.get("last_four")) != lf.group(1):
                return f"missing line: last four differs from the database: {t[:80]}"
            end = re.search(r"ending in (\d{4})", inner)
            if end and re.sub(r"\D", "", pid)[-4:] != end.group(1):
                return f"missing line: 'ending in' is not the id's digits: {t[:80]}"
            brand = inner.split(",")[0].strip() if rec.get("source") == "credit_card" and "," in inner else None
            if brand and rnorm(brand) != rnorm(str(rec.get("brand") or "").replace("_", " ")):
                return f"missing line: brand differs from the database: {t[:80]}"
            return None
        m = R_SAID_HIDDEN.match(t)
        if m:
            return None if self._said_ok(m.group("said"), history) else f"listing quote not in an agent message: {t[:80]}"
        m = R_SAID.match(t)
        if m:
            if not self._said_ok(m.group("said"), history):
                return f"listing quote not in an agent message: {t[:80]}"
            rest = m.group("rest")
            val = rest.split(" is ", 1)[1] if " is " in rest else ""
            return None if val and value_in_records(val, recs) else f"missing line value not of the call: {t[:80]}"
        m = R_MISS_LINE.match(t)
        if m:
            rest = m.group("rest")
            for line in sorted(self.line_names, key=len, reverse=True):
                if rest == line:
                    return None
                if rest.startswith(line + " "):
                    val = rest[len(line) + 1:]
                    return None if value_in_records(val, recs) else f"missing line value not of the call: {t[:80]}"
            # an unknown line name (another agent's new line): the value check on the words after the first two
            words_ = rest.split(" ")
            return None if any(value_in_records(" ".join(words_[k:]), recs) for k in range(1, min(len(words_), 8))) \
                else f"missing line value not of the call: {t[:80]}"
        return f"unparsed missing line: {t[:80]}"

    @staticmethod
    def _said_ok(said: str, history: List[dict]) -> bool:
        want = rnorm(said.replace("’", "'"))
        agents = [rnorm((m.get("content") or "").replace("’", "'")) for m in history if m.get("role") == "assistant"]
        return all(any(p.strip() in a for a in agents) for p in want.split(" / ") if p.strip())

    def check_v4_advice(self, a: str, domain: Optional[str], args: dict, users: Optional[List[str]] = None
                        ) -> Optional[str]:
        """v4 advice lines: ids of the call only; tools of the domain, and the transfer line's quote is a user message
        (whole, or its start when cut with ' ...'); insurance = the call's."""
        argset = arg_strings(args)
        m = A_GO.match(a)
        if m:
            for _, rx in self.FB._ID_PATTERNS[:2]:
                for x in rx.findall(m.group("action")):
                    if x.lstrip("#").lower() not in {s.lstrip("#") for s in argset}:
                        return f"go-ahead action names a value that is not the call's: {a[:80]}"
            return None
        m = A_REMIND.match(a)
        if m:
            oid = m.group("oid")
            return None if oid in ("this", "order") or oid == str(args.get("order_id")) else \
                f"reminder order is not the call's: {a[:80]}"
        m = A_WHY.match(a)
        if m:
            rid = m.group("rid")
            return None if rid == "the" or rid == str(args.get("reservation_id")) else \
                f"reservation is not the call's: {a[:80]}"
        m = A_TOOLS.match(a)
        if m:
            tools = (m.group("tools") or "").split(", ") if m.group("tools") else []
            bad = [x for x in tools if domain and (x not in self.schemas[domain] or x == "transfer_to_human_agents")]
            if bad:
                return f"tools line names a tool that is not a tool of the domain: {a[:80]}"
            q = m.group("quote")
            if q is not None:
                said = [re.sub(r"\s+", " ", u).strip() for u in users or []]
                cut = q[:-4].rstrip() if q.endswith(" ...") else None
                if not any(s == q or (cut and s.startswith(cut)) for s in said):
                    return f"tools line quote is not a user message: {a[:80]}"
            return None
        m = A_INS.match(a)
        if m:
            return None if m.group("v") in (str(args.get("insurance")), "not set") else f"insurance differs: {a[:80]}"
        if A_CLASH.match(a) or A_CLASH_HIDDEN.match(a) or A_PAYASK.match(a) or A_LISTING.match(a):
            return None
        return "not a v4 line"

    def check_advice_text(self, a: str, by_words: dict, results: dict, users: List[str],
                          domain: Optional[str] = None, args: Optional[dict] = None) -> Optional[str]:
        if any(rx.match(a) for rx in V4_ADVICE):
            return self.check_v4_advice(a, domain, args or {}, users)
        for rx in (A_STEP, A_CHANGE, A_ASK, A_ASKNEG, A_USERONLY):
            m = rx.match(a)
            if m:
                return None if m.group("words") in by_words else f"advice names no fact: {a[:80]}"
        m = A_NONE.match(a)
        if m:
            f = by_words.get(m.group("words"))
            if f is None:
                return f"advice names no fact: {a[:80]}"
            return None if m.group("shown") == shown_of(results[f]) else f"advice value false: {a[:80]}"
        m = A_ASKNO.match(a) or A_SAIDNO.match(a)
        if m:
            q = m.group("quote").rstrip(" .")
            last = re.sub(r"\s+", " ", users[-1]).strip() if users else ""
            ok = bool(users) and (last == m.group("quote") or (m.group("quote").endswith(" ...")
                                                              and last.startswith(q[:-3].rstrip())))
            if m.re is A_ASKNO and m.group("words") not in by_words:
                return f"advice names no fact: {a[:80]}"
            return None if ok else f"quote is not the user's latest message: {a[:80]}"
        if A_LOOKUP.match(a) or A_LOGIN.match(a):
            return None                              # checked in P10.2 (their argument is the call's, below)
        return f"unparsed advice: {a[:80]}"

    # --- P10.2
    def check_steps(self, domain: str, tool: str, args: dict, text: str, db: dict, c: collections.Counter
                    ) -> List[str]:
        fails = []
        sch = self.schemas[domain]
        for ln in text.split("\n"):
            m = R_ITEM.match(ln) or R_SUB.match(ln)
            if not m:
                continue
            for a in split_advice(m.group("text")):
                lu = A_LOOKUP.match(a)
                if lu:
                    c["P10.2 look-up steps"] += 1
                    t, k = lu.group("tool"), lu.group("key")
                    val = json.loads(lu.group("val"))
                    props = ((sch.get(t) or {}).get("parameters") or {}).get("properties") or {}
                    if t not in sch or k not in props:
                        fails.append(f"look-up step not in the schemas: {a[:80]}")
                        continue
                    if args.get(k, _MISSING) != val and not any(v == val for v in args.values()):
                        fails.append(f"look-up value is not a value of the call: {a[:80]}")
                    run_db = copy.deepcopy(db) if t in self.write[domain] else db
                    try:
                        out = tau_copy.tools(domain)[t].invoke(data=run_db, **{k: val})
                    except Exception as e:  # noqa: BLE001 - τ-bench's Env makes it an Error text
                        out = f"Error: {e}"
                    if failed(out):
                        fails.append(f"look-up step gives an Error on the copy: {a[:60]} -> {str(out)[:60]}")
                    else:
                        c["P10.2 look-up steps run with no Error"] += 1
                    continue
                lg = A_LOGIN.match(a)
                if lg:
                    c[K_LOGIN] += 1
                    for call in lg.group("calls").split(" or "):
                        cm = A_CALL.match(call)
                        if not cm or cm.group("tool") not in sch:
                            fails.append(f"step tool not in the schemas: {call[:60]}")
                            continue
                        want = list((sch[cm.group("tool")].get("parameters") or {}).get("required") or [])
                        got = [x.strip() for x in cm.group("args").split(",") if x.strip()]
                        if got != want:
                            fails.append(f"step argument names differ from the schema: {call[:60]}")
                    continue
                if any(rx.match(a) for rx in (A_STEP, A_CHANGE, A_ASK, A_ASKNEG, A_ASKNO) + V4_ADVICE):
                    c["P10.2 message steps (no tool)"] += 1
        if tool != "respond" and tool not in sch:
            fails.append(f"the closing's tool is not in the schemas: {tool}")
        return fails


# ----------------------------------------------------------------------------------------------- the run
def decision_view(rec: dict) -> str:
    keep = {k: rec.get(k) for k in ("action_allowed", "margin", "violated_rules", "mln", "unknown_predicates",
                                    "allowed_eps0", "circuit", "matched", "trace_position")}
    keep["values"] = {n: v.get("value") for n, v in (rec.get("judge") or {}).items()}
    keep["v3_facts"] = {n: (f.get("value"), f.get("source")) for n, f in ((rec.get("v3") or {}).get("facts") or {}
                                                                          ).items()}
    return json.dumps(O._jn(keep), sort_keys=True)


def dev_conversations(datasets: Iterable[str], tot: collections.Counter, limit: Optional[int]
                      ) -> Iterable[O.SavedConversation]:
    n_by: collections.Counter = collections.Counter()
    for conv in O.iter_conversations(list(datasets)):
        if conv.side != O.DEV:
            tot["hold-out Stage B tries skipped (not read)"] += 1
            continue
        n_by[conv.dataset] += 1
        if limit is not None and n_by[conv.dataset] > limit:
            continue
        yield conv


def pct(n: float, d: float) -> str:
    return f"{100.0 * n / d:.1f} %" if d else "n/a"


def length_stats(xs: List[int]) -> Dict[str, Any]:
    if not xs:
        return {"n": 0}
    s = sorted(xs)
    return {"n": len(s), "mean": round(statistics.mean(s), 1), "median": statistics.median(s),
            "p90": s[min(len(s) - 1, int(0.9 * len(s)))], "max": s[-1], "min": s[0]}


def run(datasets: Iterable[str], all_checks: bool, limit: Optional[int], log=say) -> Dict[str, Any]:
    t0 = time.time()
    G = guard_module()
    Capture = capture_class()
    ck = Checker()
    FB, F, MV, TC = ck.FB, ck.F, ck.MV, ck.TC
    guards = {}
    for d in paths.DOMAINS:
        g = build_guard(d)
        g.__class__ = Capture
        guards[d] = g
    tot: collections.Counter = collections.Counter()
    pops = {"saved_block": collections.Counter(), "v4_block_at_saved_allow": collections.Counter()}
    adv: Dict[str, collections.Counter] = {p: collections.Counter() for p in pops}
    closing: Dict[str, collections.Counter] = {p: collections.Counter() for p in pops}
    lengths: Dict[str, Dict[str, List[int]]] = {p: collections.defaultdict(list) for p in pops}
    c9: Dict[str, collections.Counter] = {p: collections.Counter() for p in pops}
    fails: Dict[str, List[dict]] = collections.defaultdict(list)
    examples: Dict[str, List[dict]] = collections.defaultdict(list)
    for conv in dev_conversations(datasets, tot, limit):
        tot["conversations"] += 1
        g = guards[conv.domain]
        g.state_source = Walk(conv)
        own = OwnDB(conv.domain, conv.ep["executed"])
        try:
            for ch in conv.checks():
                tot["checks"] += 1
                saved_block = ch.saved_decision == "block"
                tot[f"saved {ch.saved_decision}"] += 1
                if not (saved_block or all_checks):
                    continue
                judged = ch.saved_judge()
                if judged is None:
                    judged = {}
                    tot["judge skipped in the source run (given {})"] += 1
                g.switches["messages"] = "rule"
                g.captured = None
                rec_r = O.run_guard(g, ch.history, ch.msg, ch.n_exec, ch.past, judged)
                pop = "saved_block" if saved_block else "v4_block_at_saved_allow"
                c = pops[pop]
                c["checks"] += 1
                if rec_r.get("action_allowed", True):
                    c["v4 allows (no message)"] += 1
                    continue
                c["v4 blocks"] += 1
                cap = g.captured
                if cap is None:
                    c["v4 block without a captured message"] += 1
                    continue
                d = cap["data"]
                tool, args, results, st, view = d["tool"], d["args"], d["results"], d["state"], d["view"]
                viol = [str(v["rule_id"]) for v in cap["violated"]]
                text_rule = rec_r.get("feedback_text") or cap["text"]
                msgrec = (rec_r.get("v3") or {}).get("message") or {}
                if msgrec.get("fallback"):
                    c["P10.7 guard message fallbacks"] += 1
                    fails["P10.7"].append({"ckey": ch.ckey, "error": msgrec.get("error")})
                # the builder's own call on the same inputs
                try:
                    plan = FB.explain(conv.domain, tool, args, cap["violated"], results, st, view,
                                      ck.table[conv.domain], ck.rule_set[conv.domain])
                    mine = FB.render(plan)
                    simple_mine = FB.build_simple(conv.domain, tool, args, cap["violated"], results, st, view,
                                                  ck.table[conv.domain], ck.rule_set[conv.domain])
                except Exception as e:  # noqa: BLE001 - counted (P10.7)
                    c["P10.7 builder exceptions"] += 1
                    fails["P10.7"].append({"ckey": ch.ckey, "error": f"{type(e).__name__}: {e}"[:300]})
                    continue
                if mine != text_rule:
                    c[K_TEXTDIFF] += 1
                    fails["P10.7"].append({"ckey": ch.ckey, "error": "text differs"})
                # P10.6: the same check with messages = frozen and simple
                texts = {"rule": text_rule}
                views = {"rule": decision_view(rec_r)}
                for mode in ("frozen", "simple"):
                    g.switches["messages"] = mode
                    g.captured = None
                    r = O.run_guard(g, ch.history, ch.msg, ch.n_exec, ch.past, judged)
                    texts[mode] = r.get("feedback_text") or ""
                    views[mode] = decision_view(r)
                g.switches["messages"] = "rule"
                same = views["rule"] == views["frozen"] == views["simple"]
                c["P10.6 decisions equal (frozen, rule, simple)"] += same
                if not same:
                    fails["P10.6"].append({"ckey": ch.ckey})
                # own database, me, history
                db = own.at(ch.history)
                me = own_me(conv.domain, ch.history, db)
                c["blocks before login"] += me is None
                # P10.1
                f1 = ck.check_values(conv.domain, tool, args, viol, results, text_rule, ch.history, db)
                c["P10.1 rule messages with a false or unverified value"] += bool(f1)
                c["P10.1 failing lines (rule)"] += len(f1)
                if f1:
                    fails["P10.1"].append({"ckey": ch.ckey, "fails": f1[:5]})
                f1s = []
                for ln in texts["simple"].split("\n"):
                    m = SIMPLE_FACT.match(ln)
                    if m:
                        n = m.group("name")
                        want = results.get(n)
                        if want is None:
                            f1s.append(f"simple names an unknown fact {n}")
                        elif m.group("v") != ("not established" if want.get("value") is None
                                              else ("true" if want["value"] else "false")):
                            f1s.append(f"simple value false: {n}")
                c["P10.1 simple messages with a false value"] += bool(f1s)
                if f1s:
                    fails["P10.1 simple"].append({"ckey": ch.ckey, "fails": f1s[:5]})
                # P10.2
                f2 = ck.check_steps(conv.domain, tool, args, text_rule, db, c)
                c["P10.2 rule messages with a step that is not a real call"] += bool(f2)
                if f2:
                    fails["P10.2"].append({"ckey": ch.ckey, "fails": f2[:5]})
                # P10.3
                if tool != "respond" and TC.is_write_tool(conv.domain, tool) and tool in TC.TOOL_CHECKS:
                    lab = TC.check(st, {"tool": tool, "args": args})
                    for fact, tv in lab["facts"].items():
                        if tv is None or fact not in plan["facts"]:
                            continue
                        if not any(nm["fact"] == fact for nm in plan["not_met"]):
                            continue
                        c["P10.3 facts the tool decides, named in the message"] += 1
                        says_no = plan["facts"][fact]["status"] == "none"
                        line = f"Not possible with these arguments: {FB.words(fact)} is "
                        in_text = line in text_rule
                        if says_no != in_text:
                            fails["P10.3"].append({"ckey": ch.ckey, "fact": fact, "why": "plan and text differ"})
                            c["P10.3 mismatches"] += 1
                            continue
                        if in_text == (tv is False):
                            c["P10.3 matches"] += 1
                        else:
                            c["P10.3 mismatches"] += 1
                            fails["P10.3"].append({"ckey": ch.ckey, "fact": fact, "tool_value": tv,
                                                   "not_possible_line": in_text, "check": lab["check"]})
                # P10.4
                scan = ck.scan[conv.domain]
                extra = touched_records(conv.domain, ch.history, db, scan, args)
                typed = user_texts(ch.history)
                argset = arg_strings(args)
                for mode in ("rule", "simple"):
                    hits = scan.hits(texts[mode], typed, argset, extra)
                    leak = [h for h in hits if me is None or me not in h["users"]]
                    c[f"P10.4 {mode} messages with a leak"] += bool(leak)
                    if leak:
                        fails[f"P10.4 {mode}"].append({"ckey": ch.ckey, "me": me,
                                                       "hits": [h["value"] for h in leak][:5]})
                # P10.9 (v4): the block names a line the agent can fix in one turn
                p9 = fixable_line_problems(plan, FB)
                c[K_P109] += bool(p9)
                if p9:
                    fails["P10.9"].append({"ckey": ch.ckey, "problems": p9[:5]})
                for x in p9:
                    c9[pop][x] += 1
                # P10.10 (v4): no expected value leaks (before login, another user's)
                p10 = missing_leaks(plan, text_rule, me, scan, typed, argset, extra, FB)
                c[K_P1010] += bool(p10)
                if p10:
                    fails["P10.10"].append({"ckey": ch.ckey, "me": me, "leaks": p10[:5]})
                c["v4 missing lines shown"] += sum(1 for nm in plan["not_met"] for e in nm["evidence"]
                                                   if e.get("type") == "missing")
                c["v4 blocks with a missing line"] += any(e.get("type") == "missing" for nm in plan["not_met"]
                                                          for e in nm["evidence"])
                # P10.5
                bad5 = []
                for a in FB.advice_lines(plan["advice"]):
                    if a["type"] in ("lookup", "user_args_call", "step", "ask", "change", "ask_no") and a.get("fact"):
                        if user_only_not_given(ck.defs[conv.domain][a["fact"]], results[a["fact"]]):
                            bad5.append(a["fact"])
                c["P10.5 rule messages offering a user_only fact as a step"] += bool(bad5)
                if bad5:
                    fails["P10.5"].append({"ckey": ch.ckey, "facts": bad5})
                bad5s = []
                for ln in texts["simple"].split("\n"):
                    m = SIMPLE_TODO.match(ln)
                    if m:
                        for n in [x.strip() for x in m.group("names").split(",")]:
                            if n in ck.defs[conv.domain] and user_only_not_given(ck.defs[conv.domain][n],
                                                                                  results.get(n) or {}):
                                bad5s.append(n)
                c["P10.5 simple messages offering a user_only fact as a step"] += bool(bad5s)
                if bad5s:
                    fails["P10.5 simple"].append({"ckey": ch.ckey, "facts": bad5s})
                # P10.8
                last_user = [m for m in ch.history if m.get("role") == "user"]
                strict = bool(last_user) and MV.is_strict_no(MV.normalize(last_user[-1].get("content") or ""))
                fixable = own_closing_ok(conv.domain, tool, viol, results, ck.table_rules[conv.domain],
                                         ck.defs[conv.domain], F)
                forbids = text_rule.rstrip().endswith("as it stands.")
                if fixable and not strict and forbids:
                    c[K_P108] += 1
                    fails["P10.8"].append({"ckey": ch.ckey})
                if (not fixable or strict) and not forbids:
                    c[K_LENIENT] += 1
                    fails["closing too lenient"].append({"ckey": ch.ckey})
                if forbids != plan["forbid"]:
                    c["closing in the text differs from the plan"] += 1
                # other checks
                for ev in (judged or {}).values():
                    e = (ev or {}).get("evidence") or ""
                    if len(e) >= 25 and e in text_rule:
                        c[K_JUDGE] += 1
                        fails["judge text"].append({"ckey": ch.ckey})
                        break
                if any(x in text_rule for x in ck.descriptions[conv.domain]):
                    c["rule messages with a predicate description"] += 1
                # counts
                adv[pop][plan["advice_class"]] += 1
                closing[pop]["forbids the same call" if plan["forbid"] else "call again"] += 1
                for k, v in (("frozen", texts["frozen"]), ("rule", text_rule), ("simple", texts["simple"]),
                             ("simple (feedback_v4.build_simple)", simple_mine)):
                    lengths[pop][k].append(len(v))
                c["strict no before the block"] += strict
                c["blocks with a stand-in unknown"] += any(shown_of(results[f]) == "not established"
                                                           for f in plan["facts"])
                if len(examples[plan["advice_class"]]) < 3 and pop == "saved_block":
                    examples[plan["advice_class"]].append({"ckey": ch.ckey, "rule": text_rule,
                                                           "simple": texts["simple"], "frozen": texts["frozen"]})
        finally:
            g.state_source = None
        if tot["conversations"] % 200 == 0:
            log(f"{tot['conversations']} conversations, {tot['checks']} checks, "
                f"{sum(p['v4 blocks'] for p in pops.values())} v4 blocks, {time.time() - t0:.0f} s")
    fb = {d: guards[d].counters.get("message_fallbacks", 0) for d in paths.DOMAINS}
    return {"total": dict(tot), "populations": {p: dict(c) for p, c in pops.items()},
            "advice_class": {p: dict(c.most_common()) for p, c in adv.items()},
            "closing": {p: dict(c) for p, c in closing.items()},
            "p109_reasons": {p: dict(c.most_common(40)) for p, c in c9.items()},
            "lengths": {p: {k: length_stats(v) for k, v in L.items()} for p, L in lengths.items()},
            "guard_message_fallbacks": fb, "guard_counters": {d: dict(guards[d].counters) for d in paths.DOMAINS},
            "llm_calls": dict(COUNT), "frozen_overrides": dict(OVERRIDES),
            "guard_unrecorded": guards[paths.DOMAINS[0]].info.get("unrecorded"),
            "fails": {k: v[:MAX_EXAMPLES] for k, v in fails.items()},
            "fail_counts": {k: len(v) for k, v in fails.items()}, "examples": examples,
            "seconds": round(time.time() - t0, 1), "all_checks": all_checks, "limit": limit}


# ----------------------------------------------------------------------------------------------- report
def marks(res: Dict[str, Any], pop: str = "saved_block") -> List[Tuple[str, str, str, bool]]:
    c = res["populations"][pop]
    blocks = c.get("v4 blocks", 0)
    fb = c.get("P10.7 guard message fallbacks", 0) + c.get("P10.7 builder exceptions", 0) + c.get(K_TEXTDIFF, 0)
    steps = c.get("P10.2 look-up steps", 0)
    m3 = c.get("P10.3 facts the tool decides, named in the message", 0)
    out = [
        ("P10.1", "every value in a message is true (rule)",
         f"{c.get('P10.1 rule messages with a false or unverified value', 0)} messages with a failure "
         f"({c.get('P10.1 failing lines (rule)', 0)} lines); simple: "
         f"{c.get('P10.1 simple messages with a false value', 0)}",
         c.get("P10.1 rule messages with a false or unverified value", 0) == 0
         and c.get("P10.1 simple messages with a false value", 0) == 0),
        ("P10.2", "every suggested step is a real call",
         f"{c.get('P10.2 rule messages with a step that is not a real call', 0)} messages fail; look-up steps "
         f"{steps}, run with no Error {c.get('P10.2 look-up steps run with no Error', 0)}; steps with the user's "
         f"details {c.get(K_LOGIN, 0)}; "
         f"message steps {c.get('P10.2 message steps (no tool)', 0)}",
         c.get("P10.2 rule messages with a step that is not a real call", 0) == 0
         and c.get("P10.2 look-up steps run with no Error", 0) == steps),
        ("P10.3", "\"not possible\" lines match τ-bench's refusal",
         f"{c.get('P10.3 matches', 0)} / {m3} facts the tool decides ({pct(c.get('P10.3 matches', 0), m3)}); "
         f"mismatches {c.get('P10.3 mismatches', 0)}", c.get("P10.3 mismatches", 0) == 0),
        ("P10.4", "no leak before login, no other user's data (raw scan)",
         f"rule {c.get('P10.4 rule messages with a leak', 0)}; simple {c.get('P10.4 simple messages with a leak', 0)}",
         c.get("P10.4 rule messages with a leak", 0) == 0 and c.get("P10.4 simple messages with a leak", 0) == 0),
        ("P10.5", "no user_only fact offered as a step",
         f"rule {c.get('P10.5 rule messages offering a user_only fact as a step', 0)}; simple (TGR's own text) "
         f"{c.get('P10.5 simple messages offering a user_only fact as a step', 0)}",
         c.get("P10.5 rule messages offering a user_only fact as a step", 0) == 0),
        ("P10.6", "the message changes no decision (frozen = rule = simple)",
         f"{c.get('P10.6 decisions equal (frozen, rule, simple)', 0)} / {blocks} "
         f"({pct(c.get('P10.6 decisions equal (frozen, rule, simple)', 0), blocks)})",
         c.get("P10.6 decisions equal (frozen, rule, simple)", 0) == blocks),
        ("P10.7", "fallbacks", f"{fb} (guard {c.get('P10.7 guard message fallbacks', 0)}, builder exceptions "
                               f"{c.get('P10.7 builder exceptions', 0)}, text differs "
                               f"{c.get(K_TEXTDIFF, 0)})",
         fb == 0),
        ("P10.8", "no \"do not repeat\" when a step can fix it and no strict no",
         f"{c.get(K_P108, 0)}", c.get(K_P108, 0) == 0),
        ("P10.9", "every block names a line the agent can fix in one turn",
         f"{blocks - c.get(K_P109, 0)} / {blocks} ({pct(blocks - c.get(K_P109, 0), blocks)}); blocks with a missing "
         f"line {c.get('v4 blocks with a missing line', 0)}", c.get(K_P109, 0) == 0),
        ("P10.10", "no expected value before login or of another user",
         f"{c.get(K_P1010, 0)} blocks; missing lines {c.get('v4 missing lines shown', 0)}", c.get(K_P1010, 0) == 0),
    ]
    return out


def render_md(res: Dict[str, Any], meta: Dict[str, Any]) -> str:
    L: List[str] = []
    w = L.append
    w("# Tracker v4: block message checks (development data)")
    w("")
    w(f"Written by `scoring/v4_message_check.py` on {meta['when']} ({res['seconds']:.0f} s). $0: no LLM call "
      f"({sum(res['llm_calls'].get(k, 0) for k in ('TGR._judge (LLM judge) calls', 'LLM calls'))} seen), no network. "
      "Development data only: the two hold-out data sets are not opened; "
      f"{res['total'].get('hold-out Stage B tries skipped (not read)', 0)} hold-out Stage B tries skipped before any "
      "check was read.")
    w("")
    w("**Facts at each block:** the v4 guard (`guard/tgr_tracker_v4.py`, facts = v4, meaning = saved_judge, lazy) "
      "through the offline base (`fork/offline_v3.py` run_guard) with the check's saved judge values; the message is "
      "the one the v4 guard sends with messages = rule (it calls `guard/feedback_v4.py` build_message). At every v4 "
      "block the guard also ran with messages = frozen and simple.")
    w("")
    t = res["total"]
    w(f"Conversations {t.get('conversations', 0)}, checks {t.get('checks', 0)} (saved block "
      f"{t.get('saved block', 0)}, saved allow {t.get('saved allow', 0)}); judge skipped in the source run "
      f"(given no values) {t.get('judge skipped in the source run (given {})', 0)}.")
    w("")
    for pop, title in (("saved_block", "Saved blocks (the pass marks)"),
                       ("v4_block_at_saved_allow", "v4 blocks at saved allows (with --all; reported)")):
        c = res["populations"].get(pop) or {}
        if not c.get("checks"):
            continue
        w(f"## {title}")
        w("")
        w(f"Checks {c.get('checks', 0)}; v4 blocks {c.get('v4 blocks', 0)}; v3 allows {c.get('v4 allows (no message)', 0)}. "
          f"Blocks before login {c.get('blocks before login', 0)}; with a strict no {c.get('strict no before the block', 0)}; "
          f"with a stand-in unknown shown as not established {c.get('blocks with a stand-in unknown', 0)}.")
        w("")
        w("| id | check | result | pass |")
        w("|---|---|---|---|")
        for mid, name, result, ok in marks(res, pop):
            w(f"| {mid} | {name} | {result} | {'yes' if ok else '**NO**'} |")
        w("")
        w(f"Other: rule messages quoting the judge's saved evidence {c.get(K_JUDGE, 0)}; "
          f"with a rule-set predicate description {c.get('rule messages with a predicate description', 0)}; "
          f"closing 'call again' although no step can fix it (not a pass mark) "
          f"{c.get(K_LENIENT, 0)}; "
          f"closing text vs plan differs {c.get('closing in the text differs from the plan', 0)}.")
        w("")
        w("**Advice class per block** (the whos of the advice lines):")
        w("")
        w("| class | blocks |")
        w("|---|---|")
        for k, v in (res["advice_class"].get(pop) or {}).items():
            w(f"| {k} | {v} |")
        w("")
        r9 = (res.get("p109_reasons") or {}).get(pop) or {}
        if r9:
            w("**P10.9 reasons** (advice lines that name no fixable line):")
            w("")
            w("| reason | lines |")
            w("|---|---|")
            for k, v in r9.items():
                w(f"| {k} | {v} |")
            w("")
        cl = res["closing"].get(pop) or {}
        w(f"**Closing:** call again {cl.get('call again', 0)}; forbids the same call {cl.get('forbids the same call', 0)}.")
        w("")
        w("**Length (characters):**")
        w("")
        w("| message | n | mean | median | p90 | max |")
        w("|---|---|---|---|---|---|")
        for k, s in (res["lengths"].get(pop) or {}).items():
            if s.get("n"):
                w(f"| {k} | {s['n']} | {s['mean']} | {s['median']} | {s['p90']} | {s['max']} |")
        w("")
    w("## Examples (saved blocks; rule message, then p9's simple message)")
    w("")
    shown = 0
    for cls in ("agent", "ask", "none", "user_only", "agent+ask", "agent+ask+none"):
        for ex in (res["examples"].get(cls) or [])[:1]:
            w(f"**{cls}** — `{ex['ckey']}`")
            w("")
            w("```")
            w(ex["rule"])
            w("```")
            w("")
            w("```")
            w(ex["simple"])
            w("```")
            w("")
            shown += 1
    if not shown:
        w("None.")
        w("")
    w("## Failures (first examples)")
    w("")
    if not res["fail_counts"]:
        w("None.")
    for k, n in sorted(res["fail_counts"].items()):
        w(f"- {k}: {n}; first: `{json.dumps(res['fails'][k][:2], ensure_ascii=False)[:600]}`")
    w("")
    w("## Files")
    w("")
    for rel, h in meta["sha256"].items():
        w(f"- `{rel}`: `{h}`")
    w("")
    w(f"Guard message fallbacks (p9's counter): {res['guard_message_fallbacks']}.")
    w("")
    w(f"Guard files not recorded in its frozen table: {res.get('guard_unrecorded')}.")
    w("")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    from state_tracker.v3.frozen import check_manifest
    check_manifest()
    ap = argparse.ArgumentParser(description="v4: the block message checks on the development data.")
    ap.add_argument("--all", action="store_true", help="every development check, not only the saved blocks")
    ap.add_argument("--limit", type=int, default=DEV_LIMIT,
                    help=f"at most N conversations per data set (default and maximum {DEV_LIMIT}: the p12a set)")
    ap.add_argument("--datasets", nargs="*", default=list(DEV_DATASETS))
    ap.add_argument("--no-write", action="store_true", help="print the result only")
    a = ap.parse_args(argv)
    bad = [d for d in a.datasets if d in HOLDOUT_DATASETS or d not in DEV_DATASETS]
    if bad:
        ap.error(f"not one of the 4 v4 development data sets {list(DEV_DATASETS)}: {bad}")
    if a.limit is None or not 0 < a.limit <= DEV_LIMIT:
        ap.error(f"--limit must be 1..{DEV_LIMIT} (only the 200 development conversations are allowed)")
    install_safety()
    res = run(a.datasets, a.all, a.limit)
    meta = {"when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            "sha256": {rel: sha256_file(os.path.join(PC_DIR, rel)) for rel in OWN_FILES}}
    say(json.dumps({"populations": res["populations"], "fail_counts": res["fail_counts"],
                    "advice_class": res["advice_class"], "closing": res["closing"], "lengths": res["lengths"],
                    "llm_calls": res["llm_calls"], "seconds": res["seconds"]}, indent=1, default=str))
    for mid, name, result, ok in marks(res):
        say(f"{mid} {'PASS' if ok else 'FAIL'}: {name}: {result}")
    if not a.no_write:
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(dict(res, meta=meta), f, indent=1, ensure_ascii=False, default=str)
        with open(OUT_MD, "w", encoding="utf-8") as f:
            f.write(render_md(res, meta))
        say(f"wrote {os.path.relpath(OUT_MD, PC_DIR)} and {os.path.relpath(OUT_JSON, PC_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
