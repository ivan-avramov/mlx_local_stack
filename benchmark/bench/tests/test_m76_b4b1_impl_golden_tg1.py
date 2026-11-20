"""M76 B4b-1 acceptance 1 (last clause): tg1 unchanged — golden of tg1's plan, argv, schedules, harvest rules, B8 and signals
outputs, and a tg1 row through the real tg1 entry (fake client), equal except the closure-derived identity fields, which are
asserted to change (a shared-core edit rotates the tg1 closure, C178).

The facts were recorded on the unchanged baseline into `fixtures/m76_b4b1_impl/tg1_golden.json` (`M76_B4B1_REGEN=1`)."""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

import pytest

from bench import chain_core as core
from bench import p426_freeze as fz
from bench import p426_harvest as H
from bench import p426_hooks as ph
from bench import p426_receipt as pr
from bench import p426_wave2 as W2
from bench import schedules

BENCH = Path(__file__).resolve().parents[1].parent
REPO = BENCH.parent
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "m76_b4b1_impl" / "tg1_golden.json"
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
WD = Path("/wd-golden")
CLOSURE_ROW = ("generation_identity_sha256",)
CLOSURE_RUNTIME = ("probe_code_sha256", "generation_identity_sha256")


def _chain():
    sys.path.insert(0, str(BENCH / "chains" / "c147"))
    import run_tg1_chain as C
    return C


def _norm(x, tmp=None):
    if isinstance(x, dict):
        return {str(k): _norm(v, tmp) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_norm(v, tmp) for v in x]
    if isinstance(x, Path):
        x = str(x)
    if isinstance(x, str):
        x = x.replace(str(REPO), "<REPO>").replace(str(WD), "<WD>")
        if tmp is not None:
            x = x.replace(str(Path(tmp).resolve()), "<TMP>").replace(str(tmp), "<TMP>")
        return x
    return x


def _base(session, extra=()):
    head = ["pilot"] if session == "pilot" else ["chain", session]
    return head + ["--p426", "--models", ENTRY, "--predictor", "mtp", "--out-root", f"{WD}/m76/p426/wave2/leg.a1",
                   "--campaign-core", "c", "--frozen-prompt-date", "Fri Nov 13 2026", "--probe-code-sha", "a" * 64,
                   "--policy-sha", "b" * 64, "--frozen-record", f"{WD}/r.json", *extra]


def chain_facts():
    C = _chain()
    names = C.load_universe()
    out = {}
    for session in ("pilot", "s1", "s2", "reload", "s3"):
        for extra in ((), ("--lever", "kv", "--kv-arm", "x"), ("--lever", "kv", "--kv-arm", "n16")):
            if session == "s3" and not extra:
                continue
            a = C.parse_args(_base(session, extra))
            config = C.tg1_config(a)
            chain = C.Chain.__new__(C.Chain)
            chain.a, chain.config, chain.names = a, config, names
            chain.builder = config.schedule["builder"]
            sched = chain.tg1_schedule()
            chain.schedule = sched
            loads = chain.plan()
            leg = loads[0]["legs"][0]
            inv = leg["invocations"][0]
            view = dict(leg, out=f"{WD}/out.jsonl")
            cmd = core.build_cmd("py", "probe.py", view, dict(inv, names=list(inv["names"])), "a4.json", "cancel", "ack",
                                 scaffold=leg["label"], frozen="Fri Nov 13 2026", attempt=1, nonce="n" * 64,
                                 evidence="p426")
            out[f"{session}{extra}"] = dict(args={k: v for k, v in sorted(vars(a).items())},
                                            config=dataclasses.asdict(config), schedule=sched,
                                            schedule_sha=schedules.schedule_sha256(sched), plan=loads, cmd=cmd,
                                            freezes=chain.freezes_schedule, p426=config.transport_policy)
    return out


def _records(tmp_path, lever):
    run = tmp_path / f"run-{lever}"
    run.mkdir()
    if lever == "kv":
        base = dict(kind=fz.KIND_V8, lever="kv", arms=["n16", "x"], build="s3", n16_commit="1" * 40, x_commit="2" * 40,
                    pilot_deadline_s=5000)
    else:
        base = dict(kind=fz.KIND_V8, off_commit="1" * 40, on_commit="2" * 40, pilot_deadline_s=4000)
    base.update(probe_code_sha256="a" * 64, scaffold_policy_sha256="b" * 64, frozen_prompt_date="Fri Nov 13 2026")
    v8 = ph.write_exclusive(run / "v8_base.json", base)
    amend = ph.write_exclusive(run / "amendment.json", dict(
        kind=fz.KIND_AMENDMENT, v8_base_sha256=v8["sha256"], w_python_s=300, w_go_s=400,
        leg_deadline_s=dict(s1=1, s2=2, s3=3, reload=4)))
    return run, v8, amend


