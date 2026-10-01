"""M54: AgentBench `os-std` adapter — corpus loading, task-config normalization (mirrors
upstream `task.py`'s `_load_configs`/`_evaluate_answer` semantics exactly), one-container-per-task
lifecycle over `docker` with a persistent per-task shell session (upstream-faithful), and the
dual-submit shim that lets agent_loop.run_agent terminate on either upstream tool.

Upstream: THUDM/AgentBench (Apache-2.0), pinned commit d1e4a10db08c87075c78972e48ecc182be03e2d5,
`os-std` split (`configs/tasks/os.yaml`, `src/server/tasks/os_interaction/task.py`,
`src/server/tasks/os_interaction/environment.py`). Corpus vendored at
`benchmark/corpora/agentbench_os_v1.jsonl` (+ manifest + scripts + LICENSE).

DUAL-SUBMIT DESIGN NOTE. Upstream's os-std protocol has TWO tools that end an episode
(`answer_action`, `finish_action`); `agent_loop.run_agent` only matches a single literal
`submit_tool` name. `DualSubmitDriver.complete()` renames any `finish_action` tool call to the
canonical `answer_action` (folding its `thought` into an `answer` key) BEFORE returning to
run_agent, so termination is a single-name match from run_agent's point of view, while the TWO
upstream tool schemas still reach the model verbatim. `submitted_via` records which was used.

CONTAINER LIFECYCLE (cold-review F4a: upstream-faithful, not one `docker exec` per command). One
task = one container: create (`-w /root --memory 1g --memory-swap 1g --cpus 2`, environment.py:20-
29) -> init scripts (fresh non-interactive `docker exec`, mirroring `execute_independent`) -> a
SINGLE persistent `docker exec -i <name> /bin/bash --login` session for `start` AND every
`bash_action` (mirroring `execute`/the session Container upstream uses — this is what makes a
`start` script's `cd`/`su -`/env vars persist into later `bash_action` calls) -> evaluate (match,
or the check-script chain, each via a FRESH non-interactive `docker exec`, mirroring
`execute_independent` again) -> `docker rm -f`, always in a `finally` (success, failure, timeout,
KeyboardInterrupt all remove the container and close the shell — AC9).

TRANSPORT VS INFRA FAILURES (cold-review F1). A `driver.complete` exception (HTTP error, timeout,
connection error) surfaces from `agent_loop.run_agent` as `outcome=server_error` + a populated
`error` string — AGENTS.md: transport/HTTP failures ESCALATE, they are NEVER graded. `run_task`
detects exactly that signature and raises `TransportFailure` instead of returning a row (container
still cleaned up in `finally`). A DOCKER-side setup/evaluate failure (container wouldn't start, an
init/start script failed, grading itself errored) stays a labelled row with `setup_error: true` so
the CLI can report and exclude it from the accuracy denominator without crashing the batch.

D2 EXCLUSION (pre-registered, C107; cold-review F6/F7). Before any model call, for every CHECK task
(never `match`): run `evaluation.example.code` to completion in two FRESH containers with TWO
DIFFERENT placeholder "answers" (`""` and a sentinel). Disagreement reveals the example script
reads the answer argument (`gold_mismatch`) — a blind spot in treating a null check-slot as
an answer-independent gold. Empty stdout at either run, or any failure/timeout, is `no_gold`. This
is a corpus-level, not per-model, artifact (see `exclusions_artifact_path` et al.) — the cached
gold is NOT substituted into per-item grading; grading always re-runs the check chain live in the
task's own post-agent container, exactly as task.py does.
"""
from __future__ import annotations

import codecs
import hashlib
import json
import queue
import random
import re
import statistics
import subprocess
import sys
import threading
import time
import uuid
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

# task.py:558-566 (empty tool_calls re-prompt) and :660-668 (bash-output wrapping), VERBATIM.
NO_TOOL_CALL_REPROMPT = "No executable tool calls found. Please call a tool instead"
TRUNCATE_LIMIT = 800
TRUNCATE_KEEP = 780
TRUNCATE_MARKER = "\n[truncated because the output is too long]"
OUTPUT_PREFIX = "The output of the OS:\n\n"
EMPTY_OUTPUT_TEXT = "The output of the OS is empty."

DEFAULT_EXEC_TIMEOUT_S = 30.0          # cold-review F5(e); upstream per-command bound
IMAGE_NAMES = ("default", "packages", "ubuntu")
# D2 answer-dependence probe (cold-review N3/N4): two PLAUSIBLE-LOOKING answers (not an empty
# string or an obviously-synthetic sentinel, which a script might special-case or which might
# coincidentally behave like "no match" either way) fed to `evaluation.example` at a null
# check-slot. Disagreement between them means the script reads the answer argument.
ANSWER_PLACEHOLDER_PRIMARY = "1"
ANSWER_PLACEHOLDER_PROBE = "2"
# Distinct, non-prefix-colliding container-name prefixes (cold-review F16): the old scheme had the
# generate prefix ("agentbench-os") as a literal PREFIX of the prepare prefix
# ("agentbench-os-prep"), so a generate-mode startup sweep silently killed live prepare containers
# (and vice versa) whenever both ran the same day.
GENERATE_CONTAINER_PREFIX = "agentbench-os-run"
PREPARE_CONTAINER_PREFIX = "agentbench-os-prep"
# D2 exclusion rule version. v2 (operator 2026-09-30, after the live --prepare run found 11 of 13
# exclusions were randomized-init tasks -- $RANDOM/shuf -- legitimately disagreeing across two
# FRESH containers): gold-slot tasks are now probed with the example run TWICE inside the SAME
# already-set-up container, mirroring upstream (`task.py` grades the check chain, including any
# null-slot `example`, inside the task's OWN live container, never a fresh one per probe).
EXCLUSIONS_RULE_VERSION = 2


class TransportFailure(RuntimeError):
    """`driver.complete` raised during the agent loop (HTTP error/timeout/connection error).
    AGENTS.md: transport/HTTP failures ESCALATE, they are NEVER graded -- `run_task` raises this
    instead of returning a row; the container is still removed (`finally`)."""


# --------------------------------------------------------------------------- corpus
def load_corpus(path, limit=None) -> list:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[:limit] if limit else rows


def apply_exclusions(tasks: list, exclusions: list) -> list:
    excluded_ids = {e["id"] for e in exclusions}
    return [t for t in tasks if t["id"] not in excluded_ids]


def pilot_draw(task_ids: list, seed: int, n: int = 5) -> list:
    """Seeded random subset of `task_ids`, size <= n. NEVER the first n (AGENTS.md: the corpus is
    ordered easy-first) -- shuffle the whole pool, then take a prefix of the SHUFFLED order."""
    pool = list(task_ids)
    random.Random(seed).shuffle(pool)
    return pool[:n]


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- corpus-level exclusions artifact
def exclusions_artifact_path(corpus_path) -> Path:
    """A CORPUS artifact, not per-model/per-run (cold-review F6): sibling of the corpus jsonl,
    e.g. `agentbench_os_v1.jsonl` -> `agentbench_os_v1.exclusions.json`."""
    p = Path(corpus_path)
    stem = p.name[:-len(".jsonl")] if p.name.endswith(".jsonl") else p.name
    return p.parent / f"{stem}.exclusions.json"


def scripts_root_sha256(scripts_root) -> str:
    """5th cold review P10: sha256 over every vendored script file under `scripts_root` (sorted
    relative posix paths + contents) -- an edit to a check/example/init script invalidates the
    exclusions artifact just like a corpus or image change does."""
    root = Path(scripts_root)
    h = hashlib.sha256()
    if root.exists():
        for f in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
            h.update(f.relative_to(root).as_posix().encode("utf-8") + b"\x00")
            h.update(f.read_bytes() + b"\x00")
    return h.hexdigest()


def build_disposition_map(tasks: list, scripts_root, golds: dict, exclusions: list) -> dict:
    """P10: a per-task disposition covering EVERY corpus id -- `"match"` (never examined by D2),
    `"kept"`, or `"excluded:<reason>"`. Built from `prepare_exclusions`'s own outputs rather than
    changing that function's return shape (every existing caller keeps working)."""
    excluded_reason = {e["id"]: e["reason"] for e in exclusions}
    disposition = {}
    for task in tasks:
        cfg = task_config(task, scripts_root)
        if cfg["match"] is not None:
            disposition[task["id"]] = "match"
        elif task["id"] in excluded_reason:
            disposition[task["id"]] = f"excluded:{excluded_reason[task['id']]}"
        else:
            disposition[task["id"]] = "kept"
    return disposition


def write_exclusions_artifact(path, *, corpus_sha256: str, image_ids: dict, golds: dict,
                              exclusions: list, complete: bool,
                              manual_exclusions_sha256: str | None = None,
                              scripts_root: str | None = None,
                              scripts_sha256: str | None = None,
                              disposition: dict | None = None,
                              rule_version: int = EXCLUSIONS_RULE_VERSION) -> dict:
    doc = {"rule_version": rule_version, "corpus_sha256": corpus_sha256, "image_ids": image_ids,
          "scripts_root": str(scripts_root) if scripts_root is not None else None,
          "scripts_sha256": scripts_sha256, "golds": golds, "exclusions": exclusions,
          "disposition": disposition or {}, "complete": complete,
          "manual_exclusions_sha256": manual_exclusions_sha256, "generated_at": int(time.time())}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return doc


