"""B2 (P426) per-item reconciliation and engagement (spec 4, 16.2): the client's `request_usage`, the server log's
`Request started / completed / failed` lines and the worker's `/metrics` deltas must tell one story per item.

Pure functions over parsed data: no process, network or GPU. A violation is a problem string; the hooks turn any
problem into `invalidate` (systemic)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

STREAM_CLOSED = "stream_closed_before_completion"
BACKEND = "cached_session"
SETTLE_POLL_S = 2.0
_MARK = re.compile(r"Request (started|completed|failed): ")
_FAILED = re.compile(r"^(?P<head>.*?)\berror=(?P<error>.*) in_flight=(?P<in_flight>\d+)\s*$")
_INT_KEYS = ("in_flight", "cached_tokens", "prompt_tokens", "generated_tokens")
_FLOAT_KEYS = ("decode_tok_s", "prefill_tok_s", "elapsed")
_REQUIRED = dict(started=("in_flight",), completed=("session", "backend", "prompt_tokens", "generated_tokens"),
                 failed=("error", "in_flight"))
_RENAME = dict(decode="decode_tok_s", prefill="prefill_tok_s")
DRAFT_KEYS = ("draft_rounds", "draft_n", "draft_n_accepted", "draft_kind")
KILL_CASES = ("kill_boundary", "kill_inflight_failed", "kill_completed_unaccounted")


class LogParseError(ValueError):
    """A `Request ...` line that does not parse: systemic (spec 4.3 last bullet)."""


@dataclass(frozen=True)
class LogLine:
    kind: str                    # started | completed | failed
    fields: dict                 # values are strings as logged (spec 16.4); `_int` reads a validated integer field
    offset: int                  # byte offset of the line start within the parsed data


def _int(line, key):
    return int(line.fields[key])


@dataclass
class ItemReport:
    ok: bool
    case: str
    problems: list = field(default_factory=list)
    requests: list = field(default_factory=list)
    totals: dict = field(default_factory=dict)
    checks: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SettleResult:
    settled: bool
    in_flight: int | None
    waited_s: float


# -- parsing
def _check_number(text, key):
    """The logged value must be a number of its kind; the field itself stays the string as logged."""
    try:
        if key in _INT_KEYS:
            if not re.fullmatch(r"-?\d+", text):
                raise ValueError
        else:
            float(text[:-1] if text.endswith("s") else text)
    except ValueError:
        raise LogParseError(f"field {key}={text!r} is not a number") from None


def _parse_line(text, offset):
    m = _MARK.search(text)
    if not m:
        return None
    kind, rest = m.group(1), text[m.end():]
    fields = {}
    if kind == "failed":
        f = _FAILED.match(rest)
        if not f:
            raise LogParseError(f"unparseable Request failed line at byte {offset}")
        fields["error"], fields["in_flight"] = f.group("error"), f.group("in_flight")
        rest = f.group("head")
    for tok in rest.split():
        if "=" not in tok:
            continue
        key, value = tok.split("=", 1)
        key = _RENAME.get(key, key)
        if key in _INT_KEYS or key in _FLOAT_KEYS:
            _check_number(value, key)
        fields.setdefault(key, value)
    missing = [k for k in _REQUIRED[kind] if k not in fields]
    if missing:
        raise LogParseError(f"Request {kind} line at byte {offset} lacks {missing}")
    return LogLine(kind, fields, offset)


def parse_log(data: bytes) -> list:
    """Every `Request started / completed / failed` line of `data` (an unterminated final segment is a half-written line
    and is not read). Raises `LogParseError` for a request line that does not parse."""
    out, pos = [], 0
    while True:
        end = data.find(b"\n", pos)
        if end < 0:
            return out
        line = _parse_line(data[pos:end].decode("utf-8", "replace"), pos)
        if line is not None:
            out.append(line)
        pos = end + 1


# -- worker counters
def _summary(snapshot):
    snapshot = snapshot or {}
    return snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else snapshot


def decode_time(snapshot) -> float:
    """The worker's `D` = generated_tokens_total / avg_decode_tok_s from the unrounded values; 0 when the rate is 0."""
    s = _summary(snapshot)
    rate = s.get("avg_decode_tok_s") or 0
    return float(s.get("generated_tokens_total") or 0) / rate if rate > 0 else 0.0


