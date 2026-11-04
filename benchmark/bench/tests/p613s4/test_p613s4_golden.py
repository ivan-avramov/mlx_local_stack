"""Golden counts on the committed data (marker `p613s4_golden`): the contract's designer counts for the A7 first divergence.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.

Reads `benchmark/results/p426/` (B8.json, panel/, wave2/) and the `evidence` commit `b6ec7819` through the shared git objects
(`git show`, no checkout). A missing input skips with the reason (never a silent pass).

Golden (contract): s1 identical 18, environment 24, cutoff 1, generation 0; s2 identical 17, environment 25, cutoff 1, generation 0
(86 items). `p613-step3` committed sheet (at STEP3_COMMIT) is what the no-`--evidence-ref` path must still reproduce.
"""
from __future__ import annotations

import json

import pytest

from bench.tests.p613s3 import s3world as S
from bench.tests.p613s4 import dview as D

pytestmark = pytest.mark.p613s4_golden

EVIDENCE_REF = "b6ec7819"
STEP3_COMMIT = "e8383713"            # HEAD of the step-3 / "C288 — P613 step 4 Go" state: the committed step-3 sheet
RESULTS = S.BENCH_DIR / "results" / "p426"
ROWS = S.BENCH_DIR / "results"
GOLD = {"s1": {"identical": 18, "environment": 24, "cutoff": 1, "generation": 0},
        "s2": {"identical": 17, "environment": 25, "cutoff": 1, "generation": 0}}


@pytest.fixture(scope="module")
def real():
    top = S.git(S.BENCH_DIR, "rev-parse", "--show-toplevel")
    for ref in (EVIDENCE_REF, STEP3_COMMIT):
        try:
            S.git(top, "cat-file", "-e", f"{ref}^{{commit}}")
        except RuntimeError:
            pytest.skip(f"commit {ref} is not in this repository's objects")
    return dict(top=top, b8=json.loads((RESULTS / "B8.json").read_text()))


def cli(out_dir, *, ref):
    out_dir.mkdir(parents=True, exist_ok=True)
    md, js = out_dir / "SIGNALS.md", out_dir / "SIGNALS.json"
    args = ["all", "--results-root", RESULTS, "--rows-root", ROWS, "--b8", RESULTS / "B8.json", "--out-md", md, "--out-json", js,
            "--panel", RESULTS / "panel"]
    if ref:
        args += ["--evidence-ref", ref]
    proc = S.run_cli("bench.p426_signals", args, env_extra={"MLX_BENCH_RESULTS": str(ROWS)}, home=ROWS)
    return proc, md, js


@pytest.fixture(scope="module")
def runs(real, tmp_path_factory):
    out = []
    for i in range(2):
        proc, md, js = cli(tmp_path_factory.mktemp(f"goldfinal{i}"), ref=EVIDENCE_REF)
        assert proc.returncode == 0, proc.stderr[-1200:]
        out.append((md, js))
    return out


@pytest.fixture(scope="module")
def div(real, divmod_):
    return divmod_.a7_divergence(RESULTS, real["b8"], EVIDENCE_REF, real["top"])


# class: new-behaviour (per-session counts on the committed pairs: s1 18/24/1/0, s2 17/25/1/0)
def test_golden_counts(div):
    c = D.counts(div)
    assert c["s1"] == GOLD["s1"] and c["s2"] == GOLD["s2"]
    assert c["both"] == {k: GOLD["s1"][k] + GOLD["s2"][k] for k in D.KINDS}


# class: new-behaviour (86 items, 43 per session, every one B8-accepted; no generation item)
def test_golden_items(div):
    got = D.items(div)
    assert len(got) == 86
    assert sum(1 for s, _ in got if s == "s1") == 43 and sum(1 for s, _ in got if s == "s2") == 43
    assert [k for k, v in got.items() if v[0] == "generation"] == []


# class: new-behaviour (every environment item names its first differing tool; every environment / generation item has k)
def test_golden_environment_items_carry_tool_and_k(div):
    for key, (kind, k, tool) in D.items(div).items():
        if kind == "environment":
            assert isinstance(tool, str) and tool, key
        if kind in ("environment", "generation"):
            assert isinstance(k, int) and k >= 0, key


