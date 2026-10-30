"""P426 B2 frozen tests, delivery 2d: fixtures for `test_b2_frozen_fix_cases.py` (the failing cases of the s1-s5 findings,
C239). Built on the frozen P426 world (`b2_frozen_add_support.world`, `b2_frozen_support.p426_world`); hermetic."""
from __future__ import annotations

import json
from pathlib import Path

from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_support as S

SESSION_OUT = {"pilot": "pilot", "s1": "s1", "s2": "s2", "reload": "reload"}


def leg(tmp_path, monkeypatch, *, arm="off", mode=("pilot",), adjust=None, probe_env=None, extra=()):
    """One hermetic `--p426` leg: (rc, env). `mode` = ("pilot",) or ("chain", "<session>"); the out-root is the leg's
    attempt `tg1-p426-<arm>-<session>.a1`; `adjust(env)` runs before the chain starts."""
    session = mode[1] if mode[0] == "chain" else "pilot"
    env = A.world(tmp_path, monkeypatch, arm=arm, out_name=f"tg1-p426-{arm}-{session}.a1")
    env["ops"].extra_env.update(probe_env or {})
    if adjust:
        adjust(env)
    argv, r = S.p426_argv(env, mode, extra=extra)
    try:
        rc = S.run_p426(env, argv, rfd=r)
    finally:
        env["ops"].cancel()
    return rc, env


def chain_json(env):
    p = Path(env["out"]) / "chain.json"
    return json.loads(p.read_text()) if p.exists() else {}


def go_items(env):
    """The items that received `.go` (started), by the bare item name the probe ran (`<base>.item<k>.go` -> its invocation)."""
    return sorted(p.name for p in Path(env["out"]).rglob("*.go"))


def started_any(env):
    return bool(go_items(env))


def go_invocation_started(env):
    """True when an invocation of the Go language started items (its rows file stem names `opencode_go`)."""
    return any("opencode_go" in name for name in go_items(env))


def python_invocation_started(env):
    return any("opencode_python" in name for name in go_items(env))


def text(env):
    return "\n".join(env["lines"])


