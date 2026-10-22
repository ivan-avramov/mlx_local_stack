"""P426 B10: the leg wrapper — every Wave-1 leg (and smoke) runs inside it (plan §2).

Pre-leg: destinations absent (no resume), the ON registry differs from OFF in exactly the entry's three MTP settings, the
target / drafter snapshots match the reviewed pins, power + orphan gate, nothing busy. Then the arm's lean router and the
worker argv checks (ChainOps), the driver, and the exit receipt: router / worker identity unchanged, power never failed
(watcher receipt + `pmset -g log`), planned membership == rows, the engagement gate (ON: every row engaged with sane
counters; OFF: none), `in_flight` = 1 on every ON `Request started` line. Any problem → INVALID; power → speed INVALID.
"""

import json
from pathlib import Path

import pytest

from bench import p426_leg as L

ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
OFF = f"""models:
  - name: Other
    hf_path: x/other
  - name: {ENTRY}
    hf_path: caslca/{ENTRY}
    # mtp_verify_scan: joint_v1  # C177 interim
    kv_bits: 0
    # draft_kind: mtp  # C177 interim
    # draft_model: caslca/{ENTRY}-mtp-drafter
"""
ON = (
    OFF.replace("    # mtp_verify_scan: joint_v1  # C177 interim", "    mtp_verify_scan: joint_v1")
    .replace("    # draft_kind: mtp  # C177 interim", "    draft_kind: mtp")
    .replace(f"    # draft_model: caslca/{ENTRY}-mtp-drafter", f"    draft_model: caslca/{ENTRY}-mtp-drafter")
)
ENGAGED = dict(draft_kind="mtp", draft_rounds=5, draft_n=10, draft_n_accepted=7)
PLAIN = dict.fromkeys(ENGAGED)


# ------------------------------------------------------------------ registry delta
def test_the_on_registry_differs_in_exactly_the_three_mtp_settings():
    assert L.registry_delta_problems(ON, OFF, ENTRY) == []


@pytest.mark.parametrize(
    "on, why",
    [
        (ON.replace("    mtp_verify_scan: joint_v1\n", ""), "mtp_verify_scan"),
        (ON.replace("    kv_bits: 0", "    kv_bits: 4"), "kv_bits"),
        (ON.replace("x/other", "x/changed"), "Other"),
        (OFF, "no MTP"),
    ],
)
def test_any_other_registry_delta_refuses(on, why):
    problems = L.registry_delta_problems(on, OFF, ENTRY)
    assert problems and any(why in p for p in problems), problems


@pytest.mark.parametrize(
    "on, why",
    [
        (ON.replace(f"draft_model: caslca/{ENTRY}-mtp-drafter", "draft_model: caslca/other-drafter"), "draft_model"),
        (ON.replace("    draft_kind: mtp", "    draft_kind: suffix"), "draft_kind"),
        (ON.replace("    kv_bits: 0", "    kv_bits: false"), "kv_bits"),  # type change: 0 == False in Python
        (ON.replace("    hf_path: x/other\n", ""), "Other"),
        (ON + "  - name: Other\n    hf_path: x/dupe\n", "duplicate"),
    ],
)
def test_h2_the_delta_check_is_strict_and_pins_the_on_values(on, why):
    problems = L.registry_delta_problems(on, OFF, ENTRY)
    assert problems and any(why in p for p in problems), problems


def test_h2_only_comment_lines_may_be_removed():
    on = ON.replace("    kv_bits: 0\n", "    # kv_bits: 0\n    kv_bits: 0\n")
    assert L.registry_delta_problems(on, OFF, ENTRY)  # an extra added line is not one of the three


# ------------------------------------------------------------------ freshness / membership / engagement
def test_an_existing_destination_refuses(tmp_path):
    (tmp_path / "math500.p426-off-b1.jsonl").write_text("{}\n")
    assert L.destination_problems([tmp_path / "math500.p426-off-b1.jsonl", tmp_path / "absent.jsonl"]) == [
        f"destination exists: {tmp_path / 'math500.p426-off-b1.jsonl'}"
    ]


def test_membership_must_equal_the_plan():
    assert L.membership_problems(["a", "b"], [{"id": "b"}, {"id": "a"}]) == []
    assert L.membership_problems(["a", "b"], [{"id": "a"}])
    assert L.membership_problems(["a"], [{"id": "a"}, {"id": "a"}])  # duplicate row
    assert L.membership_problems(["a"], [{"id": "a"}, {"id": "z"}])


