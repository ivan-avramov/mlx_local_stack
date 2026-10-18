"""P371 phase 2b, plan 4 A3: join additions the core needs — a request group whose count the transcript cannot state
(`repeat`: opencode's compaction summary is retried once on a template miss and its tokens are one export message),
the per-class roles control and the max_tokens upper bound (the client clamps max_tokens to the remaining window)."""
from __future__ import annotations

import pytest

from bench import worker_receipts as wr

WORKER = dict(pid=4242, create_time=1760000000.25)
CTX = wr.AttemptContext.make("python|foo", 1)


def play(admits):
    fake = wr.FakeReceiptSource(WORKER)
    mark = fake.start(CTX)
    for kw in admits:
        fake.admit(**kw)
    fence = fake.fence(CTX)
    return mark, fence, wr.owned_receipts(mark, fence)


def join(admits, requests, **kw):
    mark, fence, owned = play(admits)
    return wr.join(owned, requests, supports_header=False, ctx=CTX, mark=mark, fence=fence, **kw)


def classes(result):
    return [r["cls"] for r, _ in result.pairs]


# ---------------------------------------------------------------- repeat groups
def test_a_compaction_group_may_take_one_or_two_tool_less_receipts():
    requests = [dict(cls="task"), dict(cls="compaction", repeat=(1, 2)), dict(cls="task")]
    one = join([dict(cls="task"), dict(cls="compaction"), dict(cls="task")], requests)
    two = join([dict(cls="task"), dict(cls="compaction"), dict(cls="compaction"), dict(cls="task")], requests)
    assert [r["seq"] for _, r in one.pairs] == [1, 2, 3] and [r["seq"] for _, r in two.pairs] == [1, 2, 3, 4]
    assert two.by_class["compaction"]["requests"] == 2 and two.task_tokens["requests"] == 4


def test_a_failed_compaction_is_exactly_two_requests():
    requests = [dict(cls="task"), dict(cls="compaction", repeat=(2, 2))]
    assert join([dict(cls="task"), dict(cls="compaction"), dict(cls="compaction")], requests).by_class["compaction"][
        "requests"] == 2
    with pytest.raises(wr.ReceiptMissing):
        join([dict(cls="task"), dict(cls="compaction")], requests)
    with pytest.raises(wr.ReceiptUnmatched):
        join([dict(cls="task"), dict(cls="compaction"), dict(cls="compaction"), dict(cls="compaction")], requests)


def test_a_group_never_takes_a_receipt_that_carries_tools():
    requests = [dict(cls="compaction", repeat=(1, 2)), dict(cls="task")]
    result = join([dict(cls="compaction"), dict(cls="task")], requests)         # the task receipt stays the task's
    assert classes(result) == ["compaction", "task"]


def test_a_group_leaves_a_receipt_for_every_later_request():
    requests = [dict(cls="compaction", repeat=(1, 3)), dict(cls="auxiliary")]
    result = join([dict(cls="compaction"), dict(cls="compaction"), dict(cls="auxiliary")], requests)
    assert classes(result) == ["compaction", "compaction", "auxiliary"]


def test_a_repeat_must_be_a_valid_range():
    for bad in ((0, 1), (2, 1), (1,), "x", (1, 2, 3), (1.5, 2)):
        with pytest.raises(wr.ReceiptAbort, match="repeat"):
            join([dict(cls="task")], [dict(cls="task", repeat=bad)])


def test_requests_without_repeat_keep_the_strict_count_rules():
    with pytest.raises(wr.ReceiptMissing):
        join([dict(cls="task")], [dict(cls="task"), dict(cls="task")])
    with pytest.raises(wr.ReceiptUnmatched):
        join([dict(cls="task")] * 2, [dict(cls="task")])


# ---------------------------------------------------------------- controls: roles and the max_tokens bound
def test_roles_must_be_a_nonempty_subset_of_the_classs_allowed_roles():
    controls = {"task": dict(roles=["system", "user", "assistant", "tool"])}
    assert join([dict(cls="task")], [dict(cls="task")], controls=controls)          # ["system", "user"]
    mark, fence, owned = play([dict(cls="task")])
    for roles in (["system", "developer"], []):
        bad = [dict(owned[0], roles=roles)]
        with pytest.raises(wr.ReceiptControlsMismatch, match="roles"):
            wr.join(bad, [dict(cls="task")], supports_header=False, ctx=CTX, mark=mark, fence=fence, controls=controls)


def test_a_class_without_a_roles_control_is_not_role_checked():
    mark, fence, owned = play([dict(cls="task")])
    odd = [dict(owned[0], roles=["anything"])]
    assert wr.join(odd, [dict(cls="task")], supports_header=False, ctx=CTX, mark=mark, fence=fence, controls={"task": {}})


def test_max_tokens_is_bounded_not_pinned():
    controls = {"task": dict(max_tokens_max=102400)}
    assert join([dict(cls="task", max_tokens=90000)], [dict(cls="task")], controls=controls)
    assert join([dict(cls="task", max_tokens=102400)], [dict(cls="task")], controls=controls)
    with pytest.raises(wr.ReceiptControlsMismatch, match="max_tokens"):
        join([dict(cls="task", max_tokens=102401)], [dict(cls="task")], controls=controls)