# ------------------------------------------------------------------------------------------------ post-reveal 3d (§16.8): topology
class Topology:
    """The §13 / §16.8 topology test's world: the REAL `p426_wave2` sequencer drives two hermetic P426 worlds (OFF, ON) under
    ONE `$STACK_WORKDIR`. `launch(argv)` of a chain runs the real `run_tg1_chain.main(argv[2:] + the test runner's probe /
    python / universe, ops=<the arm's FakeOps>)` on a thread; a watcher launch runs the real `bench_watch.main` on a thread
    (its `--interval` shortened, power from a fake meter). Each handle is bound to a real helper process (`pid`, start time
    through `chain_ops.default_create_time`, C151) that lives exactly as long as its thread, so the watcher's driver binding
    and the sequencer's liveness are real. No router, worker or model; the harvest and publication are recorded (s9)."""

    def __init__(self, tmp_path, monkeypatch):
        import sys
        self.tmp = Path(tmp_path)
        self.worlds = {arm: S.p426_world(self.tmp / arm, monkeypatch, arm=arm) for arm in ("off", "on")}
        monkeypatch.setenv("STACK_WORKDIR", str(self.tmp))
        self.wd = self.tmp
        self.main_root = self.tmp / "main"
        self.launches, self.harvested, self.dossiers, self.run_files, self.lines = [], [], [], [], []
        self.sys = sys

    # -- the frozen records the sequencer runs under (portable paths, the worlds' identity and pins)
    def records(self):
        ident = self.worlds["off"]["ident"]
        rec = self.tmp / "records"
        S.write_record(rec / "v8_base.json", S.v8_base(
            off_worktree="$STACK_WORKDIR/off/WT", on_worktree="$STACK_WORKDIR/on/WT",
            probe_code_sha256=ident["probe_code_sha256"], scaffold_policy_sha256=ident["scaffold_policy_sha256"],
            generation_identity_sha256=ident["generation_identity_sha256"],
            pins_sha256=S.sha256_file(self.worlds["off"]["wt"] / "src/mlx-vlm/dev/p369_phase2/pins.json"),
            frozen_prompt_date=S.EPOCH_DATE))
        return rec

    def argv(self, cmd, *extra):
        out = ["--record-dir", str(self.tmp / "records"), "--worktree-off", str(self.worlds["off"]["wt"]),
               "--worktree-on", str(self.worlds["on"]["wt"]), "--out-base", str(self.tmp / "p426/wave2")]
        return [cmd, *out, *extra]

    # -- §16.6 / §16.8 ops
    def _world_of(self, path):
        return next(e for e in self.worlds.values() if Path(e["wt"]) == Path(path))

    def worktree_state(self, path):
        return self._world_of(path)["ops"].worktree_state()

    def identity(self, path):
        ident = self._world_of(path)["ident"]
        return {k: ident[k] for k in ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256")}

    OPERATOR = "op.erator@corp-mail.example"          # a fake; the same operator address as add_scrub

    def operator_emails(self):
        return [self.OPERATOR]          # post-reveal 3g (§16.8 after delivery 3f): an empty operator-email set refuses rc 2

    def power(self):
        return dict(watts=140, volts=28, battery=80, on_battery_intervals=[])

    def historical_walls(self):
        return dict(w_python_s=300.0, w_go_s=200.0, max_request_elapsed_s=100.0)

    def harvest_path(self, attempt):
        return self.main_root / "benchmark/results/p426/wave2" / str(attempt)

    def harvest(self, leg_root, *, emails=()):
        import hashlib
        root = Path(leg_root)
        self.harvested.append(str(root))
        hj = self.harvest_path(root.name) / "HARVEST.json"
        hj.parent.mkdir(parents=True, exist_ok=True)
        hj.write_text(json.dumps(S.self_hashed(dict(leg=root.name.rsplit(".a", 1)[0], attempt=int(root.name.rsplit(".a", 1)[1]),
                                                    state="recorded", files=[], created="t"))))
        return {"rc": 0, "harvest_json": str(hj), "harvest_sha256": hashlib.sha256(hj.read_bytes()).hexdigest()}

    def publish_dossier(self, path, *, emails=()):
        self.dossiers.append(str(path))
        return {"published": [], "harvest_sha256": None, "rc": 0}

    def publish_run_files(self, paths, *, emails=()):
        self.run_files.append([str(p) for p in paths])
        return {"published": [], "harvest_sha256": None, "rc": 0}

    # -- processes
    def _helper(self):
        import subprocess
        return subprocess.Popen([self.sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def launch(self, argv, *, cwd=None, pass_fds=()):
        import threading
        from types import SimpleNamespace
        from bench import chain_ops as co
        argv = [str(a) for a in argv]
        helper = self._helper()
        res = {}
        if "--p426" in argv:
            arm = "on" if A.arg(argv, "--predictor") == "mtp" else "off"
            env = self.worlds[arm]
            t1c = S._t1c()
            chain_argv = argv[2:] + ["--probe", str(S.PROBE), "--python", self.sys.executable, "--universe", str(env["uni"]),
                                     "--arm-idle-s", "0"]

            def target():
                try:
                    res["rc"] = t1c.R.main(chain_argv, ops=env["ops"], timers=t1c.R.Timers(**t1c.TIMERS),
                                           log_out=self.lines.append, campaign=S.fake_campaign(A.arg(argv, "--campaign-core")))
                except SystemExit as e:
                    res["rc"] = e.code if isinstance(e.code, int) else 2
                except BaseException as e:  # noqa: BLE001
                    res["rc"], res["exc"] = 1, e
                finally:
                    helper.stdin.close()
            kind = "chain"
        else:
            if str(S.BENCH / "m1") not in self.sys.path:
                self.sys.path.insert(0, str(S.BENCH / "m1"))
            import bench_watch as W
            watch_argv = list(argv[2:])
            if "--interval" in watch_argv:
                watch_argv[watch_argv.index("--interval") + 1] = "0.1"
            else:
                watch_argv += ["--interval", "0.1"]

            def target():
                try:
                    res["rc"] = W.main(watch_argv, power=self.power)
                except BaseException as e:  # noqa: BLE001
                    res["rc"], res["exc"] = 1, e
                finally:
                    helper.stdin.close()
            kind = "watcher"
        th = threading.Thread(target=target, daemon=True)
        handle = SimpleNamespace(pid=helper.pid, start=co.default_create_time(helper.pid), argv=argv, kind=kind,
                                 thread=th, helper=helper, res=res)
        self.launches.append(handle)
        th.start()
        return handle

    def alive(self, pid, start):
        from bench import chain_ops as co
        h = next((x for x in self.launches if x.pid == pid), None)
        if h is None or h.helper.poll() is not None:
            return False
        try:
            return co.default_create_time(pid) == start
        except Exception:  # noqa: BLE001
            return False

    def wait(self, handle):
        handle.thread.join(300)
        handle.helper.wait(30)
        return handle.res.get("rc", 1)

    def chains(self):
        return [h for h in self.launches if h.kind == "chain"]

    def run(self, argv, timeout=600):
        """The real sequencer with a clock that advances its own waits (the 600 s idle gap, 30 s ticks) while the threads run."""
        import time
        clock = A.Clock(t=time.time(), on_sleep=lambda c: time.sleep(0.02))
        return A.run_sequencer(argv, self, clock, timeout=timeout)
