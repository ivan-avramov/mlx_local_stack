"""M76 B1 (test-writer): the f45 instability floor (S18-P13 / S22-P2: 0.02), the f45 matrix (tables, route-counter deltas per leg, the
V / X ratios and the stage-4 trigger line) and the u4 floor-less rule it must not change.

The numbers go in through the ladder rows the fake driver writes (`ops.metric(arm, block, ctx)`), the verdicts come out of the public
`run` / `matrix` entries and the generated table. Class (c) new behaviour unless marked (b) (u4 invariants, green on the baseline).
"""
from __future__ import annotations

import re

import pytest

from bench import p475_kv as K
from bench.tests.test_m76_b1_fe_support import F45_ARMS, F45_PICK, prepared_texts, world  # noqa: F401
from bench.tests.test_p475_impl_support import BASE, FakeOps, make_cfg

def section(text, title):
    """The lines of the standard table `## <title>` (exact heading, as `METRICS` titles it today)."""
    lines = text.splitlines()
    i = next(n for n, ln in enumerate(lines) if ln.strip() == f"## {title}")
    j = next((n for n in range(i + 1, len(lines)) if lines[n].startswith("## ")), len(lines))
    return lines[i + 1:j]


def row(text, title, arm, ctx):
    rows = [ln for ln in section(text, title) if ln.startswith(f"| {arm} | {ctx} |")]
    assert len(rows) == 1, (title, arm, ctx, rows)
    return rows[0]


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def trigger_block(text):
    """The stage-4 trigger line and what follows it up to the next blank line."""
    lines = text.splitlines()
    i = next((n for n, ln in enumerate(lines) if re.search(r"stage-4 trigger", ln, re.I)), None)
    assert i is not None, "no `stage-4 trigger` line in the f45 matrix"
    out = []
    for ln in lines[i:]:
        if not ln.strip() and out:
            break
        out.append(ln)
    return "\n".join(out)


TRIGGER_FORM = re.compile(r"^stage-4 trigger: \*\*(met|not met)\*\*( — .+| \(.+\))?\s*$")


def is_met(block):
    """Errata v1.1 form: `stage-4 trigger: **met** (…)` / `stage-4 trigger: **not met** — <cells>` (the verdict in bold)."""
    first = block.splitlines()[0]
    m = TRIGGER_FORM.match(first)
    assert m, first
    return m.group(1) == "met"


def names_rung(block, ctx):
    s = str(ctx)
    return bool(re.search(rf"(?<![\d,]){s[:-3]},?{s[-3:]}(?![\d,])", block))


# ================================================================================================ the floor
def prefill_x8192(r1, r2):
    """N16 prefills at the ladder default (500 tok/s); X at 8192 tokens by the two blocks' ratios; everything else neutral."""
    def metric(arm, block, ctx):
        if arm == "X" and ctx == 8192 and block in (1, 2):
            return dict(pps=500.0 * (r1 if block == 1 else r2))
        return {}
    return metric


FLOOR_CASES = [
    # (r1, r2, flagged under the 0.02 floor, label parts the cell must / must not show)
    (0.9955, 1.0045, False, ()),                      # the S18-P13 cells: spread 0.009, mean ~ 1.00
    (1.0, 1.019, False, ()),                          # |r1 - r2| just inside the floor, mean - 1 inside the floor
    (1.0, 1.021, True, ("SPREAD",)),                  # |r1 - r2| just over the floor: the second clause
    (1.03, 1.03, False, ()),                          # mean outside the floor but no spread at all
    (1.03, 1.045, False, ()),                         # |mean - 1| > floor, spread 0.015 <= |mean - 1| / 2 and <= floor
    (1.03, 1.06, True, ("SPREAD",)),                  # |mean - 1| > floor and spread > |mean - 1| / 2
    (1.03, 0.97, True, ("REVERSAL", "SPREAD")),       # sign change, both |r - 1| > floor
    (1.015, 0.985, True, ("SPREAD", "!REVERSAL")),    # sign change inside the floor: a spread, not a reversal
]


