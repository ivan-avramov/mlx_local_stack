"""P475 stage 1 — the KV-cache format matrix for `Qwen3.8-27B-mlx-uniform-4bit` (contract `docs/specs/p475-stage1-contract.md`).

Subcommands: `prepare` (arm branches + worktrees), `preflight --arm A` (the fork's qualify `--kv-arm`), `run` (plan -> legs ->
replacements -> deciding block; resumable), `matrix` (the generated table from harvested dossiers only). Every side effect on
processes, git, power and locks goes through an `Ops` object (`RealOps` here; tests pass a fake).
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import difflib
import hashlib
import importlib.util
import json
import os
import re
import signal
import sys
import time
from pathlib import Path
from typing import Protocol

from bench import kv_line
from bench.capacity_ladder import P475_DRAFT_KEYS, rung_problems

PICK = "Qwen3.8-27B-mlx-uniform-4bit"
PICK_SHORT = "u4"
ARMS = ("N16", "AF8", "TQ8", "AF4", "TQ4", "TQ4-OFF")
BASE_ARM = "TQ4"
REFERENCE_ARM = "N16"
GRID = (8192, 131072, 196608, 260096)
SMOKE_GRID = (8192,)
SMOKE_ARMS = ("N16", "TQ4")        # v1.2 (GLM F1): the worker CLI sets KV_BITS only on a quantized arm
IDLE_S = 600.0
TICK_S = 300.0
PORT = 8000
DRIVER_OVERHEAD_S = 900.0          # preload + calibration + provenance, on top of 3 x the expected rung durations
PREFLIGHT_TIMEOUT_S = 4 * 3600.0
REGISTRY = "main_models.yaml"
P475_DIR = "p475"
# v1.2 (Sol P1): the files the arm worktree executes, relative to `benchmark/`; byte-identical to the orchestrator checkout's
INSTRUMENT_FILES = ("bench/run_capacity.py", "bench/capacity_ladder.py", "bench/kv_line.py", "bench/data/p475_decode_carrier.txt",
                    "m1/bench_watch.py")
LEG_RE = re.compile(r"^u4-(n16|af8|tq8|af4|tq4|tq4-off)-(b[1-9][0-9]*|smoke)\.a([1-9][0-9]*)$")
# Per-leg wall estimates (spec v4 stage 1 "Estimate", minutes per block); per rung by the rung's share of prefill tokens.
LEG_ESTIMATE_MIN = {"N16": 25, "AF8": 35, "TQ8": 80, "AF4": 40, "TQ4": 76, "TQ4-OFF": 76}
# arm -> registry entry edits: kv_bits / kv_quant_scheme (None = remove the line); TQ4-OFF comments out the MTP lines.
# N16 changes only kv_bits: the scheme line stays as in the base (the fork's `--kv-arm` gate, spec v4; v1.2, Sol P2).
ARM_EDITS = {
    "N16": {"kv_bits": "0"},
    "AF8": {"kv_bits": "8", "kv_quant_scheme": "uniform"},
    "TQ8": {"kv_bits": "8", "kv_quant_scheme": "turboquant"},
    "AF4": {"kv_bits": "4", "kv_quant_scheme": "uniform"},
    "TQ4": {},
    "TQ4-OFF": {"draft_kind": "#", "draft_model": "#"},
}
METRICS = (("peak", "cumulative peak GB", "peak_memory_gb_cumulative"),
           ("prefill", "backend prefill tok/s", "prompt_per_second"),
           ("decode", "decode tok/s", "predicted_per_second"),
           ("acceptance", "MTP acceptance (ON)", None))


class P475Error(RuntimeError):
    """A refusal of a subcommand (printed as `REFUSED: …`, exit 2)."""


# ============================================================================================ ops (the test seam)
class Ops(Protocol):
    def power(self) -> dict: ...
    def port_listener(self, port): ...
    def busy(self) -> list: ...
    def lease(self): ...
    def now(self) -> float: ...
    def monotonic(self) -> float: ...
    def sleep(self, s) -> None: ...
    def worktree_state(self, wt) -> dict: ...
    def git(self, wt, *args) -> str: ...
    def stack(self, wt, registry, predictor): ...
    def proc_alive(self, pid, create_time) -> bool: ...
    def proc_env(self, pid) -> dict: ...
    def spawn(self, argv, env, cwd, session=True) -> dict: ...
    def wait(self, proc, timeout): ...
    def signal_group(self, proc, sig) -> None: ...
    def group_alive(self, pgid) -> bool: ...
    def start_watch(self, argv): ...
    def stop_watch(self, handle) -> None: ...
    def read_text(self, path) -> str: ...
    def pmset_log(self, start, end) -> str: ...
    def run(self, argv, cwd, env, timeout): ...


# ============================================================================================ names and paths
def arm_lower(arm):
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r} (one of {list(ARMS)})")
    return arm.lower()


def arm_of_lower(label):
    for a in ARMS:
        if a.lower() == label:
            return a
    raise ValueError(f"unknown arm {label!r}")


def branch_name(arm):
    return f"p475-{PICK_SHORT}-{arm_lower(arm)}"


KINDS = ("off", "engagement")      # C301: the OFF preflight (kv manifest) and the ON engagement check (P658 (a))


def kinds_for(arm):
    """C301: every arm needs its OFF preflight; an MTP-ON arm also its ON engagement check."""
    return ("off", "engagement") if predictor_of(arm) == "on" else ("off",)


def predictor_of(arm):
    """"on" for every arm but TQ4-OFF (the committed MTP state), "off" for TQ4-OFF."""
    arm_lower(arm)
    return "off" if arm == "TQ4-OFF" else "on"


def leg_name(arm, block, attempt):
    """`u4-<arm-lower>-b<k>.a<n>`; block "smoke" -> `u4-<arm-lower>-smoke.a<n>`."""
    if block == "smoke":
        return f"{PICK_SHORT}-{arm_lower(arm)}-smoke.a{int(attempt)}"
    return f"{PICK_SHORT}-{arm_lower(arm)}-b{int(block)}.a{int(attempt)}"


def parse_leg(name):
    m = LEG_RE.match(name or "")
    if not m:
        raise ValueError(f"not a P475 leg name: {name!r}")
    block = "smoke" if m.group(2) == "smoke" else int(m.group(2)[1:])
    return dict(arm=arm_of_lower(m.group(1)), block=block, attempt=int(m.group(3)))


def block_order(block):
    """Block 1 (and any deciding block, odd) N16 -> … -> TQ4-OFF; block 2 (even) the reverse (ABBA)."""
    return tuple(ARMS) if int(block) % 2 == 1 else tuple(reversed(ARMS))


@dataclasses.dataclass
class Config:
    repo: Path
    workdir: Path
    base: str
    model: str = PICK
    expected: dict = None
    watch_interval: float = TICK_S
    max_preflight: int = 2
    production_ref: str | None = None
    scrub: object = None
    operator_emails: tuple = ()
    run_identity: dict = None          # the run's recorded {arm_commits, gitlinks} (state.json), set by `run`

    def __post_init__(self):
        self.repo, self.workdir = Path(self.repo), Path(self.workdir)
        if self.expected is None:
            self.expected = default_expected()

    # -- paths
    @property
    def p475(self):
        return self.workdir / P475_DIR

    def worktree(self, arm):
        return self.workdir / "worktrees" / branch_name(arm)

    def registry(self, arm):
        return self.worktree(arm) / REGISTRY

    def leg_dir(self, leg):
        return self.p475 / "legs" / leg

    def receipt_path(self, leg):
        return self.leg_dir(leg) / "receipt.json"

    def preflight_dir(self, kind="off"):
        """C301: the OFF preflight records under `preflight/`, the ON engagement records under `engagement/`."""
        if kind not in KINDS:
            raise P475Error(f"unknown preflight kind {kind!r}")
        return self.p475 / ("preflight" if kind == "off" else "engagement")

    def preflight_record(self, arm, kind="off"):
        return self.preflight_dir(kind) / f"{arm}.json"

    @property
    def results(self):
        return self.repo / "benchmark" / "results" / "p475"

    def dossier(self, leg):
        return self.results / leg

    def evidence_stage(self, leg):
        return self.p475 / "evidence-stage" / leg

    @property
    def state_path(self):
        return self.p475 / "state.json"

    def out_tag(self, leg):
        return f"p475-{leg}"

    def capacity_dir(self, leg):
        """C297 (S18-P1 (c)): `run_capacity --out-dir`; a leg writes nothing in its arm worktree (R1 stays strict)."""
        return self.leg_dir(leg) / "capacity"

    def capacity_outputs(self, arm, leg):
        d = self.capacity_dir(leg)
        tag = self.out_tag(leg)
        return dict(rows=d / f"capacity_ladder.{tag}.jsonl", manifest=d / f"capacity_ladder.{tag}.manifest.json",
                    scorecard=d / f"capacity_retrieval.{tag}.json")

    def grid(self, block):
        return SMOKE_GRID if block == "smoke" else GRID

    def expected_for(self, arm, block):
        full = list(self.expected[arm])
        return [full[GRID.index(c)] for c in self.grid(block)]


def default_expected():
    """Expected seconds per rung of GRID, per arm: the spec's per-leg estimate split by each rung's share of prefill tokens."""
    total = sum(GRID)
    return {arm: [round(LEG_ESTIMATE_MIN[arm] * 60 * c / total, 1) for c in GRID] for arm in ARMS}


def driver_timeout(expected):
    return 3 * sum(expected) + DRIVER_OVERHEAD_S


# ============================================================================================ small helpers
def power_ok(p):
    return bool(isinstance(p, dict) and p.get("watts") == 140 and p.get("volts") == 28
                and isinstance(p.get("battery"), (int, float)) and not isinstance(p.get("battery"), bool) and p["battery"] > 20)


def kv_env_names(env):
    """Every `KV_*` / `TQ_*` name (and the stack-defined KV / TQ names) of `env` (R2)."""
    from bench.p426_secrets import STACK_DEFINED_KV_TQ_NAMES
    return sorted(k for k in env if k.startswith(("KV_", "TQ_")) or k in STACK_DEFINED_KV_TQ_NAMES)


def strip_kv(env):
    drop = set(kv_env_names(env))
    return {k: v for k, v in env.items() if k not in drop}


def _atomic_json(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True, default=str) + "\n")
    os.replace(tmp, path)


def write_receipt(path, doc):
    """R17: atomic and never over an existing receipt; a second write goes to `receipt.refused-<ns>.json`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".receipt.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True, default=str) + "\n")
    dest = path
    try:
        while True:
            try:
                os.link(tmp, dest)
                break
            except FileExistsError:
                dest = path.with_name(f"receipt.refused-{time.time_ns()}.json")
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def read_receipt(leg_dir):
    """R17: the canonical `receipt.json` wins over every `receipt.refused-*` variant; None when absent or unreadable."""
    try:
        doc = json.loads((Path(leg_dir) / "receipt.json").read_text())
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _read_optional(ops, path):
    """`ops.read_text(path)`, None when the file does not exist; any other read failure propagates."""
    try:
        return ops.read_text(path)
    except FileNotFoundError:
        return None


def _last_leg_end(ops, path):
    text = _read_optional(ops, path)
    if text is None:
        return None
    value = float(text.strip())
    if not (value >= 0 and value != float("inf")):
        raise ValueError(f"{path} does not hold a valid time")
    return value


def last_leg_end(ops, cfg):
    """The later of `$STACK_WORKDIR/p475/LAST_LEG_END` and `$STACK_WORKDIR/p426/LAST_LEG_END` (None before any leg)."""
    ends = [_last_leg_end(ops, cfg.workdir / P475_DIR / "LAST_LEG_END"), _last_leg_end(ops, cfg.workdir / "p426" / "LAST_LEG_END")]
    ends = [e for e in ends if e is not None]
    return max(ends) if ends else None


def _flag(argv, flag):
    from bench.chain_ops import argv_flag
    return argv_flag([str(t) for t in argv], flag)


def _argv_list(cmdline):
    """A worker command line as a list: a list as is; a `ps` line (`"<pid> <argv…>"`) split, the pid dropped."""
    if isinstance(cmdline, (list, tuple)):
        return [str(t) for t in cmdline]
    toks = str(cmdline or "").split()
    return toks[1:] if toks and toks[0].isdigit() else toks


