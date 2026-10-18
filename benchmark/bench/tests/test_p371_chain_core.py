"""P371 phase 3a (plan 3.1 `chain_core`, 4 A8 / A9 / A12, 5 lifecycle closure R15, C179): the tg1 chain on the shared chain
core: ChainConfig in chain.json, disjoint leg-attempt invocations with immutable rows files, `chain.json.progress`
(`bench.chain_rows`), load archive / quarantine, chain-side web evidence, the entry's lifecycle closure, the campaign
core. End to end against the fake probe and the fake ChainOps of `test_c147_chain_runner`."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from bench import chain_ops as co
from bench import chain_rows as cr
from bench import web_evidence as we
from bench.tests.test_c147_chain_runner import (  # noqa: F401  (fixtures: env)
    CHAIN, FP, PICK1, PICK2, PILOT, R, REPO, TIMERS, arg, chain_json, env, invocations, log_has, run)
from bench.tests.test_p371_web_evidence import DOC


def sha_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(env, path):
    return Path(path).relative_to(env["out"]).as_posix()


# ---------------------------------------------------------------- ChainConfig in chain.json
def test_the_tg1_chain_config_is_serialized_into_chain_json_and_its_sha_is_a_lifecycle_member(env):
    assert run(env, CHAIN) == 0
    cj = chain_json(env)
    cfg = R.tg1_config(R.parse_args(CHAIN))
    assert cj["chain_config"] == cfg.as_dict() and cj["lifecycle"]["chain_config"] == cfg.sha256()
    assert (cfg.transport_policy, cfg.resume_policy, cfg.predictor) == ("abort_restart", "restart_load", "off")
    assert cfg.schedule["builder"] == "tg1" and cfg.arm_switch_ops == () and cfg.contract_artifacts == ()
    assert cfg.arms[0].probe == "benchmark/run_tg1_probe.py" and cfg.arms[0].label == co.SCAFFOLD


def test_pilot_chain_and_smoke_share_one_chain_config_and_the_predictor_changes_it():
    base = R.tg1_config(R.parse_args(CHAIN))
    assert R.tg1_config(R.parse_args(PILOT)).sha256() == base.sha256() == R.tg1_config(R.parse_args(CHAIN + ["--smoke"])).sha256()
    assert R.tg1_config(R.parse_args(CHAIN + ["--predictor", "mtp"])).sha256() != base.sha256()


# ---------------------------------------------------------------- disjoint invocations (P376, plan 4 A8)
def test_pilot_and_full_are_disjoint_invocations_each_with_its_own_immutable_rows_file(env):
    assert run(env, CHAIN) == 0
    inv = [i["argv"] for i in invocations(env)]
    assert len(inv) == 6
    stem = f"{PICK1}.s1.opencode_python"
    pilot, full, go = inv[0], inv[1], inv[2]
    assert arg(pilot, "--out") == str(env["out"] / "s1" / f"{stem}.L0.pilot.a1.jsonl")
    assert arg(full, "--out") == str(env["out"] / "s1" / f"{stem}.L0.full.a2.jsonl")
    assert arg(go, "--out") == str(env["out"] / "s1" / f"{PICK1}.s1.opencode_go.L1.full.a1.jsonl")
    done = set(arg(pilot, "--items").split(","))
    rest = arg(full, "--items").split(",")
    assert len(done) == 5 and rest and not done & set(rest) and done | set(rest) == {f"p{i}" for i in range(1, 7)}
    assert arg(full, "--expect-items") == ",".join("python/" + n for n in rest) and "--limit" not in full
    assert arg(pilot, "--limit") == "5" and arg(go, "--items").split(",") == [f"g{i}" for i in range(1, 7)]
    assert [(arg(x, "--attempt"), arg(x, "--attempt-rerun-index")) for x in (pilot, full, go)] == [
        ("1", "0"), ("2", "0"), ("1", "0")]
    assert not list((env["out"] / "s1").glob("*opencode_python.jsonl"))           # no legacy shared rows file
    ids = []
    for f in sorted((env["out"] / "s1").glob(f"{stem}.L0.*.jsonl")):
        ids += [json.loads(x)["id"] for x in f.read_text().splitlines()]
    assert sorted(ids) == [f"python/p{i}" for i in range(1, 7)]
    for name in (f"{stem}.L0.pilot.a1", f"{stem}.L0.full.a2"):                    # attempt files follow the leg-attempt name
        for ext in (".json", ".log", ".ACK", ".manifest.json"):
            assert (env["out"] / "s1" / (name + ext)).exists(), name + ext


def test_the_probe_is_never_asked_to_resume_a_rows_file(env):
    assert run(env, CHAIN) == 0
    outs = [arg(i["argv"], "--out") for i in invocations(env)]
    assert len(set(outs)) == len(outs) == 6


def test_progress_records_every_invocation_with_the_sha_recorded_after_validation(env):
    assert run(env, CHAIN) == 0
    cj = chain_json(env)
    prog = cj["progress"]
    assert [(i["phase"], i["status"], i["load_gen"]) for i in prog["invocations"]] == [
        ("pilot", "validated", 0), ("full", "validated", 0), ("full", "validated", 0)] * 2
    for rec in prog["invocations"]:
        assert set(cr.INV_KEYS) <= set(rec) and rec["accepted_slots"] == rec["expected_slots"]
        assert rec["sha256"] == sha_of(env["out"] / rec["file"]) and (env["out"] / rec["manifest"]).is_file()
        assert rec["file"].startswith("s1/") and rec["file"].endswith(".jsonl")
    loads = prog["loads"]
    assert [(l["status"], l["load_gen"], len(l["workers"])) for l in loads] == [("done", 0, 1), ("done", 0, 1)]
    assert loads[0]["workers"][0]["n"] == 0 and loads[0]["workers"][0]["pid"] == 1001
    table = cr.load_slots(cj, env["out"])
    assert len(table.scored) == 24 and not table.running and not table.pending_reruns and not table.blocked
    assert all(s.source == "row" and s.disposition == "accepted" for s in table.scored.values())


def test_the_progress_inventory_is_on_disk_before_the_next_probe_starts(env):
    seen = []
    ops = env["ops"]
    orig = ops.power_ok

    def spy():
        p = env["out"] / "chain.json"
        if p.exists():
            doc = json.loads(p.read_text())
            seen.append([i["status"] for i in doc.get("progress", {}).get("invocations", [])])
        return orig()
    ops.power_ok = spy
    assert run(env, CHAIN) == 0
    assert any(s[:2] == ["validated", "validated"] for s in seen)                    # earlier invocations were persisted
    assert seen[0] == [] or "running" not in seen[0]


def test_a_running_invocation_is_persisted_before_its_probe_is_spawned(env):
    marks = []
    ops = env["ops"]
    orig = ops.env_base

    def spy():
        p = env["out"] / "chain.json"
        if (env["ops"].state / "invocations.jsonl").exists() or True:
            if p.exists():
                marks.append((len(invocations(env)), [i["status"] for i in json.loads(p.read_text()).get("progress", {}).get("invocations", [])]))
        return orig()
    ops.env_base = spy
    assert run(env, PILOT) == 0
    assert any(n == 0 and s == ["running"] for n, s in marks)                        # recorded `running` pre-spawn


def test_a_full_invocation_is_never_a_rerun_of_the_pilot_rows(env):
    assert run(env, CHAIN) == 0
    prog = chain_json(env)["progress"]
    pilot, full = prog["invocations"][0], prog["invocations"][1]
    assert not set(pilot["expected_slots"]) & set(full["expected_slots"])
    assert len(pilot["expected_slots"]) == 5 and len(full["expected_slots"]) == 1


def test_smoke_shapes_follow_the_same_disjoint_rule(env):
    env["out"] = env["wd"] / "c147-smoke"
    assert run(env, CHAIN + ["--smoke"]) == 0
    prog = chain_json(env)["progress"]
    first = [(i["phase"], len(i["expected_slots"])) for i in prog["invocations"][:3]]
    assert first == [("pilot", 1), ("full", 1), ("full", 2)]


# ---------------------------------------------------------------- restart_load: archive manifest first, archived records
PLAN_RESTART = ["normal", "normal", "hang_in_item", "normal"]


def test_restart_load_archives_with_a_sha_manifest_recorded_before_any_file_moves(env, monkeypatch):
    from bench import chain_core
    first = []
    real = shutil.move

    def spy(src, dst):
        if not first:
            doc = json.loads((env["out"] / "chain.json").read_text())
            first.append((doc["progress"]["loads"][0].get("archives"), None))
        return real(src, dst)
    monkeypatch.setattr(chain_core.shutil, "move", spy)
    assert run(env, CHAIN, plan=PLAN_RESTART) == 0
    archives, _ = first[0]
    assert archives and archives[-1]["files"], "the sha manifest must be in chain.json before the first move"
    cj = chain_json(env)
    arch = Path(cj["restarts"][0]["archive"])
    listed = archives[-1]["files"]
    assert set(listed) == {f.name for f in arch.iterdir()}
    for name, sha in listed.items():
        assert sha_of(arch / name) == sha


def test_restart_load_marks_the_loads_records_archived_and_scores_only_the_rerun(env):
    assert run(env, CHAIN, plan=PLAN_RESTART) == 0
    cj = chain_json(env)
    prog = cj["progress"]
    old = [i for i in prog["invocations"] if i["load_gen"] == 0 and i["leg_key"][0] == 0]
    assert old and all(i["status"] == "archived" for i in old)
    assert all("incomplete" in i["file"] for i in old)                               # paths rewritten to the archive
    assert any(i["sha256"] for i in old)                                             # validated shas kept
    assert prog["loads"][0]["load_gen"] == 1 and prog["loads"][0]["status"] == "done"
    new = [i for i in prog["invocations"] if i["load_gen"] == 1]
    assert [i["phase"] for i in new] == ["pilot", "full", "full"] and all(i["status"] == "validated" for i in new)
    table = cr.load_slots(cj, env["out"])
    assert len(table.scored) == 24
    # the archived (moved) pilot is not scored and its moved file is not sha-rechecked; the rerun's is
    arch_files = [env["out"] / i["file"] for i in old if (env["out"] / i["file"]).exists()]
    for f in arch_files:
        f.write_text("tampered\n")
    assert len(cr.load_slots(cj, env["out"]).scored) == 24
    rerun = env["out"] / new[0]["file"]
    rerun.write_text(rerun.read_text() + "\n")
    with pytest.raises(cr.ChainRowsError):
        cr.load_slots(cj, env["out"])


def test_the_restart_reruns_every_slot_of_the_load_from_the_first_leg(env):
    assert run(env, CHAIN, plan=PLAN_RESTART) == 0
    inv = [i["argv"] for i in invocations(env)]
    assert len(inv) == 4 + 2 + 3 and arg(inv[3], "--items") == arg(inv[0], "--items")
    assert arg(inv[3], "--out") != arg(inv[0], "--out") and "L0.pilot.a3" in arg(inv[3], "--out")


def test_a_never_validated_invocation_is_quarantined_with_a_sha_manifest_before_the_load_reruns(env):
    assert run(env, PILOT) == 0
    path = env["out"] / "chain.json"
    doc = json.loads(path.read_text())
    inv = doc["progress"]["invocations"][0]
    original = {Path(inv["file"]).name: sha_of(env["out"] / inv["file"])}
    inv.update(status="running", sha256=None, accepted_slots=[])
    doc["progress"]["loads"][0]["status"] = "running"
    path.write_text(json.dumps(doc))
    assert run(env, PILOT) == 0                                                      # resume = restart_load
    cj = chain_json(env)
    quarantined = [i for i in cj["progress"]["invocations"] if i["status"] == "quarantined"]
    assert len(quarantined) == 1 and quarantined[0]["file"].split("/")[0] == "quarantine"
    qdir = (env["out"] / quarantined[0]["file"]).parent
    manifest = json.loads((qdir / "MANIFEST.json").read_text())
    assert manifest["files"][Path(inv["file"]).name] == original[Path(inv["file"]).name]
    assert len(cr.load_slots(cj, env["out"]).scored) == 5 and cj["progress"]["loads"][0]["load_gen"] == 1


def test_a_finished_load_is_not_run_again_on_resume(env):
    assert run(env, PILOT) == 0
    before = len(invocations(env))
    assert run(env, PILOT) == 0
    assert len(invocations(env)) == before and len(env["ops"].names("load")) == 1


def test_a_pilot_then_the_chain_in_one_out_root_keep_their_loads_apart(env):
    """The operator flow (drive_chain.sh pilot, then chain ...) shares one chain.json: the pilot's load is a different load
    from the chain's first block even though both are the first of their schedule."""
    assert run(env, PILOT) == 0
    assert run(env, CHAIN) == 0
    cj = chain_json(env)
    loads = cj["progress"]["loads"]
    assert [(l["load"], l["key"], l["status"], l["load_gen"]) for l in loads] == [
        (0, f"pilot|{PICK1}", "done", 0), (1, f"s1|{PICK1}", "done", 0), (2, f"s1|{PICK2}", "done", 0)]
    assert all(i["status"] == "validated" for i in cj["progress"]["invocations"]) and len(cj["progress"]["invocations"]) == 7
    assert len(cr.load_slots(cj, env["out"]).scored) == 5 + 24
    assert not (env["out"] / "pilot" / "incomplete").exists()


