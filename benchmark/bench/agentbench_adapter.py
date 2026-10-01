"""M54: AgentBench `os-std` adapter — corpus loading, task-config normalization (mirrors
upstream `task.py`'s `_load_configs`/`_evaluate_answer` semantics exactly), one-container-per-task
lifecycle over `docker`, and the dual-submit shim that lets agent_loop.run_agent (which only
recognizes ONE literal `submit_tool` name) terminate on either upstream tool.

Upstream: THUDM/AgentBench (Apache-2.0), pinned commit d1e4a10db08c87075c78972e48ecc182be03e2d5,
`os-std` split (`configs/tasks/os.yaml`, `src/server/tasks/os_interaction/task.py`). Corpus
vendored at `benchmark/corpora/agentbench_os_v1.jsonl` (+ manifest + scripts + LICENSE).

DUAL-SUBMIT DESIGN NOTE. Upstream's os-std protocol has TWO tools that end an episode
(`answer_action`, `finish_action`); `agent_loop.run_agent` only matches a single literal
`submit_tool` name. Rather than editing the shared, heavily-tested `agent_loop.py`, this module
wraps the Driver: `DualSubmitDriver.complete()` renames any `finish_action` tool call to the
canonical `answer_action` (folding its `thought` into an `answer` key) BEFORE returning to
run_agent, so termination is a single-name match from run_agent's point of view, while the TWO
upstream tool schemas still reach the model verbatim (schemas come from the `tools` list, which
this module never touches). `submitted_via` on the wrapper records which the model actually used.

CONTAINER LIFECYCLE. One task = one container: create -> init scripts -> start (background) ->
agent loop (bash_action -> `docker exec`) -> evaluate (match, or the check-script chain against
the SAME container) -> `docker rm -f`, always in a `finally` (success, failure, timeout,
KeyboardInterrupt all remove the container — AC9).

D2 EXCLUSION (pre-registered, C107). Before any model call: for every CHECK task (never for
`match` tasks), run `evaluation.example.code` to completion in two independent FRESH containers
and compare stdout. No gold (either run errors/times out) or disagreeing golds -> excluded with a
reason. This is a diagnostic/inclusion decision only — the cached gold is NOT substituted into
per-item grading; grading always re-runs the check chain (including any `example`-script
positions) live in the task's own post-agent container, exactly as task.py does.
"""
from __future__ import annotations

import json
import random
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

from . import agent_loop
from . import agent_outcomes as AO
from . import convergence

# --------------------------------------------------------------------------- upstream-verbatim
# configs/tasks/os.yaml `default.parameters.tools` (verbatim) and `round_limit: 8`.
ROUND_LIMIT = 8

BASH_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "script": {"type": "string", "description": "The bash script to be executed."},
    },
    "required": ["script"],
    "additionalProperties": False,
}
FINISH_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string",
                    "description": "The thought or reason indicating the task is finished."},
    },
    "required": ["thought"],
    "additionalProperties": False,
}
ANSWER_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "description": "The answer to the question."},
    },
    "required": ["answer"],
    "additionalProperties": False,
}

# src/server/tasks/os_interaction/task.py `_inject_initial_messages` system_message, VERBATIM.
SYSTEM_PROMPT = """You are an assistant that will act like a person. I will play the role of a Linux (Ubuntu) operating system.
Your goal is to implement the operations required by me or answer the questions proposed by me.
For each of your turns, you should first think about what you should do, and then call exactly one of the provided tools according to the situation.
If you think the output is too long, I will truncate it. The truncated output is not complete. You have to deal with the truncating problem by yourself.
Attention, your bash code should not contain any input operation. Once again, you should use one tool in each turn, and should not respond without function calling.
Note that if you think the task has been finished, or there is some message missing to completely complete the task, you should respond with calling the function "finish_action", as no additional information will be provided.
Also, note that if you have gotten the answer to the question, you should call the "answer_action" tool instead of simply writing your answer in your response.
Your answers should be exact and precise (for example, a single number), do not answer with full sentences or phrases.
Always use a tool provided instead of simply responding with content."""

# `_inject_initial_messages` user turn template.
TASK_TEMPLATE = "Now, I will start a new problem in a new OS. My problem is:\n\n{description}"

TRUNCATE_CHARS = 8000
DEFAULT_EXEC_TIMEOUT_S = 60.0


# --------------------------------------------------------------------------- corpus
def load_corpus(path, limit=None) -> list:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[:limit] if limit else rows


def load_exclusions(path) -> list:
    if not Path(path).exists():
        return []
    return json.loads(Path(path).read_text(encoding="utf-8"))