def decode_rate(requests, delta_d):
    """Spec 8: sum(max(generated - 1, 0)) / delta D; None without a positive delta D."""
    if delta_d is None or delta_d <= 0:
        return None
    return sum(max(int(r["generated_tokens"]) - 1, 0) for r in requests if not r.get("error")) / delta_d


# -- engagement
def _is_int(value):
    return type(value) is int


def engagement_problems(requests, arm, *, item=False) -> list:
    """ON: every completed request with >= 2 generated tokens carries the MTP draft counters; OFF: no `draft_*` field. With
    `item=True` (a whole item's requests) an ON item with no request long enough to be judged is `unengaged`, never valid."""
    on, problems = str(arm).lower() == "on", []
    if item and on and not any(not r.get("error") and int(r["generated_tokens"]) >= 2 for r in requests):
        problems.append("unengaged: no request of the item is long enough (>= 2 generated tokens) to be judged")
    for k, r in enumerate(requests):
        if r.get("error"):
            continue
        if not on:
            found = [key for key in DRAFT_KEYS if r.get(key) is not None]
            if found:
                problems.append(f"request {k}: OFF arm but carries {found}")
            continue
        if int(r["generated_tokens"]) < 2:
            continue                                   # listed (see `short_requests`), not judged
        rounds, n, acc = r.get("draft_rounds"), r.get("draft_n"), r.get("draft_n_accepted")
        if not (_is_int(rounds) and rounds >= 1 and _is_int(n) and n >= 1 and _is_int(acc) and 0 <= acc <= n
                and r.get("draft_kind") == "mtp"):
            problems.append(f"request {k}: ON arm, {r['generated_tokens']} tokens, counters rounds={rounds!r} n={n!r} "
                            f"accepted={acc!r} kind={r.get('draft_kind')!r}")
    return problems


def short_requests(requests) -> list:
    """Indexes of the completed requests with <= 1 generated token (counted and listed, not judged)."""
    return [k for k, r in enumerate(requests) if not r.get("error") and int(r["generated_tokens"]) <= 1]


# -- reconciliation
def _draft_value(f, key):
    """A draft counter for the request table: an integer when logged as one, else the string as logged (so that a
    non-integer counter stays visible to `engagement_problems`)."""
    value = f.get(key)
    return int(value) if isinstance(value, str) and re.fullmatch(r"-?\d+", value) else value


def _request_row(line):
    f = line.fields
    if line.kind == "failed":
        return dict(session=None, backend=None, prompt_tokens=None, generated_tokens=None, decode_tok_s=None,
                    draft_rounds=None, draft_n=None, draft_n_accepted=None, draft_kind=None, error=f["error"], elapsed_s=None)
    return dict(session=f.get("session"), backend=f.get("backend"), prompt_tokens=_int(line, "prompt_tokens"),
                generated_tokens=_int(line, "generated_tokens"),
                decode_tok_s=float(f["decode_tok_s"]) if "decode_tok_s" in f else None,
                elapsed_s=float(f["elapsed"].rstrip("s")) if "elapsed" in f else None,       # spec 16.8: the settle bound's input
                draft_rounds=_draft_value(f, "draft_rounds"), draft_n=_draft_value(f, "draft_n"),
                draft_n_accepted=_draft_value(f, "draft_n_accepted"), draft_kind=f.get("draft_kind"), error=None)


class _Checks:
    def __init__(self):
        self.problems, self.checks = [], {}

    def __call__(self, name, ok, detail=""):
        self.checks[name] = dict(ok=bool(ok), detail=detail)
        if not ok:
            self.problems.append(f"{name}: {detail}")
        return bool(ok)


def _serial(lines, check):
    open_, bad = False, []
    for ln in lines:
        if ln.kind == "started":
            if _int(ln, "in_flight") != 1:
                bad.append(f"start at byte {ln.offset} shows in_flight={ln.fields['in_flight']}")
            if open_:
                bad.append(f"start at byte {ln.offset} precedes the previous request's terminal line")
            open_ = True
        else:
            if not open_:
                bad.append(f"{ln.kind} line at byte {ln.offset} has no start")
            open_ = False
    check("serial", not bad, "; ".join(bad))


