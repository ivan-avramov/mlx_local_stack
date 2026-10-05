"""Review follow-up (C1, C2, C5, C6): the shared exit protocol (`provenance.ExitGuard`) in the
capacity / retrieval / reasoning drivers, and the reasoning journal sidecar that gates `--resume`.

The mocked ladders here INVOKE the persistence callbacks (`on_record` / `on_rung`), so journals
really exist when the run is refused."""
import json
import pathlib

import pytest

import bench.provenance as P
from bench import paths
from bench.tests import test_serving_state_drivers as SSD
from bench.tests.test_m50_entrypoints import _refusing

MODEL = SSD.MODEL
RR, RC, RT = SSD.RR, SSD.RC, SSD.RT


# --------------------------------------------------------------------------- scaffolding
class Router:
    """A controllable router owner: `pid` and the served file are what drift tests change."""

    def __init__(self, monkeypatch, tmp_path, pid=7):
        self.pid, self.tmp_path = pid, tmp_path
        monkeypatch.setattr(P, "router_owner", self.owner)

    def owner(self, port):
        return {"pid": self.pid, "cmdline": "mlx-serve start", "cwd": str(self.tmp_path),
                "env": {"MLX_SERVE_CONFIG": str(paths.registry_path())}}


def _setup(monkeypatch, tmp_path, name):
    mod, lad, canned, extra = SSD.DRIVERS[name]
    drv, calls, results = SSD._setup(monkeypatch, tmp_path, mod, lad, canned, [[SSD.GOOD]])
    return mod, lad, canned, extra, results / MODEL


def _argv(extra, *more):
    return SSD._argv(list(extra) + list(more))


def _cap_ladder(monkeypatch, mod, canned, after=None):
    """capacity ladder mock that writes the journal through the real on_record callback."""
    def ladder(*a, **k):
        for row in canned:
            k["on_record"](dict(row))
        if after:
            after()
        return canned
    monkeypatch.setattr(mod, "run_ladder", ladder)


def _rea_ladder(monkeypatch, mod, canned, after=None, seen=None):
    def ladder(*a, **k):
        if seen is not None:
            seen.append(k.get("resume"))
        for rec in canned:
            k["on_rung"](dict(rec))
        if after:
            after()
        return canned
    monkeypatch.setattr(mod, "run_reasoning_ladder", ladder)


def _names(d):
    return sorted(p.name for p in d.iterdir())


# --------------------------------------------------------------------------- C2: capacity
@pytest.mark.parametrize("mode", ["pid", "sha"])
def test_capacity_exit_drift_sets_aside_journal_and_scorecard_and_writes_no_manifest(
        monkeypatch, tmp_path, mode):
    mod, lad, canned, extra, out = _setup(monkeypatch, tmp_path, "capacity")
    r = Router(monkeypatch, tmp_path)

    def drift():
        if mode == "pid":
            r.pid = 8
        else:
            with open(paths.registry_path(), "a") as f:
                f.write("\n# edited\n")
    _cap_ladder(monkeypatch, mod, canned, after=drift)
    with pytest.raises(P.ServedConfigError, match="C106"):
        mod.main(_argv(extra))
    names = _names(out)
    assert not [n for n in names if n in ("capacity_ladder.jsonl", "capacity_retrieval.json",
                                          "capacity_ladder.manifest.json")]
    journal = list(out.glob("capacity_ladder.jsonl.refused-*"))
    scorecard = list(out.glob("capacity_retrieval.json.refused-*"))
    assert len(journal) == 1 and len(scorecard) == 1
    assert '"ctx"' in journal[0].read_text()                       # the real rows moved, not a stub
    assert "served_config_drift" in journal[0].read_text()
    assert "C106" in json.loads(scorecard[0].read_text())["served_config_drift"]["error"]


def test_capacity_late_serving_state_error_also_sets_both_aside(monkeypatch, tmp_path):
    mod, lad, canned, extra, out = _setup(monkeypatch, tmp_path, "capacity")
    _cap_ladder(monkeypatch, mod, canned)

    def boom(*a, **k):
        raise P.ServingStateError("C35 tripwire: changed late")
    monkeypatch.setattr(P, "gather", boom)
    with pytest.raises(P.ServingStateError):
        mod.main(_argv(extra))
    assert not (out / "capacity_ladder.jsonl").exists() and not (out / "capacity_retrieval.json").exists()
    assert len(list(out.glob("capacity_ladder.jsonl.refused-*"))) == 1
    assert len(list(out.glob("capacity_retrieval.json.refused-*"))) == 1


