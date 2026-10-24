"""R2 (eval v2, Part 4 reference): replay fakes for an end-to-end test of the fork branch runner. No LLM call.

Given one saved conversation (one line of an episodes.jsonl file), `ReplayFakes` gives fake callables with the same
signatures as the real ones. Each fake answers ONLY what is in the saved conversation, and raises `ReplayMiss` (with
the first difference) for anything else, so a wrong prefix, a wrong user list or a wrong judge prompt is caught.

  fake            replaces                                              answers
  ---------------------------------------------------------------------------------------------------------------
  fakes.agent     agent_completion (exp_core/models.py make_completion   the saved next agent message, when `messages`
                  ("agent"); episode.py calls it with messages=, tools=)  equals ep["messages"][:2 + 2*i] exactly
  fakes.user      tau_bench.envs.user.completion (LLMUserSimulationEnv   the saved next user reply, when `messages`
                  .generate_next_message calls it with messages=)        equals the rebuilt user list prefix exactly
  fakes.judge_    method_tgr.llm.structured (the only LLM call of TGR    the saved judge values of that guard check,
  structured      and TGR + tracker: TGR._judge, stage "tgr_judge")       found by the exact judge prompt (sha256)
  fakes.judge_llm an object with policy_pipeline.llm.LLM.call's          same, one level lower (for a runner that sets
                  signature (set as repro_runtime.calls._llm)            its own LLM object); no cache file is written

Judge values: frozen TGR records (partner runs, guard "tgr") give guard.judge (value + evidence). TGR + tracker
records give guard.tracker.judge_values (the judge's own values); the evidence of a value the tracker changed was not
saved (the guard shows the tracker's evidence for it anyway), so the fake returns a placeholder evidence for it,
UNLESS judge_cache_dir is given (our runs: output/_llmcache/<tag>/structured, read only): then the fake returns the
judge's full original answer from the cache (its values are checked against tracker.judge_values first). Use the
cache when frozen TGR must judge a TGR + tracker conversation (branch A of a source-2 fork): its block message shows
the judge's evidence.

Usage (venv Python, run from predicate_correctness/, never with user_strategy="llm"):

    from tests import audit_v2_replay_fakes as RF
    RF.block_network()                                  # optional: no socket can connect in this process
    ep = RF.load_line("output/online/p10_nano_train/retail/tgr_tracker/episodes.jsonl", 5)
    fakes = RF.ReplayFakes(ep, domain="retail", task_split="test",
                           judge_cache_dir=RF.judge_cache_for("p10_nano_train"))   # None for the partner's runs
    # (loose=True: accept message dicts without their None-valued keys, e.g. "tool_calls": None)
    with fakes.installed():                             # patches the user simulator's completion and the judge
        out = branch_runner(..., agent_completion=fakes.agent)      # e.g. fork/run_branch.py, from attempt i
    print(fakes.report())                               # calls answered, judge checks used
    print(RF.compare_episode(out_record, ep, from_attempt=i))       # messages / executed / attempts / reward equal?

To check a branch runner: run it from any attempt i of a saved conversation with the SAVED decision and the SOURCE
run's guard (frozen TGR for the partner's "tgr" runs, TGR + tracker for our "tgr_tracker" runs). It must reproduce
the saved conversation exactly. With the other decision, the agent fake raises ReplayMiss at prefix 2 + 2*(i+1):
that is expected (the conversation leaves the saved one), and ReplayMiss.detail shows the first new message.

Self-test (replay from the start with the copied run_episode loop, plus negative tests):
    LITELLM_LOCAL_MODEL_COST_MAP=True PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B \
        -m tests.audit_v2_replay_fakes > output/logs/v2_r2_fakes_selftest.log 2>&1
writes output/eval_v2/checks/ref/ref_rebuild_fakes_selftest.json.

Written by R2 (independent reference; did not read fork/rebuild.py, fork/find_points.py or fork/run_*.py).
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import sys
import threading
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))           # predicate_correctness/
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

REF_DIR = os.path.join(PC_DIR, "output", "eval_v2", "checks", "ref")
RULES_DIR = os.path.join(PC_DIR, "from_shieldagent", "rules")
HI = "Hi! How can I help you today?"
CHANGED_EVIDENCE = "(replay fake: the judge's evidence for this value was not saved; the tracker replaced it)"
PROBE_ANSWER = "(replay fake: answer to the env-build probe call)"


# ----------------------------------------------------------------------------------------------- small helpers
def canon(obj: Any) -> str:
    """The canonical JSON text used for every sha256 here."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha(obj: Any) -> str:
    return hashlib.sha256(canon(obj).encode("utf-8")).hexdigest()


