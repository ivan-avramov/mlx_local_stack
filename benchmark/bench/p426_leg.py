"""P426 B10: the leg wrapper — one Wave-1 leg (or smoke) of the Fable MTP re-certification (`docs/specs/p426-fable-mtp-recert.md`
§2), fail closed.

  .venv-bench/bin/python -m bench.p426_leg --spec <leg.json>      (from benchmark/, inside the frozen worktree)

Pre-leg (refuse → NOT_STARTED, nothing started): destinations absent, the ON registry differs from OFF in exactly the entry's MTP
settings (OFF = the committed registry), target / drafter snapshots match the reviewed pins, power + orphan gate, nothing busy.
Leg: the arm's lean router + worker argv checks (`ChainOps.start_router` / `load`), the 5-minute watcher, the driver. Exit:
router / worker identity unchanged, power re-checked, membership == plan, the engagement gate, the leg's own server-log slice
reconciled exactly (non-empty, started == completed == expected, no failure; every ON request `backend=cached_session` — the
serial model-thread path whose drafter counters are exact under any HTTP overlap, B1 D1 / E1), teardown. Any problem → INVALID; a power failure, a
watcher power receipt or an on-battery interval → the leg's SPEED invalid (quality stands). The receipt is written either way.
"""

import argparse
import collections
import dataclasses
import difflib
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from bench.chain_ops import ChainAbort, argv_flag

MTP_KEYS = ("draft_kind", "draft_model", "mtp_verify_scan")
_REQUEST = re.compile(r"Request (started|completed|failed): (.*)$")


@dataclasses.dataclass
class LegSpec:
    name: str
    arm: str  # "on" | "off"
    kind: str  # "rows" | "reasoning" | "vision"
    model: str
    registry_text: str
    off_registry_text: str
    driver_argv: list
    destinations: list
    rows_path: Path
    planned: list
    receipt_dir: Path
    server_log: Path
    timeout_s: float = 6 * 3600
    mtp_keys: tuple = MTP_KEYS
    row_key: str = "id"
    expected_requests: int = 0
    expected_extra: int = 0  # requests with no row (reasoning's chars-per-token calibration)
    seeds: dict = None  # K4: {row key: {field: planned seed}}
    pins: dict = None  # K2: stack_head, stack_clean, mlx_vlm, mlx_serve, registry_off_sha, registry_on_sha
    cwd: str = None


P426_ON = {  # the exact settings the ON arm adds (the C177 lines restored), pinned independently of the fork rule (H2)
    "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed": {
        "mtp_verify_scan": "joint_v1",
        "draft_kind": "mtp",
        "draft_model": "caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter",
    }
}


def _strict(text):
    """Strict parse (B4 code round 2 H2): CR, duplicate keys and non-YAML raise ValueError."""
    import yaml

    if "\r" in text:
        raise ValueError("CR line ending")

    class Strict(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        keys = [loader.construct_object(k, deep=deep) for k, _ in node.value if k.tag != "tag:yaml.org,2002:merge"]
        dupes = sorted({str(k) for k in keys if keys.count(k) > 1})
        if dupes:
            raise ValueError(f"duplicate registry keys {dupes}")
        return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)

    Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        return yaml.load(text, Loader=Strict) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"not YAML: {exc}") from exc


