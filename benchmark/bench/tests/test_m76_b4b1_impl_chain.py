"""M76 B4b-1 acceptance 1 (implementer tests): the tg2 chain — `run_config` (`tg2-p426`), the schedule builder table (golden) and
its pins (a consistent redraw refuses), the readers (`planned_slots`, `classify_leg`), `run_tg2_chain.py`'s `--leg` /
`--rehearsal` mapping and record kinds, the shared core's P426 gating on `P426_CONFIG_IDS` (frozen schedule, `--evidence p426`,
no overlay under `--predictor mtp`, docker for every language, the corpus grader bound), the A4 / `validate_leg` / docker gates
on the tg2 label, and the R2 / R3 targets on Rust."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import chain_core as core
from bench import chain_ops as co
from bench import p426_freeze as fz
from bench import p426_hooks as ph
from bench import run_config as rc
from bench import schedules
from bench.token_turn_gate import TransportAbort

BENCH = Path(__file__).resolve().parents[1].parent
REPO = BENCH.parent
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
DRAW = json.loads((BENCH / "m65/tg2_draw.json").read_text())
LANGS = ("rust", "javascript", "java", "cpp")
WD = Path("/wd-tg2")


def _T():
    sys.path.insert(0, str(BENCH / "chains" / "c147"))
    import run_tg2_chain as T
    return T


def perm(lang):
    return DRAW["languages"][lang]["permutation"]


# ----------------------------------------------------------------------------------------------- run_config
def test_tg2_p426_is_a_p426_config_with_its_own_builder():
    assert rc.P426_CONFIG_IDS == ("tg1-p426", "tg2-p426")
    arm = rc.ArmBinding(arm="oc", probe="benchmark/run_tg2_probe.py", label="opencode-v2-web-tg2", arm_spec="oc")
    ok = rc.ChainConfig(config_id="tg2-p426", arms=(arm,), schedule=dict(builder="tg2_p426", params=dict(p426=True, models=[ENTRY])),
                        out_root_family="m63", predictor="mtp", arm_switch_ops=(), transport_policy="p426_continue",
                        resume_policy="restart_load", snapshot_complete_required=False)
    assert ok.transport_policy == "p426_continue"
    for bad in (dict(builder="tg1", params=dict(p426=True, models=[ENTRY])),
                dict(builder="tg2_p426", params=dict(p426=True, models=[ENTRY, "b"])),
                dict(builder="tg2_p426", params=dict(models=[ENTRY]))):
        with pytest.raises(ValueError):
            rc.ChainConfig(config_id="tg2-p426", arms=(arm,), schedule=bad, out_root_family="m63", predictor="mtp",
                           arm_switch_ops=(), transport_policy="p426_continue", resume_policy="restart_load",
                           snapshot_complete_required=False)
    with pytest.raises(ValueError):                         # p426_continue stays P426-only
        rc.ChainConfig(config_id="tg2", arms=(arm,), schedule=dict(builder="tg2_p426", params=dict(p426=True, models=[ENTRY])),
                       out_root_family="m63", predictor="mtp", arm_switch_ops=(), transport_policy="p426_continue",
                       resume_policy="restart_load", snapshot_complete_required=False)


# ----------------------------------------------------------------------------------------------- the schedule table (E12)
TABLE = {"pilot": ("pilot", 1001, LANGS, 1), "s1": ("s1", 1001, LANGS, 20), "s2": ("s2", 2002, tuple(reversed(LANGS)), 20),
         "reload": ("reload", 1001, LANGS, 5), "r2": ("s1", 1001, ("rust",), 1), "r3": ("s1", 1001, ("rust",), 1)}


@pytest.mark.parametrize("leg", list(TABLE))
def test_the_schedule_table(leg):
    session, seed, order, n = TABLE[leg]
    s = schedules.tg2_p426(DRAW, leg, ENTRY, "mtp")
    assert s["builder"] == "tg2_p426" and s["p426"] is True and s["picks"] == [ENTRY] and s["predictor"] == "mtp"
    assert s["draw_sha256"] == schedules.TG2_DRAW_SHA256 and s["universe_sha256"] == schedules.TG2_UNIVERSE_SHA256
    (block,) = s["blocks"]
    assert block["session"] == session and block["seed_base"] == seed and block["model"] == ENTRY
    assert [lg["lang"] for lg in block["legs"]] == list(order)
    for lg in block["legs"]:
        items = perm(lg["lang"])[:n]
        assert lg["session"] == session and lg["seed_base"] == seed and lg["stem"] == schedules.flat_stem(ENTRY, session, lg["lang"])
        (inv,) = lg["invocations"]
        assert inv["expect"] == items and inv["names"] == [i.split("/", 1)[1] for i in items] == lg["full_names"]
        assert inv["limit"] is None and lg["draft_kind"] == "mtp"
    assert fz.planned_slots_of(s) == n * len(order)
    schedules.check_tg2_p426(s, DRAW, leg)


def test_the_schedule_golden_hashes_are_stable():
    shas = {leg: schedules.schedule_sha256(schedules.tg2_p426(DRAW, leg, ENTRY, "mtp")) for leg in TABLE}
    assert shas == {leg: schedules.schedule_sha256(schedules.tg2_p426(json.loads(json.dumps(DRAW)), leg, ENTRY, "mtp"))
                    for leg in TABLE}
    assert len(set(shas.values())) == len(TABLE)                # r2 / r3: the same one Rust item, named by their own leg


def test_the_pins_and_a_consistent_redraw_refuses(tmp_path):
    raw = (BENCH / "m65/tg2_draw.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == schedules.TG2_DRAW_SHA256
    assert (BENCH / "m65/tg2_draw.json.sha256").read_text().split()[0] == schedules.TG2_DRAW_SHA256
    assert DRAW["universe_sha256"] == schedules.TG2_UNIVERSE_SHA256
    redraw = json.loads(json.dumps(DRAW))
    redraw["languages"]["rust"]["permutation"].reverse()
    for tier in ("screen", "decider"):
        redraw["languages"]["rust"][tier] = redraw["languages"]["rust"]["permutation"][:len(redraw["languages"]["rust"][tier])]
    with pytest.raises((TransportAbort, ValueError), match="pin|frozen|sha"):
        schedules.tg2_p426(redraw, "s1", ENTRY, "mtp")
    s = schedules.tg2_p426(DRAW, "s1", ENTRY, "mtp")
    with pytest.raises((TransportAbort, ValueError)):
        schedules.check_tg2_p426(s, redraw, "s1")
    tampered = json.loads(json.dumps(s))
    tampered["blocks"][0]["legs"][1]["invocations"][0]["names"].reverse()
    with pytest.raises((TransportAbort, ValueError)):
        schedules.check_tg2_p426(tampered, DRAW, "s1")


def test_the_legs_reader_sees_the_tg2_schedule():
    s = schedules.tg2_p426(DRAW, "s2", ENTRY, "mtp")
    legs = schedules.legs(s)
    assert [lg["lang"] for lg in legs] == list(reversed(LANGS)) and all(len(lg["items"]) == 20 for lg in legs)


# ----------------------------------------------------------------------------------------------- run_tg2_chain argv (E2)
def _argv(*head, arm="x", out=None, extra=()):
    leg = head[1] if head[0] == "--leg" else f"rehearsal-{head[1]}"
    out = out or f"{WD}/m76/p426/wave2.tg2/tg2-m76-{arm}-{leg}.a1"
    return [*head, "--p426", "--models", ENTRY, "--predictor", "mtp", "--out-root", str(out), "--campaign-core", "c",
            "--frozen-prompt-date", "Fri Nov 13 2026", "--probe-code-sha", "a" * 64, "--policy-sha", "b" * 64,
            "--frozen-record", f"{WD}/r.json", "--lever", "kv", "--kv-arm", arm, *extra]


@pytest.mark.parametrize("leg,mode,sessions,kind", [("pilot", "pilot", [], fz.KIND_V8), ("s1", "chain", ["s1"], fz.KIND_AMENDMENT),
                                                    ("s2", "chain", ["s2"], fz.KIND_AMENDMENT),
                                                    ("reload", "chain", ["reload"], fz.KIND_AMENDMENT)])
def test_the_leg_mapping(leg, mode, sessions, kind):
    T = _T()
    a = T.parse_args(_argv("--leg", leg))
    assert (a.mode, a.sessions, a.rehearsal, a.inject, a.tg2_leg) == (mode, sessions, False, None, leg)
    assert T.record_kind(a) == kind
    assert a.probe == str(REPO / "benchmark/run_tg2_probe.py") and a.tg2_draw == str(BENCH / "m65/tg2_draw.json")


@pytest.mark.parametrize("which,inject,arm", [("r2", "reconcile-mismatch", "x"), ("r3", "stall-kill", "n16")])
def test_the_rehearsal_mapping(which, inject, arm):
    T = _T()
    a = T.parse_args(_argv("--rehearsal", which, arm=arm))
    assert (a.mode, a.sessions, a.rehearsal, a.inject, a.tg2_leg) == ("chain", ["s1"], True, inject, which)
    assert T.record_kind(a) == fz.KIND_REHEARSAL


def test_the_argv_refusals():
    T = _T()
    base = _argv("--leg", "s1")
    for bad in ([*base, "--rehearsal", "r2"], [x for x in base if x not in ("--leg", "s1")],
                [x for x in base if x not in ("--lever", "kv", "--kv-arm", "x")], ["--leg", "s3", *base[2:]],
                [x if x != "mtp" else "off" for x in base], [*base, "--smoke"]):
        with pytest.raises(SystemExit):
            T.parse_args(bad)
    assert T.LANGS == LANGS
    assert T.CORE_SPECS["probe_entry"] == "benchmark/run_tg2_probe.py"
    assert T.CORE_SPECS["chain_entry"] == "benchmark/chains/c147/run_tg2_chain.py"
    assert T.CORE_SPECS["probe_data"][-1] == "benchmark/opencode_bench_v2_web_tg2.json"


def test_the_out_root_must_be_the_legs_name(tmp_path):
    T = _T()
    a = T.parse_args(_argv("--leg", "s1", out=tmp_path / "m76" / "p426" / "wave2.tg2" / "tg2-m76-x-s2.a1"))
    with pytest.raises(T.Refused, match="tg2-m76-x-s1"):
        T.check_out_root(a, a.out_root and Path(a.out_root))
    a = T.parse_args(_argv("--rehearsal", "r3", arm="n16", out=tmp_path / "tg2-m76-n16-rehearsal-r3.a2"))
    T.check_out_root(a, Path(a.out_root))


def test_the_chain_config_and_the_plan():
    T = _T()
    a = T.parse_args(_argv("--leg", "s2"))
    cfg = T.tg2_config(a)
    assert cfg.config_id == "tg2-p426" and cfg.transport_policy == "p426_continue"
    assert cfg.schedule["builder"] == "tg2_p426" and cfg.schedule["params"]["tg2_leg"] == "s2"
    assert cfg.arms[0].label == "opencode-v2-web-tg2" and cfg.arms[0].probe == "benchmark/run_tg2_probe.py"
    assert cfg.arms[0].probe_data == T.CORE_SPECS["probe_data"]
    chain = _bare_chain(a, cfg)
    sched = chain.build_schedule()
    assert sched == schedules.tg2_p426(DRAW, "s2", ENTRY, "mtp")
    chain.schedule = sched
    loads = chain.plan()
    (load,) = loads
    assert [leg["lang"] for leg in load["legs"]] == list(reversed(LANGS))
    slots = [s for leg in load["legs"] for s in chain.leg_slots(leg)]
    assert len(slots) == 80 and slots[0] == f"tg2-p426|oc|{ENTRY}|s2|cpp|{perm('cpp')[0].split('/')[1]}"
    for leg in load["legs"]:
        chain.verify_schedule(leg)
    leg = dict(load["legs"][0], items=load["legs"][0]["items"][::-1])
    with pytest.raises(co.ChainAbort):
        chain.verify_schedule(leg)


def _bare_chain(a, cfg):
    chain = core.Chain.__new__(core.Chain)
    chain.a, chain.config = a, cfg
    chain.builder = cfg.schedule["builder"]
    chain.per_arm = False
    chain.bindings = {b.arm: b for b in cfg.arms}
    chain.arm_ids = [b.arm for b in cfg.arms]
    return chain


def test_the_core_gates_on_the_p426_config_ids():
    T = _T()
    a = T.parse_args(_argv("--leg", "s1"))
    chain = _bare_chain(a, T.tg2_config(a))
    assert chain.freezes_schedule and chain.p426
    assert chain.p426_evidence() == "p426"


def test_the_corpus_grader_bound_reaches_t_coop():
    from bench import corpus_tg2
    timeouts = corpus_tg2.Tg2Corpus().grader_timeouts()
    assert co.t_coop(0, "python") == 5 + 660 + 300 + 120 + 300 + 80                    # tg1's table unchanged
    worst = max(timeouts.values())
    assert co.t_coop(0, "rust", grader_timeout_s=timeouts) == 5 + (2 * worst + 60) + 300 + 120 + timeouts["rust"] + 80


class _StartOps:
    """The box at a tg2 leg's start: the committed registry is served (no overlay may be generated), power is fine, the docker
    gate answers what the test says and records the images it was asked for."""

    def __init__(self, wd, docker=False):
        self.wd, self.calls, self.docker, self.overlay = str(wd), [], docker, str(REPO / "main_models.yaml")

    def ensure_overlay(self):
        raise AssertionError("an overlay was generated for a tg2 leg (the committed registry is served verbatim)")

    def overlay_sha(self):
        return "a" * 64

    def power_ok(self):
        self.calls.append("power_ok")
        return True

    def docker_ok(self, images=None):
        self.calls.append(("docker_ok", tuple(images or ())))
        return self.docker

    def stop_stack(self):
        self.calls.append("stop_stack")
        return None


def test_a_tg2_leg_starts_on_the_committed_registry_and_gates_docker_on_the_tg2_images(tmp_path):
    from bench import tg2_grade as tg
    T = _T()
    out = tmp_path / "m76/p426/wave2.tg2/tg2-m76-x-s1.a1"
    out.mkdir(parents=True)
    rec = tmp_path / "run"
    v8 = ph.write_exclusive(rec / "v8_base.json", dict(kind=fz.KIND_V8, lever="kv", arms=["n16", "x"], corpus="tg2",
                                                       settle_bound_s=1000.0))
    ph.write_exclusive(rec / "amendment.json", dict(kind=fz.KIND_AMENDMENT, v8_base_sha256=v8["sha256"], corpus="tg2",
                                                    settle_bound_s=1200.0))
    a = T.parse_args([x if x != f"{WD}/r.json" else str(rec / "amendment.json") for x in _argv("--leg", "s1", out=out)])
    ops = _StartOps(tmp_path)
    logs = []
    chain = T.Chain(a, ops, core.Timers(), logs.append, T.load_names(), out, lifecycle={"runner": "benchmark/chains/c147/run_tg2_chain.py"},
                    campaign=object())
    for name in ("init_lifecycle", "recover_txns", "adopt_receipts", "derive_policy", "write_json"):
        setattr(chain, name, lambda *x, **k: None)
    chain.verify_contract = lambda where: None
    chain.stop_requested = lambda: False
    chain.p426_close_log_bounds = lambda: None                   # no router was started: nothing to bound
    rc = chain.run()
    assert rc != 0 and any("docker gate FAIL" in str(m) for m in logs)
    assert ops.calls[0] == "power_ok" and ops.calls[1] == ("docker_ok", ("aider-benchmark", tg.IMAGE_TAG))
    assert json.loads((out / "schedule.json").read_text()) == schedules.tg2_p426(DRAW, "s1", ENTRY, "mtp")
    assert chain.pinned["registry_sha256"] == "a" * 64
    assert chain.inject_langs == dict(r2="rust", r3="rust") and chain.grader_timeout_s["rust"] >= 2 * 180 + 300


# ----------------------------------------------------------------------------------------------- gates on the tg2 label
class _Sh:
    def __init__(self):
        self.cmds = []

    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        return SimpleNamespace(returncode=0, stdout="27.0" if "info" in cmd else "sha256:" + "1" * 64, stderr="")


def test_the_docker_gate_checks_the_tg2_image(tmp_path):
    from bench import tg2_grade as tg
    ops = co.ChainOps(REPO, tmp_path, tmp_path / "reg.yaml", lambda m: None, sh=_Sh())
    assert ops.docker_ok(images=(co.GRADER_IMAGE, tg.IMAGE_TAG))
    inspected = [c[3] for c in ops.sh.cmds if c[:3] == ["docker", "image", "inspect"]]
    assert inspected == [co.GRADER_IMAGE, tg.IMAGE_TAG]
    ops2 = co.ChainOps(REPO, tmp_path, tmp_path / "reg.yaml", lambda m: None, sh=_Sh())
    assert ops2.docker_ok()
    assert [c[3] for c in ops2.sh.cmds if c[:3] == ["docker", "image", "inspect"]] == [co.GRADER_IMAGE]


def test_the_a4_gate_runs_the_tg2_scaffold(tmp_path):
    sh = _Sh()
    ops = co.ChainOps(REPO, tmp_path, tmp_path / "reg.yaml", lambda m: None, sh=sh)
    ops.receipt = tmp_path / "a4.json"
    ops.a4_log_dir = tmp_path / "a4"
    ops.receipt.write_text(json.dumps(dict(**{"pass": True}, run_id="r")))
    ops.a4_gate(ENTRY, "t", scaffold="opencode-v2-web-tg2")
    (cmd,) = [c for c in sh.cmds if any("session_pinning_gate" in str(x) for x in c)]
    assert cmd[cmd.index("--scaffold") + 1] == "opencode-v2-web-tg2"
    sys.path.insert(0, str(REPO / "scripts"))
    import session_pinning_gate as gate
    assert gate.carrier_path("opencode-v2-web-tg2") == REPO / "benchmark/opencode_bench_v2_web_tg2.json"
    assert gate.carrier_path("opencode-v2-web-tg1") == REPO / "benchmark/opencode_bench_v2_web_tg1.json"


def test_validate_leg_takes_the_scaffold_of_the_leg(tmp_path):
    out = tmp_path / "rows.jsonl"
    out.write_text("")
    out.with_suffix(".manifest.json").write_text(json.dumps(dict(model=ENTRY, runtime=dict(scaffold="opencode-v2-web-tg2"))))
    leg = dict(session="s1", model=ENTRY, lang="rust", seed_base=1001, expected_ids=[], out=str(out), rc=0, draft_kind="mtp")
    tg2 = co.validate_leg(leg, {}, str(tmp_path), policy_sha="p" * 64, scaffold="opencode-v2-web-tg2")
    tg1 = co.validate_leg(leg, {}, str(tmp_path), policy_sha="p" * 64)
    assert not any(w.startswith("runtime_scaffold:") for w in tg2)
    assert any(w.startswith("runtime_scaffold:") for w in tg1)


def test_validate_reports_accepts_the_tg2_languages():
    from bench import structured_grade as sg
    art = lambda *names: {n: dict(path=f"seq-0001/{n}", sha256="0" * 64) for n in names}       # noqa: E731
    parsed = {"rust": art("execute.stdout", "phases.json"), "java": art("junit-000.xml", "phases.json"),
              "javascript": art("report.json", "phases.json"), "cpp": art("report.xml", "phases.json")}
    def v(reports, lang, modified, **kw):
        return sg.validate_reports(reports, lang, modified, grader="tg2", **kw)
    for lang, a in parsed.items():
        assert v([dict(boundary=1, seq=1, final=True, outcome="parsed", artifacts=a)], lang, False) == []
        assert v([dict(boundary=1, seq=1, final=True, outcome="parsed", artifacts={"phases.json": a["phases.json"]})], lang, False)
        report = {k: x for k, x in a.items() if k != "phases.json"}
        assert v([dict(boundary=1, seq=1, final=True, outcome="parsed", artifacts=report)], lang, False)
    for outcome in ("compile_failure", "timeout", "oom", "mem_kill", "crash", "storage_cap", "output_cap"):
        assert v([dict(boundary=1, seq=1, final=True, outcome=outcome, artifacts=art("phases.json"))], "rust", False) == []
    assert v([dict(boundary=1, seq=1, final=True, outcome="tampered", artifacts={})], "cpp", True) == []
    assert v([dict(boundary=1, seq=1, final=True, outcome="infrastructure", artifacts=art("phases.json"))], "java", False)
    assert v([dict(boundary=1, seq=1, final=True, outcome="parsed", artifacts=art("report.xml", "phases.json"))], "python", False)
    # without the tg2 grader the receipts keep today's rules (a fake corpus named rust / java / ... is unaffected)
    assert sg.validate_reports([dict(boundary=1, seq=1, final=True, outcome="parsed", artifacts=art("go.jsonl"))], "rust", False) == []
    assert sg.validate_reports([dict(boundary=1, seq=1, final=True, outcome="compile_failure", artifacts=art("x"))],
                               "python", False)                       # tg1's outcome set unchanged


# ----------------------------------------------------------------------------------------------- R2 / R3 on Rust
def test_r2_invalidates_the_first_rust_item():
    from bench import chain_hooks as ch
    h = ph.P426Hooks(ops=None, out_root=Path("/x"), arm="ON", settle_bound_s=900, inject="reconcile-mismatch", inject_lang="rust")
    assert h.inject_lang == "rust"
    assert ph.is_lang(f"tg2-p426|oc|{ENTRY}|s1|rust|say", {"id": "rust/say"}, "rust")
    assert not ph.is_lang(f"tg1-p426|oc|{ENTRY}|s1|go|x", {"id": "go/x"}, "rust")
    assert ph.P426Hooks(ops=None, out_root=Path("/x"), arm="ON", settle_bound_s=900).inject_lang == "go"
    assert ch is not None


def test_r3_kills_the_first_rust_item():
    T = _T()
    a = T.parse_args(_argv("--rehearsal", "r3", arm="n16"))
    chain = _bare_chain(a, T.tg2_config(a))
    chain.inject_langs = T.INJECT_LANGS
    chain.schedule = schedules.tg2_p426(DRAW, "r3", ENTRY, "mtp")
    leg = chain.schedule["blocks"][0]["legs"][0]
    got = chain.p426_inject_stall(leg, dict(names=list(leg["full_names"])))
    assert got == (perm("rust")[0], core.INJECT_STALL_S)
    assert T.INJECT_LANGS == dict(r2="rust", r3="rust")
