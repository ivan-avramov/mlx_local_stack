"""M76 B1 (test-writer): the f45 arm registries (X, V, XO over the REAL committed `main_models.yaml` entry), the edit model's two new
operations ("add a line after key K", "comment a line") and their refusals, R1 (arm diff = exactly the listed lines + the comment),
and the expected KV line of the f45 arms.

Class: (c) new behaviour unless stated; (a) marks a failure the specification fixes (the baseline edit model can only rewrite lines
that already exist, so it cannot add `tq4_attention`).
"""
from __future__ import annotations

import difflib
import re

import pytest
import yaml

from bench.tests.test_m76_b1_fe_support import (BASE, F45_ARMS, F45_PICK, entry_lines, entry_of, prepare_f45, prepared_texts,  # noqa: F401
                                                real_text, world)

MTP_KEYS = ("draft_kind", "draft_model", "mtp_verify_scan")
U4_PICK = "Qwen3.8-27B-mlx-uniform-4bit"


def line_diff(base, arm):
    """(removed [(index in base, line)], added [line]) of the arm text against the base text."""
    b, a = base.splitlines(), arm.splitlines()
    removed, added = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, b, a, autojunk=False).get_opcodes():
        if op != "equal":
            removed += [(i, b[i]) for i in range(i1, i2)]
            added += a[j1:j2]
    return removed, added


def in_entry(text, old, new):
    """`text` with the first `old` inside the f45 entry's lines replaced by `new` (never another entry's)."""
    lines, start, end = entry_lines(text)
    for n in range(start, end):
        if old in lines[n]:
            lines[n] = lines[n].replace(old, new, 1)
            return "".join(lines)
    raise AssertionError(f"{old!r} not in the entry")


def classify_added(added, arm, mode):
    """Name each added line: kv / tq4 / comment / commented-out / OTHER."""
    kinds = []
    for ln in added:
        if re.match(r"^    kv_bits: 4(\s+#.*)?$", ln):
            kinds.append("kv")
        elif re.match(rf"^    tq4_attention: {mode}\s*(#.*)?$", ln):
            kinds.append("tq4")
        elif f"# PROVISIONAL M76 arm {arm}" in ln:
            kinds.append("comment")
        elif re.match(rf"^    # ({'|'.join(MTP_KEYS)}):", ln):
            kinds.append("commented-out")
        else:
            kinds.append(f"OTHER:{ln}")
    return kinds


def check_arm(texts, arm, mode, commented):
    """The arm diff is exactly the spec's lines + one arm comment, inside the entry; returns the added kinds."""
    base, text = real_text(), texts[arm]
    removed, added = line_diff(base, text)
    _, start, end = entry_lines(base)
    assert all(start <= i < end for i, _ in removed), removed
    want_removed = {"kv_bits: 0"} | {k for k in MTP_KEYS if k in commented}
    got_removed = {re.match(r"^\s*([a-z_0-9]+: ?\S*)", ln).group(1) for i, ln in removed if i != start}
    assert {g.split(" ")[0].rstrip(":") for g in got_removed} == {w.split(":")[0] for w in want_removed}, removed
    kinds = classify_added(added, arm, mode)
    assert not [k for k in kinds if k.startswith("OTHER")], kinds
    assert kinds.count("kv") == 1 and kinds.count("tq4") == 1 and kinds.count("commented-out") == len(commented), kinds
    assert text.count(f"PROVISIONAL M76 arm {arm}") == 1 and "PROVISIONAL P475 arm" not in text
    lines = text.splitlines()
    _, ts, te = entry_lines(text)                                    # the f45 entry's span only (another entry also has `kv_bits: 4`)
    i = next(n for n in range(ts, te) if re.match(r"^    kv_bits: 4(\s+#.*)?$", lines[n]))
    assert re.match(rf"^    tq4_attention: {mode}\s*(#.*)?$", lines[i + 1]), lines[i:i + 2]         # "on the line after kv_bits"
    base_lines = base.splitlines()
    assert lines[te:] == base_lines[end:]                                                           # nothing after the entry changed
    assert ts == start and lines[:start] == base_lines[:start]                                      # nor before it
    return kinds


@pytest.mark.parametrize("arm, mode", [("X", "m72_exact"), ("V", "m72_v1")])
def test_x_and_v_differ_from_the_base_by_exactly_the_listed_lines(prepared_texts, arm, mode):
    """(a)/(c) X: `kv_bits: 0 …` -> `kv_bits: 4` + `tq4_attention: <mode>` on the next line + the arm comment; nothing else."""
    check_arm(prepared_texts, arm, mode, commented=())
    e, b = entry_of(prepared_texts[arm]), entry_of(real_text())
    assert e == dict(b, kv_bits=4, tq4_attention=mode)
    base_doc, arm_doc = yaml.safe_load(real_text()), yaml.safe_load(prepared_texts[arm])
    assert [m for m in arm_doc["models"] if m["name"] != F45_PICK] == [m for m in base_doc["models"] if m["name"] != F45_PICK]
    assert {k: v for k, v in arm_doc.items() if k != "models"} == {k: v for k, v in base_doc.items() if k != "models"}