def _bench_watch():
    path = Path(__file__).resolve().parents[1] / "m1" / "bench_watch.py"
    spec = importlib.util.spec_from_file_location("p475_bench_watch", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================================================ arm registries (R1)
def _entry_span(lines, model):
    for i, ln in enumerate(lines):
        m = re.match(r"^(\s*)- name:\s*(\S+)\s*(#.*)?$", ln)
        if m and m.group(2) == model:
            indent = m.group(1)
            end = len(lines)
            for j in range(i + 1, len(lines)):
                s = lines[j]
                if not s.strip() or s.lstrip().startswith("#"):
                    continue
                lead = len(s) - len(s.lstrip())
                if lead < len(indent) + 2:
                    end = j
                    break
            return i, end, indent + "  "
    raise ValueError(f"{model}: no `- name:` entry in the registry")


def arm_registry_text(base_text, arm, model=PICK):
    """The arm's `main_models.yaml`: the base text with only the arm's entry keys changed and a `# PROVISIONAL P475 arm <ARM>`
    comment; TQ4 is the base text itself."""
    edits = ARM_EDITS[arm]
    if not edits:
        return base_text
    lines = base_text.splitlines(keepends=True)
    start, end, ki = _entry_span(lines, model)
    out, seen = [], set()
    for i, ln in enumerate(lines):
        m = re.match(rf"^{re.escape(ki)}(kv_bits|kv_quant_scheme|draft_kind|draft_model):(.*?)(\r?\n)?$", ln) if start < i < end else None
        if not m or m.group(1) not in edits:
            out.append(ln)
            if i == start:
                out.append(f"{ki}# PROVISIONAL P475 arm {arm}\n")
            continue
        key, nl = m.group(1), m.group(3) or ""
        seen.add(key)
        value = edits[key]
        if value is None:
            continue                                            # the key is removed
        if value == "#":
            out.append(f"{ki}# {key}:{m.group(2)}{nl}")          # commented out, content kept
        else:
            out.append(f"{ki}{key}: {value}{nl}")
    missing = [k for k, v in edits.items() if v not in (None, "#") and k not in seen]
    if missing or ("draft_kind" in edits and "draft_kind" not in seen):
        raise ValueError(f"{model}: the base entry lacks {missing or ['draft_kind']}")
    return "".join(out)


def _allowed_added(arm, ki):
    edits = ARM_EDITS[arm]
    pats = [re.compile(rf"^{re.escape(ki)}# PROVISIONAL P475 arm {re.escape(arm)}$")]
    for key, value in edits.items():
        if value == "#":
            pats.append(re.compile(rf"^{re.escape(ki)}# {key}:.*$"))
        elif value is not None:
            pats.append(re.compile(rf"^{re.escape(ki)}{key}:\s*{re.escape(value)}\s*(#.*)?$"))
    return pats


def registry_diff_problems(base_text, arm_text, arm, model=PICK):
    """R1: the arm commit's registry differs from the base only by the arm's keys and its PROVISIONAL comment."""
    import yaml
    if arm == BASE_ARM:
        return [] if arm_text == base_text else ["TQ4: the registry differs from the base"]
    problems = []
    want = arm_registry_text(base_text, arm, model)
    try:
        if yaml.safe_load(arm_text) != yaml.safe_load(want):
            problems.append(f"{arm}: the registry's parsed content is not the base with only the arm's keys changed")
    except yaml.YAMLError as exc:
        return [f"{arm}: the registry does not parse ({type(exc).__name__})"]
    base_lines, arm_lines = base_text.splitlines(), arm_text.splitlines()
    start, end, ki = _entry_span(base_lines, model)
    removable = {ln for ln in base_lines[start + 1:end]
                 if re.match(rf"^{re.escape(ki)}({'|'.join(ARM_EDITS[arm])}):", ln)}
    added_ok = _allowed_added(arm, ki)
    comments = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, base_lines, arm_lines, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        for ln in base_lines[i1:i2]:
            if ln not in removable:
                problems.append(f"{arm}: removed line outside the arm's keys: {ln.strip()[:80]!r}")
        for ln in arm_lines[j1:j2]:
            if not any(p.match(ln) for p in added_ok):
                problems.append(f"{arm}: added line outside the arm's keys: {ln.strip()[:80]!r}")
            elif "PROVISIONAL P475 arm" in ln:
                comments += 1
    if comments != 1:
        problems.append(f"{arm}: {comments} `# PROVISIONAL P475 arm {arm}` comment(s), need exactly 1")
    return problems


def _gitlinks(text):
    out = {}
    for line in (text or "").splitlines():
        if "\t" in line:
            meta, rel = line.split("\t", 1)
            parts = meta.split()
            if len(parts) >= 3:
                out[rel] = parts[2]
    return out


def arm_identity(arm, ops, cfg):
    """R1: (identity, problems) of the arm worktree — clean, HEAD == the arm branch's commit, its parent == the base (TQ4: HEAD ==
    the base), the commit's diff ⊆ the arm's keys + comment, gitlinks == the base's."""
    wt = cfg.worktree(arm)
    problems = []
    st = ops.worktree_state(wt)
    head = (st or {}).get("head")
    ident = dict(worktree=str(wt), branch=branch_name(arm), head=head, clean=(st or {}).get("clean"),
                 gitlinks=(st or {}).get("gitlinks"), base=cfg.base)
    if not ident["clean"]:
        problems.append(f"{arm}: worktree not clean")
    commit = ops.git(wt, "rev-parse", f"refs/heads/{branch_name(arm)}").strip()
    ident["arm_commit"] = commit
    if head != commit:
        problems.append(f"{arm}: HEAD {head} != the arm commit {commit}")
    if arm == BASE_ARM:
        if head != cfg.base:
            problems.append(f"{arm}: HEAD {head} != the base {cfg.base}")
    else:
        parent = ops.git(wt, "rev-parse", f"{head}^").strip()
        ident["parent"] = parent
        if parent != cfg.base:
            problems.append(f"{arm}: parent {parent} != the base {cfg.base}")
        files = sorted(ops.git(wt, "diff", "--name-only", cfg.base, head).split())
        ident["diff_files"] = files
        if files != [REGISTRY]:
            problems.append(f"{arm}: the arm commit changes {files}, not only {REGISTRY}")
        if REGISTRY in files:
            problems += registry_diff_problems(ops.git(wt, "show", f"{cfg.base}:{REGISTRY}"),
                                               ops.git(wt, "show", f"{head}:{REGISTRY}"), arm, cfg.model)
    base_links = _gitlinks(ops.git(wt, "ls-tree", cfg.base, "src/mlx-vlm", "src/mlx-serve"))
    ident["base_gitlinks"] = base_links
    if not base_links or ident["gitlinks"] != base_links:
        problems.append(f"{arm}: gitlinks {ident['gitlinks']} != the base's {base_links}")
    return ident, problems


def instrument_shas(root):
    """{rel: sha256 or None (absent / unreadable)} of the instrument files under `<root>/benchmark/`."""
    out = {}
    for rel in INSTRUMENT_FILES:
        try:
            out[rel] = hashlib.sha256((Path(root) / "benchmark" / rel).read_bytes()).hexdigest()
        except OSError:
            out[rel] = None
    return out


def instrument_problems(arm, cfg):
    """v1.2 (Sol P1): (orchestrator shas, problems) — the arm worktree's instrument files byte-identical to the orchestrator
    checkout's (`cfg.repo`); a file absent on either side refuses."""
    mine, theirs = instrument_shas(cfg.repo), instrument_shas(cfg.worktree(arm))
    problems = []
    for rel in INSTRUMENT_FILES:
        if mine[rel] is None:
            problems.append(f"instrument {rel}: absent in the orchestrator checkout")
        elif theirs[rel] is None:
            problems.append(f"instrument {rel}: absent in the {arm} worktree")
        elif mine[rel] != theirs[rel]:
            problems.append(f"instrument {rel}: the {arm} worktree's copy differs from the orchestrator checkout's")
    return mine, problems


def recorded_identity_problems(arm, ident, recorded):
    """v1.2 (Sol P3): the arm commit and gitlinks equal the ones the run recorded at its earlier legs."""
    if not recorded:
        return []
    problems = []
    want = (recorded.get("arm_commits") or {}).get(arm)
    if want is not None and ident.get("arm_commit") != want:
        problems.append(f"{arm}: arm commit {ident.get('arm_commit')} != the run's recorded {want}")
    links = recorded.get("gitlinks")
    if links is not None and ident.get("gitlinks") != links:
        problems.append(f"{arm}: gitlinks {ident.get('gitlinks')} != the run's recorded {links}")
    return problems


# ============================================================================================ prepare
def prepare(ops, cfg, arms=ARMS):
    """Create / verify every arm branch and worktree (idempotent); a dirty or diverged arm refuses. Returns the problems."""
    problems = []
    (cfg.workdir / "p369" / "phase2").mkdir(parents=True, exist_ok=True)   # C296 (P656 3): the fork qualify's lock dir
    for arm in arms:
        wt, br = cfg.worktree(arm), branch_name(arm)
        try:
            try:
                ops.git(cfg.repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{br}")
                have_branch = True
            except Exception:  # noqa: BLE001 — rc != 0: no such branch
                have_branch = False
            if not Path(wt).exists():
                wt.parent.mkdir(parents=True, exist_ok=True)
                if have_branch:
                    ops.git(cfg.repo, "worktree", "add", str(wt), br)
                else:
                    ops.git(cfg.repo, "worktree", "add", "-b", br, str(wt), cfg.base)
                ops.git(wt, "submodule", "update", "--init", "--force")
                if arm != BASE_ARM and ops.git(wt, "rev-parse", "HEAD").strip() == cfg.base:
                    base_text = ops.git(wt, "show", f"{cfg.base}:{REGISTRY}")
                    (wt / REGISTRY).write_text(arm_registry_text(base_text, arm, cfg.model))
                    ops.git(wt, "add", REGISTRY)
                    ops.git(wt, "commit", "-m", f"chore(stack): P475 arm {arm} for {cfg.model} (PROVISIONAL, local arm branch)",
                            "--", REGISTRY)
                dotenv = cfg.repo / ".env"
                if dotenv.exists() and not (wt / ".env").exists():
                    (wt / ".env").symlink_to(dotenv)
            _ensure_venvs(ops, cfg, wt)
            _, found = arm_identity(arm, ops, cfg)
            problems += found
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{arm}: prepare failed: {type(exc).__name__}: {exc}")
    return problems


def _ensure_venvs(ops, cfg, wt):
    env = strip_kv(dict(os.environ))
    if not (Path(wt) / ".venv" / "bin" / "python").exists():
        _checked(ops.run(["uv", "sync", "--frozen"], str(wt), env, 3600), "uv sync --frozen")
    bench = Path(wt) / ".venv-bench"
    if not (bench / "bin" / "python").exists():
        _checked(ops.run(["uv", "venv", "--python", "3.12", "--python-preference", "only-managed", str(bench)], str(wt), env, 1800),
                 "uv venv .venv-bench")
        _checked(ops.run(["uv", "pip", "sync", "--python", str(bench / "bin" / "python"), "benchmark/requirements-bench.lock"],
                         str(wt), env, 3600), "uv pip sync .venv-bench")
    _ensure_fork_venv(ops, cfg, wt, env)


FORK_VENV_EXCLUDE = ("mlx-vlm", "mlx-serve", "mlx-local-stack")


def fork_constraints(freeze_text):
    """The arm `.venv`'s pins as constraints for the fork venv: no editable / direct-URL lines, no fork or stack project."""
    out = []
    for line in (freeze_text or "").splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "-")) or " @ " in s:
            continue
        name = re.split(r"[=<>!~;\[ ]", s, 1)[0].strip().lower().replace("_", "-")
        if name in FORK_VENV_EXCLUDE:
            continue
        out.append(s)
    return "".join(f"{x}\n" for x in out)


def _ensure_fork_venv(ops, cfg, wt, env):
    """C296 (P656 3): `src/mlx-vlm/.venv` (qualify's `fork_versions` interpreter), the fork installed editable with the arm
    `.venv`'s own versions as constraints."""
    fork = Path(wt) / "src" / "mlx-vlm"
    venv = fork / ".venv"
    if (venv / "bin" / "python").exists():
        return
    arm_py = Path(wt) / ".venv" / "bin" / "python"
    freeze = _checked(ops.run(["uv", "pip", "freeze", "--python", str(arm_py)], str(wt), env, 600), "uv pip freeze (arm .venv)")
    cpath = cfg.p475 / "fork-venv" / f"{Path(wt).name}.constraints.txt"
    cpath.parent.mkdir(parents=True, exist_ok=True)
    cpath.write_text(fork_constraints(getattr(freeze, "stdout", "")))
    _checked(ops.run(["uv", "venv", "--python", "3.12", "--python-preference", "only-managed", str(venv)], str(fork), env, 1800),
             "uv venv (fork)")
    _checked(ops.run(["uv", "pip", "install", "--python", str(venv / "bin" / "python"), "-e", str(fork), "-c", str(cpath)],
                     str(fork), env, 3600), "uv pip install (fork)")


def _checked(cp, what):
    if getattr(cp, "returncode", 1) != 0:
        raise P475Error(f"{what} exited {getattr(cp, 'returncode', None)}")
    return cp


# ============================================================================================ preflight (R15)
def preflight_argv(arm, cfg, out_dir, reviewed_head, kind="off"):
    wt = cfg.worktree(arm)
    fork = wt / "src" / "mlx-vlm"
    argv = [str(wt / ".venv" / "bin" / "python"), str(fork / "dev" / "p369_phase2" / "qualify.py"),
            "--stack-root", str(wt), "--fork-root", str(fork), "--out", str(out_dir),
            "--reviewed-head", reviewed_head, "--entry", cfg.model, "--predictor", "on" if kind == "engagement" else "off"]
    if cfg.production_ref:
        argv += ["--production-ref", cfg.production_ref]
    argv += ["--kv-arm"]
    return argv + (["--engagement-only"] if kind == "engagement" else [])


def preflight_report_problems(report, model, kind="off"):
    if not isinstance(report, dict):
        return ["no report.json"]
    problems = []
    if kind == "engagement":                     # C301: uncertified MTP-ON engagement evidence (fork P658 (a)), nothing else
        if report.get("predictor") != "on":
            problems.append(f"report predictor {report.get('predictor')!r} (need 'on')")
        if report.get("engagement_only") is not True:
            problems.append(f"report engagement_only {report.get('engagement_only')!r} (need true)")
        if report.get("certifies") is not False:
            problems.append(f"report certifies {report.get('certifies')!r} (need false)")
    state = (report.get("entries") or {}).get(model) or {}
    if state.get("status") != "COMPLETED":
        problems.append(f"qualify status {state.get('status')!r} (need COMPLETED)")
    if "status" in report and report["status"] != "COMPLETED":
        problems.append(f"qualify report status {report['status']!r}")
    if (report.get("kv_arm") or {}).get("entry") != model:
        problems.append(f"kv_arm.entry {(report.get('kv_arm') or {}).get('entry')!r} != {model!r}")
    return problems


