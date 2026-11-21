"""M76 B4b-2 panel (`p426_panel`): the A8 members (frozen against B8-A8's sha, A1–A7 against B8's), the code rubric, the Holm
family, the A8 packet (the prompt check against the evidence export, the protected-path assertion incl. a grader-accepted Rust
`Cargo.toml`, non-UTF-8 listing), the leak refusal per item, selection on the row's own `passed` (spec v1.5 §6, §7.4, §9.1)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from bench import p426_panel as P
from bench import p426_signals as S
from bench import p426_verify as V
from bench.tests.test_m76_b4b2_impl_world import A8World, attempt, dumps

BENCH = Path(__file__).resolve().parents[2]


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------------------------------------ members / rubric
def test_members_are_unchanged_without_b8_a8():
    assert P.kv_members() == ("A1", "A2", "A3", "A4", "A5", "A7-s1", "A7-s2", "A7-s3")
    assert P.kv_members(a8_sessions=("s1", "s2"))[-2:] == ("A8-s1", "A8-s2")
    assert P.kv_rubric("A8-s1") == P.kv_rubric("A7-s1") == "code" and "A8" in P.KV_INPUT_SOURCE


def test_the_a8_members_are_b8_a8s_accepted_confirmatory_sessions(tmp_path):
    w = A8World(tmp_path, sessions=("pilot", "s1"))
    doc = w.b8_a8()
    assert P.kv_a8_member_sessions(doc) == ("s1",) and P.kv_a8_member_sessions(None) == ()
    b8 = dict(axes=dict(A7=dict(sessions=["s1"], pairs=[dict(pair="s1", accepted=True)])))
    assert P.kv_expected_members(b8) == ["A7-s1"]
    assert P.kv_expected_members(b8, b8_a8=doc) == ["A7-s1", "A8-s1"]


def test_the_holm_family_adds_a8_and_keeps_the_raw_statistics():
    members = {m: dict(judged=8, identical=0, vector=[0.5] * 8, mean=1.0) for m in ("A1", "A2", "A7-s1")}
    members["A8-s1"] = dict(judged=6, identical=0, vector=[0.5] * 6, mean=1.0)
    base = S.kv_panel_family({k: v for k, v in members.items() if k != "A8-s1"})
    fam = S.kv_panel_family(members, a8_sessions=("s1",))
    assert base["family"] == ["A1", "A2", "A7-s1"] and fam["family"] == ["A1", "A2", "A7-s1", "A8-s1"]
    for m in base["family"]:
        assert fam["members"][m]["permutation_p"] == base["members"][m]["permutation_p"]     # raw statistics unchanged
    assert fam["m"] == 4 and any(fam["members"][m]["holm_p"] != base["members"][m]["holm_p"] for m in base["family"])
    assert S.kv_panel_family(members) == base                                               # without B8-A8: no A8 member


# ------------------------------------------------------------------------------------------------ §6.2 protected paths / diff
def _entry(lang, prepared, solutions):
    return dict(lang=lang, prepared={k: sha(v) for k, v in prepared.items()}, solutions=solutions)


def test_a_grader_accepted_cargo_toml_is_diffed_as_content():
    start = {"Cargo.toml": b'[package]\nname = "x"\n', "src/lib.rs": b"pub fn f() {}\n", "tests/t.rs": b"#[test]\nfn t() {}\n"}
    entry = _entry("rust", start, ["src/lib.rs"])
    tree = {"Cargo.toml": b'[package]\nname = "x"\n[dependencies]\nregex = "1"\n', "src/lib.rs": b"pub fn f() { 1; }\n",
            "src/helper.rs": b"pub fn h() {}\n"}
    diff, binary = P._a8_diff(entry, tree, [], start, "w")
    assert "+[dependencies]" in diff and "b/src/helper.rs" in diff and "b/src/lib.rs" in diff and binary == []
    assert diff.index("a/Cargo.toml") < diff.index("b/src/helper.rs") < diff.index("b/src/lib.rs")          # sorted by path


@pytest.mark.parametrize("lang,rel", [("rust", "tests/t.rs"), ("javascript", "package.json"), ("javascript", "babel.config.js"),
                                      ("java", "build.gradle"), ("cpp", "CMakeLists.txt")])
def test_a_changed_protected_path_refuses(lang, rel):
    start = {rel: b"original\n", "sol.x": b"stub\n"}
    entry = _entry(lang, start, ["sol.x"])
    with pytest.raises(V.RefusalError, match=f"protected path {rel}"):
        P._a8_diff(entry, {rel: b"changed\n", "sol.x": b"done\n"}, [], start, "w")


def test_a_cargo_toml_outside_rust_is_protected():
    start = {"Cargo.toml": b"a\n", "sol.x": b"stub\n"}
    with pytest.raises(V.RefusalError, match="protected path Cargo.toml"):
        P._a8_diff(_entry("cpp", start, ["sol.x"]), {"Cargo.toml": b"b\n"}, [], start, "w")


def test_non_utf8_files_are_listed_by_path_and_size_and_unchanged_files_skipped():
    start = {"sol.js": b"stub\n", "spec.js": b"t\n"}
    entry = _entry("javascript", start, ["sol.js"])
    diff, binary = P._a8_diff(entry, {"sol.js": b"stub\n", "data.bin": b"\xff\xfe\x00"}, [], start, "w")
    assert diff == "" and binary == ["data.bin (3 bytes)"]
    resp = P._a8_response(diff, binary, "read 2")
    assert "### Non-UTF-8 files" in resp and "- data.bin (3 bytes)" in resp and resp.endswith("read 2")


# ------------------------------------------------------------------------------------------------ §6.2 the prompt check
class _Corpus:
    def __init__(self, prompt):
        self._prompt = prompt
        self.universe = dict(items={"rust/say": dict(status="valid", prepared={"src/lib.rs": "0" * 64}, solutions=["src/lib.rs"])})

    def prompt(self, prepared, inject=None):
        assert inject is None and prepared.lang == "rust" and prepared.name == "say"
        return self._prompt


def _export_world(tmp_path, monkeypatch, text):
    export = json.dumps(dict(info={}, messages=[dict(type="user", text=text), dict(type="assistant", content=[])])).encode()
    raw = "a" * 64
    pub = f"{V.KV_REPO_PREFIX}{V.A8_NS}/tg2-m76-x-s1.a1/evidence/RUN1/rust__say.json"
    att = dict(name="tg2-m76-x-s1.a1", harvest=dict(files=[dict(destination="evidence", published=pub, sha256=raw,
                                                                 published_sha256=sha(export))]))
    row = dict(final_tree=dict(manifest="$STACK_WORKDIR/t/stem.L0.full.a1.RUN1/rust__say.final_tree/manifest.json"),
               evidence_sha256=dict(export=raw))
    monkeypatch.setattr(P, "_git_show", lambda top, ref, path: export if path == pub else b"")
    return dict(prefix=V.KV_REPO_PREFIX, namespace=V.A8_NS), att, row


@pytest.mark.parametrize("quoted", [True, False])
def test_the_prompt_check_passes_on_the_runners_prompt(tmp_path, monkeypatch, quoted):
    prompt = "Implement the solution in src/lib.rs so that …; Helper modules may go under src/."
    ctx, att, row = _export_world(tmp_path, monkeypatch, f'"{prompt}"' if quoted else prompt)
    got, entry = P.a8_prompt_check(ctx, att, row, "rust/say", _Corpus(prompt), ("top", "ref"))
    assert got == prompt and entry["lang"] == "rust"


def test_the_prompt_check_refuses_a_different_first_user_message(tmp_path, monkeypatch):
    ctx, att, row = _export_world(tmp_path, monkeypatch, "Implement something else")
    with pytest.raises(V.RefusalError, match="first user message"):
        P.a8_prompt_check(ctx, att, row, "rust/say", _Corpus("Implement the solution"), ("top", "ref"))


def test_the_prompt_check_refuses_an_export_harvest_does_not_bind(tmp_path, monkeypatch):
    ctx, att, row = _export_world(tmp_path, monkeypatch, "p")
    row["evidence_sha256"]["export"] = "b" * 64
    with pytest.raises(V.RefusalError, match="no single HARVEST evidence record"):
        P.a8_prompt_check(ctx, att, row, "rust/say", _Corpus("p"), ("top", "ref"))
    row["evidence_sha256"]["export"] = "a" * 64
    monkeypatch.setattr(P, "_git_show", lambda top, ref, path: b'{"messages": []}')
    with pytest.raises(V.RefusalError, match="not the HARVEST-published bytes"):
        P.a8_prompt_check(ctx, att, row, "rust/say", _Corpus("p"), ("top", "ref"))


def _polyglot():
    root = Path(os.environ.get("POLYGLOT_DIR") or str(Path(os.environ.get("STACK_WORKDIR", "")) / "polyglot-benchmark"))
    if not (root / "rust").is_dir():
        pytest.skip("polyglot corpus not found (set POLYGLOT_DIR / STACK_WORKDIR)")
    pinned = json.loads((BENCH / "m65" / "tg2_universe.json").read_text())["polyglot_sha"]
    return P.a8_corpus(root, polyglot_sha=lambda r: pinned)


def test_the_real_prompt_and_start_tree_are_the_runners():
    """E1: the rebuilt prompt is `corpus_tg2.prompt` (the helper sentence H, no inject addendum); the start tree is
    `tg2_materialize.prepare_tree`, hashed against the universe's `prepared` (never `_StartTree`)."""
    from bench import corpus_tg2
    corpus = _polyglot()
    for rid in ("rust/say", "javascript/word-search", "java/zipper", "cpp/spiral-matrix"):
        prompt, entry = P.a8_prompt(corpus, rid)
        assert prompt.startswith("Implement the solution in ") and prompt.endswith(corpus_tg2.HINTS[rid.split("/")[0]])
        start = P._a8_start_tree(corpus, rid, entry)
        assert {k: sha(v) for k, v in start.items()} == entry["prepared"]


