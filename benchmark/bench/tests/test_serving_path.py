"""C47 (2026-09-03): the fingerprint's `"code"` key used to be the raw submodule COMMIT sha, so
every fork commit — including tool-only ones never imported by the server, e.g. the MTP
checkpoint splitter `split_mtp.py` — refused pairing with every earlier row. This hashes the
SERVING-PATH tree instead (excluding the tool-only surface) and keeps the commit shas as a
downgraded warning when the tree is byte-identical.

Real temp git repos throughout (no network, no mutation of the real src/mlx-vlm / src/mlx-serve
worktrees) — `subprocess` git commands are the mechanism under test, so mocking them would test
nothing.
"""
import subprocess

import pytest

import bench.provenance as P


# --------------------------------------------------------------------------- temp-repo helpers
def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _make_repo(tmp_path, name):
    """A fresh git repo at tmp_path/name — `name` must be "mlx-vlm" or "mlx-serve" so
    `serving_path_hash` resolves the right ls-tree root from its basename."""
    d = tmp_path / name
    d.mkdir()
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t.example")
    _git(d, "config", "user.name", "t")
    return d


def _commit(d, files, msg):
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(d, "add", "-A")
    _git(d, "commit", "-q", "-m", msg)
    return subprocess.check_output(["git", "-C", str(d), "rev-parse", "HEAD"],
                                   text=True).strip()


# --------------------------------------------------------------------------- (a) stability + change
def test_hash_is_stable_and_changes_with_a_serving_file(tmp_path):
    d = _make_repo(tmp_path, "mlx-vlm")
    c1 = _commit(d, {"mlx_vlm/server/generation.py": "a=1\n"}, "init")
    h1a = P.serving_path_hash(str(d), c1)
    h1b = P.serving_path_hash(str(d), c1)
    assert h1a is not None
    assert h1a == h1b

    c2 = _commit(d, {"mlx_vlm/server/generation.py": "a=2\n"}, "serving change")
    h2 = P.serving_path_hash(str(d), c2)
    assert h2 != h1a


def test_mlx_serve_root_is_src(tmp_path):
    d = _make_repo(tmp_path, "mlx-serve")
    c1 = _commit(d, {"src/mlx_serve/cli.py": "a=1\n"}, "init")
    h1 = P.serving_path_hash(str(d), c1)
    assert h1 is not None
    c2 = _commit(d, {"src/mlx_serve/cli.py": "a=2\n"}, "change")
    assert P.serving_path_hash(str(d), c2) != h1


# --------------------------------------------------------------------------- FIX-4: dependency pins
def test_mlx_vlm_pyproject_change_moves_the_hash(tmp_path):
    """FIX-4 (2026-09-03 verifier round, operator-ruled): dependency pins are output-relevant
    (the pinned mlx version) — a fork commit touching ONLY `pyproject.toml` must not be inert."""
    d = _make_repo(tmp_path, "mlx-vlm")
    c1 = _commit(d, {"mlx_vlm/server/generation.py": "a=1\n", "pyproject.toml": "mlx==1.0\n"}, "init")
    h1 = P.serving_path_hash(str(d), c1)
    c2 = _commit(d, {"pyproject.toml": "mlx==1.1\n"}, "bump mlx pin")
    assert P.serving_path_hash(str(d), c2) != h1


def test_mlx_vlm_requirements_and_uvlock_change_moves_the_hash(tmp_path):
    d = _make_repo(tmp_path, "mlx-vlm")
    c1 = _commit(d, {"mlx_vlm/server/generation.py": "a=1\n",
                     "requirements.txt": "mlx==1.0\n", "uv.lock": "x\n"}, "init")
    h1 = P.serving_path_hash(str(d), c1)
    c2 = _commit(d, {"requirements.txt": "mlx==1.1\n"}, "bump requirements")
    assert P.serving_path_hash(str(d), c2) != h1
    c3 = _commit(d, {"uv.lock": "y\n"}, "bump lock")
    assert P.serving_path_hash(str(d), c3) not in (h1, P.serving_path_hash(str(d), c2))


