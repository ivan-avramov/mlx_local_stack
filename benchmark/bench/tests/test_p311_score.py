"""P311-lite (v): scoring out of the tg1 probe: `tg1_score` sidecar, the fail-closed `row_scores` join, git-tree contact
inputs, and the readers that use it (spec 1 and tests 8, 9)."""
import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from bench import answer_key, row_scores, tg1_score, web_scan
from bench.tests import p311_legacy as legacy

REFERENCE = "def secret_solution(values):\n    total = sum(values) * 3\n    return total + len(values) * 17\n" * 3
SCAFFOLD = "opencode-v2-web-tg1"


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                   capture_output=True)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """STACK_WORKDIR, a committed polyglot corpus, a rows file with a manifest, transcripts under opencode_transcripts."""
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    corpus = tmp_path / "polyglot"
    monkeypatch.setenv("POLYGLOT_DIR", str(corpus))
    item = corpus / "python/exercises/practice/one"
    (item / ".meta").mkdir(parents=True)
    (item / ".meta/example.py").write_text(REFERENCE)
    (item / "solution.py").write_text("def secret_solution(values):\n    pass\n")
    git(corpus, "init", "-q")
    git(corpus, "add", "-A")
    git(corpus, "commit", "-q", "-m", "corpus")
    sha = subprocess.check_output(["git", "-C", str(corpus), "rev-parse", "HEAD"], text=True).strip()
    rows = tmp_path / "legs/rows.jsonl"
    rows.parent.mkdir()
    w = dict(tmp=tmp_path, corpus=corpus, sha=sha, rows=rows, made=[])
    (rows.with_suffix(".manifest.json")).write_text(json.dumps({"runtime": {"polyglot_sha": sha}}))
    return w


def part(name, inputs, content=None):
    return {"type": "tool", "name": name, "state": {"input": inputs, "status": "completed", "content": content}}


FULL_LEGACY = {"web_fetches": [], "net_shell": [], "web_denied": 0, "subagent_calls": 0, "web_audit_incomplete": False,
               "answer_key_contact": False, "answer_key_evidence": []}


def make_row(w, item="python/one", *, texts=(), session="ses_1", **extra):
    """A new-style tg1 row (no web fields) plus its stored transcript; returns the row."""
    parts = [part("webfetch", {"url": f"https://example.test/{i}"}, t) for i, t in enumerate(texts)]
    export = {"messages": [{"type": "assistant", "content": parts}]}
    path = w["tmp"] / "opencode_transcripts/m/rows.run" / (item.replace("/", "__") + "." + session + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(export))
    row = {"id": item, "model": "m", "sample": 0, "session_id": session, "scaffold": SCAFFOLD, "passed": True,
           "nonconv_kind": None, "stop_reason": "completed",
           "transcript_path": "$STACK_WORKDIR/" + path.relative_to(w["tmp"]).as_posix(),
           "evidence_sha256": {"export": hashlib.sha256(path.read_bytes()).hexdigest()}, **extra}
    w["made"].append(row)
    return row


def write_rows(w, rows):
    w["rows"].write_text("".join(json.dumps(r) + "\n" for r in rows))
    return w["rows"]


def sidecar(w):
    return row_scores.sidecar_path(w["rows"])


def records(w):
    path = sidecar(w)
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# ---------------------------------------------------------------- contact: refs vs disk, git tree
def test_contact_refs_equals_legacy_contact_on_disk(tmp_path):
    item = tmp_path / "item"
    (item / ".meta").mkdir(parents=True)
    (item / ".meta/example.py").write_text(REFERENCE)
    (item / ".meta/proof.ci.go").write_text("package x\nfunc Secret() int { return 12345678 }\n" * 4)
    (item / ".meta/config.json").write_text("{}")
    for texts in ([], [{"source": "s", "text": REFERENCE}], [{"source": "t", "text": "nothing like it"}],
                  [{"source": "u", "text": "package x\nfunc Secret() int { return 12345678 }\n" * 4}]):
        assert answer_key.contact(item, texts) == legacy.legacy_contact(item, texts)


def test_tree_references_come_from_the_recorded_commit_not_the_checkout(world):
    item = world["corpus"] / "python/exercises/practice/one"
    (item / ".meta/example.py").write_text("tampered in the working tree\n")
    (item / ".meta/example_extra.py").write_text("untracked\n")
    refs = tg1_score.tree_references(world["corpus"], world["sha"], "python", "one")
    assert refs == [(".meta/example.py", REFERENCE)]
    assert tg1_score.reference_digest(refs) == tg1_score.reference_digest([(".meta/example.py", REFERENCE)])


