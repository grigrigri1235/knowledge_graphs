"""Tracker v3, part 8, step 3: the dry run of the tiny questions (docs/planning/tracker_v3/p8.md). $0.

Fake answers only, with the network blocked (questions.block_network(); P8.2: 0 network events). For every saved
guard check of the development data it evaluates, with the merged v3 fact files, the facts of the rules of the
pending action, and counts the tiny questions they ask: exact counts per data set, per question and per
conversation, strong-agent conversations apart from weak-agent ones (P8.3). The cost is the prompt token count x the
logged list price (gpt-6-luna: $0.10 per 1M input tokens, $0.50 per 1M output tokens). No tokenizer of the model is
installed, so input tokens are characters / 4, marked "(estimate)"; a second column uses a tokens-per-character
ratio fitted on saved gpt-6-luna judge prompts of Stage A (their prompt characters and the input tokens the API
reported; only these two numbers are read). Output tokens are an assumption (no gpt-6-luna low-effort call was ever
made here).

Passes (each with its own answers store, shared by all conversations of the run, as the real answers file is):
  every_yes_exh  every fact of the matched rules, fake "yes" with valid quotes, every candidate asked
  every_no       every fact, fake "no"
  lazy_yes       only the question facts some rule still needs (rule table rows), stop at the first yes, "yes"
  lazy_no        the same with "no"
The budget count is the upper bound = the keys of every_yes_exh and every_no together: with these combine shapes
(no NOT; at most one OR group with two question parts), every question that any answers could reach is asked in one
of the two (questions_reach_check() checks this on the fact files). The real count lies between the lazy counts and
the upper bound, depending on the answers and on how p9 evaluates facts.

Data: development data only (fork/offline_v3.py; side "dev", asserted). Strong = the gpt-6-luna agent, weak =
gpt-5-nano. The paid set of p12 is the strong conversations of Stage A, ours and the partner's train runs (Stage B
keeps the judge stand-in). The 99-task conversations are ours.p10_luna_train and partner.luna_train_v5.
`--side holdout --count-only` counts calls only on the hold-out (for p12's request; nothing of the saved guard
records is read there). `--answers real` is p12's paid run (questions.RealBackend: refuses without
--approved "<the user's words>", --max-usd and --max-calls; the strong-agent data only: PAID_DATASETS on side dev
(p12a), HOLDOUT_REAL_DATASETS on side holdout (p12b), luna conversations only; it needs its own --out, never
p8_dryrun.md). Neither is run by p8. Fake answers on the hold-out need --count-only (a full fake run would also
read the hold-out's saved judge fact names).
`--workers N` (p12 step 0): N threads, one conversation per task, with one shared answer store and one shared
budget per pass (each (question, input) key asked once; once the budget stop fires no new call starts); counts are
added in conversation order, so the report is the same for any N (apart from the time). --limit-convs works with it.

Run from predicate_correctness/ (the runner copy's modules need the venv):
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v3_p8_dryrun \\
        > output/logs/v3_p8_<nn>_dryrun.log 2>&1
main() first calls state_tracker.v3.frozen.check_manifest(). Writes output/eval_v3/p8_dryrun.md (--out). Never
imports gold code or another scoring module.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import os
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from state_tracker import paths                                   # noqa: E402
from state_tracker.v3 import facts_format_v3 as F                 # noqa: E402
from state_tracker.v3 import questions as Q                       # noqa: E402

STRONG_DATASETS = ("stage_a.luna.tgr_frozen", "stage_a.luna.tgr_tracker", "ours.p10_luna_train",
                   "partner.luna_train_v5")
WEAK_DATASETS = ("stage_a.nano.tgr_frozen", "stage_a.nano.tgr_tracker", "ours.p10_nano_train", "partner.nano_train")
DEV_DATASETS = STRONG_DATASETS + WEAK_DATASETS + ("stage_b",)
PAID_DATASETS = STRONG_DATASETS                     # p12: the strong-agent development data (Stage B keeps the stand-in)
TASK99_DATASETS = ("ours.p10_luna_train", "partner.luna_train_v5")
HOLDOUT_DATASETS = ("ours.p10_luna_val", "partner.luna_val", "stage_b")
HOLDOUT_REAL_DATASETS = HOLDOUT_DATASETS            # p12b: the strong agent's val runs and the Stage B tries forked
#                                                     from them (side "holdout" only; real mode keeps the luna agent)
STRONG_AGENT, WEAK_AGENT = "luna", "nano"
PASSES = ("every_yes_exh", "every_no", "lazy_yes", "lazy_no")
UPPER = ("every_yes_exh", "every_no")
OUTPUT_TOKENS = {"low": 40, "point": 120, "high": 300}            # assumption per call (low effort, a short JSON)
P12_HIGH_PER_CALL = 0.0003                                        # p12.md: the high estimate per call, in $
P12_MIN_LIMIT = 10.0
FOCUS_FACTS = {                                                   # the p4 audit's main too-strict facts (coordinator)
    "retail": ("agent_reminded_user_to_include_all_items_for_exchange",
               "agent_reminded_user_to_include_all_items_for_modification",
               "user_explicitly_confirmed_pending_action", "user_chose_price_difference_payment_method"),
}
DRYRUN_MD = os.path.join(paths.OUTPUT_DIR, "eval_v3", "p8_dryrun.md")
JUDGE_CACHE_GLOB = os.path.join(paths.OUTPUT_DIR, "_llmcache", "v2_stage_a_luna", "*", "structured", "*", "*.json")


class NotReady(RuntimeError):
    """A fact the dry run needs has a part without an expression, or a name no module registered yet."""


# ----------------------------------------------------------------------------------------------- rules and facts

def load_rule_table(domain: str) -> dict:
    with open(F.rule_table_path(domain), encoding="utf-8") as f:
        return json.load(f)


class Rules:
    """The rule table of one domain: which facts each action needs, and whether a rule is already decided."""

    def __init__(self, table: dict):
        self.rules = table["rules"]
        self.by_action: Dict[str, List[dict]] = collections.defaultdict(list)
        for r in self.rules:
            for a in r["actions"]:
                self.by_action[a].append(r)

    def facts_for(self, tool: str) -> List[str]:
        return sorted({f for r in self.by_action.get(tool, []) for f in r["facts"]})

    def rules_for(self, tool: str) -> List[dict]:
        return list(self.by_action.get(tool, []))

    @staticmethod
    def decided(rule: dict, known: Dict[str, bool], tool: str) -> bool:
        """True when every row of the rule (for this action) that fits the known values gives the same result."""
        rows = [r for r in rule["rows"] if r.get("action") in (None, tool)]
        fit = {r["holds"] for r in rows if all(known.get(f, v) == v for f, v in r["values"].items())}
        return len(fit) <= 1

    def needed(self, fact: str, known: Dict[str, bool], tool: str) -> bool:
        """A fact is needed while one rule of the action that holds it is not decided by the known facts."""
        return any(fact in r["facts"] and not self.decided(r, known, tool) for r in self.rules_for(tool))


def question_parts(entry: dict) -> List[str]:
    return [pid for pid, p in entry["parts"].items() if p.get("source") == "question"]


def has_question(entry: dict) -> bool:
    return bool(question_parts(entry))


def readiness(docs: Dict[str, dict], tables: Dict[str, "Rules"]) -> List[str]:
    """Problems that stop the run: a fact of a rule with a part not written or a name not registered."""
    out = []
    for d, doc in docs.items():
        needed = {f for r in tables[d].rules for f in r["facts"]}
        for name in sorted(needed):
            e = doc["facts"].get(name)
            if e is None:
                out.append(f"{d}: fact {name} is not in the fact file")
                continue
            try:
                F.compile_entry(e, name, F.L.domain_kinds(d))
            except F.NotDefinedYet as x:
                out.append(f"{d}: {x}")
            except F.L.LookupFormatError as x:
                out.append(f"{d}: {name}: {x}")
    return out


def questions_reach_check(docs: Dict[str, dict]) -> List[str]:
    """For every fact: the question parts that some assignment of part values makes the evaluator run must all be
    run under all-true or all-false question answers (with any code values). Returns the facts where not."""
    bad = []
    for d, doc in docs.items():
        for name, e in doc["facts"].items():
            qs = question_parts(e)
            if not qs:
                continue
            tree = F.parse_combine(e["combine"])
            order = F.combine_ids(tree)
            codes = [p for p in order if p not in qs]
            for bits in range(2 ** len(codes)):
                code_vals = {p: bool(bits >> i & 1) for i, p in enumerate(codes)}
                reach_any: Set[str] = set()
                for qbits in range(2 ** len(qs)):
                    reach_any |= _run_order(tree, order, code_vals, {p: bool(qbits >> i & 1) for i, p in enumerate(qs)})
                ext = _run_order(tree, order, code_vals, {p: True for p in qs}) | \
                    _run_order(tree, order, code_vals, {p: False for p in qs})
                if reach_any - ext:
                    bad.append(f"{d}: {name}: parts {sorted(reach_any - ext)} (code {code_vals})")
                    break
    return bad


def _run_order(tree: tuple, order: List[str], code_vals: Dict[str, bool], q_vals: Dict[str, bool]) -> Set[str]:
    """The question parts the evaluator's resolve() runs (facts_format_v3._Pass.resolve, same pick rule)."""
    known = dict(code_vals)
    ran: Set[str] = set()
    while True:
        v = F.combine_value(tree, known)
        if v is not None:
            return ran
        unknown = [p for p in order if p not in known]
        pick = next((p for p in unknown if F.combine_value(tree, dict(known, **{p: True}))
                     != F.combine_value(tree, dict(known, **{p: False}))), unknown[0])
        ran.add(pick)
        known[pick] = q_vals[pick]


