"""Eval v2 Part 3b: tests of the Stage B branch code (fork/run_branch.py, fork/run_all.py and their helpers).

No test makes an LLM call or opens a network connection:
  - the agent is a scripted fake completion; the user simulator is a scripted fake inside FakeEnv, which has the
    same step() and calculate_reward() as τ-bench's envs/base.py Env, on the copied tools and data;
  - the judge is a fake LLM (FakeCachedLLM, with a disk cache like policy_pipeline.llm.LLM) behind the per-try
    cache proxy (fork/branch_cache.py); when no fake is set, any judge call fails (_NoLLM);
  - one test runs the real τ-bench env in the venv Python (a fresh process, network blocked, fake completions);
  - the dry run with the real safety (write guard, network block) runs in a fresh process.
The fork states are built by hand (Scenario), from a real retail conversation made with the copied tools.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_eval_v2_fork -v
Standard library only (the venv test uses ~/venvs/tau-bench/bin/python and is skipped if it is missing).
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import unittest
import uuid
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from guard import runner_path                                       # noqa: E402

runner_path.setup()

from fork import branch_cache, branch_env, guards_build, run_all   # noqa: E402
from fork import run_branch as rb                                   # noqa: E402
from fork.schema import BRANCH_GUARD, ForkPoint, ForkState          # noqa: E402
from method_tgr.runtime import Conversation, load_rule_set          # noqa: E402  (runner copy)
from repro_runtime import calls                                     # noqa: E402  (runner copy)
from state_tracker import paths, tau_copy                           # noqa: E402
from state_tracker.state import load_db, run_tool                   # noqa: E402

VENV_PY = os.path.expanduser("~/venvs/tau-bench/bin/python")
# one temp folder per process, so two suite runs at once never share (or remove) each other's files (audit A5 W8);
# under output/ but not under output/eval_v2/, so the soft-stop scan never counts the fake costs of these tests
TMP_ROOT = os.path.join(paths.OUTPUT_DIR, f"_tmp_test_eval_v2_fork_{os.getpid()}")
DOMAIN = "retail"
SPLIT, TASK = "train", 4                     # τ-bench retail TASKS_TRAIN[4]: Juan Rossi cancels #W7602708
OID, REASON = "#W7602708", "no longer needed"
LOGIN = {"first_name": "Juan", "last_name": "Rossi", "zip": "77209"}
FIRST_USER = "Hi, I'm Juan Rossi, zip 77209. Please cancel order #W7602708, I no longer need it."
GREETING = "Hi! How can I help you today?"
FEEDBACK_A = "BLOCKED by policy guardrail. The cancel_pending_order call was NOT executed (test feedback of A)."
FEEDBACK_B = "BLOCKED by policy guardrail. Test feedback of B."
REPLY = "Is there anything else I can help you with?"


class _NoLLM:
    """Installed whenever no fake judge is: any judge call fails loudly (never a real client, never a cache)."""
    model, max_output_tokens = "no-llm", 16000
    cache_dir = os.path.join(paths.OUTPUT_DIR, "_no_llm_never_written")

    def call(self, **_):
        raise AssertionError("an LLM call was attempted in a unit test")


calls._llm = _NoLLM()


def jload(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ============================================================================================ fakes

class FakeAction:
    def __init__(self, name: str, kwargs: dict):
        self.name, self.kwargs = name, kwargs

    def model_dump(self):
        return {"name": self.name, "kwargs": self.kwargs}


def fake_message_to_action(msg: dict) -> FakeAction:
    """τ-bench's tool_calling_agent.message_to_action, returning FakeAction."""
    tcs = msg.get("tool_calls")
    if tcs is not None and len(tcs) > 0 and tcs[0]["function"] is not None:
        return FakeAction(tcs[0]["function"]["name"], json.loads(tcs[0]["function"]["arguments"]))
    return FakeAction("respond", {"content": msg["content"]})


class FakeInfo:
    def __init__(self, **kw):
        self.d = kw

    def model_dump(self):
        return dict(self.d)


_usage_tls = threading.local()


def fake_reset_usage():
    _usage_tls.u = {r: {"calls": 0, "cost": 0.0} for r in ("agent", "user")}


def fake_usage() -> dict:
    if not hasattr(_usage_tls, "u"):
        fake_reset_usage()
    return _usage_tls.u


def user_prompt(instruction: str) -> str:
    return f"FAKE USER SIMULATOR. Instruction: {instruction}"


class FakeUser:
    """LLMUserSimulationEnv's message handling, with a scripted reply instead of the user model."""
    is_test_fake = True

    def __init__(self, messages: List[dict], script: Callable[[List[dict]], str], log: Optional[list] = None):
        self.messages = messages
        self.script = script
        self.log = log if log is not None else []

    def build_system_prompt(self, instruction):
        return user_prompt(instruction)

    def step(self, content: str) -> str:
        self.messages.append({"role": "user", "content": content})
        self.log.append(copy.deepcopy(self.messages))
        reply = self.script(self.messages)
        self.messages.append({"role": "assistant", "content": reply, "tool_calls": None})
        u = fake_usage()["user"]
        u["calls"] += 1
        u["cost"] += 0.0005
        return reply

    def get_total_cost(self):
        return 0.0


class FakeTask:
    def __init__(self, instruction: str, actions: List[FakeAction], outputs=()):
        self.instruction, self.actions, self.outputs = instruction, actions, list(outputs)


def gt_task() -> FakeTask:
    return FakeTask("Your name is Juan Rossi and your zip code is 77209. Cancel order #W7602708 because no longer "
                    "needed.", [FakeAction("cancel_pending_order", {"order_id": OID, "reason": REASON})])


class FakeEnv:
    """τ-bench's envs/base.py Env.step and calculate_reward (same code paths), on the copied tools and data."""

    def __init__(self, task: FakeTask, task_index: int, n_tasks: int, data: dict, actions: List[FakeAction],
                 user: FakeUser, domain: str = DOMAIN):
        self.domain = domain
        self.tools_map = tau_copy.tools(domain)
        self.terminate_tools = ["transfer_to_human_agents"]
        self.tasks = [FakeTask("other", [])] * n_tasks
        self.tasks = list(self.tasks)
        self.tasks[task_index] = task
        self.task_index, self.task = task_index, task
        self.data, self.actions, self.user = data, actions, user
        self.data_load_func = lambda: load_db(domain)

    def step(self, action):
        self.actions.append(action)
        reward, done, info = 0, False, {"task": "t", "source": None, "user_cost": None, "reward_info": None}
        if action.name == "respond":
            observation = self.user.step(action.kwargs["content"])
            info["source"] = "user"
            done = "###STOP###" in observation
        elif action.name in self.tools_map:
            try:
                observation = self.tools_map[action.name].invoke(data=self.data, **action.kwargs)
            except Exception as e:  # noqa: BLE001 - as Env.step
                observation = f"Error: {e}"
            info["source"] = action.name
            if action.name in self.terminate_tools:
                done = True
        else:
            observation = f"Unknown action {action.name}"
        if done:
            r = self.calculate_reward()
            reward = r["reward"]
            info["reward_info"] = r
        return SimpleNamespace(observation=observation, reward=reward, done=done, info=FakeInfo(**info))

    def get_data_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.data, sort_keys=True).encode()).hexdigest()

    def calculate_reward(self) -> dict:
        data_hash = self.get_data_hash()
        reward = 1.0
        self.data = self.data_load_func()
        for action in self.task.actions:
            if action.name not in self.terminate_tools:
                self.step(action)
        gt = self.get_data_hash()
        info = {"r_actions": data_hash == gt, "gt_data_hash": gt}
        if not info["r_actions"]:
            reward = 0.0
        return {"reward": reward, "info": info, "actions": [a.model_dump() for a in self.task.actions]}


def make_fake_env(state: ForkState, script=None, log=None) -> FakeEnv:
    """A FakeEnv at the fork state (as fork/branch_env.py make_env does for τ-bench)."""
    user = FakeUser(copy.deepcopy(state.user_messages), script or (lambda m: "###STOP###"), log)
    n = branch_env.TASK_COUNTS[(state.fork.domain, state.task_split)]
    return FakeEnv(gt_task(), state.task_index, n, copy.deepcopy(state.data),
                   [FakeAction(a["name"], copy.deepcopy(a["kwargs"])) for a in state.env_actions], user)


class FakeAgent:
    """Scripted agent completion: script(messages) -> the agent message dict. Records what it saw."""

    def __init__(self, script: Callable[[List[dict]], dict], cost: float = 0.001):
        self.script, self.cost = script, cost
        self.seen: List[List[dict]] = []
        self._lock = threading.Lock()

    def __call__(self, messages=None, model=None, custom_llm_provider=None, tools=None, temperature=None, **_):
        with self._lock:
            self.seen.append(copy.deepcopy(messages))
        d = copy.deepcopy(self.script(messages))
        u = fake_usage()["agent"]
        u["calls"] += 1
        u["cost"] += self.cost
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(model_dump=lambda d=d: copy.deepcopy(d)))],
                               _hidden_params={"response_cost": self.cost})


def reply_msg(text: str = REPLY) -> dict:
    return {"role": "assistant", "content": text, "tool_calls": None}


def tool_msg(name: str, args: dict, cid: str) -> dict:
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def always_reply(messages):
    return reply_msg()


@dataclasses.dataclass
class FakeCachedLLM:
    """A stand-in for policy_pipeline.llm.LLM: the same cache key and record layout, so the copied runtime reads the
    usage back; the answer comes from `answer(names)` instead of the API. `log` is shared by all copies."""
    cache_dir: Optional[str] = None
    model: str = "fake-judge"
    max_output_tokens: int = 16000
    usage: dict = dataclasses.field(default_factory=dict)
    _lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    answer: Optional[Callable[[List[str]], Dict[str, Any]]] = None
    log: list = dataclasses.field(default_factory=list)

    def __post_init__(self):
        if self.cache_dir is not None:                      # as policy_pipeline.llm.LLM
            os.makedirs(self.cache_dir, exist_ok=True)

    def call(self, *, stage, system, user, schema, schema_name, effort="low", sample=0):
        from guard.offline import FakeJudge
        params = {"model": self.model, "effort": effort, "max_output_tokens": self.max_output_tokens,
                  "schema_name": schema_name, "schema": schema, "sample": sample}
        key = hashlib.sha256(json.dumps({"system": system, "user": user, "params": params},
                                        sort_keys=True).encode()).hexdigest()
        path = os.path.join(self.cache_dir, key[:2], key + ".json")
        names = FakeJudge.predicates_in(user)
        hit = os.path.exists(path)
        if hit:
            with open(path) as f:
                rec = json.load(f)
        else:
            vals = (self.answer or (lambda ns: {n: True for n in ns}))(names)
            word = {True: "true", False: "false", None: "unknown"}
            rec = {"parsed": {"predicates": [{"name": n, "value": word[v], "evidence": f"fake evidence for {n}"}
                                             for n, v in vals.items()]},
                   "usage": {"input_tokens": 1000, "output_tokens": 100, "reasoning_tokens": 0}, "seconds": 0.0}
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(rec, f)
        self.log.append({"cache_dir": self.cache_dir, "hit": hit, "names": names, "user": user})
        return rec["parsed"]


def negated(action: str) -> set:
    """Predicates written 'NOT x' in the rules of an action (frozen retail rule set)."""
    rs = load_rule_set(paths.rule_set_path(DOMAIN))
    return {x for r in rs["rules"] if r["id"] in rs["circuits"].get(action, [])
            for x in rs["predicates"] if f"NOT {x}" in r["logic"]}


def allow_respond(names: List[str]) -> Dict[str, Any]:
    neg = negated("respond")
    return {n: n not in neg for n in names}


class StubGuard:
    """A guard with run_episode's interface: allowed(msg, n_exec) decides; the trace as TGR keeps it."""
    name = "stub"

    def __init__(self, allowed: Callable[[dict, int], bool]):
        self.allowed = allowed
        self.checks: List[dict] = []

    def new_episode(self):
        return Conversation()

    def check(self, conv, executed, msg, index):
        ok = self.allowed(msg, index)
        tp = {"stub_step": index}
        rec = {"action_allowed": ok, "trace_position": tp, "trace_len_before": len(conv.trace),
               "usage": {"cost_usd": 0.0002, "n_llm_calls": 1}, "seconds": 0.0}
        if ok:
            conv.trace.append(tp)
        else:
            rec["feedback_text"] = "STUB BLOCK"
        self.checks.append({"index": index, "trace_len": len(conv.trace), "ok": ok, "n_executed": len(executed)})
        return rec

    def commit(self, conv, rec):
        if not rec["action_allowed"]:
            conv.trace.append(rec["trace_position"])