def test_the_campaign_core_specs_follow_the_probe_identity_recipe_and_the_entry_closure():
    from bench import campaign_core as cc
    from bench import identity_closure as ic
    from bench import tg1_runner
    assert tuple(R.CORE_SPECS["probe_data"]) == tuple(tg1_runner.GENERATION_DATA)
    now = cc.closure_shas(REPO, **R.CORE_SPECS)
    assert now["probe_closure_sha256"] == ic.closure_sha256("benchmark/run_tg1_probe.py", REPO, data=tg1_runner.GENERATION_DATA)
    assert {"benchmark/bench/chain_core.py", "benchmark/bench/campaign_core.py"} <= set(
        cc.members(REPO, R.CORE_SPECS["chain_entry"], R.CORE_SPECS["chain_data"]))


def test_an_unregistered_rows_file_in_the_out_root_is_refused_by_the_loader(env):
    assert run(env, PILOT) == 0
    (env["out"] / "pilot" / f"{PICK1}.pilot.opencode_python.L0.pilot.a9.jsonl").write_text("")
    with pytest.raises(cr.ChainRowsError, match="unregistered"):
        cr.load_slots(chain_json(env), env["out"])


# ---------------------------------------------------------------- chain-side web evidence (plan 4 A12)
def test_web_evidence_is_extracted_per_row_with_the_sha_recorded_per_slot_attempt(env):
    assert run(env, PILOT, extra_env={"FAKE_EXPORT_DOC": json.dumps(DOC)}) == 0
    cj = chain_json(env)
    atts = cj["progress"]["slot_attempts"]
    assert len(atts) == 5 and all(a["disposition"] == "accepted" and a["rerun_index"] == 0 for a in atts)
    for a in atts:
        w = a["web_evidence"]
        assert w["count"] == 4 and w["path"].endswith(".web.jsonl")
        path = Path(w["path"].replace("$STACK_WORKDIR", str(env["wd"])))
        assert path.name == "export.web.jsonl" and sha_of(path) == w["sha256"]
        assert [json.loads(x)["tool"] for x in path.read_text().splitlines()][:2] == ["websearch", "webfetch"]
    assert len(cr.load_slots(cj, env["out"]).scored) == 5