@pytest.mark.parametrize(
    "arm, drafts, ok",
    [
        ("on", [ENGAGED, ENGAGED], True),
        ("on", [ENGAGED, PLAIN], False),  # a row that did not engage
        ("on", [ENGAGED, dict(ENGAGED, draft_rounds=0)], False),
        ("on", [ENGAGED, dict(ENGAGED, draft_n_accepted=11)], False),  # accepted > proposed
        ("on", [ENGAGED, dict(ENGAGED, draft_kind="suffix")], False),
        ("on", [ENGAGED, None], False),  # missing telemetry
        ("off", [PLAIN, PLAIN], True),
        ("off", [PLAIN, ENGAGED], False),
        ("off", [PLAIN, None], True),  # reasoning rows carry None under plain decode
    ],
)
def test_the_engagement_gate(arm, drafts, ok):
    rows = [{"id": str(i), "draft": d, "completion_tokens": 5} for i, d in enumerate(drafts)]
    assert (L.engagement_problems(arm, rows) == []) is ok


def test_vision_rows_gate_both_turns():
    rows = [{"id": "a", "draft": ENGAGED, "completion_tokens": 5, "turn2": {"draft": PLAIN, "completion_tokens": 1}}]
    assert L.engagement_problems("on", rows)  # turn 2 did not engage
    rows[0]["turn2"]["draft"] = ENGAGED
    assert L.engagement_problems("on", rows) == []


def test_reasoning_journal_rows_are_flattened(tmp_path):
    p = tmp_path / "reasoning.p426-on-b1.partial.jsonl"
    p.write_text(json.dumps({"key": "k", "record": {"rows": [{"seed": 1, "draft": ENGAGED}] * 2}}) + "\n")
    assert len(L.read_rows(p)) == 2


def _log(n, backend="cached_session", in_flight=1, failed=0, started=None, completed=None):
    ts = "2026-10-22 01:00:00,000 - mlx_vlm.server - INFO - "
    lines = [f"{ts}Request started: endpoint=/chat/completions model=m stream=True in_flight={in_flight}"
             for _ in range(n if started is None else started)]
    lines += [f"{ts}Request completed: endpoint=/chat/completions model=m stream=True backend={backend} session=s "
              f"cached_tokens=0 prompt_tokens=9 generated_tokens=5 elapsed=1.000s prefill=1.0 tok/s decode=1.0 tok/s "
              f"finish_reason=stop in_flight=0" for _ in range(n if completed is None else completed)]
    lines += [f"{ts}Request failed: endpoint=/chat/completions model=m stream=True error=x in_flight=0"] * failed
    return lines


def test_e1_a_reconciled_log_slice_is_clean():
    problems, stats = L.log_problems(_log(3), "on", expected=3)
    assert problems == [] and stats == {"started": 3, "completed": 3, "failed": 0, "overlapping": 0}


@pytest.mark.parametrize(
    "lines, why",
    [
        ([], "no server log records"),
        (_log(3, started=2), "started"),
        (_log(3, completed=2), "completed"),
        (_log(3, failed=1), "failed"),
        (_log(2), "expected 3"),
        (_log(3, backend="continuous_batching"), "cached_session"),
    ],
)
def test_e1_the_log_slice_fails_closed(lines, why):
    problems, _ = L.log_problems(lines, "on", expected=3)
    assert problems and any(why in p for p in problems), problems


def test_cached_session_requests_are_exact_under_http_overlap():
    """B1 D1: cached_session requests run serially on the model-owning daemon thread — an HTTP overlap is recorded, not
    invalidating; the OFF arm has no backend requirement."""
    problems, stats = L.log_problems(_log(3, in_flight=2), "on", expected=3)
    assert problems == [] and stats["overlapping"] == 3
    assert L.log_problems(_log(3, backend="continuous_batching"), "off", expected=3)[0] == []