@pytest.mark.parametrize("r1, r2, flagged, parts", FLOOR_CASES)
def test_the_f45_floor_decides_which_cells_flag(world, r1, r2, flagged, parts):
    """(c) `spread` only when |mean − 1| > floor and |r1 − r2| > |mean − 1| / 2, or |r1 − r2| > floor; `reversal` needs |r1 − 1| and
    |r2 − 1| > floor besides the sign change. A flagged cell triggers the deciding block b3 (block-1 order)."""
    w = world
    w.ops.metric = prefill_x8192(r1, r2)
    rc = w.main("run")
    legs = w.ops.spawned_legs()
    text = w.matrix_text()
    cell = cells(row(text, "backend prefill tok/s", "X", 8192))
    label = cell[-1]
    if flagged:
        assert legs[8:] == [f"f45-{a.lower()}-b3.a1" for a in F45_ARMS] and rc == 0, (legs, rc)
        for p in parts:
            assert (p[1:] not in label) if p.startswith("!") else (p in label), (parts, label)
    else:
        assert len(legs) == 8 and label == "stable" and rc == 0, (legs, label, rc)


def test_the_s18_p13_cells_do_not_trigger_a_deciding_block_under_f45_but_do_under_u4(world, tmp_path):
    """(b)+(c) The two AF4 8192 prefill cells of S18-P13 (spread 0.009, mean ~ 1.00): flagged by today's u4 rule (the u4 run adds
    deciding block b3), not by the f45 floor."""
    uops, ucfg = FakeOps(tmp_path / "u"), make_cfg(tmp_path / "u")
    uops.add_all(ucfg)
    uops.metric = lambda arm, block, ctx: dict(pps=500.0 * (0.9955 if block == 1 else 1.0045)) if arm == "AF4" and ctx == 8192 and block in (1, 2) else {}
    args = K.parse_args(["--workdir", str(ucfg.workdir), "--repo", str(ucfg.repo), "--base", BASE, "run"])
    assert K.run(args, uops) == 0
    assert len(uops.spawned) == 18                                           # 12 measured + the deciding block b3
    u4_text = (ucfg.results / f"MATRIX.{K.PICK}.md").read_text()
    assert "SPREAD" in row(u4_text, "backend prefill tok/s", "AF4", 8192)
    w = world
    w.ops.metric = prefill_x8192(0.9955, 1.0045)
    assert w.main("run") == 0 and len(w.ops.spawned_legs()) == 8


@pytest.mark.parametrize("r1, r2, label", [(1.0, 1.019, "SPREAD"), (1.015, 0.985, "REVERSAL"), (0.9955, 1.0045, "SPREAD")])
def test_u4_keeps_its_floor_less_rule(tmp_path, r1, r2, label):
    """(b) u4 today: any spread above |mean − 1| / 2 and any sign change flags, however small (no floor)."""
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_all(cfg)
    ops.metric = lambda arm, block, ctx: dict(pps=500.0 * (r1 if block == 1 else r2)) if arm == "AF4" and ctx == 8192 and block in (1, 2) else {}
    args = K.parse_args(["--workdir", str(cfg.workdir), "--repo", str(cfg.repo), "--base", BASE, "run"])
    assert K.run(args, ops) == 0 and len(ops.spawned) == 18
    assert label in row((cfg.results / f"MATRIX.{K.PICK}.md").read_text(), "backend prefill tok/s", "AF4", 8192)


# ================================================================================================ the f45 matrix content
def vx_metric(vx=lambda ctx, block: 1.25, flag_x=None):
    """N16 / X / V / XO values chosen so no V / X ratio collides with another ratio of the tables:
    decode N16 30, X 40, V 40 × vx; prefill N16 500, X 400, V 360; peak N16 40, X 20, V 30; XO 25 / 400 / 20."""
    def metric(arm, block, ctx):
        if arm == "N16":
            return dict(decode=30.0, pps=500.0, peak=40.0)
        if arm == "XO":
            return dict(decode=25.0, pps=400.0, peak=20.0)
        x_decode = 40.0 if not flag_x or block != 2 or ctx not in flag_x else 44.0
        if arm == "X":
            return dict(decode=x_decode, pps=400.0, peak=20.0)
        return dict(decode=x_decode * vx(ctx, block), pps=360.0, peak=30.0)
    return metric


