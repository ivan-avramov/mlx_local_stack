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
import dataclasses
import difflib
import json
import re
import subprocess
import sys
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


def _models(text):
    import yaml

    doc = yaml.safe_load(text) or {}
    return {m.get("name"): m for m in doc.get("models") or []}, {k: v for k, v in doc.items() if k != "models"}


def registry_delta_problems(on_text, off_text, entry, keys=MTP_KEYS):
    """ON == OFF except that ``entry`` gains exactly ``keys`` (and nothing else changes, in settings and in lines)."""
    on, on_top = _models(on_text)
    off, off_top = _models(off_text)
    problems = []
    if on_top != off_top:
        problems.append("top-level registry settings differ")
    for name in sorted(set(on) | set(off)):
        if name == entry:
            continue
        if on.get(name) != off.get(name):
            problems.append(f"{name}: settings differ between the arms")
    a, b = on.get(entry), off.get(entry)
    if a is None or b is None:
        return problems + [f"{entry}: missing from an arm's registry"]
    added = {k for k in a if k not in b}
    if not added:
        return problems + [f"{entry}: the ON registry carries no MTP settings"]
    for key in sorted(set(keys) - added):
        problems.append(f"{entry}: ON lacks {key}")
    for key in sorted(added - set(keys)):
        problems.append(f"{entry}: ON adds non-MTP setting {key}")
    for key in sorted(k for k in b if a.get(k) != b.get(k)):
        problems.append(f"{entry}: {key} differs between the arms")
    changed = [d for d in difflib.ndiff(off_text.splitlines(), on_text.splitlines()) if d[:2] in ("- ", "+ ")]
    if not problems and len(changed) != 2 * len(keys):
        problems.append(f"{entry}: {len(changed)} changed lines, expected {2 * len(keys)}")
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


def model_argv_problems(cmdline, registry_text, model):
    entry = _models(registry_text)[0].get(model) or {}
    got = argv_flag((cmdline or "").split(), "--model")
    return [] if got == [entry.get("hf_path")] else [f"worker --model {got} != registry {entry.get('hf_path')!r}"]


def _write(spec, receipt):
    Path(spec.receipt_dir).mkdir(parents=True, exist_ok=True)
    path = Path(spec.receipt_dir) / f"{spec.name}.receipt.json"
    path.write_text(json.dumps(receipt, indent=1, default=str) + "\n")
    return receipt


def run_leg(spec, ops, *, run_driver, pins_check, watcher, battery_intervals, clock):
    receipt = dict(name=spec.name, arm=spec.arm, kind=spec.kind, model=spec.model, problems=[], speed_problems=[])
    pre = destination_problems(spec.destinations)
    if spec.arm == "on":
        pre += registry_delta_problems(spec.registry_text, spec.off_registry_text, spec.model, spec.mtp_keys)
    elif spec.registry_text != spec.off_registry_text:
        pre.append("the OFF arm must serve the committed registry verbatim")
    pre += pins_check(spec.model, spec.arm)
    if not ops.power_ok():
        pre.append("power / orphan gate failed at entry")
    busy = ops.busy_procs()
    if busy:
        pre.append("busy processes: " + "; ".join(busy)[:400])
    receipt["pre_state"] = ops.start_state()
    if pre:
        return _write(spec, dict(receipt, verdict="NOT_STARTED", problems=pre, speed_valid=False))
    problems, speed = [], []
    start = clock()
    receipt["started"] = start
    stop_watch = None
    try:
        receipt["router_pid"] = ops.start_router()
        ident = ops.load(spec.model)
        receipt["worker"] = ident
        problems += model_argv_problems(ident.get("cmdline"), spec.registry_text, spec.model)
        stop_watch = watcher(spec)
        log = Path(spec.server_log)
        offset = log.stat().st_size if log.exists() else 0  # E1: only this leg's records count
        rc = run_driver(spec.driver_argv, ops.env_base(), spec.timeout_s)
        tail = log.read_bytes()[offset:].decode("utf-8", errors="replace") if log.exists() else ""
        log_found, receipt["log"] = log_problems(tail.splitlines(), spec.arm, spec.expected_requests)
        problems += log_found
        if rc != 0:
            problems.append(f"driver exit {rc}")
        if not ops.router_ok():
            problems.append("router identity / served config changed during the leg")
        now = ops.worker_ident(spec.model)
        if not now or (now["pid"], now["create_time"]) != (ident["pid"], ident["create_time"]):
            problems.append(f"worker identity changed: {ident.get('pid')} -> {now}")
        rows = read_rows(spec.rows_path)
        problems += membership_problems(spec.planned, rows, spec.row_key)
        problems += engagement_problems(spec.arm, rows, spec.row_key)
        if not ops.power_ok():
            speed.append("power / orphan gate failed at exit")
    except ChainAbort as exc:
        problems.append(str(exc))
    finally:
        power_receipt = stop_watch() if stop_watch else None
        if power_receipt:
            speed.append(f"watcher power failure at {power_receipt.get('first_failure_at')}")
        ops.stop_stack()
    end = clock()
    receipt["ended"] = end
    speed += [f"battery interval {a} -> {b}" for a, b in battery_intervals(start, end)]
    verdict = "INVALID" if problems else "VALID"
    return _write(
        spec,
        dict(receipt, verdict=verdict, problems=problems, speed_problems=speed, speed_valid=verdict == "VALID" and not speed),
    )


