"""Tracker v3, part 13 step 1: the "Direct + facts" guard (docs/planning/tracker_v3/p13.md, overview Q13, Q14).

The partner's Direct guard (one LLM call per step with the whole policy), run from the runner copy, plus one block in
its prompt: "Facts checked by code (reliable)".

What is the same as Direct (from_shieldagent/runner/repro_runtime/direct.py and repro_online/guards.py, unchanged):
  - the prompt template (repro_runtime/prompts/direct.md, filled by repro_runtime.prompts.render), the history text
    (repro_core.taubench_steps.render_history, cut to its last 24,000 characters), the action text
    (repro_runtime.shield.action_text);
  - the call: repro_runtime.calls.structured (stage "direct", schema direct.SCHEMA, schema name "direct_decision",
    effort "medium"); the model is the process's guard role (exp_core.models.activate(profile, "guard"): gpt-6-luna
    for luna-dev), set by the runner, not here;
  - the decision parsing (safe, violated_policy_statements -> P1, P2, ...), the record fields and the feedback text
    (repro_runtime.shield.render_feedback(violated, explanation, "")).
The policy text: from_shieldagent/policies/<domain>_wiki.txt, read by path, sha256 checked (equal to the partner's
policy_docs file and to τ-bench's wiki.md). The copy's DirectGuard opens a policy_docs/ folder the copy does not have,
so direct_guard(domain) builds the copy's DirectGuard with this loader (its check() code unchanged) for the plain
`direct` arm.

The facts block (Q14):
  - the facts: the v3 facts of the pending action's rules (the frozen rule set's circuit of the action, as TGR finds
    it: matched = [tool], names = the circuit's atoms minus the action names), kept only when EVERY part of the fact's
    definition has a code source (database, event, arguments, structure). A fact with a tiny-question part is left
    out, its code parts too: the LLM reads meaning itself;
  - the values: the ONE v3 evaluator (state_tracker/v3/facts_format_v3.evaluate) on the state built with the pending
    call and the message view, exactly as the v3 guard's first pass (guard/tgr_tracker_v3.py: _state_view, the probe
    answers hook; no question is ever asked). The facts come from the whole conversation and the database; the LLM
    sees the history cut as Direct's;
  - not in the block: a fact whose evaluation raised (fact error), and every fact when the state cannot be trusted
    (a state error: build error, replay mismatch, parse problem, state problem, view error). Both are recorded;
  - the place: in the user message, right after "The agent's next action: <action>", before Direct's last paragraph
    ("Decide whether ..."), separated by one empty line. With no fact there is no block, and the prompt equals
    Direct's, byte for byte;
  - before login (no `me`, p7: guard/feedback_v3.logged_in_user) each fact is one line "- <fact in words>: true |
    false", plus, when the value is the rule's safe default because of a problem, the line "(a problem: <kinds>; the
    value is the rule's safe default)" (audit C #2), nothing else. After login each fact also gets the same problem
    note, its parts (source, value, a short plain text from the fact file) and evidence: the database values the part
    read (only records of `me` or catalog records, each line passed through the info classes, as the p10 block
    message does), the call's arguments the part read, and the event-log status of the look-ups the part needs.

Every check's record is Direct's record plus rec["direct_facts"]: {version, block (bool), facts {name: {value,
source}}, left_out {name: reason}, logged_in, state_error, fact_errors, history_chars, history_cut (the 24,000-char
cut happened), direct_prompt_sha256 (Direct's own prompt), prompt_sha256 (the prompt sent), block_sha256,
block_chars, block_text (the block as sent, or None), evidence (counts), evidence_lines ([{fact, part, source,
text}]: each evidence line of the block, audit C #5), seconds_facts}.

Our code. It imports the runner copy through guard/runner_path.py (never puts from_shieldagent/ on sys.path), never
imports gold code or a scoring module, and makes no LLM call itself: the one call per check is the copy's
repro_runtime.calls.structured, as in Direct (tests replace that seam with a fake LLM).
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "guard"

from guard import runner_path                                            # noqa: E402

runner_path.setup()

from repro_core.taubench_steps import RESPOND, Step, render_history      # noqa: E402  (runner copy)
from repro_online.guards import DirectGuard, make_step                   # noqa: E402  (runner copy)
from repro_runtime import calls as copy_calls                            # noqa: E402  (runner copy)
from repro_runtime import direct as copy_direct                          # noqa: E402  (runner copy)
from repro_runtime import prompts as copy_prompts                        # noqa: E402  (runner copy)
from repro_runtime.shield import action_text, render_feedback            # noqa: E402  (runner copy)
from method_tgr.rules import to_aspm                                     # noqa: E402  (runner copy)
from method_tgr.runtime import load_rule_set                             # noqa: E402  (runner copy)

from guard import feedback_v3 as FB                                      # noqa: E402  (p10: me, traced reads)
from guard import tgr_tracker_v3 as V3                                   # noqa: E402  (p9: state, probe, facts)
from state_tracker import paths                                          # noqa: E402
from state_tracker.v3 import facts_format_v3 as F                        # noqa: E402
from state_tracker.v3 import info_classes as IC                          # noqa: E402

NAME = "direct_facts_v3"
VERSION = "v3.p13.2"                    # p13.2: audit C fixes (problem note before login; block text saved)
EFFORT = "medium"                       # the copy's DirectGuard default (checked in build and the tests)
HISTORY_CHARS = 24000                   # the copy's direct() default (checked in build and the tests)
STAGE = "direct"
SCHEMA_NAME = "direct_decision"
TEMPLATE = "direct"

BLOCK_TITLE = "Facts checked by code (reliable):"
BLOCK_NOTE = ("(computed by code from the database, the tool-call log, the call's arguments and the message "
              "structure of the whole conversation)")
SEP = "\n\n"                            # the block's separator in the user message (as the template's paragraphs)
ACTION_FIELD = "{action}"
MAX_PLAIN_CHARS = 160                   # a part's plain text in the block (after login)
HIDDEN_OTHER = FB.HIDDEN_OTHER

POLICY_REL = "from_shieldagent/policies/{}_wiki.txt"
# sha256 of the policy files (from_shieldagent/SHA256SUMS; equal to the partner's policy_docs/<domain>_wiki.txt and to
# τ-bench's envs/<domain>/wiki.md at 59a200c, checked on 2026-10-23).
POLICY_SHA256 = {
    "retail": "d539fd2a46a8b8dd2e934ff9ed92f43e9f6b56bc7a718db8d2803ba8ad8f6bf7",
    "airline": "56c335801c16e26b54f600f9db99eb04d31db477e86eb160341d5c66b796c5c8",
}
# The runner-copy files whose code Direct runs (their sha256 must equal from_shieldagent/SHA256SUMS).
DIRECT_FILES = ("runner/repro_online/guards.py", "runner/repro_runtime/direct.py", "runner/repro_runtime/prompts.py",
                "runner/repro_runtime/prompts/direct.md", "runner/repro_runtime/shield.py",
                "runner/repro_runtime/calls.py", "runner/repro_core/taubench_steps.py")
SUMS_REL = "from_shieldagent/SHA256SUMS"


class DirectInputChanged(RuntimeError):
    """A policy file or a runner-copy file of Direct differs from its recorded sha256, or the copy's defaults moved."""


