"""B8 Wave 1 rules 1, 2 (a-d), 4: each accepted AND each rejected (contract "B8 - Wave 1 rules").

Class of every test is stated in the comment above it: reproduces-failure (the spec fixes it) | invariant | new-behaviour.
A rejected pair is NOT a refusal: `accepted: false`, every reason names the rule and both values.
"""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from bench.tests.p613s2 import w1view as V
from bench.tests.p613s2 import wave1world as WW

ROUTER_KINDS = ("math500", "cjudge", "vision", "reasoning")
LEG_KINDS = WW.KINDS
KEYS_N = {"math500": 5, "cjudge": 3, "vision": 2, "reasoning": 2, "m1": 1}


def only_rejected(b8, kind, block):
    bad = V.rejected(b8)
    assert [(p["kind"], V.digit(p["block"])) for p in bad] == [(kind, V.digit(block))], \
        [(p["kind"], p["block"], p["reasons"]) for p in bad]
    return bad[0]


def named(p, *words):
    t = V.reason_text(p)
    for w in words:
        assert w.lower() in t, (w, p["reasons"])


# ===================================================================================================== the accepted baseline
# class: new-behaviour (10 pairs = 5 kinds x 2 blocks, all accepted and speed-valid, with the contract's record shape)
def test_default_world_accepts_ten_pairs(wave1):
    w, b8 = wave1()
    assert b8["axis"] == "wave1" and len(b8["pairs"]) == 10
    assert sorted((p["kind"], V.digit(p["block"])) for p in b8["pairs"]) == sorted((k, b) for k in WW.KINDS for b in "12")
    for p in b8["pairs"]:
        assert p["accepted"] is True and p["reasons"] == [] and p["speed_valid"] is True, p
        assert p["off"] == WW.leg_name(p["kind"], "off", "b" + V.digit(p["block"]))
        assert p["on"] == WW.leg_name(p["kind"], "on", "b" + V.digit(p["block"]))
        assert p["keys_accepted"] == KEYS_N[p["kind"]] and p["keys_rejected"] == []
        assert len(p["keys"]) == KEYS_N[p["kind"]]
        assert all(set(k) >= {"key", "identical"} for k in p["keys"])


# class: new-behaviour (key shapes: A1/A2 (block, id, sampler_seed); A3 (block, id, seed); A4 (block, task seed, sampler_seed); M1 (block))
def test_key_shapes(wave1):
    w, b8 = wave1()
    ids = w.ids
    for block, name in (("b1", "block1"), ("b2", "block2")):
        for kind, seedf in (("math500", None), ("cjudge", None)):
            keys = {tuple(k["key"][1:]) for k in V.pair(b8, kind, block)["keys"]}
            assert keys == {(rid, WW.sampler_seed(kind, rid)) for rid in ids[kind][name]}
            assert all(V.digit(k["key"][0]) == V.digit(block) for k in V.pair(b8, kind, block)["keys"])
        keys = {tuple(k["key"][1:]) for k in V.pair(b8, "vision", block)["keys"]}
        assert keys == {(rid, WW.sampler_seed("vision", rid)) for rid in ids["vision"][name]}
        keys = {tuple(k["key"][1:]) for k in V.pair(b8, "reasoning", block)["keys"]}
        assert keys == {(s, ids["reasoning"]["request_seeds"][str(s)]) for s in ids["reasoning"][name]}
        assert [V.digit(k["key"][0]) for k in V.pair(b8, "m1", block)["keys"]] == [V.digit(block)]
        assert len(V.pair(b8, "m1", block)["keys"][0]["key"]) == 1


# class: new-behaviour (`inputs` = {rows_root-relative path: sha256} of every file read; never an excluded file, never absolute)
def test_inputs_cover_the_files_read(wave1):
    w, b8 = wave1()
    inputs = b8["inputs"]
    assert inputs and all(isinstance(k, str) and not k.startswith("/") and ".." not in k.split("/") for k in inputs)
    for rel, sha in inputs.items():
        assert hashlib.sha256((w.rows_root / rel).read_bytes()).hexdigest() == sha, rel
    must = ["p426/ids.json", "p426/wave1.s2/run/frozen.s2.json"]
    for kind in WW.KINDS:
        for arm in WW.ARMS:
            for block in WW.BLOCKS:
                must.append(w.rel(w.path_of(kind, arm, block, "receipt")))
                must.append(w.rel(w.path_of(kind, arm, block, "scrub")))
                if kind != "m1":
                    must += [w.rel(w.path_of(kind, arm, block, "rows")), w.rel(w.path_of(kind, arm, block, "manifest"))]
                else:
                    must += [w.rel(w.path_of(kind, arm, block, x)) for x in ("result", "job", "report")]
    must += [w.rel(w.path_of("math500", arm, b, "score")) for arm in WW.ARMS for b in WW.BLOCKS]
    assert not [m for m in must if m not in inputs], [m for m in must if m not in inputs][:5]
    assert not [k for k in inputs if "smoke" in k or "/archive/" in k or "p426/wave1/" in k or "p426-off" in k or "p426-on" in k]