def read_preflight(cfg, arm, kind="off"):
    try:
        doc = json.loads(cfg.preflight_record(arm, kind).read_text())
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def qualify_refused_before_start(returncode, report, stderr_tail):
    """C302 (S18-P12 b): `qualify` refused before its measurement loop — a nonzero exit, a report without `started` whose every
    entry is NOT_RUN (its own preflight: power, process census, …). Returns the reason (its last `refused:` line), else None.
    A run with no report (a configuration refusal) or one that started still counts as an attempt."""
    if returncode == 0 or not isinstance(report, dict) or "started" in report:
        return None
    entries = report.get("entries")
    if not isinstance(entries, dict) or not entries:
        return None
    if any(not isinstance(e, dict) or e.get("status") != "NOT_RUN" for e in entries.values()):
        return None
    lines = [ln.strip() for ln in (stderr_tail or "").splitlines() if ln.strip().startswith("refused:")]
    return "qualify " + (lines[-1] if lines else "refused before any entry started")[:400]


class _NotStarted(Exception):
    """C296 (P656): an environmental refusal before `qualify` runs (port / busy / lease / leftover out dir)."""


STDERR_TAIL = 4000


def _tail(text):
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return (text or "")[-STDERR_TAIL:]


def preflight(arm, ops, cfg, max_retries=None, kind="off"):
    """The fork's qualify `--kv-arm --predictor off --entry <pick>` on the arm worktree; a refusal is retried at most
    `max_retries` times, then the arm is REFUSED. A final record (PASS / REFUSED) is never redone. C296 (P656): an
    environmental refusal (port / busy / lease / leftover out dir) records NOT_STARTED, consumes no attempt and is never final.
    C301: `kind="engagement"` is the ON engagement check of an MTP-ON arm (`--predictor on --engagement-only`, its own records);
    S18-P3: a record taken on another base is not final — NOT_STARTED, returned unwritten, the old record kept as evidence."""
    max_retries = cfg.max_preflight if max_retries is None else max_retries
    if kind not in kinds_for(arm):
        raise P475Error(f"{arm} has no {kind} check (MTP-OFF arms take only the OFF preflight)")
    rec = read_preflight(cfg, arm, kind)
    if rec is not None and rec.get("base") != cfg.base:
        return dict(arm=arm, model=cfg.model, base=cfg.base, kind=kind, status="NOT_STARTED", attempts=[], max_retries=max_retries,
                    not_started=[dict(reason=f"{cfg.preflight_record(arm, kind)} was taken on base {rec.get('base')!r}, not "
                                             f"{cfg.base} (archive $STACK_WORKDIR/{P475_DIR}/ whole before a re-prepare)",
                                      at=ops.now())],
                    stale_record=str(cfg.preflight_record(arm, kind)))
    if rec and rec.get("status") in ("PASS", "REFUSED"):
        return rec
    attempts = list((rec or {}).get("attempts") or [])
    not_started = list((rec or {}).get("not_started") or [])
    rec = dict(arm=arm, model=cfg.model, base=cfg.base, kind=kind, status="PENDING", attempts=attempts, max_retries=max_retries,
               not_started=not_started)
    while len(attempts) < 1 + max_retries:
        n = len(attempts) + 1
        out = cfg.preflight_dir(kind) / f"{arm}.a{n}"
        att = dict(attempt=n, out=str(out), problems=[], started=ops.now())
        try:
            with contextlib.ExitStack() as stack:
                try:
                    power = ops.power()                       # C302 (S18-P12 a): as the leg pre-check
                    if not power_ok(power):
                        raise P475Error(f"power {power} (need 140 W / 28 V / battery > 20 %)")
                    if ops.port_listener(PORT) is not None:
                        raise P475Error(f":{PORT} is bound")
                    busy = ops.busy()
                    if busy:
                        raise P475Error("busy processes: " + "; ".join(map(str, busy))[:400])
                    stack.enter_context(ops.lease())
                    if out.exists():
                        raise P475Error(f"{out} exists")
                except Exception as exc:  # noqa: BLE001 — nothing ran: not an attempt
                    raise _NotStarted(f"{type(exc).__name__}: {exc}") from None
                links = (ops.worktree_state(cfg.worktree(arm)) or {}).get("gitlinks") or {}
                reviewed = links.get("src/mlx-vlm")
                if not reviewed:
                    raise P475Error("the arm worktree's src/mlx-vlm gitlink is unknown")
                argv = preflight_argv(arm, cfg, out, reviewed, kind)
                att["argv"] = argv
                try:
                    cp = ops.run(argv, str(cfg.worktree(arm)), strip_kv(dict(os.environ)), PREFLIGHT_TIMEOUT_S)
                except Exception as exc:  # noqa: BLE001 — a timeout (group reaped by RealOps.run) keeps its stderr
                    att["stderr_tail"] = _tail(getattr(exc, "stderr", None))
                    raise
                att["stderr_tail"] = _tail(getattr(cp, "stderr", None))
                att["returncode"] = getattr(cp, "returncode", None)
                if att["returncode"] != 0:
                    att["problems"].append(f"qualify exit {att['returncode']}")
                text = _read_optional(ops, out / "report.json")
                report = json.loads(text) if text else None
                att["report"] = {k: (report or {}).get(k) for k in ("predictor", "entries", "kv_arm", "production", "registry_sha256",
                                                                     "started")}
                refused = qualify_refused_before_start(att["returncode"], report, att.get("stderr_tail"))
                if refused is not None:                       # C302 (S18-P12 b): nothing was measured — not an attempt
                    aside = out.with_name(f"{out.name}.not-started-{len(not_started) + 1}")
                    os.rename(out, aside)                     # kept as evidence; the attempt number is free again
                    raise _NotStarted(f"{refused} (qualify output kept in {aside.name})")
                att["problems"] += preflight_report_problems(report, cfg.model, kind)
        except _NotStarted as exc:
            not_started.append(dict(reason=str(exc), at=ops.now()))
            rec["status"] = "NOT_STARTED"
            _atomic_json(cfg.preflight_record(arm, kind), rec)
            return rec
        except Exception as exc:  # noqa: BLE001 — a refusal of this attempt (I/O, timeout, qualify)
            att["problems"].append(f"{type(exc).__name__}: {exc}")
        att["ended"] = ops.now()
        attempts.append(att)
        if not att["problems"]:
            rec["status"] = "PASS"
            break
        _atomic_json(cfg.preflight_record(arm, kind), rec)
    if rec["status"] != "PASS":
        rec["status"] = "REFUSED"
    _atomic_json(cfg.preflight_record(arm, kind), rec)
    return rec


# ============================================================================================ the leg (run_leg)
def _destinations(leg, arm, cfg):
    outs = cfg.capacity_outputs(arm, leg)
    return [cfg.receipt_path(leg), cfg.dossier(leg), cfg.dossier(leg).with_name(f"{leg}.stage"), outs["rows"], outs["manifest"],
            outs["scorecard"], cfg.evidence_stage(leg)]                  # v1.2 (TW F2): the evidence stage is a destination


def _registry_entry(text, model):
    import yaml
    doc = yaml.safe_load(text) or {}
    return next((m for m in doc.get("models") or [] if isinstance(m, dict) and m.get("name") == model), None)


def predictor_argv_problems(argv, entry, predictor):
    """ON: exactly `--draft-kind mtp` and the entry's `--draft-model`; OFF: no draft / MTP flag."""
    problems = []
    kinds, drafters, scans = _flag(argv, "--draft-kind"), _flag(argv, "--draft-model"), _flag(argv, "--mtp-verify-scan")
    if predictor == "on":
        if kinds != ["mtp"]:
            problems.append(f"ON worker --draft-kind {kinds} != ['mtp']")
        if drafters != [(entry or {}).get("draft_model")]:
            problems.append(f"ON worker --draft-model {drafters} != [{(entry or {}).get('draft_model')!r}]")
    else:
        if kinds or drafters or scans:
            problems.append(f"OFF worker carries a predictor flag (--draft-kind {kinds}, --draft-model {drafters}, "
                            f"--mtp-verify-scan {scans})")
    return problems


