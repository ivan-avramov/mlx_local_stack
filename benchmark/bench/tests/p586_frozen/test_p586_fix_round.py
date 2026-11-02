"""Fix round 1 (fixlist.adopted.md X1–X8): one test group per adopted defect, built from its reproducible failing case and the spec,
through the same seams as the rest of this directory (the done hook / `reconcile_item` with `ClientEvidence`, `p426_freeze.main`,
`p426_leg.main`'s captured `clock` / `battery_intervals`, `harvest_wave2` / the harvest CLI) — not from the implementer's tests.

Classes: [R] reproduces the adopted defect (red on the round-0 candidate), [I] preserves an invariant, [N] new behaviour the
finding adds. A test can be red on the baseline only because the P586 interface is missing there; that is noted per group."""
from __future__ import annotations

import calendar
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import p426_freeze as fz
from bench import p426_hooks as ph
from bench import p426_leg
from bench import p426_reconcile as pr


def _sibling(name):
    """A sibling module of this directory, loaded by path (this directory is not a package)."""
    spec = importlib.util.spec_from_file_location(f"p586_frozen_sibling_{name}", Path(__file__).with_name(f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


FAILED_LINE = b"2026-11-01 01:17:02,001 - mlx_vlm.server - WARNING - Request failed"


def _export_and_row(kit, mutate):
    """The fixture export changed by `mutate(doc)`, and the fixture row whose `evidence_sha256.export` is the changed bytes' sha
    (so only the changed fact differs, never the sha check)."""
    doc = kit.export_doc()
    mutate(doc)
    body = json.dumps(doc, indent=2).encode()
    r = kit.row()
    r["evidence_sha256"]["export"] = hashlib.sha256(body).hexdigest()
    return body, r


def _client_failing(rec):
    return [k for k, v in rec["checks"].items() if k.startswith("client_abort_") and not v["ok"]]


# =============================================================================================== X1 — the close gap from two clocks
def test_x1_a_pause_across_the_fall_back_is_refused_whatever_the_local_stamps_say(tmp_path, kit):
    """[R] X1 (sol-1's scenario): one telemetry line (elapsed 22.5 s), then nothing until the client's abort, 3622.6 s later by
    the export's wall time; the local stamps read 01:59:59 (PDT) -> 02:00:21 (PST), a naive 22 s. The round-0 candidate accepted it
    (its gap was the naive stamp difference). Red on the baseline too (no P586 path)."""
    data = kit.window_keeping_telemetry(1)
    (only,) = kit.telemetry(data)
    data = kit.restamp(data, only.stamp.encode() + b" - mlx_vlm.server - INFO - Stream Telemetry", "2026-11-01 01:59:59,001")
    data = kit.restamp(data, FAILED_LINE, "2026-11-01 02:00:21,001")
    assert kit.FIXTURE_WALL_S - only.elapsed_s > 3600
    disp, rec, _ = kit.run_fixture_item(tmp_path, window=data)
    assert disp.kind == "invalidate" and rec["verdict"] == "invalid"
    assert kit.names_condition(_client_failing(rec), "b"), rec["checks"]


def test_x1_the_real_item_is_still_accepted_and_its_gap_is_the_two_clock_difference(tmp_path, kit):
    """[I] X1: the leg-3 item (gap 3645.065 - 3643.5 = 1.565 s) stays `kill_client_aborted`; a ClientEvidence carrying that gap is
    accepted and one carrying the naive-stamp 1.293 s is accepted too (both within the bound: the bound, not the value, decides)."""
    disp, rec, _ = kit.run_fixture_item(tmp_path)
    assert disp.kind == "accept" and rec["case"] == "kill_client_aborted", rec["problems"]
    assert kit.FIXTURE_CLOSE_GAP_X1_S == pytest.approx(1.565)
    assert kit.reconcile_fixture(close_gap_s=kit.FIXTURE_CLOSE_GAP_X1_S).ok


def test_x1_wall_s_absent_fails_and_never_raises(tmp_path, kit):
    """[R] X1 / X3: the aborted message without `time.created` (sha recomputed): no wall time, so no close gap -> the hook
    invalidates (continuity and provenance), never an exception (round 0: `KeyError` out of the hook)."""
    body, r = _export_and_row(kit, lambda d: kit.last_assistant(d)["time"].pop("created"))
    disp, rec, _ = kit.run_fixture_item(tmp_path, r=r, export=body)
    assert disp.kind == "invalidate" and rec["verdict"] == "invalid"
    failing = _client_failing(rec)
    assert kit.names_condition(failing, "b") and kit.names_condition(failing, "a"), rec["checks"]


# =============================================================================================== X2 — the export belongs to the row
def _x2_reports(kit):
    def foreign_id(d):
        d["info"]["id"] = "ses_someone_else"

    def usage_absent(d):
        [m for m in d["messages"] if m.get("type") == "assistant"][0]["id"] = "msg_not_the_rows"

    def usage_order_swapped(d):
        a = [m for m in d["messages"] if m.get("type") == "assistant"]
        a[0]["id"], a[1]["id"] = a[1]["id"], a[0]["id"]
    return dict(foreign_id=foreign_id, usage_absent=usage_absent, usage_order_swapped=usage_order_swapped)


@pytest.mark.parametrize("flip", ["foreign_id", "usage_absent", "usage_order_swapped"])
def test_x2_an_export_that_is_not_the_rows_fails_provenance(kit, flip):
    """[R] X2: (a) also requires `export.info.id == row.session_id` and every `request_usage` message id among the export's
    assistant ids, in order, before the aborted one. The export alone is changed and its sha is taken as matching (`sha_ok=True`):
    the round-0 candidate accepted all three."""
    doc = kit.export_doc()
    _x2_reports(kit)[flip](doc)
    r = kit.reconcile_fixture(export=doc)
    assert r.ok is False and kit.names_condition(kit.failing_client_checks(r), "a"), r.checks


def test_x2_the_aborted_message_is_not_a_usage_message(kit):
    """[R] X2: a `request_usage` entry naming the aborted (last assistant) message itself is not "before the aborted one"."""
    r = kit.row()
    r["request_usage"][-1][0] = kit.last_assistant(kit.export_doc())["id"]
    rep = kit.reconcile_fixture(r=r)
    assert rep.ok is False and kit.names_condition(kit.failing_client_checks(rep), "a"), rep.checks


def test_x2_a_foreign_export_with_its_own_sha_is_refused_at_the_hook(tmp_path, kit):
    """[R] X2 through the hook, the failed variant: the leg-3 export with another `info.id`, the row's export sha recomputed for
    it (the sha check passes) -> invalidate on provenance."""
    body, r = _export_and_row(kit, lambda d: d["info"].update(id="ses_someone_else"))
    disp, rec, _ = kit.run_fixture_item(tmp_path, r=r, export=body)
    assert disp.kind == "invalidate" and kit.names_condition(_client_failing(rec), "a"), rec["checks"]


# =============================================================================================== X3 — validated times
@pytest.mark.parametrize("field, value", [("created", None), ("created", "1793520977003"), ("created", 1793524622069),
                                          ("created", 1793520977003.5), ("created", True), ("completed", None),
                                          ("completed", "1793524622068")],
                         ids=["created-missing", "created-text", "created-after-completed", "created-float", "created-bool",
                              "completed-missing", "completed-text"])
def test_x3_bad_message_times_fail_provenance_and_never_raise(kit, field, value):
    """[R] X3: `time.created` and `time.completed` must both be ints with created <= completed; otherwise (a) fails, `ok=False`,
    no exception, no `client_abort` block (round 0: the block raised `KeyError` / `TypeError` or used an unvalidated value)."""
    doc = kit.export_doc()
    t = kit.last_assistant(doc)["time"]
    if value is None:
        t.pop(field)
    else:
        t[field] = value
    rep = kit.reconcile_fixture(export=doc)
    assert rep.ok is False and kit.names_condition(kit.failing_client_checks(rep), "a"), rep.checks
    assert getattr(rep, "client_abort", None) is None


def test_x3_the_block_carries_the_validated_wall_time(tmp_path, kit):
    """[I] X3: on the real item the block's `wall_s` is the validated (completed - created) / 1000, a float."""
    disp, rec, _ = kit.run_fixture_item(tmp_path)
    assert disp.kind == "accept"
    assert isinstance(rec["client_abort"]["wall_s"], float) and rec["client_abort"]["wall_s"] == pytest.approx(kit.FIXTURE_WALL_S)


# =============================================================================================== X4 — the freeze's own probe-kill tuple
def _freeze_world(tmp_path, monkeypatch):
    R = _sibling("test_p586_rehearsal")
    wd = tmp_path / "wd"
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    off, on = wd / "p426" / "stack-p426-off", wd / "p426" / "stack-p426-on"
    for wt in (off, on):
        pins = wt / "src/mlx-vlm/dev/p369_phase2/pins.json"
        pins.parent.mkdir(parents=True)
        pins.write_text('{"pins": true}')
    world = dict(wd=wd, off=off, on=on, ops=R.FOps(wd, off, on), rehearsal=wd / "p426" / "rehearsal", rec=wd / "p426" / "record")
    return R, world


def _v8_with_r3_case(tmp_path, monkeypatch, capsys, case):
    R, world = _freeze_world(tmp_path, monkeypatch)
    manifest = world["rehearsal"] / "manifest.json"
    rc, err = R._run(["rehearsal", "--off-worktree", world["off"], "--on-worktree", world["on"], "--out-root",
                      world["rehearsal"] / "stage", "--out", manifest], world["ops"], capsys)
    assert rc == 0, err
    legs = R._legs(world)
    n = 0
    for p in sorted((Path(legs["r3"]) / "items").glob("*.json")):
        if p.name.endswith((".ready.json", ".dnf.json")):
            continue
        doc = json.loads(p.read_text())
        if str(doc.get("case", "")).startswith("kill"):
            p.write_text(json.dumps(ph.seal(dict(doc, case=case)), indent=1, sort_keys=True) + "\n")
            n += 1
    assert n == 1, "premise: R3's tree has exactly one kill item"
    out = world["rec"] / "v8_base.json"
    rc, err = R._run(["v8", "--off-worktree", world["off"], "--on-worktree", world["on"], "--rehearsal-manifest", manifest,
                      "--r1-off", legs["r1_off"], "--r1-on", legs["r1_on"], "--r2", legs["r2"], "--r3", legs["r3"], "--out", out],
                     world["ops"], capsys)
    return rc, err, out


@pytest.mark.parametrize("case", ["kill_client_aborted", "kill_client_aborted_completed_unaccounted"])
def test_x4_an_r3_whose_only_kill_case_is_a_client_abort_is_refused(tmp_path, monkeypatch, capsys, case):
    """[R] X4: R3 certifies the PROBE's kill; an R3 tree whose only kill case is a client-abort case is refused naming R3 (round 0
    accepted it through `prc.KILL_CASES`). Passes on the baseline (its freeze tuple is the probe-kill one)."""
    rc, err, out = _v8_with_r3_case(tmp_path, monkeypatch, capsys, case)
    assert rc == 2 and err.startswith("REFUSED:") and "R3" in err
    assert not out.exists()


@pytest.mark.parametrize("case", ["kill_boundary", "kill_inflight_failed", "kill_completed_unaccounted"])
def test_x4_a_probe_kill_case_is_accepted(tmp_path, monkeypatch, capsys, case):
    """[I] X4: each of the three probe-kill cases still certifies R3."""
    rc, err, out = _v8_with_r3_case(tmp_path, monkeypatch, capsys, case)
    assert rc == 0, err
    assert out.exists()


# =============================================================================================== X5 / X6 — the leg's battery seam and stamps
def _captured(tmp_path, monkeypatch):
    D = _sibling("test_p586_dst")
    return D, D._capture_leg_main(tmp_path, monkeypatch)


def test_x5_a_monkeypatched_subprocess_run_reaches_the_battery_closure(tmp_path, monkeypatch, los_angeles, no_path_leak):
    """[R] X5: `main`'s battery closure resolves `subprocess.run` at call time: a fake installed AFTER `main` built the closure is
    the one that runs, and no real process starts (round 0: the default bound at import ran the real `pmset -g log`, which stalled
    the suite). Passes on the baseline (its closure called `subprocess.run` directly)."""
    D, (captured, windows) = _captured(tmp_path, monkeypatch)
    ran = []

    def fake_run(argv, **kw):
        ran.append(list(argv))
        return SimpleNamespace(returncode=0, stdout=D.PMSET, stderr="")

    def no_popen(*a, **k):
        raise AssertionError("a real process started")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", no_popen)
    rep, s, e = D._stamps(captured, D.SUMMER_START, D.SUMMER_END)          # outside DST: only the seam is under test here
    captured["battery_intervals"](s, e)
    assert ran == [["pmset", "-g", "log"]]
    assert windows                                                             # the fake's output reached the fork's parser


MARKED = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


def test_x6_the_leg_clock_writes_marked_utc_stamps(tmp_path, monkeypatch, los_angeles, no_path_leak):
    """[R] X6: the leg receipt's `started` / `ended` come from `main`'s clock: `YYYY-MM-DDTHH:MM:SSZ`, UTC, now (round 0: an
    unmarked UTC text, the same format as the baseline's local one). Red on the baseline (local, unmarked)."""
    _D, (captured, _w) = _captured(tmp_path, monkeypatch)
    stamp = captured["clock"]()
    assert isinstance(stamp, str) and MARKED.fullmatch(stamp), stamp
    assert abs(calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")) - time.time()) < 300


@pytest.mark.parametrize("bad", ["2026-11-01 08:14:12", "2026-11-01T08:14:12", "2026-11-01 08:14:12Z"])
def test_x6_an_unmarked_stamp_is_refused_never_guessed(tmp_path, monkeypatch, los_angeles, no_path_leak, bad):
    """[R] X6: an unmarked (or half-marked) text is a `ValueError` in `watch_problems` and in the battery closure, never read as
    local or UTC (round 0 read it as UTC; the baseline as local). The other end is the leg clock's OWN stamp, so the test cannot
    pass merely because the code fails to read the marked form."""
    _D, (captured, _w) = _captured(tmp_path, monkeypatch)
    good = captured["clock"]()
    with pytest.raises(ValueError):
        p426_leg.watch_problems(dict(ticks=99, power_failure=None, exited_early=False), bad, good)
    with pytest.raises(ValueError):
        captured["battery_intervals"](bad, good)


def test_x6_the_clocks_own_stamps_round_trip(tmp_path, monkeypatch, los_angeles, no_path_leak):
    """[N] X6: two stamps of the leg's own clock are accepted by `watch_problems` (a 0-s leg needs 0 ticks)."""
    _D, (captured, _w) = _captured(tmp_path, monkeypatch)
    s = captured["clock"]()
    assert [p for p in p426_leg.watch_problems(dict(ticks=0, power_failure=None, exited_early=False), s, s) if "tick" in p] == []


# =============================================================================================== X7 — Go telemetry counters in a run HOME
GO_DIR = "home/Library/Application Support/go/telemetry/local"
GO_NAMES = [f"{n}@go1.27.3-go1.27.3-darwin-arm64-2026-11-01.v1.count" for n in ("compile", "asm", "go", "link", "vet")]


def _go_world(kit, tmp_path):
    w = kit.World(tmp_path)
    for n in GO_NAMES:
        kit.put(w.run / GO_DIR / n, f"counters of {n}\n".encode())
    return w


def _private_digest(base):
    files = sorted((p.relative_to(base).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
                   for p in base.rglob("*") if p.is_file())
    return len(files), hashlib.sha256("".join(f"{r}\t{s}\n" for r, s in files).encode()).hexdigest(), files


def test_x7_the_five_real_go_counter_names_harvest_cleanly(tmp_path, kit):
    """[R] X7 (leg 3's real names): the harvest commits; HARVEST.json names no counter file (the email gate read
    `compile@go1.27.3-…` as an address); one entry for the private run directory. Red on the baseline and round 0."""
    w = _go_world(kit, tmp_path)
    doc = w.harvest()
    text = (w.main / kit.WAVE2 / kit.NAME / "HARVEST.json").read_text()
    assert "@go1.27.3" not in text
    assert [f["source"] for f in doc["files"] if f.get("exclusion_reason") == "private_state"] == [f"run:{kit.RUN_ID}/home/"]


def test_x7_the_folded_entry_has_the_count_and_the_digest_and_the_list_goes_to_evidence(tmp_path, kit):
    """[N] X7: `{source: run:<id>/home/, destination: excluded, reason: private_state, files: count, sha256: sha256 of the sorted
    "<relpath>\\t<sha256>\\n" lines}` (relpath read as below the private directory — the spec does not say below which root); the
    per-file list is `<attempt>/excluded_private_state.json` in the EVIDENCE stage only, holding every relpath."""
    w = _go_world(kit, tmp_path)
    doc = w.harvest()
    (home,) = [f for f in doc["files"] if f.get("exclusion_reason") == "private_state"]
    count, digest, files = _private_digest(w.run / "home")
    assert home["destination"] == "excluded" and home["published"] is None
    assert home["files"] == count == 6 and home["sha256"] == digest
    listing = json.loads((w.stage / kit.WAVE2 / kit.NAME / "excluded_private_state.json").read_text())
    text = json.dumps(listing)                                    # the list's layout is the implementer's; its content is the spec's
    assert all(r in text and s in text for r, s in files), text[:500]
    assert not (w.main / kit.WAVE2 / kit.NAME / "excluded_private_state.json").exists()


def test_x7_the_dry_run_over_the_same_tree_is_clean(tmp_path, kit, capsys):
    """[R] X7: `--dry-run` (CLI) over that tree: rc 0, nothing written (round 0: rc 4, `HARVEST.json: quarantined … (email)`)."""
    w = _go_world(kit, tmp_path)
    kit.harvest_box(tmp_path)
    snap = kit.tree_snapshot(tmp_path)
    box = kit.harvest_box(tmp_path)
    rc = __import__("bench.p426_harvest", fromlist=["main"]).main(
        ["wave2", "--leg-root", str(w.root), "--main-root", str(w.main), "--evidence-stage", str(w.stage), "--dry-run"], **box)
    assert rc == 0, capsys.readouterr().err
    assert kit.tree_snapshot(tmp_path) == snap


def test_x7_a_foreign_address_in_a_main_bound_record_still_refuses(tmp_path, kit):
    """[I] X7: the email gate is unchanged: a foreign address in a `main` record still refuses, nothing published."""
    from bench import p426_harvest as H
    w = _go_world(kit, tmp_path)
    with (w.root / "watch.jsonl").open("a") as f:
        f.write(json.dumps(dict(note="write to someone@elsewhere.net")) + "\n")
    with pytest.raises(H.HarvestError):
        w.harvest()
    assert not (w.main / kit.WAVE2).exists() or not any((w.main / kit.WAVE2).iterdir())


def test_x7_other_exclusions_stay_per_file(tmp_path, kit):
    """[I] X7: an exclusion that is not `private_state` (a leg root's `tmp/uv-<hex>.lock`) keeps its own per-file entry."""
    w = kit.World(tmp_path)
    kit.put(w.root / "tmp" / "uv-0123abcd.lock", b"")
    doc = w.harvest()
    (lock,) = [f for f in doc["files"] if f["source"] == "leg:tmp/uv-0123abcd.lock"]
    assert lock["destination"] == "excluded" and "files" not in lock


# =============================================================================================== X8 — the harvest namespace
NS = "wave2.v8-af0711cf"


def test_x8_a_namespace_moves_every_destination_and_published_path(tmp_path, kit):
    """[N] X8: `namespace="wave2.v8-af0711cf"` publishes under `benchmark/results/p426/wave2.v8-af0711cf/<attempt>/` (main and
    evidence), every published path below it, nothing under `wave2/`. Red on the baseline (no keyword)."""
    w = kit.World(tmp_path)
    doc = w.harvest(namespace=NS)
    base = f"benchmark/results/p426/{NS}/{kit.NAME}"
    assert (w.main / base / "HARVEST.json").is_file() and (w.stage / base / "RUNLOG.md").is_file()
    assert all(f["published"].startswith(base + "/") for f in doc["files"] if f["published"])
    assert not (w.main / kit.WAVE2).exists() and not (w.stage / kit.WAVE2).exists()


@pytest.mark.parametrize("ns", ["../x", "wave3", "wave2/", "wave2.", "wave2.Upper", "wave2.a/b", ""])
def test_x8_an_invalid_namespace_is_refused_and_nothing_is_published(tmp_path, kit, ns):
    """[N] X8: anything but `wave2` / `wave2.<label>` (label `[a-z0-9][a-z0-9.-]*`) refuses before anything is written."""
    from bench import p426_harvest as H
    w = kit.World(tmp_path)
    with pytest.raises(H.HarvestError):
        w.harvest(namespace=ns)
    assert not (w.main / "benchmark").exists() and not w.stage.exists()


def test_x8_the_cli_takes_the_namespace_and_the_default_is_unchanged(tmp_path, kit, capsys):
    """[N] X8: `--namespace wave2.v8-af0711cf` publishes there; without it the destination is `wave2/` as before."""
    from bench import p426_harvest as H
    w = kit.World(tmp_path / "a")
    argv = ["wave2", "--leg-root", str(w.root), "--main-root", str(w.main), "--evidence-stage", str(w.stage)]
    assert H.main(argv + ["--namespace", NS], **kit.harvest_box(tmp_path / "a")) == 0, capsys.readouterr().err
    assert (w.main / f"benchmark/results/p426/{NS}/{kit.NAME}/HARVEST.json").is_file()
    w2 = kit.World(tmp_path / "b")
    argv = ["wave2", "--leg-root", str(w2.root), "--main-root", str(w2.main), "--evidence-stage", str(w2.stage)]
    assert H.main(argv, **kit.harvest_box(tmp_path / "b")) == 0
    assert (w2.main / kit.WAVE2 / kit.NAME / "HARVEST.json").is_file()


def test_x8_the_record_publishers_take_the_namespace(tmp_path, kit):
    """[N] X8: `publish_run_files` / `publish_dossier` publish below `<namespace>/run/` and `<namespace>/pairs/`; a bad namespace
    refuses."""
    from bench import p426_harvest as H
    w = kit.World(tmp_path)
    run = kit.pjson(tmp_path / "recs" / "frozen.json", kit.seal(dict(b=2)))
    dossier = kit.pjson(tmp_path / "recs" / "dossier.json", kit.seal(dict(a=1)))
    H.publish_run_files([run], main_root=w.main, scrub=kit.scrub_for(tmp_path), namespace=NS)
    H.publish_dossier(dossier, main_root=w.main, evidence_stage=w.stage, scrub=kit.scrub_for(tmp_path), namespace=NS)
    assert (w.main / f"benchmark/results/p426/{NS}/run/frozen.json").is_file()
    assert (w.main / f"benchmark/results/p426/{NS}/pairs/dossier.json").is_file()
    with pytest.raises(H.HarvestError):
        H.publish_run_files([run], main_root=w.main, scrub=kit.scrub_for(tmp_path), namespace="wave3")