# class: invariant (verification is read-only: no file of the tree changes)
def test_verify_wave1_writes_nothing(verify, make_w1):
    w = make_w1()
    before = {p: p.read_bytes() for p in w.rows_root.rglob("*") if p.is_file() and ".git" not in p.parts}
    verify.verify_wave1(w.p426, w.rows_root, w.repo)
    after = {p: p.read_bytes() for p in w.rows_root.rglob("*") if p.is_file() and ".git" not in p.parts}
    assert before == after


# ============================================================================================================== rule 1: validity
# class: new-behaviour (verdict not VALID -> that pair rejected, naming rule 1 and the value; every other pair stays accepted)
@pytest.mark.parametrize("kind", LEG_KINDS)
@pytest.mark.parametrize("arm", WW.ARMS)
def test_rule1_invalid_verdict_rejects_only_that_pair(verify, make_w1, kind, arm):
    w = make_w1()
    w.edit_receipt(kind, arm, "b1", lambda d: d.update(verdict="INVALID"))
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    p = only_rejected(b8, kind, "b1")
    named(p, "rule 1", "invalid", WW.leg_name(kind, arm, "b1"))


# class: new-behaviour (non-empty `problems` rejects the pair)
@pytest.mark.parametrize("kind", ("math500", "m1"))
def test_rule1_problems_reject(verify, make_w1, kind):
    w = make_w1()
    w.edit_receipt(kind, "on", "b2", lambda d: d.update(problems=["worker died"]))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), kind, "b2")
    named(p, "rule 1", "worker died")


# class: new-behaviour (receipt `name` / `arm` / `kind` must match its path)
@pytest.mark.parametrize("field,value", [("name", "math500-p426s2-on-b2"), ("arm", "off"), ("kind", "cjudge")])
def test_rule1_receipt_identity_must_match_path(verify, make_w1, field, value):
    w = make_w1()
    w.edit_receipt("math500", "on", "b1", lambda d: d.update({field: value}))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "math500", "b1")
    named(p, "rule 1", field, value)


# class: new-behaviour (the M1 receipt kind is `qualify`, the other kinds are their own name)
def test_rule1_m1_receipt_kind_is_qualify(verify, make_w1):
    w = make_w1()
    w.edit_receipt("m1", "on", "b1", lambda d: d.update(kind="m1"))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "m1", "b1")
    named(p, "rule 1", "kind")


# class: new-behaviour (speed_valid false: the pair STAYS accepted, labelled power-invalid; only that block's speed leaves inference)
@pytest.mark.parametrize("arm", WW.ARMS)
def test_rule1_power_invalid_pair_stays_labelled(verify, make_w1, arm):
    w = make_w1()
    w.edit_receipt("cjudge", arm, "b2", lambda d: d.update(speed_valid=False, speed_problems=["power"]))
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    assert V.accepted_all(b8)
    assert V.pair(b8, "cjudge", "b2")["speed_valid"] is False
    assert V.pair(b8, "cjudge", "b1")["speed_valid"] is True
    assert "power-invalid" in json.dumps(b8)


# class: new-behaviour (SCRUB: a covered file whose bytes changed after publication rejects the pair; both shas are named)
@pytest.mark.parametrize("kind,what", [("math500", "rows"), ("math500", "stdout"), ("cjudge", "manifest"), ("vision", "rows"),
                                       ("reasoning", "rows"), ("m1", "result"), ("m1", "stdout")])
def test_rule1_scrub_mismatch_rejects_the_pair(verify, make_w1, kind, what):
    w = make_w1()
    path = w.path_of(kind, "on", "b1", what)
    published = hashlib.sha256(path.read_bytes()).hexdigest()
    if what == "rows":
        # amended (delivery 3): a value-preserving edit that keeps every row parseable (` ": "` -> ` " : "` after the first key); appending a
        # byte tore the jsonl, and a torn rows file is a refusal (step-1 chain_rows rule), not a SCRUB rejection
        path.write_bytes(path.read_bytes().replace(b'": ', b'" : ', 1))
    else:
        path.write_bytes(path.read_bytes() + b" ")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), kind, "b1")
    named(p, "rule 1", path.name, published, actual)