# ============================================================================================ scenario

class Scenario:
    """A real retail conversation (copied tools and data) up to a fork attempt, as a ForkState, its source record
    and its ForkPoint.

    reads: extra executed get_order_details calls after the login (to set n_exec); blocks: blocked attempts of the
    same cancel call just before the fork (blocks in a row at the fork); pending: "cancel" or "respond"."""

    _aspm = None

    def __init__(self, reads: int = 1, blocks: int = 0, pending: str = "cancel", source_guard: str = "tgr",
                 decision_a: str = "block", decision_b: str = "allow", fork_id: str = "test_fork_1",
                 profile: str = "luna-dev", task_split: str = SPLIT, task_index: int = TASK, login: bool = True):
        self.db = load_db(DOMAIN)
        self.messages = [{"role": "system", "content": tau_copy.policy_text(DOMAIN)},
                         {"role": "user", "content": FIRST_USER}]
        self.executed = list(self.messages)
        self.attempts: List[dict] = []
        self.trace: List[dict] = []
        self.consecutive = 0
        if login:
            self.run_call("find_user_id_by_name_zip", LOGIN)
        for _ in range(reads):
            self.run_call("get_order_details", {"order_id": OID})
        cancel_args = {"order_id": OID, "reason": REASON}
        for _ in range(blocks):
            self.block_call("cancel_pending_order", cancel_args)
        i = len(self.attempts)
        if pending == "cancel":
            self.pending = tool_msg("cancel_pending_order", cancel_args, f"call_fork_{i}")
            action, arguments = "cancel_pending_order", cancel_args
        else:
            self.pending = reply_msg("Your order is cancelled.")
            action, arguments = "respond", {"content": "Your order is cancelled."}
        a_preds, names = self.circuit(action)
        values_a = {n: (False if n == "user_authenticated" else True) for n in names}
        values_b = dict(values_a, user_authenticated=True)
        src_vals = values_b if source_guard == "tgr_tracker" else values_a
        saved_tp = {**{p: p == action for p in a_preds}, **src_vals}
        self.fork_attempt = {"exec_step": len(self.trace), "attempt": self.consecutive + 1, "action": action,
                             "kwargs": arguments, "agent_text": "", "blocked": True, "cap_override": False,
                             "executed_prefix_len": len(self.executed),
                             "guard": {"trace_position": saved_tp, "action_allowed": False, "step_index": len(self.trace),
                                       "judge": {n: {"value": v, "evidence": "saved"} for n, v in src_vals.items()},
                                       "usage": {"cost_usd": 0.0003, "n_llm_calls": 1}}}
        fb = {"block": None, "allow": None}
        self.fork = ForkPoint(
            fork_id=fork_id, source="saved_tgr" if source_guard != "tgr_tracker" else "online_tracker",
            run="test_run", episodes_path="", line_no=0, agent={v: k for k, v in AGENTS_BY_PROFILE.items()}[profile],
            profile=profile, domain=DOMAIN, task_split=task_split, task_index=task_index, trial=0, attempt_index=i,
            exec_step=len(self.trace), attempt=self.consecutive + 1, action=action,
            arguments=arguments, source_guard=source_guard,
            decision_a=decision_a, decision_b=decision_b,
            feedback_a=FEEDBACK_A if decision_a == "block" else fb["allow"],
            feedback_b=FEEDBACK_B if decision_b == "block" else fb["allow"],
            kind="block removed" if decision_a == "block" else "block added",
            changed_predicates=[{"name": "user_authenticated", "judge": False, "tracker": True}],
            values_a=values_a, values_b=values_b)
        self.task_split, self.task_index = task_split, task_index

    @classmethod
    def circuit(cls, action: str):
        if cls._aspm is None:
            cls._aspm = guards_build.build_frozen(DOMAIN, tau_copy.tools_info(DOMAIN)).tgr.aspm
        aspm = cls._aspm
        names = sorted({n for r in aspm.circuit([action]) for n in aspm.rules[r].atoms} - aspm.action_predicates)
        return sorted(aspm.action_predicates), names

    def run_call(self, name: str, args: dict) -> None:
        cid = f"call_{len(self.attempts)}"
        out = run_tool(DOMAIN, self.db, name, copy.deepcopy(args))
        m = tool_msg(name, args, cid)
        t = {"role": "tool", "tool_call_id": cid, "name": name, "content": out}
        tp = {"prefix_step": len(self.trace)}
        self.attempts.append({"exec_step": len(self.trace), "attempt": self.consecutive + 1, "action": name,
                              "kwargs": args, "agent_text": "", "blocked": False, "cap_override": False,
                              "executed_prefix_len": len(self.executed),
                              "guard": {"trace_position": tp, "action_allowed": True}, "observation": out})
        self.messages += [m, t]
        self.executed += [m, t]
        self.trace.append(tp)
        self.consecutive = 0

    def block_call(self, name: str, args: dict) -> None:
        cid = f"call_{len(self.attempts)}"
        m = tool_msg(name, args, cid)
        fb = "BLOCKED by policy guardrail. (saved block)"
        self.attempts.append({"exec_step": len(self.trace), "attempt": self.consecutive + 1, "action": name,
                              "kwargs": args, "agent_text": "", "blocked": True, "cap_override": False,
                              "executed_prefix_len": len(self.executed),
                              "guard": {"trace_position": {"blocked": True}, "action_allowed": False},
                              "feedback": fb})
        self.messages += [m, {"role": "tool", "tool_call_id": cid, "name": name, "content": fb}]
        self.consecutive += 1

    def user_messages(self) -> List[dict]:
        msgs = [{"role": "system", "content": user_prompt(gt_task().instruction)},
                {"role": "user", "content": GREETING},
                {"role": "assistant", "content": FIRST_USER, "tool_calls": None}]
        for k in range(2, len(self.executed) - 1, 2):
            if self.executed[k + 1]["role"] == "user":
                msgs += [{"role": "user", "content": self.executed[k]["content"]},
                         {"role": "assistant", "content": self.executed[k + 1]["content"], "tool_calls": None}]
        return msgs

    def state(self) -> ForkState:
        env_actions = [{"name": fake_message_to_action(self.executed[k]).name,
                        "kwargs": fake_message_to_action(self.executed[k]).kwargs}
                       for k in range(2, len(self.executed) - 1, 2)]
        return ForkState(fork=copy.deepcopy(self.fork), task_split=self.task_split, task_index=self.task_index,
                         data=copy.deepcopy(self.db), env_actions=env_actions, messages=copy.deepcopy(self.messages),
                         executed=copy.deepcopy(self.executed), pending=copy.deepcopy(self.pending),
                         user_messages=self.user_messages(), trace=copy.deepcopy(self.trace),
                         consecutive_blocks=self.consecutive, n_exec=len(self.trace))

    def source(self) -> dict:
        i = len(self.attempts)
        return {"path": "test", "line_no": 0, "attempts_prefix": copy.deepcopy(self.attempts),
                "fork_attempt": copy.deepcopy(self.fork_attempt),
                "fork_trace_position": copy.deepcopy(self.fork_attempt["guard"]["trace_position"]),
                "messages_prefix": copy.deepcopy(self.messages), "pending": copy.deepcopy(self.pending),
                "executed_prefix": copy.deepcopy(self.executed),
                "source": {"reward": 0.0, "models": {"agent": "gpt-6-luna", "user": "gpt-6-luna", "guard": "gpt-6-luna"}},
                "_i": i}

    def episode(self) -> dict:
        """The source conversation as one episodes.jsonl line (the fork attempt blocked, then the end)."""
        msgs = self.messages + [self.pending, {"role": "tool" if self.fork.action != "respond" else "system",
                                               **({"tool_call_id": self.pending["tool_calls"][0]["id"],
                                                   "name": self.fork.action} if self.fork.action != "respond" else {}),
                                               "content": FEEDBACK_A}]
        return {"task_index": self.task_index, "trial": 0, "env": DOMAIN, "guard": self.fork.source_guard,
                "profile": self.fork.profile, "task_split": self.task_split, "error": None, "reward": 0.0,
                "models": {"agent": "gpt-6-luna", "user": "gpt-6-luna", "guard": "gpt-6-luna"},
                "attempts": self.attempts + [self.fork_attempt], "messages": msgs, "executed": self.executed}


AGENTS_BY_PROFILE = {"luna": "luna-dev", "nano": "nano-agent-luna"}


def guards_real():
    return guards_build.build_branch_guards(DOMAIN, tau_copy.tools_info(DOMAIN))


class TmpMixin:
    def setUp(self):
        self.tmp = os.path.join(TMP_ROOT, uuid.uuid4().hex[:12])
        os.makedirs(self.tmp)

    def tearDown(self):
        calls._llm = _NoLLM()
        shutil.rmtree(self.tmp, ignore_errors=True)
        try:
            os.rmdir(TMP_ROOT)
        except OSError:
            pass


def run(sc_or_state, branch, guard, agent=None, source=None, script=None, log=None, try_index=0, **kw):
    state = sc_or_state.state() if isinstance(sc_or_state, Scenario) else sc_or_state
    src = source if source is not None else sc_or_state.source()
    env = make_fake_env(state, script, log)
    fake_reset_usage()
    rec = rb.run_branch(state, branch, try_index, env=env, guard=guard, agent_completion=agent or FakeAgent(always_reply),
                        tools_info=tau_copy.tools_info(DOMAIN), source=src, message_to_action=fake_message_to_action,
                        usage_fn=fake_usage, **kw)
    return rec, env


# ============================================================================================ tests: one branch