def test_web_evidence_of_an_abandoned_invocations_partial_rows_is_extracted_before_the_load_is_archived(env):
    """A12: every attempt with a stored transcript (pass, fail, cut, incident, cancel ...) leaves a hashed evidence file."""
    plan = ["abort_after_n", "normal"]
    assert run(env, ["chain", "reload", "--probe-code-sha", "9" * 64], plan=plan,
               extra_env={"FAKE_N": "2", "FAKE_EXPORT_DOC": json.dumps(DOC)}) == 0
    recs = [i for i in chain_json(env)["progress"]["invocations"] if i["load_gen"] == 0]
    assert len(recs) == 1 and recs[0]["status"] == "archived"
    w = recs[0]["web_evidence"]
    assert len(w) == 2 and all(v["count"] == 4 and v["sha256"] for v in w.values())
    for slot, v in w.items():
        path = Path(v["path"].replace("$STACK_WORKDIR", str(env["wd"])))
        assert path.name == "export.web.jsonl" and sha_of(path) == v["sha256"] and slot.startswith("tg1|oc|")


def test_an_unreadable_export_leaves_an_unavailable_record_never_a_no_contact_claim(env):
    assert run(env, PILOT, extra_env={"FAKE_EXPORT_RAW": "not json at all"}) == 0
    for a in chain_json(env)["progress"]["slot_attempts"]:
        assert a["web_evidence"] == {"web_evidence": "unavailable", "reason": "transcript unreadable (export failed or malformed)"}


