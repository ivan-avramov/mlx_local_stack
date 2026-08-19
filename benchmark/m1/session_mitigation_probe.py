"""D6 session-floor mitigation probe — the 4-point live gate that decides whether the fork's
shrink-on-retire / headroom-eviction knobs (`docs/lab-notebook.md` D6, fork commit 07ed59e2)
get enabled in serving.

WHY THIS EXISTS. `$STACK_WORKDIR/scratch/d6-session-prealloc-audit.md` established that with
`kv_prealloc_tokens == max_kv_cache_size`, every LRU-retained session floors its KV cache at the
FULL cap (measured 58 GB + swap at the default session cap of 8 — see docs/lab-notebook.md). The
fork now carries two OPT-IN mitigations, both off by default: `--cache-session-shrink` releases a
session's KV floor back to its real offset immediately after each turn (re-floors on the session's
next use), and `--cache-session-evict-headroom-frac` evicts idle sessions once active memory
crosses a fraction of the recommended working set. Both trade something for the memory they save
(shrink pays a realloc+copy on resume; eviction can defeat the whole point of session caching if it
fires too eagerly), so enabling either in production is GATED on four live measurements. This
script IS that gate:

  1. FOOTPRINT DROP   — resident peak after N idle sessions, shrink ON vs OFF. Pass: > 1 GB/session.
  2. RESUME TAX       — added time-to-first-token on a shrunk session's next turn (the re-floor
                         realloc+copy), ON vs OFF. Pass: < 2000 ms.
  3. RE-FLOOR SPIKE    — the transient peak during that resume turn (old+new buffers coexist
                         mid-copy — same OOM shape as the 384K double-buffer that measurably
                         OOMed). Pass: absolute peak stays under the 46 GB capacity gate.
  4. EVICTION THRASH   — alternating turns across more sessions than headroom allows; verdict is
                         PASS only if alternating exactly 2 sessions does NOT evict each other
                         every turn (which would force full re-prefill every turn — worse than no
                         eviction at all).

MECHANICS. This drives the mlx_vlm WORKER directly on its own probe port (default 8093), NOT the
mlx-serve router (:8000) — the router can't pin the exact per-model CLI flag set this probe needs
to vary (shrink on/off, headroom frac), so we replicate mlx-serve's own argv construction
(`src/mlx-serve/src/mlx_serve/process_manager.py::_build_command`) directly against the fork
checkout. Needs the fork's own venv: `<repo>/../mlx-vlm/.venv/bin/python` by default (override with
--python / --mlx-vlm-root or env MLX_VLM_FORK_ROOT). Per AGENTS.md's one-resident-model rule, this
REFUSES to run at all if :8000, :8091, or :8092 has a listener (the campaign router / task model)
unless --force, and refuses to start a worker on a probe port that's already busy.

GENERATION PARAMS ARE DELIBERATELY MINIMAL (thinking disabled, temperature 0, small max_tokens).
AGENTS.md's "thinking is enabled for all tests" rule guards against distorting a QUALITY signal —
this probe measures KV-cache memory/latency mechanics, not model quality or convergence, so a small
deterministic turn that reliably exercises prefill+decode+cache-store is the right instrument, not
a violation of that rule.

INSTRUMENTATION. Every turn is read from TWO places: the raw `/v1/chat/completions` response
(content, finish_reason) and the worker's own `/metrics` `latest` envelope, fetched immediately
after (session_id, cached_tokens, ttft_s, prompt_eval_time_s, peak_memory_gb — see
`mlx_vlm/server/generation.py::_build_metrics_envelope`). `/metrics` carries NO session-count or
per-session-byte-size counters as of fork commit 07ed59e2 (checked: `_server_runtime_snapshot` /
`ServerMetricsStore.snapshot` expose only aggregate request stats + APC stats) — so per-session
byte accounting is inferred from `mx.get_peak_memory()` (the campaign's own capacity metric, `peak_
memory_gb`), read serially across controlled arms, never from RSS. Eviction/shrink EVENTS are read
from the worker's own stderr/stdout log (`--log-file`, `logger.info` lines in
`session_manager.py::_evict_for_headroom` and `generate/common.py::_shrink_cache_entries`) since
neither is countered via HTTP.

  cd /path/to/mlx_local_stack
  PYTHONPATH=benchmark .venv-bench/bin/python -m m1.session_mitigation_probe \\
      --model Ornith-1.0-35B-mlx-uniform-4bit --workdir "$STACK_WORKDIR/scratch/d6-probe"
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# One-resident-model guard ports: the campaign router (:8000) and the task model, checked under
# BOTH the documented default (AGENTS.md: 8092) and the port named in this probe's own spec (8091)
# — cheap to check both, and a false negative here is a one-resident-model violation.
GUARD_PORTS = (8000, 8091, 8092)

CHAT_ID_HEADER = "X-MLX-VLM-Chat-Id"  # fork default (session_manager._chat_id_header); passed
# explicitly to the worker too so a future fork default change can't silently desync this probe.

_EVICT_RE = re.compile(r"Headroom eviction: dropped chat_id=(\S+)")
_SHRINK_RE = re.compile(
    r"Session cache shrink-on-retire: (\S+) offset=(\S+) freed ([\d.]+) MiB"
)


# ---------------------------------------------------------------------------
# Pure helpers — no network, no subprocess. Fully unit-testable.
# ---------------------------------------------------------------------------


def _port_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """True iff something accepts a TCP connection on host:port."""
    with contextlib.suppress(OSError):
        with socket.create_connection((host, port), timeout=timeout):
            return True
    return False


def refuse_if_campaign_busy(force: bool, ports=GUARD_PORTS, checker=_port_listening) -> list:
    """One-resident-model guard. Raises SystemExit when a campaign port is live and --force was
    not given; returns the list of busy ports otherwise (empty when the box is quiet)."""
    busy = [p for p in ports if checker(p)]
    if busy and not force:
        raise SystemExit(
            f"refusing to run: port(s) {busy} have a listener (one-resident-model rule — the "
            f"campaign router or task model may be up). Pass --force to override."
        )
    return busy


def _filler_system_prompt(session_idx: int, target_tokens: int = 3000) -> str:
    """Deterministic, distinct-per-session filler text sized to roughly `target_tokens` (~4
    chars/token — not tokenizer-exact, the spec only asks for ~2-4K tokens)."""
    unit = (
        f"[d6-probe session {session_idx} filler block] "
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor "
        "incididunt ut labore et dolore magna aliqua. "
    )
    target_chars = max(len(unit), target_tokens * 4)
    reps = max(1, -(-target_chars // len(unit)))  # ceil div
    return (unit * reps)[:target_chars]


def count_log_events(log_text: str) -> dict:
    """Parse shrink/eviction INFO lines out of a worker log. Pure — testable against a canned
    string without ever touching a real log file."""
    evictions = _EVICT_RE.findall(log_text or "")
    shrinks = _SHRINK_RE.findall(log_text or "")
    return {
        "n_evictions": len(evictions),
        "evicted_chat_ids": evictions,
        "n_shrinks": len(shrinks),
    }


def parse_metrics_latest(payload: dict) -> dict:
    """Extract the fields we use from a `/metrics` response's `latest` envelope (see
    `mlx_vlm/server/generation.py::_build_metrics_envelope` for the full schema this mirrors).
    Tolerates a missing/None `latest` (e.g. queried before any request completed) by returning
    None-valued defaults rather than raising — a probe that crashes on an empty metrics snapshot
    is worse than one that reports "no data yet"."""
    latest = (payload or {}).get("latest") or {}
    return {
        "session_id": latest.get("session_id"),
        "cached_tokens": int(latest.get("cached_tokens") or 0),
        "prompt_tokens": int(latest.get("prompt_tokens") or 0),
        "completion_tokens": int(latest.get("completion_tokens") or 0),
        "ttft_s": latest.get("ttft_s"),
        "prompt_eval_time_s": latest.get("prompt_eval_time_s"),
        "decode_tok_s": latest.get("decode_tok_s"),
        "peak_memory_gb": float(latest.get("peak_memory_gb") or 0.0),
        "finish_reason": latest.get("finish_reason"),
    }


def verdict_footprint(off_peak_gb: float, on_peak_gb: float, n_sessions: int,
                       *, min_saving_gb: float = 1.0) -> dict:
    """Measurement 1. Pass iff shrink-ON saves more than `min_saving_gb` per retired session."""
    saved_total_gb = off_peak_gb - on_peak_gb
    saved_per_session_gb = saved_total_gb / n_sessions if n_sessions else 0.0
    passed = saved_per_session_gb > min_saving_gb
    return {
        "off_peak_gb": off_peak_gb, "on_peak_gb": on_peak_gb, "n_sessions": n_sessions,
        "saved_total_gb": round(saved_total_gb, 3),
        "saved_per_session_gb": round(saved_per_session_gb, 3),
        "min_saving_gb": min_saving_gb, "pass": passed,
        "criterion": f"saving > {min_saving_gb:g} GB/session",
    }


def verdict_resume_tax(off_ttft_s: Optional[float], on_ttft_s: Optional[float],
                        *, max_added_ms: float = 2000.0) -> dict:
    """Measurement 2. Pass iff the re-floor's added time-to-first-token stays under the budget.
    None inputs (a failed turn) fail closed — an unmeasured tax cannot be certified safe."""
    if off_ttft_s is None or on_ttft_s is None:
        return {
            "off_ttft_s": off_ttft_s, "on_ttft_s": on_ttft_s, "added_ms": None,
            "max_added_ms": max_added_ms, "pass": False,
            "criterion": f"resume tax < {max_added_ms:g} ms",
            "note": "missing ttft_s on at least one arm — cannot certify",
        }
    added_ms = (on_ttft_s - off_ttft_s) * 1000.0
    passed = added_ms < max_added_ms
    return {
        "off_ttft_s": off_ttft_s, "on_ttft_s": on_ttft_s, "added_ms": round(added_ms, 1),
        "max_added_ms": max_added_ms, "pass": passed,
        "criterion": f"resume tax < {max_added_ms:g} ms",
    }


def verdict_refloor_spike(peak_before_gb: float, peak_after_gb: float,
                           *, gate_gb: float = 46.0, warn_gb: float = 42.0) -> dict:
    """Measurement 3. Pass iff the ABSOLUTE peak during/after the resume turn (which is what the
    46 GB capacity gate is defined on — the prefill spike, not the delta) stays under the gate.
    `warn_gb` is a loud early flag distinct from the pass/fail line itself."""
    spike_gb = max(0.0, peak_after_gb - peak_before_gb)
    passed = peak_after_gb < gate_gb
    warn = peak_after_gb >= warn_gb
    out = {
        "peak_before_gb": peak_before_gb, "peak_after_gb": peak_after_gb,
        "spike_gb": round(spike_gb, 3), "gate_gb": gate_gb, "warn_gb": warn_gb,
        "warn": warn, "pass": passed,
        "criterion": f"peak stays under the {gate_gb:g} GB gate with the model resident",
    }
    if warn:
        out["warning"] = (
            f"peak_after_gb={peak_after_gb:.2f} GB is within {gate_gb - peak_after_gb:.2f} GB "
            f"of the {gate_gb:g} GB capacity gate"
        )
    return out


def eviction_reuse_ratios(turns: list, session_ids) -> dict:
    """cached_tokens/prompt_tokens per turn, per session, EXCLUDING each session's first turn
    (which has nothing to reuse and is not informative about eviction). `turns` is a list of
    TurnRecord-like objects/dicts with `.chat_id`/`.cached_tokens`/`.prompt_tokens` (or the dict
    equivalents) in chronological order."""
    seen = {sid: 0 for sid in session_ids}
    ratios = {sid: [] for sid in session_ids}
    for t in turns:
        cid = t["chat_id"] if isinstance(t, dict) else t.chat_id
        if cid not in seen:
            continue
        seen[cid] += 1
        if seen[cid] == 1:
            continue
        pt = t["prompt_tokens"] if isinstance(t, dict) else t.prompt_tokens
        ct = t["cached_tokens"] if isinstance(t, dict) else t.cached_tokens
        ratios[cid].append((ct / pt) if pt else 0.0)
    return ratios


def verdict_eviction_thrash(ratios: dict, *, threshold: float = 0.5) -> dict:
    """Measurement 4. Pass iff NO revisit turn came back with a reuse ratio below `threshold` —
    i.e. alternating two sessions never evicted the other out from under it. A turn below
    threshold means that session's cache was gone (full or near-full re-prefill): thrash."""
    flat = [r for rs in ratios.values() for r in rs]
    below = [r for r in flat if r < threshold]
    passed = len(below) == 0 and len(flat) > 0
    return {
        "reuse_ratios": ratios, "n_checked": len(flat), "n_below_threshold": len(below),
        "threshold": threshold, "pass": passed,
        "criterion": "no alternating-2 thrash (revisit reuse ratio >= threshold)",
    }