# ----------------------------------------------------------------------------------------------- cases

@dataclass
class Case:
    """One guard check: what the counting needs."""
    dataset: str
    conv_key: str
    agent: str
    domain: str
    tool: str
    args: Dict[str, Any]
    state: Any
    view: Any
    judge_names: Optional[Set[str]] = None          # the saved judge's fact names (dev, frozen sources; else None)


def _view_builder() -> Callable[..., Any]:
    from state_tracker.v3 import message_view as MV                 # p7 (registers the structure helpers)
    return MV.build_view


def warm_up(docs: Dict[str, dict]) -> None:
    """Fill the per-process caches once, in this thread, before the worker threads start (τ-bench's start data,
    the info-class index, the questions file, the view's normalization)."""
    from state_tracker.v3 import info_classes as IC
    from state_tracker.v3 import message_view as MV
    for d in docs:
        MV._initial_db(d)
        IC.base_index(d)
    Q.load_questions()
    Q.normalize_text("warm up")


def import_helper_modules() -> List[str]:
    """Import every module that registers fact helpers: p6 (code_helpers), p7 (message_view, info_classes), p8."""
    import importlib
    done = []
    for m in ("state_tracker.v3.code_helpers", "state_tracker.v3.message_view", "state_tracker.v3.info_classes",
              "state_tracker.v3.questions"):
        importlib.import_module(m)
        done.append(m)
    return done


def side_conversations(datasets: Sequence[str], side: str, *, limit_convs: Optional[int] = None,
                       counts: Optional[collections.Counter] = None, agent: Optional[str] = None) -> Iterator[Any]:
    """The saved conversations of the data sets on one side (dev or holdout); the first limit_convs of each data set.
    agent: only that agent's conversations (real mode: the strong agent), the others counted as skipped."""
    from fork import offline_v3 as OV                               # the offline base (sets up the runner path)
    n_conv: collections.Counter = collections.Counter()
    for conv in OV.iter_conversations(datasets):
        if conv.side != side:
            if counts is not None:
                counts[f"conversations of the other side skipped ({conv.side})"] += 1
            continue
        if agent is not None and conv.agent != agent:
            if counts is not None:
                counts[f"conversations of another agent skipped ({conv.agent})"] += 1
            continue
        n_conv[conv.dataset] += 1
        if limit_convs is not None and n_conv[conv.dataset] > limit_convs:
            continue
        yield conv