def test_the_f45_matrix_has_its_label_arms_and_ratios_vs_n16(world):
    """(c) Title "M76 stage 1 (P475 instrument)", the f45 pick, only N16 / X / V / XO rows, acceptance (MTP ON) without XO, ratios vs N16."""
    w = world
    w.ops.metric = vx_metric()
    assert w.main("run") == 0
    text = w.matrix_text(partial=False)
    first = text.splitlines()[0]
    assert "M76 stage 1 (P475 instrument)" in first and F45_PICK in first and "partial matrix, P475 v4" not in first
    for title in ("cumulative peak GB", "backend prefill tok/s", "decode tok/s"):
        assert {cells(ln)[0] for ln in section(text, title) if ln.startswith("| ") and not ln.startswith("| arm") and "---" not in ln} \
            == set(F45_ARMS), title
    assert {cells(ln)[0] for ln in section(text, "MTP acceptance (ON)") if ln.startswith("| ") and not ln.startswith("| arm")} \
        == {"N16", "X", "V"}
    c = cells(row(text, "decode tok/s", "X", 8192))
    assert c[2:4] == ["40.00", "40.00"] and c[-3:-1] == ["1.333", "1.333"]                  # b1 / N16 and b2 / N16
    assert "AF8" not in text and "TQ8" not in text


def test_the_matrix_records_the_route_counters_per_leg(world):
    """(c) "the route-counter … per leg" (Errata v1.1: the exit counters are the leg's counts): every TQ4 leg's own counters (the fake
    scales them by the block number) are in the table."""
    w = world
    w.ops.metric = vx_metric()
    assert w.main("run") == 0
    text = w.matrix_text(partial=False)
    for counter in ("p2s", "d2_verify", "mma", "d2", "native:prefill", "native:decode", "native:verify"):
        assert counter in text, counter
    for number in ("900", "1800", "1200", "2400", "1300", "2600"):               # X / V b1, b2 ; XO d2 b1, b2 ; XO native:decode
        assert number in text, number


def test_the_v_over_x_ratios_are_tabulated_per_rung_and_block(world):
    """(c) V / X per rung and block for decode, prefill and peak: 50 / 40 = 1.25, 360 / 400 = 0.9, 30 / 20 = 1.5 on every rung of both
    blocks."""
    w = world
    w.ops.metric = vx_metric()
    assert w.main("run") == 0
    text = w.matrix_text(partial=False)
    m = re.search(r"V\s*/\s*X", text)
    assert m, "no V / X table in the f45 matrix"
    tail = text[m.start():]
    for pattern, what in ((r"(?<![\d.])1\.250?(?!\d)", "decode"), (r"(?<![\d.])0\.900?(?!\d)", "prefill"), (r"(?<![\d.])1\.500?(?!\d)", "peak")):
        assert len(re.findall(pattern, tail)) >= 8, (what, "4 rungs x 2 blocks")


# ================================================================================================ the stage-4 trigger
def vx_by(table):
    """{(ctx, block): ratio}, default 1.25."""
    return lambda ctx, block: table.get((ctx, block), 1.25)


TRIGGER_CASES = [
    # id, V / X decode ratio overrides, expected met, rungs the not-met line must name
    ("all-1.25", {}, True, ()),
    ("boundary-1.05-inclusive", {(131072, 1): 1.05, (131072, 2): 1.05, (260096, 1): 1.05, (260096, 2): 1.05}, True, ()),
    ("131072-b2-just-below", {(131072, 2): 1.0475}, False, (131072,)),
    ("260096-b1-below", {(260096, 1): 1.04}, False, (260096,)),
    ("both-rungs-below", {(131072, 1): 1.0, (131072, 2): 1.0, (260096, 1): 1.0, (260096, 2): 1.0}, False, (131072, 260096)),
    ("only-the-other-rungs-below", {(8192, 1): 1.0, (8192, 2): 1.0, (196608, 1): 0.9, (196608, 2): 0.9}, True, ()),
]


@pytest.mark.parametrize("name, table, met, rungs", TRIGGER_CASES, ids=[c[0] for c in TRIGGER_CASES])
def test_the_stage_4_trigger_line(world, name, table, met, rungs):
    """(c) **met** iff V / X decode ≥ 1.05 at 131,072 and at 260,096 in both blocks (and no unresolved flag there), else **not met**
    with the failing cells named; the other rungs do not count."""
    w = world
    w.ops.metric = vx_metric(vx_by(table))
    assert w.main("run") == 0
    block = trigger_block(w.matrix_text(partial=False))
    assert is_met(block) is met, block
    for ctx in rungs:
        assert names_rung(block, ctx), (ctx, block)