def apply_exclusions(tasks: list, exclusions: list) -> list:
    excluded_ids = {e["id"] for e in exclusions}
    return [t for t in tasks if t["id"] not in excluded_ids]


def pilot_draw(task_ids: list, seed: int, n: int = 5) -> list:
    """Seeded random subset of `task_ids`, size <= n. NEVER the first n (AGENTS.md: the corpus is
    ordered easy-first) -- shuffle the whole pool, then take a prefix of the SHUFFLED order."""
    pool = list(task_ids)
    random.Random(seed).shuffle(pool)
    return pool[:n]


# --------------------------------------------------------------------------- task config
def _load_script_obj(obj, scripts_root, group):
    """Mirrors task.py `load_script`: None -> None; a bare string -> ("bash", string); a dict
    with "file" -> read from `<scripts_root>/<group>/<file>`; a dict with "code" -> inline."""
    if obj is None:
        return None
    if isinstance(obj, str):
        return ("bash", obj)
    if not isinstance(obj, dict):
        return None
    lang = obj.get("language", "bash")
    if "file" in obj:
        p = Path(scripts_root) / str(group) / obj["file"]
        return (lang, p.read_text(encoding="utf-8"))
    if "code" in obj:
        return (lang, obj["code"])
    raise ValueError(f"invalid script object: {obj!r}")


def task_config(task: dict, scripts_root) -> dict:
    """Normalize one vendored task row into {image, init_scripts, start, match, check, example}.

    Mirrors task.py `_load_configs` field-by-field, INCLUDING its quirk: `create` is only ever
    treated as a dict (`"local" in item["create"]`, `"init" in item["create"]`); one upstream task
    (data/os_interaction/data/5/new.json #7) carries a malformed LIST `create` field, which makes
    both membership tests False on real upstream code -> image="default", no init script. The
    `isinstance(create, dict)` guard below reproduces that exact (accidental) upstream behaviour.
    """
    group = task["group"]
    create = task.get("create")
    if isinstance(create, dict):
        image = create.get("local", "default")
        init_raw = create.get("init")
    else:
        image = "default"
        init_raw = None
    if init_raw is None:
        init_scripts = []
    elif isinstance(init_raw, list):
        init_scripts = [_load_script_obj(s, scripts_root, group) for s in init_raw]
    else:
        init_scripts = [_load_script_obj(init_raw, scripts_root, group)]
    start = _load_script_obj(task.get("start"), scripts_root, group) if "start" in task else None

    ev = task.get("evaluation") or {}
    match = check = example = None
    if "match" in ev:
        m = ev["match"]
        match = {"answer": m, "strip": True} if isinstance(m, str) else m
    elif "check" in ev:
        raw_check = ev["check"]
        if not isinstance(raw_check, list):
            raw_check = [raw_check]
        check = [_load_script_obj(s, scripts_root, group) for s in raw_check]
        if "example" in ev:
            example = _load_script_obj(ev["example"], scripts_root, group)
    return {"image": image, "init_scripts": init_scripts, "start": start,
            "match": match, "check": check, "example": example}


# --------------------------------------------------------------------------- docker primitives
def docker_available(runner=subprocess.run) -> bool:
    try:
        proc = runner(["docker", "info"], capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001 -- docker absent/not running/unresponsive -> degrade
        return False
    return getattr(proc, "returncode", 1) == 0


def images_available(images=("default", "packages", "ubuntu"), runner=subprocess.run) -> dict:
    out = {}
    for name in images:
        try:
            proc = runner(["docker", "image", "inspect", f"local-os/{name}"],
                          capture_output=True, text=True, timeout=10)
            out[name] = getattr(proc, "returncode", 1) == 0
        except Exception:  # noqa: BLE001
            out[name] = False
    return out


def container_name(prefix: str, task_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "-", task_id)
    return f"{prefix}-{safe}"


def sweep_stale_containers(prefix: str, runner=subprocess.run) -> list:
    """Remove any container whose name starts with `prefix` (a crash/interrupt from a prior run
    left it behind). Returns the names removed. Best-effort: never raises."""
    try:
        proc = runner(["docker", "ps", "-a", "--filter", f"name=^{prefix}-", "--format", "{{.Names}}"],
                      capture_output=True, text=True, timeout=30)
    except Exception:  # noqa: BLE001
        return []
    names = [n for n in (proc.stdout or "").splitlines() if n.strip()]
    for n in names:
        remove_container(n, runner)
    return names


def create_container(image: str, name: str, runner=subprocess.run, timeout: float = 60.0) -> None:
    proc = runner(["docker", "run", "-d", "--rm=false", "--name", name, image, "sleep", "infinity"],
                  capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"docker run {image} (name={name}) failed: {(proc.stderr or '')[:300]}")


def remove_container(name: str, runner=subprocess.run) -> None:
    try:
        runner(["docker", "rm", "-f", name], capture_output=True, text=True, timeout=30)
    except Exception:  # noqa: BLE001 -- cleanup must never raise over the real error/result
        pass


def docker_exec(container: str, lang_code, timeout: float, runner=subprocess.run,
                extra_params=()) -> dict:
    """Run one (language, code) script inside `container`. Returns
    {exit_code, stdout, stderr, timed_out}. `extra_params` are appended argv (the answer / prior
    check-script stdout chain), mirroring task.py `execute_independent`."""
    lang, code = lang_code
    params = [str(p) for p in extra_params]
    if lang == "bash":
        cmd = ["docker", "exec", container, "bash", "-c", code]
        if params:
            cmd += ["--", *params]
    elif lang == "python":
        cmd = ["docker", "exec", container, "python3", "-c", code, *params]
    else:
        raise ValueError(f"unsupported script language {lang!r}")
    try:
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "stdout": "", "stderr": "", "timed_out": True}
    return {"exit_code": proc.returncode, "stdout": proc.stdout or "", "stderr": proc.stderr or "",
            "timed_out": False}


