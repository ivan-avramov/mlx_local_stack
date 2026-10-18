"""P371 (plan 4 A3, spec 7): the runner side of the worker receipt protocol.

The fork endpoint (P372, `../mlx-vlm`) is built later; the protocol is pinned NOW by the fixture
`bench/tests/fixtures/p371_receipt_protocol.json`, which both sides test against:

    POST /bench/attempt/start  {attempt_id}  ->  {worker:{pid,create_time}, seq}
    POST /bench/attempt/fence  {attempt_id}  ->  {worker, last_seq, receipts:[<receipt>, ...]}

A fence returns after every request admitted before it finalized. The attempt OWNS the receipts with
`start.seq < seq <= fence.last_seq`. The start, the fence and EVERY receipt must name the attempt's worker (a
replacement between the marks is `WorkerMismatch`, cause `worker_crash`). A receipt carries exactly `RECEIPT_FIELDS`.

`join` pairs the adapter's classified requests (`{cls, [tools_sha256]}`, admission order; class task / compaction /
auxiliary, from the FINALIZED transcript) ONE-TO-ONE with the owned receipts by fence + admission order + timestamps
(received_mono strictly increasing in seq order), plus the `X-Bench-Attempt` header when the adapter supports it (a
headerless client's receipts carry a null header; a non-null header must always match). Per-class checks: tools
required / forbidden per class (`DEFAULT_CLASS_RULES`: a compaction or auxiliary request is tool-less), the request's
own tool-set hash when it states one, and the generation controls (`controls[cls]`: sampling, seed, thinking budget,
max tokens). Task tokens = every owned task + compaction receipt, disconnected generations included; auxiliary
requests are joined and reported apart (`by_class`). Controls may also carry `roles` (the class's allowed message roles; a receipt's roles must be a nonempty subset),
`max_tokens_max` (the client clamps `max_tokens` to the remaining window, so it is bounded, not pinned) and a request
may declare `repeat=(lo, hi)` (see `_repeat_range`). Token convention the worker endpoint must follow (P372):
`completion_tokens` is ALL generated tokens and `reasoning_tokens` the thinking subset of them (never summed here).
Every failure is a `tg.TransportAbort` subclass; only
`WorkerMismatch` carries a cause (`worker_crash`, R21).

No adapter, corpus, scoring or process module is imported (it is in the probe closure by construction, R26)."""
from __future__ import annotations

import abc
import hashlib
import json
import math
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import token_turn_gate as tg

ATTEMPT_HEADER = "X-Bench-Attempt"
SAMPLING_FIELDS = ("temperature", "top_p", "top_k", "min_p", "presence_penalty")
RECEIPT_FIELDS = (
    "seq", "worker", "attempt_header", "received_mono", "finished_mono", "sampling", "seed", "thinking_budget",
    "max_tokens", "roles", "request_tools_present", "request_tools_sha256", "prompt_tokens", "cache_tokens",
    "completion_tokens", "reasoning_tokens", "disconnected", "terminal")
CLASSES = ("task", "compaction", "auxiliary")
TASK_TOTAL_CLASSES = ("task", "compaction")             # compaction tokens count to the task (A2); auxiliary apart
DEFAULT_CLASS_RULES = dict(task="required", compaction="forbidden", auxiliary="forbidden")
TOKEN_FIELDS = ("prompt_tokens", "cache_tokens", "completion_tokens", "reasoning_tokens")
RECEIPT_POLICIES = ("absent", "required")


# ---------------------------------------------------------------- aborts
class ReceiptAbort(tg.TransportAbort):
    """Worker-side evidence cannot support a scored row."""
    cause = None


class ReceiptSchemaError(ReceiptAbort):
    pass


class ReceiptUnavailable(ReceiptAbort):
    pass


class ReceiptTransportError(ReceiptAbort):
    pass


class ReceiptMissing(ReceiptAbort):
    pass


class ReceiptDuplicate(ReceiptAbort):
    pass


class ReceiptUnmatched(ReceiptAbort):
    pass


class ReceiptLate(ReceiptAbort):
    pass


class ReceiptAmbiguous(ReceiptAbort):
    pass


