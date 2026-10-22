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

    def stop_stack(self):
        self.calls.append("stop_stack")
        return 0

    def listeners(self, port=8000):
        return []


def _spec(tmp_path, arm="on", rows=None, planned=("a", "b")):
    rows_path = tmp_path / "rows.jsonl"
    spec = L.LegSpec(
        name=f"a1-{arm}-b1",
        arm=arm,
        kind="rows",
        model=ENTRY,
        registry_text=ON if arm == "on" else OFF,
        off_registry_text=OFF,
        driver_argv=["true"],
        destinations=[rows_path],
        rows_path=rows_path,
        planned=list(planned),
        receipt_dir=tmp_path / "receipts",
        server_log=tmp_path / "mlx_vlm.log",
        expected_requests=len(planned),
    )
    spec._test_rows = rows if rows is not None else [
        {"id": i, "draft": ENGAGED if arm == "on" else PLAIN, "completion_tokens": 5} for i in planned
    ]
    return spec


def _run(tmp_path, spec, ops, *, driver_rc=0, power_receipt=None, battery=()):
    spec.server_log.write_text("2026-10-21 23:00:00,000 - earlier leg - INFO - Request started: in_flight=1\n")

    def driver(argv, env, timeout):
        spec.rows_path.write_text("".join(json.dumps(r) + "\n" for r in spec._test_rows))
        with spec.server_log.open("a") as f:  # only this leg's slice (after the pre-leg offset) counts
            f.write("\n".join(_log(len(spec._test_rows))) + "\n")
        return driver_rc

    return L.run_leg(
        spec,
        ops,
        run_driver=driver,
        pins_check=lambda model, arm: [],
        watcher=lambda spec: (lambda: power_receipt),
        battery_intervals=lambda start, end: list(battery),
        clock=iter(["2026-10-22 01:00:00", "2026-10-22 02:00:00"]).__next__,
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
    spec = _spec(tmp_path, rows=[{"id": "a", "draft": ENGAGED, "completion_tokens": 5},
                                 {"id": "b", "draft": PLAIN, "completion_tokens": 5}])
    receipt = _run(tmp_path, spec, FakeOps())
    assert receipt["verdict"] == "INVALID"


def test_e1_a_leg_whose_log_slice_does_not_reconcile_is_invalid(tmp_path):
    spec = _spec(tmp_path)
    spec.expected_requests = 5
    assert _run(tmp_path, spec, FakeOps())["verdict"] == "INVALID"
