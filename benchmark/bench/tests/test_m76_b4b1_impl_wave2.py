"""M76 B4b-1 acceptance 1 (implementer tests): the tg2 Wave 2 legs of lever kv — the sequencer's tg2 table, argv, deadlines and
namespace, the positives record (sealed; a failed kind refuses v8; a changed record refuses on resume), the tg2 rehearsal
manifest / v8 base / amendment (the freeze round trip up to an s1 leg's record check), `tg2_strict_rows` (a DNF slot, a missing
slot), the two re-check gates (inside / outside / unrealisable; the stop, rc 5, the ack), the dossier pairs of tg2, and the
harvest rules on the recorded real `tg2_grade` trees."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import p426_freeze as fz
from bench import p426_harvest as H
from bench import p426_hooks as ph
from bench import p426_receipt as pr
from bench import p426_wave2 as W2
from bench import schedules

BENCH = Path(__file__).resolve().parents[1].parent
FIX = Path(__file__).resolve().parent / "fixtures" / "m76_b4b1_impl" / "tg2-grade-trees"
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
DRAW = json.loads((BENCH / "m65/tg2_draw.json").read_text())
LANGS = ("rust", "javascript", "java", "cpp")
DATE = "Fri Nov 13 2026"
IDENT = dict(probe_code_sha256="a" * 64, scaffold_policy_sha256="b" * 64, generation_identity_sha256="c" * 64)
COMMIT = {"n16": "1" * 40, "x": "2" * 40}
GITLINKS = {"src/mlx-vlm": "3" * 40, "src/mlx-serve": "4" * 40}


def _T():
    sys.path.insert(0, str(BENCH / "chains" / "c147"))
    import run_tg2_chain as T
    return T


def perm(lang):
    return DRAW["languages"][lang]["permutation"]


# ----------------------------------------------------------------------------------------------- the table and argv
def test_the_tg2_leg_table():
    t = W2.kv_tg2_legs("n16", "x")
    assert [s["name"] for s in t["run"]] == ["tg2-m76-n16-pilot", "tg2-m76-x-pilot", "tg2-m76-n16-s1", "tg2-m76-x-s1",
                                             "tg2-m76-x-s2", "tg2-m76-n16-s2", "tg2-m76-x-reload", "tg2-m76-n16-reload"]
    assert [s["role"] for s in t["run"]] == ["first", "second"] * 4
    assert [s["record"] for s in t["run"]] == ["v8", "v8"] + ["amendment"] * 6
    assert [s["name"] for s in t["rehearsal"]] == ["tg2-m76-x-rehearsal-r2", "tg2-m76-n16-rehearsal-r3"]
    assert [s["expect"] for s in t["rehearsal"]] == ["INVALID", "VALID"] and t["makeup"] == ()
    with pytest.raises(ValueError):
        W2.kv_tg2_legs("x", "n16")


def _records(tmp_path, **v8_extra):
    run = tmp_path / "run"
    run.mkdir(exist_ok=True)
    v8 = ph.write_exclusive(run / "v8_base.json", dict(kind=fz.KIND_V8, lever="kv", arms=["n16", "x"], corpus="tg2",
                                                       n16_commit=COMMIT["n16"], x_commit=COMMIT["x"], frozen_prompt_date=DATE,
                                                       pilot_deadline_s=fz.TG2_PILOT_DEADLINE_S, **IDENT, **v8_extra))
    amend = ph.write_exclusive(run / "amendment.json", dict(kind=fz.KIND_AMENDMENT, v8_base_sha256=v8["sha256"], corpus="tg2",
                                                            leg_deadline_s=dict(s1=10.0, s2=20.0, reload=5.0)))
    return run, v8, amend


def test_the_tg2_argv_is_what_the_tg2_chain_accepts(tmp_path):
    T = _T()
    run, v8, amend = _records(tmp_path)
    t = W2.kv_tg2_legs("n16", "x")
    wts = {"n16": tmp_path / "wt-n16", "x": tmp_path / "wt-x"}
    for spec in t["run"]:
        rec = run / ("v8_base.json" if spec["record"] == "v8" else "amendment.json")
        argv = W2.leg_argv(spec, 3, worktrees=wts, record_path=rec, out_base=tmp_path / "ob", lever="kv")
        assert argv[1] == str(wts[spec["arm"]] / "benchmark/chains/c147/run_tg2_chain.py")
        assert argv[argv.index("--out-root") + 1] == str(tmp_path / "ob" / f"{spec['name']}.a3")
        a = T.parse_args(argv[2:])
        assert a.tg2_leg == spec["kind"] and a.kv_arm == spec["arm"] and a.predictor == "mtp"
        assert W2.leg_deadline(amend, v8, spec) == (fz.TG2_PILOT_DEADLINE_S if spec["kind"] == "pilot"
                                                    else amend["leg_deadline_s"][spec["kind"]])
    assert fz.TG2_PILOT_DEADLINE_S == W2.REHEARSAL_DEADLINE_S == 6 * 3600.0


def test_the_tg2_namespace(tmp_path):
    ops = W2.BoxSeqOps(tmp_path, main_root=tmp_path / "main", evidence_stage=tmp_path / "ev", lever="kv", corpus="tg2")
    assert ops.harvest_path("tg2-m76-x-s1.a1") == tmp_path / "main/benchmark/results/m76/wave2.tg2/tg2-m76-x-s1.a1"
    tg1 = W2.BoxSeqOps(tmp_path, main_root=tmp_path / "main", evidence_stage=tmp_path / "ev", lever="kv")
    assert tg1.harvest_path("tg1-m76-x-s1.a1") == tmp_path / "main/benchmark/results/m76/wave2/tg1-m76-x-s1.a1"
    assert H.namespace_root("wave2.tg2", "kv") == Path("benchmark/results/m76/wave2.tg2")
    assert H._arm_of("tg2-m76-n16-rehearsal-r3") == "n16" and H._arm_of("tg2-m76-x-reload") == "x"


def test_the_tg2_dossier_pairs(tmp_path):
    for pair in ("pilot", "s1", "s2", "reload"):
        assert pair in pr.dossier_pairs("tg2")
    for pair in ("r1", "makeup", "s3"):
        assert pair not in pr.dossier_pairs("tg2")
        with pytest.raises(ValueError):
            pr.write_kv_dossier(tmp_path / f"{pair}.json", pair=pair, ref="n16", test="x", arms={}, differences=[],
                                verdict="PASS", corpus="tg2")
    assert pr.dossier_pairs("tg1") == pr.KV_DOSSIER_PAIRS


# ----------------------------------------------------------------------------------------------- positives (E6)
class PosOps:
    """The box side of the positives (`p426_wave2 positives`): the worktree, the probe identity, the serving session, the
    grader results of the stubs / references, the inject probe runs and their `inject_verify` verdicts."""

    def __init__(self, *, fail=None, aborts=None, grade_fail=None):
        self.fail, self.aborts, self.grade_fail = fail or set(), dict(aborts or {}), grade_fail or set()
        self.served, self.runs = [], []

    def worktree_state(self, path):
        return dict(head=COMMIT["n16"], clean=True, gitlinks=dict(GITLINKS))

    def identity(self, path):
        return dict(IDENT)

    def positives_session(self, worktree, *, frozen_prompt_date):
        ops = self

        class Session:
            def __enter__(self):
                ops.served.append(("start", str(worktree), frozen_prompt_date))
                return self

            def __exit__(self, *exc):
                ops.served.append(("stop",))
                return False
        return Session()

    def positive_grade(self, lang, item, variant):
        passed = variant == "reference"
        if (lang, variant) in self.grade_fail:
            passed = not passed
        return dict(outcome="parsed", passed=passed, failing=0 if passed else 3, leaves=5 if passed else 2)

    def positive_inject(self, lang, item, kind, *, seed, attempt):
        self.runs.append((lang, kind, attempt))
        if self.aborts.get((lang, kind), 0) >= attempt:
            return dict(transport_abort=True, run=f"run-{lang}-{kind}-{attempt}")
        # S27 X12: a PASS row always exists and must verify against the recorded sha (the writer no longer skips a missing
        # row): the run directory lives under the test's STACK_WORKDIR; its name keeps the language at split("-")[1]
        import hashlib
        import os
        run = Path(os.environ["STACK_WORKDIR"]) / f"run-{lang}-{kind}-{attempt}"
        run.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(dict(id=f"{lang}/{item}", kind=kind)) + "\n").encode()
        (run / f"{kind}.attempt{attempt}.jsonl").write_bytes(raw)
        return dict(transport_abort=False, run=str(run), rc=0, row_sha256=hashlib.sha256(raw).hexdigest(),
                    evidence_sha256="e" * 64)

    def inject_verify(self, run, kind):
        lang = Path(run).name.split("-")[1]
        return "FAIL" if (lang, kind) in self.fail else "PASS"


def _positives(tmp_path, ops, name="positives.json"):
    out = tmp_path / "run" / name
    rc = W2.main(["positives", "--corpus", "tg2", "--lever", "kv", "--arm-worktree", f"n16={tmp_path / 'wt-n16'}",
                  "--out", str(out), "--frozen-prompt-date", DATE], ops=ops)
    return rc, out


@pytest.fixture
def wd(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    return tmp_path


def test_the_positives_record_is_sealed_and_complete(wd):
    ops = PosOps(aborts={("java", "loop"): 1})
    rc, out = _positives(wd, ops)
    assert rc == 0
    doc = json.loads(out.read_text())
    assert ph.sealed_ok(doc) and doc["kind"] == "tg2_positives" and doc["verdict"] == "PASS"
    assert doc["n16_commit"] == COMMIT["n16"] and all(doc[k] == v for k, v in IDENT.items())
    assert doc["scaffold"] == "opencode-v2-web-tg2" and doc["frozen_prompt_date"] == DATE
    assert doc["draw_sha256"] == schedules.TG2_DRAW_SHA256 and doc["universe_sha256"] == schedules.TG2_UNIVERSE_SHA256
    assert doc["image_id"]
    # S27 §4.5 (C373): + ONE deterministic interrupt positive (the first tg2 language's pilot item), run first
    assert sorted((p["language"], p["kind"]) for p in doc["injects"]) == sorted(
        [(lang, k) for lang in LANGS for k in ("stall", "loop", "alloc")] + [(LANGS[0], "interrupt")])
    assert doc["injects"][0]["kind"] == "interrupt" and doc["proofs"][f"{LANGS[0]}/interrupt"] == "in_flight"
    for p in doc["injects"]:
        assert p["item"] == perm(p["language"])[0] and p["seed"] == 1001 and p["verdict"] == "PASS"
        assert p["attempts"] == (2 if (p["language"], p["kind"]) == ("java", "loop") else 1)
    assert {(g["language"], g["variant"]): g["passed"] for g in doc["grades"]} == {
        (lang, v): v == "reference" for lang in LANGS for v in ("stub", "reference")}
    assert ops.served[0][0] == "start" and ops.served[-1] == ("stop",)
    rc2, _ = _positives(wd, PosOps())
    assert rc2 == 2                                                           # exclusive: never overwritten


@pytest.mark.parametrize("ops_kw", [dict(fail={("cpp", "alloc")}), dict(aborts={("rust", "stall"): 2}),
                                    dict(grade_fail={("java", "stub")})], ids=["verify-fail", "two-aborts", "stub-pass"])
def test_a_failed_positive_is_recorded_and_not_a_pass(wd, ops_kw):
    rc, out = _positives(wd, PosOps(**ops_kw))
    assert rc == 1
    doc = json.loads(out.read_text())
    assert ph.sealed_ok(doc) and doc["verdict"] == "FAIL" and doc["problems"]


# ----------------------------------------------------------------------------------------------- L1: a real-shaped v2 inject row
RUN_ID = "20261116T120000-abcdefabcdef"


def _ev(kind, mid, **part):
    return json.dumps(dict(type=kind, sessionID="s1", part=dict(messageID=mid, **part)))


def _v2_stall_row(base, *, toolwindows=False):
    """A tg2 stall positive's row and manifest as the probe writes them: the evidence fields from the real
    `OpencodeArm.row_fields` over the real `evidence_suffixes` (events / export / stderr / datefreeze [+ toolwindows]), the
    grade reports from the real `arm_runner.grade_reports` over a recorded real `tg2_grade` tree."""
    import hashlib
    import shutil
    from bench import arm_opencode as ao
    from bench import arm_runner
    from bench import structured_grade as sg
    base.mkdir(parents=True, exist_ok=True)
    arm = ao.OpencodeArm(None, mode="tg1", scaffold="tg2")
    suffixes = dict(arm.evidence_suffixes())
    assert "datefreeze" in suffixes                                   # every v2 row is date-frozen
    if toolwindows:
        suffixes["toolwindows"] = ".toolwindows.jsonl"
    stem = base / "evidence" / "rust__say"
    stem.parent.mkdir(parents=True, exist_ok=True)
    events = []
    for k in range(1, 6):
        events += [_ev("step_start", f"m{k}", id=f"s{k}"), _ev("step_finish", f"m{k}", id=f"f{k}")]
    events.append(_ev("step_start", "m6", id="s6"))
    artifacts = {}
    for key, suffix in suffixes.items():
        path = stem.with_name(stem.name + suffix)
        path.write_text("\n".join(events) + "\n" if key == "events" else "{}" if key == "export" else f"{key}\n")
        artifacts[key] = path
    fields = ao.OpencodeArm.row_fields(arm, version="2.0.20", rc=0, artifacts=artifacts,
                                       sha_of=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest(), portable=str)
    keep = base / "keep"
    src = FIX / "rust" / "reference" / "rust__say.grades" / "seq-0001"
    shutil.copytree(src, keep / "seq-0001")
    index = json.loads((keep / "seq-0001" / "index.json").read_text())
    names = sorted(p.name for p in (keep / "seq-0001").iterdir() if p.is_file() and p.name != "index.json")
    sg._write_index(keep, keep / "seq-0001", 1, 5, True, index["outcome"], names)
    reports = arm_runner.grade_reports(keep)
    worker = dict(pid=1, create_time=2.0, model_path="m", registry_sha256="a" * 64)
    killed = [dict(pid=10, create_time=1.0, role="client", argv=["opencode", "run"])]
    row = dict(fields, id="rust/say", scaffold="opencode-v2-web-tg2-inject:stall", test_modified=False, grade_reports=reports,
               gate=dict(stop_reason="stalled", no_progress_tokens=50, no_progress_requests=5, max_identical_run_live=1,
                         baseline_failing=1, failing_trajectory=[[1, 1, False]], requests_completed=5),
               termination=dict(reason="stalled", killed=killed, killed_verified=True, cancel_wait_s=2.5, in_flight_at_kill=1,
                                worker_summary_before=dict(in_flight=1, requests_started=4, requests_completed=3),
                                worker_summary_after=dict(in_flight=0, requests_started=4, requests_completed=3)),
               reconciliation=dict(unmatched_export_messages=1, trailing="interrupted"), mem_kills=[],
               worker_before=worker, worker_after=worker, request_usage=[["1", 10, 100, 81920]], orphans_unattributed=[])
    manifest = dict(run_id=RUN_ID, runtime=dict(scaffold=row["scaffold"],
                                                inject=dict(kind="stall", policy=dict(gate={}, hygiene=dict(per_process=1)))))
    return row, manifest


def _fake_worktree(tmp_path, row, manifest):
    """An arm worktree whose venv python is the bench interpreter, except that `run_tg2_probe.py` (the probe: it needs the
    router, the worker and the agent) writes the prepared row / manifest to its `--out`; `inject_verify.py` is the real one."""
    import os
    wt = tmp_path / "wt-n16"
    (wt / "benchmark/m62").mkdir(parents=True)
    os.symlink(BENCH / "m62" / "inject_verify.py", wt / "benchmark/m62/inject_verify.py")
    (wt / "benchmark/run_tg2_probe.py").write_text("raise SystemExit('never run: the fake interpreter answers')\n")
    (tmp_path / "prepared.jsonl").write_text(json.dumps(row) + "\n")
    (tmp_path / "prepared.manifest.json").write_text(json.dumps(manifest))
    py = wt / ".venv-bench/bin/python"
    py.parent.mkdir(parents=True)
    py.write_text(f"""#!/bin/sh