def jnorm(obj: Any) -> Any:
    """As the runner writes a record: a JSON round trip (tuples -> lists, unknown objects -> str)."""
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))


def first_diff(a: List[Any], b: List[Any]) -> Optional[int]:
    for k in range(min(len(a), len(b))):
        if a[k] != b[k]:
            return k
    return None if len(a) == len(b) else min(len(a), len(b))


def _short(x: Any, n: int = 300) -> str:
    s = x if isinstance(x, str) else canon(x)
    return s if len(s) <= n else s[:n] + f"... ({len(s)} chars)"


class ReplayMiss(AssertionError):
    """A fake was asked something that is not in the saved conversation."""

    def __init__(self, fake: str, message: str, **detail):
        self.fake, self.detail = fake, detail
        extra = "; ".join(f"{k}={_short(v)}" for k, v in detail.items())
        super().__init__(f"[replay fake {fake}] {message}" + (f" | {extra}" if extra else ""))


def block_network() -> None:
    """Refuse any socket connect / name lookup in this process (audit hook; cannot be removed)."""
    def hook(event, args):
        if event in ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex"):
            raise RuntimeError(f"network blocked by tests/audit_v2_replay_fakes.py ({event} {args[:2]!r})")
    sys.addaudithook(hook)


# ----------------------------------------------------------------------------------------------- saved runs
def load_line(path: str, line_no: int) -> dict:
    """One raw line (0-based) of an episodes.jsonl file."""
    p = path if os.path.isabs(path) else os.path.join(PC_DIR, path)
    with open(p, encoding="utf-8") as f:
        for k, line in enumerate(f):
            if k == line_no:
                return json.loads(line)
    raise IndexError(f"{path} has no line {line_no}")


def good_episodes(path: str) -> Dict[Tuple[int, int], Tuple[int, dict]]:
    """{(task_index, trial): (line_no, episode)}: the last line without an error per (task, trial) (HANDOFF 5.6)."""
    p = path if os.path.isabs(path) else os.path.join(PC_DIR, path)
    out: Dict[Tuple[int, int], Tuple[int, dict]] = {}
    with open(p, encoding="utf-8") as f:
        for k, line in enumerate(f):
            ep = json.loads(line)
            if ep.get("error") is None:
                out[(ep["task_index"], ep["trial"])] = (k, ep)
    return out


def task_instruction(domain: str, task_split: str, task_index: int) -> str:
    """The task's instruction from the venv's τ-bench task files (what env.reset gives the user simulator)."""
    if domain == "retail":
        if task_split == "test":
            from tau_bench.envs.retail.tasks_test import TASKS_TEST as tasks
        elif task_split == "train":
            from tau_bench.envs.retail.tasks_train import TASKS_TRAIN as tasks
        elif task_split == "dev":
            from tau_bench.envs.retail.tasks_dev import TASKS_DEV as tasks
        else:
            raise ValueError(task_split)
    elif domain == "airline":
        if task_split != "test":
            raise ValueError(f"airline has only the test split, not {task_split!r}")
        from tau_bench.envs.airline.tasks_test import TASKS as tasks
    else:
        raise ValueError(domain)
    return tasks[task_index].instruction


def user_system_prompt(instruction: Optional[str]) -> str:
    """LLMUserSimulationEnv.build_system_prompt (the real one; it does not use self)."""
    from tau_bench.envs.user import LLMUserSimulationEnv
    return LLMUserSimulationEnv.build_system_prompt(None, instruction)


def is_respond(msg: dict) -> bool:
    """tau_bench.agents.tool_calling_agent.message_to_action's test: no usable tool call -> respond."""
    tcs = msg.get("tool_calls")
    return not (tcs is not None and len(tcs) > 0 and tcs[0].get("function") is not None)


def user_messages_from_executed(executed: List[dict], instruction: str) -> List[dict]:
    """The user simulator's message list after the executed history (part1.md 5.3): system prompt, "Hi! ...", its first
    message, then (agent text as "user", its reply as "assistant") for every executed reply to the user."""
    out = [{"role": "system", "content": user_system_prompt(instruction)},
           {"role": "user", "content": HI},
           {"role": "assistant", "content": executed[1]["content"], "tool_calls": None}]
    for p in range(2, len(executed) - 1, 2):
        m, ans = executed[p], executed[p + 1]
        if is_respond(m):
            if ans.get("role") != "user":
                raise ValueError(f"executed[{p + 1}] should be the user's reply, got role {ans.get('role')!r}")
            out.append({"role": "user", "content": m.get("content")})
            out.append({"role": "assistant", "content": ans.get("content"), "tool_calls": None})
        elif ans.get("role") != "tool":
            raise ValueError(f"executed[{p + 1}] should be a tool output, got role {ans.get('role')!r}")
    return out