def _parse_jsonl(text):
    rows = []
    for line in (text or "").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def watch_speed_problems(text, t_launch, t_exit, interval):
    """R9–R11: the watcher journal over the driver interval: present, finalized after the driver exit, power ok on every
    in-run tick, enough ticks, no gap > 2 x interval, the battery window proven and empty. Returns (problems, summary)."""
    if not text:
        return ["no watcher report"], dict(ticks=0)
    try:
        lines = [json.loads(x) for x in text.splitlines() if x.strip()]
    except ValueError:
        return ["watcher report unparseable"], dict(ticks=0)
    ticks = [x for x in lines if isinstance(x, dict) and "exit_state" not in x]
    ends = [x for x in lines if isinstance(x, dict) and "exit_state" in x]
    problems = []
    span = (t_exit - t_launch) if None not in (t_exit, t_launch) else 0
    need = max(0, int((span - 2 * interval) // interval))
    if len(ticks) < need:
        problems.append(f"watcher ticks {len(ticks)} < {need} for a {span:.0f} s driver interval")
    if not ends or lines[-1] is not ends[-1] or len(ends) != 1:
        problems.append("watcher journal not finalized (no single closing exit line)")
    else:
        end = ends[0]
        if end.get("exit_state") != "driver_exited":
            problems.append(f"watcher exit_state {end.get('exit_state')!r}")
        if not isinstance(end.get("t"), (int, float)) or (t_exit is not None and end["t"] < t_exit - 5):
            problems.append("watcher exited early (before the driver exit)")
        bi = end.get("battery_intervals")
        if not isinstance(bi, list):
            problems.append("watcher: battery window unproven")
        elif bi:
            problems.append(f"watcher: {len(bi)} on-battery interval(s) in its window")
    if not ticks or not any(t.get("driver_alive") is True for t in ticks):
        problems.append("watcher never saw the driver alive (binding failed)")
    for t in ticks:
        if t.get("driver_alive") is False:
            continue
        if not power_ok(dict(watts=t.get("watts"), volts=t.get("volts"), battery=t.get("battery"))):
            problems.append(f"watcher tick {t.get('tick')}: power {t.get('watts')} W {t.get('volts')} V {t.get('battery')} %")
    stamps = [x.get("t") for x in ticks + ends]
    if any(not isinstance(s, (int, float)) for s in stamps):
        problems.append("watcher tick times missing: gaps unprovable")
    else:
        worst = max((b - a for a, b in zip(stamps, stamps[1:])), default=0.0)
        if worst > 2 * interval:
            problems.append(f"watcher tick gap {worst:.0f} s > 2 x {interval:.0f} s")
    return problems, dict(ticks=len(ticks), need=need, finalized=bool(ends))


def battery_problems(text, t_launch, t_exit):
    """The `pmset -g log` history over exactly [driver launch, driver exit]: well-formed, the source proven at launch, no
    on-battery interval."""
    from bench.p426_leg import power_history_problems
    problems = power_history_problems(0, text)
    if problems:
        return problems
    runs = _bench_watch().parse_battery_log(text, now=t_exit, since=t_launch)
    if runs is None:
        return ["pmset -g log: no power-source event at or before the driver launch (window unproven)"]
    inside = [r for r in runs if r[1] > t_launch and r[0] < t_exit]
    return [f"pmset -g log: on battery {a:.0f} -> {b:.0f} inside the driver interval" for a, b in inside]


def driver_argv(arm, leg, cfg, block):
    wt = cfg.worktree(arm)
    expected = cfg.expected_for(arm, block)
    return [str(wt / ".venv-bench" / "bin" / "python"), "-m", "bench.run_capacity", "--model", cfg.model,
            "--grid", ",".join(str(c) for c in cfg.grid(block)), "--sampling-profile", "deployed", "--seed", "0",
            "--out-tag", cfg.out_tag(leg), "--out-dir", str(cfg.capacity_dir(leg)), "--p475-strict",
            "--expected-rung-seconds", ",".join(f"{x:g}" for x in expected)]


def watch_argv(arm, leg, cfg, block, proc, rows_path):
    wt = cfg.worktree(arm)
    return [str(wt / ".venv-bench" / "bin" / "python"), str(wt / "benchmark" / "m1" / "bench_watch.py"),
            "--driver-pid", str(proc["pid"]), "--driver-create-time", repr(float(proc["create_time"])),
            "--capacity-rows", str(rows_path),
            "--expected-rung-seconds", ",".join(f"{x:g}" for x in cfg.expected_for(arm, block)),
            "--out", str(cfg.leg_dir(leg) / "watch.jsonl"), "--interval", f"{cfg.watch_interval:g}"]


def watch_rows_problems(argv, rows_path):
    """P651 / C293 (GLM F7): the watcher's `--capacity-rows` is exactly the leg's own ladder rows file (else its journal could tick
    healthily over a stale or foreign file); a mismatch is a speed problem (R11)."""
    vals = _flag(argv, "--capacity-rows")
    if vals != [str(rows_path)]:
        return [f"watcher --capacity-rows {vals} != the leg's rows file [{str(rows_path)!r}]"]
    return []


def _reap_driver(ops, proc):
    """R6 (v1.2, Sol P5 / TW F3): the driver's own process group (pgid = its pid: `spawn(session=True)`) is signalled while ANY
    member lives — also after a normal leader exit — escalated TERM -> KILL, reaped, and verified empty with `group_alive`."""
    if proc is None:
        return []
    pgid = proc["pid"]
    try:
        for sig, grace in ((signal.SIGTERM, 30), (signal.SIGKILL, 10)):
            leader = ops.proc_alive(proc["pid"], proc["create_time"])
            if not leader and not ops.group_alive(pgid):
                break
            try:
                ops.signal_group(proc, sig)
            except ProcessLookupError:
                pass
            if leader:
                ops.wait(proc, grace)
            for _ in range(grace):
                if not ops.group_alive(pgid):
                    break
                ops.sleep(1)
        leader = ops.proc_alive(proc["pid"], proc["create_time"])
        group = ops.group_alive(pgid)
    except Exception as exc:  # noqa: BLE001 — group state unprovable: fail closed
        return [f"driver process group {pgid}: liveness unreadable ({type(exc).__name__}: {exc})"]
    problems = []
    if leader:
        problems.append(f"driver pid {proc['pid']} survived SIGTERM / SIGKILL")
    if group:
        problems.append(f"driver process group {pgid} not empty after SIGTERM / SIGKILL")
    return problems


def drafter_key_shape(rows):
    return [{k: ("absent" if k not in r else "null" if r[k] is None else "value") for k in P475_DRAFT_KEYS} for r in rows]


def worker_env_record(env):
    """v1.2 (GLM F1): the worker environment as recorded in the receipt — every variable NAME, and the values of the KV / TQ names
    only (the D1 question); never any other value."""
    return dict(names=sorted(env), kv_tq={k: env[k] for k in kv_env_names(env)})


def telemetry_identities(rows):
    """v1.2 (contract acceptance 3): per rung, the two backend telemetry identities R21 relies on, as observed."""
    out = []
    for r in rows:
        pn, pt, ms, pps = r.get("prompt_n"), r.get("prompt_tokens"), r.get("prompt_ms"), r.get("prompt_per_second")
        derived = pn / (ms / 1000) if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (pn, ms)) and ms else None
        rel = abs(pps - derived) / derived if derived and isinstance(pps, (int, float)) and not isinstance(pps, bool) else None
        out.append(dict(ctx=r.get("ctx"), prompt_n=pn, prompt_tokens=pt, prompt_n_equals_prompt_tokens=pn == pt, prompt_ms=ms,
                        prompt_per_second=pps, prompt_per_second_derived=derived, prompt_per_second_rel_diff=rel))
    return out


def run_leg(leg, arm, ops, cfg):
    """One leg, fail closed (contract "Leg lifecycle"); a receipt is written on every path. Returns the receipt dict (plus
    `_receipt_path` and `_harvest`)."""
    info = parse_leg(leg)
    block, predictor = info["block"], predictor_of(arm)
    if info["arm"] != arm:
        raise ValueError(f"leg {leg} is not an arm {arm} leg")
    wt, registry = cfg.worktree(arm), cfg.registry(arm)
    outs = cfg.capacity_outputs(arm, leg)
    receipt = dict(leg=leg, arm=arm, block=block, attempt=info["attempt"], model=cfg.model, predictor=predictor, base=cfg.base,
                   grid=list(cfg.grid(block)), expected_rung_seconds=cfg.expected_for(arm, block), problems=[],
                   speed_problems=[], speed_valid=False, power={},
                   paths=dict(worktree=str(wt), registry=str(registry), rows=str(outs["rows"]), manifest=str(outs["manifest"]),
                              watch=str(cfg.leg_dir(leg) / "watch.jsonl"), worker_log=str(wt / "logs" / "mlx_vlm.log"),
                              router_log=str(wt / "logs" / "main_model.log")))
    with contextlib.ExitStack() as lease_scope:
        # ---------------------------------------------------------------- 1. pre-check (nothing started)
        pre = []
        try:
            p = ops.power()
            receipt["power"]["entry"] = p
            if not power_ok(p):
                pre.append(f"power {p} (need 140 W / 28 V / battery > 20 %)")
            listener = ops.port_listener(PORT)
            if listener is not None:
                pre.append(f":{PORT} bound by pid {listener}")
            busy = ops.busy()
            if busy:
                pre.append("busy processes: " + "; ".join(map(str, busy))[:400])
            try:
                lease_scope.enter_context(ops.lease())
                receipt["lease"] = "chain"
            except Exception as exc:  # noqa: BLE001 — p426_locks.LockRefused (or an unreadable lock)
                pre.append(f"lease refused: {type(exc).__name__}: {exc}")
            try:
                last = last_leg_end(ops, cfg)
                now = ops.now()
                receipt["idle"] = dict(last_leg_end=last, now=now)
                if last is not None and now - last < IDLE_S:
                    pre.append(f"only {now - last:.0f} s since LAST_LEG_END (need {IDLE_S:.0f} s)")
            except Exception as exc:  # noqa: BLE001
                pre.append(f"LAST_LEG_END unreadable: {type(exc).__name__}: {exc}")
            present = [str(d) for d in _destinations(leg, arm, cfg) if Path(d).exists()]
            if present:
                pre.append(f"destinations exist: {present}")
            for kind in kinds_for(arm):                     # C301: the OFF preflight, and on ON arms the engagement check
                pf = read_preflight(cfg, arm, kind)
                key, what = ("preflight", "preflight") if kind == "off" else ("engagement", "engagement check")
                receipt[key] = dict(record=str(cfg.preflight_record(arm, kind)), status=(pf or {}).get("status"),
                                    base=(pf or {}).get("base"))
                if (pf or {}).get("status") != "PASS":
                    pre.append(f"{what} of {arm} is {(pf or {}).get('status')!r}, not PASS")
                elif pf.get("base") != cfg.base:               # S18-P3
                    pre.append(f"{what} of {arm} was taken on base {pf.get('base')!r}, not {cfg.base}")
            shas, found = instrument_problems(arm, cfg)
            receipt["instrument"] = shas
            pre += found
            ident, found = arm_identity(arm, ops, cfg)
            receipt["identity_entry"] = ident
            pre += found + recorded_identity_problems(arm, ident, cfg.run_identity)
        except Exception as exc:  # noqa: BLE001
            pre.append(f"pre-check failed: {type(exc).__name__}: {exc}")
        if pre:
            receipt.update(verdict="NOT_STARTED", problems=pre)
            return dict(receipt, _receipt_path=str(write_receipt(cfg.receipt_path(leg), receipt)), _harvest=None)

        # ---------------------------------------------------------------- 2–6. router, checks, driver, watcher, teardown
        problems, speed = [], []
        handle = ident_w = proc = watch = None
        rows = []
        try:
            handle = ops.stack(wt, registry, "mtp" if predictor == "on" else "off")
            receipt["router_pid"] = handle.start_router()
            router = getattr(handle, "router", None)
            receipt["router"] = dict(router) if isinstance(router, dict) else dict(pid=receipt["router_pid"])
            log_path = Path(receipt["paths"]["worker_log"])
            before = _read_optional(ops, log_path) or ""
            ident_w = handle.load(cfg.model)
            receipt["worker"] = {k: ident_w.get(k) for k in ("pid", "create_time")}
            argv = _argv_list(ident_w.get("cmdline"))
            receipt["worker_argv"] = argv
            expected = [str(t) for t in handle.expected_worker_argv(registry, cfg.model)]
            receipt["expected_worker_argv"] = expected
            post = []
            if argv != expected:                                        # R3: every KV flag included
                post.append("worker argv differs from the one mlx-serve builds from the arm registry")
            worker_env = ops.proc_env(ident_w["pid"]) or {}
            leaked = kv_env_names(worker_env)
            receipt["worker_env"] = worker_env_record(worker_env)
            if leaked:
                post.append(f"worker environment carries stripped name(s) {leaked}")
            after = _read_optional(ops, log_path) or ""
            since = after[len(before):] if after.startswith(before) else after
            try:
                parsed = kv_line.parse_kv_line(since)
                receipt["kv_line"] = parsed
                post += [f"KV line: {p}" for p in kv_line.kv_line_problems(parsed, arm)]
            except kv_line.KVLineError as exc:
                receipt["kv_line"] = None
                post.append(f"KV line: {exc}")
            entry = _registry_entry(ops.read_text(registry), cfg.model)
            post += predictor_argv_problems(argv, entry, predictor)
            if post:                                                   # R5: refuse before the driver
                problems += post
                raise _Abort()
            # ---------------- 4. driver + 5. watcher
            d_argv = driver_argv(arm, leg, cfg, block)
            base_env = handle.env_base() if hasattr(handle, "env_base") else dict(os.environ)
            env = dict(strip_kv(dict(base_env)), MLX_SERVE_CONFIG=str(registry), MLX_BENCH_SESSION_PREFIX=cfg.out_tag(leg))
            receipt["driver_argv"] = d_argv
            timeout = driver_timeout(cfg.expected_for(arm, block))
            receipt["driver_timeout_s"] = timeout
            cfg.leg_dir(leg).mkdir(parents=True, exist_ok=True)
            t_launch = ops.now()
            proc = ops.spawn(d_argv, env, str(wt / "benchmark"), session=True)
            receipt["driver"] = dict(proc, launch=t_launch)
            try:
                w_argv = [str(t) for t in watch_argv(arm, leg, cfg, block, proc, outs["rows"])]
                receipt["watcher_argv"] = w_argv                 # P651 / C293 (GLM F7): the argv the watcher was started with
                speed += watch_rows_problems(w_argv, outs["rows"])
                watch = ops.start_watch(w_argv)
            except Exception as exc:  # noqa: BLE001 — R11: a watcher failure is a speed problem
                speed.append(f"watcher failed to start: {type(exc).__name__}: {exc}")
            rc = ops.wait(proc, timeout)
            if rc is None:
                problems.append(f"driver timed out after {timeout:.0f} s")
            elif rc != 0:
                problems.append(f"driver exit {rc}")
            receipt["driver"]["returncode"] = rc
        except _Abort:
            pass
        except BaseException as exc:  # noqa: BLE001 — receipted; an interrupt is re-raised after the receipt
            problems.append(f"{type(exc).__name__}: {exc}")
            if not isinstance(exc, Exception):
                receipt["_interrupt"] = exc
        finally:
            problems += _reap_driver(ops, proc)                          # R6: before the watcher stop and teardown
            if proc is not None:
                t_exit = ops.now()
                receipt["driver"]["exit"] = t_exit
                if watch is not None:
                    try:
                        ops.stop_watch(watch)
                    except Exception as exc:  # noqa: BLE001
                        speed.append(f"watcher stop failed: {type(exc).__name__}: {exc}")
                try:
                    wp, summary = watch_speed_problems(_read_optional(ops, cfg.leg_dir(leg) / "watch.jsonl"),
                                                       t_launch, t_exit, cfg.watch_interval)
                except Exception as exc:  # noqa: BLE001
                    wp, summary = [f"watcher report unreadable: {type(exc).__name__}: {exc}"], {}
                receipt["watcher"] = dict(summary, valid=not wp, problems=wp)
                speed += wp
                try:
                    speed += battery_problems(ops.pmset_log(t_launch, t_exit), t_launch, t_exit)
                except Exception as exc:  # noqa: BLE001
                    speed.append(f"pmset -g log failed: {type(exc).__name__}: {exc}")
                try:
                    p = ops.power()
                    receipt["power"]["exit"] = p
                    if not power_ok(p):
                        speed.append(f"power at driver exit {p}")
                except Exception as exc:  # noqa: BLE001
                    speed.append(f"power reading at exit failed: {type(exc).__name__}: {exc}")
                try:
                    rows = _parse_jsonl(_read_optional(ops, outs["rows"]))
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"ladder rows unreadable: {type(exc).__name__}: {exc}")
                problems += _rows_problems(rows, cfg.grid(block), predictor, cfg.out_tag(leg))
                receipt["drafter_keys"] = drafter_key_shape(rows)
                receipt["telemetry"] = telemetry_identities(rows)
            problems += _teardown(ops, handle, ident_w, receipt)
            try:
                ident_exit, found = arm_identity(arm, ops, cfg)
                receipt["identity_exit"] = ident_exit
                problems += found
                if ident_exit != receipt.get("identity_entry"):
                    problems.append("arm identity changed during the leg")
            except Exception as exc:  # noqa: BLE001
                problems.append(f"exit identity check failed: {type(exc).__name__}: {exc}")
        interrupt = receipt.pop("_interrupt", None)
        verdict = "INVALID" if problems else "VALID"
        receipt.update(verdict=verdict, problems=problems, speed_problems=speed, speed_valid=verdict == "VALID" and not speed)
        path = write_receipt(cfg.receipt_path(leg), receipt)
        harvest_state = None
        if interrupt is None:
            try:
                harvest(leg, ops, cfg)
                harvest_state = "harvested"
            except Exception as exc:  # noqa: BLE001
                harvest_state = f"harvest failed: {type(exc).__name__}: {exc}"
        out = dict(receipt, _receipt_path=str(path), _harvest=harvest_state)
    if interrupt is not None:
        raise interrupt
    return out


class _Abort(Exception):
    """A post-load precondition failed (R5): tear down without launching the driver."""


def _rows_problems(rows, grid, predictor, tag):
    problems = []
    if [r.get("ctx") for r in rows] != list(grid):
        problems.append(f"ladder rows cover {[r.get('ctx') for r in rows]}, planned {list(grid)}")
    for r in rows:
        found = rung_problems(r, predictor)
        if found:
            problems.append(f"rung {r.get('ctx')}: " + "; ".join(found))
        sid = r.get("session_id") or ""
        if not sid.startswith(tag + "-"):
            problems.append(f"rung {r.get('ctx')}: session id {sid!r} is not under {tag}")
    sids = [r.get("session_id") for r in rows]
    if len(set(sids)) != len(sids):
        problems.append("a session id appears on two rungs")
    return problems


