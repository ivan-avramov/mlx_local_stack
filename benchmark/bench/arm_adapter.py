"""M64 ArmAdapter contract (spec docs/specs/m64-scaffold-arms.md section 5), as code.

One adapter per scaffold arm (`oc`, `pi`, `dsh`). The runner (`bench.arm_runner`) and the chain (`m64 chain`) know a
client only through this contract: hermetic environment and generated config, spawn command, the normalized event
stream the M62 gate is fed from, the transcript and its reconciliation against the stream, web evidence, cancellation,
and the identities (snapshot, generation composite) the chain freezes. Grading stays runner-owned.

This module is pure: it imports no client, scoring or process module, so any adapter (or a test double) can import it.
It is NOT part of the tg1 generation closure (`run_tg1_probe.py` never imports it).

`Snapshot` / `epoch_id` / `arm_generation_sha256` implement spec 4; `NormalizedEvent` is the spec 5 event record;
`UnavailableSearchService` is the D2 (C165 2d) stub: the shared SearXNG MCP service is a later build step and an arm
whose configuration needs it REFUSES to run until a real service replaces the stub.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
import hashlib
import json
import re

SCHEMA_VERSION = 1
ARM_IDS = ("oc", "pi", "dsh")
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]*$")
EVENT_KINDS = ("request_start", "request_finish", "tool", "compaction", "error", "terminal")
TERMINAL_SHAPES = ("stop", "length", "error", "cancel", "client_cut")
TOOL_STATUSES = ("running", "completed", "error")
# Native client cuts registered by an arm's contract test (spec 8.3): client-side terminations scored as strict
# failures, never retried. opencode 2.0.20: `client_inactivity` (C154); an analogue in Pi / dsh is added here when found.
KNOWN_CLIENT_CUTS = ("client_inactivity",)


class ArmRefused(RuntimeError):
    """The arm cannot run (unregistered, a required service missing, a REJECTED snapshot). Nothing was spawned."""


class ArmContractError(ValueError):
    """An adapter or one of its records violates the contract."""


def valid_arm_id(value):
    """An arm of the spec (oc, pi, dsh); a new arm is a spec amendment, so the set is closed."""
    return isinstance(value, str) and value in ARM_IDS


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _count(value):
    return type(value) is int and value >= 0


# ---------------------------------------------------------------- usage and events
@dataclass(frozen=True)
class Usage:
    """Per-request token usage (spec 5 event record). Validated like the gate: non-negative ints, never bools."""
    input: int
    cache_read: int
    cache_write: int
    output: int
    reasoning: int

    def __post_init__(self):
        for name in ("input", "cache_read", "cache_write", "output", "reasoning"):
            if not _count(getattr(self, name)):
                raise ArmContractError(f"usage {name} must be a non-negative integer, got {getattr(self, name)!r}")

    @property
    def completion_tokens(self):
        return self.output + self.reasoning

    @property
    def prompt_tokens(self):
        return self.input + self.cache_read + self.cache_write

    def as_dict(self):
        return dict(input=self.input, cache_read=self.cache_read, cache_write=self.cache_write,
                    output=self.output, reasoning=self.reasoning)


@dataclass(frozen=True)
class NormalizedEvent:
    """`{request_seq, usage{input, cache_read, cache_write, output, reasoning}, tool{name, inputs, status, start, end},
    compaction, error, terminal}` (spec 5), one record per client event, in stream order."""
    kind: str
    request_seq: int | None = None
    usage: Usage | None = None
    tool: dict | None = None
    compaction: dict | None = None
    error: dict | None = None
    terminal: str | None = None

    def __post_init__(self):
        if self.kind not in EVENT_KINDS:
            raise ArmContractError(f"event kind {self.kind!r} is not one of {EVENT_KINDS}")
        if self.request_seq is not None and not (type(self.request_seq) is int and self.request_seq >= 1):
            raise ArmContractError("request_seq must be an integer >= 1")
        if self.kind in ("request_start", "request_finish", "tool") and self.request_seq is None:
            raise ArmContractError(f"a {self.kind} event needs a request_seq")
        if self.kind == "request_finish" and not isinstance(self.usage, Usage):
            raise ArmContractError("a request_finish event needs usage")
        if self.kind == "terminal" and self.terminal not in TERMINAL_SHAPES:
            raise ArmContractError(f"terminal {self.terminal!r} is not one of {TERMINAL_SHAPES}")

    @classmethod
    def request_start(cls, seq):
        return cls("request_start", request_seq=seq)

    @classmethod
    def request_finish(cls, seq, usage):
        return cls("request_finish", request_seq=seq, usage=usage)

    @classmethod
    def tool(cls, seq, name, inputs, status, *, start, end):
        if not (isinstance(name, str) and name):
            raise ArmContractError("tool name must be a nonempty string")
        if status not in TOOL_STATUSES:
            raise ArmContractError(f"tool status {status!r} is not one of {TOOL_STATUSES}")
        if end is not None and start is not None and end < start:
            raise ArmContractError("tool end precedes its start")
        return cls("tool", request_seq=seq,
                   tool=dict(name=name, inputs=inputs, status=status, start=start, end=end))

    @classmethod
    def compaction(cls, seq, info):
        return cls("compaction", request_seq=seq, compaction=dict(info))

    @classmethod
    def error(cls, error):
        return cls("error", error=dict(error))

    @classmethod
    def terminal(cls, shape):
        return cls("terminal", terminal=shape)


# ---------------------------------------------------------------- transcript and reconciliation
@dataclass
class Transcript:
    """The client's own record of the session (opencode: `session export`; Pi: the session file), raw + parsed."""
    raw: str
    doc: dict


