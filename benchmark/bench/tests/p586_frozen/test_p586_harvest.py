"""P587 (criterion 4): the Go grader's stderr has a harvest rule, every file of leg 3 has one, and `harvest_wave2(dry_run=True)`
/ `bench.p426_harvest wave2 --dry-run` reports every problem of a tree at once, writes nothing, rc 0 clean / 4 otherwise.

`fixtures/p586/leg3_tree.tsv` is the real leg-3 listing (leg root + the Go evidence directory). The dry-run world is a copy of
the s9 harvest world (`kit.World`). Where the spec leaves the dry run's report channel open (return value, exception or
printed text), the function-level tests read all three; the CLI tests read rc and the printed text.

Classes: [R] reproduces the failure the spec fixes, [I] preserves an invariant, [N] exercises new behaviour."""
from __future__ import annotations

import json

import pytest

from bench import p426_harvest as H


# =============================================================================================== classify
def test_every_leg3_file_has_a_harvest_rule(kit):
    """[R] criterion 4: `classify` of every path of leg 3's real tree returns a rule (baseline: the Go grader's
    `go.stderr` files have none — the harvest refused them)."""
    tree = kit.leg3_tree()
    assert len(tree) == 206
    missing = [f"{k}:{rel}" for k, rel in tree if H.classify(k, rel) is None]
    assert missing == [], "no rule: " + ", ".join(missing)


@pytest.mark.parametrize("rel", ["go__crypto-square.grades/seq-0001/go.stderr", "go__beer-song.grades/seq-0005/go.stderr",
                                 "go__x.grades/seq-12/go.stderr"])
def test_the_go_grader_stderr_rule(kit, rel):
    """[R] `classify("evidence", "<item>.grades/seq-<NNNN>/go.stderr") == ("evidence", None)`."""
    assert H.classify("evidence", rel) == ("evidence", None)


@pytest.mark.parametrize("kind, rel", [
    ("evidence", "go.stderr"),                                           # flat
    ("evidence", "go__x.grades/go.stderr"),                              # two parts
    ("evidence", "go__x.grades/seq-0001/sub/go.stderr"),                 # four parts
    ("evidence", "go__x.grade/seq-0001/go.stderr"),                      # first part not `.grades`
    ("evidence", "go__x.grades/seq-/go.stderr"),                         # no digits
    ("evidence", "go__x.grades/seqA/go.stderr"),
    ("evidence", "go__x.grades/seq-0001x/go.stderr"),
    ("evidence", "go__x.grades/seq-0001/python.stderr"),                 # another name
    ("evidence", "go__x.grades/seq-0001/go.stderr.bak"),
    ("evidence", "go__x.stderr"),
    ("leg", "s1/go__x.grades/seq-0001/go.stderr"),                       # another root kind
    ("run", "go__x.grades/seq-0001/go.stderr"),
])
def test_nothing_else_gains_a_rule(kit, kind, rel):
    """[I] "nothing else changes": near misses of the exact shape stay without a rule (as on the baseline)."""
    assert H.classify(kind, rel) is None


@pytest.mark.parametrize("kind, rel, want", [
    ("evidence", "go__x.grades/seq-0001/go.jsonl", ("evidence", None)),
    ("evidence", "go__x.grades/seq-0001/index.json", ("evidence", None)),
    ("evidence", "go__x.stderr.txt", ("evidence", None)),
    ("evidence", "go__x.final_tree/manifest.json", ("main", None)),
    ("leg", "leg.json", ("main", None)),
    ("leg", "RUNLOG.md", ("evidence", None)),
    ("run", "home/x.db", ("excluded", "private_state")),
])
def test_the_existing_rules_are_unchanged(kit, kind, rel, want):
    """[I] the rules leg 3 already used keep their destinations."""
    assert H.classify(kind, rel) == want


# =============================================================================================== dry run (function)
def _problem_world(kit, tmp_path):
    """The s9 world plus four problems in four places and two phases: three files without a rule (leg root, run dir, evidence
    dir: the inventory) and an exact credential value in RUNLOG.md (the secret gate, which the baseline reaches only after a
    clean inventory)."""
    w = kit.World(tmp_path)
    kit.put(w.root / "stray.unknown-kind", "x")
    kit.put(w.run / "grading-private" / "keep" / "seq-1" / "mystery.bin", "x")
    kit.put(w.ev / "python__beer-song.grades" / "seq-0001" / "notes.bin", "x")
    (w.root / "RUNLOG.md").write_text(f"probe stderr: token {kit.FAKE_SECRET}\n")
    return w


