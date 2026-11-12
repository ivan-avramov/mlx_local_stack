"""M76 B1 implementer test support (no tests here): an `f45` world over the P475 stage-1 fakes (`p475s1/fakes.py`) — the
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` entry, arms N16 / X / V / XO, branches `m76-f45-<arm>`, the worker's
`tq4_attention=<mode> self-test:` line and the driver manifest's route counters (`tq4_route_counts_at_creation`,
`router_exit.tq4_route_counts_at_exit`, as `bench.provenance` / `run_capacity` store them). The arm registries are written
here independently of the candidate."""
from __future__ import annotations

import json
import re
from pathlib import Path

from bench import p475_kv as K
from bench.tests.p475s1 import fakes as F

REPO = Path(__file__).resolve().parents[3]
F45 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
DRAFTER45 = f"caslca/{F45}-mtp-drafter"
ARMS45 = ("N16", "X", "V", "XO")
ANALOG = {"N16": "N16", "X": "TQ4", "V": "TQ4", "XO": "TQ4-OFF"}      # the u4 fake arm whose numbers / KV line an f45 arm reuses
MODES = {"N16": "off", "X": "m72_exact", "V": "m72_v1", "XO": "m72_exact"}
EXPECTED_S = [60.0, 400.0, 800.0, 1500.0]

BASE45 = f"""mlx_port: 8091
models:
  - name: Other-Model-4bit
    type: vision
    kv_bits: 4
    draft_kind: mtp
    draft_model: caslca/Other-Model-4bit-mtp-drafter
  - name: {F45}
    type: vision
    hf_path: caslca/{F45}
    max_kv_cache_size: 262144
    kv_prealloc_tokens: 262144
    kv_quant_scheme: turboquant
    kv_bits: 0  # C81: native16 KV is the default
    quantized_kv_start: 0
    prefill_step_size: 512
    attention_policy: fused_v1
    mtp_verify_scan: joint_v1
    generation_defaults:
      temperature: 0.5
      top_p: 0.95
    draft_kind: mtp
    draft_model: {DRAFTER45}
    presentation:
      role: main
"""

# the counters that are > 0 at exit per arm (ROUTE_RULES' positive counters; every other counter 0)
GOOD_MOVES = {"X": ("p2s", "d2_verify", "native:prefill", "native:verify"),
              "V": ("p2s", "mma", "native:prefill", "native:verify"),
              "XO": ("p2s", "d2", "native:prefill", "native:decode")}
ALL_COUNTERS = ("p2s", "mma", "d2", "d2_verify", "native:prefill", "native:verify", "native:decode", "fallback:mask",
                "fallback:dtype")


def good_counts(arm):
    """(creation, exit) as a real leg records them (Errata v1.1): `run_capacity` gathers the creation block after the ladder,
    so creation == exit; the exit block's absolutes carry the leg's counts."""
    exit_ = {k: (11 if k in GOOD_MOVES[arm] else 0) for k in ALL_COUNTERS}
    return dict(exit_), exit_


def manifest_for(arm, creation=None, exit_=None, mode=None):
    """The capacity manifest's mode-relevant keys as `run_capacity` writes them (gather, then `man["router_exit"] = exit_blk`)."""
    man = {"model": F45, "probe": "capacity_ladder", "runtime": {"tq4_attention": MODES[arm] if mode is None else mode},
           "router_exit": {"pid": 4242, "config_sha256": "0" * 64}}
    if MODES[arm] == "off":
        return man
    c, e = good_counts(arm)
    c = c if creation is None else creation
    e = e if exit_ is None else exit_
    m = MODES[arm] if mode is None else mode
    man["tq4_route_counts_at_creation"] = {"mode": m, "route_counts": c, "source": "worker-health"}
    man["router_exit"]["tq4_route_counts_at_exit"] = {"mode": m, "route_counts": e, "source": "worker-health"}
    return man


def entry_range(lines, model):
    s = next(i for i, ln in enumerate(lines) if ln.rstrip("\n") == f"  - name: {model}")
    e = next((j for j in range(s + 1, len(lines)) if lines[j].startswith("  - name:")), len(lines))
    return s, e