class _Message:
    """Shaped like exp_core.models._Message (what τ-bench and repro_online read)."""

    def __init__(self, d: dict):
        self._d = copy.deepcopy(d)
        self.role = "assistant"
        self.content = self._d.get("content")
        self.tool_calls = self._d.get("tool_calls")

    def model_dump(self, **_) -> dict:
        return {"role": "assistant", "content": copy.deepcopy(self.content),
                "tool_calls": copy.deepcopy(self.tool_calls) if self.tool_calls else None}


def _response(d: dict) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=_Message(d))], _hidden_params={"response_cost": 0.0})


# ----------------------------------------------------------------------------------------------- judge prompts
class JudgePrompts:
    """Builds TGR's judge prompt for a guard check, with the runner copy's own pieces (method_tgr/runtime.py
    TGR._judge: same rule set, same render_history(max_chars=24000), same action_text, same template)."""

    def __init__(self, domain: str, rules_dir: Optional[str] = None):
        from guard import runner_path
        runner_path.setup()
        from method_tgr import prompts
        from method_tgr.rules import RESPOND, to_aspm
        from method_tgr.runtime import TGRConfig, load_rule_set
        from repro_core.taubench_steps import render_history
        from repro_online.guards import make_step
        from repro_runtime.shield import action_text
        self.rules_path = os.path.join(rules_dir or os.path.join(RULES_DIR, domain), "rule_set.json")
        self.rule_set = load_rule_set(self.rules_path)
        self.aspm = to_aspm(self.rule_set)
        self.grounded = self.rule_set["flags"]["a"]
        self.history_chars = TGRConfig().history_chars
        self._prompts, self._render_history, self._make_step, self._action_text = prompts, render_history, make_step, action_text
        self._respond = RESPOND

    def step(self, executed_prefix: List[dict], msg: dict, index: int):
        return self._make_step(executed_prefix, msg, index)

    def matched(self, step) -> List[str]:
        name = self._respond if step.kind == "respond" else step.name
        return [name] if name in self.aspm.action_predicates else []

    def prompt(self, executed_prefix: List[dict], msg: dict, index: int) -> dict:
        """{system, user, circuit, names, action_text} of the judge call at this check ({} names: no judge call)."""
        aspm, preds_def = self.aspm, self.rule_set["predicates"]
        step = self.step(executed_prefix, msg, index)
        a_text = self._action_text(step)
        circuit = aspm.circuit(self.matched(step))
        names = sorted({n for r in circuit for n in aspm.rules[r].atoms} - aspm.action_predicates)
        out = {"circuit": list(circuit), "names": names, "action_text": a_text, "system": None, "user": None}
        if not circuit or not names:
            return out
        rules = "\n".join(f"[{r}] {aspm.rules[r].description}\n    logic: {aspm.rules[r].logic}" for r in circuit)
        preds = "\n".join(f"- {n}: {aspm.descriptions.get(n, '')}"
                          + (f" (evidence from: {', '.join(preds_def[n]['source'])})"
                             if self.grounded and preds_def.get(n, {}).get("source") else "") for n in names)
        facts = "\n".join(f"- {b['text']}" for b in self.rule_set.get("background", [])) or "(none)"
        sysmsg, user = self._prompts.render("judge", history=self._render_history(step.history,
                                                                                    max_chars=self.history_chars),
                                            action=a_text, rules=rules, facts=facts, predicates=preds)
        out.update(system=sysmsg, user=user)
        return out


def judge_key(system: str, user: str) -> str:
    return sha([system, user])


def judge_cache_path(cache_dir: str, system: str, user: str, model: str = "gpt-6-luna", effort: str = "medium",
                     max_output_tokens: int = 16000) -> str:
    """Where policy_pipeline.llm.LLM.call cached this judge prompt (same key formula; read only here)."""
    from method_tgr.runtime import JUDGE_SCHEMA
    params = {"model": model, "effort": effort, "max_output_tokens": max_output_tokens,
              "schema_name": "predicate_values", "schema": JUDGE_SCHEMA, "sample": 0}
    key = hashlib.sha256(json.dumps({"system": system, "user": user, "params": params}, sort_keys=True).encode()).hexdigest()
    return os.path.join(cache_dir, key[:2], key + ".json")


def judge_values_of(parsed: dict, names: List[str]) -> Dict[str, Optional[bool]]:
    """What TGR._judge makes of a judge answer (values only)."""
    val = {"true": True, "false": False, "unknown": None}
    got = {p["name"]: val[p["value"]] for p in parsed.get("predicates", []) if p["name"] in names}
    return {n: got.get(n) for n in names}