NEEDLES = ("stray.unknown-kind", "mystery.bin", "notes.bin", "RUNLOG.md")


def _dry(w, capsys, **kw):
    """-> (raised?, text): whatever the dry run reports, by return value, exception or print."""
    raised, text = False, ""
    try:
        out = w.harvest(dry_run=True, **kw)
        text = json.dumps(out, default=str) if not isinstance(out, str) else out
    except H.HarvestError as exc:
        raised, text = True, str(exc)
    cap = capsys.readouterr()
    return raised, text + "\n" + cap.out + "\n" + cap.err


def test_dry_run_reports_every_problem_at_once_and_writes_nothing(tmp_path, kit, capsys):
    """[N] criterion 4: all four problems in one dry run (it does not stop at the first, nor at the inventory phase); nothing
    written anywhere (no stage, no destination, no review file); the credential value never printed."""
    w = _problem_world(kit, tmp_path)
    snap = kit.tree_snapshot(tmp_path)
    _raised, text = _dry(w, capsys, secrets={"environ:P426_TEST_API_KEY": kit.FAKE_SECRET})
    for needle in NEEDLES:
        assert needle in text, (needle, text)
    assert kit.FAKE_SECRET not in text
    assert kit.tree_snapshot(tmp_path) == snap
    assert not (w.wd / "p426" / "review").exists()


def test_dry_run_of_a_clean_tree_reports_nothing_and_writes_nothing(tmp_path, kit, capsys):
    """[N] a clean tree: no HarvestError, nothing written (a real harvest of the same tree would publish)."""
    w = kit.World(tmp_path)
    snap = kit.tree_snapshot(tmp_path)
    raised, _text = _dry(w, capsys)
    assert raised is False
    assert kit.tree_snapshot(tmp_path) == snap
    assert not (w.main / kit.WAVE2).exists() and not w.stage.exists()


def test_the_real_harvest_still_refuses_at_the_first_phase(tmp_path, kit):
    """[I] without `dry_run` the harvest is unchanged: it refuses, publishes nothing."""
    w = _problem_world(kit, tmp_path)
    with pytest.raises(H.HarvestError):
        w.harvest(secrets={"environ:P426_TEST_API_KEY": kit.FAKE_SECRET})
    assert not (w.main / kit.WAVE2).exists() or not any((w.main / kit.WAVE2).iterdir())


# =============================================================================================== dry run (CLI)
def _cli(w, kit, tmp_path, *extra, environ_extra=None):
    box = kit.harvest_box(tmp_path)
    box["environ"].update(environ_extra or {})
    argv = ["wave2", "--leg-root", str(w.root), "--main-root", str(w.main), "--evidence-stage", str(w.stage), *extra]
    return H.main(argv, **box)


def test_cli_dry_run_prints_every_problem_and_exits_4(tmp_path, kit, capsys):
    """[N] `--dry-run`: rc 4 with problems, every problem printed, the credential value never, nothing written."""
    w = _problem_world(kit, tmp_path)
    kit.harvest_box(tmp_path)
    snap = kit.tree_snapshot(tmp_path)
    rc = _cli(w, kit, tmp_path, "--dry-run", environ_extra={"P426_TEST_API_KEY": kit.FAKE_SECRET})
    out = capsys.readouterr()
    text = out.out + out.err
    assert rc == 4, text
    for needle in NEEDLES:
        assert needle in text, (needle, text)
    assert kit.FAKE_SECRET not in text
    assert kit.tree_snapshot(tmp_path) == snap


def test_cli_dry_run_of_a_clean_tree_exits_0_and_writes_nothing(tmp_path, kit, capsys):
    """[N] `--dry-run` on a clean tree: rc 0, nothing written."""
    w = kit.World(tmp_path)
    kit.harvest_box(tmp_path)
    snap = kit.tree_snapshot(tmp_path)
    rc = _cli(w, kit, tmp_path, "--dry-run")
    assert rc == 0, capsys.readouterr()
    assert kit.tree_snapshot(tmp_path) == snap


def test_cli_without_dry_run_is_unchanged(tmp_path, kit, capsys):
    """[I] the CLI without `--dry-run`: a refused tree is rc 2 (`REFUSED:`), as on the baseline."""
    w = _problem_world(kit, tmp_path)
    rc = _cli(w, kit, tmp_path)
    assert rc == 2 and "REFUSED:" in capsys.readouterr().err
