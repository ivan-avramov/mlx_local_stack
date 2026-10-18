"""P371 phase 2a test helper: drive the shared core the way the two probe entries bind it (tg1 / m64-oc-tg1)."""
from __future__ import annotations

from bench import arm_opencode as ao
from bench import arm_runner
from bench import corpus_tg1
from bench import tg1_runner


def corpus_for(p, a):
    return corpus_tg1.Tg1Corpus(getattr(a, "universe", None) or arm_runner.DEFAULT_UNIVERSE,
                                polyglot_root=p._polyglot_root, polyglot_sha=p._polyglot_sha)


def m64_main(p, adapter, a, template=None, *, receipts_policy="absent", receipt_source=None, evidence=None):
    """`run_oc_probe` binding: the m64 template / evidence policy, the tg1 corpus. Tests may bind `required` worker
    receipts with a fake source (production stays `absent` until P372)."""
    if evidence is None:
        # the production policy has the item barrier ON (the chain answers it, P371 3b); a direct item run has no chain
        evidence = ao.m64_evidence(receipts=receipts_policy, item_barrier="off")
    return arm_runner.main(p, adapter, a, template=template or ao.m64_template(), evidence=evidence,
                           corpus=corpus_for(p, a), receipts=receipt_source)


def m64_print_identity(p, adapter, a, template=None):
    return arm_runner.print_identity(p, adapter, a, template=template or ao.m64_template(), corpus=corpus_for(p, a))


def tg1_main(p, adapter, a):
    return arm_runner.main(p, adapter, a, template=tg1_runner.TG1_POLICY, evidence=tg1_runner.TG1_EVIDENCE,
                           corpus=corpus_for(p, a))


def run_item_tg1(p, *, work, entry, **kwargs):
    """The pre-P371 `tg1_runner.run_item(p, work=, entry=, ...)` call shape over the shared core: tg1 adapter + corpus,
    the entry dict wrapped into a `PreparedItem`."""
    from pathlib import Path
    from bench import corpus as cp
    work = Path(work)
    lang = entry.get("lang", "python")
    solution = entry.get("solution", "solution.py")
    base = (work / solution).read_bytes() if (work / solution).is_file() else b""
    import hashlib
    prepared = cp.PreparedItem(
        item_id=entry.get("id") or f"{lang}/{work.name}", lang=lang,
        name=(entry.get("id") or f"{lang}/{work.name}").split("/", 1)[1], work=work, entry=dict(entry),
        editable=(solution,), baseline={solution: hashlib.sha256(base).hexdigest()}, protected=entry.get("protected", {}),
        prepared=entry.get("prepared", {}), tests=(entry.get("test", "t"),))
    corpus = corpus_tg1.Tg1Corpus(arm_runner.DEFAULT_UNIVERSE)
    from bench import structured_grade as sg
    kwargs.setdefault("join_timeout_s", arm_runner.grade_join_timeout_s(sg.TIMEOUTS))     # the entry passes the policy's
    return arm_runner.run_item(p, ao.OpencodeArm(p, mode="tg1"), corpus=corpus, prepared=prepared, **kwargs)