class PromptShapeError(RuntimeError):
    """Direct's user message does not end with the template's last paragraph (the block cannot be placed)."""


# ----------------------------------------------------------------------------------------------- inputs
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


def _abs(rel: str) -> str:
    return os.path.join(paths.PC_DIR, *rel.split("/"))


def load_policy(domain: str) -> str:
    """The policy text of a domain (from_shieldagent/policies/<domain>_wiki.txt), read by path, sha256 checked."""
    if domain not in POLICY_SHA256:
        raise ValueError(f"unknown domain {domain!r}")
    with open(_abs(POLICY_REL.format(domain)), "rb") as f:
        raw = f.read()
    h = sha256_bytes(raw)
    if h != POLICY_SHA256[domain]:
        raise DirectInputChanged(f"{POLICY_REL.format(domain)}: sha256 {h} != recorded {POLICY_SHA256[domain]}")
    return raw.decode("utf-8")


def _sums() -> Dict[str, str]:
    out = {}
    with open(_abs(SUMS_REL), encoding="utf-8") as f:
        for ln in f:
            parts = ln.rstrip("\n").split("  ", 1)
            if len(parts) == 2:
                out[parts[1]] = parts[0]
    return out


def check_direct_inputs() -> Dict[str, str]:
    """sha256 of the policy files and of Direct's runner-copy files (equal to SHA256SUMS), and the copy's defaults
    (DirectGuard effort, direct() history_chars). Raises DirectInputChanged. Returns {rel: sha256}."""
    sums = _sums()
    got, bad = {}, []
    for d in POLICY_SHA256:
        rel = f"policies/{d}_wiki.txt"
        with open(_abs("from_shieldagent/" + rel), "rb") as f:
            h = sha256_bytes(f.read())
        got["from_shieldagent/" + rel] = h
        if h != POLICY_SHA256[d] or sums.get(rel) != POLICY_SHA256[d]:
            bad.append(f"{rel}: sha256 {h}, SHA256SUMS {sums.get(rel)}, recorded {POLICY_SHA256[d]}")
    for rel in DIRECT_FILES:
        with open(_abs("from_shieldagent/" + rel), "rb") as f:
            h = sha256_bytes(f.read())
        got["from_shieldagent/" + rel] = h
        if sums.get(rel) != h:
            bad.append(f"{rel}: sha256 {h} != SHA256SUMS {sums.get(rel)}")
    eff = inspect.signature(DirectGuard.__init__).parameters["effort"].default
    hc = inspect.signature(copy_direct.direct).parameters["history_chars"].default
    if eff != EFFORT:
        bad.append(f"DirectGuard effort default {eff!r} != {EFFORT!r}")
    if hc != HISTORY_CHARS:
        bad.append(f"direct() history_chars default {hc!r} != {HISTORY_CHARS!r}")
    if bad:
        raise DirectInputChanged("Direct inputs changed: " + "; ".join(bad))
    return got