def conv_cases(conv: Any, side: str, build_view: Callable[..., Any], *, read_judge_names: bool = True,
               verify: int = 0) -> Iterator[Case]:
    """The saved checks of one conversation, one Case per check. States come from one walk (state.walk; the same
    State object changes after each yield, so a conversation is evaluated by one thread, in order); the first
    `verify` checks are compared with build_state."""
    from fork import offline_v3 as OV
    from state_tracker import state as S
    checks = list(conv.checks())
    executed = conv.ep["executed"]
    by_len: Dict[int, List[Any]] = collections.defaultdict(list)
    for c in checks:
        by_len[len(c.history)].append(c)
    verified = 0
    for n, st in S.walk(executed, conv.domain, stops=sorted(by_len)):
        for c in by_len[n]:
            assert c.side == side, c.ckey
            tool, args = OV.call_of(c.msg)
            st.pending = S.normalize_action({"tool": tool, "args": args})
            if verified < verify:
                ref = c.state()
                if ref.db != st.db or len(ref.events) != len(st.events):
                    raise RuntimeError(f"{c.ckey}: the walked state differs from build_state")
                verified += 1
            view = build_view(c.history, pending={"tool": tool, "args": args}, state=st, domain=conv.domain)
            names = None
            if read_judge_names and side == OV.DEV and conv.source_guard == "frozen":
                j = c.saved.get("judge")
                names = set(j) if isinstance(j, dict) and j else None
            yield Case(conv.dataset, conv.conv_key, conv.agent, conv.domain, tool, args, st, view, names)


def iter_cases(datasets: Sequence[str], side: str, *, limit_convs: Optional[int] = None,
               read_judge_names: bool = True, verify_states: int = 0,
               counts: Optional[collections.Counter] = None, agent: Optional[str] = None) -> Iterator[Case]:
    """The saved checks of the data sets, one Case per check, on one side (dev or holdout; asserted). The first
    verify_states checks (in conversation order) are compared with build_state."""
    build_view = _view_builder()
    left = verify_states
    for conv in side_conversations(datasets, side, limit_convs=limit_convs, counts=counts, agent=agent):
        quota = min(left, len(conv.check_indices()))
        left -= quota
        yield from conv_cases(conv, side, build_view, read_judge_names=read_judge_names, verify=quota)


def conversation_units(datasets: Sequence[str], side: str, *, limit_convs: Optional[int] = None,
                       read_judge_names: bool = True, verify_states: int = 0,
                       counts: Optional[collections.Counter] = None, agent: Optional[str] = None
                       ) -> Tuple[Iterator[Tuple[Any, int]], Callable[[Tuple[Any, int]], Iterator[Case]]]:
    """For run_parallel: (units, cases_of). A unit is (conversation, its state-check quota); the quotas are the same
    as iter_cases' (the first verify_states checks in conversation order), so the work does not depend on threads."""
    build_view = _view_builder()

    def units() -> Iterator[Tuple[Any, int]]:
        left = verify_states
        for conv in side_conversations(datasets, side, limit_convs=limit_convs, counts=counts, agent=agent):
            quota = min(left, len(conv.check_indices()))
            left -= quota
            yield conv, quota

    def cases_of(unit: Tuple[Any, int]) -> Iterator[Case]:
        conv, quota = unit
        return conv_cases(conv, side, build_view, read_judge_names=read_judge_names, verify=quota)

    return units(), cases_of


# ----------------------------------------------------------------------------------------------- counting

class Acc:
    """What a pass asked, per conversation, question and fact: the pass's totals, or (with --workers) one
    conversation's part, made by one thread and added to the totals in conversation order."""

    def __init__(self):
        self.conv_keys: Dict[str, Set[str]] = collections.defaultdict(set)
        self.conv_qid: Dict[str, Dict[str, Set[str]]] = collections.defaultdict(lambda: collections.defaultdict(set))
        self.fact_keys: Dict[str, Set[str]] = collections.defaultdict(set)
        self.conv_fact: Dict[str, Dict[str, Set[str]]] = collections.defaultdict(lambda: collections.defaultdict(set))
        self.fact_asks: collections.Counter = collections.Counter()
        self.key_qid: Dict[str, str] = {}
        self.evaluated: collections.Counter = collections.Counter()      # fact evaluations
        self.skipped: collections.Counter = collections.Counter()        # question facts no rule needed (lazy)
        self.problems: collections.Counter = collections.Counter()       # (fact, kind)
        self.errors: collections.Counter = collections.Counter()         # (fact, error type)
        self._conv: Optional[str] = None

    def record(self, key: str, qid: str, fact: Optional[str]) -> None:
        self.conv_keys[self._conv].add(key)
        self.conv_qid[self._conv][qid].add(key)
        self.key_qid[key] = qid
        if fact is not None:
            self.fact_keys[fact].add(key)
            self.conv_fact[self._conv][fact].add(key)
            self.fact_asks[fact] += 1

    def add(self, other: "Acc") -> None:
        """Add another part (sets: union; counts: sums), keeping first-seen order as a sequential run would."""
        for c, ks in other.conv_keys.items():
            self.conv_keys[c] |= ks
        for c, d in other.conv_qid.items():
            for q, ks in d.items():
                self.conv_qid[c][q] |= ks
        for f, ks in other.fact_keys.items():
            self.fact_keys[f] |= ks
        for c, d in other.conv_fact.items():
            for f, ks in d.items():
                self.conv_fact[c][f] |= ks
        self.key_qid.update(other.key_qid)
        for name in ("fact_asks", "evaluated", "skipped", "problems", "errors"):
            getattr(self, name).update(getattr(other, name))


class PassCounter(Acc):
    """One pass: its answers hook, and what it asked, per conversation, question and fact."""

    def __init__(self, name: str, backend: Any, lazy: bool, doc: Optional[dict] = None, store: Any = None):
        super().__init__()
        self.name = name
        self.lazy = lazy
        self.hook = Q.Questions(backend, store, doc=doc)
        self.hook.on_ask = self._on_ask
        self._tl = threading.local()            # with --workers: this thread's part (an Acc), else the pass itself

    def acc(self) -> Acc:
        sink = getattr(self._tl, "sink", None)
        return self if sink is None else sink

    def _on_ask(self, key: str, qid: str, fact: Optional[str], part: Optional[str], cached: bool) -> None:
        self.acc().record(key, qid, fact)

    def chars(self) -> Dict[str, int]:
        return {e["key"]: e["chars"] for e in self.hook.log}


