"""Shared fake for the P475 stage-1 tests: a `World` (clock, event log, process table, git facts, driver / watcher simulation)
and `FakeOps` implementing exactly the contract's "Ops interface" table (docs/specs/p475-stage1-contract.md v1.1).

Formats reproduced, never invented: the `KV cache resolved:` line (mlx_vlm/server/app.py), the worker argv (mlx-serve
`process_manager._build_command`), `pmset -g ac / batt / log` text (`chain_ops.parse_power`, qualify `battery_intervals`), the
server timings keys (`mlx_vlm/server/schemas.py`), the watcher's JSON ticks (`bench_watch.run_p426`).

Every guess about an UNSPECIFIED shape sits in this file or in `helpers.py` (one place to adjust); see the report's ambiguity list.
Knobs on `World` may be plain values or callables `f(arm, leg_no)` (leg_no = the 1-based count of `stack()` calls).
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import re
import shlex
import signal
import subprocess
from pathlib import Path
from types import SimpleNamespace

PICK = "Qwen3.8-27B-mlx-uniform-4bit"
DRAFTER = f"caslca/{PICK}-mtp-drafter"
ARMS = ("N16", "AF8", "TQ8", "AF4", "TQ4", "TQ4-OFF")
FULL_GRID = (8192, 131072, 196608, 260096)
EXPECTED_RUNG_S = (60.0, 400.0, 800.0, 1500.0)           # grid order; sum 2760 s
OPERATOR_EMAIL = "op.tester@opdomain.io"
GOOD_POWER ={"watts": 140.0, "volts": 28.0, "battery": 80}
KV_NAMES = ("KV_BITS", "KV_GROUP_SIZE", "KV_KEY_BITS", "KV_VALUE_BITS", "KV_KEY_SCHEME", "KV_VALUE_SCHEME",
            "KV_QUANT_SCHEME", "KV_PREALLOC_TOKENS", "TQ_KV_QUANT_MODE", "TQ_PREFILL_IMPL", "TQ_FUSED_PREFILL",
            "TQ_DECODE_2PASS_LEGACY", "KV_SOMETHING_NEW", "TQ_SOMETHING_NEW")

# arm -> (kv_bits in the entry, kv_quant_scheme in the entry or None, predictor)
ARM_FACTS = {
    # v1.2 (Sol P2): N16 = `kv_bits: 0` only; the base's scheme line stays
    "N16": (0, "turboquant", "mtp"), "AF8": (8, "uniform", "mtp"), "TQ8": (8, "turboquant", "mtp"),
    "AF4": (4, "uniform", "mtp"), "TQ4": (4, "turboquant", "mtp"), "TQ4-OFF": (4, "turboquant", "off"),
}
# metric multipliers vs N16 (peak GB offset, prefill x, decode x) so a default matrix has distinct, ordered values
ARM_METRIC = {"N16": (0.0, 1.00, 1.00), "AF8": (-3.0, 0.90, 0.95), "TQ8": (-3.5, 0.80, 0.90),
              "AF4": (-5.0, 0.85, 0.92), "TQ4": (-5.5, 0.70, 0.85), "TQ4-OFF": (-5.5, 0.70, 0.50)}

BASE_REGISTRY = f"""models:
  - name: {PICK}
    type: vision
    hf_path: caslca/{PICK}
    max_kv_cache_size: 262144
    kv_prealloc_tokens: 262144
    kv_quant_scheme: turboquant
    kv_bits: 4
    quantized_kv_start: 0
    draft_kind: mtp
    draft_model: {DRAFTER}
    generation_defaults:
      temperature: 0.6
      top_p: 0.95