def test_a_row_without_a_stored_transcript_is_unavailable(env, tmp_path):
    from bench import chain_core
    ch = chain_core.Chain.__new__(chain_core.Chain)
    ch.wd = env["wd"]
    assert ch.web_record({"id": "python/x"}, we.OPENCODE_RULES, tmp_path / "x.web.jsonl") == {
        "web_evidence": "unavailable", "reason": "no transcript"}
    assert not (tmp_path / "x.web.jsonl").exists()


def test_a_transcript_whose_sha_differs_aborts_the_chain(env, monkeypatch):
    def boom(*a, **k):
        raise we.TranscriptShaMismatch("transcript export.json differs from its recorded sha256")
    monkeypatch.setattr(we, "extract", boom)
    assert run(env, PILOT) == 2 and log_has(env, "differs from its recorded sha256")


# ---------------------------------------------------------------- lifecycle closure (plan 5, R15)
def lifecycle_copy(tmp_path):
    out = {}
    for name, src in R.lifecycle_files(REPO).items():
        dst = Path(tmp_path) / "lifecycle" / Path(src).relative_to(REPO)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(Path(src).read_bytes())
        out[name] = dst
    return out


def touch(path):
    path.write_bytes(path.read_bytes() + b"\n# drift\n")


MEMBERS = ["runner", "chain_ops", "gate", "launcher", "launch_tg1", "benchmark/bench/chain_core.py",
           "benchmark/bench/chain_rows.py", "benchmark/bench/schedules.py", "benchmark/bench/run_config.py",
           "benchmark/bench/web_evidence.py", "benchmark/bench/arm_specs.py", "benchmark/bench/campaign_core.py"]