# class: new-behaviour (SCRUB: a listed file that is missing rejects the pair)
def test_rule1_scrub_missing_file_rejects_the_pair(verify, make_w1):
    w = make_w1()
    w.path_of("vision", "off", "b2", "stdout").unlink()
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "vision", "b2")
    named(p, "rule 1", "leg.stdout")


# class: invariant (a SCRUB path that is not under benchmark/results/ is not read from outside rows_root)
def test_rule1_scrub_path_traversal_is_not_followed(verify, make_w1, tmp_path):
    w = make_w1()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    sha = hashlib.sha256(outside.read_bytes()).hexdigest()

    p = w.path_of("math500", "on", "b1", "scrub")
    doc = json.loads(p.read_text())
    doc["files"]["benchmark/results/../../../../outside.txt"] = {"published_sha256": sha}
    p.write_text(WW.dumps(doc))
    assert V.refused_or_rejected(lambda: verify.verify_wave1(w.p426, w.rows_root, w.repo),
                                 lambda b8: not V.pair(b8, "math500", "b1")["accepted"])


# ============================================================================================================ rule 2(a): receipts
# class: new-behaviour (pins without frozen_sha differ across the pair -> rejected, naming both values)
def test_rule2a_pins_differ_across_the_pair(verify, make_w1):
    w = make_w1()
    w.edit_receipt("math500", "off", "b1", lambda d: d["pins"].update(mlx_vlm="ee" * 20))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "math500", "b1")
    named(p, "rule 2", "pins", "ee" * 20, WW.GITLINKS["src/mlx-vlm"])


# class: new-behaviour (pins equal across the pair but != frozen.s2.json -> rejected)
def test_rule2a_pins_differ_from_the_frozen_record(verify, make_w1):
    w = make_w1()
    for arm in WW.ARMS:
        w.edit_receipt("vision", arm, "b2", lambda d: d["pins"].update(uv_lock_sha256="99" * 32))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "vision", "b2")
    named(p, "rule 2", "frozen", "99" * 32)


# class: new-behaviour (pins.frozen_sha must equal state.frozen_sha)
def test_rule2a_pins_frozen_sha_vs_state(verify, make_w1):
    w = make_w1()
    w.edit_receipt("cjudge", "on", "b1", lambda d: d["state"].update(frozen_sha="12" * 32))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "cjudge", "b1")
    named(p, "rule 2", "frozen_sha", "12" * 32)


# class: new-behaviour (frozen_sha must equal sha256 of the frozen.s2.json BYTES: a frozen file edited after the legs ran rejects all)
def test_rule2a_frozen_bytes_changed_rejects_every_pair(verify, make_w1):
    w = make_w1()
    f = w.w1 / "run" / "frozen.s2.json"
    f.write_bytes(f.read_bytes() + b"\n")
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    assert len(V.rejected(b8)) == 10
    assert all("rule 2" in V.reason_text(p) and "frozen" in V.reason_text(p) for p in b8["pairs"])


# class: new-behaviour (state.stack_head must equal the frozen stack_head of the arm)
@pytest.mark.parametrize("arm", WW.ARMS)
def test_rule2a_state_stack_head(verify, make_w1, arm):
    w = make_w1()
    w.edit_receipt("reasoning", arm, "b2", lambda d: d["state"].update(stack_head="cd" * 20))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "reasoning", "b2")
    named(p, "rule 2", "stack_head", "cd" * 20)


# ============================================================================================================ rule 2(b): registry
# class: new-behaviour (the registry is OPENED, not trusted: a frozen registry_<arm>_sha that git does not reproduce rejects the arm's pairs)
@pytest.mark.parametrize("arm", WW.ARMS)
def test_rule2b_registry_sha_is_recomputed_from_git(verify, make_w1, arm):
    w = make_w1(frozen={f"registry_{arm}_sha": "0" * 64})
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    assert len(V.rejected(b8)) == 10
    assert all("rule 2" in V.reason_text(p) and "registry" in V.reason_text(p) and "0" * 64 in V.reason_text(p)
               for p in b8["pairs"])