def overall_verdict(report: dict) -> dict:
    """ENABLE only if every measurement actually run in this invocation passed. A measurement not
    run at all (partial --phases) is excluded from the checks, not silently counted as a pass."""
    checks = {}
    if "footprint" in report:
        checks["footprint_drop"] = report["footprint"]["pass"]
    if "resume_tax" in report:
        checks["resume_tax"] = report["resume_tax"]["pass"]
    if "refloor_spike" in report:
        checks["refloor_spike"] = report["refloor_spike"]["pass"]
    if "eviction_thrash" in report:
        checks["eviction_thrash"] = report["eviction_thrash"]["pass"]
    failing = sorted(k for k, ok in checks.items() if not ok)
    if not checks:
        verdict = "NO-PHASES-RUN"
    elif failing:
        verdict = "DO-NOT-ENABLE"
    else:
        verdict = "ENABLE"
    return {"checks": checks, "failing_points": failing, "verdict": verdict}


def _git_sha(repo_dir) -> Optional[str]:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001 — provenance is best-effort, never fatal
        return None


# ---------------------------------------------------------------------------
# Worker command construction — mirrors src/mlx-serve/.../process_manager.py::_build_command
# for the vision path, plus the D6 flags it doesn't know about yet.
# ---------------------------------------------------------------------------