case "$1" in
  *run_tg2_probe.py)
    out=""; prev=""
    for x in "$@"; do [ "$prev" = "--out" ] && out="$x"; prev="$x"; done
    cp "{tmp_path}/prepared.jsonl" "$out" && cp "{tmp_path}/prepared.manifest.json" "${{out%.jsonl}}.manifest.json"
    exit 0;;
esac
exec "{sys.executable}" "$@"
""")
    py.chmod(0o755)
    return wt


def _box_positives(tmp_path, wt):
    import os
    ops = W2.BoxSeqOps(tmp_path, main_root=tmp_path / "main", evidence_stage=tmp_path / "ev", lever="kv", corpus="tg2")
    out_root = tmp_path / "m65" / "inject" / "positives-x"
    out_root.mkdir(parents=True)
    ops._pos = dict(ops=SimpleNamespace(env_base=lambda: dict(os.environ)), wt=wt, out_root=out_root, date=DATE,
                    receipt=tmp_path / "a4.json")
    return ops


@pytest.mark.parametrize("toolwindows", [False, True], ids=["v2", "v2+toolwindows"])
def test_l1_a_real_shaped_tg2_inject_row_verifies_through_the_box_seams(tmp_path, toolwindows):
    row, manifest = _v2_stall_row(tmp_path / "arts", toolwindows=toolwindows)
    assert set(row["evidence_sha256"]) == {"events", "export", "stderr", "datefreeze"} | ({"toolwindows"} if toolwindows else set())
    ops = _box_positives(tmp_path, _fake_worktree(tmp_path, row, manifest))
    res = ops.positive_inject("rust", "rust/say", "stall", seed=1001, attempt=1)
    assert res["transport_abort"] is False and Path(res["run"], "stall.attempt1.jsonl").is_file()
    assert ops.inject_verify(res["run"], "stall") == "PASS"


def _iv_verdict(tmp_path, row, manifest):
    if str(BENCH) not in sys.path:
        sys.path.insert(0, str(BENCH))
    from m62 import inject_verify as iv
    run = tmp_path / "run"
    run.mkdir(parents=True)
    (run / "stall.attempt1.jsonl").write_text(json.dumps(row) + "\n")
    (run / "stall.attempt1.manifest.json").write_text(json.dumps(manifest))
    lines = []
    code = iv.main(["--run", str(run), "--kind", "stall", "--workdir", str(tmp_path), "--scaffold", "opencode-v2-web-tg2"],
                   out=lines.append)
    return lines[0].split(": ", 1)[1], code


def _drop_datefreeze(row):
    row["evidence_sha256"].pop("datefreeze")
    row.pop("datefreeze_path")


def _wrong_datefreeze(row):
    Path(row["datefreeze_path"]).write_text("changed\n")


def _stray_key(row):
    row["evidence_sha256"]["extra"] = "0" * 64


def _toolwindows_without_path(row):
    row["evidence_sha256"]["toolwindows"] = row["evidence_sha256"]["stderr"]


def _datefreeze_path_missing(row):
    row.pop("datefreeze_path")


@pytest.mark.parametrize("mutate,want", [
    (_drop_datefreeze, "FAIL:evidence_sha256_keys"), (_wrong_datefreeze, "FAIL:evidence_sha:datefreeze"),
    (_stray_key, "FAIL:evidence_sha256_keys"), (_toolwindows_without_path, "FAIL:evidence_sha256_keys"),
    (_datefreeze_path_missing, "FAIL:evidence_sha256_keys")],
    ids=["no-datefreeze", "datefreeze-sha", "stray-key", "toolwindows-no-path", "datefreeze-no-path"])
def test_l1_the_tg2_evidence_keys_are_the_rows_recorded_artifacts(tmp_path, mutate, want):
    row, manifest = _v2_stall_row(tmp_path / "arts")
    assert _iv_verdict(tmp_path / "ok", row, manifest) == ("PASS", 0)
    mutate(row)
    assert _iv_verdict(tmp_path / "bad", row, manifest) == (want, 1)


# ----------------------------------------------------------------------------------------------- rehearsal manifest, v8, amendment
class FreezeOps:
    def worktree_state(self, path):
        arm = "n16" if "n16" in str(path) else "x"
        return dict(head=COMMIT[arm], clean=True, gitlinks=dict(GITLINKS))

    def identity(self, path):
        return dict(IDENT)

    def build_inputs(self):
        from bench import p426_plan
        b = sorted(p426_plan.KV_BUILDS)[0]
        exp = p426_plan.EXPECTED_BUILDS[b]
        return dict(build=b, production_ref=exp["production_ref"], grader_image_id="sha256:" + "f" * 64, frozen_prompt_date=DATE,
                    stack_suite_receipt_sha256="9" * 64)

    def historical_walls(self):
        raise AssertionError("tg2 takes no historical walls")


OK = lambda kind, **inputs: []                                       # noqa: E731


def _worktrees(wd):
    from bench import p426_plan
    exp = p426_plan.EXPECTED_BUILDS[sorted(p426_plan.KV_BUILDS)[0]]
    GITLINKS.update({"src/mlx-vlm": exp["mlx_vlm"], "src/mlx-serve": exp["mlx_serve"]})
    out = {}
    for arm in ("n16", "x"):
        wt = wd / f"wt-{arm}"
        pins = wt / fz.PINS_RELATIVE
        pins.parent.mkdir(parents=True, exist_ok=True)
        pins.write_text('{"pins": 1}\n')
        out[arm] = wt
    return out


def _rehearsal_leg(wd, name, state, manifest, *, inject, elapsed=120.0):
    root = wd / "m76/p426/rehearsal.tg2" / name
    (root / "items").mkdir(parents=True)
    slot = f"tg2-p426|oc|{ENTRY}|s1|rust|{perm('rust')[0].split('/')[1]}"
    rec = ph.seal(dict(slot=slot, verdict="reconciled", case="kill_boundary" if "r3" in name else "completed",
                       requests=[dict(elapsed_s=elapsed, generated_tokens=40)]))
    (root / "items" / "x.json").write_text(json.dumps(rec))
    invalid = [dict(stage="done", slot=slot, reason=fz.R2_REASON)] if state == "INVALID" else []
    (root / "chain.json").write_text(json.dumps(dict(status="finished", p426_invalid=invalid, p426_dnf=[], inject=inject,
                                                     frozen_record=dict(path=fz.portable(manifest, wd),
                                                                        sha256=json.loads(manifest.read_text())["sha256"]))))
    ph.write_exclusive(root / "receipt.json", dict(argv={}, env={}))
    ph.write_exclusive(root / "leg.json", dict(leg=name.rsplit(".a", 1)[0], attempt=1, state=state,
                                               reason=fz.R2_REASON if state == "INVALID" else ""))
    return root


def _freeze(argv, ops):
    return fz.main(argv, ops=ops, checks=OK)


def _round_trip(wd, *, positives_ops=None, tamper=None, extra_v8=()):
    wts = _worktrees(wd)
    kv = ["--lever", "kv", "--corpus", "tg2", "--pair", "n16,x", "--arm-worktree", f"n16={wts['n16']}",
          "--arm-worktree", f"x={wts['x']}"]
    rec = wd / "run"
    manifest = rec / "rehearsal_manifest.json"
    assert _freeze(["rehearsal", *kv, "--out-root", str(wd / "m76/p426/rehearsal.tg2/r"), "--out", str(manifest),
                    "--frozen-prompt-date", DATE], FreezeOps()) == 0
    mdoc = json.loads(manifest.read_text())
    assert mdoc["corpus"] == "tg2" and mdoc["kind"] == fz.KIND_REHEARSAL
    r2 = _rehearsal_leg(wd, "tg2-m76-x-rehearsal-r2.a1", "INVALID", manifest, inject="reconcile-mismatch", elapsed=300.0)
    r3 = _rehearsal_leg(wd, "tg2-m76-n16-rehearsal-r3.a1", "VALID", manifest, inject="stall-kill", elapsed=200.0)
    rc, pos = _positives(wd, positives_ops or PosOps())
    if tamper:
        tamper(pos)
    v8 = rec / "v8_base.json"
    rc = _freeze(["v8", *kv, "--rehearsal-manifest", str(manifest), "--r2", str(r2), "--r3", str(r3), "--positives", str(pos),
                  "--out", str(v8), *extra_v8], FreezeOps())
    return rc, v8, pos


def test_the_freeze_round_trip_to_an_s1_leg(wd, monkeypatch):
    rc, v8, pos = _round_trip(wd)
    assert rc == 0
    base = json.loads(v8.read_text())
    assert base["corpus"] == "tg2" and base["lever"] == "kv" and base["arms"] == ["n16", "x"]
    assert base["positives_sha256"] == json.loads(pos.read_text())["sha256"]
    assert base["tg2_draw_sha256"] == schedules.TG2_DRAW_SHA256 and base["pilot_deadline_s"] == fz.TG2_PILOT_DEADLINE_S
    assert base["settle_bound_s"] == max(900.0, 2 * 300.0)
    assert set(base["rehearsal_receipts"]) == {"r2", "r3"} and "r1_env_difference" not in base
    # pilot -> the strict pilot gate -> the amendment
    seen = {}

    def gate(a, b, arms, *, leg_name=None, n=None):
        seen.update(leg=[leg_name(x) for x in arms], n=n)
        return []
    monkeypatch.setattr(fz, "pilot_gate_problems", gate)
    monkeypatch.setattr(fz, "pilot_dossier_problems", lambda *a, **k: [])
    roots = {}
    for arm, walls in (("n16", {"rust": 500.0, "javascript": 100.0, "java": 200.0, "cpp": 300.0}),
                       ("x", {"rust": 400.0, "javascript": 900.0, "java": 100.0, "cpp": 100.0})):
        roots[arm] = _pilot_root(wd, arm, walls)
    monkeypatch.setattr(fz, "pilot_dossier_path", lambda a, b, arms=None: _dossier(wd))
    out = v8.with_name("amendment.json")
    amend = fz.write_amendment(v8, roots["n16"], roots["x"], out, None, corpus="tg2")
    assert seen == dict(leg=["tg2-m76-n16-pilot", "tg2-m76-x-pilot"], n=4)
    w = dict(rust=500.0, javascript=900.0, java=382.0, cpp=382.0)
    assert {lang: amend[f"w_{lang}_s"] for lang in LANGS} == w
    for leg, n in (("s1", 20), ("s2", 20), ("reload", 5)):
        assert amend["leg_deadline_s"][leg] == pytest.approx(1.5 * sum(n * w[lang] for lang in LANGS) + 1800 + 3660)
    assert amend["corpus"] == "tg2" and amend["v8_base_sha256"] == base["sha256"]
    # an s1 leg runs under the amendment, a tg1 record never runs a tg2 leg
    T = _T()
    a = T.parse_args(["--leg", "s1", "--p426", "--models", ENTRY, "--predictor", "mtp", "--out-root", str(wd / "o/tg2-m76-n16-s1.a1"),
                      "--campaign-core", "c", "--frozen-prompt-date", DATE, "--probe-code-sha", "a" * 64, "--policy-sha",
                      "b" * 64, "--frozen-record", str(out), "--lever", "kv", "--kv-arm", "n16"])
    assert T.check_frozen_record(a)["base"]["corpus"] == "tg2"
    tg1 = ph.write_exclusive(wd / "tg1v8" / "v8_base.json", dict(kind=fz.KIND_V8, lever="kv", arms=["n16", "x"]))
    a.mode, a.frozen_record = "pilot", str(wd / "tg1v8" / "v8_base.json")
    with pytest.raises(T.Refused, match="tg2"):
        T.check_frozen_record(a)
    assert tg1


def _pilot_root(wd, arm, walls):
    root = wd / "m76/p426/wave2.tg2" / f"tg2-m76-{arm}-pilot.a1" / "pilot"
    root.mkdir(parents=True)
    lines = [json.dumps(dict(id=perm(lang)[0], wall_s=w)) for lang, w in walls.items()]
    (root / "x.L0.full.a1.jsonl").write_text("\n".join(lines) + "\n")
    leg = root.parent
    (leg / "chain.json").write_text(json.dumps(dict(progress=dict(invocations=[dict(status="validated", file="pilot/x.L0.full.a1.jsonl")]))))
    (leg / "items").mkdir()
    (leg / "items" / "a.json").write_text(json.dumps(dict(requests=[dict(elapsed_s=100.0)])))
    return leg


def _dossier(wd):
    p = wd / "pairs" / "pilot.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}")
    return p


def test_v8_refuses_a_failed_positives_record(wd):
    rc, v8, _ = _round_trip(wd, positives_ops=PosOps(fail={("rust", "loop")}))
    assert rc == 2 and not v8.exists()


def test_v8_refuses_a_changed_positives_record(wd):
    def tamper(pos):
        doc = json.loads(pos.read_text())
        doc["n16_commit"] = "9" * 40
        pos.write_text(json.dumps(ph.seal({k: v for k, v in doc.items() if k != "sha256"})))
    rc, v8, _ = _round_trip(wd, tamper=tamper)
    assert rc == 2 and not v8.exists()


def test_the_sequencer_reverifies_the_positives_record_on_resume(wd):
    rc, v8, pos = _round_trip(wd)
    assert rc == 0
    a = SimpleNamespace(cmd="run", lever="kv", corpus="tg2", arms=("n16", "x"), worktrees={"n16": wd / "wt-n16", "x": wd / "wt-x"},
                        out_base=str(wd / "m76/p426/wave2.tg2"), pause_file=None, record_dir=str(v8.parent), rerun=[],
                        rerun_reason=None, through=None, recheck_ack=None)
    seq = W2.Sequencer(a, SimpleNamespace(), lambda: 0.0, lambda s: None, wd)
    seq.load_records()                                                         # the sealed record matches v8
    doc = json.loads(pos.read_text())
    doc["image_id"] = "sha256:" + "0" * 64
    pos.write_text(json.dumps(ph.seal({k: v for k, v in doc.items() if k != "sha256"})))
    with pytest.raises(fz.Refusal, match="positives"):
        seq.load_records()


def test_a_tg2_leg_without_a_deadline_never_launches(tmp_path):
    run, v8, amend = _records(tmp_path)
    a = SimpleNamespace(cmd="run", lever="kv", corpus="tg2", arms=("n16", "x"), worktrees={"n16": tmp_path, "x": tmp_path},
                        out_base=str(tmp_path / "ob"), pause_file=None, record_dir=str(run), rerun=[], rerun_reason=None,
                        through=None, recheck_ack=None)
    launched = []
    seq = W2.Sequencer(a, SimpleNamespace(launch=lambda *x, **k: launched.append(x)), lambda: 0.0, lambda s: None, tmp_path)
    seq.wait_boundary = seq.verify_world = seq.check_power = lambda: None
    seq.base, seq.amendment = v8, dict(amend, leg_deadline_s=dict(s1=10.0))
    spec = seq.by_name["tg2-m76-x-s2"]
    with pytest.raises(W2.Stop, match="no supervision deadline"):
        seq.run_leg(spec)
    assert launched == [] and seq.seq["legs"] == []


# ----------------------------------------------------------------------------------------------- strict rows (for the re-checks)
def _leg(root, session, rows, dnf=(), planned=None):
    sched = schedules.tg2_p426(DRAW, session, ENTRY, "mtp")
    root.mkdir(parents=True)
    (root / "schedule.json").write_text(json.dumps(sched))
    (root / session).mkdir()
    (root / session / "m.L0.full.a1.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (root / session / "m.L0.full.a1.manifest.json").write_text("{}")
    (root / "chain.json").write_text(json.dumps(dict(schedule_sha256=schedules.schedule_sha256(sched), p426_dnf=[
        dict(slot=f"tg2-p426|oc|{ENTRY}|{session}|{i.split('/')[0]}|{i.split('/')[1]}", item=i.split("/")[1],
             language=i.split("/")[0], session=session) for i in dnf])))
    return root


def _ids(session):
    return [i for lg in schedules.tg2_p426(DRAW, session, ENTRY, "mtp")["blocks"][0]["legs"] for i in lg["invocations"][0]["expect"]]


def test_strict_rows_score_pass_and_converged_and_a_dnf_as_zero(tmp_path):
    ids = _ids("s1")
    rows = [dict(id=i, passed=k % 3 != 0, converged=k % 5 != 0) for k, i in enumerate(ids[1:], 1)]
    root = _leg(tmp_path / "a", "s1", rows, dnf=[ids[0]])
    got = W2.tg2_strict_rows([root], "s1")
    assert set(got) == set(ids)
    assert got[ids[0]] == {"s1": 0}
    for k, i in enumerate(ids[1:], 1):
        assert got[i] == {"s1": int(k % 3 != 0 and k % 5 != 0)}


def test_strict_rows_refuse_a_planned_slot_with_neither_row_nor_dnf(tmp_path):
    ids = _ids("s1")
    root = _leg(tmp_path / "a", "s1", [dict(id=i, passed=True, converged=True) for i in ids[1:]])
    with pytest.raises(fz.Refusal, match=ids[0]):
        W2.tg2_strict_rows([root], "s1")


def _all_rows(ids):
    return [dict(id=i, passed=True, converged=True) for i in ids]


def test_l4_strict_rows_refuse_a_stray_row(tmp_path):
    ids = _ids("s1")
    stray = perm("rust")[25]
    assert stray not in ids
    root = _leg(tmp_path / "a", "s1", _all_rows(ids) + [dict(id=stray, passed=True, converged=True)])
    with pytest.raises(fz.Refusal, match=stray):
        W2.tg2_strict_rows([root], "s1")


def test_l4_strict_rows_refuse_a_stray_dnf(tmp_path):
    ids = _ids("s1")
    stray = perm("cpp")[-1]
    assert stray not in ids
    root = _leg(tmp_path / "a", "s1", _all_rows(ids), dnf=[stray])
    with pytest.raises(fz.Refusal, match=stray):
        W2.tg2_strict_rows([root], "s1")


def test_l4_strict_rows_refuse_a_slot_with_both_a_row_and_a_dnf(tmp_path):
    ids = _ids("s1")
    root = _leg(tmp_path / "a", "s1", _all_rows(ids), dnf=[ids[3]])
    with pytest.raises(fz.Refusal, match=ids[3]):
        W2.tg2_strict_rows([root], "s1")


def test_l4_a_dnf_of_another_session_is_not_this_sessions(tmp_path):
    ids = _ids("s1")
    root = _leg(tmp_path / "a", "s1", _all_rows(ids))
    chain = json.loads((root / "chain.json").read_text())
    chain["p426_dnf"].append(dict(slot="x", item=perm("rust")[25].split("/")[1], language="rust", session="s2"))
    (root / "chain.json").write_text(json.dumps(chain))
    assert set(W2.tg2_strict_rows([root], "s1")) == set(ids)


# ----------------------------------------------------------------------------------------------- the re-check gates (E4)
class RecheckOps:
    def __init__(self, roots):
        self.roots = roots
        self.published = []

    def harvest_path(self, attempt):
        return self.roots[attempt]

    def publish_run_files(self, paths, *, emails):
        self.published.append([Path(p).name for p in paths])


def _seq(tmp_path, roots, ack=None):
    a = SimpleNamespace(cmd="run", lever="kv", corpus="tg2", arms=("n16", "x"), worktrees={"n16": tmp_path, "x": tmp_path},
                        out_base=str(tmp_path / "ob"), pause_file=None, record_dir=str(tmp_path / "ob" / "run"), rerun=[],
                        rerun_reason=None, through=None, recheck_ack=ack)
    seq = W2.Sequencer(a, RecheckOps(roots), lambda: 0.0, lambda s: None, tmp_path)
    for arm in ("n16", "x"):
        seq.seq["legs"].append(dict(leg=f"tg2-m76-{arm}-s1", attempt=1, state="VALID"))
        seq.seq["harvested"].append(dict(attempt=f"tg2-m76-{arm}-s1.a1", harvest_sha256="h"))
    return seq


def _pair_roots(tmp_path, n16_pass, x_pass):
    ids = _ids("s1")
    return {f"tg2-m76-{arm}-s1.a1": _leg(tmp_path / arm, "s1", [dict(id=i, passed=bool(f(k)), converged=True) for k, i in enumerate(ids)])
            for arm, f in (("n16", n16_pass), ("x", x_pass))}


def test_an_inside_recheck_is_sealed_recorded_and_continues(tmp_path):
    seq = _seq(tmp_path, _pair_roots(tmp_path, lambda k: k % 2, lambda k: (k % 2) ^ (k < 8)))
    seq.ensure_recheck("s1")
    path = tmp_path / "ob" / "run" / "recheck-s1.json"
    doc = json.loads(path.read_text())
    assert ph.sealed_ok(doc) and doc["recheck"]["inside"] is True and doc["gate"] == "s1"
    assert W2.read_sequence(tmp_path / "ob")["rechecks"]["s1"]["sha256"] == doc["sha256"]
    seq.ensure_recheck("s1")                                                    # resume: re-verified, not re-run
    assert path in seq.run_file_paths()


@pytest.mark.parametrize("rows", [(lambda k: 0, lambda k: 0), (lambda k: 1, lambda k: 1)], ids=["all-fail", "all-pass"])
def test_an_unrealisable_recheck_stops_with_rc_5_until_acked(tmp_path, rows):
    seq = _seq(tmp_path, _pair_roots(tmp_path, *rows))
    with pytest.raises(W2.Stop) as stop:
        seq.ensure_recheck("s1")
    assert stop.value.rc == 5
    doc = json.loads((tmp_path / "ob" / "run" / "recheck-s1.json").read_text())
    assert doc["recheck"]["inside"] is False and doc["recheck"]["observed_unrealisable"] is True
    with pytest.raises(W2.Stop) as again:                                       # a wrong ack still stops
        _seq(tmp_path, seq.ops.roots, ack="0" * 64).ensure_recheck("s1")
    assert again.value.rc == 5
    acked = _seq(tmp_path, seq.ops.roots, ack=doc["sha256"])
    acked.ensure_recheck("s1")
    rec = W2.read_sequence(tmp_path / "ob")["rechecks"]["s1"]
    assert rec["ack"]["sha256"] == doc["sha256"] and rec["ack"]["at"]


def test_the_second_recheck_never_stops(tmp_path):
    ids1, ids2 = _ids("s1"), _ids("s2")
    roots = {}
    for arm in ("n16", "x"):
        roots[f"tg2-m76-{arm}-s1.a1"] = _leg(tmp_path / arm / "1", "s1", [dict(id=i, passed=False, converged=True) for i in ids1])
        roots[f"tg2-m76-{arm}-s2.a1"] = _leg(tmp_path / arm / "2", "s2", [dict(id=i, passed=False, converged=True) for i in ids2])
    seq = _seq(tmp_path, roots)
    for arm in ("n16", "x"):
        seq.seq["legs"].append(dict(leg=f"tg2-m76-{arm}-s2", attempt=1, state="VALID"))
        seq.seq["harvested"].append(dict(attempt=f"tg2-m76-{arm}-s2.a1", harvest_sha256="h"))
    seq.ensure_recheck("s2")
    doc = json.loads((tmp_path / "ob" / "run" / "recheck-s2.json").read_text())
    assert doc["recheck"]["inside"] is False and doc["sessions"] == ["s1", "s2"]


def _no_recheck(monkeypatch):
    from bench import m76_sim

    def boom(*a, **k):
        raise AssertionError("the re-check was re-run")
    monkeypatch.setattr(m76_sim, "recheck", boom)


INSIDE = (lambda k: k % 2, lambda k: (k % 2) ^ (k < 8))


def test_l3_a_record_without_its_sealed_file_stops_and_never_reruns(tmp_path, monkeypatch):
    roots = _pair_roots(tmp_path, *INSIDE)
    _seq(tmp_path, roots).ensure_recheck("s1")
    path = tmp_path / "ob" / "run" / "recheck-s1.json"
    rec = W2.read_sequence(tmp_path / "ob")["rechecks"]["s1"]
    path.unlink()
    _no_recheck(monkeypatch)
    with pytest.raises(W2.Stop) as stop:
        _seq(tmp_path, roots).ensure_recheck("s1")
    assert stop.value.rc == 1 and "recheck-s1.json" in str(stop.value)
    assert not path.exists() and W2.read_sequence(tmp_path / "ob")["rechecks"]["s1"] == rec


def _crash_between_seal_and_save(tmp_path, rows):
    roots = _pair_roots(tmp_path, *rows)
    try:
        _seq(tmp_path, roots).ensure_recheck("s1")
    except W2.Stop:
        pass
    doc = W2.read_sequence(tmp_path / "ob")
    rec = doc["rechecks"].pop("s1")
    W2.write_sequence(tmp_path / "ob", doc)
    return roots, rec


def test_l3_a_sealed_file_without_its_record_is_reverified_and_recorded(tmp_path, monkeypatch):
    roots, rec = _crash_between_seal_and_save(tmp_path, INSIDE)
    _no_recheck(monkeypatch)
    seq = _seq(tmp_path, roots)
    seq.ensure_recheck("s1")
    got = W2.read_sequence(tmp_path / "ob")["rechecks"]["s1"]
    assert {k: got[k] for k in ("sha256", "path", "inside", "operator_review")} == \
        {k: rec[k] for k in ("sha256", "path", "inside", "operator_review")}
    assert "recorded from the sealed file" in (tmp_path / "ob" / W2.LOG_FILE).read_text()


def test_l3_an_outside_sealed_file_without_its_record_still_stops_until_acked(tmp_path, monkeypatch):
    roots, rec = _crash_between_seal_and_save(tmp_path, (lambda k: 0, lambda k: 0))
    _no_recheck(monkeypatch)
    with pytest.raises(W2.Stop) as stop:
        _seq(tmp_path, roots).ensure_recheck("s1")
    assert stop.value.rc == 5
    _seq(tmp_path, roots, ack=rec["sha256"]).ensure_recheck("s1")
    assert W2.read_sequence(tmp_path / "ob")["rechecks"]["s1"]["ack"]["sha256"] == rec["sha256"]


def test_l3_a_changed_file_without_its_record_stops(tmp_path, monkeypatch):
    roots, _ = _crash_between_seal_and_save(tmp_path, INSIDE)
    path = tmp_path / "ob" / "run" / "recheck-s1.json"
    doc = json.loads(path.read_text())
    doc["recheck"]["inside"] = False
    path.write_text(json.dumps(doc))
    _no_recheck(monkeypatch)
    with pytest.raises(W2.Stop) as stop:
        _seq(tmp_path, roots).ensure_recheck("s1")
    assert stop.value.rc == 1
    assert "s1" not in W2.read_sequence(tmp_path / "ob").get("rechecks", {})


@pytest.mark.parametrize("arm", ["n16", "x"])
def test_v1_a_recorded_recheck_of_another_selection_stops_on_resume(tmp_path, monkeypatch, arm):
    roots = _pair_roots(tmp_path, *INSIDE)
    _seq(tmp_path, roots).ensure_recheck("s1")
    rec = W2.read_sequence(tmp_path / "ob")["rechecks"]["s1"]
    _no_recheck(monkeypatch)
    seq = _seq(tmp_path, roots)
    seq.seq["legs"].append(dict(leg=f"tg2-m76-{arm}-s1", attempt=2, state="VALID"))      # an s1 rerun selects attempt 2
    seq.seq["harvested"].append(dict(attempt=f"tg2-m76-{arm}-s1.a2", harvest_sha256="h"))
    with pytest.raises(W2.Stop) as stop:
        seq.ensure_recheck("s1")
    assert stop.value.rc == 1 and "attempts" in str(stop.value)
    assert W2.read_sequence(tmp_path / "ob")["rechecks"]["s1"] == rec


def test_v1_a_recorded_recheck_of_the_current_selection_resumes(tmp_path, monkeypatch):
    roots = _pair_roots(tmp_path, *INSIDE)
    _seq(tmp_path, roots).ensure_recheck("s1")
    _no_recheck(monkeypatch)
    _seq(tmp_path, roots).ensure_recheck("s1")


# ----------------------------------------------------------------------------------------------- L5 / L6: the tg2 v8 and pair contract
@pytest.mark.parametrize("flag", ["--r1-off", "--r1-on"])
def test_l5_the_tg2_v8_refuses_the_r1_flags(wd, flag, capsys):
    rc, v8, _ = _round_trip(wd, extra_v8=[flag, str(wd / "r1")])
    assert rc == 2 and not v8.exists() and "R1" in capsys.readouterr().err


@pytest.mark.parametrize("pair", ["n16,v", "x,v"])
def test_l6_the_tg2_freeze_refuses_a_pair_other_than_n16_x(wd, pair, capsys):
    ref, test = pair.split(",")
    wts = {arm: wd / f"wt-{arm}" for arm in (ref, test)}
    kv = ["--lever", "kv", "--corpus", "tg2", "--pair", pair, *[x for arm in (ref, test) for x in ("--arm-worktree", f"{arm}={wts[arm]}")]]
    out = wd / "run" / "m.json"
    assert _freeze(["rehearsal", *kv, "--out-root", str(wd / "m76/p426/rehearsal.tg2/r"), "--out", str(out),
                    "--frozen-prompt-date", DATE], FreezeOps()) == 2
    assert _freeze(["v8", *kv, "--rehearsal-manifest", str(out), "--r2", "r2", "--r3", "r3", "--positives", "p", "--out",
                    str(out)], FreezeOps()) == 2
    assert not out.exists() and "n16" in capsys.readouterr().err


@pytest.mark.parametrize("pair", [("n16", "v"), ("x", "v")])
def test_l6_the_tg2_leg_table_is_n16_x_only(pair):
    with pytest.raises(ValueError, match="n16"):
        W2.kv_tg2_legs(*pair)


@pytest.mark.parametrize("arm", ["x", "v"])
def test_l6_the_positives_run_on_n16_only(wd, arm):
    out = wd / "run" / "positives.json"
    rc = W2.main(["positives", "--corpus", "tg2", "--lever", "kv", "--arm-worktree", f"{arm}={wd / 'wt'}", "--out", str(out),
                  "--frozen-prompt-date", DATE], ops=PosOps())
    assert rc == 2 and not out.exists()


def test_l6_the_tg2_sequencer_refuses_a_pair_other_than_n16_x(wd):
    for pair in ("n16,v", "x,v"):
        ref, test = pair.split(",")
        rc = W2.main(["run", "--corpus", "tg2", "--lever", "kv", "--pair", pair, "--arm-worktree", f"{ref}={wd}",
                      "--arm-worktree", f"{test}={wd}", "--out-base", str(wd / "m76/p426/wave2.tg2/ob"), "--record-dir",
                      str(wd / "run")], ops=SimpleNamespace(wd=wd))
        assert rc == 2


def test_l6_the_tg2_chain_refuses_arm_v_and_a_record_of_another_pair(wd):
    T = _T()
    argv = ["--leg", "s1", "--p426", "--models", ENTRY, "--predictor", "mtp", "--out-root", str(wd / "o/tg2-m76-v-s1.a1"),
            "--campaign-core", "c", "--frozen-prompt-date", DATE, "--probe-code-sha", "a" * 64, "--policy-sha", "b" * 64,
            "--frozen-record", str(wd / "r.json"), "--lever", "kv", "--kv-arm", "v"]
    with pytest.raises((SystemExit, T.Refused)):
        T.parse_args(argv)
    for arms in (["n16", "v"], ["x", "n16"]):
        path = wd / "-".join(arms) / "v8_base.json"
        ph.write_exclusive(path, dict(kind=fz.KIND_V8, lever="kv", arms=arms, corpus="tg2"))
        a = T.parse_args(["--leg", "pilot"] + argv[2:-1] + ["n16"])
        a.frozen_record = str(path)
        with pytest.raises(T.Refused, match="n16"):
            T.check_frozen_record(a)
    ok = wd / "ok" / "v8_base.json"
    ph.write_exclusive(ok, dict(kind=fz.KIND_V8, lever="kv", arms=["n16", "x"], corpus="tg2"))
    a.frozen_record = str(ok)
    assert T.check_frozen_record(a)["base"]["arms"] == ["n16", "x"]


# ----------------------------------------------------------------------------------------------- harvest rules (H5)
def test_every_file_of_the_recorded_trees_is_classified():
    seen = 0
    for tree in sorted(p for p in FIX.glob("*/*") if p.is_dir()):
        for path in sorted(p for p in tree.rglob("*") if p.is_file()):
            rel = path.relative_to(tree).as_posix()
            if rel == "result.json":                                 # the recorder's own summary, not a harvested file
                continue
            kind = "run" if rel.startswith("grading-private/") else "evidence"
            got = H.classify(kind, rel)
            assert got is not None, f"{tree.name}: {rel} has no harvest rule"
            assert got[0] == "evidence", rel                         # raw grader output: evidence, never main
            seen += 1
    assert seen > 1000


def test_the_grade_sequence_rules_are_bounded_by_the_directory():
    assert H.classify("evidence", "rust__say.grades/seq-0001/cl-holder-n.err") == ("evidence", None)
    assert H.classify("evidence", "rust__say.grades/seq-0001/compile.inspect.err") == ("evidence", None)
    assert H.classify("evidence", "rust__say.grades/seq-0001/execute.stdout") == ("evidence", None)
    assert H.classify("run", "grading-private/.tg2-registry/mlxbench-tg2-0a.json") == ("evidence", None)
    assert H.classify("run", "grading-private/other.json") == ("main", None)
    for refused in ("rust__say.grades/execute.stdout", "rust__say.grades/seq-0001/sub/x.out", "rust__say/seq-0001/x.out",
                    "x.out", "rust__say.grades/seq-1/x.inspect", "rust__say.grades/seq-0001/x.bin",
                    "go__x.grades/seq-0001/python.stderr", "x.grades/seq-0001/other.stderr",          # P586 / P587 unchanged
                    "python__x.grades/seq-0001/compile.out"):
        assert H.classify("evidence", refused) is None, refused