# ---------------------------------------------------------------- scoring writes one record per row
def test_tg1_score_writes_one_record_per_row_equal_to_the_legacy_in_row_fields(world):
    hit = make_row(world, texts=[REFERENCE], session="ses_hit")
    clean = make_row(world, item="python/one", texts=["unrelated docs text"], session="ses_clean")
    write_rows(world, [hit, clean])
    result = tg1_score.score_rows(world["rows"])
    assert result["written"] == 2 and not result["errors"]
    recs = records(world)
    assert [r["row_key"] for r in recs] == [["m", "python/one", 0, "ses_hit"], ["m", "python/one", 0, "ses_clean"]]
    assert recs[0]["scoring_code_sha256"] == row_scores.scoring_code_sha256()
    assert recs[0]["transcript_sha256"] == hit["evidence_sha256"]["export"]
    assert recs[0]["polyglot_sha"] == world["sha"] and len(recs[0]["reference_digest"]) == 64
    # the labels are what the old in-process scan produced (disk contact on the same files)
    export = json.loads((world["tmp"] / hit["transcript_path"].removeprefix("$STACK_WORKDIR/")).read_text())
    old = legacy.legacy_web_audit(copy.deepcopy(export), world["corpus"] / "python/exercises/practice/one",
                                  world["tmp"] / "opencode_transcripts/m/old/item.json", scaffold=SCAFFOLD)
    for key in ("web_denied", "subagent_calls", "web_audit_incomplete", "answer_key_contact"):
        assert recs[0]["fields"][key] == old[key]
    assert recs[0]["fields"]["answer_key_contact"] is True and recs[1]["fields"]["answer_key_contact"] is False
    assert [e["status"] for e in recs[0]["fields"]["web_fetches"]] == ["completed"]


def test_a_dirty_corpus_reference_does_not_change_the_label(world):
    row = make_row(world, texts=[REFERENCE])
    write_rows(world, [row])
    (world["corpus"] / "python/exercises/practice/one/.meta/example.py").write_text("gone\n")
    tg1_score.score_rows(world["rows"])
    assert records(world)[0]["fields"]["answer_key_contact"] is True


def test_tg1_score_is_idempotent_and_a_new_scoring_sha_appends_a_replacement(world):
    write_rows(world, [make_row(world, texts=["x"])])
    assert tg1_score.score_rows(world["rows"])["written"] == 1
    assert tg1_score.score_rows(world["rows"])["written"] == 0 and len(records(world)) == 1
    assert tg1_score.score_rows(world["rows"], scoring_sha="1" * 64)["written"] == 1
    assert [r["scoring_code_sha256"] for r in records(world)] == [row_scores.scoring_code_sha256(), "1" * 64]


def test_tg1_score_refuses_a_transcript_that_does_not_match_the_row_hash(world):
    row = make_row(world, texts=["x"])
    path = world["tmp"] / row["transcript_path"].removeprefix("$STACK_WORKDIR/")
    path.write_text(path.read_text() + " ")
    write_rows(world, [row])
    result = tg1_score.score_rows(world["rows"])
    assert result["written"] == 0 and "evidence_sha256" in result["errors"][0]
    assert not sidecar(world).exists()
    assert tg1_score.main([str(world["rows"])]) != 0


def test_tg1_score_never_scores_legacy_rows(world):
    legacy_row = make_row(world, texts=["x"], **FULL_LEGACY)
    write_rows(world, [legacy_row])
    assert tg1_score.score_rows(world["rows"])["written"] == 0


# ---------------------------------------------------------------- the join
def scored(w, rows):
    write_rows(w, rows)
    tg1_score.score_rows(w["rows"])
    return row_scores.effective_rows(rows, sidecar(w))


def test_join_merges_the_sidecar_fields_into_a_copy(world):
    row = make_row(world, texts=[REFERENCE])
    out, = scored(world, [row])
    assert out is not row and out["answer_key_contact"] is True and out["score_source"] == "sidecar"
    assert "answer_key_contact" not in row                          # the append-only row is never rewritten


