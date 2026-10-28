"""P426 T3 frozen tests — names under `s2` (spec §4 "Names under a label b ≠ s", §6): tunes for every axis and the smoke,
leg names (receipts, `.stdout`, `.watch.log`), the per-request session prefix and the M1 qualify directory — from one whole
`--build s2` Wave-1 run over the two committed arms (`t3_frozen_support.s2_full_run`).

Classes: [N] exercises new behaviour; [I] preserves an invariant; [R] reproduces a failure the specification fixes."""

from pathlib import Path

from bench.tests import t3_frozen_support as T
from bench.tests.t3_frozen_support import s2_full_run  # noqa: F401 — the module-scoped run

NAMES = T.s2_leg_names()


def _tune(name):
    return name.split("-", 1)[1]  # "<axis>-p426s2-<arm>-<sel>" → "p426s2-<arm>-<sel>"


def _by_prefix(run):
    return {d["prefix"][len("p426-"):]: d for d in run.box.drivers if d["prefix"]}


def test_every_s2_leg_runs_valid_in_the_plan_order(s2_full_run):
    """[N] the success path: 10 smokes then 20 legs, all VALID, rc 0."""
    assert s2_full_run.rc == 0, s2_full_run.why()
    assert T.launched_names(s2_full_run.box) == NAMES
    for n in NAMES:
        doc = T.receipt(s2_full_run.world.out / "receipts", n)
        assert doc is not None and doc["verdict"] == "VALID", (n, doc and doc["problems"])


def test_every_s2_launch_carries_build_s2_once(s2_full_run):
    """[N] §4: the sequencer passes `--build` when the label is not `s`."""
    launches = s2_full_run.box.launches
    assert len(launches) == 30, s2_full_run.why()
    for x in launches:
        assert x["argv"].count("--build") == 1 and x["argv"][x["argv"].index("--build") + 1] == "s2", x["argv"]


def test_leg_files_follow_the_s2_leg_name(s2_full_run):
    """[N] §4: receipt, `.stdout` and `.watch.log` (router legs) carry `<axis>-p426s2-<arm>-…`; nothing carries an S name."""
    out = s2_full_run.world.out
    assert s2_full_run.rc == 0, s2_full_run.why()
    for n in NAMES:
        assert (out / f"{n}.stdout").exists(), n
        if not n.startswith("m1-"):
            assert list(out.rglob(f"{n}.watch.log")), n
    assert not [p for p in out.rglob("*") if "-p426-" in p.name]


def test_math500_and_cjudge_tunes(s2_full_run):
    """[N] §4: tunes `p426s2-<arm>-b<n>` / `p426s2-<arm>-smoke` for the two row axes."""
    got = _by_prefix(s2_full_run)
    for n in [n for n in NAMES if n.split("-")[0] in ("math500", "cjudge")]:
        assert n in got, (n, sorted(got))
        assert T._flag(got[n]["argv"], "--tune") == _tune(n)


def test_vision_tunes(s2_full_run):
    """[N] §4: the vision rows `vision_gate.p426s2-…jsonl`."""
    got = _by_prefix(s2_full_run)
    for n in [n for n in NAMES if n.startswith("vision-")]:
        assert n in got, (n, sorted(got))
        assert Path(T._flag(got[n]["argv"], "--out")).name == f"vision_gate.{_tune(n)}.jsonl"


def test_reasoning_tunes(s2_full_run):
    """[N] §4: the reasoning out-tag `p426s2-…` (rows `reasoning.p426s2-….partial.jsonl`)."""
    got = _by_prefix(s2_full_run)
    for n in [n for n in NAMES if n.startswith("reasoning-")]:
        assert n in got, (n, sorted(got))
        assert T._flag(got[n]["argv"], "--out-tag") == _tune(n)


def test_the_session_prefix_is_p426_dash_the_s2_leg_name(s2_full_run):
    """[N] §4: `MLX_BENCH_SESSION_PREFIX=p426-<leg name>` for every router leg."""
    assert sorted(_by_prefix(s2_full_run)) == sorted(n for n in NAMES if not n.startswith("m1-")), s2_full_run.why()


def test_the_m1_qualify_directory_is_per_label(s2_full_run):
    """[N] §4: `<workdir>/p426/s2/m1/<tune>`; S's `<workdir>/p426/m1` is never created."""
    w = s2_full_run.world
    outs = sorted(T._flag(d["argv"], "--out") for d in s2_full_run.box.drivers if not d["prefix"])
    want = sorted(str(w.wd / "p426" / "s2" / "m1" / _tune(n)) for n in NAMES if n.startswith("m1-"))
    assert outs == want, s2_full_run.why()
    for o in want:
        assert (Path(o) / "report.json").exists()
    assert not (w.wd / "p426" / "m1").exists()


def test_rows_in_main_carry_only_s2_stems(s2_full_run):
    """[N] §4: every row / sidecar follows from the tune — 24 router legs' rows reach `main` under `p426s2-…` stems."""
    res = s2_full_run.world.main / "benchmark" / "results" / T.ENTRY
    names = sorted(p.name for p in res.iterdir()) if res.exists() else []
    stems = {f"{n.split('-')[0] if n.split('-')[0] != 'vision' else 'vision_gate'}.{_tune(n)}" for n in NAMES
             if not n.startswith("m1-")}
    assert {s for s in stems if any(x.startswith(s + ".") for x in names)} == stems, names
    assert not [x for x in names if ".p426-" in x]
