"""Builders shared by the B2 s8 tests (`test_b2_s8_freeze.py`, `test_b2_s8_wave2.py`): a sealed arm-equality receipt per arm, and a
leg root the way the chain and the sequencer leave one (`chain.json`, `items/`, `receipt.json`, rows, `leg.json`). Hermetic: files
under the caller's `tmp_path` only."""
from __future__ import annotations

import json
from pathlib import Path

from bench import chain_rows as cr
from bench import p426_hooks as ph

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
DRAFTER = "caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter"
X40 = "a" * 40
Y40 = "b" * 40
X64 = "c" * 64


def receipt(arm, *, env_extra=None, drafter_revision="rev-d"):
    worker = ["<WT>/.venv/bin/python", "-m", "mlx_vlm.server", "--model", "<model>"]
    if arm == "on":
        worker += ["--draft-kind", "mtp", "--draft-model", DRAFTER, "--mtp-verify-scan", "joint_v1"]
    env = {"HOME": "$HOME", "STACK_WORKDIR": "$STACK_WORKDIR", "PWD": "<volatile>"}
    env.update(env_extra or {})
    doc = dict(argv=dict(router=["<WT>/.venv/bin/mlx-serve", "start"], worker=worker),
               env=dict(router=dict(env), worker=dict(env), probe=dict(env)),
               credential_keys=dict(router=[], worker=[], probe=[]),
               interpreters=[dict(path="<WT>/.venv/bin/python", inventory_sha256=X64, editables={})],
               loaded_images=[dict(path="<WT>/lib/libmlx.dylib", sha256=X64), dict(path="<WT>/lib/mlx.metallib", sha256=X64)],
               probe_entry="<WT>/benchmark/run_tg1_probe.py",
               snapshots=dict(target=dict(hf_path="t/t", revision="rev-t", files={"a": X64}),
                              drafter=dict(hf_path=DRAFTER, revision=drafter_revision, files={"b": X64}) if arm == "on" else None))
    return ph.seal(doc)


def request(arm, *, tokens=40, elapsed=50.0):
    r = dict(session="ses", backend="mlx", prompt_tokens=100, generated_tokens=tokens, decode_tok_s=30.0, error=None,
             draft_rounds=None, draft_n=None, draft_n_accepted=None, draft_kind=None, elapsed_s=elapsed)
    if arm == "on":
        r.update(draft_rounds=10, draft_n=30, draft_n_accepted=20, draft_kind="mtp")
    return r


def slot(arm, session, i, lang="python"):
    return f"e|{arm}|{MODEL}|{session}|{lang}|item{i}"


def write_leg_root(root, *, arm, leg, attempt=1, state="VALID", klass="valid", reason="", session="s1", items=5, dnf=0, rc=0,
                   status="finished", invalid=None, kill=False, walls=None, speed_valid=True, engagement_ok=True,
                   verdict="reconciled", with_receipt=True, with_leg=True, receipt_doc=None, lang="python", slots=None, elapsed=50.0, planned=None, schedule=True,
                   schedule_sha=None, frozen_record=None, inject=None):
    """A leg root as the chain leaves it. `walls` = the per-row `wall_s` values (default 100 + i); `slots` = explicit row slots."""
    root = Path(root)
    (root / "items").mkdir(parents=True)
    (root / session).mkdir(exist_ok=True)
    slots = list(slots) if slots else [slot(arm, session, i, lang) for i in range(items)]
    items = len(slots)
    walls = list(walls) if walls is not None else [100.0 + i for i in range(items)]
    ledger, rows = [], []
    for i in range(items):
        s = slots[i]
        ledger.append(dict(slot=s, kind="row", invocation=f"{session}/rows.jsonl", index=i))
        rows.append(dict(slot=s, wall_s=walls[i % len(walls)]))
        ready = dict(slot=s, item=s.rsplit("|", 1)[-1], k=i, log_cursor=dict(path="<WT>/logs/x", device=1, inode=2, offset=0),
                     worker_snapshot={}, owned=dict(router=dict(pid=1, start=1.0), worker=dict(pid=2, create_time=2.0)), at="t")
        sealed = ph.write_exclusive(root / "items" / (cr.slot_file(s) + ".ready.json"), ready)
        reqs = [request(arm, elapsed=elapsed)]
        if arm == "on" and not engagement_ok:
            reqs[0]["draft_rounds"] = None
        rec = dict(slot=s, ready_sha256=sealed["sha256"], log_range=dict(start=0, end=1, sha256=X64), worker_before={}, worker_after={},
                   case="kill_boundary" if kill and i == 0 else "completed", requests=reqs,
                   totals=dict(requests=1, prompt_tokens=100, generated_tokens=40, decode_s=1.0, accepted=0, proposed=0),
                   checks={}, verdict=verdict)
        ph.write_exclusive(root / "items" / (cr.slot_file(s) + ".json"), rec)
    dnf_recs = []
    for j in range(dnf):
        s = slot(arm, session, items + j, lang)
        dnf_recs.append(dict(slot=s, cause="timeout"))
        ready = dict(slot=s, item=s.rsplit("|", 1)[-1], k=items + j, log_cursor=dict(path="<WT>/logs/x", device=1, inode=2, offset=0),
                     worker_snapshot={}, owned=dict(router=dict(pid=1, start=1.0), worker=dict(pid=2, create_time=2.0)), at="t")
        sealed = ph.write_exclusive(root / "items" / (cr.slot_file(s) + ".ready.json"), ready)       # a DNF has its ready record too
        ph.write_exclusive(root / "items" / (cr.slot_file(s) + ".dnf.json"),
                           dict(slot=s, ready_sha256=sealed["sha256"], case="dnf_boundary", requests=[], verdict="reconciled"))
        ledger.append(dict(slot=s, kind="dnf", invocation=f"{session}/rows.jsonl", index=len(ledger)))
    with (root / session / "rows.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    invs = [dict(file=f"{session}/rows.jsonl", status="validated", leg_key=[0, lang, 0])]
    chain = dict(status=status, rc=rc, p426_ledger=ledger, p426_dnf=dnf_recs, p426_invalid=list(invalid or []),
                 progress=dict(invocations=invs))
    if frozen_record is not None:     # what the chain records of the frozen record it ran under (`frozen_record`, `inject`)
        chain.update(frozen_record=frozen_record, inject=inject)
    if schedule:                      # the chain's frozen schedule: `schedule.json` + its sha256 in chain.json (spec 7)
        from bench import schedules
        n = len(ledger) if planned is None else planned
        names = [f"item{i}" for i in range(n)]
        sched = dict(builder="tg1", blocks=[dict(session=session, legs=[dict(lang=lang, full_names=names, invocations=[
            dict(phase="full", names=names, limit=None, expect=[f"{lang}/{x}" for x in names])])])])
        (root / "schedule.json").write_text(json.dumps(sched))
        chain["schedule_sha256"] = schedule_sha or schedules.schedule_sha256(sched)
    (root / "chain.json").write_text(json.dumps(chain))
    if with_receipt:
        ph.write_exclusive(root / "receipt.json", receipt_doc or receipt(arm))
    if with_leg:
        ph.write_exclusive(root / "leg.json", dict(leg=leg, attempt=attempt, state=state, **{"class": klass}, reason=reason,
                                                   chain_rc=rc, started="s", ended="e", speed_valid=speed_valid,
                                                   speed_reason="ok" if speed_valid else "x"))
    return root