@dataclass
class WorkerConfig:
    hf_path: str
    port: int
    cache_session_max: int
    chat_id_header: str
    shrink_on: bool
    evict_headroom_frac: float
    log_path: Path
    python_exe: Path
    mlx_vlm_root: Path
    max_kv_cache_size: int = 0
    kv_prealloc_tokens: int = 0
    kv_bits: int = 0
    kv_quant_scheme: Optional[str] = None
    quantized_kv_start: int = 0
    prefill_step_size: Optional[int] = None
    startup_timeout: float = 900.0
    extra_env: dict = field(default_factory=dict)


def build_worker_command(cfg: WorkerConfig) -> list:
    cmd = [
        str(cfg.python_exe), "-m", "mlx_vlm.server",
        "--model", cfg.hf_path,
        "--host", "127.0.0.1",
        "--port", str(cfg.port),
    ]
    if cfg.max_kv_cache_size:
        cmd += ["--max-kv-size", str(cfg.max_kv_cache_size)]
    if cfg.kv_prealloc_tokens:
        cmd += ["--kv-prealloc-tokens", str(cfg.kv_prealloc_tokens)]
    if cfg.kv_bits:
        cmd += ["--kv-bits", str(cfg.kv_bits)]
    if cfg.kv_quant_scheme:
        cmd += ["--kv-quant-scheme", cfg.kv_quant_scheme]
    if cfg.prefill_step_size:
        cmd += ["--prefill-step-size", str(cfg.prefill_step_size)]
    cmd += ["--quantized-kv-start", str(cfg.quantized_kv_start or 0)]
    cmd += [
        "--cache-session-max", str(cfg.cache_session_max),
        "--cache-chat-id-header", cfg.chat_id_header,
        "--cache-session-shrink", "on" if cfg.shrink_on else "off",
        "--cache-session-evict-headroom-frac", str(cfg.evict_headroom_frac),
        "--log-level", "INFO",
        "--log-file", str(cfg.log_path),
    ]
    return cmd


