"""C366 (S27-P6): two positives verdicts ruled after the 2026-11-19 tg2 positives.
(a) PASS_BY_TRANSFER (stall / loop): the stop fired, the client kill verified, nothing was in flight at the kill (so the
    in-flight interrupt / cancellation link is not exercised), and the same language's stall PASS in the sealed 11-17 reference
    record (byte-identical cancel path) carries that link.
(b) WAIVED (alloc): the only kill is a model-role process other than the planted `bytearray(` command, over the inject's lowered
    per-process limit, no tool call carries the marker, and another language's alloc PASSes in the same record."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench import p426_freeze as fz
from bench import p426_hooks as ph
from bench import p426_wave2 as W2
from bench.tests.s26_frozen import s26_support as X


@pytest.fixture
def world(tmp_path):
    return X.HostWorld(tmp_path / "host")


@pytest.fixture
def reference(tmp_path, monkeypatch):
    """A sealed reference record: stall PASS in every language (the 11-17 shape), at the C366 path under `$STACK_WORKDIR`."""
    wd = Path(tmp_path) / "wd"
    injects = [dict(language=lang, kind=k, verdict="PASS" if k == "stall" else "FAIL (inject_verify rc 4)",
                    row_sha256=f"{n:064x}") for n, (lang, k) in enumerate((lang, k) for lang in X.LANGS for k in X.KINDS)]
    doc = ph.seal(dict(kind=fz.KIND_POSITIVES, corpus="tg2", arm="n16", n16_commit="c" * 40, injects=injects, verdict="FAIL"))
    path = wd / "m76" / "p426" / "tg2" / "attempt1-FAIL" / "positives.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))
    monkeypatch.setattr(W2, "TRANSFER_REFERENCE", dict(W2.TRANSFER_REFERENCE, sha256=doc["sha256"],
                                                       path="$STACK_WORKDIR/m76/p426/tg2/attempt1-FAIL/positives.json"))
    monkeypatch.setattr(fz, "TRANSFER_REFERENCE_SHA256", doc["sha256"])
    monkeypatch.setattr(W2, "worktree_cancel_path_sha256", lambda wt: fz.CANCEL_PATH_SHA256)   # the fake worktree has no sources
    monkeypatch.setattr(fz, "TRANSFER_REFERENCE_STALL_ROWS",
                        {i["language"]: i["row_sha256"] for i in injects if i["kind"] == "stall"})
    return dict(path=path, doc=doc)


def stopped(stop, in_flight=0, verified=True, client=True):
    def mutate(row, manifest):
        row["gate"]["stop_reason"] = stop
        term = row["termination"]
        killed = [k for k in term.get("killed") or [] if k.get("role") != "client"]
        if client:
            killed.append(dict(role="client", pid=11, create_time=1.0, argv=["opencode", "run"]))
        term.update(reason=stop, killed=killed, killed_verified=verified, in_flight_at_kill=in_flight,
                    worker_summary_before=dict(in_flight=in_flight, requests_started=4, requests_completed=4 - in_flight),
                    worker_summary_after=dict(in_flight=0, requests_started=4, requests_completed=4 - in_flight))
    return mutate


def unrelated_kill(argv=("npm", "install"), rss=545_865_728, limit=512 * 1024 ** 2):
    def mutate(row, manifest):
        row["stop_reason"] = "completed"
        row["termination"] = dict(row["termination"], reason=None, killed=[])
        row["mem_kills"] = [dict(role="model", argv=list(argv), rss=rss, tool_call_id="c-npm")]
        manifest["runtime"]["inject"]["policy"] = dict(manifest["runtime"]["inject"].get("policy") or {},
                                                       hygiene=dict(per_process=limit))
    return mutate


def run(tmp_path, monkeypatch, world, **kw):
    ops = X.PosOps(tmp_path, world, **kw)
    rc, out = X.positives(tmp_path, monkeypatch, ops)
    return rc, X.record(out)


def entry(doc, lang, kind):
    return X.inject_of(doc, lang, kind)


# ------------------------------------------------------------------ (a) PASS_BY_TRANSFER
@pytest.mark.parametrize("kind, verdict, stop", [("stall", "not_observed:trailing", "stalled"),
                                                 ("loop", "not_observed:cancellation", "looping")])
def test_a_stop_with_nothing_in_flight_passes_by_transfer(tmp_path, monkeypatch, world, reference, kind, verdict, stop):
    rc, doc = run(tmp_path, monkeypatch, world, verdicts={("java", kind): verdict}, mutates={("java", kind): stopped(stop)},
                  shapes={("java", kind): "keep"})
    e = entry(doc, "java", kind)
    assert e["verdict"] == "PASS_BY_TRANSFER", e
    ev = e["transfer_evidence"]
    assert ev["reference_sha256"] == reference["doc"]["sha256"] and ev["in_flight_at_kill"] == 0 and ev["verify_verdict"] == verdict
    assert ev["reference_row_sha256"] == entry(reference["doc"], "java", "stall")["row_sha256"]
    assert rc == 0 and doc["verdict"] == "PASS" and doc["problems"] == []
    assert fz.positives_problems(doc, arm="n16", commit=X.COMMIT, identity=dict(X.IDENT), frozen_prompt_date=X.DATE,
                                 image_id=doc["image_id"], cancel_path_sha256=fz.CANCEL_PATH_SHA256) == []


@pytest.mark.parametrize("why, mutate, verdict", [
    ("a request was in flight", stopped("stalled", in_flight=1), "not_observed:trailing"),
    ("the kill is not verified", stopped("stalled", verified=False), "not_observed:trailing"),
    ("no client kill", stopped("stalled", client=False), "not_observed:trailing"),
    ("another stop", stopped("turn_cap"), "not_observed:trailing"),
    ("no stop at all", stopped(None), "not_observed"),
    ("a verdict that is not the in-flight link", stopped("stalled"), "FAIL:stall_threshold"),
])
def test_anything_else_is_not_transferred(tmp_path, monkeypatch, world, reference, why, mutate, verdict):
    rc, doc = run(tmp_path, monkeypatch, world, verdicts={("rust", "stall"): verdict}, mutates={("rust", "stall"): mutate})
    assert entry(doc, "rust", "stall")["verdict"] == verdict, why
    assert rc == 1 and doc["verdict"] == "FAIL"


def test_loop_descendant_not_killed_is_not_transferred(tmp_path, monkeypatch, world, reference):
    rc, doc = run(tmp_path, monkeypatch, world, verdicts={("cpp", "loop"): "not_observed:descendant"},
                  mutates={("cpp", "loop"): stopped("looping")}, shapes={("cpp", "loop"): "keep"})
    assert entry(doc, "cpp", "loop")["verdict"] == "not_observed:descendant" and rc == 1


@pytest.mark.parametrize("damage", ["missing", "other-sha", "no-stall-pass"])
def test_the_reference_must_verify_and_hold_the_languages_stall_pass(tmp_path, monkeypatch, world, reference, damage):
    if damage == "missing":
        reference["path"].unlink()
    elif damage == "other-sha":
        monkeypatch.setattr(W2, "TRANSFER_REFERENCE", dict(W2.TRANSFER_REFERENCE, sha256="1" * 64))
    else:
        body = {k: v for k, v in reference["doc"].items() if k != "sha256"}
        for i in body["injects"]:
            if i["language"] == "rust" and i["kind"] == "stall":
                i["verdict"] = "FAIL"
        resealed = ph.seal(body)
        reference["path"].write_text(json.dumps(resealed))
        monkeypatch.setattr(W2, "TRANSFER_REFERENCE", dict(W2.TRANSFER_REFERENCE, sha256=resealed["sha256"]))
    rc, doc = run(tmp_path, monkeypatch, world, verdicts={("rust", "stall"): "not_observed:trailing"},
                  mutates={("rust", "stall"): stopped("stalled")})
    assert entry(doc, "rust", "stall")["verdict"] == "not_observed:trailing" and rc == 1


def test_a_nonzero_probe_exit_is_never_transferred(tmp_path, monkeypatch, world, reference):
    rc, doc = run(tmp_path, monkeypatch, world, verdicts={("rust", "stall"): "not_observed:trailing"},
                  mutates={("rust", "stall"): stopped("stalled")}, probe_rc={("rust", "stall"): 3})
    assert entry(doc, "rust", "stall")["verdict"].startswith("FAIL:probe_rc") and rc == 1


# ------------------------------------------------------------------ (b) WAIVED
def test_an_unrelated_kill_over_the_inject_limit_is_waived_when_another_alloc_passes(tmp_path, monkeypatch, world, reference):
    rc, doc = run(tmp_path, monkeypatch, world, verdicts={("javascript", "alloc"): "FAIL:unrelated_kill"},
                  mutates={("javascript", "alloc"): unrelated_kill()})
    e = entry(doc, "javascript", "alloc")
    assert e["verdict"] == "WAIVED", e
    assert e["waived_evidence"]["killed_argv0"] == "npm" and e["waived_evidence"]["rss"] > e["waived_evidence"]["per_process"]
    assert rc == 0 and doc["verdict"] == "PASS", doc["problems"]
    assert fz.positives_problems(doc, arm="n16", commit=X.COMMIT, identity=dict(X.IDENT), frozen_prompt_date=X.DATE,
                                 image_id=doc["image_id"], cancel_path_sha256=fz.CANCEL_PATH_SHA256) == []


def test_a_waiver_needs_an_alloc_pass_in_the_same_record(tmp_path, monkeypatch, world, reference):
    verdicts = {(lang, "alloc"): "not_observed:kill" for lang in X.LANGS}
    verdicts[("javascript", "alloc")] = "FAIL:unrelated_kill"
    rc, doc = run(tmp_path, monkeypatch, world, verdicts=verdicts, mutates={("javascript", "alloc"): unrelated_kill()})
    assert entry(doc, "javascript", "alloc")["verdict"] == "WAIVED"
    assert rc == 1 and any("no alloc PASS" in p for p in doc["problems"])


@pytest.mark.parametrize("why, mutate", [
    ("the killed process is the planted command", unrelated_kill(argv=("python3", "-c", "bytearray(1 << 30)"))),
    ("the kill is not over the inject limit", unrelated_kill(rss=100 * 1024 ** 2)),
])
def test_other_unrelated_kills_are_not_waived(tmp_path, monkeypatch, world, reference, why, mutate):
    rc, doc = run(tmp_path, monkeypatch, world, verdicts={("javascript", "alloc"): "FAIL:unrelated_kill"},
                  mutates={("javascript", "alloc"): mutate})
    assert entry(doc, "javascript", "alloc")["verdict"] == "FAIL:unrelated_kill", why
    assert rc == 1


def test_a_waiver_refuses_when_a_tool_call_carries_the_marker(tmp_path, monkeypatch, world, reference):
    marker = X.ev_tool("c2", "shell", {"command": "python3 -c \"x = bytearray(10**10)\""})
    rc, doc = run(tmp_path, monkeypatch, world, verdicts={("javascript", "alloc"): "FAIL:unrelated_kill"},
                  mutates={("javascript", "alloc"): unrelated_kill()},
                  events={("javascript", "alloc"): X.default_events() + [marker]})
    assert entry(doc, "javascript", "alloc")["verdict"] == "FAIL:unrelated_kill" and rc == 1


# ------------------------------------------------------------------ v8
def _v8(doc):
    return fz.positives_problems(doc, arm="n16", commit=X.COMMIT, identity=dict(X.IDENT), frozen_prompt_date=X.DATE,
                                 image_id=doc["image_id"], cancel_path_sha256=fz.CANCEL_PATH_SHA256)


def _reseal(doc, edit):
    body = json.loads(json.dumps({k: v for k, v in doc.items() if k != "sha256"}))
    edit(body)
    return ph.seal(body)


@pytest.fixture
def transferred(tmp_path, monkeypatch, world, reference):
    rc, doc = run(tmp_path, monkeypatch, world, verdicts={("java", "stall"): "not_observed:trailing",
                                                          ("javascript", "alloc"): "FAIL:unrelated_kill"},
                  mutates={("java", "stall"): stopped("stalled"), ("javascript", "alloc"): unrelated_kill()})
    assert rc == 0 and _v8(doc) == []
    return doc


def _entry_body(body, lang, kind):
    (e,) = [i for i in body["injects"] if i["language"] == lang and i["kind"] == kind]
    return e


@pytest.mark.parametrize("edit, want", [
    (lambda b: _entry_body(b, "java", "stall")["transfer_evidence"].update(reference_sha256="2" * 64), "java stall"),
    (lambda b: _entry_body(b, "java", "stall")["transfer_evidence"].update(in_flight_at_kill=1), "java stall"),
    (lambda b: _entry_body(b, "java", "stall").pop("transfer_evidence"), "java stall"),
    (lambda b: _entry_body(b, "java", "stall")["transfer_evidence"].update(row_sha256="3" * 64), "java stall"),
    (lambda b: _entry_body(b, "javascript", "alloc").pop("waived_evidence"), "javascript alloc"),
    (lambda b: _entry_body(b, "javascript", "alloc")["waived_evidence"].update(rss=1), "javascript alloc"),
    (lambda b: [i.update(verdict="DECLINED", declined_evidence=None) for i in b["injects"]
                if i["kind"] == "alloc" and i["verdict"] == "PASS"], "no alloc PASS"),
])
def test_v8_refuses_a_transfer_or_waiver_without_valid_evidence(transferred, edit, want):
    assert any(want in p for p in _v8(_reseal(transferred, edit)))


def test_v8_refuses_transfer_for_alloc_and_waiver_for_stall(transferred):
    def swap(b):
        s, a = _entry_body(b, "java", "stall"), _entry_body(b, "javascript", "alloc")
        s["verdict"], a["verdict"] = "WAIVED", "PASS_BY_TRANSFER"
    problems = _v8(_reseal(transferred, swap))
    assert any("java stall" in p for p in problems) and any("javascript alloc" in p for p in problems)


# ------------------------------------------------------------------ the stop path must be the reference commit's (side-agent note)
def test_a_changed_stop_path_refuses_the_transfer(tmp_path, monkeypatch, world, reference):
    monkeypatch.setattr(W2, "worktree_cancel_path_sha256", lambda wt: "4" * 64)
    rc, doc = run(tmp_path, monkeypatch, world, verdicts={("rust", "stall"): "not_observed:trailing"},
                  mutates={("rust", "stall"): stopped("stalled")})
    assert entry(doc, "rust", "stall")["verdict"] == "not_observed:trailing" and rc == 1


def test_v8_refuses_a_transfer_recorded_against_another_stop_path(transferred):
    def edit(b):
        _entry_body(b, "java", "stall")["transfer_evidence"]["cancel_path_sha256"] = "5" * 64
    assert any("java stall" in p for p in _v8(_reseal(transferred, edit)))


def test_the_constant_is_the_reference_commits_stop_path():  # noqa: D103
    """`CANCEL_PATH_SHA256` is the digest of `c7c6993a`'s sources (the 11-17 reference's commit), read from git."""
    import subprocess
    from bench import paths
    root = paths.repo_root()
    ref = W2.TRANSFER_REFERENCE["commit"]
    if subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{ref}^{{commit}}"]).returncode:
        pytest.fail(f"the reference commit {ref[:12]} is not in this checkout")

    def read(rel):
        return subprocess.run(["git", "-C", str(root), "show", f"{ref}:{rel}"], capture_output=True, text=True, check=True).stdout
    assert fz.cancel_path_sha256(read) == fz.CANCEL_PATH_SHA256


def test_a_worktree_without_the_sources_has_no_digest(tmp_path):
    assert W2.worktree_cancel_path_sha256(tmp_path) is None


# ------------------------------------------------------------------ cold read r1 (docs/reviews/c366/)
def _reader(rev="9abef6a6959e1caf9"):
    import subprocess
    from bench import paths
    root = paths.repo_root()
    return lambda rel: subprocess.run(["git", "-C", str(root), "show", f"{rev}:{rel}"], capture_output=True, text=True,
                                      check=True).stdout


@pytest.mark.parametrize("rel, old, new", [
    ("benchmark/bench/proc_guard.py", "def in_flight(metrics):", "def in_flight(metrics):\n    return 0"),
    ("benchmark/bench/proc_guard.py", "def wait_cancel(", "def wait_cancel_unused(): pass\n\n\ndef wait_cancel("),
    ("benchmark/bench/arm_runner.py", "GRACEFUL_CLIENT_S = 15", "GRACEFUL_CLIENT_S = 1"),
    ("benchmark/bench/arm_runner.py", "def worker_json(endpoint):", "def worker_json(endpoint):\n    return {}"),
    ("benchmark/m62/inject_verify.py", "def cancellation_consistent(term):", "def cancellation_consistent(term):\n    return True"),
])
def test_P1_any_edit_of_the_stop_paths_closure_changes_the_digest(rel, old, new):
    read = _reader()
    base = fz.cancel_path_sha256(read)
    assert base == fz.CANCEL_PATH_SHA256

    def edited(r):
        text = read(r)
        if r == rel:
            assert old in text, (rel, old)
            text = text.replace(old, new, 1)
        return text
    assert fz.cancel_path_sha256(edited) != base


@pytest.mark.parametrize("rel, where", [("benchmark/bench/arm_runner.py", "_identity_inputs"),
                                        ("benchmark/m62/inject_verify.py", "verify_row")])
def test_P1_the_named_exclusions_do_not_change_the_digest(rel, where):
    """A statement added inside an excluded function, or after inject_verify's alloc marker, leaves the digest unchanged."""
    import ast
    read = _reader()

    def edited(r):
        text = read(r)
        if r == rel:
            node = next(n for n in ast.parse(text).body if getattr(n, "name", None) == where)
            lines = text.splitlines(keepends=True)
            lines.insert(node.end_lineno, "    _s27_probe = 1\n")         # the excluded function's (or alloc tail's) last line + 1
            text = "".join(lines)
        return text
    assert fz.cancel_path_sha256(edited) == fz.CANCEL_PATH_SHA256