def _same(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _models(text):
    doc = _strict(text)
    models = doc.get("models") or []
    names = [m.get("name") for m in models]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate model names {sorted({n for n in names if names.count(n) > 1}, key=str)}")
    return dict(zip(names, models)), names, {k: v for k, v in doc.items() if k != "models"}


def registry_delta_problems(on_text, off_text, entry, expected=None):
    """ON == OFF except that ``entry`` gains exactly its pinned MTP settings (``P426_ON``): strict, type-aware, and the text
    delta is exactly those lines added with only comment lines removed (B4 code round 2 H2)."""
    expected = expected if expected is not None else P426_ON.get(entry)
    if not expected:
        return [f"{entry}: no pinned ON settings"]
    try:
        on, on_names, on_top = _models(on_text)
        off, off_names, off_top = _models(off_text)
    except ValueError as exc:
        return [f"registry: {exc}"]
    problems = []
    if not _same(on_top, off_top):
        problems.append("top-level registry settings differ")
    if on_names != off_names:
        problems.append("the arms list different models")
    for name in sorted(set(on) | set(off), key=str):
        if name != entry and not _same(on.get(name), off.get(name)):
            problems.append(f"{name}: settings differ between the arms")
    a, b = on.get(entry), off.get(entry)
    if a is None or b is None:
        return problems + [f"{entry}: missing from an arm's registry"]
    if not any(k in a for k in expected):
        return problems + [f"{entry}: the ON registry carries no MTP settings"]
    for key, value in expected.items():
        if not _same(a.get(key), value):
            problems.append(f"{entry}: ON {key} {a.get(key)!r} != pinned {value!r}")
        if key in b:
            problems.append(f"{entry}: OFF carries {key}")
    rest = {k: v for k, v in a.items() if k not in expected}
    for key in sorted(set(rest) | set(b)):
        if not _same(rest.get(key), b.get(key)):
            problems.append(f"{entry}: {key} differs between the arms")
    delta = [d for d in difflib.ndiff(off_text.splitlines(), on_text.splitlines()) if d[:2] in ("- ", "+ ")]
    added = sorted(d[2:].strip() for d in delta if d.startswith("+ "))
    removed = [d[2:] for d in delta if d.startswith("- ")]
    if added != sorted(f"{k}: {v}" for k, v in expected.items()):
        problems.append(f"{entry}: added lines {added} are not exactly the pinned MTP lines")
    if any(not line.lstrip().startswith("#") for line in removed):
        problems.append(f"{entry}: the ON text removes a non-comment line")
    return problems


def destination_problems(paths):
    return [f"destination exists: {p}" for p in paths if Path(p).exists()]


def read_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict) and isinstance(row.get("record"), dict):  # a reasoning journal rung
            rows.extend(row["record"].get("rows") or [])
        else:
            rows.append(row)
    return rows


def membership_problems(planned, rows, key="id"):
    got = [r.get(key) for r in rows]
    problems = []
    if len(got) != len(set(got)):
        problems.append(f"duplicate rows {sorted({g for g in got if got.count(g) > 1}, key=str)}")
    if set(got) != set(planned):
        problems.append(
            f"rows != plan: missing {sorted(set(planned) - set(got), key=str)}, extra {sorted(set(got) - set(planned), key=str)}"
        )
    return problems


def _draft_problem(arm, d):
    if arm == "on":
        if not isinstance(d, dict):
            return "missing draft telemetry"
        n, acc = d.get("draft_n"), d.get("draft_n_accepted")
        if d.get("draft_kind") != "mtp":
            return f"draft_kind {d.get('draft_kind')!r}"
        if not (isinstance(d.get("draft_rounds"), int) and d["draft_rounds"] > 0):
            return f"draft_rounds {d.get('draft_rounds')!r}"
        if not (isinstance(n, int) and n > 0 and isinstance(acc, int) and 0 <= acc <= n):
            return f"draft_n {n!r} / accepted {acc!r}"
        return None
    if isinstance(d, dict) and any(v is not None for v in d.values()):
        return f"OFF row carries draft activity {d}"
    return None


def engagement_problems(arm, rows, key="id"):
    """S3: ON — every row (and a vision row's second turn) engaged with sane counters; OFF — no draft activity."""
    problems = []
    for row in rows:
        for label, d in (("", row.get("draft")), (" turn2", (row.get("turn2") or {}).get("draft", None))):
            if label and "turn2" not in row:
                continue
            why = _draft_problem(arm, d)
            if why:
                problems.append(f"{row.get(key)}{label}: {why}")
    return problems


def log_problems(lines, arm, expected):
    """B1 code round 2 E1: the leg's own server-log slice, fail closed — ``(problems, stats)``."""
    stats = dict(started=0, completed=0, failed=0, overlapping=0)
    not_cached = 0
    for line in lines:
        m = _REQUEST.search(line)
        if not m:
            continue
        kind, rest = m.groups()
        stats[kind] += 1
        flight = re.search(r"in_flight=(\d+)", rest)
        if kind == "started" and flight and int(flight.group(1)) > 1:
            stats["overlapping"] += 1
        if kind == "completed" and "backend=cached_session" not in rest:
            not_cached += 1
    problems = []
    if not any(stats.values()):
        return ["no server log records in the leg window"], stats
    if stats["started"] != stats["completed"]:
        problems.append(f"{stats['started']} started != {stats['completed']} completed")
    if stats["failed"]:
        problems.append(f"{stats['failed']} failed request(s)")
    if stats["started"] != expected:
        problems.append(f"{stats['started']} requests, expected {expected}")
    if arm == "on" and not_cached:
        problems.append(f"{not_cached} ON request(s) not backend=cached_session (drafter counters not exact)")
    return problems, stats


