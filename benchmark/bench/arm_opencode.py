"""opencode wrapped as the first M64 ArmAdapter (spec 5, 5.1; C165 2b / 2c / 2d).

Two configurations of one class:

  mode="tg1"  the existing tg1 path, unchanged: the tg1 carrier byte for byte, the tg1 label, compaction OFF, only the
              `primary` receipt kind. Every method either delegates to the function tg1 uses or reproduces its few lines;
              the parity tests (`test_m64_arm_oc_adapter.py`, `test_m64_arm_oc_parity.py`) pin that equality.
  mode="m64"  the M64 arm, label `opencode-v2-web-tg1c`: the tg1 carrier with exactly the enumerated differences
              (`M64_CARRIER_CHANGES`): compaction ON (the exposed context stays 262,144) and the shared SearXNG MCP server
              (D2). Everything else the spec keeps from tg1 is kept (subagent / execute / question / websearch denied,
              webfetch allowed with its deny patterns, retries OFF through the noretry plugin, toolbounds, datefreeze).
              Compaction requests are visible only in the session export (opencode 2.0.20 emits no event for them), so
              they are accounted from it (their tokens count to the task) and from the datefreeze receipts.

Nothing here edits a file in the tg1 generation closure: the tg1 modules are used as a library. The M64 arm refuses to
run (`ArmRefused`) while the D2 search service is the stub (`UnavailableSearchService`)."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from . import arm_adapter as aa
from . import m64_search
from . import datefreeze, identity_closure as ic, opencode_export as ox, provenance
from . import proc_guard as pg
from . import structured_grade as sg
from . import tg1_runner as t1
from . import token_turn_gate as tg
from . import toolchain
from .arm_adapter import Transcript, Usage  # noqa: F401  (re-exported for callers and tests)

REPO = Path(__file__).resolve().parents[2]
TG1_LABEL = t1.SCAFFOLD
M64_LABEL = "opencode-v2-web-tg1c"
REMOVED_TOOLS = ("subagent", "execute", "question", "websearch")
# Spec 5.1, the whole of it: the M64 carrier = the tg1 carrier + these, nothing else. (key, tg1 value, M64 value)
M64_CARRIER_CHANGES = (("compaction.auto", False, True), ("mcp.searxng", None, "shared search service"))
SNAPSHOT_OWED = ("dependency_tree", "bottle_sha256", "tool_schemas")        # build step 6 (snapshot / adoption tooling)
PLUGINS = ("noretry.js", "toolbounds.js", "datefreeze.js")
TRANSPORT_CAUSES = ("server_error", "connection", "dropped_stream", "timeout")


class TransportFailure(tg.TransportAbort):
    """A serving fault observed through the client's own error event (spec 8.3): an incident, retried by the chain,
    never a score. `cause` is the coarse class the client's error shape maps to; the chain adds worker identity."""

    def __init__(self, cause, message):
        super().__init__(message)
        self.cause = cause


def classify_error(error):
    """Coarse transport cause of one client error event, or None (not a registered transport shape)."""
    if not isinstance(error, dict):
        return None
    kind, status, message = error.get("type"), error.get("status"), error.get("message")
    if kind == "provider.transport":
        return "connection"
    if kind == "provider.invalid-output":
        return "dropped_stream"
    if isinstance(kind, str) and "timeout" in kind:
        return "timeout"
    if kind == "provider.internal" or (type(status) is int and status >= 500):
        return "server_error"
    shape = tg.own_abort_shape(error)
    if shape == "fetch":
        return "dropped_stream"
    if shape == "unable":
        return "connection"
    return None


class OfflineTestSearchService(aa.SearchService):
    """TESTS ONLY: the M64 configuration without a search service (no `mcp` block), for contract runs that must not
    depend on D2. Never usable by a real run: the arm records `search_is_offline_test` in its manifest."""
    available = True
    offline_test = True

    def require(self):
        return self

    def mcp_entry(self, client):
        return None