def test_a_polyglot_checkout_at_another_sha_refuses():
    corpus = _polyglot()
    corpus._polyglot_sha = lambda r: "0" * 40
    with pytest.raises(V.RefusalError, match="pinned polyglot root"):
        P.a8_prompt(corpus, "rust/say")


# ------------------------------------------------------------------------------------------------ §6.3 leaks
def test_the_leak_report_names_patterns_per_item():
    from bench.p426_verify import ENTRY
    home, user = P._box_identity()
    packets = {"rust/a": dict(task="t", off="uses the n16 cache", on="ok"),
               "cpp/b": dict(task="t", off=f"model {ENTRY}", on=f"path {home}/x"),
               "java/c": dict(task="t", off="Qwen2.5 docs", on="a /Users/example/path in an answer")}  # allow-shorthand allow-pii-pattern: a leak-rule input (a fake home path the rule must catch)
    rep = P.a8_leak_report(packets)
    box = {"box-home"} | ({"box-user"} if user and user in home else set())
    assert rep == {"cpp/b": sorted(box | {"registry-name"}), "rust/a": [r"\bn16\b"]}     # family tokens / generic paths: content


# ------------------------------------------------------------------------------------------------ §6.1 export / ingestion
def _export_setup(tmp_path, monkeypatch, rows=None, text=lambda rid, arm: f"diff of {rid} by {arm}"):
    w = A8World(tmp_path / "w", sessions=("pilot", "s1"), rows=rows)
    b8 = dict(lever="kv", axes={}, pair=["n16", "x"], inputs={})
    b8_path = tmp_path / "B8.json"
    b8_path.write_text(V.dumps(b8))
    b8_sha = sha(b8_path.read_bytes())
    a8_path = tmp_path / "B8-A8.json"
    a8_path.write_text(V.dumps(V.verify_a8_kv(w.root, b8_sha)))
    judges = tmp_path / "judges.json"
    judges.write_text(json.dumps(dict(text=[dict(label="j1", family="f1", client="claude-code", model="m1"),
                                            dict(label="j2", family="f2", client="cursor-agent", model="m2")])))
    out = tmp_path / "panel"
    out.mkdir()
    seen = []

    def packet(ctx, item, corpus, top_ref):
        seen.append(item)
        return dict(task=f"### Task\n\nprompt {item[1]}\n\n{P.A8_TASK_GRADER}", off=text(item[1], "off"), on=text(item[1], "on"),
                    len_off=10, len_on=12)
    monkeypatch.setattr(P, "_a8_packet", packet)
    monkeypatch.setattr(P, "a8_corpus", lambda *a, **k: object())
    monkeypatch.setattr(V, "repo_top", lambda repo: Path(repo))
    monkeypatch.setattr(V, "resolve_commit", lambda top, ref, what: "e" * 40)
    a8_inputs = dict(results_root=w.root, evidence_ref="origin/evidence", repo=tmp_path, polyglot_root=tmp_path)
    return w, b8_path, b8_sha, a8_path, judges, out, a8_inputs, seen


