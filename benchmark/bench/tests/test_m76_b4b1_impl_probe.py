"""M76 B4b-1 acceptance 1 (implementer tests): the tg2 probe entry (`run_tg2_probe.py`) and `bench.tg2_runner` — the argv and
binding, a probe without `--universe` (the committed tg2 universe), the inject flag and out root, the language refusal, the
tg2 carrier / label in the adapter, and the `Tg2Corpus` contract run through `arm_runner` with a mocked agent (the real
corpus; the grader's docker run faked from a recorded real tree)."""
from __future__ import annotations

import importlib
import json
import shlex
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import arm_runner
from bench import structured_grade as sg
from bench import tg2_grade as tg

BENCH = Path(__file__).resolve().parents[1].parent
REPO = BENCH.parent
FIX = Path(__file__).resolve().parent / "fixtures" / "m76_b4b1_impl" / "tg2-grade-trees"
UNIVERSE = json.loads((BENCH / "m65/tg2_universe.json").read_text())


def _probe():
    return importlib.import_module("run_tg2_probe")


def _parse(*extra):
    return _probe()._parser().parse_args(["--model", "m", "--items", "say", "--seed-base", "1001", *extra])


def test_the_probe_argv_is_tg1s_with_the_tg2_choices():
    a = _parse("--lang", "rust", "--scaffold", "opencode-v2-web-tg2", "--frozen-prompt-date", "Fri Nov 13 2026",
               "--evidence", "p426", "--attempt", "2")
    assert a.lang == "rust" and a.scaffold == "opencode-v2-web-tg2" and a.evidence == "p426" and a.attempt == 2
    assert a.universe is None                                   # the core falls back to the corpus's committed universe
    for lang in ("rust", "javascript", "java", "cpp"):
        assert _parse("--lang", lang).lang == lang
    for bad in (["--lang", "python"], ["--lang", "go"], ["--scaffold", "opencode-v2-web-tg1"], ["--tg2-inject", "boom"],
                ["--tg1-inject", "stall"]):
        with pytest.raises(SystemExit):
            _parse(*bad)
    assert _parse("--tg2-inject", "loop").tg1_inject == "loop"       # the core reads one inject attribute


def test_the_runner_binds_the_tg2_policy_corpus_and_evidence():
    from bench import corpus_tg2
    from bench import tg1_runner
    from bench import tg2_runner as R
    assert R.TG2_POLICY.config_id == "tg2" and R.TG2_POLICY.langs == ("rust", "javascript", "java", "cpp")
    assert R.TG2_P426_EVIDENCE == tg1_runner.TG1_P426_EVIDENCE and R.TG2_EVIDENCE == tg1_runner.TG1_EVIDENCE
    c = R._corpus(SimpleNamespace(_polyglot_root=lambda: Path("/x"), _polyglot_sha=lambda r: "s"), SimpleNamespace(universe=None))
    assert isinstance(c, corpus_tg2.Tg2Corpus) and c.universe_path == corpus_tg2.DEFAULT_UNIVERSE


def test_the_adapter_runs_the_tg2_carrier_under_the_tg2_label():
    from bench import arm_opencode as ao
    arm = ao.OpencodeArm(None, mode="tg1", scaffold="tg2")
    assert arm.label == ao.TG2_LABEL == "opencode-v2-web-tg2"
    assert arm.carrier == REPO / "benchmark/opencode_bench_v2_web_tg2.json" and arm.carrier.is_file()
    assert arm.generation_data == ao.TG2_GENERATION_DATA == ao.GENERATION_DATA[:3] + ("benchmark/opencode_bench_v2_web_tg2.json",)
    tg1 = ao.OpencodeArm(None, mode="tg1")
    assert tg1.label == ao.TG1_LABEL and tg1.generation_data == ao.GENERATION_DATA
    with pytest.raises(Exception):
        ao.OpencodeArm(None, mode="m64", scaffold="tg2")


def test_the_tg2_carrier_is_generated_and_equals_tg1s():
    sys.path.insert(0, str(REPO))
    from configgen import targets
    names = {t[0]: t for t in targets.BENCH_TARGETS}
    assert names["opencode-bench-v2-web-tg2"][2] == "benchmark/opencode_bench_v2_web_tg2.json"
    assert (REPO / "benchmark/opencode_bench_v2_web_tg2.json").read_bytes() == \
        (REPO / "benchmark/opencode_bench_v2_web_tg1.json").read_bytes()
    from bench import modelnames
    assert "benchmark/opencode_bench_v2_web_tg2.json" in modelnames.GENERATED_PATHS


# ----------------------------------------------------------------------------------------------- arm_runner with a mocked agent
def _recorded_into(keep, seq, boundary, final, lang, variant, item):
    """The docker-side grade faked from a recorded real tree: its seq dir copied into `keep`, indexed for THIS grade."""
    src = FIX / lang / variant / f"{item}.grades" / "seq-0001"
    dest = Path(keep) / ("seq-%04d" % seq)
    shutil.copytree(src, dest)
    index = json.loads((dest / "index.json").read_text())
    names = sorted(p.name for p in dest.iterdir() if p.is_file() and p.name != "index.json")
    return sg._write_index(Path(keep), dest, seq, boundary, final, index["outcome"], names)