_VAL = {True: "true", False: "false", None: "unknown"}


def saved_judge_answer(rec: dict) -> Optional[Dict[str, dict]]:
    """{name: {value, evidence}} the judge gave at this saved check, or None if the judge was not called."""
    judge = rec.get("judge") or {}
    tr = rec.get("tracker") or {}
    if tr.get("applied"):
        if tr.get("judge_skipped") or tr.get("judge_values") is None:
            return None
        changed = set(tr.get("changed") or [])
        return {n: {"value": v, "evidence": CHANGED_EVIDENCE if n in changed else (judge.get(n) or {}).get("evidence", "")}
                for n, v in tr["judge_values"].items()}
    if not judge:
        return None
    return {n: {"value": v.get("value"), "evidence": v.get("evidence", "")} for n, v in judge.items()}


# ----------------------------------------------------------------------------------------------- the fakes
class ReplayFakes:
    """Fakes that replay one saved conversation (see the module docstring)."""

    def __init__(self, ep: dict, domain: Optional[str] = None, task_split: str = "test",
                 instruction: Optional[str] = None, rules_dir: Optional[str] = None,
                 allow_build_probe: bool = False, judge_cache_dir: Optional[str] = None,
                 judge_model: str = "gpt-6-luna", loose: bool = False):
        """judge_cache_dir (optional, read only): the run's judge cache, e.g. output/_llmcache/p10_nano_train/structured.
        For TGR + tracker records it gives the judge's full original answer (with the evidence the record lost); the
        cached values must equal tracker.judge_values, else the record's values are used.
        loose: compare message lists with keys whose value is None dropped (e.g. "tool_calls": None), which the real
        model call ignores too (exp_core/models.py chat_to_responses_input). Default: exact."""
        self.judge_cache_dir, self.judge_model, self.loose = judge_cache_dir, judge_model, loose
        self.evidence_from_cache = 0
        self.ep = jnorm(ep)
        self.domain = domain or self.ep["env"]
        self.task_split, self.task_index = task_split, self.ep["task_index"]
        self.messages: List[dict] = self.ep["messages"]
        self.executed: List[dict] = self.ep["executed"]
        self.attempts: List[dict] = self.ep["attempts"]
        self.instruction = instruction if instruction is not None else task_instruction(self.domain, task_split,
                                                                                         self.task_index)
        self.user_list = user_messages_from_executed(self.executed, self.instruction)
        self.n_replies = (len(self.user_list) - 1) // 2          # replies at user_list[2], [4], ...
        self.allow_build_probe = allow_build_probe
        self.probe_system = user_system_prompt(None)
        self.prompts = JudgePrompts(self.domain, rules_dir)
        self.judge_map: Dict[str, List[dict]] = {}
        self.judge_problems: List[str] = []
        self._build_judge_map()
        self._lock = threading.Lock()
        self.log: List[dict] = []

    # ---------------------------------------------------------------- judge map
    def _build_judge_map(self) -> None:
        for i, att in enumerate(self.attempts):
            rec = att.get("guard")
            if not rec:
                continue
            ans = saved_judge_answer(rec)
            msg = self.messages[2 + 2 * i]
            pr = self.prompts.prompt(self.executed[:att["executed_prefix_len"]], msg, att["exec_step"])
            if pr["action_text"] != rec.get("action_text"):
                self.judge_problems.append(f"attempt {i}: action_text differs from the saved one")
            if list(rec.get("circuit") or []) != pr["circuit"]:
                self.judge_problems.append(f"attempt {i}: circuit {pr['circuit']} != saved {rec.get('circuit')}")
            if ans is None:
                if pr["system"] is not None and not (rec.get("tracker") or {}).get("judge_skipped"):
                    self.judge_problems.append(f"attempt {i}: a judge call is expected but none was saved")
                continue
            if sorted(ans) != pr["names"]:
                self.judge_problems.append(f"attempt {i}: judge names {sorted(ans)} != expected {pr['names']}")
            if pr["system"] is None:
                self.judge_problems.append(f"attempt {i}: judge values saved but no judge call expected")
                continue
            k = judge_key(pr["system"], pr["user"])
            response = {"predicates": [{"name": n, "value": _VAL[ans[n]["value"]], "evidence": ans[n]["evidence"]}
                                       for n in pr["names"] if n in ans]}
            if self.judge_cache_dir and (rec.get("tracker") or {}).get("applied"):
                cp = judge_cache_path(self.judge_cache_dir, pr["system"], pr["user"], model=self.judge_model)
                if os.path.exists(cp):
                    with open(cp, encoding="utf-8") as f:
                        parsed = json.load(f).get("parsed") or {}
                    if judge_values_of(parsed, pr["names"]) == {n: ans[n]["value"] for n in pr["names"]}:
                        response = parsed
                        self.evidence_from_cache += 1
                    else:
                        self.judge_problems.append(f"attempt {i}: cached judge values differ from judge_values")
                else:
                    self.judge_problems.append(f"attempt {i}: judge prompt not in the cache {self.judge_cache_dir}")
            entries = self.judge_map.setdefault(k, [])
            if entries and entries[0]["response"] != response:
                self.judge_problems.append(f"attempt {i}: same judge prompt as attempt {entries[0]['attempt']} "
                                           "but other saved values (answered in order)")
            entries.append({"attempt": i, "response": response})

    # ---------------------------------------------------------------- bookkeeping
    def _view(self, msgs: List[dict]) -> List[dict]:
        if not self.loose:
            return msgs
        return [{k: v for k, v in m.items() if v is not None} if isinstance(m, dict) else m for m in msgs]

    def _record(self, fake: str, **kw) -> None:
        with self._lock:
            self.log.append({"fake": fake, **kw})

    def report(self) -> dict:
        with self._lock:
            log = list(self.log)
        by = {}
        for r in log:
            by[r["fake"]] = by.get(r["fake"], 0) + 1
        return {"calls": by, "judge_checks_saved": sum(len(v) for v in self.judge_map.values()),
                "judge_attempts_answered": sorted({r["attempt"] for r in log if r["fake"] == "judge"}),
                "agent_attempts_answered": sorted({r["attempt"] for r in log if r["fake"] == "agent"}),
                "user_replies_answered": sorted({r["reply"] for r in log if r["fake"] == "user"}),
                "judge_answers_from_cache": self.evidence_from_cache,
                "judge_map_problems": list(self.judge_problems)}

    # ---------------------------------------------------------------- the agent
    def agent(self, model=None, custom_llm_provider=None, messages=None, tools=None, temperature=None, **_):
        """Same signature as exp_core.models.make_completion("agent")'s completion."""
        given = jnorm(messages or [])
        n = len(given)
        if n < 2 or n % 2:
            raise ReplayMiss("agent", f"asked with {n} messages; a saved agent prefix has 2 + 2*i messages")
        i = (n - 2) // 2
        if i >= len(self.attempts):
            raise ReplayMiss("agent", f"the saved conversation has no agent message after {n} messages "
                                      f"(it ended after {len(self.attempts)} attempts)")
        want = self.messages[:n]
        d = first_diff(self._view(given), self._view(want))
        if d is not None:
            raise ReplayMiss("agent", f"prefix of {n} messages differs from the saved one at message {d}",
                             index=d, given=given[d], saved=want[d])
        self._record("agent", attempt=i, tools_sha256=sha(tools) if tools is not None else None)
        return _response(self.messages[n])

    # ---------------------------------------------------------------- the user simulator
    def user(self, model=None, custom_llm_provider=None, messages=None, tools=None, temperature=None, **_):
        """Same signature as litellm.completion / make_completion("user") as LLMUserSimulationEnv calls it."""
        given = jnorm(messages or [])
        n = len(given)
        if (n == 2 and given[0].get("content") == self.probe_system and given[1] == {"role": "user", "content": HI}):
            if self.allow_build_probe:
                self._record("user_probe", reply=-1)
                return _response({"role": "assistant", "content": PROBE_ANSWER, "tool_calls": None})
            raise ReplayMiss("user", "asked the env-build probe (system prompt with no instruction): the runner built "
                                     "an LLMUserSimulationEnv the normal way (part1.md 5.7 trap 2)")
        if n < 2 or n % 2:
            raise ReplayMiss("user", f"asked with {n} messages; a saved user-simulator prefix has 2 + 2*k messages")
        k = (n - 2) // 2
        if k >= self.n_replies:
            raise ReplayMiss("user", f"the saved conversation has no user reply number {k} "
                                     f"(it has {self.n_replies} replies, the first message included)")
        want = self.user_list[:n]
        d = first_diff(self._view(given), self._view(want))
        if d is not None:
            raise ReplayMiss("user", f"user-simulator list of {n} messages differs from the rebuilt one at {d}",
                             index=d, given=given[d], saved=want[d])
        self._record("user", reply=k)
        return _response(self.user_list[n])

    # ---------------------------------------------------------------- the judge
    def _judge_lookup(self, stage: str, system: str, user: str) -> dict:
        if stage != "tgr_judge":
            raise ReplayMiss("judge", f"unexpected structured call of stage {stage!r} (only tgr_judge is replayed)")
        k = judge_key(system, user)
        entries = self.judge_map.get(k)
        if not entries:
            raise ReplayMiss("judge", "no saved guard check has this judge prompt", prompt_sha256=k,
                             prompt_tail=user[-400:])
        with self._lock:
            used = sum(1 for r in self.log if r["fake"] == "judge" and r["key"] == k)
        e = entries[min(used, len(entries) - 1)]
        self._record("judge", attempt=e["attempt"], key=k)
        return copy.deepcopy(e["response"])

    def judge_structured(self, meter, *, stage: str, system: str, user: str, schema: dict, schema_name: str,
                         effort: str, max_output_tokens: Optional[int] = None) -> dict:
        """Same signature as method_tgr.llm.structured; records a zero-usage call in the meter (as a cache miss)."""
        out = self._judge_lookup(stage, system, user)
        meter.add(stage, effort, False, {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}, 0.0)
        return out

    def judge_llm(self) -> "FakeJudgeLLM":
        return FakeJudgeLLM(self)

    # ---------------------------------------------------------------- patching
    @contextlib.contextmanager
    def installed(self, user: bool = True, judge: bool = True):
        """Patch tau_bench.envs.user.completion (user) and method_tgr.llm.structured (judge) for the block."""
        import tau_bench.envs.user as user_mod
        from guard import runner_path
        runner_path.setup()
        import method_tgr.llm as tgr_llm
        old_u, old_j = user_mod.completion, tgr_llm.structured
        try:
            if user:
                user_mod.completion = self.user
            if judge:
                tgr_llm.structured = self.judge_structured
            yield self
        finally:
            user_mod.completion, tgr_llm.structured = old_u, old_j