@dataclass
class Reconciliation:
    """What `ArmAdapter.reconcile` returns. `outcome` is the registered terminal outcome the client reported (None
    for a normal finish; `client_inactivity` for a native cut). `compaction` lists the compaction requests the
    client made, each `{reason, usage{...}}`; their tokens count to the task (C165 2b) and are accounted here, apart
    from the gate (which only sees the requests the client's live events show)."""
    outcome: str | None
    unmatched_export_messages: int = 0
    trailing: str = "none"
    uncharged_trailing: dict | None = None
    compaction: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        for entry in self.compaction:
            usage = entry.get("usage") if isinstance(entry, dict) else None
            if not (isinstance(usage, dict) and all(_count(usage.get(k)) for k in
                                                    ("input", "cache_read", "cache_write", "output", "reasoning"))):
                raise ArmContractError("every compaction entry needs a usage record (its tokens count to the task)")

    @property
    def compaction_count(self):
        return len(self.compaction)

    @property
    def compaction_completion_tokens(self):
        return sum(e["usage"]["output"] + e["usage"]["reasoning"] for e in self.compaction)

    def row_reconciliation(self):
        """The `reconciliation` row field exactly as the tg1 row carries it."""
        out = dict(unmatched_export_messages=self.unmatched_export_messages, trailing=self.trailing)
        if self.uncharged_trailing is not None:
            out["uncharged_trailing"] = self.uncharged_trailing
        return out


# ---------------------------------------------------------------- identities (spec 4)
@dataclass(frozen=True)
class Snapshot:
    """A harness snapshot as far as the adapter can state it. `complete` is False while inputs the spec requires in
    the snapshot sha (dependency tree, tool schemas, bottle sha ...) are still owed by the snapshot tooling (build
    step 6); `missing` names them. An incomplete snapshot may run smokes; it cannot register an epoch."""
    tool: str
    fields: dict
    complete: bool
    missing: tuple = ()

    def __post_init__(self):
        if self.complete and self.missing:
            raise ArmContractError("a complete snapshot cannot list missing inputs")
        if not (isinstance(self.tool, str) and self.tool):
            raise ArmContractError("snapshot tool must be a nonempty string")

    @property
    def sha256(self):
        return hashlib.sha256(_canonical(dict(tool=self.tool, fields=self.fields, complete=self.complete,
                                              missing=list(self.missing))).encode()).hexdigest()