def test_xo_is_x_with_the_three_mtp_lines_commented_out_value_kept(prepared_texts):
    """(c) XO: as X, plus `draft_kind`, `draft_model`, `mtp_verify_scan` commented out with a `# ` prefix, value kept."""
    text, base = prepared_texts["XO"], real_text()
    check_arm(prepared_texts, "XO", "m72_exact", commented=MTP_KEYS)
    originals = {m.group(1): ln.strip() for ln in base.splitlines() if (m := re.match(rf"^    ({'|'.join(MTP_KEYS)}):", ln))}
    assert sorted(originals) == sorted(MTP_KEYS)
    for key, original in originals.items():
        assert f"    # {original}" in text.splitlines(), (key, original)
    e, b = entry_of(text), entry_of(base)
    assert not (set(MTP_KEYS) & set(e))
    assert e == {k: v for k, v in dict(b, kv_bits=4, tq4_attention="m72_exact").items() if k not in MTP_KEYS}


def test_n16_is_the_base_commit_itself(tmp_path):
    """(c) N16: no edit — the arm branch stays on the base commit, nothing is committed for it."""
    rc, ops, wd = prepare_f45(tmp_path)
    assert rc == 0 and ops.branches["m76-f45-n16"] == BASE and ops.committed("m76-f45-n16") is None


def test_the_arm_edits_keep_every_other_key_of_the_entry(prepared_texts):
    """(b) The arm edits never drop or change the entry's other keys (generation_defaults, prefill_step_size, attention_policy …)."""
    base = entry_of(real_text())
    for arm in ("X", "V", "XO"):
        e = entry_of(prepared_texts[arm])
        for key in set(base) - {"kv_bits", *MTP_KEYS}:
            assert e[key] == base[key], (arm, key)


def test_the_edit_model_leaves_the_other_entries_byte_for_byte(prepared_texts):
    """(b) The u4 entry has the same keys (kv_bits, draft_kind …): an f45 arm must leave it untouched."""
    base_lines = real_text().splitlines()
    _, s, e = entry_lines(real_text(), U4_PICK)
    for arm in ("X", "V", "XO"):
        t = prepared_texts[arm].splitlines()
        assert t[s:e] == base_lines[s:e], arm


# ================================================================================================ the edit model's refusals
def _with_line_after(text, key, new_line):
    lines, start, end = entry_lines(text)
    out = []
    for n, ln in enumerate(lines):
        out.append(ln)
        if start < n < end and ln.startswith(f"    {key}:"):
            out.append(new_line + "\n")
    assert len(out) == len(lines) + 1
    return "".join(out)


def _without_key(text, key):
    lines, start, end = entry_lines(text)
    kept = [ln for n, ln in enumerate(lines) if not (start < n < end and re.match(rf"^    {key}:", ln))]
    assert len(kept) == len(lines) - 1
    return "".join(kept)


def _commits(ops):
    return {arm: ops.committed(f"m76-f45-{arm.lower()}") for arm in F45_ARMS if arm != "N16"}


@pytest.mark.parametrize("existing", ["m72_exact", "m72_v1"])
def test_adding_a_key_that_already_exists_refuses(tmp_path, capsys, existing):
    """(c) The base entry already carries `tq4_attention`: X, V and XO (which add it) refuse; no arm commit is made for them."""
    base = _with_line_after(real_text(), "kv_bits", f"    tq4_attention: {existing}")
    rc, ops, wd = prepare_f45(tmp_path, base_text=base)
    err = capsys.readouterr().err
    assert rc == 1 and "tq4_attention" in err
    assert _commits(ops) == dict(X=None, V=None, XO=None)


def test_editing_a_key_the_entry_lacks_refuses(tmp_path, capsys):
    """(c) No `kv_bits` line in the entry: every arm that rewrites it (X, V, XO) refuses, nothing is committed."""
    rc, ops, wd = prepare_f45(tmp_path, base_text=_without_key(real_text(), "kv_bits"))
    err = capsys.readouterr().err
    assert rc == 1 and "kv_bits" in err
    assert _commits(ops) == dict(X=None, V=None, XO=None)


@pytest.mark.parametrize("key", MTP_KEYS)
def test_commenting_a_line_the_entry_lacks_refuses_only_xo(tmp_path, capsys, key):
    """(c) "comment a line" on a missing key refuses: XO fails, X and V (which do not touch it) are still made."""
    rc, ops, wd = prepare_f45(tmp_path, base_text=_without_key(real_text(), key))
    err = capsys.readouterr().err
    assert rc == 1 and key in err
    commits = _commits(ops)
    assert commits["XO"] is None and commits["X"] is not None and commits["V"] is not None


