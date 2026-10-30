"""P426 B2 frozen tests, s8 freeze + sequencer (spec v3.2 §1, §5.5, §6.7, §10, §16.1-16.2, §16.4).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour.
Unit level: `p426_wave2.leg_argv(..., worktrees={"off": …, "on": …}, ...)`, `deadline_s(session, {lang: n}, amendment)`,
`makeup_groups(...)` (`{session, seed, language, items}`), and `p426_freeze.main(argv, ops=…, checks=…)` with
`ops.worktree_state(path)` and `checks(kind, **inputs) -> [failed preconditions]` (§16.4). The sequencer's `main` is not
tested: §16.4 names its ops but not its argv (report)."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from bench.tests import b2_frozen_support as S


def W2():
    from bench import p426_wave2
    return p426_wave2


def FZ():
    from bench import p426_freeze
    return p426_freeze


def arg(argv, flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


# ------------------------------------------------------------------------------------------------ leg_argv (§1, §6.7)
LEGS = {
    "tg1-p426-off-pilot": ("off", ["pilot"], "v8"),
    "tg1-p426-on-pilot": ("on", ["pilot"], "v8"),
    "tg1-p426-off-s1": ("off", ["chain", "s1"], "am"),
    "tg1-p426-on-s1": ("on", ["chain", "s1"], "am"),
    "tg1-p426-on-s2": ("on", ["chain", "s2"], "am"),
    "tg1-p426-off-s2": ("off", ["chain", "s2"], "am"),
    "tg1-p426-on-reload": ("on", ["chain", "reload"], "am"),
    "tg1-p426-off-reload": ("off", ["chain", "reload"], "am"),
}


@pytest.mark.parametrize("leg", sorted(LEGS))
def test_new_leg_argv_is_the_common_flags_plus_the_legs_own_argv(tmp_path, leg):
    arm, own, which = LEGS[leg]
    v8, am = S.record_dir(tmp_path)
    record = v8 if which == "v8" else am
    wts = {"off": tmp_path / "stack-p426-off", "on": tmp_path / "stack-p426-on"}
    argv = W2().leg_argv(leg, 2, worktrees=wts, record_path=record, out_base=tmp_path / "wd/p426/wave2")
    assert "--p426" in argv and "--rehearsal" not in argv and "--inject" not in argv
    assert all(tok in argv for tok in own)
    pos = [argv.index(tok) for tok in own]
    assert pos == sorted(pos) and pos[1:] == [p + 1 for p in pos[:-1]]            # `chain s1` in order, adjacent
    assert arg(argv, "--models") == S.MODEL and arg(argv, "--predictor") == ("mtp" if arm == "on" else "off")
    assert arg(argv, "--out-root") == str(tmp_path / "wd/p426/wave2" / f"{leg}.a2")
    assert arg(argv, "--frozen-record") == str(record)
    doc = json.loads(Path(v8).read_text())
    assert arg(argv, "--probe-code-sha") == doc["probe_code_sha256"]
    assert arg(argv, "--policy-sha") == doc["scaffold_policy_sha256"]
    assert arg(argv, "--frozen-prompt-date") == doc["frozen_prompt_date"]
    assert arg(argv, "--campaign-core") == doc[f"{arm}_commit"]


def test_new_each_attempt_has_its_own_out_root(tmp_path):
    v8, _ = S.record_dir(tmp_path)
    wts = {"off": tmp_path / "off", "on": tmp_path / "on"}
    roots = {arg(W2().leg_argv("tg1-p426-off-pilot", n, worktrees=wts, record_path=v8, out_base=tmp_path / "w"), "--out-root")
             for n in (1, 2, 3)}
    assert len(roots) == 3 and all(r.endswith((".a1", ".a2", ".a3")) for r in roots)


# ------------------------------------------------------------------------------------------------ deadlines (§10.2)
def test_new_the_leg_deadline_is_one_and_a_half_times_the_item_walls_plus_1800_s():
    amendment ={"kind": "p426_timeout_amendment", "w_python_s": 1300.0, "w_go_s": 900.0}
    got = W2().deadline_s("s1", {"python": 22, "go": 21}, amendment)
    assert got == pytest.approx(1.5 * (22 * 1300.0 + 21 * 900.0) + 1800.0)
    assert W2().deadline_s("s2", {"go": 21, "python": 22}, amendment) == pytest.approx(got)    # one value, both orders
    assert W2().deadline_s("reload", {"python": 5}, amendment) == pytest.approx(1.5 * 5 * 1300.0 + 1800.0)


# ------------------------------------------------------------------------------------------------ make-up grouping (§5.5)
def test_new_makeup_groups_by_session_seed_language_in_session_then_original_language_order():
    """post-reveal 3d (§16.8): canonical order = s1 then s2, the session's language order, then `occurrence` (the 0-based
    position in the leg's frozen order); a slot DNF'd in both arms is ONE record (runs once per make-up leg)."""
    occ = [S.occurrence("s2", "python", "grep", 2002, "on", 3), S.occurrence("s1", "go", "bowling", 1001, "off", 0),
           S.occurrence("s2", "go", "ledger", 2002, "off", 1), S.occurrence("s1", "python", "dominoes", 1001, "on", 2),
           S.occurrence("s1", "python", "beer-song", 1001, "off", 0), S.occurrence("s2", "python", "grep", 2002, "off", 3)]
    groups = W2().makeup_groups(occ)
    keys = [(g["session"], g["seed"], g["language"]) for g in groups]
    assert keys == [("s1", 1001, "python"), ("s1", 1001, "go"), ("s2", 2002, "go"), ("s2", 2002, "python")]
    items = {(g["session"], g["language"]): list(g["items"]) for g in groups}
    assert items[("s1", "python")] == ["beer-song", "dominoes"]                 # by `occurrence` (0 before 2), not input order
    assert items[("s2", "python")] == ["grep"]                                  # de-duplicated: DNF'd in both arms, run once


def test_new_makeup_groups_ignore_the_input_order_of_an_unordered_occurrence_set():
    """post-reveal 3d (§16.8, §16.6): the occurrences file is an unordered set; two orderings give the same groups."""
    occ = [S.occurrence("s1", "python", "dominoes", 1001, "on", 2), S.occurrence("s1", "python", "beer-song", 1001, "off", 0),
           S.occurrence("s2", "go", "ledger", 2002, "off", 1)]
    assert W2().makeup_groups(occ) == W2().makeup_groups(list(reversed(occ)))


def test_new_makeup_occurrences_across_both_sessions_keep_their_own_seeds():
    occ = [S.occurrence("s1", "python", "grep", 1001, "off"), S.occurrence("s2", "python", "grep", 2002, "on")]
    seeds = {g["session"]: g["seed"] for g in W2().makeup_groups(occ)}
    assert seeds == {"s1": 1001, "s2": 2002}


# ------------------------------------------------------------------------------------------------ p426_freeze (§16.1-16.2)
def freeze(argv, **kw):
    err = io.StringIO()
    with redirect_stderr(err):
        try:
            rc = FZ().main(list(argv), **kw)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 2
    return rc, err.getvalue()


class FreezeOps:
    """§16.4: `p426_freeze.main(argv, ops=…)` reads each worktree through `ops.worktree_state(path)`. post-reveal 3d (§16.8):
    also `identity(path)` (the worktree's `--print-identity`), `historical_walls() -> {w_python_s, w_go_s,
    max_request_elapsed_s}`, `build_inputs()` (§16.7: the build label, production ref, grader image id — here the S′ build
    `s2` of `p426_plan.EXPECTED_BUILDS`, whose gitlinks are the base's — plus the frozen prompt date and the stack-suite
    receipt v8 records, §10.1)."""

    def __init__(self, off, on, *, dirty=(), gitlinks=None, max_request_elapsed_s=100.0):
        self.heads = {str(off): S.OFF_COMMIT, str(on): S.ON_COMMIT}
        self.dirty, self.gitlinks = {str(d) for d in dirty}, gitlinks or {}
        self.max_request_elapsed_s = float(max_request_elapsed_s)

    def worktree_state(self, path):
        p = str(path)
        return dict(head=self.heads[p], clean=p not in self.dirty,
                    gitlinks=dict(self.gitlinks.get(p, S.BASE_GITLINKS)))

    def build_inputs(self):
        """§16.7 (1g tail): the v8 inputs `p426_freeze` cannot derive from the worktrees."""
        from bench import p426_plan
        return dict(build="s2", production_ref=p426_plan.EXPECTED_BUILDS["s2"]["production_ref"],
                    grader_image_id="sha256:" + "f" * 64, frozen_prompt_date=S.EPOCH_DATE,
                    stack_suite_receipt_sha256="2" * 64)

    def identity(self, path):
        base = S.v8_base()
        return {k: base[k] for k in ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256")}

    def historical_walls(self):
        return dict(w_python_s=300.0, w_go_s=200.0, max_request_elapsed_s=self.max_request_elapsed_s)


SEAMS = ("worktree_state", "identity", "historical_walls", "build_inputs")


class MissingSeam(FreezeOps):
    """FreezeOps without one §16.8 seam (`missing`)."""

    def __init__(self, *a, missing, **kw):
        super().__init__(*a, **kw)
        self.missing = missing

    def __getattribute__(self, name):
        if name == object.__getattribute__(self, "missing"):
            raise AttributeError(name)
        return object.__getattribute__(self, name)


@pytest.fixture(autouse=True)
def _stack_workdir(tmp_path, monkeypatch):
    """post-reveal 3c: `$STACK_WORKDIR` is `<tmp>/wd` and the worktrees / leg roots lie under it (§16.7: record paths are
    portable `$STACK_WORKDIR/…`; §1: a rehearsal writes only under `$STACK_WORKDIR/p426/rehearsal/`)."""
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))


def worktrees(tmp_path):
    off, on = tmp_path / "wd" / "stack-p426-off", tmp_path / "wd" / "stack-p426-on"
    off.mkdir(parents=True)
    on.mkdir(parents=True)
    return off, on


def rehearsal_argv(tmp_path, off, on, out):
    # post-reveal 3e (designer ruling on §16.8): `p426_freeze rehearsal --frozen-prompt-date` records the date
    return ["rehearsal", "--off-worktree", str(off), "--on-worktree", str(on), "--out-root",
            str(tmp_path / "wd/p426/rehearsal/r1"), "--out", str(out), "--frozen-prompt-date", S.EPOCH_DATE]


def leg_record(root, name, state, *, reason="", chain_rc=None):
    """`<root>/leg.json` as the sequencer writes it (§16.1 leg record, an immutable self-hashed record; post-reveal 3c: sealed)."""
    return S.write_record(root / "leg.json", S.self_hashed(dict(
        leg=name.rsplit(".a", 1)[0], attempt=int(name.rsplit(".a", 1)[1]), state=state,
        **{"class": "valid" if state == "VALID" else "systemic"}, reason=reason,
        chain_rc=(0 if state != "INVALID" else 2) if chain_rc is None else chain_rc,
        started="2026-10-27T00:00:00Z", ended="2026-10-27T01:00:00Z", speed_valid=True, speed_reason="")))


REHEARSAL_INJECT = {"tg1-p426-rehearsal-mismatch": "reconcile-mismatch", "tg1-p426-rehearsal-kill": "stall-kill"}


def portable_wd(tmp_path, path):
    """`$STACK_WORKDIR/…` of a path under `<tmp>/wd` (§16.7 / §16.8 portable form)."""
    return "$STACK_WORKDIR/" + Path(path).relative_to(tmp_path / "wd").as_posix()


def leg_root_with(tmp_path, name, state, *, elapsed_s=100.0, manifest=None):
    """A rehearsal leg root (post-reveal 3c: a complete leg in the frozen formats — chain.json, the realized ledger, sealed
    ready / item records, the receipt — plus its sealed leg record). R1 legs are VALID smoke shapes of s1's Python order; R2 is
    INVALID for the injected reconciliation mismatch; R3 is VALID with one item killed (a failed-line kill case).
    post-reveal 3h (§16.8 after the strict verify round 1, rehearsal binding): `chain.json` records `frozen_record: {path,
    sha256}` of the rehearsal manifest the leg ran under (`manifest`, a path under `<tmp>/wd`) and its `inject`."""
    from bench.tests import b2_frozen_add_support as A
    root = tmp_path / "wd/p426/rehearsal" / name
    leg = name.rsplit(".a", 1)[0]
    arm = "on" if leg in ("tg1-p426-rehearsal-on", "tg1-p426-rehearsal-mismatch") else "off"
    invalid = ([dict(stage="done", slot=A._slot("pilot", "python", "p2"), reason="reconciliation mismatch (injected)",
                     at="2026-10-27T00:30:00Z")] if state == "INVALID" else [])   # §16.8: the exact R2 reason
    A.write_leg(root, leg, ["pilot", "--p426", "--predictor", "mtp" if arm == "on" else "off", "--out-root", str(root)],
                dict(rc=2 if state == "INVALID" else 0, invalid=invalid, elapsed_s=elapsed_s))
    if leg == "tg1-p426-rehearsal-kill":                           # R3: one item's record carries the kill case (§4.3 table)
        p = sorted(q for q in (root / "items").glob("*.json") if not q.name.endswith((".ready.json", ".dnf.json")))[0]
        p.write_text(json.dumps(S.self_hashed(dict(json.loads(p.read_text()), case="kill_boundary")), sort_keys=True))
    if manifest is not None:
        cj = json.loads((root / "chain.json").read_text())
        cj.update(frozen_record=dict(path=portable_wd(tmp_path, manifest), sha256=json.loads(Path(manifest).read_text())["sha256"]),
                  inject=REHEARSAL_INJECT.get(leg))
        (root / "chain.json").write_text(json.dumps(cj))
    leg_record(root, name, state, reason=invalid[0]["reason"] if invalid else "")
    return root


OK = lambda kind, **inputs: []                                    # noqa: E731  (every precondition holds)


def test_new_freeze_rehearsal_writes_a_self_hashed_rehearsal_manifest_once(tmp_path, monkeypatch):
    off, on = worktrees(tmp_path)
    out = tmp_path / "records" / "rehearsal.json"
    argv = rehearsal_argv(tmp_path, off, on, out)
    rc, err = freeze(argv, ops=FreezeOps(off, on), checks=OK)
    assert rc == 0, err
    doc = json.loads(out.read_text())
    assert doc["kind"] == "p426_rehearsal" and doc["rehearsal"] is True and S.self_hashed(doc)["sha256"] == doc["sha256"]
    assert (doc["off_commit"], doc["on_commit"]) == (S.OFF_COMMIT, S.ON_COMMIT)
    assert (doc["off_worktree"], doc["on_worktree"]) == ("$STACK_WORKDIR/stack-p426-off", "$STACK_WORKDIR/stack-p426-on")
    assert doc["out_root"] == "$STACK_WORKDIR/p426/rehearsal/r1"                    # §16.7 portable; post-reveal 3c: wd root
    ident = FreezeOps(off, on).identity(off)                                         # post-reveal 3e: date + identity recorded
    assert doc["frozen_prompt_date"] == S.EPOCH_DATE and all(doc[k] == v for k, v in ident.items())
    before = out.read_bytes()
    rc2, err2 = freeze(argv, ops=FreezeOps(off, on), checks=OK)
    assert rc2 == 2 and "REFUSED: " in err2 and out.read_bytes() == before                 # exclusive-created, immutable


def test_new_a_failed_precondition_refuses_naming_it_and_writes_nothing(tmp_path):
    off, on = worktrees(tmp_path)
    out = tmp_path / "records" / "rehearsal.json"
    seen = []

    def checks(kind, **inputs):
        seen.append(kind)
        return ["restore diff: 4 registry lines, want 3"]
    rc, err = freeze(rehearsal_argv(tmp_path, off, on, out), ops=FreezeOps(off, on), checks=checks)
    assert rc == 2 and any("REFUSED: " in ln and "restore diff" in ln for ln in err.splitlines()) and not out.exists()
    assert seen


def test_new_a_dirty_worktree_refuses_the_rehearsal_manifest(tmp_path):
    off, on = worktrees(tmp_path)
    out = tmp_path / "records" / "rehearsal.json"
    rc, err = freeze(rehearsal_argv(tmp_path, off, on, out), ops=FreezeOps(off, on, dirty=[on]), checks=OK)
    assert rc == 2 and "REFUSED: " in err and not out.exists()


def test_new_amend_refuses_a_v8_base_with_a_bad_self_hash_and_writes_nothing(tmp_path):
    off, on = worktrees(tmp_path)
    doc = S.v8_base()
    doc["settle_bound_s"] = 1.0
    bad = S.write_record(tmp_path / "rec" / "v8_base.json", doc)
    out = tmp_path / "rec" / "timeout_amendment.json"
    rc, err = freeze(["amend", "--v8", str(bad), "--pilot-off", str(leg_root_with(tmp_path, "tg1-p426-off-pilot.a1", "VALID")),
                      "--pilot-on", str(leg_root_with(tmp_path, "tg1-p426-on-pilot.a1", "VALID")), "--out", str(out)],
                     ops=FreezeOps(off, on), checks=OK)
    assert rc == 2 and "REFUSED: " in err and not out.exists()


def _v8_argv(tmp_path, off, on, manifest, out, *, r1_on=None, r1_elapsed_s=100.0):
    """§16.7: `v8 … --r1-off <leg root> --r1-on <leg root>` (R1 is a pair); each R1 root holds its arm-equality receipt."""
    m = manifest                                                               # post-reveal 3h: every leg bound to it
    r1_off = leg_root_with(tmp_path, "tg1-p426-rehearsal-off.a1", "VALID", elapsed_s=r1_elapsed_s, manifest=m)
    r1_on_root = leg_root_with(tmp_path, "tg1-p426-rehearsal-on.a1", "VALID", elapsed_s=r1_elapsed_s, manifest=m)
    if r1_on is not None:                                                      # post-reveal 3c: replaced, the leg writes one
        (r1_on_root / "receipt.json").write_text(json.dumps(r1_on, sort_keys=True, indent=1))
    r2 = leg_root_with(tmp_path, "tg1-p426-rehearsal-mismatch.a1", "INVALID", manifest=m)
    r3 = leg_root_with(tmp_path, "tg1-p426-rehearsal-kill.a1", "VALID", manifest=m)
    return ["v8", "--off-worktree", str(off), "--on-worktree", str(on), "--rehearsal-manifest", str(manifest),
            "--r1-off", str(r1_off), "--r1-on", str(r1_on_root), "--r2", str(r2), "--r3", str(r3), "--out", str(out)]


def _on_receipt_with(**env_worker):
    doc = S.arm_receipt_doc("on")
    doc = {k: v for k, v in doc.items() if k != "sha256"}
    doc["env"] = dict(doc["env"], worker=dict(doc["env"]["worker"], **env_worker))
    return S.self_hashed(doc)


def _r1_refusal(tmp_path, r1_on):
    off, on = worktrees(tmp_path)
    reh = S.write_record(tmp_path / "wd/rec" / "rehearsal.json", S.rehearsal_manifest(tmp_path / "wd/p426/rehearsal/r1"))
    out = tmp_path / "rec" / "v8_base.json"
    rc, err = freeze(_v8_argv(tmp_path, off, on, reh, out, r1_on=r1_on), ops=FreezeOps(off, on), checks=OK)
    return rc, err, out


def test_new_v8_refuses_an_r1_difference_outside_the_closed_list_naming_its_field(tmp_path):
    """[d2] §6.5 / §16.7: R1 only confirms its observed difference is a subset of the closed list; an entry outside it
    refuses (a finding for the operator, never an allowance) and v8 writes nothing."""
    rc, err, out = _r1_refusal(tmp_path, _on_receipt_with(MLX_VLM_CACHE_SESSION_MAX="2"))
    assert rc == 2 and not out.exists()
    assert any("REFUSED: " in ln and "MLX_VLM_CACHE_SESSION_MAX" in ln for ln in err.splitlines()), err


def test_new_v8_refuses_an_r1_credential_key_in_one_leg_only_naming_the_key_never_a_value(tmp_path):
    doc = {k: v for k, v in S.arm_receipt_doc("on").items() if k != "sha256"}
    doc["credential_keys"] = dict(doc["credential_keys"], worker=["HF_TOKEN", "OPENAI_API_KEY"])
    rc, err, out = _r1_refusal(tmp_path, S.self_hashed(doc))
    assert rc == 2 and not out.exists()
    assert any("REFUSED: " in ln and "OPENAI_API_KEY" in ln for ln in err.splitlines()), err
    assert S.FAKE_SECRET_40 not in err


def test_new_an_r1_difference_inside_the_closed_list_is_not_refused_as_an_r1_finding(tmp_path):
    """The contrast to the two refusals above: the §6.3 argv items and the drafter snapshot (ON only) are on the closed list.
    v8 may still refuse a precondition this fixture does not build, but never for R1; when it writes, `r1_env_difference`
    is the §16.7 entry list `{process: router|worker|probe|-, field, off, on}`."""
    rc, err, out = _r1_refusal(tmp_path, S.arm_receipt_doc("on"))
    refused = [ln for ln in err.splitlines() if "REFUSED: " in ln]
    r1_names = ("--r1-off", "--r1-on", "r1_env_difference", "R1", "--draft", "drafter")
    assert not any(n in ln.replace(str(tmp_path), "<tmp>") for ln in refused for n in r1_names), refused
    if rc == 0:
        doc = json.loads(out.read_text())
        assert doc["r1_env_difference"] and all(set(e) == {"process", "field", "off", "on"} and
                                                e["process"] in ("router", "worker", "probe", "-")
                                                for e in doc["r1_env_difference"])


def test_new_v8_refuses_a_rehearsal_manifest_of_the_wrong_kind_and_writes_nothing(tmp_path):
    off, on = worktrees(tmp_path)
    wrong = S.write_record(tmp_path / "wd/rec" / "not_rehearsal.json", S.v8_base())     # 3h: under $STACK_WORKDIR
    out = tmp_path / "rec" / "v8_base.json"
    rc, err = freeze(_v8_argv(tmp_path, off, on, wrong, out), ops=FreezeOps(off, on), checks=OK)
    assert rc == 2 and "REFUSED: " in err and not out.exists()


def test_new_v8_refuses_arms_whose_gitlinks_differ(tmp_path):
    off, on = worktrees(tmp_path)
    reh = S.write_record(tmp_path / "wd/rec" / "rehearsal.json", S.rehearsal_manifest(tmp_path / "wd/p426/rehearsal/r1"))
    out = tmp_path / "rec" / "v8_base.json"
    moved = dict(S.BASE_GITLINKS, **{"src/mlx-vlm": "0" * 40})
    rc, err = freeze(_v8_argv(tmp_path, off, on, reh, out), ops=FreezeOps(off, on, gitlinks={str(on): moved}), checks=OK)
    assert rc == 2 and any("REFUSED: " in ln and "gitlink" in ln for ln in err.splitlines()) and not out.exists()


# ------------------------------------------------------------------------------------------------ post-reveal 3d (§16.8)
def _v8(tmp_path, *, r1_elapsed_s=100.0, max_request_elapsed_s=100.0, checks=OK, ops_factory=None):
    """A v8 freeze whose inputs all hold (both worktrees carry the fork's pins; the rehearsal legs are complete)."""
    off, on = worktrees(tmp_path)
    for wt in (off, on):
        p = wt / "src/mlx-vlm/dev/p369_phase2/pins.json"
        p.parent.mkdir(parents=True)
        p.write_bytes(S.PINS.read_bytes())
    reh = S.write_record(tmp_path / "wd/rec" / "rehearsal.json", S.rehearsal_manifest(tmp_path / "wd/p426/rehearsal/r1"))
    out = tmp_path / "rec" / "v8_base.json"
    ops = (ops_factory or (lambda o, n: FreezeOps(o, n, max_request_elapsed_s=max_request_elapsed_s)))(off, on)
    rc, err = freeze(_v8_argv(tmp_path, off, on, reh, out, r1_elapsed_s=r1_elapsed_s), ops=ops, checks=checks)
    return rc, err, out


@pytest.mark.parametrize("leg_flag,change", [("--r2", dict(inject=None)), ("--r3", dict(inject="reconcile-mismatch")),
                                             ("--r1-on", dict(frozen_record=dict(path="$STACK_WORKDIR/rec/other.json",
                                                                                 sha256="0" * 64)))],
                         ids=["r2-without-inject", "r3-wrong-inject", "r1-other-manifest"])
def test_new_v8_refuses_a_rehearsal_leg_not_bound_to_its_manifest(tmp_path, leg_flag, change):
    """post-reveal 3h (§16.8 after the strict verify round 1): each R1-off / R1-on / R2 / R3 root is a leg run under this
    rehearsal manifest (`chain.json` `frozen_record: {path, sha256}` and `inject`) with its expected injection."""
    off, on = worktrees(tmp_path)
    for wt in (off, on):
        p = wt / "src/mlx-vlm/dev/p369_phase2/pins.json"
        p.parent.mkdir(parents=True)
        p.write_bytes(S.PINS.read_bytes())
    reh = S.write_record(tmp_path / "wd/rec" / "rehearsal.json", S.rehearsal_manifest(tmp_path / "wd/p426/rehearsal/r1"))
    out = tmp_path / "rec" / "v8_base.json"
    argv = _v8_argv(tmp_path, off, on, reh, out)
    root = Path(argv[argv.index(leg_flag) + 1])
    cj = json.loads((root / "chain.json").read_text())
    cj.update(change)
    (root / "chain.json").write_text(json.dumps(cj))
    rc, err = freeze(argv, ops=FreezeOps(off, on), checks=OK)
    assert rc == 2 and not out.exists()
    label = {"--r2": "R2", "--r3": "R3", "--r1-on": "R1"}[leg_flag]
    assert any("REFUSED: " in ln and label in ln for ln in err.splitlines()), err


def test_new_v8_does_not_compare_the_rehearsal_manifests_commits_with_its_arms(tmp_path):
    """post-reveal 3h (§16.8): the manifest's commits (the B2 / throwaway rehearsal commits, §1) are not compared with the v8
    arms."""
    off, on = worktrees(tmp_path)
    for wt in (off, on):
        p = wt / "src/mlx-vlm/dev/p369_phase2/pins.json"
        p.parent.mkdir(parents=True)
        p.write_bytes(S.PINS.read_bytes())
    reh = S.write_record(tmp_path / "wd/rec" / "rehearsal.json", S.rehearsal_manifest(
        tmp_path / "wd/p426/rehearsal/r1", off_commit="c" * 40, on_commit="d" * 40))
    out = tmp_path / "rec" / "v8_base.json"
    rc, err = freeze(_v8_argv(tmp_path, off, on, reh, out), ops=FreezeOps(off, on), checks=OK)
    assert rc == 0, err


@pytest.mark.parametrize("r1_elapsed,hist_max,want", [(700.0, 300.0, 1400.0), (300.0, 800.0, 1600.0), (100.0, 200.0, 900.0)],
                         ids=["r1-largest", "history-largest", "floor"])
def test_new_v8_derives_its_settle_bound_from_r1_and_the_history_with_a_900_s_floor(tmp_path, r1_elapsed, hist_max, want):
    """§4.2 / §16.8: v8 `settle_bound_s = max(900, 2 × max(R1's largest single-request elapsed,
    historical_walls.max_request_elapsed_s))`, elapsed = the item records' request `elapsed_s`; never typed."""
    rc, err, out = _v8(tmp_path, r1_elapsed_s=r1_elapsed, max_request_elapsed_s=hist_max)
    assert rc == 0, err
    doc = json.loads(out.read_text())
    assert doc["kind"] == "p426_v8_base" and doc["settle_bound_s"] == pytest.approx(want)


@pytest.mark.parametrize("pilot_elapsed,want", [(800.0, 1600.0), (300.0, 1000.0)], ids=["raised", "kept"])
def test_new_the_amendment_raises_the_settle_bound_over_both_pilots(tmp_path, pilot_elapsed, want):
    """§4.2 / §16.8: the amendment's `settle_bound_s = max(v8's, 2 × the largest single-request elapsed over both pilots)`."""
    from bench.tests import b2_frozen_add_support as A
    off, on = worktrees(tmp_path)
    v8 = S.write_record(tmp_path / "rec" / "v8_base.json", S.v8_base(settle_bound_s=1000.0))
    roots = {}
    for arm in ("off", "on"):
        name = f"tg1-p426-{arm}-pilot.a1"
        root = tmp_path / "wd/p426/wave2" / name
        A.write_leg(root, name.rsplit(".a", 1)[0], ["pilot", "--p426", "--predictor", "mtp" if arm == "on" else "off",
                                                     "--out-root", str(root)], dict(elapsed_s=pilot_elapsed if arm == "on" else 50.0))
        leg_record(root, name, "VALID")
        roots[arm] = root
    dossier = pilot_dossier(tmp_path, roots)
    out = tmp_path / "rec" / "amendment.json"
    rc, err = freeze(["amend", "--v8", str(v8), "--pilot-off", str(roots["off"]), "--pilot-on", str(roots["on"]), "--out", str(out)],
                     ops=FreezeOps(off, on), checks=OK)
    assert rc == 0, err
    doc = json.loads(out.read_text())
    assert doc["settle_bound_s"] == pytest.approx(want)
    assert doc["pilot_dossier_sha256"] == S.sha256_file(dossier)          # post-reveal 3h (§16.8 after the strict verify round 1)


def pilot_dossier(tmp_path, roots, *, verdict="PASS"):
    """post-reveal 3h (§16.8): `amend` runs the complete pilot gate, the pilots' pair dossier included — the sequencer's
    `<out-base>/pairs/pilot__off-a<n>__on-a<m>.json` (§6.5 / §16.6), written by the pinned `p426_receipt.write_dossier`."""
    from bench import p426_receipt
    harvests = {}
    for arm in ("off", "on"):
        h = tmp_path / "main/benchmark/results/p426/wave2" / roots[arm].name / "HARVEST.json"
        h.parent.mkdir(parents=True, exist_ok=True)
        h.write_text(json.dumps(S.self_hashed(dict(leg=roots[arm].name.rsplit(".a", 1)[0], attempt=1, state="VALID", files=[]))))
        harvests[arm] = h
    path = roots["off"].parent / "pairs" / "pilot__off-a1__on-a1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    p426_receipt.write_dossier(path, pair="pilot",
                               off=dict(attempt=roots["off"].name, receipt=roots["off"] / "receipt.json", harvest=harvests["off"]),
                               on=dict(attempt=roots["on"].name, receipt=roots["on"] / "receipt.json", harvest=harvests["on"]),
                               differences=[], verdict=verdict)
    return path