def direct_guard(domain: str, effort: str = EFFORT) -> DirectGuard:
    """The copy's DirectGuard with the policy loader above (its __init__ would open policy_docs/, which the copy does
    not have). Its check() is the copy's own code, unchanged."""
    g = DirectGuard.__new__(DirectGuard)
    g.policy = load_policy(domain)
    g.effort = effort
    return g


# ----------------------------------------------------------------------------------------------- the prompt
def template_tail() -> str:
    """The part of Direct's user template after "{action}" (Direct's last paragraph, with its leading blank line)."""
    _, user = copy_prompts._load(TEMPLATE)
    if user.count(ACTION_FIELD) != 1:
        raise PromptShapeError(f"the {TEMPLATE} template has {user.count(ACTION_FIELD)} {ACTION_FIELD} fields")
    tail = user.split(ACTION_FIELD, 1)[1]
    if any("{" + k + "}" in tail for k in ("policy", "history", "action")) or not tail.startswith(SEP):
        raise PromptShapeError("the template's text after {action} holds a field or does not start a paragraph")
    return tail


def direct_prompt(policy: str, step: Step, history_chars: int = HISTORY_CHARS) -> Tuple[str, str, Dict[str, Any]]:
    """(system, user) exactly as the copy's direct() renders them, and the history facts {chars, cut}."""
    hist_full = render_history(step.history)
    sysmsg, user = copy_prompts.render(TEMPLATE, policy=policy,
                                       history=render_history(step.history, max_chars=history_chars),
                                       action=action_text(step))
    return sysmsg, user, {"history_chars": len(hist_full), "history_cut": len(hist_full) > history_chars}


def with_block(user: str, block: Optional[str]) -> str:
    """Direct's user message with the block placed right after the action line (no block: unchanged)."""
    if not block:
        return user
    tail = template_tail()
    if not user.endswith(tail):
        raise PromptShapeError("Direct's user message does not end with the template's last paragraph")
    return user[: len(user) - len(tail)] + SEP + block + tail


def prompt_sha256(system: str, user: str) -> str:
    return sha256_text(json.dumps({"system": system, "user": user}, ensure_ascii=False, sort_keys=True))