# class: new-behaviour (a stack head that does not resolve in the repo is a refusal)
@pytest.mark.parametrize("arm", WW.ARMS)
def test_rule2b_unresolvable_head_refuses(verify, make_w1, arm):
    w = make_w1(frozen={f"stack_head_{arm}": "ab" * 20})
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: new-behaviour (a repo that holds neither head refuses)
def test_rule2b_wrong_repo_refuses(verify, make_w1, tmp_path):
    w = make_w1()
    other = tmp_path / "other"
    other.mkdir()
    WW.git(other, "init", "-q")
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, other)


# class: new-behaviour (a row manifest whose registry.sha256 is not the arm's registry sha rejects the pair)
@pytest.mark.parametrize("kind", ("math500", "cjudge", "vision", "reasoning"))
def test_rule2b_manifest_registry_sha(verify, make_w1, kind):
    w = make_w1()
    w.edit_json(kind, "on", "b1", "manifest", lambda d: d["registry"].update(sha256="77" * 32))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), kind, "b1")
    named(p, "rule 2", "registry", "77" * 32)


# class: new-behaviour (M1 report.registry_sha256 must equal the arm's registry sha)
def test_rule2b_m1_report_registry_sha(verify, make_w1):
    w = make_w1()
    w.edit_json("m1", "off", "b2", "report", lambda d: d.update(registry_sha256="66" * 32))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "m1", "b2")
    named(p, "rule 2", "registry", "66" * 32)


# ================================================================================================ rule 2(c): worker argv, exact delta
def mutate_flags(w, kind, arm, block, fn):
    w.set_flags(kind, arm, block, fn)


VARIANTS = {
    "on_lacks_verify_scan": ("on", lambda fl: [f for f in fl if f[0] != "--mtp-verify-scan"], "--mtp-verify-scan"),
    "on_lacks_draft_model": ("on", lambda fl: [f for f in fl if f[0] != "--draft-model"], "--draft-model"),
    "on_lacks_draft_kind": ("on", lambda fl: [f for f in fl if f[0] != "--draft-kind"], "--draft-kind"),
    "on_other_drafter": ("on", lambda fl: [(f, "caslca/other-drafter" if f == "--draft-model" else v) for f, v in fl],
                         "caslca/other-drafter"),
    "on_other_scan": ("on", lambda fl: [(f, "per_query" if f == "--mtp-verify-scan" else v) for f, v in fl], "per_query"),
    "on_other_draft_kind": ("on", lambda fl: [(f, "suffix" if f == "--draft-kind" else v) for f, v in fl], "suffix"),
    "on_extra_flag": ("on", lambda fl: fl + [("--foo", "bar")], "--foo"),
    "off_extra_flag": ("off", lambda fl: fl + [("--bar", "baz")], "--bar"),
    "off_has_the_draft_flags": ("off", lambda fl: fl + [("--draft-kind", "mtp")], "--draft-kind"),
    "shared_value_differs": ("on", lambda fl: [(f, "131072" if f == "--max-kv-size" else v) for f, v in fl], "--max-kv-size"),
    "generation_defaults_differ": ("on", lambda fl: [(f, v.replace("81920", "40960") if f == "--generation-defaults" else v)
                                                      for f, v in fl], "--generation-defaults"),
    "boolean_flag_dropped": ("off", lambda fl: [f for f in fl if f[0] != "--lazy-prompt-embeddings"], "--lazy-prompt-embeddings"),
}


# class: new-behaviour (ON - OFF must be EXACTLY {--draft-kind mtp, --draft-model <drafter>, --mtp-verify-scan joint_v1}, OFF - ON empty)
@pytest.mark.parametrize("name", sorted(VARIANTS))
@pytest.mark.parametrize("kind", ("math500", "reasoning"))
def test_rule2c_router_argv_delta_is_exact(verify, make_w1, name, kind):
    arm, fn, token = VARIANTS[name]
    w = make_w1()
    mutate_flags(w, kind, arm, "b1", fn)
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), kind, "b1")
    named(p, "rule 2", token)


# class: new-behaviour (the same exact-delta rule on the M1 job.json argv, which is a list of flag + value pairs)
@pytest.mark.parametrize("name", ["on_lacks_verify_scan", "on_other_drafter", "on_extra_flag", "off_extra_flag",
                                  "shared_value_differs", "off_has_the_draft_flags"])
def test_rule2c_m1_argv_delta_is_exact(verify, make_w1, name):
    arm, fn, token = VARIANTS[name]
    w = make_w1()
    mutate_flags(w, "m1", arm, "b2", fn)
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "m1", "b2")
    named(p, "rule 2", token)


