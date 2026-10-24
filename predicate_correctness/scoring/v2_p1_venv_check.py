"""Eval v2, Part 1: checks inside the τ-bench venv, with NO LLM call (docs/planning/tracker_eval_v2/p1.md).

Network is blocked in this process (audit hook on socket.connect / getaddrinfo), and τ-bench's user simulator
`completion` is replaced by a fake that records its inputs. Writes are allowed only under output/ (our write guard).

  A. How the runner's env loads tasks: get_env(..., task_split=...) -> which list; index -> task. The extra retail
     tasks: τ-bench's own TASKS_TRAIN must equal our ast parse (scoring/v2_task_files.py). airline has no "train".
  B. The user simulator (LLMUserSimulationEnv, the venv's tau_bench/envs/user.py): calls made when the env is built
     and on reset; the exact shape of env.user.messages; what env.step(respond) sends to it.
  C. Rebuild at any point, on every saved conversation (partner runs and our p10 runs): a fresh env for the task, the
     executed tool calls replayed through env.tools_map (as Env.step does), env.actions rebuilt; every replayed
     output must equal the saved one; for finished conversations env.calculate_reward() must give the saved reward
     and the saved reward_info. Also one user-simulator rebuild: env.step(respond) must send the rebuilt messages.

Output: output/eval_v2/checks/part1_venv_check.json.
Run from predicate_correctness/ (venv Python):
    LITELLM_LOCAL_MODEL_COST_MAP=True PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v2_p1_venv_check \
        > output/logs/v2_p1_venv_check.log 2>&1
"""
from __future__ import annotations

import collections
import json
import os
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
PC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC not in sys.path:
    sys.path.insert(0, PC)

NET = []


def _no_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname"):
        NET.append(event)
        raise RuntimeError(f"network blocked in this check ({event})")


sys.addaudithook(_no_network)

from guard import write_guard  # noqa: E402  (stdlib)

OUT = os.path.join(PC, "output")
write_guard.install([OUT])

from guard import runner_path  # noqa: E402

runner_path.setup()
from exp_core.models import _Message  # noqa: E402  (the runner's message class: same model_dump as real calls)
from scoring.v2_task_files import task_files  # noqa: E402

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
import tau_bench  # noqa: E402
import tau_bench.envs.user as user_mod  # noqa: E402
from tau_bench.agents.tool_calling_agent import message_to_action  # noqa: E402
from tau_bench.envs import get_env  # noqa: E402
from tau_bench.types import RESPOND_ACTION_NAME, Action  # noqa: E402

OUT_JSON = os.path.join(OUT, "eval_v2", "checks", "part1_venv_check.json")
RUNS = os.path.join(PC, "from_shieldagent", "runs")
SOURCES = [("luna_train_v5", os.path.join(RUNS, "luna_train_v5", "{d}", "tgr")),
           ("nano_train", os.path.join(RUNS, "nano_train", "{d}", "tgr")),
           ("luna_val", os.path.join(RUNS, "luna_val", "{d}", "tgr")),
           ("p10_luna_train", os.path.join(OUT, "online", "p10_luna_train", "{d}", "tgr_tracker")),
           ("p10_nano_train", os.path.join(OUT, "online", "p10_nano_train", "{d}", "tgr_tracker")),
           ("p10_luna_val", os.path.join(OUT, "online", "p10_luna_val", "{d}", "tgr_tracker"))]


class FakeUser:
    """Stands in for exp_core.models.make_completion("user"): records every call, returns a fixed text."""

    def __init__(self):
        self.calls = []
        self.reply = "fake user reply"

    def __call__(self, model=None, custom_llm_provider=None, messages=None, **_):
        self.calls.append(json.loads(json.dumps(messages)))
        return SimpleNamespace(choices=[SimpleNamespace(message=_Message(self.reply, None))],
                               _hidden_params={"response_cost": 0.0})


FAKE = FakeUser()
user_mod.completion = FAKE


def jnorm(x):
    return json.loads(json.dumps(x, default=str))