# --------------------------------------------------------------------------- C5: exception paths
@pytest.mark.parametrize("name", ["capacity", "reasoning", "retrieval"])
def test_an_exception_mid_run_keeps_the_original_and_stamps_drift(monkeypatch, tmp_path, name):
    mod, lad, canned, extra, out = _setup(monkeypatch, tmp_path, name)
    r = Router(monkeypatch, tmp_path)

    def ladder(*a, **k):
        if name == "capacity":
            k["on_record"](dict(canned[0]))
        elif name == "reasoning":
            k["on_rung"](dict(canned[0]))
        r.pid = 99                                   # the router is replaced, then the run dies
        raise ConnectionError("transport died")
    monkeypatch.setattr(mod, lad, ladder)
    with pytest.raises(ConnectionError, match="transport died"):
        mod.main(_argv(extra))
    stamped = [p for p in out.iterdir() if ".refused-" in p.name] if out.exists() else []
    if name == "retrieval":
        assert stamped == []                          # nothing existed yet: nothing to quarantine
        return
    else:
        assert stamped, "journal was not set aside after a drift on an exceptional exit"
        assert all("served_config_drift" in p.read_text() for p in stamped
                   if not p.name.endswith(".provenance.json.refused-x"))
    assert not [p for p in out.iterdir() if p.name.endswith((".json", ".jsonl"))
                and ".refused-" not in p.name and "provenance" not in p.name]


@pytest.mark.parametrize("name", ["retrieval", "reasoning"])
def test_late_gather_refusal_after_drift_stamps_the_quarantined_result(monkeypatch, tmp_path, name):
    mod, lad, canned, extra, out = _setup(monkeypatch, tmp_path, name)
    r = Router(monkeypatch, tmp_path)

    def late():
        r.pid = 55
    if name == "reasoning":
        _rea_ladder(monkeypatch, mod, canned, after=late)
    else:
        monkeypatch.setattr(mod, lad, lambda *a, **k: (late(), canned)[1])

    def boom(*a, **k):
        raise P.ServingStateError("C35 tripwire: changed late")
    monkeypatch.setattr(P, "gather", boom)
    with pytest.raises(P.ServingStateError, match="C35 tripwire"):
        mod.main(_argv(extra))
    aside = list(out.glob(f"{name}.json.refused-*"))
    assert len(aside) == 1
    assert "served_config_drift" in json.loads(aside[0].read_text())


@pytest.mark.parametrize("name", ["capacity", "reasoning", "retrieval"])
def test_a_failing_quarantine_never_replaces_the_original_exception(monkeypatch, tmp_path, name):
    mod, lad, canned, extra, out = _setup(monkeypatch, tmp_path, name)
    r = Router(monkeypatch, tmp_path)

    def ladder(*a, **k):
        if name == "capacity":
            k["on_record"](dict(canned[0]))
        elif name == "reasoning":
            k["on_rung"](dict(canned[0]))
        r.pid = 99
        raise KeyError("original")
    monkeypatch.setattr(mod, lad, ladder)
    monkeypatch.setattr(P, "set_aside_refused",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("rename failed")))
    with pytest.raises(KeyError, match="original"):
        mod.main(_argv(extra))


def test_exit_guard_verifies_even_when_the_body_dies_early(monkeypatch, tmp_path):
    Router(monkeypatch, tmp_path)
    entry = P.assert_served_config("http://localhost:8000")
    calls = []
    real = P.assert_served_config_unchanged
    monkeypatch.setattr(P, "assert_served_config_unchanged",
                        lambda *a, **k: calls.append(1) or real(*a, **k))
    with pytest.raises(ValueError, match="early"):
        with P.ExitGuard(entry, "http://localhost:8000"):
            raise ValueError("early")
    assert calls == [1]


# --------------------------------------------------------------------------- order pins (C6)
@pytest.mark.parametrize("name", ["capacity", "reasoning", "retrieval"])
def test_entry_check_precedes_every_request_and_leaves_existing_outputs_untouched(
        monkeypatch, tmp_path, name):
    mod, lad, canned, extra, out = _setup(monkeypatch, tmp_path, name)
    out.mkdir(parents=True, exist_ok=True)
    pre = {out / "reasoning.partial.jsonl": b'{"key": "k", "record": {"ctx": 1}}\n',
           out / "reasoning.partial.jsonl.provenance.json": b"{}"}
    for p, b in pre.items():
        p.write_bytes(b)
    monkeypatch.setattr(mod, "MlxServeDriver", lambda: pytest.fail("driver before the M50 check"))
    _refusing(monkeypatch)
    with pytest.raises(P.ServedConfigError, match="M50"):
        mod.main(_argv(extra, *(["--resume"] if name == "reasoning" else [])))
    assert {p: p.read_bytes() for p in pre} == pre
    assert [n for n in _names(out) if "refused" in n] == []