# ------------------------------------------------------------------ the orchestration (ops injected)
class FakeOps:
    def __init__(self, *, power=True, busy=(), load_raises=None, router_ok=True, same_worker=True):
        self.calls = []
        self._power, self._busy = power, list(busy)
        self._load_raises, self._router_ok, self._same = load_raises, router_ok, same_worker

    def power_ok(self):
        self.calls.append("power_ok")
        return self._power

    def busy_procs(self):
        return list(self._busy)

    def start_state(self):
        return {"watts": 140, "volts": 28, "batt": 80, "busy": list(self._busy), "orphans_clean": True}

    def env_base(self):
        return {"MLX_SERVE_CONFIG": "arm.yaml"}

    def start_router(self):
        self.calls.append("start_router")
        return 101

    def load(self, model):
        self.calls.append(f"load {model}")
        if self._load_raises:
            raise self._load_raises
        return {"pid": 202, "create_time": 1.0, "cmdline": f"202 python -m mlx_vlm.server --model caslca/{ENTRY} --port 8091"}

    def worker_ident(self, model):
        return {"pid": 202, "create_time": 1.0 if self._same else 2.0}

    def router_ok(self):
        return self._router_ok

    router_config_sha = None  # set per test: the served file's sha at start (ChainOps records it)

    def stop_stack(self):
        self.calls.append("stop_stack")
        if getattr(self, "stop_raises", None):
            raise self.stop_raises
        return getattr(self, "stop_rc", 0)

    def listeners(self, port=8000):
        return []


PINS = dict(stack_head="s" * 40, stack_clean=True, mlx_vlm="v" * 40, mlx_serve="m" * 40)


def _row(i, arm, pt=None):
    return {"id": i, "draft": ENGAGED if arm == "on" else PLAIN, "completion_tokens": 5, "session_id": f"p426-t-{i}",
            "prompt_tokens": pt if pt is not None else 100 + ord(i[0]), "sampler_seed": 7, "sample": 0, "seed_base": 0}


def _spec(tmp_path, arm="on", rows=None, planned=("a", "b")):
    rows_path = tmp_path / "rows.jsonl"
    registry = ON if arm == "on" else OFF
    spec = L.LegSpec(
        name=f"a1-{arm}-b1",
        arm=arm,
        kind="rows",
        model=ENTRY,
        registry_text=registry,
        off_registry_text=OFF,
        driver_argv=["true"],
        destinations=[rows_path],
        rows_path=rows_path,
        planned=list(planned),
        receipt_dir=tmp_path / "receipts",
        server_log=tmp_path / "mlx_vlm.log",
        expected_requests=len(planned),
        seeds={i: {"sampler_seed": 7, "sample": 0, "seed_base": 0} for i in planned},
        pins=dict(PINS, registry_off_sha=L.sha256_text(OFF), registry_on_sha=L.sha256_text(ON)),
    )
    spec._test_rows = rows if rows is not None else [_row(i, arm) for i in planned]
    return spec


def _log_for(rows, extra=0):
    """The worker's started / completed lines for exactly these rows (+ ``extra`` drafter-free requests)."""
    ts = "2026-10-22 01:00:00,000 - mlx_vlm.server - INFO - "
    out = []
    recs = [(r.get("session_id"), r.get("prompt_tokens"), r.get("draft") or {}) for r in rows]
    recs += [(f"p426-t-extra{k}", 9, {}) for k in range(extra)]
    for sid, pt, d in recs:
        out.append(f"{ts}Request started: endpoint=/chat/completions model=m stream=True in_flight=1")
        draft = (f" draft_kind=mtp draft_n={d['draft_n']} draft_n_accepted={d['draft_n_accepted']} draft_rounds={d['draft_rounds']}"
                 if d.get("draft_n") is not None else "")
        out.append(f"{ts}Request completed: endpoint=/chat/completions model=m stream=True backend=cached_session session={sid} "
                   f"cached_tokens=0 prompt_tokens={pt} generated_tokens=5 elapsed=1.000s prefill=1.0 tok/s decode=1.0 tok/s "
                   f"finish_reason=stop in_flight=0{draft}")
    return out


def _run(tmp_path, spec, ops, *, driver_rc=0, power_receipt=None, battery=(), battery_problems=(), watch=None,
         driver_raises=None, state=None, log_lines=None, stop_watch_raises=None):
    watch = watch if watch is not None else dict(power_failure=power_receipt, exited_early=False, ticks=20)
    spec.server_log.write_text("2026-10-21 23:00:00,000 - earlier leg - INFO - Request started: in_flight=1\n")

    def driver(argv, env, timeout, cwd=None):
        if driver_raises:
            raise driver_raises
        spec.rows_path.write_text("".join(json.dumps(r) + "\n" for r in spec._test_rows))
        with spec.server_log.open("a") as f:  # only this leg's slice (after the pre-leg offset) counts
            f.write("\n".join(log_lines if log_lines is not None else _log_for(spec._test_rows, spec.expected_extra)) + "\n")
        return driver_rc

    def stop_watch():
        if stop_watch_raises:
            raise stop_watch_raises
        return watch

    if getattr(ops, "router_config_sha", None) is None:  # ChainOps records the served file's sha at start
        ops.router_config_sha = L.sha256_text(spec.registry_text)
    return L.run_leg(
        spec,
        ops,
        run_driver=driver,
        pins_check=lambda model, arm: [],
        watcher=lambda spec: stop_watch,
        battery_intervals=lambda start, end: (list(battery), list(battery_problems)),
        clock=iter(["2026-10-22 01:00:00", "2026-10-22 02:00:00"]).__next__,
        repo_state=lambda: dict(state if state is not None else PINS),
    )


