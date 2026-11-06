"""P475 stage 1 (implementer tests): the fake box every p475_kv test drives — a fake `Ops` with real formats (the fork's `KV cache
resolved:` line, worker argv as mlx-serve's `_build_command` emits it, `run_capacity --p475-strict` ladder rows, bench_watch
capacity-mode JSON ticks, `pmset -g log` text). No process, router, model or GPU is touched."""
from __future__ import annotations

import contextlib
import json
import subprocess
import uuid
from pathlib import Path

import yaml

from bench import p426_harvest, p426_locks
from bench import p475_kv as K

BASE = "b" * 40
VLM_LINK, SERVE_LINK = "d94e38a9" + "0" * 32, "1ddf6f84" + "0" * 32
DRAFTER = "caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter"


def base_registry():
    return f"""mlx_port: 8091
models:
  - name: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
    type: vision
    hf_path: caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
    kv_bits: 0
    draft_kind: mtp
    draft_model: caslca/other-drafter
  - name: {K.PICK}
    type: vision
    on_demand: true
    hf_path: caslca/{K.PICK}
    max_kv_cache_size: 262144
    kv_prealloc_tokens: 262144
    # a comment line inside the entry
    kv_quant_scheme: turboquant
    kv_bits: 4
    quantized_kv_start: 0
    prefill_step_size: 512
    draft_kind: mtp
    draft_model: {DRAFTER}  # an inline note
    generation_defaults:
      temperature: 0.6
      max_tokens: 102400
      enable_thinking: true
task_model:
  name: tiny
"""


def make_cfg(tmp_path, **kw):
    wd, repo = tmp_path / "wd", tmp_path / "repo"
    (repo / "benchmark" / "results").mkdir(parents=True, exist_ok=True)
    wd.mkdir(parents=True, exist_ok=True)
    scrub = p426_harvest.Scrub(workdir=wd, repo=repo, home=tmp_path / "home", user="p475fakeuser", hosts=("p475fakehost",))
    return K.Config(repo=repo, workdir=wd, base=BASE, scrub=scrub, **kw)


def build_argv(registry_text, model):
    """The worker argv mlx-serve's `_build_command` builds for `model` (the same flag order)."""
    doc = yaml.safe_load(registry_text)
    e = next(m for m in doc["models"] if m["name"] == model)
    cmd = ["/wt/.venv/bin/mlx_vlm.server", "--model", e["hf_path"], "--host", "127.0.0.1", "--port", str(doc["mlx_port"])]
    if e.get("max_kv_cache_size"):
        cmd += ["--max-kv-size", str(e["max_kv_cache_size"])]
    if e.get("kv_prealloc_tokens"):
        cmd += ["--kv-prealloc-tokens", str(e["kv_prealloc_tokens"])]
    if (e.get("kv_bits") or 0) > 0:
        cmd += ["--kv-bits", str(e["kv_bits"])]
    if e.get("kv_quant_scheme"):
        cmd += ["--kv-quant-scheme", e["kv_quant_scheme"]]
    if e.get("prefill_step_size"):
        cmd += ["--prefill-step-size", str(e["prefill_step_size"])]
    if e.get("generation_defaults"):
        cmd += ["--generation-defaults", json.dumps(e["generation_defaults"])]
    if e.get("draft_kind"):
        cmd += ["--draft-kind", e["draft_kind"]]
        if e.get("draft_model"):
            cmd += ["--draft-model", e["draft_model"]]
    return cmd + ["--quantized-kv-start", str(e.get("quantized_kv_start", 0))]


def kv_log_line(arm, **over):
    bits, scheme = K.kv_line.ARM_FORMATS[arm]
    vals = dict(kv_bits=float(bits) if bits else None, kv_key_bits=None, kv_value_bits=None, kv_key_scheme=None,
                kv_value_scheme=None, kv_quant_scheme=scheme if bits else None, kv_group_size=64, quantized_kv_start=0,
                TQ_KV_QUANT_MODE="mse")
    vals.update(over)
    body = " ".join(f"{k}={v!r}" for k, v in vals.items())
    return f"2026-11-04 10:00:00,000 INFO mlx_vlm.server.app: KV cache resolved: {body}\n"