def truncate_output(text: str, limit: int = TRUNCATE_CHARS):
    if len(text) <= limit:
        return text, False
    return text[:limit], True


# --------------------------------------------------------------------------- evaluation
def evaluate_match(answer, match_cfg: dict) -> bool:
    a = answer
    if isinstance(a, str) and match_cfg.get("strip"):
        a = a.strip()
    if "answer" in match_cfg:
        return a == match_cfg["answer"]
    if "regex" in match_cfg:
        return bool(re.search(match_cfg["regex"], a or ""))
    return False


def run_check_chain(container: str, check_list: list, example, answer, runner=subprocess.run,
                    timeout: float = DEFAULT_EXEC_TIMEOUT_S) -> bool:
    """Mirrors task.py `_evaluate_by_check_scripts`: params starts as [str(answer)]; each script
    runs with the accumulated params and its stdout is appended for the next; a None entry runs
    `example` instead (the "gold" position); any timeout/nonzero exit fails the whole chain; an
    ungradable None-with-no-example also fails (same effective outcome as task.py's uncaught
    TypeError, but never raises here)."""
    params = [str(answer) if answer is not None else ""]
    for entry in check_list:
        script = entry if entry is not None else example
        if script is None:
            return False
        res = docker_exec(container, script, timeout, runner, extra_params=params)
        if res["timed_out"] or res["exit_code"] != 0:
            return False
        params.append(res["stdout"])
    return True


def compute_gold(image: str, init_scripts: list, start, example, container: str,
                 runner=subprocess.run, timeout: float = DEFAULT_EXEC_TIMEOUT_S):
    """D2: a FRESH container, init + start, then `example` once. Returns its stdout, or None on
    any setup/example failure (no gold)."""
    remove_container(container, runner)
    try:
        try:
            create_container(f"local-os/{image}", container, runner)
        except Exception:  # noqa: BLE001
            return None
        for s in init_scripts:
            res = docker_exec(container, s, timeout, runner)
            if res["timed_out"] or res["exit_code"] != 0:
                return None
        if start:
            res = docker_exec(container, start, timeout, runner)
            if res["timed_out"] or res["exit_code"] != 0:
                return None
        if example is None:
            return None
        res = docker_exec(container, example, timeout, runner, extra_params=[""])
        if res["timed_out"] or res["exit_code"] != 0:
            return None
        return res["stdout"]
    finally:
        remove_container(container, runner)


def prepare_exclusions(tasks: list, scripts_root, runner=subprocess.run,
                       timeout: float = DEFAULT_EXEC_TIMEOUT_S,
                       prefix: str = "agentbench-os-prep") -> tuple:
    """D2 (AC2), no model calls. Returns (golds: {id: str}, exclusions: [{id, reason, ...}]).
    `match` tasks are never excluded (never even examined) by this step."""
    golds, exclusions = {}, []
    for task in tasks:
        cfg = task_config(task, scripts_root)
        if cfg["match"] is not None:
            continue
        name = container_name(prefix, task["id"])
        g1 = compute_gold(cfg["image"], cfg["init_scripts"], cfg["start"], cfg["example"], name,
                          runner, timeout)
        g2 = compute_gold(cfg["image"], cfg["init_scripts"], cfg["start"], cfg["example"], name,
                          runner, timeout)
        if g1 is None or g2 is None:
            exclusions.append({"id": task["id"], "reason": "no_gold"})
            continue
        if g1 != g2:
            exclusions.append({"id": task["id"], "reason": "gold_mismatch", "gold_1": g1, "gold_2": g2})
            continue
        golds[task["id"]] = g1
    return golds, exclusions