class FakeJudgeLLM:
    """policy_pipeline.llm.LLM look-alike (attributes model, max_output_tokens, cache_dir; method call)."""
    model = "replay-fake"
    max_output_tokens = 16000
    cache_dir = "/nonexistent/replay-fake-no-cache"      # never created: structured() then records zero usage

    def __init__(self, fakes: ReplayFakes):
        self.fakes = fakes

    def call(self, *, stage: str, system: str, user: str, schema: dict, schema_name: str, effort: str = "low",
             sample: int = 0) -> dict:
        return self.fakes._judge_lookup(stage, system, user)


def new_llm_user(model: str = "replay-fake", provider: str = "replay-fake", messages: Optional[List[dict]] = None):
    """A real LLMUserSimulationEnv without its __init__ (which calls the model once, part1.md 5.7 trap 2)."""
    from tau_bench.envs.user import LLMUserSimulationEnv
    u = LLMUserSimulationEnv.__new__(LLMUserSimulationEnv)
    u.messages = copy.deepcopy(messages) if messages else []
    u.model, u.provider, u.total_cost = model, provider, 0.0
    return u


# ----------------------------------------------------------------------------------------------- comparing
ATT_FIELDS = ("exec_step", "attempt", "action", "kwargs", "agent_text", "blocked", "cap_override",
              "executed_prefix_len", "observation", "feedback")
