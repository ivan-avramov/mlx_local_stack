"""P609: the v8 freeze accepts only a PASS gate receipt for exactly the OFF arm's commit under the current gate policy, whose bytes
hash to the stated `stack_suite_receipt_sha256` (before P609 it checked only that the sha256 looked like one)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bench import p426_freeze as fz
from bench.tests import test_b2_s8_freeze as T
from bench.tests.test_b2_s8_freeze import world  # noqa: F401  (fixture)

OFF = "a" * 40
DIGEST = "d" * 64


def receipt(tmp_path, *, name="stack-receipt.json", **over):
    doc = dict(repo="stack", sha=OFF, verdict="PASS", policy_digest=DIGEST, problems=[])
    doc.update(over)
    path = tmp_path / "gate" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(doc).encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def problems(path, sha, *, off=OFF, wd=None, digest=DIGEST):
    return fz.suite_receipt_problems(receipt=None if path is None else str(path), receipt_sha256=sha, off_head=off,
                                     wd=wd or path.parent.parent, digest_for=lambda s: digest)


def test_a_pass_receipt_for_the_off_commit_under_the_current_policy_is_accepted(tmp_path):
    path, sha = receipt(tmp_path)
    assert problems(path, sha) == []


def test_a_fail_receipt_is_refused(tmp_path):
    path, sha = receipt(tmp_path, verdict="FAIL", problems=["pytest: rc 1"])
    got = problems(path, sha)
    assert got and "FAIL" in " ".join(got)


def test_a_receipt_for_another_commit_is_refused(tmp_path):
    path, sha = receipt(tmp_path, sha="b" * 40)
    assert any("OFF" in p for p in problems(path, sha))


def test_a_receipt_of_another_repo_is_refused(tmp_path):
    path, sha = receipt(tmp_path, repo="mlx-vlm")
    assert problems(path, sha)


def test_a_receipt_under_a_stale_gate_policy_is_refused(tmp_path):
    path, sha = receipt(tmp_path)
    assert any("policy" in p for p in problems(path, sha, digest="e" * 64))


def test_receipt_bytes_must_hash_to_the_stated_sha256(tmp_path):
    path, _ = receipt(tmp_path)
    assert any("sha256" in p for p in problems(path, "0" * 64))


def test_a_missing_or_unreadable_receipt_is_refused(tmp_path):
    assert problems(None, "0" * 64, wd=tmp_path)
    assert problems(tmp_path / "gate" / "absent.json", "0" * 64)
    path = tmp_path / "gate" / "bad.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not json")
    assert problems(path, hashlib.sha256(b"{not json").hexdigest())


def test_a_portable_workdir_path_resolves(tmp_path):
    path, sha = receipt(tmp_path)
    assert fz.suite_receipt_problems(receipt="$STACK_WORKDIR/gate/" + path.name, receipt_sha256=sha, off_head=OFF, wd=tmp_path,
                                     digest_for=lambda s: DIGEST) == []


def test_default_checks_run_the_suite_receipt_check_in_v8(world, monkeypatch):  # noqa: F811
    for name in ("entry_point_problems", "help_problems"):
        monkeypatch.setattr(fz, name, lambda wt: [])
    monkeypatch.setattr(fz.p426_plan, "restore_diff_problems", lambda off, on, entry: [])
    monkeypatch.setattr(fz, "venv_problems", lambda wt, build: [])
    monkeypatch.setattr(fz, "production_tree_problems", lambda wt, ref, link: [])
    seen = []
    monkeypatch.setattr(fz, "suite_receipt_problems", lambda **kw: seen.append(kw) or ["receipt is FAIL"])
    got = fz.default_checks("v8", off_worktree=world["off"], on_worktree=world["on"], build="s2", production_ref="r" * 40,
                            gitlinks={"mlx_vlm": "g" * 40, "mlx_serve": "h" * 40}, off_head=OFF, suite_receipt="x.json",
                            suite_receipt_sha256="f" * 64, wd=world["wd"])
    assert got == ["stack suite receipt: receipt is FAIL"]
    assert seen == [dict(receipt="x.json", receipt_sha256="f" * 64, off_head=OFF, wd=world["wd"])]


def test_the_rehearsal_kind_does_not_need_a_suite_receipt(world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(fz.p426_plan, "restore_diff_problems", lambda off, on, entry: [])
    monkeypatch.setattr(fz, "entry_point_problems", lambda wt: [])
    monkeypatch.setattr(fz, "suite_receipt_problems", lambda **kw: ["must not run"])
    assert fz.default_checks("rehearsal", off_worktree=world["off"], on_worktree=world["on"]) == []


def test_v8_hands_the_receipt_and_the_off_head_to_the_checks(world, capsys):  # noqa: F811
    manifest = T.make_manifest(world, capsys)
    legs = T.make_rehearsal_legs(world)
    world["ops"].inputs["stack_suite_receipt"] = "$STACK_WORKDIR/gate/r.json"
    seen = {}
    rc, err = T.run(T.v8_argv(world, manifest, legs, world["rec"] / "v8_base.json"), world["ops"],
                    checks=lambda kind, **kw: seen.update({kind: kw}) or [], capsys=capsys)
    assert rc == 0, err
    kw = seen["v8"]
    assert kw["off_head"] == T.OFF_HEAD and kw["suite_receipt"] == "$STACK_WORKDIR/gate/r.json"
    assert kw["suite_receipt_sha256"] == "f" * 64 and Path(kw["wd"]) == Path(world["wd"])


def test_v8_refuses_through_the_default_checks_on_a_fail_receipt(world, capsys, monkeypatch, tmp_path):  # noqa: F811
    for name in ("entry_point_problems", "help_problems"):
        monkeypatch.setattr(fz, name, lambda wt: [])
    monkeypatch.setattr(fz.p426_plan, "restore_diff_problems", lambda off, on, entry: [])
    monkeypatch.setattr(fz, "venv_problems", lambda wt, build: [])
    monkeypatch.setattr(fz, "production_tree_problems", lambda wt, ref, link: [])
    monkeypatch.setattr(fz, "gate_policy_digest", lambda sha: DIGEST)
    path, sha = receipt(tmp_path, sha=T.OFF_HEAD, verdict="FAIL")
    manifest = T.make_manifest(world, capsys)
    legs = T.make_rehearsal_legs(world)
    world["ops"].inputs.update(stack_suite_receipt=str(path), stack_suite_receipt_sha256=sha)
    out = world["rec"] / "v8_base.json"
    rc = fz.main([str(x) for x in T.v8_argv(world, manifest, legs, out)], ops=world["ops"])
    err = capsys.readouterr().err
    assert rc == 2 and "FAIL" in err and not out.exists()
