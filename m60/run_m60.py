#!/usr/bin/env python3
"""M60 — certification of the FINAL shipped state of the first pick on Math500 + cjudge generation.

Spec of record: <repo>/docs/specs/m60-shipped-state-certification.md. This file is SELF-CONTAINED
(no sourced shell functions, no helper module): one loaded instance, tune `m60ship`.

  preflight -> lean router (MLX_SERVE_CONFIG=main_models.yaml, MLX_VLM_CACHE_SESSION_MAX=1) ->
  ownership/env/worker verification -> Math500 pilot (5 recorded ids, tune m60ship) ->
  the SAME 5 ids again (tune m60ship-p2) -> pilot-twice compare -> cjudge pilot (5) ->
  cost go/no-go -> Math500 remaining 95 -> cjudge remaining 35 -> unload + stack_stop ->
  ROW GUARD -> grade -> reference regrade check -> paired read -> summary.

Launch (ONLY after the operator says the stack is down; never while a waiter may be alive):
  . "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
  cd "$STACK_WORKDIR/m60" && nohup "$STACK_REPO/.venv-bench/bin/python" run_m60.py \
      > run_m60.out 2>&1 < /dev/null &
Exit code is ALSO written to run_m60.rc (0 complete — read summary.json for the verdict;
2 preflight refusal; 3 tripwire/abort, nothing graded; 4 internal error).
  --dry-run        every CPU-side check + every command, no request, nothing started
  --analyze-only   row guard + grade + paired read over rows already on disk (no router)
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
TUNE, TUNE_P2 = "m60ship", "m60ship-p2"
REF_ON, REF_OFF = "m40on", "m37med"
SERVE_CONFIG = "main_models.yaml"          # the registry of record IS the shipped state
SESSION_MAX = "1"
BASE = "http://localhost:8000"
MATH_N, CJUDGE_N, CJUDGE_PILOT_N = 100, 40, 5
GO_NO_GO_H = 4.0                           # abort if a pilot projects more than this for its bench
BOUND_H = {"math500": 12.0, "cjudge": 8.0}  # driver wall bound (M40 values); never a tuning knob
MARGIN = 0.05
NONCONV_RED_FLAG = 3
LEN_RATIO_BAND = (0.8, 1.25)
WATCH_INTERVAL_S = 300
EXPECT_POWER = {"watt": 140, "mv": 28000, "batt_min": 20}
EXPECT_SAMPLING = {"temperature": 0.5, "top_p": 0.95, "top_k": 20, "min_p": 0.0,
                   "presence_penalty": 0.0, "max_tokens": 102400, "thinking_budget": 81920,
                   "enable_thinking": True, "reasoning_effort": "medium"}
BUSY_PATTERNS = ("mlx_vlm.server", "mlx_vlm/server", "mlx-serve start", "session_cache_probe",
                 "opencode run", "run.py generate", "run_opencode_probe", "run_agentbench_os",
                 "bench.run_", "vision_gate.py", "decode_probe", "parity_replay", "runserver.sh")

RC_OK, RC_REFUSED, RC_TRIPWIRE, RC_INTERNAL = 0, 2, 3, 4


class Refusal(Exception):
    """Preflight refusal — nothing was started."""


class Tripwire(Exception):
    """Abort; nothing is graded."""


# ============================================================================ pure helpers
def sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode()).hexdigest()


def reasoning_identity(row: dict):
    """The strongest reasoning identity a row carries: the full-trace sha when present, else the
    compressed view (head, tail, length)."""
    if row.get("reasoning_sha256") is not None:
        return ("sha", row["reasoning_sha256"])
    return ("compressed", row.get("reasoning_head"), row.get("reasoning_tail"), row.get("reasoning_chars"))


def pilot_twice_diff(rows_a: list, rows_b: list, ids: list) -> list:
    """Problems between two generations of the same ids on ONE loaded instance; [] = identical.
    Compares content, reasoning identity, completion tokens, finish reason and sampler seed."""
    probs = []
    a = {r["id"]: r for r in rows_a if r.get("sample", 0) == 0}
    b = {r["id"]: r for r in rows_b if r.get("sample", 0) == 0}
    for i in ids:
        if i not in a or i not in b:
            probs.append(f"{i}: missing in {'first' if i not in a else 'second'} generation")
            continue
        ra, rb = a[i], b[i]
        if ra.get("error") or rb.get("error"):
            probs.append(f"{i}: error row ({ra.get('error')!r} / {rb.get('error')!r})")
            continue
        for label, va, vb in (
                ("content", sha256_text(ra.get("content")), sha256_text(rb.get("content"))),
                ("reasoning", reasoning_identity(ra), reasoning_identity(rb)),
                ("completion_tokens", ra.get("completion_tokens"), rb.get("completion_tokens")),
                ("finish_reason", ra.get("finish_reason"), rb.get("finish_reason")),
                ("sampler_seed", ra.get("sampler_seed"), rb.get("sampler_seed"))):
            if va != vb:
                probs.append(f"{i}: {label} differs ({str(va)[:24]} vs {str(vb)[:24]})")
    return probs


def row_guard(rows: list) -> list:
    """Rows that must NEVER be graded: an error that is not the probe-timeout DNF (C119 is not
    built — `generate` still records transport/harness exceptions as error rows)."""
    return [{"id": r.get("id"), "error": str(r.get("error"))[:120], "error_kind": r.get("error_kind")}
            for r in rows if r.get("error") and r.get("error_kind") != "probe_timeout"]


def project_hours(walls_s: list, n_full: int):
    return (statistics.mean(walls_s) * n_full / 3600.0) if walls_s else None


def go_no_go(walls_s: list, n_full: int, bound_h: float = GO_NO_GO_H) -> dict:
    proj = project_hours(walls_s, n_full)
    return {"projected_h": None if proj is None else round(proj, 3), "bound_h": bound_h,
            "mean_s": round(statistics.mean(walls_s), 1) if walls_s else None,
            "max_s": round(max(walls_s), 1) if walls_s else None,
            "go": proj is not None and proj <= bound_h}


def m60_verdict(delta: float, lo: float, hi: float, margin: float = MARGIN) -> str:
    """Pre-registered (spec "Criteria"): PASS if the CI lower bound is above -margin (evaluated
    FIRST: a significant but sub-margin loss is the <=5 % lossy-lever case, as in
    compare_predictor); FAIL if the CI upper bound is below 0 or the point is <= -margin;
    otherwise INCONCLUSIVE."""
    if lo > -margin:
        return "PASS"
    if hi < 0 or delta <= -margin:
        return "FAIL"
    return "INCONCLUSIVE"


def discordant(new: dict, ref: dict) -> dict:
    ids = sorted(set(new) & set(ref))
    n_only = [i for i in ids if statistics.mean(new[i]) > statistics.mean(ref[i])]
    r_only = [i for i in ids if statistics.mean(new[i]) < statistics.mean(ref[i])]
    return {"new_only_wins": n_only, "ref_only_wins": r_only}


def paired_read(new: dict, ref: dict, *, iters: int = 10000, seed: int = 0, margin: float = MARGIN) -> dict:
    """new - ref on {item: [scores]} with the campaign's two-stage paired cluster bootstrap
    (`bench.stats.paired_delta`); the M60 verdict is read off (delta, lo, hi)."""
    from bench import stats
    d = stats.paired_delta(new, ref, iters=iters, seed=seed, margin=margin)
    out = {"delta": d["delta"], "lo": d["lo"], "hi": d["hi"], "n_items": d["n_items"], "mde": d["mde"],
           "stats_verdict": d["verdict"], "new": stats.pass_at_1(new), "ref": stats.pass_at_1(ref),
           "margin": margin, "iters": iters, "seed": seed}
    out.update(discordant(new, ref))
    out["m60_verdict"] = m60_verdict(d["delta"], d["lo"], d["hi"], margin)
    return out


def parse_power(ac_text: str, batt_text: str) -> dict:
    w = re.search(r"Wattage\s*=\s*(\d+)W", ac_text or "")
    v = re.search(r"Voltage\s*=\s*(\d+)mV", ac_text or "")
    b = re.search(r"(\d+)%", batt_text or "")
    return {"watt": int(w.group(1)) if w else None, "mv": int(v.group(1)) if v else None,
            "batt": int(b.group(1)) if b else None}


def power_problems(p: dict, expect: dict = EXPECT_POWER) -> list:
    probs = []
    if p.get("watt") != expect["watt"]:
        probs.append(f"adapter wattage {p.get('watt')} != {expect['watt']} W")
    if p.get("mv") != expect["mv"]:
        probs.append(f"adapter voltage {p.get('mv')} != {expect['mv']} mV")
    if p.get("batt") is None or p["batt"] <= expect["batt_min"]:
        probs.append(f"battery {p.get('batt')} % not above {expect['batt_min']} %")
    return probs


def registry_entry_problems(entry: dict) -> list:
    """The registry entry must BE the shipped state M60 certifies."""
    probs = []
    want = {"kv_bits": 0, "attention_policy": "fused_v1", "lazy_prompt_embeddings": True,
            "mtp_verify_scan": "joint_v1", "draft_kind": "mtp", "max_kv_cache_size": 262144,
            "kv_prealloc_tokens": 262144}
    for k, v in want.items():
        if entry.get(k) != v:
            probs.append(f"registry {k}={entry.get(k)!r}, expected {v!r}")
    if not entry.get("draft_model"):
        probs.append("registry draft_model missing")
    gd = entry.get("generation_defaults") or {}
    for k, v in EXPECT_SAMPLING.items():
        if gd.get(k) != v:
            probs.append(f"registry generation_defaults.{k}={gd.get(k)!r}, expected {v!r}")
    return probs


def worker_cmdline_problems(cmd: str) -> list:
    probs = []
    for needle in ("--attention-policy fused_v1", "--lazy-prompt-embeddings",
                   "--mtp-verify-scan joint_v1", "--draft-kind mtp", "--max-kv-size 262144",
                   "--kv-prealloc-tokens 262144"):
        if needle not in cmd:
            probs.append(f"worker cmdline lacks `{needle}`")
    m = re.search(r"--kv-bits\s+(\S+)", cmd)
    if m and m.group(1) not in ("0", "0.0"):
        probs.append(f"worker cmdline carries --kv-bits {m.group(1)} (native16 expected)")
    if "--mtp-verify-ab" in cmd:
        probs.append("worker cmdline carries --mtp-verify-ab (gate-1 AB mode, not the shipped state)")
    return probs


def manifest_problems(man: dict, registry_sha: str, fp_version: int, router_pid=None) -> list:
    probs = []
    rt, kv, sm = man.get("runtime") or {}, man.get("kv") or {}, man.get("sampling") or {}
    checks = [("runtime.draft_kind", rt.get("draft_kind"), "mtp"),
              ("runtime.attention_policy", rt.get("attention_policy"), "fused_v1"),
              ("runtime.lazy_prompt_embeddings", rt.get("lazy_prompt_embeddings"), True),
              ("runtime.mtp_verify_scan", rt.get("mtp_verify_scan"), "joint_v1"),
              ("kv.kv_bits", kv.get("kv_bits"), 0),
              ("kv.max_kv_cache_size", kv.get("max_kv_cache_size"), 262144),
              ("kv.kv_prealloc_tokens", kv.get("kv_prealloc_tokens"), 262144),
              ("registry.sha256", (man.get("registry") or {}).get("sha256"), registry_sha),
              ("fingerprint_version", man.get("fingerprint_version"), fp_version),
              ("sampling_profile", man.get("sampling_profile"), "deployed")]
    checks += [(f"sampling.{k}", sm.get(k), v) for k, v in EXPECT_SAMPLING.items()]
    for label, got, want in checks:
        if got != want:
            probs.append(f"{label}={got!r}, expected {want!r}")
    if fp_version < 8:
        probs.append(f"fingerprint version {fp_version} < 8")
    router = man.get("router")
    if isinstance(router, dict):
        if router.get("config_sha256") != registry_sha:
            probs.append(f"router.config_sha256={router.get('config_sha256')!r} != registry sha")
        if router_pid is not None and router.get("pid") != router_pid:
            probs.append(f"router.pid={router.get('pid')!r} != live router pid {router_pid}")
    else:
        probs.append("manifest has no router block (M50 attribution missing)")
    return probs


def _flatten(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, dict):
            out.update(_flatten(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def manifest_diff(a: dict, b: dict, skip=("timestamp", "router", "router_exit", "router_history",
                                         "runtime.n_todo", "runtime.n_done_before")) -> dict:
    fa, fb = _flatten(a), _flatten(b)
    out = {}
    for k in sorted(set(fa) | set(fb)):
        if any(k == s or k.startswith(s + ".") for s in skip):
            continue
        if fa.get(k) != fb.get(k):
            out[k] = [fa.get(k), fb.get(k)]
    return out


def summarize_rows(rows: list) -> dict:
    ok = [r for r in rows if not r.get("error")]
    walls = [r["wall_s"] for r in rows if isinstance(r.get("wall_s"), (int, float))]
    toks = [r.get("completion_tokens") or 0 for r in ok]
    dps = [r["decode_tps"] for r in ok if isinstance(r.get("decode_tps"), (int, float))]
    dn = sum((r.get("draft") or {}).get("draft_n") or 0 for r in ok)
    da = sum((r.get("draft") or {}).get("draft_n_accepted") or 0 for r in ok)
    ratios = [(r["draft"]["draft_n_accepted"] / r["draft"]["draft_n"]) for r in ok
              if (r.get("draft") or {}).get("draft_n")]
    counters = {}
    for r in ok:
        for grp in ("verify", "sdpa"):
            for k, v in (r.get(grp) or {}).items():
                if isinstance(v, (int, float)):
                    counters[k] = counters.get(k, 0) + v
                elif isinstance(v, dict):
                    slot = counters.setdefault(k, {})
                    for kk, vv in v.items():
                        slot[kk] = slot.get(kk, 0) + (vv if isinstance(vv, (int, float)) else 1)
    kinds = {}
    for r in rows:
        if r.get("nonconv_kind"):
            kinds[r["nonconv_kind"]] = kinds.get(r["nonconv_kind"], 0) + 1
    return {"n": len(rows), "errors": [(r.get("id"), r.get("error_kind"), str(r.get("error"))[:60])
                                       for r in rows if r.get("error")],
            "converged": sum(1 for r in ok if r.get("converged") is True),
            "non_converged": sum(1 for r in rows if r.get("error") or r.get("converged") is False),
            "nonconv_kinds": kinds,
            "wall_mean_s": round(statistics.mean(walls), 1) if walls else None,
            "wall_max_s": round(max(walls), 1) if walls else None,
            "wall_sum_h": round(sum(walls) / 3600, 3) if walls else None,
            "tok_mean": round(statistics.mean(toks)) if toks else None,
            "tok_max": max(toks) if toks else None,
            "decode_tps_mean": round(statistics.mean(dps), 2) if dps else None,
            "draft_rows_engaged": sum(1 for r in ok if (r.get("draft") or {}).get("draft_n")),
            "draft_rows_kind_mtp": sum(1 for r in ok if (r.get("draft") or {}).get("draft_kind") == "mtp"),
            "draft_acceptance_pooled": round(da / dn, 4) if dn else None,
            "draft_acceptance_mean_of_ratios": round(statistics.mean(ratios), 4) if ratios else None,
            "counters": counters}


def length_ratio(new_rows: list, ref_rows: list) -> dict:
    a = {r["id"]: r.get("completion_tokens") for r in new_rows if not r.get("error")}
    b = {r["id"]: r.get("completion_tokens") for r in ref_rows if not r.get("error")}
    ids = [i for i in a if i in b and a[i] and b[i]]
    if not ids:
        return {"n": 0, "ratio": None, "in_band": None}
    ratio = sum(a[i] for i in ids) / sum(b[i] for i in ids)
    return {"n": len(ids), "ratio": round(ratio, 4), "band": list(LEN_RATIO_BAND),
            "in_band": LEN_RATIO_BAND[0] <= ratio <= LEN_RATIO_BAND[1]}


def busy_processes(ps_lines: list, self_pids: set) -> list:
    out = []
    for line in ps_lines:
        parts = line.strip().split(None, 1)
        if len(parts) < 2 or not parts[0].isdigit() or int(parts[0]) in self_pids:
            continue
        if any(p in parts[1] for p in BUSY_PATTERNS):
            out.append(line.strip()[:160])
    return out


# ============================================================================ environment
def load_config_env() -> dict:
    """Machine-local values come from config.sh (never hard-coded): STACK_REPO, STACK_WORKDIR,
    MLX_BOX ... A missing redirection is a blocker."""
    cfg = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "mlx_local_stack" / "config.sh"
    env = dict(os.environ)
    if cfg.is_file():
        r = subprocess.run(["bash", "-c", f'set -a; . "{cfg}"; env -0'], capture_output=True, timeout=30)
        if r.returncode == 0:
            for kv in r.stdout.split(b"\0"):
                if b"=" in kv:
                    k, v = kv.split(b"=", 1)
                    env[k.decode()] = v.decode(errors="replace")
    return env


ENV = load_config_env()
for _k in ("STACK_REPO", "STACK_WORKDIR", "MLX_BOX"):
    if not ENV.get(_k):
        sys.stderr.write(f"REFUSED: {_k} is not set (config.sh not loaded) — blocker\n")
        sys.exit(RC_REFUSED)
REPO = Path(ENV["STACK_REPO"])
WD = Path(ENV["STACK_WORKDIR"]) / "m60"
PY = str(REPO / ".venv-bench" / "bin" / "python")
RESULTS = REPO / "benchmark" / "results" / MODEL
IDS_FILE = Path(ENV["STACK_WORKDIR"]) / "queue" / "resolution" / "ids.json"
DRY = False
_LOG = None
_STATE = {"router_owned": False, "power_ticks": [], "children": []}


def scrub(s: str) -> str:
    s = str(s)
    for real, ph in ((ENV["STACK_WORKDIR"], "$STACK_WORKDIR"), (str(REPO), "$STACK_REPO"),
                     (str(Path.home()), "$HOME")):
        s = s.replace(real, ph)
    return s


def log(msg: str) -> None:
    line = f"[{time.strftime('%m-%d %H:%M:%S')}] {'DRY ' if DRY else ''}{scrub(msg)}"
    print(line, flush=True)
    if _LOG is not None:
        _LOG.write(line + "\n")
        _LOG.flush()


def sh(cmd, timeout=60, **kw):
    kw.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)


def listeners() -> list:
    return [int(x) for x in sh(["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN", "-t"]).stdout.split()]


def ps_lines() -> list:
    return sh(["ps", "-axo", "pid=,args="]).stdout.splitlines()


def proc_env(pid: int) -> str:
    return sh(["ps", "-Eww", "-o", "command=", "-p", str(pid)]).stdout


def read_power() -> dict:
    return parse_power(sh(["pmset", "-g", "ac"]).stdout, sh(["pmset", "-g", "batt"]).stdout)


def rows_of(bench: str, tune: str) -> list:
    p = RESULTS / f"{bench}.{tune}.jsonl"
    if not p.is_file():
        return []
    out = []
    for n, line in enumerate(p.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            raise Tripwire(f"{p.name} line {n} is not valid JSON (torn row file)")
    return out


def count_rows(bench: str, tune: str) -> int:
    """Complete lines only — safe to call while the driver is appending (never parses a torn tail)."""
    p = RESULTS / f"{bench}.{tune}.jsonl"
    return p.read_bytes().count(b"\n") if p.is_file() else 0


def manifest_of(bench: str, tune: str):
    p = RESULTS / f"{bench}.{tune}.manifest.json"
    return json.loads(p.read_text()) if p.is_file() else None


def registry_sha() -> str:
    return hashlib.sha256((REPO / SERVE_CONFIG).read_bytes()).hexdigest()


def registry_entry() -> dict:
    import yaml
    data = yaml.safe_load((REPO / SERVE_CONFIG).read_text())
    for e in data.get("models") or []:
        if e.get("name") == MODEL:
            return e
    raise Refusal(f"{MODEL} not in {SERVE_CONFIG}")


def load_ids() -> tuple:
    d = json.loads(IDS_FILE.read_text())["math500"]
    ids, pilot = d["ids"], d["pilot"]
    if len(ids) != MATH_N or len(set(ids)) != MATH_N:
        raise Refusal(f"resolution ids.json[math500] has {len(ids)} ids, expected {MATH_N} distinct")
    if len(pilot) != 5 or not set(pilot) <= set(ids):
        raise Refusal("resolution ids.json[math500][pilot] is not 5 ids inside [ids]")
    return ids, pilot


def driver_env() -> dict:
    env = dict(ENV)
    env.pop("APC_ENABLED", None)
    env["MLX_SERVE_CONFIG"] = SERVE_CONFIG
    return env


# ============================================================================ preflight
def preflight(analyze_only: bool = False) -> dict:
    """Every CPU-side check. Real mode: any problem refuses. Dry-run: problems are listed as
    WOULD-REFUSE and the plan still prints; static problems (registry, references, ids) fail it."""
    static, dynamic = [], []
    entry = {}
    try:
        entry = registry_entry()
        static += registry_entry_problems(entry)
    except Refusal as e:
        static.append(str(e))
    try:
        ids, pilot = load_ids()
    except (Refusal, OSError, KeyError, ValueError) as e:
        ids, pilot = [], []
        static.append(f"resolution ids: {e}")
    for bench, tune, n in (("math500", REF_ON, MATH_N), ("math500", REF_OFF, MATH_N),
                           ("cjudge", REF_ON, CJUDGE_N)):
        try:
            rows = rows_of(bench, tune)
        except Tripwire as e:
            rows = []
            static.append(str(e))
        if len(rows) != n:
            static.append(f"reference {bench}.{tune}: {len(rows)} rows, expected {n}")
        elif bench == "math500" and {r["id"] for r in rows} != set(ids):
            static.append(f"reference math500.{tune}: item ids differ from the resolution id set")
        if manifest_of(bench, tune) is None:
            static.append(f"reference {bench}.{tune}: manifest missing")
        if bench == "math500" and not (RESULTS / f"{bench}.{tune}.score.json").is_file():
            static.append(f"reference {bench}.{tune}: committed score.json missing")
    anchors = REPO / "benchmark/results/judge_c_v1/pairs.jsonl"
    if not anchors.is_file():
        static.append("judge anchors benchmark/results/judge_c_v1/pairs.jsonl missing")
    for tool in ("uv", "lsof", "pmset"):
        if shutil.which(tool, path=ENV.get("PATH")) is None:
            static.append(f"`{tool}` not on PATH")
    if not Path(PY).is_file():
        static.append(f"{PY} missing")
    if not (REPO / "scripts/stack_stop.sh").is_file():
        static.append("scripts/stack_stop.sh missing")
    existing = {t: len(rows_of(b, t)) for b, t in (("math500", TUNE), ("math500", TUNE_P2), ("cjudge", TUNE))
                if (RESULTS / f"{b}.{t}.jsonl").exists()}
    if existing and not analyze_only:
        static.append(f"rows already exist for this arm {existing}: one loaded instance per arm — "
                      f"archive them (never --clean-stale) or use --analyze-only")

    ls = listeners()
    if ls:
        dynamic.append(f":8000 is bound by pid(s) {ls} — the stack must be DOWN (scripts/stack_stop.sh)")
    busy = busy_processes(ps_lines(), {os.getpid(), os.getppid()})
    if busy:
        dynamic.append(f"{len(busy)} serving/benchmark process(es) alive: " + " | ".join(busy[:4]))
    power = read_power()
    dynamic += power_problems(power)
    dk = sh(["docker", "compose", "ps", "-q"], cwd=str(REPO)) if shutil.which("docker") else None
    if dk is not None and dk.returncode == 0 and dk.stdout.strip():
        dynamic.append("docker compose services are up (OpenWebUI) — lean router only")
    hot = [l.strip()[:120] for l in sh(["ps", "-axo", "pcpu=,pid=,args="]).stdout.splitlines()
           if l.strip() and float(l.split()[0]) > 50.0 and int(l.split()[1]) != os.getpid()]
    info = {"registry_sha256": registry_sha(), "power": power, "hot_processes": hot,
            "git_head": sh(["git", "-C", str(REPO), "rev-parse", "HEAD"]).stdout.strip(),
            "submodules": sh(["git", "-C", str(REPO), "submodule", "status"]).stdout.strip().splitlines(),
            "registry_dirty": bool(sh(["git", "-C", str(REPO), "status", "--porcelain", SERVE_CONFIG]).stdout.strip())}
    log(f"preflight: registry sha256={info['registry_sha256'][:16]}… dirty={info['registry_dirty']} "
        f"head={info['git_head'][:7]} power={power}")
    for s in info["submodules"]:
        log(f"preflight: submodule {s.strip()}")
    if hot:
        log(f"preflight: WARN {len(hot)} process(es) above 50 % CPU (decode/wall figures are descriptive "
            f"only; sweep leaked pty shells before citing them): {hot[:3]}")
    for p in static:
        log(f"preflight: STATIC PROBLEM — {p}")
    for p in dynamic:
        log(f"preflight: {'WOULD REFUSE' if DRY else 'REFUSE'} — {p}")
    if not static and not dynamic:
        log("preflight: all checks pass")
    return {"static": static, "dynamic": dynamic, "info": info, "ids": ids, "pilot": pilot}


# ============================================================================ router
def start_router() -> int:
    env = dict(ENV)
    env.pop("APC_ENABLED", None)
    dotenv = REPO / ".env"            # AGENTS.md lean start: `set -a; . ./.env; set +a` when present
    if dotenv.is_file():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.replace("export ", "").strip()] = v.strip().strip('"').strip("'")
        env.pop("APC_ENABLED", None)
    env["MLX_VLM_CACHE_SESSION_MAX"] = SESSION_MAX
    env["MLX_SERVE_CONFIG"] = SERVE_CONFIG
    # --frozen --no-sync: never re-lock or re-sync the venv from the served source's metadata (the
    # submodule may sit on an unadopted merge sha whose requirements differ from uv.lock).
    cmd = ["uv", "run", "--frozen", "--no-sync", "mlx-serve", "start"]
    log(f"RUN router: MLX_VLM_CACHE_SESSION_MAX={SESSION_MAX} MLX_SERVE_CONFIG={SERVE_CONFIG} "
        f"nohup {' '.join(cmd)} >logs/main_model.log 2>&1 </dev/null &   (cwd=$STACK_REPO, APC_ENABLED absent)")
    if DRY:
        return -1
    if listeners():
        raise Refusal(":8000 became bound before the router start")
    (REPO / "logs").mkdir(exist_ok=True)
    subprocess.Popen(cmd, cwd=str(REPO), env=env, stdout=open(REPO / "logs/main_model.log", "a"),
                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    _STATE["router_owned"] = True
    for _ in range(90):
        if listeners():
            break
        time.sleep(2)
    return verify_router()


def verify_router() -> int:
    ls = listeners()
    if len(ls) != 1:
        raise Tripwire(f"expected exactly one :8000 listener, found {ls}")
    pid = ls[0]
    e = proc_env(pid)
    probs = []
    if "mlx-serve" not in e:
        probs.append("listener is not mlx-serve")
    if f"MLX_SERVE_CONFIG={SERVE_CONFIG}" not in e:
        probs.append(f"router env lacks MLX_SERVE_CONFIG={SERVE_CONFIG}")
    if f"MLX_VLM_CACHE_SESSION_MAX={SESSION_MAX}" not in e:
        probs.append(f"router env lacks MLX_VLM_CACHE_SESSION_MAX={SESSION_MAX}")
    if "APC_ENABLED" in e:
        probs.append("router env carries APC_ENABLED")
    cwd = sh(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"]).stdout
    if str(REPO) not in cwd:
        probs.append("router cwd is not the stack repo (MLX_SERVE_CONFIG would resolve elsewhere)")
    log(f"router pid={pid} owns :8000; env/cwd problems={probs or 'none'}")
    if probs:
        raise Tripwire("router ownership/environment: " + "; ".join(probs))
    return pid


def worker_procs() -> list:
    out = []
    for line in ps_lines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and "mlx_vlm.server" in parts[1] and MODEL in parts[1] and "uv run" not in parts[1]:
            out.append((int(parts[0]), parts[1]))
    return out


def force_load_and_verify_worker() -> dict:
    log(f"RUN load: POST {BASE}/v1/models/load {{\"model\": \"{MODEL}\", \"keep_alive\": \"240m\"}} (timeout 900 s)")
    if DRY:
        return {}
    headers = {"Content-Type": "application/json"}
    if ENV.get("MLX_API_KEY"):
        headers["Authorization"] = f"Bearer {ENV['MLX_API_KEY']}"
    req = urllib.request.Request(BASE + "/v1/models/load", method="POST", headers=headers,
                                 data=json.dumps({"model": MODEL, "keep_alive": "240m"}).encode())
    try:
        urllib.request.urlopen(req, timeout=900).read()
    except Exception as e:  # noqa: BLE001 — transport: abort
        raise Tripwire(f"model load failed: {type(e).__name__}: {e}")
    ws = worker_procs()
    if len(ws) != 1:
        raise Tripwire(f"expected exactly one worker for {MODEL}, found {len(ws)}")
    pid, cmd = ws[0]
    probs = worker_cmdline_problems(cmd)
    e = proc_env(pid)
    if "APC_ENABLED" in e:
        probs.append("worker env carries APC_ENABLED")
    if f"MLX_VLM_CACHE_SESSION_MAX={SESSION_MAX}" not in e:
        probs.append(f"worker env lacks MLX_VLM_CACHE_SESSION_MAX={SESSION_MAX}")
    log(f"worker pid={pid} cmdline: {cmd}")
    if probs:
        raise Tripwire("worker verification: " + "; ".join(probs))
    return {"pid": pid, "cmdline": scrub(cmd)}


def stop_stack() -> None:
    log("RUN unload: POST /v1/models/unload ; then scripts/stack_stop.sh ; then verify :8000 free and no worker")
    if DRY:
        return
    if listeners():
        try:
            urllib.request.urlopen(urllib.request.Request(BASE + "/v1/models/unload", method="POST", data=b""),
                                   timeout=180).read()
        except Exception as e:  # noqa: BLE001 — still stop by PID below
            log(f"unload POST failed ({type(e).__name__}: {e}); stopping by PID")
    r = sh(["bash", str(REPO / "scripts/stack_stop.sh")], timeout=300, cwd=str(REPO))
    log(f"stack_stop rc={r.returncode} {(r.stdout + r.stderr).strip()[-200:]}")
    left = busy_processes(ps_lines(), {os.getpid(), os.getppid()})
    if listeners() or left:
        raise Tripwire(f"stack not down after stack_stop: listeners={listeners()} processes={left[:3]}")
    _STATE["router_owned"] = False
    log("stack stopped: :8000 free, no serving process (left stopped — the operator restarts the daily driver)")


# ============================================================================ generation
def generate_cmd(bench: str, tune: str, *, ids=None, limit=None) -> list:
    cmd = [PY, str(REPO / "benchmark/run.py"), "generate", "--models", MODEL, "--benches", bench,
           "--seed", "0", "--seed-base", "0", "--samples", "1", "--order", "roundrobin",
           "--sampling-profile", "deployed", "--tune", tune, "--chunks", "all"]
    if ids is not None:           # named ids, as M40: limit 0 = whole corpus, ids select
        cmd += ["--limit", f"{bench}=0", "--ids", f"{bench}=" + ":".join(ids)]
    else:
        cmd += ["--limit", f"{bench}={limit}"]
    return cmd                    # no --probe-timeout: DERIVED (C28); no retries exist in the client


def run_generate(tag: str, bench: str, tune: str, total: int, router_pid: int, *, ids=None, limit=None,
                 fresh_manifest: bool) -> None:
    cmd = generate_cmd(bench, tune, ids=ids, limit=limit)
    log(f"RUN {tag}: MLX_SERVE_CONFIG={SERVE_CONFIG} {' '.join(cmd)}")
    wcmd = [PY, str(REPO / "benchmark/m1/bench_watch.py"), "--models", MODEL, "--bench", bench, "--tune", tune,
            "--total", str(total), "--driver-pattern", "[r]un.py generate", "--out", str(WD / f"watch_{tag}.json"),
            "--interval", str(WATCH_INTERVAL_S)]
    log(f"RUN {tag} watcher: PYTHONPATH=$STACK_REPO/benchmark {' '.join(wcmd)}")
    if DRY:
        return
    env = driver_env()
    t0 = time.time()
    drv = subprocess.Popen(cmd, cwd=str(REPO), env=env, stdout=open(WD / f"{tag}.log", "a"),
                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    (WD / f"{tag}.pid").write_text(str(drv.pid))
    _STATE["children"].append(drv)
    wenv = dict(env, PYTHONPATH=str(REPO / "benchmark"))
    w = subprocess.Popen(wcmd, cwd=str(REPO), env=wenv, stdout=open(WD / f"watch_{tag}.log", "a"),
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    _STATE["children"].append(w)
    if f"MLX_SERVE_CONFIG={SERVE_CONFIG}" not in proc_env(drv.pid):
        drv.kill(); drv.wait(); w.kill(); w.wait()
        raise Tripwire(f"{tag}: driver pid {drv.pid} env lacks MLX_SERVE_CONFIG={SERVE_CONFIG}")
    mp = RESULTS / f"{bench}.{tune}.manifest.json"
    checked, rc, next_tick = False, None, time.time() + WATCH_INTERVAL_S
    reg_sha = registry_sha()
    try:
        while rc is None:
            rc = drv.poll()
            if not checked and mp.is_file() and (not fresh_manifest or mp.stat().st_mtime >= t0 - 5):
                try:
                    man = json.loads(mp.read_text())
                except ValueError:
                    man = None                      # mid-write; retry on the next poll
                if man is not None:
                    probs = manifest_problems(man, reg_sha, _fingerprint_version(), router_pid)
                    log(f"first-manifest check {tag}: {'OK' if not probs else 'MISMATCH ' + '; '.join(probs)}")
                    checked = True
                    if probs:
                        drv.kill(); drv.wait()
                        raise Tripwire(f"{tag}: provenance mismatch — driver killed before item two; "
                                       f"rows under {bench}.{tune} are FALSE-PROVENANCE, archive them")
            if time.time() >= next_tick:
                next_tick = time.time() + WATCH_INTERVAL_S
                p = read_power()
                pp = power_problems(p)
                _STATE["power_ticks"].append({"t": int(time.time()), **p, "ok": not pp})
                log(f"tick {tag}: rows={count_rows(bench, tune)}/{total} power={p}"
                    f"{' POWER DEVIATION ' + '; '.join(pp) if pp else ''} router_alive={bool(listeners())}")
            if time.time() - t0 > BOUND_H[bench] * 3600:
                drv.kill(); drv.wait()
                raise Tripwire(f"{tag}: driver exceeded the {BOUND_H[bench]} h bound — killed by PID")
            time.sleep(2 if not checked else 10)
    finally:
        if drv.poll() is None:          # only on an abort path: the stack is being stopped anyway
            drv.kill(); drv.wait()
        w.kill(); w.wait()
    log(f"END {tag} rc={rc} elapsed={time.time() - t0:.0f}s")
    if rc != 0:
        raise Tripwire(f"{tag}: generate exited {rc} (transport/M50/C106 refusals exit nonzero) — see {tag}.log")
    if not checked:
        raise Tripwire(f"{tag}: the manifest was never verified")


_FP = {}


def _fingerprint_version() -> int:
    if "v" not in _FP:
        r = sh([PY, "-c", "from bench import provenance; print(provenance.FINGERPRINT_VERSION)"],
               cwd=str(REPO / "benchmark"), env=driver_env())
        _FP["v"] = int(r.stdout.strip())
    return _FP["v"]


def check_phase_rows(tag: str, bench: str, tune: str, expect_n: int, ids=None) -> dict:
    rows = rows_of(bench, tune)
    if ids is not None:
        rows = [r for r in rows if r["id"] in set(ids)]
    s = summarize_rows(rows)
    log(f"SUMMARY {tag}: {json.dumps(s)}")
    bad = row_guard(rows)
    if bad:
        raise Tripwire(f"{tag}: ROW GUARD — {len(bad)} non-DNF error row(s) {bad[:3]}; nothing is graded")
    if s["n"] != expect_n:
        raise Tripwire(f"{tag}: {s['n']} rows, expected {expect_n}")
    if s["draft_rows_engaged"] + len(s["errors"]) < s["n"] or s["draft_rows_kind_mtp"] + len(s["errors"]) < s["n"]:
        raise Tripwire(f"{tag}: MTP did not engage on every generated row "
                       f"({s['draft_rows_engaged']}/{s['n']}) — not the shipped state")
    return s


# ============================================================================ analysis
def _bench_imports():
    sys.path.insert(0, str(REPO / "benchmark"))
    os.environ["MLX_SERVE_CONFIG"] = str(REPO / SERVE_CONFIG)
    for k in ("STACK_WORKDIR", "STACK_REPO", "MLX_BOX"):
        os.environ.setdefault(k, ENV[k])
    from bench import compare as CMP
    from bench import grade
    return grade, CMP


def run_grade(bench: str) -> dict:
    cmd = [PY, str(REPO / "benchmark/run.py"), "grade", "--models", MODEL, "--benches", bench, "--tune", TUNE]
    log(f"RUN grade {bench}: MLX_SERVE_CONFIG={SERVE_CONFIG} {' '.join(cmd)}")
    if DRY:
        return {}
    r = sh(cmd, timeout=3600, cwd=str(REPO), env=driver_env())
    (WD / f"grade_{bench}.log").write_text(r.stdout + r.stderr)
    if r.returncode:
        raise Tripwire(f"grade {bench} exited {r.returncode} — see grade_{bench}.log")
    return json.loads((RESULTS / f"{bench}.{TUNE}.score.json").read_text())


def analyze(ids: list) -> dict:
    """Row guard -> grade -> reference regrade check -> paired read -> summary (no router needed)."""
    out = {"model": MODEL, "tune": TUNE, "registry_sha256": registry_sha()}
    math_rows, cj_rows = rows_of("math500", TUNE), rows_of("cjudge", TUNE)
    bad = row_guard(math_rows) + row_guard(cj_rows)
    if bad:
        raise Tripwire(f"ROW GUARD: {len(bad)} non-DNF error row(s) {bad[:3]}; nothing is graded")
    if len(math_rows) != MATH_N or {r["id"] for r in math_rows} != set(ids):
        raise Tripwire(f"math500.{TUNE}: {len(math_rows)} rows or id set differs from the resolution set")
    if len(cj_rows) != CJUDGE_N:
        raise Tripwire(f"cjudge.{TUNE}: {len(cj_rows)} rows, expected {CJUDGE_N}")
    out["rows"] = {"math500": summarize_rows(math_rows), "cjudge": summarize_rows(cj_rows)}
    out["scores"] = {"math500": {k: v for k, v in run_grade("math500").items() if k in
                                 ("n", "acc", "acc_strict", "acc_strict_budget", "conv_rate", "nonconv_kinds", "errors")},
                     "cjudge": {k: v for k, v in run_grade("cjudge").items() if k in ("n", "conv_rate", "nonconv_kinds", "errors")}}
    grade, CMP = _bench_imports()
    scores = {t: grade.grade("math500", MODEL, tune=t) for t in (TUNE, REF_ON, REF_OFF)}
    moved = {}
    for t in (REF_ON, REF_OFF):       # same grader code for all three; committed files untouched
        committed = json.loads((RESULTS / f"math500.{t}.score.json").read_text())
        for k in ("n", "acc", "acc_strict", "conv_rate"):
            if scores[t].get(k) != committed.get(k):
                moved[f"{t}.{k}"] = [committed.get(k), scores[t].get(k)]
    out["reference_regrade"] = {"moved": moved}
    if moved:
        raise Tripwire(f"a reference score MOVED under today's grader: {moved} — stop and report")
    per = {t: CMP._per_item(scores[t], strict=True) for t in scores}
    mans = {t: manifest_of("math500", t) for t in scores}
    out["manifest_diff_vs_m40on"] = manifest_diff(mans[REF_ON], mans[TUNE])
    log("paired read compares ACROSS these manifest differences (M60 pre-registered instrument; "
        "compare_predictor refuses a multi-key pair by design):")
    for k, (a, b) in out["manifest_diff_vs_m40on"].items():
        log(f"  {k}: {REF_ON}={str(a)[:70]} -> {TUNE}={str(b)[:70]}")
    out["math500_vs_m40on"] = paired_read(per[TUNE], per[REF_ON])
    out["math500_vs_m37med_descriptive"] = paired_read(per[TUNE], per[REF_OFF])
    nc = out["rows"]["math500"]["non_converged"]
    out["math500_red_flag"] = nc >= NONCONV_RED_FLAG
    conv_new = {r["id"] for r in cj_rows if r.get("converged") is True and not r.get("error")}
    conv_ref = {r["id"] for r in rows_of("cjudge", REF_ON) if r.get("converged") is True and not r.get("error")}
    out["cjudge"] = {"converged": len(conv_new), "shared_converged_with_m40on": len(conv_new & conv_ref),
                     "all_converge": len(conv_new) == CJUDGE_N,
                     "ready_for_judge_pass": len(conv_new) == CJUDGE_N and len(conv_new & conv_ref) >= 38,
                     "length_ratio_vs_m40on": length_ratio(cj_rows, rows_of("cjudge", REF_ON))}
    out["power_ticks_ok"] = all(t["ok"] for t in _STATE["power_ticks"]) if _STATE["power_ticks"] else None
    v = out["math500_vs_m40on"]
    out["math500_verdict"] = "RED_FLAG" if out["math500_red_flag"] else v["m60_verdict"]
    (WD / "summary.json").write_text(json.dumps(out, indent=1))
    lr = out["cjudge"]["length_ratio_vs_m40on"]
    md = [f"# M60 generation summary — {MODEL} @ {TUNE}", "",
          f"- Math500 `acc_strict@81920`: new {v['new']:.3f} vs `{REF_ON}` {v['ref']:.3f}; delta {v['delta']:+.3f} "
          f"CI95 [{v['lo']:+.3f}, {v['hi']:+.3f}], n={v['n_items']}, MDE ±{v['mde']:.3f}; new-only wins "
          f"{len(v['new_only_wins'])}, `{REF_ON}`-only wins {len(v['ref_only_wins'])} -> **{out['math500_verdict']}**",
          f"- descriptive vs `{REF_OFF}`: delta {out['math500_vs_m37med_descriptive']['delta']:+.3f} "
          f"[{out['math500_vs_m37med_descriptive']['lo']:+.3f}, {out['math500_vs_m37med_descriptive']['hi']:+.3f}]",
          f"- Math500 non-converged {nc}/{MATH_N} (red flag at >= {NONCONV_RED_FLAG}): {out['rows']['math500']['nonconv_kinds']}",
          f"- cjudge: converged {out['cjudge']['converged']}/{CJUDGE_N}, shared converged with `{REF_ON}` "
          f"{out['cjudge']['shared_converged_with_m40on']}; token-length ratio {lr.get('ratio')} "
          f"(band {list(LEN_RATIO_BAND)}, in band: {lr.get('in_band')}); ready for the judge pass: "
          f"{out['cjudge']['ready_for_judge_pass']}",
          f"- decode tok/s mean: math {out['rows']['math500']['decode_tps_mean']}, cjudge {out['rows']['cjudge']['decode_tps_mean']} "
          f"(descriptive; power ok on every tick: {out['power_ticks_ok']})",
          f"- MTP acceptance pooled: math {out['rows']['math500']['draft_acceptance_pooled']}, cjudge {out['rows']['cjudge']['draft_acceptance_pooled']}",
          f"- counters: math {out['rows']['math500']['counters']}", "",
          "Judge pass: see JUDGE.md (no GPU). No registry, pick or order change is made by this script."]
    (WD / "summary.md").write_text("\n".join(md) + "\n")
    log(f"VERDICT math500: {out['math500_verdict']}  (summary.json / summary.md written)")
    return out


def dry_selftest(ids: list) -> list:
    """Known-positive checks of the instruments on data that already exists (no request): the
    reference regrade, the paired read on the certified m40on-vs-m37med pair, the manifest check on
    the newest shipped-state v8 manifest, and the worker-cmdline check on the live worker."""
    probs = []
    grade, CMP = _bench_imports()
    scores = {t: grade.grade("math500", MODEL, tune=t) for t in (REF_ON, REF_OFF)}
    for t in (REF_ON, REF_OFF):
        committed = json.loads((RESULTS / f"math500.{t}.score.json").read_text())
        moved = {k: [committed.get(k), scores[t].get(k)] for k in ("n", "acc", "acc_strict", "conv_rate")
                 if scores[t].get(k) != committed.get(k)}
        log(f"selftest reference regrade math500.{t}: acc_strict={scores[t].get('acc_strict')} "
            f"n={scores[t].get('n')} moved={moved or 'nothing'}")
        if moved:
            probs.append(f"reference math500.{t} moves under today's grader: {moved}")
    per = {t: CMP._per_item(scores[t], strict=True) for t in scores}
    if set(per[REF_ON]) != set(ids):
        probs.append("strict per-item ids of m40on differ from the resolution id set")
    kp = paired_read(per[REF_ON], per[REF_OFF])
    log(f"selftest paired read {REF_ON} - {REF_OFF} (M40 record: +0.02 CI [0, +0.05], 2 discordant, 0 OFF-only): "
        f"delta={kp['delta']:+.3f} CI[{kp['lo']:+.3f},{kp['hi']:+.3f}] new_only={len(kp['new_only_wins'])} "
        f"ref_only={len(kp['ref_only_wins'])} m60_verdict={kp['m60_verdict']}")
    if round(kp["delta"], 4) != 0.02 or len(kp["new_only_wins"]) != 2 or kp["ref_only_wins"]:
        probs.append(f"paired-read known positive does not reproduce the M40 record: {kp}")
    md = manifest_diff(manifest_of("math500", REF_OFF), manifest_of("math500", REF_ON))
    log(f"selftest manifest diff {REF_OFF} -> {REF_ON}: {sorted(md)}")
    v8 = RESULTS / "vision_gate.m58-adopted-20261006.manifest.json"
    if v8.is_file():
        mp = manifest_problems(json.loads(v8.read_text()), registry_sha(), _fingerprint_version())
        log(f"selftest manifest check on {v8.name} (shipped state, expect no problems): {mp or 'OK'}")
        if mp:
            probs.append(f"manifest check rejects the adopted-state manifest: {mp}")
    else:
        log(f"selftest: {v8.name} absent — manifest check not exercised")
    ws = worker_procs()
    if ws:
        wp = worker_cmdline_problems(ws[0][1])
        log(f"selftest worker-cmdline check on the LIVE worker pid {ws[0][0]} (daily driver, shipped state): {wp or 'OK'}")
        if wp:
            probs.append(f"worker cmdline check rejects the live shipped-state worker: {wp}")
    else:
        log("selftest: no live worker — cmdline check not exercised")
    log(f"selftest fingerprint version (bench.provenance): {_fingerprint_version()}")
    return probs


# ============================================================================ main
def plan_and_run(args) -> int:
    pf = preflight(args.analyze_only)
    if pf["static"] and not DRY:
        log("REFUSED: static preflight problems")
        return RC_REFUSED
    ids, pilot = pf["ids"], pf["pilot"]
    if args.analyze_only:       # CPU only: no router, no dynamic preflight needed
        analyze(ids)
        return RC_OK
    if pf["dynamic"] and not DRY:
        log("REFUSED: preflight")
        return RC_REFUSED
    state = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "preflight": pf["info"]}
    router_pid = start_router()
    state["router_pid"] = router_pid
    state["worker"] = force_load_and_verify_worker()
    wpid = (state["worker"] or {}).get("pid")

    run_generate("math500_pilot_p1", "math500", TUNE, 5, router_pid, ids=pilot, fresh_manifest=True)
    run_generate("math500_pilot_p2", "math500", TUNE_P2, 5, router_pid, ids=pilot, fresh_manifest=True)
    if not DRY:
        s1 = check_phase_rows("math500_pilot_p1", "math500", TUNE, 5)
        check_phase_rows("math500_pilot_p2", "math500", TUNE_P2, 5)
        if [p for p, _ in worker_procs()] != [wpid]:
            raise Tripwire("the worker changed between the two pilot generations — not one loaded instance")
        diff = pilot_twice_diff(rows_of("math500", TUNE), rows_of("math500", TUNE_P2), pilot)
        log(f"PILOT-TWICE: {'IDENTICAL 5/5' if not diff else 'MISMATCH ' + '; '.join(diff)}")
        if diff:
            raise Tripwire("pilot-twice mismatch on one loaded instance — stop and report")
        state["pilot_twice"] = "identical 5/5"
    else:
        log("PLAN pilot-twice: compare content sha, reasoning identity, completion tokens, finish reason, "
            "sampler seed over the 5 pilot ids (m60ship vs m60ship-p2); refuse on any difference")
    run_generate("cjudge_pilot", "cjudge", TUNE, CJUDGE_PILOT_N, router_pid, limit=CJUDGE_PILOT_N, fresh_manifest=True)
    if not DRY:
        s2 = check_phase_rows("cjudge_pilot", "cjudge", TUNE, CJUDGE_PILOT_N)
        g_math = go_no_go([r["wall_s"] for r in rows_of("math500", TUNE)], MATH_N)
        g_cj = go_no_go([r["wall_s"] for r in rows_of("cjudge", TUNE)], CJUDGE_N)
        state["go_no_go"] = {"math500": g_math, "cjudge": g_cj}
        log(f"GO/NO-GO math500 {g_math} | cjudge {g_cj} (lower bounds: pilot mean x n; max shown for the tail)")
        if not (g_math["go"] and g_cj["go"]):
            raise Tripwire(f"cost no-go: a pilot projects more than {GO_NO_GO_H} h — stop and report")
        del s1, s2
    else:
        log(f"PLAN go/no-go: abort if pilot mean wall x n projects > {GO_NO_GO_H} h for either bench")
    run_generate("math500_full", "math500", TUNE, MATH_N, router_pid, ids=ids, fresh_manifest=False)
    run_generate("cjudge_full", "cjudge", TUNE, CJUDGE_N, router_pid, limit=CJUDGE_N, fresh_manifest=False)
    if not DRY:
        check_phase_rows("math500_full", "math500", TUNE, MATH_N)
        check_phase_rows("cjudge_full", "cjudge", TUNE, CJUDGE_N)
        single = [p for p, _ in worker_procs()] == [wpid] and listeners() == [router_pid]
        state["single_loaded_instance"] = single
        log(f"single loaded instance for the whole arm: {single}")
        if not single:
            raise Tripwire("router or worker changed during the arm — rows span more than one loaded instance")
    stop_stack()
    if not DRY:
        (WD / "state.json").write_text(json.dumps(state, indent=1))
    if DRY:
        run_grade("math500"); run_grade("cjudge")
        log("PLAN analyze: row guard; in-memory regrade of math500 m40on + m37med with today's grader (refuse if "
            "n/acc/acc_strict/conv_rate move vs the committed score.json); paired read new - m40on on acc_strict "
            "(bench.stats.paired_delta, 10000 iters, seed 0); descriptive vs m37med; summary.json + summary.md")
        st = dry_selftest(ids) if not pf["static"] else ["skipped: static preflight problems"]
        for p in st:
            log(f"selftest PROBLEM — {p}")
        log("DRY-RUN complete: no request sent, nothing started, no row written")
        return RC_REFUSED if (pf["static"] or st) else RC_OK
    analyze(ids)
    return RC_OK


def main(argv=None) -> int:
    global DRY, _LOG
    ap = argparse.ArgumentParser(description="M60 shipped-state certification — generation phase")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--analyze-only", action="store_true")
    args = ap.parse_args(argv)
    DRY = args.dry_run
    WD.mkdir(parents=True, exist_ok=True)
    _LOG = open(WD / ("dry_run.log" if DRY else "status.log"), "a", buffering=1)
    lock = None
    rc = RC_INTERNAL
    try:
        if not DRY:
            lock = open(WD / "run.lock", "w")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                log("REFUSED: another run_m60.py holds run.lock")
                return RC_REFUSED
            (WD / "run_m60.pid").write_text(str(os.getpid()))
            (WD / ("analyze.rc" if args.analyze_only else "run_m60.rc")).unlink(missing_ok=True)
        log(f"M60 start: model={MODEL} tune={TUNE} mode={'dry-run' if DRY else 'analyze-only' if args.analyze_only else 'RUN'}")
        rc = plan_and_run(args)
    except Refusal as e:
        log(f"REFUSED: {e}")
        rc = RC_REFUSED
    except Tripwire as e:
        log(f"ABORT (nothing graded from here): {e}")
        rc = RC_TRIPWIRE
    except Exception as e:  # noqa: BLE001
        log(f"INTERNAL ERROR: {type(e).__name__}: {e}")
        rc = RC_INTERNAL
    finally:
        for c in _STATE["children"]:
            if c.poll() is None:
                c.kill()
        if _STATE["router_owned"] and not DRY:
            try:
                stop_stack()
            except Exception as e:  # noqa: BLE001
                log(f"STACK STILL UP after abort: {e} — stop it by PID (scripts/stack_stop.sh)")
                rc = rc or RC_TRIPWIRE
        if not DRY:
            (WD / ("analyze.rc" if args.analyze_only else "run_m60.rc")).write_text(f"{rc}\n")
        log(f"M60 exit rc={rc}")
    return rc


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(Tripwire("SIGTERM")))
    sys.exit(main())