GUARD_FIELDS = ("step_index", "trace_len_before", "kind", "name", "action_text", "matched", "trace_position", "circuit",
                "judge", "mln", "margin", "allowed_eps0", "violated_rules", "unknown_predicates", "action_allowed",
                "epsilon", "reason", "feedback_text")
TRACKER_DROP = ("seconds",)


def _tracker_view(tr: Optional[dict]) -> Optional[dict]:
    if not tr:
        return tr
    out = {k: v for k, v in tr.items() if k not in TRACKER_DROP}
    if isinstance(out.get("state"), dict):
        out["state"] = {k: v for k, v in out["state"].items() if k != "seconds"}
    return out


def compare_episode(rec: dict, ep: dict, from_attempt: int = 0) -> dict:
    """Is a (re)run record the saved conversation? rec as run_episode returns it (any JSON-able dict)."""
    rec, ep = jnorm(rec), jnorm(ep)
    out = {}
    for k in ("messages", "executed"):
        d = first_diff(rec.get(k) or [], ep[k])
        out[f"{k}_equal"] = d is None
        if d is not None:
            out[f"{k}_first_diff"] = d
    for k in ("reward", "done", "n_exec_steps", "n_blocks", "n_cap_overrides", "reward_info"):
        out[f"{k}_equal"] = rec.get(k) == ep.get(k)
    ra, sa = rec.get("attempts") or [], ep["attempts"]
    out["attempts_count_equal"] = len(ra) == len(sa)
    bad = []
    for i in range(from_attempt, min(len(ra), len(sa))):
        a, b = ra[i], sa[i]
        for f in ATT_FIELDS:
            if a.get(f) != b.get(f):
                bad.append(f"attempt {i}: {f}")
        ga, gb = a.get("guard") or {}, b.get("guard") or {}
        for f in GUARD_FIELDS:
            if ga.get(f) != gb.get(f):
                bad.append(f"attempt {i}: guard.{f}")
        if _tracker_view(ga.get("tracker")) != _tracker_view(gb.get("tracker")):
            bad.append(f"attempt {i}: guard.tracker")
    out["attempt_field_differences"] = bad[:20]
    out["n_attempt_field_differences"] = len(bad)
    out["all_equal"] = all(v for k, v in out.items() if k.endswith("_equal")) and not bad
    return out