def test_mlx_serve_pyproject_and_uvlock_change_moves_the_hash(tmp_path):
    d = _make_repo(tmp_path, "mlx-serve")
    c1 = _commit(d, {"src/mlx_serve/cli.py": "a=1\n",
                     "pyproject.toml": "mlx==1.0\n", "uv.lock": "x\n"}, "init")
    h1 = P.serving_path_hash(str(d), c1)
    c2 = _commit(d, {"pyproject.toml": "mlx==1.1\n"}, "bump mlx pin")
    assert P.serving_path_hash(str(d), c2) != h1


def test_top_level_readme_change_is_still_hash_inert(tmp_path):
    """A fork commit touching only the top-level README (not a pathspec we request at all) must
    stay inert — dependency pins are hashed; unrelated top-level docs are not."""
    d = _make_repo(tmp_path, "mlx-vlm")
    c1 = _commit(d, {"mlx_vlm/server/generation.py": "a=1\n", "README.md": "old\n"}, "init")
    h1 = P.serving_path_hash(str(d), c1)
    c2 = _commit(d, {"README.md": "new\n"}, "docs only")
    assert P.serving_path_hash(str(d), c2) == h1


# --------------------------------------------------------------------------- (b) exclusion list
def test_a_splitter_only_commit_is_hash_inert(tmp_path):
    d = _make_repo(tmp_path, "mlx-vlm")
    c1 = _commit(d, {"mlx_vlm/server/generation.py": "a=1\n",
                     "mlx_vlm/split_mtp.py": "old\n"}, "init")
    h1 = P.serving_path_hash(str(d), c1)
    c2 = _commit(d, {"mlx_vlm/split_mtp.py": "new\n"}, "tool-only: splitter")
    h2 = P.serving_path_hash(str(d), c2)
    assert h1 == h2, "the C47 trigger: a tool-only commit must not move the serving-path hash"


def test_a_tests_only_commit_is_hash_inert(tmp_path):
    d = _make_repo(tmp_path, "mlx-vlm")
    c1 = _commit(d, {"mlx_vlm/server/generation.py": "a=1\n",
                     "mlx_vlm/tests/test_x.py": "old\n"}, "init")
    h1 = P.serving_path_hash(str(d), c1)
    c2 = _commit(d, {"mlx_vlm/tests/test_x.py": "new\n",
                     "mlx_vlm/tests/test_y.py": "new\n"}, "tests-only")
    assert P.serving_path_hash(str(d), c2) == h1


def test_every_declared_exclusion_is_inert_but_serving_files_still_move_the_hash(tmp_path):
    d = _make_repo(tmp_path, "mlx-vlm")
    c1 = _commit(d, {"mlx_vlm/server/generation.py": "a=1\n"}, "init")
    h1 = P.serving_path_hash(str(d), c1)
    excluded_changes = {
        "mlx_vlm/tests/test_x.py": "1",
        "mlx_vlm/evals/mmmu.py": "1",
        "mlx_vlm/trainer/lora.py": "1",
        "mlx_vlm/lora.py": "1",
        "mlx_vlm/split_mtp.py": "1",
        "mlx_vlm/convert.py": "1",
        "mlx_vlm/chat.py": "1",
        "mlx_vlm/chat_ui.py": "1",
        "mlx_vlm/LORA.MD": "1",
        "mlx_vlm/README.md": "1",          # any *.md, not just LORA.MD
    }
    c2 = _commit(d, excluded_changes, "bulk tool-only add")
    assert P.serving_path_hash(str(d), c2) == h1

    c3 = _commit(d, {"mlx_vlm/server/generation.py": "a=2\n"}, "real serving change")
    assert P.serving_path_hash(str(d), c3) != h1


def test_models_subdir_convert_py_is_NOT_excluded(tmp_path):
    """Only the top-level `mlx_vlm/convert.py` is excluded — a same-named file nested under
    `models/` is real model code and must still move the hash."""
    d = _make_repo(tmp_path, "mlx-vlm")
    c1 = _commit(d, {"mlx_vlm/models/foo/convert.py": "a=1\n"}, "init")
    h1 = P.serving_path_hash(str(d), c1)
    c2 = _commit(d, {"mlx_vlm/models/foo/convert.py": "a=2\n"}, "change")
    assert P.serving_path_hash(str(d), c2) != h1