def test_the_entrys_import_closure_the_gate_and_the_launchers_are_the_frozen_lifecycle(env):
    files = lifecycle_copy(env["wd"])
    assert set(MEMBERS) <= set(files)
    assert run(env, CHAIN, lifecycle=files) == 0
    lc = chain_json(env)["lifecycle"]
    assert set(lc) == set(files) | {"chain_config"}
    assert all(lc[n] == sha_of(p) for n, p in files.items())
    assert lc["runner"] == sha_of(REPO / "benchmark/chains/c147/run_tg1_chain.py")
    assert chain_json(env)["sha256"]["runner"] == lc["runner"] and chain_json(env)["sha256"]["launch_tg1"] == lc["launch_tg1"]


@pytest.mark.parametrize("name", MEMBERS)
def test_drift_of_any_member_aborts_before_the_next_launch(env, name):
    files = lifecycle_copy(env["wd"])
    ops = env["ops"]
    original = ops.a4_gate

    def gate(model, tag):
        if model == PICK2:
            touch(files[name])
        return original(model, tag)
    ops.a4_gate = gate
    assert run(env, CHAIN, lifecycle=files) == 2
    assert log_has(env, "lifecycle drift") and any(name in ln for ln in env["lines"] if "lifecycle drift" in ln)
    assert len(invocations(env)) == 3


