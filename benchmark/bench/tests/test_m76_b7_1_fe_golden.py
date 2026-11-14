"""M76 B7.1 acceptance criterion 3 — B7's existing report keys and numbers unchanged outside the new keys / section, and
`axis_plan` unchanged (spec `docs/specs/m76-b7-1-joint-plan.md`: "byte-identical outside the new keys / section").

Goldens are sha256 digests of the BASELINE (accepted B7, spec v1.4) artefacts, computed before B7.1 existed:
- the committed `benchmark/results/m76/b7-simulation/report.json` (canonical JSON) minus the keys `joint` / `variants`;
- the committed `REPORT.md` minus the generated "Joint plan" section (heading text contains "joint plan");
- `m76_rule.axis_plan` for every axis / option the repository uses;
- `m76_sim.build_report(reps=150, a5_ns=[72])` minus `joint` / `variants` and the interpreter / numpy version fields
  (the code path, not only the committed file: an additive section must not perturb B7's random streams or caches).
All class (a) (the specification states them); every test is green on the baseline.
"""
import hashlib
import inspect
import re

from bench.tests.test_m76_b7_1_fe_support import NEW_KEYS, canon, committed_report, COMMITTED

GOLDEN_REPORT_JSON = "0d676775e88fe9631377575a0f73dcd9a543a384dc09e23ef46e9c4789961649"
GOLDEN_REPORT_MD = "1a8d82506a051f53097e5fda9b9cf7ac1f755d36a1aeb8a8636c9d8a1c3cd1ef"
GOLDEN_AXIS_PLANS = "dde7193a79f0f75069025de2b7ea150936d737a39b4e209848661735fa4dcc8f"
GOLDEN_BUILD_150 = "0ed965ec4760a60ae5bcadef0082402462623450ca4a5e97695acbb19488a2ab"


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _strip_new(rep):
    return {k: v for k, v in rep.items() if k not in NEW_KEYS}


def test_committed_report_json_outside_new_keys_is_baseline():  # (a)
    rep = committed_report()
    assert set(rep) - set(NEW_KEYS) == {"axes", "data", "header"}
    assert _sha(canon(_strip_new(rep))) == GOLDEN_REPORT_JSON


def test_committed_report_json_only_adds_joint_and_variants():  # (a)
    """The committed report may gain `joint` and `variants` (and nothing else at the top level, none inside `axes` /
    `header` / `data`)."""
    rep = committed_report()
    assert set(rep) <= {"axes", "data", "header", *NEW_KEYS}
    assert set(rep["axes"]) == {"A1", "A5", "A7", "A8"}
    assert "joint" not in rep["axes"] and "variants" not in rep["axes"]


def test_committed_report_md_outside_joint_section_is_baseline():  # (a)
    text = (COMMITTED / "REPORT.md").read_text()
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines) if re.match(r"#{1,6}\s.*joint plan", ln, re.I)), None)
    if start is not None:
        end = next((j for j in range(start + 1, len(lines)) if re.match(r"#{1,2}\s", lines[j])), len(lines))
        lines = lines[:start] + lines[end:]
    norm = re.sub(r"\n{3,}", "\n\n", "\n".join(lines).rstrip("\n") + "\n")
    assert _sha(norm) == GOLDEN_REPORT_MD


def test_axis_plan_unchanged():  # (a)
    from bench import m76_rule as R
    plans = {
        "A1": R.axis_plan("A1"), "A1s": R.axis_plan("A1", keep_look1=False),
        "A5n": R.axis_plan("A5", n=72, calibrated=False), "A7": R.axis_plan("A7"), "A8": R.axis_plan("A8"),
        "A7u": R.axis_plan("A7", calibrated=False), "A8u": R.axis_plan("A8", calibrated=False),
    }
    # AMENDED (delivery 5, spec v1.4 / C339): the DEFAULT `axis_plan("A5")` is now the registered A5-2L plan (two looks, n 72
    # at α 0.003808 and n 120 at 0.021192), so it is no longer in the pinned set; B7's single-look A5 plan (explicit n)
    # stays pinned as "A5n", and every other plan is unchanged. The golden was recomputed on the candidate without the
    # default A5 entry and with `report_sha256` removed. The registered A5 plan is tested in test_m76_b7_1_fe_fix_v14.py.
    # AMENDED (delivery 2): `report_sha256` is the hash of the committed report file, which changes whenever the report
    # gains keys (the specification's own `joint` / `variants`); every other plan field must be unchanged. The golden
    # below was recomputed on the candidate with `report_sha256` removed (m76_rule.py is untouched by the candidate diff,
    # and the committed report minus the new keys is pinned by the tests above, so the plans' inputs are the baseline's).
    for p in plans.values():
        p.pop("report_sha256", None)
    assert _sha(canon(plans)) == GOLDEN_AXIS_PLANS
    # readable restatement of the committed plans (a variant's looks are NOT registered in this build)
    assert [len(p["looks"]) for p in (plans["A1"], plans["A5n"], plans["A7"], plans["A8"])] == [2, 1, 1, 1]
    assert plans["A5n"]["items"] == 72 and plans["A7"]["looks"][0]["alpha"] == 0.001
    assert plans["A8"]["looks"][0]["alpha"] == 0.001


def test_axis_plan_signature_and_axes_unchanged():  # (a)
    from bench import m76_rule as R
    sig = inspect.signature(R.axis_plan)
    assert list(sig.parameters) == ["axis", "keep_look1", "n", "calibrated", "report"]
    assert set(R._AXES) == {"A1", "A7", "A5", "A8"}
    for bad in ("A7-2L", "A5-2L", "A7_2L", "A5_2L"):
        try:
            R.axis_plan(bad)
        except ValueError:
            continue
        raise AssertionError(f"axis_plan({bad!r}) must stay unregistered until the operator picks a variant")


def test_build_report_reduced_reps_outside_new_keys_is_baseline():  # (a)
    from bench import m76_sim as M
    rep = M.build_report(reps=150, a5_ns=[72])
    assert set(rep) - set(NEW_KEYS) == {"axes", "data", "header"}
    rep = _strip_new(rep)
    rep["header"] = {k: v for k, v in rep["header"].items() if k not in ("python", "numpy")}
    assert _sha(canon(rep)) == GOLDEN_BUILD_150