def _agent_arm(host, solution_src):
    from bench.tests.arm_neutral import EVENTS, NeutralArm

    class Agent(NeutralArm):
        def command(self, binary, model, prompt):
            self.prompt = prompt
            lines = "".join(json.dumps(e) + "\n" for e in EVENTS)
            return [binary, "-c", "printf %s " + shlex.quote(lines) + f"; cp {shlex.quote(str(solution_src))} src/lib.rs; "
                    "mkdir -p target/debug && ln -s x target/debug/link && printf 'version = 4\\n' > Cargo.lock"]
    return Agent(host)


def test_a_tg2_item_runs_through_the_core(monkeypatch, tmp_path):
    from bench import corpus_tg2
    from bench import opencode_v2_core as core
    from bench.tests import p371_world as W
    try:
        root = core._polyglot_root()
    except SystemExit:
        pytest.skip("the pinned polyglot checkout is not on this box")
    world = W.neutral_world(monkeypatch, tmp_path)
    entry = UNIVERSE["items"]["rust/say"]
    calls = []

    def fake_grade(lang, work, slug, private, *, prepared=None, keep=None, seq=None, boundary=None, final=False, **kw):
        calls.append(dict(lang=lang, slug=slug, final=final, files=sorted(sg.manifest(work))))
        res = tg.Tg2Grade(lang=lang, leaves={leaf: True for leaf in entry["leaves"]})
        res.artifacts = _recorded_into(keep, seq, boundary, final, "rust", "reference", "rust__say")
        return res
    monkeypatch.setattr(tg, "grade", fake_grade)              # the docker run only: strip and tamper run for real
    corpus = corpus_tg2.Tg2Corpus(polyglot_root=lambda: root)
    adapter = _agent_arm(world.host, root / "rust/exercises/practice/say/.meta/example.rs")
    rc = arm_runner.main(world.host, adapter, W.args(tmp_path, items="say", lang="rust", universe=None, seed_base=1001),
                         template=W.template(config_id="tg2", langs=("rust", "javascript", "java", "cpp")),
                         evidence=W.evidence(), corpus=corpus)
    assert rc == 0
    (row,) = W.rows(world)
    assert row["id"] == "rust/say" and row["passed"] is True and row["file_changed"] is True and row["test_modified"] is False
    assert row["final_tree"]["files"].keys() == {"src/lib.rs"} and row["final_tree"]["missing"] == []
    assert calls and calls[-1]["final"] is True and "Cargo.lock" not in calls[-1]["files"]
    assert not any(f.startswith("target/") for f in calls[-1]["files"])
    finals = [g for g in row["grade_reports"] if g["final"]]
    assert len(finals) == 1 and finals[0]["outcome"] == "parsed"
    assert sg.validate_reports(row["grade_reports"], "rust", row["test_modified"], grader="tg2") == []
    assert adapter.prompt.startswith("Implement the solution in src/lib.rs so that the tests in tests/say.rs pass.")
    man = W.manifest(world)
    assert man["runtime"]["policy"]["corpus_id"] == "tg2"
    assert man["runtime"]["policy"]["grader_version"] == tg.VERSION
    assert man["runtime"]["policy"]["grade_join_timeout_s"] == arm_runner.grade_join_timeout_s(
        corpus.identity()["grader_timeout_s"])


def test_the_core_refuses_a_language_outside_the_tg2_set(monkeypatch, tmp_path):
    from bench import corpus_tg2
    from bench.tests import p371_world as W
    world = W.neutral_world(monkeypatch, tmp_path)
    corpus = corpus_tg2.Tg2Corpus(polyglot_root=lambda: tmp_path)
    with pytest.raises(SystemExit, match="Rust/JavaScript/Java/C\\+\\+"):
        arm_runner.main(world.host, _agent_arm(world.host, tmp_path / "x"), W.args(tmp_path, items="x", lang="python"),
                        template=W.template(config_id="tg2", langs=("rust", "javascript", "java", "cpp")),
                        evidence=W.evidence(), corpus=corpus)


def test_the_inject_out_root_is_the_tg2_one(monkeypatch, tmp_path):
    from bench import corpus_tg2
    from bench.tests import p371_world as W
    world = W.neutral_world(monkeypatch, tmp_path)
    corpus = corpus_tg2.Tg2Corpus(polyglot_root=lambda: tmp_path)
    kw = dict(template=W.template(config_id="tg2", langs=("rust",)), evidence=W.evidence(), corpus=corpus)
    a = W.args(tmp_path, items="say", lang="rust", tg1_inject="stall", expect_items="rust/say", limit=1,
               out=str(tmp_path / "m62/inject/rows.jsonl"))
    with pytest.raises(SystemExit, match="m65/inject"):
        arm_runner.main(world.host, _agent_arm(world.host, tmp_path / "x"), a, **kw)
    assert corpus_tg2.Tg2Corpus.inject_root == "m65/inject"