"""

GEN_DEFAULTS = {"temperature": 0.6, "top_p": 0.95}

# `uv pip freeze` of an arm `.venv` as uv prints it (C296 / P656 3): pins, the two editable forks and the stack project
FREEZE = """accelerate==1.10.0
mlx==0.32.4
mlx-audio==0.6.2
mlx-lm==0.31.3
mlx-metal==0.32.4
-e file://{wt}/src/mlx-serve
-e file://{wt}/src/mlx-vlm
mlx-local-stack @ file://{wt}
transformers==5.15.0
"""


class Cfg(dict):
    """Attribute-or-key access (the contract does not say which `cfg` is)."""
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k) from None


class ArgList(list):
    """The CLI tokens AND their parsed attributes (the contract does not say whether `run(args, ops)` takes a Namespace or tokens)."""
    def __init__(self, tokens, **attrs):
        super().__init__(tokens)
        self.__dict__.update(attrs)


def arm_lower(arm):
    return arm.lower()


def leg_name(arm, block, attempt=1):
    return f"u4-{arm_lower(arm)}-b{block}.a{attempt}"


# ---------------------------------------------------------------------------------------------------- fixed formats
def pmset_texts(watts=140, volts=28, batt=80):
    if watts is None or volts is None:                     # C302: on battery, as `pmset -g ac` / `-g batt` print it
        return ("No adapter attached.\n",
                f"Now drawing from 'Battery Power'\n -InternalBattery-0 (id=1)\t{batt}%; discharging; 2:50 remaining present: true\n")
    ac = f"Wattage = {int(watts)}W\nCurrent = 4800mA\nVoltage = {int(volts * 1000)}mV\n"
    bt = f"Now drawing from 'AC Power'\n -InternalBattery-0 (id=1)\t{batt}%; charging; 0:42 remaining present: true\n"
    return ac, bt


def stamp(epoch):
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S +0000")


def pmset_log_text(events):
    """`pmset -g log` text with `(epoch, "Batt"|"AC")` power-source events (one AC event first: a well-formed history)."""
    lines = ["2026-11-01 00:00:00 +0000 Assertions           \tUsing AC(Charge: 80)"]
    for at, src in sorted(events):
        lines.append(f"{stamp(at)} Assertions           \tUsing {'Batt' if src == 'Batt' else 'AC'}(Charge: 79)")
    return "\n".join(lines) + "\n"


def kv_line(arm, *, bits="unset", scheme="unset", start=0, group=64, mode="mse", extra=None, ts="2026-11-04 10:00:00,001"):
    """The `KV cache resolved:` line as `app.py` logs it. `bits`/`scheme` default to the arm's own resolved values."""
    ebits, escheme, _ = ARM_FACTS[arm]
    if bits == "unset":
        bits = None if ebits == 0 else float(ebits)
    if scheme == "unset":
        scheme = escheme or "uniform"
    f = dict(kv_bits=bits, kv_key_bits=None, kv_value_bits=None, kv_key_scheme=None, kv_value_scheme=None,
             kv_quant_scheme=scheme, kv_group_size=group, quantized_kv_start=start)
    f.update(extra or {})
    body = " ".join(f"{k}={v!r}" for k, v in f.items()) + f" TQ_KV_QUANT_MODE={mode!r}"
    return f"{ts} INFO mlx_vlm.server.app: KV cache resolved: {body}"


def worker_argv(wt, arm, *, kv_group_size=None, tweak=None):
    """The worker command line as mlx-serve `_build_command` emits it for the arm's entry (vision type)."""
    bits, scheme, pred = ARM_FACTS[arm]
    argv = [f"{wt}/.venv/bin/mlx_vlm.server", "--model", f"caslca/{PICK}", "--host", "127.0.0.1", "--port", "8091",
            "--max-kv-size", "262144", "--kv-prealloc-tokens", "262144"]
    if bits > 0:
        argv += ["--kv-bits", str(bits)]
    if scheme:
        argv += ["--kv-quant-scheme", scheme]
    argv += ["--prefill-step-size", "512", "--generation-defaults", json.dumps(GEN_DEFAULTS)]
    if pred == "mtp":
        argv += ["--draft-kind", "mtp", "--draft-model", DRAFTER]
    if kv_group_size is not None:
        argv += ["--kv-group-size", str(kv_group_size)]
    return tweak(argv) if tweak else argv


def metrics(arm, block, ctx, override=None):
    """Deterministic per-(arm, block, rung) numbers: peak GB (cumulative), prefill tok/s, decode tok/s, acceptance."""
    po, pf, dc = ARM_METRIC[arm]
    k = FULL_GRID.index(ctx) if ctx in FULL_GRID else 0
    m = dict(peak=34.0 + 4.0 * k + po + (0.5 if block == 2 else 0.0),
             pfs=400.0 * pf - 20.0 * k + (10.0 if block == 2 else 0.0),
             dts=40.0 * dc + (2.0 if block == 2 else 0.0),
             acc=0.60 + 0.02 * k if ARM_FACTS[arm][2] == "mtp" else None)
    m.update((override or {}).get((arm, block), {}))
    return m


def strict_row(arm, ctx, *, block=1, i=0, prefix="p475-leg", ov=None, **over):
    """A ladder row as `run_capacity --p475-strict` writes it (flat keys; the contract's persisted fields)."""
    m = metrics(arm, block, ctx, ov)
    prompt_n = ctx + 57
    pps = m["pfs"]
    on = ARM_FACTS[arm][2] == "mtp"
    row = {"ctx": ctx, "schema_version": 2, "execution_status": "completed", "elapsed_s": 100.0 + i,
           "finish_reason": "length", "completion_tokens": 256, "prompt_tokens": prompt_n, "prompt_n": prompt_n,
           "prompt_ms": prompt_n / pps * 1000.0, "prompt_per_second": pps, "cache_n": 0, "predicted_n": 256,
           "predicted_per_second": m["dts"], "peak_memory_gb_cumulative": m["peak"], "retrieval_acc": None,
           "session_id": f"{prefix}-{i:016x}", "server_peak_gb": m["peak"], "decode_tps": m["dts"]}
    if on:
        row.update(draft_kind="mtp", draft_rounds=100, draft_n=200, draft_n_accepted=int(round(200 * m["acc"])),
                   acceptance=round(m["acc"], 4))
    row.update(over)
    return row