# class: new-behaviour (CLI on the committed data: rc 0, FINAL, the section, counts, no flag, header ref, 172 evidence inputs)
def test_golden_cli_final(real, runs):
    md, js = runs[0]
    text, sig = md.read_text(), json.loads(js.read_text())
    assert text.splitlines()[0] == f"# P426 signals — {D.FINAL}" and sig["header"]["status"] == D.FINAL
    assert D.HEADING in text and D.LABEL in D.section(text)
    c = D.counts(sig["divergence"])
    assert c["s1"] == GOLD["s1"] and c["s2"] == GOLD["s2"]
    assert D.divergence_flags(sig) == []                 # the divergence flag only (the committed sheet's cross_wave flag stays)
    # fix 3: the recorded ref and the input prefix are the RESOLVED FULL sha
    full = S.git(real["top"], "rev-parse", f"{EVIDENCE_REF}^{{commit}}")
    assert sig["header"]["evidence_ref"] == full
    ev = [k for k in sig["inputs"] if k.startswith(f"evidence:{full}:")]
    assert len(ev) == 172 and all(k.endswith(".events.jsonl") for k in ev)
    assert not any(k.startswith(f"evidence:{EVIDENCE_REF}:") for k in sig["inputs"])


# class: reproduces-failure (fix 3: `evidence_ref_given` holds the string as passed, `b6ec7819`, next to the full-sha `evidence_ref`)
def test_golden_evidence_ref_given(runs):
    sig = json.loads(runs[0][1].read_text())
    assert sig["header"]["evidence_ref_given"] == EVIDENCE_REF
    assert sig["header"]["evidence_ref"] != EVIDENCE_REF and len(sig["header"]["evidence_ref"]) == 40


# class: reproduces-failure (F4, GLM: on the REAL sheet the section sits between §4.5 and Flags, once)
def test_golden_section_between_subjective_and_flags(runs):
    text = runs[0][0].read_text()
    assert text.count(D.HEADING) == 1
    assert text.index("## Subjective panel (§4.5; `subjective`)") < text.index(D.HEADING) < text.index("## Flags (`flags`")


# class: new-behaviour (F4: the same position on the COMMITTED sheet, once step 4 commits it; before that, skipped with the reason)
def test_golden_committed_sheet_section_position():
    text = (RESULTS / "SIGNALS.md").read_text()
    if D.HEADING not in text:
        pytest.skip("committed SIGNALS.md is still the step-3 sheet; this check binds when step 4 commits its outputs")
    assert text.count(D.HEADING) == 1
    assert text.index("## Subjective panel (§4.5; `subjective`)") < text.index(D.HEADING) < text.index("## Flags (`flags`")
    assert text.splitlines()[0] == f"# P426 signals — {D.FINAL}"


def _scalars(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from _scalars(v)
    elif isinstance(node, list):
        for v in node:
            yield from _scalars(v)
    else:
        yield None, node


# class: new-behaviour (byte-identical regeneration on the committed data)
def test_golden_cli_byte_identical(runs):
    assert runs[0][0].read_bytes() == runs[1][0].read_bytes()
    assert runs[0][1].read_bytes() == runs[1][1].read_bytes()


# class: invariant (no `--evidence-ref`: the output is byte-identical to the committed step-3 sheet at STEP3_COMMIT)
def test_golden_no_ref_path_reproduces_step3_sheet(real, tmp_path):
    proc, md, js = cli(tmp_path / "noref", ref=None)
    assert proc.returncode == 0, proc.stderr[-1200:]
    for name, path in (("SIGNALS.md", md), ("SIGNALS.json", js)):
        want = D.git_bytes(real["top"], STEP3_COMMIT, f"benchmark/results/p426/{name}")
        assert path.read_bytes() == want, name


# class: new-behaviour (once step 4 commits its outputs, they are the `all --evidence-ref` outputs, byte for byte)
def test_golden_committed_sheet_is_the_final_output(runs):
    committed = RESULTS / "SIGNALS.md"
    if D.HEADING not in committed.read_text():
        pytest.skip("committed SIGNALS.md is still the step-3 sheet; this check binds when step 4 commits its outputs")
    for name, path in (("SIGNALS.md", runs[0][0]), ("SIGNALS.json", runs[0][1])):
        assert (RESULTS / name).read_bytes() == path.read_bytes(), name