def test_a_clean_leg_is_valid_and_receipted(tmp_path):
    ops = FakeOps()
    spec = _spec(tmp_path)
    receipt = _run(tmp_path, spec, ops)
    assert receipt["verdict"] == "VALID" and receipt["speed_valid"] is True, receipt
    assert ops.calls[:3] == ["power_ok", "start_router", f"load {ENTRY}"] and ops.calls[-1] == "stop_stack"
    on_disk = json.loads((spec.receipt_dir / f"{spec.name}.receipt.json").read_text())
    assert on_disk["verdict"] == "VALID"


def test_a_failed_pre_check_never_starts_the_router(tmp_path):
    ops = FakeOps(power=False)
    receipt = _run(tmp_path, _spec(tmp_path), ops)
    assert receipt["verdict"] == "NOT_STARTED" and "start_router" not in ops.calls


def test_a_busy_box_never_starts_the_router(tmp_path):
    ops = FakeOps(busy=["123 opencode run"])
    assert _run(tmp_path, _spec(tmp_path), ops)["verdict"] == "NOT_STARTED"


def test_a_worker_argv_tripwire_is_invalid_and_tears_down(tmp_path):
    from bench.chain_ops import ChainAbort

    ops = FakeOps(load_raises=ChainAbort("TRIPWIRE: worker lacks the mtp predictor"))
    receipt = _run(tmp_path, _spec(tmp_path), ops)
    assert receipt["verdict"] == "INVALID" and "stop_stack" in ops.calls
    assert any("lacks the mtp predictor" in p for p in receipt["problems"])


@pytest.mark.parametrize(
    "kw, field",
    [
        (dict(driver_rc=1), "driver exit 1"),
        (dict(power_receipt={"first_failure_at": "01:30:00"}), "power"),
        (dict(battery=[("01:10:00", "01:12:00")]), "battery"),
    ],
)
def test_driver_failure_is_invalid_and_power_only_invalidates_speed(tmp_path, kw, field):
    receipt = _run(tmp_path, _spec(tmp_path), FakeOps(), **kw)
    if field == "driver exit 1":
        assert receipt["verdict"] == "INVALID" and any(field in p for p in receipt["problems"])
    else:
        assert receipt["verdict"] == "VALID" and receipt["speed_valid"] is False
        assert any(field in p for p in receipt["speed_problems"])


@pytest.mark.parametrize("kw", [dict(same_worker=False), dict(router_ok=False)])
def test_a_changed_worker_or_router_is_invalid(tmp_path, kw):
    assert _run(tmp_path, _spec(tmp_path), FakeOps(**kw))["verdict"] == "INVALID"


def test_an_unengaged_on_row_is_invalid(tmp_path):
    spec = _spec(tmp_path, rows=[_row("a", "on"), dict(_row("b", "on"), draft=PLAIN)])
    receipt = _run(tmp_path, spec, FakeOps())
    assert receipt["verdict"] == "INVALID"


def test_e1_a_leg_whose_log_slice_does_not_reconcile_is_invalid(tmp_path):
    spec = _spec(tmp_path)
    spec.expected_requests = 5
    assert _run(tmp_path, spec, FakeOps())["verdict"] == "INVALID"


# ------------------------------------------------------------------ B1 code round 3 G1–G3 (the leg wrapper)
def test_g1_a_driver_timeout_is_an_invalid_receipted_leg(tmp_path):
    import subprocess

    spec = _spec(tmp_path)
    receipt = _run(tmp_path, spec, FakeOps(), driver_raises=subprocess.TimeoutExpired(["d"], 21600))
    assert receipt["verdict"] == "INVALID" and any("timed out" in p for p in receipt["problems"])
    assert (spec.receipt_dir / f"{spec.name}.receipt.json").exists()


