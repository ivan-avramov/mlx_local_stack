"""P426 B2 frozen tests, delivery 1d: the A4 window (spec v3.2 §4.3, §16.5 `a4_window_problems(lines, a4_receipt, a4_gate)`).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour.
The window is in the gate's order (session_pinning_gate.py:288-293: A4 opencode's `ses_*` session, then A6's three `anon:*`
requests); the `ses_*` requests equal the A4 receipt (`a4_v2_latest.json`), the `anon:*` ones the A4 run's `gate.json`."""
from __future__ import annotations

import pytest

from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_support as S

SES = "ses_a4000000000000000000000000"
REQS = [(SES, 0, 9000), (SES, 8800, 9100), (SES, 0, 9300), (SES, 9200, 9400)]
ANON = [("anon:0001", 0, 3100), ("anon:0002", 0, 3101), ("anon:0003", 2600, 3102)]


def R4():
    from bench import p426_reconcile
    return p426_reconcile


def window(reqs=REQS, anon=ANON):
    lines = []
    for j, (s, c, p) in enumerate(list(reqs) + list(anon)):
        lines += [S.started_line(at=S.ts(2 * j)),
                  S.completed_line(at=S.ts(2 * j + 1), session=s, prompt_tokens=p, generated_tokens=30, cached_tokens=c)]
    return R4().parse_log(S.window(lines))


def gate(anon=ANON):
    return A.a4_gate_doc(S.a4_receipt(REQS), anon)


def test_new_a_window_equal_to_its_receipt_and_gate_json_has_no_problem():
    assert R4().a4_window_problems(window(), S.a4_receipt(REQS), gate()) == []


@pytest.mark.parametrize("anon", [
    ANON[:2],                                                         # one bare request missing
    [ANON[0], ANON[1], ("anon:0003", 2600, 3199)],                    # a prompt count differs from gate.json
    [ANON[0], ANON[1], ("anon:9999", 2600, 3102)],                    # another anonymous session
    [ANON[0], ANON[1], ("ses_x000000000000000000000000", 2600, 3102)],  # not anonymous at all
])
def test_fix_bare_requests_that_differ_from_gate_json_are_a_problem(anon):
    assert R4().a4_window_problems(window(anon=anon), S.a4_receipt(REQS), gate())


def test_fix_a_gate_json_that_lists_other_bare_requests_is_a_problem():
    other = [(s, c, p + 1) for s, c, p in ANON]
    assert R4().a4_window_problems(window(), S.a4_receipt(REQS), gate(other))


def test_fix_the_session_requests_still_equal_the_receipt():
    reqs = list(REQS)
    reqs[2] = (SES, 0, 9301)
    assert R4().a4_window_problems(window(reqs=reqs), S.a4_receipt(REQS), gate())