TICK_S = 300


def watch_problems(watch, start, end):
    """G3: the watcher's own report — absent, exited early, a power failure, or fewer ticks than the leg's span minus 10 min
    allows — invalidates the leg's speed (a crashed watcher never reads as 'no power failure')."""
    if not watch:
        return ["no watcher report"]
    problems = []
    if watch.get("power_failure"):
        problems.append(f"watcher power failure at {watch['power_failure'].get('first_failure_at')}")
    if watch.get("exited_early"):
        problems.append("watcher exited early")
    fmt = "%Y-%m-%d %H:%M:%S"
    span = (time.mktime(time.strptime(end, fmt)) - time.mktime(time.strptime(start, fmt))) if start and end else 0
    need = max(0, int((span - 2 * TICK_S) // TICK_S))
    if (watch.get("ticks") or 0) < need:
        problems.append(f"watcher ticks {watch.get('ticks')} < {need} for a {span:.0f} s leg")
    return problems


def model_argv_problems(cmdline, registry_text, model):
    """``--model`` is the registry's; M2: the predictor flags are EXACTLY the arm's (ON: --draft-kind mtp, the entry's
    --draft-model and --mtp-verify-scan; OFF: none of them, --draft-kind at most none / off)."""
    entry = _models(registry_text)[0].get(model) or {}
    toks = (cmdline or "").split()
    problems = []
    got = argv_flag(toks, "--model")
    if got != [entry.get("hf_path")]:
        problems.append(f"worker --model {got} != registry {entry.get('hf_path')!r}")
    if entry.get("draft_kind") == "mtp":
        scan = entry.get("mtp_verify_scan") or ""
        want = {"--draft-kind": ["mtp"], "--draft-model": [entry.get("draft_model")],
                "--mtp-verify-scan": [] if scan in ("", "per_query") else [scan]}
    else:
        want = {"--draft-model": [], "--mtp-verify-scan": []}
        kinds = argv_flag(toks, "--draft-kind")
        if kinds not in ([], ["none"], ["off"]):
            problems.append(f"OFF worker --draft-kind {kinds}")
    for flag, value in want.items():
        if argv_flag(toks, flag) != value:
            problems.append(f"worker {flag} {argv_flag(toks, flag)} != the arm's {value}")
    return problems


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


PIN_KEYS = ("stack_head", "stack_clean", "mlx_vlm", "mlx_serve", "frozen_sha")


def pin_problems(state, spec):
    """K2: the frozen build (stack HEAD + clean tracked tree + both submodules) and both registry texts, before anything
    starts."""
    pins = spec.pins or {}
    problems = [f"{k}: {state.get(k)!r} != pinned {pins.get(k)!r}" for k in PIN_KEYS if state.get(k) != pins.get(k)]
    if sha256_text(spec.off_registry_text) != pins.get("registry_off_sha"):
        problems.append("registry_off_sha: the committed registry is not the pinned one")
    if spec.arm == "on" and sha256_text(spec.registry_text) != pins.get("registry_on_sha"):
        problems.append("registry_on_sha: the ON overlay is not the pinned one")
    return problems


_COMPLETED = re.compile(r"Request completed: .*?prompt_tokens=(\d+)")
_DRAFT = re.compile(r"draft_n=(\d+) draft_n_accepted=(\d+)")


def _row_records(rows):
    recs = []
    for r in rows:
        for part in (r, r.get("turn2")) if "turn2" in r else (r,):
            d = (part or {}).get("draft") or {}
            recs.append((part.get("prompt_tokens"), d.get("draft_n"), d.get("draft_n_accepted")))
    return recs


_SESSION = re.compile(r"Request completed: .*? session=(\S+) .*?prompt_tokens=(\d+)")


def request_match_problems(rows, lines, extra_ids):
    """K5: every row's request(s) carry a session id (MLX_BENCH_SESSION_PREFIX) that appears on exactly one completed log
    record whose prompt tokens and draft counters equal the row's; the logged ids without a row are exactly ``extra_ids``
    (the reasoning calibration request, named in its journal sidecar)."""
    logged, problems = {}, []
    for line in lines:
        m = _SESSION.search(line)
        if not m:
            continue
        d = _DRAFT.search(line)
        rec = (int(m.group(2)), *((int(d.group(1)), int(d.group(2))) if d else (None, None)))
        if m.group(1) in logged:
            problems.append(f"session {m.group(1)} logged twice")
        logged[m.group(1)] = rec
    seen = set()
    for r in rows:
        for part in (r, r.get("turn2")) if "turn2" in r else (r,):
            part = part or {}
            sid = part.get("session_id")
            d = part.get("draft") or {}
            want = (part.get("prompt_tokens"), d.get("draft_n"), d.get("draft_n_accepted"))
            if not sid:
                problems.append(f"{r.get('id', r.get('seed'))}: a request without a session id")
                continue
            if sid in seen:
                problems.append(f"session {sid} on two rows")
            seen.add(sid)
            if sid not in logged:
                problems.append(f"{sid}: no log record")
            elif logged[sid] != want:
                problems.append(f"{sid}: log record {logged[sid]} differs from the row {want}")
    leftover = set(logged) - seen
    if leftover != set(extra_ids):
        problems.append(f"logged request(s) without a row {sorted(leftover)} != the named extras {sorted(extra_ids)}")
    return problems


def extra_ids_for(spec):
    """The named row-less requests of a leg: for reasoning, the calibration request recorded in the journal sidecar."""
    if not spec.expected_extra:
        return [], []
    sidecar = Path(f"{spec.rows_path}.provenance.json")
    try:
        sid = json.loads(sidecar.read_text()).get("calibration_session_id")
    except (OSError, ValueError) as exc:
        return [], [f"extra requests: {sidecar.name} unreadable ({type(exc).__name__})"]
    if not sid:
        return [], [f"extra requests: no calibration_session_id in {sidecar.name}"]
    return [sid], []


_POWER_EVENT = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4} .*Using (AC|Batt)\b")


def power_history_problems(returncode, text):
    """K6: the ``pmset -g log`` history must be read, contain at least one well-formed power-source event and no malformed
    one (a line naming a source without the full timestamp grammar)."""
    if returncode != 0:
        return [f"pmset -g log exited {returncode}"]
    events = bad = 0
    for line in (text or "").splitlines():
        if "Using AC" in line or "Using Batt" in line:
            if _POWER_EVENT.match(line):
                events += 1
            else:
                bad += 1
    problems = []
    if not events:
        problems.append("pmset -g log: no well-formed power-source event")
    if bad:
        problems.append(f"pmset -g log: {bad} malformed power-source line(s)")
    return problems


def _receipt_path(spec):
    return Path(spec.receipt_dir) / f"{spec.name}.receipt.json"


def _write(spec, receipt):
    """L1: atomic, and never over an existing receipt (a refusal / rerun goes beside it as ``.refused-<epoch>``)."""
    import os
    import time

    d = Path(spec.receipt_dir)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{spec.name}.{os.getpid()}.{time.time_ns()}.tmp"
    tmp.write_text(json.dumps(receipt, indent=1, default=str) + "\n")
    path = _receipt_path(spec)
    try:
        while True:
            try:
                os.link(tmp, path)  # atomic, and fails if the name exists (never replaces a published receipt)
                break
            except FileExistsError:
                path = d / f"{spec.name}.refused-{time.time_ns()}.receipt.json"
    finally:
        tmp.unlink(missing_ok=True)
    return dict(receipt, _path=str(path))


def _guard_pre(spec, ops, repo_state, pins_check):
    pre = []
    if _receipt_path(spec).exists():
        pre.append(f"receipt exists: {_receipt_path(spec)} (a leg is run once)")
    state = repo_state()
    pre += pin_problems(state, spec) + destination_problems(spec.destinations)
    if spec.arm == "on":
        pre += registry_delta_problems(spec.registry_text, spec.off_registry_text, spec.model)
    elif spec.registry_text != spec.off_registry_text:
        pre.append("the OFF arm must serve the committed registry verbatim")
    pre += pins_check(spec.model, spec.arm)
    if not ops.power_ok():
        pre.append("power / orphan gate failed at entry")
    busy = ops.busy_procs()
    if busy:
        pre.append("busy processes: " + "; ".join(busy)[:400])
    return pre, state


def _refuse(spec, receipt, exc):
    """K1: an exception or interrupt before the leg started is a receipted refusal (interrupts re-raised by the caller)."""
    return _write(spec, dict(receipt, verdict="NOT_STARTED", problems=[f"pre-check failed: {type(exc).__name__}: {exc}"],
                             speed_valid=False))


def _speed_from_power(battery_intervals, start, end):
    try:
        intervals, power_problems = battery_intervals(start, end)
    except Exception as exc:  # noqa: BLE001 — K6: an unreadable power history is a speed problem
        intervals, power_problems = [], [f"pmset -g log failed: {type(exc).__name__}: {exc}"]
    return [f"battery interval {a} -> {b}" for a, b in intervals] + list(power_problems)


def run_leg(spec, ops, *, run_driver, pins_check, watcher, battery_intervals, clock, repo_state):
    """One leg, fail closed; a receipt is written on EVERY path (K1) and an interrupt is re-raised after it."""
    from bench.p426_plan import seed_problems

    receipt = dict(name=spec.name, arm=spec.arm, kind=spec.kind, model=spec.model, problems=[], speed_problems=[],
                   pins=spec.pins)
    try:
        pre, receipt["state"] = _guard_pre(spec, ops, repo_state, pins_check)
        receipt["pre_state"] = ops.start_state()
    except BaseException as exc:  # noqa: BLE001
        refused = _refuse(spec, receipt, exc)
        if not isinstance(exc, Exception):
            raise
        return refused
    if pre:
        return _write(spec, dict(receipt, verdict="NOT_STARTED", problems=pre, speed_valid=False))
    problems, speed = [], []
    start = clock()
    receipt["started"] = start
    stop_watch, interrupted, watch = None, None, None
    served = sha256_text(spec.registry_text)
    try:
        receipt["router_pid"] = ops.start_router()
        if getattr(ops, "router_config_sha", None) != served:  # K2: the router started on the pinned file
            problems.append(f"served config {getattr(ops, 'router_config_sha', None)} != pinned {served}")
        ident = ops.load(spec.model)
        receipt["worker"] = ident
        problems += model_argv_problems(ident.get("cmdline"), spec.registry_text, spec.model)
        stop_watch = watcher(spec)
        log = Path(spec.server_log)
        offset = log.stat().st_size if log.exists() else 0  # E1: only this leg's records count
        env = dict(ops.env_base(), MLX_BENCH_SESSION_PREFIX=f"p426-{spec.name}")  # K5: per-request identity
        try:
            rc = run_driver(spec.driver_argv, env, spec.timeout_s, spec.cwd)
        except subprocess.TimeoutExpired as exc:  # G1: receipted, and every post-driver check still runs
            rc = None
            problems.append(f"driver timed out after {exc.timeout} s")
        tail = log.read_bytes()[offset:].decode("utf-8", errors="replace") if log.exists() else ""
        lines = tail.splitlines()
        log_found, receipt["log"] = log_problems(lines, spec.arm, spec.expected_requests)
        problems += log_found
        if rc not in (0, None):
            problems.append(f"driver exit {rc}")
        if not ops.router_ok():
            problems.append("router identity / served config changed during the leg")
        now = ops.worker_ident(spec.model)
        if not now or (now["pid"], now["create_time"]) != (ident["pid"], ident["create_time"]):
            problems.append(f"worker identity changed: {ident.get('pid')} -> {now}")
        rows = read_rows(spec.rows_path)
        problems += membership_problems(spec.planned, rows, spec.row_key)
        problems += engagement_problems(spec.arm, rows, spec.row_key)
        problems += seed_problems(spec.seeds or {}, rows, spec.row_key)
        extras, extra_problems = extra_ids_for(spec)
        problems += extra_problems + request_match_problems(rows, lines, extras)
        if not ops.power_ok():
            speed.append("power / orphan gate failed at exit")
    except BaseException as exc:  # noqa: BLE001 — K1: everything is receipted; interrupts re-raised below
        problems.append(f"{type(exc).__name__}: {exc}")
        if not isinstance(exc, Exception):
            interrupted = exc
    finally:
        if stop_watch:
            try:
                watch = stop_watch()
            except BaseException as exc:  # noqa: BLE001
                problems.append(f"watcher stop failed: {type(exc).__name__}: {exc}")
                interrupted = interrupted or (exc if not isinstance(exc, Exception) else None)
        try:  # G2: a teardown that fails or leaves :8000 bound invalidates the leg
            torn = ops.stop_stack()
            if torn not in (0, None):
                problems.append(f"teardown failed: stop_stack rc {torn}")
        except BaseException as exc:  # noqa: BLE001
            problems.append(f"teardown failed: {type(exc).__name__}: {exc}")
            interrupted = interrupted or (exc if not isinstance(exc, Exception) else None)
        end = clock()
        receipt.update(ended=end, watch=watch)
        try:  # K2: the frozen build must still be the one the leg started on
            exit_state = repo_state()
            if exit_state != receipt.get("state"):
                problems.append(f"build drift during the leg: {receipt.get('state')} -> {exit_state}")
        except BaseException as exc:  # noqa: BLE001
            problems.append(f"exit build check failed: {type(exc).__name__}: {exc}")
            interrupted = interrupted or (exc if not isinstance(exc, Exception) else None)
        try:  # K1: an interrupt during the power inspection still leads to the receipt
            speed += watch_problems(watch, start, end) + _speed_from_power(battery_intervals, start, end)
        except BaseException as exc:  # noqa: BLE001
            speed.append(f"power inspection failed: {type(exc).__name__}: {exc}")
            interrupted = interrupted or (exc if not isinstance(exc, Exception) else None)
        verdict = "INVALID" if problems else "VALID"
        final = _write(spec, dict(receipt, verdict=verdict, problems=problems, speed_problems=speed,
                                  speed_valid=verdict == "VALID" and not speed))
    if interrupted is not None:
        raise interrupted
    return final


def run_qualify_leg(spec, ops, *, run_driver, pins_check, battery_intervals, clock, repo_state, out_dir):
    """K3: the M1 leg — qualify runs in-process (its own worker, no router); the same pre-check, power and receipt rules,
    evidence = its report (the planned arm COMPLETED)."""
    from bench.p426_plan import qualify_problems

    receipt = dict(name=spec.name, arm=spec.arm, kind="qualify", model=spec.model, problems=[], speed_problems=[],
                   pins=spec.pins)
    try:
        pre, receipt["state"] = _guard_pre(spec, ops, repo_state, pins_check)
    except BaseException as exc:  # noqa: BLE001
        refused = _refuse(spec, receipt, exc)
        if not isinstance(exc, Exception):
            raise
        return refused
    if pre:
        return _write(spec, dict(receipt, verdict="NOT_STARTED", problems=pre, speed_valid=False))
    problems, speed, interrupted = [], [], None
    start = clock()
    try:
        rc = run_driver(spec.driver_argv, dict(ops.env_base()), spec.timeout_s, spec.cwd)
        if rc != 0:
            problems.append(f"qualify exit {rc}")
        report_path = Path(out_dir) / "report.json"
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        receipt["report"] = {k: report.get(k) for k in ("predictor", "entries", "reviewed_head", "registry_sha256")}
        problems += qualify_problems(report, spec.model, spec.arm)
        if ops.busy_procs():
            speed.append("busy processes at exit")
    except BaseException as exc:  # noqa: BLE001
        problems.append(f"{type(exc).__name__}: {exc}")
        if not isinstance(exc, Exception):
            interrupted = exc
    finally:
        end = clock()
        try:
            if repo_state() != receipt.get("state"):
                problems.append("build drift during the leg")
            speed += _speed_from_power(battery_intervals, start, end)
        except BaseException as exc:  # noqa: BLE001
            problems.append(f"exit checks failed: {type(exc).__name__}: {exc}")
            interrupted = interrupted or (exc if not isinstance(exc, Exception) else None)
        verdict = "INVALID" if problems else "VALID"
        final = _write(spec, dict(receipt, started=start, ended=end, verdict=verdict, problems=problems,
                                  speed_problems=speed, speed_valid=verdict == "VALID" and not speed))
    if interrupted is not None:
        raise interrupted
    return final


# ------------------------------------------------------------------ the real effects (CLI)
def _real_driver(argv, env, timeout, cwd=None):
    return subprocess.run(argv, env=env, timeout=timeout, stdin=subprocess.DEVNULL, cwd=cwd).returncode


def _repo_state_for(repo):
    def git(*a, cwd=repo):
        return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, timeout=60).stdout.strip()

    def state():
        return dict(
            stack_head=git("rev-parse", "HEAD"),
            stack_clean=git("status", "--porcelain", "--untracked-files=no") == "",
            mlx_vlm=git("rev-parse", "HEAD", cwd=Path(repo) / "src" / "mlx-vlm"),
            mlx_serve=git("rev-parse", "HEAD", cwd=Path(repo) / "src" / "mlx-serve"),
        )

    return state


