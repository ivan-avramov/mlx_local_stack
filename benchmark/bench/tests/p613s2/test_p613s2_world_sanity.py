"""Sanity of the synthetic Wave 1 world itself (independent of the code under test): the fixtures must look like the committed
data, so a failure of the real tests is the code's, not the fixture's. Class of every test is stated above it."""
from __future__ import annotations

import hashlib
import json

from bench.tests.p613s2 import wave1world as WW


def jl(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


# class: invariant (the world has the committed layout: 5 kinds x 2 blocks x 2 arms legs + smokes + archive + S build)
def test_world_layout(make_w1):
    w = make_w1()
    for kind in WW.KINDS:
        for block in WW.BLOCKS:
            for arm in WW.ARMS:
                assert w.path_of(kind, arm, block, "receipt").is_file()
                assert w.path_of(kind, arm, block, "scrub").is_file()
    assert (w.w1 / "run" / "frozen.s2.json").is_file()
    assert (w.w1 / "archive").is_dir() and (w.w1 / "math500-p426s2-on-smoke").is_dir() and (w.p426 / "wave1").is_dir()
    assert (w.p426 / "ids.json").is_file()


# class: invariant (the A1 score.json the fixture writes is the repo grader's own output on the rows: n / errors / correct / acc_strict)
def test_math_score_is_the_graders_output(make_w1):
    w = make_w1(rows={("math500", "on", "b1"): {"test/algebra/2.json": {"ok": False}, "test/algebra/3.json": dict(WW.NONCONV)}})
    score = json.loads(w.path_of("math500", "on", "b1", "score").read_text())
    assert (score["n"], score["errors"], score["correct"]) == (5, 0, 4)
    assert score["acc"] == 0.8 and score["acc_strict"] == 0.6      # item 3 is correct but a budget hit: strict 0
    assert score["conv_rate"] == 0.8 and score["nonconv_kinds"] == {"budget_hit": 1}


# class: invariant (SCRUB manifests re-verify; frozen sha equals the receipts' pins.frozen_sha and state.frozen_sha)
def test_scrub_and_frozen_are_consistent(make_w1):
    w = make_w1()
    fsha = hashlib.sha256((w.w1 / "run" / "frozen.s2.json").read_bytes()).hexdigest()
    for kind in WW.KINDS:
        for arm in WW.ARMS:
            rec = json.loads(w.path_of(kind, arm, "b1", "receipt").read_text())
            assert rec["pins"]["frozen_sha"] == rec["state"]["frozen_sha"] == fsha
            files = json.loads(w.path_of(kind, arm, "b1", "scrub").read_text())["files"]
            assert files
            for path, d in files.items():
                assert path.startswith("benchmark/results/")
                data = (w.rows_root / path[len("benchmark/results/"):]).read_bytes()
                assert hashlib.sha256(data).hexdigest() == d["published_sha256"]


# class: invariant (ON and OFF worker cmdlines differ by exactly the three restore-delta flags, besides PID and worktree path)
def test_cmdlines_differ_by_the_three_flags(make_w1):
    w = make_w1()
    off = json.loads(w.path_of("math500", "off", "b1", "receipt").read_text())["worker"]["cmdline"]
    on = json.loads(w.path_of("math500", "on", "b1", "receipt").read_text())["worker"]["cmdline"]
    split = lambda s, arm: sorted(p.strip().replace(f"stack-p426-s2-{arm}", "stack-p426-s2-ARM") for p in s.split(" --")[1:])
    assert not set(split(off, "off")) - set(split(on, "on"))
    assert set(split(on, "on")) - set(split(off, "off")) == {"mtp-verify-scan joint_v1", "draft-kind mtp",
                                                              f"draft-model {WW.DRAFTER}"}


# class: invariant (the tiny repo: three commits, the registry blob shas are the frozen record's, gitlinks are commit entries)
def test_repo_commits_and_registry(make_w1):
    w = make_w1()
    fr = json.loads((w.w1 / "run" / "frozen.s2.json").read_text())
    assert fr["registry_off_sha"] != fr["registry_on_sha"]
    assert len({w.commits["w1_off"], w.commits["w1_on"], w.commits["w2_off"]}) == 3
    assert WW.git(w.repo, "ls-tree", w.commits["w2_off"], "src/mlx-vlm").startswith("160000 commit")


# class: invariant (same spec, different base directory -> the same commit shas and the same frozen record bytes)
def test_worlds_are_deterministic(tmp_path, monkeypatch):
    a = WW.Wave1World(tmp_path / "a", monkeypatch)
    b = WW.Wave1World(tmp_path / "b", monkeypatch)
    assert a.commits == b.commits
    assert (a.w1 / "run" / "frozen.s2.json").read_bytes() == (b.w1 / "run" / "frozen.s2.json").read_bytes()


# ----------------------------------------------------------------------------------- the hand numbers of the scenarios
# class: invariant (scenario S: the hand-computed vectors, counts, dropped keys, acceptance and identity numbers the signals tests rely on)
def test_scenario_s_hand_numbers(make_w1):
    from bench.tests.p613s2 import test_p613s2_signals_stats as ST
    w = make_w1(**ST.S_SPEC)
    ids1, on1, off1 = ST.vecs(w, "b1", 0)
    _, on1s, off1s = ST.vecs(w, "b1", 1)
    _, on2, off2 = ST.vecs(w, "b2", 0)
    assert (sum(on1), sum(off1), sum(on1s), sum(off1s)) == (7, 6, 6, 6)
    assert (sum(on2), sum(off2)) == (5, 7)
    ids, on, off = ST.both(w, 1)
    assert len(ids) == 16 and sum(on) == 11 and sum(off) == 13
    on_ = {r["id"]: r["content"] for r in w.read_rows("math500", "on", "b1")}
    off_ = {r["id"]: r["content"] for r in w.read_rows("math500", "off", "b1")}
    assert sum(1 for k in on_ if on_[k] == off_[k]) == 6
    assert ST.tps_ratios(w, "math500", "b1")[1] == [ST.a(5)] and ST.tps_ratios(w, "math500", "b2")[1] == [ST.a(12)]
    assert ST.accept(w.read_rows("math500", "on", "b1"))[1:] == (660, 900) and ST.accept(w.read_rows("math500", "on", "b2"))[1:] == (610, 750)
    assert ST.accept(w.read_rows("vision", "on", "b1"))[1:] == (144, 200) and ST.accept(w.read_rows("vision", "on", "b2"))[1:] == (122, 200)
    assert ST.accept(w.read_rows("reasoning", "on", "b1"))[0] == 0.75 and ST.accept(w.read_rows("reasoning", "on", "b2"))[0] == 0.9
    assert ST.accept(w.read_rows("cjudge", "on", "b2"))[1:] == (190, 300)
    assert sorted(ST.tps_ratios(w, "reasoning", "b1", key=lambda r: r["seed"])[0]) == [1.5, 1.5]
    score = json.loads(w.path_of("math500", "on", "b1", "score").read_text())
    assert score["nonconv_kinds"] == {"budget_hit": 1} and score["conv_rate"] == 0.875


# class: invariant (scenario F: 8 OFF-only strict solves over both blocks, nothing else differs; the rows are valid for the grader)
def test_scenario_f_hand_numbers(make_w1):
    from bench.tests.p613s2 import test_p613s2_signals_flags as FL
    from bench.tests.p613s2 import w1view as V
    w = make_w1(**FL.F_SPEC)
    diffs = V.a1_strict_diffs(w)
    assert len(diffs) == 20 and sorted(diffs) == [-1.0] * 8 + [0.0] * 12
    sc = json.loads(w.path_of("math500", "on", "b2", "score").read_text())
    assert sc["correct"] == 6 and sc["nonconv_kinds"] == {"budget_hit": 1}


# class: invariant (scenario NB: strict delta exactly -1 / 20 in b1 and 0 in b2; a(2) is a budget hit in BOTH arms)
def test_scenario_nb_hand_numbers(make_w1):
    from bench.tests.p613s2 import test_p613s2_signals_flags as FL
    from bench.tests.p613s2 import w1view as V
    w = make_w1(**FL.NB_SPEC)
    d = V.a1_strict_diffs(w)
    assert len(d) == 40 and sum(d) == -1.0
    for arm in ("off", "on"):
        assert json.loads(w.path_of("math500", arm, "b1", "score").read_text())["nonconv_kinds"] == {"budget_hit": 1}
    assert json.loads(w.path_of("m1", "off", "b2", "result").read_text())["requests"][0]["qualify"]["peaks"]["prefill"] == 47_000_000_000


# class: invariant (the permutation oracle: the exact tail of eight equal-sign differences over 20 items is 2 / 2^8)
def test_exact_tail_oracle_for_the_holm_flag():
    from bench.tests.p613 import sigview as SV
    assert abs(SV.exact_perm_tail([-1.0] * 8) - 2 / 256) < 1e-12      # zero differences add nothing to the sign-flip tail
