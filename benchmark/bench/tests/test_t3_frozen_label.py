"""P426 T3 frozen tests — the build label (spec §4 "Label", §6): the grammar `^[a-z][a-z0-9]{0,7}$`, `--build` required by the
sequencer, `bench.p426_leg` defaulting to `s`, and `s` byte-identical to today (names, argv, records, receipts).

Classes: [N] exercises new behaviour; [I] preserves an invariant; [R] reproduces a failure the specification fixes."""

import json

import pytest

from bench import p426_leg as L, p426_wave1 as W
from bench.tests import t3_frozen_support as T
from bench.tests.t3_frozen_support import box  # noqa: F401 — the fake-box fixture

# today's receipt fields (`bench/p426_leg.py:460-461,463-464,474,478,482,495,531,545-546` and `:557-558,560,576,595-596`)
LEG_KEYS = {"name", "arm", "kind", "model", "problems", "speed_problems", "pins", "state", "pre_state", "started", "router_pid",
            "worker", "log", "ended", "watch", "verdict", "speed_valid"}
QUALIFY_KEYS = {"name", "arm", "kind", "model", "problems", "speed_problems", "pins", "state", "report", "started", "ended",
                "verdict", "speed_valid"}
STATE_KEYS = {"stack_head", "stack_clean", "mlx_vlm", "mlx_serve", "frozen_sha"}


def test_the_sequencer_requires_build(tmp_path, monkeypatch, box):
    """[N] §4: `bench.p426_wave1` requires `--build`; without it nothing is launched or harvested — and the same argv with
    `--build s` runs (the refusal is for the missing option, not the world)."""
    w = T.make_s_world(tmp_path)
    run = T.run_sequencer(w, box, T.s_argv(w, axes=["m1"]), monkeypatch)
    assert run.rc not in (0, None) and box.legs_run == [], run.why()
    assert not (w.main / "benchmark" / "results" / "p426").exists()
    ok = T.run_sequencer(w, box, T.s_argv(w, axes=["m1"], build="s"), monkeypatch)
    assert ok.rc == 0, ok.why()


@pytest.mark.parametrize("label", ["S2", "2s", "s-2", "s_2", "", "abcdefghi", "s2 "])
def test_a_label_outside_the_grammar_is_refused_by_the_sequencer(tmp_path, monkeypatch, box, label):
    """[N] §4 grammar: refused, nothing launched, no marker, no run file; the control (`s2`, fresh `--out`) runs."""
    w = T.make_arms_world(tmp_path)
    run = T.run_sequencer(w, box, T.s2_argv(w, build=label, axes=["m1"]), monkeypatch)
    T.assert_refused_before_launch(run, allow_usage=True)
    assert not (w.out / ".build").exists()
    w.out = w.wd / "p426" / "wave1.s2.control"
    ok = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    assert ok.rc == 0, ok.why()


@pytest.mark.parametrize("label", ["S2", "s-2", "abcdefghi"])
def test_a_label_outside_the_grammar_is_refused_by_the_leg(tmp_path, monkeypatch, box, label):
    """[N] §4 grammar on `bench.p426_leg`: nonzero, no driver runs; the same leg with `--build s` runs VALID."""
    w = T.make_s_world(tmp_path)
    monkeypatch.setenv("STACK_WORKDIR", str(w.wd))
    argv = ["--axis", "m1", "--arm", "off", "--smoke", "--stack-root", str(w.root), "--workdir", str(w.wd),
            "--registry-on", str(w.overlay), "--receipt-dir", str(tmp_path / "rd")]
    rc, text = T.run_main(L.main, argv + ["--build", label])
    assert rc not in (0, None) and box.drivers == [], text
    rc, text = T.run_main(L.main, argv + ["--build", "s"])
    assert rc == 0 and T.receipt(tmp_path / "rd", "m1-p426-off-smoke")["verdict"] == "VALID", text


