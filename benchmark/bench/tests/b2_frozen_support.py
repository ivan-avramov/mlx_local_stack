"""P426 B2 frozen tests (spec docs/specs/p426-b2-tg1-wave2.md v3.1, C235, C236): shared fixtures. TESTS ONLY.

Every fixture is built in the format the baseline code or the fork actually emits (the source is cited on each builder) and is
exercised against the BASELINE by `test_b2_frozen_s0_support.py`. Nothing here starts a router, worker, model, docker or a
real opencode; the chain runs use the existing fakes of `test_c147_chain_runner` (FakeOps + `chains/c147/fake_probe.py`)."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BENCH = REPO / "benchmark"
C147 = BENCH / "chains/c147"

# full registry names (AGENTS.md); the P426 entry and the two other tg1-relevant entries of the committed registry
MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
MODEL2 = "Qwen3.8-27B-mlx-uniform-4bit"
MODEL3 = "Ornith-1.0-35B-mlx-uniform-4bit"
HF = "caslca/" + MODEL
DRAFTER = HF + "-mtp-drafter"
EPOCH_DATE = "Mon Jan 05 2026"
HEX9 = "9" * 64

# ------------------------------------------------------------------------------------------------ legacy goldens (§2)
# Recorded from the B2 base commit 50ec18d1 (`schedules.tg1(...)` on the committed universe `benchmark/m62/universe.json`):
# schedule_sha256 and the sha256 of the json list of [session, model, lang, phase, names] per invocation, in launch order.
GOLDEN_P223_SCHEDULE_SHA = "e8c981f37b04ee90e79f1f2b004da4c828031df7785324e7b2bb0601e754b1d7"    # chain s1 s2 reload, off
GOLDEN_M63_SCHEDULE_SHA = "3ed3936d8765d420808056735e4ccd487aa3891355b28f96648741d8749fe70f"     # chain s1 s2 reload, mtp
GOLDEN_CHAIN_ORDER_SHA = "d49e559639052cf74e98360b0d96b6982bcfebe4d8637de1faf5d40eedb3334e"      # both predictors, 13 invocations
GOLDEN_PILOT_ORDER = [["pilot", MODEL, "python", "pilot", ["beer-song", "book-store", "dominoes", "grep", "pig-latin"]]]
# the serialized legacy `tg1` ChainConfig (`run_tg1_chain.tg1_config(parse_args(["chain","s1","--probe-code-sha",9*64]))`)
GOLDEN_TG1_CONFIG_STATIC = {
    "config_id": "tg1", "out_root_family": "c147", "predictor": "off", "arm_switch_ops": [], "transport_policy": "abort_restart",
    "resume_policy": "restart_load", "snapshot_complete_required": False, "contract_artifacts": [],
    "arms": [{"arm": "oc", "arm_spec": "oc", "label": "opencode-v2-web-tg1", "probe": "benchmark/run_tg1_probe.py",
              "probe_data": ["benchmark/opencode_plugins/toolbounds.js", "benchmark/opencode_plugins/noretry.js",
                             "benchmark/opencode_plugins/datefreeze.js", "benchmark/opencode_bench_v2_web_tg1.json"]}]}
# §14.5: the frozen runners and the serving pins at the base commit (sha256 of the file bytes; the index gitlinks)
FROZEN_RUNNERS = {
    "benchmark/chains/m59/run_m59.py": "5e50efa00202b87d9a8e971d6124b65858c07315468180c3a90c5ab047a75fef",
    "benchmark/chains/m61/run_m61.py": "4a432d0bee7d15fe3b589c70fb2d83c806879ce5877269ad8ea8f362e1fbd4bb",
    "benchmark/chains/m61/run_m61_rr.py": "fc5efff58d954060acb3c8e89c03e23da58d71f89b77728b645854b473fbfc5c",
    "benchmark/chains/m62/run_m62_live.py": "6af02c0529b69594f4cc263f8b38713672d11aa4063ee47b2a8ceb23bd2afecd",
    "benchmark/chains/m64/run_m64_chain.py": "d1b39a425c0a28ed39ff5a1bf426a9cedce35525bb55688e244266390d213c88",
    "benchmark/chains/c147/run_inject.py": "6e13965026241e0516537c418ef068dfbdf39b8e5360eb3ac619918b7200f90d",
}
# rebase-amendment P520 (S′): the base is stack main 61d31bcd (T3 merged); before: src/mlx-vlm c9543fc4bcd3111b738ba7a29ca772c2c6366817,
# src/mlx-serve 86921f029d7e55b4d8b5882f2c05ed5e2ce31ef0 (S)
BASE_GITLINKS = {"src/mlx-vlm": "1c7c8fa166582ac1a1c23ae9063527b2b5215b11",
                 "src/mlx-serve": "1ddf6f842f159a62d240f3ac6965fc33cbdb0b0d"}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def invocation_order(invocations):
    """[[session, model, lang, phase, names]] of a fake-probe run (argv recorded by `fake_probe.py` in invocations.jsonl;
    the rows file name `<model>.<session>.opencode_<lang>.L<k>.<phase>.a<n>.jsonl` is `chain_rows.rows_name`)."""
    out = []
    for inv in invocations:
        argv = inv["argv"]
        rows = Path(argv[argv.index("--out") + 1]).name
        stem, rest = rows.split(".opencode_", 1)
        lang, _leg, phase = rest.split(".")[:3]
        model, session = stem.rsplit(".", 1)
        out.append([session, model, lang, phase, argv[argv.index("--items") + 1].split(",")])
    return out


def order_sha(order):
    return hashlib.sha256(json.dumps(order).encode()).hexdigest()


def p426_order(pool, seed):
    """§7: `random.Random(seed).sample(sorted(pool), len(pool))`, no later sort."""
    import random
    return random.Random(seed).sample(sorted(pool), len(pool))


# ------------------------------------------------------------------------------------------------ worker log lines (§4.1)
# Format: the fork's `ServerMetricsStore` (src/mlx-vlm/mlx_vlm/server/generation.py): `begin_request` line 620-626,
# `record_success` line 654-674 (sdpa at 646-649, `_format_verify_counters` 766-775 appends every `verify_*` / `draft_*` key
# sorted), `record_failure` line 689-695 (error `stream_closed_before_completion`: server/openai.py:2094). The logger prefix
# `YYYY-mm-dd HH:MM:SS,mmm - mlx_vlm.server - LEVEL - ` is the one in the committed slices
# (benchmark/results/p426/wave1/math500-p426-on-b1/server_log_slice.log).
def ts(i=0):
    s = 10 + i
    return f"2026-10-22 17:{(s // 60) % 60:02d}:{s % 60:02d},{(7 * i) % 1000:03d}"


def _prefix(at, level="INFO"):
    return f"{at} - mlx_vlm.server - {level} - "


def started_line(*, at=None, model=HF, stream=True, in_flight=1, endpoint="/chat/completions"):
    return _prefix(at or ts()) + f"Request started: endpoint={endpoint} model={model} stream={stream} in_flight={in_flight}"


def draft_counters(rounds, n, accepted, kind="mtp"):
    """The per-request drafter counters (`_DRAFT_KEYS`, generation.py:883-897)."""
    return {"draft_kind": kind, "draft_rounds": rounds, "draft_n": n, "draft_n_accepted": accepted}


def completed_line(*, session, prompt_tokens, generated_tokens, at=None, model=HF, stream=True, backend="cached_session",
                   cached_tokens=0, elapsed=10.0, prefill=200.0, decode=50.0, finish_reason="stop", in_flight=0,
                   sdpa=(16, 48), draft=None, verify=None, endpoint="/chat/completions"):
    line = (_prefix(at or ts()) + f"Request completed: endpoint={endpoint} model={model} stream={stream} backend={backend} "
            f"session={session} cached_tokens={cached_tokens} prompt_tokens={prompt_tokens} "
            f"generated_tokens={generated_tokens} elapsed={elapsed:.3f}s prefill={prefill:.1f} tok/s "
            f"decode={decode:.1f} tok/s finish_reason={finish_reason} in_flight={in_flight}")
    if sdpa is not None:
        line += f" sdpa_forced={sdpa[0]} sdpa_auto={sdpa[1]}"
    payload = dict(draft or {}, **(verify or {}))
    parts = []
    for key in sorted(k for k in payload if k.startswith(("verify_", "draft_"))):
        value = payload[key]
        if isinstance(value, dict):
            value = json.dumps(value, sort_keys=True, separators=(",", ":"))
        parts.append(f"{key}={value}")
    if parts:
        line += " " + " ".join(parts)
    return line


def failed_line(*, at=None, model=HF, stream=True, error="stream_closed_before_completion", in_flight=0,
                endpoint="/chat/completions"):
    return _prefix(at or ts(), "WARNING") + (f"Request failed: endpoint={endpoint} model={model} stream={stream} "
                                             f"error={error} in_flight={in_flight}")


VERIFY_ON = {"verify_blocks_joint_v1": 8192, "verify_blocks_len1": 16, "verify_blocks_per_query": 0,
             "verify_blocks_straddle": 16, "verify_blocks_straddle_len2": 0, "verify_fallback_reasons": {}}


# ------------------------------------------------------------------------------------------------ worker /metrics (§4.1)
def metrics_doc(*, started=0, completed=0, failed=0, in_flight=0, prompt_total=0, generated_total=0, decode_s=0.0,
                streaming=None):
    """`GET /metrics` of the worker: `ServerMetricsStore.snapshot()` (generation.py:698-741). `avg_decode_tok_s` =
    generated_tokens_total / Σ decode_elapsed_s (0 when no decode time)."""
    return {"latest": None, "recent": [], "summary": {
        "uptime_s": 100.0, "requests_started": started, "requests_completed": completed, "requests_failed": failed,
        "streaming_requests": started if streaming is None else streaming, "in_flight": in_flight,
        "prompt_tokens_total": prompt_total, "completion_tokens_total": generated_total,
        "generated_tokens_total": generated_total, "avg_request_time_s": 0.0, "avg_request_tok_s": 0.0,
        "avg_decode_tok_s": (generated_total / decode_s) if decode_s > 0 else 0.0, "last_request_at": None,
        "last_error": None}}


# ------------------------------------------------------------------------------------------------ rows (§4.1)
REAL_ROW = BENCH / "bench/tests/fixtures/c147_real_tg1_pilot_row.json"     # a real tg1 probe row (run_tg1_probe, 2026-10-11)


def real_row():
    return json.loads(REAL_ROW.read_text())


def item_window(session, usage, *, draft=None, start=0):
    """The server-log window of one normally completed item whose client `request_usage` is `usage`
    ([[message_id, output_tokens, prompt_tokens, budget], ...], `token_turn_gate`): one started + one completed line per
    request, serial. Pairing (C225, the P456 rehearsal): client output_tokens == server generated_tokens, client
    prompt_tokens == server prompt_tokens. `draft(i, generated)` -> the request's draft counters or None."""
    lines = []
    for i, (_mid, out_tok, prompt_tok, _budget) in enumerate(usage):
        lines.append(started_line(at=ts(start + 2 * i)))
        lines.append(completed_line(at=ts(start + 2 * i + 1), session=session, prompt_tokens=prompt_tok,
                                    generated_tokens=out_tok, draft=draft(i, out_tok) if draft else None,
                                    verify=VERIFY_ON if draft else None))
    return lines