def _teardown(ops, handle, ident_w, receipt):
    """R7: stop the stack, then prove the worker, the :8000 listener, the router, its wrapper and every busy process gone."""
    if handle is None:
        return []
    problems = []
    try:
        rc = handle.stop_stack()
        receipt["teardown"] = dict(stop_stack=rc)
        if rc != 0:
            problems.append(f"teardown: stop_stack returned {rc!r}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"teardown: stop_stack failed: {type(exc).__name__}: {exc}")
    try:
        if ident_w is not None and not handle.unload_ok():
            problems.append("teardown: the unload was refused or the worker outlived it")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"teardown: unload state unreadable: {type(exc).__name__}: {exc}")
    survivors = []
    try:
        if ident_w and ops.proc_alive(ident_w["pid"], ident_w.get("create_time")):
            survivors.append(f"worker {ident_w['pid']}")
        listener = ops.port_listener(PORT)
        if listener is not None:
            survivors.append(f":{PORT} listener {listener}")
        router = receipt.get("router") or {}
        for rec, what in ((router, "router"), (router.get("spawned") or {}, "router wrapper")):
            if rec.get("pid") and rec.get("create_time") is not None and ops.proc_alive(rec["pid"], rec["create_time"]):
                survivors.append(f"{what} {rec['pid']}")
        if router:                                    # v1.2 (Sol P5): ChainOps spawns the wrapper in its own session
            pgid = (router.get("spawned") or {}).get("pid")
            if not pgid:
                survivors.append("router process group unknown (no spawned wrapper pid): emptiness unprovable")
            elif ops.group_alive(pgid):
                survivors.append(f"router process group {pgid} not empty")
        busy = ops.busy()
        if busy:
            survivors.append("busy: " + "; ".join(map(str, busy))[:300])
    except Exception as exc:  # noqa: BLE001
        survivors.append(f"survivor check failed: {type(exc).__name__}: {exc}")
    receipt.setdefault("teardown", {})["survivors"] = survivors
    problems += [f"teardown survivor: {s}" for s in survivors]
    return problems