# --------------------------------------------------------------------------- C1: reasoning resume
def _first_run(monkeypatch, tmp_path, router_pid=7):
    mod, lad, canned, extra, out = _setup(monkeypatch, tmp_path, "reasoning")
    r = Router(monkeypatch, tmp_path, pid=router_pid)
    _rea_ladder(monkeypatch, mod, canned)
    assert mod.main(_argv(extra)) == 0
    return mod, canned, extra, out, r


def test_a_run_writes_the_journal_sidecar(monkeypatch, tmp_path):
    mod, canned, extra, out, r = _first_run(monkeypatch, tmp_path)
    side = json.loads((out / "reasoning.partial.jsonl.provenance.json").read_text())
    assert side["router"]["pid"] == 7 and side["router"]["config_sha256"]
    assert side["registry_sha256"] and side["fingerprint"] and side["manifest"]["sampling"]
    assert "attention_policy" in side["serving_controls"]


def test_resume_accepts_a_compatible_sidecar_and_records_router_history(monkeypatch, tmp_path):
    mod, canned, extra, out, r = _first_run(monkeypatch, tmp_path)
    r.pid = 8                                            # same served file, restarted router
    seen = []
    _rea_ladder(monkeypatch, mod, canned, seen=seen)
    assert mod.main(_argv(extra, "--resume")) == 0
    assert seen[0] and 8000 in seen[0]                   # the persisted rung was reused
    man = json.loads((out / "reasoning.manifest.json").read_text())
    assert [h["pid"] for h in man["router_history"]] == [7] and man["router"]["pid"] == 8
    side = json.loads((out / "reasoning.partial.jsonl.provenance.json").read_text())
    assert side["router"]["pid"] == 8 and [h["pid"] for h in side["router_history"]] == [7]


def test_resume_refuses_when_the_served_config_changed(monkeypatch, tmp_path):
    mod, canned, extra, out, r = _first_run(monkeypatch, tmp_path)
    with open(paths.registry_path(), "a") as f:
        f.write("\n# another overlay\n")
    journal = (out / "reasoning.partial.jsonl").read_bytes()
    monkeypatch.setattr(mod, "run_reasoning_ladder", lambda *a, **k: pytest.fail("ladder ran"))
    with pytest.raises(P.ServedConfigError, match="C1 resume refused"):
        mod.main(_argv(extra, "--resume"))
    assert (out / "reasoning.partial.jsonl").read_bytes() == journal    # not quarantined, not touched


def test_resume_refuses_an_incompatible_manifest(monkeypatch, tmp_path):
    mod, canned, extra, out, r = _first_run(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "run_reasoning_ladder", lambda *a, **k: pytest.fail("ladder ran"))
    with pytest.raises(P.ServedConfigError, match="C1 resume refused"):
        mod.main(_argv(extra, "--resume", "--temp", "0.77"))


def test_resume_refuses_a_journal_without_a_sidecar(monkeypatch, tmp_path):
    mod, canned, extra, out, r = _first_run(monkeypatch, tmp_path)
    (out / "reasoning.partial.jsonl.provenance.json").unlink()
    monkeypatch.setattr(mod, "run_reasoning_ladder", lambda *a, **k: pytest.fail("ladder ran"))
    with pytest.raises(P.ServedConfigError, match="missing"):
        mod.main(_argv(extra, "--resume"))
    assert (out / "reasoning.partial.jsonl").exists()


# --------------------------------------------------------------------------- D1: no append to a journal
def test_a_fresh_run_refuses_an_existing_journal_and_changes_nothing(monkeypatch, tmp_path):
    mod, canned, extra, out, r = _first_run(monkeypatch, tmp_path)
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    monkeypatch.setattr(mod, "MlxServeDriver", lambda: pytest.fail("driver built"))
    monkeypatch.setattr(mod, "run_reasoning_ladder", lambda *a, **k: pytest.fail("ladder ran"))
    with pytest.raises(SystemExit, match="--resume or a fresh --out-tag"):
        mod.main(_argv(extra))
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before


def test_a_fresh_run_refuses_a_leftover_sidecar_alone(monkeypatch, tmp_path):
    mod, canned, extra, out, r = _first_run(monkeypatch, tmp_path)
    (out / "reasoning.partial.jsonl").unlink()
    with pytest.raises(SystemExit, match="--resume or a fresh --out-tag"):
        mod.main(_argv(extra))
    assert (out / "reasoning.partial.jsonl.provenance.json").exists()


