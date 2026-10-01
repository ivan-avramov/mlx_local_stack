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


def write_exclusions_artifact(path, *, corpus_sha256: str, image_ids: dict, golds: dict,
                              exclusions: list, complete: bool,
                              manual_exclusions_sha256: str | None = None) -> dict:
    doc = {"corpus_sha256": corpus_sha256, "image_ids": image_ids, "golds": golds,
          "exclusions": exclusions, "complete": complete, "generated_at": int(time.time()),
          "manual_exclusions_sha256": manual_exclusions_sha256}
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
                                 manual_exclusions_sha256: str | None = None):
    """None if `doc` is usable for a generate run against the CURRENT corpus + images + manual
    exclusions file; else a human-readable refusal reason."""
    if doc is None:
        return "no exclusions artifact -- run --prepare first"
    if not doc.get("complete"):
        return ("exclusions artifact has complete=false (produced with --limit, or an earlier "
               "--prepare was interrupted) -- rerun --prepare over the WHOLE corpus")
    if doc.get("corpus_sha256") != corpus_sha256:
        return "corpus changed since --prepare (sha256 mismatch) -- rerun --prepare"
    if doc.get("image_ids") != image_ids:
        return "local-os image ids changed since --prepare -- rerun --prepare"
    if doc.get("manual_exclusions_sha256") != manual_exclusions_sha256:
        return "manual exclusions file changed since --prepare -- rerun --prepare"
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
    left it behind). Returns the names removed. Best-effort: never raises. `prefix` must not be a
    PREFIX of another live prefix (cold-review F16) -- callers use the distinct
    GENERATE_/PREPARE_CONTAINER_PREFIX constants, never a shared stem."""
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
    """`-w /root --memory 1g --memory-swap 1g --cpus 2` mirror upstream's
    `environment.py:create_docker_container` (WorkingDir=/root, Memory=1GiB, MemorySwap=Memory i.e.
    swap disabled, NanoCpus=2e9 i.e. 2 vCPUs)."""
    proc = runner(["docker", "run", "-d", "--rm=false", "--name", name, "-w", "/root",
                  "--memory", "1g", "--memory-swap", "1g", "--cpus", "2",
                  image, "sleep", "infinity"],
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
    Exit code 137 (SIGKILL) is ALSO treated as `timed_out=True` defensively, in case a stray
    external kill (ours or otherwise) still let the sentinel through. A command that reads stdin
    (e.g. a bare `read` with no input piped to it) will itself hang until this timeout fires, same
    as upstream's session-based execution -- there is no attempt to detect or special-case that.

    SHELL DEATH (N9). Upstream: `exit` ends the session. If the shell process exits (EOF on
    stdout, or a `BrokenPipeError` writing to a dead stdin), `run()` returns `shell_died=True`
    immediately rather than hanging for the full timeout.
    """

    def __init__(self, container: str, popen=subprocess.Popen, runner=subprocess.run,
                read_chunk: int = 65536):
        self.container = container
        self._popen = popen
        self._runner = runner
        self._read_chunk = read_chunk
        self.proc = None
        self._q: "queue.Queue" = queue.Queue()
        self.dead = False
        self._carry = b""   # unexpected leftover bytes past a previous round's sentinel (see above)

    def start(self) -> None:
        self.proc = self._popen(
            ["docker", "exec", "-i", self.container, "/bin/bash", "--login"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
        t = threading.Thread(target=self._reader_loop, daemon=True)
        t.start()
        # N8: a login shell sources profile scripts that can print banners/MOTD/warnings before
        # anything we asked for. One no-op sentinel round, with everything read before it discarded.
        self.run("true", timeout_s=10.0)

    def _reader_loop(self) -> None:
        try:
            while True:
                chunk = self.proc.stdout.read(self._read_chunk)
                if not chunk:
                    self._q.put(None)
                    return
                self._q.put(chunk)
        except (ValueError, OSError):
            self._q.put(None)

    def run(self, command: str, timeout_s: float = DEFAULT_EXEC_TIMEOUT_S) -> dict:
        """Returns {output, exit_code, timed_out, shell_died}."""
        if self.proc is None:
            raise RuntimeError("PersistentShell.run() called before start()")
        if self.dead or self.proc.poll() is not None:
            self.dead = True
            return {"output": "", "exit_code": None, "timed_out": False, "shell_died": True}

        sentinel = f"__M54_SENTINEL_{uuid.uuid4().hex}__"
        full = f"{command}\nprintf '\\n%s%d\\n' {sentinel} $?\n"
        try:
            self.proc.stdin.write(full.encode("utf-8"))
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            self.dead = True
            return {"output": "", "exit_code": None, "timed_out": False, "shell_died": True}

        marker = ("\n" + sentinel).encode("ascii")
        raw = bytearray(self._carry)
        self._carry = b""
        search_from = 0
        start_t = time.monotonic()
        while True:
            idx = raw.find(marker, max(0, search_from - len(marker)))
            if idx != -1:
                m = re.match(rb"(\d+)\n", bytes(raw[idx + len(marker):]))
                if m:
                    exit_code = int(m.group(1))
                    timed_out = exit_code == 137     # SIGKILL -- defensive (N5)
                    output = bytes(raw[:idx]).decode("utf-8", errors="replace")
                    consumed_end = idx + len(marker) + m.end()
                    leftover = bytes(raw[consumed_end:])
                    if leftover:
                        print(f"[PersistentShell] WARNING: {len(leftover)} unexpected byte(s) past "
                             "the sentinel; carrying to the next run() call", file=sys.stderr)
                    self._carry = leftover
                    return {"output": output, "exit_code": exit_code, "timed_out": timed_out,
                           "shell_died": False}
                # digits present but not yet newline-terminated -- re-check from the SAME offset
                # once more data arrives (R4: never guess a partial exit code).
                search_from = idx
            else:
                search_from = len(raw)
            remaining = timeout_s - (time.monotonic() - start_t)
            if remaining <= 0:
                self._on_timeout()
                return {"output": raw.decode("utf-8", errors="replace"), "exit_code": None,
                       "timed_out": True, "shell_died": False}
            try:
                chunk = self._q.get(timeout=min(remaining, 0.1))
            except queue.Empty:
                continue
            if chunk is None:   # EOF -- the shell process exited (e.g. the command ran `exit`)
                self.dead = True
                return {"output": raw.decode("utf-8", errors="replace"), "exit_code": None,
                       "timed_out": False, "shell_died": True}
            raw += chunk

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
        """`exit\\n` then wait up to 2s, then kill (never leaves the process running)."""
        if self.proc is None:
            return
        try:
            self.proc.stdin.write(b"exit\n")
            self.proc.stdin.flush()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=2.0)
        except Exception:  # noqa: BLE001
            self.kill()


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
                    timeout: float = DEFAULT_EXEC_TIMEOUT_S) -> tuple:
    """Mirrors task.py `_evaluate_by_check_scripts` EXACTLY, including `params = [str(answer)]`
    (cold-review F14): a `finish_action` with no `thought` submits Python `None`, and `str(None)`
    is the literal string `"None"` sent as argv[1] -- upstream has no special-case for "no answer
    given", and neither does this. Each script runs with the accumulated params and its stdout is
    appended for the next; a None entry runs `example` instead (the "gold" position); any
    timeout/nonzero exit fails the whole chain.

    Returns `(passed: bool, gold_live: str|None)` -- `gold_live` is the stdout of the FIRST null
    ("gold slot") position actually executed in THIS live grading run (R5/AC5: the chain already
    runs it; capture it rather than trusting the D2-prepare-time value stayed valid). `None` when
    the check list has no gold slot at all."""
    params = [str(answer)]
    gold_live = None
    for entry in check_list:
        script = entry if entry is not None else example
        if script is None:
            return False, gold_live
        res = docker_exec(container, script, timeout, runner, extra_params=params)
        if entry is None and gold_live is None:
            gold_live = res["stdout"]
        if res["timed_out"] or res["exit_code"] != 0:
            return False, gold_live
        params.append(res["stdout"])
    return True, gold_live