# ============================================================================================ harvest (R18)
def operator_emails(cfg):
    """The operator address set the Gate refuses: `--operator-email`, else the main checkout's `git config user.email` (as the P426
    sequencer reads it); an empty set refuses (P426 spec 16.8: never "no operator address")."""
    import subprocess
    if cfg.operator_emails:
        return tuple(cfg.operator_emails)
    try:
        r = subprocess.run(["git", "-C", str(cfg.repo), "config", "user.email"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise P475Error("the operator email cannot be read (`git config user.email` failed in the main checkout)") from None
    emails = tuple(x for x in r.stdout.split() if x) if r.returncode == 0 else ()
    if not emails:
        raise P475Error("the operator email set is empty (`git config user.email` unset; pass --operator-email)")
    return emails


def default_scrub(cfg):
    """The Scrub the P426 harvest builds (`p426_harvest.main`): workdir / repo / home / user / hosts, the operator addresses, and
    the box's exact credential values (`p426_harvest.load_credentials`)."""
    import getpass
    import socket

    from bench import p426_harvest
    host = socket.gethostname()
    secrets = p426_harvest.load_credentials(environ=dict(os.environ), home=Path.home(),
                                            env_files=[p for p in (cfg.repo / ".env",) if p.exists()])
    return p426_harvest.Scrub(workdir=cfg.workdir, repo=cfg.repo, home=Path.home(), user=getpass.getuser(),
                              hosts=tuple(sorted({host, host.split(".")[0]} - {""})), emails=operator_emails(cfg),
                              secrets=secrets)


def _scrub_for(ops, cfg):
    if cfg.scrub is None:
        maker = getattr(ops, "scrub", None)
        cfg.scrub = maker() if callable(maker) else default_scrub(cfg)
    return cfg.scrub


def _gate(scrub):
    """v1.2 (Sol P6): the refusal gate built as the P426 harvest builds it (`Gate(scrub, secrets)`)."""
    from bench import p426_harvest
    return p426_harvest.Gate(scrub, getattr(scrub, "secrets", {}) or {})


def _publish(data, rel, scrub, gate, dest, compressible=False):
    """(published rel, scrubbed, published bytes, problems): the P437 scrub + piicheck (`p426_harvest._publish`), then
    `Gate.check(rel, original bytes, dest)` — credential formats / exact values over the original AND scrubbed bytes, the operator
    address, and (dest "main") any non-reserved address. Findings are pattern names only."""
    from bench import p426_harvest
    rel_out, scrubbed, published, problems = p426_harvest._publish(data, rel, scrub, compressible=compressible)
    _, kinds = gate.check(rel, data, dest)
    if kinds:
        problems.append(f"{rel}: refused by the harvest gate ({', '.join(kinds)})")
    return rel_out, scrubbed, published, problems


def _journal_recorded_absent(receipt):
    """The receipt itself records that the watcher wrote no journal (R11: a speed problem, never a usable leg)."""
    w = receipt.get("watcher") if isinstance(receipt.get("watcher"), dict) else {}
    return receipt.get("speed_valid") is not True and "no watcher report" in (w.get("problems") or [])


def valid_inventory(leg, receipt):
    """v1.2 (Sol vP1): the files a VALID leg's dossier holds — the receipt, the ladder rows, the capacity manifest, the watcher
    journal (unless the receipt records it absent on a speed-invalid leg), the KV line and the worker argv."""
    tag = f"p475-{leg}"
    names = ["receipt.json", f"capacity_ladder.{tag}.jsonl", f"capacity_ladder.{tag}.manifest.json", "kv_line.json",
             "worker_argv.json"]
    if not _journal_recorded_absent(receipt):
        names.append("watch.jsonl")
    return sorted(names)


def harvest(leg, ops, cfg):
    """Stage `benchmark/results/p475/<leg>.stage/` (receipt, ladder rows, manifest, watch ticks, KV line, worker argv), every file
    scrubbed and PII-checked, verify, then rename to `<leg>/`; full worker / router logs scrubbed to the evidence stage; then
    `LAST_LEG_END`. A finalized dossier is never redone."""
    final = cfg.dossier(leg)
    if final.exists():
        return "exists"
    receipt = read_receipt(cfg.leg_dir(leg))
    if receipt is None or receipt.get("verdict") not in ("VALID", "INVALID"):
        raise P475Error(f"{leg}: no VALID / INVALID canonical receipt to harvest")
    scrub = _scrub_for(ops, cfg)
    paths = receipt.get("paths") or {}
    sources = [("receipt.json", cfg.receipt_path(leg)), ("watch.jsonl", paths.get("watch"))]
    if paths.get("rows"):
        sources.append((Path(paths["rows"]).name, paths["rows"]))
    if paths.get("manifest"):
        sources.append((Path(paths["manifest"]).name, paths["manifest"]))
    files = {}
    for name, src in sources:
        text = _read_optional(ops, src) if src else None
        if text is not None:
            files[name] = text.encode("utf-8")
    files["kv_line.json"] = (json.dumps(receipt.get("kv_line"), indent=1, sort_keys=True) + "\n").encode()
    files["worker_argv.json"] = (json.dumps(dict(observed=receipt.get("worker_argv"), expected=receipt.get("expected_worker_argv")),
                                            indent=1) + "\n").encode()
    if "receipt.json" not in files:
        raise P475Error(f"{leg}: the canonical receipt is unreadable")
    if receipt.get("verdict") == "VALID":                        # v1.2 (Sol vP1): the exact VALID inventory, else no dossier
        missing = [n for n in valid_inventory(leg, receipt) if n not in files]
        if missing:
            raise P475Error(f"{leg}: harvest refused: VALID leg inventory missing {missing}")
    import shutil
    stage = final.with_name(f"{leg}.stage")
    if stage.exists():                                        # a crashed earlier staging of this leg: ours, never published
        shutil.rmtree(stage)
    gate = _gate(scrub)
    problems, manifest = [], dict(leg=leg, files={})
    staged = []
    for name, data in sorted(files.items()):
        rel = f"benchmark/results/p475/{leg}/{name}"
        _, scrubbed, published, found = _publish(data, rel, scrub, gate, "main")
        problems += found
        staged.append((name, data, scrubbed, published))
    ladders = [n for n, *_ in staged if n.startswith("capacity_ladder.") and n.endswith(".jsonl")]
    if receipt.get("verdict") == "VALID" and len(ladders) != 1:
        problems.append(f"{leg}: {len(ladders)} ladder file(s), need exactly 1")
    # evidence: the full worker / router logs, scrubbed (the designer commits them to `evidence`); gated as P426 gates evidence
    ev = cfg.evidence_stage(leg)
    ev_files = {}
    for key in ("worker_log", "router_log"):
        src = paths.get(key)
        text = _read_optional(ops, src) if src else None
        if text is None:
            continue
        rel, _, published, found = _publish(text.encode("utf-8"), Path(src).name, scrub, gate, "evidence", compressible=True)
        problems += [f"evidence {p}" for p in found]
        ev_files[rel] = published
    ev_reuse = False
    if ev.exists() or ev.is_symlink():                         # v1.2 (TW F2): never overwritten
        have = {p.name: p.read_bytes() for p in ev.iterdir()} if ev.is_dir() and not ev.is_symlink() else None
        if have != ev_files:
            problems.append(f"{leg}: evidence-stage/{leg} exists with other content (never overwritten; the operator decides)")
        ev_reuse = True                                        # a replay after a crash: byte-identical, nothing to write
    if problems:
        raise P475Error(f"{leg}: harvest refused: " + "; ".join(problems)[:1500])
    stage.mkdir(parents=True)
    for name, data, scrubbed, published in staged:
        (stage / name).write_bytes(published)
        manifest["files"][name] = dict(original_sha256=hashlib.sha256(data).hexdigest(),
                                       published_sha256=hashlib.sha256(published).hexdigest())
    (stage / "SCRUB_MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    for name, rec in manifest["files"].items():                 # verify before the rename
        if hashlib.sha256((stage / name).read_bytes()).hexdigest() != rec["published_sha256"]:
            raise P475Error(f"{leg}: {name}: read-back sha mismatch")
    if not ev_reuse:
        ev.parent.mkdir(parents=True, exist_ok=True)
        tmp = ev.with_name(f".{leg}.{os.getpid()}.{time.time_ns()}.tmp")
        tmp.mkdir()
        for rel, published in ev_files.items():
            (tmp / rel).write_bytes(published)
        if ev.exists() or ev.is_symlink():
            shutil.rmtree(tmp)
            raise P475Error(f"{leg}: evidence-stage/{leg} appeared during the harvest (never overwritten)")
        os.rename(tmp, ev)
    review = gate.review_emails()                              # foreign addresses in evidence: a local review list, never published
    if review:
        _atomic_json(cfg.p475 / "review" / f"{leg}.emails.json", review)
    os.rename(stage, final)                                    # R18: the single commit point
    end = ops.now()
    p = cfg.p475 / "LAST_LEG_END"                              # R8: the idle starts after the harvest
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".LAST_LEG_END.{os.getpid()}.tmp")
    tmp.write_text(f"{end}\n")
    os.replace(tmp, p)
    return "harvested"


def replay_harvests(ops, cfg):
    """R18: every VALID / INVALID canonical receipt without its finalized dossier is harvested now."""
    done, problems = [], []
    legs_root = cfg.p475 / "legs"
    if not legs_root.is_dir():
        return done, problems
    for d in sorted(legs_root.iterdir()):
        if not LEG_RE.match(d.name):
            continue
        rec = read_receipt(d)
        if rec and rec.get("verdict") in ("VALID", "INVALID") and not cfg.dossier(d.name).exists():
            try:
                harvest(d.name, ops, cfg)
                done.append(d.name)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{d.name}: {type(exc).__name__}: {exc}")
    return done, problems


# ============================================================================================ dossiers, metrics, matrix
def load_dossier(path):
    """(record, problems) of one finalized dossier: its receipt, exactly one ladder file, the SCRUB_MANIFEST shas (R19)."""
    path = Path(path)
    problems = []
    try:
        info = parse_leg(path.name)
    except ValueError as exc:
        return None, [str(exc)]
    try:
        receipt = json.loads((path / "receipt.json").read_text())
    except (OSError, ValueError):
        return None, [f"{path.name}: receipt.json unreadable"]
    listed = None
    try:
        man = json.loads((path / "SCRUB_MANIFEST.json").read_text())
        for name, rec in (man.get("files") or {}).items():
            if hashlib.sha256((path / name).read_bytes()).hexdigest() != rec.get("published_sha256"):
                problems.append(f"{path.name}: {name} differs from its SCRUB_MANIFEST sha")
        listed = set(man.get("files") or {})
    except (OSError, ValueError, AttributeError):
        problems.append(f"{path.name}: SCRUB_MANIFEST.json unreadable")
    if isinstance(receipt, dict) and receipt.get("verdict") == "VALID":    # v1.2 (Sol vP1): the exact VALID inventory
        for name in valid_inventory(path.name, receipt):
            if not (path / name).is_file():
                problems.append(f"{path.name}: VALID dossier lacks {name}")
            if listed is not None and name not in listed:
                problems.append(f"{path.name}: {name} missing from SCRUB_MANIFEST.json")
    ladders = sorted(path.glob("capacity_ladder.*.jsonl"))
    rows = []
    if len(ladders) != 1:
        if len(ladders) > 1 or receipt.get("verdict") == "VALID":
            problems.append(f"{path.name}: {len(ladders)} ladder files (exactly one required)")
    else:
        try:
            rows = _parse_jsonl(ladders[0].read_text())
        except (OSError, ValueError):
            problems.append(f"{path.name}: ladder rows unreadable")
    predictor = predictor_of(info["arm"])
    grid = SMOKE_GRID if info["block"] == "smoke" else GRID
    rung_ok = not _rows_problems(rows, grid, predictor, f"p475-{path.name}") if rows else False
    ident = receipt.get("identity_entry") if isinstance(receipt.get("identity_entry"), dict) else {}
    rec = dict(info, leg=path.name, verdict=receipt.get("verdict"), speed_valid=bool(receipt.get("speed_valid")),
               rows=rows, rungs_valid=rung_ok, speed_problems=receipt.get("speed_problems") or [],
               problems=receipt.get("problems") or [], receipt=receipt, arm_commit=ident.get("arm_commit"),
               gitlinks=ident.get("gitlinks"))
    rec["usable"] = not problems and rec["verdict"] == "VALID" and rec["speed_valid"] and rung_ok
    return rec, problems


def dossier_binding_problems(receipt, name, info, cfg):
    """v1.2 (Sol P3): a dossier's receipt is bound to this run — its leg identity, model, base, and the arm identity it recorded
    at entry (HEAD == the arm commit, parent / TQ4 head == the base, gitlinks == the base's, unchanged at exit)."""
    p = []
    if receipt.get("leg") != name:
        p.append(f"{name}: receipt leg {receipt.get('leg')!r} != the dossier's")
    for k in ("arm", "block", "attempt"):
        if receipt.get(k) != info[k]:
            p.append(f"{name}: receipt {k} {receipt.get(k)!r} != the leg name's {info[k]!r}")
    if receipt.get("model") != cfg.model:
        p.append(f"{name}: receipt model {receipt.get('model')!r} != the run's {cfg.model!r}")
    if receipt.get("base") != cfg.base:
        p.append(f"{name}: receipt base {receipt.get('base')!r} != the run's base {cfg.base!r}")
    ident = receipt.get("identity_entry")
    if not isinstance(ident, dict):
        return p + [f"{name}: no arm identity in the receipt"]
    if ident.get("base") != cfg.base:
        p.append(f"{name}: arm identity base {ident.get('base')!r} != the run's base {cfg.base!r}")
    commit = ident.get("arm_commit")
    if not commit or ident.get("head") != commit:
        p.append(f"{name}: arm identity HEAD {ident.get('head')!r} != its arm commit {commit!r}")
    if info["arm"] == BASE_ARM:
        if commit != cfg.base:
            p.append(f"{name}: TQ4 arm commit {commit!r} != the base")
    elif ident.get("parent") != cfg.base:
        p.append(f"{name}: arm commit parent {ident.get('parent')!r} != the base")
    if not ident.get("gitlinks") or ident.get("gitlinks") != ident.get("base_gitlinks"):
        p.append(f"{name}: gitlinks {ident.get('gitlinks')!r} != the base's {ident.get('base_gitlinks')!r}")
    if receipt.get("verdict") in ("VALID", "INVALID") and receipt.get("identity_exit") != ident:
        p.append(f"{name}: arm identity at exit differs from entry")
    return p


def _recorded_identity(cfg):
    try:
        return (json.loads(cfg.state_path.read_text()) or {}).get("identity") or None
    except (OSError, ValueError, AttributeError):
        return None


def _recorded_state(cfg):
    try:
        doc = json.loads(cfg.state_path.read_text())
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def recorded_block_plan(cfg, blocks=None):
    """v1.2 (Sol vP3): (measurement blocks, deciding blocks) the run recorded — `state["plan"]["blocks"]` (else `blocks`, else 2)
    and `state["deciding"]["block"]` once that block started (else none)."""
    st = _recorded_state(cfg)
    plan = st.get("plan") if isinstance(st.get("plan"), dict) else {}
    try:
        n = int(plan["blocks"]) if "blocks" in plan else int(blocks if blocks is not None else 2)
    except (TypeError, ValueError):
        n = int(blocks if blocks is not None else 2)
    dec = st.get("deciding") if isinstance(st.get("deciding"), dict) else {}
    deciding = [dec["block"]] if dec.get("started") and isinstance(dec.get("block"), int) else []
    return list(range(1, n + 1)), deciding


def load_dossiers(cfg, blocks=None):
    """(records, problems) of every finalized dossier, each validated (R19) and bound to this run (v1.2, Sol P3): its receipt's
    model / base / arm identity / leg identity, one arm commit per arm and one gitlink set across the run (and equal to the run's
    recorded identity when state.json has one); a second usable dossier for one arm / block slot refuses both."""
    records, problems = [], []
    if cfg.results.is_dir():
        for d in sorted(cfg.results.iterdir()):
            if d.is_dir() and LEG_RE.match(d.name):
                rec, found = load_dossier(d)
                if rec:
                    found = found + dossier_binding_problems(rec["receipt"], rec["leg"], parse_leg(rec["leg"]), cfg)
                    if found:
                        rec["usable"] = False
                    records.append(rec)
                problems += found
    measured, deciding = recorded_block_plan(cfg, blocks)
    for rec in records:                                        # v1.2 (Sol vP3): only the recorded plan's blocks
        b = rec["block"]
        if rec["usable"] and b != "smoke" and b not in measured and b not in deciding:
            problems.append(f"{rec['leg']}: block b{b} is not in the run's recorded plan (measurement blocks {measured}, "
                            f"deciding {deciding or 'none'})")
            rec["usable"] = False
    recorded = _recorded_identity(cfg) or {}
    commits = {}
    for rec in records:
        commits.setdefault(rec["arm"], set()).add(rec["arm_commit"])
    for arm, seen in sorted(commits.items()):
        want = (recorded.get("arm_commits") or {}).get(arm)
        if len(seen) > 1 or (want is not None and seen != {want}):
            problems.append(f"{arm}: dossiers disagree on the arm commit ({sorted(map(str, seen))}"
                            + (f", run recorded {want}" if want else "") + ")")
            for rec in records:
                if rec["arm"] == arm:
                    rec["usable"] = False
    links = {json.dumps(rec["gitlinks"], sort_keys=True) for rec in records}
    want_links = recorded.get("gitlinks")
    if len(links) > 1 or (want_links is not None and records and links != {json.dumps(want_links, sort_keys=True)}):
        problems.append(f"dossiers disagree on the gitlinks ({sorted(links)})")
        for rec in records:
            rec["usable"] = False
    slots = {}
    for rec in records:
        if rec["usable"]:
            slots.setdefault((rec["arm"], rec["block"]), []).append(rec)
    for (arm, block), recs in sorted(slots.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        if len(recs) > 1:
            problems.append(f"{arm} b{block}: two usable dossiers for one slot ({[r['leg'] for r in recs]})")
            for rec in recs:
                rec["usable"] = False
    return records, problems


def _metric(row, key):
    if key == "acceptance":
        dn, da = row.get("draft_n"), row.get("draft_n_accepted")
        return (da / dn) if isinstance(dn, (int, float)) and dn and isinstance(da, (int, float)) else None
    v = row.get(dict((m[0], m[2]) for m in METRICS)[key])
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def block_values(records):
    """{(arm, block): {ctx: {metric: value}}} from the usable (validated, speed-valid) dossiers; one leg per arm and block."""
    out = {}
    for rec in records:
        if not rec["usable"] or rec["block"] == "smoke":
            continue
        key = (rec["arm"], rec["block"])
        out[key] = {r["ctx"]: {m[0]: _metric(r, m[0]) for m in METRICS} for r in rec["rows"]}
    return out


def _ratio(a, b):
    return (a / b) if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b else None


def instability(values, blocks=(1, 2)):
    """R16 trigger per arm × rung × metric from the two blocks' ratios vs N16: a direction reversal or |r1 − r2| >
    |mean − 1| / 2. Returns {(arm, ctx, metric): {r1, r2, mean, reversal, spread, flag}}."""
    b1, b2 = blocks
    flags = {}
    for arm in ARMS:
        if arm == REFERENCE_ARM:
            continue
        for ctx in GRID:
            for m in METRICS:
                r = []
                for b in (b1, b2):
                    a = ((values.get((arm, b)) or {}).get(ctx) or {}).get(m[0])
                    n = ((values.get((REFERENCE_ARM, b)) or {}).get(ctx) or {}).get(m[0])
                    r.append(_ratio(a, n))
                if None in r:
                    continue
                mean = (r[0] + r[1]) / 2
                reversal = (r[0] > 1 and r[1] < 1) or (r[0] < 1 and r[1] > 1)
                spread = abs(r[0] - r[1]) > abs(mean - 1) / 2
                flags[(arm, ctx, m[0])] = dict(r1=r[0], r2=r[1], mean=mean, reversal=reversal, spread=spread,
                                               flag=reversal or spread)
    return flags


def _fmt(v, nd=2):
    if v is None:
        return "—"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def _all_receipts(cfg):
    out = []
    root = cfg.p475 / "legs"
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if LEG_RE.match(d.name):
                rec = read_receipt(d)
                if rec:
                    out.append(rec)
    return out


def _recorded_blocks(cfg):
    try:
        plan = (json.loads(cfg.state_path.read_text()) or {}).get("plan") or {}
        return int(plan["blocks"]) if "blocks" in plan else None
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def unresolved_flags(values, flags, deciding):
    """v1.2 (TW F6): the flagged (arm, ctx, metric) cells no deciding block resolved (no deciding value for the arm and the
    reference at that rung)."""
    out = []
    for (arm, ctx, key), fl in sorted(flags.items()):
        if not fl["flag"]:
            continue
        seen = any(((values.get((arm, b)) or {}).get(ctx) or {}).get(key) is not None
                   and ((values.get((REFERENCE_ARM, b)) or {}).get(ctx) or {}).get(key) is not None for b in deciding)
        if not seen:
            out.append((arm, ctx, key))
    return out


def _metric_cells_missing(values, arm, b):
    """Defensive (v1.2, Sol P4): every rung of the slot carries every tradeoff metric (acceptance on ON arms only)."""
    row = values.get((arm, b)) or {}
    keys = [m[0] for m in METRICS if m[0] != "acceptance" or predictor_of(arm) == "on"]
    return any(row.get(ctx, {}).get(k) is None for ctx in GRID for k in keys)


def matrix(cfg, blocks=None):
    """Write the generated table from harvested dossiers only; MATRIX.<pick>.md when every arm has two speed-valid legs with
    valid rungs, else MATRIX.<pick>.PARTIAL.md — exactly one of the two exists afterwards (v1.2, Sol P8). Returns (exit code,
    path): nonzero when partial or when an instability flag is unresolved (v1.2, Sol vP4). `blocks` defaults to the run's
    recorded block plan (v1.2, Sol P7), else 2; only the recorded plan's blocks and deciding block are accepted (Sol vP3)."""
    records, problems = load_dossiers(cfg, blocks)
    values = block_values(records)
    if blocks is None:
        blocks = _recorded_blocks(cfg) or 2
    blocks = max(2, int(blocks))                                  # R20: two speed-valid legs per arm, always
    order_blocks = list(range(1, blocks + 1))
    _, recorded_deciding = recorded_block_plan(cfg, blocks)       # v1.2 (Sol vP3): the recorded deciding block only
    deciding = sorted({b for (_, b) in values if b in recorded_deciding and b not in order_blocks})
    missing = [f"{arm} b{b}" for arm in ARMS for b in order_blocks
               if set(((values.get((arm, b)) or {}).keys())) != set(GRID) or _metric_cells_missing(values, arm, b)]
    refused = [a for a in ARMS if any((read_preflight(cfg, a, k) or {}).get("status") == "REFUSED" for k in kinds_for(a))]
    complete = not missing and not problems and not refused
    flags = instability(values, (1, 2))
    unresolved = set(unresolved_flags(values, flags, deciding))
    lines = [f"# P475 KV-cache format matrix — {cfg.model} — one pick (partial matrix, P475 v4)", "",
             "GENERATED by `python -m bench.p475_kv matrix` from the harvested dossiers under `benchmark/results/p475/`; never "
             "hand-edited.", "",
             "Descriptive (two order-balanced speed-valid legs per arm, no interval claimed). Ratios are vs N16 within the "
             "same block; a deciding block is its own column and never enters the two-block mean or ratios.", ""]
    if not complete:
        lines += ["**PARTIAL**: " + "; ".join(([f"missing speed-valid legs with valid rungs: {missing}"] if missing else [])
                                             + ([f"refused arms: {refused}"] if refused else [])
                                             + ([f"dossier problems: {problems}"] if problems else [])), ""]
    if unresolved:
        lines += [f"**UNRESOLVED instability** (no deciding block measured it: --max-deciding spent or 0): "
                  f"{[f'{a} {c} {k}' for a, c, k in sorted(unresolved)]}", ""]
    for key, title, _ in METRICS:
        lines += [f"## {title}", ""]
        head = "| arm | rung | b1 | b2 | mean | " + "".join(f"b{d} (deciding) | " for d in deciding) + \
               "b1 / N16 | b2 / N16 | instability |"
        lines += [head, "|" + "---|" * (head.count("|") - 1)]
        for arm in ARMS:
            if key == "acceptance" and predictor_of(arm) == "off":
                continue
            for ctx in GRID:
                v = [((values.get((arm, b)) or {}).get(ctx) or {}).get(key) for b in (1, 2)]
                mean = (v[0] + v[1]) / 2 if None not in v else None
                dec = [((values.get((arm, b)) or {}).get(ctx) or {}).get(key) for b in deciding]
                fl = flags.get((arm, ctx, key))
                r = [_ratio(v[i], ((values.get((REFERENCE_ARM, b)) or {}).get(ctx) or {}).get(key)) for i, b in enumerate((1, 2))]
                ftxt = "—" if arm == REFERENCE_ARM or fl is None else (
                    ("REVERSAL " if fl["reversal"] else "") + ("SPREAD " if fl["spread"] else "")
                    + ("UNRESOLVED" if (arm, ctx, key) in unresolved else "") or "stable")
                nd = 4 if key == "acceptance" else 2
                lines.append(f"| {arm} | {ctx} | {_fmt(v[0], nd)} | {_fmt(v[1], nd)} | {_fmt(mean, nd)} | "
                             + "".join(f"{_fmt(x, nd)} | " for x in dec)
                             + f"{'—' if arm == REFERENCE_ARM else _fmt(r[0], 3)} | {'—' if arm == REFERENCE_ARM else _fmt(r[1], 3)} | "
                             f"{ftxt.strip()} |")
        lines.append("")
    receipts = _all_receipts(cfg)
    replaced = [r["leg"] for r in receipts if r.get("verdict") == "VALID" and not r.get("speed_valid")]
    invalid = [r["leg"] for r in receipts if r.get("verdict") == "INVALID"]
    not_started = [r["leg"] for r in receipts if r.get("verdict") == "NOT_STARTED"]
    lines += ["## Legs", "",
              f"- used (speed-valid, valid rungs): {sorted(r['leg'] for r in records if r['usable'])}",
              f"- replaced (speed-invalid): {replaced}", f"- INVALID: {invalid}",
              f"- NOT_STARTED (never evidence): {not_started}", f"- refused arms (preflight): {refused}",
              f"- deciding blocks: {['b%d' % d for d in deciding] or 'none'}", ""]
    canonical, partial = f"MATRIX.{cfg.model}.md", f"MATRIX.{cfg.model}.PARTIAL.md"
    name, other = (canonical, partial) if complete else (partial, canonical)
    out = cfg.results / name
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{name}.{os.getpid()}.tmp")
    tmp.write_text("\n".join(lines))
    os.replace(tmp, out)
    (cfg.results / other).unlink(missing_ok=True)              # v1.2 (Sol P8): never a stale table beside the current one
    return (0 if complete and not unresolved else 1), out      # v1.2 (Sol vP4): an unresolved flag exits nonzero; naming unchanged


# ============================================================================================ run control
def leg_status(cfg, arm, block):
    """From the canonical receipts of (arm, block): "valid" (a VALID speed-valid leg), "invalid", "speed_invalid", or "none";
    plus the next attempt number."""
    root = cfg.p475 / "legs"
    verdicts, last = [], 0
    if root.is_dir():
        for d in root.iterdir():
            try:
                info = parse_leg(d.name)
            except ValueError:
                continue
            if info["arm"] != arm or info["block"] != block:
                continue
            last = max(last, info["attempt"])
            rec = read_receipt(d)
            if rec:
                verdicts.append((rec.get("verdict"), bool(rec.get("speed_valid"))))
    if ("VALID", True) in verdicts:
        status = "valid"
    elif any(v == "INVALID" for v, _ in verdicts):
        status = "invalid"
    elif any(v == "VALID" for v, _ in verdicts):
        status = "speed_invalid"
    else:
        status = "none"
    return status, last + 1


def load_state(cfg):
    try:
        doc = json.loads(cfg.state_path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise P475Error(f"state.json unreadable ({type(exc).__name__})") from None
    return doc


def save_state(cfg, state):
    _atomic_json(cfg.state_path, {k: v for k, v in state.items() if not k.startswith("_")})    # `_…`: this invocation only


CAP_NAMES = ("max_replacements", "max_not_started", "max_deciding")     # `--blocks` is the recorded plan, not a cap (v1.2)


def resolve_caps(state, caps):
    """R13: caps are monotonic on resume — a resumed run may keep or raise a recorded cap, never lower it."""
    old = (state or {}).get("caps") or {}
    lowered = [f"{k} {caps[k]} < recorded {old[k]}" for k in CAP_NAMES if k in old and caps[k] < old[k]]
    if lowered:
        raise P475Error("caps are monotonic on resume: " + "; ".join(lowered))
    return dict(caps)


class _Stop(Exception):
    def __init__(self, why):
        super().__init__(why)
        self.why = why


def _wait_idle(ops, cfg):
    last = last_leg_end(ops, cfg)
    if last is not None:
        remaining = IDLE_S - (ops.now() - last)
        if remaining > 0:
            ops.sleep(remaining)


def _attempt(arm, block, ops, cfg, state, log):
    """Run legs of (arm, block) until one starts (NOT_STARTED retried after its own 600 s, bounded, R14). Returns the receipt."""
    while True:
        _, n = leg_status(cfg, arm, block)
        leg = leg_name(arm, block, n)
        if block != "smoke" and "plan" not in state:              # v1.2 (Sol P7): persisted at the first measured leg
            state["plan"] = dict(state.pop("_pending_plan"))
            save_state(cfg, state)
        _wait_idle(ops, cfg)
        log(f"leg {leg}: start")
        cfg.run_identity = state.get("identity")
        receipt = run_leg(leg, arm, ops, cfg)
        state.setdefault("legs", []).append(dict(leg=leg, verdict=receipt.get("verdict"), speed_valid=receipt.get("speed_valid"),
                                                  harvest=receipt.get("_harvest")))
        if receipt.get("verdict") != "NOT_STARTED":               # v1.2 (Sol P3): the run's identity, from its first legs
            ident = receipt.get("identity_entry") or {}
            rec = state.setdefault("identity", {})
            rec.setdefault("arm_commits", {}).setdefault(arm, ident.get("arm_commit"))
            rec.setdefault("gitlinks", ident.get("gitlinks"))
        log(f"leg {leg}: {receipt.get('verdict')} speed_valid={receipt.get('speed_valid')} problems={receipt.get('problems')} "
            f"speed_problems={receipt.get('speed_problems')} harvest={receipt.get('_harvest')}")
        if receipt.get("verdict") != "NOT_STARTED":
            save_state(cfg, state)
            if receipt.get("_harvest") not in ("harvested", "exists"):
                raise _Stop(f"{leg}: {receipt.get('_harvest')}")
            if receipt.get("verdict") == "INVALID":
                raise _Stop(f"{leg}: INVALID ({'; '.join(receipt.get('problems') or [])[:400]})")
            return receipt
        state["used"]["not_started"] += 1
        save_state(cfg, state)
        if state["used"]["not_started"] > state["caps"]["max_not_started"]:
            raise _Stop(f"{leg}: NOT_STARTED and the cap --max-not-started {state['caps']['max_not_started']} is exhausted")
        ops.sleep(IDLE_S)


def _ensure_preflight(arm, ops, cfg, state, log):
    """The arm's OFF preflight, then (MTP-ON arms, C301) its ON engagement check; NOT_STARTED (incl. a record of another base,
    S18-P3) stops the run, a REFUSED one refuses the arm."""
    for kind in kinds_for(arm):
        what = "preflight" if kind == "off" else "engagement check"
        rec = read_preflight(cfg, arm, kind)
        if not rec or rec.get("status") not in ("PASS", "REFUSED") or rec.get("base") != cfg.base:
            log(f"{what} {arm}")
            rec = preflight(arm, ops, cfg, kind=kind)
        if rec.get("status") == "NOT_STARTED":
            raise _Stop(f"{what} {arm} NOT_STARTED: {(rec.get('not_started') or [{}])[-1].get('reason')}")
        if rec.get("status") != "PASS":
            if arm not in state["refused_arms"]:
                state["refused_arms"].append(arm)
            save_state(cfg, state)
            log(f"arm {arm} REFUSED by its {what}; the run continues with the others")
            return False
    return True


def _run_block(block, ops, cfg, state, log, order=None):
    unfilled = []
    order = order or block_order(block)
    for arm in order:
        if arm in state["refused_arms"] or not _ensure_preflight(arm, ops, cfg, state, log):
            continue
        status, _ = leg_status(cfg, arm, block)
        if status == "invalid":
            raise _Stop(f"{arm} b{block}: an INVALID leg stands (the run stopped there; operator decision)")
        if status == "none":
            _attempt(arm, block, ops, cfg, state, log)
    queue = [a for a in order if a not in state["refused_arms"] and leg_status(cfg, a, block)[0] == "speed_invalid"]
    while queue:                                                  # R13: after the block's ordered legs, block order kept
        arm = queue.pop(0)
        if state["used"]["replacements"] >= state["caps"]["max_replacements"]:
            unfilled.append(f"{arm} b{block}")
            continue
        state["used"]["replacements"] += 1
        save_state(cfg, state)
        _attempt(arm, block, ops, cfg, state, log)
        if leg_status(cfg, arm, block)[0] == "speed_invalid":
            queue.append(arm)
    return unfilled


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def resolve_base(base, ops, repo):
    """C296 (P655): `--base` as the full commit sha it names (`rev-parse --verify <base>^{commit}`); unresolvable refuses.
    Without an `ops` only a full sha is accepted."""
    if ops is None:
        if not FULL_SHA.match(base):
            raise P475Error(f"--base {base!r} is not a full commit sha (no git to resolve it)")
        return base
    try:
        full = ops.git(repo, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").strip()
    except Exception as exc:  # noqa: BLE001 — rc != 0: no such commit
        raise P475Error(f"--base {base!r} does not name a commit ({type(exc).__name__}: {exc})") from None
    if not FULL_SHA.match(full):
        raise P475Error(f"--base {base!r} resolved to {full!r}, not a full commit sha")
    return full


def config_from_args(args, ops=None, default_head=False):
    workdir = getattr(args, "workdir", None) or os.environ.get("STACK_WORKDIR")
    if not workdir:
        raise P475Error("STACK_WORKDIR is not set (and no --workdir)")
    repo = Path(getattr(args, "repo", None) or Path(__file__).resolve().parents[2])
    p475 = Path(workdir) / P475_DIR
    base = getattr(args, "base", None)
    if base:
        base = resolve_base(base, ops, repo)
    recorded = None
    try:
        recorded = json.loads((p475 / "state.json").read_text()).get("base")
    except (OSError, ValueError, AttributeError):
        pass
    if base and recorded and base != recorded:
        raise P475Error(f"--base {base} != the recorded base {recorded}")
    base = base or recorded
    if not base:
        if ops is None or not default_head:
            raise P475Error("no base commit: pass --base or run prepare")
        base = ops.git(repo, "rev-parse", "HEAD").strip()
    expected = default_expected()
    for spec in getattr(args, "expected_rung_seconds", None) or []:
        arm, _, vals = spec.partition("=")
        xs = [float(x) for x in vals.split(",")]
        if arm not in ARMS or len(xs) != len(GRID) or any(not (x > 0) for x in xs):
            raise P475Error(f"--expected-rung-seconds {spec!r}: ARM=<{len(GRID)} positive seconds>")
        expected[arm] = xs
    return Config(repo=repo, workdir=Path(workdir), base=base, expected=expected,
                  watch_interval=float(getattr(args, "watch_interval", None) or TICK_S),
                  max_preflight=int(getattr(args, "max_preflight", None) if getattr(args, "max_preflight", None) is not None else 2),
                  production_ref=getattr(args, "production_ref", None),
                  operator_emails=tuple(getattr(args, "operator_email", None) or ()))


def _logger(cfg):
    path = cfg.p475 / "RUNLOG.md"

    def log(msg):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
        print(line, flush=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write("- " + line + "\n")
    return log


def run(args, ops) -> int:
    """`run`: plan -> legs -> replacements -> deciding block (resumable from state.json). 0 only for a complete matrix."""
    try:
        cfg = config_from_args(args, ops)
    except P475Error as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    log = _logger(cfg)
    smoke = bool(getattr(args, "smoke", False))
    blocks = int(getattr(args, "blocks", 2))
    caps = dict(max_replacements=int(getattr(args, "max_replacements", 4)), max_not_started=int(getattr(args, "max_not_started", 3)),
                max_deciding=int(getattr(args, "max_deciding", 1)))
    try:
        state = load_state(cfg)
        caps = resolve_caps(state, caps)
        plan = (state or {}).get("plan")
        if not smoke:                                             # v1.2 (Sol P7): the block plan is fixed once a leg exists
            if plan and int(plan.get("blocks", -1)) != blocks:
                raise P475Error(f"--blocks {blocks} != the run's recorded block plan {plan} (fixed once a leg exists)")
            if not plan and _measured_legs_exist(cfg):
                raise P475Error("measured legs exist but state.json records no block plan (the operator decides)")
    except P475Error as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    state = state or dict(version=1, model=cfg.model, base=cfg.base, used=dict(replacements=0, not_started=0, deciding=0),
                          refused_arms=[], legs=[])
    state.update(base=cfg.base, caps=caps)
    state.setdefault("used", dict(replacements=0, not_started=0, deciding=0))
    state.setdefault("refused_arms", [])
    if "plan" not in state:
        state["_pending_plan"] = dict(blocks=blocks, deciding_block=blocks + 1)
    save_state(cfg, state)
    cfg.run_identity = state.get("identity")
    replayed, harvest_problems = replay_harvests(ops, cfg)
    if replayed:
        log(f"resume: harvested {replayed}")
    if harvest_problems:
        log(f"STOP: harvest replay failed: {harvest_problems}")
        return 1
    if smoke:
        return _run_smoke(ops, cfg, state, log)
    unfilled, stopped, unresolved = [], None, []
    try:
        for block in range(1, blocks + 1):
            unfilled += _run_block(block, ops, cfg, state, log)
        if blocks >= 2:
            unresolved = _deciding_step(ops, cfg, state, caps, log, unfilled)
    except _Stop as stop:
        stopped = stop.why
        log(f"STOP: {stopped}")
    save_state(cfg, state)
    rc, path = matrix(cfg, blocks=blocks)
    log(f"matrix -> {path.name} (rc {rc}); refused={state['refused_arms']} unfilled={unfilled} stopped={stopped} "
        f"unresolved_instability={unresolved}")
    ok = rc == 0 and not stopped and not unfilled and not state["refused_arms"] and not unresolved
    return 0 if ok else 1


def _measured_legs_exist(cfg):
    root = cfg.p475 / "legs"
    if not root.is_dir():
        return False
    for d in root.iterdir():
        try:
            if parse_leg(d.name)["block"] != "smoke":
                return True
        except ValueError:
            continue
    return False


def _deciding_step(ops, cfg, state, caps, log, unfilled):
    """R16 with the deciding block's identity / completion persisted (v1.2, Sol P7 / GLM F5): a completed deciding block is never
    re-entered. Returns the flags left unresolved (v1.2, TW F6: the run then exits nonzero)."""
    records, problems = load_dossiers(cfg)
    if problems:
        raise _Stop(f"dossier problems before the instability rule: {problems[:4]}")
    flags = instability(block_values(records))
    flagged = [k for k, v in flags.items() if v["flag"]]
    state["instability"] = [list(map(str, k)) for k in flagged]
    plan = state.get("plan") or state.get("_pending_plan")
    dec = state.setdefault("deciding", dict(block=plan["deciding_block"], started=False, complete=False))
    if flagged and not dec["complete"] and (dec["started"] or state["used"]["deciding"] < caps["max_deciding"]):
        if not dec["started"]:
            state["used"]["deciding"] += 1
            dec["started"] = True
        save_state(cfg, state)
        log(f"instability {flagged[:6]}… -> deciding block b{dec['block']}")
        left = _run_block(dec["block"], ops, cfg, state, log, order=block_order(1))
        unfilled += left
        if not left:
            dec["complete"] = True
        save_state(cfg, state)
        records, _ = load_dossiers(cfg)
    values = block_values(records)
    deciding = [dec["block"]] if dec["started"] else []
    unresolved = unresolved_flags(values, instability(values), deciding)
    if unresolved:
        log(f"UNRESOLVED instability (no deciding block measured it): {unresolved[:6]}")
    return unresolved


def _run_smoke(ops, cfg, state, log):
    """`run --smoke` (v1.2): `u4-n16-smoke` then `u4-tq4-smoke` on the 8192 rung; a standing INVALID smoke leg stops the run, also
    on resume (v1.2, TW F1). No matrix."""
    try:
        for arm in SMOKE_ARMS:
            if not _ensure_preflight(arm, ops, cfg, state, log):
                raise _Stop(f"{arm}: the smoke arm's preflight is not PASS")
            status, _ = leg_status(cfg, arm, "smoke")
            if status == "invalid":
                raise _Stop(f"{arm} smoke: an INVALID leg stands (the run stopped there; operator decision)")
            if status == "valid":
                continue
            _attempt(arm, "smoke", ops, cfg, state, log)
    except _Stop as stop:
        log(f"STOP: {stop.why}")
        save_state(cfg, state)
        return 1
    save_state(cfg, state)
    return 0


# ============================================================================================ RealOps
class RealOps:
    """The box: pmset, lsof / ps, the chain lease, git, the mlx-serve router (ChainOps), processes, the watcher."""

    def __init__(self, workdir, repo=None):
        self.wd = Path(workdir)
        self.repo = Path(repo) if repo else Path(__file__).resolve().parents[2]
        self._procs = {}
        self._log_dir = self.wd / P475_DIR / "spawn-logs"

    def _chain(self, wt, registry=None, predictor="off", env_source=None):
        from bench import chain_ops
        return _P475Chain(wt, self.wd, str(registry or Path(wt) / REGISTRY),
                          chain_ops.RunLog(self.wd / P475_DIR / "router.log"), predictor=predictor,
                          registry=registry, env_source=env_source if env_source is not None else strip_kv(dict(os.environ)),
                          out_root=self.wd / P475_DIR / "router")

    def power(self):
        from bench.chain_ops import default_sh, parse_power
        p = parse_power(default_sh(["pmset", "-g", "ac"]).stdout, default_sh(["pmset", "-g", "batt"]).stdout)
        return dict(watts=p["watts"], volts=p["volts"], battery=p["batt"])

    def port_listener(self, port):
        ls = self._chain(self.repo).listeners(port)
        return ls[0] if len(ls) == 1 else (ls or None)

    def busy(self):
        from bench.chain_ops import default_sh
        found = list(self._chain(self.repo).busy_procs())
        me = os.getpid()
        for line in default_sh(["ps", "-axo", "pid=,command="]).stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[0].isdigit() and int(parts[0]) != me and "run_capacity" in parts[1] \
                    and line.strip() not in found:
                found.append(line.strip())
        return found

    @contextlib.contextmanager
    def lease(self):
        from bench import p426_locks
        held = p426_locks.acquire("chain", self.wd)
        try:
            yield held
        finally:
            held.release()

    def now(self):
        return time.time()

    def monotonic(self):
        return time.monotonic()

    def sleep(self, s):
        time.sleep(max(0.0, s))

    def worktree_state(self, wt):
        return self._chain(wt).worktree_state(wt)

    def git(self, wt, *args):
        import subprocess
        r = subprocess.run(["git", "-C", str(wt), *map(str, args)], capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"git {args[0] if args else ''} failed in {Path(wt).name} (rc {r.returncode})")
        return r.stdout

    def stack(self, wt, registry, predictor):
        return self._chain(wt, registry, predictor)

    def proc_alive(self, pid, create_time):
        from bench.chain_ops import default_create_time
        try:
            return default_create_time(int(pid)) == create_time
        except Exception:  # noqa: BLE001
            return False

    def proc_env(self, pid):
        return self._chain(self.repo).proc_environ(pid)

    def spawn(self, argv, env, cwd, session=True):
        """v1.2 (Sol vP2): the new process group is captured at spawn (`start_new_session`: pgid == pid); if anything after
        `Popen` raises (create-time capture included) the group is signalled TERM -> KILL and reaped, then the error re-raised."""
        import subprocess
        from bench import chain_ops
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log = open(self._log_dir / f"{time.time_ns()}.log", "ab")
        try:
            p = subprocess.Popen([str(a) for a in argv], env=env, cwd=cwd, stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=session)
        finally:
            log.close()
        pgid = p.pid if session else None                       # never the caller's own group
        try:
            rec = dict(pid=p.pid, create_time=chain_ops.default_create_time(p.pid))
            self._procs[p.pid] = p
            return rec
        except BaseException:
            self._procs.pop(p.pid, None)
            self._kill_spawned(p, pgid)
            raise

    def _kill_spawned(self, p, pgid, grace=10):
        """TERM -> KILL the spawned group (or the leader alone without a session), reap the leader, poll the group empty.
        Best effort: a cleanup failure never masks the error that triggered it."""
        import subprocess
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                if pgid is not None:
                    os.killpg(pgid, sig)
                else:
                    p.send_signal(sig)
            except ProcessLookupError:
                pass
            except Exception:  # noqa: BLE001
                continue
            try:
                p.wait(timeout=grace)
                leader_gone = True
            except subprocess.TimeoutExpired:
                leader_gone = False
            except Exception:  # noqa: BLE001
                leader_gone = False
            group_gone = True
            if pgid is not None:
                for _ in range(grace):
                    try:
                        group_gone = not self.group_alive(pgid)
                    except Exception:  # noqa: BLE001
                        group_gone = False
                    if group_gone:
                        break
                    time.sleep(1)
            if leader_gone and group_gone:
                return

    def wait(self, proc, timeout):
        import subprocess
        p = self._procs.get(proc["pid"])
        if p is None:
            return None
        try:
            return p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def signal_group(self, proc, sig):
        # a pid is never reused while a process group of that id exists, so a live group is still ours after the leader exits
        if self.proc_alive(proc["pid"], proc["create_time"]) or self.group_alive(int(proc["pid"])):
            os.killpg(int(proc["pid"]), sig)

    def group_alive(self, pgid):
        """Any non-zombie process whose process group is `pgid` (`ps -axo pid=,pgid=,stat=`); a failing `ps` raises."""
        from bench import chain_ops
        r = chain_ops.default_sh(["ps", "-axo", "pid=,pgid=,stat="])
        if r.returncode != 0:
            raise RuntimeError(f"ps exited {r.returncode}")
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1].isdigit() and int(parts[1]) == int(pgid) and not parts[2].startswith("Z"):
                return True
        return False

    def start_watch(self, argv):
        import subprocess
        script = Path(argv[1])
        bench_dir = script.parents[1]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in (str(bench_dir), os.environ.get("PYTHONPATH")) if p))
        p = subprocess.Popen([str(a) for a in argv], env=env, cwd=str(bench_dir), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        interval = float(argv[argv.index("--interval") + 1]) if "--interval" in argv else TICK_S
        time.sleep(2.0)
        if p.poll() is not None:
            raise RuntimeError(f"watcher exited at start (rc {p.returncode})")
        return dict(proc=p, interval=interval)

    def stop_watch(self, handle):
        import subprocess
        p = handle["proc"]
        try:                                           # the watcher finalizes itself once it sees the driver gone
            p.wait(timeout=handle["interval"] + 60)
            return None
        except subprocess.TimeoutExpired:
            p.terminate()
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=10)
        return None

    def read_text(self, path):
        return Path(path).read_text(errors="replace")

    def pmset_log(self, start, end):
        import subprocess
        r = subprocess.run(["pmset", "-g", "log"], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"pmset -g log exited {r.returncode}")
        return r.stdout

    def run(self, argv, cwd, env, timeout, grace=10):
        """`subprocess.run` semantics (CompletedProcess; TimeoutExpired on timeout), but the child leads its own process
        group and on a timeout or an interrupt the whole group is signalled TERM -> KILL and reaped before returning
        (C296 / P656 5: a timed-out `qualify` left its `worker.py` behind). The TimeoutExpired carries the output so far."""
        import subprocess
        p = subprocess.Popen([str(a) for a in argv], cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            out, err = p.communicate(timeout=timeout)
        except BaseException as exc:
            self._kill_spawned(p, p.pid, grace=grace)
            try:
                out, err = p.communicate(timeout=grace)
            except Exception:  # noqa: BLE001
                out, err = "", ""
            if isinstance(exc, subprocess.TimeoutExpired):
                raise subprocess.TimeoutExpired(p.args, timeout, output=out, stderr=err) from None
            raise
        return subprocess.CompletedProcess(p.args, p.returncode, out, err)


def _p475_chain_class():
    from bench import chain_ops

    class P475Chain(chain_ops.ChainOps):
        """ChainOps for one arm worktree with every KV / TQ name stripped from the router environment (R2), the worker argv
        read as the process's own argv (the console script's shebang interpreter dropped) and the unload outcome kept."""

        _unload_ok = True

        def env_base(self):
            return strip_kv(super().env_base())

        def load(self, model):
            from bench.p426_receipt import shebang_interpreter
            ident = super().load(model)
            argv = [str(t) for t in self.proc_argv(ident["pid"])]
            if len(argv) > 1 and shebang_interpreter(argv[1]) == argv[0]:
                argv = argv[1:]
            return dict(ident, cmdline=argv, ps_cmdline=ident.get("cmdline"))

        def unload(self, model):
            ok = super().unload(model)
            self._unload_ok = bool(ok)
            return ok

        def unload_ok(self):
            return self._unload_ok and self.loaded is None

    return P475Chain


def _P475Chain(*a, **kw):
    return _p475_chain_class()(*a, **kw)


# ============================================================================================ CLI
def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="bench.p475_kv", description=__doc__.splitlines()[0])
    ap.add_argument("--workdir", help="$STACK_WORKDIR (default: the environment's)")
    ap.add_argument("--repo", help="the stack main checkout (default: this file's repo)")
    ap.add_argument("--base", help="the base commit (default: recorded at prepare, else the repo HEAD)")
    ap.add_argument("--expected-rung-seconds", action="append", metavar="ARM=a,b,c,d")
    ap.add_argument("--watch-interval", type=float, default=TICK_S)
    ap.add_argument("--production-ref")
    ap.add_argument("--operator-email", action="append", default=[],
                    help="an address the harvest gate refuses (repeatable; default: the main checkout's git user.email)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    pf = sub.add_parser("preflight")
    pf.add_argument("--arm", required=True, choices=ARMS)
    pf.add_argument("--max-preflight", type=int, default=2)
    pf.add_argument("--engagement", action="store_true",
                    help="the ON engagement check of an MTP-ON arm (qualify --predictor on --engagement-only; C301)")
    r = sub.add_parser("run")
    r.add_argument("--blocks", type=int, default=2)
    r.add_argument("--max-replacements", type=int, default=4)
    r.add_argument("--max-not-started", type=int, default=3)
    r.add_argument("--max-deciding", type=int, default=1)
    r.add_argument("--max-preflight", type=int, default=2)
    r.add_argument("--smoke", action="store_true")
    sub.add_parser("matrix")
    args = ap.parse_args(argv)
    for name in ("blocks", "max_replacements", "max_not_started", "max_deciding", "max_preflight"):
        v = getattr(args, name, None)
        if v is not None and v < (1 if name == "blocks" else 0):
            ap.error(f"--{name.replace('_', '-')} must be {'>= 1' if name == 'blocks' else '>= 0'}")
    return args


def main(argv=None, ops=None) -> int:
    args = parse_args(argv)
    workdir = args.workdir or os.environ.get("STACK_WORKDIR")
    if not workdir:
        print("REFUSED: STACK_WORKDIR is not set", file=sys.stderr)
        return 2
    ops = ops or RealOps(workdir, args.repo)
    if args.cmd == "run":
        return run(args, ops)
    try:
        cfg = config_from_args(args, ops, default_head=args.cmd == "prepare")
    except P475Error as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    if args.cmd == "prepare":
        state = load_state(cfg) or dict(version=1, model=cfg.model, used=dict(replacements=0, not_started=0, deciding=0),
                                        refused_arms=[], legs=[])
        state["base"] = cfg.base
        save_state(cfg, state)
        problems = prepare(ops, cfg)
        for p in problems:
            print(f"PROBLEM: {p}", file=sys.stderr)
        return 1 if problems else 0
    if args.cmd == "preflight":
        kind = "engagement" if getattr(args, "engagement", False) else "off"
        try:
            rec = preflight(args.arm, ops, cfg, max_retries=args.max_preflight, kind=kind)
        except P475Error as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(dict(arm=args.arm, kind=kind, status=rec["status"], attempts=len(rec["attempts"]))))
        return 0 if rec["status"] == "PASS" else 1
    rc, path = matrix(cfg)
    print(f"{path.name} (rc {rc})")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