def epoch_id(snapshots):
    """sha256 of canonical JSON `{schema_version, tools:[{tool, snapshot_sha}] sorted by tool}` (spec 4)."""
    snapshots = list(snapshots)
    if not snapshots:
        raise ArmContractError("an epoch needs snapshots (no snapshots given)")
    tools = [s.tool for s in snapshots]
    if len(set(tools)) != len(tools):
        raise ArmContractError("duplicate tool in the epoch: " + ", ".join(sorted(t for t in tools if tools.count(t) > 1)))
    body = dict(schema_version=SCHEMA_VERSION,
                tools=[dict(tool=s.tool, snapshot_sha=s.sha256) for s in sorted(snapshots, key=lambda s: s.tool)])
    return hashlib.sha256(_canonical(body).encode()).hexdigest()


def arm_generation_sha256(arm_id, fields, names):
    """The per-scaffold-arm generation composite (P311-lite composite + the arm, spec 4): sha256 of canonical JSON of
    the arm id and the named fields. An absent key fails closed; a present None is a value."""
    missing = [k for k in names if k not in fields]
    if missing:
        raise ValueError("generation identity field absent: " + ", ".join(missing))
    return hashlib.sha256(_canonical(dict(arm=arm_id, fields={k: fields[k] for k in names})).encode()).hexdigest()


# ---------------------------------------------------------------- shared search service (D2): the later-step stub
class SearchService(abc.ABC):
    """The shared local search tool every arm gets (C165 2d): the M64-owned SearXNG container behind a pinned MCP
    server. `mcp_entry(client)` is the client-native MCP configuration entry."""

    @property
    @abc.abstractmethod
    def available(self):
        ...

    @abc.abstractmethod
    def require(self):
        ...

    @abc.abstractmethod
    def mcp_entry(self, client):
        ...


class UnavailableSearchService(SearchService):
    """The D2 service is a later build step (spec 12): this stub makes every arm that needs it refuse to run."""
    available = False

    def require(self):
        raise ArmRefused("the shared search service (D2: M64-owned SearXNG + pinned MCP server) is not built yet; "
                         "an arm that configures it refuses to run without it (C165 2d)")

    def mcp_entry(self, client):
        return self.require()