class WorkerHandle:
    """Subprocess lifecycle for one probe-port worker. Kill-by-PID with verification; never
    trusts `terminate()` alone (AGENTS.md: `pkill -f mlx-serve` has produced ghost workers)."""

    def __init__(self, cfg: WorkerConfig, popen=subprocess.Popen):
        self.cfg = cfg
        self._popen = popen
        self.proc = None
        self.teardown_failed = False

    def start(self):
        if _port_listening(self.cfg.port):
            raise RuntimeError(
                f"probe port {self.cfg.port} already in use; refusing to start another worker "
                f"there"
            )
        cmd = build_worker_command(self.cfg)
        env = dict(os.environ)
        existing_pp = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(self.cfg.mlx_vlm_root) + (os.pathsep + existing_pp if existing_pp else "")
        )
        env.update(self.cfg.extra_env)
        self.cfg.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.proc = self._popen(
            cmd, cwd=str(self.cfg.mlx_vlm_root), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return self.proc

    def wait_ready(self, base_url: str, timeout_s: Optional[float] = None,
                    poll_s: float = 2.0) -> dict:
        timeout_s = self.cfg.startup_timeout if timeout_s is None else timeout_s
        deadline = time.monotonic() + timeout_s
        last_err = None
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f"worker exited early with code {self.proc.returncode} "
                    f"(see {self.cfg.log_path})"
                )
            try:
                with urllib.request.urlopen(base_url + "/health", timeout=5) as r:
                    payload = json.loads(r.read().decode())
                if payload.get("status") == "healthy" and payload.get("loaded_model"):
                    return payload
            except Exception as e:  # noqa: BLE001 — expected while the model loads
                last_err = e
            time.sleep(poll_s)
        raise TimeoutError(
            f"worker did not become healthy within {timeout_s}s (last_err={last_err})"
        )

    def stop(self, timeout_s: float = 15.0) -> bool:
        """Terminate, escalate to kill, and VERIFY the PID is actually gone. Returns True iff
        teardown is confirmed clean; sets self.teardown_failed and returns False otherwise (never
        raises — teardown must not mask whatever exception is already propagating)."""
        if self.proc is None:
            return True
        pid = self.proc.pid
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                try:
                    self.proc.wait(timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    pass
        alive = self.proc.poll() is None
        if alive:
            self.teardown_failed = True
            print(f"[d6-probe] WARNING: worker pid {pid} still alive after stop()",
                  file=sys.stderr)
        return not alive


@contextlib.contextmanager
def running_worker(cfg: WorkerConfig, handle_cls=WorkerHandle):
    """Start a worker, yield it once healthy, and ALWAYS tear it down — including when the body
    raises (the `finally` runs regardless)."""
    handle = handle_cls(cfg)
    handle.start()
    try:
        handle.wait_ready(f"http://127.0.0.1:{cfg.port}")
        yield handle
    finally:
        handle.stop()


# ---------------------------------------------------------------------------
# HTTP client + turn record
# ---------------------------------------------------------------------------


@dataclass
class TurnRecord:
    chat_id: str
    ok: bool
    content: str = ""
    error: Optional[str] = None
    finish_reason: Optional[str] = None
    session_id: Optional[str] = None
    cached_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    ttft_s: Optional[float] = None
    prompt_eval_time_s: Optional[float] = None
    decode_tok_s: Optional[float] = None
    peak_memory_gb: float = 0.0
    wall_s: float = 0.0


class WorkerClient:
    """Talks to ONE worker (probe port), never the router. Pure stdlib HTTP, mirroring
    `benchmark/bench/client.py`'s shape but pointed at an arbitrary base_url and carrying the
    per-chat-id session header this probe needs."""

    def __init__(self, base_url: str, chat_id_header: str, request_timeout: float,
                 request_model: str):
        self.base_url = base_url.rstrip("/")
        self.chat_id_header = chat_id_header
        self.request_timeout = request_timeout
        self.request_model = request_model

    def _get(self, path: str, timeout: float = 10.0) -> dict:
        with urllib.request.urlopen(self.base_url + path, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def metrics(self, timeout: float = 10.0) -> dict:
        return self._get("/metrics", timeout=timeout)

    def health(self, timeout: float = 10.0) -> dict:
        return self._get("/health", timeout=timeout)

    def turn(self, chat_id: str, messages: list, *, max_tokens: int,
              timeout: Optional[float] = None) -> TurnRecord:
        """One non-streaming completion pinned to `chat_id` via the session header. Content
        comes from the raw response; the rest (session_id/cached_tokens/ttft_s/peak_memory_gb)
        comes from `/metrics` `latest`, fetched immediately after — see module docstring."""
        timeout = self.request_timeout if timeout is None else timeout
        body = {
            "model": self.request_model, "messages": messages, "stream": False,
            "max_tokens": max_tokens, "temperature": 0.0, "enable_thinking": False,
        }
        req = urllib.request.Request(
            self.base_url + "/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", self.chat_id_header: chat_id},
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode())
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as e:
            return TurnRecord(chat_id=chat_id, ok=False, error=str(e),
                               wall_s=round(time.perf_counter() - t0, 3))
        wall_s = time.perf_counter() - t0
        choice = (resp.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        finish_reason = choice.get("finish_reason")
        try:
            m = parse_metrics_latest(self.metrics())
        except Exception as e:  # noqa: BLE001 — content still landed; report metrics as missing
            m = parse_metrics_latest({})
            m["metrics_error"] = str(e)
        return TurnRecord(
            chat_id=chat_id, ok=True, content=content,
            finish_reason=finish_reason or m.get("finish_reason"),
            session_id=m.get("session_id"), cached_tokens=m.get("cached_tokens", 0),
            prompt_tokens=m.get("prompt_tokens", 0), completion_tokens=m.get("completion_tokens", 0),
            ttft_s=m.get("ttft_s"), prompt_eval_time_s=m.get("prompt_eval_time_s"),
            decode_tok_s=m.get("decode_tok_s"), peak_memory_gb=m.get("peak_memory_gb", 0.0),
            wall_s=round(wall_s, 3),
        )


# ---------------------------------------------------------------------------
# Phase runners (1+2+3 share one "core" arm pair; 4 is independent)
# ---------------------------------------------------------------------------


def run_core_arm(client: WorkerClient, arm_name: str, n_sessions: int, gen_max_tokens: int,
                  request_timeout: float) -> dict:
    """N distinct sessions, each one turn; then a resume turn on session 0 (the one that has
    been idle longest — shrink-on-retire, when enabled, fires right after ITS turn ends, long
    before sessions 1..N-1 are even created). Returns raw per-turn data plus the two peak
    readings measurements 1/2/3 are built from."""
    turns = []
    prompts = {}
    for i in range(n_sessions):
        chat_id = f"d6-probe-{arm_name}-s{i}"
        sys_prompt = _filler_system_prompt(i)
        prompts[i] = sys_prompt
        msgs = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Summarize the block above in one sentence. (session {i})"},
        ]
        rec = client.turn(chat_id, msgs, max_tokens=gen_max_tokens, timeout=request_timeout)
        turns.append(rec)

    peak_after_n_sessions_gb = turns[-1].peak_memory_gb if turns else 0.0
    peak_before_resume_gb = peak_after_n_sessions_gb

    resume_chat_id = f"d6-probe-{arm_name}-s0"
    resume_msgs = [
        {"role": "system", "content": prompts.get(0, "")},
        {"role": "user", "content": "Summarize the block above in one sentence. (session 0)"},
        {"role": "assistant", "content": turns[0].content if turns else ""},
        {"role": "user", "content": "Thanks -- now give a two-word title for it."},
    ]
    resume_rec = client.turn(resume_chat_id, resume_msgs, max_tokens=gen_max_tokens,
                              timeout=request_timeout)
    peak_after_resume_gb = resume_rec.peak_memory_gb if resume_rec.ok else peak_before_resume_gb

    return {
        "arm": arm_name,
        "turns": [dataclasses.asdict(t) for t in turns],
        "resume": dataclasses.asdict(resume_rec),
        "peak_after_n_sessions_gb": peak_after_n_sessions_gb,
        "peak_before_resume_gb": peak_before_resume_gb,
        "peak_after_resume_gb": peak_after_resume_gb,
    }


EVICTION_SESSION_IDS = ("d6-probe-evict-a", "d6-probe-evict-b")


def run_eviction_arm(client: WorkerClient, n_rounds: int, gen_max_tokens: int,
                      request_timeout: float) -> list:
    """Alternate turns across the two IDs in EVICTION_SESSION_IDS for `n_rounds` full rounds,
    each turn echoing the growing conversation back (required for the session's hash-chain to
    keep matching -- see session_manager._resolve_session)."""
    prompts = {sid: _filler_system_prompt(i) for i, sid in enumerate(EVICTION_SESSION_IDS)}
    convo = {sid: [] for sid in EVICTION_SESSION_IDS}
    turns = []
    for round_i in range(n_rounds):
        for sid in EVICTION_SESSION_IDS:
            user_msg = {"role": "user",
                        "content": f"Round {round_i} for {sid}: continue briefly."}
            msgs = [{"role": "system", "content": prompts[sid]}] + convo[sid] + [user_msg]
            rec = client.turn(sid, msgs, max_tokens=gen_max_tokens, timeout=request_timeout)
            turns.append(rec)
            convo[sid] = convo[sid] + [user_msg, {"role": "assistant", "content": rec.content}]
    return turns


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_report(report: dict) -> None:
    print(f"\n=== D6 session-mitigation probe -- {report.get('model')} "
          f"(fork {report.get('fork_sha')}) ===")
    if "footprint" in report:
        f_ = report["footprint"]
        print(f"[1] FOOTPRINT DROP: {f_['saved_per_session_gb']:+.2f} GB/session "
              f"(criterion: {f_['criterion']}) -> {'PASS' if f_['pass'] else 'FAIL'}")
    if "resume_tax" in report:
        r_ = report["resume_tax"]
        added = r_.get("added_ms")
        print(f"[2] RESUME TAX: {added if added is None else f'{added:+.0f}'} ms "
              f"(criterion: {r_['criterion']}) -> {'PASS' if r_['pass'] else 'FAIL'}")
    if "refloor_spike" in report:
        s_ = report["refloor_spike"]
        print(f"[3] RE-FLOOR SPIKE: peak {s_['peak_after_gb']:.2f} GB (delta "
              f"{s_['spike_gb']:+.2f} GB) (criterion: {s_['criterion']}) -> "
              f"{'PASS' if s_['pass'] else 'FAIL'}"
              + (f"  *** {s_.get('warning')}" if s_.get("warn") else ""))
    if "eviction_thrash" in report:
        e_ = report["eviction_thrash"]
        print(f"[4] EVICTION THRASH: {e_['n_below_threshold']}/{e_['n_checked']} revisit turns "
              f"below reuse threshold {e_['threshold']:g}, {e_.get('evictions_per_turn', 0):.2f} "
              f"evictions/turn (criterion: {e_['criterion']}) -> "
              f"{'PASS' if e_['pass'] else 'FAIL'}")
    ov = report.get("overall", {})
    print(f"\nVERDICT: {ov.get('verdict')}"
          + (f"  (failing: {', '.join(ov.get('failing_points', []))})"
             if ov.get("failing_points") else ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="D6 session-floor mitigation probe (shrink-on-retire / headroom eviction).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--model", required=True, help="full registry name (main_models.yaml)")
    ap.add_argument("--registry", default=None, help="path to main_models.yaml (default: repo's)")
    ap.add_argument("--workdir", default=None,
                     help="output dir (default: $STACK_WORKDIR/scratch/d6-probe if set)")
    ap.add_argument("--probe-port", type=int, default=8093)
    ap.add_argument("--python", default=None, help="fork venv python (default: <mlx-vlm-root>/.venv/bin/python)")
    ap.add_argument("--mlx-vlm-root", default=None, help="fork checkout (default: ../mlx-vlm)")
    ap.add_argument("--num-sessions", type=int, default=3)
    ap.add_argument("--gen-max-tokens", type=int, default=300)
    ap.add_argument("--request-timeout", type=float, default=600.0)
    ap.add_argument("--startup-timeout", type=float, default=900.0)
    ap.add_argument("--cache-session-max", type=int, default=None,
                     help="default: max(num_sessions + 2, 8)")
    ap.add_argument("--eviction-headroom-frac", type=float, default=0.15)
    ap.add_argument("--eviction-session-cap", type=int, default=8)
    ap.add_argument("--eviction-rounds", type=int, default=4)
    ap.add_argument("--min-saving-gb", type=float, default=1.0)
    ap.add_argument("--max-resume-tax-ms", type=float, default=2000.0)
    ap.add_argument("--capacity-gate-gb", type=float, default=46.0)
    ap.add_argument("--capacity-warn-gb", type=float, default=42.0)
    ap.add_argument("--thrash-reuse-threshold", type=float, default=0.5)
    ap.add_argument("--phases", default="1,2,3,4", help="comma list from {1,2,3,4}")
    ap.add_argument("--force", action="store_true",
                     help="run even if :8000/:8091/:8092 has a listener")
    args = ap.parse_args(argv)

    workdir_arg = args.workdir
    if not workdir_arg and os.environ.get("STACK_WORKDIR"):
        workdir_arg = str(Path(os.environ["STACK_WORKDIR"]) / "scratch" / "d6-probe")
    if not workdir_arg:
        print("error: --workdir is required (or set STACK_WORKDIR)", file=sys.stderr)
        return 2
    workdir = Path(workdir_arg)
    workdir.mkdir(parents=True, exist_ok=True)
    logs_dir = workdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    try:
        busy = refuse_if_campaign_busy(args.force)
    except SystemExit as e:
        print(f"error: {e}", file=sys.stderr)
        return 3

    from bench import paths, provenance  # noqa: PLC0415 — kept out of the hot import path

    registry_path = args.registry or str(paths.registry_path())
    kv = provenance.registry_kv(args.model, registry_path=registry_path)
    if kv is None or not kv.get("hf_path"):
        print(f"error: model '{args.model}' not found in registry {registry_path}", file=sys.stderr)
        return 2

    mlx_vlm_root = (
        Path(args.mlx_vlm_root) if args.mlx_vlm_root
        else Path(os.environ.get("MLX_VLM_FORK_ROOT", str(paths.repo_root().parent / "mlx-vlm")))
    )
    python_exe = Path(args.python) if args.python else (mlx_vlm_root / ".venv" / "bin" / "python")
    if not python_exe.exists():
        print(f"error: python executable not found: {python_exe}", file=sys.stderr)
        return 2

    fork_sha = _git_sha(mlx_vlm_root)
    stack_sha = _git_sha(paths.repo_root())
    cache_session_max = args.cache_session_max or max(args.num_sessions + 2, 8)
    phases = {p.strip() for p in args.phases.split(",") if p.strip()}

    report = {
        "model": args.model, "hf_path": kv["hf_path"],
        "max_kv_cache_size": kv.get("max_kv_cache_size"),
        "kv_prealloc_tokens": kv.get("kv_prealloc_tokens"),
        "fork_sha": fork_sha, "stack_sha": stack_sha,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ports_busy_at_start": busy, "force": args.force,
        "phases_requested": sorted(phases),
        "num_sessions": args.num_sessions, "cache_session_max": cache_session_max,
    }

    def base_cfg(port, shrink_on, evict_frac, session_max, log_name):
        return WorkerConfig(
            hf_path=kv["hf_path"], port=port, cache_session_max=session_max,
            chat_id_header=CHAT_ID_HEADER, shrink_on=shrink_on, evict_headroom_frac=evict_frac,
            log_path=logs_dir / log_name, python_exe=python_exe, mlx_vlm_root=mlx_vlm_root,
            max_kv_cache_size=kv.get("max_kv_cache_size") or 0,
            kv_prealloc_tokens=kv.get("kv_prealloc_tokens") or 0,
            kv_bits=kv.get("kv_bits") or 0, kv_quant_scheme=kv.get("kv_quant_scheme"),
            quantized_kv_start=kv.get("quantized_kv_start") or 0,
            prefill_step_size=kv.get("prefill_step_size"), startup_timeout=args.startup_timeout,
        )

    teardown_failures = []

    if phases & {"1", "2", "3"}:
        off_cfg = base_cfg(args.probe_port, False, 0.0, cache_session_max, "off.log")
        with running_worker(off_cfg) as off_handle:
            off_client = WorkerClient(f"http://127.0.0.1:{args.probe_port}", CHAT_ID_HEADER,
                                       args.request_timeout, request_model=kv["hf_path"])
            off_result = run_core_arm(off_client, "off", args.num_sessions, args.gen_max_tokens,
                                       args.request_timeout)
        if off_handle.teardown_failed:
            teardown_failures.append("off")
        off_result["log_events"] = count_log_events(
            off_cfg.log_path.read_text(errors="replace") if off_cfg.log_path.exists() else "")

        on_cfg = base_cfg(args.probe_port, True, 0.0, cache_session_max, "on.log")
        with running_worker(on_cfg) as on_handle:
            on_client = WorkerClient(f"http://127.0.0.1:{args.probe_port}", CHAT_ID_HEADER,
                                      args.request_timeout, request_model=kv["hf_path"])
            on_result = run_core_arm(on_client, "on", args.num_sessions, args.gen_max_tokens,
                                      args.request_timeout)
        if on_handle.teardown_failed:
            teardown_failures.append("on")
        on_result["log_events"] = count_log_events(
            on_cfg.log_path.read_text(errors="replace") if on_cfg.log_path.exists() else "")

        report["core_off"] = off_result
        report["core_on"] = on_result
        if "1" in phases:
            report["footprint"] = verdict_footprint(
                off_result["peak_after_n_sessions_gb"], on_result["peak_after_n_sessions_gb"],
                args.num_sessions, min_saving_gb=args.min_saving_gb)
        if "2" in phases:
            report["resume_tax"] = verdict_resume_tax(
                off_result["resume"]["ttft_s"], on_result["resume"]["ttft_s"],
                max_added_ms=args.max_resume_tax_ms)
        if "3" in phases:
            report["refloor_spike"] = verdict_refloor_spike(
                on_result["peak_before_resume_gb"], on_result["peak_after_resume_gb"],
                gate_gb=args.capacity_gate_gb, warn_gb=args.capacity_warn_gb)

    if "4" in phases:
        evict_cfg = base_cfg(args.probe_port, True, args.eviction_headroom_frac,
                              args.eviction_session_cap, "evict.log")
        with running_worker(evict_cfg) as evict_handle:
            evict_client = WorkerClient(f"http://127.0.0.1:{args.probe_port}", CHAT_ID_HEADER,
                                         args.request_timeout, request_model=kv["hf_path"])
            turns = run_eviction_arm(evict_client, args.eviction_rounds, args.gen_max_tokens,
                                      args.request_timeout)
        if evict_handle.teardown_failed:
            teardown_failures.append("evict")
        log_events = count_log_events(
            evict_cfg.log_path.read_text(errors="replace") if evict_cfg.log_path.exists() else "")
        ratios = eviction_reuse_ratios(turns, EVICTION_SESSION_IDS)
        total_alt_turns = sum(len(v) for v in ratios.values())
        evictions_per_turn = (log_events["n_evictions"] / total_alt_turns) if total_alt_turns else 0.0
        report["eviction_thrash"] = verdict_eviction_thrash(
            ratios, threshold=args.thrash_reuse_threshold)
        report["eviction_thrash"]["evictions_per_turn"] = round(evictions_per_turn, 3)
        report["eviction_thrash"]["log_events"] = log_events
        report["eviction_turns"] = [dataclasses.asdict(t) for t in turns]

    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    report["teardown_failures"] = teardown_failures
    report["overall"] = overall_verdict(report)

    out_path = workdir / f"d6_probe_{args.model}_{int(time.time())}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    report["_out_path"] = str(out_path)

    _print_report(report)
    print(f"\njson -> {out_path}")
    if teardown_failures:
        print(f"WARNING: teardown did not verify clean for arm(s): {teardown_failures}",
              file=sys.stderr)

    return 0 if report["overall"]["verdict"] != "DO-NOT-ENABLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
