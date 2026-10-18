"""P371 review r3 F16: the invocation's final manifest is read ONCE and validated against THIS invocation (model, language, seed
base, scaffold label, arm, the worker at launch) before anything hydrates from it; a run id already seen in this chain is
refused; the seen-run-id set lives in `progress.seen_run_ids` and survives a resume."""
from __future__ import annotations

import json

from bench.tests.m64_support import FakeOps, M, SMOKE, Crash, chain_json, env, kill_probes, run      # noqa: F401  (fixture: env)
from bench.tests.test_p371_m64_resume import LEG3_SLOT2, CrashAt, crash_run


def build(tmp_path):
    a = M.parse_args(SMOKE + ["--out-root", str(tmp_path / "o")])
    chain = M.build_chain(a, FakeOps(tmp_path), M.Timers(), lambda m: None, {"python": ["a"], "go": ["b"]}, tmp_path / "o", {})
    out = tmp_path / "rows.a1.jsonl"
    view = dict(out=str(out), slot_base="e|oc|m|s1|python", arm="oc", model="m", lang="python", seed_base=1001,
                label=chain.label_of("oc"))
    worker = dict(pid=7, create_time=1.5)
    good = {"run_id": "R-good", "model": "m", "worker": dict(worker, model_path="x"),
            "runtime": {"lang": "python", "seed_base": 1001, "scaffold": chain.label_of("oc"), "arm": "oc"},
            "cleanup_status": {"completed": True}}
    return chain, out, view, worker, good


def hydrate(chain, out, view, worker, man, **att_extra):
    out.with_suffix(".manifest.json").write_text(json.dumps(man))
    att = dict(attempt=1, run_id=None, worker=worker, transport_abort=None, cancelled_item=None, cleanup_status=None, **att_extra)
    chain.hydrate_from_manifest(att, view, out, {"expected_slots": ["e|oc|m|s1|python|a"]})
    return att


def test_a_manifest_bound_to_this_invocation_hydrates_and_its_run_id_is_remembered(tmp_path):
    chain, out, view, worker, good = build(tmp_path)
    att = hydrate(chain, out, view, worker, good)
    assert att["run_id"] == "R-good" and att["cleanup_status"] == {"completed": True} and "R-good" in chain.seen_run_ids


def test_a_foreign_manifest_copied_in_is_refused_field_by_field(tmp_path):
    for path, value in (("model", "other"), ("worker", dict(pid=8, create_time=1.5)), ("runtime.lang", "go"),
                        ("runtime.seed_base", 7), ("runtime.scaffold", "other-label"), ("runtime.arm", "pi")):
        chain, out, view, worker, good = build(tmp_path / path.replace(".", "_"))
        (tmp_path / path.replace(".", "_")).mkdir(parents=True, exist_ok=True)
        d = good
        parts = path.split(".")
        for k in parts[:-1]:
            d = d[k]
        d[parts[-1]] = value
        att = hydrate(chain, out, view, worker, good)
        assert att["manifest_problem"].startswith("binding differs") and path.split(".")[-1] in att["manifest_problem"], path
        assert att["cleanup_status"] is None and att["run_id"] is None and "R-good" not in chain.seen_run_ids


def test_a_run_id_already_seen_in_this_chain_is_refused(tmp_path):
    chain, out, view, worker, good = build(tmp_path)
    chain.seen_run_ids.add("R-good")
    att = hydrate(chain, out, view, worker, good)
    assert att["manifest_problem"] == "run_id already seen" and att["cleanup_status"] is None


def test_the_seen_set_is_persisted_in_chain_json_and_a_resume_keeps_it(env):
    crash_run(env, CrashAt(LEG3_SLOT2))
    first = set(chain_json(env)["progress"]["seen_run_ids"])
    assert len(first) >= 3
    assert run(env, __import__("bench.tests.m64_support", fromlist=["SMOKE"]).SMOKE) == 0
    cj = chain_json(env)
    final = set(cj["progress"]["seen_run_ids"])
    assert first <= final and {a["run_id"] for a in cj["attempts"] if a["run_id"]} <= final