# ---------------------------------------------------------------- the contract
class ArmAdapter(abc.ABC):
    """Spec 5. Concrete adapters set the class attributes and implement every abstract member; `cancel` is shared.

    Attributes: `arm_id` (oc|pi|dsh), `tool` (client name), `label` (the scaffold label rows and manifests carry),
    `GENERATION_FIELDS` (names of the generation composite's inputs), `native_client_cuts` (registered client-side
    terminations), `removed_tools` (D1/D2 tools removed from this arm's default set, disclosed)."""
    arm_id: str
    tool: str
    label: str
    GENERATION_FIELDS: tuple
    native_client_cuts: tuple
    removed_tools: tuple
    account_compaction = False          # the runner accounts compaction requests (compaction is on for this arm)
    watchdog_enabled = False            # the runner runs the spec 5.4 shell watchdog
    pinned_version = ""                 # the client version the identity is read against
    observed = None                     # set by the runner after each item: {events, reconciliation, tool_windows}
    date_receipt_key = None             # evidence key of the per-item date-freeze receipts (None: the arm has none)
    report_gate_on_abort = False        # the abort stamp carries the failed attempt's gate report (M64 chains count it)

    # -- identity and provenance
    @abc.abstractmethod
    def snapshot(self):
        """`Snapshot` of this client as the adapter can state it."""

    @abc.abstractmethod
    def identity(self, **kw):
        """The probe identity dict (policy, probe_code_sha256, versions, exe sha ...), as `tg1_runner.identity`."""

    @abc.abstractmethod
    def manifest_fields(self):
        """Fields merged into the manifest's `runtime` (arm, snapshot, identities, ack wait, heartbeat kind)."""

    @abc.abstractmethod
    def row_fields(self, **kw):
        """Client-specific row fields (versions, paths, evidence) for one item."""

    # -- run construction
    @abc.abstractmethod
    def selection(self, system_file=None):
        """The generated config (carrier) selection: bytes + provenance fields."""

    @abc.abstractmethod
    def declared_model(self, selection, model):
        """`(model_declaration, base_url)` the client is configured with (budgets, context, endpoint)."""

    @abc.abstractmethod
    def require_binary(self):
        """Path of the pinned client executable (refuses when absent)."""

    @abc.abstractmethod
    def preflight(self, *, selection, path=None, router=None, limit=None, model=None, exe_sha=None):
        """A4-equivalent: the session routing / server cache-session proof for THIS selection (the adapter extracts its
        own carrier fields from `selection`). Returns the receipt or None."""

    @abc.abstractmethod
    def seed_overlay(self, model, seed, *, attempt=None):
        """The per-item seed overlay the client config receives (client-native shape). `attempt` (an
        `AttemptContext`) is passed ONLY when the evidence policy requires worker receipts and the adapter
        `supports_attempt_header`: the overlay then carries the correlation header (R3, R31)."""

    @abc.abstractmethod
    def overlay_sha(self, env):
        """sha256 of the overlay actually present in the spawn environment `env` (the row's `overlay_sha256`)."""

    def generation_identity_sha256(self, fields):
        """The generation composite over `fields` (default: the per-arm recipe, spec 4)."""
        return arm_generation_sha256(self.arm_id, fields, self.GENERATION_FIELDS)

    def valid_frozen_date(self, date):
        """Is `date` the shape this client prints into its prompt (the P364 frozen date)? Default: any nonempty string."""
        return isinstance(date, str) and bool(date)

    def verify_item_env(self, env, paths, frozen_date):
        """Refuse a spawn environment that does not name this item's evidence paths / frozen date (default: nothing)."""

    @abc.abstractmethod
    def make_run_dir(self, workdir, run_id, selection):
        """Create the hermetic run directory (HOME/config/plugins) and return it."""

    @abc.abstractmethod
    def build_env(self, run_dir, scratch, overlay, *, receipts, frozen_date, toolwindow_receipts=None, attempt=None):
        """Hermetic spawn environment for one item (cwd = the fixed scratch path). `toolwindow_receipts` (an absolute
        path outside the config dir) is passed when the generation policy's watchdog is on (A4); `attempt` is this
        item attempt's `AttemptContext` (always passed)."""

    @abc.abstractmethod
    def verify_env(self, env, run_dir, selection, overlay):
        """Refuse unless the environment / config directory is exactly what the identity covers."""

    @abc.abstractmethod
    def discover(self, scratch, env, **kw):
        """Version check + destination proof before any session (no model request). Returns the version."""

    @abc.abstractmethod
    def command(self, binary, model, prompt):
        """argv of the item run."""

    @abc.abstractmethod
    def evidence_suffixes(self):
        """`{name: suffix}` of the per-item evidence files (events, stderr, export, receipts ...)."""

    @abc.abstractmethod
    def guard_roots(self, work, env, private):
        """Roots the process guard attributes processes to."""

    # -- stream, transcript, reconciliation
    @abc.abstractmethod
    def new_stream(self, gate, on_complete):
        """The incremental event consumer feeding the gate (`feed`, `finish`, `session_id`, `starts` ...)."""

    @abc.abstractmethod
    def events(self, stream):
        """`list[NormalizedEvent]` for everything the stream has consumed so far."""

    @abc.abstractmethod
    def transcript(self, guard, env, work, stream, binary, raw_sink=None):
        """Acquire the client's session record under the guard. Returns a `Transcript`; `raw_sink(text)` receives the
        raw output before any refusal so the evidence file exists even when acquisition fails."""

    @abc.abstractmethod
    def final_boundary(self, transcript):
        """The completed-request count the final grade is credited to (from the transcript)."""

    @abc.abstractmethod
    def reconcile(self, stream, transcript, receipts, rc, outcome):
        """Match the live stream, the transcript and the receipts; exit code never establishes success. Returns a
        `Reconciliation`; an unregistered terminal shape raises `TransportAbort`."""

    @abc.abstractmethod
    def tool_windows(self, stream):
        """`[(start, end, name)]` tool-execution windows (epoch seconds; `end` None while open) for the shell
        watchdog (spec 5.4)."""

    @abc.abstractmethod
    def tmp_escapes(self, transcript, env):
        """Paths the session wrote outside its scratch directory (diagnostic)."""

    @abc.abstractmethod
    def receipts_reconcile(self, paths, **kw):
        """Reconcile per-request receipts (date freeze today; worker receipts, spec 7, in the fork step)."""

    # -- arm naming (defaults suit a client with none of these needs)
    @abc.abstractmethod
    def evidence_root(self, workdir):
        """Directory under which per-model evidence lives (`$STACK_WORKDIR/transcripts/<arm>` for the M64 arms)."""

    @abc.abstractmethod
    def row_identity_fields(self):
        """Constant row fields naming the harness (`bench`, `schema_version`)."""

    @abc.abstractmethod
    def metrics(self, p, transcript, export):
        """Client-specific row metrics derived from the transcript (loop / traffic / tool-bound counts)."""

    @abc.abstractmethod
    def identity_binary(self):
        """`(path, exists)` of the client binary for `--print-identity` (a stand-in path when absent)."""

    @abc.abstractmethod
    def identity_summary(self, ident, binary_exists):
        """Client-named identity keys `--print-identity` adds (version, exe sha)."""

    def merge_receipts(self, reconciliation, summary):
        """Fold a receipts summary into the Reconciliation (default: keep it as `extra['receipts']`)."""
        reconciliation.extra["receipts"] = summary

    def transport_cause(self, exc):
        """The transport-incident cause of an abort (spec 8.3), or None when it is not a classified transport failure."""
        return None

    # -- cancellation: SIGTERM first (spec 5), shared
    def cancel(self, guard, wait, *, before_signal=None, after_signal=None):
        """Signal the client with SIGTERM and wait; survivors are the caller's to SIGKILL (`guard.kill_role`)."""
        return guard.graceful_stop("client", wait, before_signal=before_signal, after_signal=after_signal) or []