def m64_carrier_doc(base, entry):
    """The M64 carrier document: `base` (the tg1 carrier) with exactly `M64_CARRIER_CHANGES` applied. Refuses a base
    that is not the tg1 carrier shape (so a changed base can never smuggle an unenumerated difference in)."""
    doc = copy.deepcopy(base)
    if doc.get("compaction") != {"auto": False}:
        raise aa.ArmContractError("the tg1 carrier must have exactly compaction {auto: false} to derive the M64 carrier")
    if "mcp" in doc:
        raise aa.ArmContractError("the tg1 carrier already has an mcp block")
    if dict(action="websearch", resource="*", effect="deny") not in doc.get("permissions", []):
        raise aa.ArmContractError("hosted websearch must already be denied in the tg1 carrier (C165 2d)")
    doc["compaction"] = {"auto": True}
    if entry is not None:
        doc["mcp"] = {"searxng": entry}
    return doc


class OcStream(tg.EventStream):
    """The tg1 event stream (the gate sees exactly what it sees today) plus the spec 5 normalized event list."""

    def __init__(self, gate, on_complete=None):
        super().__init__(gate, on_complete)
        self.normalized = []
        self.tool_windows = []
        self.compaction_events = []        # (after_request, info), filled at reconcile from the session export
        self.late_finishes = {}            # request_seq -> Usage of a request the live events never closed (reconcile)
        self.terminal_shape = None

    def accept(self, e):
        super().accept(e)
        kind = e.get("type")
        part = e.get("part") or {}
        if kind == "step_start":
            self.normalized.append(aa.NormalizedEvent.request_start(len(self.starts)))
        elif kind == "tool_use":
            state = part["state"]
            start, end = state["time"]["start"] / 1000.0, state["time"]["end"] / 1000.0
            self.normalized.append(aa.NormalizedEvent.tool(len(self.starts), part["tool"], state["input"],
                                                           state["status"], start=start, end=end))
            self.tool_windows.append((start, end, part["tool"]))
        elif kind == "step_finish":
            t = part["tokens"]
            self.normalized.append(aa.NormalizedEvent.request_finish(len(self.starts), Usage(
                input=t["input"], cache_read=t["cache"]["read"], cache_write=t["cache"]["write"],
                output=t["output"], reasoning=t["reasoning"])))
        elif kind == "error":
            self.normalized.append(aa.NormalizedEvent.error(e["error"]))


