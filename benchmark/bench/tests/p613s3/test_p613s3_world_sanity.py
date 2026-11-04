"""The hermetic world is itself checked (these tests need none of the step-3 code and PASS on the baseline).

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from bench.tests.p613s3 import s3world as S
from bench.tests.p613s3.test_p613s3_signals import exact_p


def rows_of(case, arm, session):
    out = {}
    for f in sorted((case.attempt(arm, session) / session).glob("*.jsonl")):
        for line in f.read_text().splitlines():
            r = json.loads(line)
            out[r["id"]] = r
    return out


# class: invariant (B8 over the world: the four A7 pairs accepted, identical counts as designed)
def test_world_b8_shape(a7):
    pairs = {p["pair"]: p for p in a7.b8["axes"]["A7"]["pairs"]}
    assert set(pairs) == {"s1", "s2", "pilot", "reload"} and all(p["accepted"] for p in pairs.values())
    assert sum(k["identical"] for k in pairs["s1"]["keys"]) == 1 and sum(k["identical"] for k in pairs["s2"]["keys"]) == 2
    assert [r["key"] for r in pairs["s1"]["keys_rejected"]] == [["s1", "go/psi"]]
    assert sum(p["identical"]["n"] for p in a7.b8["axes"]["wave1"]["pairs"]) == 24


# class: invariant (the selection rule, computed independently from the rows + B8 flags, gives the designed counts)
def test_world_selection_by_rule(a7):
    sel, ident, one, neither = {}, {}, {}, {}
    for pair in a7.b8["axes"]["A7"]["pairs"]:
        if pair["role"] != "pair":
            continue
        s = pair["pair"]
        off, on = rows_of(a7, "off", s), rows_of(a7, "on", s)
        rejected = {tuple(r["key"]) for r in pair["keys_rejected"]}
        for k in pair["keys"]:
            rid = k["key"][1]
            both = off[rid]["passed"] is True and on[rid]["passed"] is True
            if k["identical"]:
                ident.setdefault(s, []).append(rid)
            elif both:
                sel.setdefault(s, []).append(rid)
            elif off[rid]["passed"] is True or on[rid]["passed"] is True:
                one.setdefault(s, []).append(rid)
            else:
                neither.setdefault(s, []).append(rid)
        assert rejected == ({("s1", "go/psi")} if s == "s1" else set())
    assert sorted(sel["s1"]) == sorted(S.S1_SEL) and sorted(sel["s2"]) == sorted(S.S2_SEL)
    assert len(ident["s1"]) == 1 and len(ident["s2"]) == 2
    assert sorted(one["s1"]) == sorted(S.S1_ONE) and sorted(one["s2"]) == sorted(S.S2_ONE)
    assert neither["s1"] == S.S1_NEITHER and neither["s2"] == S.S2_NEITHER


# class: invariant (every evidence object hashes to its name, every events file to the row's sha, every start file to the universe)
def test_world_hashes_are_consistent(a7):
    universe = json.loads(a7.universe.read_text())["items"]
    for session in ("s1", "s2"):
        for arm in ("off", "on"):
            for rid, row in rows_of(a7, arm, session).items():
                tree = a7.item_dir(arm, session, rid)
                manifest = json.loads((tree / "manifest.json").read_text())
                assert S.sha_file(tree / "manifest.json") == row["final_tree"]["manifest_sha256"]
                base = tree.relative_to(a7.repo).as_posix()
                for name, sha in manifest["files"].items():
                    blob = subprocess.run(["git", "-C", str(a7.repo), "show", f"{a7.evidence_ref}:{base}/objects/{sha}"],
                                          capture_output=True, check=True).stdout
                    assert S.sha_bytes(blob) == sha
                ev = subprocess.run(["git", "-C", str(a7.repo), "show", f"{a7.evidence_ref}:{base[:-len('.final_tree')]}.events.jsonl"],
                                    capture_output=True, check=True).stdout
                # E2: the evidence-branch events file is the SCRUBBED copy; HARVEST binds raw (row) sha -> published (branch) sha
                harvest = json.loads((a7.attempt(arm, session) / "HARVEST.json").read_text())
                lang, item = rid.split("/")
                recs = [f for f in harvest["files"] if f["published"].endswith(f"/{lang}__{item}.events.jsonl")]
                assert len(recs) == 1 and recs[0]["destination"] == "evidence"
                assert recs[0]["sha256"] == row["evidence_sha256"]["events"] and S.sha_bytes(ev) == recs[0]["published_sha256"]
                assert S.sha_bytes(ev) != row["evidence_sha256"]["events"]
                # W1: real rows name the run directory in final_tree.manifest
                assert row["final_tree"]["manifest"].endswith(f"/{lang}__{item}.final_tree/manifest.json")
    for rid, item in universe.items():
        lang, name = rid.split("/")
        for rel, sha in item["prepared"].items():
            f = a7.polyglot / lang / "exercises" / "practice" / name / rel
            assert S.sha_file(f) == sha, (rid, rel)


# class: invariant (the known case's events carry exactly the designed tool counts, with noise around them)
def test_world_known_case_events(a7):
    tree = a7.item_dir("off", "s1", "python/alpha")
    ev = subprocess.run(["git", "-C", str(a7.repo), "show",
                         f"{a7.evidence_ref}:{tree.relative_to(a7.repo).as_posix()[:-len('.final_tree')]}.events.jsonl"],
                        capture_output=True, check=True, text=True).stdout
    docs = [json.loads(l) for l in ev.splitlines()]
    tools = {}
    for d in docs:
        if d["type"] == "tool_use":
            tools[d["part"]["tool"]] = tools.get(d["part"]["tool"], 0) + 1
    assert tools == {"edit": 2, "read": 3, "shell": 2, "write": 1}
    assert {d["type"] for d in docs} == {"step_start", "tool_use", "text", "step_finish"}
    assert [d["part"]["tool"] for d in docs if d["type"] == "tool_use"] != sorted(d["part"]["tool"] for d in docs if d["type"] == "tool_use")


# class: invariant (the evidence is not in the work tree: it can only be read through the git objects)
def test_world_evidence_is_not_checked_out(a7):
    assert not list(a7.results_root.glob("wave2/*/evidence/*/*.events.jsonl"))
    assert not list(a7.results_root.glob("wave2/*/evidence/*/*.final_tree/objects"))


# class: invariant (hand-computed exact sign-flip p values used by the signals tests)
def test_exact_p_values():
    assert exact_p([.5, .375, 0, 0, .125, .5]) == 0.125
    assert exact_p([.375, 0, 0, .125, .5]) == 0.25
    assert exact_p([-0.5] * 8) == 2 / 256
    assert exact_p([0.5] * 4) == 0.125


# class: invariant (the fake `cursor-agent`: version, a verdict, failure, garbage; each judging call is logged once)
def test_fake_cursor_agent(tmp_path):
    fake = S.install_fake_cursor(tmp_path / "bin")
    log = tmp_path / "log"
    env = {"FAKE_CURSOR_LOG": str(log), "FAKE_CURSOR_FAIL": "p0002", "FAKE_CURSOR_MODE": "B"}
    full = {"PATH": f"{fake}:/usr/bin:/bin", **env}
    def call(*argv):
        return subprocess.run(["cursor-agent", *argv], capture_output=True, text=True, env=full)
    assert call("--version").stdout.strip() == "9.9.9-fake" and not log.exists()
    r = call("-p", "Read the file p0001.md in this workspace")
    assert json.loads(r.stdout) == {"choice": "B", "rationale": "fake judge"}
    assert call("-p", "Read the file p0002.md in this workspace").returncode == 3
    assert log.read_text().split() == ["p0001", "p0002"]
    full["FAKE_CURSOR_MODE"] = "garbage"
    assert call("-p", "Read the file p0003.md in this workspace").stdout.strip() == "not json at all"


# class: invariant (the diff helper is the contract's difflib call)
def test_expected_diff_shape():
    d = S.expected_diff(S.START, S.OFF_SOLUTION, "sol.py")
    assert d.startswith("--- a/sol.py\n+++ b/sol.py\n@@ -1,3 +1,2 @@\n")
    assert S.expected_diff("", "hello\n", "n.md") == "--- a/n.md\n+++ b/n.md\n@@ -0,0 +1 @@\n+hello\n"


# class: invariant (tamper_evidence leaves the original evidence commit intact and yields a distinct commit)
def test_tamper_evidence_is_a_separate_commit(clone):
    case = clone()
    ref = case.tamper_evidence(lambda f: f.update({next(iter(f)): b"x"}))
    assert ref != case.evidence_ref
    assert S.git(case.repo, "rev-parse", "refs/heads/evidence") == case.evidence_ref


# class: invariant (a refusal helper never accepts a missing interface as a refusal)
def test_refuses_helper_rejects_programming_errors():
    class Empty:
        pass
    with pytest.raises(AssertionError):
        S.refuses(lambda: Empty().missing())
    assert isinstance(S.refuses(lambda: (_ for _ in ()).throw(ValueError("x"))), ValueError)