def test_join_legacy_rows_pass_through_as_the_same_objects(world):
    legacy_tg1 = {"id": "python/one", "model": "m", "scaffold": SCAFFOLD, **FULL_LEGACY}
    standard = {"id": "python/one", "model": "m", "scaffold": "opencode-v2-web", "passed": True}   # scored in-process
    rows = [legacy_tg1, standard]
    out = row_scores.effective_rows(rows, None)
    assert out[0] is legacy_tg1 and out[1] is standard
    assert not row_scores.needs_sidecar(legacy_tg1) and not row_scores.needs_sidecar(standard)
    assert row_scores.needs_sidecar({"scaffold": "opencode-v2-web-tg1-inject:stall"})


def test_join_missing_record_is_unscored_not_clean(world):
    row = make_row(world, texts=[REFERENCE])
    out, = row_scores.effective_rows([row], sidecar(world))
    assert out["score_unscored"] == "missing" and "answer_key_contact" not in out


def test_join_stale_transcript_duplicate_and_stale_scoring_each_fail_closed(world):
    row = make_row(world, texts=["x"])
    write_rows(world, [row])
    tg1_score.score_rows(world["rows"])
    rec = records(world)[0]
    path = sidecar(world)

    def put(*recs):
        path.write_text("".join(json.dumps(r) + "\n" for r in recs))
        return row_scores.effective_rows([row], path)[0].get("score_unscored")
    assert put(rec) is None
    assert put({**rec, "transcript_sha256": "0" * 64}) == "stale_transcript"
    assert put(rec, rec) == "duplicate"
    assert put({**rec, "scoring_code_sha256": "2" * 64}) == "stale_scoring"
    # a record under the current scoring code replaces an older one for the same row
    assert put({**rec, "scoring_code_sha256": "2" * 64}, rec) is None
    # two records under the current code disagree even when their content differs
    assert put(rec, {**rec, "fields": {**rec["fields"], "answer_key_contact": True}}) == "duplicate"
    path.write_text("not json\n")
    assert row_scores.effective_rows([row], path)[0]["score_unscored"] == "unreadable"


def test_join_keys_on_session_so_attempts_of_one_item_do_not_share_a_record(world):
    first = make_row(world, texts=["x"], session="ses_a")
    second = make_row(world, texts=[REFERENCE], session="ses_b")
    a, b = scored(world, [first, second])
    assert a["answer_key_contact"] is False and b["answer_key_contact"] is True


# ---------------------------------------------------------------- readers: audit, states, report
def test_audit_states_and_report_use_the_join_and_exclude_unscored_rows(world):
    hit = make_row(world, texts=[REFERENCE], session="ses_hit")
    other = make_row(world, item="python/two", texts=["docs"], session="ses_other")
    rows = [hit, other]
    # nothing scored yet: both rows are unscored, excluded from strict scoring, never "no contact"
    rep = answer_key.report_rows(rows, score_sidecar=sidecar(world))
    assert rep["strict_n"] == 0 and rep["unscored"] == 2 and rep["provisional"] is True
    states = answer_key.audit_states(rows, score_sidecar=sidecar(world))
    assert [s["unscored"] for s in states] == ["missing", "missing"] and not any(s["cheat"] for s in states)
    # no sidecar path given at all is the same fail-closed answer
    assert answer_key.report_rows(rows)["unscored"] == 2


def test_end_to_end_transcript_to_score_to_p201_audit_to_strict_exclusion(world, monkeypatch):
    import web_audit
    monkeypatch.setattr(web_audit, "auditor_version", lambda: "fixture-auditor 1")
    hit = make_row(world, texts=[REFERENCE], session="ses_hit")
    clean = make_row(world, item="python/two", texts=["plain docs"], session="ses_clean")
    two = world["corpus"] / "python/exercises/practice/two"
    (two / ".meta").mkdir(parents=True)
    (two / ".meta/example.py").write_text("print('two reference')\n" * 10)
    (two / "solution.py").write_text("def f():\n    pass\n")
    git(world["corpus"], "add", "-A")
    git(world["corpus"], "commit", "-q", "-m", "two")
    world["rows"].with_suffix(".manifest.json").write_text(json.dumps({"runtime": {"polyglot_sha": subprocess.check_output(
        ["git", "-C", str(world["corpus"]), "rev-parse", "HEAD"], text=True).strip()}}))
    rows = write_rows(world, [hit, clean])
    # the P201 audit refuses to run on unscored rows
    with pytest.raises(row_scores.Unscored):
        web_audit.audit_rows(rows, polyglot_root=world["corpus"], auditor=lambda prompt: '{"label": "docs", "reason": "x"}')
    assert tg1_score.score_rows(rows)["written"] == 2
    calls = []

    def auditor(prompt):
        calls.append(prompt)
        return json.dumps({"label": "solution" if "secret_solution" in prompt else "docs", "reason": "fixture"})
    side = web_audit.audit_rows(rows, polyglot_root=world["corpus"], auditor=auditor)
    assert len(calls) == 2 and side.exists()
    rep = answer_key.report_rows([hit, clean], audit_sidecar=side, score_sidecar=sidecar(world))
    assert rep["unscored"] == 0
    assert rep["flagged: answer-key contact"] == 1 and rep["flagged: web contact"] == 1
    # the contact row is cheat-flagged, rerun-eligible but needs an operator (the contact source is a URL here): it is
    # not scored; the clean row is
    assert [r["id"] for r in rep["scored_rows"]] == ["python/two"]