class OpencodeArm(aa.ArmAdapter):
    arm_id = "oc"
    tool = "opencode"
    label = M64_LABEL
    GENERATION_FIELDS = t1.GENERATION_FIELDS
    native_client_cuts = ("client_inactivity",)
    removed_tools = REMOVED_TOOLS

    pinned_version = "2.0.20"

    def __init__(self, p=None, *, mode="m64", search=None):
        if mode not in ("tg1", "m64"):
            raise aa.ArmContractError(f"unknown opencode arm mode {mode!r}")
        self.p, self.mode = p, mode
        self.search = search if search is not None else m64_search.service()
        self.m64 = mode == "m64"
        self.label = M64_LABEL if self.m64 else TG1_LABEL
        self.receipt_kinds = ("primary", "compaction") if self.m64 else ("primary",)
        self.account_compaction = self.m64
        self.watchdog_enabled = self.m64
        self._pinned = {}

    @property
    def search_is_offline_test(self):
        return bool(getattr(self.search, "offline_test", False))

    @property
    def generation_data(self):
        """Non-Python inputs of the generation identity: the tg1 set (plugins, the tg1 carrier = the base the M64
        carrier derives from); the M64 transform itself is Python and is in the import closure."""
        return t1.GENERATION_DATA

    # ---------------------------------------------------------------- identity / provenance
    def selection(self, system_file=None):
        p = self.p
        if not self.m64:
            return p._carrier_selection(self.label, system_file, source=t1.CARRIER)
        if self.search_is_offline_test:
            entry = None
        else:
            entry = self.search.mcp_entry("opencode")
            if not isinstance(entry, dict) or not entry:
                raise aa.ArmRefused("the shared search service gave no client-native MCP entry for opencode (C165 2d)")
        base_bytes = t1.CARRIER.read_bytes()
        doc = m64_carrier_doc(json.loads(base_bytes), entry)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "opencode_bench_v2_web_tg1c.json"
            source.write_bytes(json.dumps(doc, sort_keys=True, indent=2).encode())
            sel = p._carrier_selection(self.label, system_file, source=source)
        sel["source"] = t1.CARRIER
        sel["fields"] = {**sel["fields"],
                         "carrier_source": (t1.CARRIER.relative_to(REPO).as_posix() if t1.CARRIER.is_relative_to(REPO)
                                            else p._portable(t1.CARRIER)),
                         "carrier_source_sha256": hashlib.sha256(base_bytes).hexdigest(),
                         "carrier_transform": "opencode-v2-web-tg1c",
                         "carrier_changes": json.dumps([list(c) for c in M64_CARRIER_CHANGES])}
        return sel

    def snapshot(self):
        p = self.p
        binary = Path(p._require_opencode_bin())
        sel = self.selection()
        fields = dict(
            label=self.label, version=p.PINNED_OPENCODE_VERSION_V2, exe_sha256=p._sha_of(binary),
            plugins={name: p._sha_of(REPO / "benchmark/opencode_plugins" / name) for name in sorted(PLUGINS)},
            carrier_sha256=sel["fields"]["opencode_bench_config_sha256"],
            carrier_source_sha256=sel["fields"]["carrier_source_sha256"],
            env_policy=p.SCAFFOLD_ENV_POLICY_V2, receipt_kinds=list(self.receipt_kinds),
            compaction="on" if self.m64 else "off", removed_tools=list(self.removed_tools),
            search_service="shared-searxng-mcp" if self.m64 and not self.search_is_offline_test else None)
        return aa.Snapshot(tool=self.tool, fields=fields, complete=False, missing=SNAPSHOT_OWED)

    def identity(self, *, selection, universe_sha, version, binary, inject=None):
        """`tg1_runner.identity` with this arm's label, plus (M64 only) the arm's own policy keys. In tg1 mode the result
        equals `tg1_runner.identity` for the same inputs."""
        p = self.p
        gate, hygiene = t1.effective_policy(inject)
        label = (self.label + "-inject:" + inject) if inject else self.label
        policy = dict(
            gate=gate, hygiene=hygiene,
            toolbounds_sha256=p._sha_of(t1.PLUGIN), noretry_sha256=p._sha_of(p.NORETRY_PLUGIN),
            datefreeze_sha256=p._sha_of(t1.DATEFREEZE_PLUGIN),
            carrier_sha256=selection["fields"]["opencode_bench_config_sha256"],
            universe_sha256=universe_sha, grader_version=sg.VERSION, grader_timeout_s=sg.TIMEOUTS,
            grade_join_timeout_s=t1.grade_join_timeout_s(),
            plugin_proof="GET /api/integration awaits Plugin.awaitActivation",
            env=p.SCAFFOLD_ENV_POLICY_V2, scaffold=label)
        policy["toolchain"] = toolchain.current()
        if self.m64:
            from . import arm_watchdog
            policy["arm"] = dict(arm=self.arm_id, compaction="on", receipt_kinds=list(self.receipt_kinds),
                                 removed_tools=list(self.removed_tools),
                                 search_service="shared-searxng-mcp" if not self.search_is_offline_test else None,
                                 watchdog=dict(limit_s=arm_watchdog.LIMIT_S, grace_s=arm_watchdog.GRACE_S))
        if inject:
            policy["inject"] = dict(kind=inject, prompt_addendum_sha256=t1.inject_addendum_sha256(inject))
        entry = Path(p.__file__).resolve().relative_to(REPO.resolve()).as_posix()
        result = dict(
            scaffold=label, policy=policy,
            scaffold_policy_sha256=hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest(),
            probe_code_sha256=ic.closure_sha256(entry, REPO, data=self.generation_data),
            opencode_version=version, opencode_exe_sha256=p._sha_of(binary))
        if inject:
            result["inject"] = dict(kind=inject, policy=dict(gate=gate, hygiene=hygiene),
                                    prompt_addendum_sha256=t1.inject_addendum_sha256(inject))
        return result

    def manifest_fields(self):
        return dict(arm=self.arm_id, tool=self.tool, label=self.label,
                    compaction="on" if self.m64 else "off",
                    search_service=("shared-searxng-mcp" if self.m64 and not self.search_is_offline_test else None),
                    search_is_offline_test=self.search_is_offline_test,
                    receipt_kinds=list(self.receipt_kinds), watchdog=self.watchdog_enabled)

    def row_fields(self, *, version, rc, artifacts, sha_of, portable):
        """The opencode-named row fields tg1 writes, from one finished item."""
        return dict(
            opencode_version=version, opencode_rc=rc,
            events_path=portable(artifacts["events"]), datefreeze_path=portable(artifacts["datefreeze"]),
            transcript_path=portable(artifacts["export"]),
            evidence_sha256={k: sha_of(v) for k, v in artifacts.items()},
            stderr_path=portable(artifacts["stderr"]))

    # ---------------------------------------------------------------- run construction
    def declared_model(self, selection, model):
        carrier = json.loads(selection["bytes"])
        datefreeze.refuse_websocket(carrier)             # P364: the hooks are transport-neutral; WebSocket is untested
        declared = carrier["providers"]["mlx-local"]["models"].get(model)
        if declared is None:
            raise tg.TransportAbort("model absent from tg1 carrier")
        return declared, carrier["providers"]["mlx-local"]["settings"]["baseURL"]

    def require_binary(self):
        return self.p._require_opencode_bin()

    def preflight(self, *, path, router, limit, model, exe_sha, carrier_sha):
        """A4-equivalent: the session-pinning receipt for THIS carrier (the receipt records the carrier sha)."""
        return self.p._a4_receipt(path, router, limit, model, exe_sha, carrier_sha)

    def make_run_dir(self, workdir, run_id, selection):
        p = self.p
        run_dir = p._make_run_dir(workdir, run_id, selection)
        shutil.copyfile(t1.PLUGIN, run_dir / "cfg/opencode/plugins/toolbounds.js")
        shutil.copyfile(t1.DATEFREEZE_PLUGIN, run_dir / "cfg/opencode/plugins/datefreeze.js")
        self._pinned = dict(noretry=p._sha_of(p.NORETRY_PLUGIN), toolbounds=p._sha_of(t1.PLUGIN),
                            datefreeze=p._sha_of(t1.DATEFREEZE_PLUGIN),
                            carrier_source=selection["fields"]["carrier_source_sha256"],
                            system=selection["fields"].get("agent_system_sha256"),
                            source_path=selection["source"], system_path=selection["system_path"])
        return run_dir

    def build_env(self, run_dir, scratch, overlay, *, receipts, frozen_date):
        return self.p._opencode_env(run_dir, scratch, overlay, frozen_date=frozen_date, receipts=receipts)

    def verify_env(self, env, run_dir, selection, overlay):
        """P151/P364: the hashed carrier + the three hashed plugins + exactly the seed overlay, the frozen date, a receipt
        path outside the config dir; then the source files must still hash to what the run dir was built from. The
        tg1 plugin-set check (`scaffold=` the tg1 label) is the right check for both modes: the plugin set is shared."""
        p, pin = self.p, self._pinned
        provenance.opencode_v2_env_check(
            env, run_dir, selection["fields"]["opencode_bench_config_sha256"], pin["noretry"], overlay,
            scaffold=TG1_LABEL, toolbounds_sha=pin["toolbounds"], datefreeze_sha=pin["datefreeze"])
        if (p._sha_of(pin["source_path"]) != pin["carrier_source"]
                or p._sha_of(t1.PLUGIN) != pin["toolbounds"] or p._sha_of(p.NORETRY_PLUGIN) != pin["noretry"]
                or p._sha_of(t1.DATEFREEZE_PLUGIN) != pin["datefreeze"]
                or pin["system_path"] and p._sha_of(pin["system_path"]) != pin["system"]):
            raise tg.TransportAbort("tg1 input provenance drift")

    def discover(self, scratch, env, *, model, run_dir, binary, overlay, runner, check_version=False):
        """(version or None, destination) with no model request: `--version` (when asked) and the destination proof,
        including that every plugin loaded (the tg1 proof; the M64 policy check differs only by compaction ON)."""
        p = self.p
        version = None
        if check_version:
            result = runner([binary, "--version"], cwd=scratch, env=env, capture_output=True, text=True, timeout=30,
                            stdin=subprocess.DEVNULL)
            version = p._parse_version(result.stdout)
            if result.returncode or version != "2.0.20":
                raise tg.TransportAbort("tg1 requires pinned opencode 2.0.20")
        logged = {**env, "OPENCODE_PRINT_LOGS": "1"}
        if not self.m64:
            return version, provenance.opencode_v2_destination(scratch, logged, model, run_dir, binary, overlay,
                                                               scaffold=TG1_LABEL, runner=runner)
        self._check_m64_carrier(run_dir)
        base = provenance.opencode_v2_destination(scratch, env, model, run_dir, binary, overlay, scaffold=None,
                                                  runner=runner)
        self._prove_plugins(scratch, logged, run_dir, binary, runner)
        return version, base

    def _check_m64_carrier(self, run_dir):
        doc = json.loads((Path(run_dir).resolve() / "cfg/opencode/opencode.json").read_text())
        deny = lambda action: dict(action=action, resource="*", effect="deny") in doc.get("permissions", [])   # noqa: E731
        if (doc.get("compaction", {}).get("auto") is not True
                or doc.get("agents", {}).get("title", {}).get("disabled") is not True
                or not all(deny(a) for a in self.removed_tools)):
            raise provenance.ServedConfigError(
                "M50 tripwire: M64 title/compaction/execute/subagent/question/websearch policy differs")
        if ("mcp" in doc) == self.search_is_offline_test:
            raise provenance.ServedConfigError("M50 tripwire: M64 carrier mcp block differs from the search service")

    def _prove_plugins(self, scratch, env, run_dir, binary, runner):
        """Pinned 2.0.20 `integration.list` awaits plugin activation (`config.get` does not): every plugin of the set must
        be on disk at the repository sha and logged as loaded (the proof tg1 performs)."""
        def refuse(reason):
            raise provenance.ServedConfigError("M50 tripwire: " + reason)

        config = Path(run_dir).resolve() / "cfg/opencode/opencode.json"
        activation = runner([str(binary), "api", "GET", "/api/integration", "--standalone"], cwd=str(scratch), env=env,
                            capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
        if activation.returncode:
            refuse(f"M64 plugin activation discovery exit {activation.returncode}")
        if "failed to load plugin" in activation.stderr:
            refuse("M64 plugin activation log records a failed plugin load")
        for name in sorted(PLUGINS):
            plugin = config.parent / "plugins" / name
            source = REPO / "benchmark/opencode_plugins" / name
            if not plugin.is_file() or self.p._sha_of(plugin) != self.p._sha_of(source):
                refuse("M64 plugin missing or sha differs: " + name)
            loaded = False
            for line in activation.stderr.splitlines():
                try:
                    fields = dict(t.split("=", 1) for t in shlex.split(line) if "=" in t)
                except ValueError:
                    continue
                if (fields.get("msg") == "loading plugin" and fields.get("role") == "server"
                        and fields.get("id") == str(plugin.resolve())):
                    loaded = True
            if not loaded:
                refuse("M64 plugin load proof missing: " + name)

    def command(self, binary, model, prompt):
        return [binary, "run", "--standalone", "--model", "mlx-local/" + model, "--format", "json", "--title",
                "probe", prompt]

    def evidence_suffixes(self):
        return {"events": ".events.jsonl", "stderr": ".stderr.txt", "export": ".json",
                "datefreeze": ".datefreeze.jsonl"}

    def guard_roots(self, work, env, private):
        return [work, env["TMPDIR"], private]

    # ---------------------------------------------------------------- stream, transcript, reconciliation
    def new_stream(self, gate, on_complete):
        return OcStream(gate, on_complete)

    def events(self, stream):
        merged = list(stream.normalized)
        for seq, usage in sorted(stream.late_finishes.items()):
            last = max((i for i, e in enumerate(merged) if e.request_seq == seq), default=len(merged) - 1)
            merged.insert(last + 1, aa.NormalizedEvent.request_finish(seq, usage))
        for after, info in sorted(stream.compaction_events, key=lambda x: x[0]):
            at = max((i + 1 for i, e in enumerate(merged) if e.kind == "request_finish" and e.request_seq <= after),
                     default=0)
            merged.insert(at, aa.NormalizedEvent.compaction(max(after, 1), info))
        if stream.terminal_shape is not None:
            merged.append(aa.NormalizedEvent.terminal(stream.terminal_shape))
        return merged

    def transcript(self, guard, env, work, stream, binary, raw_sink=None):
        exported, _ = ox.run_export(lambda export_env, timeout: guard.run_grader(     # P273: logged-lock retry
            [binary, "session", "export", stream.session_id or "", "--standalone"], cwd=work, env=export_env,
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout), env, timeout=120)
        if raw_sink is not None:
            raw_sink(exported.stdout or "")
        if exported.returncode:
            raise tg.TransportAbort("session export failed: " + ox.export_failure_tail(exported.stderr))
        try:
            doc = json.loads(exported.stdout)
        except ValueError as exc:
            raise tg.TransportAbort("unparsable session export") from exc
        return Transcript(raw=exported.stdout or "", doc=doc)

    def final_boundary(self, transcript):
        return len([m for m in transcript.doc.get("messages", [])
                    if m.get("type") == "assistant" and not m.get("error")])

    def reconcile(self, stream, transcript, receipts, rc, outcome):
        doc = transcript.doc
        try:
            summary = tg.reconcile(stream, doc, rc, outcome)
        except tg.TransportAbort as exc:
            causes = [classify_error(e) for e in stream.errors]
            if stream.errors and all(causes):
                raise TransportFailure(causes[0], str(exc)) from exc
            raise
        for seq, message_id in enumerate(stream.starts, 1):        # the final request usually has no live step_finish
            values = stream.gate.usage.get(message_id)
            if values is not None and not any(e.kind == "request_finish" and e.request_seq == seq
                                              for e in stream.normalized):
                output, reasoning, inp, read, write = values
                stream.late_finishes[seq] = Usage(input=inp, cache_read=read, cache_write=write, output=output,
                                                  reasoning=reasoning)
        compaction, extra = [], {}
        if self.account_compaction:
            compaction = self._compaction_entries(doc, stream)
        if receipts is not None:
            dated = self.receipts_reconcile(receipts["path"], frozen=receipts["frozen"],
                                            session_id=stream.session_id, requests_observed=len(stream.starts),
                                            killed=receipts["killed"])
            extra["date_summary"] = dated
            if self.account_compaction:
                extra["compaction_receipts"] = dated["compaction_receipts"]
                extra["compaction_accounting_complete"] = dated["compaction_receipts"] == len(compaction)
        # `tg.reconcile` derives these two outcomes itself (from the client's error event and exit code)
        derived = outcome or next((f for f in ("client_inactivity", "context_overflow") if f in stream.gate.flags), None)
        stream.terminal_shape = self._terminal_shape(doc, rc, derived)
        return aa.Reconciliation(
            outcome=derived,
            unmatched_export_messages=summary["unmatched_export_messages"], trailing=summary["trailing"],
            uncharged_trailing=summary["uncharged_trailing"], compaction=compaction, extra=extra)

    def _compaction_entries(self, doc, stream):
        entries, before = [], 0
        for message in doc.get("messages", []):
            if message.get("type") == "assistant":
                before += 1
            elif message.get("type") == "compaction":
                try:
                    values = tg.usage_tuple(message.get("tokens"))
                except tg.TransportAbort:
                    raise tg.TransportAbort("compaction usage missing or malformed: its tokens cannot be counted") \
                        from None
                output, reasoning, inp, read, write = values
                usage = Usage(input=inp, cache_read=read, cache_write=write, output=output, reasoning=reasoning)
                info = dict(reason=message.get("reason"), status=message.get("status"), usage=usage.as_dict())
                entries.append(info)
                stream.compaction_events.append((before, info))
        return entries

    def _terminal_shape(self, doc, rc, outcome):
        if outcome == "client_inactivity":
            return "client_cut"
        if outcome in tg.KILL_OUTCOMES:
            return "cancel"
        if outcome == "context_overflow":
            return "error"
        assistants = [m for m in doc.get("messages", []) if m.get("type") == "assistant"]
        return "length" if assistants and assistants[-1].get("finish") == "length" else "stop"

    def receipts_reconcile(self, path, **kw):
        got = datefreeze.reconcile(path, allowed_kinds=self.receipt_kinds, **kw)
        if self.m64:
            got = dict(got, compaction_receipts=got["receipts"] - got["requests"])
        return got

    def web_evidence(self, transcript, env):
        """Raw evidence: every web-capable or shell tool call in the session, with its request. Whether one is a fetch,
        a search or networking is the audit's classification (scoring, step 5), not generation's."""
        found, request = [], 0
        for message in transcript.doc.get("messages", []):
            if message.get("type") != "assistant":
                continue
            request += 1
            for part in message.get("content", []):
                if isinstance(part, dict) and part.get("type") == "tool" and (
                        part.get("name") in ("webfetch", "websearch", "shell") or "search" in str(part.get("name"))):
                    found.append(dict(request=request, tool=part.get("name"), id=part.get("id"),
                                      inputs=(part.get("state") or {}).get("input"),
                                      status=(part.get("state") or {}).get("status")))
        return found

    def tool_windows(self, stream):
        return list(stream.tool_windows)

    def evidence_root(self, workdir):
        """tg1 keeps `opencode_transcripts`; the M64 arms use `transcripts/<arm>` (spec 9)."""
        return Path(workdir) / ("transcripts/" + self.arm_id if self.m64 else "opencode_transcripts")

    def row_identity_fields(self):
        return dict(bench="opencode", schema_version=3)

    def metrics(self, p, transcript, export):
        return dict(tool_bounds_rejections=t1.tool_bounds_rejections(export),
                    loop_metrics=p.loop_metrics(p._metric_export(export)),
                    traffic=p.traffic_metrics(p._metric_export(export)))

    def identity_binary(self):
        exe = Path(os.environ.get("OPENCODE_PROBE_BIN") or self.p._default_opencode_bin())
        return (exe if exe.is_file() else Path(self.p.__file__)), exe.is_file()

    def identity_summary(self, ident, binary_exists):
        out = dict(opencode_version=ident["opencode_version"])
        if binary_exists:
            out["opencode_exe_sha256"] = ident["opencode_exe_sha256"]
        return out

    def merge_receipts(self, reconciliation, summary):
        reconciliation.extra["date_summary"] = summary
        if self.account_compaction:
            reconciliation.extra["compaction_receipts"] = summary["compaction_receipts"]
            reconciliation.extra["compaction_accounting_complete"] = (
                summary["compaction_receipts"] == reconciliation.compaction_count)

    def transport_cause(self, exc):
        return exc.cause if isinstance(exc, TransportFailure) else None

    def tmp_escapes(self, transcript, env):
        return pg.tmp_escapes(transcript.doc, env)