def expected_arm_text(base, arm, model=F45):
    """The arm table of the specification, applied by hand: the comment after `- name:`, `kv_bits: 4` + the mode line after it
    (X / V / XO), the three MTP lines commented with the value kept (XO)."""
    if arm == "N16":
        return base
    lines = base.splitlines(keepends=True)
    s, e = entry_range(lines, model)
    out = []
    for i, ln in enumerate(lines):
        if not (s < i < e):
            out.append(ln)
            if i == s:
                out.append(f"    # PROVISIONAL M76 arm {arm}\n")
            continue
        if ln.startswith("    kv_bits:"):
            out.append("    kv_bits: 4\n")
            out.append(f"    tq4_attention: {'m72_v1' if arm == 'V' else 'm72_exact'}\n")
        elif arm == "XO" and re.match(r"^    (draft_kind|draft_model|mtp_verify_scan):", ln):
            out.append("    # " + ln[4:])
        else:
            out.append(ln)
    return "".join(out)


def worker_argv45(wt, arm):
    argv = [f"{wt}/.venv/bin/mlx_vlm.server", "--model", f"caslca/{F45}", "--host", "127.0.0.1", "--port", "8091",
            "--max-kv-size", "262144", "--kv-prealloc-tokens", "262144"]
    if arm != "N16":
        argv += ["--kv-bits", "4"]
    argv += ["--kv-quant-scheme", "turboquant", "--prefill-step-size", "512", "--attention-policy", "fused_v1"]
    if arm != "N16":
        argv += ["--tq4-attention", MODES[arm]]
    argv += ["--generation-defaults", json.dumps({"temperature": 0.5, "top_p": 0.95})]
    if arm != "XO":
        argv += ["--mtp-verify-scan", "joint_v1", "--draft-kind", "mtp", "--draft-model", DRAFTER45]
    return argv


def selftest_line(mode):
    return f"2026-11-11 10:00:05,000 INFO mlx_vlm.server.generation: tq4_attention={mode} self-test: 4 cells (p2s, d2, verify)"


class World45(F.World):
    def __init__(self, tmp_path, monkeypatch):
        super().__init__(tmp_path, monkeypatch)
        self.arm_commit = {a: (self.base if a == "N16" else f"{i:x}" * 40) for i, a in enumerate(ARMS45, 1)}
        self.selftest = None              # None = the arm's own line (none on N16); str = that line instead ("" = none)
        self.manifest_override = {}       # arm -> a manifest dict (or callable(arm) -> dict)
        self.f45_metric = {}              # (arm, block) -> metric overrides (`metrics()` keys: peak / pfs / dts / acc)
    def wt(self, arm):
        return self.wd / "worktrees" / f"m76-f45-{arm.lower()}"

    def arm_of(self, wt):
        name = Path(wt).name
        return next((a for a in ARMS45 if name == f"m76-f45-{a.lower()}"), None)

    def make_worktrees(self, arms=ARMS45):
        for a in arms:
            wt = self.wt(a)
            (wt / "logs").mkdir(parents=True, exist_ok=True)
            (wt / "benchmark" / "results").mkdir(parents=True, exist_ok=True)
            (wt / "main_models.yaml").write_text(self.arm_registry(a))
            for venv in (".venv", ".venv-bench", "src/mlx-vlm/.venv"):
                (wt / venv / "bin").mkdir(parents=True, exist_ok=True)
                (wt / venv / "bin" / "python").write_text("")
            self.install_instrument(wt)
        self.install_instrument(self.main)
        return self

    def arm_registry(self, arm):
        if arm in self.arm_registry_override:
            return self.arm_registry_override[arm]
        return expected_arm_text(BASE45, arm)

    def parent(self, arm):
        return self.arm_parent.get(arm, "a" * 40 if arm == "N16" else self.base)


class FakeStack45(F.FakeStack):
    def expected_worker_argv(self, registry, model):
        self.w.ev("expected_worker_argv", registry=str(registry), model=model)
        return worker_argv45(self.wt, self.arm)

    def load(self, model):
        w = self.w
        w.ev("load", model=model)
        log = self.wt / "logs" / "mlx_vlm.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        st = w.selftest if w.selftest is not None else ("" if self.arm == "N16" else selftest_line(MODES[self.arm]))
        with log.open("a") as f:
            f.write(f"2026-11-11 10:00:00,000 INFO mlx_vlm.server: loading model from {self.wt}/cache\n")
            f.write(F.kv_line(ANALOG[self.arm]) + "\n")
            if st:
                f.write(st + "\n")
            f.write("2026-11-11 10:00:09,000 INFO mlx_vlm.server: ready\n")
        pid = w.next_pid
        w.next_pid += 1
        w.procs[pid] = 1000.5 + pid
        self.worker = {"pid": pid, "create_time": w.procs[pid]}
        return {"pid": pid, "create_time": w.procs[pid], "cmdline": worker_argv45(self.wt, self.arm)}