# ------------------------------------------------------ C47 follow-up: drafters/*/split.py, mtp_split.py
def test_a_per_drafter_split_py_commit_is_hash_inert(tmp_path):
    """(a) `mlx_vlm/speculative/drafters/qwen3_5_mtp/split.py` is the conversion-time splitter for
    that drafter, imported only by convert.py/split_mtp.py — a change to it must not move the
    hash (operator-verified, 2026-09-03)."""
    d = _make_repo(tmp_path, "mlx-vlm")
    c1 = _commit(d, {"mlx_vlm/speculative/drafters/qwen3_5_mtp/split.py": "old\n",
                     "mlx_vlm/server/generation.py": "a=1\n"}, "init")
    h1 = P.serving_path_hash(str(d), c1)
    c2 = _commit(d, {"mlx_vlm/speculative/drafters/qwen3_5_mtp/split.py": "new\n"}, "split-only")
    assert P.serving_path_hash(str(d), c2) == h1


def test_a_drafter_model_py_commit_still_moves_the_hash(tmp_path):
    """(b) NEGATIVE CONTROL: the drafter's OTHER files (e.g. its model.py, the drafter head) ARE
    serving code — only `split.py` itself, one level under `drafters/`, is excluded."""
    d = _make_repo(tmp_path, "mlx-vlm")
    c1 = _commit(d, {"mlx_vlm/speculative/drafters/qwen3_5_mtp/model.py": "old\n"}, "init")
    h1 = P.serving_path_hash(str(d), c1)
    c2 = _commit(d, {"mlx_vlm/speculative/drafters/qwen3_5_mtp/model.py": "new\n"}, "drafter head change")
    assert P.serving_path_hash(str(d), c2) != h1


def test_mtp_split_py_under_drafters_is_hash_inert(tmp_path):
    """(c) `mlx_vlm/speculative/drafters/mtp_split.py` (the shared splitter, distinct from the
    top-level `mlx_vlm/split_mtp.py`) is imported only by convert.py/split_mtp.py -- inert."""
    d = _make_repo(tmp_path, "mlx-vlm")
    c1 = _commit(d, {"mlx_vlm/speculative/drafters/mtp_split.py": "old\n",
                     "mlx_vlm/server/generation.py": "a=1\n"}, "init")
    h1 = P.serving_path_hash(str(d), c1)
    c2 = _commit(d, {"mlx_vlm/speculative/drafters/mtp_split.py": "new\n"}, "mtp_split-only")
    assert P.serving_path_hash(str(d), c2) == h1


# --------------------------------------------------------------------------- (g) bad commit
def test_serving_path_hash_on_a_bad_commit_returns_none_without_raising(tmp_path):
    d = _make_repo(tmp_path, "mlx-vlm")
    _commit(d, {"mlx_vlm/server/generation.py": "a=1\n"}, "init")
    assert P.serving_path_hash(str(d), "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef") is None


def test_serving_path_hash_unknown_submodule_name_returns_none(tmp_path):
    d = _make_repo(tmp_path, "some-other-repo")
    c1 = _commit(d, {"x.py": "a=1\n"}, "init")
    assert P.serving_path_hash(str(d), c1) is None