def test_the_a8_member_is_frozen_against_b8_a8_and_selects_on_passed(tmp_path, monkeypatch):
    probe = A8World(tmp_path / "probe", sessions=("s1",))
    one_arm = probe.ids("s1")[5]
    w, b8_path, b8_sha, a8_path, judges, out, a8_inputs, seen = _export_setup(
        tmp_path, monkeypatch, rows={("x", "s1"): {one_arm: dict(passed=False)}})
    done = P.kv_export(w.root.parent, b8_path, judges, out, members=("A8-s1",), b8_a8_path=a8_path, a8_inputs=a8_inputs)
    frozen = done["A8-s1"]
    a8_sha = sha(a8_path.read_bytes())
    assert frozen["b8_sha256"] == a8_sha != b8_sha and frozen["rubric"] == "code"
    assert frozen["excluded"] == {"not both pass": [one_arm]} and len(seen) == 79 and ("s1", one_arm) not in seen
    assert frozen["counts"]["planned_verdicts"] == 79 * 2 * 2
    members = P.kv_panel_members(out, "n16", "x", b8_sha, a8_sessions=("s1",), b8_a8_sha256=a8_sha)
    assert members["A8-s1"]["planned_items"] == 79
    with pytest.raises(V.RefusalError, match="another B8-A8 record"):
        P.kv_panel_members(out, "n16", "x", b8_sha, a8_sessions=("s1",), b8_a8_sha256="0" * 64)
    assert P.kv_panel_members(out, "n16", "x", b8_sha) == {}                       # without B8-A8: no A8 member is read


