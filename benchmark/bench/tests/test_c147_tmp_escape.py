"""C147 §4: /tmp escape candidates and exact-path cleanup on a real filesystem (TMP_ROOT injected)."""

import hashlib
import json
import os
from pathlib import Path
import time
import pytest
from bench import proc_guard as pg

FIXTURE = Path(__file__).parent / "fixtures/opencode_2.0.20_tool_parts.json"
FIXTURE_SHA256 = "7539f17cc5f128912d6f5d717ba1e4b8e088defa85d96a61c3c454a453ee357e"
ENV = {"TMPDIR": "/work/run/tmp/oc-item/", "PWD": "/work/scratch/oc-item/item"}


def export_of(*parts):
    return {"messages": [{"type": "assistant", "content": [
        {"type": "tool", "id": f"p{i}", "name": n, "state": {"status": s, "input": inp}}
        for i, (n, s, inp) in enumerate(parts)]}]}


def test_fixture_is_the_recorded_2_0_20_shape_and_pinned():
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256
    assert b"/Users/" not in raw
    doc = json.loads(raw)
    parts = doc["messages"][0]["content"]
    assert {p["name"] for p in parts} == {"read", "write", "edit", "shell"}
    assert all(set(p) == {"id", "name", "state", "type"} and set(p["state"]) == {"status", "input"} for p in parts)
    write = next(p for p in parts if p["name"] == "write")
    assert set(write["state"]["input"]) == {"path", "content"}
    edit = next(p for p in parts if p["name"] == "edit")
    assert set(edit["state"]["input"]) == {"path", "oldString", "newString"}
    shell = next(p for p in parts if p["name"] == "shell")
    assert set(shell["state"]["input"]) == {"command", "workdir"}


def test_recorded_export_has_no_escape():
    assert pg.tmp_escapes(json.loads(FIXTURE.read_bytes()), ENV) == []


def test_exact_write_edit_candidates_from_the_recorded_shape():
    doc = json.loads(FIXTURE.read_bytes())
    parts = doc["messages"][0]["content"]
    write = next(p for p in parts if p["name"] == "write")
    edit = next(p for p in parts if p["name"] == "edit")
    write["state"]["input"]["path"] = "/tmp/bench199_test.go"
    edit["state"]["input"]["path"] = "/private/tmp/sub/edited.py"
    got = pg.tmp_escapes(doc, ENV)
    assert [(c["path"], c["source"], c["exact"], c["status"]) for c in got] == [
        ("/tmp/bench199_test.go", "write", True, "completed"),
        ("/tmp/sub/edited.py", "edit", True, "completed"),
    ]


def test_relative_paths_resolve_against_workdir_then_scratch_and_filepath_is_not_an_alias():
    e = export_of(
        ("write", "completed", {"path": "z.go", "content": "", "workdir": "/tmp"}),
        ("write", "completed", {"path": "inside.go", "content": ""}),
        ("write", "completed", {"filePath": "/tmp/alias.go", "content": ""}),
        ("read", "completed", {"path": "/tmp/read-only.txt"}),
    )
    assert [c["path"] for c in pg.tmp_escapes(e, ENV)] == ["/tmp/z.go"]


@pytest.mark.parametrize("command,paths,tokens", [
    ("echo hi >/tmp/new", ["/tmp/new"], [">/tmp/new"]),
    ("cat /tmp/a; ls", ["/tmp/a"], ["/tmp/a;"]),
    ("python3 -c \"open('/tmp/p','w')\"", ["/tmp/p"], None),
    ("ls /private/tmp/q/ x", ["/tmp/q/"], ["/private/tmp/q/"]),
    ("cd /tmp && ls", [], None),
    ("echo 'unbalanced /tmp/raw", ["/tmp/raw"], ["echo 'unbalanced /tmp/raw"]),
    ("ls /work/run/tmp/oc-item/x /work/scratch/oc-item/item/tmp/y/z", [], None),
])
def test_shell_mentions_are_uncertain_best_effort(command, paths, tokens):
    got = pg.tmp_escapes(export_of(("shell", "completed", {"command": command, "workdir": "/w"})), ENV)
    assert [c["path"] for c in got] == paths
    assert all(c["source"] == "shell" and c["exact"] is False for c in got)
    if tokens:
        assert [c["token"] for c in got] == tokens


