"""P371 phase 4 (A13): the contract suite on REAL core runs, with a client that is not opencode.

`FakeClientHarness` drives `arm_runner.main` (the shared item core: gate, guard, grader, reconciliation, row, manifest)
with `ContractFakeArm` (a non-opencode adapter) and `tests/fake_contract_client.py` (a real process that makes real HTTP
requests to the scripted mock provider `opencode_v2_mock.MockServer` and prints the gate's event lines). The `ArmRun` a
check consumes is built from what that run left behind: the wire capture of the mock, the adapter's observed events /
reconciliation / tool windows, the row, the abort. Nothing is fabricated.

Every injected defect (`DEFECTS`) is a switch of ONE real run, never a hand-made summary:
  client   a behaviour of the fake client process (a wrong seed on request N, an extra tool, a retry after a 500 ...);
  adapter  a switch of `ContractFakeArm` (its stream drops events, its reconcile accepts what it must refuse ...);
  script   a mock-provider script entry.
`check_name` names the contract check that must turn red for it."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

from bench import arm_adapter as aa
from bench import arm_runner
from bench import rowschema
from bench import run_config as rc
from bench import token_turn_gate as tg
from bench.tests import arm_contract_suite as cs
from bench.tests.arm_neutral import NeutralArm, NeutralCorpus
from bench.tests.opencode_v2_mock import MockServer
from bench.tests.p371_world import args as core_args

CLIENT = Path(__file__).resolve().with_name("fake_contract_client.py")
MODEL = "neutral/model"
ITEM = "fake/one"
SEED_BASE = 77
SAMPLING = dict(temperature=0.6, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, enable_thinking=True,
                thinking_budget=81920, max_tokens=102400)
TOOLS = ("shell", "write", "read", "edit")
ROLES = {"system", "user", "assistant", "tool"}
SUMMARY_PREFIX = "You MUST summarize the conversation above"
DEFAULT_USAGE = dict(prompt_tokens=100, completion_tokens=10)


def tmpl():
    return rc.PolicyTemplate(config_id="contract-fake", langs=("fake",), inject_allowed=("stall", "loop"),
                             compaction="on_accounted")


def evidence():
    return rc.EvidencePolicy(namespace="neutral_evidence", web_evidence=True, final_tree=True, worker_receipts="absent",
                             item_barrier="off")


class ContractCorpus(NeutralCorpus):
    """The neutral one-file corpus plus inject addenda (the stall / loop positives are `--tg1-inject` runs)."""

    def inject_addendum_sha256(self, kind):
        return hashlib.sha256(("[inject:%s]" % kind).encode()).hexdigest()


# ---------------------------------------------------------------- the adapter under test
class FakeStream(tg.EventStream):
    """The gate's event stream plus the adapter's normalization (`NormalizedEvent`s, tool windows, compaction events)."""

    def __init__(self, gate, on_complete, adapter):
        super().__init__(gate, on_complete)
        self.adapter = adapter
        self.normalized = []
        self.windows = []
        self.terminal_shape = None
        self.finishes = 0

    def accept(self, e):
        kind = e.get("type") if isinstance(e, dict) else None
        flags = self.adapter.defects
        if kind == "compaction":
            info = e["info"]
            self.normalized.append(aa.NormalizedEvent.compaction(max(len(self.starts), 1),
                                                                 dict(reason=info["reason"], usage=info["usage"])))
            return
        if kind == "step_finish" and "stall_unseen" in flags:
            return                                          # requests never reach the gate
        if kind == "step_finish" and "hard_unseen" in flags:
            self.finishes += 1
            if self.finishes % 2 == 0:
                return                                      # every second request is invisible
        if kind == "tool_use" and "loop_unseen" in flags:
            return                                          # tool calls never reach the gate
        super().accept(e)
        part = e.get("part") or {}
        if kind == "step_start":
            self.normalized.append(aa.NormalizedEvent.request_start(len(self.starts)))
        elif kind == "tool_use":
            state = part["state"]
            self.normalized.append(aa.NormalizedEvent.tool(
                max(len(self.starts), 1), part["tool"], state["input"], state["status"],
                start=state["time"]["start"] / 1000.0, end=state["time"]["end"] / 1000.0))
            self.windows.append((state["time"]["start"] / 1000.0, state["time"]["end"] / 1000.0, part["tool"]))
        elif kind == "step_finish":
            t = part["tokens"]
            self.normalized.append(aa.NormalizedEvent.request_finish(len(self.gate.request_usage), aa.Usage(
                t["input"], t["cache"]["read"], t["cache"]["write"], t["output"], t["reasoning"])))


class ContractFakeArm(NeutralArm):
    """A conforming non-opencode adapter (the neutral adapter + a real client process + normalization), with named defect
    switches in `defects` (adapter-side injected defects)."""
    native_client_cuts = ("client_inactivity",)
    removed_tools = ("subagent", "execute", "question", "websearch")
    account_compaction = True
    # like opencode 2.0.20 (P378): the summary request carries the tool set
    receipt_class_rules = dict(task="required", compaction="required", auxiliary="forbidden")

    def __init__(self, p=None, *, defects=(), client=None, signals=None):
        super().__init__(p)
        self.defects = set(defects)
        self.client = dict(client or {})
        self.signals = signals
        self.binary_path = sys.executable

    def require_binary(self):
        return self.binary_path

    def identity(self, *, selection, universe_sha, version, binary, inject=None, inject_addendum_sha256=None):
        """The neutral identity with the inject kind's single lowered gate / hygiene constant (what a real adapter's
        identity states: `arm_runner.effective_policy`)."""
        ident = super().identity(selection=selection, universe_sha=universe_sha, version=version, binary=binary,
                                 inject=inject, inject_addendum_sha256=inject_addendum_sha256)
        ident["policy"]["gate"], ident["policy"]["hygiene"] = arm_runner.effective_policy(inject)
        return ident

    def command(self, binary, model, prompt):
        return [binary, str(CLIENT)]

    def build_env(self, run_dir, scratch, overlay, **kw):
        env = super().build_env(run_dir, scratch, overlay, **kw)
        tmp = Path(env["TMPDIR"])
        tmp.mkdir(parents=True, exist_ok=True)
        env["FAKE_CLIENT_CONFIG"] = json.dumps(self.client)
        env["FAKE_CLIENT_EXPORT"] = str(tmp / "export.json")
        if self.signals:
            env["FAKE_CLIENT_SIGNALS"] = str(self.signals)
        return env

    def new_stream(self, gate, on_complete):
        return FakeStream(gate, on_complete, self)

    def events(self, stream):
        out = list(stream.normalized)
        if stream.terminal_shape is not None and "no_terminal" not in self.defects:
            out.append(aa.NormalizedEvent.terminal(stream.terminal_shape))
        return out

    def tool_windows(self, stream, final=False):
        return [] if "window_missing" in self.defects else list(stream.windows)

    def transcript(self, guard, env, work, stream, binary, raw_sink=None):
        raw = Path(env["FAKE_CLIENT_EXPORT"]).read_text()
        if raw_sink is not None:
            raw_sink(raw)
        return aa.Transcript(raw=raw, doc=json.loads(raw))

    def final_boundary(self, transcript):
        return len([m for m in transcript.doc["messages"] if m.get("type") == "assistant" and not m.get("error")])

    def reconcile(self, stream, transcript, receipts, rc_, outcome):
        doc = transcript.doc
        try:
            summary = tg.reconcile(stream, doc, rc_, outcome)
            if "reject_cut" in self.defects and "client_inactivity" in stream.gate.flags:
                raise tg.TransportAbort("a registered native client cut was refused")
        except tg.TransportAbort:
            if "accepts_mystery" in self.defects:
                stream.terminal_shape = "stop"
                return aa.Reconciliation(outcome=None)
            raise
        derived = outcome or ("client_inactivity" if "client_inactivity" in stream.gate.flags else None)
        stream.terminal_shape = ("cancel" if derived == "runner_cancel" else "client_cut" if derived == "client_inactivity"
                                 else "length" if doc["messages"][-1].get("finish") == "length" else "stop")
        compaction = [dict(reason=c["reason"], usage=dict(c["usage"])) for c in doc.get("compaction", [])]
        return aa.Reconciliation(outcome=derived, unmatched_export_messages=summary["unmatched_export_messages"],
                                 trailing=summary["trailing"], uncharged_trailing=summary["uncharged_trailing"],
                                 compaction=compaction)

    def cancel(self, guard, wait, **kw):
        if "cancel_kills" in self.defects:
            guard.kill_role("client")                       # SIGKILL: the client never sees SIGTERM
            return [dict(pid=0, create_time=0.0, role="client", argv=[])]
        return super().cancel(guard, wait, **kw)


# ---------------------------------------------------------------- the injected defects
# name -> (kind, check function name, switch). `kind` client: a key of the fake client's `behaviour`; adapter: a switch of
# `ContractFakeArm.defects`; script: the mock-provider script (entry 1 of the run's script).
DEFECTS = {
    "wrong_seed": ("client", "check_wire_controls", dict(seed_at={"2": 1})),
    "tools_change": ("client", "check_wire_controls", dict(tools_change_at=2)),
    "developer_role": ("client", "check_wire_controls", dict(developer_role_at=2)),
    "extra_tool": ("client", "check_removed_tools_absent", dict(extra_tool=True)),
    "retry": ("client", "check_retries_off", dict(retry_on_500=True)),
    "scored_500": ("client", "check_retries_off", dict(swallow_500=True)),
    "compaction_uncounted": ("client", "check_compaction", dict(compaction_uncounted=True)),
    "compaction_tokens_wrong": ("client", "check_compaction", dict(compaction_tokens_wrong=True)),
    "no_compaction_event": ("client", "check_compaction", dict(no_compaction_event=True)),
    "compaction_wrong_seed": ("client", "check_compaction", dict(compaction_seed=1)),
    "compaction_wrong_budget": ("client", "check_compaction", dict(compaction_budget=1)),
    "compaction_no_tools": ("client", "check_compaction", dict(compaction_no_tools=True)),
    "compaction_bad_role": ("client", "check_compaction", dict(compaction_extra_role=True)),
    "accepts_mystery": ("adapter", "check_terminal_shapes", "accepts_mystery"),
    "cut_rejected": ("adapter", "check_terminal_shapes", "reject_cut"),
    "no_terminal": ("adapter", "check_event_normalization", "no_terminal"),
    "window_missing": ("adapter", "check_tool_windows", "window_missing"),
    "stall_unseen": ("adapter", "check_gate_positives", "stall_unseen"),
    "loop_unseen": ("adapter", "check_gate_positives", "loop_unseen"),
    "hard_unseen": ("adapter", "check_gate_positives", "hard_unseen"),
    "cancel_kills": ("adapter", "check_cancel_sigterm_first", "cancel_kills"),
}
# the 17 defects of the pre-P371 selftest (kept by name) and the ones added with the per-class compaction checks
LEGACY_DEFECTS = ("wrong_seed", "tools_change", "developer_role", "extra_tool", "retry", "scored_500",
                  "compaction_uncounted", "compaction_tokens_wrong", "no_compaction_event", "accepts_mystery",
                  "cut_rejected", "no_terminal", "window_missing", "stall_unseen", "loop_unseen", "hard_unseen",
                  "cancel_kills")


class FakeClientHarness(cs.ArmHarness):
    """The contract suite's harness over real core runs of the fake client. `world` is the p371 neutral world fixture."""
    timeout_configurable = False
    search_required = False
    reduced_window = 20000

    def __init__(self, world, defect=None, *, monkeypatch):
        self.world, self.mp, self.defect, self.n = world, monkeypatch, defect, 0
        kind, _, switch = DEFECTS[defect] if defect else (None, None, None)
        self.client_behaviour = dict(switch) if kind == "client" else {}
        self.adapter_defects = {switch} if kind == "adapter" else set()
        self.adapter = ContractFakeArm()
        self.adapter.defects = set(self.adapter_defects)
        self.expected = cs.ExpectedWire(sampling={**SAMPLING, "seed": rowschema.sample_seed(ITEM, 0, base=SEED_BASE)},
                                        roles=set(ROLES), required_tools=set(TOOLS))

    # -- one real run of the core with the fake client
    def _run_core(self, script, *, window=None, gate_overrides=None, inject=None, shape=None, cancel=False, extra=None):
        self.n += 1
        sub = Path(tempfile.mkdtemp(prefix=f"run{self.n}-", dir=self.world.tmp))
        self.mp.setenv("STACK_WORKDIR", str(sub))
        (sub / "m62/inject").mkdir(parents=True)
        out = (sub / "m62/inject" / "rows.jsonl") if inject else (sub / "rows.jsonl")
        signals = sub / "signals.txt"
        with MockServer(script) as mock:
            cfg = dict(base=mock.base, model=MODEL, sampling=SAMPLING, tools=list(TOOLS), window=window,
                       behaviour={**self.client_behaviour, **({"shape": shape} if shape else {}), **(extra or {})})
            if cancel:
                cfg["cancel_file"] = str(sub / "cancel")
            adapter = ContractFakeArm(self.world.host, defects=self.adapter_defects, client=cfg, signals=signals)
            adapter.arm_defect_names = set(self.adapter_defects)
            self.adapter = adapter
            a = core_args(sub, out=str(out), items="one", lang="fake", seed_base=SEED_BASE, limit=1 if inject else 5,
                          tg1_inject=inject, expect_items=ITEM if inject else None,
                          cancel_file=cfg.get("cancel_file"))
            a.gate_overrides = gate_overrides
            abort, status = None, 0
            try:
                status = arm_runner.main(self.world.host, adapter, a, template=tmpl(), evidence=evidence(),
                                         corpus=ContractCorpus(sub))
            except SystemExit as exc:
                abort = exc if exc.code not in (0, None) else None
            except BaseException as exc:  # noqa: BLE001 — an unexpected error is the run's abort, never a pass
                abort = exc
            row = json.loads(out.read_text().splitlines()[0]) if out.exists() and out.read_text().strip() else None
            manifest_path = Path(str(out.with_suffix("")) + ".manifest.json")
            manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
            usage = [self._usage_of(script, i) for i in range(1, len(mock.chats) + 1)]
            chats = mock.chats
        seen = adapter.observed or {}
        compaction_use = [u for c, u in zip(chats, usage) if self._is_compaction(c["body"])]
        task_use = [u for c, u in zip(chats, usage) if not self._is_compaction(c["body"])]
        signals_seen = signals.read_text().split() if signals.exists() else []
        cancelled = (manifest.get("cancelled_item") or None)
        return cs.ArmRun(
            requests=[cs.WireRequest(c["path"], c["headers"], c["body"]) for c in chats],
            events=seen.get("events", []), reconciliation=seen.get("reconciliation"), abort=abort, row=row,
            gate=(row or {}).get("gate", {}), flags=(row or {}).get("nonconv_flags", []),
            wire_compaction_usage=[self._tokens(u) for u in compaction_use], wire_usage=task_use,
            tool_windows=seen.get("tool_windows", []), cancelled_item=cancelled, client_signals=signals_seen)

    @staticmethod
    def _is_compaction(body):
        last = (body.get("messages") or [{}])[-1].get("content")
        return isinstance(last, str) and last.startswith(SUMMARY_PREFIX)

    @staticmethod
    def _usage_of(script, i):
        kind = script.get(i)
        return kind["usage"] if isinstance(kind, dict) and "usage" in kind else DEFAULT_USAGE

    @staticmethod
    def _tokens(u):
        return dict(input=u["prompt_tokens"], cache_read=0, cache_write=0, output=u["completion_tokens"], reasoning=0)

    def request_class(self, req):
        return "compaction" if self._is_compaction(req.body) else "task"

    # -- the ArmHarness contract
    def run(self, script, *, window=None, gate_overrides=None, inject=None):
        return self._run_core(script, window=window, gate_overrides=gate_overrides, inject=inject)

    def compaction_script(self):
        return {1: {"name": "write", "input": {"path": "solution.py", "content": "answer = 42\n"},
                    "usage": {"prompt_tokens": 19500, "completion_tokens": 10, "total_tokens": 19510}}}

    def shape(self, name):
        if name in ("stop", "length"):
            return self._run_core({}, shape=None if name == "stop" else "length")
        if name == "cancel":
            return self._run_core({}, shape="cancel", cancel=True)
        if name == "error":
            return self._run_core({}, shape="error")
        if name.startswith("client_cut:"):
            return self._run_core({}, shape="client_cut")
        return self._run_core({}, shape="unregistered")

    def cancel_run(self):
        """A real cancel: the runner's cooperative cancel mid-session; what the client process saw is its signal log."""
        return self._run_core({}, shape="cancel", cancel=True)