class FakeOps45(F.FakeOps):
    def stack(self, wt, registry, predictor):
        return FakeStack45(self.w, wt, registry, predictor)

    def git(self, wt, *args):
        w = self.w
        w.git_calls.append((str(wt), args))
        arm = w.arm_of(wt)
        flat = [a for a in args if not a.startswith("-")]
        branch = next((a for a in flat if a.startswith("refs/heads/m76-f45-")), None)
        if branch is not None:
            named = next(a for a in ARMS45 if branch == f"refs/heads/m76-f45-{a.lower()}")
            return w.arm_commit[named] + "\n"
        if arm is None:
            commit = next((a for a in flat if a.endswith("^{commit}")), None)
            if commit is not None:
                return w.base + "\n"
            return w.base + "\n" if "rev-parse" in args else ""
        if "show" in args:
            rev = flat[-1].split(":", 1)[0]
            return BASE45 if rev == w.base else w.arm_registry(arm)
        return super().git(wt, *args)

    def _finish(self, d):
        w = self.w
        d.finished = True
        w.procs.pop(d.pid, None)
        argv = d.argv
        m = re.match(r"p475-f45-(n16|x|v|xo)-(?:b(\d+)|smoke)\.a\d+$", d.tag or "")
        arm = next(a for a in ARMS45 if a.lower() == m.group(1))
        block = int(m.group(2)) if m.group(2) else 1
        grid = [int(x) for x in argv[argv.index("--grid") + 1].split(",")]
        prefix = d.env.get("MLX_BENCH_SESSION_PREFIX", "p475-leg")
        out = Path(argv[argv.index("--out-dir") + 1])
        out.mkdir(parents=True, exist_ok=True)
        ov = {(ANALOG[arm], block): w.f45_metric.get((arm, block), {})}
        rows = [F.strict_row(ANALOG[arm], ctx, block=block, i=i, prefix=prefix, ov=ov) for i, ctx in enumerate(grid)]
        tag = d.tag
        (out / f"capacity_ladder.{tag}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (out / f"capacity_retrieval.{tag}.json").write_text(json.dumps({"model": F45, "records": rows}))
        man = w.manifest_override.get(arm)
        man = man(arm) if callable(man) else man
        (out / f"capacity_ladder.{tag}.manifest.json").write_text(json.dumps(man if man is not None else manifest_for(arm)))
        d.rc = w.driver_rc
        d.end_mono = self.monotonic()
        d.end_epoch = w.epoch

    def run(self, argv, cwd, env, timeout):
        cp = super().run(argv, cwd, env, timeout)
        if "--out" in argv:                                  # qualify's report names the f45 entry
            rp = Path(argv[argv.index("--out") + 1]) / "report.json"
            if rp.exists():
                rp.write_text(rp.read_text().replace(F.PICK, F45))
        return cp


def world45(tmp_path, monkeypatch):
    w = World45(tmp_path, monkeypatch).make_worktrees()
    w.write_last_leg_end("p475", w.epoch0 - 7200)
    return w


def cfg45(w, **kw):
    return K.Config(repo=w.main, workdir=w.wd, base=w.base, expected={a: list(EXPECTED_S) for a in ARMS45}, campaign="f45", **kw)


def ready45(w):
    ops = FakeOps45(w)
    cfg = cfg45(w)
    assert K.prepare(ops, cfg) == []
    for a in ARMS45:
        assert K.preflight(a, ops, cfg)["status"] == "PASS", a
        if a != "XO":
            assert K.preflight(a, ops, cfg, kind="engagement")["status"] == "PASS", a
    w.events.clear()
    w.run_calls.clear()
    w.git_calls.clear()
    return ops


def run_leg45(w, arm, block=1, attempt=1, ops=None):
    ops = ops or FakeOps45(w)
    leg = K.leg_name(arm, block, attempt, "f45")
    return K.run_leg(leg, arm, ops, cfg45(w))


def parse45(w, sub, *flags):
    top = ["--campaign", "f45", "--workdir", str(w.wd), "--repo", str(w.main), "--base", w.base]
    for a in ARMS45:
        top += ["--expected-rung-seconds", f"{a}=" + ",".join(f"{x:g}" for x in EXPECTED_S)]
    return K.parse_args(top + [sub, *map(str, flags)])