class TestBranchesWithRealGuards(TmpMixin, unittest.TestCase):
    """Both real branch guards (frozen TGR, TGR + tracker) with a fake judge behind the per-try cache."""

    @classmethod
    def setUpClass(cls):
        cls.guards = guards_real()

    def judge(self):
        base = FakeCachedLLM(answer=allow_respond)
        return base, branch_cache.install(base)

    def run_both(self, sc: Scenario):
        base, proxy = self.judge()
        state = sc.state()
        before = copy.deepcopy(state)
        out = {}
        for b in ("A", "B"):
            agent = FakeAgent(always_reply)
            ulog: list = []
            with proxy.use(os.path.join(self.tmp, sc.fork.fork_id, b, "0", "structured")):
                rec, env = run(state, b, self.guards[b]["guard"], agent=agent, source=sc.source(), log=ulog)
            out[b] = {"rec": rec, "env": env, "agent": agent, "ulog": ulog}
        self.assertEqual(state, before, "run_branch changed the fork state")
        return out, base, state

    def test_same_start_different_fork_decision(self):
        sc = Scenario(reads=1)
        out, base, state = self.run_both(sc)
        i = sc.fork.attempt_index
        ra, rb_ = out["A"]["rec"], out["B"]["rec"]
        for r in (ra, rb_):
            self.assertIsNone(r["error"], r.get("traceback"))
            self.assertEqual(r["messages"][:2 + 2 * i], state.messages)
            self.assertEqual(r["executed"][:len(state.executed)], state.executed)
            self.assertEqual([x for x in r["attempts"][:i]], [dict(x, fork_part="prefix") for x in sc.attempts])
            self.assertEqual(r["messages"][2 + 2 * i], state.pending)
            self.assertEqual(r["fork_attempt_index"], i)
            self.assertEqual(r["attempts"][i]["fork_part"], "fork")
        # A: blocked with A's message, a tool message with the same call id; not executed
        tc = state.pending["tool_calls"][0]
        self.assertTrue(ra["attempts"][i]["blocked"])
        self.assertEqual(ra["attempts"][i]["feedback"], FEEDBACK_A)
        self.assertEqual(ra["messages"][3 + 2 * i], {"role": "tool", "tool_call_id": tc["id"],
                                                      "name": "cancel_pending_order", "content": FEEDBACK_A})
        self.assertEqual(len(ra["executed"]), len(state.executed) + 2)          # only the reply after it
        self.assertEqual(ra["attempts"][i + 1]["attempt"], 2)                    # blocks in a row went on
        self.assertEqual(ra["attempts"][i + 1]["exec_step"], state.n_exec)
        # B: executed, the real tool output in both lists
        self.assertFalse(rb_["attempts"][i]["blocked"])
        obs = rb_["attempts"][i]["observation"]
        self.assertIn('"status": "cancelled"', obs)
        self.assertEqual(rb_["messages"][3 + 2 * i], {"role": "tool", "tool_call_id": tc["id"],
                                                       "name": "cancel_pending_order", "content": obs})
        self.assertEqual(rb_["executed"][len(state.executed):len(state.executed) + 2], rb_["messages"][2 + 2 * i:4 + 2 * i])
        self.assertEqual(rb_["attempts"][i + 1]["attempt"], 1)
        # the first new agent call saw the shared prefix, the pending message and the branch's answer
        self.assertEqual(out["A"]["agent"].seen[0], state.messages + ra["messages"][2 + 2 * i:4 + 2 * i])
        self.assertEqual(out["B"]["agent"].seen[0], state.messages + rb_["messages"][2 + 2 * i:4 + 2 * i])
        self.assertEqual(out["A"]["agent"].seen[0][:-1], out["B"]["agent"].seen[0][:-1])
        # the fork record
        self.assertEqual((ra["fork_decision"], ra["fork_feedback"]), ("block", FEEDBACK_A))
        self.assertEqual((rb_["fork_decision"], rb_["fork_feedback"]), ("allow", None))
        self.assertEqual(ra["attempts"][i]["guard"]["fork_applied"]["guard"], "tgr_frozen")
        self.assertEqual(rb_["attempts"][i]["guard"]["fork_applied"]["guard"], "tgr_tracker")
        self.assertEqual((ra["guard"], rb_["guard"]), ("tgr_frozen", "tgr_tracker"))

    def test_guard_after_the_fork_is_the_branch_guard(self):
        sc = Scenario(reads=1)
        out, base, state = self.run_both(sc)
        i = sc.fork.attempt_index
        ga = out["A"]["rec"]["attempts"][i + 1]["guard"]
        gb = out["B"]["rec"]["attempts"][i + 1]["guard"]
        self.assertNotIn("tracker", ga)                         # frozen TGR record
        self.assertIn("tracker", gb)                            # TGR + tracker record
        self.assertIn("user_authenticated", gb["tracker"]["replaced"])
        self.assertTrue(ga["action_allowed"] and gb["action_allowed"])
        # the trace length the guard saw continues from the rebuild (+1 in B, where the fork action ran)
        self.assertEqual(ga["trace_len_before"], state.n_exec)
        self.assertEqual(gb["trace_len_before"], state.n_exec + 1)
        # one judge call per branch, each in its own try folder, none from a cache
        dirs = [x["cache_dir"] for x in base.log]
        self.assertEqual(len(base.log), 2)
        self.assertEqual(len(set(dirs)), 2)
        self.assertFalse(any(x["hit"] for x in base.log))
        self.assertTrue(all(d.startswith(self.tmp) for d in dirs))
        # the guard cost of the new check is counted; cost_usd adds agent, user and guard
        for b in ("A", "B"):
            r = out[b]["rec"]
            self.assertGreater(r["cost"]["guard"], 0)
            self.assertAlmostEqual(r["cost_usd"], r["cost"]["agent"] + r["cost"]["user"] + r["cost"]["guard"])
            self.assertEqual(r["cost"]["agent"], 0.001)
            self.assertEqual(r["cost"]["user"], 0.0005)

    def test_score_from_the_final_database(self):
        """The task is to cancel the order. B runs the cancel at the fork: reward 1. A blocks it: reward 0. τ-bench's
        scoring (calculate_reward in the env.step that ends the conversation) hashes the final env.data."""
        sc = Scenario(reads=1)
        out, base, state = self.run_both(sc)
        ra, rb_ = out["A"]["rec"], out["B"]["rec"]
        self.assertEqual((ra["reward"], ra["done"]), (0.0, True))
        self.assertEqual((rb_["reward"], rb_["done"]), (1.0, True))
        self.assertFalse(ra["reward_info"]["info"]["r_actions"])
        self.assertTrue(rb_["reward_info"]["info"]["r_actions"])
        self.assertEqual(state.data["orders"][OID]["status"], "pending")         # the fork state is untouched
        # the user simulator continued from the rebuilt list: its first new input is that list + the agent's reply
        for b in ("A", "B"):
            seen = out[b]["ulog"][0]
            self.assertEqual(seen, state.user_messages + [{"role": "user", "content": REPLY}])
            self.assertEqual(out[b]["rec"]["user_messages_final"], seen + [
                {"role": "assistant", "content": "###STOP###", "tool_calls": None}])

    def test_respond_fork_block_is_a_system_message(self):
        sc = Scenario(reads=1, pending="respond")
        out, base, state = self.run_both(sc)
        i = sc.fork.attempt_index
        ra, rb_ = out["A"]["rec"], out["B"]["rec"]
        self.assertEqual(ra["messages"][3 + 2 * i], {"role": "system", "content": FEEDBACK_A})
        self.assertEqual(ra["attempts"][i]["action"], "respond")
        # the blocked reply never reached the user simulator; in B it did (and the user ended the conversation)
        self.assertEqual(out["A"]["ulog"][0], state.user_messages + [{"role": "user", "content": REPLY}])
        self.assertEqual(out["B"]["ulog"][0], state.user_messages + [{"role": "user",
                                                                       "content": "Your order is cancelled."}])
        self.assertEqual(rb_["messages"][3 + 2 * i], {"role": "user", "content": "###STOP###"})
        self.assertEqual(rb_["n_exec_after_fork"], 1)
        self.assertEqual(rb_["calls"]["agent"], 0)


class TestTracePosition(unittest.TestCase):

    def test_frozen_source(self):
        sc = Scenario(source_guard="tgr")
        saved = sc.fork_attempt["guard"]["trace_position"]
        ta = rb.fork_trace_position(sc.fork, "A", saved)
        tb = rb.fork_trace_position(sc.fork, "B", saved)
        self.assertEqual(ta, saved)
        self.assertIs(ta["user_authenticated"], False)
        self.assertIs(tb["user_authenticated"], True)
        self.assertEqual({k: v for k, v in tb.items() if k != "user_authenticated"},
                         {k: v for k, v in ta.items() if k != "user_authenticated"})
        self.assertTrue(tb["cancel_pending_order"])

    def test_tracker_source(self):
        sc = Scenario(source_guard="tgr_tracker")
        saved = sc.fork_attempt["guard"]["trace_position"]
        self.assertIs(saved["user_authenticated"], True)
        self.assertEqual(rb.fork_trace_position(sc.fork, "B", saved), saved)
        self.assertIs(rb.fork_trace_position(sc.fork, "A", saved)["user_authenticated"], False)

    def test_values_cross_check(self):
        sc = Scenario(source_guard="tgr")
        saved = sc.fork_attempt["guard"]["trace_position"]
        sc.fork.values_b = dict(sc.fork.values_b, user_authenticated=False)
        with self.assertRaises(rb.ForkMismatch):
            rb.fork_trace_position(sc.fork, "B", saved)

    def test_allowed_fork_action_is_committed_to_the_trace(self):
        sc = Scenario(reads=2)
        seen = []
        g = StubGuard(lambda m, n: (seen.append(n) or True))
        rec, _ = run(sc, "B", g)
        self.assertEqual(g.checks[0]["trace_len"], sc.fork.exec_step + 2)   # + the fork action + this step
        rec, _ = run(sc, "A", StubGuard(lambda m, n: True))
        self.assertEqual(rec["attempts"][sc.fork.attempt_index]["guard"]["trace_len_before"], sc.fork.exec_step)


class TestLimits(unittest.TestCase):
    """The cap (3 blocks in a row, then the cap override) and the 30-step limit continue from the rebuilt counts."""

    def test_cap_counts_the_rebuilt_blocks(self):
        sc = Scenario(reads=1, blocks=2)                       # the fork is the 3rd try of the cancel
        i = sc.fork.attempt_index
        n = [0]

        def script(m):                                          # the cancel once more, then a reply
            n[0] += 1
            return tool_msg("cancel_pending_order", {"order_id": OID, "reason": REASON}, "c_again") if n[0] == 1 \
                else reply_msg()
        g = StubGuard(lambda m, n: bool(not m.get("tool_calls")))  # blocks every tool call, allows replies
        rec, env = run(sc, "A", g, agent=FakeAgent(script))
        self.assertIsNone(rec["error"], rec.get("traceback"))
        fa, nx = rec["attempts"][i], rec["attempts"][i + 1]
        self.assertEqual((fa["attempt"], fa["blocked"], fa["cap_override"]), (3, True, False))
        self.assertEqual((nx["attempt"], nx["blocked"], nx["cap_override"]), (4, False, True))   # 3 in a row: runs
        self.assertIn('"status": "cancelled"', nx["observation"])
        self.assertEqual(rec["n_cap_overrides_after_fork"], 1)
        self.assertEqual(rec["n_blocks"], 2 + 1)                 # 2 rebuilt + the fork
        self.assertEqual([c["ok"] for c in g.checks], [False, True])
        self.assertEqual(g.checks[1]["trace_len"], sc.fork.exec_step + 2)    # the override was committed
        self.assertEqual(rec["reward"], 1.0)

    def test_block_at_the_fork_after_three_is_a_cap_override(self):
        sc = Scenario(reads=1, blocks=3)                       # the fork is the 4th try: a block there runs
        i = sc.fork.attempt_index
        rec, env = run(sc, "A", StubGuard(lambda m, n: True))
        fa = rec["attempts"][i]
        self.assertEqual((fa["attempt"], fa["blocked"], fa["cap_override"]), (4, False, True))
        self.assertTrue(rec["fork_cap_override"])
        self.assertIn('"status": "cancelled"', fa["observation"])
        self.assertEqual(rec["reward"], 1.0)

    def test_step_limit_counts_from_n_exec(self):
        sc = Scenario(reads=27)                                # n_exec 28 at the fork
        state = sc.state()
        self.assertEqual(state.n_exec, 28)
        agent = FakeAgent(lambda m: tool_msg("get_order_details", {"order_id": OID}, f"c{len(m)}"))
        rec, env = run(sc, "B", StubGuard(lambda m, n: True), agent=agent)
        self.assertEqual(rec["n_exec_steps"], 30)
        self.assertEqual(rec["n_exec_after_fork"], 2)          # the fork action + 1 more
        self.assertEqual(rec["calls"]["agent"], 1)
        self.assertEqual((rec["done"], rec["reward"], rec["reward_info"]), (False, 0.0, None))
        self.assertEqual(len(rec["executed"]), 2 + 2 * 30)
        rec, env = run(sc, "A", StubGuard(lambda m, n: True), agent=agent)
        self.assertEqual((rec["n_exec_steps"], rec["n_exec_after_fork"], rec["calls"]["agent"]), (30, 2, 2))

    def test_custom_limits(self):
        sc = Scenario(reads=1)
        agent = FakeAgent(lambda m: tool_msg("get_order_details", {"order_id": OID}, f"c{len(m)}"))
        rec, env = run(sc, "B", StubGuard(lambda m, n: True), agent=agent, max_num_steps=5)
        self.assertEqual(rec["n_exec_steps"], 5)