@pytest.mark.parametrize("how", ["rc", "raises"])
def test_g2_a_failed_teardown_is_invalid(tmp_path, how):
    ops = FakeOps()
    if how == "rc":
        ops.stop_rc = 1
    else:
        ops.stop_raises = RuntimeError(":8000 still bound")
    receipt = _run(tmp_path, _spec(tmp_path), ops)
    assert receipt["verdict"] == "INVALID" and any("teardown" in p for p in receipt["problems"])


@pytest.mark.parametrize(
    "watch, why",
    [
        (dict(power_failure=None, exited_early=True, ticks=20), "exited early"),
        (dict(power_failure=None, exited_early=False, ticks=3), "ticks"),
        ({}, "no watcher report"),
    ],
)
def test_g3_an_unhealthy_watcher_invalidates_speed(tmp_path, watch, why):
    """The clock spans one hour (12 five-minute ticks): fewer than 11 ticks, an early exit or no report → speed INVALID
    (a crashed watcher must never read as 'no power failure')."""
    receipt = _run(tmp_path, _spec(tmp_path), FakeOps(), watch=watch)
    assert receipt["verdict"] == "VALID" and receipt["speed_valid"] is False
    assert any(why in p for p in receipt["speed_problems"]), receipt["speed_problems"]


# ------------------------------------------------------------------ stack code round 1 K1 K2 K4 K5 K6
@pytest.mark.parametrize("exc", [OSError("rows unreadable"), ValueError("bad json")])
def test_k1_any_driver_exception_is_receipted_and_torn_down(tmp_path, exc):
    ops = FakeOps()
    spec = _spec(tmp_path)
    receipt = _run(tmp_path, spec, ops, driver_raises=exc)
    assert receipt["verdict"] == "INVALID" and "stop_stack" in ops.calls
    assert (spec.receipt_dir / f"{spec.name}.receipt.json").exists()


def test_k1_an_interrupt_is_receipted_then_re_raised(tmp_path):
    ops = FakeOps()
    spec = _spec(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, spec, ops, driver_raises=KeyboardInterrupt())
    doc = json.loads((spec.receipt_dir / f"{spec.name}.receipt.json").read_text())
    assert doc["verdict"] == "INVALID" and "stop_stack" in ops.calls


def test_k1_a_failing_watcher_stop_still_tears_down(tmp_path):
    ops = FakeOps()
    receipt = _run(tmp_path, _spec(tmp_path), ops, stop_watch_raises=RuntimeError("watcher gone"))
    assert receipt["verdict"] == "INVALID" and "stop_stack" in ops.calls


@pytest.mark.parametrize(
    "state, why",
    [
        (dict(PINS, stack_head="x" * 40), "stack_head"),
        (dict(PINS, stack_clean=False), "stack_clean"),
        (dict(PINS, mlx_vlm="w" * 40), "mlx_vlm"),
        (dict(PINS, mlx_serve="n" * 40), "mlx_serve"),
    ],
)
def test_k2_the_frozen_build_is_pinned_before_anything_starts(tmp_path, state, why):
    ops = FakeOps()
    receipt = _run(tmp_path, _spec(tmp_path), ops, state=state)
    assert receipt["verdict"] == "NOT_STARTED" and "start_router" not in ops.calls
    assert any(why in p for p in receipt["problems"]), receipt["problems"]


def test_k2_the_registry_texts_are_pinned(tmp_path):
    spec = _spec(tmp_path)
    spec.pins["registry_on_sha"] = "0" * 64
    receipt = _run(tmp_path, spec, FakeOps())
    assert receipt["verdict"] == "NOT_STARTED" and any("registry_on_sha" in p for p in receipt["problems"])


def test_k4_a_row_with_unplanned_seeds_is_invalid(tmp_path):
    spec = _spec(tmp_path, rows=[_row("a", "on"), dict(_row("b", "on"), sampler_seed=8)])
    receipt = _run(tmp_path, spec, FakeOps())
    assert receipt["verdict"] == "INVALID" and any("seeds" in p for p in receipt["problems"])


def test_k5_a_substituted_log_record_is_caught_even_when_counts_match(tmp_path):
    spec = _spec(tmp_path)
    rows = spec._test_rows
    lines = _log_for([rows[0], dict(rows[1], session_id="p426-t-foreign")])  # same count and counters, foreign identity
    receipt = _run(tmp_path, spec, FakeOps(), log_lines=lines)
    assert receipt["verdict"] == "INVALID" and any("no log record" in p for p in receipt["problems"])