# ================================================================================================ A. task loading
def check_task_loading() -> dict:
    out = {"tau_bench": tau_bench.__file__}
    parsed = task_files()
    for split, key in (("test", "retail/test"), ("train", "retail/train"), ("dev", "retail/dev")):
        env = get_env("retail", user_strategy="human", user_model="none", task_split=split, task_index=0)
        mine = parsed[key]["tasks"]
        theirs = [t.model_dump() for t in env.tasks]
        same = len(mine) == len(theirs) and all(
            {k: a[k] for k in ("user_id", "instruction", "actions", "outputs")} ==
            {k: b[k] for k in ("user_id", "instruction", "actions", "outputs")} for a, b in zip(mine, theirs))
        out[f"retail/{split}"] = {"count": len(env.tasks), "ast_parse_equal": same,
                                  "module": type(env).__module__}
    for split in ("test", "train"):
        try:
            env = get_env("airline", user_strategy="human", user_model="none", task_split=split, task_index=0)
            out[f"airline/{split}"] = {"count": len(env.tasks)}
        except Exception as e:  # noqa: BLE001
            out[f"airline/{split}"] = {"error": f"{type(e).__name__}: {e}"}
    # index -> task: env.task == env.tasks[i], also after reset-like assignment
    env = get_env("retail", user_strategy="human", user_model="none", task_split="train", task_index=499)
    out["train_index_499_user"] = env.task.user_id
    out["train_index_499_equals_list"] = env.task == env.tasks[499]
    try:
        get_env("retail", user_strategy="human", user_model="none", task_split="train", task_index=500)
        out["train_index_500"] = "no error"
    except Exception as e:  # noqa: BLE001
        out["train_index_500"] = f"{type(e).__name__}: {e}"
    return out


# ================================================================================================ B. user simulator
def check_user_sim() -> dict:
    out = {}
    n0 = len(FAKE.calls)
    env = get_env("retail", user_strategy="llm", user_model="fake", user_provider="azure", task_split="train",
                  task_index=7)
    out["user_calls_when_env_is_built"] = len(FAKE.calls) - n0
    out["build_call_messages"] = FAKE.calls[-1] if len(FAKE.calls) > n0 else None
    n1 = len(FAKE.calls)
    env_h = get_env("retail", user_strategy="human", user_model="none", task_split="train", task_index=7)
    out["user_calls_when_env_is_built_human"] = len(FAKE.calls) - n1
    out["same_tools_and_wiki_human_vs_llm"] = env_h.tools_info == env.tools_info and env_h.wiki == env.wiki
    n2 = len(FAKE.calls)
    reset = env.reset(task_index=7)
    out["user_calls_on_reset"] = len(FAKE.calls) - n2
    out["reset_observation"] = reset.observation
    msgs = jnorm(env.user.messages)
    out["user_messages_after_reset"] = [{"role": m["role"], "keys": sorted(m), "content_head": (m.get("content") or "")[:160]}
                                        for m in msgs]
    want_sys = env.user.build_system_prompt(instruction=env.task.instruction)
    out["system_prompt_is_build_system_prompt(instruction)"] = msgs[0]["content"] == want_sys
    out["greeting"] = msgs[1]
    n3 = len(FAKE.calls)
    r = env.step(Action(name=RESPOND_ACTION_NAME, kwargs={"content": "Hello, I can help. What is your name?"}))
    out["user_calls_on_respond"] = len(FAKE.calls) - n3
    out["respond_step"] = {"observation": r.observation, "done": r.done, "source": r.info.source}
    out["user_messages_after_respond"] = [{"role": m["role"], "content_head": (m.get("content") or "")[:80]}
                                          for m in jnorm(env.user.messages)]
    out["last_call_input_equals_user_messages_before_reply"] = FAKE.calls[-1] == jnorm(env.user.messages)[:-1]
    FAKE.reply = "###STOP###"
    r = env.step(Action(name=RESPOND_ACTION_NAME, kwargs={"content": "Anything else?"}))
    FAKE.reply = "fake user reply"
    out["stop_step"] = {"observation": r.observation, "done": r.done, "reward": r.reward,
                        "reward_info_keys": sorted((r.info.reward_info.model_dump() if r.info.reward_info else {}))}
    out["user_total_cost_is_last_call_only"] = "LLMUserSimulationEnv.generate_next_message sets total_cost = cost of the last call"
    return out


# ================================================================================================ C. rebuild + score
def load_episodes(path):
    keep = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("error") is None:
                keep[(r["task_index"], r["trial"])] = r
    return [keep[k] for k in sorted(keep)]


def run_call(env, action):
    """One tool call exactly as Env.step runs it (without the user simulator)."""
    if action.name in env.tools_map:
        try:
            return env.tools_map[action.name].invoke(data=env.data, **action.kwargs)
        except Exception as e:  # noqa: BLE001 - as Env.step
            return f"Error: {e}"
    return f"Unknown action {action.name}"


def rebuild_env(env, task_index, executed):
    """The env as it was after `executed`: fresh data for the task, tool calls replayed, env.actions rebuilt.
    Returns the list of (index, replayed output, saved output) for the tool calls."""
    env.task_index = task_index
    env.task = env.tasks[task_index]
    env.data = env.data_load_func()
    env.actions = []
    outs = []
    for i in range(2, len(executed) - 1, 2):
        m, r = executed[i], executed[i + 1]
        action = message_to_action(m)          # from the message's arguments string (not attempts[].kwargs)
        env.actions.append(action)
        if action.name != RESPOND_ACTION_NAME:
            outs.append((i, run_call(env, action), r.get("content")))
    return outs