class TestRecord(unittest.TestCase):

    def test_episode_compatible_fields(self):
        sc = Scenario(reads=1, blocks=1)
        rec, env = run(sc, "A", StubGuard(lambda m, n: True), try_index=3)
        for k in ("task_index", "reward", "done", "n_exec_steps", "n_blocks", "n_cap_overrides", "seconds", "cost",
                  "latency", "calls", "attempts", "messages", "executed", "reward_info", "error", "usage_roles",
                  "env", "guard", "trial", "profile", "cost_usd", "fork_id", "branch", "try", "fork",
                  "fork_attempt_index", "fork_decision", "task_split"):
            self.assertIn(k, rec)
        self.assertEqual(len(rec["messages"]), 2 + 2 * len(rec["attempts"]))
        self.assertEqual(len(rec["executed"]), 2 + 2 * rec["n_exec_steps"])
        for k, a in enumerate(rec["attempts"]):
            self.assertEqual(rec["messages"][2 + 2 * k]["role"], "assistant")
            if not a["blocked"]:
                p = a["executed_prefix_len"]
                self.assertEqual(rec["executed"][p:p + 2], rec["messages"][2 + 2 * k:4 + 2 * k])
            self.assertEqual(a["fork_part"], "prefix" if k < sc.fork.attempt_index else
                             ("fork" if k == sc.fork.attempt_index else "after"))
        self.assertEqual(rec["n_blocks"], 2)                   # 1 rebuilt block + the fork block of A
        self.assertEqual((rec["trial"], rec["try"], rec["source_trial"]), (3, 3, 0))
        self.assertEqual(rec["usage_roles"]["agent"]["calls"], rec["calls"]["agent"])
        json.dumps(rec)                                        # JSON-ready

    def test_error_in_the_loop_is_recorded(self):
        sc = Scenario(reads=1)

        def broken(m):
            raise RuntimeError("agent down")
        rec, env = run(sc, "A", StubGuard(lambda m, n: True), agent=FakeAgent(broken))
        self.assertIn("agent down", rec["error"])
        self.assertEqual((rec["reward"], rec["done"]), (0.0, False))
        self.assertIn("cost_usd", rec)
        self.assertEqual(len(rec["attempts"]), sc.fork.attempt_index + 1)   # the fork attempt was applied

    def test_check_state(self):
        sc = Scenario(reads=1, blocks=1)
        rb.check_state(sc.state(), sc.source(), tau_copy.policy_text(DOMAIN))
        for change in (lambda s: s.trace.pop(), lambda s: setattr(s, "consecutive_blocks", 0),
                       lambda s: s.messages.pop(), lambda s: setattr(s, "n_exec", 5),
                       lambda s: s.pending["tool_calls"][0]["function"].update(arguments="{}")):
            s = sc.state()
            change(s)
            with self.assertRaises(rb.ForkMismatch):
                rb.check_state(s, sc.source())
        with self.assertRaises(rb.ForkMismatch):
            rb.check_state(sc.state(), sc.source(), "another policy")

    def test_check_fork_point(self):
        sc = Scenario()
        self.assertEqual(rb.check_fork_point(sc.fork), [])
        for kw in ({"decision_b": "block"}, {"kind": "block added"}, {"feedback_a": None},
                   {"source_guard": "shield"}, {"changed_predicates": []}, {"fork_id": "../x"},
                   {"changed_predicates": [{"name": "user_authenticated", "judge": 0, "tracker": True}]}):
            f = dataclasses.replace(sc.fork, **kw)
            self.assertTrue(rb.check_fork_point(f), kw)

    def test_check_env(self):
        sc = Scenario(reads=1)
        state = sc.state()
        branch_env.check_env(make_fake_env(state), state)
        for change in (lambda e: e.actions.pop(), lambda e: e.user.messages.pop(),
                       lambda e: e.data["orders"][OID].update(status="cancelled"),
                       lambda e: setattr(e, "task_index", 5), lambda e: e.tasks.pop()):
            env = make_fake_env(state)
            change(env)
            with self.assertRaises(branch_env.EnvMismatch):
                branch_env.check_env(env, state)


class TestJudgeCache(TmpMixin, unittest.TestCase):

    def test_tries_get_separate_fresh_caches(self):
        sc = Scenario(reads=1)
        g = guards_real()["A"]["guard"]
        base = FakeCachedLLM(answer=allow_respond)
        proxy = branch_cache.install(base)
        for t in (0, 1):
            folder = os.path.join(rb.try_cache_dir(self.tmp, sc.fork.fork_id, "A", t), "structured")
            with proxy.use(folder):
                rec, _ = run(sc, "A", g, try_index=t)
            self.assertIsNone(rec["error"], rec.get("traceback"))
        self.assertEqual(len(base.log), 2)
        self.assertEqual(base.log[0]["user"], base.log[1]["user"])        # the same judge prompt in both tries
        self.assertEqual([x["hit"] for x in base.log], [False, False])     # but no shared answer
        self.assertNotEqual(base.log[0]["cache_dir"], base.log[1]["cache_dir"])
        self.assertTrue(base.log[1]["cache_dir"].endswith(os.path.join(sc.fork.fork_id, "A", "1", "structured")))
        # inside one try the cache works as in the runner (same prompt -> the same answer, from the cache)
        with proxy.use(os.path.join(self.tmp, "same")):
            run(sc, "A", g)
            run(sc, "A", g)
        self.assertEqual([x["hit"] for x in base.log[2:]], [False, True])
        # outside a try: no judge call at all
        with self.assertRaises(branch_cache.NoTryCache):
            proxy.call(stage="x", system="s", user="u", schema={}, schema_name="n")


# ============================================================================================ tests: run_all

class StandInSoftStop:
    """guard/soft_stop.py's interface (spent_usd, decide) with a scripted decision."""

    def __init__(self, go_checks: Optional[int] = None, spent: float = 0.0):
        self.go_checks, self.spent = go_checks, spent
        self.checks: List[tuple] = []

    def spent_usd(self, root=None):
        return self.spent

    def decide(self, spent, left_estimate):
        self.checks.append((spent, left_estimate))
        if self.go_checks is not None and len(self.checks) > self.go_checks:
            return False, "stand-in: stop"
        return True, "stand-in: go"


class FakeRuntime:
    """run_all's runtime with fakes: scripted agent, FakeEnv with a scripted user, stub or real guards, a fake judge
    behind the per-try cache. Records the order of the tries (judge_cache folders)."""

    def __init__(self, guards: Optional[dict] = None, agent: Optional[FakeAgent] = None, judge: bool = True):
        self.guards = guards
        self.agent_completion = agent or FakeAgent(always_reply)
        self.message_to_action = fake_message_to_action
        self.judge_base = FakeCachedLLM(answer=allow_respond) if judge else None
        self.proxy = None
        self.order: List[str] = []
        self.envs = 0
        self.setups: List[tuple] = []

    def setup(self, profile, cache_root, dry_run):
        self.setups.append((profile, cache_root, dry_run))
        if self.judge_base is not None and not dry_run:
            self.proxy = branch_cache.install(self.judge_base)
        return {"models": {"agent": "gpt-6-luna", "user": "gpt-6-luna", "guard": "gpt-6-luna",
                           "rulebuild": "gpt-6-luna"}}

    def domain(self, d):
        if self.guards is None:
            self.guards = {b: {"guard": StubGuard(lambda m, n: True), "info": {"branch_guard": BRANCH_GUARD[b]}}
                           for b in ("A", "B")}
        return {"tools_info": tau_copy.tools_info(d), "wiki": tau_copy.policy_text(d), "guards": self.guards}

    def make_env(self, state):
        self.envs += 1
        return make_fake_env(state)

    def reset_usage(self):
        fake_reset_usage()

    def usage(self):
        return fake_usage()

    def judge_cache(self, folder):
        self.order.append(os.path.relpath(folder, self.cache_root_seen(folder)))
        return self.proxy.use(folder) if self.proxy is not None else contextlib.nullcontext()

    @staticmethod
    def cache_root_seen(folder):
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(folder))))


class RunAllBase(TmpMixin):

    def make_files(self, scenarios: List[Scenario]) -> str:
        """Write the source episodes file and the fork points file; returns the fork points path."""
        ep_path = os.path.join(self.tmp, "episodes.jsonl")
        with open(ep_path, "w") as f:
            for k, sc in enumerate(scenarios):
                sc.fork.episodes_path = os.path.relpath(ep_path, PC_DIR)
                sc.fork.line_no = k
                f.write(json.dumps(sc.episode()) + "\n")
        pts = os.path.join(self.tmp, "fork_points.jsonl")
        with open(pts, "w") as f:
            for sc in scenarios:
                f.write(json.dumps(sc.fork.to_dict()) + "\n")
        self.by_id = {sc.fork.fork_id: sc for sc in scenarios}
        return pts

    def rebuild(self, fp: ForkPoint) -> ForkState:
        st = self.by_id[fp.fork_id].state()
        st.fork = fp
        return st

    def main(self, pts, *extra, rt=None, ss=None):
        self.out = os.path.join(self.tmp, "stage_b")
        self.cache = os.path.join(self.tmp, "cache")
        rt = rt or FakeRuntime()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = run_all.main([pts, "--out-root", self.out, "--cache-root", self.cache, *extra], runtime=rt,
                               rebuild_fn=self.rebuild, soft_stop=ss or StandInSoftStop(), safety=False)
        return res, buf.getvalue(), rt


class TestRunAll(RunAllBase, unittest.TestCase):

    def scenarios(self, n=2):
        return [Scenario(reads=1, fork_id=f"fk_{k}") for k in range(n)]

    def test_runs_every_try_interleaved_and_writes_files(self):
        pts = self.make_files(self.scenarios(2))
        res, log, rt = self.main(pts, "--tries", "2", "--workers", "1")
        self.assertEqual(res["counts"]["ran"], 8)
        self.assertEqual(res["counts"]["ok"], 8)
        want = [os.path.join(f, b, str(t), "structured") for t in (0, 1) for f in ("fk_0", "fk_1") for b in ("A", "B")]
        self.assertEqual(rt.order, want)
        for t in (0, 1):
            for f in ("fk_0", "fk_1"):
                for b in ("A", "B"):
                    r = jload(rb.try_path(self.out, f, b, t))
                    self.assertIsNone(r["error"], r.get("traceback"))
                    self.assertEqual((r["fork_id"], r["branch"], r["try"]), (f, b, t))
                    self.assertGreater(r["cost_usd"], 0)
                    self.assertEqual(r["reward"], 1.0 if b == "B" else 0.0)
                    self.assertTrue(r["judge_cache"].endswith(os.path.join(f, b, str(t))))
        self.assertIn("[v2-stage-b] DONE: 8 tries run (8 ok, 0 with an error), 0 already done, 0 not started", log)
        self.assertIn("[v2-stage-b] start:", log)

    def test_soft_stop_stops_new_tries(self):
        pts = self.make_files(self.scenarios(2))
        ss = StandInSoftStop(go_checks=4, spent=100.0)        # the plan's status check + 3 tries
        res, log, rt = self.main(pts, "--tries", "2", "--workers", "1", "--profile", "luna-dev", ss=ss)
        self.assertEqual(res["counts"]["ran"], 3)
        self.assertEqual(res["counts"]["not_started"], 5)
        self.assertIn("[v2-stage-b] STOPPED (soft stop):", log)
        self.assertEqual(len(rt.order), 3)
        self.assertEqual(log.count("STOPPED (soft stop)"), 1)
        # left_estimate = tries not started x mean cost (the Part 1 prior before any try finished)
        first = ss.checks[1]                                    # [0] is the plan's status line
        self.assertAlmostEqual(first[1], 8 * run_all.PRIOR_USD_PER_TRY["luna-dev"])
        self.assertEqual(first[0], 100.0)
        # after a finished try the mean of the finished tries is used, and this run's spend is added
        r0 = jload(rb.try_path(self.out, "fk_0", "A", 0))
        self.assertAlmostEqual(ss.checks[2][1], 7 * r0["cost_usd"])
        self.assertAlmostEqual(ss.checks[2][0], 100.0 + r0["cost_usd"])
        self.assertFalse(os.path.exists(rb.try_path(self.out, "fk_1", "B", 0)))

    def test_resume_skips_finished_and_keeps_failed_output(self):
        pts = self.make_files(self.scenarios(2))
        res, log, rt = self.main(pts, "--tries", "1", "--workers", "2")
        self.assertEqual(res["counts"]["ran"], 4)
        # make (fk_0, B, 0) a failed try, and leave a stale cache folder for (fk_1, A, 0) without its file
        p = rb.try_path(self.out, "fk_0", "B", 0)
        r = jload(p)
        r["error"] = "RuntimeError: test failure"
        with open(p, "w") as f:
            json.dump(r, f)
        os.remove(rb.try_path(self.out, "fk_1", "A", 0))
        stale = rb.try_cache_dir(self.cache, "fk_1", "A", 0)
        os.makedirs(os.path.join(stale, "structured"), exist_ok=True)
        before = os.path.getmtime(rb.try_path(self.out, "fk_0", "A", 0))
        res, log, rt = self.main(pts, "--tries", "1", "--workers", "1")
        self.assertEqual(res["already_done"], 2)
        self.assertEqual(res["failed_to_rerun"], 1)
        self.assertEqual(res["counts"]["ran"], 2)
        self.assertEqual(sorted(rt.order), sorted([os.path.join("fk_0", "B", "0", "structured"),
                                                   os.path.join("fk_1", "A", "0", "structured")]))
        self.assertEqual(os.path.getmtime(rb.try_path(self.out, "fk_0", "A", 0)), before)    # untouched
        kept = os.path.join(self.out, "fk_0", "B", "0.failed1.json")
        self.assertEqual(jload(kept)["error"], "RuntimeError: test failure")
        self.assertIsNone(jload(p)["error"])
        self.assertTrue(os.path.isdir(os.path.join(self.cache, "fk_0", "B", "0.failed1")))
        self.assertTrue(os.path.isdir(stale + ".stale1"))
        self.assertIn("moved_before_rerun", jload(p))
        # a third run: nothing to do
        res, log, rt = self.main(pts, "--tries", "1")
        self.assertEqual((res["counts"]["ran"], res["already_done"]), (0, 4))

    def test_dry_run_makes_no_llm_call_and_writes_nothing(self):
        scs = self.scenarios(2)
        pts = self.make_files(scs)
        agent = FakeAgent(always_reply)
        rt = FakeRuntime(agent=agent)
        res, log, rt = self.main(pts, "--dry-run", rt=rt)
        self.assertEqual(agent.seen, [])
        self.assertEqual(rt.judge_base.log, [])
        self.assertEqual(rt.envs, 2)                            # every fork rebuilt and its env built
        self.assertFalse(os.path.exists(self.out))
        self.assertFalse(os.path.exists(self.cache))
        self.assertEqual(res["dry_run"]["forks_ok"], 2)
        self.assertEqual(res["dry_run"]["problems"], [])
        self.assertEqual(res["to_run"], 4 * 5)
        self.assertIn("[v2-stage-b] DRY RUN DONE: 2 of 2 forks rebuilt and checked, 0 problem(s)", log)
        self.assertEqual(rt.setups[0][2], True)

    def test_dry_run_lists_a_bad_fork(self):
        scs = self.scenarios(2)
        pts = self.make_files(scs)
        good = self.rebuild

        def rebuild(fp):
            st = good(fp)
            if fp.fork_id == "fk_1":
                st.trace = st.trace[:-1]
            return st
        self.rebuild = rebuild
        res, log, rt = self.main(pts, "--dry-run")
        self.assertEqual(res["dry_run"]["forks_ok"], 1)
        self.assertEqual(len(res["dry_run"]["problems"]), 1)
        self.assertIn("fk_1", res["dry_run"]["problems"][0])

    def test_failed_rebuild_is_a_failed_try(self):
        pts = self.make_files(self.scenarios(1))

        def rebuild(fp):
            raise RuntimeError("rebuild failed (test)")
        self.rebuild = rebuild
        res, log, rt = self.main(pts, "--tries", "1")
        self.assertEqual(res["counts"]["error"], 2)
        r = jload(rb.try_path(self.out, "fk_0", "A", 0))
        self.assertIn("rebuild failed", r["error"])
        self.assertEqual(r["cost_usd"], 0.0)