class ReceiptHeaderMismatch(ReceiptAbort):
    pass


class ReceiptToolsMismatch(ReceiptAbort):
    pass


class ReceiptControlsMismatch(ReceiptAbort):
    pass


class WorkerMismatch(ReceiptAbort):
    """A mark or receipt names another worker than the attempt's: the worker was replaced mid-attempt (R21)."""
    cause = "worker_crash"


# ---------------------------------------------------------------- context, marks, schema
@dataclass(frozen=True)
class AttemptContext:
    """One attempt at one slot: `attempt_id` = slot + attempt number + re-run index; `header` is the correlation
    header value the generated provider config sends (`X-Bench-Attempt`)."""
    attempt_id: str
    slot: str
    attempt: int
    rerun_index: int

    @classmethod
    def make(cls, slot, attempt, rerun_index=0):
        if not (isinstance(slot, str) and slot and slot.isprintable()):
            raise ValueError(f"slot must be a nonempty printable string, got {slot!r}")
        if not (type(attempt) is int and attempt >= 1) or not (type(rerun_index) is int and rerun_index >= 0):
            raise ValueError("attempt must be an integer >= 1 and rerun_index an integer >= 0")
        return cls(attempt_id=f"{slot}#a{attempt}.r{rerun_index}", slot=slot, attempt=attempt, rerun_index=rerun_index)

    @property
    def header(self):
        return self.attempt_id


@dataclass(frozen=True)
class StartMark:
    worker: dict
    seq: int


@dataclass(frozen=True)
class Fence:
    worker: dict
    last_seq: int
    receipts: tuple


def _count(v, minimum=0):
    return type(v) is int and v >= minimum


def _number(v):
    return type(v) in (int, float) and math.isfinite(v)


def _bad(what):
    raise ReceiptSchemaError(what)


def validate_worker(worker, what="worker"):
    if not (isinstance(worker, dict) and set(worker) == {"pid", "create_time"} and _count(worker["pid"], 1)
            and _number(worker["create_time"])):
        _bad(f"{what} must be exactly {{pid:int, create_time:number}}, got {worker!r}")
    return worker


def validate_receipt(r):
    """Exactly the A3 field list with exact types; returns the receipt."""
    if not isinstance(r, dict) or set(r) != set(RECEIPT_FIELDS):
        _bad("receipt fields differ from the A3 list: " + (
            "not an object" if not isinstance(r, dict) else
            f"missing {sorted(set(RECEIPT_FIELDS) - set(r))} extra {sorted(set(r) - set(RECEIPT_FIELDS))}"))
    if not _count(r["seq"], 1):
        _bad("seq must be an integer >= 1")
    validate_worker(r["worker"], "receipt worker")
    if r["attempt_header"] is not None and not isinstance(r["attempt_header"], str):
        _bad("attempt_header must be a string or null")
    if not (_number(r["received_mono"]) and _number(r["finished_mono"]) and r["finished_mono"] >= r["received_mono"]):
        _bad("received_mono / finished_mono must be numbers with finished >= received")
    s = r["sampling"]
    if not (isinstance(s, dict) and set(s) == set(SAMPLING_FIELDS) and all(_number(s[k]) for k in SAMPLING_FIELDS)):
        _bad(f"sampling must be exactly {SAMPLING_FIELDS} as numbers")
    if not _count(r["seed"]) or not _count(r["thinking_budget"]) or not _count(r["max_tokens"]):
        _bad("seed, thinking_budget and max_tokens must be non-negative integers")
    if not (isinstance(r["roles"], list) and all(isinstance(x, str) for x in r["roles"])):
        _bad("roles must be a list of strings")
    present, sha = r["request_tools_present"], r["request_tools_sha256"]
    if type(present) is not bool or not (sha is None or isinstance(sha, str)) or (present and not sha) or (
            not present and sha is not None):
        _bad("request_tools_present is a bool and request_tools_sha256 a string exactly when tools are present")
    for name in TOKEN_FIELDS:
        if not _count(r[name]):
            _bad(f"{name} must be a non-negative integer")
    if type(r["disconnected"]) is not bool or not (isinstance(r["terminal"], str) and r["terminal"]):
        _bad("disconnected must be a bool and terminal a nonempty string")
    return r