def user_messages(env, executed):
    """The user simulator's messages after `executed` (rebuilt; τ-bench does not save them)."""
    msgs = [{"role": "system", "content": env.user.build_system_prompt(instruction=env.task.instruction)},
            {"role": "user", "content": "Hi! How can I help you today?"},
            {"role": "assistant", "content": executed[1]["content"], "tool_calls": None}]
    for i in range(2, len(executed) - 1, 2):
        m, r = executed[i], executed[i + 1]
        if r.get("role") == "user":
            msgs.append({"role": "user", "content": m.get("content")})
            msgs.append({"role": "assistant", "content": r.get("content"), "tool_calls": None})
    return msgs


def check_rebuild() -> dict:
    out = {}
    demo = None
    for tag, pattern in SOURCES:
        for d in ("airline", "retail"):
            t0 = time.time()
            eps = load_episodes(os.path.join(pattern.format(d=d), "episodes.jsonl"))
            env = get_env(d, user_strategy="llm", user_model="fake", user_provider="azure", task_split="test",
                          task_index=0)
            c = collections.Counter()
            bad = []
            for ep in eps:
                exe = ep["executed"]
                outs = rebuild_env(env, ep["task_index"], exe)
                c["tool calls"] += len(outs)
                mism = [i for i, got, want in outs if got != want]
                c["tool calls with a different output"] += len(mism)
                if mism:
                    bad.append((ep["task_index"], ep["trial"], "outputs differ at", mism[:3]))
                if ep["done"]:
                    c["finished"] += 1
                    rr = env.calculate_reward()
                    same_r = rr.reward == ep["reward"]
                    same_info = jnorm(rr.model_dump()) == ep["reward_info"]
                    c["reward equal"] += same_r
                    c["reward_info equal"] += same_info
                    if not (same_r and same_info):
                        bad.append((ep["task_index"], ep["trial"], "reward", rr.reward, ep["reward"]))
                else:
                    c["not finished (max steps)"] += 1
                    c["not finished, saved reward 0"] += ep["reward"] == 0
                if demo is None and tag == "p10_luna_train" and d == "retail":
                    demo = demo_user_rebuild(env, ep)
            out[f"{tag}/{d}"] = {"conversations": len(eps), **dict(c), "problems_first": bad[:10],
                                 "seconds": round(time.time() - t0, 1)}
            print(f"[rebuild] {tag}/{d}: {json.dumps(out[f'{tag}/{d}'])}", flush=True)
    out["user_sim_rebuild_demo"] = demo
    return out


def demo_user_rebuild(env, ep) -> dict:
    """At the 3rd executed reply of a saved conversation: rebuild the user simulator, send the saved agent text,
    and check what the fake receives = rebuilt messages + that text."""
    exe = ep["executed"]
    replies = [i for i in range(2, len(exe) - 1, 2) if exe[i + 1].get("role") == "user"]
    if len(replies) < 3:
        return None
    k = replies[2]
    prefix = exe[:k]
    rebuild_env(env, ep["task_index"], prefix)
    env.user.messages = user_messages(env, prefix)
    n = len(FAKE.calls)
    action = message_to_action(exe[k])
    r = env.step(action)
    sent = FAKE.calls[-1] if len(FAKE.calls) > n else None
    want = jnorm(user_messages(env, prefix)) + [{"role": "user", "content": exe[k]["content"]}]
    return {"task": ep["task_index"], "trial": ep["trial"], "fork_at_executed_index": k,
            "fake_calls": len(FAKE.calls) - n, "sent_equals_rebuilt_plus_agent_text": sent == want,
            "observation": r.observation, "n_user_sim_messages_sent": len(sent or []),
            "saved_reply_was": (exe[k + 1].get("content") or "")[:100]}


def main() -> int:
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    res = {"task_loading": check_task_loading()}
    print("[A]", json.dumps(res["task_loading"]), flush=True)
    res["user_sim"] = check_user_sim()
    print("[B]", json.dumps({k: v for k, v in res["user_sim"].items() if k != "build_call_messages"})[:3000], flush=True)
    res["rebuild"] = check_rebuild()
    res["network_attempts_blocked"] = len(NET)
    res["fake_user_calls"] = len(FAKE.calls)
    res["refused_writes"] = len(write_guard.REFUSED)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False, default=str)
    print("wrote", OUT_JSON, "| network attempts", len(NET), "| refused writes", len(write_guard.REFUSED), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