def _deltas(before, after, C, F, S, check):
    b, a = _summary(before), _summary(after)

    def d(key):
        try:
            return a[key] - b[key]
        except (KeyError, TypeError):
            return None
    want = dict(requests_completed=len(C), requests_started=len(S), requests_failed=len(F),
                prompt_tokens_total=sum(_int(x, "prompt_tokens") for x in C),
                generated_tokens_total=sum(_int(x, "generated_tokens") for x in C))
    got = {k: d(k) for k in want}
    check("worker_deltas", got == want, f"worker delta {got} != log {want}")
    check("started_terminated", len(S) == len(C) + len(F), f"|S|={len(S)} != |C|+|F|={len(C) + len(F)}")


def _reconcile(*, usage, session, lines, before, after, kind, killed, expected, inflight_possible):
    """`kind` = 'completed' | 'kill' | 'dnf'; `expected` = the boundary request count the evidence states."""
    check = _Checks()
    C = [x for x in lines if x.kind == "completed"]
    F = [x for x in lines if x.kind == "failed"]
    S = [x for x in lines if x.kind == "started"]
    n = len(usage)
    _serial(lines, check)
    _deltas(before, after, C, F, S, check)
    check("session_backend", all(x.fields["session"] == session and x.fields["backend"] == BACKEND for x in C),
          f"every completed line must carry session={session!r} backend={BACKEND}; got "
          f"{sorted({(x.fields['session'], x.fields['backend']) for x in C})}")
    prefix = {"completed": "", "kill": "kill_", "dnf": "dnf_"}[kind]
    case = {"": "completed"}.get(prefix, prefix + "boundary")
    unaccounted = len(C) == n + 1 and not F and (kind != "completed")
    inflight_failed = len(F) == 1 and kind != "completed"
    if inflight_failed:
        case = prefix + "inflight_failed"
        check("inflight_evidence", inflight_possible,          # §4.3: a boundary abort / kill with a trailing failed line is systemic
              "a trailing failed line, but the structured evidence says no request was in flight")
        last = lines[-1] if lines else None
        check("failed_line", last is not None and last.kind == "failed" and STREAM_CLOSED in last.fields["error"]
              and len(S) == len(C) + 1,
              f"the single failed line must be the last of the window with error={STREAM_CLOSED} and |S|=|C|+1")
        check("boundary_count", len(C) == expected, f"|C|={len(C)} != the evidence's completed count {expected}")
    elif unaccounted:
        case = prefix + "completed_unaccounted"
        check("unaccounted_inflight", inflight_possible, "no in-flight message in the abort manifest")
        check("unaccounted_count", n == expected, f"request_usage has {n} entries, the evidence states {expected}")
    else:
        check("failed_lines", not F, f"{len(F)} unexpected Request failed line(s) (allowed: none for this outcome)")
        check("boundary_count", len(C) == n == expected,
              f"|C|={len(C)}, len(request_usage)={n}, the evidence states {expected}")
    paired = C[:n]
    bad = [k for k, (x, u) in enumerate(zip(paired, usage))
           if (_int(x, "generated_tokens"), _int(x, "prompt_tokens")) != (u[1], u[2])]
    pairing_ok = not bad and len(C) >= n
    check("pairing", pairing_ok, "" if pairing_ok else
          f"positional pairing fails at position {bad[0] if bad else len(C)}: "
          f"{'tokens differ' if bad else 'count differs'} (|C|={len(C)}, request_usage={n})")
    requests = [_request_row(x) for x in lines if x.kind in ("completed", "failed")]
    delta_d = decode_time(after) - decode_time(before)
    done = [r for r in requests if not r["error"]]
    totals = dict(requests=len(C), prompt_tokens=sum(r["prompt_tokens"] for r in done),
                  generated_tokens=sum(r["generated_tokens"] for r in done), decode_s=delta_d,
                  accepted=sum(r["draft_n_accepted"] for r in done if _is_int(r["draft_n_accepted"])),
                  proposed=sum(r["draft_n"] for r in done if _is_int(r["draft_n"])))
    return ItemReport(ok=not check.problems, case=case, problems=check.problems, requests=requests, totals=totals,
                      checks=check.checks)