def test_the_stage_4_trigger_line_has_exactly_the_errata_form(world):
    """(c) Errata v1.1: the line is `stage-4 trigger: **met** …` / `stage-4 trigger: **not met** — <cells>`: the line STARTS with
    `stage-4 trigger:` (nothing bold before it), the verdict alone is bold, and exactly one such line exists. (a) fails before the
    fix round (the whole phrase was bold)."""
    w = world
    w.ops.metric = vx_metric(vx_by({(131072, 2): 1.0475}))
    assert w.main("run") == 0
    text = w.matrix_text(partial=False)
    lines = [ln for ln in text.splitlines() if re.search(r"stage-4 trigger", ln, re.I)]
    assert len(lines) == 1 and lines[0].startswith("stage-4 trigger: **not met** — "), lines
    assert "**stage-4" not in text and names_rung(lines[0], 131072)


def test_the_stage_4_met_line_form(world):
    """(c) The met form: `stage-4 trigger: **met**` first on its line."""
    w = world
    w.ops.metric = vx_metric()
    assert w.main("run") == 0
    lines = [ln for ln in w.matrix_text(partial=False).splitlines() if re.search(r"stage-4 trigger", ln, re.I)]
    assert len(lines) == 1 and lines[0].startswith("stage-4 trigger: **met**") and "**not met**" not in lines[0], lines


def test_only_the_decode_flags_of_v_and_x_block_the_trigger(world):
    """(c) Errata v1.1: "the blocking flags are the decode-metric flags of V and X at 131,072 and 260,096 only": an unresolved
    PREFILL flag of V at 131072 (cap 0 leaves it unresolved) does not block a met trigger."""
    w = world
    base = vx_metric()

    def metric(arm, block, ctx):
        out = base(arm, block, ctx)
        if arm == "V" and ctx == 131072 and block == 2:
            out = dict(out, pps=out["pps"] * 1.3)
        return out
    w.ops.metric = metric
    assert w.main("run", "--max-deciding", "0") == 1
    text = w.matrix_text(partial=False)
    assert "UNRESOLVED" in text and is_met(trigger_block(text)) is True


def test_an_unresolved_instability_flag_on_a_trigger_cell_blocks_the_trigger(world):
    """(c) V / X is 1.25 everywhere but X's decode at 131072 swings between the blocks and `--max-deciding 0` leaves the flag
    unresolved: not met."""
    w = world
    w.ops.metric = vx_metric(flag_x=(131072,))
    rc = w.main("run", "--max-deciding", "0")
    assert rc == 1 and len(w.ops.spawned_legs()) == 8
    text = w.matrix_text(partial=False)
    assert "UNRESOLVED" in text
    block = trigger_block(text)
    assert is_met(block) is False and names_rung(block, 131072), block


def test_a_resolved_flag_on_a_trigger_cell_does_not_block_the_trigger(world):
    """(c) Same swing, default cap: the deciding block b3 resolves the flag; the trigger is met."""
    w = world
    w.ops.metric = vx_metric(flag_x=(131072,))
    assert w.main("run") == 0
    legs = w.ops.spawned_legs()
    assert legs[8:] == [f"f45-{a.lower()}-b3.a1" for a in F45_ARMS]
    assert is_met(trigger_block(w.matrix_text(partial=False))) is True


def test_an_unresolved_flag_on_another_rung_does_not_block_the_trigger(world):
    """(c) "no unresolved instability flag on those cells": a flag at 8192 left unresolved does not touch the trigger."""
    w = world
    w.ops.metric = vx_metric(flag_x=(8192,))
    assert w.main("run", "--max-deciding", "0") == 1
    assert is_met(trigger_block(w.matrix_text(partial=False))) is True


def test_a_partial_f45_matrix_has_no_met_trigger(world):
    """(c) A refused arm (V: its preflight REFUSED) -> `.PARTIAL.md` in the f45 results dir, V / X cannot be computed: not met."""
    w = world
    w.ops.metric = vx_metric()
    K._atomic_json(w.cfg.preflight_record("V"), dict(arm="V", status="REFUSED", attempts=[], base=BASE))
    assert w.main("run") == 1
    path = w.results / f"MATRIX.{F45_PICK}.PARTIAL.md"
    assert path.is_file() and not (w.results / f"MATRIX.{F45_PICK}.md").exists()
    assert is_met(trigger_block(path.read_text())) is False
    assert not any(leg.startswith("f45-v-") for leg in w.ops.spawned_legs())