def test_k5_round2_a_record_matching_by_identity_must_match_its_counters(tmp_path):
    spec = _spec(tmp_path)
    rows = spec._test_rows
    lines = _log_for([rows[0], dict(rows[1], prompt_tokens=999)])
    receipt = _run(tmp_path, spec, FakeOps(), log_lines=lines)
    assert receipt["verdict"] == "INVALID" and any("differs" in p for p in receipt["problems"])


def test_k5_round2_a_row_without_a_session_id_is_invalid(tmp_path):
    spec = _spec(tmp_path, rows=[_row("a", "on"), dict(_row("b", "on"), session_id=None)])
    receipt = _run(tmp_path, spec, FakeOps())
    assert receipt["verdict"] == "INVALID" and any("session id" in p for p in receipt["problems"])


def test_k5_the_planned_extra_requests_are_allowed_exactly(tmp_path):
    spec = _spec(tmp_path)
    spec.expected_extra, spec.expected_requests = 1, 3
    assert _run(tmp_path, spec, FakeOps())["verdict"] == "VALID"
    (tmp_path / "b").mkdir()
    spec2 = _spec(tmp_path / "b")
    spec2.expected_extra, spec2.expected_requests = 1, 3
    lines = _log_for(spec2._test_rows, extra=2)
    assert _run(tmp_path / "b", spec2, FakeOps(), log_lines=lines)["verdict"] == "INVALID"


def test_k6_an_unreadable_power_history_invalidates_speed(tmp_path):
    receipt = _run(tmp_path, _spec(tmp_path), FakeOps(), battery_problems=["pmset -g log: no power-source events"])
    assert receipt["verdict"] == "VALID" and receipt["speed_valid"] is False
    assert any("pmset" in p for p in receipt["speed_problems"])


# ------------------------------------------------------------------ stack code round 2 K1 K2 K6 L1 (the leg wrapper)
def test_k1_round2_an_interrupt_during_the_pre_check_is_receipted_then_re_raised(tmp_path):
    ops = FakeOps()
    spec = _spec(tmp_path)

    def boom():
        raise KeyboardInterrupt()

    ops.busy_procs = boom
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, spec, ops)
    assert json.loads((spec.receipt_dir / f"{spec.name}.receipt.json").read_text())["verdict"] == "NOT_STARTED"


def test_l1_an_existing_receipt_is_never_overwritten(tmp_path):
    spec = _spec(tmp_path)
    spec.receipt_dir.mkdir(parents=True)
    original = spec.receipt_dir / f"{spec.name}.receipt.json"
    original.write_text('{"verdict": "VALID"}')
    receipt = _run(tmp_path, spec, FakeOps())
    assert receipt["verdict"] == "NOT_STARTED" and any("receipt exists" in p for p in receipt["problems"])
    assert json.loads(original.read_text()) == {"verdict": "VALID"}
    assert len(list(spec.receipt_dir.glob(f"{spec.name}.refused-*.receipt.json"))) == 1


def test_k2_round2_the_served_config_is_the_pinned_one(tmp_path):
    ops = FakeOps()
    ops.router_config_sha = "f" * 64  # the router started on some other file
    receipt = _run(tmp_path, _spec(tmp_path), ops)
    assert receipt["verdict"] == "INVALID" and any("served config" in p for p in receipt["problems"])


def test_k2_round2_the_receipt_records_the_resolved_build(tmp_path):
    receipt = _run(tmp_path, _spec(tmp_path), FakeOps())
    assert receipt["state"] == PINS and receipt["pins"]["registry_on_sha"] == L.sha256_text(ON)


@pytest.mark.parametrize(
    "text, ok",
    [
        ("2026-10-22 01:00:00 -0700 Assertions  Summary- [System: x] Using AC(Charge: 80)\n", True),
        ("", False),
        ("garbage Using AC here\n", False),
        ("2026-10-22 01:00:00 -0700 Assertions  Using AC(Charge: 80)\nnot a date Using Batt\n", False),
    ],
)
def test_k6_round2_the_power_history_grammar_is_strict(text, ok):
    assert (L.power_history_problems(0, text) == []) is ok
    assert L.power_history_problems(1, text)  # a failed read is never clean