def test_a_changed_chain_config_aborts_a_resume_and_leaves_the_record_frozen(env, monkeypatch):
    assert run(env, PILOT) == 0
    before = (env["out"] / "chain.json").read_bytes()
    real = R.tg1_config

    def other(a):
        import dataclasses
        return dataclasses.replace(real(a), out_root_family="elsewhere")
    monkeypatch.setattr(R, "tg1_config", other)
    assert run(env, CHAIN) == 2
    assert log_has(env, "chain_config") and (env["out"] / "chain.json").read_bytes() == before


def test_drift_at_exit_is_an_abort_for_a_closure_member_too(env):
    files = lifecycle_copy(env["wd"])
    ops = env["ops"]
    ops.on_unload = lambda: touch(files["benchmark/bench/chain_core.py"]) if len(ops.names("unload")) >= 2 else None
    assert run(env, CHAIN, lifecycle=files) == 2 and log_has(env, "lifecycle drift")


# ---------------------------------------------------------------- C179 campaign core
class FakeCampaign:
    """`at_ref` / `current` / `require_equal` of `campaign_core.Campaign`, with shas the test controls."""

    def __init__(self, at=None, now=None):
        from bench import campaign_core as cc
        self.cc = cc
        self.now = now or {"probe_closure_sha256": "a" * 64, "chain_closure_sha256": "b" * 64}
        self.at = at or dict(tag="campaign-1", commit="c" * 40, **self.now)
        self.refs = []

    def at_ref(self, ref):
        self.refs.append(ref)
        if ref != self.at["tag"]:
            raise self.cc.CampaignError(f"--campaign-core {ref!r} does not resolve to a commit in this repository")
        return dict(self.at)

    def current(self):
        return dict(self.now)

    def require_equal(self, recorded, now):
        self.cc.require_equal(recorded, now)


def run_campaign(env, argv, campaign, **kw):
    from bench.tests import test_c147_chain_runner as T
    return T.run(env, list(argv), campaign=campaign, **kw)


def test_a_matching_campaign_core_is_recorded_and_the_chain_runs(env):
    cam = FakeCampaign()
    assert run_campaign(env, CHAIN + ["--campaign-core", "campaign-1"], cam) == 0
    assert chain_json(env)["artifacts"]["campaign_core"] == cam.at and cam.refs == ["campaign-1"]


def test_without_the_flag_the_campaign_core_is_recorded_as_null(env):
    assert run(env, PILOT) == 0
    assert chain_json(env)["artifacts"] == {"campaign_core": None}


@pytest.mark.parametrize("which", ["probe_closure_sha256", "chain_closure_sha256"])
def test_a_core_file_changed_after_the_tag_refuses_before_anything_is_written(env, which):
    base = dict(tag="campaign-1", commit="c" * 40, probe_closure_sha256="a" * 64, chain_closure_sha256="b" * 64)
    cam = FakeCampaign(at={**base, which: "0" * 64})
    assert run_campaign(env, CHAIN + ["--campaign-core", "campaign-1"], cam) == 2
    assert log_has(env, "campaign core drift") and invocations(env) == [] and not (env["out"] / "chain.json").exists()
    assert not env["ops"].names("start_router")