# ----------------------------------------------------------------------------------------------- self-test
def _guard_for(ep: dict, domain: str, tools_info: list):
    from guard import runner_path
    runner_path.setup()
    if ep.get("guard") == "tgr_tracker":
        from guard.tgr_tracker import TGRTrackerGuard
        return TGRTrackerGuard(domain, tools_info)
    if ep.get("guard") == "tgr":
        from repro_online.guards import TGRGuard
        return TGRGuard("tgr", os.path.join(RULES_DIR, domain), tools_info)
    raise ValueError(f"guard {ep.get('guard')!r}")


def judge_cache_for(run: str) -> Optional[str]:
    """Our runs' judge cache (output/_llmcache/<tag>/structured), if it exists. The partner's caches are not copied."""
    p = os.path.join(PC_DIR, "output", "_llmcache", run, "structured")
    return p if os.path.isdir(p) else None


def replay_from_start(ep: dict, domain: str, task_split: str = "test",
                      judge_cache_dir: Optional[str] = None) -> Tuple[dict, ReplayFakes]:
    """The copied run_episode loop, with a real env (user_strategy="human" + a real LLMUserSimulationEnv without
    the build call), the source run's real guard, and the replay fakes."""
    from guard import runner_path
    runner_path.setup()
    from tau_bench.envs import get_env
    from repro_online import episode
    fakes = ReplayFakes(ep, domain=domain, task_split=task_split, judge_cache_dir=judge_cache_dir)
    env = get_env(domain, user_strategy="human", user_model="none", task_split=task_split, task_index=ep["task_index"])
    env.user = new_llm_user()
    guard = _guard_for(ep, domain, env.tools_info)
    with fakes.installed():
        rec = episode.run_episode(env, fakes.agent, env.tools_info, env.wiki, guard, ep["task_index"],
                                  max_num_steps=30)
    return rec, fakes


def _negative_tests(ep: dict, domain: str) -> dict:
    """Each fake must raise ReplayMiss on a prefix that is not in the saved conversation."""
    fakes = ReplayFakes(ep, domain=domain)
    res = {}

    def expect_miss(name, fn):
        try:
            fn()
            res[name] = "NOT RAISED (bad)"
        except ReplayMiss as e:
            res[name] = "raised: " + str(e)[:160]

    msgs = copy.deepcopy(ep["messages"][:4])
    msgs[3]["content"] = (msgs[3].get("content") or "") + " (changed)"
    expect_miss("agent_wrong_prefix", lambda: fakes.agent(messages=msgs, tools=None))
    expect_miss("agent_odd_length", lambda: fakes.agent(messages=ep["messages"][:3]))
    expect_miss("agent_after_end", lambda: fakes.agent(messages=ep["messages"]))
    ul = copy.deepcopy(fakes.user_list[:4]) if len(fakes.user_list) >= 4 else None
    if ul:
        ul[3]["content"] = "something the agent never said"
        expect_miss("user_wrong_prefix", lambda: fakes.user(messages=ul))
    expect_miss("user_build_probe", lambda: fakes.user(messages=[{"role": "system", "content": user_system_prompt(None)},
                                                               {"role": "user", "content": HI}]))
    expect_miss("user_after_end", lambda: fakes.user(messages=fakes.user_list + [{"role": "user", "content": "x"}]))
    from repro_runtime.calls import Meter
    expect_miss("judge_unknown_prompt", lambda: fakes.judge_structured(Meter(), stage="tgr_judge", system="s",
                                                                       user="u", schema={}, schema_name="x",
                                                                       effort="medium"))
    expect_miss("judge_other_stage", lambda: fakes.judge_structured(Meter(), stage="explain", system="s", user="u",
                                                                    schema={}, schema_name="x", effort="low"))
    # loose mode: a message without its None-valued keys is accepted only with loose=True
    no_none = [{k: v for k, v in m.items() if v is not None} for m in fakes.user_list[:4]]
    expect_miss("user_without_none_keys_exact", lambda: fakes.user(messages=no_none))
    loose = ReplayFakes(ep, domain=domain, loose=True)
    # positive: the right prefixes are answered
    ok = fakes.agent(messages=ep["messages"][:2]).choices[0].message.model_dump() == ep["messages"][2]
    okm = fakes.user(messages=fakes.user_list[:2]).choices[0].message.model_dump() == fakes.user_list[2]
    res["agent_first_prefix_answered"] = ok
    res["user_first_prefix_answered"] = okm
    res["loose_accepts_without_none_keys"] = loose.user(messages=no_none).choices[0].message.content == \
        fakes.user_list[4]["content"]
    pos = ("agent_first_prefix_answered", "user_first_prefix_answered", "loose_accepts_without_none_keys")
    res["all_raised"] = all(isinstance(v, str) and v.startswith("raised") for k, v in res.items() if k not in pos)
    res["all_positive_ok"] = all(res[k] is True for k in pos)
    return res


