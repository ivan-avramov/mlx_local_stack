"""P371 phase 3b test support: the M64 chain entry on the shared core against the fake arm probe and a fake ChainOps.
No router, worker or GPU. The fixtures and runners the M64 chain test modules share."""
from __future__ import annotations

import importlib.util
import json
import os
import signal
import sys
import threading
from pathlib import Path

import pytest

from bench import arm_specs
from bench import chain_ops as co
from bench.tests.test_c147_chain_runner import FakeOps as BaseFakeOps, TIMERS

REPO = Path(__file__).resolve().parents[3]
M64 = REPO / "benchmark/chains/m64"
C147 = REPO / "benchmark/chains/c147"
PICK1, PICK2 = co.PICK1, co.PICK2
FROZEN = "Mon Jan 05 2026"
LABELS = {"oc": arm_specs.OC.label, "pi": "fake-pi-label", "dsh": "fake-dsh-label"}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


sys.path.insert(0, str(C147))
M = _load("run_m64_chain", M64 / "run_m64_chain.py")
FAP = _load("fake_arm_probe", M64 / "fake_arm_probe.py")
FAP_PATH = M64 / "fake_arm_probe.py"


def fake_specs(monkeypatch, barrier=None):
    """Test-only specs for the arms that have no adapter yet: the oc field set under another arm id and label."""
    for arm in ("pi", "dsh"):
        policy = dict(arm_specs.OC.evidence_policy, namespace="transcripts/" + arm)
        monkeypatch.setitem(arm_specs.SPECS, arm, arm_specs.ArmSpec(
            arm_id=arm, label=LABELS[arm], probe="benchmark/chains/m64/fake_arm_probe.py",
            generation_fields=arm_specs.OC.generation_fields, runtime_pinned=arm_specs.OC.runtime_pinned,
            sha_fields=arm_specs.OC.sha_fields, version_field="opencode_version",
            web_evidence_rules=arm_specs.OC.web_evidence_rules, evidence_policy=policy))


class FakeOps(BaseFakeOps):
    """The c147 fake plus the arm hooks (search restart, cache reset, warm-up), a per-arm A4 scaffold, a router and a
    worker that a test can kill by marker file (`kill_worker` / `kill_router` plan steps of the fake probe)."""

    def __init__(self, wd):
        super().__init__(wd)
        self.tmpdir = Path(wd) / "m64/tmp"
        self.unload_ok = True
        self.restarts = 0

    def a4_gate(self, model, tag, scaffold=None):
        self._c("a4_gate", model, scaffold)
        path = Path(self.write_a4_receipt(model))
        if path.is_file():
            doc = json.loads(path.read_text())
            doc["scaffold"] = scaffold
            path.write_text(json.dumps(doc))
        return str(path)

    def require_arm_ops(self):
        self._c("require_arm_ops")

    def search_restart(self, leg):
        self._c("search_restart", leg["arm"], leg["block"])

    def reset_cache_session(self, model):
        self._c("reset_cache_session", model)

    def warmup(self, model):
        self._c("warmup", model)

    def env_base(self):
        env = super().env_base()
        env["FAKE_ARM_LABELS"] = json.dumps({v: k for k, v in LABELS.items()})
        return env

    def unload(self, model):
        self._c("unload", model)
        self.loaded = None
        if self.on_unload:
            self.on_unload()
        return self.unload_ok

    def load(self, model):
        (self.state / "worker_gone").unlink(missing_ok=True)
        return super().load(model)

    def worker_ident(self, model):
        if (self.state / "worker_gone").exists():
            return None
        return super().worker_ident(model)

    def router_ok(self):
        self._check()
        return self.router_alive and not (self.state / "router_gone").exists()

    def restart_router(self):
        self._c("restart_router")
        (self.state / "router_gone").unlink(missing_ok=True)
        self.restarts += 1