# ================================================================================================ R1 on the f45 arms
@pytest.mark.parametrize("arm, tamper", [
    ("X", lambda t: in_entry(t, "tq4_attention: m72_exact", "tq4_attention: m72_v1")),                # the other mode
    ("V", lambda t: in_entry(t, "tq4_attention: m72_v1", "tq4_attention: m72_exact")),
    ("V", lambda t: in_entry(t, "    tq4_attention: m72_v1", "    # tq4_attention: m72_v1")),            # the added line commented out
    ("X", lambda t: in_entry(t, "    kv_bits: 4", "    kv_bits: 8")),                                    # a wrong width
    ("XO", lambda t: in_entry(t, "    # draft_kind:", "    draft_kind:")),                              # a line left un-commented
    ("XO", lambda t: in_entry(t, "    # mtp_verify_scan:", "    mtp_verify_scan:")),
    ("X", lambda t: in_entry(t, "prefill_step_size: 512", "prefill_step_size: 1024")),                  # another key of the entry
    ("V", lambda t: t.replace("PROVISIONAL M76 arm V", "PROVISIONAL P475 arm V", 1)),                  # the u4 comment text
    ("X", lambda t: t.replace("PROVISIONAL M76 arm X", "PROVISIONAL M76 arm V", 1)),                   # another arm's comment
    ("X", lambda t: t + "# trailing note\n"),                                                           # an extra line elsewhere
    ("X", lambda t: t.replace("PROVISIONAL M76 arm X", "", 1)),                                         # the comment missing
])
def test_an_arm_commit_beyond_its_listed_edit_is_not_started(world, arm, tamper):
    """(c) R1: the arm worktree's commit must be the base plus exactly the arm's listed lines + comment; any deviation (wrong mode,
    missing line, extra change, wrong comment) is a pre-check refusal, nothing starts."""
    w = world
    rec = w.ops.arms[arm]
    tampered = tamper(rec["text"])
    assert tampered != rec["text"]
    rec["text"] = tampered
    _, r = w.run_leg(arm)
    assert r["verdict"] == "NOT_STARTED" and r["problems"], r
    assert not w.ops.spawned and not any(c[0] == "stack" for c in w.ops.calls)


def test_the_n16_commit_must_be_the_base_itself(world):
    """(c) The base arm of f45 is N16: a commit on top of the base (HEAD != base) is refused."""
    w = world
    w.ops.arms["N16"].update(head="c" * 40, branch_tip="c" * 40)
    _, r = w.run_leg("N16")
    assert r["verdict"] == "NOT_STARTED" and any("base" in p for p in r["problems"]), r["problems"]


def test_an_x_arm_commit_is_not_an_xo_arm_commit(world):
    """(c) R1 distinguishes the arms: XO's worktree holding X's registry (MTP lines still active) is refused."""
    w = world
    w.ops.arms["XO"]["text"] = w.ops.arms["X"]["text"]
    _, r = w.run_leg("XO")
    assert r["verdict"] == "NOT_STARTED" and r["problems"] and not w.ops.spawned


# ================================================================================================ the expected KV line
@pytest.mark.parametrize("arm", ["X", "V", "XO"])
def test_the_tq4_arms_expect_todays_tq4_kv_line(world, arm):
    """(c) bits 4, `turboquant`, split fields None, group 64, start 0, `TQ_KV_QUANT_MODE` 'mse': a healthy line is VALID and recorded."""
    w = world
    _, r = w.run_leg(arm)
    assert r["verdict"] == "VALID", r["problems"]
    assert r["kv_line"]["kv_bits"] == 4 and r["kv_line"]["kv_quant_scheme"] == "turboquant"


@pytest.mark.parametrize("arm", ["X", "V", "XO"])
@pytest.mark.parametrize("over", [dict(kv_bits=None), dict(kv_bits=0.0), dict(kv_bits=8.0), dict(kv_quant_scheme="uniform"),
                                  dict(kv_group_size=32), dict(quantized_kv_start=1), dict(TQ_KV_QUANT_MODE="prod"),
                                  dict(kv_key_bits=4), dict(kv_value_scheme="uniform")])
def test_a_tq4_arm_with_another_kv_line_is_invalid_before_the_driver(world, arm, over):
    """(c) R5/R22 for f45: each deviation from the TQ4 rule aborts the leg after load, before the driver."""
    w = world
    w.ops.kv_over_arm[arm] = over
    _, r = w.run_leg(arm)
    assert r["verdict"] == "INVALID" and any("KV line" in p for p in r["problems"]), r["problems"]
    assert not w.ops.spawned and ("stop_stack",) in w.ops.calls


@pytest.mark.parametrize("over", [dict(kv_bits=4.0), dict(kv_bits=8.0)])
def test_the_native_arm_expects_the_native_line(world, over):
    """(b)/(c) N16 as today's native rule: the healthy native line (kv_bits None) is VALID; a quantized line is refused."""
    w = world
    _, ok = w.run_leg("N16")
    assert ok["verdict"] == "VALID" and ok["kv_line"]["kv_bits"] is None, ok["problems"]
    w.ops.t += 700
    w.ops.kv_over_arm["N16"] = over
    _, r = w.run_leg("N16", attempt=2)
    assert r["verdict"] == "INVALID" and any("KV line" in p for p in r["problems"]) and len(w.ops.spawned) == 1
