"""M6a — native MTP head speed probe: decode tok/s with the model's own multi-token-prediction
head ON vs OFF, on a small fixed item set. GATE <1.3x DECIDES WHETHER M6b (the full paired ±5pp
quality OFAT) IS WORTH RUNNING AT ALL — this script measures nothing about quality itself.

WHY A SEPARATE PROBE, NOT `suffix_ofat.py`. That module analyses ALREADY-GENERATED paired rows;
it never touches a server. MTP is a REGISTRY-LEVEL, STARTUP-TIME flag exactly like suffix
(`draft_kind`, AGENTS.md's suffix-decoding block), so — per the "never change serving config
during a live run" / "verify a flag LANDED" rules — this probe must itself: stand up a temporary
registry copy, restart the router between arms, and read the WORKER'S ACTUAL CMDLINE off `ps`
before trusting either arm. Trusting the yaml alone is exactly the mistake AGENTS.md records
against suffix.

WHY IT NEVER TOUCHES `main_models.yaml`. The real registry is git-tracked, shared with the live
campaign router, and may be mid-run on this box right now. This probe edits a scratch COPY under
`--workdir` (or `$STACK_WORKDIR`) and points a throwaway router at that copy via
`MLX_SERVE_CONFIG`. It REFUSES outright if :8000 already has a listener — that means the
campaign's own router is up, and this probe must never kill or restart someone else's process.

WHY DECODE-ONLY, THREE ITEMS, NO SAMPLING OVERRIDES. This is a speed gate, not an accuracy
measurement (that is M6b, paired, on-graded rows). Sending NO sampling params lets the temp
registry's own `generation_defaults` resolve the request (the FU-2 path mlx-serve actually
ships), so both arms run at the model's real deployed sampling. Prefill-TTFT and decode-tok/s are
reported SEPARATELY per the campaign's measurement-discipline rule — `driver.MlxServeDriver`
already does this split (`prefill_s` = wall minus the server's own predicted-decode time), so this
probe reuses it rather than re-deriving it.

GRACEFUL DEGRADATION. Not every checkpoint ships an MTP sidecar. If `--draft-kind mtp` makes the
model fail to load (worker crash or router health timeout on the ON arm), that is a VALID probe
outcome — `status: "no_mtp_head"`, exit 0 — not a script bug.

  cd benchmark && PYTHONPATH=. ../.venv-bench/bin/python -m m1.mtp_probe \\
      --model Qwen3.8-27B-mlx-uniform-4bit --workdir "$STACK_WORKDIR"
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from bench.driver import MlxServeDriver

GATE_THRESHOLD = 1.3

# Three moderate coding prompts (~300 prompt tokens each), chosen to produce ~1-3K completion
# tokens under normal (converging) decoding — enough decode volume for a tok/s reading to mean
# something, short enough that three items and two arms is a ~few-minute probe, not a benchmark
# rung. Same items, same order, both arms (OFAT — only `draft_kind` moves between them).
DEFAULT_ITEMS = [
    {
        "id": "lru_cache",
        "messages": [{"role": "user", "content": (
            "Implement a Python class `LRUCache` with a fixed integer capacity, supporting "
            "`get(key) -> value or -1` and `put(key, value)` in O(1) average time using a dict "
            "plus a doubly linked list (do not use `collections.OrderedDict`). Include type "
            "hints and a module-level docstring explaining the eviction policy. After the "
            "class, write at least 5 `unittest.TestCase` tests covering: basic get/put, "
            "eviction order on capacity overflow, updating an existing key refreshes its "
            "recency, get on a missing key returns -1, and a capacity-1 cache. Return the "
            "complete file as a single ```python code block, runnable with "
            "`python -m unittest`."
        )}],
    },
    {
        "id": "token_bucket",
        "messages": [{"role": "user", "content": (
            "Implement a Python class `TokenBucket` rate limiter with `capacity` and "
            "`refill_rate` (tokens/second) constructor arguments, a thread-safe "
            "`allow(n_tokens=1) -> bool` method that consumes tokens if available else returns "
            "False, and an internal monotonic-clock-based refill calculation (no background "
            "thread). Include type hints and a docstring. Then write at least 5 "
            "`unittest.TestCase` tests: initial full bucket allows up to capacity, exceeding "
            "capacity denies, refill after simulated elapsed time raises available tokens "
            "(mock `time.monotonic`), a `threading.Lock` guards the internal state, and "
            "requesting more than capacity always fails. Return the complete file as a single "
            "```python code block."
        )}],
    },
    {
        "id": "bst",
        "messages": [{"role": "user", "content": (
            "Implement a Python class `BST` (binary search tree) with `insert(value)`, "
            "`search(value) -> bool`, `delete(value)`, and `inorder() -> list` methods, using "
            "no external libraries, with type hints and a docstring. Then write at least 5 "
            "`unittest.TestCase` tests: insert then search, inorder returns a sorted list, "
            "delete a leaf, delete a node with one child, and delete a node with two children. "
            "Return the complete file as a single ```python code block."
        )}],
    },
]


# --------------------------------------------------------------------------------- registry copy
def edit_registry_copy(src: Path, dest: Path, model: str, arm: str,
                       draft_model: str | None = None) -> Path:
    """Write a scratch copy of the registry with ONLY `model`'s draft state changed: arm "off"
    strips draft_kind (and its suffix-only knobs) entirely; arm "on" sets draft_kind: mtp — plus
    `draft_model` when the MTP head lives in a separate extracted sidecar dir (the M6c
    nemotron_h leg) rather than being discovered inside the checkpoint. Never touches `src`.
    Raises if `model` is absent from the registry (fail loud, not silently no-op)."""
    import yaml  # lazy: this module must stay importable without pyyaml present
    data = yaml.safe_load(src.read_text(encoding="utf-8"))
    models = data.get("models") or []
    entry = next((m for m in models if m.get("name") == model), None)
    if entry is None:
        known = sorted(m.get("name") for m in models)
        raise ValueError(f"model {model!r} not found in registry {src}; known models: {known}")
    for key in ("draft_kind", "draft_block_size", "suffix_min_match", "draft_model",
                "draft_cooldown"):
        entry.pop(key, None)
    if arm == "on":
        entry["draft_kind"] = "mtp"
        if draft_model:
            entry["draft_model"] = draft_model
    dest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return dest


def _original_cap(registry_src: Path, model: str):
    """The model's REAL `max_kv_cache_size`, read from the untouched registry, for provenance."""
    import yaml  # lazy
    try:
        data = yaml.safe_load(registry_src.read_text(encoding="utf-8"))
        entry = next((m for m in (data.get("models") or []) if m.get("name") == model), None)
        return entry.get("max_kv_cache_size") if entry else None
    except Exception:  # noqa: BLE001 — provenance is best-effort, never fatal
        return None