def _validate_mark(doc):
    if not (isinstance(doc, dict) and set(doc) == {"worker", "seq"} and _count(doc["seq"])):
        _bad("start response must be exactly {worker, seq}")
    return StartMark(worker=validate_worker(doc["worker"], "start worker"), seq=doc["seq"])


def _validate_fence(doc):
    if not (isinstance(doc, dict) and set(doc) == {"worker", "last_seq", "receipts"} and _count(doc["last_seq"])
            and isinstance(doc["receipts"], list)):
        _bad("fence response must be exactly {worker, last_seq, receipts[]}")
    return Fence(worker=validate_worker(doc["worker"], "fence worker"), last_seq=doc["last_seq"],
                 receipts=tuple(validate_receipt(r) for r in doc["receipts"]))


# ---------------------------------------------------------------- sources
class ReceiptSource(abc.ABC):
    """`start(ctx)` immediately before the client spawns; `fence(ctx)` after it exits."""
    available = True

    def check(self):
        """Refuse before any spawn when the source cannot serve a `required` policy."""

    @abc.abstractmethod
    def start(self, ctx):
        """Returns a `StartMark`."""

    @abc.abstractmethod
    def fence(self, ctx):
        """Returns a `Fence` once every request admitted before it has finalized."""


class UnavailableReceiptSource(ReceiptSource):
    """The fork endpoint is not built (P372): `required` refuses at start, before any spawn."""
    available = False

    def __init__(self, reason="the worker receipt endpoint is not available"):
        self.reason = reason

    def check(self):
        raise ReceiptUnavailable(self.reason)

    def start(self, ctx):
        self.check()

    def fence(self, ctx):
        self.check()


def require_source(policy, source):
    """`worker_receipts` policy check before any spawn: `required` + an unusable source refuses."""
    if policy not in RECEIPT_POLICIES:
        raise ValueError(f"worker_receipts policy must be one of {RECEIPT_POLICIES}, got {policy!r}")
    if policy == "required":
        source.check()


class HttpReceiptSource(ReceiptSource):
    """The protocol client for the fork endpoint. Transport and shape failures raise (never degrade to client
    accounting)."""

    def __init__(self, base_url, *, api_key=None, timeout_s=30.0):
        self.base = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    def check(self):
        """Refuse before any spawn unless the worker serves the receipt route (F2). The probe is a GET of the start route:
        a POST-only route answers 405 (it exists), an absent one 404, a worker that is down a transport error."""
        headers = {"Authorization": "Bearer " + self.api_key} if self.api_key else {}
        request = urllib.request.Request(self.base + "/bench/attempt/start", headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s):
                return
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                return                                  # 405 / 400 / 401 ...: the route exists
            why = "the worker has no /bench/attempt/start route"
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            why = f"the worker is unreachable ({type(exc).__name__})"
        raise ReceiptUnavailable(f"the worker receipt endpoint is not available: {why} (fork control endpoint: P372)")

    def _post(self, path, body):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers=headers,
                                         method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, socket.timeout, OSError, ValueError) as exc:
            raise ReceiptTransportError(f"worker receipt endpoint {path} failed: {type(exc).__name__}") from exc

    def start(self, ctx):
        return _validate_mark(self._post("/bench/attempt/start", dict(attempt_id=ctx.attempt_id)))

    def fence(self, ctx):
        return _validate_fence(self._post("/bench/attempt/fence", dict(attempt_id=ctx.attempt_id)))