def test_a_fresh_out_tag_is_not_blocked_by_another_tags_journal(monkeypatch, tmp_path):
    mod, canned, extra, out, r = _first_run(monkeypatch, tmp_path)
    assert mod.main(_argv(extra, "--out-tag", "t2")) == 0
    assert (out / "reasoning.t2.partial.jsonl").exists()


# --------------------------------------------------------------------------- D3: gather -> verify -> publish
@pytest.mark.parametrize("name", ["capacity", "retrieval", "reasoning"])
def test_an_overlay_change_during_gather_is_caught_and_the_run_refused(monkeypatch, tmp_path, name):
    mod, lad, canned, extra, out = _setup(monkeypatch, tmp_path, name)
    Router(monkeypatch, tmp_path)
    if name == "capacity":
        _cap_ladder(monkeypatch, mod, canned)
    elif name == "reasoning":
        _rea_ladder(monkeypatch, mod, canned)
    real_gather = P.gather

    def gather(*a, **k):
        man = real_gather(*a, **k)
        with open(paths.registry_path(), "a") as f:
            f.write("\n# overlay changed while gathering\n")
        return man
    monkeypatch.setattr(P, "gather", gather)
    canonical_at_verify = []
    real_verify = P.assert_served_config_unchanged

    def verify(*a, **k):
        canonical_at_verify.append((out / "capacity_retrieval.json").exists())
        return real_verify(*a, **k)
    monkeypatch.setattr(P, "assert_served_config_unchanged", verify)
    with pytest.raises(P.ServedConfigError, match="C106"):
        mod.main(_argv(extra))
    assert canonical_at_verify == [False] * len(canonical_at_verify) and canonical_at_verify
    canon = [p.name for p in out.iterdir() if p.name.endswith((".json", ".jsonl"))
             and ".refused-" not in p.name and "provenance" not in p.name]
    assert canon == []


# --------------------------------------------------------------------------- D4 / D5: guard cleanup
def _drift_guard(monkeypatch, tmp_path):
    r = Router(monkeypatch, tmp_path)
    entry = P.assert_served_config("http://localhost:8000")
    r.pid = 8                                            # drift: exit check will refuse
    return P.ExitGuard(entry, "http://localhost:8000", label="t")


def test_malformed_artifact_json_is_still_moved_aside(monkeypatch, tmp_path):
    art = tmp_path / "x.json.pending-1"
    art.write_text("{not json")
    g = _drift_guard(monkeypatch, tmp_path)
    g.track(art, tmp_path / "x.json")
    with pytest.raises(ValueError, match="orig"):
        with g:
            raise ValueError("orig")
    assert not art.exists() and not (tmp_path / "x.json").exists()
    aside = [p for p in tmp_path.glob("x.json.refused-*") if not p.name.endswith(".stamp-error")]
    assert len(aside) == 1 and aside[0].read_text() == "{not json"
    assert list(tmp_path.glob("x.json.refused-*.stamp-error"))


def test_a_failing_drift_append_still_moves_the_journal_aside(monkeypatch, tmp_path):
    art = tmp_path / "j.jsonl"
    art.write_text('{"ctx": 1}\n')
    art.chmod(0o444)                                    # append fails
    g = _drift_guard(monkeypatch, tmp_path)
    g.track(art)
    with pytest.raises(ValueError, match="orig"):
        with g:
            raise ValueError("orig")
    assert not art.exists()
    assert len(list(tmp_path.glob("j.jsonl.refused-*"))) >= 1
    assert list(tmp_path.glob("j.jsonl.refused-*.stamp-error"))


def test_a_print_raising_broken_pipe_never_replaces_the_original_exception(monkeypatch, tmp_path):
    art = tmp_path / "x.json"
    art.write_text("{}")
    g = _drift_guard(monkeypatch, tmp_path)
    g.track(art)

    def boom(*a, **k):
        raise BrokenPipeError("stdout closed")
    monkeypatch.setattr("builtins.print", boom)
    with pytest.raises(ValueError, match="orig"):
        with g:
            raise ValueError("orig")
    assert not art.exists() and len(list(tmp_path.glob("x.json.refused-*"))) == 1


def test_a_broken_pipe_on_the_verification_warning_is_swallowed(monkeypatch, tmp_path):
    Router(monkeypatch, tmp_path)
    entry = P.assert_served_config("http://localhost:8000")
    monkeypatch.setattr(P, "assert_served_config_unchanged",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("lsof exploded")))
    monkeypatch.setattr("builtins.print",
                        lambda *a, **k: (_ for _ in ()).throw(BrokenPipeError("closed")))
    with pytest.raises(KeyError, match="orig"):
        with P.ExitGuard(entry, "http://localhost:8000"):
            raise KeyError("orig")