class DriverSim:
    def __init__(self, world, pid, ct, argv, env, cwd, spawn_mono, spawn_epoch):
        self.w, self.pid, self.ct, self.argv, self.env, self.cwd = world, pid, ct, argv, env, cwd
        self.spawn_mono, self.spawn_epoch = spawn_mono, spawn_epoch
        self.end_mono = None
        self.rc = None
        self.finished = False
        self.signals = []
        self.tag = argv[argv.index("--out-tag") + 1] if "--out-tag" in argv else None

    def arm_block(self):
        m = re.match(r"p475-u4-(.+?)-(?:b(\d+)|(smoke))\.a\d+$", self.tag or "")
        arm = next((a for a in ARMS if a.lower() == (m.group(1) if m else None)), None)
        return arm, (int(m.group(2)) if m and m.group(2) else 1)


class World:
    def __init__(self, tmp_path, monkeypatch):
        self.tmp = Path(tmp_path)
        self.wd = self.tmp / "wd"
        self.main = self.tmp / "repo"
        for d in (self.wd, self.main / "benchmark" / "results"):
            d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("STACK_WORKDIR", str(self.wd))
        from bench import paths
        monkeypatch.setattr(paths, "REPO_ROOT", self.main)
        monkeypatch.setattr(paths, "BENCHMARK_DIR", self.main / "benchmark")
        for n in KV_NAMES:
            monkeypatch.delenv(n, raising=False)
        self.monkeypatch = monkeypatch
        self.epoch0 = 1_800_000_000.0
        self.t = 0.0
        self.now_calls = 0
        self.now_snaps = []
        self.events = []
        self.next_pid = 6000
        self.procs = {}                     # pid -> create_time of a live process
        self.listener = {}                  # port -> pid
        self.spawns, self.watches, self.stacks, self.git_calls, self.run_calls, self.env_snaps = [], [], [], [], [], []
        self.leg_no, self.cur = 0, (None, 0)
        self.drivers = []
        # ---- knobs (value or callable(arm, leg_no))
        self.power_val = dict(GOOD_POWER)
        self.busy_list = []
        self.lease_refuse = False
        self.base = "b" * 40
        self.arm_commit = {a: (self.base if a == "TQ4" else f"{i:x}" * 40) for i, a in enumerate(ARMS, 1)}
        self.arm_head = {}                  # arm -> head override
        self.arm_clean = {}
        self.arm_parent = {}
        self.arm_gitlinks = {}
        self.arm_registry_override = {}     # arm -> a tampered committed registry text
        self.arm_files = {}                 # arm -> the file list `git diff --name-only <base> HEAD` prints (default: the registry only)
        self.preflight_plan = {}            # arm -> list of "pass" | "refuse" | "wrong_entry" | "no_report" | "rc1"
        self.preflight_calls = {}
        self.kv_text = None                 # None = the arm's own good line; "" = no line; str = that text
        self.stale_kv = None                # a line pre-written to the worker log before the leg
        self.argv_tweak = None
        self.argv_group = None
        self.worker_env_extra = {}
        self.router_env_extra = {}
        self.load_raises = False
        self.unload_ok_value = True
        self.survivors = ()                 # subset of {"worker", "listener", "router", "wrapper"}
        self.start_router_raises = False
        self.driver_duration = None         # None = sum(expected)
        self.driver_rc = 0
        self.driver_ignores_term = False
        self.driver_unkillable = False
        self.row_mutate = None              # f(row, i, arm, leg_no) -> row
        self.metric_override = {}
        self.watch_mode = "ok"
        self.battery_events = []            # (epoch, "Batt"|"AC") inside the world's epoch
        self.pmset_raises = False
        self.ws_hook = None                 # f(arm), called inside every worktree_state read
        self.worker_log_extra = ""          # a line the worker log carries (evidence-gate tests)
        self.group_members = {}            # pgid -> pids of group members besides the leader (v1.2 group_alive)
        self.driver_child = False           # the driver leaves a child in its group
        self.child_ignores_term = False
        self.child_unkillable = False
        self.router_group_extra = False     # the router wrapper's group holds one more member
        self.group_raises = False
        self.wait_hook = None              # f(), called inside every ops.wait (a test may raise an interrupt)
        self.spawn_raises = False
        self.sleep_hook = None             # f(seconds), called after every ops.sleep (a test may raise to interrupt a run)
        # C296 (S18): P655 / P656 knobs
        self.unresolvable = set()           # revisions `rev-parse --verify <rev>^{commit}` refuses in the repo
        self.qualify_stderr = ""            # the stderr every qualify run returns (the no_report mode keeps its own)
        self.uv_rc = 0                      # the exit status of every `uv` call
        self.arm_freeze = FREEZE            # `uv pip freeze --python <arm>/.venv/bin/python` stdout ({wt} = the worktree)
        # C297 (S18-P1): a driver write under an arm worktree leaves it dirty (untracked), as on the box (P659)
        self.untracked = {}                 # arm -> set of worktree-relative paths a driver wrote
        self.driver_ignores_out_dir = False
        # C301 (S18-P10): the ON engagement check (`qualify --kv-arm --predictor on --engagement-only`)
        self.engagement_plan = {}           # arm -> list of "pass" | "refuse" | "certifies" | "no_flag" | "predictor_off"

    # ------------------------------------------------------------------ small helpers
    def ev(self, name, **kw):
        self.events.append((name, dict(kw, t=self.t)))

    def names(self):
        return [e[0] for e in self.events]

    def index(self, name, nth=0):
        idx = [i for i, e in enumerate(self.events) if e[0] == name]
        return idx[nth] if len(idx) > nth else None

    def K(self, name):
        v = getattr(self, name)
        return v(*self.cur) if callable(v) else v

    @property
    def epoch(self):
        return self.epoch0 + self.t

    def wt(self, arm):
        return self.wd / "worktrees" / f"p475-u4-{arm_lower(arm)}"

    def arm_of(self, wt):
        name = Path(wt).name
        return next((a for a in ARMS if name == f"p475-u4-{arm_lower(a)}"), None)

    def make_worktrees(self, arms=ARMS):
        for a in arms:
            wt = self.wt(a)
            (wt / "logs").mkdir(parents=True, exist_ok=True)
            (wt / "benchmark" / "results").mkdir(parents=True, exist_ok=True)
            (wt / "main_models.yaml").write_text(BASE_REGISTRY)
            for venv in (".venv", ".venv-bench", "src/mlx-vlm/.venv"):   # prepare would build a worktree's missing venvs
                (wt / venv / "bin").mkdir(parents=True, exist_ok=True)
                (wt / venv / "bin" / "python").write_text("")
            self.install_instrument(wt)
        self.install_instrument(self.main)
        return self

    INSTRUMENT = ("bench/run_capacity.py", "bench/capacity_ladder.py", "bench/kv_line.py", "bench/data/p475_decode_carrier.txt",
                  "m1/bench_watch.py")

    def install_instrument(self, root):
        """v1.2 (Sol P1): the five instrument files of the contract's Leg lifecycle 1, byte-identical in the orchestrator checkout
        and in every arm worktree."""
        for rel in self.INSTRUMENT:
            p = Path(root) / "benchmark" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"# fake instrument file {rel}\n")

    def write_last_leg_end(self, ns, epoch):
        p = self.wd / ns / "LAST_LEG_END"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"{epoch}\n")

    # ------------------------------------------------------------------ git facts
    def arm_registry(self, arm):
        """The arm's committed `main_models.yaml` text, as the contract's arm table defines it (the base with only the arm's
        entry keys changed + one `# PROVISIONAL P475 arm <ARM>` comment; TQ4 is the base itself). Written independently of the
        candidate. A test may tamper through `arm_registry_override`."""
        if arm in self.arm_registry_override:
            return self.arm_registry_override[arm]
        if arm == "TQ4":
            return BASE_REGISTRY
        bits, scheme, pred = ARM_FACTS[arm]
        out = []
        for ln in BASE_REGISTRY.splitlines():
            out.append(ln)
            if ln.startswith("  - name:"):
                out.append(f"    # PROVISIONAL P475 arm {arm}")
        text = "\n".join(out) + "\n"
        if arm == "TQ4-OFF":
            text = text.replace("    draft_kind: mtp", "    # draft_kind: mtp").replace("    draft_model:", "    # draft_model:")
        else:
            text = text.replace("    kv_bits: 4", f"    kv_bits: {bits}")
            text = text.replace("    kv_quant_scheme: turboquant\n", f"    kv_quant_scheme: {scheme}\n" if scheme else "")
        return text

    def gitlinks(self, arm):
        return self.arm_gitlinks.get(arm, self.base_gitlinks())

    def base_gitlinks(self):
        return {"src/mlx-vlm": "d94e38a9" + "0" * 32, "src/mlx-serve": "1ddf6f84" + "0" * 32}

    def head(self, arm):
        return self.arm_head.get(arm, self.arm_commit[arm])

    def clean(self, arm):
        return self.arm_clean.get(arm, True) and not self.untracked.get(arm)

    def parent(self, arm):
        return self.arm_parent.get(arm, "a" * 40 if arm == "TQ4" else self.base)