class FakeReceiptSource(ReceiptSource):
    """Test double. The test plays the worker: `admit(cls, ...)` records one request's receipt. Fault injection:
    `drop_seqs`, `duplicate_seqs`, `foreign_worker` ({seq: worker}), `fence_worker`, `start_worker`,
    `fence_receipt_worker` (every receipt names it), `late_after_fence` (n extra receipts beyond `last_seq`)."""

    def __init__(self, worker):
        self.worker = dict(worker)
        self._seq = 0
        self._mono = 0.0
        self._receipts = []
        self._starts = {}
        self.calls = []
        self.drop_seqs, self.duplicate_seqs, self.foreign_worker = set(), set(), {}
        self.fence_worker = self.start_worker = self.fence_receipt_worker = None
        self.late_after_fence = 0

    def start(self, ctx):
        self.calls.append(("start", ctx.attempt_id))
        self._starts[ctx.attempt_id] = self._seq
        return StartMark(worker=dict(self.start_worker or self.worker), seq=self._seq)

    def admit(self, cls="task", *, header=None, tools=None, tools_sha256=None, seed=1234567, thinking_budget=81920,
              max_tokens=102400, sampling=None, prompt_tokens=1000, cache_tokens=0, completion_tokens=100,
              reasoning_tokens=0, disconnected=False, terminal="stop", roles=None):
        self.calls.append(("admit", cls))
        self._seq += 1
        has_tools = (cls == "task") if tools is None else tools
        if tools_sha256 is not None:
            has_tools = True
        self._mono += 1.0
        self._receipts.append(dict(
            seq=self._seq, worker=dict(self.worker), attempt_header=header, received_mono=self._mono,
            finished_mono=self._mono + 0.5,
            sampling=dict(sampling or dict(temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=1.5)),
            seed=seed, thinking_budget=thinking_budget, max_tokens=max_tokens,
            roles=list(roles) if roles is not None else ["system", "user"],
            request_tools_present=has_tools, request_tools_sha256=(tools_sha256 or "ab" * 32) if has_tools else None,
            prompt_tokens=prompt_tokens, cache_tokens=cache_tokens, completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens, disconnected=disconnected, terminal=terminal))
        self._mono += 1.0
        return self._seq

    def all_receipts(self):
        return [dict(r) for r in self._receipts]

    def fence(self, ctx):
        self.calls.append(("fence", ctx.attempt_id))
        start = self._starts[ctx.attempt_id]
        out = []
        for r in self._receipts:
            if r["seq"] <= start or r["seq"] in self.drop_seqs:
                continue
            r = dict(r)
            if self.fence_receipt_worker is not None:
                r["worker"] = dict(self.fence_receipt_worker)
            if r["seq"] in self.foreign_worker:
                r["worker"] = dict(self.foreign_worker[r["seq"]])
            out.append(r)
            if r["seq"] in self.duplicate_seqs:
                out.append(dict(r))
        for i in range(self.late_after_fence):
            late = dict(self._receipts[-1], seq=self._seq + 1 + i)
            late["received_mono"] = late["finished_mono"] + 1 + i
            late["finished_mono"] = late["received_mono"] + 0.5
            out.append(late)
        return Fence(worker=dict(self.fence_worker or self.worker), last_seq=self._seq, receipts=tuple(out))


# ---------------------------------------------------------------- ownership and join
def owned_receipts(mark, fence):
    """The receipts of the attempt `(mark.seq, fence.last_seq]`, validated: worker identity of the marks and of
    EVERY listed receipt, nothing finalized after the fence, no duplicate, no gap. Returns them in seq order."""
    if mark.worker != fence.worker:
        raise WorkerMismatch("worker identity differs between the start and the fence (worker replaced mid-attempt)")
    if fence.last_seq < mark.seq:
        raise ReceiptAbort("fence precedes the start mark")
    for r in fence.receipts:
        validate_receipt(r)
        if r["worker"] != mark.worker:
            raise WorkerMismatch(f"receipt {r['seq']} names another worker than the attempt's")
    late = [r["seq"] for r in fence.receipts if r["seq"] > fence.last_seq]
    if late:
        raise ReceiptLate(f"receipts {late} were finalized after the fence")
    seqs = [r["seq"] for r in fence.receipts if r["seq"] > mark.seq]
    dupes = sorted({s for s in seqs if seqs.count(s) > 1})
    if dupes:
        raise ReceiptDuplicate(f"duplicate receipts for seq {dupes}")
    owned = sorted((r for r in fence.receipts if r["seq"] > mark.seq), key=lambda r: r["seq"])
    want = list(range(mark.seq + 1, fence.last_seq + 1))
    if [r["seq"] for r in owned] != want:
        raise ReceiptMissing(f"owned seq range {want[:1]}..{want[-1:]} has gaps: have {[r['seq'] for r in owned]}")
    return owned


