"""Scenario schema for the A14 baseline (stdlib only; copied into the bundle, used by the new side later).

ONE scenario file drives BOTH sides. It is pure data; the two sides interpret it with their own fakes:
  * OLD side (`driver.py`, inside the bundle): `tg_fixture` + the fake opencode shell binary (ITEM) or
    `FakeOps` + `chains/c147/fake_probe.py` (CHAIN).
  * NEW side (phase 2/3, `runner.run_new_side`): the current tree's equivalent fakes, same fields.

ITEM scenario fields
  name, kind="item", doc
  frozen_date        the `--frozen-prompt-date` (default "Mon Jan 05 2026")
  stream             null = the fixture default (1 finished request 10 out / 100 in, then an open one), or
                     {requests: [{output, input, calls: [{shell input}]}], open_request: bool, raw: [event dict] | null}
                     `raw` replaces the generated events (e.g. an inactivity or provider error event)
  export             null = derived from `stream`, or {"patch_last": {fields merged into the last export message}}
  client             {rc: int (0), linger_s: number (0: client lingers after its events, killed by the gate or a
                     cancel), writes_solution: bool (true), edits_protected_test: bool (false),
                     export_rc: int (0), export_stdout: null | text}
  gate_policy        {name: value} overrides of `token_turn_gate.POLICY` for this scenario (the injected-positive idiom
                     of C147, without the inject label); e.g. {"no_progress_requests": 4}
  grade              "real" (default) | "transport_abort" (the grader raises TransportAbort on the final grade)
  runs               [{items: "one", extra: [argv], cancel: null | "client_started" | "final_grade",
                       before: ["identity_change"]}]   (sequential invocations sharing out / manifest)
CHAIN scenario fields
  name, kind="chain", doc, argv (chain CLI args, e.g. ["chain","s1","--probe-code-sha", <64 hex>]),
  plan (FAKE_PROBE_PLAN list | null), behaviour (FAKE_PROBE_BEHAVIOUR | null), extra_env, timers (overrides),
  metrics (null | {"summary": {"in_flight": n}}), manifest_override (dotted overrides JSON | null),
  helper (null | {"stop_after_log": "<substring>", "delay_s": number}), shapes ["a"|"b"|"c"|"d"...], expect_rc
RESULT (normalized): ITEM {scenario, kind, runs: [{outcome, rows, manifest, client_calls, evidence}]};
CHAIN {scenario, kind, rc, shapes, chain_json, files: {relpath: {kind, rows|doc|sha}}, invocations, ops_calls,
step_manifests, milestones}."""
from __future__ import annotations

import json
from pathlib import Path

ITEM_KEYS = {"name", "kind", "doc", "frozen_date", "stream", "export", "client", "gate_policy", "grade", "runs"}
CHAIN_KEYS = {"name", "kind", "doc", "argv", "plan", "behaviour", "extra_env", "timers", "metrics",
              "manifest_override", "helper", "shapes", "expect_rc"}
CLIENT_DEFAULT = {"rc": 0, "linger_s": 0, "writes_solution": True, "edits_protected_test": False, "export_rc": 0,
                  "export_stdout": None}
CANCELS = (None, "client_started", "final_grade")


class ScenarioError(ValueError):
    pass


def load(path):
    return validate(json.loads(Path(path).read_text()))


def validate(s):
    if not isinstance(s, dict) or s.get("kind") not in ("item", "chain"):
        raise ScenarioError("scenario needs kind item|chain")
    allowed = ITEM_KEYS if s["kind"] == "item" else CHAIN_KEYS
    extra = set(s) - allowed
    if extra:
        raise ScenarioError("unknown scenario keys: %s" % sorted(extra))
    for key in ("name", "doc"):
        if not isinstance(s.get(key), str) or not s[key]:
            raise ScenarioError("scenario needs a non-empty %s" % key)
    if s["kind"] == "item":
        if not s.get("runs"):
            raise ScenarioError("item scenario needs runs")
        for run in s["runs"]:
            if run.get("cancel") not in CANCELS:
                raise ScenarioError("unknown cancel trigger %r" % run.get("cancel"))
            if not run.get("items"):
                raise ScenarioError("every run needs items")
        if s.get("grade", "real") not in ("real", "transport_abort"):
            raise ScenarioError("unknown grade mode")
        bad = set(s.get("client") or {}) - set(CLIENT_DEFAULT)
        if bad:
            raise ScenarioError("unknown client keys: %s" % sorted(bad))
    else:
        if not s.get("argv") or s["argv"][0] not in ("pilot", "chain"):
            raise ScenarioError("chain scenario needs argv starting with pilot|chain")
        if "expect_rc" not in s:
            raise ScenarioError("chain scenario needs expect_rc")
    return s


def client_of(s):
    return {**CLIENT_DEFAULT, **(s.get("client") or {})}