def test_a_leak_refuses_the_member_per_item(tmp_path, monkeypatch):
    w, b8_path, _b8_sha, a8_path, judges, out, a8_inputs, _seen = _export_setup(
        tmp_path, monkeypatch, text=lambda rid, arm: f"tq4 kv_bits {rid}" if arm == "on" and rid.startswith("cpp/") else "clean")
    with pytest.raises(V.RefusalError, match="per item") as exc:
        P.kv_export(w.root.parent, b8_path, judges, out, members=("A8-s1",), b8_a8_path=a8_path, a8_inputs=a8_inputs)
    assert "cpp/" in str(exc.value) and "kv_bits" in str(exc.value) and not (out / "A8-s1").exists()


def test_the_export_refuses_a_b8_a8_of_another_b8(tmp_path, monkeypatch):
    w, b8_path, _b8_sha, a8_path, judges, out, a8_inputs, _seen = _export_setup(tmp_path, monkeypatch)
    b8_path.write_text(V.dumps(dict(lever="kv", axes={}, pair=["n16", "x"], inputs={}, note="another")))
    with pytest.raises(V.RefusalError, match="another B8.json"):
        P.kv_export(w.root.parent, b8_path, judges, out, members=("A8-s1",), b8_a8_path=a8_path, a8_inputs=a8_inputs)


def test_an_a8_member_is_not_in_the_family_without_b8_a8(tmp_path, monkeypatch):
    w, b8_path, _b8_sha, _a8_path, judges, out, _a8_inputs, _seen = _export_setup(tmp_path, monkeypatch)
    with pytest.raises(V.RefusalError, match="not in the KV family"):
        P.kv_export(w.root.parent, b8_path, judges, out, members=("A8-s1",))