def reconcile_item(row, lines, before, after) -> ItemReport:
    """One item's window against its row (spec 4.3): `row` carries `session_id`, `request_usage`, the outcome fields."""
    gate = row.get("gate") or {}
    term = row.get("termination") if isinstance(row.get("termination"), dict) else {}
    at_kill = gate.get("requests_completed_at_kill")
    # structured fields only (never key names): a kill count, `client_inactivity`, an in-flight count at kill or the kill's
    # reason. The probe fills `termination.killed` only inside its kill path, after it recorded the count and the reason; a
    # `killed` list without any of those markers is not a kill, and the item is reconciled as a completed one.
    killed = (at_kill is not None or row.get("nonconv_kind") == "client_inactivity"
              or term.get("in_flight_at_kill") is not None or term.get("reason") is not None)
    usage = [list(u) for u in row.get("request_usage") or []]
    if killed:
        expected = at_kill if at_kill is not None else gate.get("requests_completed")
    else:
        expected = len(usage)
    in_flight = term.get("in_flight_at_kill")                  # the worker's in-flight count when the probe killed (structured evidence)
    inflight_possible = _is_int(in_flight) and in_flight >= 1
    return _reconcile(usage=usage, session=row.get("session_id"), lines=lines, before=before, after=after,
                      kind="kill" if killed else "completed", killed=killed, expected=expected, inflight_possible=inflight_possible)


def reconcile_dnf(abort_manifest, lines, before, after) -> ItemReport:
    """A DNF window (no row) against the abort manifest's `transport_abort.gate.request_usage`,
    `transport_abort.session_id` and `transport_abort.in_flight.message_id` (spec 4.3 DNF rows, 16.1 as the probe writes it)."""
    stamp = abort_manifest.get("transport_abort") or {}
    usage = [list(u) for u in (stamp.get("gate") or {}).get("request_usage") or []]
    return _reconcile(usage=usage, session=stamp.get("session_id"), lines=lines, before=before, after=after, kind="dnf",
                      killed=False, expected=len(usage),
                      inflight_possible=bool((stamp.get("in_flight") or {}).get("in_flight") is True
                                             or (stamp.get("in_flight") or {}).get("message_id") is not None))


# -- A4 window
def _triples(requests):
    return [(r.get("session"), r.get("cached"), r.get("prompt")) for r in requests or []]


def a4_window_problems(lines, a4_receipt, a4_gate) -> list:
    """The A4 window against the A4 run's own evidence (spec 4.3): the 3 `anon:*` requests equal `gate.json`
    (`A6_bare_anonymous.requests`: session, cached, prompt) and the window's own 4-request `ses_*` session equals the A4
    receipt (`turns[*].requests`: session, cached, prompt), request by request in order."""
    C = [x for x in lines if x.kind == "completed"]
    got = lambda sel: [(x.fields["session"], _int(x, "cached_tokens"), _int(x, "prompt_tokens"))  # noqa: E731
                       for x in C if str(x.fields["session"]).startswith(sel)]
    anon, ses = got("anon:"), got("ses_")
    want_ses = _triples([r for t in (a4_receipt or {}).get("turns") or [] for r in t.get("requests") or []])
    want_anon = _triples(((a4_gate or {}).get("A6_bare_anonymous") or {}).get("requests"))
    problems = []
    if anon != want_anon:
        problems.append(f"A4 window: the anon:* requests {anon} differ from gate.json's {want_anon}")
    if ses != want_ses or len({s for s, _c, _p in ses}) > 1:
        problems.append(f"A4 window: the ses_* requests {ses} differ from the A4 receipt's {want_ses} (one session)")
    if len(anon) + len(ses) != len(C):
        problems.append(f"A4 window: {len(C) - len(anon) - len(ses)} completed line(s) of no A4 session")
    if any(x.kind == "failed" for x in lines):
        problems.append("A4 window: a Request failed line")
    return problems


# -- settle
def _pending(data):
    lines = parse_log(data)
    opened = 0
    for ln in lines:
        opened += 1 if ln.kind == "started" else -1
    return max(opened, 0)


def settle(read_metrics, read_log, cursor, *, bound_s, clock, sleep) -> SettleResult:
    """Poll every 2 s until `in_flight == 0` and every `Request started` after `cursor` has its terminal line; not settled
    after `bound_s` (also when the metrics are unreadable). `read_log(cursor)` returns the log bytes after the cursor."""
    t0 = clock()
    while True:
        metrics = read_metrics()
        in_flight = None
        try:
            in_flight = _summary(metrics)["in_flight"]
        except (KeyError, TypeError):
            pass
        if type(in_flight) is not int:
            in_flight = None
        pending = _pending(read_log(cursor))
        waited = clock() - t0
        if in_flight == 0 and pending == 0:
            return SettleResult(True, 0, waited)
        if waited >= bound_s:
            return SettleResult(False, in_flight, waited)
        sleep(SETTLE_POLL_S)