def test_traversal_paths_are_reported_and_marked_by_components():
    e = export_of(("write", "completed", {"path": "/tmp/../tmp/x", "content": ""}),
                  ("write", "completed", {"path": "/tmp//y", "content": ""}),
                  ("write", "completed", {"path": "../../../../tmp/rel", "content": "", "workdir": "/a/b"}))
    got = pg.tmp_escapes(e, ENV)
    assert [c["path"] for c in got][:2] == ["/tmp/../tmp/x", "/tmp//y"]
    assert len(got) == 3 and got[2]["path"].endswith("/tmp/rel")


def test_paths_under_item_tmpdir_or_scratch_are_dropped():
    e = export_of(("write", "completed", {"path": ENV["TMPDIR"] + "x", "content": ""}),
                  ("write", "completed", {"path": ENV["PWD"] + "/a.py", "content": ""}))
    assert pg.tmp_escapes(e, {"TMPDIR": "/tmp/own/", "PWD": ENV["PWD"]}) == []
    e = export_of(("write", "completed", {"path": "/tmp/own/x", "content": ""}))
    assert pg.tmp_escapes(e, {"TMPDIR": "/tmp/own/", "PWD": "/s"}) == []


# ---- cleanup on a real filesystem ----

@pytest.fixture
def root(tmp_path):
    r = tmp_path / "tmproot"
    r.mkdir()
    (r / "preexisting.txt").write_text("old")
    ROOT_FOR_CAND[0] = r
    return r


