"""P371 review r6 residuals F26 - F29."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from bench import atomic_publish as ap
from bench import chain_core
from bench.tests.m64_support import SMOKE, Crash, chain_json, env, kill_probes, log_has, run      # noqa: F401  (fixture: env)
from bench.tests.test_p371_review_r3_f16 import build


# ------------------------------------------------------------------------------------------------ F26
def test_temp_names_are_random_per_call_and_collisions_retry_without_touching_the_colliding_file(tmp_path, monkeypatch):
    dest = tmp_path / "e.json"
    names = iter(["aa" * 8, "aa" * 8, "bb" * 8])
    monkeypatch.setattr(ap.secrets, "token_hex", lambda n: next(names))
    squatter = tmp_path / f".e.json.tmp.{os.getpid()}.{'aa' * 8}"
    squatter.write_bytes(b"someone else's temp")
    ap.publish_exclusive(dest, b"payload")
    assert dest.read_bytes() == b"payload" and squatter.read_bytes() == b"someone else's temp"    # no O_TRUNC over it


def test_a_linked_destination_is_never_truncated_by_a_later_publisher(tmp_path):
    dest = tmp_path / "e.json"
    ap.publish_exclusive(dest, b"first")
    with pytest.raises(FileExistsError):
        ap.publish_exclusive(dest, b"second")
    assert dest.read_bytes() == b"first" and not ap.leftover_temps(tmp_path)


def test_two_publishers_in_one_process_use_distinct_temp_names(tmp_path, monkeypatch):
    seen = []
    real = os.link
    monkeypatch.setattr(os, "link", lambda s, d, *a, **k: (seen.append(os.path.basename(s)), real(s, d, *a, **k))[1])
    ap.publish_exclusive(tmp_path / "x.json", b"1")
    ap.publish_exclusive(tmp_path / "x.json.2", b"2")
    assert len(set(seen)) == 2 and all(re.fullmatch(r"\.x\.json(\.2)?\.tmp\.\d+\.[0-9a-f]{16}", n) for n in seen)


# ------------------------------------------------------------------------------------------------ F27
def test_the_sweep_matches_exactly_the_publishers_temp_grammar_and_keeps_every_other_dotfile(tmp_path):
    mine = tmp_path / f".t.web.jsonl.tmp.4242.{'ab' * 8}"
    mine.write_text("half")
    keep = [tmp_path / n for n in (".gitkeep", ".env", ".t.tmp.notapid.abcdef0123456789", ".t.web.jsonl.tmp.4242",
                                   f".t.tmp.1.{'AB' * 8}", f".t.tmp.1.{'ab' * 7}", f"x.tmp.1.{'ab' * 8}", ".tmp.1.abcdef0123456789")]
    for p in keep:
        p.write_text("keep me")
    assert ap.leftover_temps(tmp_path) == [mine]
    assert ap.parse_temp(mine.name) == dict(name="t.web.jsonl", pid=4242, rand="ab" * 8)
    assert all(ap.parse_temp(p.name) is None for p in keep)


def test_the_chain_sweep_removes_only_its_own_temps(tmp_path):
    from bench.tests.m64_support import FakeOps, M
    lines = []
    chain = M.build_chain(M.parse_args(SMOKE + ["--out-root", str(tmp_path / "o")]), FakeOps(tmp_path), M.Timers(),
                          lines.append, {"python": ["a"], "go": ["b"]}, tmp_path / "o", {})
    mine = tmp_path / f".t.web.jsonl.tmp.7.{'cd' * 8}"
    other = tmp_path / ".important"
    mine.write_text("x")
    other.write_text("y")
    assert chain.sweep_temps(tmp_path) == [mine.name] and other.exists() and not mine.exists()


# ------------------------------------------------------------------------------------------------ F28
def test_a_wrong_language_row_in_a_crashed_invocation_is_quarantined_not_an_aborted_resume(env, monkeypatch):
    from bench.tests.test_p371_review_r1_f9 import crash_at_continue, table
    seen = {"n": 0}

    def second(path):
        seen["n"] += 1
        return seen["n"] == 2
    real = crash_at_continue(monkeypatch, second)
    with pytest.raises(Crash):
        run(env, SMOKE)
    kill_probes(env)
    monkeypatch.setattr(chain_core, "barrier_signal", real)
    rec = next(i for i in chain_json(env)["progress"]["invocations"] if i["status"] == "running")
    path = env["out"] / rec["file"]
    path.write_text(path.read_text().replace('"id": "python/', '"id": "go/'))
    assert run(env, SMOKE) == 0
    cj = chain_json(env)
    assert next(i for i in cj["progress"]["invocations"] if i["attempt"] == rec["attempt"] and i["file"].endswith(
        Path(rec["file"]).name)).get("status") == "quarantined"
    assert log_has(env, "language") and len(table(env).scored) == 16


# ------------------------------------------------------------------------------------------------ F29
def test_the_evidence_root_is_derived_from_the_bound_manifest_when_the_barrier_never_saw_the_run_id(tmp_path):
    chain, out, view, worker, good = build(tmp_path)
    chain.resolve_specs()
    model_dir_view = dict(view, model="m")
    good["runtime"]["invocation_nonce"] = "a" * 64
    out.with_suffix(".manifest.json").write_text(json.dumps(good))
    root = Path(chain.ops.wd) / "transcripts/oc/m" / f"{out.stem}.R-good"
    (root / "item").mkdir(parents=True)
    stray = root / "item" / f".events.jsonl.tmp.9.{'ef' * 8}"
    stray.write_text("half")
    att = dict(attempt=1, run_id=None, worker=worker)
    removed = chain.sweep_running_evidence(model_dir_view, att, out, {"nonce": "a" * 64})
    assert removed == [stray.name] and not stray.exists()
    foreign = dict(good, run_id="R-other", model="elsewhere")
    out.with_suffix(".manifest.json").write_text(json.dumps(foreign))
    assert chain.sweep_running_evidence(model_dir_view, att, out, {"nonce": "a" * 64}) == []       # an unbound manifest names no root