class FakeStack:
    def __init__(self, world, wt, registry, predictor):
        w = world
        self.w, self.wt, self.registry, self.predictor = w, Path(wt), registry, predictor
        self.arm = w.arm_of(wt)
        self.router = None
        self.worker = None
        w.leg_no += 1
        w.cur = (self.arm, w.leg_no)
        w.stacks.append(self)
        w.env_snaps.append(("stack", dict(os.environ)))
        w.ev("stack", wt=str(wt), registry=str(registry), predictor=predictor)

    def start_router(self):
        w = self.w
        w.env_snaps.append(("start_router", dict(os.environ)))
        w.ev("start_router")
        (self.wt / "logs").mkdir(parents=True, exist_ok=True)
        with (self.wt / "logs" / "main_model.log").open("a") as f:
            f.write(f"router starting from {self.wt}\n")
        if w.K("start_router_raises"):
            raise RuntimeError("TRIPWIRE: router did not start")
        wrapper, router = w.next_pid, w.next_pid + 1
        w.next_pid += 2
        w.procs[wrapper], w.procs[router] = 1000.5 + wrapper, 1000.5 + router
        w.listener[8000] = router
        if w.K("router_group_extra"):
            w.group_members[wrapper] = {w.next_pid}
            w.next_pid += 1
        self.router = {"pid": router, "create_time": w.procs[router],
                       "spawned": {"pid": wrapper, "create_time": w.procs[wrapper]}}
        return router

    def expected_worker_argv(self, registry, model):
        self.w.ev("expected_worker_argv", registry=str(registry), model=model)
        return worker_argv(self.wt, self.arm, kv_group_size=None)

    def load(self, model):
        w = self.w
        w.env_snaps.append(("load", dict(os.environ)))
        w.ev("load", model=model)
        if w.K("load_raises"):
            raise RuntimeError("TRIPWIRE: expected one worker")
        argv = worker_argv(self.wt, self.arm, kv_group_size=w.K("argv_group"), tweak=w.K("argv_tweak"))
        log = self.wt / "logs" / "mlx_vlm.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        text = w.K("kv_text")
        line = kv_line(self.arm) if text is None else text
        with log.open("a") as f:
            f.write(f"2026-11-04 10:00:00,000 INFO mlx_vlm.server: loading model from {self.wt}/cache\n")
            if line:
                f.write(line + "\n")
            if w.worker_log_extra:
                f.write(w.worker_log_extra + "\n")
            f.write("2026-11-04 10:00:09,000 INFO mlx_vlm.server: ready\n")
        pid = w.next_pid
        w.next_pid += 1
        w.procs[pid] = 1000.5 + pid
        self.worker = {"pid": pid, "create_time": w.procs[pid]}
        # RealOps' `load` returns the process's own argv as a LIST (delivery-2 resolution P3: an interface adaptation)
        return {"pid": pid, "create_time": w.procs[pid], "cmdline": list(argv)}

    def env_base(self):
        """What a ChainOps hands out as the router's environment; the code under test strips the KV / TQ names from it for the driver."""
        return dict(os.environ, **self.w.K("router_env_extra"))

    def unload_ok(self):
        self.w.ev("unload_ok")
        return bool(self.w.K("unload_ok_value"))

    def stop_stack(self):
        w = self.w
        w.ev("stop_stack")
        surv = set(w.K("survivors") or ())
        if self.worker and "worker" not in surv:
            w.procs.pop(self.worker["pid"], None)
        if self.router:
            if "router" not in surv:
                w.procs.pop(self.router["pid"], None)
            if "wrapper" not in surv:
                w.procs.pop(self.router["spawned"]["pid"], None)
            if "router_group" not in surv:
                w.group_members.pop(self.router["spawned"]["pid"], None)
            if "listener" not in surv:
                w.listener.pop(8000, None)
        return 0