def ladder_row(ctx, predictor, prefix, *, peak=20.0, pps=500.0, decode=30.0, accepted=0.6, **over):
    prompt_n = ctx - 100
    row = dict(ctx=ctx, schema_version=2, execution_status="completed", elapsed_s=10.0, finish_reason="length",
               completion_tokens=256, prompt_tokens=prompt_n, retrieval_acc=None, prompt_n=prompt_n, cache_n=0,
               prompt_ms=prompt_n / pps * 1000, prompt_per_second=pps, predicted_n=256, predicted_per_second=decode,
               peak_memory_gb_cumulative=peak, session_id=f"{prefix}-{uuid.uuid4().hex[:16]}", rung_problems=[])
    if predictor == "on":
        row.update(draft_kind="mtp", draft_n=200, draft_n_accepted=int(200 * accepted), draft_rounds=100)
    else:
        row.update(draft_kind=None, draft_n=None, draft_n_accepted=None, draft_rounds=None)
    row.update(over)
    return row


REAL_BENCHMARK = Path(__file__).resolve().parents[2]


def install_instrument(root):
    """Copy this checkout's instrument files (contract Leg lifecycle 1) under `<root>/benchmark/`."""
    for rel in K.INSTRUMENT_FILES:
        dst = Path(root) / "benchmark" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((REAL_BENCHMARK / rel).read_bytes())


class FakeHandle:
    def __init__(self, ops, wt, registry, predictor):
        self.ops, self.wt, self.registry, self.predictor = ops, Path(wt), Path(registry), predictor
        self.router = None
        self.loaded = False

    def start_router(self):
        self.ops.calls.append(("start_router", str(self.wt), self.predictor))
        self.router = dict(pid=100, create_time=1.0, spawned=dict(pid=99, create_time=0.5))
        self.ops.alive |= {(100, 1.0), (99, 0.5)}
        self.ops.listener = 100
        return 100

    def load(self, model):
        self.ops.calls.append(("load", model))
        arm = self.ops.arm_of(self.wt)
        log = self.wt / "logs" / "mlx_vlm.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write("2026-11-04 09:59:59,000 INFO loading\n")
            f.write(self.ops.kv_line_for(arm))
        self.ops.alive.add((200, 2.0))
        self.loaded = True
        text = self.registry.read_text()
        argv = self.ops.worker_argv_override or build_argv(text, model)
        return dict(pid=200, create_time=2.0, cmdline=list(argv))

    def expected_worker_argv(self, registry, model):
        return build_argv(Path(registry).read_text(), model)

    def env_base(self):
        return {"PATH": "/usr/bin", "KV_BITS": "4", "TQ_KV_QUANT_MODE": "prod", "MLX_SERVE_CONFIG": "wrong"}

    def stop_stack(self):
        self.ops.calls.append(("stop_stack",))
        if not self.ops.survivor:
            self.ops.alive -= {(100, 1.0), (99, 0.5), (200, 2.0)}
            self.ops.listener = None
        return self.ops.stop_rc

    def unload_ok(self):
        return self.ops.unload_result