def validate_adapter(adapter):
    """Class-attribute checks every adapter must pass (the method set is enforced by `abc`)."""
    def bad(what, why):
        raise ArmContractError(f"adapter {type(adapter).__name__}: {what} {why}")

    if not valid_arm_id(getattr(adapter, "arm_id", None)):
        bad("arm_id", f"{getattr(adapter, 'arm_id', None)!r} is not a short lowercase id")
    if not (isinstance(getattr(adapter, "tool", None), str) and adapter.tool):
        bad("tool", "must be a nonempty string")
    if not (isinstance(getattr(adapter, "label", None), str) and LABEL_RE.match(adapter.label)):
        bad("label", f"{getattr(adapter, 'label', None)!r} is not a nonempty label without whitespace")
    fields = getattr(adapter, "GENERATION_FIELDS", None)
    if not (isinstance(fields, tuple) and fields and all(isinstance(f, str) and f for f in fields)
            and len(set(fields)) == len(fields)):
        bad("GENERATION_FIELDS", "must be a nonempty tuple of unique field names")
    cuts = getattr(adapter, "native_client_cuts", None)
    if not (isinstance(cuts, tuple) and all(c in KNOWN_CLIENT_CUTS for c in cuts) and len(set(cuts)) == len(cuts)):
        bad("native_client_cuts", f"must be a tuple of registered cuts {KNOWN_CLIENT_CUTS}")
    removed = getattr(adapter, "removed_tools", None)
    if not (isinstance(removed, tuple) and all(isinstance(t, str) and t for t in removed)
            and len(set(removed)) == len(removed)):
        bad("removed_tools", "must be a tuple of unique tool names (empty when the default set has none of D1/D2)")


class ArmRegistry:
    """Arms the chain may schedule. An arm that is not registered cannot run (spec 2: dsh may be REJECTED and the build
    then HOLDS, never silently dropped: the chain refuses an unregistered arm)."""

    def __init__(self):
        self._classes = {}

    def register(self, cls):
        probe = cls.__new__(cls)               # class attributes only: validation must not need construction
        validate_adapter(probe)
        if cls.arm_id in self._classes:
            raise ArmContractError(f"arm {cls.arm_id!r} is already registered")
        self._classes[cls.arm_id] = cls
        return cls

    def get(self, arm_id, **kwargs):
        if not valid_arm_id(arm_id):
            raise ArmRefused(f"unknown arm {arm_id!r} (arms: {', '.join(ARM_IDS)})")
        if arm_id not in self._classes:
            raise ArmRefused(f"arm {arm_id!r} is not registered (no adapter built or its snapshot was REJECTED)")
        return self._classes[arm_id](**kwargs)

    def registered(self):
        return tuple(a for a in ARM_IDS if a in self._classes)
