"""P426 B2 frozen tests, delivery 1d: every fixture of `b2_frozen_add_support` validated on the BASELINE (all pass there).
A record, like `test_b2_frozen_s0_support.py`; not part of the committed suite."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_support as S


def test_the_world_carries_the_section_16_5_seams_consistently(tmp_path, monkeypatch):
    env = A.world(tmp_path, monkeypatch, arm="on", busy=["4242 python -m bench.run_lcb --model other"], descendants={7})
    try:
        ops = env["ops"]
        ident = ops.load(S.MODEL)
        assert ops.expected_worker_argv(ops.overlay, S.MODEL) == ops.proc_argv(ident["pid"])
        assert all(re.match(r"^\d+ \S", ln) for ln in ops.busy_procs()) and ops.descendants(1) == {7}
        assert ops.create_time(ident["pid"]) == ident["create_time"] and ops.create_time(1) == 1.0
        e = ops.proc_environ(ident["pid"])
        assert e["HOME"] == A.SHARED_ENV["HOME"] and e["MLX_SERVE_CONFIG"] == ops.overlay
    finally:
        env["ops"].cancel()


def test_pair_argv_adds_the_pair_receipt_and_never_a_key(tmp_path, monkeypatch):
    env = A.world(tmp_path, monkeypatch)
    try:
        argv, r = A.pair_argv(env, ("pilot",), extra=["--pair-receipt", "/x/receipt.json"])
        assert r is None and "--hmac-fd" not in argv and A.arg(argv, "--pair-receipt") == "/x/receipt.json"
    finally:
        env["ops"].cancel()


def test_the_gate_json_builder_has_the_gates_shape():
    src = (S.REPO / "scripts/session_pinning_gate.py").read_text()
    assert 'res["A4_opencode"]' in src and 'res["A6_bare_anonymous"]' in src
    assert 'out.append({"cached": r["cached_tokens"], "prompt": r["prompt_tokens"],' in src
    doc = A.a4_gate_doc(S.a4_receipt([("ses_a", 0, 1)] * 4), [("anon:1", 0, 3100)] * 3)
    assert set(doc["A6_bare_anonymous"]["requests"][0]) == {"cached", "prompt", "session"}


def test_the_record_fixture_tree_verifies_and_detects_a_mutation(tmp_path):
    real = next(Path(S.REPO / ".venv-bench/lib").glob("python3*/site-packages/pyyaml-*.dist-info/RECORD"), None)
    line_re = re.compile(r"^[^,]+,sha256=[A-Za-z0-9_-]{43},\d+$")
    if real is not None:
        assert any(line_re.match(ln) for ln in real.read_text().splitlines())
    tree = A.site_tree(tmp_path / "sp", worktree=tmp_path / "WT")
    lines = (tree / "fakepkg-1.0.dist-info/RECORD").read_text().splitlines()
    assert all(line_re.match(ln) for ln in lines[:-1]) and lines[-1] == "fakepkg-1.0.dist-info/RECORD,,"
    assert A.verify_record(tree, "fakepkg-1.0.dist-info") == [] and A.verify_record(tree, "mlx_serve-0.3.0.dist-info") == []
    (tree / "fakepkg/core.py").write_bytes(b"def f():\n    return 3\n")
    assert A.verify_record(tree, "fakepkg-1.0.dist-info") == ["fakepkg/core.py"]
    du = json.loads((tree / "mlx_serve-0.3.0.dist-info/direct_url.json").read_text())
    assert set(du) == {"url", "dir_info"} and du["dir_info"] == {"editable": True} and du["url"].startswith("file://")


def test_the_real_chain_ops_fixture_spawns_nothing(tmp_path):
    ops = A.chain_ops(tmp_path)
    assert ops.busy_procs() == [] and callable(ops.start_state)
    assert Path(ops.registry) == Path(ops.overlay) != S.REPO / "main_models.yaml"     # P520: never the live registry


def test_the_sequencer_fakes_write_a_leg_in_the_frozen_formats(tmp_path):
    from bench import chain_rows as cr
    clock = A.Clock()
    ops = A.SeqOps(clock, script={"tg1-p426-on-pilot": {"dnf": 1, "runtime_s": 50.0}}, main_root=tmp_path / "main",
                   emails=("op@corp-mail.example",))
    # post-reveal 3d (§16.8): the sequencer seams
    assert ops.operator_emails() == ["op@corp-mail.example"]
    assert ops.harvest_path("tg1-p426-on-pilot.a1") == tmp_path / "main/benchmark/results/p426/wave2/tg1-p426-on-pilot.a1"
    assert ops.worktree_state(tmp_path / "stack-p426-off")["head"] == S.OFF_COMMIT
    assert set(ops.identity(tmp_path)) == {"probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256"}
    assert set(ops.historical_walls()) == {"w_python_s", "w_go_s", "max_request_elapsed_s"}
    root = tmp_path / "wd/p426/wave2/tg1-p426-on-pilot.a1"
    h = ops.launch(["pilot", "--p426", "--predictor", "mtp", "--out-root", str(root)], cwd="/", pass_fds=())
    wh = ops.launch(["python", "m1/bench_watch.py", "--chain-json", str(root / "chain.json"), "--driver-pid", str(h.pid),
                     "--out", str(root / "watch.jsonl")], cwd="/", pass_fds=())
    cj = json.loads((root / "chain.json").read_text())
    assert cj["status"] == "finished" and len(cj["p426_ledger"]) == 5 and len(cj["p426_dnf"]) == 1
    assert [x["kind"] for x in cj["p426_ledger"]] == ["dnf"] + ["row"] * 4
    rec = json.loads((root / "receipt.json").read_text())
    assert S.self_hashed(rec)["sha256"] == rec["sha256"] and rec["snapshots"]["drafter"]
    items = sorted((root / "items").glob("*.json"))
    assert any(p.name.endswith(".dnf.json") for p in items)
    assert all(p.name.startswith(A.slot_file(cr.slot_for(f"tg1-p426|oc|{S.MODEL}|pilot|python", "python/p1"))[:20]) for p in items)
    watch = [json.loads(x) for x in (root / "watch.jsonl").read_text().splitlines()]
    assert "exit_state" in watch[-1]
    assert ops.alive(h.pid, h.start) and ops.alive(wh.pid, wh.start)
    assert ops.wait(h) == 0 and not ops.alive(h.pid, h.start) and clock.t >= h.end
    assert not ops.alive(h.pid, h.start + 1)                                  # bound by pid AND start
    res = ops.harvest(root, emails=("op@corp-mail.example",))
    assert res["rc"] == 0 and ops.harvested == [str(root)] and ops.harvest_emails == [("op@corp-mail.example",)]
    hj = json.loads(Path(res["harvest_json"]).read_text())
    assert S.self_hashed(hj)["sha256"] == hj["sha256"] and res["harvest_sha256"] == S.sha256_file(res["harvest_json"])
    assert Path(res["harvest_json"]) == ops.harvest_path(root.name) / "HARVEST.json"
    from bench import schedules                                                # 3d (§16.8): the leg's frozen schedule
    sched = json.loads((root / "schedule.json").read_text())
    assert cj["schedule_sha256"] == schedules.schedule_sha256(sched)
    assert sum(len(leg["full_names"]) for b in sched["blocks"] for leg in b["legs"]) == len(cj["p426_ledger"])
    assert all("elapsed_s" in r for p in items if not p.name.endswith(".ready.json")
               for r in json.loads(p.read_text())["requests"])
    assert ops.publish_dossier("/x/pairs/pilot__off-a1__on-a1.json", emails=())["rc"] == 0 and ops.dossiers
    assert ops.publish_run_files(["/x/records/v8_base.json", "/x/sequence.json"], emails=())["rc"] == 0
    assert ops.run_files == [(["/x/records/v8_base.json", "/x/sequence.json"], ())]
    assert ops.power()["battery"] == 80


def test_the_watcher_death_script_leaves_no_exit_state(tmp_path):
    clock = A.Clock()
    ops = A.SeqOps(clock, script={"tg1-p426-off-pilot": {"watcher_dies": True}}, main_root=tmp_path / "main")
    root = tmp_path / "tg1-p426-off-pilot.a1"
    root.mkdir()
    (root / "chain.json").write_text("{}")
    wh = ops.launch(["bench_watch.py", "--chain-json", str(root / "chain.json"), "--driver-pid", "1", "--out",
                     str(root / "watch.jsonl")], cwd="/", pass_fds=())
    clock.sleep(2.0)
    assert not ops.alive(wh.pid, wh.start)
    assert all("exit_state" not in json.loads(x) for x in (root / "watch.jsonl").read_text().splitlines())


def test_the_sequencer_argv_and_records_builders(tmp_path):
    d = A.sequencer_records(tmp_path)
    v8 = json.loads((d / "v8_base.json").read_text())
    assert v8["kind"] == "p426_v8_base" and S.self_hashed(v8) == v8 and not (d / "amendment.json").exists()
    argv, wts = A.seq_argv(tmp_path, "run", "--through", "tg1-p426-on-pilot")
    assert argv[0] == "run" and A.arg(argv, "--record-dir") == str(d) and wts["off"].is_dir()
    assert A.is_subsequence([1, 3], [1, 2, 3]) and not A.is_subsequence([3, 1], [1, 2, 3])
    c = A.Clock(on_sleep=lambda c: None)
    t0 = c.t
    c.sleep(600)
    assert c.t == t0 + 600 and c.sleeps == 1
