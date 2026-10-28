"""P426 T3 frozen tests — harvest paths per label and the naming exemption (spec §4 "harvest dossiers", `bench.modelnames`,
§6): `s2` dossiers in `benchmark/results/p426/wave1.s2/<leg>/`, run files in `wave1.s2/run/`, nothing under S's `wave1/`; the
exemption for harvested Wave-1 evidence matches `benchmark/results/p426/wave1(\\.[a-z][a-z0-9]{0,7})?/`.

Classes: [N] exercises new behaviour; [I] preserves an invariant; [R] reproduces a failure the specification fixes."""

import json

import pytest

from bench import modelnames
from bench.tests import t3_frozen_support as T
from bench.tests.t3_frozen_support import s2_full_run  # noqa: F401 — the module-scoped run

NAMES = T.s2_leg_names()


def test_every_s2_leg_has_its_dossier_under_wave1_s2(s2_full_run):
    """[N] §4: `wave1.s2/<leg>/SCRUB_MANIFEST.json` for all 30 legs; each manifest lists only its dossier and its rows."""
    base = s2_full_run.world.main / "benchmark" / "results" / "p426"
    assert s2_full_run.rc == 0, s2_full_run.why()
    for n in NAMES:
        manifest = json.loads((base / "wave1.s2" / n / "SCRUB_MANIFEST.json").read_text())
        assert manifest["leg"] == n
        for rel in manifest["files"]:
            assert rel.startswith(f"benchmark/results/p426/wave1.s2/{n}/") or (
                rel.startswith(f"benchmark/results/{T.ENTRY}/") and ".p426s2-" in rel), rel
    assert sorted(p.name for p in base.iterdir()) == ["wave1.s2"]


def test_the_s2_run_files_are_the_record_and_the_sequence_log(s2_full_run):
    """[N] §4: run files in `wave1.s2/run/` — `frozen.s2.json` and `sequence.log`; no ON overlay (retired under `s2`)."""
    run_dir = s2_full_run.world.main / "benchmark" / "results" / "p426" / "wave1.s2" / "run"
    names = sorted(p.name for p in run_dir.iterdir()) if run_dir.exists() else []
    assert "frozen.s2.json" in names and "sequence.log" in names, names
    assert not [x for x in names if "registry-on" in x], names
    assert (run_dir / "frozen.s2.json").read_bytes() == s2_full_run.world.frozen.read_bytes()


def test_the_m1_on_dossier_carries_the_overlay_qualify_served(s2_full_run):
    """[N] §4 (P472 / P504): the M1 ON dossier's `m1/` copy holds `overlay-<entry>.yaml`, byte-equal to `WT_on`'s registry."""
    w = s2_full_run.world
    for n in [n for n in NAMES if n.startswith("m1-") and "-on-" in n]:
        p = w.main / "benchmark/results/p426/wave1.s2" / n / "m1" / f"overlay-{T.ENTRY}.yaml"
        assert p.exists() and T.sha256_file(p) == T.sha256_file(w.on / "main_models.yaml"), n


EXEMPT = ["benchmark/results/p426/wave1/math500-p426-on-b1/leg.stdout",
          "benchmark/results/p426/wave1/run/registry-on.yaml"]
EXEMPT_NEW = ["benchmark/results/p426/wave1.s2/math500-p426s2-on-b1/leg.stdout",
              "benchmark/results/p426/wave1.s2/run/frozen.s2.json",
              "benchmark/results/p426/wave1.a/x.log",
              "benchmark/results/p426/wave1.abcdefgh/x.log",
              "benchmark/results/p426/wave1.s9z/m1-p426s9z-on-b2/m1/report.json"]
NOT_EXEMPT = ["benchmark/results/p426/wave1.S2/x.log", "benchmark/results/p426/wave1.2s/x.log",
              "benchmark/results/p426/wave1.abcdefghi/x.log", "benchmark/results/p426/wave1.s-2/x.log",
              "benchmark/results/p426/wave1s2/x.log", "benchmark/results/p426/wave1./x.log",
              "benchmark/results/p426/wave2/x.log", "benchmark/results/p426/x/wave1.s2/x.log", "docs/wave1.s2/x.md",
              "benchmark/results/p426/wave1.s2"]


@pytest.mark.parametrize("path", EXEMPT)
def test_s_wave1_evidence_stays_exempt(tmp_path, path):
    """[I] `bench.modelnames`: S's harvested evidence remains data."""
    diff = T.added_line_diff(path, f"the {T.fragment()} drafter")
    assert modelnames.diff_violations(diff, root=T.names_root(tmp_path)) == []


@pytest.mark.parametrize("path", EXEMPT_NEW)
def test_labelled_wave1_evidence_is_exempt(tmp_path, path):
    """[N] `bench.modelnames`: `wave1.<label>/` (the label grammar) is harvested evidence too."""
    diff = T.added_line_diff(path, f"the {T.fragment()} drafter")
    assert modelnames.diff_violations(diff, root=T.names_root(tmp_path)) == []


@pytest.mark.parametrize("path", NOT_EXEMPT)
def test_paths_outside_the_pattern_are_still_checked(tmp_path, path):
    """[I] the exemption is exactly the pattern: no other label shape, directory or prefix is laundered."""
    diff = T.added_line_diff(path, f"the {T.fragment()} drafter")
    assert modelnames.diff_violations(diff, root=T.names_root(tmp_path)), path