def test_P1_a_missing_truncation_marker_refuses(tmp_path):
    read = _reader()
    with pytest.raises(ValueError):
        fz.cancel_path_sha256(lambda r: read(r).replace("    # alloc\n", "    # gone\n") if r.endswith("inject_verify.py") else read(r))


def test_P2_a_reference_row_of_another_language_is_refused(transferred):
    def edit(b):
        ev = _entry_body(b, "java", "stall")["transfer_evidence"]
        ev["reference_row_sha256"] = fz.TRANSFER_REFERENCE_STALL_ROWS["rust"]
    assert any("java stall" in p for p in _v8(_reseal(transferred, edit)))


def test_P2_v8_refuses_a_transfer_when_the_live_stop_path_differs_or_is_unknown(transferred):
    for live in (None, "6" * 64):
        problems = fz.positives_problems(transferred, arm="n16", commit=X.COMMIT, identity=dict(X.IDENT),
                                         frozen_prompt_date=X.DATE, image_id=transferred["image_id"], cancel_path_sha256=live)
        assert any("live stop path" in p for p in problems), live


def test_P2_the_reference_row_constants_are_the_sealed_reference_records():
    """The constants are the 11-17 record's stall rows (read here when the record is on this box; else the sha alone)."""
    assert set(fz.TRANSFER_REFERENCE_STALL_ROWS) == set(X.LANGS)
    assert all(len(v) == 64 for v in fz.TRANSFER_REFERENCE_STALL_ROWS.values())