def read_exclusions_artifact(path):
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def validate_exclusions_artifact(doc, *, corpus_sha256: str, image_ids: dict,
                                 manual_exclusions_sha256: str | None = None,
                                 scripts_sha256: str | None = None,
                                 all_task_ids: list | None = None,
                                 rule_version: int = EXCLUSIONS_RULE_VERSION):
    """None if `doc` is usable for a generate run against the CURRENT corpus + images + manual
    exclusions file + vendored scripts; else a human-readable refusal reason."""
    if doc is None:
        return "no exclusions artifact -- run --prepare first"
    if doc.get("rule_version") != rule_version:
        return (f"exclusions artifact rule_version={doc.get('rule_version')!r} but this driver "
               f"expects {rule_version} -- rerun --prepare")
    if not doc.get("complete"):
        return ("exclusions artifact has complete=false (produced with --limit, or an earlier "
               "--prepare was interrupted) -- rerun --prepare over the WHOLE corpus")
    if doc.get("corpus_sha256") != corpus_sha256:
        return "corpus changed since --prepare (sha256 mismatch) -- rerun --prepare"
    if doc.get("image_ids") != image_ids:
        return "local-os image ids changed since --prepare -- rerun --prepare"
    if doc.get("manual_exclusions_sha256") != manual_exclusions_sha256:
        return "manual exclusions file changed since --prepare -- rerun --prepare"
    if scripts_sha256 is not None and doc.get("scripts_sha256") != scripts_sha256:
        return "vendored scripts changed since --prepare (sha256 mismatch) -- rerun --prepare"
    if all_task_ids is not None:
        disposition = doc.get("disposition") or {}
        missing = [i for i in all_task_ids if i not in disposition]
        if missing:
            return (f"exclusions artifact is missing a disposition for {len(missing)} corpus "
                   f"id(s) (e.g. {missing[0]!r}) -- rerun --prepare")
    return None


# --------------------------------------------------------------------------- manual exclusions
def manual_exclusions_path(corpus_path) -> Path:
    """A hand-curated corpus-sibling file (never auto-generated) naming tasks excluded for a
    reason the D2 probe cannot mechanically detect (e.g. a probe blind spot found by inspection --
    see std-007-84). `{id: reason}`."""
    p = Path(corpus_path)
    stem = p.name[:-len(".jsonl")] if p.name.endswith(".jsonl") else p.name
    return p.parent / f"{stem}.manual_exclusions.json"