SELFTEST_SOURCES = (   # (run, domain, guard folder, episodes path): one conversation chosen from each
    ("luna_train_v5", "retail", "from_shieldagent/runs/luna_train_v5/retail/tgr/episodes.jsonl"),
    ("nano_train", "airline", "from_shieldagent/runs/nano_train/airline/tgr/episodes.jsonl"),
    ("nano_train", "retail", "from_shieldagent/runs/nano_train/retail/tgr/episodes.jsonl"),
    ("p10_luna_train", "airline", "output/online/p10_luna_train/airline/tgr_tracker/episodes.jsonl"),
    ("p10_nano_train", "retail", "output/online/p10_nano_train/retail/tgr_tracker/episodes.jsonl"),
    ("p10_luna_val", "retail", "output/online/p10_luna_val/retail/tgr_tracker/episodes.jsonl"),
)


def _pick(path: str, want_cap: bool, want_max_steps: bool = False) -> Tuple[int, dict]:
    """The first good conversation (by line) with blocks (and a cap override / 30 steps if asked)."""
    eps = sorted(good_episodes(path).values(), key=lambda x: x[0])
    if want_max_steps:
        for line, ep in eps:
            if ep["n_exec_steps"] >= 30:
                return line, ep
        raise LookupError(path)
    tests = ([lambda e: e["n_blocks"] >= 2 and e["n_cap_overrides"] >= 1] if want_cap else []) + \
            [lambda e: e["n_blocks"] >= 2, lambda e: e["n_blocks"] >= 1, lambda e: True]
    for t in tests:
        for line, ep in eps:
            if ep["done"] and t(ep):
                return line, ep
    raise LookupError(path)


def selftest() -> dict:
    from guard import write_guard
    write_guard.install([os.path.join(PC_DIR, "output")])
    block_network()
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    results = []
    picks = [(run, dom, path, *_pick(path, want_cap=True)) for run, dom, path in SELFTEST_SOURCES]
    run, dom, path = SELFTEST_SOURCES[2]
    picks.append((run, dom, path, *_pick(path, want_cap=False, want_max_steps=True)))      # a 30-step conversation
    for run, dom, path, line, ep in picks:
        row = {"run": run, "domain": dom, "episodes_path": path, "line_no": line, "task_index": ep["task_index"],
               "trial": ep["trial"], "guard": ep["guard"], "attempts": len(ep["attempts"]),
               "n_exec_steps": ep["n_exec_steps"], "n_blocks": ep["n_blocks"],
               "n_cap_overrides": ep["n_cap_overrides"], "reward": ep["reward"], "done": ep["done"]}
        try:
            rec, fakes = replay_from_start(ep, dom, judge_cache_dir=judge_cache_for(run))
            row["compare"] = compare_episode(rec, ep)
            row["fakes"] = fakes.report()
        except Exception as e:  # noqa: BLE001 - recorded
            import traceback
            row["error"] = f"{type(e).__name__}: {e}"
            row["traceback"] = traceback.format_exc()[-3000:]
        print(f"[r2-fakes] {run}/{dom} task {ep['task_index']} trial {ep['trial']}: "
              f"{'ERROR ' + row['error'][:300] if 'error' in row else row['compare']['all_equal']}", flush=True)
        results.append(row)
    neg = _negative_tests(picks[0][4], picks[0][1])
    out = {"what": "replay from the start with the copied run_episode loop, real env and guard, replay fakes",
           "results": results, "negative_tests": neg,
           "all_replays_equal": all(r.get("compare", {}).get("all_equal") for r in results),
           "refused_writes": list(write_guard.REFUSED)}
    os.makedirs(REF_DIR, exist_ok=True)
    with open(os.path.join(REF_DIR, "ref_rebuild_fakes_selftest.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("[r2-fakes] all replays equal:", out["all_replays_equal"], "| negative tests all raised:", neg["all_raised"],
          flush=True)
    return out


if __name__ == "__main__":
    selftest()