def _pins_check_for(fork_dev):
    sys.path.insert(0, str(fork_dev))
    from p369_phase2 import orchestrate

    pins = orchestrate.load_pins()

    def check(model, arm):
        entry = pins.get(model)
        if entry is None:
            return [f"{model}: no reviewed pins"]
        target = orchestrate.weights_record(entry["target"]["hf_path"])
        drafter = orchestrate.weights_record(entry["drafter"]["hf_path"]) if arm == "on" else entry["drafter"]
        return orchestrate.pins_problems(pins, model, target, drafter)

    return check


def _watcher_for(repo, total, out_dir, interval_s=None, startup_s=10.0):
    """P444: the watcher runs as a script from `benchmark/m1/`, so `bench` is importable only via PYTHONPATH; it tracks THIS
    leg process by pid (it is the watcher's parent, and macOS `pgrep` excludes ancestors); one that exits within `startup_s`
    raises — the leg is receipted INVALID before the driver runs."""
    import os

    def start(spec):
        receipt = Path(out_dir) / f"{spec.name}.power.json"
        bench_dir = str(Path(repo) / "benchmark")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in (bench_dir, os.environ.get("PYTHONPATH")) if p))
        proc = subprocess.Popen(
            [str(Path(repo) / ".venv-bench/bin/python"), str(Path(repo) / "benchmark/m1/bench_watch.py"),
             "--models", spec.model, "--bench", spec.kind, "--total", str(total),
             "--driver-pid", str(os.getpid()), "--out", str(Path(out_dir) / f"{spec.name}.watch.log"),
             "--rows-file", str(spec.rows_path), "--power-receipt", str(receipt), "--flat-escalate", "8",
             *(["--interval", str(interval_s)] if interval_s else [])],
            stdin=subprocess.DEVNULL, start_new_session=True, env=env, cwd=bench_dir,
        )
        deadline = time.monotonic() + startup_s
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"watcher exited at start (rc {proc.returncode})")
            time.sleep(0.25)

        def stop():
            exited_early = proc.poll() is not None
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
            log = Path(out_dir) / f"{spec.name}.watch.log"
            ticks = sum(1 for line in log.read_text().splitlines() if line.startswith("===== ") and "driver=" in line) if log.exists() else 0
            return dict(
                power_failure=json.loads(receipt.read_text()) if receipt.exists() else None,
                exited_early=exited_early,
                ticks=ticks,
            )

        return stop

    return start