@dataclass
class JoinResult:
    pairs: list                      # [(request, receipt)] in admission order
    by_class: dict
    task_tokens: dict
    accounting: str = "receipts"


def _zero():
    return dict(requests=0, **{k: 0 for k in TOKEN_FIELDS})


def _repeat_range(request):
    """`(lo, hi)` receipts a classified request may own. Default `(1, 1)`. A client that cannot state how many worker
    requests one transcript entry made (opencode: one compaction message = its summary request, retried once when the
    summary misses the template) declares a range; the join resolves it from the receipts' own tool rule."""
    repeat = request.get("repeat", (1, 1))
    if not (isinstance(repeat, (tuple, list)) and len(repeat) == 2 and all(type(x) is int for x in repeat)
            and 1 <= repeat[0] <= repeat[1]):
        raise ReceiptAbort(f"request repeat must be (lo, hi) integers with 1 <= lo <= hi, got {repeat!r}")
    return repeat[0], repeat[1]


def _tools_fit(rule, receipt):
    present = receipt["request_tools_present"]
    return (present if rule == "required" else not present) if rule in ("required", "forbidden") else True


def _assign(receipts, requests, rules):
    """`[(request, receipt)]` in admission order: every request takes its `lo` receipts and extends towards `hi` only
    over following receipts that satisfy its class's tool rule while enough receipts remain for every later request."""
    ranges = [_repeat_range(r) for r in requests]
    lo_total, hi_total = sum(lo for lo, _ in ranges), sum(hi for _, hi in ranges)
    if len(receipts) < lo_total:
        raise ReceiptMissing(f"{lo_total} requests but only {len(receipts)} receipts")
    if len(receipts) > hi_total:
        raise ReceiptUnmatched(f"{len(receipts)} receipts but only {hi_total} requests")
    pairs, i = [], 0
    for index, (request, (lo, hi)) in enumerate(zip(requests, ranges)):
        later = sum(lo for lo, _ in ranges[index + 1:])
        take = lo
        while (take < hi and len(receipts) - (i + take) > later and i + take < len(receipts)
               and _tools_fit(rules.get(request.get("cls")), receipts[i + take])):
            take += 1
        pairs.extend((request, r) for r in receipts[i:i + take])
        i += take
    if i != len(receipts):
        raise ReceiptUnmatched(f"{len(receipts) - i} receipts left after the last request")
    return pairs


def join(receipts, classified_requests, *, supports_header, ctx=None, controls=None, class_rules=None, mark=None,
         fence=None):
    """One-to-one join + per-class checks (see the module docstring). `receipts` are the attempt's owned receipts."""
    rules = dict(DEFAULT_CLASS_RULES, **(class_rules or {}))
    receipts = [validate_receipt(r) for r in receipts]
    seqs = [r["seq"] for r in receipts]
    dupes = sorted({s for s in seqs if seqs.count(s) > 1})
    if dupes:
        raise ReceiptDuplicate(f"duplicate receipts for seq {dupes}")
    receipts.sort(key=lambda r: r["seq"])
    requests = list(classified_requests)
    for request in requests:
        if request.get("cls") not in CLASSES:
            raise ReceiptAbort(f"unknown request class {request.get('cls')!r}")
    pairs = _assign(receipts, requests, rules)
    for a, b in zip(receipts, receipts[1:]):
        if not b["received_mono"] > a["received_mono"]:
            raise ReceiptAmbiguous(f"receipts {a['seq']} and {b['seq']} are not ordered by timestamp")
    expected = None if ctx is None else ctx.header
    result = JoinResult(pairs=[], by_class={}, task_tokens=_zero())
    for request, r in pairs:
        cls = request["cls"]
        if mark is not None and r["worker"] != mark.worker:
            raise WorkerMismatch(f"receipt {r['seq']} names another worker than the attempt's")
        header = r["attempt_header"]
        if header is None and supports_header:
            raise ReceiptHeaderMismatch(f"receipt {r['seq']} carries no {ATTEMPT_HEADER} but the client sends it")
        if header is not None and expected is not None and header != expected:
            raise ReceiptHeaderMismatch(f"receipt {r['seq']} header {header!r} is not this attempt's")
        _check_tools(cls, rules[cls], request, r)
        _check_controls(cls, (controls or {}).get(cls), r)
        bucket = result.by_class.setdefault(cls, _zero())
        bucket["requests"] += 1
        for k in TOKEN_FIELDS:
            bucket[k] += r[k]
        if cls in TASK_TOTAL_CLASSES:
            result.task_tokens["requests"] += 1
            for k in TOKEN_FIELDS:
                result.task_tokens[k] += r[k]
        result.pairs.append((request, r))
    return result