class FakeOps:
    def __init__(self, tmp_path):
        self.tmp = Path(tmp_path)
        self.t = 1_000_000.0
        self.calls, self.slept, self.spawned, self.signals = [], [], [], []
        self.arms = {}
        self.cfg = None
        self.power_reading = dict(watts=140, volts=28, battery=90)
        self.exit_power = None
        self.listener = None
        self.busy_list = []
        self.lock_refused = False
        self.alive = set()
        self.kv_over = {}
        self.worker_argv_override = None
        self.worker_env = {"PATH": "/usr/bin", "MLX_SERVE_CONFIG": "x"}
        self.driver_rc = 0
        self.driver_seconds = 2400.0
        self.driver_hangs = False
        self.row_over = {}
        self.metric = lambda arm, block, ctx: {}
        self.watch_mode = "ok"
        self.pmset_text = None
        self.stop_rc = 0
        self.unload_result = True
        self.survivor = False
        self.qualify = {}
        self.leg_script = {}             # leg -> dict(driver_rc=…, watch_mode=…) one-shot overrides
        self._current = None
        self.group_members = {}          # pgid -> count of live members other than the leader (a lingering child)
        self.group_ignores = {}          # pgid -> set of signals the lingering members survive
        self.group_raises = False

    # -- the arm world
    def add_arm(self, cfg, arm, **over):
        self.cfg = cfg
        text = K.arm_registry_text(base_registry(), arm)
        head = BASE if arm == K.BASE_ARM else f"{K.ARMS.index(arm) + 1:x}" * 40
        rec = dict(head=head, branch_tip=head, parent=BASE, clean=True, files=[] if arm == K.BASE_ARM else [K.REGISTRY],
                   text=text, gitlinks={"src/mlx-vlm": VLM_LINK, "src/mlx-serve": SERVE_LINK})
        rec.update(over)
        self.arms[arm] = rec
        wt = cfg.worktree(arm)
        wt.mkdir(parents=True, exist_ok=True)
        (wt / K.REGISTRY).write_text(text)
        (wt / "benchmark").mkdir(exist_ok=True)
        for root in (cfg.repo, wt):                      # v1.2 (Sol P1): the arm runs the orchestrator's own instrument bytes
            install_instrument(root)
        return rec

    def add_all(self, cfg, preflight=True):
        for arm in K.ARMS:
            self.add_arm(cfg, arm)
            if preflight:
                K._atomic_json(cfg.preflight_record(arm), dict(arm=arm, status="PASS", attempts=[]))

    def arm_of(self, wt):
        for arm in self.arms:
            if Path(self.cfg.worktree(arm)) == Path(wt):
                return arm
        raise KeyError(wt)

    def kv_line_for(self, arm):
        return kv_log_line(arm, **self.kv_over)

    # -- Ops
    def power(self):
        return dict(self.power_reading)

    def port_listener(self, port):
        return self.listener

    def busy(self):
        return list(self.busy_list)

    @contextlib.contextmanager
    def lease(self):
        if self.lock_refused:
            raise p426_locks.LockRefused("gate/RUNNING is held (a local gate run is running)")
        self.calls.append(("lease", "acquire"))
        try:
            yield
        finally:
            self.calls.append(("lease", "release"))

    def now(self):
        return self.t

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s

    def worktree_state(self, wt):
        a = self.arms[self.arm_of(wt)]
        return dict(head=a["head"], clean=a["clean"], gitlinks=dict(a["gitlinks"]))

    def git(self, wt, *args):
        self.calls.append(("git", str(wt), args))
        commit = next((x for x in args if str(x).endswith("^{commit}")), None)
        if args[:1] == ("rev-parse",) and commit is not None:      # C296 (P655): the base resolved in the repo
            rev = str(commit)[: -len("^{commit}")]
            if rev and BASE.startswith(rev):
                return BASE + "\n"
            raise RuntimeError("git rev-parse failed (rc 128)")
        a = self.arms[self.arm_of(wt)]
        if args[:1] == ("rev-parse",) and args[1].startswith("refs/heads/"):
            return a["branch_tip"] + "\n"
        if args[:1] == ("rev-parse",) and args[1].endswith("^"):
            return a["parent"] + "\n"
        if args[:2] == ("diff", "--name-only"):
            return "\n".join(a["files"]) + "\n"
        if args[:1] == ("show",):
            return base_registry() if args[1].startswith(BASE) else a["text"]
        if args[:1] == ("ls-tree",):
            return f"160000 commit {VLM_LINK}\tsrc/mlx-vlm\n160000 commit {SERVE_LINK}\tsrc/mlx-serve\n"
        raise AssertionError(f"unexpected git {args}")

    def stack(self, wt, registry, predictor):
        self.calls.append(("stack", str(wt), str(registry), predictor))
        return FakeHandle(self, wt, registry, predictor)

    def proc_alive(self, pid, create_time):
        return (pid, create_time) in self.alive

    def proc_env(self, pid):
        return dict(self.worker_env)

    def spawn(self, argv, env, cwd, session=True):
        self.spawned.append(dict(argv=list(argv), env=dict(env), cwd=cwd, session=session))
        self._current = dict(argv=list(argv), env=dict(env), launch=self.t)
        proc = dict(pid=300 + len(self.spawned), create_time=3.0 + len(self.spawned))
        self.alive.add((proc["pid"], proc["create_time"]))
        return proc

    def _leg(self):
        tag = self._current["argv"][self._current["argv"].index("--out-tag") + 1]
        return tag[len("p475-"):]

    def wait(self, proc, timeout):
        if (proc["pid"], proc["create_time"]) not in self.alive:
            return 0
        leg = self._leg()
        script = self.leg_script.get(leg, {})
        if self.driver_hangs or script.get("hang"):
            self.t += timeout if timeout else 0
            return None
        self.t += script.get("seconds", self.driver_seconds)
        info = K.parse_leg(leg)
        argv = self._current["argv"]
        grid = [int(x) for x in argv[argv.index("--grid") + 1].split(",")]
        prefix = self._current["env"]["MLX_BENCH_SESSION_PREFIX"]
        outs = self.cfg.capacity_outputs(info["arm"], leg)
        outs["rows"].parent.mkdir(parents=True, exist_ok=True)
        pred = K.predictor_of(info["arm"])
        with outs["rows"].open("w") as f:
            for ctx in grid:
                row = ladder_row(ctx, pred, prefix, **self.metric(info["arm"], info["block"], ctx))
                row.update(self.row_over)
                row.update(script.get("row_over", {}))
                f.write(json.dumps(row) + "\n")
        outs["manifest"].write_text(json.dumps(dict(runtime=dict(probe="capacity_ladder"))))
        self.alive.discard((proc["pid"], proc["create_time"]))
        return script.get("driver_rc", self.driver_rc)

    def signal_group(self, proc, sig):
        self.signals.append((proc["pid"], sig))
        if sig == 9 or not self.driver_hangs:
            self.alive.discard((proc["pid"], proc["create_time"]))
        if self.group_members.get(proc["pid"]) and sig not in self.group_ignores.get(proc["pid"], set()):
            self.group_members[proc["pid"]] = 0

    def group_alive(self, pgid):
        self.calls.append(("group_alive", pgid))
        if self.group_raises:
            raise RuntimeError("ps failed")
        return bool(self.group_members.get(pgid)) or any(p == pgid for p, _ in self.alive)

    def start_watch(self, argv):
        self.calls.append(("start_watch", list(argv)))
        return dict(argv=list(argv), start=self.t)

    def stop_watch(self, handle):
        self.calls.append(("stop_watch",))
        argv = handle["argv"]
        out = Path(argv[argv.index("--out") + 1])
        interval = float(argv[argv.index("--interval") + 1])
        mode = self.leg_script.get(self._leg(), {}).get("watch_mode", self.watch_mode)
        if mode == "absent":
            return None
        start, end = handle["start"], self.t
        lines, n, t = [], 0, start
        while t < end:
            power = dict(self.power_reading)
            if mode == "power_fail" and n == 1:
                power["watts"] = 96
            if not (mode == "gap" and 0 < n < 4):
                lines.append(dict(tick=n, t=t, interval_s=interval, mode="capacity", driver_alive=True,
                                  driver=dict(pid=int(argv[argv.index("--driver-pid") + 1]),
                                              start=float(argv[argv.index("--driver-create-time") + 1])), **power))
            n += 1
            t += interval
        lines.append(dict(tick=n, t=end, interval_s=interval, driver_alive=False, watts=140, volts=28, battery=90))
        if mode != "unfinalized":
            lines.append(dict(exit_state="driver_exited", t=end + (-600 if mode == "early" else 1), ticks=n + 1,
                              window=dict(start=start, end=end), battery_intervals=[] if mode != "battery" else [dict(start=start, end=end)]))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(x) + "\n" for x in lines))
        return None

    def read_text(self, path):
        return Path(path).read_text()

    def scrub(self):
        return self.cfg.scrub

    def pmset_log(self, start, end):
        if self.pmset_text is not None:
            return self.pmset_text
        import datetime
        stamp = datetime.datetime.fromtimestamp(start - 3600, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S +0000")
        return f"{stamp} Assertions  \tUsing AC (Charge: 90%)\n"

    def run(self, argv, cwd, env, timeout):
        self.calls.append(("run", list(argv)))
        out = Path(argv[argv.index("--out") + 1])
        arm = self.arm_of(cwd)
        plan = self.qualify.get(arm, ["COMPLETED"])
        n = sum(1 for c in self.calls if c[0] == "run" and self.arm_of(Path(c[1][c[1].index("--stack-root") + 1])) == arm)
        status = plan[min(n, len(plan)) - 1]
        out.mkdir(parents=True, exist_ok=True)
        entry = argv[argv.index("--entry") + 1]
        (out / "report.json").write_text(json.dumps(dict(predictor="off", entries={entry: dict(status=status, arm="mtp_off")},
                                                         kv_arm=dict(entry=entry, delta={}))))
        return subprocess.CompletedProcess(argv, 0 if status == "COMPLETED" else 1, "", "")


def test_the_fake_world_builds_every_arm(tmp_path):
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_all(cfg)
    assert sorted(ops.arms) == sorted(K.ARMS)