# class: new-behaviour (a multiset: the SAME flags in another order are accepted; PID and arm worktree path are normalised away)
@pytest.mark.parametrize("kind", ("cjudge", "m1"))
def test_rule2c_flag_order_does_not_matter(verify, make_w1, kind):
    w = make_w1()
    mutate_flags(w, kind, "on", "b1", lambda fl: list(reversed(fl)))
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    assert V.accepted_all(b8), [p["reasons"] for p in V.rejected(b8)]


# class: new-behaviour (the default world differs in PID and in `stack-p426-s2-<arm>` only: that is accepted; a PID change alone too)
def test_rule2c_pid_and_worktree_component_are_normalised(verify, make_w1):
    w = make_w1()
    w.edit_receipt("vision", "on", "b1", lambda d: d["worker"].update(
        cmdline=d["worker"]["cmdline"].replace("95861", "11111", 1)))
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    assert V.accepted_all(b8)
    cmd_off = json.loads(w.path_of("vision", "off", "b1", "receipt").read_text())["worker"]["cmdline"]
    assert "stack-p426-s2-off" in cmd_off and "stack-p426-s2-on" not in cmd_off


# class: new-behaviour (a worktree path that is NOT the arm's stack-p426-s2-<arm> component is a real difference)
def test_rule2c_other_worktree_path_is_a_difference(verify, make_w1):
    w = make_w1()
    w.edit_receipt("vision", "on", "b1", lambda d: d["worker"].update(
        cmdline=d["worker"]["cmdline"].replace("stack-p426-s2-on", "stack-elsewhere-on")))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "vision", "b1")
    named(p, "rule 2", "stack-elsewhere-on")


# ============================================================================================================ rule 2(d): equal
# class: new-behaviour (manifest sampling / kv must be equal across the pair)
@pytest.mark.parametrize("kind", ("math500", "cjudge", "vision", "reasoning"))
@pytest.mark.parametrize("section,field,value", [("sampling", "temperature", 0.7), ("kv", "max_kv_cache_size", 131072),
                                                 ("sampling", "max_tokens", 4096)])
def test_rule2d_manifest_sampling_and_kv(verify, make_w1, kind, section, field, value):
    w = make_w1()
    w.edit_json(kind, "on", "b2", "manifest", lambda d: d[section].update({field: value}))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), kind, "b2")
    named(p, "rule 2", section, str(value))


# class: invariant (manifest fields outside sampling / kv / registry (runtime.draft_kind, router pid, timestamp) may differ)
def test_rule2d_runtime_and_router_may_differ(verify, make_w1):
    w = make_w1()
    w.edit_json("math500", "on", "b1", "manifest", lambda d: d.update(timestamp=1, router={"pid": 1, "config_sha256": d["registry"]["sha256"]}))
    assert V.accepted_all(verify.verify_wave1(w.p426, w.rows_root, w.repo))


# class: new-behaviour (row thinking_budget must be equal across the pair, row by row)
@pytest.mark.parametrize("kind", ("math500", "cjudge"))
def test_rule2d_row_thinking_budget(verify, make_w1, kind):
    w = make_w1()
    w.edit_rows(kind, "on", "b1", lambda rows: rows[0].update(thinking_budget=40960))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), kind, "b1")
    named(p, "rule 2", "thinking_budget", "40960", "81920")


# class: new-behaviour (M1 served: every key except draft_kind / drafter_loaded / verify_policy must be equal)
def test_rule2d_m1_served_other_keys_equal(verify, make_w1):
    w = make_w1()
    w.edit_json("m1", "on", "b1", "result", lambda d: d["served"].update(session_max=2))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "m1", "b1")
    named(p, "rule 2", "served", "session_max")


# class: invariant (M1 served draft_kind / drafter_loaded / verify_policy are the legitimate differences)
def test_rule2d_m1_served_arm_keys_may_differ(verify, make_w1):
    w = make_w1()
    served = json.loads(w.path_of("m1", "on", "b1", "result").read_text())["served"]
    off_served = json.loads(w.path_of("m1", "off", "b1", "result").read_text())["served"]
    assert served["draft_kind"] != off_served["draft_kind"] and served["drafter_loaded"] != off_served["drafter_loaded"]
    assert V.accepted_all(verify.verify_wave1(w.p426, w.rows_root, w.repo))