def _check_tools(cls, rule, request, r):
    present = r["request_tools_present"]
    if rule == "required" and not present:
        raise ReceiptToolsMismatch(f"a {cls} request must carry tools (receipt {r['seq']})")
    if rule == "forbidden" and present:
        raise ReceiptToolsMismatch(f"a {cls} request must be tool-less (receipt {r['seq']})")
    want = request.get("tools_sha256")
    if want is not None and want != r["request_tools_sha256"]:
        raise ReceiptToolsMismatch(f"receipt {r['seq']} tool-set hash differs from the client's request")


def _check_controls(cls, want, r):
    if not want:
        return
    for key in ("seed", "thinking_budget", "max_tokens"):
        if key in want and r[key] != want[key]:
            raise ReceiptControlsMismatch(f"{cls} receipt {r['seq']}: {key} {r[key]!r} != {want[key]!r}")
    if "sampling" in want and r["sampling"] != want["sampling"]:
        raise ReceiptControlsMismatch(f"{cls} receipt {r['seq']}: sampling {r['sampling']!r} != {want['sampling']!r}")
    if "max_tokens_max" in want and r["max_tokens"] > want["max_tokens_max"]:
        raise ReceiptControlsMismatch(
            f"{cls} receipt {r['seq']}: max_tokens {r['max_tokens']!r} exceeds the bound {want['max_tokens_max']!r}")
    if "roles" in want:
        allowed = set(want["roles"])
        if not r["roles"] or not set(r["roles"]) <= allowed:
            raise ReceiptControlsMismatch(
                f"{cls} receipt {r['seq']}: roles {r['roles']!r} are not a nonempty subset of {sorted(allowed)!r}")


def fence_totals(mark, fence):
    """What a fence lists for the attempt (`seq > mark.seq`), for the ABORT stamp (P371 3b): requests and token totals of
    EVERY listed receipt (all classes: an aborted attempt has no classified requests), plus `worker_ok` (the start, the
    fence and every receipt name one worker). Never raises on a malformed receipt: a bad one is counted as unreadable."""
    reqs, tokens, bad, seen = 0, {k: 0 for k in TOKEN_FIELDS}, 0, set()
    worker_ok = mark.worker == fence.worker
    for r in fence.receipts:
        try:
            if r["seq"] <= mark.seq or r["seq"] in seen:
                continue
            seen.add(r["seq"])
            worker_ok = worker_ok and r["worker"] == mark.worker
            for k in TOKEN_FIELDS:
                tokens[k] += int(r[k])
            reqs += 1
        except (KeyError, TypeError, ValueError):
            bad += 1
    return dict(fence_taken=True, requests=reqs, worker_ok=bool(worker_ok), unreadable=bad, **tokens)


def write_receipts_file(path, ctx, mark, fence):
    """Persist the raw fenced receipt set (`<evidence>.receipts.json`), exclusive create; returns its sha256."""
    doc = dict(attempt_id=ctx.attempt_id, start=dict(worker=mark.worker, seq=mark.seq),
               fence=dict(worker=fence.worker, last_seq=fence.last_seq, receipts=list(fence.receipts)))
    raw = (json.dumps(doc, sort_keys=True, indent=1) + "\n").encode()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise ReceiptAbort("receipt evidence is immutable: " + path.name + " exists") from None
    with os.fdopen(fd, "wb") as fp:
        fp.write(raw)
        fp.flush()
        os.fsync(fp.fileno())
    return hashlib.sha256(raw).hexdigest()