# --------------------------------------------------------------------------------- flag landing
def verify_draft_flag(cmdline: str, arm: str, draft_model: str | None = None) -> bool:
    """AGENTS.md rule: never trust the yaml alone. `cmdline` is the WORKER's actual `ps -o
    command=` output. Returns whether the flag state matches what `arm` expects. When the ON
    arm uses an external drafter dir, `--draft-model <dir>` must ALSO have landed — an MTP
    kind without its sidecar is a plain-decode arm mislabelled ON."""
    tokens = cmdline.split()
    landed = False
    model_landed = False
    for i, tok in enumerate(tokens):
        if tok == "--draft-kind" and i + 1 < len(tokens) and tokens[i + 1] == "mtp":
            landed = True
        if tok == "--draft-model" and i + 1 < len(tokens) and tokens[i + 1] == draft_model:
            model_landed = True
    if arm != "on":
        return not landed
    return landed and (model_landed if draft_model else True)


# --------------------------------------------------------------------------------- process probes
def listener_pids(port: int = 8000, runner=subprocess.run) -> list[int]:
    """PIDs with a LISTEN socket on `port`, via the same `lsof` recipe bench_heartbeat.sh and
    convert_distills.sh already use for this exact check."""
    r = runner(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
               capture_output=True, text=True)
    pids = []
    for line in (r.stdout or "").splitlines()[1:]:  # header row first
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            pids.append(int(parts[1]))
    return sorted(set(pids))


def worker_pids(pattern: str = "mlx_vlm.server", runner=subprocess.run) -> list[int]:
    r = runner(["pgrep", "-f", pattern], capture_output=True, text=True)
    return [int(x) for x in (r.stdout or "").split() if x.isdigit()]