def default_passes(doc: Optional[dict] = None) -> List[PassCounter]:
    return [PassCounter("every_yes_exh", Q.FakeBackend("yes", exhaustive=True), lazy=False, doc=doc),
            PassCounter("every_no", Q.FakeBackend("no"), lazy=False, doc=doc),
            PassCounter("lazy_yes", Q.FakeBackend("yes"), lazy=True, doc=doc),
            PassCounter("lazy_no", Q.FakeBackend("no"), lazy=True, doc=doc)]


@dataclass
class Totals:
    conversations: Dict[str, Dict[str, Any]] = field(default_factory=dict)     # conv_key -> meta
    checks: collections.Counter = field(default_factory=collections.Counter)   # dataset -> checks
    question_checks: collections.Counter = field(default_factory=collections.Counter)
    code_problems: collections.Counter = field(default_factory=collections.Counter)
    code_errors: collections.Counter = field(default_factory=collections.Counter)
    judge_names: collections.Counter = field(default_factory=collections.Counter)


class Cancelled(RuntimeError):
    """A worker stopped early: another worker hit a hard stop (its own error is the one reported)."""


HARD_STOPS = (Q.BudgetExceeded, Q.NetworkBlocked, Q.RealModeRefused)


def run_cases(cases: Iterable[Case], docs: Dict[str, dict], tables: Dict[str, Rules],
              passes: Sequence[PassCounter], totals: Optional[Totals] = None,
              progress: Optional[Callable[[int], None]] = None,
              stop: Optional[threading.Event] = None) -> Totals:
    """Evaluate the facts of every case under every pass; code-only facts once per case (no answers hook).
    stop (run_parallel): set by another worker after a hard stop; this one then stops before its next case."""
    totals = totals or Totals()
    for i, c in enumerate(cases):
        if stop is not None and stop.is_set():
            raise Cancelled("stopped: another worker hit a hard stop")
        totals.conversations.setdefault(c.conv_key, {"dataset": c.dataset, "agent": c.agent, "domain": c.domain})
        totals.checks[c.dataset] += 1
        rules = tables[c.domain]
        doc = docs[c.domain]
        names = rules.facts_for(c.tool)
        if c.judge_names is not None:
            totals.judge_names["equal" if set(names) == c.judge_names else "differ"] += 1
        if not names:
            continue
        code_known: Dict[str, bool] = {}
        qfacts = []
        for name in names:
            e = doc["facts"][name]
            if has_question(e):
                qfacts.append(name)
                continue
            try:
                r = F.evaluate(e, c.state, c.args, view=c.view, answers=None, name=name)
            except Exception as x:                       # noqa: BLE001 - counted, reported (another part's code)
                totals.code_errors[(name, type(x).__name__)] += 1
                continue
            code_known[name] = r["value"]
            for p in r["problems"]:
                totals.code_problems[(name, p["kind"])] += 1
        if qfacts:
            totals.question_checks[c.dataset] += 1
        for ps in passes:
            acc = ps.acc()                               # the pass itself, or this thread's part (--workers)
            acc._conv = c.conv_key
            ps.hook.where = c.conv_key                   # per thread
            known = dict(code_known)
            for name in qfacts:
                if ps.lazy and not rules.needed(name, known, c.tool):
                    acc.skipped[name] += 1
                    continue
                acc.evaluated[name] += 1
                try:
                    r = F.evaluate(doc["facts"][name], c.state, c.args, view=c.view, answers=ps.hook, name=name)
                except HARD_STOPS:
                    raise
                except Exception as x:                   # noqa: BLE001 - counted, reported
                    acc.errors[(name, type(x).__name__)] += 1
                    continue
                known[name] = r["value"]
                for p in r["problems"]:
                    acc.problems[(name, p["kind"])] += 1
        if progress is not None:
            progress(i + 1)
    return totals


def merge_totals(dst: Totals, src: Totals) -> None:
    for k, m in src.conversations.items():
        dst.conversations.setdefault(k, m)
    for name in ("checks", "question_checks", "code_problems", "code_errors", "judge_names"):
        getattr(dst, name).update(getattr(src, name))


def _stop_budgets(passes: Sequence[PassCounter], why: str) -> None:
    for ps in passes:
        b = getattr(ps.hook.backend, "budget", None)
        if b is not None:
            b.stop(why)


def run_parallel(units: Iterable[Any], cases_of: Callable[[Any], Iterable[Case]], docs: Dict[str, dict],
                 tables: Dict[str, Rules], passes: Sequence[PassCounter], workers: int,
                 totals: Optional[Totals] = None, progress: Optional[Callable[[int], None]] = None,
                 window: Optional[int] = None) -> Totals:
    """run_cases with `workers` threads, one unit (a conversation) per task. The passes' hooks are shared: one
    answer store and one budget per pass; a (question, input) key is asked once even when two threads need it at
    the same time (questions.Questions waits for the first). Each unit's counts are made by its thread in a part
    of its own and added to the totals in unit order, so the summaries (and the report) are the same as with one
    worker. A hard stop (the budget, the network block, real mode refused) in one worker sets the stop: the
    budget stop stays fired (no new call starts), the other workers stop before their next check, no new unit
    starts, and the first hard stop is raised here. Units are read in this thread, at most `window` ahead."""
    totals = totals or Totals()
    stop = threading.Event()
    window = window or max(2, 4 * workers)
    done = {"checks": 0}
    first: List[BaseException] = []

    def work(unit: Any) -> Tuple[Totals, List[Acc]]:
        parts = [Acc() for _ in passes]
        for ps, part in zip(passes, parts):
            ps._tl.sink = part
        try:
            t = run_cases(cases_of(unit), docs, tables, passes, Totals(), stop=stop)
        except BaseException as e:
            if not isinstance(e, Cancelled):
                stop.set()
                _stop_budgets(passes, f"stopped after {type(e).__name__} in another worker: {e}")
            raise
        finally:
            for ps in passes:
                ps._tl.sink = None
        return t, parts

    def take(fut: Any) -> None:
        try:
            t, parts = fut.result()
        except Cancelled:
            return
        except BaseException as e:                       # noqa: BLE001 - kept, raised after the drain
            first.append(e)
            return
        if stop.is_set():
            return                                       # after a stop, the report is not written anyway
        merge_totals(totals, t)
        for ps, part in zip(passes, parts):
            ps.add(part)
        done["checks"] += sum(t.checks.values())
        if progress is not None:
            progress(done["checks"])

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="p12w") as ex:
        pending: collections.deque = collections.deque()
        try:
            for u in units:
                if stop.is_set():
                    break
                pending.append(ex.submit(work, u))
                while len(pending) >= window:
                    take(pending.popleft())
        finally:
            if sys.exc_info()[0] is not None:            # reading the units failed: stop the workers
                stop.set()
            while pending:
                take(pending.popleft())
    if first:
        hard = [e for e in first if isinstance(e, HARD_STOPS)]
        raise (hard or first)[0]
    return totals