# class: new-behaviour (M1 snapshots: everything except `--draft-model` must be equal)
def test_rule2d_m1_snapshots(verify, make_w1):
    w = make_w1()
    w.edit_json("m1", "on", "b2", "result", lambda d: d["snapshots"].update({"--model": "ff" * 20}))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "m1", "b2")
    named(p, "rule 2", "snapshots", "ff" * 20)


# class: new-behaviour (M1 report reviewed_head / production / versions, qualify generate_seed / prompt.sized must be equal)
@pytest.mark.parametrize("what,fn,token", [
    ("report", lambda d: d.update(reviewed_head="de" * 20), "reviewed_head"),
    ("report", lambda d: d.update(production="ad" * 20), "production"),
    ("report", lambda d: d["versions"].update(mlx="0.99"), "versions"),
    ("result", lambda d: d["requests"][0]["qualify"].update(generate_seed=8), "generate_seed"),
    ("result", lambda d: d["requests"][0]["qualify"]["prompt"]["sized"].update(tokens=1), "sized"),
])
def test_rule2d_m1_report_and_qualify_equal(verify, make_w1, what, fn, token):
    w = make_w1()
    w.edit_json("m1", "on", "b1", what, fn)
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "m1", "b1")
    named(p, "rule 2", token)


# class: new-behaviour (OFF rows: every draft value must be null)
@pytest.mark.parametrize("kind", ("math500", "cjudge", "vision"))
@pytest.mark.parametrize("field,value", [("draft_kind", "mtp"), ("draft_n", 10)])
def test_rule2d_off_rows_draft_null(verify, make_w1, kind, field, value):
    w = make_w1()
    w.edit_rows(kind, "off", "b1", lambda rows: rows[0]["draft"].update({field: value}))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), kind, "b1")
    named(p, "rule 2", "draft", field)


# class: new-behaviour (the A4 OFF draw's draft must be null too)
def test_rule2d_off_a4_draft_null(verify, make_w1):
    w = make_w1()
    w.edit_rows("reasoning", "off", "b2", lambda rows: rows[1]["draft"].update(draft_n_accepted=3))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "reasoning", "b2")
    named(p, "rule 2", "draft")


# class: new-behaviour (ON rows: draft_kind == mtp, draft_n > 0, 0 <= draft_n_accepted <= draft_n)
@pytest.mark.parametrize("kind", ("math500", "cjudge", "vision", "reasoning"))
@pytest.mark.parametrize("patch,token", [({"draft_kind": "suffix"}, "draft_kind"), ({"draft_n": 0, "draft_n_accepted": 0}, "draft_n"),
                                         ({"draft_n_accepted": 201}, "draft_n_accepted"),      # amended: 201 > draft_n of every kind (A4 draws have 200)
                                         ({"draft_n_accepted": -1}, "draft_n_accepted"), ({"draft_n": None}, "draft_n"),
                                         ({"draft_kind": None}, "draft_kind")])
def test_rule2d_on_rows_draft_counters(verify, make_w1, kind, patch, token):
    w = make_w1()
    w.edit_rows(kind, "on", "b1", lambda rows: rows[0]["draft"].update(patch))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), kind, "b1")
    named(p, "rule 2", token)


# class: invariant (draft_n_accepted == draft_n and == 0 are inside the closed interval: accepted)
def test_rule2d_draft_boundaries_are_inclusive(verify, make_w1):
    w = make_w1()
    w.edit_rows("math500", "on", "b1", lambda rows: (rows[0]["draft"].update(draft_n_accepted=100),
                                                      rows[1]["draft"].update(draft_n_accepted=0)))
    assert V.accepted_all(verify.verify_wave1(w.p426, w.rows_root, w.repo))


# ============================================================================================================ rule 4: speed
# class: new-behaviour (per block: both legs speed-valid -> pair.speed_valid; a power-invalid OFF OR ON leg makes the block descriptive)
@pytest.mark.parametrize("kind", WW.KINDS)
def test_rule4_speed_valid_is_per_pair(verify, make_w1, kind):
    w = make_w1()
    w.edit_receipt(kind, "off", "b1", lambda d: d.update(speed_valid=False))
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    assert V.accepted_all(b8)
    assert [p["speed_valid"] for p in b8["pairs"] if p["kind"] == kind and V.digit(p["block"]) == "1"] == [False]
    assert all(p["speed_valid"] for p in b8["pairs"] if not (p["kind"] == kind and V.digit(p["block"]) == "1"))