# ------------------------------------------------------------------------------------------------ registry (§6.2)
# The committed registry's shape (main_models.yaml: `models:` entries with `name`, `hf_path`; the three C177 keys of an MTP
# entry are `draft_kind` / `draft_model` / `mtp_verify_scan` — `bench.p426_leg.MTP_KEYS`).
C177_KEYS = ("draft_kind", "draft_model", "mtp_verify_scan")


def registry_text(models=(MODEL, MODEL2), *, on=(), partial=()):
    out = ["mlx_port: 8091", "models:"]
    for name in models:
        out += [f"  - name: {name}", "    type: vision", f"    hf_path: caslca/{name}", "    max_kv_cache_size: 262144"]
        if name in on:
            out += ["    draft_kind: mtp", f"    draft_model: caslca/{name}-mtp-drafter", "    mtp_verify_scan: joint_v1"]
        elif name in partial:
            out += ["    draft_kind: mtp"]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------------ the chain harness
def _t1c():
    from bench.tests import test_c147_chain_runner as t1c
    return t1c


def make_ops(wd, registry=None):
    """The existing `FakeOps` of test_c147_chain_runner plus the served registry as `ChainOps.overlay` (§3: in P426 / C221
    mode the overlay IS `<WT>/main_models.yaml`) and `overlay_sha()` = its sha256."""
    t1c = _t1c()
    ops = t1c.FakeOps(wd)
    reg = Path(wd) / "WT" / "main_models.yaml"
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(registry if registry is not None else registry_text())
    ops.overlay = str(reg)
    ops.overlay_sha = lambda: sha256_file(reg)
    original = ops.load

    def load(model):                       # the worker (and the probe's manifest) report the served registry's sha
        ident = original(model)
        w = ops.state / "worker.json"
        w.write_text(json.dumps(dict(json.loads(w.read_text()), registry_sha256=sha256_file(reg))))
        ops.extra_env["FAKE_REGISTRY_SHA"] = sha256_file(reg)
        return ident
    ops.load = load
    # §16.2 ChainOps seams on the fake: the served worktree's server log
    log = reg.parent / "logs" / "mlx_vlm.log"
    log.parent.mkdir(exist_ok=True)
    log.touch()
    (reg.parent / "logs" / "main_model.log").touch()
    ops.repo = reg.parent
    ops.server_log_path = lambda: log

    def read_log(path, start, end=None):
        data = Path(path).read_bytes()
        return data[start:end]
    ops.read_log = read_log
    return ops


def chain_env(tmp_path, monkeypatch, *, registry=None, universe=None, out="c147"):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    ops = make_ops(tmp_path, registry)
    uni = tmp_path / "universe.json"
    uni.write_text(json.dumps({"items": universe if universe is not None else {
        **{f"python/p{i}": {} for i in range(1, 7)}, **{f"go/g{i}": {} for i in range(1, 7)}}}))
    return dict(wd=tmp_path, ops=ops, uni=uni, lines=[], out=tmp_path / out)


def run_chain(env, argv, **kw):
    """`run_tg1_chain.main(argv, ops=…, timers=…, log_out=…)` in a thread (test_c147_chain_runner.run)."""
    return _t1c().run(env, argv, **kw)


def invocations(env):
    return _t1c().invocations(env)


def chain_json(env):
    return json.loads((Path(env["out"]) / "chain.json").read_text())


def runner_module():
    return _t1c().R


def main_refusal(argv, ops, *, campaign=None):
    """(rc, text) of `run_tg1_chain.main(argv, ops=<fake>)` when it refuses before running: argparse errors (SystemExit 2),
    `Refused` (SystemExit 2, its message), or a returned nonzero rc; `text` = the log lines + stderr + stdout + the exit
    message. The ops are always the fakes, so a refusal that does not fire can never reach a real router. `campaign` (1h):
    the fake campaign helper for a `--campaign-core` tag (`fake_campaign`), so a P426 argv's tag resolves."""
    kw = {} if campaign is None else {"campaign": campaign}
    import io
    from contextlib import redirect_stderr, redirect_stdout
    R = runner_module()
    lines = []
    err, out = io.StringIO(), io.StringIO()
    with redirect_stderr(err), redirect_stdout(out):
        try:
            rc = R.main(list(argv), ops=ops, timers=R.Timers(**_t1c().TIMERS), log_out=lines.append, **kw)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 2
            if not isinstance(e.code, int) and e.code is not None:
                lines.append(str(e.code))
            elif e.args and isinstance(e.args[0], str):
                lines.append(e.args[0])
    return rc, "\n".join(lines) + err.getvalue() + out.getvalue()