class Crash(BaseException):
    """A simulated chain-process death (never caught by the chain's own handlers)."""


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    fake_specs(monkeypatch)
    ops = FakeOps(tmp_path)
    uni = tmp_path / "universe.json"
    uni.write_text(json.dumps({"items": {**{f"python/p{i:02d}": {} for i in range(22)},
                                         **{f"go/g{i:02d}": {} for i in range(21)}}}))
    yield dict(wd=tmp_path, ops=ops, uni=uni, lines=[], out=tmp_path / "m64-smoke")
    ops.cancel()


def arms_of(argv):
    return argv[argv.index("--arms") + 1].split(",") if "--arms" in argv else ["oc"]


def run(env, argv, *, timers=None, plan=None, extra_env=None, timeout=120, lifecycle=None, fake_all=True, epoch=None,
        frozen=FROZEN, hooks=None, campaign=None):
    """`run_m64_chain.main` in a thread; returns the exit code (re-raises whatever the chain raised, e.g. `Crash`)."""
    ops = env["ops"]
    if plan is not None:
        ops.extra_env["FAKE_ARM_PLAN"] = json.dumps(plan)
    ops.extra_env.update(extra_env or {})
    full = list(argv) + ["--python", sys.executable, "--out-root", str(env["out"]), "--arm-idle-s", "0",
                         "--universe", str(env["uni"])]
    if fake_all:
        for arm in ("oc", "pi", "dsh"):
            full += ["--probe", f"{arm}={FAP_PATH}"]
    if epoch and "--epoch-id" not in argv:
        full += ["--epoch-id", epoch]
    if frozen and not any(x in argv for x in ("--frozen-prompt-date", "--frozen-date-from")):
        full += ["--frozen-prompt-date", frozen]
    tm = M.Timers(**{**TIMERS, **(timers or {})})
    res = {}

    def target():
        try:
            res["rc"] = M.main(full, ops=ops, timers=tm, log_out=env["lines"].append, lifecycle_files=lifecycle,
                               hooks=hooks, campaign=campaign)
        except BaseException as e:  # noqa: BLE001
            res["exc"] = e

    th = threading.Thread(target=target, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        ops.cancel()
        th.join(10)
        pytest.fail("runner did not finish: " + "\n".join(env["lines"][-15:]))
    if "exc" in res:
        raise res["exc"]
    if res["rc"] not in (0, 3):                                      # shown by pytest when the test then fails
        print("\n".join(env["lines"][-25:]))
    return res["rc"]


def kill_probes(env):
    """What a chain-process death leaves behind is dead probes: SIGKILL every probe the chain spawned."""
    for ln in invocations_raw(env):
        try:
            os.kill(ln["pid"], signal.SIGKILL)
        except (ProcessLookupError, PermissionError, KeyError):
            pass


def invocations_raw(env):
    p = env["ops"].state / "invocations.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()] if p.exists() else []


def invocations(env):
    return invocations_raw(env)


def arg(argv, flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


def chain_json(env):
    return json.loads((env["out"] / "chain.json").read_text())


def log_has(env, text):
    return any(text in ln for ln in env["lines"])


def calls(env, *names):
    return [c for c in env["ops"].calls if c[0] in names]


SMOKE = ["chain", "s1", "--smoke", "--arms", "oc", "--probe-code-sha", "oc=" + "9" * 64]
SMOKE3 = ["chain", "s1", "--smoke", "--arms", "oc,pi,dsh", "--probe-code-sha", "oc=" + "9" * 64,
          "--probe-code-sha", "pi=" + "9" * 64, "--probe-code-sha", "dsh=" + "9" * 64]


def schedule(env):
    """The chain's frozen schedule.json, or (before the chain ran) the one a SMOKE s1 chain of `oc` will freeze."""
    path = env["out"] / "schedule.json"
    if path.exists():
        return json.loads(path.read_text())
    from bench import schedules
    items = json.loads(Path(env["uni"]).read_text())["items"]
    names = {lang: sorted(k.split("/", 1)[1] for k in items if k.startswith(lang + "/")) for lang in ("python", "go")}
    return schedules.blocks(["oc"], names, picks=(PICK1, PICK2), sessions=["s1"], reload_control=False, smoke=True)
