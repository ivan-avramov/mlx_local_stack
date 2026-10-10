"""C147 chain runner end-to-end against the fake probe (contract implementation) with a fake ChainOps.
The runner never starts a real router/worker here: every chain_ops call is injected."""
import importlib.util
import json
import os
import random
import signal
import sys
import threading
import time
from pathlib import Path

import pytest

from bench import chain_ops as co

REPO = Path(__file__).resolve().parents[3]
C147 = REPO / "benchmark/chains/c147"
PICK1, PICK2 = co.PICK1, co.PICK2


def _load(name):
    spec = importlib.util.spec_from_file_location(name, C147 / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


R = _load("run_tg1_chain")
FP = _load("fake_probe")


class FakeOps:
    """Every chain_ops call the runner makes, recorded. Workers get distinct pid/create_time per load."""

    def __init__(self, wd):
        self.wd = Path(wd)
        self.tmpdir = self.wd / "c147/tmp"
        self.state = self.wd / "fakestate"
        self.state.mkdir(parents=True, exist_ok=True)
        self.calls = []
        self.pid = 1000
        self.ident = None
        self.loaded = None
        self.metrics = {"summary": {"in_flight": 0}}
        self.extra_env = {}
        self.on_unload = None
        self.power = True
        self.leftover_calls = []

    def _c(self, name, *a):
        self.calls.append((name,) + a)

    def ensure_overlay(self):
        self._c("ensure_overlay")

    def overlay_sha(self):
        return "a" * 64

    def power_ok(self):
        self._c("power_ok")
        return self.power

    def power_state(self):
        return {"watts": 140, "volts": 28, "batt": 80}

    def free_mem_mb(self):
        return 12345

    def start_state(self):
        self._c("start_state")
        return {"watts": 140, "volts": 28, "batt": 80, "free_mem_mb": 1, "busy": [], "orphans_clean": True}

    def start_router(self):
        self._c("start_router")
        return 1

    def load(self, model):
        self.pid += 1
        self.ident = {"pid": self.pid, "create_time": 1.7e9 + self.pid, "cmdline": "mlx_vlm.server --model x"}
        self.loaded = model
        (self.state / "worker.json").write_text(json.dumps(
            {"pid": self.pid, "create_time": self.ident["create_time"], "model_path": "caslca/" + model,
             "registry_sha256": "a" * 64}))
        self._c("load", model, self.pid)
        return dict(self.ident)

    def unload(self, model):
        self._c("unload", model)
        self.loaded = None
        if self.on_unload:
            self.on_unload()
        return True

    def a4_gate(self, model, tag):
        self._c("a4_gate", model)
        return str(self.wd / "session_gate/a4_v2_latest.json")

    def stop_stack(self):
        self._c("stop_stack")
        return 0

    def worker_metrics(self):
        m = self.metrics
        return m() if callable(m) else m

    def worker_ident(self, model):
        if not self.loaded:
            return None
        return {"pid": self.ident["pid"], "create_time": self.ident["create_time"]}

    def create_time(self, pid):
        return 1.0

    def env_base(self):
        env = dict(os.environ)
        env.update(STACK_WORKDIR=str(self.wd), FAKE_PROBE_STATE=str(self.state), FAKE_ITEM_S="0.03",
                   FAKE_HB_S="0.02", FAKE_TICK_S="0.01")
        env.update(self.extra_env)
        return env

    def rows(self, path):
        return co.ChainOps.rows(self, path)

    def leftovers(self, roots, run_ids=()):
        self.leftover_calls.append((list(roots), list(run_ids)))
        return ["process 99: leftover under scratch"]

    def names(self, prefix):
        return [c for c in self.calls if c[0] == prefix]


TIMERS = dict(poll_s=0.02, watch_s=0.15, idle_sample_s=0.05, hb_age_s=0.3, idle_needed=3, manifest_alarm_s=0.4,
              term_wait_s=0.6, kill_wait_s=3.0, barrier_exit_wait_s=3.0, t_coop_scale=1e-4)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    ops = FakeOps(tmp_path)
    uni = tmp_path / "universe.json"
    uni.write_text(json.dumps({"items": {**{f"python/p{i}": {} for i in range(1, 7)},
                                         **{f"go/g{i}": {} for i in range(1, 7)}}}))
    lines = []
    yield dict(wd=tmp_path, ops=ops, uni=uni, lines=lines, out=tmp_path / "c147")
    # leftover fake probes from a failed test
    inv = ops.state / "invocations.jsonl"
    if inv.exists():
        for ln in inv.read_text().splitlines():
            try:
                os.kill(json.loads(ln)["pid"], signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def run(env, argv, timers=None, plan=None, behaviour=None, extra_env=None, timeout=90, helper=None, universe=True):
    ops = env["ops"]
    if plan is not None:
        ops.extra_env["FAKE_PROBE_PLAN"] = json.dumps(plan)
    if behaviour is not None:
        ops.extra_env["FAKE_PROBE_BEHAVIOUR"] = behaviour
    ops.extra_env.update(extra_env or {})
    full = list(argv) + ["--probe", str(C147 / "fake_probe.py"), "--python", sys.executable, "--out-root",
                         str(env["out"]), "--arm-idle-s", "0"]
    if universe:
        full += ["--universe", str(env["uni"])]
    tm = R.Timers(**{**TIMERS, **(timers or {})})
    res = {}

    def target():
        try:
            res["rc"] = R.main(full, ops=ops, timers=tm, log_out=env["lines"].append)
        except BaseException as e:  # noqa: BLE001
            res["exc"] = e

    th = threading.Thread(target=target, daemon=True)
    th.start()
    if helper:
        threading.Thread(target=helper, daemon=True).start()
    th.join(timeout)
    if th.is_alive():
        pytest.fail("runner did not finish: " + "\n".join(env["lines"][-15:]))
    if "exc" in res:
        raise res["exc"]
    return res["rc"]


def log_has(env, text):
    return any(text in ln for ln in env["lines"])


def wait_for(cond, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def invocations(env):
    p = env["ops"].state / "invocations.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()] if p.exists() else []


def arg(argv, flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


def chain_json(env):
    return json.loads((env["out"] / "chain.json").read_text())


CHAIN = ["chain", "s1", "--probe-code-sha", "p" * 64]
PILOT = ["pilot"]


# --------------------------------------------------------------------------- schedule
def test_universe_is_22_python_21_go():
    names = R.load_universe()
    assert len(names["python"]) == 22 and len(names["go"]) == 21 and "counter" not in names["go"]


def test_schedule_order_blocks_seeds_reload():
    names = R.load_universe()
    blocks = R.schedule("chain", ["s1", "s2", "reload"], names, "/o")
    assert [(b["session"], b["model"], [leg["lang"] for leg in b["legs"]]) for b in blocks] == [
        ("s1", PICK1, ["python", "go"]), ("s1", PICK2, ["python", "go"]),
        ("s2", PICK2, ["python", "go"]), ("s2", PICK1, ["python", "go"]),
        ("reload", PICK1, ["python"])]
    assert [b["seed_base"] for b in blocks] == [1001, 1001, 2002, 2002, 1001]
    for b in blocks:
        assert all(leg["seed_base"] == b["seed_base"] for leg in b["legs"])
    for leg in (leg for b in blocks[:4] for leg in b["legs"]):
        assert len(leg["pilot_names"]) == 5 and set(leg["pilot_names"]) <= set(leg["full_names"])
        assert leg["full_names"] == sorted(names[leg["lang"]])
    reload_leg = blocks[4]["legs"][0]
    assert reload_leg["full_names"] == reload_leg["pilot_names"] == sorted(random.Random(1001).sample(names["python"], 5))
    assert reload_leg["out"] == f"/o/reload/{PICK1}.reload.opencode_python.jsonl"
    assert blocks[0]["legs"][0]["out"] == f"/o/s1/{PICK1}.s1.opencode_python.jsonl"


def test_pilot_mode_schedule_is_one_pick1_python_pilot_step():
    b = R.schedule("pilot", [], R.load_universe(), "/o")
    assert len(b) == 1 and b[0]["model"] == PICK1 and b[0]["legs"][0]["lang"] == "python" and b[0]["pilot_only"]
    assert [s["kind"] for s in R.steps_for(b[0], 0)] == ["pilot"]


def test_steps_pilot_then_full_first_leg_only():
    names = R.load_universe()
    blk = R.schedule("chain", ["s1"], names, "/o")[0]
    assert [s["kind"] for s in R.steps_for(blk, 0)] == ["pilot", "full"]
    assert [s["kind"] for s in R.steps_for(blk, 1)] == ["full"]


def test_build_cmd_exact_vectors():
    leg = dict(model=PICK1, lang="python", seed_base=1001, out="/o/x.jsonl")
    pilot = dict(kind="pilot", names=["a", "b"], limit=5)
    full = dict(kind="full", names=["a", "b", "c"], limit=None)
    assert R.build_cmd("/py", "/probe.py", leg, pilot, "/r.json", "/c", "/k") == [
        "/py", "/probe.py", "--model", PICK1, "--items", "a,b", "--lang", "python", "--seed-base", "1001",
        "--out", "/o/x.jsonl", "--scaffold", "opencode-v2-web-tg1", "--expect-items", "python/a,python/b",
        "--a4-v2-receipt", "/r.json", "--sampling-profile", "deployed", "--cancel-file", "/c", "--manifest-ack",
        "/k", "--limit", "5"]
    cmd = R.build_cmd("/py", "/probe.py", leg, full, "/r.json", "/c", "/k")
    assert "--limit" not in cmd and arg(cmd, "--items") == "a,b,c" and arg(cmd, "--expect-items") == "python/a,python/b,python/c"


def test_chain_requires_probe_code_sha(env):
    with pytest.raises(SystemExit) as e:
        R.parse_args(["chain"])
    assert e.value.code == 2
    assert R.parse_args(["pilot"]).probe_code_sha is None


# --------------------------------------------------------------------------- end to end
def test_pilot_mode_end_to_end(env):
    rc = run(env, PILOT)
    assert rc == 0
    inv = invocations(env)
    assert len(inv) == 1
    argv = inv[0]["argv"]
    assert arg(argv, "--limit") == "5" and len(arg(argv, "--items").split(",")) == 5
    assert arg(argv, "--expect-items") == ",".join("python/" + n for n in arg(argv, "--items").split(","))
    assert arg(argv, "--scaffold") == "opencode-v2-web-tg1" and arg(argv, "--sampling-profile") == "deployed"
    assert arg(argv, "--cancel-file").endswith(".attempt1.CANCEL") and arg(argv, "--manifest-ack").endswith(".attempt1.ACK")
    out = env["out"] / "pilot" / f"{PICK1}.pilot.opencode_python.jsonl"
    assert len(out.read_text().splitlines()) == 5
    att = json.loads((env["out"] / "pilot" / f"{PICK1}.pilot.opencode_python.attempt1.json").read_text())
    assert att["rc"] == 0 and att["run_id"] and att["worker"]["pid"] == 1001 and att["cancel"] and att["ack"] and att["argv"]
    assert att["cleanup_status"]["uncertain"] is False and att["probe_pid"] > 0
    names = [c[0] for c in env["ops"].calls]
    assert names[:1] == ["ensure_overlay"] and "start_router" in names and names[-2:] == ["unload", "stop_stack"]
    cj = chain_json(env)
    assert cj["rc"] == 0 and cj["status"] == "finished" and len(cj["attempts"]) == 1
    assert all(len(cj["sha256"][k]) == 64 for k in ("runner", "chain_ops", "gate", "overlay"))


def test_pilot_then_full_same_rows_file_and_blocks(env):
    rc = run(env, CHAIN)
    assert rc == 0
    inv = [i["argv"] for i in invocations(env)]
    assert len(inv) == 6                                  # per block: python pilot, python full, go full
    for blk in (0, 3):
        pilot, full, go = inv[blk], inv[blk + 1], inv[blk + 2]
        model = arg(pilot, "--model")
        assert arg(pilot, "--limit") == "5" and arg(pilot, "--out") == arg(full, "--out")
        assert "--limit" not in full and len(arg(full, "--items").split(",")) == 6
        assert set(arg(pilot, "--items").split(",")) <= set(arg(full, "--items").split(","))
        assert arg(go, "--lang") == "go" and "--limit" not in go and arg(go, "--model") == model
        assert arg(pilot, "--a4-v2-receipt") == arg(go, "--a4-v2-receipt")
    assert [arg(inv[i], "--model") for i in (0, 3)] == [PICK1, PICK2]
    for stem_model in (PICK1, PICK2):
        for lang in ("python", "go"):
            f = env["out"] / "s1" / f"{stem_model}.s1.opencode_{lang}.jsonl"
            assert len(f.read_text().splitlines()) == 6
    loads = env["ops"].names("load")
    assert [c[1] for c in loads] == [PICK1, PICK2]
    # worker identity: one value inside a block (both legs), distinct across blocks
    def worker(model, lang):
        return json.loads((env["out"] / "s1" / f"{model}.s1.opencode_{lang}.manifest.json").read_text())["worker"]
    assert worker(PICK1, "python") == worker(PICK1, "go") != worker(PICK2, "python") == worker(PICK2, "go")
    names = [c[0] for c in env["ops"].calls]
    assert names.index("unload") < [i for i, n in enumerate(names) if n == "load"][1]       # fresh load per block


def test_all_sessions_reload_control(env):
    rc = run(env, ["chain", "--probe-code-sha", "p" * 64], timeout=120)
    assert rc == 0
    assert [c[1] for c in env["ops"].names("load")] == [PICK1, PICK2, PICK2, PICK1, PICK1]
    assert len({c[2] for c in env["ops"].names("load")}) == 5
    rl = env["out"] / "reload" / f"{PICK1}.reload.opencode_python.jsonl"
    assert len(rl.read_text().splitlines()) == 5
    assert len([i for i in invocations(env) if arg(i["argv"], "--out") == str(rl)]) == 1     # pilot == full set: one step
    s2 = json.loads((env["out"] / "s2" / f"{PICK2}.s2.opencode_python.manifest.json").read_text())
    assert s2["runtime"]["seed_base"] == 2002


# --------------------------------------------------------------------------- barrier
@pytest.mark.parametrize("override,frag", [
    ({"runtime.probe_code_sha256": "x" * 64}, "probe_code_sha256"),
    ({"runtime.scaffold_policy_sha256": "0" * 64}, "scaffold_policy_sha256"),
    ({"runtime.draft_kind": "mtp"}, "draft_kind"),
    ({"runtime.seed_base": 7}, "seed_base"),
    ({"runtime.lang": "go"}, "lang"),
    ({"runtime.scaffold": "opencode-v2-web"}, "scaffold"),
    ({"model": PICK2}, "model"),
    ({"registry.sha256": "b" * 64}, "registry.sha256"),
    ({"worker": {"pid": 5, "create_time": 1.0, "model_path": "m", "registry_sha256": "a" * 64}}, "worker identity"),
    ({"worker": {"pid": "5"}}, "untyped"),
])
def test_first_manifest_mismatch_no_ack_cancel_exit_2(env, override, frag):
    rc = run(env, CHAIN, extra_env={"FAKE_MANIFEST_OVERRIDE": json.dumps(override)})
    assert rc == 2
    sdir = env["out"] / "s1"
    assert not list(sdir.glob("*.ACK"))
    assert list(sdir.glob("*.CANCEL"))
    assert log_has(env, "BARRIER MISMATCH") and any(frag in ln for ln in env["lines"] if "MISMATCH" in ln)
    assert not list(sdir.glob("*.jsonl"))                         # nothing generated
    assert len(invocations(env)) == 1


def test_barrier_acks_before_item_one(env):
    run(env, PILOT)
    sdir = env["out"] / "pilot"
    assert list(sdir.glob("*.ACK")) and not list(sdir.glob("*.CANCEL"))


def test_missing_manifest_is_alarm_only_until_stop(env):
    stop = env["out"] / "STOP"
    cancel_seen = []

    def helper():
        time.sleep(1.2)
        cancel_seen.append(bool(list((env["out"] / "pilot").glob("*.CANCEL"))))
        stop.write_text("")
    rc = run(env, PILOT, behaviour="no_manifest", helper=helper)
    assert cancel_seen == [False]
    assert log_has(env, "ALARM manifest missing")
    assert rc == 3


# --------------------------------------------------------------------------- idle predicate / cancellation
def _stop_after(env, delay, check):
    def helper():
        time.sleep(delay)
        check()
        (env["out"] / "STOP").write_text("")
    return helper


@pytest.mark.parametrize("behaviour,metrics", [
    ("hang_in_item", {"summary": {"in_flight": 1}}),                         # busy never cancels
    ("hang_in_item", None),                                                  # unreadable metrics never counts
    ("stale_heartbeat_growing_events", {"summary": {"in_flight": 0}}),       # stale heartbeat, growing events
])
def test_no_automatic_cancel_then_stop_cancels_exit_3(env, behaviour, metrics):
    env["ops"].metrics = metrics
    seen = []
    helper = _stop_after(env, 1.5, lambda: seen.append(list((env["out"] / "pilot").glob("*.CANCEL"))))
    rc = run(env, PILOT, behaviour=behaviour, helper=helper)
    assert seen == [[]]
    assert rc == 3
    sdir = env["out"] / "pilot"
    stopped = list((sdir / "stopped").glob("*"))
    assert len(stopped) == 1 and any(f.name.endswith(".CANCEL") for f in stopped[0].iterdir())
    assert (next(f for f in stopped[0].iterdir() if f.name.endswith(".CANCEL"))).read_text().strip() == "STOP"
    assert chain_json(env)["restarts"] == [] and chain_json(env)["stop"]["where"] == "leg"
    assert not [c for c in env["ops"].calls if c[0] == "load"][1:]                  # no restart consumed


def test_idle_cancel_archive_restart_validates_block(env):
    rc = run(env, CHAIN, plan=["normal", "normal", "hang_in_item", "normal"])
    assert rc == 0
    cj = chain_json(env)
    assert len(cj["restarts"]) == 1
    arch = Path(cj["restarts"][0]["archive"])
    names = sorted(f.name for f in arch.iterdir())
    # block = both legs archived (the completed python leg too), every attempt: rows/manifest/log/attempt.json/cancel/ack
    for lang in ("python", "go"):
        stem = f"{PICK1}.s1.opencode_{lang}"
        if lang == "python":
            assert stem + ".jsonl" in names                 # the completed leg is archived with the block
        assert stem + ".manifest.json" in names
        assert any(n.startswith(stem + ".attempt") and n.endswith(".log") for n in names)
        assert any(n.startswith(stem + ".attempt") and n.endswith(".json") for n in names)
    assert any(n.endswith(".CANCEL") for n in names) and any(n.endswith(".ACK") for n in names)
    assert arch.parent.name == "incomplete" and arch.name.startswith(PICK1 + ".")
    # fresh instance, rerun from the first leg incl. the pilot step, same items and seeds
    loads = [c for c in env["ops"].calls if c[0] == "load"]
    assert [c[1] for c in loads] == [PICK1, PICK1, PICK2] and len({c[2] for c in loads}) == 3
    seq = [c[0] for c in env["ops"].calls]
    assert seq.index("unload") < [i for i, n in enumerate(seq) if n == "load"][1]
    inv = [x["argv"] for x in invocations(env)]
    assert arg(inv[3], "--limit") == "5" and arg(inv[3], "--items") == arg(inv[0], "--items")
    assert arg(inv[3], "--seed-base") == arg(inv[0], "--seed-base")
    assert arg(inv[3], "--cancel-file") != arg(inv[0], "--cancel-file")                # unique per attempt
    for lang in ("python", "go"):
        assert len((env["out"] / "s1" / f"{PICK1}.s1.opencode_{lang}.jsonl").read_text().splitlines()) == 6
    assert log_has(env, "CANCEL file written (idle)") and log_has(env, "T_coop=")
    w1 = json.loads((env["out"] / "s1" / f"{PICK1}.s1.opencode_python.manifest.json").read_text())["worker"]
    assert w1["pid"] == 1002                                                             # the restarted instance


def test_second_incomplete_in_a_block_exits_2(env):
    rc = run(env, ["chain", "reload", "--probe-code-sha", "p" * 64], plan=["abort_after_n"],
             extra_env={"FAKE_N": "1"})
    assert rc == 2
    cj = chain_json(env)
    assert len(cj["restarts"]) == 1
    assert log_has(env, "incomplete twice")
    assert len(env["ops"].names("load")) == 2


def test_probe_rc_nonzero_after_all_rows_is_incomplete(env):
    # abort_after_n with N=5 on the 5-item reload block: rows complete, but rc != 0 and manifest aborted
    rc = run(env, ["chain", "reload", "--probe-code-sha", "p" * 64], plan=["abort_after_n", "normal"],
             extra_env={"FAKE_N": "5"})
    assert rc == 0
    assert log_has(env, "rc_nonzero") and log_has(env, "manifest_abort")
    assert len(chain_json(env)["restarts"]) == 1


# --------------------------------------------------------------------------- escalation
def test_escalation_sigterm_then_restart(env):
    rc = run(env, ["chain", "reload", "--probe-code-sha", "p" * 64], plan=["ignore_cancel", "normal"],
             extra_env={"FAKE_PROBE_ACK_WAIT": "30"})
    assert rc == 0
    assert log_has(env, "CANCEL file written (idle)") and log_has(env, "ESCALATE SIGTERM")
    assert not log_has(env, "ESCALATE SIGKILL")
    first = chain_json(env)["attempts"][0]
    assert first["rc"] == 143 and first["cleanup_status"]["uncertain"] is False


def test_escalation_sigkill_leaves_no_cleanup_status_restart_refused(env):
    rc = run(env, ["chain", "reload", "--probe-code-sha", "p" * 64], plan=["ignore_cancel"],
             extra_env={"FAKE_IGNORE_TERM": "1"})
    assert rc == 2
    assert log_has(env, "ESCALATE SIGTERM") and log_has(env, "ESCALATE SIGKILL")
    assert log_has(env, "restart refused") and log_has(env, "LEFTOVER (listed, not killed)")
    assert env["ops"].leftover_calls and chain_json(env)["restarts"] == []
    assert chain_json(env)["attempts"][0]["rc"] == -signal.SIGKILL


def test_escalation_held_while_activity_resumed(env):
    state = {"busy": False}
    env["ops"].metrics = lambda: {"summary": {"in_flight": 1 if state["busy"] else 0}}

    def helper():
        wait_for(lambda: log_has(env, "CANCEL file written (idle)"))
        state["busy"] = True
        time.sleep(0.9)
        state["busy"] = False
    rc = run(env, ["chain", "reload", "--probe-code-sha", "p" * 64], plan=["ignore_cancel", "normal"],
             helper=helper, extra_env={"FAKE_PROBE_ACK_WAIT": "30"})
    held = [ln for ln in env["lines"] if "ESCALATION HELD" in ln]
    assert len(held) >= 2
    first_held = next(i for i, ln in enumerate(env["lines"]) if "ESCALATION HELD" in ln)
    sigterm = next(i for i, ln in enumerate(env["lines"]) if "ESCALATE SIGTERM" in ln)
    assert first_held < sigterm
    assert rc == 0


def test_escalation_unreadable_metrics_sends_no_signal_exit_2(env):
    state = {"bad": False}
    env["ops"].metrics = lambda: None if state["bad"] else {"summary": {"in_flight": 0}}

    def helper():
        wait_for(lambda: log_has(env, "CANCEL file written (idle)"))
        state["bad"] = True
    rc = run(env, ["chain", "reload", "--probe-code-sha", "p" * 64], plan=["ignore_cancel", "normal"], helper=helper,
             extra_env={"FAKE_PROBE_ACK_WAIT": "30"})
    assert rc == 2
    assert not log_has(env, "ESCALATE SIGTERM") and log_has(env, "no signal sent")
    assert env["ops"].leftover_calls


def test_escalation_worker_identity_drift_sends_no_signal_exit_2(env):
    orig = env["ops"].worker_ident

    def drifting(model):
        r = orig(model)
        if r and log_has(env, "CANCEL file written (idle)"):
            return {"pid": r["pid"] + 500, "create_time": r["create_time"]}
        return r
    env["ops"].worker_ident = drifting
    rc = run(env, ["chain", "reload", "--probe-code-sha", "p" * 64], plan=["ignore_cancel", "normal"],
             extra_env={"FAKE_PROBE_ACK_WAIT": "30"})
    assert rc == 2
    assert not log_has(env, "ESCALATE SIGTERM") and log_has(env, "no signal sent")


def test_escalation_held_when_heartbeat_activity_resumed(env):
    def helper():
        wait_for(lambda: log_has(env, "CANCEL file written (idle)"))
        logf = next((env["out"] / "reload").glob("*.attempt1.log"))
        for k in range(12):
            with logf.open("a") as f:
                f.write(json.dumps({"m62_watch": {"requests_completed": 10 + k, "last_prompt_tokens": 1}, "elapsed_s": k}) + "\n")
            time.sleep(0.08)
    rc = run(env, ["chain", "reload", "--probe-code-sha", "p" * 64], plan=["ignore_cancel", "normal"], helper=helper,
             extra_env={"FAKE_PROBE_ACK_WAIT": "30"})
    assert log_has(env, "ESCALATION HELD") and any("heartbeat" in ln for ln in env["lines"] if "HELD" in ln)
    assert rc == 0


# --------------------------------------------------------------------------- restart eligibility
@pytest.mark.parametrize("extra,metrics,frag", [
    ({"FAKE_CLEANUP_UNCERTAIN": "1"}, None, "cleanup uncertain"),
    ({}, {"summary": {"in_flight": 2}}, "worker health"),
    ({}, "unreadable", "worker health"),
])
def test_restart_refused_lists_and_kills_nothing(env, extra, metrics, frag):
    if metrics == "unreadable":
        env["ops"].metrics = None
    elif metrics is not None:
        env["ops"].metrics = metrics
    rc = run(env, ["chain", "reload", "--probe-code-sha", "p" * 64], plan=["abort_after_n"], extra_env=extra)
    assert rc == 2
    assert log_has(env, "restart refused") and any(frag in ln for ln in env["lines"] if "restart refused" in ln)
    assert log_has(env, "LEFTOVER (listed, not killed)")
    assert env["ops"].leftover_calls[0][0] == [str(env["ops"].tmpdir)]
    assert not (env["out"] / "reload" / "incomplete").exists()
    assert len(env["ops"].names("load")) == 1                    # no restart


def test_restart_refused_when_worker_identity_changed(env):
    orig = env["ops"].worker_ident

    def drifting(model):
        r = orig(model)
        return {"pid": r["pid"] + 500, "create_time": r["create_time"]} if r and invocations(env) else r
    env["ops"].worker_ident = drifting
    rc = run(env, ["chain", "reload", "--probe-code-sha", "p" * 64], plan=["abort_after_n"])
    assert rc == 2 and log_has(env, "identity changed")


# --------------------------------------------------------------------------- STOP
def test_stop_during_pilot_exit_3_archives_under_stopped(env):
    helper = _stop_after(env, 0.4, lambda: None)
    rc = run(env, PILOT, behaviour="hang_in_item", helper=helper)
    assert rc == 3
    stopped = list((env["out"] / "pilot" / "stopped").glob("*"))
    assert len(stopped) == 1 and stopped[0].name.startswith(f"{PICK1}.pilot.opencode_python.")
    assert chain_json(env)["restarts"] == [] and len(env["ops"].names("load")) == 1
    assert env["ops"].names("stop_stack")


def test_stop_during_full_leg(env):
    def helper():
        wait_for(lambda: len(invocations(env)) == 2)
        wait_for(lambda: list((env["out"] / "s1").glob("*attempt2.ACK")))
        (env["out"] / "STOP").write_text("")
    rc = run(env, CHAIN, plan=["normal", "hang_in_item"], helper=helper)
    assert rc == 3
    assert len(invocations(env)) == 2                                  # no further launches
    assert list((env["out"] / "s1" / "stopped").glob("*"))
    assert chain_json(env)["restarts"] == []


def test_stop_during_restart_preparation(env):
    def hook():
        if len(env["ops"].names("unload")) == 1:
            (env["out"] / "STOP").write_text("")
    env["ops"].on_unload = hook
    rc = run(env, ["chain", "reload", "--probe-code-sha", "p" * 64], plan=["abort_after_n", "normal"])
    assert rc == 3
    assert len(env["ops"].names("load")) == 1 and len(invocations(env)) == 1
    assert chain_json(env)["stop"]["where"] == "restart preparation"


def test_stop_at_block_boundary(env):
    def hook():
        (env["out"] / "STOP").write_text("")
    env["ops"].on_unload = hook
    rc = run(env, CHAIN)
    assert rc == 3
    assert len(env["ops"].names("load")) == 1 and len(invocations(env)) == 3
    assert chain_json(env)["stop"]["where"] == "block boundary"


def test_stop_present_at_start_launches_nothing(env):
    env["out"].mkdir(parents=True)
    (env["out"] / "STOP").write_text("")
    rc = run(env, PILOT)
    assert rc == 3 and not env["ops"].names("start_router") and not invocations(env)


# --------------------------------------------------------------------------- refusals / exit codes
def test_stale_cancel_file_refuses_spawn(env):
    sdir = env["out"] / "pilot"
    sdir.mkdir(parents=True)
    (sdir / f"{PICK1}.pilot.opencode_python.attempt1.CANCEL").write_text("x")
    rc = run(env, PILOT)
    assert rc == 2 and not invocations(env) and log_has(env, "stale cancel/ack")


def test_stale_ack_file_refuses_spawn(env):
    sdir = env["out"] / "pilot"
    sdir.mkdir(parents=True)
    (sdir / f"{PICK1}.pilot.opencode_python.attempt1.ACK").write_text("x")
    assert run(env, PILOT) == 2


def test_power_gate_failure_aborts_2(env):
    env["ops"].power = False
    assert run(env, PILOT) == 2 and not invocations(env)
    assert env["ops"].names("stop_stack")


def test_unexpected_error_propagates_and_stack_stops(env):
    def boom():
        raise RuntimeError("boom")
    env["ops"].start_router = boom
    with pytest.raises(RuntimeError):
        run(env, PILOT)
    assert env["ops"].names("stop_stack") and chain_json(env)["status"] == "crashed"


# --------------------------------------------------------------------------- watcher
def test_watcher_fields_and_correction(env):
    # slow items so several ticks occur; a tiny --pred-s makes ETA/prediction exceed 1.5
    env["ops"].extra_env.update(FAKE_ITEM_S="0.4", FAKE_HB_S="0.1")
    rc = run(env, PILOT + ["--pred-s", f"python:{PICK1}=0.01"], timers=dict(watch_s=0.25))
    assert rc == 0
    watch = [ln for ln in env["lines"] if " WATCH " in ln]
    assert len(watch) >= 2
    w = [ln for ln in watch if "/5 passed=" in ln and "kinds={'ok'" in ln][-1]
    for frag in ("a1:", "/5 passed=", "mean=", "eta=", "pred=", "ratio=", "kinds=", "conv=", "out_tok_p50/p90/max=",
                 "budget_hits=", "adapter=140W 28V batt=80%", "free_mem_mb=12345", "hb_age=", "hb="):
        assert frag in w, frag
    assert any("CORRECTION?" in ln for ln in watch)
    assert any('"requests_completed": 3' in ln for ln in watch)


def test_watcher_default_prediction_is_pilot_mean_and_no_false_correction(env):
    env["ops"].extra_env.update(FAKE_ITEM_S="0.3")
    rc = run(env, PILOT, timers=dict(watch_s=0.2))
    assert rc == 0
    ticks = [ln for ln in env["lines"] if " WATCH " in ln and "5/5" in ln]
    # with 5 rows the prediction is the pilot mean itself: ratio 1.00, no CORRECTION?
    assert not ticks or all("CORRECTION?" not in ln for ln in ticks)


def test_watcher_alarm_past_threshold(env, monkeypatch):
    monkeypatch.setattr(co, "alarm_s", lambda n, m, mx: 0.05)
    env["ops"].extra_env.update(FAKE_ITEM_S="0.3")
    assert run(env, PILOT, timers=dict(watch_s=0.2)) == 0
    assert any("ALARM elapsed=" in ln for ln in env["lines"])


def test_watcher_flags_transport_abort_lines(env):
    def helper():
        wait_for(lambda: list((env["out"] / "pilot").glob("*.attempt1.log")))
        time.sleep(0.3)
        with next((env["out"] / "pilot").glob("*.attempt1.log")).open("a") as f:
            f.write("TransportAbort: injected\n")
        assert wait_for(lambda: any("CORRECTION?" in ln for ln in env["lines"] if " WATCH " in ln), 10)
        (env["out"] / "STOP").write_text("")
    rc = run(env, PILOT, behaviour="hang_in_item", timers=dict(watch_s=0.1), helper=helper)
    assert rc == 3


# --------------------------------------------------------------------------- inject driver
RI = _load("run_inject")


STUB_PROBE = """
import sys, os, json
a = sys.argv[1:]
out = a[a.index("--out") + 1]
open(os.environ["STUB_LOG"], "a").write(json.dumps(a) + "\\n")
open(out, "w").write(json.dumps({"id": "x"}) + "\\n")
sys.exit(int(os.environ.get("STUB_PROBE_RC", "0")))
"""

STUB_VERIFY = """
import sys, os, json, glob
d = sys.argv[sys.argv.index("--run") + 1]
script = json.load(open(os.environ["STUB_SCRIPT"]))
n = int(open(os.environ["STUB_COUNT"]).read()) if os.path.exists(os.environ["STUB_COUNT"]) else 0
open(os.environ["STUB_COUNT"], "w").write(str(n + 1))
rc, lines = script[min(n, len(script) - 1)]
files = sorted(os.path.basename(f)[:-6] for f in glob.glob(d + "/*.jsonl"))
for f in files:
    print(f + " " + lines.get(f.split(".")[0] + "." + f.split(".")[1], lines.get("*", "PASS")))
sys.exit(rc)
"""


def _inject_env(env, tmp_path, script, probe_rc="0"):
    probe = tmp_path / "stub_probe.py"
    probe.write_text(STUB_PROBE)
    ver = tmp_path / "stub_verify.py"
    ver.write_text(STUB_VERIFY)
    (tmp_path / "script.json").write_text(json.dumps(script))
    env["ops"].extra_env.update(STUB_LOG=str(tmp_path / "probe.log"), STUB_SCRIPT=str(tmp_path / "script.json"),
                                STUB_COUNT=str(tmp_path / "count"), STUB_PROBE_RC=probe_rc)
    return ["--probe", str(probe), "--verify", str(ver), "--python", sys.executable, "--universe", str(env["uni"]),
            "--out-dir", str(tmp_path / "m62inject"), "--min-free-mb", "1"]


def _run_inject(env, args):
    return RI.main(args, ops=env["ops"], log_out=env["lines"].append)


def _probe_args(tmp_path):
    return [json.loads(x) for x in (tmp_path / "probe.log").read_text().splitlines()]


def test_inject_items_distinct_seeded_python_one_per_kind():
    names = R.load_universe()
    items = RI.pick_items(names)
    assert list(items) == ["stall", "loop", "alloc"] and len(set(items.values())) == 3
    assert all(i in names["python"] for i in items.values())
    assert items == RI.pick_items(names)                          # deterministic draw


def test_inject_happy_path_three_legs_final_suite_unload_stop(env, tmp_path):
    args = _inject_env(env, tmp_path, [[0, {"*": "PASS"}]])
    rc = _run_inject(env, args)
    assert rc == 0
    legs = _probe_args(tmp_path)
    assert len(legs) == 3
    assert [x[x.index("--tg1-inject") + 1] for x in legs] == ["stall", "loop", "alloc"]
    for x, n in zip(legs, (1, 1, 1)):
        assert x[x.index("--seed-base") + 1] == "1001" and x[x.index("--out") + 1].endswith(f".attempt{n}.jsonl")
        assert "--limit" not in x and x[x.index("--scaffold") + 1] == "opencode-v2-web-tg1"
        assert x[x.index("--expect-items") + 1] == "python/" + x[x.index("--items") + 1]
    names = [c[0] for c in env["ops"].calls]
    assert names[-2:] == ["unload", "stop_stack"] and "a4_gate" in names
    assert env["ops"].names("load")[0][1] == PICK1
    assert str(tmp_path / "m62inject") in legs[0][legs[0].index("--out") + 1]


def test_inject_retry_on_not_observed_uses_next_seed_same_item(env, tmp_path):
    # leg 1: not_observed (rc 4) -> retried with seed 2002 on the same item; then PASS everywhere
    script = [[4, {"stall.attempt1": "not_observed:x"}], [0, {"*": "PASS"}]]
    args = _inject_env(env, tmp_path, script)
    rc = _run_inject(env, args)
    legs = _probe_args(tmp_path)
    assert [x[x.index("--tg1-inject") + 1] for x in legs][:2] == ["stall", "stall"]
    assert [x[x.index("--seed-base") + 1] for x in legs][:2] == ["1001", "2002"]
    assert legs[0][legs[0].index("--items") + 1] == legs[1][legs[1].index("--items") + 1]
    assert rc == 0


def test_inject_three_misses_is_a_build_finding_rc_4(env, tmp_path):
    args = _inject_env(env, tmp_path, [[4, {"*": "competing_trigger:T"}]])
    assert _run_inject(env, args) == 4
    legs = _probe_args(tmp_path)
    assert [x[x.index("--seed-base") + 1] for x in legs] == ["1001", "2002", "3003"]
    assert log_has(env, "BUILD FINDING") and env["ops"].names("stop_stack")


def test_inject_fail_verdict_stops_driver_rc_1(env, tmp_path):
    args = _inject_env(env, tmp_path, [[1, {"*": "FAIL:sha mismatch"}]])
    assert _run_inject(env, args) == 1
    assert len(_probe_args(tmp_path)) == 1 and env["ops"].names("stop_stack")


def test_inject_probe_failure_aborts_2_no_verify(env, tmp_path):
    args = _inject_env(env, tmp_path, [[0, {"*": "PASS"}]], probe_rc="3")
    assert _run_inject(env, args) == 2
    assert not (tmp_path / "count").exists()
    assert log_has(env, "transport failure aborts")


def test_inject_prechecks_memory_and_idle_worker(env, tmp_path):
    args = _inject_env(env, tmp_path, [[0, {"*": "PASS"}]])
    env["ops"].metrics = {"summary": {"in_flight": 1}}
    assert _run_inject(env, args) == 2 and not (tmp_path / "probe.log").exists()
    args2 = args[:-1] + ["999999999"]
    env["ops"].metrics = {"summary": {"in_flight": 0}}
    assert _run_inject(env, args2) == 2


def test_inject_final_suite_failure_propagates(env, tmp_path):
    script = [[0, {"*": "PASS"}], [0, {"*": "PASS"}], [0, {"*": "PASS"}], [4, {"*": "PASS"}]]
    args = _inject_env(env, tmp_path, script)
    assert _run_inject(env, args) == 4


# --------------------------------------------------------------------------- drive scripts
def _drive(tmp_path, script, extra_env, args):
    import subprocess
    cfgdir = tmp_path / "xdg" / "mlx_local_stack"
    cfgdir.mkdir(parents=True)
    (cfgdir / "config.sh").write_text(f'export STACK_WORKDIR="{tmp_path / "wd"}"\n')
    stub = tmp_path / "py.sh"
    stub.write_text('#!/bin/bash\necho "ran $@"\nexit ${STUB_RC:-0}\n')
    stub.chmod(0o755)
    env = {**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "xdg"), "C147_PY": str(stub), **extra_env}
    env.pop("STACK_WORKDIR", None)
    return subprocess.run(["bash", str(C147 / script)] + args, env=env, capture_output=True, text=True, timeout=30)


def test_drive_chain_preserves_exit_code_and_writes_rc(tmp_path):
    r = _drive(tmp_path, "drive_chain.sh", {"STUB_RC": "3"}, ["pilot"])
    assert r.returncode == 3
    assert (tmp_path / "wd/c147/chain.rc").read_text().strip() == "3"
    assert "ran" in (tmp_path / "wd/c147/chain.out").read_text() and "run_tg1_chain.py pilot" in (tmp_path / "wd/c147/chain.out").read_text()


def test_drive_inject_preserves_exit_code_and_writes_rc(tmp_path):
    r = _drive(tmp_path, "drive_inject.sh", {"STUB_RC": "4"}, [])
    assert r.returncode == 4 and (tmp_path / "wd/m62/inject/inject.rc").read_text().strip() == "4"


@pytest.mark.parametrize("name", ["drive_chain.sh", "drive_inject.sh", "run_tg1_chain.py", "run_inject.py", "fake_probe.py",
                                  "README.md"])
def test_no_masked_failures_no_home_paths(name):
    text = (C147 / name).read_text()
    assert "|| true" not in text and "pgrep -f" not in text
    for bad in ("/Users/", "/home/"):
        assert bad not in text
    if name.endswith(".sh"):
        import subprocess
        assert subprocess.run(["bash", "-n", str(C147 / name)]).returncode == 0


# --------------------------------------------------------------------------- Q1 foreign listener, real ChainOps
def _real_ops_with_foreign_listener(tmp_path):
    sent, calls = [], []

    def sh(cmd, **kw):
        calls.append(cmd)
        s = " ".join(cmd) if isinstance(cmd, list) else cmd
        if "pmset -g ac" in s:
            return co.Result(" Wattage = 140W\n Voltage = 28000mV\n")
        if "pmset -g batt" in s:
            return co.Result("\t85%; charging\n")
        if "sweep_orphan" in s:
            return co.Result("no orphaned\n")
        if s.startswith("lsof"):
            return co.Result("p4242\n")
        return co.Result("")
    ov = tmp_path / "ov.yaml"
    ov.write_text("mlx_port: 8091\nmodels: []\n")
    lines = []
    ops = co.ChainOps(REPO, tmp_path, ov, co.RunLog(tmp_path / "RL.md", out=lines.append), sh=sh,
                      http=lambda *a, **k: b"{}", popen=lambda *a, **k: pytest.fail("router must not be spawned"),
                      sleep=lambda s: None, create_time=lambda p: 1.0, kill=lambda p, s: sent.append((p, s)))
    return ops, sent, calls, lines


def test_chain_runner_foreign_listener_refused_nothing_torn_down(env, tmp_path):
    ops, sent, calls, lines = _real_ops_with_foreign_listener(tmp_path)
    rc = R.main(PILOT + ["--probe", str(C147 / "fake_probe.py"), "--python", sys.executable, "--out-root",
                         str(env["out"]), "--universe", str(env["uni"])], ops=ops, timers=R.Timers(**TIMERS),
                log_out=lines.append)
    assert rc == 2 and sent == []
    assert not any("stack_stop" in " ".join(c) for c in calls if isinstance(c, list))
    assert any("NOTHING" in ln for ln in lines)


def test_inject_driver_foreign_listener_refused_nothing_torn_down(env, tmp_path):
    ops, sent, calls, lines = _real_ops_with_foreign_listener(tmp_path)
    rc = RI.main(["--universe", str(env["uni"]), "--out-dir", str(tmp_path / "inj")], ops=ops, log_out=lines.append)
    assert rc == 2 and sent == []
    assert not any("stack_stop" in " ".join(c) for c in calls if isinstance(c, list))


# --------------------------------------------------------------------------- Q3 receipt / Q4 pinning
def test_receipt_shape_from_fake_probe_abort_is_top_level(env, tmp_path):
    out = tmp_path / "x.jsonl"
    FP.write_leg(out, PICK1, "python", 1001, ["python/a"], {"pid": 1, "create_time": 1.0, "model_path": "m",
                                                          "registry_sha256": "a" * 64}, tmp_path)
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    cs = R.receipt_from_manifest(man)
    assert set(cs) == {"survivors", "containers_remaining", "uncertain", "orphans_unattributed"}
    assert R.receipt_from_manifest({"transport_abort": {"cleanup_status": cs}}) is None     # one location only


def _chain_for(env):
    a = R.parse_args(PILOT)
    return R.Chain(a, env["ops"], R.Timers(**TIMERS), lambda m: env["lines"].append(m), R.load_universe(str(env["uni"])),
                   env["out"])


def test_check_restart_eligible_against_real_probe_manifest(env):
    fx = REPO / "benchmark/bench/tests/fixtures/c147_cancel_manifest.json"
    if not fx.exists():
        pytest.skip("real probe-produced fixture c147_cancel_manifest.json is not present yet (probe worker saves it)")
    man = json.loads(fx.read_text())
    ch = _chain_for(env)
    ops = env["ops"]
    ops.load(PICK1)
    block = {"worker": {"pid": ops.ident["pid"], "create_time": ops.ident["create_time"]}}
    att = {"cleanup_status": R.receipt_from_manifest(man)}
    assert att["cleanup_status"] is not None
    ch.check_restart_eligible(att, {"model": PICK1}, block)           # clean receipt authorises the restart


def test_pin_from_raises_when_identity_field_missing(env, tmp_path):
    ch = _chain_for(env)
    out = tmp_path / "y.jsonl"
    FP.write_leg(out, PICK1, "python", 1001, ["python/a"], {"pid": 1, "create_time": 1.0, "model_path": "m",
                                                          "registry_sha256": "a" * 64}, tmp_path)
    mp = out.with_suffix(".manifest.json")
    man = json.loads(mp.read_text())
    man["runtime"].pop("opencode_exe_sha256")
    mp.write_text(json.dumps(man))
    from bench import chain_ops as _co
    with pytest.raises(_co.ChainAbort, match="opencode_exe_sha256"):
        ch.pin_from({"out": str(out)})
    FP.write_leg(out, PICK1, "python", 1001, ["python/a"], {"pid": 1, "create_time": 1.0, "model_path": "m",
                                                          "registry_sha256": "a" * 64}, tmp_path)
    ch2 = _chain_for(env)
    ch2.pin_from({"out": str(out)})
    assert ch2.pinned["opencode_exe_sha256"] == "e" * 64 and ch2.pinned["serving_path"] == "sp1"