class TestRefusals(RunAllBase, unittest.TestCase):

    def test_profile_choices(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                run_all.parse_args(["x.jsonl", "--profile", "grok-eval"])
        with self.assertRaises(SystemExit):
            run_all.parse_args(["x.jsonl", "--branches", "A,C"])

    def test_test_group_and_task_splits(self):
        labels = {d: v["split"] for d, v in jload(paths.SPLITS_FILE).items()}
        test_ids = sorted(int(k) for k, v in labels["retail"].items() if v == "test")
        train_ids = sorted(int(k) for k, v in labels["retail"].items() if v == "train")
        sc = Scenario()
        f = sc.fork
        self.assertIsNone(run_all.task_refusal(dataclasses.replace(f, task_split="train", task_index=499), labels))
        self.assertIsNone(run_all.task_refusal(dataclasses.replace(f, task_split="test", task_index=train_ids[0]),
                                               labels))
        for kw in ({"task_split": "test", "task_index": test_ids[0]}, {"task_split": "train", "task_index": 500},
                   {"task_split": "train", "domain": "airline"}, {"task_split": "dev", "task_index": 0}):
            self.assertIsNotNone(run_all.task_refusal(dataclasses.replace(f, **kw), labels), kw)
        bad = Scenario(fork_id="fk_test", task_split="test", task_index=test_ids[0])
        pts = self.make_files([bad])
        with self.assertRaises(run_all.RunRefused):
            self.main(pts, "--dry-run")

    def test_profile_and_agent_must_match(self):
        sc = Scenario()
        sc.fork.agent = "nano"
        pts = self.make_files([sc])
        with self.assertRaises(run_all.RunRefused):
            self.main(pts, "--dry-run")

    def test_mixed_profiles_need_profile(self):
        a, b = Scenario(fork_id="fk_l"), Scenario(fork_id="fk_n", profile="nano-agent-luna")
        pts = self.make_files([a, b])
        with self.assertRaises(run_all.RunRefused):
            self.main(pts, "--dry-run")
        res, log, rt = self.main(pts, "--dry-run", "--profile", "nano-agent-luna")
        self.assertEqual((res["forks"], res["forks_other_profile_skipped"]), (1, 1))

    def test_paths_stay_in_output(self):
        for bad in ({"out_root": PC_DIR}, {"out_root": os.path.expanduser("~/ShieldAgent/output")},
                    {"out_root": paths.OUTPUT_DIR}, {"cache_root": os.path.join(PC_DIR, "from_shieldagent")}):
            with self.assertRaises(run_all.RunRefused):
                run_all.resolve_roots(bad.get("out_root", run_all.STAGE_B_DIR), bad.get("cache_root"))
        o, c = run_all.resolve_roots(run_all.STAGE_B_DIR, None)
        self.assertEqual(c, os.path.realpath(os.path.join(paths.OUTPUT_DIR, "_llmcache", "eval_v2_stage_b")))
        self.assertTrue(run_all.spend_seen_by_soft_stop(o))
        self.assertTrue(run_all.spend_seen_by_soft_stop(os.path.join(paths.OUTPUT_DIR, "eval_v2", "smoke", "stage_b")))
        self.assertFalse(run_all.spend_seen_by_soft_stop(os.path.join(paths.OUTPUT_DIR, "elsewhere")))
        with self.assertRaises(rb.ForkMismatch):
            rb.try_path(o, "..", "A", 0)

    def test_spend_gate_counts_own_spend_until_the_next_scan(self):
        ss = StandInSoftStop(spent=10.0)
        t = [0.0]
        g = run_all.SpendGate(ss, 0.01, [], 5, seen_by_scan=True, refresh_s=60, clock=lambda: t[0])
        self.assertIsNone(g.try_start())
        g.finished(2.0, True)
        self.assertEqual(g.spent(), 12.0)                       # own spend added until the next scan
        t[0] = 61.0
        ss.spent = 12.5
        self.assertEqual(g.spent(), 12.5)                       # the scan sees the file: not counted twice
        g2 = run_all.SpendGate(ss, 0.01, [], 5, seen_by_scan=False, refresh_s=0, clock=lambda: t[0])
        g2.finished(1.0, True)
        self.assertEqual(g2.spent(), 13.5)                      # a folder the scan cannot see: always added


_DRY_RUN_PROBE = r"""
import contextlib, io, json, os, socket, sys
sys.dont_write_bytecode = True
pc, tmp = sys.argv[1], sys.argv[2]
sys.path.insert(0, pc)
from tests import test_eval_v2_fork as T
from fork import run_all
from guard import write_guard
case = T.RunAllBase()
case.tmp = tmp
pts = os.path.join(tmp, "fork_points.jsonl")
case.by_id = {sc.fork.fork_id: sc for sc in [T.Scenario(reads=1, fork_id=f"fk_{k}") for k in range(2)]}
for line in open(pts):
    d = json.loads(line)
    case.by_id[d["fork_id"]].fork = T.ForkPoint.from_dict(d)
agent = T.FakeAgent(T.always_reply)
rt = T.FakeRuntime(agent=agent)
out, cache = os.path.join(tmp, "stage_b"), os.path.join(tmp, "cache")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    res = run_all.main([pts, "--out-root", out, "--cache-root", cache, "--dry-run"], runtime=rt,
                       rebuild_fn=case.rebuild, soft_stop=T.StandInSoftStop(), safety=True)
rep = {"forks_ok": res["dry_run"]["forks_ok"], "agent_calls": len(agent.seen), "judge_calls": len(rt.judge_base.log),
       "write_guard": write_guard.installed(), "out_exists": os.path.exists(out), "cache_exists": os.path.exists(cache),
       "done_line": "DRY RUN DONE" in buf.getvalue()}
try:
    open(os.path.join(pc, "output", "logs", "v2_b3_dry_probe.tmp"), "w").close()
    rep["write_in_output"] = "WRITTEN"
except PermissionError:
    rep["write_in_output"] = "refused"
try:
    socket.create_connection(("example.com", 443), timeout=2)
    rep["network"] = "CONNECTED"
except RuntimeError:
    rep["network"] = "blocked"
except OSError as e:
    rep["network"] = "oserror " + str(e)
print(json.dumps(rep))
"""


class TestDryRunSafetyInAFreshProcess(RunAllBase, unittest.TestCase):

    def test_dry_run_with_the_real_write_guard_and_network_block(self):
        scs = [Scenario(reads=1, fork_id=f"fk_{k}") for k in range(2)]
        self.make_files(scs)
        r = subprocess.run([sys.executable, "-B", "-c", _DRY_RUN_PROBE, PC_DIR, self.tmp], capture_output=True,
                           text=True, cwd=PC_DIR, timeout=600, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        rep = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(rep, {"forks_ok": 2, "agent_calls": 0, "judge_calls": 0, "write_guard": True,
                               "out_exists": False, "cache_exists": False, "done_line": True,
                               "write_in_output": "refused", "network": "blocked"})


# ============================================================================================ venv: real τ-bench env

_VENV_PROBE = r"""
import json, os, sys
from types import SimpleNamespace
sys.dont_write_bytecode = True
pc, tmp = sys.argv[1], sys.argv[2]
NET = []
def _no_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname"):
        NET.append(event)
        raise RuntimeError("network blocked in this test")
sys.addaudithook(_no_network)
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
sys.path.insert(0, pc)
from tests import test_eval_v2_fork as T
from fork import branch_cache, branch_env, guards_build, run_branch as rb
import tau_bench.envs.user as user_mod
from tau_bench.envs import get_env
USER_CALLS = []
def fake_user_completion(model=None, custom_llm_provider=None, messages=None, **_):
    USER_CALLS.append(json.loads(json.dumps(messages)))
    msg = SimpleNamespace(content="###STOP###", model_dump=lambda: {"role": "assistant", "content": "###STOP###",
                                                                   "tool_calls": None})
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], _hidden_params={"response_cost": 0.0})
user_mod.completion = fake_user_completion
probe = get_env("retail", user_strategy="human", user_model="x", task_split="test", task_index=0)
guards = guards_build.build_branch_guards("retail", probe.tools_info)
sc = T.Scenario(reads=1)
real_task = get_env("retail", user_strategy="human", user_model="x", task_split="train", task_index=T.TASK).task
base = T.FakeCachedLLM(answer=T.allow_respond)
proxy = branch_cache.install(base)
out = {"wiki_same": probe.wiki == sc.messages[0]["content"], "tools_sha": guards["A"]["info"]["tools_sha256"]}
makers = [("branch_env", lambda st: branch_env.make_env(st, "gpt-6-luna"))]
try:
    from fork import rebuild as RB
    if hasattr(RB, "make_env"):
        makers.append(("rebuild", lambda st: RB.make_env(st, user_model="gpt-6-luna")))
except ImportError:
    pass
for name, mk in makers:
    for b in ("A", "B"):
        st = sc.state()
        # the real task's user-simulator prompt (τ-bench's own build_system_prompt)
        from tau_bench.envs.user import LLMUserSimulationEnv
        st.user_messages[0]["content"] = LLMUserSimulationEnv.build_system_prompt(None, real_task.instruction)
        st.extra["instruction"] = real_task.instruction
        n_user = len(USER_CALLS)
        try:
            env = mk(st)
        except Exception as e:
            out[f"{name}_{b}"] = {"make_env_error": f"{type(e).__name__}: {e}"}
            continue
        made_calls = len(USER_CALLS) - n_user
        branch_env.check_env(env, st)
        agent = T.FakeAgent(T.always_reply)
        with proxy.use(os.path.join(tmp, name, b, "structured")):
            rec = rb.run_branch(st, b, 0, env=env, guard=guards[b]["guard"], agent_completion=agent,
                                tools_info=probe.tools_info, source=sc.source())
        out[f"{name}_{b}"] = {"error": rec["error"], "reward": rec["reward"], "done": rec["done"],
                              "r_actions": (rec["reward_info"] or {}).get("info", {}).get("r_actions"),
                              "user_calls_in_make_env": made_calls,
                              "user_saw_rebuilt": USER_CALLS[-1] == st.user_messages + [
                                  {"role": "user", "content": T.REPLY}],
                              "fork_blocked": rec["attempts"][sc.fork.attempt_index]["blocked"],
                              "n_exec_after_fork": rec["n_exec_after_fork"], "type": type(env.user).__name__}
out["network_attempts"] = len(NET)
out["judge_calls"] = len(base.log)
print(json.dumps(out))
"""


_VENV_RUN_ALL = r"""
import contextlib, io, json, os, sys
from types import SimpleNamespace
sys.dont_write_bytecode = True
pc, tmp = sys.argv[1], sys.argv[2]
NET = []
def _no_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname"):
        NET.append(event)
        raise RuntimeError("network blocked in this test")
sys.addaudithook(_no_network)
sys.path.insert(0, pc)
from tests import test_eval_v2_fork as T
from fork import run_all
from guard import write_guard
USER_CALLS = []
def fake_user_completion(model=None, custom_llm_provider=None, messages=None, **_):
    USER_CALLS.append(len(messages))
    msg = SimpleNamespace(content="###STOP###", model_dump=lambda: {"role": "assistant", "content": "###STOP###",
                                                                   "tool_calls": None})
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], _hidden_params={"response_cost": 0.0})
pts = os.path.join(tmp, "fork_points.jsonl")
out, cache = os.path.join(tmp, "stage_b"), os.path.join(tmp, "cache")
judge = T.FakeCachedLLM(answer=T.allow_respond)
agent = T.FakeAgent(T.always_reply)
rep = {}
for k in range(2):
    rt = run_all.TauRuntime(agent_completion=agent, user_completion=fake_user_completion, judge_base=judge)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = run_all.main([pts, "--out-root", out, "--cache-root", cache, "--tries", "1", "--workers", "2"],
                           runtime=rt, safety=True)
    rep[f"run{k}"] = {"counts": res["counts"], "already_done": res["already_done"], "fakes": res["setup"]["fakes"],
                      "make_env": res["setup"]["make_env"], "done_line": "[v2-stage-b] DONE:" in buf.getvalue()}
tries = {}
for b in ("A", "B"):
    r = json.load(open(os.path.join(out, "fk_e2e", b, "0.json")))
    tries[b] = {"error": r["error"], "reward": r["reward"], "guard": r["guard"], "fork_decision": r["fork_decision"],
                "cost_usd": r["cost_usd"], "n_exec_after_fork": r["n_exec_after_fork"],
                "seed_written": (r.get("judge_seed") or {}).get("written"),
                "cache_files": sum(len(f) for _, _, f in os.walk(os.path.join(cache, "fk_e2e", b, "0")))}
rep["tries"] = tries
rep["network_attempts"] = len(NET)
rep["write_guard"] = write_guard.installed()
rep["refused_writes"] = len(write_guard.REFUSED)
rep["judge_calls"] = len(judge.log)
rep["user_calls"] = len(USER_CALLS)
print(json.dumps(rep))
"""


@unittest.skipUnless(os.path.exists(VENV_PY), "venv Python not found")
class TestRunAllInTheVenv(RunAllBase, unittest.TestCase):
    """fork/run_all.py main() end to end in the venv: the real runtime (model routing, τ-bench, both guards,
    fork/rebuild.py rebuild and make_env, guard/soft_stop.py, the write guard), with the agent, user and judge fakes
    passed to TauRuntime; then a second run resumes (nothing to do). Network blocked."""

    def test_run_all_end_to_end_with_fakes(self):
        try:
            from fork import rebuild as b2_rebuild                # noqa: F401
        except ImportError:
            self.skipTest("fork/rebuild.py not there yet")
        sc = Scenario(reads=1, fork_id="fk_e2e")
        make_real(sc, user_authenticated=False)          # a fork point the real guards agree with (the judge seed checks it)
        self.make_files([sc])
        r = subprocess.run([VENV_PY, "-B", "-c", _VENV_RUN_ALL, PC_DIR, self.tmp], capture_output=True, text=True,
                           cwd=PC_DIR, timeout=900, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        rep = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(rep["network_attempts"], 0)
        self.assertTrue(rep["write_guard"])
        self.assertEqual(rep["refused_writes"], 0)
        self.assertEqual(rep["run0"]["counts"]["ok"], 2)
        self.assertEqual((rep["run1"]["counts"]["ran"], rep["run1"]["already_done"]), (0, 2))
        self.assertEqual(rep["run0"]["fakes"], ["agent", "user", "judge"])
        self.assertTrue(rep["run0"]["done_line"])
        a, b = rep["tries"]["A"], rep["tries"]["B"]
        self.assertEqual((a["error"], a["reward"], a["guard"], a["fork_decision"]), (None, 0.0, "tgr_frozen", "block"))
        self.assertEqual((b["error"], b["reward"], b["guard"], b["fork_decision"]), (None, 1.0, "tgr_tracker", "allow"))
        self.assertEqual((a["n_exec_after_fork"], b["n_exec_after_fork"]), (1, 2))
        self.assertGreater(a["cache_files"], 0)                 # each try's judge answers are in its own folder
        self.assertGreater(b["cache_files"], 0)
        self.assertEqual((a["seed_written"], b["seed_written"]), (True, True))   # + the fork attempt's seed
        self.assertEqual(rep["judge_calls"], 2)
        self.assertEqual(rep["user_calls"], 2)                  # one reply per branch; no call to build an env


@unittest.skipUnless(os.path.exists(VENV_PY), "venv Python not found")
class TestRealTauBenchEnvInTheVenv(TmpMixin, unittest.TestCase):
    """The real τ-bench env (venv), built at the fork with no LLM call (fork/branch_env.py make_env, and
    fork/rebuild.py make_env if it exists), real branch guards, fake agent, user and judge, network blocked."""

    def test_branches_in_the_real_env(self):
        r = subprocess.run([VENV_PY, "-B", "-c", _VENV_PROBE, PC_DIR, self.tmp], capture_output=True, text=True,
                           cwd=PC_DIR, timeout=900, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        rep = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertTrue(rep["wiki_same"])
        self.assertEqual(rep["network_attempts"], 0)
        self.assertIn("branch_env_A", rep)
        try:
            from fork import rebuild as b2_rebuild
            if hasattr(b2_rebuild, "make_env"):                 # fork/run_all.py uses it when it exists
                self.assertIn("rebuild_A", rep)
                self.assertIn("rebuild_B", rep)
        except ImportError:
            pass
        for key, v in rep.items():
            if not isinstance(v, dict):
                continue
            self.assertNotIn("make_env_error", v, key)
            self.assertIsNone(v["error"], key)
            self.assertEqual(v["user_calls_in_make_env"], 0, key)
            self.assertTrue(v["user_saw_rebuilt"], key)
            self.assertEqual(v["type"], "LLMUserSimulationEnv", key)
            self.assertTrue(v["done"], key)
            if key.endswith("_A"):
                self.assertEqual((v["reward"], v["r_actions"], v["fork_blocked"], v["n_exec_after_fork"]),
                                 (0.0, False, True, 1), key)
            else:
                self.assertEqual((v["reward"], v["r_actions"], v["fork_blocked"], v["n_exec_after_fork"]),
                                 (1.0, True, False, 2), key)


# ============================================================================================ tests: fix round 1 (F2)

from fork import judge_seed                                         # noqa: E402
from fork import points_tgr as PT                                   # noqa: E402

CANCEL_ARGS = {"order_id": OID, "reason": REASON}
SAVED_CALL = {"stage": "tgr_judge", "effort": "medium", "n": 1, "cache_hit": 0, "seconds": 4.44,
              "input_tokens": 7975, "output_tokens": 293, "reasoning_tokens": 191}
_OFFLINE: Dict[str, Any] = {}
_NEG_ALL: List[set] = []


def _off():
    if "retail" not in _OFFLINE:
        _OFFLINE["retail"] = PT.OfflineGuards(DOMAIN)
    return _OFFLINE["retail"]


def allow_all(names: List[str]) -> Dict[str, Any]:
    """A judge that lets everything through: every negated predicate false, every other true."""
    if not _NEG_ALL:
        rs = load_rule_set(paths.rule_set_path(DOMAIN))
        _NEG_ALL.append({x for r in rs["rules"] for x in rs["predicates"] if f"NOT {x}" in r["logic"]})
    return {n: n not in _NEG_ALL[0] for n in names}


def make_real(sc: Scenario, user_authenticated: bool, source_guard: str = "tgr"):
    """Make the scenario's fork point and saved fork attempt what fork/find_points.py gives for the real guards: both
    guards run offline (fork/points_tgr.py) on the fork attempt with the judge's values (negated predicates false,
    the others true, user_authenticated as given; evidence "saved evidence for <name>"). The saved record gets a
    judge usage like a real one. Returns (record A, record B, judge values)."""
    off = _off()
    st = sc.state()
    _, names = Scenario.circuit(sc.fork.action)
    vals = allow_all(names)
    vals["user_authenticated"] = user_authenticated
    judged = {n: {"value": v, "evidence": f"saved evidence for {n}"} for n, v in vals.items()}
    ra = off.check("A", st.executed, st.pending, st.n_exec, st.trace, judged)
    rb_ = off.check("B", st.executed, st.pending, st.n_exec, st.trace, judged)
    saved = json.loads(json.dumps(ra if source_guard != "tgr_tracker" else rb_))
    saved["calls"] = [dict(SAVED_CALL)]
    saved["usage"] = {"n_llm_calls": 1, "cache_hits": 0, "input_tokens": 7975, "output_tokens": 293,
                      "reasoning_tokens": 191, "api_seconds": 4.4, "cost_usd": 0.000944,
                      "calls_by_stage": {"tgr_judge": 1}}
    f = sc.fork
    f.source_guard = source_guard
    f.source = "online_tracker" if source_guard == "tgr_tracker" else "saved_tgr"
    f.decision_a = "allow" if ra["action_allowed"] else "block"
    f.decision_b = "allow" if rb_["action_allowed"] else "block"
    f.kind = {("block", "allow"): "block removed", ("allow", "block"): "block added"}.get((f.decision_a, f.decision_b),
                                                                                       "no fork")
    f.feedback_a, f.feedback_b = PT.feedback_of(ra), PT.feedback_of(rb_)
    f.changed_predicates = [{"name": n, "judge": vals[n], "tracker": rb_["judge"][n]["value"]}
                            for n in rb_["tracker"]["changed"]]
    f.values_a = dict(vals)
    f.values_b = {n: x["value"] for n, x in rb_["judge"].items()}
    f.margin_a, f.margin_b = ra.get("margin"), rb_.get("margin")
    f.violated_a = [v["rule_id"] for v in ra["violated_rules"]] if not ra["action_allowed"] else []
    f.violated_b = [v["rule_id"] for v in rb_["violated_rules"]] if not rb_["action_allowed"] else []
    sc.fork_attempt["guard"] = saved
    sc.fork_attempt["blocked"] = not saved["action_allowed"]
    return ra, rb_, vals


def repeat_then_reply(i: int) -> Callable[[List[dict]], dict]:
    """The weak agent's habit: right after the fork attempt (attempt i) it sends the same call again (a new call id),
    then a reply."""
    def script(m):
        if len(m) == 4 + 2 * i:
            return tool_msg("cancel_pending_order", CANCEL_ARGS, "call_repeat")
        return reply_msg()
    return script


def files_in(folder: str) -> List[str]:
    return sorted(os.path.join(d, x) for d, _, fs in os.walk(folder) for x in fs)


class TestJudgeSeed(TmpMixin, unittest.TestCase):
    """F2 item 1 (audit A5 W1): each try's fresh judge cache gets the source judge's answer to the fork attempt, at the
    key the copied LLM.call uses. An exact repeat of the blocked fork call is then a cache hit with the same decision
    (as in the source runs); any other prompt calls the judge."""

    @classmethod
    def setUpClass(cls):
        cls.guards = guards_real()

    def proxy(self):
        base = FakeCachedLLM(answer=allow_all)                  # a fresh judge call lets everything through
        return base, branch_cache.install(base)

    def folder(self, name: str) -> str:
        return os.path.join(self.tmp, name, "structured")

    def run_try(self, sc: Scenario, branch: str, script, seed: bool = True, name: Optional[str] = None):
        base, proxy = self.proxy()
        state, source = sc.state(), sc.source()
        g = self.guards[branch]["guard"]
        with proxy.use(self.folder(name or branch)):
            info = run_all.seed_fork_judge(g, state, source, branch) if seed else None
            rec, _ = run(state, branch, g, agent=FakeAgent(script), source=source)
        self.assertIsNone(rec["error"], rec.get("traceback"))
        return rec, info, base

    def test_exact_repeat_after_a_blocked_fork_is_a_cache_hit_branch_a(self):
        sc = Scenario(reads=1)
        make_real(sc, user_authenticated=False)                 # the judge misses the login: A blocks, B allows
        self.assertEqual((sc.fork.decision_a, sc.fork.decision_b), ("block", "allow"))
        i = sc.fork.attempt_index
        rec, info, base = self.run_try(sc, "A", repeat_then_reply(i))
        self.assertTrue(info["written"], info)
        self.assertTrue(info["decision_matches"] and info["feedback_matches"])
        self.assertEqual(info["from"], "saved guard record of the fork attempt (attempts[i].guard.judge)")
        self.assertTrue(os.path.exists(os.path.join(PC_DIR, info["file"])))
        rep = rec["attempts"][i + 1]
        self.assertEqual((rep["action"], rep["attempt"], rep["blocked"]), ("cancel_pending_order", 2, True))
        self.assertEqual(rep["feedback"], sc.fork.feedback_a)                  # blocked again, the same message
        self.assertEqual(rep["guard"]["usage"]["cache_hits"], 1)
        self.assertEqual(rep["guard"]["usage"]["input_tokens"], SAVED_CALL["input_tokens"])   # usage as the cache has it
        self.assertGreater(rep["guard"]["usage"]["cost_usd"], 0)
        self.assertTrue(base.log[0]["hit"])
        # the seed record has LLM.call's layout
        with open(os.path.join(PC_DIR, info["file"]), encoding="utf-8") as fh:
            seeded = json.load(fh)
        for k in ("key", "stage", "params", "system", "user", "output_text", "parsed", "response", "usage", "seconds",
                  "created", "seed"):
            self.assertIn(k, seeded)
        self.assertEqual(seeded["params"], {"model": "fake-judge", "effort": "medium", "max_output_tokens": 16000,
                                            "schema_name": "predicate_values", "schema": seeded["params"]["schema"],
                                            "sample": 0})
        self.assertEqual(os.path.basename(info["file"]), seeded["key"] + ".json")
        # without the seed, the same repeat is a fresh judge call, and this fresh judge lets it through (the bias)
        rec2, _, base2 = self.run_try(sc, "A", repeat_then_reply(i), seed=False, name="noseed")
        self.assertFalse(base2.log[0]["hit"])
        self.assertFalse(rec2["attempts"][i + 1]["blocked"])

    def test_a_non_repeat_calls_the_judge(self):
        sc = Scenario(reads=1)
        make_real(sc, user_authenticated=False)
        rec, info, base = self.run_try(sc, "A", always_reply)
        self.assertTrue(info["written"])
        self.assertEqual([x["hit"] for x in base.log], [False])              # the reply's judge prompt is new
        self.assertEqual(len(files_in(self.folder("A"))), 2)                  # the seed + that call

    def test_block_added_branch_b_and_the_same_seed_in_both_branches(self):
        sc = Scenario(reads=1, login=False)
        make_real(sc, user_authenticated=True)                  # the judge says logged in; the tracker sees no login
        self.assertEqual((sc.fork.decision_a, sc.fork.decision_b), ("allow", "block"))
        i = sc.fork.attempt_index
        rec, info_b, base = self.run_try(sc, "B", repeat_then_reply(i))
        self.assertTrue(info_b["written"], info_b)
        rep = rec["attempts"][i + 1]
        self.assertEqual((rep["blocked"], rep["guard"]["usage"]["cache_hits"]), (True, 1))
        self.assertIn("tracker", rep["guard"])
        self.assertEqual(rep["feedback"], sc.fork.feedback_b)
        base, proxy = self.proxy()
        with proxy.use(self.folder("A")):
            info_a = run_all.seed_fork_judge(self.guards["A"]["guard"], sc.state(), sc.source(), "A")
        self.assertTrue(info_a["written"])
        self.assertEqual(info_a["key"], info_b["key"])          # both guards send the same judge prompt at the fork
        with open(os.path.join(PC_DIR, info_a["file"]), encoding="utf-8") as fa, \
                open(os.path.join(PC_DIR, info_b["file"]), encoding="utf-8") as fb:
            ja, jb = json.load(fa), json.load(fb)
        self.assertEqual((ja["parsed"], ja["usage"]), (jb["parsed"], jb["usage"]))

    def test_tracker_source_seed_comes_from_the_run_judge_cache(self):
        sc = Scenario(reads=1, source_guard="tgr_tracker")
        ra, rb_, vals = make_real(sc, user_authenticated=False, source_guard="tgr_tracker")
        self.assertEqual((sc.fork.decision_a, sc.fork.decision_b), ("block", "allow"))
        st = sc.state()
        off = _off()
        names = PT.judge_names(off.frozen, rb_["circuit"])
        system, user = PT.judge_prompt(off.frozen, st.executed, rb_["action_text"], rb_["circuit"], names)
        key = PT.judge_cache_key(system, user, "gpt-6-luna", "medium")       # the source run's key
        src_cache = os.path.join(self.tmp, "source_run_cache", "structured")
        word = {True: "true", False: "false", None: "unknown"}
        src = {"key": key, "stage": "tgr_judge", "params": {"model": "gpt-6-luna"}, "system": system, "user": user,
               "output_text": "{}", "parsed": {"predicates": [{"name": n, "value": word[vals[n]],
                                                                "evidence": f"saved evidence for {n}"} for n in names]},
               "response": {"id": "resp_1"}, "usage": {"input_tokens": 1234, "output_tokens": 56,
                                                       "reasoning_tokens": 7}, "seconds": 2.5, "created": "x"}
        os.makedirs(os.path.join(src_cache, key[:2]))
        with open(os.path.join(src_cache, key[:2], key + ".json"), "w") as fh:
            json.dump(src, fh)
        base, proxy = self.proxy()
        with proxy.use(self.folder("A")):
            info = judge_seed.seed_try(self.guards["A"]["guard"], st, sc.source(), "A",
                                       branch_cache.current_per_try_llm(), cache_dir_fn=lambda fp: src_cache)
        self.assertTrue(info["written"], info)
        self.assertEqual(info["from"], "source run's judge cache (read only)")
        with open(os.path.join(PC_DIR, info["file"]), encoding="utf-8") as fh:
            seeded = json.load(fh)
        for k in ("parsed", "usage", "seconds", "response", "output_text"):
            self.assertEqual(seeded[k], src[k], k)
        self.assertEqual(seeded["seed"]["source_key"], key)
        self.assertNotEqual(info["key"], key)                    # the try's own key (its judge model)
        # not in the source run's cache: nothing written, and the reason is recorded
        with proxy.use(self.folder("A2")):
            info2 = judge_seed.seed_try(self.guards["A"]["guard"], st, sc.source(), "A",
                                        branch_cache.current_per_try_llm(),
                                        cache_dir_fn=lambda fp: os.path.join(self.tmp, "empty_cache"))
        self.assertFalse(info2["written"])
        self.assertIn("no source answer", info2["why"])
        self.assertEqual(files_in(self.folder("A2")), [])

    def test_a_fork_point_the_guard_does_not_agree_with_fails_before_any_call(self):
        sc = Scenario(reads=1)
        make_real(sc, user_authenticated=False)
        sc.fork.feedback_a = "another block message"
        base, proxy = self.proxy()
        with proxy.use(self.folder("A")):
            with self.assertRaises(judge_seed.SeedMismatch):
                run_all.seed_fork_judge(self.guards["A"]["guard"], sc.state(), sc.source(), "A")
        self.assertEqual(base.log, [])
        self.assertEqual(files_in(self.folder("A")), [])

    def test_dry_run_seed_writes_nothing_and_has_the_try_key(self):
        sc = Scenario(reads=1)
        make_real(sc, user_authenticated=False)
        target = SimpleNamespace(model="fake-judge", max_output_tokens=16000, cache_dir=self.folder("dry"))
        info = run_all.seed_fork_judge(self.guards["A"]["guard"], sc.state(), sc.source(), "A", target=target,
                                       write=False)
        self.assertFalse(info["written"])
        self.assertTrue(info["decision_matches"])
        self.assertFalse(os.path.exists(self.folder("dry")))
        base, proxy = self.proxy()
        with proxy.use(self.folder("A")):
            real = run_all.seed_fork_judge(self.guards["A"]["guard"], sc.state(), sc.source(), "A")
        self.assertEqual(info["key"], real["key"])

    def test_no_seed_for_a_stub_guard_or_a_judge_without_a_try_copy(self):
        sc = Scenario(reads=1)
        info = run_all.seed_fork_judge(StubGuard(lambda m, n: True), sc.state(), sc.source(), "A")
        self.assertFalse(info["written"])
        self.assertIn("not a TGR guard", info["why"])

        class PlainJudge:                                        # not a dataclass: used as it is, no per-try copy
            model, max_output_tokens, cache_dir = "plain", 16000, os.path.join(self.tmp, "plain")

            def call(self, **_):
                raise AssertionError("no call expected")
        proxy = branch_cache.install(PlainJudge())
        make_real(sc, user_authenticated=False)
        with proxy.use(self.folder("plain")):
            info = run_all.seed_fork_judge(self.guards["A"]["guard"], sc.state(), sc.source(), "A")
        self.assertFalse(info["written"])
        self.assertIn("no per-try judge LLM copy", info["why"])


class TestForkGuardRecord(TmpMixin, unittest.TestCase):
    """F2 item 6 (audit A4 W1): the fork attempt's guard record has the branch guard's rules, margin and values."""

    def test_rules_margin_and_values_at_the_fork(self):
        guards = guards_real()
        base = FakeCachedLLM(answer=allow_all)
        proxy = branch_cache.install(base)
        sc = Scenario(reads=1)
        ra, rb_, vals = make_real(sc, user_authenticated=False)      # block removed, frozen TGR source
        i = sc.fork.attempt_index
        out = {}
        for b in ("A", "B"):
            with proxy.use(self.folder(b)):
                out[b], _ = run(sc, b, guards[b]["guard"])
        ga, gb = out["A"]["attempts"][i]["guard"], out["B"]["attempts"][i]["guard"]
        self.assertEqual(ga["violated_rules"], sc.fork_attempt["guard"]["violated_rules"])   # the source record's
        self.assertEqual([v["rule_id"] for v in ga["violated_rules"]], sc.fork.violated_a)
        self.assertEqual(sc.fork.violated_a, ["8"])
        self.assertAlmostEqual(ga["margin"], sc.fork.margin_a)
        self.assertEqual(ga["values_used"], sc.fork.values_a)
        self.assertEqual((gb["violated_rules"], gb["margin"], gb["values_used"]), ([], sc.fork.margin_b,
                                                                                  sc.fork.values_b))
        # block added: B blocks and is not the source guard: the rules come from the fork point, with TGR's text
        sc2 = Scenario(reads=1, login=False)
        ra2, rb2, _ = make_real(sc2, user_authenticated=True)
        with proxy.use(self.folder("B2")):
            rec, _ = run(sc2, "B", guards["B"]["guard"])
        g2 = rec["attempts"][sc2.fork.attempt_index]["guard"]
        self.assertEqual(g2["violated_rules"], json.loads(json.dumps(rb2["violated_rules"])))
        self.assertAlmostEqual(g2["margin"], rb2["margin"])
        self.assertEqual(g2["values_used"], sc2.fork.values_b)
        self.assertFalse(g2["action_allowed"])

    def folder(self, name):
        return os.path.join(self.tmp, name, "structured")


class TestRunAllFixes(RunAllBase, unittest.TestCase):
    """F2 items 1, 8, 9 through run_all.main."""

    def test_try_files_record_the_judge_seed(self):
        sc = Scenario(reads=1, fork_id="fk_seed")
        make_real(sc, user_authenticated=False)
        i = sc.fork.attempt_index
        pts = self.make_files([sc])
        rt = FakeRuntime(guards=guards_real(), agent=FakeAgent(repeat_then_reply(i)))
        rt.judge_base = FakeCachedLLM(answer=allow_all)
        res, log, rt = self.main(pts, "--tries", "1", "--workers", "1", rt=rt)
        self.assertEqual(res["counts"]["ok"], 2)
        for b in ("A", "B"):
            r = jload(rb.try_path(self.out, "fk_seed", b, 0))
            self.assertIsNone(r["error"], r.get("traceback"))
            self.assertTrue(r["judge_seed"]["written"], r["judge_seed"])
            self.assertTrue(r["judge_seed"]["decision_matches"])
        ra = jload(rb.try_path(self.out, "fk_seed", "A", 0))
        self.assertEqual((ra["attempts"][i + 1]["blocked"], ra["attempts"][i + 1]["guard"]["usage"]["cache_hits"]),
                         (True, 1))
        self.assertIn("judge seeds written 2 of 2", log)
        res, log, _ = self.main(pts, "--dry-run", rt=FakeRuntime(guards=guards_real()))
        self.assertEqual(res["dry_run"]["forks_ok"], 1, res["dry_run"]["problems"])
        self.assertEqual(res["dry_run"]["judge_seeds"]["checked"], 2)
        self.assertIn("judge seeds checked 2", log)

    def test_dry_run_lists_a_fork_whose_seed_does_not_match(self):
        sc = Scenario(reads=1, fork_id="fk_bad_seed")
        make_real(sc, user_authenticated=False)
        sc.fork.feedback_b = None
        sc.fork.decision_b = "allow"
        sc.fork.feedback_a = "not TGR's message"
        pts = self.make_files([sc])
        res, log, _ = self.main(pts, "--dry-run", rt=FakeRuntime(guards=guards_real()))
        self.assertEqual(res["dry_run"]["forks_ok"], 0)
        self.assertIn("SeedMismatch", res["dry_run"]["problems"][0])

    def test_source_checks_run_before_the_rebuild(self):
        scs = [Scenario(reads=1, fork_id="fk_ok"), Scenario(reads=1, fork_id="fk_outside")]
        pts = self.make_files(scs)
        with open(pts) as fh:
            rows = [json.loads(x) for x in fh]
        rows[1]["episodes_path"] = os.path.join("..", "outside_predicate_correctness", "episodes.jsonl")
        with open(pts, "w") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in rows))
        seen = []
        good = self.rebuild

        def rebuild(fp):
            seen.append(fp.fork_id)
            return good(fp)
        self.rebuild = rebuild
        res, log, rt = self.main(pts, "--tries", "1", "--workers", "1")
        r = jload(rb.try_path(self.out, "fk_outside", "A", 0))
        self.assertIn("ForkMismatch", r["error"])
        self.assertIn("is not under predicate_correctness", r["error"])
        self.assertNotIn("fk_outside", seen)                     # refused before the rebuild read anything
        self.assertIn("fk_ok", seen)
        seen.clear()
        res, log, rt = self.main(pts, "--dry-run")
        self.assertEqual(res["dry_run"]["forks_ok"], 1)
        self.assertIn("fk_outside", res["dry_run"]["problems"][0])
        self.assertEqual(seen, ["fk_ok"])

    def test_later_left_usd_is_added_to_every_soft_stop_check(self):
        pts = self.make_files([Scenario(reads=1, fork_id=f"fk_{k}") for k in range(2)])
        ss = StandInSoftStop()
        res, log, rt = self.main(pts, "--tries", "1", "--workers", "1", "--profile", "luna-dev",
                                 "--later-left-usd", "12.5", ss=ss)
        self.assertEqual(res["later_left_usd"], 12.5)
        self.assertEqual(res["soft_stop"]["later_left_usd"], 12.5)
        prior = run_all.PRIOR_USD_PER_TRY["luna-dev"]
        self.assertAlmostEqual(ss.checks[0][1], 4 * prior + 12.5)      # the plan's status line
        self.assertAlmostEqual(ss.checks[1][1], 4 * prior + 12.5)      # before the first try
        r0 = jload(rb.try_path(self.out, "fk_0", "A", 0))
        self.assertAlmostEqual(ss.checks[2][1], 3 * r0["cost_usd"] + 12.5)
        for argv in (["x.jsonl", "--later-left-usd", "-1"], ["x.jsonl", "--later-left-usd", "nan"]):
            with self.assertRaises(run_all.RunRefused):
                run_all.parse_args(argv)
        # the $30 rule with it (the real decide): over $100 with $1 left here + $40 later -> stop; + $20 -> finish
        from guard import soft_stop
        g = run_all.SpendGate(soft_stop, 1.0, [], 1, seen_by_scan=False, refresh_s=1e9, later_left=40.0)
        g.spend_fn = lambda: 120.0
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertIsNotNone(g.try_start())
        self.assertIn("+ later jobs $40.00", buf.getvalue())
        g = run_all.SpendGate(soft_stop, 1.0, [], 1, seen_by_scan=False, refresh_s=1e9, later_left=20.0)
        g.spend_fn = lambda: 120.0
        self.assertIsNone(g.try_start())


class TestRunAllWithTheRealSoftStop(RunAllBase, unittest.TestCase):
    """F2 item 10 (audit A5 W7): run_all.main with the REAL guard/soft_stop.py (load_soft_stop, SpendScanner of
    output/eval_v2/ before every try, decide). The fake try files and this run's big fake costs stay in this test's
    temp folder under output/ (not under output/eval_v2/: the real scan never sees them; the gate adds this run's own
    spend). 50 finished fake tries of $0.01 are already there; 2 tries are left, each costs $120 (fake agent)."""

    def prepare(self):
        pts = self.make_files([Scenario(reads=1, fork_id="fk_ss")])
        self.out = os.path.join(self.tmp, "stage_b")
        for t in range(1, 26):
            for b in ("A", "B"):
                p = rb.try_path(self.out, "fk_ss", b, t)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w") as fh:
                    json.dump({"fork_id": "fk_ss", "branch": b, "try": t, "error": None, "cost_usd": 0.01}, fh)
        return pts

    def main_real(self, pts, *extra):
        self.cache = os.path.join(self.tmp, "cache")
        rt = FakeRuntime(agent=FakeAgent(always_reply, cost=120.0))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = run_all.main([pts, "--out-root", self.out, "--cache-root", self.cache, "--tries", "26",
                                "--workers", "1", *extra], runtime=rt, rebuild_fn=self.rebuild, soft_stop=None,
                               safety=False)
        return res, buf.getvalue()

    def test_real_soft_stop_finishes_with_little_left(self):
        from guard import soft_stop
        pts = self.prepare()
        self.assertFalse(run_all.spend_seen_by_soft_stop(self.out))
        res, log = self.main_real(pts)
        self.assertEqual((res["already_done"], res["to_run"]), (50, 2))
        self.assertEqual(res["counts"]["ran"], 2)                # over $100 after the 1st, but about $2.4 left
        self.assertNotIn("STOPPED (soft stop)", log)
        self.assertGreaterEqual(res["counts"]["cost"], 240.0)
        self.assertEqual(res["soft_stop"]["reason"].split(" ")[0], "spent")
        self.assertIs(run_all.load_soft_stop(), soft_stop)

    def test_real_soft_stop_stops_with_the_later_jobs(self):
        from guard import soft_stop
        pts = self.prepare()
        base = soft_stop.spent_usd()                             # the real spend now (read only)
        res, log = self.main_real(pts, "--later-left-usd", "40")
        want = 0 if base >= soft_stop.SOFT_STOP_USD else 1       # $40 + about $2.4 left > $30 once over $100
        self.assertEqual(res["counts"]["ran"], want)
        self.assertEqual(res["counts"]["not_started"], 2 - want)
        self.assertEqual(log.count("STOPPED (soft stop)"), 1)
        self.assertIn("later jobs $40.00", log)


_REAL_LLM_PROBE = r"""
import json, os, sys
from types import SimpleNamespace
sys.dont_write_bytecode = True
pc, tmp = sys.argv[1], sys.argv[2]
NET = []
def _no_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.create_connection"):
        NET.append(event)
        raise RuntimeError("network blocked in this test")
sys.addaudithook(_no_network)
sys.path.insert(0, pc)
from tests import test_eval_v2_fork as T
from fork import branch_cache, run_all
from guard.offline import FakeJudge
import policy_pipeline.llm as v1
CALLS = []
class FakeResponses:
    def create(self, **kw):
        user = kw["input"][1]["content"]
        vals = T.allow_all(FakeJudge.predicates_in(user))
        word = {True: "true", False: "false", None: "unknown"}
        parsed = {"predicates": [{"name": n, "value": word[v], "evidence": "fake client"} for n, v in vals.items()]}
        CALLS.append(kw["model"])
        return SimpleNamespace(output_text=json.dumps(parsed), model_dump=lambda mode=None: {"fake": True},
                               usage=SimpleNamespace(input_tokens=100, output_tokens=10,
                                                     output_tokens_details=SimpleNamespace(reasoning_tokens=0)))
v1._client, v1._deployment = SimpleNamespace(responses=FakeResponses()), "fake-deployment"
base = v1.LLM(cache_dir=os.path.join(tmp, "base"), model="gpt-6-luna", max_output_tokens=16000)
proxy = branch_cache.install(base)
guards = T.guards_real()
sc = T.Scenario(reads=1)
T.make_real(sc, False)
i = sc.fork.attempt_index
out = {}
for mode in ("seed", "noseed"):
    folder = os.path.join(tmp, mode, "structured")
    state, source = sc.state(), sc.source()
    n0 = len(CALLS)
    with proxy.use(folder):
        info = run_all.seed_fork_judge(guards["A"]["guard"], state, source, "A") if mode == "seed" else {}
        T.fake_reset_usage()
        env = T.make_fake_env(state)
        rec = run_all.rb.run_branch(state, "A", 0, env=env, guard=guards["A"]["guard"],
                                    agent_completion=T.FakeAgent(T.repeat_then_reply(i)),
                                    tools_info=T.tau_copy.tools_info(T.DOMAIN), source=source,
                                    message_to_action=T.fake_message_to_action, usage_fn=T.fake_usage)
    rep = rec["attempts"][i + 1]
    out[mode] = {"error": rec["error"], "seed_written": info.get("written"), "repeat_blocked": rep["blocked"],
                 "repeat_cache_hits": rep["guard"]["usage"]["cache_hits"], "client_calls": len(CALLS) - n0,
                 "files": sum(len(f) for _, _, f in os.walk(folder))}
out["network"] = len(NET)
print(json.dumps(out))
"""


class TestSeedWithTheRealLLMClass(TmpMixin, unittest.TestCase):
    """F2 item 1 with the copied policy_pipeline.llm.LLM itself behind the per-try proxy (its own cache key and file
    layout), a fake HTTP client, in a fresh process with the network blocked: the seeded repeat is a cache hit (no
    client call); without the seed it is a client call."""

    def test_seed_key_matches_the_real_llm_call(self):
        r = subprocess.run([sys.executable, "-B", "-c", _REAL_LLM_PROBE, PC_DIR, self.tmp], capture_output=True,
                           text=True, cwd=PC_DIR, timeout=600, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        rep = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(rep["network"], 0)
        s, n = rep["seed"], rep["noseed"]
        self.assertEqual((s["error"], s["seed_written"], s["repeat_blocked"], s["repeat_cache_hits"]),
                         (None, True, True, 1))
        self.assertEqual(s["client_calls"], 1)                   # only the reply after the repeat
        self.assertEqual(s["files"], 2)                          # the seed + that reply
        self.assertEqual((n["error"], n["repeat_blocked"], n["repeat_cache_hits"]), (None, False, 0))
        self.assertGreaterEqual(n["client_calls"], 1)


if __name__ == "__main__":
    unittest.main()