# --------------------------------------------------------------------------- (c) pinned worktree
def test_git_shas_serving_path_follows_the_pinned_worktree_not_the_parent_pointer(
        tmp_path, monkeypatch):
    """The exact scenario this exists for: a submodule worktree checked out at an OLDER commit
    than what the parent repo's tree records for it (a benchmark run in flight, the stack's own
    pointer moved on without a `git submodule update`)."""
    upstream = _make_repo(tmp_path, "upstream-mlx-vlm")
    c1 = _commit(upstream, {"mlx_vlm/server/generation.py": "a=1\n"}, "init")
    _commit(upstream, {"mlx_vlm/server/generation.py": "a=2\n"}, "later upstream change")

    root = tmp_path / "stack"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.example")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("hi\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    subprocess.run(["git", "-C", str(root), "-c", "protocol.file.allow=always",
                   "submodule", "add", str(upstream), "src/mlx-vlm"],
                  check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _git(root, "commit", "-q", "-m", "add submodule")
    # Pin the worktree back to c1 WITHOUT committing that in the parent — the parent's recorded
    # tree entry for src/mlx-vlm still points at the later commit.
    _git(root / "src" / "mlx-vlm", "checkout", "-q", c1)
    recorded = subprocess.check_output(
        ["git", "-C", str(root), "ls-tree", "HEAD", "--", "src/mlx-vlm"], text=True)
    assert c1 not in recorded, "test setup bug: the parent must NOT already record c1"

    monkeypatch.setattr(P.paths, "repo_root", lambda: root)
    (root / "src" / "mlx-serve").mkdir(parents=True)  # absent submodule: serving_path -> None

    shas = P._git_shas()
    assert shas["serving_path"]["src/mlx-vlm"] == P.serving_path_hash(str(root / "src" / "mlx-vlm"), c1)
    assert shas["serving_path"]["src/mlx-serve"] is None


def test_git_shas_serving_path_ignores_a_diverging_submodule_status_line(tmp_path, monkeypatch):
    """FIX-3 (2026-09-03 verifier round): the test above does NOT discriminate a mutation that
    swaps the dedicated `git -C <sub> rev-parse HEAD` call for `subs.get(sub)` (whatever
    `git submodule status` printed) — in the real-submodule case above, `submodule status`
    ALSO reports the worktree HEAD, so the mutant would pass unnoticed. Here `git submodule
    status`'s output is stubbed to a sha that DIFFERS from the worktree's actual `rev-parse HEAD`
    (simulating either a stale/lying status line or that mutation), and `serving_path` must still
    follow the worktree, not the stubbed `submodules` value."""
    d = _make_repo(tmp_path, "mlx-vlm")
    c1 = _commit(d, {"mlx_vlm/server/generation.py": "a=1\n"}, "init")

    root = tmp_path / "stack2"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.example")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("hi\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    (root / "src").mkdir()
    d.rename(root / "src" / "mlx-vlm")

    real_check_output = subprocess.check_output
    fake_sha = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

    def fake_check_output(args, **kwargs):
        if args[:3] == ["git", "submodule", "status"]:
            return f"+{fake_sha} src/mlx-vlm (deadbee)\n"
        return real_check_output(args, **kwargs)

    monkeypatch.setattr(P.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(P.paths, "repo_root", lambda: root)

    shas = P._git_shas()
    assert shas["submodules"]["src/mlx-vlm"] == fake_sha    # the stubbed, WRONG value
    assert shas["submodules"]["src/mlx-vlm"] != c1
    # serving_path must have ignored it and used the real worktree HEAD (c1) instead.
    assert shas["serving_path"]["src/mlx-vlm"] == P.serving_path_hash(str(root / "src" / "mlx-vlm"), c1)


# --------------------------------------------------------------------------- (d) derive_serving_path
def test_derive_serving_path_recomputes_from_recorded_commit_shas(tmp_path):
    root = tmp_path / "stack"
    sub = root / "src" / "mlx-vlm"
    sub.mkdir(parents=True)
    _git(sub, "init", "-q")
    _git(sub, "config", "user.email", "t@t.example")
    _git(sub, "config", "user.name", "t")
    c1 = _commit(sub, {"mlx_vlm/server/generation.py": "a=1\n"}, "init")

    v3_manifest = {"fingerprint_version": 3,
                  "git": {"submodules": {"src/mlx-vlm": c1, "src/mlx-serve": "unknownsha"}}}
    out = P.derive_serving_path(v3_manifest, repo_root=root)
    assert out["src/mlx-vlm"] == P.serving_path_hash(str(sub), c1)
    assert out["src/mlx-serve"] is None    # commit not present locally -> None, never raises


def test_derive_serving_path_missing_git_block_is_all_none(tmp_path):
    assert P.derive_serving_path({}, repo_root=tmp_path) == \
        {"src/mlx-vlm": None, "src/mlx-serve": None}


# --------------------------------------------------------------------------- (e)/(f) is_compatible
def _v5(vlm_hash="h1", serve_hash="h2", vlm_sha="sha-vlm-a", serve_sha="sha-serve-a"):
    return {"fingerprint_version": 5, "sampling_profile": "deployed",
           "sampling": {"temperature": 0.4}, "kv": {"kv_bits": 4},
           "runtime": {"apc_enabled": "0", "draft_kind": "off"},
           "git": {"submodules": {"src/mlx-vlm": vlm_sha, "src/mlx-serve": serve_sha},
                  "serving_path": {"src/mlx-vlm": vlm_hash, "src/mlx-serve": serve_hash}}}


def test_is_compatible_v5_v5_equal_hash_different_sha_is_TRUE():
    a = _v5(vlm_sha="sha-A")
    b = _v5(vlm_sha="sha-B")          # same hashes, different commit shas
    assert a["git"]["serving_path"] == b["git"]["serving_path"]
    assert a["git"]["submodules"] != b["git"]["submodules"]
    assert P.is_compatible(a, b) is True


def test_is_compatible_v5_v5_different_hash_is_FALSE():
    a = _v5(vlm_hash="h1")
    b = _v5(vlm_hash="hDIFFERENT")
    assert P.is_compatible(a, b) is False


def test_is_compatible_v5_vs_v3_derived_uses_hashes(monkeypatch):
    v5 = _v5(vlm_hash="hh", serve_hash="ss")
    v3 = {"fingerprint_version": 3, "sampling_profile": "deployed",
         "sampling": {"temperature": 0.4}, "kv": {"kv_bits": 4},
         "runtime": {"apc_enabled": "0", "draft_kind": "off"},
         "git": {"submodules": {"src/mlx-vlm": "old-tool-only-sha", "src/mlx-serve": "sha-serve-a"}}}
    monkeypatch.setattr(P, "derive_serving_path",
                        lambda man, repo_root=None: {"src/mlx-vlm": "hh", "src/mlx-serve": "ss"})
    # Negotiated version is min(3, 5) = 3 -- a naive commit-sha compare at v3 would refuse on the
    # differing src/mlx-vlm sha; the derived hash must override that for "code".
    assert P.is_compatible(v3, v5) is True
    assert P.is_compatible(v5, v3) is True


def test_is_compatible_v5_vs_v3_derived_still_refuses_a_real_serving_change(monkeypatch):
    v5 = _v5(vlm_hash="hh", serve_hash="ss")
    v3 = {"fingerprint_version": 3, "sampling_profile": "deployed",
         "sampling": {"temperature": 0.4}, "kv": {"kv_bits": 4},
         "runtime": {"apc_enabled": "0", "draft_kind": "off"},
         "git": {"submodules": {"src/mlx-vlm": "old-sha", "src/mlx-serve": "sha-serve-a"}}}
    monkeypatch.setattr(P, "derive_serving_path",
                        lambda man, repo_root=None: {"src/mlx-vlm": "DIFFERENT", "src/mlx-serve": "ss"})
    assert P.is_compatible(v3, v5) is False


def test_is_compatible_both_v5_missing_serving_path_falls_back_to_commit_sha():
    """FIX-1 (2026-09-03 verifier round): two NATIVE v5 manifests that both failed to record
    `serving_path` (e.g. git was unavailable when they were written) do NOT compare "code" as
    None==None -> equal — that silently disagreed with compare.py's DEPLOYED CODE block, which
    already refuses this exact case via its own commit-sha fallback (spec §4). `is_compatible`
    now falls back to the recorded commit sha too, so the two seams agree on one manifest pair:
    differing shas -> incompatible, equal shas -> compatible."""
    def _man(sha):
        return {"fingerprint_version": 5, "sampling_profile": "deployed",
               "sampling": {"temperature": 0.4}, "kv": {"kv_bits": 4},
               "runtime": {"apc_enabled": "0", "draft_kind": "off"},
               "git": {"submodules": {"src/mlx-vlm": sha}, "serving_path": {}}}
    assert P.is_compatible(_man("sha-a"), _man("sha-b")) is False
    assert P.is_compatible(_man("sha-a"), _man("sha-a")) is True


def test_is_compatible_v5_asymmetric_serving_path_availability_is_incompatible():
    """One side recorded a real hash, the other recorded none at all -- genuinely asymmetric
    information, unlike the both-missing case above. Dict equality naturally refuses it, the
    same way a one-sided kv_extra/sampling key already does."""
    a = {"fingerprint_version": 5, "sampling_profile": "deployed", "sampling": {"temperature": 0.4},
        "kv": {"kv_bits": 4}, "runtime": {"apc_enabled": "0", "draft_kind": "off"},
        "git": {"submodules": {"src/mlx-vlm": "sha-a"}, "serving_path": {"src/mlx-vlm": "h1"}}}
    b = {"fingerprint_version": 5, "sampling_profile": "deployed", "sampling": {"temperature": 0.4},
        "kv": {"kv_bits": 4}, "runtime": {"apc_enabled": "0", "draft_kind": "off"},
        "git": {"submodules": {"src/mlx-vlm": "sha-a"}, "serving_path": {}}}
    assert P.is_compatible(a, b) is False


# --------------------------------------------------------------------------- compare.py matrix
import bench.compare as CMP
import bench.generate as G


def _rows(ids):
    return [{"id": i, "sample": 0, "schema_version": 2, "content": r"\boxed{42}",
            "answer_gold": "42", "completion_tokens": 10, "prompt_tokens": 10,
            "thinking_budget": 16384, "finish_reason": "stop"} for i in ids]


def _write_manifest(tmp_results, model, bench, *, git):
    import json
    p = G.result_path(model, bench).with_suffix(".manifest.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {"box": "M5", "sampling_profile": "deployed", "fingerprint_version": 2,
          "sampling": {"temperature": 0.4, "thinking_budget": 16384, "max_tokens": 102400},
          "kv": {"kv_bits": 4}, "runtime": {"apc_enabled": "0"}, "git": git}
    p.write_text(json.dumps(doc))


@pytest.fixture
def _rowfixtures(write_rows, tmp_results):
    write_rows("A", "math500", _rows(["a", "b"]))
    write_rows("B", "math500", _rows(["a", "b"]))
    return tmp_results


def test_compare_refuses_on_different_serving_path_hash(_rowfixtures, monkeypatch):
    _write_manifest(_rowfixtures, "A", "math500",
                    git={"submodules": {"src/mlx-vlm": "sha-A", "src/mlx-serve": "s"}})
    _write_manifest(_rowfixtures, "B", "math500",
                    git={"submodules": {"src/mlx-vlm": "sha-B", "src/mlx-serve": "s"}})
    calls = iter([{"src/mlx-vlm": "hashX", "src/mlx-serve": "same"},
                 {"src/mlx-vlm": "hashY", "src/mlx-serve": "same"}])
    monkeypatch.setattr(CMP.provenance, "serving_path_for", lambda man: next(calls))
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False
    assert "mlx-vlm" in r["reason"] and "C47" in r["reason"]


def test_compare_warns_not_refuses_when_hash_equal_but_sha_differs(_rowfixtures, monkeypatch):
    _write_manifest(_rowfixtures, "A", "math500",
                    git={"submodules": {"src/mlx-vlm": "sha-A", "src/mlx-serve": "s"}})
    _write_manifest(_rowfixtures, "B", "math500",
                    git={"submodules": {"src/mlx-vlm": "sha-B", "src/mlx-serve": "s"}})
    same = {"src/mlx-vlm": "hashX", "src/mlx-serve": "same"}
    monkeypatch.setattr(CMP.provenance, "serving_path_for", lambda man: dict(same))
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is True
    joined = " ".join(r["warnings"])
    assert "C47" in joined and "sha-A"[:12] in joined and "sha-B"[:12] in joined


def test_compare_falls_back_to_commit_sha_refusal_when_hash_unavailable(_rowfixtures, monkeypatch):
    _write_manifest(_rowfixtures, "A", "math500",
                    git={"submodules": {"src/mlx-vlm": "sha-A", "src/mlx-serve": "s"}})
    _write_manifest(_rowfixtures, "B", "math500",
                    git={"submodules": {"src/mlx-vlm": "sha-B", "src/mlx-serve": "s"}})
    monkeypatch.setattr(CMP.provenance, "serving_path_for",
                        lambda man: {"src/mlx-vlm": None, "src/mlx-serve": None})
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is False
    assert "code" in r["reason"].lower() or "mlx-vlm" in r["reason"]
    assert "C47" not in r["reason"]   # this is the UNCHANGED pre-C47 fallback message


def test_compare_unrecorded_git_on_both_sides_still_just_warns(_rowfixtures):
    _write_manifest(_rowfixtures, "A", "math500", git={})
    _write_manifest(_rowfixtures, "B", "math500", git={})
    r = CMP.compare("A", "B", "math500")
    assert r["comparable"] is True
    assert any("unrecorded" in w for w in r["warnings"])