# ----------------------------------------------------------------------------------------------- summaries

def dist(xs: List[int]) -> Dict[str, Any]:
    """n, mean, median, p90, max, sum, and with_any (how many are > 0)."""
    if not xs:
        return {"n": 0, "mean": 0.0, "median": 0, "p90": 0, "max": 0, "sum": 0, "with_any": 0}
    s = sorted(xs)
    return {"n": len(s), "mean": round(sum(s) / len(s), 2), "median": statistics.median(s),
            "p90": s[min(len(s) - 1, int(math.ceil(0.9 * len(s))) - 1)], "max": s[-1], "sum": sum(s),
            "with_any": sum(1 for x in s if x > 0)}


def group_convs(totals: Totals, group: str) -> List[str]:
    out = []
    for k, m in totals.conversations.items():
        ds, agent = m["dataset"], m["agent"]
        if group == "all" or group == ds \
                or (group == "strong" and agent == STRONG_AGENT) or (group == "weak" and agent == WEAK_AGENT) \
                or (group == "paid" and agent == STRONG_AGENT and ds in PAID_DATASETS) \
                or (group == "task99" and ds in TASK99_DATASETS):
            out.append(k)
    return out


def keys_of(passes: Dict[str, PassCounter], names: Sequence[str], convs: Iterable[str]) -> Set[str]:
    out: Set[str] = set()
    for c in convs:
        for n in names:
            out |= passes[n].conv_keys.get(c, set())
    return out


def per_conv(passes: Dict[str, PassCounter], names: Sequence[str], convs: Iterable[str],
             qid: Optional[str] = None) -> List[int]:
    xs = []
    for c in convs:
        ks: Set[str] = set()
        for n in names:
            ks |= (passes[n].conv_qid.get(c, {}).get(qid, set()) if qid else passes[n].conv_keys.get(c, set()))
        xs.append(len(ks))
    return xs


def by_qid(passes: Dict[str, PassCounter], names: Sequence[str], keys: Set[str]) -> Dict[str, int]:
    kq: Dict[str, str] = {}
    for n in names:
        kq.update(passes[n].key_qid)
    c = collections.Counter(kq[k] for k in keys)
    return {q: c[q] for q in sorted(c, key=Q._qkey)}


def fit_tokens(sample: int = 600, seed: int = 0) -> Optional[Dict[str, float]]:
    """tokens = b x characters (least squares through zero; a = 0), on saved gpt-6-luna judge prompts (Stage A,
    development data): only the prompt length and the reported input tokens are read. The judge prompts are long and
    hold JSON, so this ratio is on the high side for the short tiny prompts. None when no record is there."""
    files = sorted(glob.glob(JUDGE_CACHE_GLOB))
    if not files:
        return None
    rng = random.Random(seed)
    pick = files if len(files) <= sample else rng.sample(files, sample)
    xs, ys = [], []
    for p in pick:
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            if (d.get("params") or {}).get("model") != "gpt-6-luna":
                continue
            xs.append(len(d.get("system") or "") + len(d.get("user") or ""))
            ys.append(float(d["usage"]["input_tokens"]))
        except (ValueError, KeyError, TypeError, OSError):
            continue
    if len(xs) < 20:
        return None
    sxx = sum(x * x for x in xs)
    b = sum(x * y for x, y in zip(xs, ys)) / sxx if sxx else 0.25
    return {"a": 0.0, "b": round(b, 6), "n": len(xs), "chars_per_token": round(1 / b, 3) if b else None,
            "chars_range": [min(xs), max(xs)]}


def cost_of(n_calls: int, input_tokens: float, price: Dict[str, float]) -> Dict[str, float]:
    out = {}
    for k, ot in OUTPUT_TOKENS.items():
        out[k] = round(input_tokens * price["input_per_m"] / 1e6 + n_calls * ot * price["output_per_m"] / 1e6, 4)
    return out