# ------------------------------------------------------------------------------------------------ locks (§9)
@contextlib.contextmanager
def held_flock(path):
    """Hold `flock(LOCK_EX | LOCK_NB)` on `path` (created) for the block, from THIS process's own open file description."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield fd
    finally:
        os.close(fd)


def is_flocked(path):
    """True when another open file description holds an exclusive flock on `path` (BSD flock: a second open() conflicts
    even inside one process)."""
    path = Path(path)
    if not path.exists():
        return False
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


class GateReached(Exception):
    """Raised by the fake clone: `local_gate run` got past every refusal to its first work step."""


def gate_harness(monkeypatch, wd):
    """`bench.local_gate.main(["run", "--repo", "stack"])` with git, the busy census and the clone faked: the fake clone
    records the state of `gate/RUNNING` and raises `GateReached` (nothing is cloned or run). Returns the record dict."""
    from bench import local_gate as lg
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    seen = dict(reached=False, running_locked=None)

    def git(cwd, *a, check=True):
        if a[:3] == ("remote", "get-url", "origin"):
            return "https://github.com/" + lg.CANONICAL["stack"] + ".git"
        if a and a[0] == "rev-parse":
            return "a" * 40
        return ""

    def clone(live, sha, dest):
        seen["reached"] = True
        seen["running_locked"] = is_flocked(Path(wd) / "gate" / "RUNNING")
        raise GateReached()
    monkeypatch.setattr(lg, "_git", git)
    monkeypatch.setattr(lg, "clone_scratch", clone)
    monkeypatch.setitem(lg.run.__kwdefaults__, "busy", lambda: [])
    return seen


def gate_main():
    """(rc or the exception) of the faked `local_gate run`."""
    from bench import local_gate as lg
    try:
        return lg.main(["run", "--repo", "stack"])
    except GateReached as e:
        return e


# ------------------------------------------------------------------------------------------------ harvest (§11)
def harvest_repo(tmp_path):
    """A scratch copy of the stack's `benchmark/bench` package (no tests) so that `python -m bench.p426_harvest wave2 …`
    writes its `main` destinations (`benchmark/results/p426/wave2/<leg>/`) into the scratch tree, never the real checkout."""
    root = tmp_path / "repo"
    dst = root / "benchmark" / "bench"
    shutil.copytree(BENCH / "bench", dst, ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"), symlinks=True)
    for p in dst.rglob("*"):
        if p.is_symlink():
            raise AssertionError(f"the bench package carries a symlink {p}")
    return root


FAKE_HF_TOKEN_FILE = "hf_" + "Q" * 34                       # format `hf_…` (§11.3), fake
FAKE_SECRET_40 = "Zk3" + "x7Pq" * 9 + "W"                   # a 40-char opaque credential value, no known format (fake)


def harvest_env(tmp_path, *, home=None, env_extra=None):
    """A hermetic environment for the harvest subprocess: HOME / XDG_CONFIG_HOME / STACK_WORKDIR under tmp_path (never the
    operator's real credential files)."""
    home = Path(home or tmp_path / "home")
    home.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "TMPDIR", "PYTHONHASHSEED")}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"), STACK_WORKDIR=str(tmp_path / "wd"),
               PYTHONDONTWRITEBYTECODE="1")
    env.update(env_extra or {})
    return env


def run_harvest(repo_root, leg_root, env, *, main_root, stage, timeout=120):
    """§16.2: `python -m bench.p426_harvest wave2 --leg-root <dir> --main-root <checkout> --evidence-stage <dir>`, run from
    the scratch copy of the package (nothing can land in the real checkout even if `--main-root` were ignored)."""
    import subprocess
    return subprocess.run([sys.executable, "-m", "bench.p426_harvest", "wave2", "--leg-root", str(leg_root), "--main-root",
                           str(main_root), "--evidence-stage", str(stage)], cwd=str(repo_root / "benchmark"), env=env,
                          capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)


def all_output_text(tmp_path, exclude=()):
    """Every byte the test tree holds outside `exclude` (decoded loosely), for `never printed / written` checks."""
    ex = [Path(e).resolve() for e in exclude]
    chunks = []
    for p in Path(tmp_path).rglob("*"):
        if p.is_symlink() or not p.is_file():
            continue
        rp = p.resolve()
        if any(rp == e or e in rp.parents for e in ex):
            continue
        try:
            chunks.append(p.read_bytes().decode("utf-8", "replace"))
        except OSError:
            pass
    return "\n".join(chunks)


# ------------------------------------------------------------------------------------------------ the item-barrier fake probe
PROBE = Path(__file__).resolve()                     # this file is also the fake probe (`--probe`), see `probe_main`
CLEANUP_EXACT = {"survivors": [], "containers_remaining": [], "uncertain": False, "orphans_unattributed": [], "unknown": [],
                 "completed": True}                  # chain_incident.CLEANUP_KEYS, certain / completed / empty


def evidence_policy(item_barrier):
    """`runtime.evidence_policy` as the real probe writes it (`arm_runner._main`: `evidence.as_dict()`) for the tg1
    `EvidencePolicy` (tg1_runner.TG1_EVIDENCE) with the given item barrier."""
    return {"namespace": "opencode_transcripts", "web_evidence": True, "final_tree": True, "worker_receipts": "absent",
            "item_barrier": item_barrier}


def barrier_env(state, *, item_barrier="on", log=None, metrics=None, requests=2, draft=None):
    """The fake probe's knobs. 2d: no arm-specific key by default — whether the server drafts follows the served registry's
    entry (`fake_probe.served_draft_kind`), as on a real worker; `draft=True/False` forces it (`B2_DRAFT`) for a test that
    injects a server fault on one leg."""
    env = dict(B2_ITEM_BARRIER=item_barrier, B2_PROBE_LOG=str(log or ""), B2_PROBE_METRICS=str(metrics or ""),
               B2_REQUESTS=str(requests), FAKE_PROBE_STATE=str(state))
    if draft is not None:
        env["B2_DRAFT"] = "1" if draft else "0"
    return env