def run_reference(image: str, init_scripts: list, start, example, container: str,
                  runner=subprocess.run, timeout: float = DEFAULT_EXEC_TIMEOUT_S,
                  answer_placeholder: str = ANSWER_PLACEHOLDER_PRIMARY) -> tuple:
    """D2: a FRESH container, init + start, then `example` once with `answer_placeholder` as its
    sole argv (mirrors the chain's `params=[answer]` at the null slot). Returns
    `(exit_ok: bool, stdout: str|None)` -- `exit_ok` is False on any setup/example failure or
    timeout; `stdout` is only meaningful when `exit_ok` is True."""
    remove_container(container, runner)
    try:
        try:
            create_container(f"local-os/{image}", container, runner)
        except Exception:  # noqa: BLE001
            return False, None
        for s in init_scripts:
            res = docker_exec(container, s, timeout, runner)
            if res["timed_out"] or res["exit_code"] != 0:
                return False, None
        if start:
            res = docker_exec(container, start, timeout, runner)
            if res["timed_out"] or res["exit_code"] != 0:
                return False, None
        if example is None:
            return False, None
        res = docker_exec(container, example, timeout, runner, extra_params=[answer_placeholder])
        if res["timed_out"] or res["exit_code"] != 0:
            return False, None
        return True, res["stdout"]
    finally:
        remove_container(container, runner)


