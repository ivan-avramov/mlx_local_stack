"""S29 I1 (spec docs/specs/s29-tg2-testable.md v1.1, acceptance 5): the tg2 identity binds the carrier, the prompt's helper
sentences and the workspace preparation; the pre-S29 identity (tg1's carrier bytes, no workspace binding) and the new one
differ, and a row / record of each refuses to pool (the generation composite pairs nothing across them; the positives record of
the other identity refuses)."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from bench import arm_opencode as ao
from bench import identity_closure as ic
from bench import tg1_pairing
from bench.tests.s26_frozen import s26_support as X
from bench.tests.s26_frozen.test_s26_arm_identity import identity_inputs

BENCH = Path(__file__).resolve().parents[1].parent
REPO = BENCH.parent
PRE_S29_HINTS = {                         # the helper sentences of the pre-S29 tg2 identity (baseline cd334f773), verbatim
    "rust": "Helper modules may go under src/; you may add [dependencies] from the offline crates listed in OFFLINE_CRATES.md "
            "to Cargo.toml.",
    "java": "Helper classes may go only in the solution's package.",
    "javascript": "Helper .js files may go beside the solution.",
    "cpp": "Helper .h / .cpp files may go beside the solution.",
}


def test_the_new_helper_sentences_extend_the_pre_s29_ones():
    from bench import corpus_tg2
    assert all(corpus_tg2.HINTS[lang].startswith(PRE_S29_HINTS[lang] + " ") for lang in PRE_S29_HINTS)


@pytest.fixture
def prefilled(tmp_path, monkeypatch):
    gw = X.GradleWorld(tmp_path, monkeypatch)
    assert gw.prefill() == 0
    return gw


def _composite(ident, selection):
    return ao.p311_generation_identity_sha256({**ident, **selection["fields"], "polyglot_sha": "p" * 40,
                                               "sampling_profile": "deployed"})


def _tg2(monkeypatch=None):
    import importlib
    from bench import tg2_runner
    from types import SimpleNamespace
    p = importlib.import_module("run_tg2_probe")
    adapter = ao.OpencodeArm(p, mode="tg1", scaffold="tg2")
    ident, _ = identity_inputs("run_tg2_probe", "tg2")
    return ident, adapter.selection(None), tg2_runner._corpus(p, SimpleNamespace(universe=None))


def _old(monkeypatch, tmp_path):
    """The pre-S29 tg2 identity's inputs: the carrier was tg1's bytes, the corpus identity had no workspace binding."""
    from bench import corpus_tg2
    old = tmp_path / "opencode_bench_v2_web_tg2.json"
    shutil.copyfile(BENCH / "opencode_bench_v2_web_tg1.json", old)
    monkeypatch.setattr(ao, "TG2_CARRIER", old)
    real = corpus_tg2.Tg2Corpus.identity
    monkeypatch.setattr(corpus_tg2.Tg2Corpus, "identity", lambda self: {k: v for k, v in real(self).items() if k != "workspace"})


def test_the_corpus_identity_binds_the_testable_workspace():
    from bench import corpus_tg2
    from bench import tg2_materialize as mat
    ws = corpus_tg2.workspace_identity()
    assert ws["testable"] == mat.TESTABLE_VERSION
    assert ws["full_suite_commands"] == corpus_tg2.FULL_SUITE_COMMANDS
    import json
    assert ws["hints_sha256"] == hashlib.sha256(json.dumps(corpus_tg2.HINTS, sort_keys=True, separators=(",", ":"))
                                                .encode()).hexdigest()


def test_the_policy_carries_the_workspace_and_the_new_carrier(prefilled):
    from bench import corpus_tg2
    ident, selection, _ = _tg2()
    assert ident["policy"]["corpus_identity"]["workspace"] == corpus_tg2.workspace_identity()
    assert ident["policy"]["carrier_sha256"] == hashlib.sha256((BENCH / "opencode_bench_v2_web_tg2.json").read_bytes()).hexdigest()
    assert selection["fields"]["opencode_bench_config_sha256"] == ident["policy"]["carrier_sha256"]


def test_old_and_new_identities_differ_and_never_pool(prefilled, monkeypatch, tmp_path):
    new, new_sel, _ = _tg2()
    _old(monkeypatch, tmp_path)
    old, old_sel, _ = _tg2()
    assert old["scaffold"] == new["scaffold"] == "opencode-v2-web-tg2"            # the label stays; the identity values move
    assert old["scaffold_policy_sha256"] != new["scaffold_policy_sha256"]
    assert old_sel["fields"]["opencode_bench_config_sha256"] != new_sel["fields"]["opencode_bench_config_sha256"]
    g_old, g_new = _composite(old, old_sel), _composite(new, new_sel)
    assert g_old != g_new
    rows = lambda g, arm: [dict(id=f"cpp/x{k}", sample=0, generation_identity_sha256=g, arm_identity_sha256=arm,  # noqa: E731
                                prompt_date="Fri Nov 13 2026") for k in range(3)]
    got = tg1_pairing.pair_rows(rows(g_old, "a" * 64), rows(g_new, "b" * 64))
    assert got["paired"] == [] and len(got["generation_mismatch"]) == 3
    same = tg1_pairing.pair_rows(rows(g_new, "a" * 64), rows(g_new, "b" * 64))
    assert len(same["paired"]) == 3                                                # the control: same identity pairs


def test_a_positives_record_of_the_old_identity_refuses(prefilled, monkeypatch, tmp_path):
    from bench import p426_freeze as fz
    new, _, _ = _tg2()
    _old(monkeypatch, tmp_path)
    old, _, _ = _tg2()
    from bench import p426_hooks as ph
    from bench import tg2_grade
    live = {k: new.get(k) for k in fz.IDENTITY_KEYS}

    def problems(ident):
        doc = ph.seal(dict(kind=fz.KIND_POSITIVES, verdict="PASS", problems=[], arm="n16", n16_commit="c" * 40,
                           **{k: ident.get(k) for k in fz.IDENTITY_KEYS}))
        return fz.positives_problems(doc, arm="n16", commit="c" * 40, identity=live, frozen_prompt_date="d",
                                     image_id=tg2_grade.pinned_image_id())
    assert "scaffold_policy_sha256 differs from the probe's live identity" in problems(old)
    assert not [p for p in problems(new) if "live identity" in p]                 # the control: the new record's identity holds


@pytest.mark.parametrize("change", ["hints", "testable", "commands"])
def test_each_bound_part_moves_the_identity(prefilled, monkeypatch, change):
    from bench import corpus_tg2
    from bench import tg2_materialize as mat
    base = _tg2()[0]["scaffold_policy_sha256"]
    if change == "hints":
        monkeypatch.setitem(corpus_tg2.HINTS, "cpp", corpus_tg2.HINTS["cpp"] + " ")
    elif change == "testable":
        monkeypatch.setattr(mat, "TESTABLE_VERSION", mat.TESTABLE_VERSION + "-x")
    else:
        monkeypatch.setitem(corpus_tg2.FULL_SUITE_COMMANDS, "rust", "cargo test --all")
    assert _tg2()[0]["scaffold_policy_sha256"] != base


def test_the_probe_code_closure_holds_the_workspace_and_prompt_code():
    files = {Path(f).resolve().relative_to(REPO.resolve()).as_posix() for f in ic.python_closure(REPO / "benchmark/run_tg2_probe.py", REPO)}
    assert {"benchmark/bench/corpus_tg2.py", "benchmark/bench/tg2_materialize.py"} <= files
    arm = ao.OpencodeArm(None, mode="tg1", scaffold="tg2")
    assert "benchmark/opencode_bench_v2_web_tg2.json" in arm.identity_data