def load_manual_exclusions(path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


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


def images_available(images=IMAGE_NAMES, runner=subprocess.run) -> dict:
    out = {}
    for name in images:
        try:
            proc = runner(["docker", "image", "inspect", f"local-os/{name}"],
                          capture_output=True, text=True, timeout=10)
            out[name] = getattr(proc, "returncode", 1) == 0
        except Exception:  # noqa: BLE001
            out[name] = False
    return out


def current_image_ids(images=IMAGE_NAMES, runner=subprocess.run) -> dict:
    """{name: `docker image inspect --format '{{.Id}}'` output, or None if unavailable}."""
    out = {}
    for name in images:
        try:
            proc = runner(["docker", "image", "inspect", "--format", "{{.Id}}", f"local-os/{name}"],
                          capture_output=True, text=True, timeout=10)
            out[name] = (proc.stdout or "").strip() if getattr(proc, "returncode", 1) == 0 else None
        except Exception:  # noqa: BLE001
            out[name] = None
    return out


def container_name(prefix: str, task_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "-", task_id)
    return f"{prefix}-{safe}"


def sweep_stale_containers(prefix: str, runner=subprocess.run) -> list:
    """Remove any container whose name starts with `prefix-` (a crash/interrupt from a prior run
    left it behind). Returns the names removed. `prefix` must not be a PREFIX of another live
    prefix (cold-review F16) -- callers use the distinct GENERATE_/PREPARE_CONTAINER_PREFIX
    constants, never a shared stem.

    P26: each removal is VERIFIED (same fail-closed gate as run_task's final cleanup and D2
    prepare) -- raises `ContainerCleanupError` on the first one that can't be confirmed absent,
    rather than silently starting a run on a box that may already be accumulating live
    containers.

    7th cold review round 7 P40 (HIGH): discovering the stale list is now ALSO fail-closed --
    a failed `docker ps -a` (nonzero rc, launch exception, or timeout) raises
    `ContainerDiscoveryError` BEFORE a single container is created, instead of the old best-effort
    `except Exception: return []`, which made "docker is unreachable" and "genuinely nothing to
    sweep" indistinguishable; a transient discovery failure could let another task's container
    start while an earlier crashed run's container survived under the exact same prefix."""
    try:
        proc = runner(["docker", "ps", "-a", "--filter", f"name=^{prefix}-", "--format", "{{.Names}}"],
                      capture_output=True, text=True, timeout=30)
    except Exception as e:  # noqa: BLE001
        raise ContainerDiscoveryError(
            f"startup sweep discovery failed for prefix {prefix!r}: {type(e).__name__}: {e}") from e
    if getattr(proc, "returncode", None) != 0:
        raise ContainerDiscoveryError(
            f"startup sweep discovery failed for prefix {prefix!r}: `docker ps -a` exited "
            f"{getattr(proc, 'returncode', None)} (stderr={(getattr(proc, 'stderr', '') or '')[:200]!r})")
    names = [n for n in (proc.stdout or "").splitlines() if n.strip()]
    for n in names:
        if not remove_container(n, runner, verify=True):
            raise ContainerCleanupError(f"stale container {n} was not verifiably removed at startup sweep")
    return names


def create_container(image: str, name: str, runner=subprocess.run, timeout: float = 60.0) -> None:
    """`-w /root --memory 1g --memory-swap 1g --cpus 2` mirror upstream's
    `environment.py:create_docker_container` (WorkingDir=/root, Memory=1GiB, MemorySwap=Memory i.e.
    swap disabled, NanoCpus=2e9 i.e. 2 vCPUs)."""
    proc = runner(["docker", "run", "-d", "--rm=false", "--name", name, "-w", "/root",
                  "--memory", "1g", "--memory-swap", "1g", "--cpus", "2",
                  image, "sleep", "infinity"],
                 capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"docker run {image} (name={name}) failed: {(proc.stderr or '')[:300]}")


class ContainerCleanupError(RuntimeError):
    """5th cold review P16: `docker rm -f` either reported failure or a `docker ps -a` check
    afterward still shows the container -- the caller (run_agentbench_os.py) raises this AFTER the
    row has been written, stopping the run rather than starting the next container on a box that
    may be silently accumulating live containers."""


class ContainerDiscoveryError(RuntimeError):
    """7th cold review round 7 P40 (HIGH): a startup sweep's OWN discovery command
    (`docker ps -a --filter name=<prefix>`) failing must ABORT before a single container is
    created -- a failed discovery returning an empty match list is INDISTINGUISHABLE from a
    genuinely clean box, and silently proceeding on that non-evidence can leave a crashed prior
    run's container alive alongside a brand-new one using the same name pattern."""


def remove_container(name: str, runner=subprocess.run, verify: bool = False):
    """Best-effort by default (returns None, never raises -- every OTHER call site, e.g. D2
    prepare's per-probe churn and the pre-clean before `create_container`, wants exactly that).

    `verify=True` (run_task's own final cleanup, prepare, startup sweeps, exceptional exits --
    ALL of them, round 6 P26) confirms ABSENCE via `docker ps -a --filter name=<name>`, fail-
    closed: verified ONLY if that check command ITSELF succeeded (rc 0) AND its stdout is empty.

    6th cold review round 6 P26 (HIGH): the OLD check only looked at `check`'s STDOUT, never its
    OWN returncode -- a `docker ps -a` invocation that itself FAILED (rc 1, e.g. a daemon hiccup)
    but happened to produce no stdout (an error went to stderr, or the process died before
    printing anything) was indistinguishable from "confirmed empty", so `verify=True` could
    return `True` while nothing was actually proven. Now the check command's own rc is required.

    Addendum G: the final verdict depends SOLELY on the VERIFICATION step, independent of
    `docker rm -f`'s own rc -- a `docker run` that itself failed (container never created) makes
    `rm -f` legitimately report nonzero (no such container), which is NOT a cleanup failure; what
    matters is only whether the container is PROVABLY absent now, which `docker ps -a` answers on
    its own."""
    try:
        runner(["docker", "rm", "-f", name], capture_output=True, text=True, timeout=30)
    except Exception:  # noqa: BLE001 -- cleanup must never raise over the real error/result
        pass
    if not verify:
        return None
    try:
        check = runner(["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
                      capture_output=True, text=True, timeout=30)
        check_rc = getattr(check, "returncode", None)
        stdout = (getattr(check, "stdout", "") or "").strip()
    except Exception:  # noqa: BLE001 -- cannot verify -> treat as NOT verified (fail closed)
        check_rc, stdout = None, "unverifiable"
    return check_rc == 0 and stdout == ""


def docker_exec(container: str, lang_code, timeout: float, runner=subprocess.run,
                extra_params=()) -> dict:
    """One FRESH, non-interactive `docker exec` (mirrors task.py `execute_independent`, used for
    init scripts and all evaluation/check/example scripts -- NEVER for `start` or `bash_action`,
    which share the persistent session; see `PersistentShell`). Returns
    {exit_code, stdout, stderr, timed_out}. `extra_params` are appended argv (the answer / prior
    check-script stdout chain)."""
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


def truncate_output(text: str, limit: int = TRUNCATE_LIMIT, keep: int = TRUNCATE_KEEP,
                    marker: str = TRUNCATE_MARKER):
    """task.py:660-668, verbatim mechanism: over `limit` chars -> first `keep` chars + marker
    (the result can exceed `limit` once the marker is added, exactly like upstream)."""
    if len(text) <= limit:
        return text, False
    return text[:keep] + marker, True


def wrap_os_output(text: str) -> str:
    """task.py:660-668 VERBATIM wrapping: the already-(possibly)-truncated text, or the exact
    empty-output sentence."""
    return f"{OUTPUT_PREFIX}{text}" if text else EMPTY_OUTPUT_TEXT


# --------------------------------------------------------------------------- persistent shell (F4a)
class PersistentShell:
    """One `docker exec -i <container> /bin/bash --login` process for the life of a task (upstream
    `Container.execute`'s session, not a fresh exec per command). `start` and every `bash_action`
    are written to this SAME shell's stdin AS-IS -- no `bash -c`, no in-container `timeout` wrapper
    -- so a `start` script's `cd`/`var=...`/`su - jack` genuinely persists into later commands: a
    `su - jack` hands stdin to jack's own shell, and the NEXT command we write (including its
    sentinel) is simply read by whichever shell currently owns stdin. A fresh `docker exec` per
    command (the pre-cold-review-round-2 design) could never do this at all.

    PROTOCOL (2nd cold review, N1/N2). Each `run(cmd)` writes
        {cmd}\\nprintf '\\n%s%d\\n' {sentinel} $?\\n
    where `sentinel` is a fresh uuid per call -- the command text VERBATIM, then one more line that
    prints a literal newline, the sentinel, and `$?` (the command's exit status). The printf's
    leading `\\n` guarantees the sentinel always starts a fresh output line even when the command's
    own output had no trailing newline, and that exact injected newline is the one stripped from
    the returned output.

    SENTINEL SEARCH (3rd cold review R1/R4/R9): matching is done on the RAW BYTES with
    `bytearray.find(marker, start)`, never by re-running a regex over the whole accumulated buffer
    after every chunk -- the earlier `re.search(..., DOTALL)` approach was O(n^2) (measured: 20 KB
    -> 9.4s, 50 KB -> 116s, >=100 KB effectively hangs). `search_from` only moves forward, so total
    work across a `run()` call is O(bytes received), not O(bytes^2). The marker (`"\\n" + sentinel`)
    is pure ASCII, so finding it in the RAW byte stream is always safe even if a multi-byte UTF-8
    character from the command's own output happens to straddle a chunk boundary elsewhere in the
    buffer (UTF-8 continuation bytes are never valid ASCII byte values, so they can't produce a
    false match, and the marker's own bytes can't be split by someone else's multi-byte sequence).
    The exit-code digits after the marker must themselves be terminated by a newline
    (`re.match(rb"(\\d+)\\n", ...)`) before the round is considered complete -- a chunk boundary
    landing mid-digits (e.g. "...13" | "7\\n") must not be read as exit code 13 (R4); if the
    trailing newline hasn't arrived yet, reading continues from the SAME marker offset. The output
    span is decoded to `str` ONCE, as a whole, only after its complete byte range is known -- this
    (not a streaming incremental decoder) is what actually guarantees a multi-byte character that
    was split across two `read()` chunks decodes correctly (R9): by decode time the two chunks'
    bytes are already concatenated contiguously. Any bytes received after the exit-code's newline
    are unexpected (nothing should still be arriving once a round is consumed) and are carried to
    the NEXT `run()` call rather than dropped, with a warning logged.

    TIMEOUT is enforced ONLY on the Python side (there is no in-container `timeout` anymore): if
    the sentinel hasn't arrived within `timeout_s`, the Popen is killed and a best-effort
    `docker exec <container> pkill -KILL -f "bash --login"` is issued (R7: deliberately simple and
    bounded -- the container is removed at task end regardless, and exact process-GROUP semantics
    inside an arbitrary image are unverified, so this is a backstop, not the primary guarantee).
    (4th cold review G1: exit code 137 is NO LONGER treated as a timeout -- there is no
    in-container timeout wrapper any more, so a model-run process legitimately OOM-killed by the
    container's 1 GiB memory cap also exits 137, and mis-scoring that as `exec_timeout` would
    hide a real memory failure behind the wrong label. Only OUR OWN Python-side deadline counts.)
    A command that reads stdin (e.g. a bare `read` with no input piped to it) will itself hang
    until this timeout fires, same as upstream's session-based execution (R8) -- there is no
    attempt to detect or special-case that.

    THE DEADLINE COVERS THE WRITE TOO (5th cold review P8): it is set once, before the command is
    even written to stdin, and the write itself goes through a bounded writer thread -- if the
    shell is busy (e.g. running a long foreground command) and never reads stdin, the OS pipe's
    write buffer fills and a plain `.write()` blocks indefinitely; that blocking IS a timeout, not
    just a slow read.

    MEMORY IS BOUNDED (G2): the reader thread's queue has `maxsize=256` (backpressure on a chatty
    background process once we stop reading its queue -- e.g. `while :; do echo tick; done &`
    inside the task), and the retained raw buffer is capped at ~1 MiB, keeping the first and last
    512 KiB with a `[... N bytes dropped ...]` marker in between. The MODEL never sees more than
    780 chars anyway (`truncate_output`); `raw_output_len` on the row/transcript still reports the
    TRUE pre-cap length so a huge/degenerate output is still visible in the data, just not held
    entirely in memory.

    INVALID UTF-8 (5th cold review P15b): reproduces upstream's exact behaviour
    (`_execute_bash_command`: a strict `.decode("utf-8")` that raises on any invalid byte) --
    the WHOLE output becomes the literal upstream string `"OS Environment output cannot be
    decoded as UTF-8"` rather than per-character `errors="replace"` mojibake.

    SHELL DEATH (N9). Upstream: `exit` ends the session. If the shell process exits (EOF on
    stdout, or a `BrokenPipeError` writing to a dead stdin), `run()` returns `shell_died=True`
    immediately rather than hanging for the full timeout.
    """

    UPSTREAM_DECODE_ERROR_TEXT = "OS Environment output cannot be decoded as UTF-8"
    MAX_RETAINED_BYTES = 1024 * 1024
    RETAINED_HEAD_BYTES = 512 * 1024
    RETAINED_TAIL_BYTES = 512 * 1024
    MAX_RETAINED_CHARS = 1024 * 1024
    RETAINED_HEAD_CHARS = 512 * 1024
    RETAINED_TAIL_CHARS = 512 * 1024

    def __init__(self, container: str, popen=subprocess.Popen, runner=subprocess.run,
                read_chunk: int = 65536, queue_maxsize: int = 256):
        self.container = container
        self._popen = popen
        self._runner = runner
        self._read_chunk = read_chunk
        self.proc = None
        self._q: "queue.Queue" = queue.Queue(maxsize=queue_maxsize)
        self.dead = False
        self._carry = b""   # unexpected leftover bytes past a previous round's sentinel (see above)
        self._reader_thread = None
        # 7th cold review round 7 P41 (MEDIUM): checked by the reader's put-retry loop so it can
        # actually STOP once close() wants it to, instead of blocking forever inside a bare
        # `Queue.put()` on a full queue nobody is draining any more (a timed `Thread.join()` alone
        # cannot interrupt a thread parked in a blocking call).
        self._cancel = threading.Event()

    def start(self) -> dict:
        """Returns the handshake (no-op sentinel round) result -- P9(b): the caller MUST check
        this and refuse to make any model call if it didn't cleanly succeed."""
        self.proc = self._popen(
            ["docker", "exec", "-i", self.container, "/bin/bash", "--login"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        # N8: a login shell sources profile scripts that can print banners/MOTD/warnings before
        # anything we asked for. One no-op sentinel round, with everything read before it discarded.
        return self.run("true", timeout_s=10.0)

    def _put_until_cancelled(self, item) -> None:
        """P41: retry `put(timeout=...)` in a loop, checking `self._cancel` between attempts --
        unlike a bare blocking `put()`, this can actually be told to STOP once nobody is going to
        drain the queue any more (close() sets the cancel event)."""
        while not self._cancel.is_set():
            try:
                self._q.put(item, timeout=0.2)
                return
            except queue.Full:
                continue

    def _reader_loop(self) -> None:
        try:
            while not self._cancel.is_set():
                chunk = self.proc.stdout.read(self._read_chunk)
                if not chunk:
                    self._put_until_cancelled(None)
                    return
                self._put_until_cancelled(chunk)   # backpressure (G2), but CANCELLABLE (P41)
        except (ValueError, OSError):
            # the stdout fd is gone (close() closed it, or the process died) -- EOF-equivalent.
            self._put_until_cancelled(None)

    def _start_writer(self, data: bytes) -> dict:
        """5th cold review round 6, P22 (HIGH, deadlock): the OLD design made `run()` BLOCK on
        `_write_with_deadline` (a synchronous `done.wait(...)`) before EVER draining the reader
        queue. Reproduced: bash given `head -c 20MB /dev/zero` followed by a 300KiB comment on the
        SAME stdin write wedges solid -- bash starts executing the first line and floods its own
        stdout; the reader thread (already running) fills the BOUNDED queue (G2, maxsize=256) and
        blocks on `put()`; `run()`'s main loop isn't draining that queue yet because it is still
        parked waiting for the ENTIRE write to finish; the write can't finish because bash hasn't
        gotten back to reading more stdin (it's busy, and backed up on its own stdout). Classic
        two-sided pipe deadlock.

        Fix: the write now happens in an INDEPENDENT background thread that `run()` never awaits
        synchronously -- `run()` starts this and immediately begins draining the queue in the SAME
        loop, both bounded by the SAME overall deadline, so the reader is always being serviced
        and the writer's blocking `.write()` calls keep completing as bash keeps making progress.
        The data is written in bounded chunks so an `abort` request (deadline expiry, or a found
        sentinel making the rest of the write moot) is noticed promptly rather than only at the
        next multi-hundred-KB syscall boundary."""
        box: dict = {"done": False, "error": None, "abort": False, "thread": None}

        def _writer():
            try:
                view = memoryview(data)
                off = 0
                chunk_size = 65536
                while off < len(view):
                    if box["abort"]:
                        return
                    piece = bytes(view[off:off + chunk_size])
                    n = self.proc.stdin.write(piece)
                    if not n:
                        n = len(piece)   # some stream wrappers return None on success
                    off += n
                self.proc.stdin.flush()
            except Exception as e:  # noqa: BLE001
                box["error"] = e
            finally:
                box["done"] = True

        t = threading.Thread(target=_writer, daemon=True)
        box["thread"] = t
        t.start()
        return box

    def run(self, command: str, timeout_s: float = DEFAULT_EXEC_TIMEOUT_S) -> dict:
        """Returns {output, exit_code, timed_out, shell_died, raw_output_len}."""
        if self.proc is None:
            raise RuntimeError("PersistentShell.run() called before start()")
        if self.dead or self.proc.poll() is not None:
            self.dead = True
            return {"output": "", "exit_code": None, "timed_out": False, "shell_died": True,
                   "raw_output_len": 0}

        # P8: the deadline is set BEFORE anything is written, and covers the write itself.
        deadline = time.monotonic() + timeout_s
        sentinel = f"__M54_SENTINEL_{uuid.uuid4().hex}__"
        full = f"{command}\nprintf '\\n%s%d\\n' {sentinel} $?\n"
        data = full.encode("utf-8")
        # P22: start the write CONCURRENTLY -- never await it before draining the reader queue.
        writer_box = self._start_writer(data)

        marker = ("\n" + sentinel).encode("ascii")

        # P28 (MEDIUM): decode INCREMENTALLY as each ORIGINAL chunk arrives, never by re-decoding
        # an arbitrary byte-offset slice of the (possibly head/tail-capped) accumulated buffer --
        # a fixed byte cut can land mid-multibyte-character (reproduced: 1.2MB of valid `€`
        # characters, 3 bytes each, produced the upstream decode-error message for the WHOLE
        # output because the 512KiB head/tail cut split one). `codecs.getincrementaldecoder`
        # correctly buffers a trailing incomplete sequence across chunk boundaries by itself.
        # `raw` stays BYTES-only and is used EXCLUSIVELY for sentinel search (ASCII, never
        # decoded) -- its own byte-level cap (`_cap_buffer`) is therefore safe as-is. The decoded
        # TEXT is capped separately, by CHARACTER count (`_cap_text`), which can never split a
        # codepoint.
        decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
        decoded_text = ""
        decode_broken = False

        def _feed(piece: bytes) -> None:
            nonlocal decoded_text, decode_broken
            if decode_broken or not piece:
                return
            try:
                decoded_text = self._cap_text(decoded_text + decoder.decode(piece))
            except UnicodeDecodeError:
                decode_broken = True

        raw = bytearray(self._carry)
        total_bytes_in = len(self._carry)   # G2: tracked INDEPENDENTLY of capping, so
        _feed(bytes(self._carry))           # a previous round's leftover carry IS output text too
        self._carry = b""                   # `raw_output_len` stays exact regardless of how many
        search_from = 0                     # times the retained buffer gets compacted.

        try:
            while True:
                idx = raw.find(marker, max(0, search_from - len(marker)))
                if idx != -1:
                    m = re.match(rb"(\d+)\n", bytes(raw[idx + len(marker):]))
                    if m:
                        exit_code = int(m.group(1))
                        # bytes after idx were never touched by capping (capping only ever drops a
                        # MIDDLE span strictly before the eventual sentinel position) -- so
                        # total_bytes_in minus that trailing length is the exact TRUE output
                        # length, and the trailing span's CHARACTER length (it's pure ASCII --
                        # sentinel + digits + newline, plus any rare non-ASCII "leftover") equals
                        # its byte length closely enough to trim `decoded_text` by.
                        raw_output_len = total_bytes_in - (len(raw) - idx)
                        trailer_len = len(raw) - idx
                        output = (self.UPSTREAM_DECODE_ERROR_TEXT if decode_broken
                                 else decoded_text[:max(0, len(decoded_text) - trailer_len)])
                        consumed_end = idx + len(marker) + m.end()
                        leftover = bytes(raw[consumed_end:])
                        if leftover:
                            print(f"[PersistentShell] WARNING: {len(leftover)} unexpected byte(s) "
                                 "past the sentinel; carrying to the next run() call",
                                 file=sys.stderr)
                        self._carry = leftover
                        writer_box["abort"] = True
                        return {"output": output, "exit_code": exit_code, "timed_out": False,
                               "shell_died": False, "raw_output_len": raw_output_len}
                    # digits present but not yet newline-terminated -- re-check from the SAME
                    # offset once more data arrives (R4: never guess a partial exit code).
                    search_from = idx
                else:
                    search_from = len(raw)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    writer_box["abort"] = True
                    self._on_timeout()
                    out = self.UPSTREAM_DECODE_ERROR_TEXT if decode_broken else decoded_text
                    return {"output": out, "exit_code": None, "timed_out": True,
                           "shell_died": False, "raw_output_len": total_bytes_in}
                try:
                    chunk = self._q.get(timeout=min(remaining, 0.1))
                except queue.Empty:
                    if writer_box["done"] and writer_box["error"] is not None:
                        # the write itself failed (broken pipe / shell gone) AND nothing more is
                        # arriving on this pass -- the shell is dead.
                        self.dead = True
                        out = self.UPSTREAM_DECODE_ERROR_TEXT if decode_broken else decoded_text
                        return {"output": out, "exit_code": None, "timed_out": False,
                               "shell_died": True, "raw_output_len": total_bytes_in}
                    continue
                if chunk is None:   # EOF -- the shell process exited (e.g. the command ran `exit`)
                    self.dead = True
                    out = self.UPSTREAM_DECODE_ERROR_TEXT if decode_broken else decoded_text
                    return {"output": out, "exit_code": None, "timed_out": False,
                           "shell_died": True, "raw_output_len": total_bytes_in}
                total_bytes_in += len(chunk)
                raw += chunk
                _feed(chunk)
                capped = self._cap_buffer(raw)
                if len(capped) != len(raw):
                    # bytes were physically removed from the middle -- any offset computed against
                    # the OLD buffer is no longer meaningful; the capped buffer is <=~1MiB
                    # regardless, so a full re-scan from 0 is cheap (the G2 bound, not the R1
                    # O(n^2) problem).
                    search_from = 0
                raw = capped
        finally:
            writer_box["abort"] = True

    def _cap_buffer(self, raw: bytearray) -> bytearray:
        """G2: bound memory on a chatty background writer -- keep head+tail, drop the middle.
        BYTES ONLY -- `raw` is never decoded (see P28); this cut can split a multibyte character
        and that is fine, since it's used exclusively for ASCII sentinel search."""
        if len(raw) <= self.MAX_RETAINED_BYTES:
            return raw
        head = bytes(raw[:self.RETAINED_HEAD_BYTES])
        tail = bytes(raw[-self.RETAINED_TAIL_BYTES:])
        newly_dropped = len(raw) - len(head) - len(tail)
        marker = f"\n[... {newly_dropped} bytes dropped ...]\n".encode("ascii")
        return bytearray(head + marker + tail)

    def _cap_text(self, text: str) -> str:
        """G2/P28: the character-count analogue of `_cap_buffer`, for the DECODED output text --
        slicing a `str` by character count can never split a codepoint, unlike a byte-offset cut."""
        if len(text) <= self.MAX_RETAINED_CHARS:
            return text
        head = text[:self.RETAINED_HEAD_CHARS]
        tail = text[-self.RETAINED_TAIL_CHARS:]
        dropped = len(text) - len(head) - len(tail)
        return f"{head}\n[... {dropped} chars dropped ...]\n{tail}"

    def _on_timeout(self) -> None:
        self.kill()
        try:
            self._runner(["docker", "exec", self.container, "pkill", "-KILL", "-f", "bash --login"],
                        capture_output=True, text=True, timeout=10)
        except Exception:  # noqa: BLE001 -- best-effort; the Popen kill above is the real backstop
            pass

    def kill(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.kill()
        except Exception:  # noqa: BLE001 -- best-effort
            pass
        self.dead = True

    def close(self) -> None:
        """`exit\n` then wait up to 2s, then kill (never leaves the process running).

        P22: the write itself now goes through the SAME bounded, backgrounded writer as `run()`
        (reproduced: a descendant process still holding the pipe open, e.g. a backgrounded
        `sleep 30 &`, could previously wedge `close()`'s raw `self.proc.stdin.write()` solid,
        requiring the test process itself to be killed). `close()` never waits on the write
        directly -- it polls briefly, then proceeds to `wait()`/`kill()` regardless.

        7th cold review round 7 P41 (MEDIUM), reproduced: after a background writer filled the
        queue, `close()` itself returned in ~0.3s (bounded, as designed) -- but after killing every
        process, the READER THREAD remained alive, still parked in a blocking `Queue.put()` with
        256 queued chunks nobody would ever drain; `Thread.join(timeout=...)` only WAITS, it cannot
        cancel a thread stuck in a blocking call. Fixed: `self._cancel` is set FIRST (the reader's
        own put-retry loop notices it and returns), the stdout PIPE HANDLE is explicitly closed
        (unblocks a reader stuck in `.read()` instead of `.put()`, by making that read raise), and
        then both threads are joined with a bounded timeout -- this method now actually PROVES
        nothing is left running, not just that close() itself returned quickly."""
        if self.proc is None:
            return
        self._cancel.set()
        writer_box = None
        try:
            writer_box = self._start_writer(b"exit\n")
        except Exception:  # noqa: BLE001
            pass
        if writer_box is not None:
            write_deadline = time.monotonic() + 0.5
            while not writer_box["done"] and time.monotonic() < write_deadline:
                time.sleep(0.02)
            writer_box["abort"] = True
        try:
            self.proc.wait(timeout=2.0)
        except Exception:  # noqa: BLE001
            self.kill()
        self.dead = True
        try:
            if self.proc.stdout is not None:
                self.proc.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)
        if writer_box is not None and writer_box.get("thread") is not None:
            writer_box["thread"].join(timeout=0.5)


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


# 5th cold review P9(a) + 6th cold review round 6 P23/addendum C + 7th cold review round 7 P37:
# a docker EXECUTION failure (the daemon unreachable, the container gone, docker itself
# misconfigured) must never be scored as the checker's legitimate nonzero verdict -- but
# classification is now by EXPLICIT EVIDENCE for EVERY nonzero/timeout result, never an exit-code
# BAND:
#   - P37 (HIGH), reproduced end-to-end: exit 1 + "container ... is not running" in stderr still
#     scored `failed_tests` (the OLD {125,126,127}-band gate never even looked at exit 1); exit
#     127 + an APPLICATION's own "application is not running" stderr text was EXCLUDED as infra
#     (the OLD stderr substring list -- "is not running"/"No such container" -- collides with
#     ordinary application error text, which has nothing to do with docker). The test this
#     superseded (formerly at this file's ~line 242) directly asserted the first wrong behavior.
#   - Minimal fix per the coordinator: run a live HEALTH PROBE (`docker exec <c> true`, 3s) after
#     ANY nonzero/timeout checker result, REGARDLESS of its own rc or exit code. Health probe OK
#     -> the checker itself produced a real (if failing) verdict -> `failed_tests`, IN the
#     denominator. Health probe ALSO fails (nonzero/timeout), OR the ORIGINAL stderr carries an
#     unambiguous DOCKER-CLI ERROR PREFIX (never ordinary free-form application text) -> infra,
#     `setup_error` with `infra_evidence` attached.
_DOCKER_CLI_STDERR_PREFIXES = (
    "Error response from daemon",
    "Cannot connect to the Docker daemon",
    "docker: Error",
    "OCI runtime",
)


def _docker_stderr_is_cli_prefixed(stderr) -> bool:
    """P37: ONLY docker's OWN CLI error prefixes -- never generic substrings like "is not
    running"/"No such container" that an APPLICATION's own stderr can just as easily contain,
    with nothing to do with docker at all."""
    s = stderr or ""
    return any(s.startswith(p) or f"\n{p}" in s for p in _DOCKER_CLI_STDERR_PREFIXES)


def _docker_health_check(container: str, runner=subprocess.run, timeout: float = 3.0) -> bool:
    """P23/addendum C/P37: `docker exec <container> true` -- a cheap, fast probe proving docker
    (not the checker script) is still responsive. True = healthy. 3s timeout per P37 (a health
    probe that can't answer in 3s is itself evidence of an unresponsive daemon/container)."""
    res = docker_exec(container, ("bash", "true"), timeout, runner)
    return (not res.get("timed_out")) and res.get("exit_code") == 0


def _classify_check_result(container: str, res: dict, runner) -> dict | None:
    """P37: the EXPLICIT-EVIDENCE classifier for ONE nonzero/timeout checker result. Returns
    `None` (a legitimate model/checker failure, stays `failed_tests`) or an `infra_evidence` dict
    (`{"message", "exit_code", "stderr", "timed_out", "health_probe_ok"}`)."""
    if _docker_stderr_is_cli_prefixed(res.get("stderr")):
        return {"message": f"docker CLI error prefix in stderr (exit={res.get('exit_code')}, "
                          f"timed_out={res.get('timed_out')}): {(res.get('stderr') or '')[:200]}",
               "exit_code": res.get("exit_code"), "stderr": (res.get("stderr") or "")[:200],
               "timed_out": bool(res.get("timed_out")), "health_probe_ok": None}
    healthy = _docker_health_check(container, runner)
    if healthy:
        # the checker ran to completion (or to ITS OWN timeout) under a PROVEN-responsive
        # docker/container -- whatever it reported is the model's own doing.
        return None
    return {"message": f"docker health probe failed after checker result (exit={res.get('exit_code')}, "
                      f"timed_out={res.get('timed_out')}): {(res.get('stderr') or '')[:200]}",
           "exit_code": res.get("exit_code"), "stderr": (res.get("stderr") or "")[:200],
           "timed_out": bool(res.get("timed_out")), "health_probe_ok": False}


def run_check_chain(container: str, check_list: list, example, answer, runner=subprocess.run,
                    timeout: float = DEFAULT_EXEC_TIMEOUT_S) -> tuple:
    """Mirrors task.py `_evaluate_by_check_scripts` EXACTLY, including `params = [str(answer)]`
    (cold-review F14): a `finish_action` with no `thought` submits Python `None`, and `str(None)`
    is the literal string `"None"` sent as argv[1] -- upstream has no special-case for "no answer
    given", and neither does this. Each script runs with the accumulated params and its stdout is
    appended for the next; a None entry runs `example` instead (the "gold" position); any
    timeout/nonzero exit fails the whole chain.

    Returns `(passed: bool, gold_live: str|None, infra_evidence: dict|None)`. `gold_live` is the
    stdout of the FIRST null ("gold slot") position actually executed in THIS live grading run
    (R5/AC5: the chain already runs it; capture it rather than trusting the D2-prepare-time value
    stayed valid). `None` when the check list has no gold slot at all. `infra_evidence` (P23/P37)
    is set only when a live health probe (or an unambiguous docker CLI stderr prefix) proves the
    failure was docker's, not the checker's -- the caller must turn that into a `setup_error` row
    with the evidence attached, never a plain `failed_tests`."""
    params = [str(answer)]
    gold_live = None
    for entry in check_list:
        script = entry if entry is not None else example
        if script is None:
            return False, gold_live, None
        res = docker_exec(container, script, timeout, runner, extra_params=params)
        if entry is None and gold_live is None:
            gold_live = res["stdout"]
        if res.get("timed_out") or res.get("exit_code") != 0:
            infra_evidence = _classify_check_result(container, res, runner)
            return False, gold_live, infra_evidence
        params.append(res["stdout"])
    return True, gold_live, None


def _container_setup(image: str, init_scripts: list, start, container: str,
                     runner=subprocess.run, timeout: float = DEFAULT_EXEC_TIMEOUT_S) -> dict:
    """Fresh container: create + init + start. Returns
    {"ok", "failed_step": "create"|"init"|"start"|None, "exit_code", "timed_out", "stderr"}."""
    remove_container(container, runner)
    try:
        create_container(f"local-os/{image}", container, runner)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "failed_step": "create", "exit_code": None, "timed_out": False,
               "stderr": str(e)[:300]}
    for s in init_scripts:
        res = docker_exec(container, s, timeout, runner)
        if res["timed_out"] or res["exit_code"] != 0:
            return {"ok": False, "failed_step": "init", "exit_code": res["exit_code"],
                   "timed_out": res["timed_out"], "stderr": (res["stderr"] or "")[:300]}
    if start:
        res = docker_exec(container, start, timeout, runner)
        if res["timed_out"] or res["exit_code"] != 0:
            return {"ok": False, "failed_step": "start", "exit_code": res["exit_code"],
                   "timed_out": res["timed_out"], "stderr": (res["stderr"] or "")[:300]}
    return {"ok": True, "failed_step": None, "exit_code": 0, "timed_out": False, "stderr": ""}


def _run_example_in_container(container: str, example, runner, timeout: float, placeholder: str) -> dict:
    if example is None:
        return {"ok": False, "exit_code": None, "timed_out": False, "stdout": "", "stderr": ""}
    res = docker_exec(container, example, timeout, runner, extra_params=[placeholder])
    return {"ok": (not res["timed_out"] and res["exit_code"] == 0), "exit_code": res["exit_code"],
           "timed_out": res["timed_out"], "stdout": res["stdout"], "stderr": res["stderr"] or ""}


def run_reference(image: str, init_scripts: list, start, example, container: str,
                  runner=subprocess.run, timeout: float = DEFAULT_EXEC_TIMEOUT_S,
                  answer_placeholder: str = ANSWER_PLACEHOLDER_PRIMARY) -> tuple:
    """NO-gold-slot path: a FRESH container, init + start, then `example` once. Returns
    `(exit_ok: bool, stdout: str|None)`."""
    try:
        setup = _container_setup(image, init_scripts, start, container, runner, timeout)
        if not setup["ok"]:
            return False, None
        r = _run_example_in_container(container, example, runner, timeout, answer_placeholder)
        return (True, r["stdout"]) if r["ok"] else (False, None)
    finally:
        # 6th cold review round 6 P26: the SAME fail-closed verified-removal gate as run_task's
        # final cleanup applies here too -- prepare must not silently proceed to the next task on
        # a box that may be accumulating live containers.
        if not remove_container(container, runner, verify=True):
            raise ContainerCleanupError(
                f"container {container} was not verifiably removed during D2 prepare")


def run_reference_pair_in_container(image: str, init_scripts: list, start, example: object,
                                    container: str, runner=subprocess.run,
                                    timeout: float = DEFAULT_EXEC_TIMEOUT_S) -> dict:
    """D2 rule v2 (operator 2026-09-30): gold-slot tasks are graded by running `example` TWICE
    inside the SAME already-set-up container (one init+start), mirroring upstream -- task.py grades
    the check chain, including any null-slot `example`, inside the task's OWN live container, never
    a fresh one per probe. This is why a randomized init ($RANDOM/shuf) no longer produces a false
    `gold_mismatch`: the environment is fixed once per probe, same as a real grading run.

    Returns a full diagnostic:
      {"outcome": "ok"|"no_gold"|"gold_mismatch", "gold": str|None,
       "failed_step": "create"|"init"|"start"|"example_missing"|"example"|None,
       "exit_codes": [c1, c2], "stdout": [s1[:200], s2[:200]], "stderr": [e1[:300], e2[:300]],
       "timed_out": bool}
    """
    try:
        setup = _container_setup(image, init_scripts, start, container, runner, timeout)
        if not setup["ok"]:
            return {"outcome": "no_gold", "gold": None, "failed_step": setup["failed_step"],
                   "exit_codes": [setup["exit_code"], None], "stdout": ["", ""],
                   "stderr": [setup["stderr"], ""], "timed_out": setup["timed_out"]}
        if example is None:
            return {"outcome": "no_gold", "gold": None, "failed_step": "example_missing",
                   "exit_codes": [None, None], "stdout": ["", ""], "stderr": ["", ""],
                   "timed_out": False}
        r1 = _run_example_in_container(container, example, runner, timeout, ANSWER_PLACEHOLDER_PRIMARY)
        r2 = _run_example_in_container(container, example, runner, timeout, ANSWER_PLACEHOLDER_PROBE)
        diag = {"exit_codes": [r1["exit_code"], r2["exit_code"]],
               "stdout": [r1["stdout"][:200], r2["stdout"][:200]],
               "stderr": [r1["stderr"][:300], r2["stderr"][:300]],
               "timed_out": r1["timed_out"] or r2["timed_out"]}
        if not r1["ok"] or not r2["ok"] or not r1["stdout"] or not r2["stdout"]:
            return {"outcome": "no_gold", "gold": None, "failed_step": "example", **diag}
        if r1["stdout"] != r2["stdout"]:
            return {"outcome": "gold_mismatch", "gold": None, "failed_step": None, **diag}
        return {"outcome": "ok", "gold": r1["stdout"], "failed_step": None, **diag}
    finally:
        # P26: same fail-closed gate as run_reference / run_task's final cleanup.
        if not remove_container(container, runner, verify=True):
            raise ContainerCleanupError(
                f"container {container} was not verifiably removed during D2 prepare")


def _check_list_has_gold_slot(check_list) -> bool:
    return bool(check_list) and any(entry is None for entry in check_list)


def prepare_exclusions(tasks: list, scripts_root, runner=subprocess.run,
                       timeout: float = DEFAULT_EXEC_TIMEOUT_S,
                       prefix: str = PREPARE_CONTAINER_PREFIX, manual: dict | None = None) -> tuple:
    """D2 (AC2 + cold-review N3/N4/R10/D2-v2/P10), no model calls. Returns
    (golds: {id: str}, exclusions: [{id, reason, ...diagnostic...}]).

    `match` tasks are checked FIRST and are never excluded or examined by anything below -- 5th
    cold review P10: a manual exclusion must NOT pre-empt the match exemption. `manual` (id ->
    reason) is checked next and short-circuits: a hand-curated exclusion is never re-probed.

    A check list's position-0..n entries can include a `None` ("gold slot": the live grading chain
    runs `example` there, fed the actual submitted answer). Only THOSE tasks are probed, via
    `run_reference_pair_in_container` (D2 rule v2: ONE fresh container, `example` run twice inside
    it with placeholders `"1"`/`"2"`): disagreement is `gold_mismatch` (a genuinely nondeterministic
    reference OR an answer-reading one -- EXPECTED for randomized-init tasks, not necessarily an
    error); empty/failed/timed-out is `no_gold`, with the failing step recorded.

    A check list with NO gold slot (every position a literal checker script) never touches a gold
    value at grading time, so the two-placeholder probe would prove nothing; it only needs its
    reference solution to run once, exit 0 (`reference_failed` otherwise); no gold is ever cached
    for these."""
    manual = manual or {}
    golds, exclusions = {}, []
    for task in tasks:
        cfg = task_config(task, scripts_root)
        if cfg["match"] is not None:
            continue
        if task["id"] in manual:
            exclusions.append({"id": task["id"], "reason": "manual", "note": manual[task["id"]]})
            continue
        name = container_name(prefix, task["id"])
        if _check_list_has_gold_slot(cfg["check"]):
            result = run_reference_pair_in_container(cfg["image"], cfg["init_scripts"], cfg["start"],
                                                      cfg["example"], name, runner, timeout)
            if result["outcome"] == "ok":
                golds[task["id"]] = result["gold"]
            else:
                exclusions.append({"id": task["id"], "reason": result["outcome"],
                                   "failed_step": result["failed_step"],
                                   "exit_codes": result["exit_codes"], "stdout": result["stdout"],
                                   "stderr": result["stderr"], "timed_out": result["timed_out"]})
        else:
            ok, _stdout = run_reference(cfg["image"], cfg["init_scripts"], cfg["start"],
                                        cfg["example"], name, runner, timeout,
                                        ANSWER_PLACEHOLDER_PRIMARY)
            if not ok:
                exclusions.append({"id": task["id"], "reason": "reference_failed"})
    return golds, exclusions


# --------------------------------------------------------------------------- dual-submit driver
def _parse_args_or_error(raw) -> tuple:
    """6th cold review round 6 P27: mirrors `agent_loop._parse_args_with_error` -- malformed
    arguments are NEVER silently turned into `{}`.

    7th cold review round 7 addendum R5: the fed-back text is the BARE `str(e)`, no
    "Error parsing arguments: " prefix -- see `agent_loop._parse_args_with_error`'s docstring;
    these two functions must stay byte-for-byte identical in their error TEXT, since
    `DualSubmitDriver.complete()`'s `turn_entry["tool_result"]` (P43a) must match exactly what
    `agent_loop.run_agent`'s OWN re-parse of the same raw string feeds back to the model. Returns
    (args: dict, error: str|None)."""
    if isinstance(raw, dict):
        return raw, None
    try:
        v = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        return {}, str(e)
    if not isinstance(v, dict):
        return {}, f"expected a JSON object, got {type(v).__name__}"
    return v, None


def _extract_tool_arg(args: dict, expected_key: str):
    """7th cold review round 7 addendum R2: mirrors upstream AgentBench task.py's own
    `_extract_function`, which does `list(json.loads(args).values())[0]` -- upstream ignores
    argument KEY NAMES entirely and takes the first value by POSITION. Our tools each declare a
    single named JSON-schema property (`script`, `thought`, `answer`), so: prefer the EXPECTED
    key when present (handles extra hallucinated keys alongside the correct one), falling back to
    the first value in the dict when it is absent (handles a plausible-but-wrong key name, e.g. a
    model emitting `command` instead of `script` for `bash_action` -- common enough across model
    families that dropping the argument entirely, as the old `args.get(expected_key, "")` did,
    silently turned a real action into a no-op)."""
    if expected_key in args:
        return args[expected_key]
    if args:
        return next(iter(args.values()))
    return None


class DualSubmitDriver:
    """Wraps a Driver so BOTH `answer_action` and `finish_action` end an `agent_loop.run_agent`
    episode (see module docstring). Also records per-turn telemetry (`per_turn`) since
    `run_agent`'s return value only carries AGGREGATE counters, and the row schema wants it per
    turn (finish_reason for the `tool_calls`-vs-`stop` convergence rule, and a per-turn decode_tps
    for timeout self-derivation -- cold-review F2/F8)."""

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
        tm = out.get("raw_timings") or {}
        ct = out.get("completion_tokens")
        pred_ms = tm.get("predicted_ms")
        decode_tps = (ct / (pred_ms / 1000.0)) if (pred_ms and ct) else out.get("decode_tps")

        # Transcript turn entry (quality-inspection feature): everything available from the raw
        # response goes in now; `tool_result`/`raw_output_len` are patched in by build_tools's
        # `_bash` (the tool's ACTUAL execution happens after this call returns, inside
        # agent_loop), and a dispatched submit's tool_result is known to be "submitted" here
        # directly since run_agent never calls the submit Tool's `fn` at all.
        turn_entry = {"turn": len(self.per_turn) + 1, "completion_tokens": ct,
                     "prompt_tokens": out.get("prompt_tokens"), "finish_reason": out.get("finish_reason"),
                     "decode_tps": decode_tps, "assistant_content": out.get("content") or "",
                     "wall_s": out.get("wall_s"), "tool_call": None, "tool_result": None,
                     "raw_output_len": None}
        reasoning = out.get("reasoning")
        if reasoning:
            turn_entry["reasoning_content"] = reasoning

        raw_tcs = out.get("tool_calls") or []
        new_tcs = []
        for i, tc in enumerate(raw_tcs):
            fn = dict(tc.get("function") or {})
            name = fn.get("name")
            args, parse_error = _parse_args_or_error(fn.get("arguments"))
            if i == 0:
                turn_entry["tool_call"] = {"name": name, "args": args}
                if parse_error is not None:
                    turn_entry["tool_call"]["parse_error"] = parse_error
                    # P43(a): record the ACTUAL fed-back text in tool_result too -- this mirrors
                    # agent_loop.py's OWN `_parse_args_with_error` byte-for-byte (same message
                    # format), which is what the model genuinely receives as the tool response.
                    turn_entry["tool_result"] = parse_error
            # P27: a MALFORMED finish_action/answer_action is NEVER a submission -- leave `fn`
            # completely UNCHANGED (do not rename, do not reserialize into fresh always-valid
            # JSON) so agent_loop.run_agent's OWN fresh parse of the SAME raw argument string
            # fails identically and feeds back upstream's corrective parse-error text, rather than
            # us "fixing" a garbled call into a clean `{"answer": null}` that would then parse
            # successfully and silently credit the episode.
            if parse_error is None and name == "finish_action":
                fn["name"] = self.SUBMIT_TOOL
                # R2: _extract_tool_arg, not a bare args.get("thought") -- a model that emits
                # e.g. {"reason": "..."} instead of {"thought": "..."} must not have its
                # submission silently become {"answer": None}.
                fn["arguments"] = json.dumps({"answer": _extract_tool_arg(args, "thought")})
                # cold-review N10: run_agent only ever DISPATCHES tool_calls[0]
                # (single_tool_call_per_turn=True) -- a submit riding in position 1+ never actually
                # runs, so it must not be recorded as having submitted anything.
                if i == 0:
                    self.submitted_via = "finish"
                    turn_entry["tool_result"] = "submitted"
            elif parse_error is None and name == self.SUBMIT_TOOL:
                # R2: normalize answer_action's args to the canonical {"answer": ...} key too, by
                # the SAME rule -- agent_loop.run_agent re-parses THIS rewritten arguments string,
                # so `submitted["answer"]` must never silently come back None because the model
                # used a plausible-but-wrong key (e.g. "response" instead of "answer").
                fn["arguments"] = json.dumps({"answer": _extract_tool_arg(args, "answer")})
                if i == 0:
                    self.submitted_via = "answer"
                    turn_entry["tool_result"] = "submitted"
            new_tc = dict(tc)
            new_tc["function"] = fn
            new_tcs.append(new_tc)

        self.per_turn.append(turn_entry)
        out = dict(out)
        out["tool_calls"] = new_tcs
        return out


def build_tools(shell: PersistentShell, timeout: float = DEFAULT_EXEC_TIMEOUT_S,
                counters: dict | None = None, exec_timeout_flag: dict | None = None,
                shell_died_flag: dict | None = None, transcript_turns: list | None = None) -> list:
    """The three upstream tools. `bash_action` runs through the task's `PersistentShell` (NOT a
    fresh `docker exec`, see module docstring); the other two are no-ops in dispatch terms --
    `DualSubmitDriver` renames every terminating call to the literal submit_tool name before
    `run_agent` ever sees it, so these `fn`s are never invoked in practice. They are still
    registered so their schemas reach the model verbatim and so agent_outcomes' arg-schema
    counters have something to check against.

    On a timed-out command: a best-effort kill is issued (see PersistentShell._on_timeout),
    `exec_timeout_flag["hit"]` is set, and `agent_loop.AbortEpisode` ends the episode immediately
    (upstream ends the task on a hung command rather than feeding back an error and continuing).
    On shell death (N9, e.g. the model ran `exit`) via a `bash_action`: `shell_died_flag["hit"]` is
    set and the episode ends with a FAILED_TESTS outcome -- a death the MODEL caused is a scored
    fail, in the acc denominator (R2; a death during the `start` script, before any model action,
    is handled separately in `run_task` and stays setup_error)."""
    counters = counters if counters is not None else {}
    counters.setdefault("tool_timeouts", 0)
    exec_timeout_flag = exec_timeout_flag if exec_timeout_flag is not None else {}
    exec_timeout_flag.setdefault("hit", False)
    shell_died_flag = shell_died_flag if shell_died_flag is not None else {}
    shell_died_flag.setdefault("hit", False)

    def _bash(args: dict) -> str:
        # R2: _extract_tool_arg, not a bare args.get("script", "") -- models commonly emit
        # "command" instead of "script"; upstream ignores the key name entirely.
        script = _extract_tool_arg(args, "script") or ""
        res = shell.run(script, timeout_s=timeout)
        if res["shell_died"]:
            shell_died_flag["hit"] = True
            # R2: a shell death triggered by the MODEL'S OWN action (running `exit`, `set -e` then
            # a failing command, ...) is a SCORED FAIL, not an infra failure -- upstream's
            # equivalent is "later reads return empty and the task fails". Only a death during
            # start()/the start script (before any model action; handled separately in run_task,
            # never reaches here) is setup_error.
            msg = "the persistent shell exited (e.g. the command ran `exit`)"
            # P43(a): save the fed-back abort message in the transcript BEFORE raising -- the OLD
            # code raised immediately, leaving tool_result=None/error=None even though the model
            # DID get this text back (agent_loop's `except AbortEpisode` feeds e.message to it).
            if transcript_turns:
                transcript_turns[-1]["tool_result"] = msg
                transcript_turns[-1]["raw_output_len"] = res.get("raw_output_len")
            raise agent_loop.AbortEpisode(AO.FAILED_TESTS, msg)
        if res["timed_out"]:
            counters["tool_timeouts"] += 1
            exec_timeout_flag["hit"] = True
            msg = f"command timed out after {timeout:.0f}s and the shell was killed"
            if transcript_turns:
                transcript_turns[-1]["tool_result"] = msg
                transcript_turns[-1]["raw_output_len"] = res.get("raw_output_len")
            raise agent_loop.AbortEpisode(AO.FAILED_TESTS, msg)
        clipped, _truncated = truncate_output(res["output"])
        wrapped_text = wrap_os_output(clipped)
        if transcript_turns:
            # the turn entry for THIS call was appended by DualSubmitDriver.complete() just
            # before run_agent dispatched us; patch in what only the tool itself knows.
            transcript_turns[-1]["tool_result"] = wrapped_text
            transcript_turns[-1]["raw_output_len"] = res.get("raw_output_len", len(res["output"]))
        return wrapped_text

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


def evaluate_convergence(per_turn: list, thinking_budget, context_limit, max_tokens) -> dict:
    """Cold-review F2: the server returns `finish_reason="tool_calls"` on every tool-calling turn
    (mlx_vlm/server/openai.py), so a convergence rule that only accepts `"stop"` marks EVERY
    multi-turn episode non-converged regardless of quality. A turn is converged iff
    `finish_reason` in {"stop", "tool_calls"} AND its completion_tokens stayed under the RESOLVED
    thinking budget for that turn (prompt_tokens grows turn over turn, so the resolved budget
    shrinks over the episode -- `bench.convergence.resolved_thinking_budget` per turn, falling back
    to the declared budget when context_limit/max_tokens are unknown). Episode `converged` = ALL
    turns converged; `budget_hits` counts turns that hit their own resolved budget.

    6th cold review round 6 P24 (HIGH): the `missing_usage` nonconv_kind (5th cold review P11) is
    REMOVED -- `bench.client.probe` now REFUSES (`MalformedResponseError` -> `TransportFailure`
    escalation, never a scored row) any response missing `usage.completion_tokens`, so a turn
    reaching this function with `completion_tokens is None` cannot happen on a live run any more.
    The `ct is None` branch below stays purely DEFENSIVE (never crash on malformed/historical
    data) -- it does not force episode non-convergence; that invariant is now enforced upstream,
    at the transport boundary, where it belongs."""
    finish_reasons, budget_hits = [], 0
    per_turn_converged = []
    per_turn_resolved_budget = []
    nonconv_kinds = set()
    for t in per_turn:
        fr = t.get("finish_reason")
        finish_reasons.append(fr)
        ct = t.get("completion_tokens")
        budget = thinking_budget
        if context_limit and max_tokens and t.get("prompt_tokens") is not None:
            rb = convergence.resolved_thinking_budget(
                {"thinking_budget": thinking_budget, "prompt_tokens": t.get("prompt_tokens")},
                context_limit=context_limit, max_tokens=max_tokens)
            if rb is not None:
                budget = rb
        per_turn_resolved_budget.append(budget)
        hit_budget = bool(budget is not None and ct is not None and ct >= budget)
        if hit_budget:
            budget_hits += 1
            nonconv_kinds.add("budget_hit")
        ok_finish = fr in ("stop", "tool_calls")
        # 7th cold review round 7 P36: `finish_reason=="length"` IS itself a budget/length
        # exhaustion event (the server hit max_tokens) -- classify it as `budget_hit`, not the
        # generic `bad_finish_reason` bucket, even when the turn's own completion_tokens stayed
        # under the (possibly larger) thinking_budget.
        if fr == "length":
            nonconv_kinds.add("budget_hit")
        elif not ok_finish:
            nonconv_kinds.add("bad_finish_reason")
        per_turn_converged.append(ok_finish and not hit_budget)
    if not per_turn:
        episode_converged = None
    else:
        episode_converged = all(per_turn_converged)
    return {"converged": episode_converged, "per_turn_finish_reasons": finish_reasons,
            "budget_hits": budget_hits, "per_turn_converged": per_turn_converged,
            "per_turn_resolved_budget": per_turn_resolved_budget,
            "nonconv_kinds": sorted(nonconv_kinds) if episode_converged is False else []}


# --------------------------------------------------------------------------- per-task run
def _fail_row(base: dict, outcome: str, t0, clock, **extra) -> dict:
    row = {**base, "passed": False, "outcome": outcome, "turns": 0, "submitted_via": None,
          "answer": None, "gold_prepare": base.get("gold_prepare"), "gold_live": None,
          "per_turn_completion_tokens": [], "completion_tokens_total": 0,
          "per_turn_finish_reasons": [], "converged": None, "per_turn_resolved_budget": [],
          "nonconv_kinds": [],
          "budget_hits": 0, "wall_s": round(clock() - t0, 2), "tool_calls": 0, "tool_timeouts": 0,
          "repeat_calls": 0, "exec_timeout": False, "shell_died": False, "setup_error": True,
          "decode_tps": None, "per_turn_decode_tps": [], "error": None, "_transcript_turns": [],
          "infra_evidence": None}
    row.update(extra)
    return row


def run_task(model: str, task: dict, scripts_root, driver, params: dict, *,
            container_prefix: str = GENERATE_CONTAINER_PREFIX,
            exec_timeout: float = DEFAULT_EXEC_TIMEOUT_S, llm_timeout: float = 3600.0,
            max_turns: int = ROUND_LIMIT, deadline_s=None, context_limit=None, gold_prepare=None,
            runner=subprocess.run, popen=subprocess.Popen, clock=time.perf_counter) -> dict:
    """One task, one container, start to `docker rm -f` (always, via `finally` -- AC9). Raises
    `TransportFailure` (never returns a row) if `driver.complete` itself failed during the agent
    loop (cold-review F1) or `KeyboardInterrupt`; any other exception (docker/setup/evaluate
    infra failure) is converted to a `setup_error: true` row so the batch never crashes.
    `gold_prepare` (from the D2 exclusions artifact) is populated onto every row verbatim (AC5);
    `gold_live` (R5) is the gold-slot stdout actually observed when THIS run's check chain graded
    the answer -- None for match tasks, tasks with no gold slot, or an episode that never
    submitted."""
    cfg = task_config(task, scripts_root)
    name = container_name(container_prefix, task["id"])
    remove_container(name, runner)   # idempotent pre-clean (a prior interrupted run may have left one)
    t0 = clock()
    base = {"id": task["id"], "group": task.get("group"), "labels": task.get("labels") or [],
            "image": cfg["image"], "gold_prepare": gold_prepare}
    shell = None
    row = None
    wrapped = None   # P43(a): referenced in the final except-all, so a completed episode's
                     # per_turn transcript survives an UNEXPECTED exception during grading too
    try:
        try:
            create_container(f"local-os/{cfg['image']}", name, runner)
        except Exception as e:  # noqa: BLE001
            row = _fail_row(base, AO.SERVER_ERROR, t0, clock,
                             error=f"container create: {type(e).__name__}: {e}")
            return row

        for s in cfg["init_scripts"]:
            res = docker_exec(name, s, exec_timeout, runner)
            if res["timed_out"] or res["exit_code"] != 0:
                row = _fail_row(base, AO.SERVER_ERROR, t0, clock,
                                 error=f"init script failed (timed_out={res['timed_out']}, "
                                       f"exit={res['exit_code']}): {res['stderr'][:200]}")
                return row

        shell = PersistentShell(name, popen=popen, runner=runner)
        handshake = shell.start()
        # P9(b): validate the handshake BEFORE the first model call -- a shell that never came up
        # cleanly must never reach the agent loop.
        if handshake["shell_died"] or handshake["timed_out"] or handshake["exit_code"] != 0:
            row = _fail_row(base, AO.SERVER_ERROR, t0, clock,
                             shell_died=handshake["shell_died"],
                             error=f"shell handshake failed (shell_died={handshake['shell_died']}, "
                                   f"timed_out={handshake['timed_out']}, exit={handshake['exit_code']})")
            return row
        if cfg["start"]:
            lang, code = cfg["start"]
            if lang != "bash":
                row = _fail_row(base, AO.SERVER_ERROR, t0, clock,
                                 error=f"unsupported start script language {lang!r}")
                return row
            res = shell.run(code, timeout_s=exec_timeout)
            if res["shell_died"] or res["timed_out"] or res["exit_code"] != 0:
                row = _fail_row(base, AO.SERVER_ERROR, t0, clock,
                                 shell_died=res["shell_died"],
                                 error=f"start script failed (shell_died={res['shell_died']}, "
                                       f"timed_out={res['timed_out']}, exit={res['exit_code']})")
                return row

        tool_counters = {"tool_timeouts": 0}
        exec_timeout_flag = {"hit": False}
        shell_died_flag = {"hit": False}
        wrapped = DualSubmitDriver(driver, timeout=llm_timeout)
        tools = build_tools(shell, exec_timeout, tool_counters, exec_timeout_flag, shell_died_flag,
                            transcript_turns=wrapped.per_turn)
        task_text = TASK_TEMPLATE.format(description=task.get("description", ""))
        result = agent_loop.run_agent(
            wrapped, model, SYSTEM_PROMPT, task_text, tools, params, max_turns=max_turns,
            submit_tool=DualSubmitDriver.SUBMIT_TOOL, deadline_s=deadline_s,
            loop_guard=AO.LoopGuard(max_identical=0, max_unknown=0),   # F5(d): the round cap is the bound
            clock=clock, no_tool_call_reprompt=NO_TOOL_CALL_REPROMPT,
            single_tool_call_per_turn=True)

        if result.get("outcome") == AO.SERVER_ERROR and result.get("error"):
            raise TransportFailure(f"task {task['id']}: {result['error']}")

        gold_live_box = {"value": None}
        infra_error_box = {"value": None}

        def _evaluate(answer):
            if cfg["match"] is not None:
                return evaluate_match(answer, cfg["match"])
            passed, gold_live, infra_error = run_check_chain(name, cfg["check"], cfg["example"],
                                                             answer, runner, exec_timeout)
            gold_live_box["value"] = gold_live
            infra_error_box["value"] = infra_error
            return passed

        # AbortEpisode already set result["outcome"] to FAILED_TESTS (exec timeout, model-caused
        # shell death) or SERVER_ERROR (start-caused shell death); finalize_outcome passes any
        # non-SOLVED outcome through unchanged, so no manual override is needed here -- only the
        # row-level setup_error/shell_died flags are.
        outcome, passed, answer = finalize_outcome(result, _evaluate)

        counters = result.get("counters") or {}
        conv = evaluate_convergence(wrapped.per_turn, params.get("thinking_budget"), context_limit,
                                    params.get("max_tokens"))
        dtps = [t.get("decode_tps") for t in wrapped.per_turn if isinstance(t.get("decode_tps"), (int, float))]
        common = {"turns": result.get("turns", 0), "submitted_via": wrapped.submitted_via,
                 "answer": answer, "gold_live": gold_live_box["value"],
                 "per_turn_completion_tokens": [t.get("completion_tokens") for t in wrapped.per_turn],
                 "completion_tokens_total": counters.get("completion_tokens", 0),
                 "per_turn_finish_reasons": conv["per_turn_finish_reasons"],
                 "converged": conv["converged"], "budget_hits": conv["budget_hits"],
                 "per_turn_resolved_budget": conv["per_turn_resolved_budget"],
                 "nonconv_kinds": conv["nonconv_kinds"],
                 "wall_s": counters.get("wall_s", round(clock() - t0, 2)),
                 "tool_calls": counters.get("tool_calls", 0),
                 "tool_timeouts": tool_counters["tool_timeouts"],
                 "repeat_calls": counters.get("repeat_identical_calls", 0),
                 "exec_timeout": exec_timeout_flag["hit"], "shell_died": shell_died_flag["hit"],
                 "decode_tps": round(statistics.mean(dtps), 2) if dtps else None,
                 "per_turn_decode_tps": [t.get("decode_tps") for t in wrapped.per_turn],
                 "_transcript_turns": wrapped.per_turn}

        # P9(a)/P23: a docker EXECUTION failure during grading (explicit evidence only -- see
        # run_check_chain) is an infra failure, never a graded model loss -- override whatever
        # finalize_outcome computed. Addendum I: the row still carries the episode's ACTUAL
        # completed turns/transcript/tokens (`common`, built above) -- a grading-time infra
        # failure must not reset an already-executed episode back to zero.
        ie = infra_error_box["value"]
        if ie is not None:
            row = {**base, **common, "passed": False, "outcome": AO.SERVER_ERROR,
                  "setup_error": True, "error": ie["message"], "infra_evidence": ie}
            return row

        row = {**base, **common, "passed": passed, "outcome": outcome,
              # R2: by this point we are PAST the start-phase checks (which already returned
              # early via _fail_row, setup_error=True, for a start-caused death) -- any
              # shell_died here came from a bash_action, i.e. the model's own doing, and is
              # IN the acc denominator (outcome is already FAILED_TESTS via AbortEpisode above).
              "setup_error": False, "error": result.get("error"), "infra_evidence": None}
        return row
    except TransportFailure:
        raise
    except KeyboardInterrupt:
        raise
    except Exception as e:  # noqa: BLE001 -- infra/setup/evaluate failure; never crash the batch
        # 7th cold review round 7 P43(a): an UNEXPECTED exception during GRADING (e.g. a bug in
        # _evaluate, after the agent loop already completed some turns) must not silently reset
        # an already-executed episode's transcript to empty -- preserve whatever turns the model
        # actually produced.
        extra_turns = wrapped.per_turn if wrapped is not None else []
        row = _fail_row(base, AO.SERVER_ERROR, t0, clock, error=f"{type(e).__name__}: {e}",
                        _transcript_turns=extra_turns)
        return row
    finally:
        if shell is not None:
            shell.close()
        # P16: verify removal; the CALLER (after appending this row) decides whether
        # to stop the run on an unverified cleanup -- raising HERE would override the
        # function's return value and the row would never reach the caller at all.
        verified = remove_container(name, runner, verify=True)
        if row is not None:
            row["container_removed_verified"] = verified
            # 6th cold review round 6 P32: wall_total_s is the FULL task cost -- container
            # create -> verified removal -- not just the agent loop's own wall_s. `t0` is set
            # right before create_container, so this finally block (which runs after everything,
            # including this verified-removal call) is the correct measurement point.
            row["wall_total_s"] = round(clock() - t0, 2)