FROZEN = "p426/frozen.json"  # K2: the one frozen-build record, under $STACK_WORKDIR (written once when S is cut)


def main(argv=None):
    """``--axis --arm (--block N | --smoke) --stack-root <frozen worktree> --workdir <STACK_WORKDIR> --registry-on <overlay>
    --receipt-dir <dir>``: the leg is PLANNED from ids.json (K3) and pinned to ``<workdir>/p426/frozen.json`` (K2); a failure
    before the leg starts still leaves a NOT_STARTED receipt (K1)."""
    import os
    import time

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--axis", required=True)
    ap.add_argument("--arm", required=True, choices=("off", "on"))
    sel = ap.add_mutually_exclusive_group(required=True)
    sel.add_argument("--block", type=int)
    sel.add_argument("--smoke", action="store_true")
    ap.add_argument("--stack-root", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--registry-on", required=True, help="the ON overlay written by bench.p426_overlay")
    ap.add_argument("--receipt-dir", required=True)
    ap.add_argument("--timeout-s", type=float, default=6 * 3600)
    args = ap.parse_args(argv)
    name = f"{args.axis}-p426-{args.arm}-{'smoke' if args.smoke else f'b{args.block}'}"
    stub = LegSpec(name=name, arm=args.arm, kind=args.axis, model=None, registry_text="", off_registry_text="",
                   driver_argv=[], destinations=[], rows_path=None, planned=[], receipt_dir=Path(args.receipt_dir),
                   server_log=None)
    try:
        from bench import p426_plan
        from bench.chain_ops import ChainOps

        configured = os.environ.get("STACK_WORKDIR")
        if not configured or Path(configured).resolve() != Path(args.workdir).resolve():
            raise ValueError(f"--workdir {args.workdir} is not $STACK_WORKDIR ({configured})")
        repo = Path(args.stack_root).resolve()
        frozen_path = Path(args.workdir).resolve() / FROZEN
        frozen_bytes = frozen_path.read_bytes()  # K2: ONE snapshot, parsed and hashed
        pins = dict(json.loads(frozen_bytes), frozen_sha=hashlib.sha256(frozen_bytes).hexdigest())
        plan = p426_plan.plan_leg(repo, args.axis, args.arm, args.block, smoke=args.smoke, workdir=args.workdir,
                                  reviewed_head=pins.get("mlx_vlm"))
        off_text = (repo / "main_models.yaml").read_bytes().decode("utf-8")
        on_path = Path(args.registry_on)
        spec = LegSpec(
            name=name, arm=args.arm, kind=args.axis, model=plan["entry"],
            registry_text=on_path.read_bytes().decode("utf-8") if args.arm == "on" else off_text,
            off_registry_text=off_text, driver_argv=plan["driver_argv"],
            destinations=p426_plan.existing_outputs(plan) + ([plan["rows_path"]] if plan["rows_path"] else []),
            rows_path=plan["rows_path"], planned=plan["planned"], receipt_dir=Path(args.receipt_dir),
            server_log=repo / "logs/mlx_vlm.log", timeout_s=args.timeout_s, row_key=plan["row_key"],
            expected_requests=plan["expected_requests"], expected_extra=plan["expected_extra"], seeds=plan["seeds"],
            pins=pins, cwd=plan["cwd"],
        )
        log_path = Path(args.receipt_dir) / f"{name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        def log(msg):
            with log_path.open("a") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

        registry = str(on_path) if args.arm == "on" else str(repo / "main_models.yaml")
        ops = ChainOps(repo, Path(args.workdir), registry, log, predictor="mtp" if args.arm == "on" else "off",
                       out_root=Path(args.receipt_dir))
        fork_dev = repo / "src" / "mlx-vlm" / "dev"  # K2: the frozen build's own harness, never a sibling checkout
        sys.path.insert(0, str(fork_dev))
        from p369_phase2 import qualify

        def battery(start, end):
            out = subprocess.run(["pmset", "-g", "log"], capture_output=True, text=True, timeout=120)
            problems = power_history_problems(out.returncode, out.stdout)  # K6: strict grammar
            epoch = [time.mktime(time.strptime(x, "%Y-%m-%d %H:%M:%S")) for x in (start, end)]
            return (qualify.battery_intervals(out.stdout, *epoch) if not problems else []), problems

        base_state = _repo_state_for(repo)

        def repo_state():  # K2: the frozen record's current bytes are part of the build identity, at entry and exit
            return dict(base_state(), frozen_sha=hashlib.sha256(frozen_path.read_bytes()).hexdigest())

        common = dict(run_driver=_real_driver, pins_check=_pins_check_for(fork_dev), battery_intervals=battery,
                      clock=lambda: time.strftime("%Y-%m-%d %H:%M:%S"), repo_state=repo_state)
    except BaseException as exc:  # noqa: BLE001 — K1: planning / loading failures are receipted too
        _refuse(stub, dict(name=name, arm=args.arm, kind=args.axis, problems=[], speed_problems=[]), exc)
        if not isinstance(exc, Exception):
            raise
        print(f"[p426_leg] NOT_STARTED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if plan["kind"] == "qualify":
        receipt = run_qualify_leg(spec, ops, out_dir=plan["out_dir"], **common)
    else:
        receipt = run_leg(spec, ops, watcher=_watcher_for(repo, len(spec.planned), args.receipt_dir), **common)
    print(json.dumps({k: receipt.get(k) for k in ("name", "verdict", "speed_valid", "problems", "speed_problems")}, indent=1))
    return 0 if receipt["verdict"] == "VALID" else 1


if __name__ == "__main__":
    sys.exit(main())
