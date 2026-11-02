"""P586–P593 frozen acceptance tests (SPEC v1, docs/specs/p586-relaunch-build.md): shared kit.

The kit is exposed as the `kit` fixture (this module itself), so the test modules never import `conftest` by name.
Everything is hermetic: files under `tmp_path` only, fakes for every process / network seam, the real leg-3 records from
`bench/tests/fixtures/p586/` for the data formats."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import chain_hooks as ch
from bench import chain_rows as cr
from bench import p426_hooks as ph
from bench import p426_reconcile as pr

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "p586"
MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
SESSION = "ses_e69d1f63bffe7ieF7PENCpeugn"
SLOT = f"tg1-p426|oc|{MODEL}|s1|go|crypto-square"
STREAM_CLOSED = "stream_closed_before_completion"
CAP_SOURCE = "opencode 2.0.20 LocationActivity timeToLive default (C154); not configurable"
DECODE_RATE_SOURCE = "completed requests (spec 8)"
ABORT_ERROR = {"type": "aborted", "message": "Step interrupted"}

# the five conditions (a)-(e) and the words of the spec each `client_abort_<x>` check name is matched by (the spec fixes the
# prefix, not the suffix: the suffixes are taken from the spec's own condition titles)
COND_WORDS = {"a": ("provenance",), "b": ("continuity",), "c": ("kill", "marker"), "d": ("accounting",),
              "e": ("ending", "exit", "normal")}


# ----------------------------------------------------------------------------------------------- the real leg-3 records
def row():
    return json.loads((FIX / "row.json").read_text())


def export_bytes():
    return (FIX / "export.json").read_bytes()


def export_doc():
    return json.loads(export_bytes())


def window_bytes():
    return (FIX / "window.log").read_bytes()


def item_record_baseline():
    return json.loads((FIX / "item_record_baseline.json").read_text())


def before():
    return copy.deepcopy(item_record_baseline()["worker_before"])


def after():
    return copy.deepcopy(item_record_baseline()["worker_after"])


def ready_record():
    return json.loads((FIX / "ready.json").read_text())


def leg3_tree():
    out = []
    for line in (FIX / "leg3_tree.tsv").read_text().splitlines():
        if line.strip():
            kind, rel = line.split("\t", 1)
            out.append((kind, rel))
    return out


def window_lines(data=None):
    return pr.parse_log(window_bytes() if data is None else data)


def last_assistant(doc):
    return [m for m in doc["messages"] if m.get("type") == "assistant"][-1]


def stamp_epoch_local_naive(stamp):
    """`YYYY-MM-DD HH:MM:SS,mmm` as a plain wall-clock number (no zone): only for differences of two stamps of one zone."""
    import calendar
    day, ms = stamp.split(",")
    return calendar.timegm(time.strptime(day, "%Y-%m-%d %H:%M:%S")) + int(ms) / 1000.0


def line_stamp(data, offset):
    end = data.index(b"\n", offset)
    return data[offset:end].decode()[:23]


# the fixture's local-stamp difference: last telemetry line (01:17:00,708) -> the trailing failed line (01:17:02,001). Since
# adopted finding X1 this is a premise about the log text only; no condition reads it.
FIXTURE_CLOSE_GAP_S = 1.293
# X1 (fix round 1): the close gap = the aborted message's export wall time (client UTC ms) - the last telemetry line's elapsed (the
# worker's monotonic clock): (1793524622068 - 1793520977003) / 1000 - 3643.5 = 3645.065 - 3643.5
FIXTURE_WALL_S = (1793524622068 - 1793520977003) / 1000
FIXTURE_CLOSE_GAP_X1_S = FIXTURE_WALL_S - 3643.5


def telemetry_line_indexes(data):
    """Indexes (in `data.split(b"\\n")`) of the `Stream Telemetry` lines."""
    return [i for i, ln in enumerate(data.split(b"\n")) if b"Stream Telemetry" in ln]


def window_keeping_telemetry(n, data=None):
    """The window with only its first `n` telemetry lines kept (the worker stopped streaming after the n-th line: a pause up to
    the client's abort). Request lines and worker counters are unchanged (telemetry lines are not counted)."""
    data = window_bytes() if data is None else data
    lines = data.split(b"\n")
    drop = set(telemetry_line_indexes(data)[n:])
    return b"\n".join(ln for i, ln in enumerate(lines) if i not in drop)


def x1_gap_after_keeping(n, data=None):
    """The X1 close gap of `window_keeping_telemetry(n)`: the export wall time minus the n-th line's elapsed."""
    return FIXTURE_WALL_S - telemetry(data)[n - 1].elapsed_s


def restamp(data, old_prefix, new_stamp):
    """Rewrite the leading local stamp of the one line that starts with `old_prefix` (bytes)."""
    assert data.count(old_prefix) == 1, old_prefix
    i = data.index(old_prefix)
    return data[:i] + new_stamp.encode() + data[i + 23:]


# ----------------------------------------------------------------------------------------------- the new interface
def telemetry(data=None):
    return pr.parse_telemetry(window_bytes() if data is None else data)


def client(*, export=None, sha_ok=True, lines=None, close_gap_s=FIXTURE_CLOSE_GAP_X1_S):
    """The `ClientEvidence` the done hook builds for the fixture item (each argument overridable)."""
    return pr.ClientEvidence(export=export_doc() if export is None else export, export_sha_ok=sha_ok,
                             telemetry=telemetry() if lines is None else lines, close_gap_s=close_gap_s)


def reconcile_fixture(*, r=None, log_lines=None, b=None, a=None, **client_kw):
    """The fixture item through `reconcile_item`. `log_lines` replaces the parsed `Request` lines; every other keyword goes to
    `client()` (`lines=` = the telemetry, `close_gap_s=`, `export=`, `sha_ok=`). Delivery 2c: the log-lines parameter was
    called `lines` and swallowed the telemetry override of the (b) / no-local-stamp tests."""
    return pr.reconcile_item(row() if r is None else r, window_lines() if log_lines is None else log_lines,
                             before() if b is None else b, after() if a is None else a, client=client(**client_kw))


def client_checks(report):
    return {k: v for k, v in (report.checks or {}).items() if k.startswith("client_abort_")}


def failing_client_checks(report):
    return sorted(k for k, v in client_checks(report).items() if not v["ok"])


def names_condition(names, cond):
    return any(any(w in n for w in COND_WORDS[cond]) for n in names)


# ----------------------------------------------------------------------------------------------- the completed variant
COMPLETED_LINE = (
    "2026-11-01 01:17:02,001 - mlx_vlm.server - INFO - Request completed: endpoint=/chat/completions "
    f"model=caslca/{MODEL} stream=True backend=cached_session session={SESSION} cached_tokens=3990 "
    "prompt_tokens=5366 generated_tokens=77510 elapsed=3645.000s prefill=1800.0 tok/s decode=21.3 tok/s "
    "finish_reason=length in_flight=0 sdpa_forced=32 sdpa_auto=1168")


def completed_variant_window():
    """The fixture window with its trailing `Request failed` line replaced by a `Request completed` line of the row's session
    at the same stamp (the server finished the request the client had already aborted)."""
    data = window_bytes()
    body = data.rstrip(b"\n")
    cut = body.rfind(b"\n") + 1
    assert b"Request failed" in body[cut:]
    return body[:cut] + COMPLETED_LINE.encode() + b"\n"


def completed_variant_after():
    """Worker counters moved by exactly the variant window, `last_request_at` = the aborted message's completion (exact
    match), no failed request recorded."""
    b, a = before(), after()
    a.update(requests_completed=b["requests_completed"] + 3, requests_failed=b["requests_failed"], requests_started=b["requests_started"] + 3,
             prompt_tokens_total=b["prompt_tokens_total"] + 2951 + 3991 + 5366,
             generated_tokens_total=b["generated_tokens_total"] + 125 + 71 + 77510,
             completion_tokens_total=b["completion_tokens_total"] + 125 + 71 + 77510, last_error=None,
             last_request_at=last_assistant(export_doc())["time"]["completed"] / 1000)
    return a


def reconcile_completed_variant(*, r=None, a=None, **client_kw):
    data = completed_variant_window()
    lines = pr.parse_log(data)
    kw = dict(lines=pr.parse_telemetry(data))
    kw.update(client_kw)
    return pr.reconcile_item(row() if r is None else r, lines, before(), completed_variant_after() if a is None else a,
                             client=client(**kw))


# ----------------------------------------------------------------------------------------------- the done hook (fake ops)
WORKER = dict(pid=23439, create_time=1793515319.955416)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class LogOps:
    """The `ChainOps` seams `P426Hooks` uses: a worker log file in `tmp`, settable `/metrics`, the owned identities."""

    def __init__(self, tmp):
        self.wd = Path(tmp) / "wd"
        self.wd.mkdir(parents=True, exist_ok=True)
        self.log = Path(tmp) / "wt" / "logs" / "mlx_vlm.log"
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_bytes(b"2026-11-01 01:00:00,000 - mlx_vlm.server - INFO - an earlier line\n")
        self.summary = before()
        self.worker = dict(WORKER)

    def server_log_path(self):
        return self.log

    def read_log(self, path, start, end=None):
        return Path(path).read_bytes()[start:end]

    def worker_metrics(self):
        return dict(summary=copy.deepcopy(self.summary))

    def worker_ident(self, model):
        return dict(self.worker)

    def create_time(self, pid):
        return 2.0

    def append(self, data):
        with open(self.log, "ab") as f:
            f.write(data)


def make_hooks(tmp_path, *, arm="OFF", inject=None):
    ops, clk = LogOps(tmp_path), Clock()
    out = Path(tmp_path) / "leg"
    out.mkdir()
    st = ph.log_stat(ops.log)
    (out / "log_bounds.json").write_text(json.dumps(dict(
        files=[dict(path=ph.portable_log(ops.log), device=st["device"], inode=st["inode"], offset_start=0, offset_end=None)],
        created="t", finalized=None)))
    hooks = ph.P426Hooks(ops=ops, out_root=out, arm=arm, settle_bound_s=10.0, clock=clk, sleep=clk.sleep, inject=inject)
    hooks.bind_router(5, 2.0)
    return ops, hooks, out


def ctx(r=None, *, slot=SLOT, item=None, k=0):
    item = item if item is not None else slot.rsplit("|", 1)[-1]
    return dict(stage="ready" if r is None else "done", slot=slot, item=item, k=k, ready={}, row=r,
                load=dict(idx=0, load_gen=0, worker=dict(WORKER), session="s1", model=MODEL, arm="oc"))


def item_record(out, slot=SLOT):
    return json.loads((Path(out) / "items" / f"{cr.slot_file(slot)}.json").read_text())


def run_fixture_item(tmp_path, *, r=None, window=None, export=None, a=None, transcript=None):
    """The leg-3 item through `P426Hooks.before_attempt` / `after_attempt`: ready at the log's end, the worker log grows by the
    fixture window, `/metrics` moves to the fixture's `worker_after`. -> (disposition, item record, ops)."""
    ops, hooks, out = make_hooks(tmp_path)
    assert hooks.before_attempt(SLOT, ctx()).kind == "accept"
    ops.append(window_bytes() if window is None else window)
    ops.summary = after() if a is None else a
    r = row() if r is None else r
    if transcript is None:
        ev = Path(tmp_path) / "ev"
        ev.mkdir(exist_ok=True)
        path = ev / "go__crypto-square.json"
        path.write_bytes(export_bytes() if export is None else export)
        transcript = str(path)
    r["transcript_path"] = transcript
    disp = hooks.after_attempt(SLOT, dict(id="go/crypto-square"), ctx(r))
    return disp, item_record(out), ops


# ----------------------------------------------------------------------------------------------- TZ
@pytest.fixture
def los_angeles(monkeypatch):
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


# ----------------------------------------------------------------------------------------------- the harvest world
# a copy of `test_b2_s9_harvest.World` (the leg root as chain / probe / sequencer leave it), so that this frozen directory
# does not depend on another suite's helpers
LEG, N = "tg1-p426-off-s1", 1
NAME = f"{LEG}.a{N}"
RUN_ID = "20261028T100000-abcdef012345"
STEM = f"{MODEL}.s1"
WAVE2 = "benchmark/results/p426/wave2"
FAKE_SECRET = "Zk3" + "x7Pq" * 9 + "W"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canon_sha(doc) -> str:
    body = {k: v for k, v in doc.items() if k != "sha256"}
    return sha(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def seal(doc):
    return dict(doc, sha256=canon_sha(doc))


def put(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return path


def pjson(path, doc):
    return put(path, json.dumps(doc, indent=1, sort_keys=True))


def scrub_for(tmp_path):
    from bench import p426_harvest as H
    return H.Scrub(workdir=Path(tmp_path) / "wd", repo=Path(tmp_path) / "main", home=Path(tmp_path) / "home", user="b2opuser",
                   hosts=("b2host",), emails=())


class World:
    def __init__(self, tmp_path):
        self.tmp = Path(tmp_path)
        self.wd = self.tmp / "wd"
        self.main, self.stage = self.tmp / "main", self.tmp / "stage"
        self.root = self.wd / "p426" / "wave2" / NAME
        self.run = self.wd / "opencode-probe-v2" / f"run-{RUN_ID}"
        self.ev = self.wd / "opencode_transcripts" / MODEL / f"{STEM}.{RUN_ID}"
        self.build()

    def p(self, path):
        return "$STACK_WORKDIR/" + Path(path).relative_to(self.wd).as_posix()

    def build(self):
        from bench import schedules
        r = self.root
        pjson(r / "leg.json", seal(dict(leg=LEG, attempt=N, state="VALID", **{"class": "valid"}, reason="", chain_rc=0,
                                        started="2026-10-28T10:00:00Z", ended="2026-10-28T11:00:00Z")))
        put(r / "RUNLOG.md", "chain: started\n")
        names = ["beer-song"]
        slots = [f"e|off|{MODEL}|s1|python|{n}" for n in names]
        ledger = [dict(slot=s, kind="row", invocation="s1/rows.jsonl", index=i) for i, s in enumerate(slots)]
        sched = dict(builder="tg1", blocks=[dict(session="s1", legs=[dict(lang="python", full_names=names, invocations=[
            dict(phase="full", names=names, limit=None, expect=[f"python/{n}" for n in names])])])])
        pjson(r / "schedule.json", sched)
        pjson(r / "chain.json", dict(status="finished", rc=0, schedule_sha256=schedules.schedule_sha256(sched), p426_ledger=ledger,
                                     p426_dnf=[], p426_invalid=[], argv=["chain", "s1", "--frozen-record",
                                                                         "$STACK_WORKDIR/p426/records/amendment.json"],
                                     progress=dict(invocations=[dict(file="s1/rows.jsonl", manifest="s1/rows.manifest.json",
                                                                     status="validated", leg_key=[0, "python", 0])])))
        pjson(r / "receipt.json", seal(dict(argv=dict(router=[], worker=[]), env={}, credential_keys={})))
        put(r / "watch.jsonl", json.dumps(dict(t=1)) + "\n" + json.dumps(dict(exit_state="driver_exited")) + "\n")
        rows = []
        for i, (s, n) in enumerate(zip(slots, names)):
            sf = s.replace("|", "__")
            ready = seal(dict(slot=s, item=f"python/{n}", k=i, log_cursor=dict(path="<WT>/logs/m", device=1, inode=2, offset=0),
                              worker_snapshot={}, at="t"))
            pjson(r / "items" / f"{sf}.ready.json", ready)
            pjson(r / "items" / f"{sf}.json", seal(dict(slot=s, ready_sha256=ready["sha256"], log_range=dict(start=0, end=1, sha256="0" * 64),
                                                        requests=[], verdict="reconciled", case="completed")))
            rows.append(self.row(n))
            base = r / "s1" / "rows"
            for kind in ("ready", "go", "done", "continue"):
                put(f"{base}.item{i}.{kind}", "{}")
        put(r / "s1" / "rows.jsonl", "".join(json.dumps(x) + "\n" for x in rows))
        pjson(r / "s1" / "rows.manifest.json", dict(run_id=RUN_ID, model=MODEL, worker={}))
        pjson(r / "log_bounds.json", dict(files=[], created="t", finalized="t"))

    def row(self, n):
        ev = self.ev
        files = {}
        for key, suffix in (("events", ".events.jsonl"), ("stderr", ".stderr.txt"), ("export", ".json"), ("datefreeze", ".datefreeze.jsonl")):
            files[key] = put(ev / f"python__{n}{suffix}", f"{key} of {n}\n")
        put(ev / f"python__{n}.web.jsonl", "{}\n")
        tree = ev / f"python__{n}.final_tree"
        code = b"answer = 42\n"
        put(tree / "objects" / sha(code), code)
        manifest = pjson(tree / "manifest.json", dict(files={"solution.py": sha(code)}, missing=[]))
        report = pjson(self.run / "grading-private" / "keep" / "seq-1" / "report.json", dict(outcome="pass"))
        pjson(self.run / "grading-private" / "keep" / "seq-1" / "index.json", dict(boundary=1, seq=1, final=True, outcome="pass",
                                                                                   artifacts=dict(report=dict(path="report.json", sha256=sha(report.read_bytes())))))
        put(self.run / "grading-private" / "keep" / "seq-1" / "change.diff", "--- a\n+++ b\n")
        put(self.run / "cfg" / "opencode" / "plugins" / "noretry.js", "// plugin\n")
        pjson(self.run / "cfg" / "opencode" / "opencode.json", {"provider": {}})
        put(self.run / "home" / ".config" / "state.db", b"\x00sqlite private state")
        return dict(id=f"python/{n}", slot_base="x", passed=True, events_path=self.p(files["events"]), stderr_path=self.p(files["stderr"]),
                    transcript_path=self.p(files["export"]), datefreeze_path=self.p(files["datefreeze"]),
                    evidence_sha256={k: sha(v.read_bytes()) for k, v in files.items()},
                    final_tree=dict(manifest=self.p(manifest), manifest_sha256=sha(manifest.read_bytes()), files={"solution.py": sha(code)}, missing=[]),
                    grade_reports=[dict(boundary=1, seq=1, final=True, outcome="pass",
                                        artifacts=dict(report=dict(path=self.p(report), sha256=sha(report.read_bytes()))))])

    def harvest(self, **kw):
        from bench import p426_harvest as H
        return H.harvest_wave2(self.root, main_root=self.main, evidence_stage=self.stage, scrub=scrub_for(self.tmp),
                               secrets=kw.pop("secrets", {}), worktree=None, workdir=self.wd, **kw)


def tree_snapshot(root):
    """{relative path: bytes} of every regular file below `root` (what a dry run must leave unchanged)."""
    root = Path(root)
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file() and not p.is_symlink()}


def harvest_box(tmp_path):
    home = Path(tmp_path) / "home"
    home.mkdir(exist_ok=True)
    return dict(environ=dict(STACK_WORKDIR=str(Path(tmp_path) / "wd"), HOME=str(home), XDG_CONFIG_HOME=str(home / ".config")),
                home=home)


# ----------------------------------------------------------------------------------------------- a bare chain (method level)
GOOD_CLEANUP = dict(survivors=[], containers_remaining=[], uncertain=False, orphans_unattributed=[], unknown=[], completed=True)


def bare_chain(tmp_path):
    from bench import chain_core as core
    from bench import run_config as rc
    c = core.Chain.__new__(core.Chain)
    c.config = SimpleNamespace(transport_policy="p426_continue", config_id=rc.P426_CONFIG_ID)
    c.builder, c.per_arm = "tg1", False
    c.a = SimpleNamespace(predictor="off")
    c.progress = dict(loads=[], invocations=[], slot_attempts=[], pre_spawn=[], txns=[], abort_evidence=[])
    c.incidents, c.dnf, c.realized, c.p426_dnf, c.p426_ledger, c.p426_invalid = [], [], [], [], [], []
    c.hooks = ch.ChainHooks()
    c.out_root = Path(tmp_path)
    c.saved, c.logged = [], []
    c.log = c.logged.append
    c.write_json = lambda status=None: c.saved.append(status)
    c.p426_router = dict(pid=1, start=5.0)
    c.ops = SimpleNamespace(worker_ident=lambda model: dict(WORKER), create_time=lambda pid: 5.0,
                            worker_metrics=lambda: {"summary": {"in_flight": 0}})
    c.listing = lambda *a, **k: None
    c.loads = []
    return c


# ----------------------------------------------------------------------------------------------- invariant cases
def _w12():
    """The fixture window's first two requests (lines 1–46: two complete `cached_session` requests of the row's session)."""
    return b"\n".join(window_bytes().split(b"\n")[:46]) + b"\n"


def _after_for(lines):
    a = before()
    c = [x for x in lines if x.kind == "completed"]
    a["requests_started"] += sum(1 for x in lines if x.kind == "started")
    a["requests_completed"] += len(c)
    a["requests_failed"] += sum(1 for x in lines if x.kind == "failed")
    a["prompt_tokens_total"] += sum(int(x.fields["prompt_tokens"]) for x in c)
    a["generated_tokens_total"] += sum(int(x.fields["generated_tokens"]) for x in c)
    return a


def _case_row(*, kind=None, at_kill=None, term=None, usage=None):
    r = row()
    r["nonconv_kind"] = kind
    r["nonconv_flags"] = [kind] if kind else []
    r["converged"] = kind is None
    r["stop_reason"] = "stop" if kind is None else kind
    r["gate"]["requests_completed_at_kill"] = at_kill
    r["termination"] = dict(r["termination"], **(term or {}))
    if usage is not None:
        r["request_usage"] = usage
    return r


def invariant_cases():
    """name -> (row, lines, before, after): rows WITHOUT `client_inactivity`, in the real worker-log format. Their baseline
    reports are `test_p586_golden_data.GOLDEN` (captured on a09a5a7e)."""
    w12 = pr.parse_log(_w12())
    full = pr.parse_log(window_bytes())
    unacc = pr.parse_log(completed_variant_window())
    kill = dict(reason="budget_hit", in_flight_at_kill=1, killed=[dict(pid=1)], killed_verified=True)
    return {
        "completed": (_case_row(), w12, before(), _after_for(w12)),
        "completed_token_mismatch": (_case_row(usage=[["m1", 125, 2951, 81920], ["m2", 72, 3991, 81920]]), w12, before(),
                                     _after_for(w12)),
        "completed_with_a_failed_line": (_case_row(), full, before(), after()),
        "budget_kill_boundary": (_case_row(kind="budget_hit_kill", at_kill=2, term=dict(reason="budget_hit")), w12, before(),
                                 _after_for(w12)),
        "budget_kill_boundary_count_mismatch": (_case_row(kind="budget_hit_kill", at_kill=3, term=dict(reason="budget_hit")), w12,
                                                before(), _after_for(w12)),
        "probe_kill_inflight_failed": (_case_row(kind="budget_hit_kill", at_kill=2, term=kill), full, before(), after()),
        "probe_kill_failed_without_inflight_evidence": (_case_row(kind="budget_hit_kill", at_kill=2, term=dict(reason="budget_hit")),
                                                        full, before(), after()),
        "probe_kill_completed_unaccounted": (_case_row(kind="stalled", at_kill=2, term=kill), unacc, before(),
                                             completed_variant_after()),
        "probe_kill_worker_delta_mismatch": (_case_row(kind="budget_hit_kill", at_kill=2, term=kill), full, before(),
                                             dict(after(), requests_failed=2)),
    }


def golden():
    import importlib.util
    spec = importlib.util.spec_from_file_location("p586_frozen_golden_data", Path(__file__).with_name("test_p586_golden_data.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.GOLDEN


@pytest.fixture
def kit():
    return sys.modules[__name__]


@pytest.fixture
def no_path_leak(monkeypatch):
    """`p426_leg.main` inserts the fork's dev directory into `sys.path`: undone after the test."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    return None