# --------------------------------------------------------------------------- dual-submit driver
def _parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


class DualSubmitDriver:
    """Wraps a Driver so BOTH `answer_action` and `finish_action` end an `agent_loop.run_agent`
    episode (see module docstring). Also records per-turn telemetry (`per_turn`) since
    `run_agent`'s return value only carries AGGREGATE counters, and AC5 wants it per turn."""

    SUBMIT_TOOL = "answer_action"

    def __init__(self, inner, timeout: float = 3600.0):
        self.inner = inner
        self.timeout = timeout
        self.submitted_via = None
        self.per_turn = []

    def preload(self, model, timeout: float = 900) -> float:
        return self.inner.preload(model, timeout=timeout)

    def complete(self, model, messages, params, timeout=None, tools=None) -> dict:
        out = self.inner.complete(model, messages, params,
                                  timeout=timeout if timeout is not None else self.timeout,
                                  tools=tools)
        self.per_turn.append({"completion_tokens": out.get("completion_tokens"),
                              "prompt_tokens": out.get("prompt_tokens"),
                              "finish_reason": out.get("finish_reason")})
        new_tcs = []
        for tc in (out.get("tool_calls") or []):
            fn = dict(tc.get("function") or {})
            name = fn.get("name")
            if name == "finish_action":
                args = _parse_args(fn.get("arguments"))
                fn["name"] = self.SUBMIT_TOOL
                fn["arguments"] = json.dumps({"answer": args.get("thought")})
                self.submitted_via = "finish"
            elif name == self.SUBMIT_TOOL:
                self.submitted_via = "answer"
            new_tc = dict(tc)
            new_tc["function"] = fn
            new_tcs.append(new_tc)
        out = dict(out)
        out["tool_calls"] = new_tcs
        return out


def build_tools(container: str, runner=subprocess.run, timeout: float = DEFAULT_EXEC_TIMEOUT_S,
                counters: dict | None = None) -> list:
    """The three upstream tools. `bash_action` actually executes (via `docker exec`); the other
    two are no-ops in dispatch terms -- DualSubmitDriver renames every terminating call to the
    literal submit_tool name before `run_agent` ever sees it, so these `fn`s are never invoked in
    practice. They are still registered so their schemas reach the model verbatim and so
    agent_outcomes' arg-schema counters have something to check against."""
    counters = counters if counters is not None else {}
    counters.setdefault("tool_timeouts", 0)

    def _bash(args: dict) -> str:
        script = args.get("script", "")
        res = docker_exec(container, ("bash", script), timeout, runner)
        if res["timed_out"]:
            counters["tool_timeouts"] += 1
            return f"ERROR: command timed out after {timeout:.0f}s"
        text = res["stdout"] + (("\n" + res["stderr"]) if res["stderr"] else "")
        text = text if text else "(empty output)"
        clipped, truncated = truncate_output(text)
        if truncated:
            clipped += "\n[truncated because the output is too long]"
        return clipped

    return [
        agent_loop.Tool("bash_action",
                        "Execute bash code to perform an operation in the Linux environment.",
                        BASH_TOOL_SCHEMA, _bash),
        agent_loop.Tool("finish_action",
                        "Indicate that the task has been finished or need some additional "
                        "information to be finished.",
                        FINISH_TOOL_SCHEMA, lambda a: "submitted"),
        agent_loop.Tool("answer_action", "Provide the answer to the question.",
                        ANSWER_TOOL_SCHEMA, lambda a: "submitted"),
    ]


# --------------------------------------------------------------------------- outcome / convergence
def finalize_outcome(result: dict, evaluate_submission: Callable[[object], bool]):
    """(outcome, passed, answer) from a `run_agent` result. Only `SOLVED` episodes are graded;
    every other outcome (NO_SUBMIT/TURN_CAP/DEADLINE/TOOL_ERROR_LOOP/SERVER_ERROR) is a scored
    FAIL, never dropped (AC3)."""
    submitted = result.get("submitted")
    answer = (submitted or {}).get("answer") if submitted else None
    outcome = result["outcome"]
    if outcome == AO.SOLVED:
        passed = bool(evaluate_submission(answer))
        return (AO.SOLVED if passed else AO.FAILED_TESTS), passed, answer
    return outcome, False, answer