def wave2_facts(tmp_path):
    out = {}
    for lever in ("mtp", "kv"):
        run, v8, amend = _records(tmp_path, lever)
        if lever == "kv":
            table = W2.kv_legs("n16", "x")
            wts = {"n16": WD / "wt-n16", "x": WD / "wt-x"}
        else:
            table = dict(run=W2.RUN_LEGS, makeup=W2.MAKEUP_LEGS, rehearsal=W2.REHEARSAL_LEGS)
            wts = {"off": WD / "wt-off", "on": WD / "wt-on"}
        argv = {}
        for spec in table["run"] + table["makeup"]:
            rec = run / ("v8_base.json" if spec["record"] == "v8" else "amendment.json")
            kw = dict(occurrences=WD / "occ.jsonl") if spec["kind"] == "makeup" else {}
            a = W2.leg_argv(spec, 1, worktrees=wts, record_path=rec, out_base=WD / "out", lever=lever,
                            pair_receipt=WD / "r.json" if spec["role"] == "second" else None, **kw)
            argv[spec["name"]] = [x.replace(str(run), "<RUN>") for x in a]
        deadlines = {s["name"]: W2.leg_deadline(amend, v8, s, {"python": 2, "go": 1} if s["kind"] == "makeup" else None)
                     for s in table["run"] + table["makeup"] + table["rehearsal"]}
        out[lever] = dict(table=table, argv=argv, deadlines=deadlines,
                          out_root={s["name"]: str(W2.out_root_of(s, 2, WD / "out")) for s in table["run"]})
    out["freeze"] = dict(item_count=fz.ITEM_COUNT, pilot=fz.kv_pilot_leg("x"), rehearsal=fz.kv_rehearsal_legs("n16", "x"),
                         r1=fz.REHEARSAL_R1_ITEMS, deadline=fz.deadline_formula({"python": 22, "go": 21},
                                                                                {"python": 300, "go": 400}))
    out["pairs"] = dict(pairs=list(pr.PAIRS), kv=list(pr.KV_DOSSIER_PAIRS))
    return out


HARVEST_RELS = [
    ("leg", "leg.json"), ("leg", "chain.json"), ("leg", "RUNLOG.md"), ("leg", "x.stdout"), ("leg", "items/a.json"),
    ("leg", "items/a.ready.json"), ("leg", "a4/a.json"), ("leg", "a4/a.log"), ("leg", "s1/m.L0.full.a1.jsonl"),
    ("leg", "s1/m.L0.full.a1.manifest.json"), ("leg", "s1/m.item0.ready"), ("leg", "s1/m.ACK"), ("leg", "s1/p426_dnf/x.json"),
    ("leg", "tmp/mlx-manager-logs/a.log"), ("leg", "tmp/uv-0a.lock"), ("leg", "quarantine/x"), ("leg", "zzz.bin"),
    ("run", "home/x"), ("run", "grading-private/a.json"), ("run", "grading-private/a.out"), ("run", "grading-private/a.bin"),
    ("run", "cfg/opencode/opencode.json"), ("run", "cfg/opencode/plugins/x.js"), ("run", "other.txt"),
    ("evidence", "python__a.events.jsonl"), ("evidence", "python__a.json"), ("evidence", "python__a.stderr.txt"),
    ("evidence", "python__a.grades/seq-0001/report.xml"), ("evidence", "python__a.grades/seq-0001/stdout.txt"),
    ("evidence", "go__a.grades/seq-0001/go.stderr"), ("evidence", "go__a.grades/go.stderr"),
    ("evidence", "go__a.grades/seq-0001/go.jsonl"), ("evidence", "python__a.final_tree/manifest.json"),
    ("evidence", "python__a.final_tree/objects/ab"), ("evidence", "python__a.bin"),
]


def harvest_facts():
    return dict(rules=[[k, r, H.classify(k, r)] for k, r in HARVEST_RELS],
                ns={ns + "|" + lv: str(H.namespace_root(ns, lv)) for ns in ("wave2", "wave2.x") for lv in ("mtp", "kv")},
                arm_of={n: H._arm_of(n) for n in ("tg1-m76-n16-s1", "tg1-p426-off-pilot", "tg1-m76-rehearsal-kill")})


def b8_signals_facts(tmp_path):
    from bench import p426_signals as S
    from bench import p426_verify as V
    from bench.tests.test_m76_b3_impl_a7 import IDS, KVWorld
    fails = {rid: dict(passed=False, acc=0) for rid in IDS["s2"][:2]}
    w = KVWorld(tmp_path / "b8", rows={("x", "s2"): fails})
    b8 = V.verify_a7_kv(w.root, ("n16", "x"))
    rec, decode = S._kv_a7_section(w.root.parent, b8, "n16", "x")
    return _norm(dict(b8=b8, signals=rec, decode=decode), tmp_path)


VOLATILE_ROW = ("wall_s", "prompt_date_real", "tmp_window", "silence_observations", "events_path", "transcript_path",
                "stderr_path", "datefreeze_path", "evidence_sha256", "grade_reports", "final_tree", "worker_before",
                "worker_after", "termination", "tmp_escapes", "tmp_cleaned", "tmp_not_removed", "snapshot_sha256")


