"""M76 B4b-2 (spec v1.5 §6.2, §6.3, §7.4; change review B12) — the A8 panel packet and export as SCENARIOS: a synthetic tg2 world
(`test_m76_b4b2_fe_support.World`) whose target rust item has real final trees (manifest on `main`, objects / events / session export on a
real git evidence ref), a synthetic polyglot exercise whose start tree is `tg2_materialize.prepare_tree`, and B8-A8 built by
`verify_a8_kv` from that world. The tests drive `kv_a8_context` -> `_a8_packet` and `kv_export(..., b8_a8_path=, a8_inputs=)`.

Class: (a) reproduces a failure the spec fixes · (b) preserves an invariant · (c) new behaviour. Interfaces used (candidate 2):
`P.kv_a8_context(results_root, b8_a8, b8_sha256, repo_root)`, `P._a8_packet(ctx, (session, id), corpus, (top, ref))`,
`P.a8_leak_report(packets)`, `P.kv_export(..., members=("A8-s1",), b8_a8_path=, a8_inputs={results_root, evidence_ref, repo,
polyglot_root})`; the pinned tg2 universe cannot hold a synthetic exercise, so the corpus is a stub with the `.universe` / `.prompt` /
`.polyglot_root()` surface `_a8_packet` reads (`P.a8_corpus` is replaced in the export tests).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from bench import p426_panel as P
from bench import p426_verify as V
from bench import structured_grade as sg
from bench import tg2_materialize as mat
from bench.tests import test_m76_b4b2_fe_support as W

GIT_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
JUDGES = dict(text=[dict(label="claude", family="anthropic", client="claude-code:blind-judge", model="claude-opus"),
                    dict(label="gpt", family="openai", client="cursor-agent", model="gpt-5.6-sol")])
PROMPT = "Implement the solution in src/lib.rs so that the tests pass. Helper modules may go under src/."


def sha(b):
    return hashlib.sha256(b).hexdigest()


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=GIT_ENV).stdout.strip()


# ------------------------------------------------------------------------------------------------------------------ the scenario
class PWorld(W.World):
    """The tg2 world with real final trees for the target item (its manifest on `main` lists the tree's files and shas)."""

    def __init__(self, base, trees, target, **kw):
        self.trees, self.target = trees, target
        super().__init__(base, **kw)

    def _manifest_doc(self, arm, session, rid, **kw):
        if rid == self.target and self.trees.get(arm):
            return dict(files={rel: sha(b) for rel, b in sorted(self.trees[arm].items())}, item=rid, missing=[], **kw)
        return super()._manifest_doc(arm, session, rid, **kw)


class Corpus:
    """What `_a8_packet` reads of the tg2 corpus: the universe entries, the runner's prompt, the polyglot root."""

    def __init__(self, root, rid, entry, prompt=PROMPT):
        self.universe = dict(items={rid: entry})
        self._root, self._prompt = Path(root), prompt

    def prompt(self, prepared, inject=None):
        return self._prompt

    def polyglot_root(self):
        return self._root


class Scenario:
    def __init__(self, tmp_path, tweak=None, export_text=None, bad_object=False):
        self.tmp = Path(tmp_path)
        sched = W.schedule_ids(W.tg2_schedule("s1"))
        self.rid = next(i for i in sched if i.startswith("rust/"))
        self.lang, self.item = self.rid.split("/", 1)
        self.poly = self.tmp / "polyglot"
        ex = self.poly / "rust" / "exercises" / "practice" / self.item
        files = {".meta/config.json": json.dumps(dict(files=dict(solution=["src/lib.rs", "Cargo.toml"], test=[f"tests/{self.item}.rs"],
                                                               example=[".meta/example.rs"]))),
                 ".meta/example.rs": "pub fn f() -> u8 { 0 }\n", ".docs/instructions.md": "Do it.\n",
                 "Cargo.toml": '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n',
                 "src/lib.rs": "pub fn f() -> u8 { unimplemented!() }\n", f"tests/{self.item}.rs": "#[test]\nfn t() { assert_eq!(x::f(), 1); }\n"}
        for rel, text in files.items():
            (ex / rel).parent.mkdir(parents=True, exist_ok=True)
            (ex / rel).write_text(text)
        start_dir = self.tmp / "start"
        mat.prepare_tree(self.poly, "rust", self.item, start_dir)
        self.prepared = sg.manifest(start_dir)
        self.start = {rel: (start_dir / rel).read_bytes() for rel in self.prepared}
        self.entry = dict(status="valid", prepared=self.prepared, solutions=["src/lib.rs"], tests=[f"tests/{self.item}.rs"])
        self.corpus = Corpus(self.poly, self.rid, self.entry)
        trees = {}
        for arm, body in (("n16", b"pub fn f() -> u8 { 1 }\n"), ("x", b"pub fn f() -> u8 { 2 }\n")):
            tree = dict(self.start)
            tree["src/lib.rs"] = body
            if tweak:
                tweak(arm, tree)
            trees[arm] = tree
        self.trees = trees
        # only the target is a both-arm pass: the export selects exactly it (the other 79 are "not both pass")
        self.w = PWorld(self.tmp / "w", trees, self.rid, corpus="tg2", sessions=("s1",),
                        outcomes={("x", "s1"): {i: False for i in sched if i != self.rid}})
        (self.w.root / "B8.json").write_text(json.dumps(dict(lever="kv", pair=["n16", "x"], axes={}, generator="bench.p426_verify")))
        self.git = self.tmp / "evidence"
        self.git.mkdir()
        git(self.git, "init", "-q")
        prefix = V.KV_REPO_PREFIX
        for arm in ("n16", "x"):
            run = self.w.runs[(arm, "s1", "rust")]
            stem = f"{V.A8_NS}/{self.w.att(arm, 's1')}/evidence/{run}/{self.lang}__{self.item}"
            events = b"".join(json.dumps(dict(type="tool_use", part=dict(tool=t))).encode() + b"\n" for t in ("read", "edit", "read"))
            text = export_text(arm) if export_text else PROMPT
            export = json.dumps(dict(messages=[dict(type="user", text=text), dict(type="assistant", content=[])])).encode()
            for rel, data in trees[arm].items():
                self._put(f"{prefix}{stem}.final_tree/objects/{sha(data)}", b"tampered\n" if (bad_object and arm == "x" and rel == "src/lib.rs")
                          else data)
            self._put(f"{prefix}{stem}.events.jsonl", events)
            self._put(f"{prefix}{stem}.json", export)
            self.w.edit_row(arm, "s1", self.rid, evidence_sha256=dict(events=sha(events), export=sha(export)))
            self.w.edit_harvest(arm, "s1", lambda d, ev=events, ex_=export, st=stem: d["files"].extend([
                dict(destination="evidence", published=f"{prefix}{st}.events.jsonl", sha256=sha(ev), published_sha256=sha(ev),
                     source="x", compression=None, exclusion_reason=None),
                dict(destination="evidence", published=f"{prefix}{st}.json", sha256=sha(ex_), published_sha256=sha(ex_),
                     source="x", compression=None, exclusion_reason=None)]))
        git(self.git, "add", "-A")
        git(self.git, "commit", "-q", "-m", "evidence")
        self.commit = git(self.git, "rev-parse", "HEAD")
        self.w.write_rechecks(ack=True, gates=("s1",))
        self.doc = V.verify_a8_kv(self.w.root)
        s1 = {p["pair"]: p for p in self.doc["pairs"]}["s1"]
        assert s1["accepted"], s1["reasons"]                   # the scenario's premise: B8-A8 accepts the session
        self.b8_sha = self.w.base_b8_sha()

    def _put(self, rel, data):
        path = self.git / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def top_ref(self):
        top = V.repo_top(self.git)
        return top, V.resolve_commit(top, self.commit, "--evidence-ref")

    def context(self):
        return P.kv_a8_context(self.w.root, self.doc, self.b8_sha, V.STACK_REPO)

    def packet(self):
        return P._a8_packet(self.context(), ("s1", self.rid), self.corpus, self.top_ref())

    def export(self, monkeypatch, out):
        (self.w.root / "B8-A8.json").write_text(V.dumps(self.doc))
        judges = self.tmp / "judges.json"
        judges.write_text(json.dumps(JUDGES))
        monkeypatch.setattr(P, "a8_corpus", lambda *a, **k: self.corpus)
        return P.kv_export(self.w.root.parent, self.w.root / "B8.json", judges, out, members=("A8-s1",),
                           b8_a8_path=self.w.root / "B8-A8.json",
                           a8_inputs=dict(results_root=self.w.root, evidence_ref=self.commit, repo=self.git, polyglot_root=self.poly))


# ------------------------------------------------------------------------------------------------------------------ the packet
# (c) both arms' final trees, bound by B8-A8 and read from the evidence ref, become the diff against the prepared start tree
def test_the_packet_is_the_runners_prompt_and_each_arms_diff(tmp_path):
    sc = Scenario(tmp_path)
    pkt = sc.packet()
    assert PROMPT in pkt["task"] and pkt["task"].startswith("### Task")
    assert "b/src/lib.rs" in pkt["off"] and "{ 1 }" in pkt["off"] and "{ 2 }" not in pkt["off"]
    assert "b/src/lib.rs" in pkt["on"] and "{ 2 }" in pkt["on"]
    assert "Tool use" in pkt["off"] and "read 2" in pkt["off"] and "edit 1" in pkt["off"]
    assert pkt["len_off"] > 0 and pkt["len_on"] > 0
    assert "tests/" not in pkt["off"] and "Cargo.toml" not in pkt["off"]            # unchanged files are not in the diff


# (c) an item whose prompt is not the runner's (the export's first user message differs) refuses
def test_a_prompt_that_is_not_the_runners_refuses(tmp_path):
    sc = Scenario(tmp_path, export_text=lambda arm: PROMPT if arm == "n16" else "Please solve the exercise in some other way")
    with pytest.raises(V.RefusalError, match="first user message"):
        sc.packet()


# (c) ... the opencode export quotes the run argument: the quoted prompt is the runner's too
def test_the_quoted_prompt_is_the_runners_prompt(tmp_path):
    assert PROMPT in Scenario(tmp_path, export_text=lambda arm: f'"{PROMPT}"').packet()["task"]


# (a) delivery 5, real bytes: opencode records the run argument double-quoted with each embedded `"` backslash-escaped (the real
# rust/say pilot export: `It's fine to stop at \"trillion\".`); the quoted, escaped prompt IS the runner's prompt
def test_the_exports_escaped_embedded_quotes_are_the_runners_prompt(tmp_path):
    prompt = PROMPT + ' It\'s fine to stop at "trillion".'
    sc = Scenario(tmp_path, export_text=lambda arm: '"' + prompt.replace('"', '\\"') + '"')
    sc.corpus._prompt = prompt
    assert prompt in sc.packet()["task"]


# (c) ... and an export whose escaped text differs by one word is not
def test_an_escaped_export_that_differs_still_refuses(tmp_path):
    prompt = PROMPT + ' It\'s fine to stop at "trillion".'
    sc = Scenario(tmp_path, export_text=lambda arm: '"' + prompt.replace('"', '\\"').replace("trillion", "billion") + '"')
    sc.corpus._prompt = prompt
    with pytest.raises(V.RefusalError, match="first user message"):
        sc.packet()


# (c) an item whose start tree is not the bound one (the polyglot checkout changed under the universe's `prepared`) refuses
def test_a_start_tree_that_is_not_the_bound_one_refuses(tmp_path):
    sc = Scenario(tmp_path)
    (sc.poly / "rust" / "exercises" / "practice" / sc.item / "src" / "lib.rs").write_text("pub fn f() -> u8 { 99 }\n")
    with pytest.raises(V.RefusalError, match="prepared"):
        sc.packet()


# (c) an item whose final tree is not the bound one refuses: an object that does not hash to its name ...
def test_a_final_tree_object_that_is_not_its_name_refuses(tmp_path):
    with pytest.raises(V.RefusalError, match="hashes to"):
        Scenario(tmp_path, bad_object=True).packet()


# (c) ... and a manifest on `main` changed after B8-A8 read it (the record no longer binds it)
def test_a_final_tree_manifest_changed_after_b8_a8_refuses(tmp_path):
    sc = Scenario(tmp_path)
    path = next(sc.w.root.glob(f"{V.A8_NS}/tg2-m76-x-s1.a1/evidence/*/{sc.lang}__{sc.item}.final_tree/manifest.json"))
    path.write_text(path.read_text() + " ")
    with pytest.raises(V.RefusalError, match="changed|sha"):
        sc.context()


# (c) a protected path that changed (the tests the grader holds) is refused: the final tree is the grader's accepted files
def test_a_changed_protected_test_file_refuses(tmp_path):
    def tweak(arm, tree):
        if arm == "x":
            tree[f"tests/{Scenario_item(tmp_path)}.rs"] = b"#[test]\nfn t() { assert!(true); }\n"
    with pytest.raises(V.RefusalError, match="protected path"):
        Scenario(tmp_path, tweak=tweak).packet()


def Scenario_item(tmp_path):
    return next(i for i in W.schedule_ids(W.tg2_schedule("s1")) if i.startswith("rust/")).split("/", 1)[1]


# (c) ... except a Rust Cargo.toml the grader accepted, which is diffed as content
def test_a_grader_accepted_rust_cargo_toml_is_diffed_as_content(tmp_path):
    def tweak(arm, tree):
        if arm == "x":
            tree["Cargo.toml"] = tree["Cargo.toml"] + b'\n[dependencies]\nregex = "1"\n'
    pkt = Scenario(tmp_path, tweak=tweak).packet()
    assert "a/Cargo.toml" in pkt["on"] and '+regex = "1"' in pkt["on"] and "Cargo.toml" not in pkt["off"]


# (c) a new helper file is part of the diff (nothing protected is new)
def test_a_new_helper_file_is_in_the_diff(tmp_path):
    def tweak(arm, tree):
        if arm == "x":
            tree["src/helper.rs"] = b"pub fn h() {}\n"
    pkt = Scenario(tmp_path, tweak=tweak).packet()
    assert "b/src/helper.rs" in pkt["on"] and "helper" not in pkt["off"]


# ------------------------------------------------------------------------------------------------------------------ the leak rule
# (b) the leak report names the pattern per item, never the matched text
def test_the_leak_report_names_patterns_not_text():
    pkts = {"rust/a": dict(task="clean", off="clean", on="uses caslca/some-model and SECRET-ANSWER"),
            "rust/b": dict(task="clean", off="clean", on="clean")}
    rep = P.a8_leak_report(pkts)
    assert list(rep) == ["rust/a"] and rep["rust/a"] and not any("SECRET" in h for h in rep["rust/a"])


# (c) a leak refuses that member's export, per item, writing nothing
def test_a_leaking_item_refuses_the_member_export(tmp_path, monkeypatch):
    def tweak(arm, tree):
        if arm == "x":
            tree["src/lib.rs"] = b"// tuned for the n16 comparison\npub fn f() -> u8 { 2 }\n"
    sc = Scenario(tmp_path, tweak=tweak)
    out = tmp_path / "panel"
    out.mkdir()
    with pytest.raises(V.RefusalError) as exc:
        sc.export(monkeypatch, out)
    msg = str(exc.value)
    assert sc.rid in msg and "tuned for" not in msg and "A8-s1" in msg
    assert not list(out.iterdir())


# (c) a clean item exports: the member is frozen against B8-A8's FILE sha (A1-A7 stay on B8's)
def test_a_clean_item_exports_a_member_frozen_against_b8_a8(tmp_path, monkeypatch):
    sc = Scenario(tmp_path)
    out = tmp_path / "panel"
    out.mkdir()
    done = sc.export(monkeypatch, out)
    frozen = done["A8-s1"]
    assert frozen["b8_sha256"] == sha((sc.w.root / "B8-A8.json").read_bytes()) != sc.b8_sha
    assert (out / "A8-s1").is_dir() and not list(out.glob(".*.partial"))


# (c) the export of an A8 member needs the B8-A8 record
def test_an_a8_member_without_b8_a8_refuses(tmp_path, monkeypatch):
    sc = Scenario(tmp_path)
    judges = tmp_path / "judges.json"
    judges.write_text(json.dumps(JUDGES))
    out = tmp_path / "panel"
    out.mkdir()
    with pytest.raises(V.RefusalError):
        P.kv_export(sc.w.root.parent, sc.w.root / "B8.json", judges, out, members=("A8-s1",))