def test_the_leg_defaults_to_s(tmp_path, monkeypatch, box):
    """[I] §4: `bench.p426_leg` without `--build` and with `--build s` write the same names, directories and record shape."""
    got = {}
    for flag in ([], ["--build", "s"]):
        w = T.make_s_world(tmp_path / ("explicit" if flag else "default"))
        monkeypatch.setenv("STACK_WORKDIR", str(w.wd))
        rd = w.tmp / "rd"
        rc, text = T.run_main(L.main, ["--axis", "m1", "--arm", "on", "--block", "1", "--stack-root", str(w.root), "--workdir",
                                       str(w.wd), "--registry-on", str(w.overlay), "--receipt-dir", str(rd), *flag])
        assert rc == 0, text
        doc = T.receipt(rd, "m1-p426-on-b1")
        assert doc["verdict"] == "VALID", doc["problems"]
        assert (w.wd / "p426" / "m1" / "p426-on-b1" / "report.json").exists()
        assert doc["pins"] == dict(json.loads(w.frozen.read_text()), frozen_sha=T.sha256_file(w.frozen))
        got[bool(flag)] = (sorted(doc), sorted(doc["state"]), sorted(p.name for p in rd.iterdir()))
    assert got[True] == got[False]


@pytest.fixture(scope="module")
def s_run(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    b = T.Box(mp)
    try:
        w = T.make_s_world(tmp_path_factory.mktemp("srun"))
        yield T.run_sequencer(w, b, T.s_argv(w, build="s"), mp)
    finally:
        b.close()
        mp.undo()


def test_under_s_every_leg_runs_valid_with_todays_names(s_run):
    """[I] §4: `--build s` = today's 30 legs, names, receipts."""
    assert s_run.rc == 0, s_run.why()
    assert T.launched_names(s_run.box) == [W.leg_name(*leg) for leg in W.schedule()] == T.s_leg_names()
    for n in T.s_leg_names():
        doc = T.receipt(s_run.world.out / "receipts", n)
        assert doc["verdict"] == "VALID", doc["problems"]
        assert set(doc) == (QUALIFY_KEYS if n.startswith("m1-") else LEG_KEYS) and set(doc["state"]) == STATE_KEYS


def test_under_s_the_leg_argv_is_byte_identical_and_carries_no_build(s_run):
    """[I] §4: 'the sequencer passes `--build` only when the label is not `s`'; today's exact argv and cwd."""
    w = s_run.world
    want = [[str(w.root / ".venv-bench" / "bin" / "python"), "-m", "bench.p426_leg", "--axis", a, "--arm", arm,
             *(["--smoke"] if sel == "smoke" else ["--block", str(sel)]), "--stack-root", str(w.root), "--workdir", str(w.wd),
             "--registry-on", str(w.overlay), "--receipt-dir", str(w.out / "receipts")] for a, arm, sel in W.schedule()]
    assert [x["argv"] for x in s_run.box.launches] == want
    assert {x["cwd"] for x in s_run.box.launches} == {str(w.root / "benchmark")}


def test_under_s_tunes_prefixes_m1_and_paths_are_todays(s_run):
    """[I] §4: tunes `p426-<arm>-…`, session prefix `p426-<leg>`, M1 `<wd>/p426/m1/<tune>`, dossiers `wave1/<leg>`, run files
    `wave1/run/{frozen.json, registry-on.yaml, sequence.log}`; no `wave1.s`, no `.build` marker."""
    w, b = s_run.world, s_run.box
    names = T.s_leg_names()
    assert sorted(d["prefix"] for d in b.drivers if d["prefix"]) == sorted(f"p426-{n}" for n in names if not n.startswith("m1-"))
    tunes = sorted(T._flag(d["argv"], "--tune") for d in b.drivers if T._flag(d["argv"], "--tune"))
    assert tunes == sorted(n.split("-", 1)[1] for n in names if n.split("-")[0] in ("math500", "cjudge"))
    assert sorted(p.name for p in (w.wd / "p426" / "m1").iterdir()) == sorted(n.split("-", 1)[1] for n in names
                                                                              if n.startswith("m1-"))
    wave1 = w.main / "benchmark" / "results" / "p426"
    assert sorted(p.name for p in wave1.iterdir()) == ["wave1"]
    assert sorted(p.name for p in (wave1 / "wave1").iterdir()) == sorted(names + ["run"])
    assert sorted(p.name for p in (wave1 / "wave1" / "run").iterdir()) == ["frozen.json", "registry-on.yaml", "sequence.log"]
    assert (wave1 / "wave1" / "run" / "frozen.json").read_bytes() == w.frozen.read_bytes()
    assert sorted(p.name for p in w.out.iterdir()) == sorted(["receipts", "sequence.log"] + [f"{n}.stdout" for n in names])
    assert not (w.wd / "p426" / "frozen.s.json").exists()