def _check_list_has_gold_slot(check_list) -> bool:
    return bool(check_list) and any(entry is None for entry in check_list)


def prepare_exclusions(tasks: list, scripts_root, runner=subprocess.run,
                       timeout: float = DEFAULT_EXEC_TIMEOUT_S,
                       prefix: str = PREPARE_CONTAINER_PREFIX, manual: dict | None = None) -> tuple:
    """D2 (AC2 + cold-review N3/N4/R10), no model calls. Returns (golds: {id: str}, exclusions:
    [{id, reason, ...}]). `match` tasks are never excluded (never even examined).

    `manual` (id -> reason, from `manual_exclusions_path`/`load_manual_exclusions`) is checked
    FIRST and short-circuits: a hand-curated exclusion is never re-probed (it is excluded on
    inspection, not on a mechanical result the probe could second-guess).

    A check list's position-0..n entries can include a `None` ("gold slot": the live grading
    chain runs `example` there, fed the actual submitted answer). Only THOSE tasks need the two-
    placeholder probe (`"1"`/`"2"`, two plausible-looking answers -- N4): disagreement means the
    example script is not a stable answer-independent ground truth -- either it reads its answer
    argument, or it is simply nondeterministic (`gold_mismatch`, R10: one reason covers both, since
    neither makes it usable as a cached gold); empty stdout at either run is `no_gold`.

    A check list with NO gold slot (every position is a literal checker script -- a "pure state
    check", e.g. "did the file move") never touches a gold value at grading time, so probing with
    two placeholders would prove nothing about the real failure mode. Those tasks only need their
    REFERENCE SOLUTION to actually run: init + start + `example` once, exit 0. Nonzero/timeout ->
    `reference_failed`; no gold is cached either way (none is ever used)."""
    manual = manual or {}
    golds, exclusions = {}, []
    for task in tasks:
        if task["id"] in manual:
            exclusions.append({"id": task["id"], "reason": "manual", "note": manual[task["id"]]})
            continue
        cfg = task_config(task, scripts_root)
        if cfg["match"] is not None:
            continue
        name = container_name(prefix, task["id"])
        if _check_list_has_gold_slot(cfg["check"]):
            ok1, g1 = run_reference(cfg["image"], cfg["init_scripts"], cfg["start"], cfg["example"],
                                    name, runner, timeout, ANSWER_PLACEHOLDER_PRIMARY)
            ok2, g2 = run_reference(cfg["image"], cfg["init_scripts"], cfg["start"], cfg["example"],
                                    name, runner, timeout, ANSWER_PLACEHOLDER_PROBE)
            if not ok1 or not ok2 or not g1 or not g2:
                exclusions.append({"id": task["id"], "reason": "no_gold"})
                continue
            if g1 != g2:
                exclusions.append({"id": task["id"], "reason": "gold_mismatch",
                                   "gold_primary": g1, "gold_probe": g2})
                continue
            golds[task["id"]] = g1
        else:
            ok, _stdout = run_reference(cfg["image"], cfg["init_scripts"], cfg["start"],
                                        cfg["example"], name, runner, timeout,
                                        ANSWER_PLACEHOLDER_PRIMARY)
            if not ok:
                exclusions.append({"id": task["id"], "reason": "reference_failed"})
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
            args = _parse_args(fn.get("arguments"))
            if i == 0:
                turn_entry["tool_call"] = {"name": name, "args": args}
            if name == "finish_action":
                fn["name"] = self.SUBMIT_TOOL
                fn["arguments"] = json.dumps({"answer": args.get("thought")})
                # cold-review N10: run_agent only ever DISPATCHES tool_calls[0]
                # (single_tool_call_per_turn=True) -- a submit riding in position 1+ never actually
                # runs, so it must not be recorded as having submitted anything.
                if i == 0:
                    self.submitted_via = "finish"
                    turn_entry["tool_result"] = "submitted"
            elif name == self.SUBMIT_TOOL:
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
        script = args.get("script", "")
        res = shell.run(script, timeout_s=timeout)
        if res["shell_died"]:
            shell_died_flag["hit"] = True
            # R2: a shell death triggered by the MODEL'S OWN action (running `exit`, `set -e` then
            # a failing command, ...) is a SCORED FAIL, not an infra failure -- upstream's
            # equivalent is "later reads return empty and the task fails". Only a death during
            # start()/the start script (before any model action; handled separately in run_task,
            # never reaches here) is setup_error.
            raise agent_loop.AbortEpisode(
                AO.FAILED_TESTS, "the persistent shell exited (e.g. the command ran `exit`)")
        if res["timed_out"]:
            counters["tool_timeouts"] += 1
            exec_timeout_flag["hit"] = True
            raise agent_loop.AbortEpisode(
                AO.FAILED_TESTS, f"command timed out after {timeout:.0f}s and the shell was killed")
        clipped, _truncated = truncate_output(res["output"])
        wrapped_text = wrap_os_output(clipped)
        if transcript_turns:
            # the turn entry for THIS call was appended by DualSubmitDriver.complete() just
            # before run_agent dispatched us; patch in what only the tool itself knows.
            transcript_turns[-1]["tool_result"] = wrapped_text
            transcript_turns[-1]["raw_output_len"] = len(res["output"])
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
    turns converged; `budget_hits` counts turns that hit their own resolved budget."""
    finish_reasons, budget_hits = [], 0
    per_turn_converged = []
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
        hit_budget = bool(budget is not None and ct is not None and ct >= budget)
        if hit_budget:
            budget_hits += 1
        per_turn_converged.append(fr in ("stop", "tool_calls") and not hit_budget)
    episode_converged = all(per_turn_converged) if per_turn_converged else None
    return {"converged": episode_converged, "per_turn_finish_reasons": finish_reasons,
            "budget_hits": budget_hits, "per_turn_converged": per_turn_converged}


# --------------------------------------------------------------------------- per-task run
def _fail_row(base: dict, outcome: str, t0, clock, **extra) -> dict:
    row = {**base, "passed": False, "outcome": outcome, "turns": 0, "submitted_via": None,
          "answer": None, "gold_prepare": base.get("gold_prepare"), "gold_live": None,
          "per_turn_completion_tokens": [], "completion_tokens_total": 0,
          "per_turn_finish_reasons": [], "converged": None,
          "budget_hits": 0, "wall_s": round(clock() - t0, 2), "tool_calls": 0, "tool_timeouts": 0,
          "repeat_calls": 0, "exec_timeout": False, "shell_died": False, "setup_error": True,
          "decode_tps": None, "per_turn_decode_tps": [], "error": None, "_transcript_turns": []}
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
    try:
        try:
            create_container(f"local-os/{cfg['image']}", name, runner)
        except Exception as e:  # noqa: BLE001
            return _fail_row(base, AO.SERVER_ERROR, t0, clock,
                             error=f"container create: {type(e).__name__}: {e}")

        for s in cfg["init_scripts"]:
            res = docker_exec(name, s, exec_timeout, runner)
            if res["timed_out"] or res["exit_code"] != 0:
                return _fail_row(base, AO.SERVER_ERROR, t0, clock,
                                 error=f"init script failed (timed_out={res['timed_out']}, "
                                       f"exit={res['exit_code']}): {res['stderr'][:200]}")

        shell = PersistentShell(name, popen=popen, runner=runner)
        shell.start()
        if cfg["start"]:
            lang, code = cfg["start"]
            if lang != "bash":
                return _fail_row(base, AO.SERVER_ERROR, t0, clock,
                                 error=f"unsupported start script language {lang!r}")
            res = shell.run(code, timeout_s=exec_timeout)
            if res["shell_died"] or res["timed_out"] or res["exit_code"] != 0:
                return _fail_row(base, AO.SERVER_ERROR, t0, clock,
                                 shell_died=res["shell_died"],
                                 error=f"start script failed (shell_died={res['shell_died']}, "
                                       f"timed_out={res['timed_out']}, exit={res['exit_code']})")

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

        def _evaluate(answer):
            if cfg["match"] is not None:
                return evaluate_match(answer, cfg["match"])
            passed, gold_live = run_check_chain(name, cfg["check"], cfg["example"], answer,
                                                runner, exec_timeout)
            gold_live_box["value"] = gold_live
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
        return {**base, "passed": passed, "outcome": outcome, "turns": result.get("turns", 0),
                "submitted_via": wrapped.submitted_via, "answer": answer,
                "gold_live": gold_live_box["value"],
                "per_turn_completion_tokens": [t.get("completion_tokens") for t in wrapped.per_turn],
                "completion_tokens_total": counters.get("completion_tokens", 0),
                "per_turn_finish_reasons": conv["per_turn_finish_reasons"],
                "converged": conv["converged"], "budget_hits": conv["budget_hits"],
                "wall_s": counters.get("wall_s", round(clock() - t0, 2)),
                "tool_calls": counters.get("tool_calls", 0),
                "tool_timeouts": tool_counters["tool_timeouts"],
                "repeat_calls": counters.get("repeat_identical_calls", 0),
                "exec_timeout": exec_timeout_flag["hit"], "shell_died": shell_died_flag["hit"],
                # R2: by this point we are PAST the start-phase checks (which already returned
                # early via _fail_row, setup_error=True, for a start-caused death) -- any
                # shell_died here came from a bash_action, i.e. the model's own doing, and is
                # IN the acc denominator (outcome is already FAILED_TESTS via AbortEpisode above).
                "setup_error": False,
                "decode_tps": round(statistics.mean(dtps), 2) if dtps else None,
                "per_turn_decode_tps": [t.get("decode_tps") for t in wrapped.per_turn],
                "error": result.get("error"), "_transcript_turns": wrapped.per_turn}
    except TransportFailure:
        raise
    except KeyboardInterrupt:
        raise
    except Exception as e:  # noqa: BLE001 -- infra/setup/evaluate failure; never crash the batch
        return _fail_row(base, AO.SERVER_ERROR, t0, clock, error=f"{type(e).__name__}: {e}")
    finally:
        if shell is not None:
            shell.close()
        remove_container(name, runner)