def _amend_with_dossier(tmp_path, verdict):
    from bench.tests import b2_frozen_add_support as A
    off, on = worktrees(tmp_path)
    v8 = S.write_record(tmp_path / "rec" / "v8_base.json", S.v8_base(settle_bound_s=1000.0))
    roots = {}
    for arm in ("off", "on"):
        name = f"tg1-p426-{arm}-pilot.a1"
        root = tmp_path / "wd/p426/wave2" / name
        A.write_leg(root, name.rsplit(".a", 1)[0], ["pilot", "--p426", "--predictor", "mtp" if arm == "on" else "off",
                                                     "--out-root", str(root)], {})
        leg_record(root, name, "VALID")
        roots[arm] = root
    if verdict is not None:
        pilot_dossier(tmp_path, roots, verdict=verdict)
    out = tmp_path / "rec" / "amendment.json"
    rc, err = freeze(["amend", "--v8", str(v8), "--pilot-off", str(roots["off"]), "--pilot-on", str(roots["on"]), "--out", str(out)],
                     ops=FreezeOps(off, on), checks=OK)
    return rc, err, out


@pytest.mark.parametrize("verdict", [None, "FAIL"], ids=["no-dossier", "fail-dossier"])
def test_new_amend_refuses_without_a_pass_pilot_dossier(tmp_path, verdict):
    """post-reveal 3h (§16.8 after the strict verify round 1): `p426_freeze amend` runs the complete pilot gate itself; with
    no pilot pair dossier, or a FAIL one, it refuses and writes nothing."""
    rc, err, out = _amend_with_dossier(tmp_path, verdict)
    assert rc == 2 and any(ln.startswith("REFUSED: ") and "dossier" in ln for ln in err.splitlines()), err
    assert not out.exists()


def test_new_v8_refuses_a_failed_production_tree_precondition_naming_it(tmp_path):
    """§10.1 / §16.8: every precondition (the fork tree at the gitlink against the production ref's tree under `mlx_vlm/`
    among them) goes through `checks(kind, **inputs)`; a failed one refuses naming it and writes nothing."""
    def checks(kind, **inputs):
        return ["production tree: src/mlx-vlm at the gitlink differs from the production ref under mlx_vlm/"] if kind == "v8" else []
    rc, err, out = _v8(tmp_path, checks=checks)
    assert rc == 2 and any("REFUSED: " in ln and "production tree" in ln for ln in err.splitlines()) and not out.exists()


@pytest.mark.parametrize("seam", SEAMS)
def test_new_a_missing_freeze_seam_is_a_refusal_never_a_traceback(tmp_path, seam):
    """§16.8: a missing seam is a refusal (`REFUSED:`, rc 2), never a traceback; nothing is written."""
    rc, err, out = _v8(tmp_path, ops_factory=lambda o, n: MissingSeam(o, n, missing=seam))
    assert rc == 2 and any(ln.startswith("REFUSED: ") for ln in err.splitlines()) and "Traceback" not in err
    assert not out.exists()