# ------------------------------------------------------------------ the real effects (CLI)
def _real_driver(argv, env, timeout):
    return subprocess.run(argv, env=env, timeout=timeout, stdin=subprocess.DEVNULL).returncode


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


def _watcher_for(repo, total, out_dir):
    def start(spec):
        receipt = Path(out_dir) / f"{spec.name}.power.json"
        proc = subprocess.Popen(
            [str(Path(repo) / ".venv-bench/bin/python"), str(Path(repo) / "benchmark/m1/bench_watch.py"),
             "--models", spec.model, "--bench", spec.kind, "--total", str(total),
             "--driver-pattern", "p426_leg", "--out", str(Path(out_dir) / f"{spec.name}.watch.log"),
             "--rows-file", str(spec.rows_path), "--power-receipt", str(receipt), "--flat-escalate", "8"],
            stdin=subprocess.DEVNULL, start_new_session=True,
        )

        def stop():
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
            return json.loads(receipt.read_text()) if receipt.exists() else None

        return stop

    return start


def main(argv=None):
    import time

    from bench.chain_ops import ChainOps

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", required=True)
    args = ap.parse_args(argv)
    doc = json.loads(Path(args.spec).read_text())
    repo, workdir = Path(doc["repo"]), Path(doc["workdir"])
    spec = LegSpec(
        name=doc["name"], arm=doc["arm"], kind=doc["kind"], model=doc["model"],
        registry_text=Path(doc["registry"]).read_text(), off_registry_text=(repo / "main_models.yaml").read_text(),
        driver_argv=doc["driver_argv"], destinations=[Path(p) for p in doc["destinations"]],
        rows_path=Path(doc["rows_path"]), planned=doc["planned"], receipt_dir=Path(doc["receipt_dir"]),
        server_log=repo / "logs/mlx_vlm.log", timeout_s=float(doc.get("timeout_s", 6 * 3600)),
        row_key=doc.get("row_key", "id"), expected_requests=int(doc["expected_requests"]),
    )
    log_path = Path(doc["receipt_dir"]) / f"{spec.name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(msg):
        with log_path.open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

    ops = ChainOps(repo, workdir, doc["registry"], log, predictor="mtp" if spec.arm == "on" else "off",
                   out_root=Path(doc["receipt_dir"]))
    sys.path.insert(0, str(Path(doc["fork_dev"])))
    from p369_phase2 import qualify

    def battery(start, end):
        out = subprocess.run(["pmset", "-g", "log"], capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            return [("pmset -g log unreadable", "")]
        epoch = [time.mktime(time.strptime(x, "%Y-%m-%d %H:%M:%S")) for x in (start, end)]
        return qualify.battery_intervals(out.stdout, *epoch)

    receipt = run_leg(
        spec, ops, run_driver=_real_driver, pins_check=_pins_check_for(doc["fork_dev"]),
        watcher=_watcher_for(repo, len(spec.planned), doc["receipt_dir"]), battery_intervals=battery,
        clock=lambda: time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    print(json.dumps({k: receipt[k] for k in ("name", "verdict", "speed_valid", "problems", "speed_problems")}, indent=1))
    return 0 if receipt["verdict"] == "VALID" else 1


if __name__ == "__main__":
    sys.exit(main())