class FakeOps:
    """Implements exactly the contract's Ops table; everything observable lands in `world.events`."""

    def __init__(self, world):
        self.w = world

    # --- environment facts
    def power(self):
        w = self.w
        w.ev("power")
        v = w.power_val(w.cur) if callable(w.power_val) else w.power_val
        ac, bt = pmset_texts(v["watts"], v["volts"], v["battery"])
        from bench import chain_ops
        p = chain_ops.parse_power(ac, bt)
        return {"watts": p["watts"], "volts": p["volts"], "battery": p["batt"]}

    def port_listener(self, port):
        self.w.ev("port_listener", port=port)
        return self.w.listener.get(port)

    def busy(self):
        self.w.ev("busy")
        return list(self.w.K("busy_list") or [])

    @contextlib.contextmanager
    def lease(self):
        from bench import p426_locks
        w = self.w
        w.ev("lease_try")
        if w.K("lease_refuse"):
            raise p426_locks.LockRefused("p426/LEG.lock is held (another a P426 chain leg is running)")
        w.ev("lease_enter")
        try:
            yield
        finally:
            w.ev("lease_exit")

    def now(self):
        w = self.w
        w.now_calls += 1
        snap = ((w.main / "benchmark/results/p475").exists() and
                any(p.is_dir() and not p.name.endswith(".stage") for p in (w.main / "benchmark/results/p475").glob("*")),
                any((w.main / "benchmark/results/p475").glob("*.stage")) if (w.main / "benchmark/results/p475").exists() else False)
        v = w.epoch + 0.001 * w.now_calls
        w.now_snaps.append((v, snap))
        return v

    def monotonic(self):
        return 5000.0 + self.w.t

    def sleep(self, s):
        self.w.ev("sleep", s=s)
        self.w.t += float(s)
        if self.w.sleep_hook:
            self.w.sleep_hook(s)

    # --- git / worktrees
    def worktree_state(self, wt):
        w = self.w
        w.ev("worktree_state", wt=str(wt))
        arm = w.arm_of(wt)
        if w.ws_hook:
            w.ws_hook(arm)
        return {"head": w.head(arm), "clean": w.clean(arm), "gitlinks": dict(w.gitlinks(arm))}

    def git(self, wt, *args):
        w = self.w
        w.git_calls.append((str(wt), args))
        arm = w.arm_of(wt)
        flat = [a for a in args if not a.startswith("-")]
        branch = next((a for a in flat if a.startswith("refs/heads/p475-u4-")), None)
        if branch is not None:                                     # `rev-parse [--verify] refs/heads/<arm branch>`, in the repo or a worktree
            named = next(a for a in ARMS if branch == f"refs/heads/p475-u4-{arm_lower(a)}")
            return w.arm_commit[named] + "\n"
        commit = next((a for a in flat if a.endswith("^{commit}")), None)
        if arm is None and commit is not None:                     # C296 (P655): `rev-parse --verify <rev>^{commit}` in the repo
            rev = commit[: -len("^{commit}")]
            if rev in w.unresolvable or not rev:
                raise RuntimeError("git rev-parse failed in repo (rc 128)")
            if w.base.startswith(rev):
                return w.base + "\n"
            if re.fullmatch(r"[0-9a-f]{40}", rev):
                return rev + "\n"
            raise RuntimeError("git rev-parse failed in repo (rc 128)")
        if arm is None:
            return w.base + "\n" if "rev-parse" in args else ""
        if "diff" in args:                                         # `diff --name-only <base> <head>`
            return "".join(f"{f}\n" for f in w.arm_files.get(arm, ["main_models.yaml"]))
        if "show" in args:                                         # `show <rev>:main_models.yaml`
            rev = flat[-1].split(":", 1)[0]
            return BASE_REGISTRY if rev == w.base else w.arm_registry(arm)
        if "ls-tree" in args:                                      # the BASE's gitlinks
            return "".join(f"160000 commit {sha}\t{p}\n" for p, sha in w.base_gitlinks().items())
        if "status" in args:
            if w.untracked.get(arm):
                return "".join(f"?? {r}\n" for r in sorted(w.untracked[arm]))
            return "" if w.clean(arm) else " M main_models.yaml\n"
        if "rev-parse" in args:
            ref = flat[-1] if flat else "HEAD"
            if ref.endswith("^"):                                  # `<head sha>^`
                return w.parent(arm) + "\n"
            return w.head(arm) + "\n"
        return ""

    def stack(self, wt, registry, predictor):
        return FakeStack(self.w, wt, registry, predictor)

    # --- processes
    def proc_alive(self, pid, create_time):
        ct = self.w.procs.get(pid)
        return ct is not None and (create_time is None or ct == create_time)

    def proc_env(self, pid):
        w = self.w
        env = {"PATH": "/usr/bin", "MLX_VLM_CACHE_SESSION_MAX": "1"}
        env.update(w.K("worker_env_extra") or {})
        return env

    def spawn(self, argv, env, cwd, session=True):
        w = self.w
        pid = w.next_pid
        w.next_pid += 1
        ct = 1000.5 + pid
        w.procs[pid] = ct
        w.ev("spawn", argv0=str(argv[0]), session=session)
        if w.K("spawn_raises"):
            w.procs.pop(pid, None)                       # an exec that failed leaves no process behind
            raise OSError("exec failed")
        if w.K("driver_child"):
            w.group_members[pid] = {w.next_pid}
            w.next_pid += 1
        rec = DriverSim(w, pid, ct, list(argv), dict(env or {}), str(cwd), self.monotonic(), w.epoch)
        dur = w.K("driver_duration")
        if dur is None:
            dur = sum(float(x) for x in argv[argv.index("--expected-rung-seconds") + 1].split(","))
        rec.duration = dur
        rec.end_mono = rec.spawn_mono + dur
        w.drivers.append(rec)
        w.spawns.append(SimpleNamespace(argv=list(argv), env=dict(env or {}), cwd=str(cwd), session=session, sim=rec))
        return {"pid": pid, "create_time": ct}

    def _sim(self, proc):
        return next(d for d in self.w.drivers if d.pid == proc["pid"])

    def _finish(self, d):
        w = self.w
        d.finished = True
        w.procs.pop(d.pid, None)
        arm, block = d.arm_block()
        argv = d.argv
        grid = [int(x) for x in argv[argv.index("--grid") + 1].split(",")] if "--grid" in argv else list(FULL_GRID)
        model = argv[argv.index("--model") + 1] if "--model" in argv else PICK
        prefix = d.env.get("MLX_BENCH_SESSION_PREFIX", "p475-leg")
        if "--out-dir" in argv and not w.driver_ignores_out_dir:
            out = Path(argv[argv.index("--out-dir") + 1])
        else:
            out = Path(d.cwd) / "results" / model
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        for i, ctx in enumerate(grid):
            row = strict_row(arm, ctx, block=block, i=i, prefix=prefix, ov=w.metric_override)
            if w.row_mutate:
                row = w.row_mutate(row, i, arm, w.leg_no)
            rows.append(row)
        tag = d.tag
        (out / f"capacity_ladder.{tag}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (out / f"capacity_retrieval.{tag}.json").write_text(json.dumps({"model": model, "records": rows}))
        (out / f"capacity_ladder.{tag}.manifest.json").write_text(json.dumps({"model": model, "probe": "capacity_ladder"}))
        wt = w.wt(arm) if arm else None
        if wt is not None and (out == wt or wt in out.parents):
            rel = out.relative_to(wt)
            w.untracked.setdefault(arm, set()).update(
                str(rel / f"{stem}.{tag}.{ext}") for stem, ext in
                (("capacity_ladder", "jsonl"), ("capacity_retrieval", "json"), ("capacity_ladder", "manifest.json")))
        d.rc = w.driver_rc
        d.end_mono = self.monotonic()
        d.end_epoch = w.epoch

    def wait(self, proc, timeout):
        w = self.w
        w.ev("wait", timeout=timeout)
        if w.wait_hook:
            w.wait_hook()
        if w.t > 5_000_000:
            raise AssertionError("runaway wait: the code under test never gave up on a process (unbounded wait)")
        d = self._sim(proc)
        if d.rc is not None:
            return d.rc
        remaining = d.end_mono - self.monotonic()
        if remaining <= timeout and not (d.duration == float("inf")):
            w.t += max(0.0, remaining)
            self._finish(d)
            return d.rc
        w.t += timeout
        return None

    def signal_group(self, proc, sig):
        w = self.w
        d = self._sim(proc)
        name = signal.Signals(sig).name if isinstance(sig, int) else str(sig)
        w.ev("signal_group", sig=name)
        d.signals.append(name)
        members = w.group_members.get(d.pid, set())
        if members:                                  # the group's other members (a child the leader left behind)
            if name == "SIGKILL" and not w.child_unkillable:
                members.clear()
            elif name == "SIGTERM" and not (w.child_ignores_term or w.child_unkillable):
                members.clear()
        if d.rc is not None or d.finished:
            return
        if w.K("driver_unkillable"):
            return
        if name == "SIGTERM" and w.K("driver_ignores_term"):
            return
        d.rc = -signal.Signals[name].value
        d.end_epoch = w.epoch
        w.procs.pop(d.pid, None)

    def group_alive(self, pgid):
        """v1.2 (Sol P5): any live member of the process group `pgid` (the leader's pid, or a child the leader left behind)."""
        w = self.w
        w.ev("group_alive", pgid=pgid)
        if w.group_raises:
            raise RuntimeError("ps -axo pid=,pgid=,stat= exited 1")
        return pgid in w.procs or bool(w.group_members.get(pgid))

    # --- watcher
    def start_watch(self, argv):
        w = self.w
        w.ev("start_watch")
        h = {"argv": list(argv), "arm": w.cur[0], "leg_no": w.cur[1], "started_epoch": w.epoch, "sim": w.drivers[-1] if w.drivers else None}
        w.watches.append(h)
        return h

    def stop_watch(self, handle):
        w = self.w
        w.ev("stop_watch")
        argv = handle["argv"]
        if "--out" not in argv:
            return None
        out = Path(argv[argv.index("--out") + 1])
        mode = w.watch_mode(*w.cur) if callable(w.watch_mode) else w.watch_mode
        d = handle["sim"]
        end = getattr(d, "end_epoch", w.epoch) if d else w.epoch
        start = d.spawn_epoch if d else handle["started_epoch"]
        if mode == "missing":
            return None
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(watch_journal(start, end, d, mode))
        return None

    def scrub(self):
        """The harvest's Scrub, hermetic (no `git config user.email`, no box credentials): a fixed operator address, user, host, home."""
        from bench import p426_harvest
        return p426_harvest.Scrub(workdir=self.w.wd, repo=self.w.main, home=self.w.tmp / "home", user="fakeuser",
                                  hosts=("fakehost",), emails=(OPERATOR_EMAIL,), secrets={})

    # --- text / logs
    def read_text(self, path):
        return Path(path).read_text()

    def pmset_log(self, start, end):
        w = self.w
        w.ev("pmset_log", start=start, end=end)
        if w.pmset_raises:
            raise RuntimeError("pmset -g log exited 1")
        return pmset_log_text(w.battery_events)

    def run(self, argv, cwd, env, timeout):
        w = self.w
        w.ev("run", argv0=str(argv[0]))
        w.run_calls.append(SimpleNamespace(argv=list(argv), cwd=str(cwd), env=dict(env or {}), timeout=timeout))
        if str(argv[0]) == "uv":                                   # C296 (P656 3): prepare's venv builds
            argv = [str(a) for a in argv]
            if w.uv_rc != 0:
                return subprocess.CompletedProcess(argv, w.uv_rc, "", "uv: failed")
            if "freeze" in argv:
                return subprocess.CompletedProcess(argv, 0, w.arm_freeze.format(wt=cwd), "")
            if "venv" in argv:
                target = Path(next(a for a in reversed(argv) if not a.startswith("-") and a != "venv" and a != "3.12"))
                (target / "bin").mkdir(parents=True, exist_ok=True)
                (target / "bin" / "python").write_text("")
            return subprocess.CompletedProcess(argv, 0, "", "")
        arm = w.arm_of(argv[argv.index("--stack-root") + 1]) if "--stack-root" in argv else None
        engagement = "--engagement-only" in argv
        key = f"{arm}:engagement" if engagement else arm
        n = w.preflight_calls.get(key, 0)
        w.preflight_calls[key] = n + 1
        plan = (w.engagement_plan if engagement else w.preflight_plan).get(arm, [])
        mode = plan[n] if n < len(plan) else (plan[-1] if plan else "pass")
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        if mode == "no_report":
            return subprocess.CompletedProcess(argv, 1, "", "refused")
        if mode in ("env_refused", "started_not_run"):            # C302: qualify's own refusal, as the box recorded it (S18-P12)
            doc = {"predictor": "on" if engagement else "off", "kv_arm": {"entry": PICK, "delta": {}},
                   "entries": {PICK: {"status": "NOT_RUN", "arm": "mtp_off", "reason": "not reached"}},
                   "finished": "2026-11-06T11:43:10"}
            if mode == "started_not_run":                          # it began the measurement loop, then stopped
                doc["started"] = "2026-11-06T11:43:00"
            (out / "report.json").write_text(json.dumps(doc))
            err = ("refused: [\"power {'watts': None, 'volts': None, 'battery': 84, 'ac_ok': False, 'battery_ok': True}\"]"
                   if mode == "env_refused" else "interrupted")
            return subprocess.CompletedProcess(argv, 1, "", w.qualify_stderr or err)
        if mode == "timeout":                                      # C296 (P656 5): RealOps.run raises after reaping the group
            raise subprocess.TimeoutExpired(argv, timeout, output="", stderr=w.qualify_stderr or "qualify: still running")
        # qualify.py's report.json: per-entry status under `entries`, no top-level status; `kv_arm` under --kv-arm
        report = {"predictor": "off", "entries": {PICK: {"status": "COMPLETED"}}, "kv_arm": {"entry": PICK, "delta": {}}}
        if engagement:                                             # the fork's P658 (a) report fields
            report.update(predictor="on", engagement_only=True, certifies=False)
            if mode == "certifies":
                report["certifies"] = True
            elif mode == "no_flag":
                report.pop("engagement_only")
            elif mode == "predictor_off":
                report["predictor"] = "off"
        rc = 0
        if mode == "refuse":
            report["entries"][PICK]["status"], rc = "REFUSED", 1
        elif mode == "wrong_entry":
            report["kv_arm"]["entry"] = "Some-Other-Model"
        elif mode == "rc1":
            rc = 1
        (out / "report.json").write_text(json.dumps(report))
        return subprocess.CompletedProcess(argv, rc, "", w.qualify_stderr)


def watch_journal(start, end, d, mode):
    """`watch.jsonl` as `bench_watch` capacity mode writes it (P426-mode ticks + one closing exit_state line)."""
    interval = 300.0
    pid = d.pid if d else 0
    ticks, t, n = [], start, 0
    times = []
    while t <= end:
        times.append(t)
        t += interval
    if mode == "few_ticks":
        times = times[:2]
    if mode.startswith("ticks:"):
        want = int(mode.split(":")[1])
        times = [start + k * (end - start) / want for k in range(want)]
    if mode == "gap" and len(times) > 6:
        times = times[:4] + [x + 400.0 for x in times[4:]]
        times = [x for x in times if x <= end]
    for t in times:
        watts = 96 if (mode == "power_fail" and n == 2) else 140
        ticks.append({"tick": n, "t": t, "at": stamp(t), "interval_s": interval, "watts": watts, "volts": 28, "battery": 80,
                      "power_ok": watts == 140, "driver_alive": True, "driver": {"pid": pid, "start": d.ct if d else None},
                      "elapsed_s": [100.0 + n], "rate": "RATE 1.00x", "eta_s": max(0.0, end - t)})
        n += 1
    lines = list(ticks)
    if mode != "no_exit":
        lines.append({"exit_state": "driver_exited" if mode != "early_exit" else "watcher_died", "t": end, "at": stamp(end),
                      "interval_s": interval, "ticks": n, "window": {"start": start, "end": end}, "battery_intervals": []})
    return "".join(json.dumps(x, sort_keys=True) + "\n" for x in lines)