def test_legacy_rows_give_the_same_report_with_or_without_a_sidecar_argument():
    rows = [{"id": "python/a", "model": "m", "sample": 0, "scaffold": "opencode-v2-web", "passed": True,
             "web_fetches": [], "net_shell": [], "answer_key_contact": False, "answer_key_evidence": [],
             "stop_reason": "completed", "nonconv_kind": None}]
    plain = answer_key.report_rows(copy.deepcopy(rows))
    with_arg = answer_key.report_rows(copy.deepcopy(rows), score_sidecar="/nonexistent/x.score.jsonl")
    assert plain == with_arg and plain["unscored"] == 0


# ---------------------------------------------------------------- print-identity (spec 7)
def test_print_identity_reports_the_scoring_code_sha_without_importing_scoring_into_the_probe(monkeypatch, tmp_path, capsys):
    import importlib
    from bench import tg1_runner
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    probe = importlib.import_module("run_tg1_probe")

    class A:
        universe = None
        agent_system_file = None
        tg1_inject = None
        sampling_profile = "deployed"
    assert tg1_runner.print_identity(probe, A()) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scoring_code_sha256"] == row_scores.scoring_code_sha256()
    assert (tg1_runner.SCORING_ENTRY, tg1_runner.SCORING_DATA) == (row_scores.SCORING_ENTRY, row_scores.SCORING_DATA)
    assert out["scoring_code_sha256"] != out["probe_code_sha256"]


# ---- review L7: an explicit legacy discriminator
@pytest.mark.parametrize("partial", [{"web_fetches": []}, {"answer_key_contact": False},
                                     {k: v for k, v in FULL_LEGACY.items() if k != "answer_key_evidence"},
                                     {"web_audit_error": "x"}])
def test_a_partial_in_row_schema_is_unscored_not_legacy(world, partial):
    row = make_row(world, texts=["x"], **partial)
    assert row_scores.needs_sidecar(row)
    out, = row_scores.effective_rows([row], sidecar(world))
    assert out["score_unscored"] == "missing"


def test_current_epoch_rows_are_never_legacy_even_with_full_in_row_fields(world):
    row = make_row(world, texts=["x"], generation_identity_sha256="a" * 64, arm_identity_sha256="b" * 64, **FULL_LEGACY)
    assert row_scores.needs_sidecar(row) and not row_scores.is_legacy(row)
    assert row_scores.effective_rows([row], None)[0]["score_unscored"] == "missing"


def test_a_sidecar_merged_row_is_not_an_authoritative_legacy_row(world):
    row = make_row(world, texts=[REFERENCE], generation_identity_sha256="a" * 64, arm_identity_sha256="b" * 64)
    out, = scored(world, [row])
    assert out["answer_key_contact"] is True and not row_scores.is_legacy(out) and row_scores.needs_sidecar(out)
    # handing the merged row back to a reader with no sidecar must not make it authoritative
    assert row_scores.effective_rows([out], None)[0]["score_unscored"] == "missing"


def test_complete_legacy_tg1_rows_still_pass_through(world):
    row = make_row(world, texts=["x"], **FULL_LEGACY)
    assert row_scores.is_legacy(row) and row_scores.effective_rows([row], None)[0] is row


# ---- review L8: unscored rows are unknown in the displayed counters
def test_unscored_rows_are_marked_for_the_reports(world):
    row = make_row(world, texts=["x"])
    out, = row_scores.effective_rows([row], None)
    assert out["score_unscored"] and not out.get("web_fetches") and not out.get("answer_key_contact")