def test_P3_an_edited_manifest_is_not_waived(tmp_path, monkeypatch, world, reference):
    def after_write(lang, kind, events_path, run):
        if (lang, kind) == ("javascript", "alloc"):
            m = Path(run) / "alloc.attempt1.manifest.json"
            doc = json.loads(m.read_text())
            doc["runtime"]["inject"]["policy"]["hygiene"]["per_process"] = 300 * 1024 ** 2
            m.write_text(json.dumps(doc))
    rc, doc = run(tmp_path, monkeypatch, world, verdicts={("javascript", "alloc"): "FAIL:unrelated_kill"},
                  mutates={("javascript", "alloc"): unrelated_kill(rss=400 * 1024 ** 2)}, hooks={"after_write": after_write})
    assert entry(doc, "javascript", "alloc")["verdict"] == "FAIL:unrelated_kill" and rc == 1


def test_P3_v8_binds_the_waiver_to_the_entrys_manifest_sha(transferred):
    def edit(b):
        _entry_body(b, "javascript", "alloc")["waived_evidence"]["manifest_sha256"] = "7" * 64
    assert any("javascript alloc" in p for p in _v8(_reseal(transferred, edit)))


def test_the_committed_reference_is_the_constant_and_holds_the_stall_rows():
    """The reference the rule reads is committed on `main` (side-agent note): sealed, `TRANSFER_REFERENCE_SHA256`, and its
    stall rows are `TRANSFER_REFERENCE_STALL_ROWS`."""
    from bench import paths
    path = Path(W2.TRANSFER_REFERENCE["path"].replace("$STACK_REPO", str(paths.repo_root())))
    doc = json.loads(path.read_text())
    assert ph.sealed_ok(doc) and doc["sha256"] == fz.TRANSFER_REFERENCE_SHA256
    rows = {e["language"]: e["row_sha256"] for e in doc["injects"] if e["kind"] == "stall" and e["verdict"] == "PASS"}
    assert rows == fz.TRANSFER_REFERENCE_STALL_ROWS
    for lang, sha in rows.items():                                   # the committed row files are those rows
        row = path.parent / "run" / lang / "stall.attempt1.jsonl"
        import hashlib
        assert hashlib.sha256(row.read_bytes()).hexdigest() == sha