def _fp():
    import importlib.util
    spec = importlib.util.spec_from_file_location("b2_fake_probe_c147", C147 / "fake_probe.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _wait_any(paths, cancel, timeout=120.0, tick=0.01):
    import time
    end = time.time() + timeout
    while time.time() < end:
        for p in paths:
            if p.exists():
                return p
        if cancel.exists():
            return cancel
        time.sleep(tick)
    return None


def fake_identity():
    """The fake probe's `--print-identity` document, shaped as the real probe's (`arm_runner.print_identity`, lines 926-956:
    arm, config_id, scaffold, scaffold_policy_sha256, probe_code_sha256, polyglot_sha, snapshot_*, generation_identity_sha256);
    the composite is the one the fake's manifests carry (`chain_ops.composite_sha` of the manifest runtime, frozen date
    `EPOCH_DATE`)."""
    FP = _fp()
    worker = {"pid": 1, "create_time": 1.0, "model_path": HF, "registry_sha256": "a" * 64}
    man = FP.build_manifest(MODEL, "python", 1001, worker, "identity", {}, frozen=EPOCH_DATE)
    snap = FP.snapshot()
    return {"arm": "oc", "config_id": "tg1", "scaffold": FP.SCAFFOLD,
            "scaffold_policy_sha256": os.environ.get("FAKE_PRINT_POLICY_SHA", FP.CAMPAIGN),
            "probe_code_sha256": os.environ.get("FAKE_PROBE_CODE_SHA", HEX9), "polyglot_sha": "1" * 40,
            "generation_identity_sha256": man["runtime"]["generation_identity_sha256"], "snapshot_tool": snap["tool"],
            "snapshot_sha256": snap["sha256"], "snapshot_complete": snap["complete"], "snapshot_fields": snap["fields"]}


def probe_main(argv):
    """The c147 fake-probe contract (`chains/c147/fake_probe.py`: manifest before item one, ack, rows, cleanup receipt) plus
    the real probe's item barrier (`bench.item_barrier` + `arm_runner._main`): `<base>.item<k>.ready` before item k, wait for
    `.go` / `.stop`; the row, then `<base>.item<k>.done` (the `_done_record` shape), wait for `.continue` / `.stop`; a stop
    is a clean `hook_stop` exit. Each item's requests are appended to $B2_PROBE_LOG in the fork's log format and counted
    in $B2_PROBE_METRICS (`metrics_doc`); rows carry `request_usage` + `session_id` as the real row does."""
    import argparse
    import time
    import uuid
    FP = _fp()
    raw = list(argv)
    if "--print-identity" in raw:
        if os.environ.get("FAKE_PROBE_STATE"):
            st = Path(os.environ["FAKE_PROBE_STATE"])
            st.mkdir(parents=True, exist_ok=True)
            with (st / "identity_calls.jsonl").open("a") as f:
                f.write(json.dumps({"argv": raw}) + "\n")
        print(json.dumps(fake_identity(), sort_keys=True), flush=True)
        return 0
    ap = argparse.ArgumentParser()
    for f in ("--model", "--items", "--lang", "--out", "--scaffold", "--expect-items", "--a4-v2-receipt",
              "--sampling-profile", "--cancel-file", "--manifest-ack", "--universe", "--frozen-prompt-date",
              "--invocation-nonce", "--evidence"):
        ap.add_argument(f)
    ap.add_argument("--seed-base", type=int)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--attempt-rerun-index", type=int, default=0)
    ap.add_argument("--inject-stall-item", default=None)          # post-reveal 3d (§16.8): R3's stall injection
    ap.add_argument("--inject-stall-s", type=float, default=None)
    a, _unknown = ap.parse_known_args(raw)          # tolerant: the chain may pass flags the fake does not use
    env = os.environ
    state = Path(env["FAKE_PROBE_STATE"])
    with (state / "invocations.jsonl").open("a") as f:
        f.write(json.dumps({"argv": raw, "pid": os.getpid()}) + "\n")
    lock_probe = env.get("B2_LOCK_PROBE")
    if lock_probe:                                        # §9: does this child hold an fd on the chain's lock file?
        held = []
        try:
            target = os.stat(lock_probe)
            for fd in range(3, 1024):
                try:
                    st = os.fstat(fd)
                except OSError:
                    continue
                if (st.st_dev, st.st_ino) == (target.st_dev, target.st_ino):
                    held.append(fd)
        except OSError:
            held = None
        (state / "lockcheck.json").write_text(json.dumps({"inherited_fds": held}))

    cancel, ack, out = Path(a.cancel_file), Path(a.manifest_ack), Path(a.out)
    if cancel.exists() or ack.exists() or out.exists():
        print("REFUSED: cancel / ack / rows file already exists", flush=True)
        return 2
    worker = json.loads((state / "worker.json").read_text())
    served_reg = env.get("FAKE_SERVED_REGISTRY")
    if served_reg and not env.get("FAKE_REGISTRY_SHA"):   # 2d: the probe hashes the served registry itself (no arm key in env)
        os.environ["FAKE_REGISTRY_SHA"] = hashlib.sha256(Path(served_reg).read_bytes()).hexdigest()
    drafting = (env["B2_DRAFT"] == "1") if "B2_DRAFT" in env else FP.served_draft_kind(a.model) == "mtp"
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    man = FP.build_manifest(a.model, a.lang, a.seed_base, worker, run_id, {}, frozen=a.frozen_prompt_date)
    man["runtime"]["evidence_policy"] = evidence_policy(env.get("B2_ITEM_BARRIER", "on"))
    if a.invocation_nonce:
        man["runtime"]["invocation_nonce"] = a.invocation_nonce
    mp = out.with_suffix(".manifest.json")

    def save():
        FP._atomic(mp, json.dumps(man, indent=2).encode())
    save()
    if _wait_any([ack], cancel) != ack:
        man["transport_abort"] = {"error": "manifest not acknowledged", "cleanup_status": dict(CLEANUP_EXACT)}
        man["cleanup_status"] = dict(CLEANUP_EXACT)
        save()
        return 1
    barrier = env.get("B2_ITEM_BARRIER", "on") == "on"
    base = str(out.with_suffix(""))
    names = [x for x in a.items.split(",") if x][: a.limit or None]
    rows, n_req = [], int(env.get("B2_REQUESTS", "2"))
    log, mfile = env.get("B2_PROBE_LOG"), env.get("B2_PROBE_METRICS")

    def signal(k, kind):
        p = Path(f"{base}.item{k}.{kind}")
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        return fd, p

    def wait(k, ok):
        got = _wait_any([Path(f"{base}.item{k}.stop"), Path(f"{base}.item{k}.{ok}")], cancel)
        return "stop" if got is None or got.name.endswith(".stop") or got == cancel else ok

    def account(served, *, failed=0):
        """The worker's counters for what the server saw (`ServerMetricsStore.begin_request` / `record_*`)."""
        if not mfile:
            return
        m = json.loads(Path(mfile).read_text()) if Path(mfile).exists() else metrics_doc()
        s = m["summary"]
        prev_d = s["generated_tokens_total"] / s["avg_decode_tok_s"] if s["avg_decode_tok_s"] else 0.0
        doc = metrics_doc(started=s["requests_started"] + len(served) + failed,
                          completed=s["requests_completed"] + len(served), failed=s["requests_failed"] + failed,
                          prompt_total=s["prompt_tokens_total"] + sum(u[2] for u in served),
                          generated_total=s["generated_tokens_total"] + sum(u[1] for u in served),
                          decode_s=prev_d + sum(u[1] for u in served) / 50.0)
        FP._atomic(Path(mfile), json.dumps(doc).encode())

    def session_of(item):
        return "ses_" + hashlib.sha256(f"{run_id}|{item}".encode()).hexdigest()[:26]

    def usage_of(k):
        return [[f"msg_{k:03d}{i:03d}", 40 + 10 * i + k, 3000 + 500 * i + k, 81920] for i in range(n_req)]

    def requests(item, k, name):
        session, usage = session_of(item), usage_of(k)
        draft = (lambda i, g: draft_counters(max(1, g // 2), g, g // 2)) if drafting else None
        served = [list(u) for u in usage]
        if name in skew:                                  # the server logged one more generated token than the client saw
            served[-1][1] += 1
        if log:
            with open(log, "a") as f:
                f.write("".join(ln + "\n" for ln in item_window(session, served, draft=draft, start=10 * k)))
        account(served)
        return session, usage

    def dnf(item, k, mode):
        """A transport abort of item k after its `.go` (§16.1 abort manifest = `arm_runner._main`'s stamp + the P426 keys):
        `boundary` (every started request completed), `inflight_failed` (one more started, the server failed it) or
        `inflight_completed` (one more started, the server completed it after the client lost it)."""
        session, usage = session_of(item), usage_of(k)
        lines = item_window(session, usage, start=10 * k)
        extra = [f"msg_{k:03d}999", 7, 9000 + k, 81920]
        if mode == "inflight_failed":
            lines += [started_line(at=ts(10 * k + 8)), failed_line(at=ts(10 * k + 9))]
            account(usage, failed=1)
        elif mode == "inflight_completed":
            lines += item_window(session, [extra], start=10 * k + 8)
            account(usage + [extra])
        else:
            account(usage)
        if log:
            with open(log, "a") as f:
                f.write("".join(ln + "\n" for ln in lines))
        inflight = mode != "boundary"
        man["transport_abort"] = {
            "cause": env.get("B2_ABORT_CAUSE", "connection"), "error": "TransportFailure: provider.transport",
            "evidence": {"id": item, "files": {}}, "termination": {"in_flight_at_kill": None, "killed": [], "reason": None},
            "gate": {"requests_completed": len(usage), "output_tokens_completed": sum(u[1] for u in usage),
                     "request_usage": usage},
            "session_id": session,
            "in_flight": {"in_flight": inflight, "message_id": extra[0] if inflight else None,
                          "requests_started": len(usage) + (1 if inflight else 0)},
            "cleanup_status": dict(CLEANUP_EXACT), "grade_reports": []}
        man["cleanup_status"] = dict(CLEANUP_EXACT)
        save()
        print(f"TransportAbort: {item}", flush=True)
        return 1

    skew = set(filter(None, env.get("B2_SKEW_ITEMS", "").split(",")))
    aborts = json.loads(env.get("B2_ABORTS") or "{}")
    for k, name in enumerate(names):
        item = f"{a.lang}/{name}"
        if barrier:
            fd, _ = signal(k, "ready")
            os.close(fd)
            if wait(k, "go") == "stop":
                man["hook_stop"] = dict(before_slot=item)
                man["cleanup_status"] = dict(CLEANUP_EXACT)
                save()
                break
        if name in aborts:
            return dnf(item, k, aborts[name])
        session, usage = requests(item, k, name)
        row = FP.build_row(a.model, item, a.seed_base, worker, env.get("STACK_WORKDIR", ""), out, run_id,
                           runtime=man["runtime"])
        row.update(session_id=session, request_usage=usage, stop_reason="completed")
        row["gate"] = dict(row["gate"], requests_completed=len(usage), output_tokens_completed=sum(u[1] for u in usage))
        stalled = a.inject_stall_item == item and a.inject_stall_s is not None
        if stalled:                                       # the lowered stall limit fires: a probe kill at a request boundary,
            ref = golden_row("item_stall_kill")           # the real probe's row shape (P371 golden `item_stall_kill`)
            row.update(passed=False, converged=False, nonconv_kind=ref["nonconv_kind"], nonconv_flags=list(ref["nonconv_flags"]),
                       stop_reason=ref["stop_reason"],
                       termination=dict(ref["termination"], in_flight_at_kill=0,
                                        killed=[dict(k_, pid=os.getpid(), create_time=1.0, argv="opencode run")
                                                for k_ in ref["termination"]["killed"]]))
            row["gate"] = dict(row["gate"], requests_completed_at_kill=len(usage), stop_reason=ref["gate"]["stop_reason"])
        rows.append(row)
        FP._atomic(out, "".join(json.dumps(r) + "\n" for r in rows).encode())
        print(f"{item}: passed={not stalled} nonconv={'stalled' if stalled else None}", flush=True)
        if barrier:
            done = dict(id=item, attempt_id=f"{item}#{a.attempt}.{a.attempt_rerun_index}", passed=not stalled,
                        nonconv_kind="stalled" if stalled else None, evidence={}, receipts=None, final_tree=None)
            fd, _ = signal(k, "done")
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps(done))
            if wait(k, "continue") == "stop":
                stop = Path(f"{base}.item{k}.stop")
                payload = json.loads(stop.read_text() or "{}") if stop.exists() else {}
                man["hook_stop"] = dict(after_slot=item, disposition=payload.get("disposition"))
                man["cleanup_status"] = dict(CLEANUP_EXACT)
                save()
                break
    man["cleanup_status"] = dict(CLEANUP_EXACT)
    save()
    return 0


def run_core(env, argv, *, config=None, hooks=None, extra_env=None, timeout=90):
    """`chain_core.Chain(config, args, ops, timers, log, *, repo, out_root, names, lifecycle_files, campaign, hooks)` (the
    baseline core constructor) over the item-barrier fake probe; `config(cfg)` rewrites the entry's ChainConfig. Returns rc."""
    from bench import chain_core as core
    from bench import chain_ops as co
    t1c = _t1c()
    R = t1c.R
    ops = env["ops"]
    ops.extra_env.update(extra_env or {})
    full = list(argv) + ["--probe", str(PROBE), "--python", sys.executable, "--out-root", str(env["out"]),
                         "--arm-idle-s", "0", "--universe", str(env["uni"]), "--frozen-prompt-date", EPOCH_DATE]
    a = R.parse_args(full)
    cfg = config(R.tg1_config(a)) if config else R.tg1_config(a)
    out = R.resolve_out_root(a, env["wd"])
    out.mkdir(parents=True, exist_ok=True)
    log = co.RunLog(out / "RUNLOG.md", out=env["lines"].append)
    chain = core.Chain(cfg, a, ops, R.Timers(**t1c.TIMERS), log, repo=REPO, out_root=out, names=R.load_universe(a.universe),
                       lifecycle_files=R.lifecycle_files(REPO), campaign=None, hooks=hooks)
    res = {}

    def target():
        try:
            res["rc"] = chain.run()
        except BaseException as e:  # noqa: BLE001
            res["exc"] = e
    th = threading.Thread(target=target, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        ops.cancel()
        th.join(10)
        raise AssertionError("chain did not finish: " + "\n".join(env["lines"][-15:]))
    if "exc" in res:
        raise res["exc"]
    return res["rc"]


def barrier_files(directory):
    return sorted(p.name for p in Path(directory).rglob("*") if ".item" in p.name and not p.name.startswith("."))


def ops_with_metrics_file(ops, path):
    """`ops.worker_metrics()` reads the fake probe's metrics state ($B2_PROBE_METRICS) in the worker's `/metrics` shape."""
    path = Path(path)
    ops.metrics = lambda: json.loads(path.read_text()) if path.exists() else metrics_doc()
    return ops


# ------------------------------------------------------------------------------------------------ the real probe in-process (§2)
def probe_fixture(monkeypatch, tmp_path):
    """The real `run_tg1_probe` entry in-process with the existing mocked tg1 world (`test_tg1_integration.tg_fixture`: fake
    client shell script, mocked worker / router / grader). The fake client is renamed so that no spawned command line
    contains the strings a live GPU run censuses. `f["run"](items, extra=[...])` -> the probe's rc; `f["out"]` the rows."""
    import importlib
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    p = importlib.import_module("run_tg1_probe")
    from bench.tests.test_tg1_integration import tg_fixture
    f = tg_fixture(p, monkeypatch, tmp_path)
    src = Path(os.environ["OPENCODE_PROBE_BIN"])
    dst = tmp_path / "oc-fixture-client"
    src.rename(dst)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(dst))
    f["probe"] = p
    return f


@contextlib.contextmanager
def barrier_answerer(directory, *, ready="go", done="continue"):
    """Answer every `.ready` with `.go` and every `.done` with `.continue` under `directory` (the chain's role,
    `chain_core.barrier_signal`), until the block exits."""
    import time
    halt = threading.Event()

    def loop():
        while not halt.is_set():
            for p in list(Path(directory).glob("*.item*.ready")) + list(Path(directory).glob("*.item*.done")):
                answer = p.with_suffix("." + (ready if p.suffix == ".ready" else done))
                if not answer.exists() and not p.with_suffix(".stop").exists():
                    answer.write_text("")
            time.sleep(0.01)
    th = threading.Thread(target=loop, daemon=True)
    th.start()
    try:
        yield
    finally:
        halt.set()
        th.join(5)


def client_error_events(error_type):
    """A tg1 client stream (the gate's event shape: `test_token_turn_gate.event` / `usage`, every step event with a part id,
    a native error event without one, token_turn_gate.py:326-334): request m1 completed, request m2 started, then the
    client's error event (`provider.invalid-output` = dropped_stream, `provider.transport` = connection; arm_opencode.classify_error)."""
    from bench.tests.test_token_turn_gate import event, usage
    return [event("step_start", "m1"), event("step_finish", "m1", tokens=usage(10, 100)), event("step_start", "m2"),
            {"type": "error", "sessionID": "s1", "error": {"type": error_type, "message": "broken"}}]


ERROR_TYPES = {"drop": "provider.invalid-output", "refuse": "provider.transport"}
ERROR_SESSION = "s1"                                   # the session id the gate's `event` helper stamps


def set_client_error(f, tmp_path, kind):
    """The fixture client (`probe_fixture`) replays `client_error_events` and exits 1 (fixture_probe's canned events / rc
    files, test_opencode_v2_probe.py:115-116) — no malformed leading line."""
    (Path(tmp_path) / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in client_error_events(ERROR_TYPES[kind])))
    (Path(tmp_path) / "rc").write_text("1")


def manifest_of(rows_path):
    return json.loads(Path(rows_path).with_suffix(".manifest.json").read_text())


# ------------------------------------------------------------------------------------------------ v3.2 §16.1 records
def canonical_bytes(doc):
    """§16: the canonical JSON of a record (`sort_keys`, separators `,` `:`, UTF-8)."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def self_hashed(doc):
    """§16: `sha256` = sha256 of the canonical JSON of the record without its `sha256` field."""
    body = {k: v for k, v in doc.items() if k != "sha256"}
    return dict(body, sha256=hashlib.sha256(canonical_bytes(body)).hexdigest())


def write_record(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x") as f:                       # exclusive create
        json.dump(doc, f, sort_keys=True, indent=1)
    return path


WT_PORTABLE = "$STACK_WORKDIR/WT"       # the fixtures' worktree (`chain_env`: `<STACK_WORKDIR>/WT`), portable (§16.7, 1g tail)


def portable(path):
    """A record path field in the portable form (§16.7): `$STACK_WORKDIR/<rel>` when `path` lies under `$STACK_WORKDIR`."""
    wd = os.environ.get("STACK_WORKDIR")
    p = Path(path)
    if wd:
        try:
            return "$STACK_WORKDIR/" + p.relative_to(Path(wd)).as_posix()
        except ValueError:
            pass
    return str(p)


def rehearsal_manifest(out_root, *, off_commit="a" * 40, on_commit="b" * 40, ident=None):
    """post-reveal 3e (designer ruling on §16.8): the manifest records the rehearsal's frozen prompt date and the probe
    identity keys (`p426_freeze rehearsal --frozen-prompt-date`, `ops.identity(off_worktree)`)."""
    ident = ident or {k: v8_base()[k] for k in ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256")}
    return self_hashed(dict(kind="p426_rehearsal", off_commit=off_commit, on_commit=on_commit, off_worktree=WT_PORTABLE,
                            on_worktree=WT_PORTABLE, out_root=portable(out_root), rehearsal=True, created="2026-10-27T00:00:00Z",
                            frozen_prompt_date=EPOCH_DATE, **ident))


def v8_base(**over):
    doc = dict(kind="p426_v8_base", build="S'", off_commit="a" * 40, on_commit="b" * 40, off_worktree=WT_PORTABLE,
               on_worktree=WT_PORTABLE, gitlinks={"mlx_vlm": BASE_GITLINKS["src/mlx-vlm"], "mlx_serve": BASE_GITLINKS["src/mlx-serve"]},
               production_ref="c" * 40, probe_code_sha256=HEX9, scaffold_policy_sha256="c" * 64,
               generation_identity_sha256="d" * 64, pins_sha256="e" * 64, grader_image_id="sha256:" + "f" * 64,
               frozen_prompt_date=EPOCH_DATE, pilot_deadline_s=4000.0, settle_bound_s=900.0, generic_pred_s=250,
               volatile_env_keys=["_", "OLDPWD", "PWD", "SHLVL", "TERM_SESSION_ID", "SECURITYSESSIONID", "__CF*"],
               r1_env_difference=[], rehearsal_manifest_sha256="1" * 64, stack_suite_receipt_sha256="2" * 64,
               created="2026-10-27T00:00:00Z")
    doc.update(over)
    return self_hashed(doc)


def timeout_amendment(v8_path, **over):
    """`v8_base_sha256` = the `sha256` (self-hash) field of `v8_base.json` in the same directory (§16.1, v3.2 ruling)."""
    doc = dict(kind="p426_timeout_amendment", v8_base_sha256=json.loads(Path(v8_path).read_text())["sha256"], w_python_s=1300.0, w_go_s=900.0,
               leg_deadline_s={"s1": 70000.0, "s2": 70000.0, "reload": 12000.0}, settle_bound_s=900.0,
               created="2026-10-27T00:00:00Z")
    doc.update(over)
    return self_hashed(doc)


def record_dir(tmp_path):
    """A record directory as v8 lays it out: `v8_base.json` + `timeout_amendment.json`. Returns (v8 path, amendment path)."""
    d = Path(tmp_path) / "records"
    v8 = write_record(d / "v8_base.json", v8_base())
    am = write_record(d / "timeout_amendment.json", timeout_amendment(v8))
    return v8, am


# ------------------------------------------------------------------------------------------------ real scored-fail rows (§4.3)
GOLDEN = BENCH / "bench/tests/p371_baseline/golden"            # rows recorded from the real probe (P371 baseline A14)


def golden_row(name):
    """The first row of a P371 golden run (`item_stall_kill` = a probe kill at a request boundary: `nonconv_kind`
    `stalled`, `gate.requests_completed_at_kill`, `termination.in_flight_at_kill`; `item_client_inactivity`:
    `requests_completed_at_kill` null)."""
    d = json.loads((GOLDEN / f"{name}.json").read_text())
    runs = d["runs"] if isinstance(d["runs"], list) else list(d["runs"].values())
    return json.loads(json.dumps(runs[0]["rows"][0]))


def summary(**kw):
    """The `/metrics` summary dict (`metrics_doc(...)["summary"]`, generation.py:725-740)."""
    return metrics_doc(**kw)["summary"]


def window(lines):
    """A log window's bytes (one `\\n`-terminated line each, as the logger writes them)."""
    return "".join(ln + "\n" for ln in lines).encode("utf-8")


def counters_after(before, usage_like, *, failed=0, extra_started=0, decode_s=0.0):
    """The worker summary after `usage_like` ([.., out, prompt, ..] per completed request) on top of `before`."""
    return summary(started=before["requests_started"] + len(usage_like) + failed + extra_started,
                   completed=before["requests_completed"] + len(usage_like), failed=before["requests_failed"] + failed,
                   prompt_total=before["prompt_tokens_total"] + sum(u[2] for u in usage_like),
                   generated_total=before["generated_tokens_total"] + sum(u[1] for u in usage_like),
                   decode_s=decode_s)


# ------------------------------------------------------------------------------------------------ §4 abort manifest / A4 receipt
def abort_manifest(usage, *, in_flight=None, cause="connection", session="ses_dnf00000000000000000000000"):
    """The probe's abort manifest in P426 mode (§16.1; arm_runner._main's `transport_abort` stamp, the gate report inside it
    as for m64)."""
    return {"transport_abort": {"cause": cause, "error": "TransportFailure: provider.transport", "evidence": None,
                                "session_id": session, "in_flight": {"in_flight": in_flight is not None, "message_id": in_flight,
                                                                   "requests_started": len(usage) + (in_flight is not None)},
                                "termination": {"in_flight_at_kill": None, "killed": [], "reason": None},
                                "gate": {"request_usage": [list(u) for u in usage], "requests_completed": len(usage)},
                                "cleanup_status": dict(CLEANUP_EXACT)},
            "cleanup_status": dict(CLEANUP_EXACT)}


def a4_gate_doc(receipt, anon):
    """`<workdir>/gate.json` as `scripts/session_pinning_gate.py:main` writes it (lines 284-304): the A4 opencode result and
    A6's three bare requests `{cached, prompt, session}` (lines 47-60)."""
    return {"model": MODEL, "started": "2026-10-27T00:00:00", "opencode_version": "2.0.20", "A4_opencode": receipt,
            "A6_bare_anonymous": {"pass": True, "requests": [{"cached": c, "prompt": p, "session": s} for s, c, p in anon]}}


def a4_receipt(requests):
    """`a4_v2_latest.json` as `scripts/session_pinning_gate.py:_a4_opencode_v2` writes it (lines 154-206): two turns of
    `{rc, requests: [{session, cached, prompt}]}` in one `ses_*` session."""
    sid = requests[0][0]
    turns = [{"rc": 0, "requests": [{"session": s, "cached": c, "prompt": p} for s, c, p in requests[:2]]},
             {"rc": 0, "requests": [{"session": s, "cached": c, "prompt": p} for s, c, p in requests[2:]]}]
    return {"pass": True, "model": MODEL, "opencode_version": "2.0.20", "session_id": sid, "sessions": [sid],
            "turns": turns, "cross_process_reuse": True}


# ------------------------------------------------------------------------------------------------ v3.2 §16.1 receipts
def LOADED_IMAGES(wt):
    """The native libraries a worker loads (§6.4: `libmlx.dylib` and `mlx.metallib`, mlx's wheel layout `mlx/lib/`)."""
    lib = f"{wt}/.venv/lib/python3.12/site-packages/mlx/lib"
    return [{"path": f"{lib}/libmlx.dylib", "sha256": "9" * 64}, {"path": f"{lib}/mlx.metallib", "sha256": "7" * 64}]


def pinned_snapshots(arm):
    """`{target, drafter}` as `ChainOps.snapshot_hashes` reports them: the fork's `pins.json` entries for MODEL
    (`{hf_path, revision, files}`); the drafter ON only."""
    pin = json.loads(PINS.read_text())[MODEL]
    return {"target": pin["target"], "drafter": pin["drafter"] if arm == "on" else None}


def arm_receipt_doc(arm="off", **over):
    """An arm-equality receipt in the §16.1 shape; ON = OFF + the §6.3 argv delta + the drafter snapshot."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:          # the worker argv mlx-serve builds for the entry, <WT> canonicalized
        reg = Path(d) / "main_models.yaml"
        reg.write_text(registry_text((MODEL,), on=(MODEL,) if arm == "on" else ()))
        worker = [x.replace(str(REPO), "<WT>") for x in served_worker_argv(reg, MODEL)]
    env = {"HOME": "<HOME>", "MLX_SERVE_CONFIG": "<WT>/main_models.yaml", "TMPDIR": "<OUT>/tmp", "PWD": "<volatile>",
           "SHLVL": "<volatile>", "MLX_VLM_CACHE_SESSION_MAX": "1"}
    doc = dict(argv={"router": ["<WT>/.venv/bin/mlx-serve", "start"], "worker": worker},
               env={"router": dict(env), "worker": dict(env), "probe": dict(env, STACK_WORKDIR="<STACK_WORKDIR>")},
               credential_keys={"router": ["HF_TOKEN"], "worker": ["HF_TOKEN"], "probe": ["HF_TOKEN"]},   # C238: keys only
               interpreters=[{"path": "<WT>/.venv/bin/python", "inventory_sha256": "8" * 64,
                              "editables": {"mlx-vlm": {"tree": "<WT>/src/mlx-vlm", "gitlink": BASE_GITLINKS["src/mlx-vlm"],
                                                        "clean": True}}}],
               loaded_images=LOADED_IMAGES("<WT>"),
               probe_entry="<WT>/benchmark/run_tg1_probe.py",
               snapshots=pinned_snapshots(arm))                  # 1i: the `pins.json` shape {hf_path, revision, files}
    doc.update(over)
    return self_hashed(doc)


# ------------------------------------------------------------------------------------------------ v3.2 harvest legs
def not_started_leg_root(wd, leg="tg1-p426-off-pilot", attempt=1):
    """The root of an attempt whose entry check failed (§5.1 NOT_STARTED): the sequencer's leg record (§16.1) and the
    chain's RUNLOG; nothing launched."""
    root = Path(wd) / "p426" / "wave2" / f"{leg}.a{attempt}"
    root.mkdir(parents=True)
    # post-reveal 3h (§16.8 after the strict verify round 1): the leg record is immutable, so it carries its self-hash
    (root / "leg.json").write_text(json.dumps(self_hashed({"leg": leg, "attempt": attempt, "state": "NOT_STARTED",
                                                           "class": "NOT_STARTED", "reason": "power: 96 W", "chain_rc": 2,
                                                           "started": "2026-10-27T00:00:00Z",
                                                           "ended": "2026-10-27T00:00:01Z"})))
    (root / "RUNLOG.md").write_text("REFUSED: power: 96 W\n")
    return root


def occurrence(session, language, item, seed, arm, position=0):
    """A §5.5 occurrence record. post-reveal 3d (§16.8): `occurrence` = the 0-based position of the item in its (session,
    language) order in that leg's frozen schedule (it was a repeat count)."""
    return dict(session=session, language=language, item=item, seed=seed, arm_of_dnf=arm, occurrence=position)


# ------------------------------------------------------------------------------------------------ the P426 leg (§16.4)
OFF_COMMIT, ON_COMMIT = "a" * 40, "b" * 40
PINS = REPO / "src/mlx-vlm/dev/p369_phase2/pins.json"      # the fork's snapshot pins (Wave 1's B10)
GATE_JSON = "c102a/gate.json"                              # session_pinning_gate.py:267, 299: `--workdir` default under $STACK_WORKDIR


def served_worker_argv(registry_path, model):
    """The worker argv mlx-serve builds from the entry (§6.3): `mlx_serve.config._load` + `process_manager._build_command`
    (src/mlx-serve/src/mlx_serve/process_manager.py:115-191) on the given registry file."""
    from mlx_serve import config, process_manager as pm
    old = config._CONFIG_PATH
    config._CONFIG_PATH = Path(registry_path)
    try:
        cfg = config._load()[0][model]
    finally:
        config._CONFIG_PATH = old
    return pm._build_command(cfg)


def a4_gate_writer(ops, wd, log, account):
    """The A4 gate as `ChainOps.a4_gate` runs it (chain_ops.py:591-612): `session_pinning_gate.py` appends its requests to the
    worker log (A4 opencode's 4-request `ses_*` session, then A6's 3 `anon:*` requests, lines 288-293), writes
    `session_gate/a4_v2_latest.json` (lines 154-217) and `<workdir>/gate.json` (lines 284-304); returns the receipt path."""
    def gate(model, tag, **kw):
        ops.calls.append(("a4_gate", model))
        n = len([c for c in ops.calls if c[0] == "a4_gate"])
        sid = f"ses_a4{n:024d}"
        ses = [(sid, 0, 9000), (sid, 8800, 9100), (sid, 0, 9300), (sid, 9200, 9400)]
        anon = [(f"anon:{n:04d}{i:04d}", 2600 if i == 2 else 0, 3100 + i) for i in range(3)]
        lines = []
        for j, (s, c, p) in enumerate(ses + anon):
            lines += [started_line(at=ts(200 + 2 * j)),
                      completed_line(at=ts(201 + 2 * j), session=s, prompt_tokens=p, generated_tokens=30, cached_tokens=c)]
        with open(log, "a") as f:
            f.write("".join(ln + "\n" for ln in lines))
        account([[s, 30, p, 0] for s, c, p in ses + anon])
        rec = dict(a4_receipt(ses), run_id=f"a4-v2-{n}")
        path = Path(wd) / "session_gate/a4_v2_latest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, indent=2) + "\n")
        g = Path(wd) / GATE_JSON
        g.parent.mkdir(parents=True, exist_ok=True)
        g.write_text(json.dumps({"model": model, "A4_opencode": rec, "A6_bare_anonymous": {
            "pass": True, "requests": [{"cached": c, "prompt": p, "session": s} for s, c, p in anon]}}, indent=1))
        return str(path)
    return gate


def p426_world(tmp_path, monkeypatch, *, arm="off", universe=None, out_name=None, rehearsal=False):
    """A hermetic positive `--p426` leg (§16.4): FakeOps with the §16.2 / §16.4 seams, the item-barrier fake probe writing
    the worker log and metrics, records written with the §16.1 recipe, and an injected campaign helper."""
    on = arm == "on"
    env = chain_env(tmp_path, monkeypatch, registry=registry_text((MODEL,), on=(MODEL,) if on else ()), universe=universe)
    ops, wd = env["ops"], Path(tmp_path)
    wt = Path(ops.overlay).parent
    commit = ON_COMMIT if on else OFF_COMMIT
    pins = wt / "src/mlx-vlm/dev/p369_phase2/pins.json"
    pins.parent.mkdir(parents=True, exist_ok=True)
    pins.write_bytes(PINS.read_bytes())
    log, metrics = ops.server_log_path(), wt / "metrics.json"
    ops_with_metrics_file(ops, metrics)
    state = dict(clean=True, head=commit, worker_shift=0)

    def account(served, failed=0):
        m = json.loads(metrics.read_text()) if metrics.exists() else metrics_doc()
        s = m["summary"]
        prev_d = s["generated_tokens_total"] / s["avg_decode_tok_s"] if s["avg_decode_tok_s"] else 0.0
        metrics.write_text(json.dumps(metrics_doc(
            started=s["requests_started"] + len(served) + failed, completed=s["requests_completed"] + len(served),
            failed=s["requests_failed"] + failed, prompt_total=s["prompt_tokens_total"] + sum(u[2] for u in served),
            generated_total=s["generated_tokens_total"] + sum(u[1] for u in served),
            decode_s=prev_d + sum(u[1] for u in served) / 50.0)))
    ops.worktree_state = lambda *a: dict(head=state["head"], clean=state["clean"], gitlinks=dict(BASE_GITLINKS))
    ops.last_leg_end = lambda: None
    ops.a4_gate = a4_gate_writer(ops, wd, log, account)
    original_ident = ops.worker_ident

    def worker_ident(model):
        r = original_ident(model)
        return dict(r, pid=r["pid"] + state["worker_shift"]) if r else r
    ops.worker_ident = worker_ident
    router_argv = [str(wt / ".venv/bin/mlx-serve"), "start"]

    def proc_argv(pid):
        if pid == 1:                                          # FakeOps.start_router returns pid 1
            return list(router_argv)
        if ops.ident and pid == ops.ident["pid"]:
            return served_worker_argv(ops.overlay, MODEL)
        return [sys.executable, str(PROBE)]
    ops.proc_argv = proc_argv
    ops.proc_environ = lambda pid: {"HOME": str(wd / "home"), "MLX_SERVE_CONFIG": str(wt / "main_models.yaml"),
                                    "STACK_WORKDIR": str(wd), "PWD": str(wt), "SHLVL": "2", "HF_TOKEN": FAKE_SECRET_40,
                                    "MLX_VLM_CACHE_SESSION_MAX": "1", "TOKENIZERS_PARALLELISM": "false"}
    ops.interpreter_inventory = lambda pid: {"path": str(wt / ".venv/bin/python"), "inventory_sha256": "8" * 64,
                                             "editables": {"mlx-vlm": {"tree": str(wt / "src/mlx-vlm"),
                                                                       "gitlink": BASE_GITLINKS["src/mlx-vlm"], "clean": True}}}
    ops.loaded_images = lambda pid: LOADED_IMAGES(wt)          # 1i: both libraries of §6.4
    ops.snapshot_hashes = lambda model: pinned_snapshots(arm)
    # §16.5 / §16.6 seams: the expected worker argv is mlx-serve's own; the after-load census sees no other process; the
    # owned worker's identity is `(pid, create_time(pid))` with its own start time (the router's is 1.0, its pid 1)
    ops.expected_worker_argv = lambda registry_path, model: served_worker_argv(registry_path, model)
    ops.busy_procs = lambda: []
    ops.descendants = lambda pid: set()
    ops.create_time = lambda pid: ops.ident["create_time"] if ops.ident and pid == ops.ident["pid"] else 1.0
    ident = fake_identity()
    recs = wd / "records"
    v8 = write_record(recs / "v8_base.json", v8_base(
        off_worktree=portable(wt), on_worktree=portable(wt), probe_code_sha256=ident["probe_code_sha256"],
        scaffold_policy_sha256=ident["scaffold_policy_sha256"], generation_identity_sha256=ident["generation_identity_sha256"],
        pins_sha256=sha256_file(pins), frozen_prompt_date=EPOCH_DATE))
    am = write_record(recs / "timeout_amendment.json", timeout_amendment(v8))
    reh_root = wd / "p426/rehearsal" / f"tg1-p426-rehearsal-{arm}.a1"
    reh = write_record(recs / "rehearsal.json", rehearsal_manifest(reh_root, ident={
        k: ident[k] for k in ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256")}))   # 3e: the world's
    out = reh_root if rehearsal else wd / "p426/wave2" / (out_name or f"tg1-p426-{arm}-pilot.a1")
    env.update(out=out, wt=wt, log=log, metrics=metrics, state=state, commit=commit, arm=arm, ident=ident,
               records=dict(v8=v8, am=am, reh=reh))
    ops.extra_env.update(barrier_env(ops.state, log=log, metrics=metrics), FAKE_SERVED_REGISTRY=str(ops.overlay))
    loader = ops.load

    def load(model):                     # 2d: the launch environment carries no arm-specific key (`make_ops.load` adds
        ident = loader(model)            # FAKE_REGISTRY_SHA for the legacy fakes; the B2 probe hashes the served file)
        ops.extra_env.pop("FAKE_REGISTRY_SHA", None)
        return ident
    ops.load = load
    return env


def p426_argv(env, mode=("pilot",), *, record=None, extra=()):
    """§6.7's common flags for the world's leg + the test runner's probe / python / universe (C238: no key, no `--hmac-fd`).
    Returns (argv, None); the second value is kept for the callers' `rfd=` (always None now)."""
    on = env["arm"] == "on"
    rec = record or (env["records"]["reh"] if "--rehearsal" in mode else
                     env["records"]["v8"] if mode[0] == "pilot" else env["records"]["am"])
    argv = list(mode) + ["--p426", "--models", MODEL, "--predictor", "mtp" if on else "off", "--out-root", str(env["out"]),
                         "--probe-code-sha", env["ident"]["probe_code_sha256"],
                         "--policy-sha", env["ident"]["scaffold_policy_sha256"], "--frozen-prompt-date", EPOCH_DATE,
                         "--campaign-core", env["commit"], "--frozen-record", str(rec), "--probe", str(PROBE),
                         "--python", sys.executable, "--universe", str(env["uni"]), "--arm-idle-s", "0", *extra]
    return argv, None


def fake_campaign(commit):
    from bench.tests.test_p371_chain_core import FakeCampaign
    now = {"probe_closure_sha256": "a" * 64, "chain_closure_sha256": "b" * 64}
    return FakeCampaign(at=dict(tag=commit, commit=commit, **now), now=now)


def run_p426(env, argv, *, rfd=None, timeout=120, helper=None):
    """`run_tg1_chain.main(argv, ops=<FakeOps>, timers=…, log_out=…, campaign=<fake>)` in a thread; rc, or the exit code of a
    refusal (`REFUSED: …`, SystemExit 2)."""
    t1c = _t1c()
    R = t1c.R
    res = {}

    def target():
        import io
        from contextlib import redirect_stderr
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                res["rc"] = R.main(list(argv), ops=env["ops"], timers=R.Timers(**t1c.TIMERS), log_out=env["lines"].append,
                                   campaign=fake_campaign(env["commit"]))
        except SystemExit as e:
            res["rc"] = e.code if isinstance(e.code, int) else 2
            env["lines"].append(str(e.args[0]) if e.args else "")
        except BaseException as e:  # noqa: BLE001
            res["exc"] = e
        finally:
            env["lines"].extend(err.getvalue().splitlines())
    th = threading.Thread(target=target, daemon=True)
    th.start()
    if helper:
        threading.Thread(target=helper, daemon=True).start()
    th.join(timeout)
    if rfd is not None:
        try:
            os.close(rfd)
        except OSError:
            pass
    if th.is_alive():
        env["ops"].cancel()
        th.join(10)
        raise AssertionError("chain did not finish: " + "\n".join(env["lines"][-15:]))
    if "exc" in res:
        raise res["exc"]
    return res["rc"]


# ------------------------------------------------------------------------------------------------ simultaneous start (§9)
def simultaneous(*fns, timeout=60):
    """Run `fns` in threads released by one barrier; returns their results (or exceptions) in order."""
    bar = threading.Barrier(len(fns))
    res = [None] * len(fns)

    def wrap(i, f):
        bar.wait()
        try:
            res[i] = f()
        except BaseException as e:  # noqa: BLE001
            res[i] = e
    ths = [threading.Thread(target=wrap, args=(i, f), daemon=True) for i, f in enumerate(fns)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(timeout)
    return res


if __name__ == "__main__":                  # the item-barrier fake probe (`--probe <this file>`)
    sys.path.insert(0, str(BENCH))
    sys.exit(probe_main(sys.argv[1:]))