def tg1_row_facts(monkeypatch, tmp_path):
    """One tg1 row through the real tg1 entry (`run_tg1_probe.py`, fake opencode, real tg1 corpus and grader); volatile
    per-run fields (paths with the run id, times) are dropped; the closure-derived fields are kept apart."""
    import importlib
    from bench import structured_grade as sg
    from bench.tests.test_tg1_integration import tg_fixture
    fake_repo = tmp_path / "repo-venv"
    (fake_repo / ".venv-bench/bin").mkdir(parents=True)
    shim = fake_repo / ".venv-bench/bin/python"                         # the copy has no .venv-bench: the bench interpreter
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    shim.chmod(0o755)
    monkeypatch.setattr(sg, "REPO", fake_repo)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    p = importlib.import_module("run_tg1_probe")
    f = tg_fixture(p, monkeypatch, tmp_path)
    assert f["run"]("one", extra=["--expect-items", "python/one"]) == 0
    row = json.loads(f["out"].read_text())
    man = json.loads(f["out"].with_suffix(".manifest.json").read_text())
    from bench import arm_opencode as ao
    runtime = dict(man.get("runtime") or {})
    # the fake client binary embeds tmp paths: its sha varies per run, so the composite is compared with it fixed
    composite = ao.p311_generation_identity_sha256(dict(runtime, opencode_exe_sha256="fixed"))
    closure = dict(row={k: row.get(k) for k in CLOSURE_ROW},
                   runtime=dict({k: runtime.get(k) for k in CLOSURE_RUNTIME}, composite_fixed_exe=composite))
    assert row["generation_identity_sha256"] == runtime["generation_identity_sha256"]
    stable = {k: v for k, v in row.items() if k not in VOLATILE_ROW + CLOSURE_ROW}
    rt = {k: v for k, v in runtime.items() if k not in CLOSURE_RUNTIME + ("snapshot_sha256", "opencode_exe_sha256")}
    rt["snapshot_fields"] = {k: v for k, v in (rt.get("snapshot_fields") or {}).items() if k != "exe_sha256"}
    return dict(row=_norm(stable, tmp_path), runtime=_norm(rt, tmp_path),
                grade_reports=[dict(outcome=g["outcome"], final=g["final"], seq=g["seq"], artifacts=sorted(g["artifacts"]))
                               for g in row["grade_reports"]],
                final_tree=dict(files=row["final_tree"]["files"], missing=row["final_tree"]["missing"])), closure


def _facts(monkeypatch, tmp_path):
    row, closure = tg1_row_facts(monkeypatch, tmp_path / "row")
    facts = json.loads(json.dumps(dict(chain=_norm(chain_facts()), wave2=_norm(wave2_facts(tmp_path)),
                                       harvest=harvest_facts(), b8=b8_signals_facts(tmp_path), row=row), default=str))
    return facts, closure


@pytest.fixture
def recorded():
    if not FIXTURE.is_file():
        pytest.fail(f"{FIXTURE.name} missing: record it on the baseline with M76_B4B1_REGEN=1")
    return json.loads(FIXTURE.read_text())


def test_regen_or_compare(monkeypatch, tmp_path):
    (tmp_path / "row").mkdir()
    facts, closure = _facts(monkeypatch, tmp_path)
    if os.environ.get("M76_B4B1_REGEN") or not FIXTURE.is_file():         # recorded once, on the unchanged baseline
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(dict(facts=facts, closure=closure), indent=1, sort_keys=True) + "\n")
        pytest.skip("recorded the tg1 golden")
    rec = json.loads(FIXTURE.read_text())
    for key in ("chain", "wave2", "harvest", "b8", "row"):
        # S27 (spec v1.4): the only allowed differences — the chain entry's `--pause-file` (§8.2), the row's `cleanup_status`
        # (§3.6), the tg1 template's `inject_allowed` + interrupt (§4.5) and the policy sha it rotates (§9)
        s27 = (".args.pause_file", ".row.cleanup_status", ".runtime.policy.inject_allowed", ".runtime.scaffold_policy_sha256")
        diffs = [d for d in _diff(facts[key], rec["facts"][key]) if not d.split(":", 1)[0].endswith(s27)]
        assert not diffs, f"tg1 {key} facts differ from the baseline golden: " + "; ".join(diffs[:12])


def _diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += _diff(a.get(k, "<absent>"), b.get(k, "<absent>"), f"{path}.{k}")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in _diff(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: {str(a)[:80]!r} != {str(b)[:80]!r}"]


def test_closure_identity_fields_rotate(monkeypatch, tmp_path, recorded):
    """C178: the shared-core edit rotates the tg1 closure identities (probe_code_sha256 and the composite derived from it)."""
    (tmp_path / "row").mkdir()
    _, closure = tg1_row_facts(monkeypatch, tmp_path / "row")
    was = recorded["closure"]
    assert closure["runtime"]["probe_code_sha256"] != was["runtime"]["probe_code_sha256"]
    assert closure["runtime"]["composite_fixed_exe"] != was["runtime"]["composite_fixed_exe"]
