"""M76 B4b-1 (acceptance 1, "tg1 unchanged"): the tg1 surface is pinned to the BASELINE's output — schedules, probe argv, the P426 config,
the plan of a frozen tg1 schedule, the harvest classifier, the report validator, `t_coop`, the tg1 corpus prompt / identity — and the
regenerated B8 / SIGNALS equal the committed P426 ones. The tg1 probe identity equals the baseline's EXCEPT the closure-derived fields
(`probe_code_sha256`, `generation_identity_sha256`, `arm_identity_sha256`, the campaign-core shas), which must CHANGE (C178: a shared-core
edit rotates the closure identities).

The golden `fixtures/m76_b4b1_fe/golden_tg1_surface.json` / `golden_tg1_identity.json` were written by running `surface()` / the probe's
`--print-identity` on the BASELINE (`M76_B4B1_RECORD=1`). Class of each test: (b) preserves an invariant, (a) reproduces a failure
the spec fixes (closure rotation), (c) new behaviour."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench.tests import test_m76_b4b1_fe_support as S

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
P426 = S.BENCH / "results" / "p426"
EVIDENCE_REF = "b6ec7819"
CLOSURE_FIELDS = ("probe_code_sha256", "generation_identity_sha256", "arm_identity_sha256")


def _canon(o):
    return json.loads(json.dumps(o, sort_keys=True, default=str))


def _tg1_args(*extra):
    return S.tg1_chain_entry().parse_args(["chain", "s1", "--p426", "--lever", "kv", "--kv-arm", "n16", "--models", MODEL,
                                           "--predictor", "mtp", "--out-root", "tg1-m76-n16-s1.a1", "--probe-code-sha", "a" * 64,
                                           "--policy-sha", "b" * 64, "--frozen-prompt-date", "Sat Oct 17 2026",
                                           "--campaign-core", "tag", "--frozen-record", "r.json", *extra])


def surface(tmp_path):
    from bench import chain_core as core, chain_ops as co, p426_harvest as H, schedules
    from bench import structured_grade as sg
    R1 = S.tg1_chain_entry()
    names = R1.load_universe()
    out = {}
    shapes = dict(pilot=("pilot", [], {}), s1=("chain", ["s1"], {}), s2=("chain", ["s2"], {}), reload=("chain", ["reload"], {}),
                  s3=("chain", ["s3"], dict(s3=True)), rehearsal=("chain", ["s1"], dict(rehearsal=True)))
    sched_of, sch = {}, {}
    for key, (mode, sessions, kw) in shapes.items():
        sched = schedules.tg1(mode, sessions, names, picks=(MODEL,), predictor="mtp", p426=True, **kw)
        sched_of[key] = sched
        sch[key] = dict(sha256=schedules.schedule_sha256(sched), blocks=[(b["session"], b["model"], b["seed_base"], b["pilot_only"]) for b in sched["blocks"]],
                        legs=[(l["session"], l["lang"], l["seed_base"], len(l["items"]), l["items"][:3], [i["phase"] for i in l["invocations"]])
                              for l in schedules.legs(sched)])
    out["schedules"] = sch
    out["schedule_legs_sha"] = {k: schedules.schedule_sha256(dict(legs=schedules.legs(v))) for k, v in sched_of.items()}
    leg = dict(sched_of["s1"]["blocks"][0]["legs"][0], out="/o/leg")
    step = dict(names=leg["invocations"][0]["names"], limit=leg["invocations"][0]["limit"])
    step_p = dict(names=["a"], limit=1)
    out["argv"] = dict(
        plain=core.build_cmd("py", "probe.py", leg, step, "rcpt", "cancel", "ack", scaffold="opencode-v2-web-tg1"),
        full=core.build_cmd("py", "probe.py", leg, step_p, "rcpt", "cancel", "ack", scaffold="opencode-v2-web-tg1", universe="u.json",
                            frozen="Sat Oct 17 2026", out="/o/x", attempt=2, rerun_index=1, epoch="e1", nonce="n" * 64, evidence="p426",
                            inject_stall=("python/a", 30)),
        entry=R1.build_cmd("py", "probe.py", leg, step_p, "rcpt", "cancel", "ack", universe="u.json", frozen="Sat Oct 17 2026",
                           evidence="p426"))
    cfg = R1.tg1_config(_tg1_args())
    d = cfg.as_dict()
    out["config"] = {k: d[k] for k in ("config_id", "schedule", "out_root_family", "predictor", "transport_policy", "resume_policy",
                                       "snapshot_complete_required", "arm_switch_ops")}
    out["config"]["arms"] = [dict(arm=b["arm"]) for b in d["arms"]]
    a = _tg1_args()
    a.frozen_record = None                       # no record on disk here: the hooks fall back to the 900 s settle floor
    chain = core.Chain(cfg, a, SimpleNamespace(wd=tmp_path), None, lambda *_: None, repo=tmp_path, out_root=tmp_path / "o", names={},
                       lifecycle_files={})
    plans = {}
    for key in ("pilot", "s1", "s2", "reload", "s3"):
        chain.schedule = sched_of[key]
        plans[key] = _canon(chain.plan())
    out["plan"] = plans
    battery = [
        ("leg", "leg.json"), ("leg", "chain.json"), ("leg", "schedule.json"), ("leg", "receipt.json"), ("leg", "RUNLOG.md"),
        ("leg", "STOP"), ("leg", "x.log"), ("leg", "x.png"), ("leg", "items/a.json"), ("leg", "items/a/b.json"), ("leg", "a4/x.json"),
        ("leg", "a4/x.stdout"), ("leg", "a4/x.bin"), ("leg", "s1/x.jsonl"), ("leg", "s1/x.manifest.json"), ("leg", "s1/x.stderr"),
        ("leg", "s1/x.bin"), ("leg", "s1/x.item1.ready"), ("leg", "s1/x.ACK"), ("leg", "s1/p426_dnf/x.json"), ("leg", "tmp/mlx-manager-logs/m.log"),
        ("leg", "tmp/uv-0f.lock"), ("leg", "tmp/other"), ("leg", "quarantine/x.bin"), ("leg", "x.final_tree/manifest.json"),
        ("leg", "x.final_tree/objects/" + "a" * 64), ("leg", "x.final_tree/other"),
        ("run", "home/x"), ("run", "grading-private/x.json"), ("run", "grading-private/x.log"), ("run", "grading-private/x.out"),
        ("run", "grading-private/x.bin"), ("run", "grading-private/.tg2-list/ls-ps.out"), ("run", "cfg/opencode/opencode.json"),
        ("run", "cfg/opencode/plugins/a.js"), ("run", "cfg/other"), ("run", "positives.json"),
        ("evidence", "x.json"), ("evidence", "x.xml"), ("evidence", "x.out"), ("evidence", "d/x.txt"), ("evidence", "go__a.grades/seq-0001/go.stderr"),
        ("evidence", "go__a.grades/go.stderr"), ("evidence", "go__a.grades/seq-0001/go.jsonl"), ("evidence", "x.final_tree/objects/" + "b" * 64),
    ]
    out["classify"] = {f"{k}:{r}": H.classify(k, r) for k, r in battery}
    art = dict(path="x", sha256="a" * 64)
    py = [dict(boundary=0, seq=1, final=True, outcome="parsed", artifacts={"stdout.txt": art, "stderr.txt": art, "report.xml": art})]
    go = [dict(boundary=0, seq=1, final=True, outcome="parsed", artifacts={"go.jsonl": art, "go.stderr": art})]
    out["validate_reports"] = {
        "py_ok": sg.validate_reports(py, "python", False), "go_ok": sg.validate_reports(go, "go", False),
        "py_as_go": sg.validate_reports(py, "go", False), "py_compile": sg.validate_reports([dict(py[0], outcome="compile_failure")], "python", False),
        "tampered": sg.validate_reports([dict(py[0], outcome="tampered", artifacts={})], "python", True),
        "empty": sg.validate_reports([], "python", False), "rust": sg.validate_reports(py, "rust", False)}
    out["t_coop"] = {f"{lang}:{t}": co.t_coop(t, lang) for lang in ("python", "go", "other") for t in (0, 90_000, 250_000)}
    out["grader_timeouts"] = dict(co.GRADER_TIMEOUT_S)
    out["sg_timeouts"] = dict(sg.TIMEOUTS)
    return _canon(out)


@pytest.fixture(scope="module")
def surf(tmp_path_factory):
    got = surface(tmp_path_factory.mktemp("tg1surface"))
    if S.RECORD:
        S.golden("golden_tg1_surface", got)
    return got


def _want():
    path = S.FIX / "golden_tg1_surface.json"
    if not path.is_file():
        pytest.fail("golden_tg1_surface.json is missing (record it on the baseline with M76_B4B1_RECORD=1)", pytrace=False)
    return json.loads(path.read_text())


# (b) tg1's plan, argv, schedules, harvest classes, report validator and `t_coop` are the baseline's, key by key
@pytest.mark.parametrize("key", ["schedules", "schedule_legs_sha", "argv", "config", "plan", "classify", "validate_reports", "t_coop",
                                 "grader_timeouts", "sg_timeouts"])
def test_tg1_surface_is_the_baseline(key, surf):
    want = _want()
    assert key in want
    assert surf[key] == want[key]


# (b) the tg1 corpus prompt, tamper / grade wiring and identity are the baseline's
def test_tg1_corpus_prompt_and_identity_unchanged(tmp_path):
    from bench import corpus_tg1
    R1 = S.tg1_chain_entry()
    root = S.polyglot()
    corpus = corpus_tg1.Tg1Corpus(S.BENCH / "m62" / "universe.json", polyglot_root=root, polyglot_sha=lambda r: "0" * 40)
    corpus.load_universe()
    item = corpus.items("python")[0]
    prepared = corpus.prepare(item, tmp_path / "w")
    surface = _canon(dict(item=item, prompt=corpus.prompt(prepared), stall=corpus.prompt(prepared, inject="stall"),
                          identity=corpus.identity(), needs_docker={l: corpus.needs_docker(l) for l in ("python", "go")}))
    got, want = S.golden("golden_tg1_corpus", surface)
    assert got == want


# (b) the regenerated B8 and SIGNALS equal the committed P426 ones, byte for byte (the P426 evidence commit must be present)
def _cli(module, args, tmp_path):
    env = {"PYTHONPATH": str(S.BENCH), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(tmp_path),
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "MLX_BENCH_RESULTS": str(S.BENCH / "results")}
    return subprocess.run([sys.executable, "-m", module, *map(str, args)], cwd=S.BENCH, capture_output=True, text=True, timeout=1800,
                          env=env)


def _need_evidence():
    probe = subprocess.run(["git", "-C", str(S.REPO), "cat-file", "-e", f"{EVIDENCE_REF}^{{commit}}"], capture_output=True)
    if probe.returncode:
        pytest.skip(f"evidence commit {EVIDENCE_REF} is not in this checkout")


def test_signals_regenerate_byte_identical(tmp_path):
    _need_evidence()
    args = ["all", "--results-root", P426, "--rows-root", S.BENCH / "results", "--b8", P426 / "B8.json", "--out-md", tmp_path / "SIGNALS.md",
            "--out-json", tmp_path / "SIGNALS.json", "--panel", P426 / "panel", "--evidence-ref", EVIDENCE_REF]
    proc = _cli("bench.p426_signals", args, tmp_path)
    assert proc.returncode == 0, proc.stderr[-1200:]
    for name in ("SIGNALS.md", "SIGNALS.json"):
        assert (tmp_path / name).read_bytes() == (P426 / name).read_bytes(), name


def test_b8_regenerates_byte_identical(tmp_path):
    _need_evidence()
    out = tmp_path / "B8.json"
    proc = _cli("bench.p426_verify", ["all", "--results-root", P426, "--rows-root", S.BENCH / "results", "--repo", S.REPO, "--out", out],
                tmp_path)
    assert proc.returncode == 0, proc.stderr[-1200:]
    assert out.read_bytes() == (P426 / "B8.json").read_bytes()


# ------------------------------------------------------------------------------------------------ closure identities
def _identity(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(S.BENCH), STACK_WORKDIR=os.environ.get("STACK_WORKDIR", str(tmp_path)))
    proc = subprocess.run([sys.executable, str(S.BENCH / "run_tg1_probe.py"), "--print-identity"], cwd=S.REPO, capture_output=True,
                          text=True, timeout=300, env=env)
    assert proc.returncode == 0, (proc.stderr or proc.stdout)[-800:]
    return json.loads(proc.stdout)


def _paths(doc, prefix=()):
    if isinstance(doc, dict):
        for k, v in doc.items():
            yield from _paths(v, prefix + (k,))
    else:
        yield prefix, doc


def _scrub(doc):
    return json.loads(json.dumps(doc).replace(str(S.REPO), "<REPO>"))


# (b) the tg1 probe identity equals the baseline's in every field that is not closure-derived
# (a) and the closure-derived ones change: the shared core (arm_runner / chain_core / ... , C178) is edited, so tg1's closure rotates
INVARIANT_FIELDS = ("arm", "config_id", "scaffold", "scaffold_policy_sha256", "polyglot_sha")     # not closure-derived, not box-bound
BASELINE_CLOSURE = {"probe_code_sha256": "28ce3add173f6540fe37f17864b9caf730f7566338920de7aeb583c2ab25ec21"}      # recorded on the baseline


def test_tg1_identity_unchanged_except_the_closure_fields(tmp_path):
    S.polyglot()
    got = _scrub(_identity(tmp_path))
    if S.RECORD:
        S.golden("golden_tg1_identity", got)
    want = json.loads((S.FIX / "golden_tg1_identity.json").read_text())
    box = {"opencode_exe_sha256"}            # designer amendment (merge): present iff the box resolves an opencode binary
    assert set(got) - box == set(want) - box, sorted((set(got) ^ set(want)) - box)
    assert {k: got[k] for k in INVARIANT_FIELDS} == {k: want[k] for k in INVARIANT_FIELDS}
    assert want["probe_code_sha256"] == BASELINE_CLOSURE["probe_code_sha256"]


# (a) C178: the shared-core edit rotates tg1's probe closure (`probe_code_sha256`); `generation_identity_sha256` / `arm_identity_sha256` /
# the campaign-core shas are derived from a live worker / a campaign tag and are checked by the leg tests, not by `--print-identity`
def test_tg1_probe_closure_identity_rotates(tmp_path):
    S.polyglot()
    got = _scrub(_identity(tmp_path))
    assert got["probe_code_sha256"] != BASELINE_CLOSURE["probe_code_sha256"], "tg1's probe closure did not change"