def sha_of(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def cand(path, source="write", status="completed", exact=True, token=None, content=None, root=None):
    """A candidate. For writes the recorded content hash defaults to the file's CURRENT bytes (the tool wrote them)."""
    entry = dict(path=path, source=source, exact=exact, token=token or path, status=status)
    if source == "write":
        if content is None:
            disk = Path(root or ROOT_FOR_CAND[0]) / path[len("/tmp/"):]
            content = disk.read_bytes() if disk.is_file() else b"x"
        entry["content_sha256"] = sha_of(content)
    return entry


ROOT_FOR_CAND = [None]


def item(root, act):
    before = pg.tmp_listing(root)
    t0 = time.time()
    act()
    time.sleep(0.01)
    after = pg.tmp_listing(root)
    return before, after, (t0, time.time())


def clean(root, cands, before, after, window, **kw):
    return pg.tmp_clean(cands, before, after, window, root=root, **kw)


def test_listing_is_name_inode_device_and_does_not_follow_symlinks(root):
    (root / "l").symlink_to("/")
    got = pg.tmp_listing(root)
    st = os.lstat(root / "preexisting.txt")
    assert got["preexisting.txt"] == (st.st_ino, st.st_dev)
    assert got["l"] == (os.lstat(root / "l").st_ino, os.lstat(root / "l").st_dev)


def test_write_completed_new_file_is_removed(root):
    b, a, w = item(root, lambda: (root / "new.txt").write_text("x"))
    cleaned, kept = clean(root, [cand("/tmp/new.txt")], b, a, w)
    assert cleaned == ["/tmp/new.txt"] and kept == [] and not (root / "new.txt").exists()


def test_written_file_in_a_new_directory_removes_the_emptied_parent_too(root):
    def act():
        (root / "d").mkdir()
        (root / "d/f.py").write_text("x")
    b, a, w = item(root, act)
    cleaned, kept = clean(root, [cand("/tmp/d/f.py")], b, a, w)
    assert cleaned == ["/tmp/d/f.py", "/tmp/d"] and not (root / "d").exists()


def test_a_successful_edit_never_authorizes_deletion_even_of_an_unrelated_creators_file(root):
    """Q13: an edit needs a pre-existing file, so it cannot prove creation. Another process made it after the
    pre-item listing and the model then edited it successfully: diagnostic only."""
    b, a, w = item(root, lambda: (root / "theirs").write_text("created by another process"))
    assert clean(root, [cand("/tmp/theirs", "edit", status="completed")], b, a, w) == (
        [], [["/tmp/theirs", "ambiguous"]])
    assert (root / "theirs").read_text() == "created by another process"


def test_write_whose_content_was_replaced_after_completion_is_kept_as_modified(root):
    b, a, w = item(root, lambda: (root / "n").write_text("what our tool wrote"))
    c = cand("/tmp/n", content="what our tool wrote")
    (root / "n").write_text("replaced by someone else, same inode")        # same inode, different bytes
    assert clean(root, [c], b, a, w) == ([], [["/tmp/n", "modified"]])
    assert (root / "n").read_text() == "replaced by someone else, same inode"


def test_write_with_matching_content_is_removed(root):
    b, a, w = item(root, lambda: (root / "n").write_bytes("h\u00e9llo\n".encode()))
    assert clean(root, [cand("/tmp/n", content="h\u00e9llo\n")], b, a, w) == (["/tmp/n"], [])


def test_write_candidate_without_a_recorded_content_hash_is_ambiguous(root):
    b, a, w = item(root, lambda: (root / "n").write_text("x"))
    c = cand("/tmp/n")
    c.pop("content_sha256")
    assert clean(root, [c], b, a, w) == ([], [["/tmp/n", "ambiguous"]])


def test_preexisting_name_never_removed_even_for_write(root):
    b, a, w = item(root, lambda: (root / "preexisting.txt").write_text("rewritten"))
    cleaned, kept = clean(root, [cand("/tmp/preexisting.txt"), cand("/tmp/preexisting.txt", "edit")], b, a, w)
    assert cleaned == [] and kept == [["/tmp/preexisting.txt", "pre_existing"]]
    assert (root / "preexisting.txt").exists()


def test_missing(root):
    b, a, w = item(root, lambda: None)
    assert clean(root, [cand("/tmp/never")], b, a, w) == ([], [["/tmp/never", "missing"]])


def test_symlink_first_component_and_symlinked_parent(root, tmp_path):
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep").write_text("precious")

    def act():
        (root / "lnk").symlink_to(victim)
        (root / "lnk2").symlink_to(victim / "keep")
    b, a, w = item(root, act)
    cleaned, kept = clean(root, [cand("/tmp/lnk/keep"), cand("/tmp/lnk2")], b, a, w)
    assert cleaned == [] and kept == [["/tmp/lnk/keep", "symlink"], ["/tmp/lnk2", "symlink"]]
    assert (victim / "keep").read_text() == "precious"


def test_not_owned(root):
    b, a, w = item(root, lambda: (root / "n").write_text("x"))
    assert clean(root, [cand("/tmp/n")], b, a, w, uid=os.getuid() + 1) == ([], [["/tmp/n", "not_owned"]])


def test_outside_window(root):
    b, a, w = item(root, lambda: (root / "n").write_text("x"))
    late = (w[1] + 100, w[1] + 200)
    assert clean(root, [cand("/tmp/n")], b, a, late) == ([], [["/tmp/n", "outside_window"]])


def test_replaced_first_component_between_listing_and_removal(root):
    b, a, w = item(root, lambda: (root / "n").write_text("x"))
    (root / "n").unlink()
    (root / "n").write_text("someone else")
    assert clean(root, [cand("/tmp/n")], b, a, w) == ([], [["/tmp/n", "replaced"]])
    assert (root / "n").read_text() == "someone else"


def test_replaced_nested_file_between_final_check_and_unlink(root, monkeypatch):
    def act():
        (root / "d").mkdir()
        (root / "d/f").write_text("x")
    b, a, w = item(root, act)

    def swap():
        (root / "d/f").unlink()
        (root / "d/f").write_text("not ours")
    monkeypatch.setattr(pg, "_PRE_UNLINK_HOOK", swap)
    cleaned, kept = clean(root, [cand("/tmp/d/f")], b, a, w)
    assert cleaned == [] and kept == [["/tmp/d/f", "replaced"]]
    assert (root / "d/f").read_text() == "not ours"


@pytest.mark.parametrize("path", ["/tmp/../tmp/x", "/tmp//x", "/tmp/./x", "/tmp/a/../x"])
def test_traversal(root, path):
    b, a, w = item(root, lambda: (root / "x").write_text("x"))
    assert clean(root, [cand(path)], b, a, w) == ([], [[path, "traversal"]])
    assert (root / "x").exists()


def test_ambiguous_when_the_creating_call_did_not_complete(root):
    b, a, w = item(root, lambda: (root / "n").write_text("x"))
    assert clean(root, [cand("/tmp/n", status="error")], b, a, w) == ([], [["/tmp/n", "ambiguous"]])
    assert (root / "n").exists()


def test_not_regular_fifo(root):
    b, a, w = item(root, lambda: os.mkfifo(root / "ff"))
    assert clean(root, [cand("/tmp/ff")], b, a, w) == ([], [["/tmp/ff", "not_regular"]])


def test_recorded_files_and_the_directories_they_empty_are_removed(root):
    def act():
        (root / "good").mkdir()
        (root / "good/a").write_text("1")
        (root / "good/sub").mkdir()
        (root / "good/sub/b").write_text("2")
    b, a, w = item(root, act)
    cleaned, kept = clean(root, [cand("/tmp/good/a"), cand("/tmp/good/sub/b")], b, a, w)
    assert sorted(cleaned) == ["/tmp/good", "/tmp/good/a", "/tmp/good/sub", "/tmp/good/sub/b"] and kept == []
    assert not (root / "good").exists()


def test_unrecorded_child_is_never_deleted_only_the_recorded_file_goes(root):
    def act():
        (root / "d").mkdir()
        (root / "d/mine").write_text("1")
        (root / "d/other").write_text("created by someone else, same uid, inside the window")
    b, a, w = item(root, act)
    cleaned, kept = clean(root, [cand("/tmp/d/mine")], b, a, w)
    assert cleaned == ["/tmp/d/mine"] and kept == [["/tmp/d", "dir_mixed"]]
    assert (root / "d/other").exists() and not (root / "d/mine").exists()
    # naming the directory itself (a write path) never empties it either
    assert clean(root, [cand("/tmp/d", content="")], b, a, w) == ([], [["/tmp/d", "replaced"]])
    assert (root / "d/other").exists()


@pytest.mark.parametrize("status", ["error", "running", "pending"])
def test_errored_or_pending_edit_naming_an_unrelated_creators_file_is_kept(root, status):
    b, a, w = item(root, lambda: (root / "theirs.txt").write_text("another process made this"))
    assert clean(root, [cand("/tmp/theirs.txt", "edit", status=status)], b, a, w) == (
        [], [["/tmp/theirs.txt", "ambiguous"]])
    assert (root / "theirs.txt").exists()


def test_directory_mixed_entries_are_not_removed(root, tmp_path):
    before = pg.tmp_listing(root)
    t0 = time.time()
    (root / "mixed").mkdir()
    (root / "mixed/old").write_text("old")
    t_old_end = time.time()
    time.sleep(0.05)
    (root / "mixed/late").write_text("late")
    after = pg.tmp_listing(root)
    window = (t0, t_old_end)
    cleaned, kept = clean(root, [cand("/tmp/mixed")], before, after, window)
    assert cleaned == [] and kept == [["/tmp/mixed", "replaced"]]
    assert (root / "mixed/old").exists() and (root / "mixed/late").exists()
    b, a, w = item(root, lambda: ((root / "m2").mkdir(), (root / "m2/l").symlink_to("/")))
    assert clean(root, [cand("/tmp/m2")], b, a, w)[1] == [["/tmp/m2", "replaced"]]


def test_shell_mentions_are_never_removed_automatically(root):
    b, a, w = item(root, lambda: (root / "theirs").write_text("unrelated creator"))
    c = cand("/tmp/theirs", "shell", exact=False, token="cat /tmp/theirs")
    assert clean(root, [c], b, a, w) == ([], [])
    assert (root / "theirs").exists()


def test_duplicate_candidates_are_processed_once(root):
    b, a, w = item(root, lambda: (root / "n").write_text("x"))
    cleaned, kept = clean(root, [cand("/tmp/n"), cand("/tmp/n")], b, a, w)
    assert cleaned == ["/tmp/n"] and kept == []


# ---- operator tool ----

def test_operator_tool_lists_everything_removes_only_checked_writes_never_shell_or_edit(tmp_path):
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from m62 import tmp_escape_clean as tool
    root = tmp_path / "tmproot"
    root.mkdir()
    t0 = time.time()
    (root / "mine.txt").write_text("ours")
    (root / "changed.txt").write_text("ours")
    (root / "shellfile").write_text("x")
    (root / "edited").write_text("x")
    t1 = time.time() + 1
    (root / "changed.txt").write_text("not ours any more")
    row = dict(id="python/one", tmp_window=[t0, t1], tmp_escapes=[
        dict(path="/tmp/mine.txt", source="write", exact=True, token="/tmp/mine.txt", status="completed",
             content_sha256=sha_of("ours")),
        dict(path="/tmp/changed.txt", source="write", exact=True, token="/tmp/changed.txt", status="completed",
             content_sha256=sha_of("ours")),
        dict(path="/tmp/shellfile", source="shell", exact=False, token="cat /tmp/shellfile", status="completed"),
        dict(path="/tmp/edited", source="edit", exact=True, token="/tmp/edited", status="completed")])
    rows = tmp_path / "rows.jsonl"
    rows.write_text(json.dumps(row) + "\n")
    lines = []
    assert tool.main(["--rows", str(rows), "--root", str(root)], out=lines.append) == 0
    assert (root / "mine.txt").exists() and "dry run" in lines[-1] and "listed=4" in lines[-1]
    lines = []
    tool.main(["--rows", str(rows), "--root", str(root), "--yes"], out=lines.append)
    assert not (root / "mine.txt").exists() and (root / "changed.txt").exists()
    assert (root / "shellfile").exists() and (root / "edited").exists()
    assert any("kept /tmp/changed.txt (modified)" in x for x in lines) and "removed=1 kept=1" in lines[-1]


def test_write_candidates_record_the_content_hash_of_what_the_client_was_asked_to_write():
    e = export_of(("write", "completed", {"path": "/tmp/new.txt", "content": "héllo\n"}),
                  ("edit", "completed", {"path": "/tmp/e.txt", "oldString": "a", "newString": "b"}))
    got = pg.tmp_escapes(e, ENV)
    assert got[0]["content_sha256"] == sha_of("héllo\n") and "content_sha256" not in got[1]


def test_write_path_replaced_by_an_empty_directory_is_kept_and_never_rmdird(root, monkeypatch):
    """Q20: the recorded write must itself still be a regular file with matching content."""
    b, a, w = item(root, lambda: (root / "replacement").mkdir())
    rmdirs = []
    real = os.rmdir
    monkeypatch.setattr(os, "rmdir", lambda *x, **k: (rmdirs.append(x), real(*x, **k))[1])
    assert clean(root, [cand("/tmp/replacement", content="what we wrote")], b, a, w) == (
        [], [["/tmp/replacement", "replaced"]])
    assert (root / "replacement").is_dir() and rmdirs == []
