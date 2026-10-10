"""C147 chain operations: router/worker lifecycle, gates, run log, leg validation, cancellation predicate.

Extracted from the frozen M59 runner (benchmark/chains/m59/run_m59.py) with its tripwires intact; every external
effect (ps/lsof/pmset/vm_stat, HTTP, process spawn, sleep) goes through an injectable callable so the module is
tested on fake outputs. `leg_rate_check` and `mem_watchdog.py` are deliberately NOT carried over (spec 3).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

CAMPAIGN_POLICY_SHA = "ba86ba16e40e5e7b3535d64de2de9e95b323158049358b1f41b2ed26a83bb15c"
SCAFFOLD = "opencode-v2-web-tg1"
PICK1 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
PICK2 = "Qwen3.8-27B-mlx-uniform-4bit"
BUSY = ("mlx_vlm.server", "mlx_vlm/server", "mlx-serve start", "session_cache_probe", "opencode run",
        "run.py generate", "run_opencode_probe", "run_agentbench_os", "runserver.sh")
SELF_MARKERS = ("run_tg1_chain.py", "run_inject.py", "drive_chain.sh", "drive_inject.sh")
GRADER_TIMEOUT_S = {"python": 300, "go": 180}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ChainAbort(Exception):
    """A chain-level abort; the runner maps it to its exit code (2 unless stated)."""

    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code


def utc_stamp(t=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def file_sha(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


# --------------------------------------------------------------------------- run log
class RunLog:
    """RUNLOG.md append + stdout, UTC timestamps. `out` and `clock` are injectable."""

    def __init__(self, path, out=None, clock=None):
        self.path = Path(path)
        self.out = out or (lambda s: print(s, flush=True))
        self.clock = clock or time.time
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, msg):
        line = f"{utc_stamp(self.clock())} {msg}"
        self.out(line)
        with self.path.open("a") as f:
            f.write("- " + line + "\n")
        return line


# --------------------------------------------------------------------------- overlay
def make_overlay(src, dst):
    """Draft-OFF bench overlay. Recipe copied from benchmark/chains/m59/make_overlay.py (M59): the registry with
    every draft_*/moe_expand/mtp_verify_scan field removed. NEVER commit; never point the daily driver at it."""
    import yaml
    raw = Path(src).read_text()
    d = yaml.safe_load(raw)
    for m in d["models"]:
        for k in [k for k in m if k.startswith("draft") or k in ("moe_expand", "mtp_verify_scan")]:
            m.pop(k)
    head = (f"# C147 BENCH OVERLAY (draft-OFF) -- generated from main_models.yaml sha256 "
            f"{hashlib.sha256(raw.encode()).hexdigest()[:16]}; every draft_*/moe_expand/mtp_verify_scan field "
            f"removed (recipe of M59 make_overlay.py). NEVER commit; never point the daily-driver router at it.\n")
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(head + yaml.safe_dump(d, sort_keys=False))
    return str(dst)


# --------------------------------------------------------------------------- default effects
class Result:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def default_sh(cmd, *, timeout=120, cwd=None, env=None, shell=False):
    """Run in its OWN session; a timeout signals only that group (ownership by session, never by path)."""
    p = subprocess.Popen(cmd, shell=shell, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         stdin=subprocess.DEVNULL, text=True, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.communicate()
        raise
    return Result(out, err, p.returncode)


def default_http(base, path, body=None, timeout=900, headers=None):
    req = urllib.request.Request(base + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout).read()


def default_create_time(pid):
    import psutil
    return psutil.Process(int(pid)).create_time()


def env_tripwires(env_text, overlay):
    """Router/worker environment tripwires over `ps -E` output (spec 3, M59)."""
    probs = []
    if not re.search(rf"(^|\s)MLX_SERVE_CONFIG={re.escape(str(overlay))}(\s|$)", env_text):
        probs.append("MLX_SERVE_CONFIG")
    if not re.search(r"(^|\s)MLX_VLM_CACHE_SESSION_MAX=1(\s|$)", env_text):
        probs.append("SESSION_MAX")
    if "APC_ENABLED" in env_text:
        probs.append("APC_ENABLED present")
    return probs


def parse_power(ac_out, batt_out):
    w = re.search(r"Wattage\s*=\s*(\d+)\s*W", ac_out or "")
    v = re.search(r"Voltage\s*=\s*(\d+)\s*(mV|V)", ac_out or "")
    b = re.search(r"(\d+)%", batt_out or "")
    volts = None
    if v:
        volts = int(v.group(1)) / 1000 if v.group(2) == "mV" else int(v.group(1))
    return {"watts": int(w.group(1)) if w else None, "volts": volts, "batt": int(b.group(1)) if b else None}


def parse_free_mb(vm_out):
    ps = re.search(r"page size of (\d+) bytes", vm_out or "")
    free = re.search(r"Pages free:\s+(\d+)\.", vm_out or "")
    spec = re.search(r"Pages speculative:\s+(\d+)\.", vm_out or "")
    if not (ps and free):
        return None
    pages = int(free.group(1)) + (int(spec.group(1)) if spec else 0)
    return pages * int(ps.group(1)) // (1024 * 1024)


class ChainOps:
    """Stack operations with injectable effects. `sh(cmd, timeout=, cwd=, env=, shell=)` returns an object with
    .stdout/.returncode; `http(path, body=None, timeout=)` returns bytes; `popen` spawns the router."""

    def __init__(self, repo, workdir, overlay, log, *, sh=None, http=None, popen=None, sleep=time.sleep,
                 create_time=None, base="http://localhost:8000", registry=None, env_source=None):
        self.repo, self.wd, self.overlay = Path(repo), Path(workdir), str(overlay)
        self.log = log
        self.sh = sh or default_sh
        self._http = http or (lambda path, body=None, timeout=900: default_http(base, path, body, timeout))
        self.popen = popen or subprocess.Popen
        self.sleep = sleep
        self.create_time = create_time or default_create_time
        self.registry = Path(registry) if registry else self.repo / "main_models.yaml"
        self.env_source = env_source if env_source is not None else os.environ
        self.tmpdir = self.wd / "c147" / "tmp"
        self.py = self.repo / ".venv-bench/bin/python"
        self.receipt = self.wd / "session_gate/a4_v2_latest.json"
        self.loaded = None

    # -- environment
    def env_base(self):
        env = {k: v for k, v in self.env_source.items() if k != "APC_ENABLED"}
        dotenv = self.repo / ".env"
        if dotenv.is_file():
            for line in dotenv.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.replace("export ", "").strip()] = v.strip().strip('"').strip("'")
        env.pop("APC_ENABLED", None)
        env["STACK_WORKDIR"] = str(self.wd)
        env["MLX_SERVE_CONFIG"] = self.overlay
        env["MLX_VLM_CACHE_SESSION_MAX"] = "1"
        env["MLX_VLM_LOG_FILE"] = "logs/mlx_vlm.log"
        env["MLX_VLM_LOG_LEVEL"] = "INFO"
        env["TMPDIR"] = str(self.tmpdir)
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        return env

    def ensure_overlay(self):
        if not Path(self.overlay).is_file():
            make_overlay(self.registry, self.overlay)
        return self.overlay

    def overlay_sha(self):
        return file_sha(self.overlay)

    # -- state
    def power_state(self):
        ac = self.sh(["pmset", "-g", "ac"]).stdout
        batt = self.sh(["pmset", "-g", "batt"]).stdout
        return parse_power(ac, batt)

    def orphans_clean(self):
        o = self.sh([str(self.repo / "scripts/sweep_orphan_shells.sh")]).stdout
        return "no orphaned" in o

    def power_ok(self):
        """140 W AND 28 V adapter, battery strictly > 20 %, orphan-shell sweep clean."""
        s = self.power_state()
        orphans = self.orphans_clean()
        ok = (s["watts"] == 140 and s["volts"] == 28 and s["batt"] is not None and s["batt"] > 20 and orphans)
        self.log(f"GATE adapter={s['watts']}W {s['volts']}V batt={s['batt']}% orphans={'0' if orphans else 'PRESENT'}"
                 f" -> {'ok' if ok else 'FAIL'}")
        return bool(ok)

    def free_mem_mb(self):
        return parse_free_mb(self.sh(["vm_stat"]).stdout)

    def listeners(self, port=8000):
        out = self.sh(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"]).stdout
        return sorted({int(line[1:]) for line in out.splitlines() if line.startswith("p") and line[1:].isdigit()})

    def busy_procs(self):
        out = self.sh(["ps", "-axo", "pid=,command="]).stdout
        me = os.getpid()
        res = []
        for line in out.splitlines():
            parts = line.split(None, 1)
            if len(parts) < 2 or not parts[0].isdigit() or int(parts[0]) == me:
                continue
            if any(m in line for m in SELF_MARKERS):
                continue
            if any(b in line for b in BUSY):
                res.append(line.strip())
        return res

    def start_state(self):
        s = self.power_state()
        busy = self.busy_procs()
        return {"watts": s["watts"], "volts": s["volts"], "batt": s["batt"], "free_mem_mb": self.free_mem_mb(),
                "busy": busy, "orphans_clean": self.orphans_clean()}

    def proc_env(self, pid):
        return self.sh(["ps", "-o", "command=", "-E", "-p", str(pid)]).stdout

    # -- router
    def start_router(self):
        if self.listeners():
            raise ChainAbort(f"REFUSED: :8000 already bound by {self.listeners()}")
        busy = self.busy_procs()
        if busy:
            raise ChainAbort("REFUSED: busy processes present: " + "; ".join(busy)[:600])
        env = self.env_base()
        cmd = ["uv", "run", "--frozen", "--no-sync", "mlx-serve", "start"]
        self.log(f"RUN router: MLX_VLM_CACHE_SESSION_MAX=1 MLX_SERVE_CONFIG={self.overlay} {' '.join(cmd)} "
                 f"(cwd={self.repo})")
        (self.repo / "logs").mkdir(exist_ok=True)
        with open(self.repo / "logs/main_model.log", "a") as lf:
            self.popen(cmd, cwd=str(self.repo), env=env, stdout=lf, stderr=subprocess.STDOUT,
                       stdin=subprocess.DEVNULL, start_new_session=True)
        for _ in range(120):
            if self.listeners():
                break
            self.sleep(2)
        ls = self.listeners()
        if len(ls) != 1:
            raise ChainAbort(f"TRIPWIRE: expected one :8000 listener, found {ls}")
        pid = ls[0]
        e = self.proc_env(pid)
        probs = (["not mlx-serve"] if "mlx-serve" not in e else []) + env_tripwires(e, self.overlay)
        cwd = self.sh(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"]).stdout
        if str(self.repo) not in cwd:
            probs.append("cwd not the stack repo")
        self.log(f"router pid={pid} owns :8000; problems={probs or 'none'}")
        if probs:
            raise ChainAbort("TRIPWIRE: router ownership/environment: " + "; ".join(probs))
        return pid

    # -- worker
    def worker_cmdlines(self, model):
        out = self.sh(["ps", "-axo", "pid=,command="]).stdout
        return [ln.strip() for ln in out.splitlines()
                if "mlx_vlm.server" in ln and model in ln and "uv run" not in ln]

    def worker_ident(self, model):
        w = self.worker_cmdlines(model)
        if len(w) != 1:
            return None
        pid = int(w[0].split()[0])
        try:
            return {"pid": pid, "create_time": self.create_time(pid)}
        except Exception:  # noqa: BLE001
            return None

    def worker_env_check(self, pid):
        probs = env_tripwires(self.proc_env(pid), self.overlay)
        if probs:
            raise ChainAbort("TRIPWIRE: worker environment: " + "; ".join(probs))

    def load(self, model):
        self.log(f"RUN load {model}")
        self._http("/v1/models/load", {"model": model, "keep_alive": "240m"})
        w = []
        for _ in range(60):
            w = self.worker_cmdlines(model)
            if w:
                break
            self.sleep(5)
        if len(w) != 1:
            raise ChainAbort(f"TRIPWIRE: expected one worker for {model}, found {len(w)}")
        m = re.search(r"--draft-kind\s+(\S+)", w[0])
        if m and m.group(1) not in ("none", "off"):
            raise ChainAbort(f"TRIPWIRE: worker carries a predictor: {w[0][:300]}")
        pid = int(w[0].split()[0])
        self.worker_env_check(pid)
        ident = {"pid": pid, "create_time": self.create_time(pid), "cmdline": w[0][:400]}
        self.log(f"worker pid={pid} cmdline: {w[0][:400]}")
        self.loaded = model
        return ident

    def unload(self, model):
        try:
            self._http("/v1/models/unload", {"model": model}, timeout=120)
            self.log(f"unload {model} ok")
        except Exception as e:  # noqa: BLE001
            self.log(f"unload {model}: {e}")
        for _ in range(120):
            if not self.worker_cmdlines(model):
                self.loaded = None
                return True
            self.sleep(5)
        self.log("FATAL worker still alive after unload")
        return False

    def worker_metrics(self):
        """GET the worker /metrics; None when unreadable (never counted as idle)."""
        try:
            import yaml
            port = int(yaml.safe_load(Path(self.overlay).read_text())["mlx_port"])
            headers = {}
            key = self.env_base().get("MLX_VLM_SERVER_API_KEY")
            if key:
                headers["Authorization"] = "Bearer " + key
            req = urllib.request.Request(f"http://127.0.0.1:{port}/metrics", headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001
            return None

    # -- A4
    def a4_gate(self, model, tag):
        env = self.env_base()
        logf = self.wd / "c147" / f"a4_{tag}.log"
        logf.parent.mkdir(parents=True, exist_ok=True)
        cmd = [str(self.py), str(self.repo / "scripts/session_pinning_gate.py"), "--model", model, "--opencode",
               "v2", "--scaffold", SCAFFOLD, "--skip-owui", "--log", str(self.repo / "logs/mlx_vlm.log")]
        self.log(f"RUN A4 v2 gate ({model}) -> {logf.name}")
        t0 = time.time()
        try:
            r = self.sh(cmd, cwd=str(self.repo), env=env, timeout=1800)
        except subprocess.TimeoutExpired:
            raise ChainAbort("A4 gate timeout (chain abort, no restart)") from None
        logf.write_text((r.stdout or "") + (r.stderr or ""))
        try:
            rec = json.loads(self.receipt.read_text())
            fresh = self.receipt.stat().st_mtime >= t0 - 2
        except (OSError, ValueError):
            rec, fresh = {}, False
        self.log(f"A4 v2 rc={r.returncode} pass={rec.get('pass')} fresh={fresh} run_id={rec.get('run_id')}")
        if rec.get("pass") is not True or not fresh:
            raise ChainAbort(f"A4 v2 gate FAILED (rc={r.returncode}, pass={rec.get('pass')}, fresh={fresh})")
        return str(self.receipt)

    def stop_stack(self):
        rc = self.sh([str(self.repo / "scripts/stack_stop.sh")], timeout=300).returncode
        self.log(f"stack_stop rc={rc} listeners={self.listeners()}")
        return rc

    def rows(self, path):
        from bench import proc_guard as pg
        return pg.load_rows(path)

    def leftovers(self, roots, run_ids=()):
        """Same-uid processes with a root in their argv and `mlxbench-<run_id>-*` containers: LISTED, never killed."""
        found = []
        uid = os.getuid()
        out = self.sh(["ps", "-axo", "pid=,uid=,command="]).stdout
        for line in out.splitlines():
            parts = line.split(None, 2)
            if len(parts) == 3 and parts[1] == str(uid) and any(str(r) in parts[2] for r in roots if r):
                found.append(f"process {parts[0]}: {parts[2][:200]}")
        for rid in run_ids:
            c = self.sh(["docker", "ps", "-a", "--filter", f"name=mlxbench-{rid}-", "--format", "{{.Names}}"]).stdout
            found += [f"container {n}" for n in c.split()]
        return found


# --------------------------------------------------------------------------- arithmetic
def alarm_s(n_remaining, mean, max_item_wall):
    """expected = n_remaining x mean; alarm = 2 x expected + 3 x max_item_wall, floor 7,200 s."""
    return max(7200.0, 2 * n_remaining * mean + 3 * max_item_wall)


def t_coop(last_prompt_tokens, lang):
    """5 drain + 660 grade join + max(300, prompt/300) cancel bound + 120 export + grader timeout + 60 + 20."""
    return (5 + 660 + max(300, (last_prompt_tokens or 0) / 300) + 120 + GRADER_TIMEOUT_S.get(lang, 300)
            + 60 + 20)


def in_flight(metrics):
    try:
        v = metrics["summary"]["in_flight"]
    except (KeyError, TypeError):
        return None
    return v if type(v) is int and v >= 0 else None


class IdlePredicate:
    """Three consecutive samples >= `spacing_s` apart, each with heartbeat age > `hb_age_s`, metrics readable with
    in_flight == 0, and (against the previous sample) events bytes, rows signature and worker identity unchanged.
    Any change or unreadable metrics resets the count. `recheck` re-evaluates immediately before acting."""

    def __init__(self, spacing_s=60, hb_age_s=900, needed=3):
        self.spacing_s, self.hb_age_s, self.needed = spacing_s, hb_age_s, needed
        self.count, self.last_t, self.prev = 0, None, None

    def _idle(self, hb_age, events_bytes, rows_sig, metrics, ident):
        cur = (events_bytes, rows_sig, ident)
        unchanged = self.prev is None or cur == self.prev
        self.prev = cur
        fl = in_flight(metrics) if metrics is not None else None
        return (unchanged and hb_age is not None and hb_age > self.hb_age_s and fl == 0 and ident is not None)

    def sample(self, now, *, hb_age, events_bytes, rows_sig, metrics, ident):
        """Returns True when the predicate is satisfied. Samples closer than `spacing_s` are ignored."""
        if self.last_t is not None and now - self.last_t < self.spacing_s:
            return self.count >= self.needed
        self.last_t = now
        self.count = self.count + 1 if self._idle(hb_age, events_bytes, rows_sig, metrics, ident) else 0
        return self.count >= self.needed

    def recheck(self, *, hb_age, events_bytes, rows_sig, metrics, ident):
        if self.count < self.needed:
            return False
        if self._idle(hb_age, events_bytes, rows_sig, metrics, ident):
            return True
        self.count = 0
        return False


# --------------------------------------------------------------------------- completion = validation
RUNTIME_PINNED = ("scaffold_policy_sha256", "probe_code_sha256", "opencode_version", "opencode_exe_sha256",
                  "opencode_bench_config_sha256", "carrier_source_sha256", "agent_system_sha256", "polyglot_sha",
                  "universe_sha256")


def seed_overlay_sha(model, seed):
    overlay = {"providers": {"mlx-local": {"models": {model: {"body": {"seed": int(seed)}}}}}}
    return hashlib.sha256(json.dumps(overlay, sort_keys=True).encode()).hexdigest()


def resolve_portable(path, workdir):
    s = str(path)
    if s.startswith("$STACK_WORKDIR"):
        return Path(str(workdir) + s[len("$STACK_WORKDIR"):])
    return Path(s)


def typed_worker(w):
    return (isinstance(w, dict) and type(w.get("pid")) is int and w["pid"] > 0
            and isinstance(w.get("create_time"), (int, float)) and not isinstance(w["create_time"], bool)
            and isinstance(w.get("model_path"), str) and bool(w["model_path"])
            and isinstance(w.get("registry_sha256"), str) and bool(HEX64.match(w["registry_sha256"])))


def validate_leg(leg, pinned, workdir=None):
    """Completion = validation (spec 3). Returns a list of `code: detail` failure reasons; [] means complete.

    leg: {session, model, lang, seed_base, expected_ids, out, rc}. pinned: runtime field -> value (None = not yet
    pinned, skipped) plus `serving_path`, `registry_sha256`; scaffold policy hash and probe-code are mandatory."""
    from bench import rowschema
    from bench import proc_guard as pg
    why = []
    wd = workdir or os.environ.get("STACK_WORKDIR") or ""
    out = Path(leg["out"])
    if leg.get("rc") != 0:
        why.append(f"rc_nonzero: probe rc {leg.get('rc')}")
    try:
        rows = pg.load_rows(out)
    except Exception as e:  # noqa: BLE001
        return why + [f"rows_torn: {e}"]
    ids = [r.get("id") for r in rows]
    if sorted(ids) != sorted(leg["expected_ids"]) or len(set(ids)) != len(ids):
        why.append(f"ids_mismatch: got {sorted(ids)} expected {sorted(leg['expected_ids'])}")
    mp = out.with_suffix(".manifest.json")
    try:
        man = json.loads(mp.read_text())
    except (OSError, ValueError):
        return why + ["manifest_missing: no intact manifest"]
    rt = man.get("runtime") or {}
    if man.get("transport_abort"):
        why.append(f"manifest_abort: {man['transport_abort']}")
    if man.get("served_config_drift"):
        why.append("served_config_drift: manifest records drift")
    if man.get("model") != leg["model"]:
        why.append(f"manifest_model: {man.get('model')} != {leg['model']}")
    if rt.get("seed_base") != leg["seed_base"]:
        why.append(f"runtime_seed_base: {rt.get('seed_base')} != {leg['seed_base']}")
    if rt.get("lang") != leg["lang"]:
        why.append(f"runtime_lang: {rt.get('lang')} != {leg['lang']}")
    if rt.get("scaffold") != SCAFFOLD:
        why.append(f"runtime_scaffold: {rt.get('scaffold')}")
    if rt.get("scaffold_policy_sha256") != CAMPAIGN_POLICY_SHA:
        why.append(f"runtime_scaffold_policy_sha256: {rt.get('scaffold_policy_sha256')}")
    if rt.get("draft_kind") != "off":
        why.append(f"runtime_draft_kind: {rt.get('draft_kind')}")
    if rt.get("sampling_profile", man.get("sampling_profile")) != "deployed":
        why.append("runtime_sampling_profile: not deployed")
    if pinned.get("probe_code_sha256") is None:
        why.append("pinned_incomplete: probe_code_sha256 not pinned")
    for k in RUNTIME_PINNED:
        if pinned.get(k) is not None and rt.get(k) != pinned[k]:
            why.append(f"runtime_{k}: {rt.get(k)} != pinned {pinned[k]}")
    if not rt.get("opencode_version"):
        why.append("runtime_opencode_version: empty")
    sp = (man.get("git") or {}).get("serving_path")
    if pinned.get("serving_path") is not None and sp != pinned["serving_path"]:
        why.append(f"serving_path: {sp} != pinned {pinned['serving_path']}")
    if pinned.get("registry_sha256") is not None and (man.get("registry") or {}).get("sha256") != pinned["registry_sha256"]:
        why.append("registry_sha256: differs from the overlay the router was started with")
    mw = man.get("worker")
    if not typed_worker(mw):
        why.append(f"worker_untyped: manifest worker {mw}")
    for r in rows:
        rid = r.get("id")
        if r.get("sample") != 0:
            why.append(f"row_sample: {rid} sample {r.get('sample')}")
        exp = rowschema.sample_seed(rid, 0, leg["seed_base"])
        if r.get("sample_seed") != exp:
            why.append(f"row_sample_seed: {rid} {r.get('sample_seed')} != {exp}")
        want = seed_overlay_sha(leg["model"], exp)
        for key in ("seed_overlay_sha256", "overlay_sha256"):
            if key in r and r[key] != want:
                why.append(f"row_overlay_sha: {rid} {key}")
        for key in ("worker_before", "worker_after"):
            if not typed_worker(r.get(key)):
                why.append(f"worker_untyped: {rid} {key}")
            elif typed_worker(mw) and r[key] != mw:
                why.append(f"worker_mismatch: {rid} {key} != manifest worker")
        ev = r.get("evidence_sha256") or {}
        for name, pkey in (("events", "events_path"), ("stderr", "stderr_path"), ("export", "transcript_path")):
            sha = ev.get(name)
            if not isinstance(sha, str) or not HEX64.match(sha):
                why.append(f"evidence_sha_missing: {rid} {name}")
                continue
            if not r.get(pkey) or file_sha(resolve_portable(r[pkey], wd)) != sha:
                why.append(f"evidence_sha_mismatch: {rid} {name}")
        reports = r.get("grade_reports")
        if not isinstance(reports, list) or not reports or not any(g.get("final") for g in reports):
            why.append(f"grade_reports_missing: {rid}")
            continue
        for g in reports:
            for aname, art in (g.get("artifacts") or {}).items():
                sha = (art or {}).get("sha256")
                if not isinstance(sha, str) or not HEX64.match(sha):
                    why.append(f"report_sha_missing: {rid} {aname}")
                elif file_sha(resolve_portable(art.get("path", ""), wd)) != sha:
                    why.append(f"report_sha_mismatch: {rid} {aname}")
    return why


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2, default=str)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