def test_an_unresolvable_campaign_ref_refuses(env):
    assert run_campaign(env, CHAIN + ["--campaign-core", "missing"], FakeCampaign()) == 2
    assert log_has(env, "does not resolve") and invocations(env) == []


def test_campaign_core_drift_mid_chain_aborts_rc_2_before_the_next_launch(env):
    cam = FakeCampaign()
    ops = env["ops"]
    original = ops.a4_gate

    def gate(model, tag):
        if model == PICK2:
            cam.now = dict(cam.now, chain_closure_sha256="9" * 64)
        return original(model, tag)
    ops.a4_gate = gate
    assert run_campaign(env, CHAIN + ["--campaign-core", "campaign-1"], cam) == 2
    assert log_has(env, "campaign core drift") and len(invocations(env)) == 3


def test_campaign_core_drift_at_exit_aborts(env):
    cam = FakeCampaign()
    ops = env["ops"]
    ops.on_unload = lambda: cam.__dict__.update(now=dict(cam.now, probe_closure_sha256="8" * 64)) \
        if len(ops.names("unload")) >= 2 else None
    assert run_campaign(env, CHAIN + ["--campaign-core", "campaign-1"], cam) == 2
    assert log_has(env, "campaign core drift")


def test_a_resume_keeps_enforcing_the_recorded_campaign_core_without_the_flag(env):
    cam = FakeCampaign()
    assert run_campaign(env, PILOT + ["--campaign-core", "campaign-1"], cam) == 0
    cam.now = dict(cam.now, probe_closure_sha256="7" * 64)
    launched = len(invocations(env))
    assert run_campaign(env, CHAIN, cam) == 2
    assert log_has(env, "campaign core drift") and len(invocations(env)) == launched


def test_a_resume_with_a_different_campaign_ref_refuses(env):
    cam = FakeCampaign()
    assert run_campaign(env, PILOT + ["--campaign-core", "campaign-1"], cam) == 0
    other = FakeCampaign(at=dict(cam.at, tag="campaign-2"))
    assert run_campaign(env, CHAIN + ["--campaign-core", "campaign-2"], other) == 2
    assert log_has(env, "campaign")


def test_the_campaign_flag_is_parsed_and_validated():
    assert R.parse_args(CHAIN + ["--campaign-core", "v1"]).campaign_core == "v1"
    assert R.parse_args(CHAIN).campaign_core is None
    with pytest.raises(SystemExit):
        R.parse_args(CHAIN + ["--campaign-core", ""])


# ---------------------------------------------------------------- the fake probe contract (P371 phase 3a)
def test_the_fake_probe_refuses_an_existing_rows_file_and_takes_the_attempt_flags(tmp_path, monkeypatch):
    import subprocess
    import sys
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    out = tmp_path / "x.L0.pilot.a1.jsonl"
    cmd = [sys.executable, str(REPO / "benchmark/chains/c147/fake_probe.py"), "--model", PICK1, "--items", "a", "--lang",
           "python", "--seed-base", "1", "--out", str(out), "--scaffold", co.SCAFFOLD, "--expect-items", "python/a",
           "--a4-v2-receipt", "r", "--sampling-profile", "deployed", "--cancel-file", str(tmp_path / "c"),
           "--manifest-ack", str(tmp_path / "a"), "--frozen-prompt-date", "Mon Jan 05 2026", "--attempt", "2",
           "--attempt-rerun-index", "1"]
    out.write_text("")                                                   # a pre-existing rows file refuses (no resume)
    got = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert got.returncode == 2 and "REFUSED" in got.stdout and "already exists" in got.stdout
    out.unlink()
    (tmp_path / "a").write_text("")                                      # an ack file that exists refuses first
    got = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert got.returncode == 2 and "REFUSED" in got.stdout