# ----------------------------------------------------------------------------------------------- the facts
def code_only(entry: dict) -> bool:
    """Every part of the definition has a code source (no tiny-question part, Q14)."""
    parts = entry.get("parts") or {}
    return bool(parts) and all((p or {}).get("source") in F.CODE_SOURCES for p in parts.values()) and \
        "question" not in (entry.get("sources") or [])


class _StateCtx:
    """The two attributes TrackerTGRv3._state_view reads (online: no offline state source)."""

    def __init__(self, domain: str):
        self.domain = domain
        self.state_source = None


def _word(v: Any) -> str:
    return "true" if v is True else ("false" if v is False else "not set")


def _short(text: Any, n: int = MAX_PLAIN_CHARS) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


class FactsBlock:
    """The code-only v3 facts of one domain and the block text of a check."""

    SOURCE_WORDS = {"database": "database", "event": "tool-call log", "arguments": "call arguments",
                    "structure": "message structure"}

    def __init__(self, domain: str, facts_doc: Optional[dict] = None, rule_set: Optional[dict] = None):
        if domain not in paths.DOMAINS:
            raise ValueError(f"unknown domain {domain!r}")
        self.domain = domain
        self.doc = facts_doc if facts_doc is not None else V3.load_checked_facts(domain)
        self.rule_set = rule_set if rule_set is not None else load_rule_set(
            os.path.join(paths.RULES_DIR, domain, "rule_set.json"))
        self.aspm = to_aspm(self.rule_set)
        self.entries = self.doc["facts"]
        missing = sorted(set(self.rule_set["predicates"]) - set(self.entries))
        if missing:
            raise V3.FactFileProblem(f"{domain}: facts without a v3 entry: {missing}")
        self.code_facts = sorted(n for n, e in self.entries.items() if code_only(e))

    # --------------------------------------------------------------------------------------------- names
    def circuit_names(self, tool: str) -> List[str]:
        """The facts of the pending action's rules, as TGR finds them (grounded: matched = [tool])."""
        matched = [tool] if tool in self.aspm.action_predicates else []
        circuit = self.aspm.circuit(matched)
        return sorted({n for r in circuit for n in self.aspm.rules[r].atoms} - self.aspm.action_predicates)

    def block_names(self, tool: str) -> Tuple[List[str], Dict[str, str]]:
        """(the circuit's code-only facts, {left-out fact: "needs_question"})."""
        names = self.circuit_names(tool)
        keep = [n for n in names if code_only(self.entries[n])]
        return keep, {n: "needs_question" for n in names if n not in keep}

    # --------------------------------------------------------------------------------------------- values
    def evaluate(self, step: Step) -> Dict[str, Any]:
        """The values of the circuit's code-only facts on this check (the v3 guard's first pass), with the state and
        the view kept for the evidence. Never raises for a state or fact problem (recorded)."""
        t0 = time.time()
        tool = RESPOND if step.kind == "respond" else step.name
        args = step.arguments if isinstance(step.arguments, dict) else {}
        keep, left = self.block_names(tool)
        out: Dict[str, Any] = {"tool": tool, "args": args, "names": keep, "left_out": dict(left), "results": {},
                               "kinds": {}, "state": None, "view": None, "state_error": None, "fact_errors": [],
                               "state_info": None}
        if not keep:
            out["seconds"] = round(time.time() - t0, 3)
            return out
        st, view, serr, info = V3.TrackerTGRv3._state_view(_StateCtx(self.domain), step.history, tool, args)
        out.update(state=st, view=view, state_info=info)
        if serr is not None:
            out["state_error"] = serr
            for n in keep:
                out["left_out"][n] = f"state_error: {serr['kind']}"
            out["names"] = []
            out["seconds"] = round(time.time() - t0, 3)
            return out
        probe = V3._Probe(standin=False)
        for n in keep:
            try:
                r = F.evaluate(self.entries[n], st, args, view=view, answers=probe, name=n)
            except Exception as e:  # noqa: BLE001 - left out of the block, recorded (the v3 guard: fact_error)
                out["fact_errors"].append({"fact": n, "error": f"{type(e).__name__}: {e}"[:400]})
                out["left_out"][n] = "fact_error"
                continue
            if V3._deferred_qid(r) is not None:           # cannot happen for a code-only fact; never shown if it did
                out["left_out"][n] = "asked_a_question"
                continue
            out["results"][n] = r
            out["kinds"][n] = "code" if not r["problems"] else "blocking_value"
        out["names"] = [n for n in keep if n in out["results"]]
        out["seconds"] = round(time.time() - t0, 3)
        return out

    # --------------------------------------------------------------------------------------------- the block
    def render(self, ev: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
        """(the block text or None, evidence info {logged_in, db_lines, hidden_other, evidence_errors, ...})."""
        names = ev["names"]
        info = {"logged_in": None, "db_lines": 0, "arg_lines": 0, "event_lines": 0, "hidden_other": 0,
                "evidence_errors": 0, "trace_mismatch": 0, "shown_records": [], "evidence_lines": []}
        if not names:
            return None, info
        st, view, args, tool = ev["state"], ev["view"], ev["args"], ev["tool"]
        me = FB.logged_in_user(st, view, self.domain)
        info["logged_in"] = me is not None
        lines = [BLOCK_TITLE, BLOCK_NOTE]
        for n in names:
            r = ev["results"][n]
            lines.append(f"- {FB.words(n)}: {_word(r['value'])}")
            probs = sorted({p.get("kind") for p in r.get("problems") or [] if p.get("kind")})
            if probs:                                      # before and after login (audit C #2)
                lines.append(f"  (a problem: {', '.join(probs)}; the value is the rule's safe default)")
            if me is None:
                continue                                   # before login: true / false (and the note) only (Q14)
            lines += self._fact_lines(n, r, st, view, args, me, info)
        return "\n".join(lines), info

    def _fact_lines(self, name: str, r: dict, st: Any, view: Any, args: dict, me: str, info: dict) -> List[str]:
        entry = self.entries[name]
        out: List[str] = []
        if r.get("items") is not None:
            out.append(f"  (checked for each of {len(r['items'])} item(s) of the call's "
                       f"{(entry.get('for_each') or {}).get('arg')}; the parts below are of item "
                       f"{r.get('deciding_item')})")
        hidden = False
        for pid, part in entry["parts"].items():
            pr = (r.get("parts") or {}).get(pid) or {}
            src = part["source"]
            ran = pr.get("how") in FB.PART_RAN
            val = _word(pr.get("value")) if ran else "not needed"
            out.append(f"  - {self.SOURCE_WORDS.get(src, src)} ({val}): {_short(part.get('plain'))}")
            if not ran:
                continue
            try:
                ev_lines, hid = self._evidence(entry, name, pid, part, pr, st, view, args, me, info)
            except Exception:  # noqa: BLE001 - the part is shown without evidence, counted
                info["evidence_errors"] += 1
                continue
            hidden = hidden or hid
            out += [f"    {t}" for t in ev_lines]
            info["evidence_lines"] += [{"fact": name, "part": pid, "source": src, "text": t} for t in ev_lines]
        if hidden:
            out.append(f"  {HIDDEN_OTHER}")
        return out

    def _evidence(self, entry: dict, name: str, pid: str, part: dict, pr: dict, st: Any, view: Any, args: dict,
                  me: str, info: dict) -> Tuple[List[str], bool]:
        src = part["source"]
        x = FB.expr_info(part["expr"])
        out: List[str] = []
        hidden = False
        if src == "event":
            for lu in x["looked_up"]:
                if lu["arg"] and lu["arg"] not in args:
                    continue
                val = args.get(lu["arg"]) if lu["arg"] else None
                done = FB._event_done(st, lu["tool"], lu["key"], val)
                out.append(f"{lu['tool']} with {lu['key']} {FB.jtext(val)}: "
                           f"{'done' if done else 'not done'} before this call")
                info["event_lines"] += 1
            for e in x["events"]:
                done = any(FB._event_done(st, t, None, None) for t in e["tools"])
                out.append(f"a {' or '.join(e['tools'])} call that worked: {'yes' if done else 'none yet'}")
                info["event_lines"] += 1
            return out, hidden
        if src not in FB.VALUE_SOURCES:
            return out, hidden                             # structure: its value and plain text only
        v, reads = FB.traced_reads(entry, pid, st, copy.deepcopy(args), view, name)
        given = pr.get("value")
        if isinstance(given, bool) and v is not given:
            info["trace_mismatch"] += 1
            return out, hidden
        db = FB._db_lines(reads)
        shown_ids = {FB.jtext(rd["id"]) for rd in reads}
        for k in x["arg_keys"]:
            if k not in args or FB.jtext(args[k]) in shown_ids:
                continue
            al = FB._arg_line(k, args[k])
            if al is not None:
                out.append(al["text"])
                info["arg_lines"] += 1
        for d in db:
            owner, catalog = FB.record_owner(st, d["kind"], d["id"])
            if d["kind"] == "payment_method":
                owner, catalog = FB._payment_owner(st, d["id"]), False
            if not catalog and owner != me:
                hidden = True
                info["hidden_other"] += 1
                continue
            if IC.user_data_values(d["text"], view, st, owner_ok=[me]):
                hidden = True
                info["hidden_other"] += 1
                continue
            out.append(d["text"])
            info["db_lines"] += 1
            info["shown_records"].append({"kind": d["kind"], "id": d["id"], "owner": owner, "catalog": catalog})
        return out, hidden

    def block_for(self, step: Step) -> Dict[str, Any]:
        """The block of a check and its record part (no LLM call)."""
        t0 = time.time()
        ev = self.evaluate(step)
        block, info = self.render(ev)
        return {"block": block, "eval": ev, "info": info, "seconds": round(time.time() - t0, 3)}


# ----------------------------------------------------------------------------------------------- the guard
def direct_facts(policy: str, step: Step, effort: str, block: Optional[str],
                 history_chars: int = HISTORY_CHARS) -> Tuple[dict, Dict[str, Any]]:
    """The copy's direct() with the block placed in the user message (no block: the very same call). Returns
    (Direct's record, prompt info {direct_prompt_sha256, prompt_sha256, history_chars, history_cut})."""
    meter, t0 = copy_calls.Meter(), time.time()
    sysmsg, user0, hist = direct_prompt(policy, step, history_chars)
    user = with_block(user0, block)
    out = copy_calls.structured(meter, stage=STAGE, system=sysmsg, user=user, schema=copy_direct.SCHEMA,
                                schema_name=SCHEMA_NAME, effort=effort)
    violated = [{"rule_id": f"P{i + 1}", "description": s} for i, s in enumerate(out["violated_policy_statements"])]
    rec = {"step_index": step.index, "action_allowed": bool(out["safe"]), "violated_rules": violated,
           "explanation": out["explanation"], "seconds": round(time.time() - t0, 1), "usage": meter.summary()}
    if not out["safe"]:
        rec["feedback_text"] = render_feedback(violated, out["explanation"], "")
    pinfo = dict(hist, direct_prompt_sha256=prompt_sha256(sysmsg, user0), prompt_sha256=prompt_sha256(sysmsg, user))
    return rec, pinfo


class DirectFactsGuard:
    """Direct + facts, with the copy's guard interface (new_episode, check, commit), as repro_online.guards."""
    name = NAME

    def __init__(self, domain: str, effort: str = EFFORT, *, facts_doc: Optional[dict] = None,
                 rule_set: Optional[dict] = None, history_chars: int = HISTORY_CHARS):
        self.domain = domain
        self.policy = load_policy(domain)
        self.effort = effort
        self.history_chars = history_chars
        self.facts = FactsBlock(domain, facts_doc, rule_set)
        self.info: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self.counters: Dict[str, int] = {"checks": 0, "blocks": 0, "state_errors": 0, "fact_errors": 0,
                                         "facts_failures": 0, "history_cut": 0}

    def _count(self, k: str, n: int = 1) -> None:
        with self._lock:
            self.counters[k] = self.counters.get(k, 0) + n

    def new_episode(self):
        return None

    def check(self, state, executed, msg, index):
        return self.decide(make_step(executed, msg, index))

    def commit(self, state, rec):
        pass

    def facts_part(self, step: Step) -> Tuple[Optional[str], Dict[str, Any]]:
        """(block or None, the record part without the prompt fields). A failure of the facts code gives no block
        (the prompt is then Direct's), recorded and counted."""
        try:
            b = self.facts.block_for(step)
        except Exception as e:  # noqa: BLE001 - Direct's prompt is sent; counted
            self._count("facts_failures")
            return None, {"version": VERSION, "block": False, "facts": {}, "left_out": {}, "logged_in": None,
                          "state_error": None, "fact_errors": [], "facts_failure": f"{type(e).__name__}: {e}"[:400],
                          "evidence": {}, "evidence_lines": [], "seconds_facts": None}
        ev, info = b["eval"], b["info"]
        if ev["state_error"] is not None:
            self._count("state_errors")
        if ev["fact_errors"]:
            self._count("fact_errors", len(ev["fact_errors"]))
        part = {"version": VERSION, "block": b["block"] is not None,
                "facts": {n: {"value": ev["results"][n]["value"], "source": ev["kinds"][n],
                              "problems": [p.get("kind") for p in ev["results"][n].get("problems") or []]}
                          for n in ev["names"]},
                "left_out": dict(sorted(ev["left_out"].items())), "logged_in": info["logged_in"],
                "state_error": ev["state_error"], "fact_errors": list(ev["fact_errors"]),
                "facts_failure": None,
                "evidence": {k: info[k] for k in ("db_lines", "arg_lines", "event_lines", "hidden_other",
                                                  "evidence_errors", "trace_mismatch")},
                "evidence_lines": list(info.get("evidence_lines") or []),
                "seconds_facts": b["seconds"]}
        return b["block"], part

    def decide(self, step: Step) -> dict:
        block, part = self.facts_part(step)
        rec, pinfo = direct_facts(self.policy, step, self.effort, block, self.history_chars)
        part.update(pinfo, block_sha256=sha256_text(block) if block else None, block_chars=len(block or ""),
                    block_text=block or None)
        rec["direct_facts"] = part
        self._count("checks")
        self._count("blocks", int(block is not None))
        self._count("history_cut", int(pinfo["history_cut"]))
        return rec


def build(domain: str, *, effort: str = EFFORT, frozen_table: Optional[Dict[str, Optional[str]]] = None,
          facts_doc: Optional[dict] = None) -> DirectFactsGuard:
    """The Direct + facts guard of one domain: Direct's inputs checked (policy sha256, runner-copy files, defaults),
    the v3 guard's frozen inputs checked (guard/tgr_tracker_v3.py FROZEN_SHA256, or `frozen_table`; a changed file
    stops the run), the fact file validated (0 problems)."""
    if domain not in paths.DOMAINS:
        raise ValueError(f"unknown domain {domain!r}")
    direct_sha = check_direct_inputs()
    frozen = V3.check_frozen_v3(frozen_table)
    template_tail()                                        # the block can be placed (raises PromptShapeError)
    g = DirectFactsGuard(domain, effort, facts_doc=facts_doc)
    from state_tracker.state import build_state
    build_state([], None, domain=domain)          # load the τ-bench copy and data once, before worker threads
    g.info = {"guard": NAME, "version": VERSION, "domain": domain, "effort": effort, "history_chars": HISTORY_CHARS,
              "direct_sha256": direct_sha, "frozen_sha256": frozen["sha256"], "unrecorded": frozen["unrecorded"],
              "policy_sha256": POLICY_SHA256[domain], "code_facts": list(g.facts.code_facts),
              "template_sha256": direct_sha.get("from_shieldagent/runner/repro_runtime/prompts/direct.md")}
    return g


__all__ = ["NAME", "VERSION", "EFFORT", "HISTORY_CHARS", "BLOCK_TITLE", "load_policy", "check_direct_inputs",
           "direct_guard", "direct_prompt", "with_block", "template_tail", "prompt_sha256", "code_only", "FactsBlock",
           "direct_facts", "DirectFactsGuard", "build", "DirectInputChanged", "PromptShapeError"]