def summarize(totals: Totals, passes: Sequence[PassCounter], fit: Optional[Dict[str, float]],
              price: Dict[str, float], groups: Sequence[str]) -> Dict[str, Any]:
    P = {p.name: p for p in passes}
    chars: Dict[str, int] = {}
    for p in passes:
        chars.update(p.chars())
    have_upper = all(n in P for n in UPPER)
    modes = ([("upper", list(UPPER))] if have_upper else []) + [(n, [n]) for n in P]
    out: Dict[str, Any] = {"groups": {}, "by_fact": {}, "network_events": len(Q.network_events()),
                           "passes": {p.name: {"lazy": p.lazy, "backend": p.hook.backend.name,
                                               "exhaustive": p.hook.exhaustive} for p in passes},
                           "token_fit": fit, "price": price, "output_tokens_assumed": OUTPUT_TOKENS}
    for g in groups:
        convs = group_convs(totals, g)
        if not convs:
            continue
        row: Dict[str, Any] = {"conversations": len(convs), "checks": _checks_of(totals, convs), "modes": {}}
        for mode, names in modes:
            ks = keys_of(P, names, convs)
            ch = sum(chars.get(k, 0) for k in ks)
            tin_est = sum((chars.get(k, 0) + 3) // 4 for k in ks)          # = questions.estimate_tokens
            tin_cal = sum(fit["a"] + fit["b"] * chars.get(k, 0) for k in ks) if fit else None
            pc = per_conv(P, names, convs)
            row["modes"][mode] = {
                "calls": len(ks), "calls_sum_per_conversation": sum(pc), "per_conversation": dist(pc),
                "by_question": by_qid(P, names, ks),
                "per_conversation_by_question": {q: dist(per_conv(P, names, convs, q))
                                                 for q in by_qid(P, names, ks)},
                "prompt_chars": ch, "input_tokens_estimate": tin_est,
                "input_tokens_calibrated": round(tin_cal) if tin_cal is not None else None,
                "cost_estimate_usd": cost_of(len(ks), tin_est, price),
                "cost_calibrated_usd": cost_of(len(ks), tin_cal, price) if tin_cal is not None else None,
                "p12_high_usd": round(len(ks) * P12_HIGH_PER_CALL, 4),
                "p12_hard_limit_usd": round(max(P12_MIN_LIMIT, 2 * len(ks) * P12_HIGH_PER_CALL), 2),
            }
        out["groups"][g] = row
    for mode, names in modes:
        facts = sorted(set().union(*[set(P[n].fact_keys) for n in names]))
        out["by_fact"][mode] = {f: {"keys": len(set().union(*[P[n].fact_keys.get(f, set()) for n in names])),
                                    "asks": sum(P[n].fact_asks[f] for n in names),
                                    "evaluated": sum(P[n].evaluated[f] for n in names),
                                    "skipped_lazy": sum(P[n].skipped[f] for n in names)} for f in facts}
    out["by_fact_group"] = {}
    for g in ("paid", "strong", "weak"):
        convs = group_convs(totals, g)
        if not convs:
            continue
        out["by_fact_group"][g] = {}
        for mode, names in modes:
            per: Dict[str, Set[str]] = collections.defaultdict(set)
            per_conv_fact: Dict[str, List[int]] = collections.defaultdict(list)
            for c in convs:
                cf: Dict[str, Set[str]] = collections.defaultdict(set)
                for n in names:
                    for f, ks in P[n].conv_fact.get(c, {}).items():
                        cf[f] |= ks
                for f, ks in cf.items():
                    per[f] |= ks
                    per_conv_fact[f].append(len(ks))
            out["by_fact_group"][g][mode] = {
                f: {"keys": len(ks), "conversations": len(per_conv_fact[f]),
                    "per_conversation": dist(per_conv_fact[f] + [0] * (len(convs) - len(per_conv_fact[f])))}
                for f, ks in sorted(per.items())}
    out["problems"] = {p.name: {f"{f}: {k}": n for (f, k), n in sorted(p.problems.items())} for p in passes}
    out["errors"] = {p.name: {f"{f}: {k}": n for (f, k), n in sorted(p.errors.items())} for p in passes}
    out["code_problems"] = {f"{f}: {k}": n for (f, k), n in sorted(totals.code_problems.items())}
    out["code_errors"] = {f"{f}: {k}": n for (f, k), n in sorted(totals.code_errors.items())}
    out["judge_names"] = dict(totals.judge_names)
    out["checks_by_dataset"] = dict(totals.checks)
    out["question_checks_by_dataset"] = dict(totals.question_checks)
    out["unclear_values"] = {p.name: {q: n for q, n in sorted(p.hook.stats.blocking.items(), key=lambda x: Q._qkey(x[0]))
                                      if n} for p in passes}             # sorted: the same with any thread order
    return out


def _checks_of(totals: Totals, convs: List[str]) -> int:
    ds = collections.Counter(totals.conversations[c]["dataset"] for c in convs)
    full = {d for d in ds if sum(1 for m in totals.conversations.values() if m["dataset"] == d) == ds[d]}
    if full == set(ds):
        return sum(totals.checks[d] for d in ds)
    return -1                                          # a group that splits a data set (Stage B by agent)


# ----------------------------------------------------------------------------------------------- the report

def _money(x: Optional[Dict[str, float]]) -> str:
    if not x:
        return "-"
    return f"${x['low']:.4f} / ${x['point']:.4f} / ${x['high']:.4f}"


def render_md(numbers: Dict[str, Any], meta: Dict[str, Any]) -> str:
    L: List[str] = []
    w = L.append
    w("# Tracker v3, part 8: the tiny questions, dry run (fake answers, $0)")
    w("")
    w(f"Written by `scoring/v3_p8_dryrun.py` on {meta['when']}. No LLM call, no network: the audit hook refused "
      f"{numbers['network_events']} network attempts (P8.2 pass mark: 0 events). Side: **{meta['side']}**. Data sets: "
      f"{', '.join(meta['datasets'])}. Manifest: {meta['manifest']}.")
    w("")
    w("Passes: `every_yes_exh` and `every_no` evaluate every fact of the matched rules (fake yes with valid quotes and "
      "every candidate asked; fake no); **upper** = the questions of both together (the budget count). `lazy_yes` / "
      "`lazy_no` ask only for facts a rule still needs and stop at the first yes. Calls = distinct (question, input) "
      "keys: each is asked once and saved, also across conversations.")
    w("")
    w("## Calls per group")
    w("| group | conv. | checks | mode | calls | per conv. mean / median / p90 / max | input tokens (estimate) | "
      "calibrated | cost low / point / high (estimate) |")
    w("|---|---|---|---|---|---|---|---|---|")
    for g, row in numbers["groups"].items():
        for mode, m in row["modes"].items():
            pc = m["per_conversation"]
            w(f"| {g} | {row['conversations']} | {row['checks'] if row['checks'] >= 0 else '-'} | {mode} | "
              f"{m['calls']} | {pc['mean']} / {pc['median']} / {pc['p90']} / {pc['max']} | "
              f"{m['input_tokens_estimate']} (estimate) | {m['input_tokens_calibrated']} | "
              f"{_money(m['cost_estimate_usd'])} |")
    w("")
    w("## Calls per question (upper bound; and lazy yes / lazy no)")
    for g in ("paid", "strong", "weak"):
        row = numbers["groups"].get(g)
        if not row:
            continue
        w(f"### {g} ({row['conversations']} conversations)")
        w("| question | upper | lazy_yes | lazy_no | per conv. (upper) mean / max | conv. asking it (upper / lazy_yes) |")
        w("|---|---|---|---|---|---|")
        up = row["modes"].get("upper", {})
        ly = row["modes"].get("lazy_yes", {})
        qs = sorted(set(up.get("by_question", {})) | set(ly.get("by_question", {})), key=Q._qkey)
        for q in qs:
            pcq = up.get("per_conversation_by_question", {}).get(q, {"mean": 0, "max": 0, "with_any": 0})
            pcl = ly.get("per_conversation_by_question", {}).get(q, {"with_any": 0})
            w(f"| {q} | {up.get('by_question', {}).get(q, 0)} | {ly.get('by_question', {}).get(q, 0)} | "
              f"{row['modes'].get('lazy_no', {}).get('by_question', {}).get(q, 0)} | {pcq['mean']} / {pcq['max']} | "
              f"{pcq['with_any']} / {pcl['with_any']} |")
        w("")
    w("## Calls per fact (distinct keys the fact asked; a key shared by two facts counts for both)")
    w("All = every development data set. Paid = the strong-agent conversations of p12 (Stage A luna, ours, the "
      "partner's train runs); per conversation = mean / p90 / max over all paid conversations (0 where the fact asked "
      "nothing).")
    w("")
    w("| fact | all: upper | all: lazy_yes | paid: upper | paid: upper per conv. | paid: lazy_yes | paid: lazy_no | "
      "weak: upper | all: lazy skipped (yes) |")
    w("|---|---|---|---|---|---|---|---|---|")
    bf = numbers["by_fact"]
    bg = numbers.get("by_fact_group", {})
    focus = {f for fs in FOCUS_FACTS.values() for f in fs}

    def gk(g: str, mode: str, f: str, what: str = "keys") -> Any:
        return bg.get(g, {}).get(mode, {}).get(f, {}).get(what, 0)

    for f in sorted(set().union(*[set(v) for v in bf.values()]) if bf else []):
        u = bf.get("upper", {}).get(f, {})
        ly = bf.get("lazy_yes", {}).get(f, {})
        pc = gk("paid", "upper", f, "per_conversation") or {"mean": 0, "p90": 0, "max": 0}
        mark = " **(p4 focus)**" if f in focus else ""
        w(f"| {f}{mark} | {u.get('keys', 0)} | {ly.get('keys', 0)} | {gk('paid', 'upper', f)} | "
          f"{pc['mean']} / {pc['p90']} / {pc['max']} | {gk('paid', 'lazy_yes', f)} | {gk('paid', 'lazy_no', f)} | "
          f"{gk('weak', 'upper', f)} | {ly.get('skipped_lazy', 0)} |")
    w("")
    w("## Problems and errors")
    w(f"- question facts, problems by pass (unclear, missing argument, ...): `{json.dumps(numbers['problems'])}`")
    w(f"- question facts, errors by pass: `{json.dumps(numbers['errors'])}`")
    w(f"- code-only facts: problems `{json.dumps(numbers['code_problems'])}`, errors "
      f"`{json.dumps(numbers['code_errors'])}`")
    w(f"- unclear values raised by the question helpers: `{json.dumps(numbers['unclear_values'])}` (0 expected with "
      f"fake yes / no)")
    w(f"- facts of the matched rules vs the saved judge's fact names (frozen sources, names only): "
      f"`{json.dumps(numbers['judge_names'])}`")
    w(f"- combine shapes: question parts reachable only by mixed answers: {meta['reach'] or 'none'}")
    w("")
    w("## Cost basis")
    fit = numbers.get("token_fit")
    w(f"- price (logged list price): ${numbers['price']['input_per_m']} per 1M input tokens, "
      f"${numbers['price']['output_per_m']} per 1M output tokens (gpt-6-luna; reasoning tokens bill as output).")
    w("- input tokens: characters / 4 **(estimate)**: no tokenizer of the model is installed. "
      + (f"Calibrated: tokens = {fit['b']} x characters ({fit['chars_per_token']} characters per token), fitted "
         f"through zero on {fit['n']} saved gpt-6-luna judge prompts of Stage A ({fit['chars_range'][0]}-"
         f"{fit['chars_range'][1]} characters, JSON-heavy, so on the high side here)." if fit
         else "No calibration data found."))
    w(f"- output tokens per call: an assumption, low / point / high = {OUTPUT_TOKENS['low']} / "
      f"{OUTPUT_TOKENS['point']} / {OUTPUT_TOKENS['high']} (a short JSON answer at low effort).")
    w("")
    paid = numbers["groups"].get("paid", {}).get("modes", {}).get("upper")
    if paid:
        w("## Draft text for p12's approval request (the main chat writes approval_request.md)")
        w(f"- Calls: **{paid['calls']}** tiny questions (upper bound) on the strong-agent development data "
          f"({numbers['groups']['paid']['conversations']} conversations: Stage A gpt-6-luna, our and the partner's "
          f"train runs). The hold-out count is added by p12's request: same script, `--side holdout --count-only`.")
        w("- Model: gpt-6-luna, low effort (Q3). One call per (question, input); answers saved in "
          "`output/eval_v3/questions_answers.jsonl`.")
        w(f"- Cost: {_money(paid['cost_estimate_usd'])} (estimate; calibrated "
          f"{_money(paid['cost_calibrated_usd'])}); p12's high estimate (calls x $0.0003) = ${paid['p12_high_usd']:.2f}.")
        w(f"- Hard limit: **${paid['p12_hard_limit_usd']:.2f}** (2 x the high estimate, at least $10), and a call limit "
          f"of {int(paid['calls'] * 1.1) + 10} (the count + 10 %), enforced by questions.py's budget stop.")
        w("- Command (from predicate_correctness/, after the user's approval):")
        w("```")
        w("PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v3_p8_dryrun "
          "--answers real --approved \"<the user's approval words>\" "
          f"--max-usd {paid['p12_hard_limit_usd']:.2f} --max-calls {int(paid['calls'] * 1.1) + 10} "
          + (f"--limit-convs {numbers['limit_convs']} " if numbers.get("limit_convs") is not None else "")
          + "--workers 8 --out output/eval_v3/p12_answers_dev.md "
          "--datasets " + ",".join(PAID_DATASETS) + " > output/logs/v3_p12_<nn>_answers.log 2>&1")
        w("```")
        w("")
    w("## Numbers (JSON)")
    w("```json")
    w(json.dumps({k: v for k, v in numbers.items()}, indent=1, sort_keys=True, default=str))
    w("```")
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------------------------- main

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -B -m scoring.v3_p8_dryrun", description=__doc__.split("\n\n")[0])
    ap.add_argument("--datasets", help="comma list (default: every development data set)")
    ap.add_argument("--side", choices=("dev", "holdout"), default="dev")
    ap.add_argument("--count-only", action="store_true", help="hold-out: count calls only (required with --side "
                                                              "holdout)")
    ap.add_argument("--limit-convs", type=int, default=None, help="only the first N conversations of each data set "
                                                                  "(a quick test)")
    ap.add_argument("--verify-states", type=int, default=50, help="compare the first N walked states with "
                                                                  "build_state")
    ap.add_argument("--out", default=DRYRUN_MD)
    ap.add_argument("--facts-dir", help="read facts_v3_<domain>.json from this folder (a smoke test on a scratch "
                                        "merge before the main chat's merge; default: state_tracker/v3/)")
    ap.add_argument("--answers", choices=("fake", "real"), default="fake")
    ap.add_argument("--approved", help="real mode: the user's own approval words for this paid step")
    ap.add_argument("--max-usd", type=float, help="real mode: the dollar budget (hard stop)")
    ap.add_argument("--max-calls", type=int, help="real mode: the call budget (hard stop)")
    ap.add_argument("--workers", type=int, default=1, help="threads asking questions at the same time (one shared "
                                                           "answer store and budget; default 1: one at a time)")
    a = ap.parse_args(argv)
    if a.workers < 1 or a.workers > 32:
        ap.error("--workers must be between 1 and 32")
    if a.answers == "real" and a.count_only:
        ap.error("--count-only is a count with fake answers; it cannot be used with --answers real")
    if a.side == "holdout" and not a.count_only and a.answers != "real":
        # A fake-answer run of the hold-out without --count-only would also read the saved guard records (the
        # judge's fact names) and the problem tables of the hold-out; only the call count is allowed before p12b.
        ap.error("--side holdout needs --count-only (fake answers: a count of calls only) or --answers real (p12b)")
    if a.answers == "real" and os.path.abspath(a.out) == os.path.abspath(DRYRUN_MD):
        ap.error(f"real mode needs its own --out (not {os.path.relpath(DRYRUN_MD, PC_DIR)}, p8's frozen report), "
                 "e.g. --out output/eval_v3/p12_answers_<side>.md")
    return a


def main(argv: Optional[List[str]] = None) -> int:
    from state_tracker.v3.frozen import check_manifest
    manifest = check_manifest()
    a = parse_args(argv)
    if a.answers == "fake":
        Q.block_network()                                       # P8.2: every network socket is refused
    datasets = tuple(x for x in (a.datasets.split(",") if a.datasets else
                                 (DEV_DATASETS if a.side == "dev" else HOLDOUT_DATASETS)) if x)
    if a.answers == "real":
        allowed = PAID_DATASETS if a.side == "dev" else HOLDOUT_REAL_DATASETS
        bad = [d for d in datasets if d not in allowed]
        if bad:
            print(f"real answers only on the strong-agent data of side {a.side} {allowed}; refused: {bad}")
            return 2
        backend = Q.RealBackend(a.approved, a.max_usd, a.max_calls, log=print)   # refuses without the guards
    t0 = time.time()
    modules = import_helper_modules()
    docs = {d: F.load_facts(d, os.path.join(a.facts_dir, f"facts_v3_{d}.json") if a.facts_dir else None)
            for d in paths.DOMAINS}
    tables = {d: Rules(load_rule_table(d)) for d in paths.DOMAINS}
    problems = readiness(docs, tables)
    if problems:
        print(f"NOT READY: {len(problems)} facts cannot run yet (expressions of p6 / p7 / p8 not merged?)")
        for p in problems[:80]:
            print("  ", p)
        return 2
    reach = questions_reach_check(docs)
    if a.answers == "real":
        passes = [PassCounter("real", backend, lazy=False, store=Q.JsonlStore(Q.ANSWERS_PATH))]
    else:
        passes = default_passes()
    counts: collections.Counter = collections.Counter()
    last = {"n": 0}

    def tick(n: int) -> None:
        if n // 2000 > last["n"]:
            last["n"] = n // 2000
            print(f"{n} checks, {time.time() - t0:.0f} s, calls "
                  + ", ".join(f"{p.name} {len(p.hook.log)}" for p in passes), flush=True)

    # judge fact names are read on the development data only (never a saved guard record of the hold-out)
    kw = dict(limit_convs=a.limit_convs, read_judge_names=(a.side == "dev" and not a.count_only),
              verify_states=a.verify_states, counts=counts,
              agent=STRONG_AGENT if a.answers == "real" else None)
    try:
        if a.workers == 1:
            totals = run_cases(iter_cases(datasets, a.side, **kw), docs, tables, passes, progress=tick)
        else:
            warm_up(docs)
            units, cases_of = conversation_units(datasets, a.side, **kw)
            totals = run_parallel(units, cases_of, docs, tables, passes, a.workers, progress=tick)
    except Q.BudgetExceeded as e:                                 # real mode: the hard stop
        b = passes[0].hook.backend.budget
        print(f"STOPPED by the budget: {e}. Spent ${b.spent:.4f} (list price) in {b.calls} calls; answers saved so "
              f"far stay in {Q.ANSWERS_REL}. No report written.")
        return 3
    groups = (["all", "strong", "weak", "paid", "task99"] + list(datasets)) if a.side == "dev" else ["all"] + list(
        datasets)
    numbers = summarize(totals, passes, None if a.count_only else fit_tokens(), Q.load_questions()["price"], groups)
    numbers["skipped"] = dict(sorted(counts.items()))
    if a.limit_convs is not None:
        numbers["limit_convs"] = a.limit_convs
    if a.answers == "real":
        b = backend.budget
        numbers["real"] = {"calls": b.calls, "spent_usd_list_price": round(b.spent, 6), "max_usd": b.max_usd,
                           "max_calls": b.max_calls, "usage": dict(sorted(backend.usage.items())),
                           "answers_file": Q.ANSWERS_REL, "saved_answers": len(passes[0].hook.store),
                           "by_question": passes[0].hook.stats.as_dict(), "workers": a.workers}
    meta = {"when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "side": a.side, "datasets": list(datasets),
            "manifest": f"ok ({len(manifest)} entries)", "reach": reach, "modules": modules,
            "seconds": round(time.time() - t0, 1)}
    md = render_md(numbers, meta)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:                  # real mode: never p8's report (parse_args)
        f.write(md)
    print(md)
    ev = Q.network_events()
    print(f"network events: {len(ev)}; seconds {meta['seconds']}")
    return 0 if not ev else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