def episode_converged(per_turn: list, thinking_budget, context_limit, max_tokens):
    """Convergence of the turn that ENDED the episode (the repo's convergence vector is defined
    per generation; an agentic episode's closest analogue is its final turn), judged against the
    resolved budget when `context_limit`/`max_tokens` are known (bench.convergence)."""
    if not per_turn:
        return None
    last = per_turn[-1]
    row = {"finish_reason": last.get("finish_reason"), "completion_tokens": last.get("completion_tokens"),
          "prompt_tokens": last.get("prompt_tokens"), "thinking_budget": thinking_budget}
    if context_limit and max_tokens:
        convergence.backfill_resolved_budget([row], context_limit=context_limit, max_tokens=max_tokens)
    return convergence.is_converged(row)


# --------------------------------------------------------------------------- per-task run
def run_task(model: str, task: dict, scripts_root, driver, params: dict, *,
            container_prefix: str = "agentbench-os", exec_timeout: float = DEFAULT_EXEC_TIMEOUT_S,
            llm_timeout: float = 3600.0, max_turns: int = ROUND_LIMIT, deadline_s=None,
            loop_guard=None, context_limit=None, runner=subprocess.run,
            clock=time.perf_counter) -> dict:
    """One task, one container, start to `docker rm -f` (always, via `finally` -- AC9)."""
    cfg = task_config(task, scripts_root)
    name = container_name(container_prefix, task["id"])
    remove_container(name, runner)   # idempotent pre-clean (a prior interrupted run may have left one)
    t0 = clock()
    base = {"id": task["id"], "group": task.get("group"), "labels": task.get("labels") or [],
            "image": cfg["image"]}
    try:
        create_container(f"local-os/{cfg['image']}", name, runner)
        for s in cfg["init_scripts"]:
            res = docker_exec(name, s, exec_timeout, runner)
            if res["timed_out"] or res["exit_code"] != 0:
                raise RuntimeError(f"init script failed (timed_out={res['timed_out']}, "
                                   f"exit={res['exit_code']}): {res['stderr'][:200]}")
        if cfg["start"]:
            res = docker_exec(name, cfg["start"], exec_timeout, runner)
            if res["timed_out"] or res["exit_code"] != 0:
                raise RuntimeError(f"start script failed (timed_out={res['timed_out']}, "
                                   f"exit={res['exit_code']}): {res['stderr'][:200]}")

        tool_counters = {"tool_timeouts": 0}
        tools = build_tools(name, runner, exec_timeout, tool_counters)
        wrapped = DualSubmitDriver(driver, timeout=llm_timeout)
        task_text = TASK_TEMPLATE.format(description=task.get("description", ""))
        result = agent_loop.run_agent(wrapped, model, SYSTEM_PROMPT, task_text, tools, params,
                                      max_turns=max_turns, submit_tool=DualSubmitDriver.SUBMIT_TOOL,
                                      deadline_s=deadline_s, loop_guard=loop_guard, clock=clock)

        def _evaluate(answer):
            if cfg["match"] is not None:
                return evaluate_match(answer, cfg["match"])
            return run_check_chain(name, cfg["check"], cfg["example"], answer, runner, exec_timeout)

        outcome, passed, answer = finalize_outcome(result, _evaluate)
        counters = result.get("counters") or {}
        conv = episode_converged(wrapped.per_turn, params.get("thinking_budget"), context_limit,
                                 params.get("max_tokens"))
        return {**base, "passed": passed, "outcome": outcome, "turns": result.get("turns", 0),
                "submitted_via": wrapped.submitted_via, "answer": answer, "gold": None,
                "per_turn_completion_tokens": [t.get("completion_tokens") for t in wrapped.per_turn],
                "completion_tokens_total": counters.get("completion_tokens", 0),
                "finish_reasons": [t.get("finish_reason") for t in wrapped.per_turn],
                "converged": conv, "wall_s": counters.get("wall_s", round(clock() - t0, 2)),
                "tool_calls": counters.get("tool_calls", 0),
                "tool_timeouts": tool_counters["tool_timeouts"],
                "error": result.get("error")}
    except KeyboardInterrupt:
        raise
    except Exception as e:  # noqa: BLE001 -- infra/setup failure, not a model failure; never crash the batch
        return {**base, "passed": False, "outcome": AO.SERVER_ERROR, "turns": 0,
                "submitted_via": None, "answer": None, "gold": None,
                "per_turn_completion_tokens": [], "completion_tokens_total": 0,
                "finish_reasons": [], "converged": None, "wall_s": round(clock() - t0, 2),
                "tool_calls": 0, "tool_timeouts": 0,
                "error": f"{type(e).__name__}: {e}"}
    finally:
        remove_container(name, runner)