def worker_cmdline(pid: int, runner=subprocess.run) -> str:
    r = runner(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True)
    return (r.stdout or "").strip()


def _pid_alive(pid: int, runner=subprocess.run) -> bool:
    return runner(["ps", "-p", str(pid)], capture_output=True, text=True).returncode == 0


def kill_pid(pid: int, runner=subprocess.run, sleeper=time.sleep, killer=None) -> bool:
    """Kill BY PID (never pkill-by-pattern — AGENTS.md: pkill is known-unreliable on this box).
    SIGTERM, brief wait, SIGKILL if still alive. Returns True iff the pid is gone afterward."""
    killer = killer or os.kill
    try:
        killer(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except Exception:  # noqa: BLE001 — best-effort; the alive-check below is the real verdict
        pass
    sleeper(2)
    if _pid_alive(pid, runner=runner):
        try:
            killer(pid, signal.SIGKILL)
        except Exception:  # noqa: BLE001
            pass
        sleeper(1)
    return not _pid_alive(pid, runner=runner)


def teardown(router_pid: int | None, port: int = 8000, worker_pattern: str = "mlx_vlm.server",
            runner=subprocess.run, sleeper=time.sleep, killer=None) -> dict:
    """Kill the worker(s) first, then the router, by PID; verify 0 listeners remain. Never two
    resident models / two routers is enforced by the CALLER checking `clean` and escalating."""
    killed = []
    for wpid in worker_pids(worker_pattern, runner=runner):
        kill_pid(wpid, runner=runner, sleeper=sleeper, killer=killer)
        killed.append(wpid)
    if router_pid is not None:
        kill_pid(router_pid, runner=runner, sleeper=sleeper, killer=killer)
        killed.append(router_pid)
    sleeper(2)
    remaining = listener_pids(port, runner=runner)
    return {"killed_pids": killed, "remaining_listeners": remaining, "clean": not remaining}


# --------------------------------------------------------------------------------- router lifecycle
def parse_dotenv(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _router_env(registry_copy: Path, session_max: int, dotenv_path: Path | None = None) -> dict:
    """The runserver.sh recipe, minus APC (AGENTS.md: APC_ENABLED absent, verified, never assumed)
    and pointed at the scratch registry copy instead of the real one."""
    env = dict(os.environ)
    env.pop("APC_ENABLED", None)
    if dotenv_path is not None:
        env.update(parse_dotenv(dotenv_path))
    env["MLX_SERVE_CONFIG"] = str(registry_copy)
    env["MLX_VLM_CACHE_SESSION_MAX"] = str(session_max)
    return env


def _http_health_ok(port: int, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def wait_for_router(proc, port: int, wait_s: float = 180.0, poll_interval: float = 2.0,
                    health_check=_http_health_ok, sleeper=time.sleep, clock=time.time) -> dict:
    """Poll until the router answers /health, the process dies, or `wait_s` elapses.

    `proc` needs only `.poll()` returning None (alive) or an int (exit code) — a Popen, or a
    test double. Returns {"status": "healthy"|"died"|"timeout", "returncode": int|None}."""
    deadline = clock() + wait_s
    while clock() < deadline:
        rc = proc.poll()
        if rc is not None:
            return {"status": "died", "returncode": rc}
        if health_check(port):
            return {"status": "healthy", "returncode": None}
        sleeper(poll_interval)
    return {"status": "timeout", "returncode": proc.poll()}


# --------------------------------------------------------------------------------- request loop
def run_items(driver, model: str, items: list[dict], timeout: float) -> list[dict]:
    """One completion per item, NO sampling overrides (the temp registry's own
    `generation_defaults` resolve the request — the FU-2 path). A timeout or any request failure
    is recorded as an error row, never left to hang the probe."""
    rows = []
    for it in items:
        t0 = time.time()
        try:
            r = driver.complete(model, it["messages"], {}, timeout=timeout)
            tm = r.get("raw_timings") or {}
            rows.append({
                "id": it["id"], "error": None,
                "prompt_tokens": r.get("prompt_tokens"),
                "completion_tokens": r.get("completion_tokens"),
                "wall_s": r.get("wall_s"),
                "prefill_s": r.get("prefill_s"),
                "decode_tps": r.get("decode_tps"),
                "finish_reason": r.get("finish_reason"),
                # Engagement evidence (2026-08-23 instrument-failure lesson): the fork's
                # speculative counters, straight off the timings block.
                "draft_kind": tm.get("draft_kind"),
                "draft_rounds": tm.get("draft_rounds"),
                "draft_n": tm.get("draft_n"),
                "draft_n_accepted": tm.get("draft_n_accepted"),
            })
        except Exception as e:  # noqa: BLE001 — a failed/timed-out request is a DATA row
            rows.append({"id": it["id"], "error": f"{type(e).__name__}: {e}",
                        "wall_s": round(time.time() - t0, 1)})
    return rows


def load_items(path: Path) -> list[dict]:
    items = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if "id" not in obj or "messages" not in obj:
            raise ValueError(f"{path}:{i + 1}: item missing 'id' or 'messages'")
        items.append({"id": obj["id"], "messages": obj["messages"]})
    if not items:
        raise ValueError(f"{path}: no items found")
    return items


# --------------------------------------------------------------------------------- the gate
def compute_gate(off_rows: list[dict], on_rows: list[dict], threshold: float = GATE_THRESHOLD) -> dict:
    """Median decode tok/s per arm over items that succeeded (non-error, decode_tps present) in
    BOTH arms, and the GO/STOP verdict. Matches AGENTS.md's cluster-of-one design here: n=3 is a
    screening probe, not a powered measurement — the verdict is a threshold read, not a CI."""
    off_by_id = {r["id"]: r for r in off_rows if not r.get("error") and r.get("decode_tps")}
    on_by_id = {r["id"]: r for r in on_rows if not r.get("error") and r.get("decode_tps")}
    shared = sorted(set(off_by_id) & set(on_by_id))
    if not shared:
        return {"n_matched": 0, "median_off": None, "median_on": None, "ratio": None,
               "threshold": threshold,
               "verdict": "INCONCLUSIVE (no item succeeded with decode_tps in both arms)"}
    # Engagement tripwire (2026-08-23: the VOID 08-18 close emitted 0.99x from plain decode
    # mislabelled ON). An ON row is ENGAGED iff the fork's counters name a drafter kind —
    # zero ACCEPTED tokens still counts as engaged (a real, bad head is a valid result);
    # a missing/None kind means the drafter never entered the decode loop.
    unengaged = [i for i in shared if on_by_id[i].get("draft_kind") is None]
    if unengaged:
        return {"n_matched": len(shared), "median_off": None, "median_on": None,
               "ratio": None, "threshold": threshold, "unengaged_items": unengaged,
               "verdict": ("NOT ENGAGED (ON-arm rows carry no draft counters — plain decode "
                           "mislabelled ON; no ratio reported)")}
    med_off = statistics.median(off_by_id[i]["decode_tps"] for i in shared)
    med_on = statistics.median(on_by_id[i]["decode_tps"] for i in shared)
    if not med_off:
        return {"n_matched": len(shared), "median_off": med_off, "median_on": med_on,
               "ratio": None, "threshold": threshold,
               "verdict": "INCONCLUSIVE (OFF median decode_tps is 0)"}
    ratio = med_on / med_off
    verdict = f"GO (>={threshold}x)" if ratio >= threshold else f"STOP (<{threshold}x)"
    return {"n_matched": len(shared), "median_off": med_off, "median_on": med_on,
           "ratio": ratio, "threshold": threshold, "verdict": verdict}


# --------------------------------------------------------------------------------- arm orchestration
def run_arm(model: str, arm: str, registry_src: Path, workdir: Path, repo_root: Path,
           items: list[dict], *, request_timeout: float = 900.0, router_wait_s: float = 180.0,
           load_timeout: float = 900.0, port: int = 8000, session_max: int = 2,
           draft_model: str | None = None,
           driver_factory=MlxServeDriver, popen=subprocess.Popen, runner=subprocess.run,
           health_check=_http_health_ok, sleeper=time.sleep, clock=time.time) -> dict:
    """One arm end to end: temp registry copy -> fresh router -> verify the flag landed at the
    WORKER's cmdline -> run `items` -> teardown (always, via finally). Never assumes the previous
    arm's router is gone — refuses if a listener is already up (a caller bug, not this probe's
    to fix by killing an unknown process)."""
    registry_copy = workdir / f"registry_{arm}.yaml"
    edit_registry_copy(registry_src, registry_copy, model, arm, draft_model=draft_model)

    pre = listener_pids(port, runner=runner)
    if pre:
        return {"arm": arm, "status": "error",
               "message": f"expected 0 listeners on :{port} before starting arm={arm}, found {pre}"}

    env = _router_env(registry_copy, session_max, dotenv_path=repo_root / ".env")
    log_path = workdir / f"router_{arm}.log"
    log_f = open(log_path, "w", encoding="utf-8")
    try:
        proc = popen(["uv", "run", "mlx-serve", "start"], cwd=str(repo_root), env=env,
                     stdout=log_f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    finally:
        log_f.close()

    router_pid = None
    try:
        health = wait_for_router(proc, port, wait_s=router_wait_s, health_check=health_check,
                                 sleeper=sleeper, clock=clock)
        if health["status"] != "healthy":
            status = "no_mtp_head" if arm == "on" else "error"
            return {"arm": arm, "status": status, "router_health": health,
                   "log_path": str(log_path)}

        listeners = listener_pids(port, runner=runner)
        if len(listeners) != 1:
            return {"arm": arm, "status": "error", "log_path": str(log_path),
                   "message": f"expected exactly 1 listener on :{port} after start, "
                              f"found {listeners} — possible duplicate router"}
        router_pid = listeners[0]

        driver = driver_factory()
        try:
            driver.preload(model, timeout=load_timeout)
        except Exception as e:  # noqa: BLE001 — a load failure IS the no-mtp-head signal on arm=on
            status = "no_mtp_head" if arm == "on" else "error"
            return {"arm": arm, "status": status, "log_path": str(log_path),
                   "message": f"model load failed: {type(e).__name__}: {e}"}

        wpids = worker_pids(runner=runner)
        if len(wpids) != 1:
            return {"arm": arm, "status": "error", "log_path": str(log_path),
                   "message": f"expected exactly 1 mlx_vlm.server worker, found {wpids}"}
        cmdline = worker_cmdline(wpids[0], runner=runner)
        if not verify_draft_flag(cmdline, arm, draft_model=draft_model):
            return {"arm": arm, "status": "error", "log_path": str(log_path),
                   "message": f"draft flag did NOT land as expected for arm={arm}: {cmdline}"}

        rows = run_items(driver, model, items, request_timeout)
        return {"arm": arm, "status": "ok", "rows": rows, "worker_cmdline": cmdline,
               "log_path": str(log_path)}
    finally:
        td = teardown(router_pid, port=port, runner=runner, sleeper=sleeper)
        if not td["clean"]:
            print(f"[mtp_probe] WARNING: teardown for arm={arm} left listeners: "
                 f"{td['remaining_listeners']}", flush=True)


# --------------------------------------------------------------------------------- report
def _deployed_sha(repo_root: Path, submodule: str = "src/mlx-vlm") -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(repo_root / submodule), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return out or None
    except Exception:  # noqa: BLE001 — provenance is best-effort, never fatal
        return None


def _build_report(model: str, arm_results: dict, repo_root: Path, registry_src: Path,
                  gate_threshold: float) -> dict:
    off, on = arm_results.get("off"), arm_results.get("on")
    if on is not None and on["status"] == "no_mtp_head":
        overall = "no_mtp_head"
    elif any(r["status"] == "error" for r in arm_results.values()):
        overall = "error"
    elif off is not None and on is not None and off["status"] == on["status"] == "ok":
        overall = "ok"
    else:
        overall = "partial"

    gate = None
    if off is not None and on is not None and off["status"] == "ok" and on["status"] == "ok":
        gate = compute_gate(off["rows"], on["rows"], threshold=gate_threshold)

    return {
        "model": model,
        "status": overall,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mlx_vlm_sha": _deployed_sha(repo_root),
        "registry_cap": _original_cap(registry_src, model),
        "draft_state": {"off": "off", "on": "mtp"},
        "arms": arm_results,
        "gate": gate,
    }


def _print_report(report: dict) -> None:
    print(f"\n=== M6a MTP probe -- {report['model']} ===")
    print(f"status: {report['status']}   mlx-vlm sha: {report.get('mlx_vlm_sha')}   "
         f"registry cap: {report.get('registry_cap')}")
    for arm in ("off", "on"):
        r = report["arms"].get(arm)
        if not r:
            continue
        print(f"\n-- arm={arm}  status={r['status']}")
        for row in r.get("rows") or []:
            if row.get("error"):
                print(f"   {row['id']:16s} ERROR: {row['error']}")
            else:
                print(f"   {row['id']:16s} prefill_s={row.get('prefill_s')}  "
                     f"decode_tps={row.get('decode_tps')}  "
                     f"completion_tokens={row.get('completion_tokens')}  "
                     f"wall_s={row.get('wall_s')}")
        if r.get("message"):
            print(f"   {r['message']}")
    g = report.get("gate")
    if g and g["median_off"] is not None:
        print(f"\nmedian decode tok/s: OFF={g['median_off']:.1f}  ON={g['median_on']:.1f}  "
             f"ratio(ON/OFF)={g['ratio']:.2f}x  (n={g['n_matched']})")
        print(f"M6a GATE: {g['verdict']}")
    elif g:
        print(f"\nM6a GATE: {g['verdict']}")
    elif report["status"] == "no_mtp_head":
        print(f"\nM6a GATE: N/A -- {report['model']} has no usable MTP head")
    else:
        print(f"\nM6a GATE: N/A -- gate needs both arms to complete ok (status={report['status']})")


# --------------------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="M6a: native MTP head speed probe (decode tok/s ON vs OFF). Gate <1.3x.")
    ap.add_argument("--model", required=True, help="full registry model name")
    ap.add_argument("--workdir", default=None,
                    help="scratch dir for the registry copy/logs/result (default: $STACK_WORKDIR)")
    ap.add_argument("--arm", choices=["off", "on", "both"], default="both")
    ap.add_argument("--items", default=None,
                    help="jsonl of {id, messages}; default: 3 built-in coding prompts")
    ap.add_argument("--request-timeout", type=float, default=900.0)
    ap.add_argument("--router-wait-s", type=float, default=180.0)
    ap.add_argument("--load-timeout", type=float, default=900.0)
    ap.add_argument("--gate-threshold", type=float, default=GATE_THRESHOLD)
    ap.add_argument("--session-max", type=int, default=2)
    ap.add_argument("--draft-model", dest="draft_model", default=None,
                    help="external extracted MTP sidecar dir for the ON arm (M6c nemotron_h "
                         "leg: the head is NOT inside the checkpoint). Verified at the worker "
                         "cmdline like --draft-kind.")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    workdir_root = args.workdir or os.environ.get("STACK_WORKDIR")
    if not workdir_root:
        print("ERROR: --workdir not given and STACK_WORKDIR not set. Refusing to write outside "
             "the repo without an explicit workdir (containment rule).")
        return 2
    workdir = Path(workdir_root) / "mtp_probe" / args.model
    workdir.mkdir(parents=True, exist_ok=True)

    busy = listener_pids(8000)
    if busy:
        print(f"REFUSING: :8000 already has listener(s) pid={busy}. That is the campaign router "
             f"-- this probe never touches a router it did not start itself. Stop it yourself "
             f"first if this probe should run now.")
        return 2

    from bench import paths
    repo_root = paths.repo_root()
    registry_src = paths.registry_path()
    items = load_items(Path(args.items)) if args.items else DEFAULT_ITEMS

    arms = ["off", "on"] if args.arm == "both" else [args.arm]
    arm_results: dict[str, dict] = {}
    for arm in arms:
        print(f"[mtp_probe] === arm={arm} ===", flush=True)
        res = run_arm(args.model, arm, registry_src, workdir, repo_root, items,
                      request_timeout=args.request_timeout, router_wait_s=args.router_wait_s,
                      load_timeout=args.load_timeout, session_max=args.session_max,
                      draft_model=args.draft_model)
        arm_results[arm] = res
        print(f"[mtp_probe] arm={arm} status={res['status']}", flush=True)
        if res["status"] in ("no_mtp_head", "error"):
            break

    report = _build_report(args.model, arm_results, repo_root, registry_src, args.gate_threshold)
    json_out = Path(args.json_out) if args.json_out else workdir / "mtp_probe_result.json"
    json_out.write_text(json.dumps(report, indent=2))
    _print_report(report)
    print(f"\n[mtp_probe] json -> {json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
